"""Central Dentist LangGraph orchestration pipeline.

Coordinates the end-to-end conversation flow:
load_auth_context -> nlp_understanding -> plan_retrieval -> retrieve_patient_data ->
retrieve_conversation_context -> retrieve_optional_knowledge -> build_grounded_context ->
qwen_or_direct_answer -> validate_response -> persist_turn -> END

Zero Hugging Face dependencies. Pure LangGraph StateGraph.
Phase 12B: Hard latency budgets, stage telemetry, request trace IDs, and fail-fast cancellation.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import Any, Optional, TypedDict
from uuid import UUID

from langgraph.graph import END, START, StateGraph

from orchestrator.central_dentist.fast_path import (
    format_date_natural,
    format_fast_path_response,
)
from orchestrator.central_dentist.knowledge import lookup_dental_knowledge
from orchestrator.central_dentist.nlp import (
    CentralDentistIntent,
    analyze_message,
    has_personal_record_reference,
    is_conversational_follow_up,
)
from orchestrator.central_dentist.prompts import (
    CENTRAL_DENTIST_SYSTEM_PROMPT,
    audit_chat_prompt_size,
    build_grounded_context,
    clean_response,
    get_context_sources,
)
from orchestrator.central_dentist.retrieval import (
    AppointmentSummary,
    ScanSummary,
    retrieve_latest_screening,
    retrieve_patient_appointments,
    retrieve_patient_dentist_info,
    retrieve_scan_comparison,
    retrieve_scan_history,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Central Dentist LangGraph State
# ---------------------------------------------------------------------------

class CentralDentistState(TypedDict, total=False):
    """Structured state container for the Central Dentist LangGraph."""

    # --- Trace / Request Identity ---
    request_id: str

    # --- Input ---
    user_id: str  # Authenticated patient UUID string
    conversation_id: str | None
    message: str
    locale: str

    # --- NLP & Intent ---
    normalized_message: str
    intent: str
    entities: dict[str, Any]
    temporal_references: dict[str, Any]
    active_finding: str | None
    is_fast_path: bool
    fast_path_type: str | None

    # --- Retrieval Plan ---
    retrieval_plan: dict[str, bool]

    # --- Retrieved Patient Context ---
    latest_scan: Optional[ScanSummary]
    previous_scan: Optional[ScanSummary]
    scan_history: list[ScanSummary]
    appointments: list[AppointmentSummary]
    dentist_info: Optional[dict[str, Any]]
    knowledge_context: Optional[str]
    recent_turns: list[dict[str, str]]
    context_sources: list[str]

    # --- Generation & Validation ---
    grounded_context: str
    draft_response: Optional[str]
    final_response: Optional[str]

    # --- Observability ---
    latency_metadata: dict[str, float]
    error_state: Optional[str]

    # --- Internal Dependencies ---
    _db_session: Any
    _gateway: Any


# ---------------------------------------------------------------------------
# Fallback generator
# ---------------------------------------------------------------------------

def _build_deterministic_fallback(state: CentralDentistState) -> str:
    """Useful, grounded deterministic fallback if Qwen times out or fails."""
    intent_val = state.get("intent")
    user_msg = state.get("message", "").lower()

    # 1. General Oral Health fallback
    if intent_val == CentralDentistIntent.GENERAL_ORAL_HEALTH.value or any(
        k in user_msg
        for k in (
            "brush",
            "floss",
            "mouthwash",
            "stain",
            "sensitive",
            "bleed",
            "tartar",
            "cavity",
            "breath",
            "checkup",
        )
    ):
        knowledge = lookup_dental_knowledge(user_msg, finding_key=state.get("active_finding"))
        if knowledge:
            return knowledge

    # 2. Patient Scan / Report fallback
    latest_scan = state.get("latest_scan")
    if latest_scan and (
        intent_val
        in (
            CentralDentistIntent.SCAN_LATEST.value,
            CentralDentistIntent.REPORT_QUESTION.value,
            CentralDentistIntent.EXPLAIN_FINDING.value,
            CentralDentistIntent.EXPLAIN_CONFIDENCE.value,
            CentralDentistIntent.SCAN_COMPARE.value,
            CentralDentistIntent.SCAN_HISTORY.value,
        )
        or any(
            k in user_msg
            for k in (
                "scan",
                "report",
                "finding",
                "cavity",
                "tartar",
                "discoloration",
                "urgency",
                "confidence",
            )
        )
    ):
        date_str = format_date_natural(latest_scan.created_at)
        verdict = (latest_scan.verdict or "oral screening findings").replace("_", " ")
        conf_str = ""
        if latest_scan.confidence is not None:
            pct = (
                int(round(latest_scan.confidence * 100))
                if latest_scan.confidence <= 1.0
                else int(round(latest_scan.confidence))
            )
            conf_str = f" at {pct}% visual confidence"
        urgency = (latest_scan.urgency_level or "routine").lower()
        timeframe = (
            "a routine dental evaluation"
            if urgency == "routine"
            else f"a dental evaluation {urgency}"
        )
        return (
            f"Your latest screening was on {date_str}. It flagged {verdict}{conf_str} "
            f"and recommended {timeframe}."
        )

    # 3. Appointments fallback
    appointments = state.get("appointments")
    if appointments and (
        intent_val
        in (
            CentralDentistIntent.APPOINTMENT_STATUS.value,
            CentralDentistIntent.DENTIST_INFORMATION.value,
        )
        or "appointment" in user_msg
        or "dentist" in user_msg
    ):
        appt = appointments[0]
        return (
            f"You have an appointment requested with {appt.dentist_name}. "
            f"Its current status is {appt.status}."
        )

    # If user asked about scan but has no scans recorded yet
    if any(k in user_msg for k in ("scan", "report")):
        return "I don't see any completed screening scans in your record yet to review."

    # 4. Clean natural fallback without exposing providers, models, or "AI service"
    return (
        "I couldn't complete that answer just now. Please ask your question again, "
        "or let me know if you need help with your scan results or appointments."
    )


# ---------------------------------------------------------------------------
# Node 1: load_auth_context
# ---------------------------------------------------------------------------

def load_auth_context(state: CentralDentistState) -> dict[str, Any]:
    """Validate authenticated identity and initialize telemetry."""
    req_id = state.get("request_id") or "chat_unknown"
    t0 = time.perf_counter()
    user_id = state.get("user_id")
    if not user_id:
        logger.warning("[CENTRAL_DENTIST][%s] load_auth_context: unauthenticated", req_id)
        return {
            "error_state": "unauthenticated",
            "latency_metadata": {"chat.start_time": t0},
        }

    auth_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    logger.info("[CENTRAL_DENTIST][%s] auth_done ms=%.1f", req_id, auth_ms)

    return {
        "latency_metadata": {
            "chat.start_time": t0,
            "chat.auth_ms": auth_ms,
        },
        "locale": state.get("locale", "en"),
    }


# ---------------------------------------------------------------------------
# Node 2: nlp_understanding
# ---------------------------------------------------------------------------

def nlp_understanding(state: CentralDentistState) -> dict[str, Any]:
    """Run lightweight deterministic NLP for intent, entities, and temporal refs."""
    req_id = state.get("request_id") or "chat_unknown"
    t0 = time.perf_counter()
    raw_message = state.get("message", "")
    active_finding = state.get("active_finding")
    has_recent_scan = bool(state.get("latest_scan") or state.get("recent_turns"))

    nlp_res = analyze_message(
        raw_message,
        active_finding=active_finding,
        has_recent_scan_context=has_recent_scan,
    )

    nlp_duration_ms = (time.perf_counter() - t0) * 1000.0
    latency = dict(state.get("latency_metadata", {}))
    latency["chat.nlp_ms"] = round(nlp_duration_ms, 2)
    logger.info("[CENTRAL_DENTIST][%s] nlp_done ms=%.1f", req_id, round(nlp_duration_ms, 2))

    return {
        "normalized_message": nlp_res.normalized_message,
        "intent": nlp_res.intent.value,
        "entities": nlp_res.entities,
        "temporal_references": nlp_res.temporal_references,
        "active_finding": nlp_res.finding_reference or active_finding,
        "is_fast_path": nlp_res.is_fast_path_candidate,
        "fast_path_type": nlp_res.fast_path_type,
        "latency_metadata": latency,
    }


# ---------------------------------------------------------------------------
# Node 3: plan_retrieval
# ---------------------------------------------------------------------------

def plan_retrieval(state: CentralDentistState) -> dict[str, Any]:
    """Formulate query-aware retrieval plan to fetch only required domain data."""
    intent_val = state.get("intent", CentralDentistIntent.UNKNOWN.value)
    user_msg = state.get("message", "")
    has_record_ref = has_personal_record_reference(user_msg)

    plan = {
        "need_latest_scan": False,
        "need_scan_compare": False,
        "need_scan_history": False,
        "need_appointments": False,
        "need_dentist_info": False,
        "need_knowledge": False,
    }

    if intent_val == CentralDentistIntent.SCAN_LATEST.value:
        plan["need_latest_scan"] = True
    elif intent_val == CentralDentistIntent.SCAN_COMPARE.value:
        plan["need_scan_compare"] = True
    elif intent_val == CentralDentistIntent.SCAN_HISTORY.value:
        plan["need_scan_history"] = True
    elif intent_val in (
        CentralDentistIntent.EXPLAIN_FINDING.value,
        CentralDentistIntent.EXPLAIN_CONFIDENCE.value,
    ):
        plan["need_latest_scan"] = True
        plan["need_knowledge"] = True
    elif intent_val == CentralDentistIntent.APPOINTMENT_STATUS.value:
        plan["need_appointments"] = True
    elif intent_val == CentralDentistIntent.DENTIST_INFORMATION.value:
        plan["need_dentist_info"] = True
        plan["need_appointments"] = True
    elif intent_val == CentralDentistIntent.REPORT_QUESTION.value:
        plan["need_latest_scan"] = True
    elif intent_val == CentralDentistIntent.SYMPTOM_QUESTION.value:
        if has_record_ref:
            plan["need_latest_scan"] = True
        plan["need_knowledge"] = True
    elif intent_val in (
        CentralDentistIntent.GENERAL_ORAL_HEALTH.value,
        CentralDentistIntent.DENTAL_KNOWLEDGE.value,
    ):
        plan["need_knowledge"] = True
        if has_record_ref:
            plan["need_latest_scan"] = True
    elif intent_val == CentralDentistIntent.FOLLOW_UP_REFERENCE.value:
        plan["need_latest_scan"] = True
        plan["need_knowledge"] = True
    elif intent_val == CentralDentistIntent.GREETING.value:
        # Greetings do not need heavy DB retrieval
        pass
    else:
        # Default unknown: ONLY grab latest scan if user explicitly asked about their records/scans!
        if has_record_ref:
            plan["need_latest_scan"] = True

    return {"retrieval_plan": plan}


# ---------------------------------------------------------------------------
# Node 4: retrieve_patient_data
# ---------------------------------------------------------------------------

async def retrieve_patient_data(state: CentralDentistState) -> dict[str, Any]:
    """Execute tenant-scoped database queries using the authenticated patient UUID."""
    req_id = state.get("request_id") or "chat_unknown"
    t0 = time.perf_counter()
    session = state.get("_db_session")
    user_id_str = state.get("user_id")

    if not session or not user_id_str:
        return {
            "latest_scan": state.get("latest_scan"),
            "previous_scan": state.get("previous_scan"),
            "scan_history": state.get("scan_history", []),
            "appointments": state.get("appointments", []),
            "dentist_info": state.get("dentist_info"),
        }

    patient_uuid = UUID(user_id_str)
    plan = state.get("retrieval_plan", {})

    latest_scan = state.get("latest_scan")
    previous_scan = state.get("previous_scan")
    scan_history = list(state.get("scan_history", []))
    appointments = list(state.get("appointments", []))
    dentist_info = state.get("dentist_info")

    from orchestrator.config import settings

    try:
        async with asyncio.timeout(settings.chat_retrieval_timeout_seconds):
            if plan.get("need_scan_compare"):
                latest_scan, previous_scan = await retrieve_scan_comparison(
                    session, patient_uuid
                )
            elif plan.get("need_latest_scan"):
                latest_scan = await retrieve_latest_screening(session, patient_uuid)

            if plan.get("need_scan_history"):
                scan_history = await retrieve_scan_history(session, patient_uuid, limit=5)
                if not latest_scan and scan_history:
                    latest_scan = scan_history[0]

            if plan.get("need_appointments") or plan.get("need_dentist_info"):
                appointments = await retrieve_patient_appointments(
                    session, patient_uuid, limit=3
                )

            if plan.get("need_dentist_info"):
                dentist_info = await retrieve_patient_dentist_info(session, patient_uuid)
    except Exception as exc:
        logger.warning(
            "[CENTRAL_DENTIST][%s] retrieve_patient_data timeout/warning: %s", req_id, exc
        )

    retrieval_ms = (time.perf_counter() - t0) * 1000.0
    latency = dict(state.get("latency_metadata", {}))
    latency["chat.retrieval_ms"] = round(retrieval_ms, 2)
    logger.info("[CENTRAL_DENTIST][%s] retrieval_done ms=%.1f", req_id, round(retrieval_ms, 2))

    return {
        "latest_scan": latest_scan,
        "previous_scan": previous_scan,
        "scan_history": scan_history,
        "appointments": appointments,
        "dentist_info": dentist_info,
        "latency_metadata": latency,
    }


# ---------------------------------------------------------------------------
# Node 5: retrieve_conversation_context
# ---------------------------------------------------------------------------

async def retrieve_conversation_context(state: CentralDentistState) -> dict[str, Any]:
    """Retrieve recent messages and track active contextual references."""
    req_id = state.get("request_id") or "chat_unknown"
    t0 = time.perf_counter()
    session = state.get("_db_session")
    conv_id_str = state.get("conversation_id")
    user_id_str = state.get("user_id")

    recent_turns: list[dict[str, str]] = list(state.get("recent_turns", []))
    active_finding = state.get("active_finding")

    # Only query DB if recent_turns was not already passed in from caller
    if not recent_turns and session and conv_id_str and user_id_str:
        try:
            from orchestrator.config import settings
            from orchestrator.repositories import ConversationRepository

            async with asyncio.timeout(settings.chat_retrieval_timeout_seconds):
                repo = ConversationRepository(session)
                conv_id = UUID(conv_id_str)
                patient_id = UUID(user_id_str)

                conv = await repo.get_owned(conv_id, patient_id)
                if conv:
                    messages = await repo.list_messages(conv_id, newest_first=True, limit=10)
                    for msg in reversed(messages):
                        recent_turns.append({"role": msg.role, "content": msg.content})
        except Exception as exc:
            logger.warning(
                "[CENTRAL_DENTIST][%s] Conversation history retrieval failed: %s", req_id, exc
            )

    # If no active finding in current message, resolve from prior turn only for follow-ups
    user_msg = state.get("message", "")
    intent_val = state.get("intent")
    if not intent_val and user_msg:
        from orchestrator.central_dentist.nlp import classify_intent
        inferred_intent, _ = classify_intent(
            user_msg,
            active_finding=active_finding,
            has_recent_scan_context=bool(state.get("latest_scan") or recent_turns),
        )
        intent_val = inferred_intent.value
    elif not intent_val:
        intent_val = CentralDentistIntent.UNKNOWN.value

    is_followup = (
        intent_val == CentralDentistIntent.FOLLOW_UP_REFERENCE.value
        or is_conversational_follow_up(user_msg)
    )
    is_standalone_dental = intent_val in (
        CentralDentistIntent.GENERAL_ORAL_HEALTH.value,
        CentralDentistIntent.DENTAL_KNOWLEDGE.value,
    )

    if not is_standalone_dental and is_followup:
        if not active_finding and recent_turns:
            for turn in reversed(recent_turns):
                if turn.get("role") == "assistant":
                    content = (turn.get("content") or "").lower()
                    for f_key in (
                        "discoloration",
                        "tartar",
                        "cavity_suspect",
                        "gingivitis_signs",
                        "oral_ulcer",
                    ):
                        if f_key.replace("_", " ") in content or f_key.split("_")[0] in content:
                            active_finding = f_key
                            break
                    if active_finding:
                        break

        # Resolve from latest scan findings or verdict only for contextual follow-ups
        if not active_finding and state.get("latest_scan"):
            l_scan = state.get("latest_scan")
            if l_scan and l_scan.findings:
                active_finding = l_scan.findings[0].finding_code
            elif l_scan and l_scan.verdict:
                verdict_lower = l_scan.verdict.lower()
                for f_key in (
                    "discoloration",
                    "tartar",
                    "cavity_suspect",
                    "gingivitis_signs",
                    "oral_ulcer",
                ):
                    if f_key.replace("_", " ") in verdict_lower or f_key.split("_")[0] in verdict_lower:
                        active_finding = f_key
                        break
    elif is_standalone_dental:
        # Standalone questions start clean without inheriting previous findings
        active_finding = None

    history_ms = (time.perf_counter() - t0) * 1000.0
    latency = dict(state.get("latency_metadata", {}))
    latency["chat.history_ms"] = round(history_ms, 2)

    return {
        "recent_turns": recent_turns,
        "active_finding": active_finding,
        "latency_metadata": latency,
    }


# ---------------------------------------------------------------------------
# Node 6: retrieve_optional_knowledge
# ---------------------------------------------------------------------------

def retrieve_optional_knowledge(state: CentralDentistState) -> dict[str, Any]:
    """Perform deterministic oral health knowledge lookup."""
    plan = state.get("retrieval_plan", {})
    if not plan.get("need_knowledge"):
        return {"knowledge_context": None}

    raw_msg = state.get("message", "")
    active_finding = state.get("active_finding")
    intent_val = state.get("intent")
    allow_finding = intent_val == CentralDentistIntent.FOLLOW_UP_REFERENCE.value

    snippet = lookup_dental_knowledge(
        raw_msg,
        finding_key=active_finding,
        allow_finding_fallback=allow_finding,
    )
    return {"knowledge_context": snippet}


# ---------------------------------------------------------------------------
# Node 7: build_grounded_context
# ---------------------------------------------------------------------------

def build_grounded_context_node(state: CentralDentistState) -> dict[str, Any]:
    """Synthesize compact, grounded text for generation with topic and history isolation."""
    t0 = time.perf_counter()
    intent_val = state.get("intent", CentralDentistIntent.UNKNOWN.value)
    user_msg = state.get("message", "")

    is_standalone_dental = intent_val in (
        CentralDentistIntent.GENERAL_ORAL_HEALTH.value,
        CentralDentistIntent.DENTAL_KNOWLEDGE.value,
    )
    is_followup = (
        intent_val == CentralDentistIntent.FOLLOW_UP_REFERENCE.value
        or is_conversational_follow_up(user_msg)
    )
    has_record_ref = has_personal_record_reference(user_msg)
    is_patient_specific = intent_val in (
        CentralDentistIntent.SCAN_LATEST.value,
        CentralDentistIntent.SCAN_COMPARE.value,
        CentralDentistIntent.SCAN_HISTORY.value,
        CentralDentistIntent.REPORT_QUESTION.value,
        CentralDentistIntent.APPOINTMENT_STATUS.value,
        CentralDentistIntent.DENTIST_INFORMATION.value,
        CentralDentistIntent.EXPLAIN_CONFIDENCE.value,
    )

    # 1. History policy:
    # Standalone dental knowledge receives NO previous conversation history.
    # Follow-ups receive recent turns.
    recent_turns = None
    if is_followup:
        recent_turns = state.get("recent_turns")

    # 2. Patient data policy:
    # Only include patient clinical records if the question is patient-specific,
    # or explicitly references personal records, or is a scan follow-up.
    include_patient_records = is_patient_specific or has_record_ref or (is_followup and bool(state.get("latest_scan")))

    if include_patient_records:
        l_scan = state.get("latest_scan")
        p_scan = state.get("previous_scan")
        s_hist = state.get("scan_history")
        appts = state.get("appointments")
        d_info = state.get("dentist_info")
    else:
        l_scan = None
        p_scan = None
        s_hist = None
        appts = None
        d_info = None

    knowledge_snippet = state.get("knowledge_context")

    grounded = build_grounded_context(
        latest_scan=l_scan,
        previous_scan=p_scan,
        scan_history=s_hist,
        appointments=appts,
        dentist_info=d_info,
        knowledge_snippet=knowledge_snippet,
        recent_turns=recent_turns,
    )

    context_sources = get_context_sources(
        latest_scan=l_scan,
        previous_scan=p_scan,
        scan_history=s_hist,
        appointments=appts,
        dentist_info=d_info,
        knowledge_snippet=knowledge_snippet,
        recent_turns=recent_turns,
    )

    ctx_ms = (time.perf_counter() - t0) * 1000.0
    latency = dict(state.get("latency_metadata", {}))
    latency["chat.context_ms"] = round(ctx_ms, 2)

    return {
        "grounded_context": grounded,
        "context_sources": context_sources,
        "latency_metadata": latency,
    }


# ---------------------------------------------------------------------------
# Node 8: qwen_or_direct_answer
# ---------------------------------------------------------------------------

async def qwen_or_direct_answer(state: CentralDentistState) -> dict[str, Any]:
    """Execute direct fast path if eligible, or invoke Qwen via AIGateway."""
    req_id = state.get("request_id") or "chat_unknown"
    t0 = time.perf_counter()
    latency = dict(state.get("latency_metadata", {}))

    is_fast_path = state.get("is_fast_path", False)
    fast_path_type = state.get("fast_path_type")

    # FAST PATH CHECK
    if is_fast_path and fast_path_type:
        fast_resp = format_fast_path_response(
            fast_path_type=fast_path_type,
            latest_scan=state.get("latest_scan"),
            appointments=state.get("appointments"),
        )
        if fast_resp:
            latency["chat.qwen_ms"] = 0.0
            logger.info(
                "[CENTRAL_DENTIST][%s] fast_path_executed type=%s", req_id, fast_path_type
            )
            logger.info("[CENTRAL_DENTIST][%s] qwen_done ms=0.0", req_id)
            return {
                "draft_response": fast_resp,
                "latency_metadata": latency,
            }

    # CHAT GENERATION PATH
    gateway = state.get("_gateway")
    if gateway is None:
        from orchestrator.ai.factory import get_chat_ai_gateway

        gateway = get_chat_ai_gateway()

    from orchestrator.ai.exceptions import AllProvidersFailedError, ProviderTimeoutError
    from orchestrator.ai.schemas import ChatMessage, TextRequest
    from orchestrator.config import settings

    user_query = state.get("message", "")
    grounded_ctx = state.get("grounded_context", "")
    context_sources = state.get("context_sources", [])

    if grounded_ctx:
        user_prompt = f"PATIENT QUESTION: {user_query}\n\n{grounded_ctx}".strip()
    else:
        user_prompt = f"PATIENT QUESTION: {user_query}".strip()

    prompt_sha256 = hashlib.sha256(user_prompt.encode("utf-8")).hexdigest()[:12]

    prompt_audit = audit_chat_prompt_size(
        system_prompt=CENTRAL_DENTIST_SYSTEM_PROMPT,
        grounded_context=grounded_ctx,
        user_message=user_query,
        recent_turns=state.get("recent_turns") if ("conversation_history" in context_sources) else None,
        knowledge_snippet=state.get("knowledge_context") if ("knowledge_guideline" in context_sources) else None,
        has_patient_context=any(s in context_sources for s in ("latest_scan", "scan_history", "appointments", "dentist_info")),
    )

    primary_obj = getattr(gateway, "primary", None)
    primary_name = getattr(primary_obj, "name", "qwen") if primary_obj is not None else getattr(settings, "chat_llm_provider", "qwen")
    primary_model = getattr(primary_obj, "default_model", getattr(settings, "chat_qwen_model", "qwen3.7-flash")) if primary_obj is not None else getattr(settings, "chat_qwen_model", "qwen3.7-flash")
    logger.info(
        "[CENTRAL_DENTIST][%s] chat_started provider=%s model=%s messages=%d prompt_chars=%d max_tokens=200",
        req_id,
        primary_name,
        primary_model,
        prompt_audit["messages"],
        prompt_audit["total_chars"],
    )
    logger.info(
        "[CENTRAL_DENTIST][%s] prompt_telemetry prompt_sha256=%s intent=%s messages=%d system_chars=%d history_chars=%d patient_chars=%d knowledge_chars=%d total_chars=%d context_sources=%s",
        req_id,
        prompt_sha256,
        state.get("intent"),
        prompt_audit["messages"],
        prompt_audit["system_chars"],
        prompt_audit.get("history_chars", 0),
        prompt_audit.get("patient_context_chars", 0),
        prompt_audit.get("knowledge_context_chars", 0),
        prompt_audit["total_chars"],
        context_sources,
    )

    extra_body = None
    enable_thinking = getattr(settings, "chat_qwen_enable_thinking", False)
    if not enable_thinking:
        extra_body = {"enable_thinking": False}

    request = TextRequest(
        messages=[
            ChatMessage(role="system", content=CENTRAL_DENTIST_SYSTEM_PROMPT),
            ChatMessage(role="user", content=user_prompt),
        ],
        temperature=0.25,
        max_tokens=200,
        extra_body=extra_body,
        metadata={"request_id": req_id},
    )

    qwen_deadline = settings.chat_qwen_timeout_seconds
    fallback_used = False
    try:
        async with asyncio.timeout(qwen_deadline):
            res = await gateway.generate_text(request)
            draft = res.content or ""
    except (TimeoutError, ProviderTimeoutError) as exc:
        fallback_used = True
        qwen_ms = (time.perf_counter() - t0) * 1000.0
        logger.warning(
            "[CENTRAL_DENTIST][%s] qwen_timeout qwen_ms=%.1f fallback=true (%s)",
            req_id,
            qwen_ms,
            exc,
        )
        draft = _build_deterministic_fallback(state)
    except AllProvidersFailedError as exc:
        fallback_used = True
        qwen_ms = (time.perf_counter() - t0) * 1000.0
        logger.warning(
            "[CENTRAL_DENTIST][%s] qwen_failed qwen_ms=%.1f fallback=true (%s)",
            req_id,
            qwen_ms,
            exc,
        )
        draft = _build_deterministic_fallback(state)
    except Exception as exc:
        fallback_used = True
        qwen_ms = (time.perf_counter() - t0) * 1000.0
        logger.error(
            "[CENTRAL_DENTIST][%s] qwen_error qwen_ms=%.1f fallback=true (%s)",
            req_id,
            qwen_ms,
            exc,
            exc_info=True,
        )
        draft = _build_deterministic_fallback(state)

    qwen_ms = (time.perf_counter() - t0) * 1000.0
    latency["chat.qwen_ms"] = round(qwen_ms, 2)
    latency["chat.generation_ms"] = round(qwen_ms, 2)
    if not fallback_used:
        logger.info(
            "[CENTRAL_DENTIST][%s] qwen_success qwen_ms=%.1f total_ms=%.1f",
            req_id,
            round(qwen_ms, 1),
            round(qwen_ms, 1),
        )

    return {
        "draft_response": draft,
        "latency_metadata": latency,
    }


# ---------------------------------------------------------------------------
# Node 9: validate_response
# ---------------------------------------------------------------------------

def validate_response(state: CentralDentistState) -> dict[str, Any]:
    """Clean slop phrases and ensure concise, professional output."""
    draft = state.get("draft_response") or ""
    cleaned = clean_response(draft)

    if not cleaned:
        cleaned = (
            "I am reviewing your dental screening records. Please let me know how I can help."
        )

    return {"final_response": cleaned}


# ---------------------------------------------------------------------------
# Node 10: persist_turn
# ---------------------------------------------------------------------------

async def persist_turn(state: CentralDentistState) -> dict[str, Any]:
    """Save the completed conversation turn to PostgreSQL."""
    req_id = state.get("request_id") or "chat_unknown"
    t0 = time.perf_counter()
    session = state.get("_db_session")
    conv_id_str = state.get("conversation_id")
    user_id_str = state.get("user_id")
    final_response = state.get("final_response", "")

    assistant_msg_id = None
    assistant_created_at = None

    if session and conv_id_str and user_id_str:
        try:
            from orchestrator.chat_schemas import MessageSender
            from orchestrator.config import settings
            from orchestrator.repositories import ConversationRepository

            async with asyncio.timeout(settings.chat_persistence_timeout_seconds):
                repo = ConversationRepository(session)
                conv_id = UUID(conv_id_str)
                patient_id = UUID(user_id_str)

                # Record assistant turn
                assistant_msg = await repo.add_message(
                    conversation_id=conv_id,
                    user_id=None,
                    role=MessageSender.ASSISTANT.value,
                    content=final_response,
                    evidence_refs={
                        "intent": state.get("intent"),
                        "active_finding": state.get("active_finding"),
                        "is_fast_path": state.get("is_fast_path", False),
                    },
                )
                conv = await repo.get_owned(conv_id, patient_id)
                if conv:
                    await repo.touch(conv)
                assistant_msg_id = assistant_msg.id
                assistant_created_at = assistant_msg.created_at
        except Exception as exc:
            logger.warning(
                "[CENTRAL_DENTIST][%s] Failed to persist assistant turn: %s", req_id, exc
            )

    persist_ms = (time.perf_counter() - t0) * 1000.0
    latency = dict(state.get("latency_metadata", {}))
    latency["chat.persistence_ms"] = round(persist_ms, 2)
    logger.info("[CENTRAL_DENTIST][%s] persistence_done ms=%.1f", req_id, round(persist_ms, 2))

    start_t = latency.get("chat.start_time", t0)
    latency["chat.total_ms"] = round((time.perf_counter() - start_t) * 1000.0, 2)

    return {
        "assistant_message_id": assistant_msg_id,
        "assistant_created_at": assistant_created_at,
        "latency_metadata": latency,
    }


# ---------------------------------------------------------------------------
# StateGraph Compilation
# ---------------------------------------------------------------------------

def create_central_dentist_graph():
    """Build and compile the Central Dentist StateGraph."""
    builder = StateGraph(CentralDentistState)

    builder.add_node("load_auth_context", load_auth_context)
    builder.add_node("nlp_understanding", nlp_understanding)
    builder.add_node("plan_retrieval", plan_retrieval)
    builder.add_node("retrieve_patient_data", retrieve_patient_data)
    builder.add_node("retrieve_conversation_context", retrieve_conversation_context)
    builder.add_node("retrieve_optional_knowledge", retrieve_optional_knowledge)
    builder.add_node("build_grounded_context", build_grounded_context_node)
    builder.add_node("qwen_or_direct_answer", qwen_or_direct_answer)
    builder.add_node("validate_response", validate_response)
    builder.add_node("persist_turn", persist_turn)

    builder.add_edge(START, "load_auth_context")
    builder.add_edge("load_auth_context", "nlp_understanding")
    builder.add_edge("nlp_understanding", "plan_retrieval")
    builder.add_edge("plan_retrieval", "retrieve_patient_data")
    builder.add_edge("retrieve_patient_data", "retrieve_conversation_context")
    builder.add_edge("retrieve_conversation_context", "retrieve_optional_knowledge")
    builder.add_edge("retrieve_optional_knowledge", "build_grounded_context")
    builder.add_edge("build_grounded_context", "qwen_or_direct_answer")
    builder.add_edge("qwen_or_direct_answer", "validate_response")
    builder.add_edge("validate_response", "persist_turn")
    builder.add_edge("persist_turn", END)

    return builder.compile()


# Process-wide compiled graph instance
central_dentist_graph = create_central_dentist_graph()

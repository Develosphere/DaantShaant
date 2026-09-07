import asyncio
import logging
import uuid
from datetime import datetime, timezone
from time import perf_counter
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.config import settings

from orchestrator import conversation_state as cs
from orchestrator.chat_schemas import (
    AnalysisHistoryContext,
    ConversationHistoryResponse,
    ConversationSummary,
    CreateConversationRequest,
    CreateConversationResponse,
    MessageContext,
    MessageResponse,
    MessageSender,
    SendMessageRequest,
    SendMessageResponse,
)
from orchestrator.central_dentist import CentralDentistState, central_dentist_graph
from orchestrator.conversation_engine import conversation_engine
from orchestrator.intent_classifier import UserIntent, intent_classifier
from orchestrator.pipeline import TeethAnalyzePipelineRequest, run_teeth_analysis_pipeline
from orchestrator.repositories import ConversationRepository, ScanRepository

logger = logging.getLogger(__name__)


def _message_context(message) -> MessageContext:
    refs = message.evidence_refs or {}
    return MessageContext(
        message_id=message.id,
        conversation_id=message.conversation_id,
        user_id=message.user_id or UUID(int=0),
        sender=MessageSender(message.role),
        text=message.content,
        analysis_result=refs.get("analysis_result"),
        timestamp=message.created_at,
    )


async def create_conversation(
    request: CreateConversationRequest, patient_user_id: UUID, session: AsyncSession
) -> CreateConversationResponse:
    conversation = await ConversationRepository(session).create(
        patient_user_id, request.title or "New Conversation"
    )
    return CreateConversationResponse(
        conversation_id=conversation.id,
        user_id=conversation.patient_user_id,
        title=conversation.title or "New Conversation",
        created_at=conversation.created_at,
    )


async def get_user_conversations(
    patient_user_id: UUID, session: AsyncSession, limit: int = 50
) -> list[ConversationSummary]:
    rows = await ConversationRepository(session).list_owned(patient_user_id, limit)
    return [
        ConversationSummary(
            conversation_id=conversation.id,
            user_id=conversation.patient_user_id,
            title=conversation.title or "New Conversation",
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            message_count=count,
            last_message_preview=(
                last[:100] + "..." if last and len(last) > 100 else last
            ),
        )
        for conversation, count, last in rows
    ]


async def get_conversation_messages(
    conversation_id: UUID, patient_user_id: UUID, session: AsyncSession
) -> ConversationHistoryResponse:
    repository = ConversationRepository(session)
    conversation = await repository.get_owned(conversation_id, patient_user_id)
    if not conversation:
        raise ValueError(f"Conversation {conversation_id} not found")
    messages = await repository.list_messages(conversation_id)
    return ConversationHistoryResponse(
        conversation_id=conversation.id,
        user_id=conversation.patient_user_id,
        title=conversation.title or "New Conversation",
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[
            MessageResponse(
                message_id=message.id,
                conversation_id=message.conversation_id,
                sender=MessageSender(message.role),
                text=message.content,
                analysis_result=(message.evidence_refs or {}).get("analysis_result"),
                timestamp=message.created_at,
            )
            for message in messages
        ],
    )


async def get_recent_analysis_history(
    patient_user_id: UUID, session: AsyncSession, limit: int = 5
) -> list[AnalysisHistoryContext]:
    reports = await ScanRepository(session).recent_reports(patient_user_id, limit)
    history = []
    for report in reports:
        concerns = report.possible_concerns or {}
        findings = concerns.get("findings", []) if isinstance(concerns, dict) else []
        history.append(
            AnalysisHistoryContext(
                analysis_history_id=report.id,
                user_id=patient_user_id,
                findings=findings,
                condition_label=report.verdict,
                severity=report.urgency_level or "Unknown",
                confidence=float((report.agent_trace_summary or {}).get("confidence", 0.0)),
                created_at=report.created_at,
            )
        )
    return history


async def generate_conversational_response(
    user_text: str,
    intent: UserIntent,
    conversation_id: Optional[UUID] = None,
    analysis_result: Optional[dict] = None,
    recent_messages: Optional[list[MessageContext]] = None,
    previous_analyses: Optional[list[AnalysisHistoryContext]] = None,
    context_info: Optional[dict] = None,
) -> str:
    recent_messages = recent_messages or []
    previous_analyses = previous_analyses or []
    context_info = context_info or {}
    conv_id = str(conversation_id) if conversation_id else None
    try:
        if intent == UserIntent.OFF_DOMAIN:
            return conversation_engine.generate_off_domain_response(user_text)
        if intent == UserIntent.CORRECTION:
            return conversation_engine.generate_correction_response(user_text, conv_id or "")
        if intent == UserIntent.GREETING:
            return await conversation_engine.generate_greeting()
        if intent == UserIntent.IMAGE_ANALYSIS:
            if analysis_result:
                return await conversation_engine.generate_analysis_response(
                    user_text, analysis_result, recent_messages, previous_analyses
                )
            return "I'm ready to check out your teeth. Send me a clear photo."
        if intent == UserIntent.SYMPTOM_DISCUSSION:
            return await conversation_engine.generate_symptom_response(
                user_text,
                recent_messages,
                previous_analyses,
                context_info,
                conversation_id=conv_id,
            )
        if intent == UserIntent.COMPARE_HISTORY:
            return await conversation_engine.generate_comparison_response(
                user_text, analysis_result, previous_analyses
            )
        if intent == UserIntent.FOLLOW_UP:
            return await conversation_engine.generate_follow_up_response(
                user_text, recent_messages, conversation_id=conv_id, skip_rag=True
            )
        return await conversation_engine.generate_conversational_response(
            user_text,
            recent_messages,
            previous_analyses,
            context_info,
            conversation_id=conv_id,
        )
    except Exception as exc:
        logger.error("[CHAT] Response generation failed: %s", exc, exc_info=True)
        return cs.get_contextual_recovery(conv_id) if conv_id else "So what's going on with your teeth?"


async def send_message(
    request: SendMessageRequest,
    patient_user_id: UUID,
    session: AsyncSession,
    request_id: Optional[str] = None,
) -> SendMessageResponse:
    if not request_id:
        request_id = f"chat_{uuid.uuid4().hex[:8]}"
    _send_t0 = perf_counter()
    logger.info("[CENTRAL_DENTIST][%s] request_started", request_id)

    repository = ConversationRepository(session)
    conversation = None
    try:
        async with asyncio.timeout(settings.chat_retrieval_timeout_seconds):
            if request.conversation_id:
                conversation = await repository.get_owned(
                    request.conversation_id, patient_user_id
                )
                if not conversation:
                    raise ValueError("Conversation not found")
            else:
                title = request.text[:50] + ("..." if len(request.text) > 50 else "")
                conversation = await repository.create(patient_user_id, title)

            recent_rows = await repository.list_messages(
                conversation.id, newest_first=True, limit=10
            )
            recent_messages = [_message_context(row) for row in reversed(recent_rows)]
            user_row = await repository.add_message(
                conversation_id=conversation.id,
                user_id=patient_user_id,
                role=MessageSender.USER.value,
                content=request.text,
            )
    except TimeoutError as exc:
        logger.error("[CENTRAL_DENTIST][%s] DB initialization timed out", request_id)
        raise

    intent, context_info = intent_classifier.classify(
        request.text,
        has_image=bool(request.image_base64),
        is_first_message=not recent_messages,
    )
    cs.update_from_message(str(conversation.id), request.text, intent.value)

    analysis_result = None
    if request.image_base64:
        pipeline_response = await run_teeth_analysis_pipeline(
            TeethAnalyzePipelineRequest(
                user_id=patient_user_id,
                image_base64=request.image_base64,
                image_mime_type=request.image_mime_type,
                locale=request.locale,
            )
        )
        analysis_result = {
            "analysis": pipeline_response.analysis.model_dump(mode="json"),
            "diagnosis": pipeline_response.diagnosis.model_dump(mode="json"),
        }
        scan, report = await ScanRepository(session).add_result(
            patient_user_id=patient_user_id,
            input_mode="upload",
            analysis=pipeline_response.analysis,
            diagnosis=pipeline_response.diagnosis,
        )
        user_row.evidence_refs = {
            "analysis_result": analysis_result,
            "scan_id": str(scan.id),
            "report_id": str(report.id),
        }

    # Pass pre-loaded recent turns to avoid duplicate SQL queries in graph
    recent_turns = [
        {"role": row.role, "content": row.content} for row in reversed(recent_rows)
    ]
    state_input: CentralDentistState = {
        "user_id": str(patient_user_id),
        "conversation_id": str(conversation.id),
        "message": request.text,
        "locale": request.locale or "en",
        "request_id": request_id,
        "recent_turns": recent_turns,
        "_db_session": session,
    }

    # Global cancellable timeout budget (15.0s max)
    try:
        async with asyncio.timeout(settings.chat_request_timeout_seconds):
            graph_res = await central_dentist_graph.ainvoke(state_input)
    except TimeoutError:
        _timeout_ms = (perf_counter() - _send_t0) * 1000
        logger.error(
            "[CENTRAL_DENTIST][%s] Global chat deadline (%.1fs) exceeded after %.1f ms",
            request_id,
            settings.chat_request_timeout_seconds,
            _timeout_ms,
        )
        try:
            await session.rollback()
        except Exception:
            pass
        assistant_text = (
            "I couldn't complete that answer just now. Please ask your question again, "
            "or let me know if you need help with your scan results or appointments."
        )
        graph_res = {
            "final_response": assistant_text,
            "latency_metadata": {"chat.total_ms": _timeout_ms},
            "is_fast_path": False,
        }

    assistant_text = graph_res.get("final_response") or "I am reviewing your dental screening records."
    assistant_row_id = graph_res.get("assistant_message_id")
    assistant_created_at = graph_res.get("assistant_created_at")
    if not assistant_row_id:
        _t0 = perf_counter()
        try:
            async with asyncio.timeout(settings.chat_persistence_timeout_seconds):
                assistant_row = await repository.add_message(
                    conversation_id=conversation.id,
                    user_id=None,
                    role=MessageSender.ASSISTANT.value,
                    content=assistant_text,
                    evidence_refs={
                        "intent": graph_res.get("intent"),
                        "active_finding": graph_res.get("active_finding"),
                        "is_fast_path": graph_res.get("is_fast_path", False),
                        "analysis_result": analysis_result,
                    } if (analysis_result or graph_res.get("intent")) else None,
                )
                conv = await repository.get_owned(conversation.id, patient_user_id)
                if conv:
                    await repository.touch(conv)
                assistant_row_id = assistant_row.id
                assistant_created_at = assistant_row.created_at
                _persistence_ms = (perf_counter() - _t0) * 1000
                logger.info("[CENTRAL_DENTIST][%s] persistence_done ms=%.1f", request_id, _persistence_ms)
        except Exception as exc:
            logger.warning("[CENTRAL_DENTIST][%s] Persistence fallback failed: %s", request_id, exc)
            assistant_row_id = uuid.uuid4()
            assistant_created_at = datetime.now(timezone.utc)

    _total_ms = (perf_counter() - _send_t0) * 1000
    latency = graph_res.get("latency_metadata", {})
    logger.info(
        "[CENTRAL_DENTIST][%s] request_complete total_ms=%.1f nlp_ms=%s retrieval_ms=%s qwen_ms=%s fast_path=%s",
        request_id,
        _total_ms,
        latency.get("chat.nlp_ms"),
        latency.get("chat.retrieval_ms"),
        latency.get("chat.qwen_ms"),
        graph_res.get("is_fast_path", False),
    )

    return SendMessageResponse(
        conversation_id=conversation.id,
        user_message=MessageResponse(
            message_id=user_row.id,
            conversation_id=conversation.id,
            sender=MessageSender.USER,
            text=user_row.content,
            timestamp=user_row.created_at,
        ),
        assistant_message=MessageResponse(
            message_id=assistant_row_id,
            conversation_id=conversation.id,
            sender=MessageSender.ASSISTANT,
            text=assistant_text,
            analysis_result=analysis_result,
            timestamp=assistant_created_at,
        ),
    )

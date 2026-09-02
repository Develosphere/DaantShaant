"""PostgreSQL-backed chat and conversation business logic."""

import logging
from time import perf_counter
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

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
    request: SendMessageRequest, patient_user_id: UUID, session: AsyncSession
) -> SendMessageResponse:
    _send_t0 = perf_counter()
    logger.info("[CHAT_TIMING] route_start")
    repository = ConversationRepository(session)
    conversation = None
    if request.conversation_id:
        conversation = await repository.get_owned(
            request.conversation_id, patient_user_id
        )
        if not conversation:
            raise ValueError("Conversation not found")
    else:
        title = request.text[:50] + ("..." if len(request.text) > 50 else "")
        conversation = await repository.create(patient_user_id, title)

    _t0 = perf_counter()
    recent_rows = await repository.list_messages(
        conversation.id, newest_first=True, limit=10
    )
    _history_load_ms = (perf_counter() - _t0) * 1000
    logger.info("[CHAT_TIMING] history_load_ms=%.1f", _history_load_ms)
    recent_messages = [_message_context(row) for row in reversed(recent_rows)]
    user_row = await repository.add_message(
        conversation_id=conversation.id,
        user_id=patient_user_id,
        role=MessageSender.USER.value,
        content=request.text,
    )

    _t0 = perf_counter()
    intent, context_info = intent_classifier.classify(
        request.text,
        has_image=bool(request.image_base64),
        is_first_message=not recent_messages,
    )
    cs.update_from_message(str(conversation.id), request.text, intent.value)
    _routing_ms = (perf_counter() - _t0) * 1000
    logger.info("[CHAT_TIMING] routing_ms=%.1f", _routing_ms)

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

    previous_analyses = await get_recent_analysis_history(patient_user_id, session)
    _t0 = perf_counter()
    assistant_text = await generate_conversational_response(
        request.text,
        intent,
        conversation_id=conversation.id,
        analysis_result=analysis_result,
        recent_messages=recent_messages,
        previous_analyses=previous_analyses,
        context_info=context_info,
    )
    _response_gen_ms = (perf_counter() - _t0) * 1000
    logger.info("[CHAT_TIMING] response_generation_ms=%.1f", _response_gen_ms)
    _t0 = perf_counter()
    assistant_row = await repository.add_message(
        conversation_id=conversation.id,
        user_id=None,
        role=MessageSender.ASSISTANT.value,
        content=assistant_text,
        evidence_refs={"analysis_result": analysis_result} if analysis_result else None,
    )
    await repository.touch(conversation)
    _persistence_ms = (perf_counter() - _t0) * 1000
    logger.info("[CHAT_TIMING] persistence_ms=%.1f", _persistence_ms)
    _total_ms = (perf_counter() - _send_t0) * 1000
    logger.info("[CHAT_TIMING] total_ms=%.1f", _total_ms)

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
            message_id=assistant_row.id,
            conversation_id=conversation.id,
            sender=MessageSender.ASSISTANT,
            text=assistant_row.content,
            analysis_result=analysis_result,
            timestamp=assistant_row.created_at,
        ),
    )

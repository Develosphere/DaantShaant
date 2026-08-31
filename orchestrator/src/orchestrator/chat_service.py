"""Business logic for chat and conversation management."""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from orchestrator.chat_schemas import (
    AnalysisHistoryDocument,
    ConversationDocument,
    ConversationHistoryResponse,
    ConversationSummary,
    CreateConversationRequest,
    CreateConversationResponse,
    MessageDocument,
    MessageResponse,
    MessageSender,
    SendMessageRequest,
    SendMessageResponse,
    UserDocument,
)
from orchestrator.database import (
    get_analysis_history_collection,
    get_conversations_collection,
    get_messages_collection,
    get_users_collection,
)
from orchestrator.pipeline import (
    TeethAnalyzePipelineRequest,
    run_teeth_analysis_pipeline,
)
from orchestrator.intent_classifier import intent_classifier, UserIntent
from orchestrator.conversation_engine import conversation_engine
from orchestrator import conversation_state as cs

logger = logging.getLogger(__name__)


async def ensure_user_exists(user_id: UUID) -> UserDocument:
    """Ensure user exists in database, create if not using upsert."""
    users = get_users_collection()
    
    logger.info(f"[MONGO] ensure_user_exists: user_id={user_id} (type={type(user_id).__name__})")
    
    # Use upsert to avoid race conditions and duplicate key errors
    # $setOnInsert only sets values if document is being inserted (not updated)
    user_data = {
        "_id": user_id,
        "username": f"user_{user_id.hex}",
        "created_at": datetime.now(timezone.utc),
        "profile": {}
    }
    
    result = await users.update_one(
        {"_id": user_id},
        {"$setOnInsert": user_data},
        upsert=True
    )
    
    if result.upserted_id:
        logger.info(f"[MONGO] Created new user: {user_id}")
    else:
        logger.info(f"[MONGO] User already exists: {user_id}")
    
    # Fetch the user document (either existing or just created)
    user_doc = await users.find_one({"_id": user_id})
    if not user_doc:
        raise RuntimeError(f"Failed to create or fetch user {user_id}")
    
    return UserDocument(**user_doc)


async def create_conversation(
    request: CreateConversationRequest,
) -> CreateConversationResponse:
    """Create a new conversation."""
    await ensure_user_exists(request.user_id)
    
    conversations = get_conversations_collection()
    
    title = request.title or "New Conversation"
    conversation = ConversationDocument(
        user_id=request.user_id,
        title=title,
    )
    
    await conversations.insert_one(
        conversation.model_dump(by_alias=True, mode="json")
    )
    
    logger.info(f"[CONVERSATION] Created conversation_id={conversation.conversation_id} for user_id={request.user_id}")
    
    return CreateConversationResponse(
        conversation_id=conversation.conversation_id,
        user_id=conversation.user_id,
        title=conversation.title,
        created_at=conversation.created_at,
    )


async def get_user_conversations(
    user_id: UUID,
    limit: int = 50,
) -> list[ConversationSummary]:
    """Get all conversations for a user."""
    conversations = get_conversations_collection()
    messages = get_messages_collection()
    
    # Get conversations sorted by most recent
    cursor = conversations.find({"user_id": user_id}).sort("updated_at", -1).limit(limit)
    
    summaries = []
    async for conv_doc in cursor:
        conversation = ConversationDocument(**conv_doc)
        
        # Get message count and last message
        message_count = await messages.count_documents(
            {"conversation_id": conversation.conversation_id}
        )
        
        last_message = await messages.find_one(
            {"conversation_id": conversation.conversation_id},
            sort=[("timestamp", -1)],
        )
        
        last_message_preview = None
        if last_message:
            text = last_message.get("text", "")
            last_message_preview = text[:100] + "..." if len(text) > 100 else text
        
        summaries.append(
            ConversationSummary(
                conversation_id=conversation.conversation_id,
                user_id=conversation.user_id,
                title=conversation.title,
                created_at=conversation.created_at,
                updated_at=conversation.updated_at,
                message_count=message_count,
                last_message_preview=last_message_preview,
            )
        )
    
    return summaries


async def get_conversation_messages(
    conversation_id: UUID,
) -> ConversationHistoryResponse:
    """Get all messages in a conversation."""
    conversations = get_conversations_collection()
    messages = get_messages_collection()
    
    logger.info(f"[CONVERSATION] Fetching messages for conversation_id={conversation_id}")
    
    # Get conversation
    conv_doc = await conversations.find_one({"_id": conversation_id})
    if not conv_doc:
        logger.warning(f"[CONVERSATION] Conversation {conversation_id} not found")
        raise ValueError(f"Conversation {conversation_id} not found")
    
    conversation = ConversationDocument(**conv_doc)
    
    # Get messages sorted by timestamp
    cursor = messages.find({"conversation_id": conversation_id}).sort("timestamp", 1)
    
    message_list = []
    async for msg_doc in cursor:
        message = MessageDocument(**msg_doc)
        message_list.append(
            MessageResponse(
                message_id=message.message_id,
                conversation_id=message.conversation_id,
                sender=message.sender,
                text=message.text,
                image_url=None,  # We store base64, not URLs for now
                analysis_result=message.analysis_result,
                timestamp=message.timestamp,
            )
        )
    
    logger.info(f"[CONVERSATION] Retrieved {len(message_list)} messages for conversation {conversation_id}")
    
    return ConversationHistoryResponse(
        conversation_id=conversation.conversation_id,
        user_id=conversation.user_id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=message_list,
    )


async def get_recent_analysis_history(
    user_id: UUID,
    limit: int = 5,
) -> list[AnalysisHistoryDocument]:
    """Get recent analysis history for a user."""
    analysis_history = get_analysis_history_collection()
    
    cursor = (
        analysis_history.find({"user_id": user_id})
        .sort("created_at", -1)
        .limit(limit)
    )
    
    history = []
    async for doc in cursor:
        history.append(AnalysisHistoryDocument(**doc))
    
    return history


async def generate_conversational_response(
    user_text: str,
    intent: UserIntent,
    conversation_id: Optional[UUID] = None,
    analysis_result: Optional[dict] = None,
    recent_messages: Optional[list[MessageDocument]] = None,
    previous_analyses: Optional[list[AnalysisHistoryDocument]] = None,
    context_info: Optional[dict] = None,
) -> str:
    """Generate conversational assistant response using LLM."""
    
    recent_messages = recent_messages or []
    previous_analyses = previous_analyses or []
    context_info = context_info or {}
    conv_id = str(conversation_id) if conversation_id else None
    
    logger.info(f"[CHAT] Generating response for intent={intent}, has_analysis={analysis_result is not None}, casual_address={context_info.get('has_casual_address', False)}")
    
    try:
        # --- Priority routing for new intents ---
        
        # OFF_DOMAIN: deterministic redirect, no LLM call
        if intent == UserIntent.OFF_DOMAIN:
            return conversation_engine.generate_off_domain_response(user_text)
        
        # CORRECTION: deterministic response, no LLM call
        if intent == UserIntent.CORRECTION:
            return conversation_engine.generate_correction_response(user_text, conv_id or "")
        
        # --- Existing intent routing ---
        
        if intent == UserIntent.GREETING:
            return await conversation_engine.generate_greeting()
        
        elif intent == UserIntent.IMAGE_ANALYSIS:
            if analysis_result:
                return await conversation_engine.generate_analysis_response(
                    user_text,
                    analysis_result,
                    recent_messages,
                    previous_analyses
                )
            else:
                return "I'm ready to check out your teeth. Send me a clear photo."
        
        elif intent == UserIntent.SYMPTOM_DISCUSSION:
            return await conversation_engine.generate_symptom_response(
                user_text,
                recent_messages,
                previous_analyses,
                context_info,
                conversation_id=conv_id
            )
        
        elif intent == UserIntent.COMPARE_HISTORY:
            # Use the existing comparison method
            return await conversation_engine.generate_comparison_response(
                user_text,
                analysis_result,
                previous_analyses
            )
        
        elif intent == UserIntent.FOLLOW_UP:
            return await conversation_engine.generate_follow_up_response(
                user_text,
                recent_messages,
                conversation_id=conv_id
            )
        
        else:  # GENERAL_ORAL_QUESTION or UNKNOWN
            return await conversation_engine.generate_conversational_response(
                user_text,
                recent_messages,
                previous_analyses,
                context_info,
                conversation_id=conv_id
            )
    
    except Exception as e:
        logger.error(f"[CHAT] Error generating conversational response: {e}", exc_info=True)
        # Contextual recovery instead of generic fallback
        if conv_id:
            return cs.get_contextual_recovery(conv_id)
        return "So what's going on with your teeth?"


async def send_message(request: SendMessageRequest) -> SendMessageResponse:
    """Send a message and get assistant response."""
    await ensure_user_exists(request.user_id)
    
    conversations = get_conversations_collection()
    messages = get_messages_collection()
    analysis_history = get_analysis_history_collection()
    
    logger.info(f"[CHAT] send_message: user_id={request.user_id}, conversation_id={request.conversation_id}, has_image={bool(request.image_base64)}")
    
    # Create or get conversation
    conversation_id = request.conversation_id
    if not conversation_id:
        # Create new conversation
        title = request.text[:50] + "..." if len(request.text) > 50 else request.text
        conv_request = CreateConversationRequest(
            user_id=request.user_id,
            title=title,
        )
        conv_response = await create_conversation(conv_request)
        conversation_id = conv_response.conversation_id
        logger.info(f"[CHAT] Created new conversation: {conversation_id}")
    
    # Get recent messages for context (before adding new message)
    recent_messages_cursor = messages.find(
        {"conversation_id": conversation_id}
    ).sort("timestamp", -1).limit(10)
    
    recent_messages = []
    async for msg_doc in recent_messages_cursor:
        recent_messages.append(MessageDocument(**msg_doc))
    recent_messages.reverse()  # Oldest first
    
    # Save user message
    user_message = MessageDocument(
        conversation_id=conversation_id,
        user_id=request.user_id,
        sender=MessageSender.USER,
        text=request.text,
        image_base64=request.image_base64,
        image_mime_type=request.image_mime_type if request.image_base64 else None,
    )
    await messages.insert_one(user_message.model_dump(by_alias=True, mode="json"))
    logger.info(f"[MONGO] Saved user message: {user_message.message_id}")
    
    # Classify intent with enhanced context
    is_first_message = len(recent_messages) == 0
    intent, context_info = intent_classifier.classify(
        request.text, 
        has_image=bool(request.image_base64),
        is_first_message=is_first_message
    )
    logger.info(f"[CHAT] Classified intent: {intent}, context: {context_info}")
    
    # --- UPDATE CONVERSATION STATE (before LLM generation) ---
    conv_id_str = str(conversation_id)
    state_changes = cs.update_from_message(conv_id_str, request.text, intent.value)
    logger.info(f"[CHAT] State changes: {state_changes}")
    
    # Run analysis if image provided
    analysis_result = None
    if request.image_base64:
        logger.info("[CHAT] Running image analysis pipeline...")
        pipeline_request = TeethAnalyzePipelineRequest(
            user_id=request.user_id,
            image_base64=request.image_base64,
            image_mime_type=request.image_mime_type,
            locale=request.locale,
        )
        pipeline_response = await run_teeth_analysis_pipeline(pipeline_request)
        
        # Convert to dict for storage
        analysis_result = {
            "analysis": pipeline_response.analysis.model_dump(mode="json"),
            "diagnosis": pipeline_response.diagnosis.model_dump(mode="json"),
        }
        
        # Save to analysis history
        history_doc = AnalysisHistoryDocument(
            user_id=request.user_id,
            message_id=user_message.message_id,
            conversation_id=conversation_id,
            findings=[f.model_dump() for f in pipeline_response.analysis.findings],
            condition_label=pipeline_response.diagnosis.condition_label.value,
            severity=pipeline_response.diagnosis.severity.value,
            confidence=pipeline_response.diagnosis.confidence,
        )
        await analysis_history.insert_one(
            history_doc.model_dump(by_alias=True, mode="json")
        )
        logger.info(f"[MONGO] Saved analysis history: {history_doc.analysis_history_id}")
    
    # Get recent analysis history for context
    previous_analyses = await get_recent_analysis_history(request.user_id, limit=5)
    logger.info(f"[CHAT] Retrieved {len(previous_analyses)} previous analyses")
    
    # Generate assistant response using conversational engine
    # Pass conversation_id for state-aware generation
    assistant_text = await generate_conversational_response(
        request.text,
        intent,
        conversation_id=conversation_id,
        analysis_result=analysis_result,
        recent_messages=recent_messages,
        previous_analyses=previous_analyses,
        context_info=context_info,
    )
    
    # Save assistant message
    assistant_message = MessageDocument(
        conversation_id=conversation_id,
        user_id=request.user_id,
        sender=MessageSender.ASSISTANT,
        text=assistant_text,
        analysis_result=analysis_result,
    )
    await messages.insert_one(
        assistant_message.model_dump(by_alias=True, mode="json")
    )
    logger.info(f"[MONGO] Saved assistant message: {assistant_message.message_id}")
    
    # Update conversation timestamp
    await conversations.update_one(
        {"_id": conversation_id},
        {"$set": {"updated_at": datetime.now(timezone.utc)}},
    )
    
    return SendMessageResponse(
        conversation_id=conversation_id,
        user_message=MessageResponse(
            message_id=user_message.message_id,
            conversation_id=user_message.conversation_id,
            sender=user_message.sender,
            text=user_message.text,
            image_url=None,
            analysis_result=None,
            timestamp=user_message.timestamp,
        ),
        assistant_message=MessageResponse(
            message_id=assistant_message.message_id,
            conversation_id=assistant_message.conversation_id,
            sender=assistant_message.sender,
            text=assistant_message.text,
            image_url=None,
            analysis_result=assistant_message.analysis_result,
            timestamp=assistant_message.timestamp,
        ),
    )

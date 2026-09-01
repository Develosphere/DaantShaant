"""Pydantic models for chat and conversation management."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class MessageSender(str, Enum):
    """Message sender type."""
    USER = "user"
    ASSISTANT = "assistant"


# --- Request/Response Models ---


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation."""
    title: Optional[str] = None


class CreateConversationResponse(BaseModel):
    """Response after creating a conversation."""
    conversation_id: UUID
    user_id: UUID
    title: str
    created_at: datetime


class SendMessageRequest(BaseModel):
    """Request to send a message in a conversation."""
    conversation_id: Optional[UUID] = None  # If None, creates new conversation
    text: str
    image_base64: Optional[str] = None
    image_mime_type: str = "image/jpeg"
    locale: str = "en"


class MessageResponse(BaseModel):
    """Single message in a conversation."""
    message_id: UUID
    conversation_id: UUID
    sender: MessageSender
    text: str
    image_url: Optional[str] = None
    analysis_result: Optional[dict[str, Any]] = None
    timestamp: datetime


class SendMessageResponse(BaseModel):
    """Response after sending a message."""
    conversation_id: UUID
    user_message: MessageResponse
    assistant_message: MessageResponse


class ConversationSummary(BaseModel):
    """Summary of a conversation for listing."""
    conversation_id: UUID
    user_id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    last_message_preview: Optional[str] = None


class ConversationHistoryResponse(BaseModel):
    """Full conversation history with messages."""
    conversation_id: UUID
    user_id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[MessageResponse]


# --- Internal conversation context models ---


class MessageContext(BaseModel):
    message_id: UUID
    conversation_id: UUID
    user_id: UUID
    sender: MessageSender
    text: str
    image_base64: Optional[str] = None
    image_mime_type: Optional[str] = None
    analysis_result: Optional[dict[str, Any]] = None
    timestamp: datetime


class AnalysisHistoryContext(BaseModel):
    analysis_history_id: UUID
    user_id: UUID
    message_id: UUID | None = None
    conversation_id: UUID | None = None
    findings: list[dict[str, Any]]
    condition_label: str
    severity: str
    confidence: float
    created_at: datetime

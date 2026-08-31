"""Pydantic models for chat and conversation management."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class MessageSender(str, Enum):
    """Message sender type."""
    USER = "user"
    ASSISTANT = "assistant"


# --- Request/Response Models ---


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation."""
    user_id: UUID
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
    user_id: UUID
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


# --- MongoDB Document Models ---


class UserDocument(BaseModel):
    """User document stored in MongoDB."""
    user_id: UUID = Field(default_factory=uuid4, alias="_id")
    username: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    profile: dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        populate_by_name = True


class ConversationDocument(BaseModel):
    """Conversation document stored in MongoDB."""
    conversation_id: UUID = Field(default_factory=uuid4, alias="_id")
    user_id: UUID
    title: str = "New Conversation"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    class Config:
        populate_by_name = True


class MessageDocument(BaseModel):
    """Message document stored in MongoDB."""
    message_id: UUID = Field(default_factory=uuid4, alias="_id")
    conversation_id: UUID
    user_id: UUID
    sender: MessageSender
    text: str
    image_base64: Optional[str] = None
    image_mime_type: Optional[str] = None
    analysis_result: Optional[dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    class Config:
        populate_by_name = True


class AnalysisHistoryDocument(BaseModel):
    """Analysis history document stored in MongoDB."""
    analysis_history_id: UUID = Field(default_factory=uuid4, alias="_id")
    user_id: UUID
    message_id: UUID
    conversation_id: UUID
    findings: list[dict[str, Any]]
    condition_label: str
    severity: str
    confidence: float
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    class Config:
        populate_by_name = True

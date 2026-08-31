import type { ChatMessage, ConversationSummary, SendMessageResponse } from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_ORCHESTRATOR_URL ?? "http://127.0.0.1:8000";

import { getUserId } from "./user-id";

export { getUserId };

export async function sendChatMessage(
  text: string,
  conversationId?: string,
  imageBase64?: string,
  imageMimeType = "image/jpeg"
): Promise<SendMessageResponse> {
  const userId = getUserId();
  
  const res = await fetch(`${API_BASE}/v1/chat/message`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      conversation_id: conversationId || null,
      user_id: userId,
      text,
      image_base64: imageBase64 || null,
      image_mime_type: imageMimeType,
      locale: "en",
    }),
  });
  
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(
      typeof err.detail === "string"
        ? err.detail
        : JSON.stringify(err.detail ?? res.statusText)
    );
  }
  
  return res.json();
}

export async function getUserConversations(): Promise<ConversationSummary[]> {
  const userId = getUserId();
  
  const res = await fetch(`${API_BASE}/v1/chat/conversations/${userId}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
  
  if (!res.ok) {
    throw new Error(`Failed to fetch conversations: ${res.statusText}`);
  }
  
  return res.json();
}

export async function getConversationMessages(
  conversationId: string
): Promise<ChatMessage[]> {
  const res = await fetch(`${API_BASE}/v1/chat/messages/${conversationId}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
  
  if (!res.ok) {
    throw new Error(`Failed to fetch messages: ${res.statusText}`);
  }
  
  const data = await res.json();
  return data.messages;
}

export async function createConversation(title?: string): Promise<string> {
  const userId = getUserId();
  
  const res = await fetch(`${API_BASE}/v1/chat/conversation`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: userId,
      title: title || "New Conversation",
    }),
  });
  
  if (!res.ok) {
    throw new Error(`Failed to create conversation: ${res.statusText}`);
  }
  
  const data = await res.json();
  return data.conversation_id;
}

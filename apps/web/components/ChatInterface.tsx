"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { sendChatMessage, getConversationMessages } from "@/lib/chat-api";
import { fileToImagePayload } from "@/lib/image";
import type { ChatMessage } from "@/lib/types";
import { ChatMessageBubble } from "./ChatMessage";

type Props = {
  /** localStorage key for persisting the active conversation id */
  conversationStorageKey?: string;
};

export function ChatInterface({
  conversationStorageKey = "dantshaant_current_conversation",
}: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputText, setInputText] = useState("");
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);
  const [imageAttachment, setImageAttachment] = useState<{
    base64: string;
    mimeType: string;
    preview: string;
    fileName: string;
  } | null>(null);
  
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };
  
  useEffect(() => {
    scrollToBottom();
  }, [messages]);
  
  // Load conversation from localStorage if exists
  useEffect(() => {
    const loadSavedConversation = async () => {
      const savedConvId = localStorage.getItem(conversationStorageKey);
      console.log("Checking for saved conversation:", savedConvId);
      
      if (savedConvId) {
        try {
          setConversationId(savedConvId);
          console.log("Loading conversation:", savedConvId);
          await loadConversation(savedConvId);
        } catch (error) {
          console.error("Failed to load saved conversation:", error);
          // Clear invalid conversation ID and start fresh
          console.log("Clearing invalid conversation ID");
          localStorage.removeItem(conversationStorageKey);
          setConversationId(undefined);
          setMessages([]);
        }
      }
    };
    
    loadSavedConversation();
  }, [conversationStorageKey]);
  
  const loadConversation = async (convId: string) => {
    try {
      console.log("Fetching messages for conversation:", convId);
      const msgs = await getConversationMessages(convId);
      console.log("Loaded messages:", msgs.length);
      setMessages(msgs);
    } catch (error) {
      console.error("Failed to load conversation:", error);
      throw error;
    }
  };
  
  const handleSendMessage = async () => {
    if (!inputText.trim() && !imageAttachment) return;
    
    setLoading(true);
    
    try {
      console.log("Sending message:", {
        text: inputText,
        conversationId,
        hasImage: !!imageAttachment
      });
      
      const response = await sendChatMessage(
        inputText || "Please analyze this image",
        conversationId,
        imageAttachment?.base64,
        imageAttachment?.mimeType
      );
      
      console.log("Received response:", response);
      
      // Update conversation ID if this is a new conversation
      if (!conversationId) {
        console.log("Setting new conversation ID:", response.conversation_id);
        setConversationId(response.conversation_id);
        localStorage.setItem(conversationStorageKey, response.conversation_id);
      }
      
      // Add both messages to the chat
      setMessages((prev) => [...prev, response.user_message, response.assistant_message]);
      
      // Clear input and attachment
      setInputText("");
      setImageAttachment(null);
      
      // Reset textarea height
      if (textareaRef.current) {
        textareaRef.current.style.height = "auto";
      }
    } catch (error) {
      console.error("Failed to send message:", error);
      alert(error instanceof Error ? error.message : "Failed to send message");
    } finally {
      setLoading(false);
    }
  };
  
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };
  
  const handleTextareaChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputText(e.target.value);
    
    // Auto-resize textarea
    e.target.style.height = "auto";
    e.target.style.height = `${e.target.scrollHeight}px`;
  };
  
  const handleImageSelect = async (file: File) => {
    try {
      const payload = await fileToImagePayload(file);
      setImageAttachment({
        base64: payload.base64,
        mimeType: payload.mimeType,
        preview: payload.previewUrl,
        fileName: payload.fileName,
      });
    } catch (error) {
      alert(error instanceof Error ? error.message : "Invalid image file");
    }
  };
  
  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      handleImageSelect(file);
    }
    e.target.value = "";
  };
  
  const removeImageAttachment = () => {
    setImageAttachment(null);
  };
  
  const startNewConversation = () => {
    setMessages([]);
    setConversationId(undefined);
    setInputText("");
    setImageAttachment(null);
    localStorage.removeItem(conversationStorageKey);
  };
  
  return (
    <div className="chat-interface">
      <div className="chat-header">
        <div className="chat-header-content">
          <h2 className="chat-title">DantShaant AI Assistant</h2>
          <p className="chat-subtitle">Your oral health companion</p>
        </div>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={startNewConversation}
        >
          New Chat
        </button>
      </div>
      
      <div className="chat-messages">
        {messages.length === 0 ? (
          <div className="chat-empty">
            <div className="chat-empty-icon">💬</div>
            <h3 className="chat-empty-title">Start a conversation</h3>
            <p className="chat-empty-text">
              Ask me about oral health, or share a photo of your teeth for analysis
            </p>
            <div className="chat-suggestions">
              <button
                type="button"
                className="chat-suggestion"
                onClick={() => setInputText("How often should I brush my teeth?")}
              >
                How often should I brush?
              </button>
              <button
                type="button"
                className="chat-suggestion"
                onClick={() => setInputText("What causes tooth sensitivity?")}
              >
                What causes sensitivity?
              </button>
              <button
                type="button"
                className="chat-suggestion"
                onClick={() => fileInputRef.current?.click()}
              >
                📷 Analyze my teeth
              </button>
            </div>
          </div>
        ) : (
          <>
            {messages.map((msg) => (
              <ChatMessageBubble key={msg.message_id} message={msg} />
            ))}
            {loading && (
              <div className="chat-message chat-message--assistant">
                <div className="chat-message-header">
                  <span className="chat-message-sender">DantShaant AI</span>
                </div>
                <div className="chat-message-content">
                  <div className="chat-typing">
                    <span></span>
                    <span></span>
                    <span></span>
                  </div>
                </div>
              </div>
            )}
          </>
        )}
        <div ref={messagesEndRef} />
      </div>
      
      <div className="chat-input-container">
        {imageAttachment && (
          <div className="chat-image-preview">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={imageAttachment.preview} alt="Attachment" />
            <div className="chat-image-preview-info">
              <span className="chat-image-preview-name">{imageAttachment.fileName}</span>
              <button
                type="button"
                className="chat-image-preview-remove"
                onClick={removeImageAttachment}
              >
                ✕
              </button>
            </div>
          </div>
        )}
        
        <div className="chat-input-wrapper">
          <button
            type="button"
            className="chat-attach-btn"
            onClick={() => fileInputRef.current?.click()}
            disabled={loading}
            title="Attach image"
          >
            📎
          </button>
          
          <textarea
            ref={textareaRef}
            className="chat-input"
            placeholder="Type a message or attach an image..."
            value={inputText}
            onChange={handleTextareaChange}
            onKeyDown={handleKeyDown}
            disabled={loading}
            rows={1}
          />
          
          <button
            type="button"
            className="chat-send-btn"
            onClick={handleSendMessage}
            disabled={loading || (!inputText.trim() && !imageAttachment)}
          >
            {loading ? "..." : "Send"}
          </button>
          
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            hidden
            onChange={handleFileInput}
          />
        </div>
      </div>
    </div>
  );
}

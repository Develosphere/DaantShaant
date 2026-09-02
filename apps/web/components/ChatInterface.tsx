"use client";

import { useEffect, useRef, useState } from "react";
import { useLanguage } from "@/i18n";
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
  const { t } = useLanguage();
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
      
      if (savedConvId) {
        try {
          setConversationId(savedConvId);
          await loadConversation(savedConvId);
        } catch (error) {
          console.error("Failed to load saved conversation:", error);
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
      const msgs = await getConversationMessages(convId);
      setMessages(msgs);
    } catch (error) {
      console.error("Failed to load conversation:", error);
      throw error;
    }
  };
  
  const handleSendMessage = async (textToSend?: string) => {
    const messageText = textToSend ?? inputText;
    if (!messageText.trim() && !imageAttachment) return;
    
    setLoading(true);
    
    try {
      const response = await sendChatMessage(
        messageText || "Please analyze this image",
        conversationId,
        imageAttachment?.base64,
        imageAttachment?.mimeType
      );
      
      if (!conversationId) {
        setConversationId(response.conversation_id);
        localStorage.setItem(conversationStorageKey, response.conversation_id);
      }
      
      setMessages((prev) => [...prev, response.user_message, response.assistant_message]);
      setInputText("");
      setImageAttachment(null);
      
      if (textareaRef.current) {
        textareaRef.current.style.height = "auto";
      }
    } catch (error) {
      console.error("Failed to send message:", error);
      alert(error instanceof Error ? error.message : t("common.error"));
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
          <h2 className="chat-title">{t("chat.title")}</h2>
          <p className="chat-subtitle">{t("chat.subtitle")}</p>
        </div>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={startNewConversation}
        >
          {t("chat.new_chat")}
        </button>
      </div>
      
      <div className="chat-messages">
        {messages.length === 0 ? (
          <div className="chat-empty">
            <div className="chat-empty-icon">💬</div>
            <h3 className="chat-empty-title">{t("chat.empty_title")}</h3>
            <p className="chat-empty-text">
              {t("chat.empty_text")}
            </p>
            <div className="chat-suggestions">
              <button
                type="button"
                className="chat-suggestion"
                onClick={() => handleSendMessage(t("chat.starter_brush"))}
              >
                {t("chat.starter_brush")}
              </button>
              <button
                type="button"
                className="chat-suggestion"
                onClick={() => handleSendMessage(t("chat.starter_sensitivity"))}
              >
                {t("chat.starter_sensitivity")}
              </button>
              <button
                type="button"
                className="chat-suggestion"
                onClick={() => fileInputRef.current?.click()}
              >
                {t("chat.starter_screen")}
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
                  <span className="chat-message-sender">{t("chat.assistant_name")}</span>
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
            title={t("chat.attach_image")}
          >
            📎
          </button>
          
          <textarea
            ref={textareaRef}
            className="chat-input"
            placeholder={t("chat.input_placeholder")}
            value={inputText}
            onChange={handleTextareaChange}
            onKeyDown={handleKeyDown}
            disabled={loading}
            rows={1}
          />
          
          <button
            type="button"
            className="chat-send-btn"
            onClick={() => handleSendMessage()}
            disabled={loading || (!inputText.trim() && !imageAttachment)}
          >
            {loading ? "..." : t("chat.send")}
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


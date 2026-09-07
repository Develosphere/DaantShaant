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

type ChatRequestState = "idle" | "sending" | "stopped" | "error";

export function ChatInterface({
  conversationStorageKey = "dantshaant_current_conversation",
}: Props) {
  const { t } = useLanguage();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputText, setInputText] = useState("");
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [requestState, setRequestState] = useState<ChatRequestState>("idle");
  const [imageAttachment, setImageAttachment] = useState<{
    base64: string;
    mimeType: string;
    preview: string;
    fileName: string;
  } | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const isSubmittingRef = useRef<boolean>(false);
  const loadedKeyRef = useRef<string | null>(null);

  const scrollToBottom = (behavior: ScrollBehavior = "smooth") => {
    messagesEndRef.current?.scrollIntoView({ behavior });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, requestState]);

  // Load conversation from localStorage if exists
  useEffect(() => {
    const loadSavedConversation = async () => {
      const savedConvId = localStorage.getItem(conversationStorageKey);

      if (savedConvId && loadedKeyRef.current !== savedConvId) {
        loadedKeyRef.current = savedConvId;
        try {
          setConversationId(savedConvId);
          const msgs = await getConversationMessages(savedConvId);
          setMessages(msgs);
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

  const handleSendMessage = async (textToSend?: string) => {
    const messageText = textToSend ?? inputText;
    if (!messageText.trim() && !imageAttachment) return;
    if (requestState === "sending" || isSubmittingRef.current) return;

    isSubmittingRef.current = true;
    const outgoingText = messageText.trim();
    const outgoingImage = imageAttachment;

    // 1. Optimistically clear input and attachment immediately
    setInputText("");
    setImageAttachment(null);
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }

    // 2. Optimistically append user message bubble to chat immediately
    const tempUserMsgId = `temp_user_${Date.now()}`;
    const optimisticUserMsg: ChatMessage = {
      message_id: tempUserMsgId,
      conversation_id: conversationId || "",
      sender: "user",
      text: outgoingText || "Please analyze this image",
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimisticUserMsg]);

    // 3. Initiate request with AbortController
    const controller = new AbortController();
    abortControllerRef.current = controller;
    setRequestState("sending");

    try {
      const response = await sendChatMessage(
        outgoingText || "Please analyze this image",
        conversationId,
        outgoingImage?.base64,
        outgoingImage?.mimeType,
        controller.signal
      );

      if (!conversationId && response.conversation_id) {
        setConversationId(response.conversation_id);
        localStorage.setItem(conversationStorageKey, response.conversation_id);
      }

      // Replace optimistic temporary message with server-confirmed messages
      setMessages((prev) => {
        const filtered = prev.filter((m) => m.message_id !== tempUserMsgId);
        return [...filtered, response.user_message, response.assistant_message];
      });
      setRequestState("idle");
    } catch (error: unknown) {
      const err = error as { name?: string; message?: string };
      if (err?.name === "AbortError" || controller.signal.aborted) {
        setRequestState("stopped");
        const stopNotice: ChatMessage = {
          message_id: `stopped_${Date.now()}`,
          conversation_id: conversationId || "",
          sender: "assistant",
          text: t("chat.stopped", "Message generation stopped."),
          timestamp: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, stopNotice]);
      } else {
        console.error("Failed to send message:", error);
        setRequestState("error");
        const rawErr = err?.message || "";
        let fallbackText = t(
          "chat.timeout_error",
          "That response took too long. Please try again."
        );
        if (rawErr.includes("503") || rawErr.toLowerCase().includes("unavailable")) {
          fallbackText = t(
            "chat.service_unavailable",
            "Patient history is temporarily unavailable. Please retry in a moment."
          );
        }
        const errNotice: ChatMessage = {
          message_id: `error_${Date.now()}`,
          conversation_id: conversationId || "",
          sender: "assistant",
          text: fallbackText,
          timestamp: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, errNotice]);
      }
    } finally {
      abortControllerRef.current = null;
      isSubmittingRef.current = false;
      setRequestState((curr) => (curr === "sending" ? "idle" : curr));
    }
  };

  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setRequestState("stopped");
    isSubmittingRef.current = false;
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
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setMessages([]);
    setConversationId(undefined);
    setInputText("");
    setImageAttachment(null);
    setRequestState("idle");
    isSubmittingRef.current = false;
    loadedKeyRef.current = null;
    localStorage.removeItem(conversationStorageKey);
  };

  const isSending = requestState === "sending";

  return (
    <div className="chat-interface">
      <div className="chat-header">
        <div className="chat-header-content">
          <h2 className="chat-title">{t("chat.title", "DaantShaant")}</h2>
          <p className="chat-subtitle">
            {t("chat.subtitle", "AI-assisted oral health guidance grounded in your records")}
          </p>
        </div>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={startNewConversation}
        >
          {t("chat.new_chat", "New Chat")}
        </button>
      </div>

      <div className="chat-messages">
        {messages.length === 0 ? (
          <div className="chat-empty">
            <div className="chat-empty-icon">💬</div>
            <h3 className="chat-empty-title">
              {t("chat.empty_title", "How can I help you today?")}
            </h3>
            <p className="chat-empty-text">
              {t(
                "chat.empty_text",
                "Ask questions about your latest oral screening, findings, appointments, or oral hygiene tips."
              )}
            </p>
            <div className="chat-suggestions">
              <button
                type="button"
                className="chat-suggestion"
                onClick={() => handleSendMessage(t("chat.starter_brush"))}
                disabled={isSending}
              >
                {t("chat.starter_brush", "What is the best way to brush my teeth?")}
              </button>
              <button
                type="button"
                className="chat-suggestion"
                onClick={() => handleSendMessage(t("chat.starter_sensitivity"))}
                disabled={isSending}
              >
                {t("chat.starter_sensitivity", "Why are my teeth sensitive to cold drinks?")}
              </button>
              <button
                type="button"
                className="chat-suggestion"
                onClick={() => fileInputRef.current?.click()}
                disabled={isSending}
              >
                {t("chat.starter_screen", "Can you review my latest screening results?")}
              </button>
            </div>
          </div>
        ) : (
          <>
            {messages.map((msg) => (
              <ChatMessageBubble key={msg.message_id} message={msg} />
            ))}
            {isSending && (
              <div className="chat-message chat-message--assistant">
                <div className="chat-message-header">
                  <span className="chat-message-sender">
                    {t("chat.assistant_name", "DaantShaant")}
                  </span>
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
                disabled={isSending}
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
            disabled={isSending}
            title={t("chat.attach_image", "Attach image")}
          >
            📎
          </button>

          <textarea
            ref={textareaRef}
            className="chat-input"
            placeholder={t("chat.input_placeholder", "Ask your oral health question...")}
            value={inputText}
            onChange={handleTextareaChange}
            onKeyDown={handleKeyDown}
            rows={1}
          />

          {isSending ? (
            <button
              type="button"
              className="chat-send-btn chat-stop-btn"
              onClick={handleStop}
              title={t("chat.stop", "Stop")}
              style={{
                backgroundColor: "#dc2626",
                color: "#ffffff",
                borderColor: "#dc2626",
                fontWeight: 600,
              }}
            >
              ⏹ {t("chat.stop", "Stop")}
            </button>
          ) : (
            <button
              type="button"
              className="chat-send-btn"
              onClick={() => handleSendMessage()}
              disabled={!inputText.trim() && !imageAttachment}
            >
              {t("chat.send", "Send")}
            </button>
          )}

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

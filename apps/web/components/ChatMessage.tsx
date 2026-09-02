"use client";

import { useState, useEffect } from "react";
import type { ChatMessage } from "@/lib/types";
import { DiagnosisReport } from "./DiagnosisReport";
import { CheckoutModal } from "./CheckoutModal";
import Link from "next/link";

type ChatMessageProps = {
  message: ChatMessage;
};

interface ParsedRec {
  name: string;
  price: string;
  why: string;
  helpsWith: string[];
}

function parseRecommendations(text: string): ParsedRec[] {
  const recommendations: ParsedRec[] = [];
  const lines = text.split("\n");
  let currentRec: Partial<ParsedRec> | null = null;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    
    // Header pattern matches: 1. Product Name — $19.99 or 1. Product Name - $19.99
    const headerMatch = line.match(/^\d+\.\s*(.+?)\s*(?:—|-)\s*\$?([0-9]+(?:\.[0-9]{2})?)/);
    
    if (headerMatch) {
      if (currentRec && currentRec.name) {
        recommendations.push(currentRec as ParsedRec);
      }
      currentRec = {
        name: headerMatch[1].trim(),
        price: headerMatch[2].trim(),
        why: "",
        helpsWith: []
      };
    } else if (currentRec) {
      const lower = line.toLowerCase();
      if (lower.startsWith("why:")) {
        currentRec.why = line.substring(4).trim();
      } else if (lower.startsWith("helps with:")) {
        let helpsText = line.substring(11).trim();
        if (helpsText.startsWith("[") && helpsText.endsWith("]")) {
          helpsText = helpsText.substring(1, helpsText.length - 1);
        }
        currentRec.helpsWith = helpsText.split(",").map(s => s.trim()).filter(Boolean);
      }
    }
  }
  
  if (currentRec && currentRec.name) {
    recommendations.push(currentRec as ParsedRec);
  }
  
  return recommendations;
}

function ChatProductCard({ name, parsedPrice, parsedWhy, parsedHelps, onBuy }: {
  name: string;
  parsedPrice: string;
  parsedWhy: string;
  parsedHelps: string[];
  onBuy: (product: any) => void;
}) {
  const [product, setProduct] = useState<any | null>(null);

  useEffect(() => {
    const fetchProduct = async () => {
      try {
        const API_BASE = process.env.NEXT_PUBLIC_ORCHESTRATOR_URL ?? "http://127.0.0.1:8000";
        const res = await fetch(`${API_BASE}/portal/products/?search=${encodeURIComponent(name)}&limit=3`);
        if (res.ok) {
          const data = await res.json();
          if (data && data.length > 0) {
            const match = data.find((p: any) => p.name.toLowerCase().includes(name.toLowerCase())) || data[0];
            setProduct(match);
          }
        }
      } catch (e) {
        console.error("Failed to fetch product detail for chat bubble:", e);
      }
    };
    void fetchProduct();
  }, [name]);

  const displayProduct = product || {
    name,
    price: parseFloat(parsedPrice) || 0,
    ai_description: parsedWhy,
    problems_solved: parsedHelps,
    images: []
  };

  const imageSrc = displayProduct.images && displayProduct.images.length > 0 
    ? displayProduct.images[0] 
    : "";

  return (
    <div className="rec-product-card rec-product-card--split" style={{ marginTop: "0.75rem" }}>
      <div className="rec-product-image-container">
        {imageSrc ? (
          <img src={imageSrc} alt={displayProduct.name} className="rec-product-image" />
        ) : (
          <div className="rec-product-image-placeholder">🦷</div>
        )}
      </div>
      <div className="rec-product-details">
        <div className="rec-product-header">
          <span className="rec-product-name">
            {displayProduct.product_id && !displayProduct.product_id.startsWith("mock-") ? (
              <Link href={`/products/${displayProduct.product_id}`} style={{ textDecoration: "none", color: "inherit", fontWeight: 700 }}>
                {displayProduct.name}
              </Link>
            ) : (
              displayProduct.name
            )}
          </span>
          <span className="rec-product-price">${displayProduct.price.toFixed(2)}</span>
        </div>
        <p className="rec-product-desc">{displayProduct.ai_description}</p>
        {displayProduct.problems_solved && displayProduct.problems_solved.length > 0 && (
          <div className="rec-product-tags">
            {displayProduct.problems_solved.map((t: string, idx: number) => (
              <span key={idx} className="rec-product-tag">{t}</span>
            ))}
          </div>
        )}
        <button className="btn btn-buy btn-sm" onClick={() => onBuy(displayProduct)}>
          Buy Now
        </button>
      </div>
    </div>
  );
}

export function ChatMessageBubble({ message }: ChatMessageProps) {
  const isUser = message.sender === "user";
  const [selectedProduct, setSelectedProduct] = useState<any | null>(null);
  const [isCheckoutOpen, setIsCheckoutOpen] = useState(false);

  const handleBuy = (product: any) => {
    setSelectedProduct(product);
    setIsCheckoutOpen(true);
  };

  const recommendations = !isUser ? parseRecommendations(message.text) : [];
  
  return (
    <div className={`chat-message ${isUser ? "chat-message--user" : "chat-message--assistant"}`}>
      <div className="chat-message-header">
        <span className="chat-message-sender">
          {isUser ? "You" : "DaantShaant AI"}
        </span>
        <span className="chat-message-time">
          {new Date(message.timestamp).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </span>
      </div>
      
      <div className="chat-message-content">
        <p className="chat-message-text">{message.text}</p>
        
        {recommendations.length > 0 && (
          <div className="chat-message-recommendations" style={{ marginTop: "1rem" }}>
            <h4 style={{ fontSize: "0.85rem", fontWeight: 700, marginBottom: "0.5rem" }}>
              🛒 Shop Recommended Items
            </h4>
            {recommendations.map((rec, idx) => (
              <ChatProductCard
                key={idx}
                name={rec.name}
                parsedPrice={rec.price}
                parsedWhy={rec.why}
                parsedHelps={rec.helpsWith}
                onBuy={handleBuy}
              />
            ))}
          </div>
        )}
        
        {message.analysis_result && !isUser && (
          <div className="chat-message-analysis">
            <DiagnosisReport
              result={message.analysis_result}
              label="Analysis Results"
              loading={false}
              liveActive={false}
            />
          </div>
        )}
      </div>

      <CheckoutModal
        product={selectedProduct}
        isOpen={isCheckoutOpen}
        onClose={() => setIsCheckoutOpen(false)}
      />
    </div>
  );
}


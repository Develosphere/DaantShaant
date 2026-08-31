"use client";

import { useState, useEffect } from "react";
import type { PipelineResult } from "@/lib/types";
import { CheckoutModal } from "./CheckoutModal";
import Link from "next/link";
import { FindDentistsButton } from "./dentists/FindDentistsButton";

type Props = {
  result: PipelineResult | null;
  label?: string;
  loading?: boolean;
  liveActive?: boolean;
};

function severityClass(severity: string): string {
  const s = severity.toLowerCase();
  if (s === "critical" || s === "high") return "severity-high";
  if (s === "moderate") return "severity-moderate";
  if (s === "mild") return "severity-mild";
  return "severity-none";
}

function conditionIcon(label: string): string {
  const l = label.toLowerCase();
  if (l.includes("healthy")) return "✦";
  if (l.includes("cavity")) return "◉";
  if (l.includes("plaque") || l.includes("tartar")) return "◎";
  if (l.includes("gingivitis") || l.includes("gum")) return "▲";
  if (l.includes("discolor")) return "◐";
  return "?";
}

function formatAction(action: string): string {
  return action.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatLabel(label: string): string {
  return label.replace(/_/g, " ");
}

export function DiagnosisReport({
  result,
  label = "AI Diagnosis",
  loading,
  liveActive,
}: Props) {
  const [recommendedProducts, setRecommendedProducts] = useState<any[]>([]);
  const [loadingRecs, setLoadingRecs] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState<any | null>(null);
  const [isCheckoutOpen, setIsCheckoutOpen] = useState(false);

  const handleBuy = (product: any) => {
    setSelectedProduct(product);
    setIsCheckoutOpen(true);
  };

  useEffect(() => {
    if (!result || !result.diagnosis) {
      setRecommendedProducts([]);
      return;
    }
    
    const condition = result.diagnosis.condition_label.toUpperCase();
    
    // Find the highest confidence visual finding (excluding healthy tissue)
    let highestFinding = "";
    let highestConf = 0;
    if (result.analysis && result.analysis.findings) {
      result.analysis.findings.forEach((f: any) => {
        const lbl = f.label.toLowerCase();
        if (lbl !== "healthy_tissue" && lbl !== "healthy" && f.confidence > highestConf) {
          highestConf = f.confidence;
          highestFinding = lbl;
        }
      });
    }
    
    const fetchRecs = async () => {
      setLoadingRecs(true);
      try {
        const API_BASE = process.env.NEXT_PUBLIC_ORCHESTRATOR_URL ?? "http://127.0.0.1:8000";
        
        if (condition.includes("HEALTHY")) {
          // Query for toothbrush and toothpaste category products
          const [resBrush, resPaste] = await Promise.all([
            fetch(`${API_BASE}/portal/products/?category=toothbrush&limit=1`),
            fetch(`${API_BASE}/portal/products/?category=toothpaste&limit=1`)
          ]);
          
          let brushData: any[] = [];
          let pasteData: any[] = [];
          
          if (resBrush.ok) brushData = await resBrush.json();
          if (resPaste.ok) pasteData = await resPaste.json();
          
          let finalProducts = [...brushData];
          if (brushData.length === 0) {
            finalProducts.push({
              product_id: "mock-toothbrush",
              name: "Ultra-Soft Eco Toothbrush",
              category: "toothbrush",
              price: 4.99,
              ai_description: "Gentle multi-level bristles designed to clean deep between teeth and along the gumline without irritation. Sustainable bamboo handle.",
              problems_solved: ["Daily plaque removal", "Gum protection"],
              images: []
            });
          }
          
          if (pasteData.length === 0) {
            finalProducts.push({
              product_id: "mock-toothpaste",
              name: "Enamel Care Fluoride Toothpaste",
              category: "toothpaste",
              price: 5.49,
              ai_description: "Remineralizes weakened enamel, protects against cavities, and delivers long-lasting fresh breath with natural mint.",
              problems_solved: ["Cavity prevention", "Enamel repair"],
              images: []
            });
          } else {
            finalProducts.push(pasteData[0]);
          }
          setRecommendedProducts(finalProducts);
          return;
        }

        // Map condition or highest visual finding to search query
        let searchQuery = "";
        if (condition.includes("CAVITY") || highestFinding.includes("cavity") || highestFinding.includes("decay")) {
          searchQuery = "cavity";
        } else if (condition.includes("PLAQUE") || condition.includes("TARTAR") || highestFinding.includes("plaque") || highestFinding.includes("tartar")) {
          searchQuery = "plaque";
        } else if (condition.includes("GINGIVITIS") || condition.includes("GUM") || highestFinding.includes("gingivitis") || highestFinding.includes("gum")) {
          searchQuery = "gum";
        } else if (condition.includes("DISCOLOR") || highestFinding.includes("discolor")) {
          searchQuery = "discoloration";
        } else {
          searchQuery = "toothbrush";
        }
        
        const res = await fetch(`${API_BASE}/portal/products/?search=${encodeURIComponent(searchQuery)}&limit=3`);
        if (res.ok) {
          let data = await res.json();
          // Fallback if search returns nothing
          if (data.length === 0) {
            const fallbackRes = await fetch(`${API_BASE}/portal/products/?limit=3`);
            if (fallbackRes.ok) {
              data = await fallbackRes.json();
            }
          }
          setRecommendedProducts(data);
        }
      } catch (e) {
        console.error("Error fetching recommended products:", e);
      } finally {
        setLoadingRecs(false);
      }
    };
    
    void fetchRecs();
  }, [result]);

  if (loading) {
    return (
      <aside className="report-panel report-panel--loading">
        <div className="report-header">
          <h2>{label}</h2>
          <span className="chip chip-analyzing">Analyzing</span>
        </div>
        <div className="loader-ring">
          <div className="loader-ring-inner" />
        </div>
        <p className="loader-text">Running vision model & clinical mapping…</p>
      </aside>
    );
  }

  if (!result) {
    return (
      <aside className="report-panel report-panel--empty">
        <div className="report-header">
          <h2>{label}</h2>
        </div>
        <div className="empty-illustration">
          <div className="empty-icon">🦷</div>
          <p className="empty-title">Your report appears here</p>
          <p className="empty-desc">
            Start the camera, upload a photo, or run live analysis. Results
            update in real time.
          </p>
        </div>
        <ul className="empty-steps">
          <li><span>1</span> Camera or upload</li>
          <li><span>2</span> Align teeth in frame</li>
          <li><span>3</span> Analyze</li>
        </ul>
      </aside>
    );
  }

  const { analysis, diagnosis } = result;
  const confidencePct = Math.round(diagnosis.confidence * 100);
  const sevClass = severityClass(diagnosis.severity);

  return (
    <aside className={`report-panel report-panel--ready ${liveActive ? "report-panel--live" : ""}`}>
      <div className="report-header">
        <h2>{label}</h2>
        {liveActive && (
          <span className="chip chip-live">
            <span className="live-dot" /> Live
          </span>
        )}
      </div>

      <div className={`condition-hero ${sevClass}`}>
        <div className="condition-icon">{conditionIcon(diagnosis.condition_label)}</div>
        <div className="condition-body">
          <span className="condition-label">Detected condition</span>
          <h3 className="condition-name">{diagnosis.condition_label}</h3>
          <span className={`severity-badge ${sevClass}`}>{diagnosis.severity}</span>
        </div>
        <div className="confidence-ring" style={{ "--pct": confidencePct } as React.CSSProperties}>
          <svg viewBox="0 0 36 36">
            <path
              className="ring-bg"
              d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
            />
            <path
              className="ring-fill"
              strokeDasharray={`${confidencePct}, 100`}
              d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
            />
          </svg>
          <span className="ring-value">{confidencePct}%</span>
        </div>
      </div>

      <div className="stat-cards">
        <div className="stat-card stat-card-wide">
          <span className="stat-label">Recommended action</span>
          <span className="stat-action">{formatAction(diagnosis.action_trigger)}</span>
        </div>
      </div>

      {analysis.findings.length > 0 && (
        <div className="findings-block">
          <h4>Visual findings</h4>
          <div className="finding-chips">
            {analysis.findings.map((f, i) => (
              <div key={i} className="finding-chip">
                <span className="finding-name">{formatLabel(f.label)}</span>
                <div className="finding-bar-wrap">
                  <div
                    className="finding-bar"
                    style={{ width: `${Math.round(f.confidence * 100)}%` }}
                  />
                </div>
                <span className="finding-pct">{Math.round(f.confidence * 100)}%</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {diagnosis.meets_threshold === false && (
        <p className="alert alert-warn">Low confidence — try a clearer, well-lit teeth photo.</p>
      )}
      {analysis.model_id === "stub-fallback" && (
        <p className="alert alert-warn">
          Gemini unavailable — showing placeholder data. Check API key and restart backend.
        </p>
      )}

      {!loading && result && !liveActive && recommendedProducts.length > 0 && (
        <div className="recommendations-block">
          <h4>🦷 Recommended Products</h4>
          <div className="recommendations-list">
            {recommendedProducts.map((p, idx) => {
              const imageSrc = p.images && p.images.length > 0 ? p.images[0] : "";
              return (
                <div key={idx} className="rec-product-card rec-product-card--split">
                  <div className="rec-product-image-container">
                    {imageSrc ? (
                      <img src={imageSrc} alt={p.name} className="rec-product-image" />
                    ) : (
                      <div className="rec-product-image-placeholder">🦷</div>
                    )}
                  </div>
                  <div className="rec-product-details">
                    <div className="rec-product-header">
                      <span className="rec-product-name">
                        {p.product_id && !p.product_id.startsWith("mock-") ? (
                          <Link href={`/products/${p.product_id}`} style={{ textDecoration: "none", color: "inherit", fontWeight: 700 }}>
                            {p.name}
                          </Link>
                        ) : (
                          p.name
                        )}
                      </span>
                      <span className="rec-product-price">${p.price.toFixed(2)}</span>
                    </div>
                    <p className="rec-product-desc">{p.ai_description}</p>
                    {p.problems_solved && p.problems_solved.length > 0 && (
                      <div className="rec-product-tags">
                        {p.problems_solved.map((t: string, tIdx: number) => (
                          <span key={tIdx} className="rec-product-tag">{t}</span>
                        ))}
                      </div>
                    )}
                    <button className="btn btn-buy btn-sm" onClick={() => handleBuy(p)}>
                      Buy Now
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {!loading && result && !liveActive && diagnosis.meets_threshold !== false && (
        <div style={{ marginTop: "1.25rem" }}>
          <FindDentistsButton
            issue={diagnosis.condition_label}
            scanId={diagnosis.diagnosis_id}
            severity={diagnosis.severity}
          />
        </div>
      )}

      <p className="disclaimer">{diagnosis.disclaimer}</p>
      
      <CheckoutModal
        product={selectedProduct}
        isOpen={isCheckoutOpen}
        onClose={() => setIsCheckoutOpen(false)}
      />
    </aside>
  );
}

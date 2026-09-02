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

const FINDING_NAME_MAP: Record<string, string> = {
  cavity_suspect: "Possible decay-related visual finding",
  cavity_advanced: "Possible structural decay / tooth wear",
  tartar: "Visible tartar / calculus",
  plaque_detected: "Visible plaque deposits",
  gingivitis_signs: "Visible signs of gum inflammation",
  gum_disease_severe: "Visible signs of advanced gum concern",
  missing_or_damaged_teeth: "Missing or visibly damaged tooth structure",
  discoloration: "Visible tooth surface discoloration",
  healthy_tissue: "Healthy oral tissue appearance",
};

function formatFindingName(label: string): string {
  const key = label.toLowerCase().trim();
  if (FINDING_NAME_MAP[key]) return FINDING_NAME_MAP[key];
  return label.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatAction(action: string): string {
  return action.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function DiagnosisReport({
  result,
  label = "AI Screening Report",
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
        const lbl = (f.label || "").toLowerCase();
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
        <p className="loader-text">Screening oral findings & evaluating clinical urgency…</p>
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
          <p className="empty-title">Your screening report appears here</p>
          <p className="empty-desc">
            Capture a snapshot, upload an image, or start live analysis. Real-time screening
            evaluates oral findings and nearby care recommendations.
          </p>
        </div>
        <ul className="empty-steps">
          <li><span>1</span> Take snapshot or upload image</li>
          <li><span>2</span> AI evaluates oral relevance & findings</li>
          <li><span>3</span> Get screening report & specialist routing</li>
        </ul>
      </aside>
    );
  }

  const { analysis, diagnosis } = result;
  const confidencePct = Math.round((diagnosis.confidence || 0) * 100);
  const sevClass = severityClass(diagnosis.severity);
  const triage = diagnosis.triage ?? null;
  const headline = triage?.condition_summary ?? diagnosis.condition_label.replace(/_/g, " ");
  const urgency = triage?.urgency_level ?? "routine";

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
          <span className="condition-label">
            {triage ? "AI Screening Verdict" : "AI Screening — Possible Concern"}
          </span>
          <h3 className="condition-name">{headline}</h3>
          <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap", alignItems: "center" }}>
            {triage ? (
              <span className={`severity-badge urgency-badge urgency-badge--${urgency}`}>
                Urgency: {urgency.toUpperCase()}
              </span>
            ) : (
              <span className={`severity-badge ${sevClass}`}>{diagnosis.severity}</span>
            )}
          </div>
        </div>
        <div className="confidence-ring" style={{ "--pct": confidencePct } as React.CSSProperties} title="AI visual confidence">
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
          <span className="stat-label">Recommended Action</span>
          <span className="stat-action">
            {triage?.recommended_actions?.[0] ?? formatAction(diagnosis.action_trigger)}
          </span>
        </div>
        {triage && (
          <>
            <div className="stat-card">
              <span className="stat-label">Visit Timeframe</span>
              <span className="stat-action">{triage.visit_timeframe}</span>
            </div>
            <div className="stat-card">
              <span className="stat-label">Recommended Specialist</span>
              <span className="stat-action">
                {triage.recommended_specialist ?? "General dentist"}
              </span>
            </div>
          </>
        )}
      </div>

      {triage && (
        <div className="findings-block triage-block">
          <h4>Clinical Screening Summary</h4>
          <p className="triage-verdict">{triage.verdict}</p>
          {triage.possible_concerns.length > 0 && (
            <>
              <span className="triage-sublabel">Possible Concerns Identified</span>
              <ul className="triage-list">
                {triage.possible_concerns.map((concern) => (
                  <li key={concern}>{concern}</li>
                ))}
              </ul>
            </>
          )}
          {triage.recommended_actions.length > 1 && (
            <>
              <span className="triage-sublabel">Recommended Next Steps</span>
              <ul className="triage-list">
                {triage.recommended_actions.slice(1).map((action) => (
                  <li key={action}>{action}</li>
                ))}
              </ul>
            </>
          )}
          {triage.limitations.length > 0 && (
            <>
              <span className="triage-sublabel">Screening Limitations</span>
              <ul className="triage-list triage-list--dim">
                {triage.limitations.map((limitation) => (
                  <li key={limitation}>{limitation}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      {analysis && analysis.findings && analysis.findings.length > 0 && (
        <div className="findings-block">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.65rem" }}>
            <h4 style={{ margin: 0 }}>Visual Screening Findings</h4>
            <span style={{ fontSize: "0.72rem", color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
              AI Visual Confidence
            </span>
          </div>
          <div className="finding-chips">
            {analysis.findings.map((f, i) => (
              <div key={i} className="finding-chip">
                <span className="finding-name">{formatFindingName(f.label)}</span>
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
        <p className="alert alert-warn">Low visual clarity — try a well-lit photo with teeth clearly visible.</p>
      )}

      {!loading && result && !liveActive && (
        <div style={{ marginTop: "1.25rem" }}>
          <FindDentistsButton
            issue={diagnosis.triage?.recommended_specialist || diagnosis.condition_label}
            scanId={diagnosis.diagnosis_id}
            severity={diagnosis.severity}
          />
        </div>
      )}

      {!loading && result && !liveActive && recommendedProducts.length > 0 && (
        <div className="recommendations-block" style={{ marginTop: "1.5rem" }}>
          <h4>🦷 Oral Care Products for You</h4>
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

      <div className="safety-statement" style={{ marginTop: "1.5rem", padding: "0.85rem 1rem", borderRadius: "10px", background: "rgba(30, 41, 59, 0.6)", border: "1px solid rgba(255, 255, 255, 0.08)", fontSize: "0.78rem", color: "#94a3b8", lineHeight: 1.5 }}>
        🛡️ <strong>Safety Statement:</strong> DaantShaant provides AI-assisted screening, not a medical diagnosis. A licensed dentist should confirm concerns and treatment needs.
      </div>

      <CheckoutModal
        product={selectedProduct}
        isOpen={isCheckoutOpen}
        onClose={() => setIsCheckoutOpen(false)}
      />
    </aside>
  );
}

export type VisualFinding = {
  label: string;
  confidence: number;
  region?: string | null;
  /** Visual clarity reported by clinical vision: "clear" | "partial" | "limited". */
  visibility?: string | null;
};

export type AnalysisResult = {
  analysis_id: string;
  user_id: string;
  findings: VisualFinding[];
  overall_quality_score: number;
  model_id: string;
  inference_ms: number;
  analyzed_at: string;
};

export type UrgencyLevel = "routine" | "soon" | "urgent" | "emergency";

/**
 * Deterministic AI screening triage (Phase 3B-lite). Screening guidance only -
 * never a confirmed diagnosis and never treatment advice.
 */
export type TriageResult = {
  verdict: string;
  condition_summary: string;
  possible_concerns: string[];
  urgency_level: UrgencyLevel;
  recommended_actions: string[];
  recommended_specialist?: string | null;
  visit_timeframe: string;
  limitations: string[];
  supporting_findings: string[];
  rule_ids: string[];
  confidence?: number | null;
  disclaimer: string;
};

export type DiagnosisResult = {
  diagnosis_id: string;
  user_id: string;
  analysis_id: string;
  condition_label: string;
  severity: string;
  confidence: number;
  confidence_threshold: number;
  meets_threshold: boolean;
  action_trigger: string;
  disclaimer: string;
  diagnosed_at: string;
  /** Additive/optional: safer screening wording; legacy keys stay authoritative for routing. */
  triage?: TriageResult | null;
};

export type RelevanceInfo = {
  classification: "relevant" | "retake" | "unrelated";
  recommended_action: "continue" | "retake" | "reject";
  reason: string;
  retake_reason?: string | null;
  confidence: number;
  relevance_score: number;
  visible_regions: string[];
};

export type PipelineResult = {
  status?: "analyzed" | "retake" | "rejected";
  relevance?: RelevanceInfo | null;
  analysis: AnalysisResult;
  diagnosis: DiagnosisResult;
};

// --- Chat Types ---

export type MessageSender = "user" | "assistant";

export type ChatMessage = {
  message_id: string;
  conversation_id: string;
  sender: MessageSender;
  text: string;
  image_url?: string | null;
  analysis_result?: PipelineResult | null;
  timestamp: string;
};

export type ConversationSummary = {
  conversation_id: string;
  user_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_message_preview?: string | null;
};

export type SendMessageResponse = {
  conversation_id: string;
  user_message: ChatMessage;
  assistant_message: ChatMessage;
};

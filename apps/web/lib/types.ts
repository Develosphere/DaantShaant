export type VisualFinding = {
  label: string;
  confidence: number;
  region?: string | null;
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
};

export type PipelineResult = {
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

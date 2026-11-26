export type SpeakerRole = "ENCUESTADOR" | "INFORMANTE" | "OTRA_PERSONA";

export type SttProvider = "assemblyai" | "deepgram" | "local_whisperx";

export type RuleKind = "obligation" | "prohibition" | "conditional" | "evidence";

export type OverrideStatus = "keep" | "followed" | "broken" | "unknown" | "custom" | "reset";

export interface SystemStatus {
  local_whisper_available: boolean;
  cuda_available: boolean;
  gpu_name: string | null;
  vram_gb: number | null;
  ffmpeg_available: boolean;
  ffprobe_available: boolean;
  is_vercel: boolean;
  supabase_configured: boolean;
  hf_token_configured: boolean;
  openrouter_configured: boolean;
  assemblyai_configured: boolean;
  deepgram_configured: boolean;
  recommended_stt_provider: SttProvider;
  jev_available: boolean;
  jev_model: string;
  example_available: boolean;
  default_model: string;
  customized_rules_count: number;
}

export interface TranscriptTurn {
  speaker: string;
  start: number | null;
  end: number | null;
  text: string;
  has_overlap?: boolean;
}

export interface TranscriptResult {
  turns: TranscriptTurn[];
  speakers: string[];
  suggested_roles: Record<string, SpeakerRole>;
  note?: string | null;
  warning?: string | null;
}

export interface ManualOverrideMeta {
  status: string;
  comment: string;
}

export interface WorstWindowInfo {
  window: number;
  p_broken: number;
  time?: [number | null, number | null] | null;
}

export interface EvaluatedInstruction {
  id: string;
  section: string;
  text: string;
  pages: string;
  kind: RuleKind;
  scope: string;
  weight: 1 | 2 | 3;
  verifiability: string;
  p_followed: number;
  p_broken: number;
  p_unknown: number;
  p_followed_if_applicable: number | null;
  gate: number | null;
  note: string;
  worst_window?: WorstWindowInfo;
  expected_broken_windows?: number;
  windows_flagged?: number;
  windows_review?: number;
  original_outcome?: {
    p_followed: number;
    p_broken: number;
    p_unknown: number;
  };
  manual_override?: ManualOverrideMeta | null;
  is_rule_customized?: boolean;
  auditor_guidance?: string;
}

export interface TopRiskItem {
  id: string;
  section: string;
  section_title: string;
  p_broken: number;
  text: string;
  worst_window: number | null;
  time?: [number | null, number | null] | null;
  manual_override?: ManualOverrideMeta | null;
  is_rule_customized?: boolean;
}

export interface SectionSummary {
  title: string;
  n_instructions: number;
  coverage: number | null;
  expected_followed: number | null;
  expected_broken: number | null;
  compliance_rate: number | null;
  compliance_rate_weighted: number | null;
  p_all_followed: number | null;
  p_all_followed_bounds: [number | null, number | null];
  p_at_most_1_broken: number | null;
  p_rate_at_least_80?: number | null;
  p_rate_at_least_90?: number | null;
  top_risks: TopRiskItem[];
}

export interface VerdictInfo {
  label: string;
  level: "ok" | "warn" | "danger" | "muted";
}

export interface OverallSummary {
  n_instructions: number;
  compliance_rate: number | null;
  compliance_rate_weighted: number | null;
  expected_followed: number;
  expected_broken: number;
  coverage: number | null;
  high_risk_count: number;
  review_count: number;
  manual_edit_count?: number;
  verdict: VerdictInfo;
  top_risks: TopRiskItem[];
}

export interface JevEvaluationReport {
  model: string | null;
  mock: boolean;
  warning?: string | null;
  speaker_map: Record<string, SpeakerRole>;
  gates: {
    opening?: number | null;
    closing?: number | null;
  };
  windows: Array<{
    window: number;
    turns: [number, number];
    bytes: number;
    time: [number | null, number | null];
    scopes: string[];
  }>;
  sections: Record<string, SectionSummary>;
  instructions: EvaluatedInstruction[];
  usage: {
    requests: number;
    cache_hits: number;
    input_tokens: number;
    cost_usd: number;
  };
  customized_rules_applied?: number;
  overall: OverallSummary;
}

export interface AuditJob {
  job_id: string;
  filename: string;
  source: string;
  stt_provider: SttProvider | null;
  has_audio: boolean;
  audio_url: string | null;
  status: "queued" | "processing" | "completed" | "error";
  stage: string;
  progress: number;
  duration_seconds: number | null;
  elapsed_seconds: number;
  created_at_iso?: string;
  result: TranscriptResult | null;
  error: string | null;
  eval_status: "idle" | "processing" | "completed" | "error";
  eval_elapsed_seconds: number;
  evaluation: JevEvaluationReport | null;
  eval_error: string | null;
}

export interface JobSummary {
  job_id: string;
  filename: string;
  source: string;
  stt_provider: SttProvider | null;
  has_audio: boolean;
  status: string;
  duration_seconds: number | null;
  eval_status: string;
  created_at_iso?: string;
  compliance_rate_weighted?: number | null;
  verdict?: VerdictInfo | null;
  manual_edit_count?: number;
}

export interface RuleQuestionSpec {
  key: string;
  type: "noul" | "choice";
  instructions: string;
  criteria: Record<string, string>;
  roles: Record<string, string>;
  default_instructions: string;
  default_criteria: Record<string, string>;
}

export interface RuleCatalogItem {
  id: string;
  section: string;
  section_title: string;
  text: string;
  default_text: string;
  pages: string;
  kind: RuleKind;
  scope: string;
  weight: 1 | 2 | 3;
  default_weight: 1 | 2 | 3;
  verifiability: string;
  note: string;
  enabled: boolean;
  auditor_guidance: string;
  is_customized: boolean;
  updated_at?: string | null;
  questions: RuleQuestionSpec[];
}

export interface RuleOverrideInput {
  custom_text?: string | null;
  weight?: number | null;
  enabled: boolean;
  auditor_guidance?: string | null;
  questions_override: Record<
    string,
    {
      instructions?: string | null;
      criteria: Record<string, string>;
    }
  >;
}

export interface EvaluationRuleEditRequest {
  override_status: OverrideStatus;
  custom_probs?: {
    p_followed: number;
    p_broken: number;
    p_unknown: number;
  } | null;
  auditor_comment?: string | null;
  update_future_rule: boolean;
  rule_override?: RuleOverrideInput | null;
}

export type RiskTier = "low" | "medium" | "high";
export type ConfidenceLevel = "high" | "medium" | "low";

export interface EvidenceItem {
  label: string;
  value: string;
  source: string;
}

export interface FactorConfidence {
  level: ConfidenceLevel;
  reasons: string[];
  inputs: Record<string, unknown>;
}

export interface FactorScore {
  key: string;
  label: string;
  score: number;
  max_score: number;
  rationale: string;
  evidence: EvidenceItem[];
  confidence: FactorConfidence;
}

export interface RiskScore {
  alert_id: string;
  total: number;
  tier: RiskTier;
  factors: FactorScore[];
  confidence: FactorConfidence;
  provenance: "ai" | "fallback" | "cached";
  model: string;
  prompt_version: string;
  generated_at: string;
  source_fingerprint: string;
}

export interface AlertSummary {
  id: string;
  transaction_id: string;
  company_id: string;
  company_name: string;
  alert_type: string;
  status: string;
  status_label: string;
  status_reason: string | null;
  sla_breached: boolean;
  amount: number;
  currency: string;
  origin_country: string;
  destination_country: string;
  created_at: string;
  score: RiskScore;
}

export interface AlertDetail extends AlertSummary {
  description: string;
  transaction: {
    id: string;
    company_id: string;
    counterparty: string;
    amount: number;
    currency: string;
    origin_country: string;
    destination_country: string;
    occurred_at: string;
    channel: string;
    purpose: string;
  };
  company: {
    id: string;
    name: string;
    industry: string;
    country: string;
    risk_rating: string;
    pep: boolean;
    sanctions_match: boolean;
    beneficial_owner_layers: number;
    prior_cases: number;
    baseline_average_amount: number;
    baseline_monthly_frequency: number;
  };
  beneficial_owners: Array<{
    id: string;
    name: string;
    ownership_percentage: number;
    is_pep: boolean;
    sanctions_match: boolean;
    nationality: string;
    residence: string;
    relationship: string;
  }>;
  amount_ratio: number;
  activity: Array<{
    period: string;
    transaction_count: number;
    total_amount: number;
    average_amount: number;
    risk_level: number;
  }>;
}

export interface AlertPage {
  items: AlertSummary[];
  page: number;
  page_size: number;
  total: number;
  pages: number;
}

export interface AlertStats {
  total: number;
  high: number;
  medium: number;
  low: number;
  average_score: number;
  open_alerts: number;
  investigating: number;
  closed: number;
  sla_breached: number;
}

export interface Explanation {
  alert_id: string;
  summary: string;
  key_drivers: string[];
  mitigating_factors: string[];
  recommended_checks: string[];
  limitations: string[];
  citations: EvidenceItem[];
  provenance: "ai" | "fallback" | "cached";
  model: string;
  prompt_version: string;
  generated_at: string;
}

export type RecommendedAction = "clear" | "escalate_tier2" | "request_kyc" | "draft_sar";
export type InsightStatus = "generated" | "reviewed" | "approved" | "overridden" | "actioned";
export type InsightConfidence = "high" | "medium" | "low";

export interface ReasoningTraceItem {
  rule_id: string;
  matched: boolean;
  inputs: Record<string, unknown>;
  note: string;
}

export interface UrgencyComponent {
  component: string;
  points: number;
  detail: string;
}

export interface PrecedentCase {
  pattern: string;
  similar_count: number;
  escalated_to_sar_pct: number;
  typical_outcome: string;
}

export interface RoutingSuggestion {
  team: string;
  queue: string;
  jurisdiction: string;
  workload_note: string;
}

export interface ActionableInsight {
  insight_id: string;
  alert_id: string;
  status: InsightStatus;
  recommended_action: RecommendedAction;
  rationale: string;
  reasoning_trace: ReasoningTraceItem[];
  urgency_score: number;
  urgency_breakdown: UrgencyComponent[];
  evidence: EvidenceItem[];
  precedent_cases: PrecedentCase[];
  draft_notes: string;
  draft_disclaimer: string;
  routing_suggestion: RoutingSuggestion;
  confidence: InsightConfidence;
  confidence_reason: string;
  provenance: "rules+ai" | "rules+fallback";
  model: string;
  prompt_version: string;
  generated_at: string;
  source_fingerprint: string;
}

export interface InsightDecisionRequest {
  decision: "approved" | "overridden";
  reason_code?: string | null;
  free_text?: string | null;
  edited_draft_notes?: string | null;
  actor?: string;
}

export interface InsightDecisionRecord {
  insight_id: string;
  alert_id: string;
  decision: "approved" | "overridden";
  reason_code: string | null;
  free_text: string | null;
  edited_draft_notes: string | null;
  actor: string;
  decided_at: string;
  previous_status: InsightStatus;
  resulting_status: InsightStatus;
  framing: string;
}

export interface InsightDecisionResponse {
  insight: ActionableInsight;
  decision: InsightDecisionRecord;
}

export type ChatCitationKind = "factor" | "evidence" | "precedent" | "policy" | "case_field" | "chart";
export type ChatChartType = "activity_vs_baseline" | "factor_breakdown" | "precedent_outcomes";

export interface ChatCitation {
  label: string;
  value: string;
  source: string;
  kind: ChatCitationKind;
}

export interface ChatChartSeries {
  key: string;
  label: string;
  type: "bar" | "line";
}

export interface ChatChartSpec {
  chart_type: ChatChartType;
  title: string;
  x_key: string;
  series: ChatChartSeries[];
  points: Array<Record<string, string | number>>;
  baseline?: number | null;
  currency?: string | null;
  source: string;
  citation_label: string;
}

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
  citations: ChatCitation[];
  chart?: ChatChartSpec | null;
  created_at: string;
}

export interface ChatSuggestion {
  id: string;
  label: string;
  prompt: string;
}

export interface ChatThreadResponse {
  alert_id: string;
  messages: ChatMessage[];
  suggestions: ChatSuggestion[];
  greeting: string;
}

export interface ChatResponse {
  alert_id: string;
  reply: string;
  citations: ChatCitation[];
  chart?: ChatChartSpec | null;
  suggested_draft_snippet?: string | null;
  refused_action: boolean;
  refusal_reason?: string | null;
  provenance: "ai" | "fallback";
  model: string;
  prompt_version: string;
  turn_id: string;
  thread_id: string;
}

export interface ServiceHealth {
  status: "healthy" | "degraded";
  data_mode: "hana" | "demo";
  hana: "connected" | "unavailable" | "not_configured";
  ai_core: "connected" | "unavailable" | "not_configured";
  model: string;
}

export type RiskTier = "low" | "medium" | "high";

export interface EvidenceItem {
  label: string;
  value: string;
  source: string;
}

export interface FactorScore {
  key: string;
  label: string;
  score: number;
  max_score: number;
  rationale: string;
  evidence: EvidenceItem[];
}

export interface RiskScore {
  alert_id: string;
  total: number;
  tier: RiskTier;
  factors: FactorScore[];
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

export interface ServiceHealth {
  status: "healthy" | "degraded";
  data_mode: "hana" | "demo";
  hana: "connected" | "unavailable" | "not_configured";
  ai_core: "connected" | "unavailable" | "not_configured";
  model: string;
}

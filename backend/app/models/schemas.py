from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


RiskTier = Literal["low", "medium", "high"]
ScoreProvenance = Literal["ai", "fallback", "cached"]
ConfidenceLevel = Literal["high", "medium", "low"]


class EvidenceItem(BaseModel):
    label: str
    value: str
    source: str

    @field_validator("label", "value", "source", mode="before")
    @classmethod
    def stringify_evidence_values(cls, value: object) -> str:
        return str(value)


class FactorConfidence(BaseModel):
    level: ConfidenceLevel
    reasons: list[str] = Field(default_factory=list)
    inputs: dict[str, object] = Field(default_factory=dict)


class FactorScore(BaseModel):
    key: str
    label: str
    score: float = Field(ge=0)
    max_score: float = Field(gt=0)
    rationale: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    confidence: FactorConfidence = Field(
        default_factory=lambda: FactorConfidence(level="medium", reasons=["Confidence not yet assessed."])
    )

    @model_validator(mode="after")
    def score_cannot_exceed_maximum(self) -> "FactorScore":
        if self.score > self.max_score:
            raise ValueError(f"{self.key} score exceeds maximum")
        return self


class RiskScore(BaseModel):
    alert_id: str
    total: float = Field(ge=0, le=100)
    tier: RiskTier
    factors: list[FactorScore]
    confidence: FactorConfidence = Field(
        default_factory=lambda: FactorConfidence(level="medium", reasons=["Confidence not yet assessed."])
    )
    provenance: ScoreProvenance = "fallback"
    model: str
    prompt_version: str
    generated_at: datetime
    source_fingerprint: str


class AlertSummary(BaseModel):
    id: str
    transaction_id: str
    company_id: str
    company_name: str
    alert_type: str
    status: str
    status_label: str
    status_reason: str | None = None
    sla_breached: bool = False
    amount: float
    currency: str
    origin_country: str
    destination_country: str
    created_at: datetime
    score: RiskScore


class TransactionDetail(BaseModel):
    id: str
    company_id: str
    counterparty: str
    amount: float
    currency: str
    origin_country: str
    destination_country: str
    occurred_at: datetime
    channel: str
    purpose: str


class CompanyDetail(BaseModel):
    id: str
    name: str
    industry: str
    country: str
    risk_rating: str
    pep: bool
    sanctions_match: bool
    beneficial_owner_layers: int
    prior_cases: int
    baseline_average_amount: float
    baseline_monthly_frequency: float


class BeneficialOwner(BaseModel):
    id: str
    name: str
    ownership_percentage: float
    is_pep: bool
    sanctions_match: bool
    nationality: str
    residence: str
    relationship: str


class ActivityPoint(BaseModel):
    period: str
    transaction_count: int
    total_amount: float
    average_amount: float
    risk_level: float


class AlertDetail(AlertSummary):
    description: str
    transaction: TransactionDetail
    company: CompanyDetail
    beneficial_owners: list[BeneficialOwner] = Field(default_factory=list)
    amount_ratio: float
    activity: list[ActivityPoint] = Field(default_factory=list)


class AlertPage(BaseModel):
    items: list[AlertSummary]
    page: int
    page_size: int
    total: int
    pages: int


class AlertStats(BaseModel):
    total: int
    high: int
    medium: int
    low: int
    average_score: float
    open_alerts: int
    investigating: int
    closed: int
    sla_breached: int


class Explanation(BaseModel):
    alert_id: str
    summary: str
    key_drivers: list[str]
    mitigating_factors: list[str]
    recommended_checks: list[str]
    limitations: list[str]
    citations: list[EvidenceItem]
    provenance: ScoreProvenance
    model: str
    prompt_version: str
    generated_at: datetime


class ServiceHealth(BaseModel):
    status: Literal["healthy", "degraded"]
    data_mode: Literal["hana", "demo"]
    hana: Literal["connected", "unavailable", "not_configured"]
    ai_core: Literal["connected", "unavailable", "not_configured"]
    model: str


RecommendedAction = Literal["clear", "escalate_tier2", "request_kyc", "draft_sar"]
InsightStatus = Literal["generated", "reviewed", "approved", "overridden", "actioned"]
InsightConfidence = Literal["high", "medium", "low"]
InsightProvenance = Literal["rules+ai", "rules+fallback"]
InsightDecision = Literal["approved", "overridden"]


class ReasoningTraceItem(BaseModel):
    rule_id: str
    matched: bool
    inputs: dict[str, object] = Field(default_factory=dict)
    note: str


class UrgencyComponent(BaseModel):
    component: str
    points: float = Field(ge=0)
    detail: str


class PrecedentCase(BaseModel):
    pattern: str
    similar_count: int = Field(ge=0)
    escalated_to_sar_pct: float = Field(ge=0, le=100)
    typical_outcome: str


class RoutingSuggestion(BaseModel):
    team: str
    queue: str
    jurisdiction: str
    workload_note: str


class ActionableInsight(BaseModel):
    insight_id: str
    alert_id: str
    status: InsightStatus
    recommended_action: RecommendedAction
    rationale: str
    reasoning_trace: list[ReasoningTraceItem] = Field(default_factory=list)
    urgency_score: float = Field(ge=0, le=100)
    urgency_breakdown: list[UrgencyComponent] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    precedent_cases: list[PrecedentCase] = Field(default_factory=list)
    draft_notes: str
    draft_disclaimer: str = "DRAFT — requires human edit/approval. Not submitted."
    routing_suggestion: RoutingSuggestion
    confidence: InsightConfidence
    confidence_reason: str
    provenance: InsightProvenance
    model: str
    prompt_version: str
    generated_at: datetime
    source_fingerprint: str


class InsightDecisionRequest(BaseModel):
    decision: InsightDecision
    reason_code: str | None = None
    free_text: str | None = None
    edited_draft_notes: str | None = None
    actor: str = "Amelia Reyes"


class InsightDecisionRecord(BaseModel):
    insight_id: str
    alert_id: str
    decision: InsightDecision
    reason_code: str | None = None
    free_text: str | None = None
    edited_draft_notes: str | None = None
    actor: str
    decided_at: datetime
    previous_status: InsightStatus
    resulting_status: InsightStatus
    framing: str = "decision_quality_audit"


class InsightDecisionResponse(BaseModel):
    insight: ActionableInsight
    decision: InsightDecisionRecord


ChatCitationKind = Literal["factor", "evidence", "precedent", "policy", "case_field", "chart"]
ChatRole = Literal["user", "assistant", "system"]
ChatChartType = Literal["activity_vs_baseline", "factor_breakdown", "precedent_outcomes"]
ChatSeriesType = Literal["bar", "line"]
ChatProvenance = Literal["ai", "fallback"]


class ChatCitation(BaseModel):
    label: str
    value: str
    source: str
    kind: ChatCitationKind


class ChatChartSeries(BaseModel):
    key: str
    label: str
    type: ChatSeriesType


class ChatChartSpec(BaseModel):
    chart_type: ChatChartType
    title: str
    x_key: str
    series: list[ChatChartSeries]
    points: list[dict[str, object]]
    baseline: float | None = None
    currency: str | None = None
    source: str
    citation_label: str


class ChatMessage(BaseModel):
    role: ChatRole
    content: str
    citations: list[ChatCitation] = Field(default_factory=list)
    chart: ChatChartSpec | None = None
    created_at: datetime


class ChatSuggestion(BaseModel):
    id: str
    label: str
    prompt: str


class ChatThreadResponse(BaseModel):
    alert_id: str
    messages: list[ChatMessage] = Field(default_factory=list)
    suggestions: list[ChatSuggestion]
    greeting: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    alert_id: str
    reply: str
    citations: list[ChatCitation] = Field(default_factory=list)
    chart: ChatChartSpec | None = None
    suggested_draft_snippet: str | None = None
    refused_action: bool = False
    refusal_reason: str | None = None
    provenance: ChatProvenance
    model: str
    prompt_version: str
    turn_id: str
    thread_id: str


class ChatAuditRecord(BaseModel):
    turn_id: str
    alert_id: str
    user_message: str
    assistant_reply: str
    citations: list[ChatCitation] = Field(default_factory=list)
    chart_type: ChatChartType | None = None
    refused_action: bool = False
    actor: str = "Amelia Reyes"
    created_at: datetime
    framing: str = "decision_quality_audit"

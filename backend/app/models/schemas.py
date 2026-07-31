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


class IntegrationMeta(BaseModel):
    source: Literal["hana", "demo"]
    normalised_status: str
    raw_status: str | None = None
    scored_queue_cap: int = 250
    privacy_region: str = "AP-Southeast (Singapore BTP)"


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
    integration: IntegrationMeta | None = None


AlertCaseStatus = Literal["open", "investigating", "closed", "closed_timeout"]


class AlertStatusUpdate(BaseModel):
    status: AlertCaseStatus
    actor: str = "Amelia Reyes, Group Chief Risk Officer"


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


class MonthlyOperationsPoint(BaseModel):
    month: str
    raised: int
    closed: int
    transaction_value_usd: float
    sla_breaches: int
    false_positives: int
    true_positives: int
    median_review_hours: float | None = None


class OperationsKpis(BaseModel):
    backlog: int
    open_alerts: int
    investigating: int
    median_review_hours: float | None = None
    closure_rate: float
    sla_adherence_rate: float
    false_positive_rate: float
    review_timeout_rate: float
    high_priority_unresolved: int
    high_priority_exposure_usd: float
    unresolved_exposure_usd: float
    backlog_change: int
    period_raised: int
    period_closed: int
    scored_queue_size: int


class OperationsDashboard(BaseModel):
    data_mode: Literal["hana", "demo"]
    months: list[MonthlyOperationsPoint]
    kpis: OperationsKpis
    notes: list[str] = Field(default_factory=list)


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
InsightStatus = Literal[
    "generated",
    "reviewed",
    "approved",
    "overridden",
    "actioned",
    "further_info_requested",
]
InsightConfidence = Literal["high", "medium", "low"]
InsightProvenance = Literal["rules+ai", "rules+fallback"]
InsightDecision = Literal["approved", "overridden", "request_further_info"]


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
    draft_disclaimer: str = "Draft only — review and approve before submitting."
    draft_email: str | None = None
    draft_email_disclaimer: str = ""
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
    edited_draft_email: str | None = None
    actor: str = "Amelia Reyes, Group Chief Risk Officer"


class InsightEmailDraftRequest(BaseModel):
    decision: InsightDecision = "approved"
    actor: str = "Amelia Reyes, Group Chief Risk Officer"


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


ChatCitationKind = Literal[
    "factor",
    "evidence",
    "precedent",
    "policy",
    "case_field",
    "chart",
    "kpi",
    "definition",
    "note",
]
ChatRole = Literal["user", "assistant", "system"]
ChatChartType = Literal[
    "activity_vs_baseline",
    "factor_breakdown",
    "precedent_outcomes",
    "closed_by_month",
    "raised_vs_closed",
    "sla_breaches",
    "transaction_value",
]
ChatSeriesType = Literal["bar", "line"]
ChatProvenance = Literal["ai", "fallback"]
RangeMonths = Literal[6, 12]


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
    suggested_email_draft: str | None = None
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
    actor: str = "Amelia Reyes, Group Chief Risk Officer"
    created_at: datetime
    framing: str = "decision_quality_audit"


class PerformanceChatThreadResponse(BaseModel):
    range_months: RangeMonths
    messages: list[ChatMessage] = Field(default_factory=list)
    suggestions: list[ChatSuggestion]
    greeting: str


class PerformanceChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    range_months: RangeMonths = 12


class PerformanceChatResponse(BaseModel):
    range_months: RangeMonths
    reply: str
    citations: list[ChatCitation] = Field(default_factory=list)
    chart: ChatChartSpec | None = None
    refused_action: bool = False
    refusal_reason: str | None = None
    provenance: ChatProvenance
    model: str
    prompt_version: str
    turn_id: str
    thread_id: str


class PerformanceChatAuditRecord(BaseModel):
    turn_id: str
    thread_id: str
    range_months: RangeMonths
    user_message: str
    assistant_reply: str
    citations: list[ChatCitation] = Field(default_factory=list)
    chart_type: ChatChartType | None = None
    refused_action: bool = False
    actor: str = "Amelia Reyes, Group Chief Risk Officer"
    created_at: datetime
    framing: str = "operations_decision_support"


AuditEventType = Literal["insight_decision", "case_chat", "performance_chat"]


class AuditEvent(BaseModel):
    event_type: AuditEventType
    timestamp: datetime
    alert_id: str | None = None
    actor: str
    summary: str
    refused_action: bool = False
    detail: dict[str, object] = Field(default_factory=dict)


class AuditPage(BaseModel):
    items: list[AuditEvent]
    total: int
    privacy: dict[str, str] = Field(default_factory=dict)

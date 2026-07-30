from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


RiskTier = Literal["low", "medium", "high"]
ScoreProvenance = Literal["ai", "fallback", "cached"]


class EvidenceItem(BaseModel):
    label: str
    value: str
    source: str

    @field_validator("label", "value", "source", mode="before")
    @classmethod
    def stringify_evidence_values(cls, value: object) -> str:
        return str(value)


class FactorScore(BaseModel):
    key: str
    label: str
    score: float = Field(ge=0)
    max_score: float = Field(gt=0)
    rationale: str
    evidence: list[EvidenceItem] = Field(default_factory=list)

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


class AlertDetail(AlertSummary):
    description: str
    transaction: TransactionDetail
    company: CompanyDetail


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

from __future__ import annotations

import math
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_repository, get_scoring_engine
from app.models.schemas import (
    AlertDetail,
    AlertPage,
    AlertStats,
    AlertSummary,
    ActivityPoint,
    BeneficialOwner,
    CompanyDetail,
    RiskScore,
    TransactionDetail,
)
from app.services.repository import RiskRepository
from app.services.scoring_engine import ScoringEngine


router = APIRouter(prefix="/alerts", tags=["alerts"])


def _summary(context: dict, score: RiskScore) -> AlertSummary:
    return AlertSummary(
        id=str(context["id"]),
        transaction_id=str(context["transaction_id"]),
        company_id=str(context["company_id"]),
        company_name=str(context["company_name"]),
        alert_type=str(context["alert_type"]),
        status=str(context["status"]),
        status_label=str(context["status_label"]),
        status_reason=context.get("status_reason"),
        sla_breached=bool(context.get("sla_breached")),
        amount=float(context["amount"]),
        currency=str(context["currency"]),
        origin_country=str(context["origin_country"]),
        destination_country=str(context["destination_country"]),
        created_at=context["created_at"],
        score=score,
    )


def _detail(context: dict, score: RiskScore, repository: RiskRepository) -> AlertDetail:
    transaction = context["transaction"]
    company = context["company"]
    owners = repository.get_beneficial_owners(str(context["company_id"]))
    activity = repository.get_transaction_activity(str(context["company_id"]), score.total)
    return AlertDetail(
        **_summary(context, score).model_dump(),
        description=str(context["description"]),
        transaction=TransactionDetail(
            id=str(context["transaction_id"]),
            company_id=str(context["company_id"]),
            counterparty=str(transaction["counterparty"]),
            amount=float(context["amount"]),
            currency=str(context["currency"]),
            origin_country=str(context["origin_country"]),
            destination_country=str(context["destination_country"]),
            occurred_at=transaction["occurred_at"],
            channel=str(transaction["channel"]),
            purpose=str(transaction["purpose"]),
        ),
        company=CompanyDetail(
            id=str(context["company_id"]),
            name=str(context["company_name"]),
            industry=str(company["industry"]),
            country=str(company["country"]),
            risk_rating=str(company["risk_rating"]),
            pep=bool(company["pep"]),
            sanctions_match=bool(company["sanctions_match"]),
            beneficial_owner_layers=int(company["beneficial_owner_layers"]),
            prior_cases=int(company["prior_cases"]),
            baseline_average_amount=float(company["baseline_average_amount"]),
            baseline_monthly_frequency=float(company["baseline_monthly_frequency"]),
        ),
        beneficial_owners=[
            BeneficialOwner(
                id=str(owner["id"]),
                name=str(owner["name"]),
                ownership_percentage=float(owner.get("ownership_percentage") or 0),
                is_pep=bool(owner.get("is_pep")),
                sanctions_match=bool(owner.get("sanctions_match")),
                nationality=str(owner.get("nationality") or "Not supplied"),
                residence=str(owner.get("residence") or "Not supplied"),
                relationship="Direct beneficial owner",
            )
            for owner in owners
        ],
        amount_ratio=round(float(context["signals"].get("amount_ratio") or 0), 1),
        activity=[
            ActivityPoint(
                period=str(point["period"]),
                transaction_count=int(point.get("transaction_count") or 0),
                total_amount=float(point.get("total_amount") or 0),
                average_amount=float(point.get("average_amount") or 0),
                risk_level=float(point.get("risk_level") or score.total),
            )
            for point in activity
        ],
    )


@router.get("", response_model=AlertPage)
def list_alerts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    tier: Literal["low", "medium", "high"] | None = None,
    status: str | None = None,
    search: str | None = None,
    sort_by: Literal["score", "created_at", "amount", "company_name"] = "score",
    sort_order: Literal["asc", "desc"] = "desc",
    repository: RiskRepository = Depends(get_repository),
    scoring: ScoringEngine = Depends(get_scoring_engine),
) -> AlertPage:
    items = [
        _summary(row, scoring.score_alert(str(row["id"]), use_ai=False))
        for row in repository.all_alert_contexts()
    ]
    if tier:
        items = [item for item in items if item.score.tier == tier]
    if status:
        items = [item for item in items if item.status.lower() == status.lower()]
    if search:
        needle = search.lower()
        items = [
            item
            for item in items
            if needle in " ".join((item.id, item.company_name, item.alert_type, item.transaction_id)).lower()
        ]
    key_functions = {
        "score": lambda item: item.score.total,
        "created_at": lambda item: item.created_at,
        "amount": lambda item: item.amount,
        "company_name": lambda item: item.company_name.lower(),
    }
    items.sort(key=key_functions[sort_by], reverse=sort_order == "desc")
    total = len(items)
    start = (page - 1) * page_size
    return AlertPage(
        items=items[start : start + page_size],
        page=page,
        page_size=page_size,
        total=total,
        pages=math.ceil(total / page_size) if total else 0,
    )


@router.get("/stats", response_model=AlertStats)
def alert_stats(
    repository: RiskRepository = Depends(get_repository),
    scoring: ScoringEngine = Depends(get_scoring_engine),
) -> AlertStats:
    rows = repository.all_alert_contexts()
    scores = [scoring.score_alert(str(row["id"]), use_ai=False) for row in rows]
    return AlertStats(
        total=len(scores),
        high=sum(score.tier == "high" for score in scores),
        medium=sum(score.tier == "medium" for score in scores),
        low=sum(score.tier == "low" for score in scores),
        average_score=round(sum(score.total for score in scores) / len(scores), 1) if scores else 0,
        open_alerts=sum(str(row["status"]).lower() == "open" for row in rows),
        investigating=sum(str(row["status"]).lower() == "investigating" for row in rows),
        closed=sum(str(row["status"]).lower() == "closed" for row in rows),
        sla_breached=sum(bool(row.get("sla_breached")) for row in rows),
    )


@router.get("/{alert_id}", response_model=AlertDetail)
def get_alert(
    alert_id: str,
    repository: RiskRepository = Depends(get_repository),
    scoring: ScoringEngine = Depends(get_scoring_engine),
) -> AlertDetail:
    context = repository.get_alert_context(alert_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return _detail(context, scoring.score_alert(alert_id), repository)


@router.get("/{alert_id}/score", response_model=RiskScore)
def get_score(
    alert_id: str,
    repository: RiskRepository = Depends(get_repository),
    scoring: ScoringEngine = Depends(get_scoring_engine),
) -> RiskScore:
    if repository.get_alert_context(alert_id) is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return scoring.score_alert(alert_id)


@router.post("/{alert_id}/score", response_model=RiskScore)
def refresh_score(
    alert_id: str,
    repository: RiskRepository = Depends(get_repository),
    scoring: ScoringEngine = Depends(get_scoring_engine),
) -> RiskScore:
    if repository.get_alert_context(alert_id) is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return scoring.score_alert(alert_id, refresh=True)

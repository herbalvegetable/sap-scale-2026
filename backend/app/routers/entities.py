from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_repository
from app.models.schemas import CompanyDetail, TransactionDetail
from app.services.repository import RiskRepository


router = APIRouter(tags=["entities"])


@router.get("/companies/{company_id}", response_model=CompanyDetail)
def get_company(company_id: str, repository: RiskRepository = Depends(get_repository)) -> CompanyDetail:
    context = next(
        (row for row in repository.all_alert_contexts() if str(row["company_id"]) == company_id),
        None,
    )
    if context is None:
        raise HTTPException(status_code=404, detail="Company not found")
    company = context["company"]
    return CompanyDetail(
        id=company_id,
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
    )


@router.get("/transactions/{transaction_id}", response_model=TransactionDetail)
def get_transaction(
    transaction_id: str,
    repository: RiskRepository = Depends(get_repository),
) -> TransactionDetail:
    context = next(
        (row for row in repository.all_alert_contexts() if str(row["transaction_id"]) == transaction_id),
        None,
    )
    if context is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    transaction = context["transaction"]
    return TransactionDetail(
        id=transaction_id,
        company_id=str(context["company_id"]),
        counterparty=str(transaction["counterparty"]),
        amount=float(context["amount"]),
        currency=str(context["currency"]),
        origin_country=str(context["origin_country"]),
        destination_country=str(context["destination_country"]),
        occurred_at=transaction["occurred_at"],
        channel=str(transaction["channel"]),
        purpose=str(transaction["purpose"]),
    )

"""Run one bounded scoring request without printing credentials or prompt data."""

from app.dependencies import (
    get_ai_core,
    get_intelligence_service,
    get_repository,
    get_scoring_engine,
    get_vector_store,
)
from app.services.ai_core_client import AICoreError


def main() -> None:
    try:
        probe = get_ai_core().chat_json(
            "Return JSON only with a boolean key named ok.",
            {"request": "connectivity check"},
        )
        print({"ai_core_probe": probe})
    except AICoreError as exc:
        print({"ai_core_probe_error": str(exc)})

    repository = get_repository()
    alert_id = str(repository.all_alert_contexts()[0]["id"])
    retrieved = get_vector_store().search(repository.all_alert_contexts()[0]["alert_type"])
    print({"rag_sources": [item["title"] for item in retrieved]})
    result = get_scoring_engine().score_alert(alert_id, refresh=True)
    print(
        {
            "alert_id": result.alert_id,
            "total": result.total,
            "tier": result.tier,
            "provenance": result.provenance,
            "model": result.model,
            "factor_count": len(result.factors),
        }
    )
    explanation = get_intelligence_service().explain_alert(alert_id, refresh=True)
    print(
        {
            "explanation_provenance": explanation.provenance,
            "summary_length": len(explanation.summary),
            "citations": len(explanation.citations),
        }
    )


if __name__ == "__main__":
    main()

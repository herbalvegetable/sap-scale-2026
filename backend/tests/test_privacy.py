from app.services.privacy import privacy_meta, redact_for_llm


def test_privacy_meta_reports_singapore_prompt_minimisation() -> None:
    meta = privacy_meta()
    assert "Singapore" in meta["region"]
    assert meta["mode"] == "prompt_minimisation"


def test_redact_for_llm_masks_company_and_owner_pii() -> None:
    payload = {
        "company_name": "Acme Global Trading Pte Ltd",
        "company": {
            "name": "Acme Global Trading Pte Ltd",
            "pep": True,
            "sanctions_match": False,
            "beneficial_owner_layers": 3,
        },
        "transaction": {
            "counterparty": "Jane Example",
            "purpose": "Invoice settlement for consulting services rendered Q1",
            "amount": 250000,
            "currency": "USD",
            "origin_country": "Singapore",
            "destination_country": "Vietnam",
        },
        "beneficial_owners": [
            {
                "name": "Wei Zhang",
                "nationality": "China",
                "residence": "Singapore",
                "is_pep": False,
                "sanctions_match": False,
            }
        ],
        "alert": {"description": "Large cross-border payment with thin KYC narrative"},
        "signals": {"amount_ratio": 4.2, "fatf_risk": "medium"},
    }

    redacted = redact_for_llm(payload)

    assert "Acme Global Trading" not in str(redacted)
    assert "Jane Example" not in str(redacted)
    assert "Wei Zhang" not in str(redacted)
    assert "China" not in str(redacted["beneficial_owners"])
    assert redacted["company_name"].startswith("Company-")
    assert redacted["transaction"]["counterparty"].startswith("Person-")
    assert "redacted purpose" in redacted["transaction"]["purpose"]
    assert redacted["beneficial_owners"][0]["nationality"] == "[redacted]"
    assert redacted["transaction"]["amount"] == 250000
    assert redacted["company"]["pep"] is True
    assert redacted["_privacy"]["mode"] == "prompt_minimisation"


def test_redact_for_llm_keeps_risk_flags() -> None:
    redacted = redact_for_llm(
        {
            "company": {"pep": True, "sanctions_match": True, "prior_cases": 2},
            "signals": {"rapid_transfers": 3, "supervisory_attention": True},
        }
    )
    assert redacted["company"]["pep"] is True
    assert redacted["company"]["sanctions_match"] is True
    assert redacted["signals"]["rapid_transfers"] == 3

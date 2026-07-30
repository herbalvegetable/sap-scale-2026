# RiskAssess

AI-assisted financial-crime alert triage for the SCALE 2026 TrustSphere Bank case. RiskAssess reads live business context from SAP HANA Cloud, uses GPT-4o through SAP AI Core to score five bounded risk factors, deterministically sums them into a 0–100 priority, and generates a grounded investigator explanation.

## What is implemented

- Live mapping of `RISK_ALERTS`, `TRANSACTIONS`, `COMPANIES`, `COUNTRIES`, `COMPANY_RISK_PROFILES`, `COMPANY_BENEFICIAL_OWNERS`, `TRANSACTION_BASELINES`, and `COMPLIANCE_CASES`.
- Bounded factor scores: entity 25, transaction 25, geography 20, deviation 15, regulatory sensitivity 15.
- SAP AI Core Orchestration `/completion` integration using GPT-4o.
- HANA `REAL_VECTOR(64)` knowledge index and cosine-similarity policy retrieval.
- Deterministic scoring and local retrieval fallbacks when external services are unavailable.
- Red-and-white responsive alert dashboard and evidence-rich alert detail view.

Read [PROJECT_SPEC.md](PROJECT_SPEC.md) for the full business, technical, governance, and acceptance specification.

## Local setup

Prerequisites: Python 3.11+, Node.js 20+, and valid SAP credentials.

### Backend

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
$env:PYTHONPATH="backend"
python -m uvicorn app.main:app --reload --port 8000
```

RiskAssess reads `credentials/team_08.env`, `credentials/team_08_credentials.json`, or a root `.env`. Copy `.env.example` to `.env` for a fresh environment. Set `DATA_MODE=demo` for an entirely offline demonstration.

API documentation is available at `http://localhost:8000/docs`.

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

### Docker

```powershell
docker compose up --build
```

The web app is exposed at `http://localhost:5173`.

## Verification

```powershell
$env:PYTHONPATH="backend"
.\.venv\Scripts\python.exe -m pytest backend\tests -q
cd frontend
npm run build
```

Read-only HANA discovery:

```powershell
$env:PYTHONPATH="backend"
.\.venv\Scripts\python.exe backend\scripts\explore_hana.py
```

One live, bounded AI/RAG smoke test:

```powershell
$env:PYTHONPATH="backend"
.\.venv\Scripts\python.exe backend\scripts\test_ai_core.py
```

## Governance notes

- RiskAssess is decision support. It does not block payments, file SARs, close alerts, or determine guilt.
- Every score exposes factor evidence, model, prompt version, provenance, and generation time.
- Model output is schema-validated; Python calculates the final score.
- Missing AI or HANA capability is clearly represented through fallback provenance and health status.
- Do not commit the supplied credential files. Rotate them if they have been shared outside the authorised competition team.

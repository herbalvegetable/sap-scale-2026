from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from threading import Lock

from app.config import Settings
from app.services.hana_client import HanaClient

logger = logging.getLogger(__name__)
DIMENSIONS = 64

POLICY_DOCUMENTS = [
    {
        "id": "POL-HUMAN-ACCOUNTABILITY",
        "title": "Human accountability requirement",
        "content": "RiskAssess output supports alert prioritisation and investigation only. A human investigator remains accountable for alert disposition, SAR decisions, payment blocking, and customer outcomes. Fully autonomous blocking is prohibited.",
        "source": "TrustSphere Governance Standard",
        "tags": "human review sar payment blocking governance",
    },
    {
        "id": "POL-SANCTIONS-PEP",
        "title": "Sanctions and PEP escalation",
        "content": "Potential sanctions matches require identity verification against the source list and aliases. PEP exposure requires enhanced due diligence and source-of-funds review; neither flag alone establishes criminal activity.",
        "source": "Customer Screening Procedure",
        "tags": "sanctions pep beneficial owner identity edd",
    },
    {
        "id": "POL-STRUCTURING",
        "title": "Structuring and velocity review",
        "content": "Closely timed transfers, repeated values below monitoring thresholds, rapid pass-through activity, and unexplained round-number payments should be reviewed together with linked transactions and the customer's established activity.",
        "source": "Transaction Monitoring Procedure",
        "tags": "structuring velocity threshold rapid transfer transaction behaviour",
    },
    {
        "id": "POL-GEOGRAPHY",
        "title": "Geographic risk assessment",
        "content": "Country risk must consider FATF status, sanctions exposure, corruption risk, the purpose of the corridor, and whether the route is normal for the customer. Geographic exposure is a risk indicator, not proof of wrongdoing.",
        "source": "Country Risk Standard",
        "tags": "fatf country geography corridor sanctions corruption",
    },
    {
        "id": "POL-BASELINE",
        "title": "Behavioural deviation assessment",
        "content": "Investigators should compare amount, frequency, counterparties, and corridors with a representative customer baseline. Data gaps and zero-value baselines must be documented and must not automatically increase risk.",
        "source": "Transaction Monitoring Procedure",
        "tags": "baseline unusual amount frequency counterparty corridor data quality",
    },
    {
        "id": "POL-PRIOR-CASES",
        "title": "Prior case context",
        "content": "Prior compliance cases may increase review priority when facts recur, but investigators must consider outcomes, recency, and whether earlier concerns were cleared. Previous cases do not determine the current disposition.",
        "source": "Case Investigation Standard",
        "tags": "prior case sar outcome regulatory sensitivity history",
    },
    {
        "id": "POL-PEP-SLA",
        "title": "PEP match review SLA",
        "content": "Confirmed or potential PEP associations require enhanced due diligence within 24 hours of alert creation for open payment holds, and within 48 hours for post-settlement monitoring alerts. Medium-FATF jurisdictions do not shorten this SLA; they require documented source-of-funds and purpose-of-payment attestation before Tier-1 clearance. A human investigator must record Approve or Override — chat or AI output cannot complete the disposition.",
        "source": "PEP Escalation Playbook",
        "tags": "pep sla edd medium fatf jurisdiction timeline due diligence",
    },
    {
        "id": "POL-MED-FATF",
        "title": "Medium FATF jurisdiction procedure",
        "content": "For corridors involving medium FATF-risk countries, investigators must verify the commercial purpose, check whether the corridor is established for the customer, and document residual geographic risk. Geographic medium scores alone do not mandate SAR drafting; combine with entity, behavioural, and regulatory factors before recommending escalation.",
        "source": "Country Risk Operating Procedure",
        "tags": "fatf medium geography corridor sla procedure sanctions",
    },
]


def hash_embedding(text: str) -> list[float]:
    """Deterministic feature-hashing embedding for an offline-safe vector index."""

    vector = [0.0] * DIMENSIONS
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], "big") % DIMENSIONS
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [round(value / norm, 7) for value in vector]


class HanaVectorStore:
    def __init__(self, settings: Settings, hana: HanaClient) -> None:
        self.settings = settings
        self.hana = hana
        self._ready = False
        self._lock = Lock()
        self._schema: str | None = None

    def _writable_schema(self) -> str:
        if self._schema:
            return self._schema
        identity = self.hana.query("SELECT CURRENT_SCHEMA FROM DUMMY")
        self._schema = str(identity[0]["current_schema"])
        return self._schema

    def ensure_index(self) -> bool:
        if self._ready:
            return True
        if not self.hana.ping():
            return False
        with self._lock:
            if self._ready:
                return True
            try:
                schema = self._writable_schema()
                existing = self.hana.query(
                    """
                    SELECT COUNT(*) AS N
                    FROM SYS.TABLES
                    WHERE SCHEMA_NAME = ? AND TABLE_NAME = 'RISK_KNOWLEDGE'
                    """,
                    (schema.upper(),),
                )[0]["n"]
                if not existing:
                    self.hana.execute(
                        f"""
                        CREATE COLUMN TABLE {schema}.RISK_KNOWLEDGE (
                            DOCUMENT_ID NVARCHAR(100) PRIMARY KEY,
                            TITLE NVARCHAR(300) NOT NULL,
                            CONTENT NCLOB NOT NULL,
                            SOURCE NVARCHAR(300) NOT NULL,
                            TAGS NVARCHAR(500),
                            EMBEDDING REAL_VECTOR({DIMENSIONS}) NOT NULL,
                            CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                        """
                    )
                count = self.hana.query(
                    f"SELECT COUNT(*) AS N FROM {schema}.RISK_KNOWLEDGE"
                )[0]["n"]
                if not count:
                    for document in POLICY_DOCUMENTS:
                        vector = json.dumps(
                            hash_embedding(f"{document['title']} {document['content']} {document['tags']}")
                        )
                        self.hana.execute(
                            f"""
                            INSERT INTO {schema}.RISK_KNOWLEDGE
                                (DOCUMENT_ID, TITLE, CONTENT, SOURCE, TAGS, EMBEDDING)
                            VALUES (?, ?, ?, ?, ?, TO_REAL_VECTOR(?))
                            """,
                            (
                                document["id"],
                                document["title"],
                                document["content"],
                                document["source"],
                                document["tags"],
                                vector,
                            ),
                        )
                self._ready = True
            except Exception as exc:
                logger.warning("HANA vector index is unavailable: %s", exc)
                return False
        return True

    def search(self, query: str, limit: int = 3) -> list[dict[str, str | float]]:
        safe_limit = min(max(limit, 1), 10)
        if self.ensure_index():
            try:
                schema = self._writable_schema()
                vector = json.dumps(hash_embedding(query))
                return self.hana.query(
                    f"""
                    SELECT TITLE, CONTENT, SOURCE,
                           COSINE_SIMILARITY(EMBEDDING, TO_REAL_VECTOR(?)) AS SCORE
                    FROM {schema}.RISK_KNOWLEDGE
                    ORDER BY SCORE DESC
                    LIMIT {safe_limit}
                    """,
                    (vector,),
                )
            except Exception as exc:
                logger.warning("HANA vector retrieval failed: %s", exc)
        scored = []
        query_vector = hash_embedding(query)
        for document in POLICY_DOCUMENTS:
            vector = hash_embedding(f"{document['title']} {document['content']} {document['tags']}")
            score = sum(left * right for left, right in zip(query_vector, vector, strict=True))
            scored.append({**document, "score": score})
        return sorted(scored, key=lambda item: float(item["score"]), reverse=True)[:safe_limit]

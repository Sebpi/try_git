"""Triage Agent -- classifies a new thread as `simple` or `complex`.

Deterministic by design (not LLM-backed): "simple" is an objective claim
about catalog-match confidence and the absence of negotiation language, not a
judgment call an LLM should be trusted to make silently. See SPEC.md agent #2.
"""
from __future__ import annotations

import config
import db
from integrations import product_catalog


def run(thread: dict, email_text: str) -> dict:
    matches = product_catalog.match_products_in_text(email_text)
    lower = email_text.lower()
    negotiation_hits = [kw for kw in config.NEGOTIATION_KEYWORDS if kw in lower]

    reasons = []
    if not matches:
        complexity = "complex"
        reasons.append("no catalog product recognised in the request")
    elif any(m.confidence < config.TRIAGE_CONFIDENCE_THRESHOLD for m in matches):
        complexity = "complex"
        low = [m.product_query_text for m in matches if m.confidence < config.TRIAGE_CONFIDENCE_THRESHOLD]
        reasons.append(f"low-confidence product match for: {', '.join(low)}")
    elif negotiation_hits:
        complexity = "complex"
        reasons.append(f"consultative/negotiation language detected: {', '.join(negotiation_hits[:3])}")
    else:
        complexity = "simple"
        reasons.append(
            f"{len(matches)} product(s) matched with high confidence, no negotiation signals"
        )

    reason_text = "; ".join(reasons)
    db.update_thread(thread["id"], complexity=complexity, complexity_reason=reason_text)
    db.log_decision(
        thread["id"], "triage",
        f"Classified as {complexity}: {reason_text}",
        {
            "matches": [m.__dict__ for m in matches],
            "negotiation_hits": negotiation_hits,
            "complexity": complexity,
        },
        confidence=min((m.confidence for m in matches), default=0.0),
    )
    return {"complexity": complexity, "reason": reason_text, "matches": matches}

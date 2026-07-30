"""Response Classifier Agent -- reads a reply on an AWAITING_RESPONSE thread.

Classifies into accept / reject / query / not_a_reply (spam/OOO) / unclear.
`unclear` deliberately routes to a human rather than guessing -- see
SPEC.md agent #9. Heuristic-first; if ANTHROPIC_API_KEY is set and the
heuristic can't decide, an LLM pass attempts a classification, but the
heuristic result always wins when it's confident since it's fully auditable.
"""
from __future__ import annotations

import re

import config
import db
from integrations import llm_client

_VALID = {"accept", "reject", "query", "not_a_reply", "unclear"}


def _keyword_hits(lower_text: str, keywords: list[str]) -> list[str]:
    return [kw for kw in keywords if kw in lower_text]


def classify(text: str) -> dict:
    lower = text.lower()

    ooo_hits = _keyword_hits(lower, config.OOO_KEYWORDS)
    if ooo_hits:
        return {"label": "not_a_reply", "reason": f"out-of-office/autoreply signal: {ooo_hits[0]}"}

    accept_hits = _keyword_hits(lower, config.ACCEPT_KEYWORDS)
    reject_hits = _keyword_hits(lower, config.REJECT_KEYWORDS)

    if accept_hits and not reject_hits:
        return {"label": "accept", "reason": f"acceptance phrase found: '{accept_hits[0]}'"}
    if reject_hits and not accept_hits:
        return {"label": "reject", "reason": f"rejection phrase found: '{reject_hits[0]}'"}
    if accept_hits and reject_hits:
        # contradictory signals in one message -- don't guess
        return {"label": "unclear", "reason": "both accept- and reject-like phrases present"}

    if "?" in text:
        return {"label": "query", "reason": "message contains a question"}

    if llm_client.available():
        try:
            raw = llm_client.complete(
                system=(
                    "Classify a customer's reply to a sales quote into exactly one label: "
                    "accept, reject, query, not_a_reply, or unclear. Reply with only the label word."
                ),
                user=text,
                max_tokens=10,
            )
            label = raw.strip().lower().split()[0].strip(".,!\"'")
            if label in _VALID:
                return {"label": label, "reason": "classified by LLM (no heuristic signal found)"}
        except Exception:
            pass

    return {"label": "unclear", "reason": "no clear accept/reject/query signal found"}


def run(thread: dict, inbound_text: str, message_id: str) -> dict:
    result = classify(inbound_text)
    db.classify_inbound(message_id, result["label"])
    db.log_decision(
        thread["id"], "response_classifier",
        f"Classified reply as '{result['label']}': {result['reason']}",
        {"label": result["label"], "reason": result["reason"]},
    )
    return result

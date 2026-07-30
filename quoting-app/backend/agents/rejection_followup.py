"""Rejection Follow-up Agent -- customer said no. See SPEC.md agent #11.

Infers the likely axis (price/availability/timeline/other) from the
rejection text where possible, drafts a "help us understand" email through
the normal approval gate, and logs the rejection to CRM regardless of
whether the customer answers the follow-up.
"""
from __future__ import annotations

import config
import db
from agents import composer
from integrations import crm_mock


def _infer_reason(text: str) -> str:
    lower = text.lower()
    for reason, keywords in config.REJECT_REASON_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return reason
    return "other"


def run(thread: dict, rejection_text: str) -> dict:
    reason = _infer_reason(rejection_text)

    if thread.get("crm_account_id"):
        crm_mock.log_opportunity_event(
            thread["crm_account_id"], "quote_rejected",
            f"Thread {thread['id']} rejected, inferred reason={reason}: {rejection_text[:200]}",
        )

    db.update_thread(thread["id"], status="REJECTED", closed_reason=f"rejected: {reason}")
    contact = crm_mock.find_contact_by_email(thread["customer_email"])
    draft = composer.compose_rejection_followup(thread, reason, contact)

    db.log_decision(
        thread["id"], "rejection_followup",
        f"Inferred rejection reason='{reason}'; follow-up draft v{draft['version']} pending approval",
        {"draft_id": draft["id"], "inferred_reason": reason},
    )
    return {"inferred_reason": reason, "draft": draft}

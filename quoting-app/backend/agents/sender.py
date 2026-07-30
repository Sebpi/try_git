"""Sender Agent -- sends an approved draft verbatim and advances thread state.

No last-mile rewriting: what was approved is what goes out. Also owns
scheduling the next reminder stage, since what to schedule next depends
entirely on what kind of message was just sent. See SPEC.md agent #8.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import config
import db
from agents import reminder as reminder_agent
from integrations import email_client


def send(draft: dict) -> dict:
    if draft["approval_status"] != "approved":
        raise ValueError(f"Refusing to send draft {draft['id']}: not approved (status={draft['approval_status']})")

    thread = db.get_thread(draft["thread_id"])
    email_client.send(to_email=thread["customer_email"], subject=draft["subject"], body=draft["body"])
    db.record_outbound(thread["id"], draft_id=draft["id"], to_email=thread["customer_email"],
                        subject=draft["subject"], body=draft["body"])

    now = datetime.now(timezone.utc)
    updates = {"last_outbound_at": now.isoformat()}

    if draft["kind"] == "quote":
        updates["status"] = "AWAITING_RESPONSE"
    elif draft["kind"] == "query_response":
        updates["status"] = "AWAITING_RESPONSE"
    elif draft["kind"] == "rejection_followup":
        updates["status"] = "FOLLOW_UP_SENT"
    elif draft["kind"] in ("reminder_1st", "reminder_2nd"):
        updates["status"] = "AWAITING_RESPONSE"

    db.update_thread(thread["id"], **updates)
    db.log_decision(
        thread["id"], "sender",
        f"Sent {draft['kind']} (draft v{draft['version']}) to {thread['customer_email']}",
        {"draft_id": draft["id"], "kind": draft["kind"]},
    )

    reminder_agent.schedule_after_send(thread["id"], draft["kind"], now)
    return db.get_thread(thread["id"])

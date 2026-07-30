"""Reminder / Nurture Agent -- the scheduler-driven agent.

Cadence (SPEC.md section 7): 1st reminder 2-3 days after the quote (or any
reply) is sent; 2nd reminder 4-5 days after *that*; close out with no more
nurture if the customer is still silent. Every send (quote, query response,
reminder) resets the "awaiting response" clock through `schedule_after_send`,
which `sender.py` calls right after a successful send -- that's the only
place stage transitions happen, so `run_sweep` never has to guess what to
schedule next, only what to *fire* now.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import config
import db

_FAR_FUTURE = "9999-01-01T00:00:00+00:00"  # sentinel: "don't re-fire, waiting on approval/send"


def schedule_after_send(thread_id: str, kind: str, sent_at: datetime) -> None:
    if kind in ("quote", "query_response"):
        next_fire = sent_at + timedelta(days=config.REMINDER_STAGE1_DAYS)
        db.upsert_reminder(thread_id, stage="1st", next_fire_at=next_fire.isoformat())
    elif kind == "reminder_1st":
        next_fire = sent_at + timedelta(days=config.REMINDER_STAGE2_DAYS)
        db.upsert_reminder(thread_id, stage="2nd", next_fire_at=next_fire.isoformat())
    elif kind == "reminder_2nd":
        db.upsert_reminder(thread_id, stage="final", next_fire_at=sent_at.isoformat())
    elif kind == "rejection_followup":
        next_fire = sent_at + timedelta(days=config.REMINDER_STAGE1_DAYS)
        db.upsert_reminder(thread_id, stage="final_followup", next_fire_at=next_fire.isoformat())


def cancel(thread_id: str) -> None:
    db.delete_reminder(thread_id)


def _draft_reminder(thread: dict, stage_label: str) -> None:
    from agents import composer  # local import: avoids a hard dependency at module load

    line_items = db.list_line_items(thread["id"])
    from integrations import crm_mock
    contact = crm_mock.find_contact_by_email(thread["customer_email"])
    draft = composer.compose_reminder(thread, stage_label, line_items, contact)

    if not config.REMINDER_REQUIRE_APPROVAL:
        from agents import approval, sender
        approval.approve(draft["id"], "system-autopilot")
        sender.send(db.get_draft(draft["id"]))
    else:
        db.notify_am(
            thread["id"], "reminder_drafted",
            f"{stage_label} reminder drafted and awaiting your approval before it goes out.",
        )
    # park this row so the sweep doesn't redraft it every run while it's
    # sitting in the approval queue -- schedule_after_send() will overwrite
    # it with the real next stage once the reminder actually sends.
    db.upsert_reminder(thread["id"], stage=f"{stage_label}_drafted", next_fire_at=_FAR_FUTURE)


def run_sweep(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    due = db.due_reminders(now.isoformat())
    fired = {"drafted_1st": 0, "drafted_2nd": 0, "closed_no_response": 0, "closed_lost": 0, "skipped": 0}

    for row in due:
        thread = db.get_thread(row["thread_id"])
        if not thread or thread["status"] not in ("AWAITING_RESPONSE", "FOLLOW_UP_SENT"):
            db.delete_reminder(row["thread_id"])
            fired["skipped"] += 1
            continue

        if row["stage"] == "1st":
            _draft_reminder(thread, "1st")
            fired["drafted_1st"] += 1
        elif row["stage"] == "2nd":
            _draft_reminder(thread, "2nd")
            fired["drafted_2nd"] += 1
        elif row["stage"] == "final":
            db.update_thread(thread["id"], status="CLOSED_NO_RESPONSE",
                              closed_reason="No response after two reminders")
            db.notify_am(thread["id"], "thread_closed_no_response",
                         "Closed: customer never responded after two reminders.")
            db.log_decision(thread["id"], "reminder",
                             "Closing thread: no response after two reminders", {})
            db.delete_reminder(thread["id"])
            fired["closed_no_response"] += 1
        elif row["stage"] == "final_followup":
            db.update_thread(thread["id"], status="CLOSED_LOST",
                              closed_reason="No response to rejection follow-up")
            db.notify_am(thread["id"], "thread_closed_lost",
                         "Closed lost: no response to the rejection follow-up.")
            db.log_decision(thread["id"], "reminder",
                             "Closing thread as lost: no response to rejection follow-up", {})
            db.delete_reminder(thread["id"])
            fired["closed_lost"] += 1
        # "*_drafted" sentinel rows are never due (far-future timestamp) so they
        # won't appear in `due` at all; nothing to handle for them here.

    return fired

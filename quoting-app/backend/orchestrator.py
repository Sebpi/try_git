"""Orchestrator -- drives the per-thread state machine across all agents.

Owns every `quote_threads.status` transition that isn't a single agent's own
terminal action (routing -> ROUTED_TO_HUMAN, acceptance -> ACCEPTED,
rejection_followup -> REJECTED, sender -> AWAITING_RESPONSE/FOLLOW_UP_SENT).
See SPEC.md section 5 for the full state diagram and agent #14 for the one
hard invariant this enforces: no outbound customer email without an approved
draft, which lives at the sender.py boundary regardless of which upstream
agent produced the draft.
"""
from __future__ import annotations

import config
import db
from agents import (
    acceptance,
    approval,
    crm_lookup,
    ingestion,
    pricing,
    query_response,
    rejection_followup,
    reminder as reminder_agent,
    response_classifier,
    routing,
    sender,
    triage,
)
from agents import composer


def process_inbound_email(raw: dict) -> dict:
    """raw: {message_id, from_email, from_name?, subject, body}"""
    thread, is_new, is_duplicate = ingestion.ingest(raw)
    if is_duplicate:
        return {"thread_id": thread["id"], "status": thread["status"], "duplicate": True}

    if is_new:
        _run_new_thread_pipeline(thread, raw["body"])
    else:
        _run_reply_pipeline(thread, raw)

    return {"thread_id": thread["id"], "status": db.get_thread(thread["id"])["status"]}


def _run_new_thread_pipeline(thread: dict, body_text: str) -> None:
    triage_result = triage.run(thread, body_text)
    if triage_result["complexity"] == "complex":
        db.update_thread(thread["id"], status="TRIAGED_COMPLEX")
        routing.run(db.get_thread(thread["id"]), triage_result["reason"], triage_result["matches"])
        return

    db.update_thread(thread["id"], status="TRIAGED_SIMPLE")
    db.update_thread(thread["id"], status="ENRICHING")
    contact = crm_lookup.run(thread)
    thread = db.get_thread(thread["id"])
    if thread["complexity"] == "complex":
        routing.run(thread, thread["complexity_reason"], triage_result["matches"])
        return

    line_items = pricing.run(thread, triage_result["matches"], thread.get("crm_account_id"))
    thread = db.get_thread(thread["id"])
    if thread["complexity"] == "complex":
        routing.run(thread, thread["complexity_reason"], triage_result["matches"])
        return

    db.update_thread(thread["id"], status="DRAFTING")
    composer.compose_initial_quote(thread, line_items, contact if contact.get("found") else None)
    db.update_thread(thread["id"], status="PENDING_APPROVAL")


def _run_reply_pipeline(thread: dict, raw: dict) -> None:
    if thread["status"] not in ("AWAITING_RESPONSE", "FOLLOW_UP_SENT"):
        db.log_decision(
            thread["id"], "orchestrator",
            f"Inbound message received while thread status={thread['status']}; "
            f"no automated action taken (thread is not awaiting a reply).",
            {"status": thread["status"]},
        )
        db.notify_am(
            thread["id"], "inbound_on_non_awaiting_thread",
            f"New message from {raw['from_email']} arrived on a thread in status={thread['status']}.",
        )
        return

    result = response_classifier.run(thread, raw["body"], raw["message_id"])
    label = result["label"]

    if label == "accept":
        acceptance.run(thread)
    elif label == "reject":
        rejection_followup.run(thread, raw["body"])
        db.update_thread(thread["id"], status="PENDING_APPROVAL")
    elif label == "query":
        db.update_thread(thread["id"], status="DRAFTING")
        query_response.run(thread, raw["body"])
        db.update_thread(thread["id"], status="PENDING_APPROVAL")
    elif label == "not_a_reply":
        pass  # clock keeps running -- this wasn't a real reply from the customer
    else:  # unclear
        db.update_thread(thread["id"], status="NEEDS_HUMAN_REVIEW")
        db.notify_am(
            thread["id"], "unclear_reply",
            f"Reply from {thread['customer_email']} couldn't be confidently classified -- please review.",
        )
        reminder_agent.cancel(thread["id"])


# --------------------------------------------------------- approval actions --
def approve_draft(draft_id: int, approver: str) -> dict:
    draft = approval.approve(draft_id, approver)
    return sender.send(draft)


def reject_draft(draft_id: int, approver: str, reason: str) -> dict:
    draft = approval.reject(draft_id, approver, reason)
    thread = db.get_thread(draft["thread_id"])
    db.log_decision(
        thread["id"], "orchestrator",
        f"Draft v{draft['version']} rejected by AM; thread held in PENDING_APPROVAL "
        f"pending a manual edit+approve or a fresh draft.",
        {"draft_id": draft_id},
    )
    return thread


def edit_and_approve_draft(draft_id: int, approver: str, subject: str, body: str) -> dict:
    new_draft = approval.edit_and_approve(draft_id, approver, subject, body)
    return sender.send(new_draft)


def run_reminder_sweep() -> dict:
    return reminder_agent.run_sweep()

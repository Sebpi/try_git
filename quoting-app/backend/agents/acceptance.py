"""Acceptance Agent -- customer said yes. See SPEC.md agent #10.

Updates CRM, notifies the AM that an order needs processing, and stops the
reminder clock. Does not trigger fulfillment/billing itself -- that's a
handoff to whatever order-processing system exists downstream.
"""
from __future__ import annotations

import db
from agents import reminder as reminder_agent
from integrations import crm_mock


def run(thread: dict) -> dict:
    if thread.get("crm_account_id"):
        crm_mock.log_opportunity_event(
            thread["crm_account_id"], "order_received",
            f"Thread {thread['id']} accepted by {thread['customer_email']}",
        )

    db.update_thread(thread["id"], status="ACCEPTED")
    reminder_agent.cancel(thread["id"])

    contact = crm_mock.find_contact_by_email(thread["customer_email"])
    am = contact["account_owner"] if contact else "Unassigned AM"
    db.notify_am(
        thread["id"], "order_received",
        f"{thread['customer_email']} accepted the quote -- order received, please process. (Owner: {am})",
    )
    db.log_decision(
        thread["id"], "acceptance",
        f"Order accepted by {thread['customer_email']}; CRM updated, {am} notified to process",
        {"account_id": thread.get("crm_account_id")},
    )
    return {"status": "ACCEPTED"}

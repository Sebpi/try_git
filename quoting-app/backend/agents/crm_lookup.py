"""CRM Lookup Agent -- resolves the sender to a CRM contact/account.

No match is treated as a deliberate escalation (unknown-customer quoting is
not something the system should auto-quote), matching SPEC.md agent #4.
"""
from __future__ import annotations

import db
from integrations import crm_mock


def run(thread: dict) -> dict:
    contact = crm_mock.find_contact_by_email(thread["customer_email"])
    if not contact:
        db.update_thread(
            thread["id"], complexity="complex",
            complexity_reason=(thread.get("complexity_reason") or "") + "; no CRM match for sender",
        )
        db.log_decision(
            thread["id"], "crm_lookup",
            f"No CRM contact found for {thread['customer_email']} -- escalating to complex/needs_review",
            {"found": False},
        )
        return {"found": False}

    db.update_thread(
        thread["id"], crm_contact_id=contact["contact_id"], crm_account_id=contact["account_id"],
    )
    db.log_decision(
        thread["id"], "crm_lookup",
        f"Matched {thread['customer_email']} to {contact['contact_name']} @ {contact['account_name']} "
        f"(owner: {contact['account_owner']})",
        {"found": True, **contact},
    )
    return {"found": True, **contact}

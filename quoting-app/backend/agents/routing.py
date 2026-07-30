"""Routing Agent -- hands a complex quote to the right AM + application engineer.

Terminal for automation: once routed, this thread is a human's to run.
See SPEC.md agent #3.
"""
from __future__ import annotations

import db
from integrations import crm_mock, product_catalog


def run(thread: dict, reason: str, matches: list | None = None) -> dict:
    contact = crm_mock.find_contact_by_email(thread["customer_email"])
    if contact:
        am_name = contact["account_owner"]
        am_email = contact["account_owner_email"]
    else:
        am_name, am_email = "Unassigned AM (unknown account)", "sales-triage@ourcompany.example"

    categories = [m.category for m in (matches or []) if getattr(m, "category", None)]
    engineer = product_catalog.engineer_for_categories(categories)

    ticket = db.create_routing_ticket(
        thread["id"], reason=reason, assigned_am=am_name, assigned_engineer=engineer,
    )
    db.update_thread(thread["id"], status="ROUTED_TO_HUMAN")
    db.notify_am(
        thread["id"], "complex_quote_routed",
        f"Complex quote routed to {am_name} + {engineer}. Reason: {reason}",
    )
    db.log_decision(
        thread["id"], "routing",
        f"Routed to AM {am_name} and application engineer {engineer}: {reason}",
        {"ticket": ticket, "am_email": am_email},
    )
    return ticket

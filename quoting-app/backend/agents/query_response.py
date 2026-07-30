"""Query Response Agent -- customer asked a question. See SPEC.md agent #12.

Reuses the CRM + pricing context already gathered on the thread; if the
question mentions a product that wasn't in the original line items, re-runs
the Pricing Agent against the new text and merges the result before drafting
the answer. Always routes through the same approval gate as the initial quote.
"""
from __future__ import annotations

import db
from agents import composer, pricing
from integrations import crm_mock, product_catalog


def run(thread: dict, question_text: str) -> dict:
    existing = db.list_line_items(thread["id"])
    existing_skus = {li["resolved_sku"] for li in existing}

    new_matches = [
        m for m in product_catalog.match_products_in_text(question_text)
        if m.resolved_sku not in existing_skus
    ]
    if new_matches:
        added = pricing.run(thread, new_matches, thread.get("crm_account_id"))
        db.log_decision(
            thread["id"], "query_response",
            f"Question mentioned {len(added)} new product(s) not on the original quote; re-priced",
            {"added_skus": [a["resolved_sku"] for a in added]},
        )
        existing = db.list_line_items(thread["id"])

    contact = crm_mock.find_contact_by_email(thread["customer_email"])
    draft = composer.compose_query_response(thread, question_text, existing, contact)
    db.log_decision(
        thread["id"], "query_response",
        f"Drafted answer v{draft['version']} pending approval",
        {"draft_id": draft["id"]},
    )
    return {"draft": draft}

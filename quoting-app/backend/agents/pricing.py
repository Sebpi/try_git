"""Product & Pricing Agent -- resolves catalog SKU + price for each line item.

Re-checks match confidence against the live catalog independently of Triage
(Triage works off the raw email; this agent works off the actual catalog and
can still catch a near-miss Triage let through) and applies any
account-specific price-book override from the CRM lookup. See SPEC.md agent #5.
"""
from __future__ import annotations

import config
import db
from integrations import crm_mock, product_catalog


def run(thread: dict, matches: list, crm_account_id: str | None) -> list[dict]:
    line_items = []
    for m in matches:
        price = m.resolved_price
        override = crm_mock.price_override(crm_account_id, m.resolved_sku) if m.resolved_sku else None
        used_override = override is not None
        if used_override:
            price = override

        line_items.append({
            "product_query_text": m.product_query_text,
            "resolved_sku": m.resolved_sku,
            "resolved_name": m.resolved_name,
            "resolved_price": price,
            "currency": m.currency,
            "quantity": m.quantity,
            "confidence": m.confidence,
            "price_book_override": used_override,
        })

    db.add_line_items(thread["id"], line_items)
    low_conf = [li for li in line_items if li["confidence"] < config.TRIAGE_CONFIDENCE_THRESHOLD]
    db.log_decision(
        thread["id"], "pricing",
        f"Resolved {len(line_items)} line item(s), {len(low_conf)} below confidence threshold",
        {"line_items": line_items},
        confidence=min((li["confidence"] for li in line_items), default=0.0),
    )
    if low_conf:
        db.update_thread(
            thread["id"], complexity="complex",
            complexity_reason=(thread.get("complexity_reason") or "")
            + "; pricing agent flagged low-confidence line item(s) after catalog re-check",
        )
    return line_items

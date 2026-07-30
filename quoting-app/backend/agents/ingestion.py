"""Ingestion Agent -- resolves an inbound email to a thread, deduped and threaded.

Threading strategy, in priority order:
1. `raw["provider_thread_id"]` -- the mail provider's own thread id (e.g.
   Gmail's `threadId`), when the transport supplies one. This is the most
   reliable signal and is what `integrations/gmail_client.py` sends.
2. A `[Ref: thr_xxxxxxxx]` token embedded in the subject (see composer.py),
   which we ask the customer to keep on reply -- the fallback for
   transports/clients that don't give us a reliable provider thread id.
3. Sender-address match against their most recently active (non-terminal)
   thread, as a last resort.
"""
from __future__ import annotations

import re

import db

REF_RE = re.compile(r"\[Ref:\s*(thr_[a-f0-9]+)\]", re.IGNORECASE)

_NON_MATCHABLE_STATES = {"ACCEPTED", "CLOSED_LOST", "CLOSED_NO_RESPONSE"}


def extract_ref(text: str) -> str | None:
    m = REF_RE.search(text or "")
    return m.group(1) if m else None


def ingest(raw: dict) -> tuple[dict, bool, bool]:
    """raw: {message_id, from_email, from_name?, subject, body, provider_thread_id?}

    Returns (thread, is_new_thread, is_duplicate_message).
    """
    existing = db.get_conn().execute(
        "SELECT * FROM inbound_messages WHERE message_id=?", (raw["message_id"],)
    ).fetchone()
    if existing and existing["thread_id"]:
        return db.get_thread(existing["thread_id"]), False, True

    provider_thread_id = raw.get("provider_thread_id")
    match_method = None
    thread = db.find_thread_by_key(provider_thread_id) if provider_thread_id else None
    if thread:
        match_method = f"provider thread id {provider_thread_id}"

    ref = extract_ref(raw.get("subject", "")) or extract_ref(raw.get("body", ""))
    if not thread and ref:
        thread = db.get_thread(ref)
        if thread:
            match_method = f"ref token {ref}"

    if not thread:
        candidates = [
            t for t in db.list_threads()
            if t["customer_email"].lower() == raw["from_email"].lower()
            and t["status"] not in _NON_MATCHABLE_STATES
        ]
        if candidates:
            thread = candidates[0]
            match_method = "sender-address fallback"

    is_new = False
    if not thread:
        thread = db.create_thread(
            email_thread_key=provider_thread_id or raw["message_id"],
            customer_email=raw["from_email"],
            customer_name=raw.get("from_name") or raw["from_email"].split("@")[0].title(),
            subject=raw.get("subject", "(no subject)"),
        )
        is_new = True
    else:
        db.update_thread(thread["id"], last_inbound_at=db.now_iso())

    db.record_inbound(
        thread["id"], message_id=raw["message_id"], from_email=raw["from_email"],
        subject=raw.get("subject", ""), body=raw.get("body", ""),
    )
    db.log_decision(
        thread["id"], "ingestion",
        ("New thread opened" if is_new else f"Matched to existing thread via {match_method}")
        + f" for {raw['from_email']}",
        {"ref_found": ref, "provider_thread_id": provider_thread_id, "is_new": is_new,
         "message_id": raw["message_id"]},
    )
    return thread, is_new, False

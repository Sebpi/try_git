"""Ingestion Agent -- resolves an inbound email to a thread, deduped and threaded.

Threading strategy: outbound emails embed a `[Ref: thr_xxxxxxxx]` token in the
subject (see composer.py) which we ask the customer to keep on reply -- the
same trick real systems use with a reply-to+ or ticket-number-in-subject
convention when proper Message-ID/References headers aren't reliably
preserved by every mail client. Falls back to matching the sender's address
against their most recently active (non-terminal) thread.
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
    """raw: {message_id, from_email, from_name?, subject, body}

    Returns (thread, is_new_thread, is_duplicate_message).
    """
    existing = db.get_conn().execute(
        "SELECT * FROM inbound_messages WHERE message_id=?", (raw["message_id"],)
    ).fetchone()
    if existing and existing["thread_id"]:
        return db.get_thread(existing["thread_id"]), False, True

    ref = extract_ref(raw.get("subject", "")) or extract_ref(raw.get("body", ""))
    thread = db.get_thread(ref) if ref else None

    if not thread:
        candidates = [
            t for t in db.list_threads()
            if t["customer_email"].lower() == raw["from_email"].lower()
            and t["status"] not in _NON_MATCHABLE_STATES
        ]
        if candidates:
            thread = candidates[0]

    is_new = False
    if not thread:
        thread = db.create_thread(
            email_thread_key=raw["message_id"],
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
        ("New thread opened" if is_new else "Matched to existing thread")
        + f" for {raw['from_email']}"
        + (f" via ref token {ref}" if ref and thread and thread['id'] == ref else " via sender-address fallback" if not is_new else ""),
        {"ref_found": ref, "is_new": is_new, "message_id": raw["message_id"]},
    )
    return thread, is_new, False

"""Bridges the Gmail inbox to the Ingestion Agent.

Polling rather than push: Gmail push notifications require a Google Cloud
Pub/Sub topic + domain verification, which is a lot of setup for a mailbox
that isn't a Workspace-managed domain. Polling every couple of minutes is
the same trade-off SPEC.md already calls out for IMAP IDLE vs. a plain poll,
and is far simpler to run anywhere.
"""
from __future__ import annotations

import logging

import orchestrator
from integrations import gmail_client

logger = logging.getLogger("quoting_app.gmail_poll")


def poll_and_ingest(max_results: int = 20) -> dict:
    if not gmail_client.available():
        return {"configured": False, "processed": 0}

    raws = gmail_client.fetch_unprocessed_inbound(max_results=max_results)
    processed = 0
    for raw in raws:
        try:
            orchestrator.process_inbound_email(raw)
        except Exception:
            # A broken/unparseable message must not jam the queue forever --
            # log it and mark processed anyway. Production would want a
            # dead-letter path instead of a silent drop; acceptable here
            # since every step is already audited in `agent_decisions`.
            logger.exception("Failed to ingest Gmail message %s", raw.get("gmail_id"))
        finally:
            gmail_client.mark_processed(raw["gmail_id"])
        processed += 1

    return {"configured": True, "processed": processed}

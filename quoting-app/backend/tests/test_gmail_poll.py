from unittest.mock import MagicMock

import db
import gmail_poll
from integrations import gmail_client


def test_poll_and_ingest_noop_when_not_configured(monkeypatch):
    monkeypatch.setattr(gmail_client, "available", lambda: False)
    result = gmail_poll.poll_and_ingest()
    assert result == {"configured": False, "processed": 0}


def test_poll_and_ingest_creates_thread_and_marks_processed(monkeypatch):
    monkeypatch.setattr(gmail_client, "available", lambda: True)
    monkeypatch.setattr(gmail_client, "fetch_unprocessed_inbound", lambda max_results=20: [{
        "gmail_id": "msg1",
        "provider_thread_id": "thread1",
        "message_id": "<abc@mail.gmail.com>",
        "from_email": "jordan.lee@northwind.example",
        "from_name": "Jordan Lee",
        "subject": "Quote request",
        "body": "Could you quote 2 wireless mouse units?",
    }])
    marked = []
    monkeypatch.setattr(gmail_client, "mark_processed", lambda gmail_id: marked.append(gmail_id))

    result = gmail_poll.poll_and_ingest()
    assert result == {"configured": True, "processed": 1}
    assert marked == ["msg1"]

    threads = db.list_threads()
    assert len(threads) == 1
    assert threads[0]["email_thread_key"] == "thread1"
    assert threads[0]["status"] == "PENDING_APPROVAL"


def test_poll_and_ingest_marks_processed_even_on_ingestion_failure(monkeypatch):
    monkeypatch.setattr(gmail_client, "available", lambda: True)
    monkeypatch.setattr(gmail_client, "fetch_unprocessed_inbound", lambda max_results=20: [{
        "gmail_id": "broken1",
        # missing from_email on purpose to trigger a KeyError deep in ingestion
    }])
    marked = []
    monkeypatch.setattr(gmail_client, "mark_processed", lambda gmail_id: marked.append(gmail_id))

    result = gmail_poll.poll_and_ingest()
    assert result == {"configured": True, "processed": 1}
    assert marked == ["broken1"]  # not stuck retrying the same broken message forever

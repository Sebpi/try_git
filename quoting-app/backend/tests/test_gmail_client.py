"""Unit tests for the Gmail integration -- mocked at the API-object boundary
so nothing here ever touches the real network (see main conversation: a
live call from this sandbox hangs against the proxy allowlist)."""
import base64
from email.mime.text import MIMEText
from unittest.mock import MagicMock

from integrations import gmail_client


def test_available_requires_all_three_env_vars(monkeypatch):
    monkeypatch.delenv("GMAIL_CLIENT_ID", raising=False)
    monkeypatch.delenv("GMAIL_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("GMAIL_REFRESH_TOKEN", raising=False)
    assert gmail_client.available() is False

    monkeypatch.setenv("GMAIL_CLIENT_ID", "id")
    monkeypatch.setenv("GMAIL_CLIENT_SECRET", "secret")
    assert gmail_client.available() is False  # refresh token still missing

    monkeypatch.setenv("GMAIL_REFRESH_TOKEN", "refresh")
    assert gmail_client.available() is True


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def test_extract_body_prefers_plain_text_part():
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/html", "body": {"data": _b64("<p>hi</p>")}},
            {"mimeType": "text/plain", "body": {"data": _b64("hi there")}},
        ],
    }
    assert gmail_client._extract_body(payload) == "hi there"


def test_extract_body_single_part_message():
    payload = {"body": {"data": _b64("just the body")}}
    assert gmail_client._extract_body(payload) == "just the body"


def test_fetch_unprocessed_inbound_shapes_messages_for_orchestrator(monkeypatch):
    fake_service = MagicMock()
    fake_service.users().labels().list().execute.return_value = {
        "labels": [{"id": "Label_1", "name": "QuotingAppProcessed"}]
    }
    fake_service.users().messages().list().execute.return_value = {
        "messages": [{"id": "msg1"}]
    }
    fake_service.users().messages().get().execute.return_value = {
        "id": "msg1",
        "threadId": "thread1",
        "labelIds": ["INBOX"],
        "payload": {
            "headers": [
                {"name": "From", "value": "Jordan Lee <jordan.lee@northwind.example>"},
                {"name": "Subject", "value": "Quote request"},
                {"name": "Message-ID", "value": "<abc@mail.gmail.com>"},
            ],
            "body": {"data": _b64("Could you quote 3 wireless mice?")},
        },
    }
    monkeypatch.setattr(gmail_client, "_service", lambda: fake_service)

    results = gmail_client.fetch_unprocessed_inbound()
    assert len(results) == 1
    r = results[0]
    assert r["gmail_id"] == "msg1"
    assert r["provider_thread_id"] == "thread1"
    assert r["from_email"] == "jordan.lee@northwind.example"
    assert r["from_name"] == "Jordan Lee"
    assert r["subject"] == "Quote request"
    assert r["body"] == "Could you quote 3 wireless mice?"


def test_send_builds_correct_mime_message(monkeypatch):
    fake_service = MagicMock()
    sent = {}

    def fake_send(userId, body):
        sent["raw"] = body["raw"]
        return MagicMock(execute=lambda: {"id": "sent1"})

    fake_service.users().messages().send.side_effect = fake_send
    monkeypatch.setattr(gmail_client, "_service", lambda: fake_service)
    monkeypatch.delenv("GMAIL_SENDER_EMAIL", raising=False)

    gmail_client.send(to_email="jordan.lee@northwind.example", subject="Your quote", body="Hi Jordan")

    decoded = base64.urlsafe_b64decode(sent["raw"]).decode()
    assert "To: jordan.lee@northwind.example" in decoded
    assert "Subject: Your quote" in decoded
    assert "Hi Jordan" in decoded
    assert "From:" not in decoded  # no GMAIL_SENDER_EMAIL set -> let Gmail fill it in

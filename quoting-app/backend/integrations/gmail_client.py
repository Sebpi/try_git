"""Gmail integration -- real send + inbound polling via the Gmail API.

Auth: OAuth2 with a long-lived refresh token. Works for both a personal
Gmail account and a Google Workspace mailbox, with no domain-wide delegation
or service account needed -- just a normal OAuth client + one-time consent.

Setup (one-time):
  1. In Google Cloud Console: create/select a project, enable the "Gmail API".
  2. Create an OAuth client ID of type "Desktop app" and download its JSON.
  3. Run `python scripts/gmail_get_refresh_token.py path/to/client_secret.json`
     (opens a browser for consent) -- it prints a refresh token.
  4. Set env vars: GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN.
     Optionally GMAIL_SENDER_EMAIL if send-as a verified alias on the account
     (Gmail ignores/rejects an unverified From address -- omit to send as the
     authenticated account itself, which is the common case).

Everything in this module is optional: `available()` gates every caller, and
`email_client.py` / the Gmail poller fall back to console/SMTP or "nothing to
poll" when it's False, so the rest of the app works fine without Gmail
configured.
"""
from __future__ import annotations

import base64
import os
from email.mime.text import MIMEText
from email.utils import parseaddr

_PROCESSED_LABEL = "QuotingAppProcessed"
_SCOPES = ["https://www.googleapis.com/auth/gmail.modify", "https://www.googleapis.com/auth/gmail.send"]


def available() -> bool:
    return bool(
        os.environ.get("GMAIL_CLIENT_ID")
        and os.environ.get("GMAIL_CLIENT_SECRET")
        and os.environ.get("GMAIL_REFRESH_TOKEN")
    )


def _service():
    from google.oauth2.credentials import Credentials  # optional dependency, imported lazily
    from googleapiclient.discovery import build

    creds = Credentials(
        token=None,
        refresh_token=os.environ["GMAIL_REFRESH_TOKEN"],
        client_id=os.environ["GMAIL_CLIENT_ID"],
        client_secret=os.environ["GMAIL_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=_SCOPES,
    )
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def send(*, to_email: str, subject: str, body: str) -> None:
    service = _service()
    msg = MIMEText(body)
    msg["To"] = to_email
    msg["Subject"] = subject
    sender = os.environ.get("GMAIL_SENDER_EMAIL")
    if sender:  # only set From if it's a verified "Send As" alias -- else let Gmail fill it in
        msg["From"] = sender
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()


def _processed_label_id(service) -> str:
    labels = service.users().labels().list(userId="me").execute().get("labels", [])
    for label in labels:
        if label["name"] == _PROCESSED_LABEL:
            return label["id"]
    created = service.users().labels().create(
        userId="me", body={"name": _PROCESSED_LABEL, "labelListVisibility": "labelHide"},
    ).execute()
    return created["id"]


def _header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _extract_body(payload: dict) -> str:
    if payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode(errors="replace")
    for part in payload.get("parts", []) or []:
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode(errors="replace")
    for part in payload.get("parts", []) or []:
        text = _extract_body(part)
        if text:
            return text
    return ""


def fetch_unprocessed_inbound(max_results: int = 20) -> list[dict]:
    """Returns raw email dicts shaped for orchestrator.process_inbound_email
    -- one per inbox message that doesn't carry our "processed" label yet."""
    service = _service()
    label_id = _processed_label_id(service)
    resp = service.users().messages().list(
        userId="me", q=f"in:inbox -label:{_PROCESSED_LABEL}", maxResults=max_results,
    ).execute()

    results = []
    for item in resp.get("messages", []):
        full = service.users().messages().get(userId="me", id=item["id"], format="full").execute()
        if label_id in full.get("labelIds", []):
            continue  # belt-and-braces: query already excludes these
        headers = full["payload"]["headers"]
        from_name, from_email = parseaddr(_header(headers, "From"))
        results.append({
            "gmail_id": full["id"],
            "provider_thread_id": full["threadId"],
            "message_id": _header(headers, "Message-ID") or full["id"],
            "from_email": from_email,
            "from_name": from_name or (from_email.split("@")[0] if from_email else "Unknown"),
            "subject": _header(headers, "Subject"),
            "body": _extract_body(full["payload"]),
        })
    return results


def mark_processed(gmail_id: str) -> None:
    service = _service()
    label_id = _processed_label_id(service)
    service.users().messages().modify(userId="me", id=gmail_id, body={"addLabelIds": [label_id]}).execute()

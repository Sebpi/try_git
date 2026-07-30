"""Outbound email sending.

Backend priority: Gmail API (if GMAIL_* env vars are set) -> SMTP (if
SMTP_HOST is set) -> console/log. The console backend keeps the whole
pipeline demoable without any mail credentials at all; Gmail is the intended
production path (see integrations/gmail_client.py for setup).
"""
from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage

from integrations import gmail_client

logger = logging.getLogger("quoting_app.email")


def send(*, to_email: str, subject: str, body: str) -> None:
    if gmail_client.available():
        gmail_client.send(to_email=to_email, subject=subject, body=body)
        return

    host = os.environ.get("SMTP_HOST")
    if not host:
        logger.info("=== OUTBOUND EMAIL (console backend) ===\nTo: %s\nSubject: %s\n\n%s\n===",
                     to_email, subject, body)
        return

    msg = EmailMessage()
    msg["From"] = os.environ.get("SMTP_FROM", "quotes@ourcompany.example")
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    with smtplib.SMTP(host, port) as server:
        server.starttls()
        if user and password:
            server.login(user, password)
        server.send_message(msg)

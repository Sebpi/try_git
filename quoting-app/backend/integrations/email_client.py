"""Outbound email sending.

Defaults to a console/log backend so the whole pipeline is demoable without
any mail credentials. Set SMTP_HOST (+ SMTP_PORT/SMTP_USER/SMTP_PASSWORD/
SMTP_FROM) to send real mail via smtplib instead.
"""
from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger("quoting_app.email")


def send(*, to_email: str, subject: str, body: str) -> None:
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

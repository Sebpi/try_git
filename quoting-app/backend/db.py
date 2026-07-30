"""SQLite persistence layer for the quoting app.

Deliberately raw sqlite3 (no ORM) -- schema mirrors SPEC.md section 4.
Every write goes through a helper here so agents never touch SQL directly.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "quoting.db")

_local = threading.local()


def get_conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        _local.conn = conn
    return conn


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


SCHEMA = """
CREATE TABLE IF NOT EXISTS quote_threads (
    id TEXT PRIMARY KEY,
    email_thread_key TEXT,
    customer_email TEXT NOT NULL,
    customer_name TEXT,
    crm_contact_id TEXT,
    crm_account_id TEXT,
    subject TEXT,
    status TEXT NOT NULL,
    complexity TEXT,
    complexity_reason TEXT,
    closed_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_inbound_at TEXT,
    last_outbound_at TEXT
);

CREATE TABLE IF NOT EXISTS quote_line_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL REFERENCES quote_threads(id),
    draft_version INTEGER,
    product_query_text TEXT,
    resolved_sku TEXT,
    resolved_name TEXT,
    resolved_price REAL,
    currency TEXT,
    quantity INTEGER,
    confidence REAL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quote_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL REFERENCES quote_threads(id),
    version INTEGER NOT NULL,
    kind TEXT NOT NULL,
    subject TEXT,
    body TEXT,
    total REAL,
    currency TEXT,
    approval_status TEXT NOT NULL DEFAULT 'pending',
    approver TEXT,
    reject_reason TEXT,
    created_at TEXT NOT NULL,
    decided_at TEXT
);

CREATE TABLE IF NOT EXISTS agent_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL REFERENCES quote_threads(id),
    agent_name TEXT NOT NULL,
    summary TEXT,
    output_json TEXT,
    confidence REAL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reminder_schedule (
    thread_id TEXT PRIMARY KEY REFERENCES quote_threads(id),
    stage TEXT NOT NULL,
    next_fire_at TEXT NOT NULL,
    fired_stages TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS routing_tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL REFERENCES quote_threads(id),
    reason TEXT,
    assigned_am TEXT,
    assigned_engineer TEXT,
    routed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS inbound_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT REFERENCES quote_threads(id),
    message_id TEXT UNIQUE,
    from_email TEXT,
    subject TEXT,
    body TEXT,
    received_at TEXT NOT NULL,
    classified_as TEXT
);

CREATE TABLE IF NOT EXISTS outbound_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL REFERENCES quote_threads(id),
    draft_id INTEGER,
    to_email TEXT,
    subject TEXT,
    body TEXT,
    sent_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS am_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL REFERENCES quote_threads(id),
    kind TEXT NOT NULL,
    message TEXT,
    created_at TEXT NOT NULL
);
"""


def init_db() -> None:
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()


def reset_db() -> None:
    """Testing helper: drop and recreate every table."""
    conn = get_conn()
    conn.executescript(
        """
        DROP TABLE IF EXISTS quote_line_items;
        DROP TABLE IF EXISTS quote_drafts;
        DROP TABLE IF EXISTS agent_decisions;
        DROP TABLE IF EXISTS reminder_schedule;
        DROP TABLE IF EXISTS routing_tickets;
        DROP TABLE IF EXISTS inbound_messages;
        DROP TABLE IF EXISTS outbound_messages;
        DROP TABLE IF EXISTS am_notifications;
        DROP TABLE IF EXISTS quote_threads;
        """
    )
    conn.commit()
    init_db()


# ---------------------------------------------------------------- threads --
def create_thread(*, email_thread_key: str, customer_email: str, customer_name: str,
                   subject: str, status: str = "NEW") -> dict:
    conn = get_conn()
    tid = new_id("thr")
    ts = now_iso()
    conn.execute(
        """INSERT INTO quote_threads
           (id, email_thread_key, customer_email, customer_name, subject, status,
            created_at, updated_at, last_inbound_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (tid, email_thread_key, customer_email, customer_name, subject, status, ts, ts, ts),
    )
    conn.commit()
    return get_thread(tid)


def get_thread(thread_id: str) -> Optional[dict]:
    row = get_conn().execute("SELECT * FROM quote_threads WHERE id=?", (thread_id,)).fetchone()
    return dict(row) if row else None


def find_thread_by_key(email_thread_key: str) -> Optional[dict]:
    row = get_conn().execute(
        "SELECT * FROM quote_threads WHERE email_thread_key=?", (email_thread_key,)
    ).fetchone()
    return dict(row) if row else None


def list_threads(status: Optional[str] = None) -> list[dict]:
    conn = get_conn()
    if status:
        rows = conn.execute(
            "SELECT * FROM quote_threads WHERE status=? ORDER BY updated_at DESC", (status,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM quote_threads ORDER BY updated_at DESC").fetchall()
    return [dict(r) for r in rows]


def update_thread(thread_id: str, **fields: Any) -> dict:
    if not fields:
        return get_thread(thread_id)
    fields["updated_at"] = now_iso()
    cols = ", ".join(f"{k}=?" for k in fields)
    conn = get_conn()
    conn.execute(f"UPDATE quote_threads SET {cols} WHERE id=?", (*fields.values(), thread_id))
    conn.commit()
    return get_thread(thread_id)


# ------------------------------------------------------------- line items --
def add_line_items(thread_id: str, items: list[dict], draft_version: int = 0) -> None:
    conn = get_conn()
    ts = now_iso()
    for it in items:
        conn.execute(
            """INSERT INTO quote_line_items
               (thread_id, draft_version, product_query_text, resolved_sku, resolved_name,
                resolved_price, currency, quantity, confidence, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (thread_id, draft_version, it.get("product_query_text"), it.get("resolved_sku"),
             it.get("resolved_name"), it.get("resolved_price"), it.get("currency"),
             it.get("quantity", 1), it.get("confidence"), ts),
        )
    conn.commit()


def list_line_items(thread_id: str) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM quote_line_items WHERE thread_id=? ORDER BY id", (thread_id,)
    ).fetchall()
    return [dict(r) for r in rows]


# ----------------------------------------------------------------- drafts --
def create_draft(thread_id: str, *, kind: str, subject: str, body: str, total: float,
                  currency: str = "USD") -> dict:
    conn = get_conn()
    last = conn.execute(
        "SELECT COALESCE(MAX(version), 0) AS v FROM quote_drafts WHERE thread_id=?", (thread_id,)
    ).fetchone()["v"]
    version = last + 1
    ts = now_iso()
    cur = conn.execute(
        """INSERT INTO quote_drafts
           (thread_id, version, kind, subject, body, total, currency, approval_status, created_at)
           VALUES (?,?,?,?,?,?,?, 'pending', ?)""",
        (thread_id, version, kind, subject, body, total, currency, ts),
    )
    conn.commit()
    return get_draft(cur.lastrowid)


def get_draft(draft_id: int) -> Optional[dict]:
    row = get_conn().execute("SELECT * FROM quote_drafts WHERE id=?", (draft_id,)).fetchone()
    return dict(row) if row else None


def list_drafts(thread_id: str) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM quote_drafts WHERE thread_id=? ORDER BY version", (thread_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def list_pending_drafts() -> list[dict]:
    rows = get_conn().execute(
        """SELECT quote_drafts.*, quote_threads.customer_email, quote_threads.customer_name,
                  quote_threads.subject AS thread_subject
           FROM quote_drafts JOIN quote_threads ON quote_threads.id = quote_drafts.thread_id
           WHERE quote_drafts.approval_status='pending'
           ORDER BY quote_drafts.created_at"""
    ).fetchall()
    return [dict(r) for r in rows]


def update_draft(draft_id: int, **fields: Any) -> dict:
    conn = get_conn()
    cols = ", ".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE quote_drafts SET {cols} WHERE id=?", (*fields.values(), draft_id))
    conn.commit()
    return get_draft(draft_id)


# ------------------------------------------------------------- decisions --
def log_decision(thread_id: str, agent_name: str, summary: str, output: Any = None,
                  confidence: Optional[float] = None) -> None:
    conn = get_conn()
    conn.execute(
        """INSERT INTO agent_decisions (thread_id, agent_name, summary, output_json, confidence, created_at)
           VALUES (?,?,?,?,?,?)""",
        (thread_id, agent_name, summary, json.dumps(output) if output is not None else None,
         confidence, now_iso()),
    )
    conn.commit()


def list_decisions(thread_id: Optional[str] = None, limit: int = 200) -> list[dict]:
    conn = get_conn()
    if thread_id:
        rows = conn.execute(
            "SELECT * FROM agent_decisions WHERE thread_id=? ORDER BY id", (thread_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM agent_decisions ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


# --------------------------------------------------------------- reminders --
def upsert_reminder(thread_id: str, *, stage: str, next_fire_at: str,
                     fired_stages: Optional[list[str]] = None) -> None:
    conn = get_conn()
    existing = conn.execute(
        "SELECT fired_stages FROM reminder_schedule WHERE thread_id=?", (thread_id,)
    ).fetchone()
    if fired_stages is None:
        fired_stages = json.loads(existing["fired_stages"]) if existing else []
    conn.execute(
        """INSERT INTO reminder_schedule (thread_id, stage, next_fire_at, fired_stages)
           VALUES (?,?,?,?)
           ON CONFLICT(thread_id) DO UPDATE SET stage=excluded.stage,
               next_fire_at=excluded.next_fire_at, fired_stages=excluded.fired_stages""",
        (thread_id, stage, next_fire_at, json.dumps(fired_stages)),
    )
    conn.commit()


def get_reminder(thread_id: str) -> Optional[dict]:
    row = get_conn().execute(
        "SELECT * FROM reminder_schedule WHERE thread_id=?", (thread_id,)
    ).fetchone()
    return dict(row) if row else None


def delete_reminder(thread_id: str) -> None:
    conn = get_conn()
    conn.execute("DELETE FROM reminder_schedule WHERE thread_id=?", (thread_id,))
    conn.commit()


def due_reminders(now: str) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM reminder_schedule WHERE next_fire_at <= ? ORDER BY next_fire_at", (now,)
    ).fetchall()
    return [dict(r) for r in rows]


# ------------------------------------------------------------------ misc --
def create_routing_ticket(thread_id: str, *, reason: str, assigned_am: str,
                           assigned_engineer: str) -> dict:
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO routing_tickets (thread_id, reason, assigned_am, assigned_engineer, routed_at)
           VALUES (?,?,?,?,?)""",
        (thread_id, reason, assigned_am, assigned_engineer, now_iso()),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM routing_tickets WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


def get_routing_ticket(thread_id: str) -> Optional[dict]:
    row = get_conn().execute(
        "SELECT * FROM routing_tickets WHERE thread_id=? ORDER BY id DESC LIMIT 1", (thread_id,)
    ).fetchone()
    return dict(row) if row else None


def record_inbound(thread_id: Optional[str], *, message_id: str, from_email: str,
                    subject: str, body: str) -> dict:
    conn = get_conn()
    cur = conn.execute(
        """INSERT OR IGNORE INTO inbound_messages
           (thread_id, message_id, from_email, subject, body, received_at)
           VALUES (?,?,?,?,?,?)""",
        (thread_id, message_id, from_email, subject, body, now_iso()),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM inbound_messages WHERE message_id=?", (message_id,)
    ).fetchone()
    return dict(row)


def classify_inbound(message_id: str, classified_as: str) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE inbound_messages SET classified_as=? WHERE message_id=?", (classified_as, message_id)
    )
    conn.commit()


def record_outbound(thread_id: str, *, draft_id: Optional[int], to_email: str,
                     subject: str, body: str) -> dict:
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO outbound_messages (thread_id, draft_id, to_email, subject, body, sent_at)
           VALUES (?,?,?,?,?,?)""",
        (thread_id, draft_id, to_email, subject, body, now_iso()),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM outbound_messages WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


def list_outbound(thread_id: str) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM outbound_messages WHERE thread_id=? ORDER BY id", (thread_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def list_inbound(thread_id: str) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM inbound_messages WHERE thread_id=? ORDER BY id", (thread_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def notify_am(thread_id: str, kind: str, message: str) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO am_notifications (thread_id, kind, message, created_at) VALUES (?,?,?,?)",
        (thread_id, kind, message, now_iso()),
    )
    conn.commit()


def list_am_notifications(limit: int = 100) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM am_notifications ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def metrics() -> dict:
    conn = get_conn()
    rows = conn.execute(
        "SELECT status, COUNT(*) AS n FROM quote_threads GROUP BY status"
    ).fetchall()
    by_status = {r["status"]: r["n"] for r in rows}
    total = sum(by_status.values())
    pending_approvals = conn.execute(
        "SELECT COUNT(*) AS n FROM quote_drafts WHERE approval_status='pending'"
    ).fetchone()["n"]
    return {"total_threads": total, "by_status": by_status, "pending_approvals": pending_approvals}

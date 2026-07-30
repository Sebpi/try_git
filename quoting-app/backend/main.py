"""FastAPI app: webhooks/simulate endpoints, thread/approval/reminder REST API,
and the admin dashboard static files. See SPEC.md for the overall design.
"""
from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db
import orchestrator

ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "dev-admin-token")
SWEEP_INTERVAL_MINUTES = int(os.environ.get("REMINDER_SWEEP_INTERVAL_MINUTES", "15"))

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

_scheduler: BackgroundScheduler | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    global _scheduler
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(orchestrator.run_reminder_sweep, "interval",
                        minutes=SWEEP_INTERVAL_MINUTES, id="reminder_sweep")
    _scheduler.start()
    yield
    _scheduler.shutdown(wait=False)


app = FastAPI(title="Quoting App", lifespan=lifespan)


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Missing or invalid X-Admin-Token header")


# ------------------------------------------------------------------- health --
@app.get("/api/health")
def health():
    return {"status": "ok", "time": db.now_iso()}


# ------------------------------------------------------------ inbound email --
class InboundEmail(BaseModel):
    from_email: str
    from_name: str | None = None
    subject: str
    body: str
    message_id: str | None = None


def _handle_inbound(payload: InboundEmail) -> dict:
    raw = payload.model_dump()
    raw["message_id"] = raw.get("message_id") or f"msg_{uuid.uuid4().hex}"
    return orchestrator.process_inbound_email(raw)


@app.post("/dev/simulate-inbound-email", dependencies=[Depends(require_admin)])
def simulate_inbound_email(payload: InboundEmail):
    """Admin-only: inject a test inbound email to exercise the whole pipeline
    without a real mailbox connected. This is what the dashboard's Simulate
    panel calls."""
    return _handle_inbound(payload)


@app.post("/webhooks/inbound-email", dependencies=[Depends(require_admin)])
def webhook_inbound_email(payload: InboundEmail):
    """Real integration point for a provider webhook (Gmail push, Graph
    notification, Postmark/SendGrid inbound parse). Swap the auth dependency
    for provider signature verification before going live."""
    return _handle_inbound(payload)


class FastForward(BaseModel):
    hours: float = 72


@app.post("/dev/fast-forward/{thread_id}", dependencies=[Depends(require_admin)])
def fast_forward(thread_id: str, payload: FastForward):
    """Admin-only testing helper: backdate a thread's clock so the reminder
    sweep treats it as if `hours` had already elapsed, without waiting."""
    thread = db.get_thread(thread_id)
    if not thread:
        raise HTTPException(404, "no such thread")
    past = datetime.now(timezone.utc) - timedelta(hours=payload.hours)
    db.update_thread(thread_id, last_outbound_at=past.isoformat())
    reminder = db.get_reminder(thread_id)
    if reminder:
        db.upsert_reminder(thread_id, stage=reminder["stage"], next_fire_at=past.isoformat())
    return {"ok": True, "backdated_to": past.isoformat()}


# ---------------------------------------------------------------- threads --
@app.get("/v1/threads", dependencies=[Depends(require_admin)])
def list_threads(status: str | None = None):
    return db.list_threads(status)


@app.get("/v1/threads/{thread_id}", dependencies=[Depends(require_admin)])
def get_thread(thread_id: str):
    thread = db.get_thread(thread_id)
    if not thread:
        raise HTTPException(404, "no such thread")
    return {
        "thread": thread,
        "line_items": db.list_line_items(thread_id),
        "drafts": db.list_drafts(thread_id),
        "decisions": db.list_decisions(thread_id),
        "reminder": db.get_reminder(thread_id),
        "routing_ticket": db.get_routing_ticket(thread_id),
        "inbound": db.list_inbound(thread_id),
        "outbound": db.list_outbound(thread_id),
    }


# -------------------------------------------------------------- approvals --
@app.get("/v1/approvals/pending", dependencies=[Depends(require_admin)])
def pending_approvals():
    return db.list_pending_drafts()


class ApproveBody(BaseModel):
    approver: str


class RejectBody(BaseModel):
    approver: str
    reason: str


class EditBody(BaseModel):
    approver: str
    subject: str
    body: str


@app.post("/v1/drafts/{draft_id}/approve", dependencies=[Depends(require_admin)])
def approve_draft(draft_id: int, payload: ApproveBody):
    try:
        return orchestrator.approve_draft(draft_id, payload.approver)
    except (ValueError, Exception) as exc:  # noqa: BLE001 -- surfaced as 400 for the dashboard
        raise HTTPException(400, str(exc))


@app.post("/v1/drafts/{draft_id}/reject", dependencies=[Depends(require_admin)])
def reject_draft(draft_id: int, payload: RejectBody):
    try:
        return orchestrator.reject_draft(draft_id, payload.approver, payload.reason)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc))


@app.post("/v1/drafts/{draft_id}/edit", dependencies=[Depends(require_admin)])
def edit_draft(draft_id: int, payload: EditBody):
    try:
        return orchestrator.edit_and_approve_draft(draft_id, payload.approver, payload.subject, payload.body)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc))


# -------------------------------------------------------------- reminders --
@app.post("/v1/reminders/run-sweep", dependencies=[Depends(require_admin)])
def run_reminder_sweep():
    return orchestrator.run_reminder_sweep()


# ---------------------------------------------------------------- misc UI --
@app.get("/v1/notifications", dependencies=[Depends(require_admin)])
def notifications():
    return db.list_am_notifications()


@app.get("/v1/metrics", dependencies=[Depends(require_admin)])
def metrics():
    return db.metrics()


@app.get("/v1/decisions", dependencies=[Depends(require_admin)])
def recent_decisions(limit: int = 50):
    return db.list_decisions(limit=limit)


# ------------------------------------------------------------- dashboard --
@app.get("/")
def dashboard_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

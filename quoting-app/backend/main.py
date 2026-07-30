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
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db
import gmail_poll
import orchestrator
from integrations import gmail_client

ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "dev-admin-token")
SWEEP_INTERVAL_MINUTES = int(os.environ.get("REMINDER_SWEEP_INTERVAL_MINUTES", "15"))
GMAIL_POLL_INTERVAL_MINUTES = int(os.environ.get("GMAIL_POLL_INTERVAL_MINUTES", "2"))

# --- seb-portal SSO integration -------------------------------------------
# Mirrors the pattern documented on stock-picker / Pick-shovels: accept a
# JWT minted by seb-portal (iss="seb-portal") alongside the local admin
# token, resolve identity as "portal:<sub>", and gate admin access on the
# token's `role` claim or an explicit allowlist. NOT verified against the
# real seb-portal source (no repo access at the time this was written) --
# double check the claim names below once that's available; this is the
# consumer-side contract stock-picker/Pick-shovels' CLAUDE.md describe.
PORTAL_JWT_SECRET = os.environ.get("PORTAL_JWT_SECRET")
PORTAL_ADMIN_USERS = {u.strip() for u in os.environ.get("QUOTING_APP_ADMIN_USERS", "").split(",") if u.strip()}
PORTAL_SIGNOUT_URL = os.environ.get("PORTAL_SIGNOUT_URL", "")

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

_scheduler: BackgroundScheduler | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    global _scheduler
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(orchestrator.run_reminder_sweep, "interval",
                        minutes=SWEEP_INTERVAL_MINUTES, id="reminder_sweep")
    if gmail_client.available():
        _scheduler.add_job(gmail_poll.poll_and_ingest, "interval",
                            minutes=GMAIL_POLL_INTERVAL_MINUTES, id="gmail_poll")
    _scheduler.start()
    yield
    _scheduler.shutdown(wait=False)


app = FastAPI(title="Quoting App", lifespan=lifespan)


def _verify_portal_jwt(token: str) -> str | None:
    """Returns a resolved "portal:<sub>" identity if `token` is a valid
    seb-portal JWT AND grants admin access to this app (role=="admin" claim,
    or the raw `sub`/resolved identity is in QUOTING_APP_ADMIN_USERS).
    Returns None on any failure -- never raises, so callers can treat it as
    just another form of "not authenticated"."""
    if not PORTAL_JWT_SECRET:
        return None
    import jwt as pyjwt
    try:
        payload = pyjwt.decode(token, PORTAL_JWT_SECRET, algorithms=["HS256"])
    except pyjwt.PyJWTError:
        return None
    if payload.get("iss") != "seb-portal":
        return None
    sub = payload.get("sub")
    if not sub:
        return None
    identity = f"portal:{sub}"
    is_admin = payload.get("role") == "admin" or sub in PORTAL_ADMIN_USERS or identity in PORTAL_ADMIN_USERS
    return identity if is_admin else None


def require_admin(x_admin_token: str | None = Header(default=None),
                   authorization: str | None = Header(default=None)) -> str:
    if x_admin_token == ADMIN_TOKEN:
        return "local:admin"
    if authorization and authorization.lower().startswith("bearer "):
        identity = _verify_portal_jwt(authorization.split(" ", 1)[1])
        if identity:
            return identity
    raise HTTPException(status_code=401,
                         detail="Missing or invalid credentials (X-Admin-Token or a seb-portal admin JWT)")


# ------------------------------------------------------------------- health --
@app.get("/api/health")
def health():
    return {"status": "ok", "time": db.now_iso()}


@app.get("/v1/whoami")
def whoami(identity: str = Depends(require_admin)):
    return {"identity": identity, "source": "portal" if identity.startswith("portal:") else "local"}


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


# -------------------------------------------------------------------- gmail --
@app.get("/v1/gmail/status", dependencies=[Depends(require_admin)])
def gmail_status():
    return {"configured": gmail_client.available(), "poll_interval_minutes": GMAIL_POLL_INTERVAL_MINUTES}


@app.post("/v1/gmail/poll-now", dependencies=[Depends(require_admin)])
def gmail_poll_now():
    return gmail_poll.poll_and_ingest()


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
@app.get("/", response_class=HTMLResponse)
def dashboard_index():
    with open(os.path.join(FRONTEND_DIR, "index.html")) as f:
        html = f.read()
    # Runtime-injected so PORTAL_SIGNOUT_URL can change without a rebuild --
    # same per-request injection pattern stock-picker/SOAR use (Pick-shovels
    # injects once at container boot instead; see its CLAUDE.md for why).
    html = html.replace("%%PORTAL_SIGNOUT_URL%%", PORTAL_SIGNOUT_URL)
    return HTMLResponse(content=html)


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

"""Approval Agent -- the human gate. Not LLM-backed: it packages a draft for
AM review and applies whatever decision the AM makes. See SPEC.md agent #7.

Nothing in this module sends email -- approve() hands off to sender.send()
so the "no send without an approved draft version" invariant lives in one
place (orchestrator + sender), not duplicated here.
"""
from __future__ import annotations

import db


class ApprovalError(Exception):
    pass


def get_pending() -> list[dict]:
    return db.list_pending_drafts()


def _require_pending(draft_id: int) -> dict:
    draft = db.get_draft(draft_id)
    if not draft:
        raise ApprovalError(f"No such draft {draft_id}")
    if draft["approval_status"] != "pending":
        raise ApprovalError(f"Draft {draft_id} is already {draft['approval_status']}")
    return draft


def approve(draft_id: int, approver: str) -> dict:
    draft = _require_pending(draft_id)
    draft = db.update_draft(draft_id, approval_status="approved", approver=approver,
                             decided_at=db.now_iso())
    db.log_decision(
        draft["thread_id"], "approval",
        f"AM {approver} approved draft v{draft['version']} ({draft['kind']})",
        {"draft_id": draft_id, "kind": draft["kind"]},
    )
    return draft


def reject(draft_id: int, approver: str, reason: str) -> dict:
    draft = _require_pending(draft_id)
    draft = db.update_draft(draft_id, approval_status="rejected", approver=approver,
                             reject_reason=reason, decided_at=db.now_iso())
    db.log_decision(
        draft["thread_id"], "approval",
        f"AM {approver} rejected draft v{draft['version']} ({draft['kind']}): {reason}",
        {"draft_id": draft_id, "kind": draft["kind"], "reason": reason},
    )
    return draft


def edit_and_approve(draft_id: int, approver: str, subject: str, body: str) -> dict:
    """AM rewrote the draft and is approving their own version in one step.

    Supersedes the original (kept for audit) and creates a new approved
    version so there's always one canonical "what got approved" record.
    """
    original = _require_pending(draft_id)
    db.update_draft(draft_id, approval_status="superseded", approver=approver,
                     decided_at=db.now_iso())
    new_draft = db.create_draft(
        original["thread_id"], kind=original["kind"], subject=subject, body=body,
        total=original["total"], currency=original["currency"],
    )
    new_draft = db.update_draft(new_draft["id"], approval_status="approved", approver=approver,
                                 decided_at=db.now_iso())
    db.log_decision(
        original["thread_id"], "approval",
        f"AM {approver} edited draft v{original['version']} -> v{new_draft['version']} and approved it",
        {"original_draft_id": draft_id, "new_draft_id": new_draft["id"]},
    )
    return new_draft

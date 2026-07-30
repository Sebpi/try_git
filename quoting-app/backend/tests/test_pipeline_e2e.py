from datetime import datetime, timedelta, timezone

import db
import orchestrator
from agents import reminder as reminder_agent


def _inbound(**kw):
    base = {"message_id": None, "from_email": "x@example.com", "from_name": "X", "subject": "s", "body": "b"}
    base.update(kw)
    if base["message_id"] is None:
        base["message_id"] = f"msg-{kw.get('subject','')}-{kw.get('body','')}-{id(kw)}"
    return base


def test_simple_quote_full_happy_path_to_acceptance():
    inbound = _inbound(
        from_email="jordan.lee@northwind.example", from_name="Jordan Lee",
        subject="Quote request",
        body="Hi, could you send a quote for 5 ergonomic office chairs?",
        message_id="m1",
    )
    result = orchestrator.process_inbound_email(inbound)
    assert result["status"] == "PENDING_APPROVAL"

    pending = db.list_pending_drafts()
    assert len(pending) == 1
    draft = pending[0]
    assert draft["kind"] == "quote"
    # Northwind has an account-specific price-book override for this SKU (289.0 vs list 329.0)
    assert draft["total"] == 5 * 289.0

    thread_after_send = orchestrator.approve_draft(draft["id"], "AM Approver")
    assert thread_after_send["status"] == "AWAITING_RESPONSE"
    assert db.get_reminder(thread_after_send["id"]) is not None

    reply = _inbound(
        from_email="jordan.lee@northwind.example", from_name="Jordan Lee",
        subject=f"Re: Quote request [Ref: {thread_after_send['id']}]",
        body="This looks great, please go ahead and confirm the order.",
        message_id="m2",
    )
    result2 = orchestrator.process_inbound_email(reply)
    assert result2["status"] == "ACCEPTED"
    assert db.get_reminder(thread_after_send["id"]) is None  # clock cancelled


def test_complex_quote_routes_to_human():
    inbound = _inbound(
        from_email="sam.osei@globex.example", from_name="Sam Osei",
        subject="Custom fit-out",
        body="We'd like custom enterprise pricing and want to book a call to discuss integration.",
        message_id="m3",
    )
    result = orchestrator.process_inbound_email(inbound)
    assert result["status"] == "ROUTED_TO_HUMAN"
    ticket = db.get_routing_ticket(result["thread_id"])
    assert ticket is not None
    assert ticket["assigned_am"] == "Marcus Webb"


def test_unknown_customer_routes_to_human():
    inbound = _inbound(
        from_email="nobody@unknown.example", from_name="Nobody",
        subject="Quote please", body="Please send a quote for 3 wireless keyboards.",
        message_id="m4",
    )
    result = orchestrator.process_inbound_email(inbound)
    assert result["status"] == "ROUTED_TO_HUMAN"


def test_rejection_flow_drafts_followup_and_closes_lost_on_silence():
    inbound = _inbound(
        from_email="peter.gibbons@initech.example", from_name="Peter Gibbons",
        subject="Quote request", body="Could you quote 2 standing desks?",
        message_id="m5",
    )
    r1 = orchestrator.process_inbound_email(inbound)
    draft = db.list_pending_drafts()[0]
    thread = orchestrator.approve_draft(draft["id"], "AM")

    reply = _inbound(
        from_email="peter.gibbons@initech.example", from_name="Peter Gibbons",
        subject=f"Re: Quote request [Ref: {thread['id']}]",
        body="Thanks but it's too expensive for us, we'll pass on this.",
        message_id="m6",
    )
    r2 = orchestrator.process_inbound_email(reply)
    assert r2["status"] == "PENDING_APPROVAL"
    followup_draft = db.list_pending_drafts()[0]
    assert followup_draft["kind"] == "rejection_followup"

    thread2 = orchestrator.approve_draft(followup_draft["id"], "AM")
    assert thread2["status"] == "FOLLOW_UP_SENT"

    # simulate silence past the follow-up window and run the sweep
    past = datetime.now(timezone.utc) - timedelta(days=10)
    reminder_row = db.get_reminder(thread2["id"])
    db.upsert_reminder(thread2["id"], stage=reminder_row["stage"], next_fire_at=past.isoformat())
    reminder_agent.run_sweep()
    closed = db.get_thread(thread2["id"])
    assert closed["status"] == "CLOSED_LOST"


def test_query_flow_reprices_new_product_and_resends():
    inbound = _inbound(
        from_email="charlie.bucket@wonka.example", from_name="Charlie Bucket",
        subject="Quote request", body="Could you quote 1 wireless mouse?",
        message_id="m7",
    )
    orchestrator.process_inbound_email(inbound)
    draft = db.list_pending_drafts()[0]
    thread = orchestrator.approve_draft(draft["id"], "AM")

    reply = _inbound(
        from_email="charlie.bucket@wonka.example", from_name="Charlie Bucket",
        subject=f"Re: Quote request [Ref: {thread['id']}]",
        body="Could you also include a wireless keyboard in this? What's the total then?",
        message_id="m8",
    )
    r2 = orchestrator.process_inbound_email(reply)
    assert r2["status"] == "PENDING_APPROVAL"
    qdraft = db.list_pending_drafts()[0]
    assert qdraft["kind"] == "query_response"
    line_items = db.list_line_items(thread["id"])
    skus = {li["resolved_sku"] for li in line_items}
    assert "IT-KB-WIRELESS" in skus and "IT-MOUSE-WIRELESS" in skus


def test_reminder_sweep_full_cadence_to_close_no_response():
    inbound = _inbound(
        from_email="jordan.lee@northwind.example", from_name="Jordan Lee",
        subject="Quote request", body="Could you quote 1 standing desk?",
        message_id="m9",
    )
    orchestrator.process_inbound_email(inbound)
    draft = db.list_pending_drafts()[0]
    thread = orchestrator.approve_draft(draft["id"], "AM")

    def backdate_and_sweep():
        row = db.get_reminder(thread["id"])
        past = datetime.now(timezone.utc) - timedelta(days=10)
        db.upsert_reminder(thread["id"], stage=row["stage"], next_fire_at=past.isoformat())
        return reminder_agent.run_sweep()

    fired = backdate_and_sweep()
    assert fired["drafted_1st"] == 1
    reminder_draft = db.list_pending_drafts()[0]
    assert reminder_draft["kind"] == "reminder_1st"
    orchestrator.approve_draft(reminder_draft["id"], "AM")

    fired = backdate_and_sweep()
    assert fired["drafted_2nd"] == 1
    reminder_draft2 = db.list_pending_drafts()[0]
    assert reminder_draft2["kind"] == "reminder_2nd"
    orchestrator.approve_draft(reminder_draft2["id"], "AM")

    fired = backdate_and_sweep()
    assert fired["closed_no_response"] == 1
    closed = db.get_thread(thread["id"])
    assert closed["status"] == "CLOSED_NO_RESPONSE"

import db
from agents import triage


def _thread():
    return db.create_thread(
        email_thread_key="k1", customer_email="jordan.lee@northwind.example",
        customer_name="Jordan Lee", subject="Quote request",
    )


def test_triage_simple_when_product_matched_and_no_negotiation():
    t = _thread()
    result = triage.run(t, "Could you send a quote for 5 ergonomic office chairs?")
    assert result["complexity"] == "simple"


def test_triage_complex_when_no_product_recognised():
    t = _thread()
    result = triage.run(t, "We need something for our new office, not sure what yet.")
    assert result["complexity"] == "complex"
    assert "no catalog product" in result["reason"]


def test_triage_complex_on_negotiation_language():
    t = _thread()
    result = triage.run(t, "We'd like 50 ergonomic office chairs but want to negotiate a custom discount and schedule a call.")
    assert result["complexity"] == "complex"
    assert "negotiation" in result["reason"]


def test_triage_persists_complexity_on_thread():
    t = _thread()
    triage.run(t, "Could you send a quote for 2 standing desks?")
    reloaded = db.get_thread(t["id"])
    assert reloaded["complexity"] == "simple"

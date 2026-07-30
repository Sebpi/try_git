from integrations import product_catalog
from agents import response_classifier


def test_exact_product_match_high_confidence():
    matches = product_catalog.match_products_in_text("I'd like 3 ergonomic office chairs please")
    assert matches
    m = matches[0]
    assert m.resolved_sku == "OFC-CHAIR-ERGO"
    assert m.confidence >= 0.9
    assert m.quantity == 3


def test_no_match_returns_empty():
    matches = product_catalog.match_products_in_text("We'd like a custom enterprise integration built")
    assert matches == []


def test_response_classifier_accept():
    result = response_classifier.classify("This looks great, please go ahead and confirm the order.")
    assert result["label"] == "accept"


def test_response_classifier_reject():
    result = response_classifier.classify("Thanks but it's too expensive for us, we'll pass on this.")
    assert result["label"] == "reject"


def test_response_classifier_query():
    result = response_classifier.classify("Does this include delivery, and what's the lead time?")
    assert result["label"] == "query"


def test_response_classifier_ooo_is_not_a_reply():
    result = response_classifier.classify("I am currently out of office and will respond when I return.")
    assert result["label"] == "not_a_reply"


def test_response_classifier_unclear_on_contradiction():
    result = response_classifier.classify("We accept but honestly this is too expensive, not interested.")
    assert result["label"] == "unclear"

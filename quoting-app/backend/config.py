"""Tunables referenced across agents. See SPEC.md for the rationale behind each."""
import os

# Triage / pricing confidence
TRIAGE_CONFIDENCE_THRESHOLD = float(os.environ.get("TRIAGE_CONFIDENCE_THRESHOLD", "0.8"))

NEGOTIATION_KEYWORDS = [
    "discount", "negotiate", "negotiable", "custom", "bespoke", "integration",
    "integrate", "scope of work", "sow", "enterprise agreement", "book a call",
    "schedule a call", "hop on a call", "meeting", "consult", "consultation",
    "tailored", "custom pricing", "volume pricing", "special pricing",
    "multi-year", "rfp", "tender", "procurement process",
]

ACCEPT_KEYWORDS = [
    "accept", "approved", "go ahead", "please proceed", "sounds good", "let's do it",
    "confirm the order", "purchase order", "po attached", "we'll take it",
    "happy to proceed", "please go ahead", "confirmed", "we accept",
]
REJECT_KEYWORDS = [
    "not moving forward", "decline", "too expensive", "went with another",
    "no thank", "not interested", "pass on this", "won't be proceeding",
    "not proceeding", "we'll pass", "not the right fit", "too pricey",
]
OOO_KEYWORDS = [
    "out of office", "automatic reply", "auto-reply", "autoreply",
    "vacation responder", "away from my desk", "on leave",
]

REJECT_REASON_KEYWORDS = {
    "price": ["expensive", "price", "cost", "budget", "cheaper", "pricey"],
    "availability": ["availability", "in stock", "lead time", "out of stock", "backorder"],
    "timeline": ["timeline", "too slow", "too long", "delivery time", "urgent", "deadline"],
}

# Reminder cadence (days). Kept as floats so a demo can use fractional days.
REMINDER_STAGE1_DAYS = float(os.environ.get("REMINDER_STAGE1_DAYS", "2.5"))
REMINDER_STAGE2_DAYS = float(os.environ.get("REMINDER_STAGE2_DAYS", "4.5"))
REMINDER_REQUIRE_APPROVAL = os.environ.get("REMINDER_REQUIRE_APPROVAL", "true").lower() == "true"

QUOTE_VALIDITY_DAYS = int(os.environ.get("QUOTE_VALIDITY_DAYS", "14"))

TERMINAL_STATES = {
    "ACCEPTED", "CLOSED_LOST", "CLOSED_NO_RESPONSE", "ROUTED_TO_HUMAN", "NEEDS_HUMAN_REVIEW",
}
# States where the thread is actively waiting on a customer reply and the
# Response Classifier / Reminder Agent should engage.
AWAITING_STATES = {"AWAITING_RESPONSE"}

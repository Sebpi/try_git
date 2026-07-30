# Agentic Quoting App — Specification

## 1. Purpose

An email-driven, multi-agent system that turns an inbound customer email into
either (a) an approved, sent quotation with automatic follow-through to
acceptance/rejection/order, or (b) a routed hand-off to a human sales team for
quotes that need consultative selling. A human (the account manager, "AM") is
always the approver before anything reaches the customer, and always the
fallback for anything the system can't handle confidently.

**Design principle:** every agent is a narrow specialist with one job and a
typed input/output contract. An orchestrator drives a per-thread state machine
across agents; no agent calls another agent directly. This mirrors the
existing 21-agent pattern in `stock-picker` (`backend/agents/` +
`orchestrator`) — same shape, different domain.

## 2. Non-goals (v1)

- Not a full CPQ (configure-price-quote) system — no multi-line, tiered,
  or bundled pricing logic beyond a per-product price lookup.
- Not a negotiation engine — the system never counter-offers a price on its
  own; anything requiring a new number/term goes to a human.
- Not a replacement for the CRM — it reads/writes to CRM as a system of
  record, it doesn't become one.

## 3. High-level flow

```
Inbound email
     │
     ▼
[Ingestion Agent] ── dedups / threads the message
     │
     ▼
[Triage Agent] ──────────────► complex? ─► [Routing Agent] ─► AM + App Engineer (human takes over, thread tagged & tracked, no further automation on it)
     │ simple
     ▼
[CRM Lookup Agent] ─► client identity, account, existing open quotes
     │
     ▼
[Product & Pricing Agent] ─► resolves product(s) + price(s) from product DB
     │
     ▼
[Quote Composer Agent] ─► drafts the quote email
     │
     ▼
[Approval Agent] ──► AM reviews (approve / edit / reject) ──► reject/edit loop back to Composer
     │ approved
     ▼
[Sender Agent] ─► sends quote to customer, starts the response-tracking clock
     │
     ▼
   ... customer reply arrives (or doesn't) ...
     │
     ▼
[Response Classifier Agent] ─► accept | reject | query | (silence, handled by Reminder Agent)
     │
     ├─ accept  ─► [Acceptance Agent]   ─► CRM update, notify AM "order received", trigger order processing
     ├─ reject  ─► [Rejection Follow-up Agent] ─► sends "why not" email (price/availability/timeline/other), logs reason, closes or re-opens loop
     └─ query   ─► [Query Response Agent] ─► drafts an answer, AM approves (same gate as initial quote), sends, resets clock

[Reminder Agent] runs continuously against every open thread with no terminal
state, firing day-2/3 and day-4/5 nudges until a definitive outcome or a
final-timeout close.
```

## 4. Core entities / data model

| Entity | Key fields | Notes |
|---|---|---|
| `QuoteThread` | id, email_thread_id (Message-ID/References chain), customer_email, crm_contact_id, crm_account_id, status, complexity, created_at, last_inbound_at, last_outbound_at, reminder_count, sla_state | One row per customer conversation. Status is the state-machine state (§5). |
| `QuoteLineItem` | thread_id, product_query_text, resolved_sku, resolved_price, currency, quantity, confidence | One or more per thread; ambiguous/unresolved lines force `complex`. |
| `QuoteDraft` | thread_id, version, body_html/text, line_items, total, approval_status, approver_id, approved_at, edits_diff | Every AM edit creates a new version; approval always binds to a specific version. |
| `AgentDecision` | thread_id, agent_name, input_ref, output, confidence, timestamp | Full audit trail — every agent call is logged, mirroring `agent_signal`/`investment_thesis` audit pattern in stock-picker. |
| `ReminderSchedule` | thread_id, next_fire_at, stage (`1st`/`2nd`/`final`), fired_at[] | Drives the nurture cadence in §7. |
| `RoutingTicket` | thread_id, reason, assigned_am_id, assigned_engineer_id, routed_at | Created when Triage marks a thread `complex`. |

State stored in Postgres/SQLite (reuse the stock-picker convention: SQLite is
fine to start, Postgres if concurrent AM approvals need row-level locking).

## 5. Thread state machine

```
NEW
 → TRIAGED_SIMPLE | TRIAGED_COMPLEX
TRIAGED_COMPLEX → ROUTED_TO_HUMAN (terminal for automation; human can manually
                  re-inject a resulting quote back into DRAFTING if they want
                  the system to send it)
TRIAGED_SIMPLE → ENRICHING (CRM + product lookup)
ENRICHING → DRAFTING (composer) → PENDING_APPROVAL
PENDING_APPROVAL → (AM rejects/edits) → DRAFTING
PENDING_APPROVAL → (AM approves) → SENT
SENT → AWAITING_RESPONSE (reminder clock starts)
AWAITING_RESPONSE → (customer replies) → CLASSIFYING
CLASSIFYING → ACCEPTED (terminal, success)
CLASSIFYING → REJECTED → FOLLOW_UP_SENT → CLOSED_LOST (terminal)
CLASSIFYING → QUERY_RECEIVED → DRAFTING (query-response draft) → PENDING_APPROVAL
                 → SENT → AWAITING_RESPONSE (loop continues)
AWAITING_RESPONSE → (no reply after final reminder) → CLOSED_NO_RESPONSE (terminal)
```

Every terminal state stops the reminder clock. Re-entering `DRAFTING` from
`QUERY_RECEIVED` always routes back through the same `PENDING_APPROVAL` gate —
**no automated email ever reaches the customer without an AM approval on that
specific draft version**, including query replies and rejection follow-ups.

## 6. Agents

Each agent is a stateless function: `(thread_context) -> AgentOutput`, logged
to `AgentDecision`. LLM-backed agents use a small/cheap model for
classification/extraction and a stronger model only for the composer (drafting
customer-facing prose) — same two-tier split as stock-picker's
`ANTHROPIC_MODEL` vs `THESIS_MODEL`.

1. **Ingestion Agent** — polls/receives inbound mail (IMAP idle, or a
   provider webhook — Gmail API push, Microsoft Graph subscription, or
   Postmark/SendGrid inbound-parse). Resolves the email to an existing
   `QuoteThread` via `In-Reply-To`/`References` headers first, falling back to
   sender-address + subject-similarity matching for clients who break
   threading. Deduplicates by `Message-ID`. Creates a new `QuoteThread` if no
   match.

2. **Triage Agent** — classifies `simple` vs `complex`. Simple requires: (a)
   the requested product(s) unambiguously match ≥1 catalog SKU at a defined
   confidence threshold, (b) quantity/spec is stated or trivially defaulted,
   (c) no explicit request for negotiation, custom terms, integration
   scoping, or a call/meeting. Anything failing (a)–(c), or below the
   confidence threshold, is `complex`. Output includes the specific reason
   (used later for routing and for audit).

3. **Routing Agent** (complex path) — determines the right AM (account
   owner from CRM) and application engineer (product-area mapping) and
   creates a `RoutingTicket` + notification (email/Slack) with the original
   customer email, the extracted ask, and *why* triage called it complex, so
   the human isn't starting cold.

4. **CRM Lookup Agent** — resolves the customer's CRM account/contact from
   the sender email (and CC'd colleagues). Surfaces existing open
   opportunities/quotes on the account so the composer doesn't quote in a
   vacuum (e.g., duplicate request, existing discount tier). No match →
   flag as `needs_review` and treat as complex (unknown-customer quoting is a
   deliberate escalation, not an auto-quote).

5. **Product & Pricing Agent** — maps each requested line to a catalog SKU
   and current price (list price, then any account-specific price book from
   CRM). Returns a confidence per line; low confidence bumps the thread back
   to complex even after Triage passed it (belt-and-braces — Triage works off
   the raw email, this agent works off the actual catalog and can catch a
   near-miss Triage didn't).

6. **Quote Composer Agent** — drafts the outbound quote email: line items,
   price, currency, validity period, and an explicit **Accept / Reject / Ask
   a question** call-to-action with a stable reference (thread/quote ID) the
   customer can reply to. Also drafts the two downstream email types reusing
   the same template family: query-response and rejection-follow-up.

7. **Approval Agent** — not an LLM decision-maker; it's the human gate.
   Packages the draft (diffable against the previous version if this is a
   re-approval) into whatever channel the AM works in (email with
   Approve/Edit/Reject links, or a Slack/Teams action, or a small internal
   web UI) and waits. Edits create a new `QuoteDraft` version and loop back to
   `DRAFTING`→`PENDING_APPROVAL` rather than sending directly, so there's
   always one canonical "what got approved" record.

8. **Sender Agent** — sends the approved version verbatim (no last-mile LLM
   rewriting after approval — what was approved is what goes out), stamps
   `SENT`, starts `AWAITING_RESPONSE`, and schedules the first reminder.

9. **Response Classifier Agent** — reads an inbound reply on an
   `AWAITING_RESPONSE` thread and classifies `accept` / `reject` / `query` /
   `unclear`. `unclear` routes to a human rather than guessing (e.g., a
   forwarded email, an out-of-office autoresponder, or a reply that's really a
   new unrelated request).

10. **Acceptance Agent** — on `accept`: updates CRM (opportunity → won /
    order stage), notifies the AM that the order was received and needs
    processing, and stops the reminder clock. Does not itself trigger
    fulfillment/billing — that's a handoff to whatever order-processing
    system exists, out of scope here.

11. **Rejection Follow-up Agent** — on `reject`: drafts a "help us
    understand" email probing the likely axis (price / availability /
    timeline / other — inferred from the rejection text where possible,
    otherwise a generic open question), sent through the same approval gate.
    Logs the rejection reason to CRM for pipeline reporting regardless of
    whether the customer answers the follow-up.

12. **Query Response Agent** — on `query`: attempts an answer using the same
    CRM + product context already gathered (and can re-invoke the Product &
    Pricing Agent if the question introduces a new product/quantity). Always
    routes the drafted answer through Approval before sending — a query
    reply is still a customer-facing commitment.

13. **Reminder / Nurture Agent** — the scheduler-driven agent (APScheduler or
    equivalent cron) that scans `AWAITING_RESPONSE` threads: fires reminder 1
    at 2–3 days of silence, reminder 2 at 4–5 days after *that* (i.e. ~day
    6–8 from the original send), and then closes the thread
    `CLOSED_NO_RESPONSE` if there's still nothing — logged and reported to
    the AM rather than silently dropped, since a cold lead is still a CRM
    signal. Reminders are also drafted-then-approved on first rollout;
    once the AM trusts the template, low-risk reminder sends can be
    fast-tracked without per-instance approval (configurable, off by
    default).

14. **Orchestrator** — owns the state machine in §5, invokes agents in
    sequence, persists `AgentDecision` rows, and enforces the one hard
    invariant: **no outbound customer email without a corresponding approved
    `QuoteDraft` version**, checked at the `Sender Agent` boundary regardless
    of which upstream agent produced the draft.

## 7. Reminder / SLA cadence

| Event | Timing |
|---|---|
| Quote sent | Day 0 |
| Reminder 1 | Day 2–3 of silence (configurable window, not a fixed instant — jitter to avoid robotic timing) |
| Reminder 2 | Day 4–5 *after reminder 1* (~day 6–8 overall) |
| Close-out | If still silent after reminder 2: `CLOSED_NO_RESPONSE`, AM notified, CRM opportunity marked stale — not auto-deleted |

Same cadence applies after a query-response send or a rejection-follow-up
send — each restarts its own `AWAITING_RESPONSE` clock, capped at the same
two-reminder ceiling so a chatty thread can't nurture forever.

## 8. Human-in-the-loop gates (summary)

- Every complex triage → human (AM + application engineer), no automation
  continues on that thread.
- Every outbound customer email (initial quote, query answer, rejection
  follow-up, reminder-if-not-fast-tracked) → AM approve/edit/reject before
  send.
- Unknown customer (no CRM match) → human review.
- Low-confidence product/price match → human review, even if Triage initially
  called it simple.
- Unclear customer response (can't classify accept/reject/query) → human
  review.
- AM is notified (not asked to approve) on: order received/accepted, thread
  closed with no response, thread closed lost with reason.

## 9. Integrations

- **Inbound email**: provider webhook (Gmail API push / Microsoft Graph
  change notifications / Postmark or SendGrid inbound parse) preferred over
  polling; IMAP IDLE as a fallback for a mailbox without a modern API.
- **Outbound email**: transactional send API (SES/SendGrid/Postmark/SMTP),
  reusing whatever the org already has (stock-picker's own SMTP/Twilio
  pattern is a reasonable precedent if this lives alongside it).
- **CRM**: read (contact/account/opportunity lookup, price books) + write
  (opportunity stage, logged activity, rejection reason). Whichever CRM —
  Salesforce/HubSpot/Dynamics — via its REST API; abstract behind a thin CRM
  client so the agent layer doesn't know the vendor.
- **Product/pricing DB**: internal catalog service or a table synced from
  the CRM/ERP price book; needs a fuzzy-match layer (name/synonym/SKU) since
  customers rarely type exact SKUs.
- **AM approval channel**: email-with-action-links is the simplest MVP
  (signed links back to the app); Slack/Teams interactive message is a nicer
  v2; a small internal review UI is the long-term answer once volume
  justifies it.
- **Scheduler**: APScheduler-style cron/interval jobs for inbox polling
  (if not webhook-driven) and the reminder sweep.

## 10. Cross-cutting concerns

- **Audit trail**: every agent decision logged with inputs/outputs/confidence
  (`AgentDecision`), every approval logged with who/when/what version — this
  is a sales-facing, money-adjacent system, treat it like the stock-picker
  learning system's decision log, not as optional.
- **Idempotency**: email webhooks can redeliver; dedupe on `Message-ID`
  before creating a new thread or re-running triage.
- **Concurrency**: two inbound emails on the same thread arriving close
  together (e.g., customer replies twice) must not race into two separate
  drafts — lock per-thread while an agent run is in flight.
- **Price staleness**: a draft approved 3 days ago whose price changed in the
  interim should re-validate price at send time, not just at draft time.
- **Guardrails**: the Composer never invents a price or product not returned
  by the Pricing Agent; the system should refuse to draft (and flag to a
  human) rather than hallucinate a number.
- **Spam/OOO filtering**: out-of-office autoreplies and obvious spam must not
  be misclassified as `query` or `reject` — Response Classifier needs an
  explicit "not a real reply" bucket that leaves the thread's clock
  untouched.

## 11. Suggested build phases

1. **MVP**: Ingestion + Triage + CRM Lookup + Pricing + Composer + Approval
   (email-link based) + Sender, single simple-quote happy path, manual
   testing of complex-routing and one reminder tier.
2. **V2**: Response Classifier + Acceptance/Rejection/Query agents, full
   reminder cadence (both tiers), CRM write-back on every outcome.
3. **V3**: Approval via Slack/Teams action buttons, price-staleness
   revalidation, account-specific price books, dashboard over
   `AgentDecision`/`QuoteThread` for pipeline visibility.

## 12. Success metrics

- % of inbound quote requests auto-classified correctly as simple/complex
  (measured against AM override rate).
- Time from inbound email to AM approval request (should be minutes, not
  hours).
- % of simple quotes that reach a definitive outcome (accept/reject) without
  needing the final close-out reminder.
- AM edit rate on drafted quotes (proxy for composer quality over time).
- False-escalation rate (simple quotes that should've triaged complex, and
  vice versa) — feed this back into the Triage prompt/thresholds the same
  way stock-picker's learning system recalibrates agent weights from
  outcomes.

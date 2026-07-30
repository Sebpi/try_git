# Quoting App

Implementation of the agentic quoting workflow described in [`SPEC.md`](./SPEC.md):
an email-driven pipeline of 14 narrow agents (triage, CRM lookup, pricing,
drafting, human approval, sending, response classification, acceptance/
rejection/query handling, reminders, routing, and an orchestrator tying them
together), plus an admin dashboard to watch it work.

Runs entirely on mocked integrations (CRM, product catalog, outbound email)
seeded with sample data, so the whole pipeline is demoable with zero external
credentials. Swap the `integrations/` modules for real CRM/catalog/email
clients when connecting it to a real inbox.

## Quick start

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

ADMIN_TOKEN=dev-admin-token uvicorn main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000/ and paste `dev-admin-token` into the token box
(top right) -- that's the shared admin secret checked on every `/v1/*` and
`/dev/*` call (see `require_admin` in `main.py`). Change `ADMIN_TOKEN` before
running this anywhere but your own machine.

From the dashboard:
- **Simulate** -- injects a test inbound email straight into the Ingestion
  Agent (three one-click examples: simple quote, complex quote, unknown
  customer).
- **Approvals** -- every draft (initial quote, query answer, rejection
  follow-up, reminder) waits here for approve / edit+approve / reject before
  anything is sent.
- **Threads** -- click through to a thread's full agent decision timeline,
  resolved line items, draft history, and a "reply as customer" panel
  (accept / reject / ask a question) to drive the rest of the flow without a
  real mailbox.
- **Overview** -- live feed of every agent decision + AM notification across
  the whole system, plus status counts.

## Tests

```bash
cd backend && source .venv/bin/activate
python -m pytest tests/ -v
```

17 tests cover the triage/pricing/response-classifier heuristics and full
pipeline runs (simple quote to acceptance, complex-quote routing, unknown
customer routing, rejection -> follow-up -> closed-lost, query re-pricing,
and the full two-stage reminder cadence to close-no-response).

## Notable design choices

- **No ANTHROPIC_API_KEY required.** Triage, pricing-match, and response
  classification are deterministic heuristics by design (auditable, testable,
  no hallucination risk on business-critical decisions). The Composer agent
  drafts from a fixed template; if `ANTHROPIC_API_KEY` is set, it runs an
  optional tone-polish pass that is instructed never to change any number,
  SKU, or the reference token (`integrations/llm_client.py`,
  `agents/composer.py`). Response classification also gets an optional LLM
  fallback for genuinely ambiguous replies before landing on `unclear`.
- **One hard invariant:** no customer-facing email ever sends without a
  specifically-approved `quote_drafts` row. Enforced at the `sender.py`
  boundary regardless of which agent produced the draft (`orchestrator.py`).
- **Thread matching** uses a `[Ref: thr_xxxxxxxx]` token embedded in every
  outbound subject line (see `agents/ingestion.py`), falling back to
  sender-address matching against the most recently active thread.
- **Reminder cadence** (day 2-3, then day 4-5, then close) is driven entirely
  by `sender.py` calling `reminder.schedule_after_send()` right after each
  send -- the sweep (`reminder.run_sweep()`, wired to an APScheduler job in
  `main.py`) only ever fires what's already due, never decides what's next.
- **`/dev/fast-forward/{thread_id}`** (admin-only) backdates a thread's clock
  for demoing/testing the reminder cadence without waiting days.

## What's stubbed for a real deployment

- `integrations/crm_mock.py` / `integrations/product_catalog.py` -- swap for
  real CRM (Salesforce/HubSpot/Dynamics) and catalog/ERP API clients behind
  the same function signatures.
- `integrations/email_client.py` -- logs to console by default; set
  `SMTP_HOST` (+ `SMTP_PORT`/`SMTP_USER`/`SMTP_PASSWORD`/`SMTP_FROM`) for real
  outbound mail. Inbound is via `POST /webhooks/inbound-email` -- point a
  provider webhook (Gmail push, Microsoft Graph, Postmark/SendGrid inbound
  parse) at it and replace the admin-token check with real provider signature
  verification.
- The Approval Agent currently surfaces drafts only in this dashboard; SPEC.md
  §6 agent #7 also anticipates an email-link or Slack/Teams action-button
  channel for AMs who don't live in the dashboard.

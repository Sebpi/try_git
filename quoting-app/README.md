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

## Gmail setup (real send + inbound)

The email client now talks to Gmail for real when configured, and falls back
to SMTP (if `SMTP_HOST` is set) or a console log otherwise -- nothing else
changes, so the app runs fine with none of this configured.

1. In [Google Cloud Console](https://console.cloud.google.com/): create/select
   a project, then **APIs & Services -> Library** -> enable the **Gmail API**.
2. **APIs & Services -> Credentials -> Create Credentials -> OAuth client ID**,
   application type **Desktop app**. Download the client secret JSON.
3. `pip install -r requirements.txt` (already includes the Gmail API client
   libs), then run:
   ```bash
   python scripts/gmail_get_refresh_token.py path/to/client_secret.json
   ```
   This opens a browser for one-time consent against the Gmail account you
   want the app to send/receive as, and prints a refresh token.
4. Set the env vars it prints:
   ```
   GMAIL_CLIENT_ID=...
   GMAIL_CLIENT_SECRET=...
   GMAIL_REFRESH_TOKEN=...
   # optional -- only if it's a verified "Send As" alias on that account:
   GMAIL_SENDER_EMAIL=quotes@yourdomain.com
   ```
5. Restart the server. It will now:
   - **Send** every approved draft as a real Gmail message
     (`integrations/gmail_client.py`).
   - **Poll** the inbox every `GMAIL_POLL_INTERVAL_MINUTES` (default 2) for
     new messages, feed each one into `orchestrator.process_inbound_email`,
     and label it `QuotingAppProcessed` so it's never re-ingested
     (`gmail_poll.py`, wired into the APScheduler job in `main.py`).
   - Match replies to their thread using Gmail's own `threadId` first (most
     reliable), falling back to the `[Ref: ...]` subject token or sender
     address the same way the mocked path already did.

   The dashboard's **Simulate** tab shows whether Gmail is connected and has
   a "Poll Gmail now" button to trigger a fetch on demand instead of waiting
   for the schedule.

Polling rather than push notifications is deliberate: Gmail push requires a
Cloud Pub/Sub topic and domain verification, which is a lot of setup for a
mailbox that isn't a Workspace-managed domain -- the same IMAP-idle-vs-poll
trade-off SPEC.md already calls out for the Ingestion Agent.

## seb-portal integration

This app's side of the shared `seb-portal` SSO gateway (the same one
stock-picker and Pick-shovels sit behind), implemented against the pattern
those two repos' `CLAUDE.md` files describe:

> **This was written without access to the seb-portal repo itself** (session
> access to `Sebpi/seb-portal` couldn't be granted at the time) -- the claim
> names, `portal_nav` payload shape, and sign-out flow below are a best-effort
> match to stock-picker/Pick-shovels' documented contract, not verified
> against the real portal source. Treat this as a starting point to diff
> against the actual portal code once you have access, not a guarantee it's
> byte-for-byte compatible. **The portal-side registration (adding this app
> to seb-portal's app list/AppSwitcher, deploying it somewhere seb-portal can
> reach) is not done** -- that half needs the seb-portal repo.

**Backend** (`main.py`):
- Set `PORTAL_JWT_SECRET` to accept JWTs minted by seb-portal. `require_admin`
  now accepts either the existing `X-Admin-Token` header OR an
  `Authorization: Bearer <jwt>` where the JWT has `iss: "seb-portal"`,
  verifies with `PORTAL_JWT_SECRET` (HS256), and resolves identity as
  `"portal:<sub>"` -- mirroring stock-picker's `get_current_user` contract.
- Admin access via a portal token requires either the JWT's `role` claim to
  equal `"admin"`, or the `sub` to be listed in `QUOTING_APP_ADMIN_USERS`
  (comma-separated), mirroring Pick-shovels' `PICK_SHOVELS_ADMIN_USERS`
  override pattern.
- `GET /v1/whoami` returns the resolved identity + whether it came from
  `local` or `portal` -- the dashboard uses this to prefill the approver name
  instead of prompting when signed in via the portal.
- `PORTAL_SIGNOUT_URL` is injected into `index.html` at request time (same
  per-request injection stock-picker/SOAR use for their portal sign-out pill;
  see Pick-shovels' `CLAUDE.md` for why it instead injects once at container
  boot -- a choice worth revisiting here if it turns out to matter for
  caching).

**Frontend** (`dashboard.js`): `ingestPortalHandoff()` captures
`#portal_token=<jwt>&portal_nav=<base64url>` from the URL hash (the same
convention Pick-shovels' `ingestPortalHandoff()` in `App.jsx` uses) into
`localStorage`, scrubs the hash, and switches `api()` to send
`Authorization: Bearer <token>` instead of `X-Admin-Token` whenever a portal
token is present. A sign-out pill and a best-effort app-switcher dropdown
(parsed from `portal_nav`, assumed to be an array of `{name, url}` -- adjust
`renderPortalBar()` once you can confirm the real shape) render in the
header when a portal session is active.

Everything above degrades to today's local-token flow when
`PORTAL_JWT_SECRET` is unset, so none of this is required to keep using the
app standalone.

## What's stubbed for a real deployment

- `integrations/crm_mock.py` / `integrations/product_catalog.py` -- swap for
  real CRM (Salesforce/HubSpot/Dynamics) and catalog/ERP API clients behind
  the same function signatures.
- The Approval Agent currently surfaces drafts only in this dashboard; SPEC.md
  §6 agent #7 also anticipates an email-link or Slack/Teams action-button
  channel for AMs who don't live in the dashboard.

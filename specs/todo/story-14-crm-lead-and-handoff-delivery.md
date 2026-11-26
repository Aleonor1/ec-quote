---
id: story-14
title: "Lead and handoff delivery to the CRM"
effort: MEDIUM
epic: EPIC-1
depends_on: [story-7]
shared_files: [ec_quote/integrations/crm.py, ec_quote/integrations/errors.py, ec_quote/api/main.py]
track: full
models: {implementer: large, qa: standard, ui: none, review: large}
---

# story-14: Lead and handoff delivery to the CRM

**Repository:** ec-quote · **Epic:** [EPIC-1](epic-1-price-and-offer.md) · **Depends on:** story-7 · **Contract:** [crm-ec-quote-bridge.md](crm-ec-quote-bridge.md)

## Summary

Every conversation that reaches a price or a handoff must exist in the CRM, where staff work: a lead with what was asked, the offer and the payment link, updated as the conversation moves, and a handoff that lands in front of a person with the summary. `ec_quote/integrations/crm.py` implements `CrmPort` and `HandoffPort` against the bridge contract. This story proves that adapter on recorded fixtures of the contract, makes delivery survive a CRM outage through an outbox with retries, and guarantees one lead per contact.

## User Story

As a staff member, I want every chat that asked for a price to appear in the CRM with its offer, and every handoff to reach me even if the CRM was down for a few minutes.

## Scope

**In:** `ec_quote/integrations/crm.py`, `ec_quote/integrations/errors.py`; `ec_quote/integrations/outbox.py` (new: durable queue in the SQLite store, retry schedule); `ec_quote/agent/store.py` (outbox table through the migration of story-3); `ec_quote/api/main.py` (outbox worker start and stop); `tests/integrations/test_crm.py`, `tests/integrations/test_outbox.py`, `tests/integrations/fixtures/crm/*.json`.

**Out:** the CRM side of the contract (EPIC-3 and the bridge spec); WhatsApp delivery of customer messages; the approval card in the inbox.

## Acceptance Criteria

1. `upsert_lead` sends the fields the bridge contract defines for a contact, summary, quote, checkout and status, authenticated with `CRM_API_SECRET`; the request body validates against the contract's schema fixture.
2. Statuses sent over a conversation's life are from the closed list of the contract (for example asked, offered, link sent, paid, handed off, lost); the same status for the same lead and offer is sent once.
3. Two `upsert_lead` calls for the same contact return the same lead id; the idempotency key is derived from channel and contact key, and the offer id when present.
4. `handoff` sends the reason code, the staff summary of story-7 and the lead id; it is sent once per handoff event even when retried.
5. A CRM timeout, connection error, 429 or 5xx leaves the item in the outbox; it is retried with backoff (1, 5, 15, 60 minutes, then hourly up to 24 hours, from the injected clock) and the customer flow is not delayed or failed by it.
6. A 4xx other than 401 and 429 marks the item failed, is not retried, and is reported in the daily metrics (story-17) with its error code; a 401 stops the worker and reports `crm_unauthorized` once.
7. Items for one contact are delivered in order; a failed lead upsert blocks that contact's later items but not other contacts.
8. After a restart the outbox continues from the stored items; nothing is lost or sent twice (the CRM fixture counts requests per idempotency key).
9. With `CRM_BASE_URL` unset, the adapter is a no-op that records items as `skipped_not_configured`, the service starts, and `/health?deep=1` reports the CRM as not configured.
10. The money values in the payload are strings with two decimals taken from the stored quote; `ad_source` is passed through unchanged when present.
11. No phone, name, email or summary text appears in logs; the log line for a delivery has the lead id, the item kind, the attempt and the status.

## Technical Notes

- The outbox worker is a background task started in the FastAPI lifespan; it takes the clock and the HTTP client by injection and has a `run_once(now)` used by tests.
- If the bridge contract is not final when this story starts, build against the version in `crm-ec-quote-bridge.md` at that commit and record the commit in the pull request; a contract change is a follow-up story.

## Hand-over

Owner: `CRM_BASE_URL` and `CRM_API_SECRET` on the VPS once the CRM side exists. Until then leads are recorded as skipped and visible in the weekly report.

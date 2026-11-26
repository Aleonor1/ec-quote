---
id: story-28
title: "CRM lead sync: offers appear as leads (optional)"
effort: MEDIUM
epic: EPIC-4
depends_on: [story-10, story-24]
shared_files: [ec_quote/integrations/crm.py, ec_quote/integrations/errors.py, ec_quote/api/main.py, ec_quote/agent/store.py]
track: full
models: {implementer: large, qa: standard, ui: none, review: large}
---

# story-28: CRM lead sync: offers appear as leads (optional)

**Repository:** ec-quote · **Epic:** [EPIC-4](epic-4-optional-site-chat-and-crm-lead-sync.md) · **Depends on:** story-10, story-24 · **Contract:** [crm-ec-quote-bridge.md](crm-ec-quote-bridge.md), section 1 only

> **Open decision.** Optional and later. The owner has not said whether and when leads should reach the CRM (EPIC-4 D4). The CRM side (`PUT /api/ec-quote/leads`) does not exist yet and is a CRM story from the bridge spec; this story must not start before both are decided.

## Summary

Offers made through the extension live only in ec-quote and in Shopify. If the owner wants them in the CRM, where leads and customers are tracked, each offer should appear there as a lead with what was asked, the price, the payment link and its status, updated when it is paid. `CrmClient` in `ec_quote/integrations/crm.py` was written on scaffold day against the bridge contract for a larger job (messages, handoffs, approvals). Only its lead upsert is used here; the rest of the bridge is no longer planned. Delivery goes through a durable outbox so a CRM outage never slows or breaks a suggestion.

## User Story

As the owner, I want every offer made on WhatsApp to be visible in the CRM next to the customer, without anyone typing it in.

## Scope

**In:** `ec_quote/integrations/crm.py` (the lead upsert only; unused bridge calls removed or clearly marked unused); `ec_quote/integrations/outbox.py` (new: durable queue in the SQLite store, retry schedule); `ec_quote/agent/store.py` (outbox table through the migration mechanism); `ec_quote/api/main.py` (outbox worker in the lifespan, only when configured); `tests/integrations/test_crm.py`, `tests/integrations/test_outbox.py`, fixtures.

**Out:** message forwarding, handoffs, approval cards, WhatsApp delivery and the paid order event of the bridge spec; anything in the CRM repository; reading from the CRM.

## Acceptance Criteria

1. With `CRM_BASE_URL` or `CRM_API_SECRET` unset, nothing is enqueued, no worker starts, the service behaves exactly as before, and health reports the CRM as not configured.
2. When configured, creating a payment link enqueues one lead upsert with the fields of the bridge contract's section 1 (contact, summary built by code, quote, checkout, status, the staff member), authenticated with the bearer token and an `Idempotency-Key` derived from channel, contact key and offer id; the body validates against the contract's fixture.
3. A status change (paid, expired, cancelled from story-24) enqueues one update for the same lead; the same status for the same offer is sent once.
4. Two upserts for the same contact return the same lead id; the id is stored on the conversation.
5. A CRM timeout, connection error, 429 or 5xx leaves the item in the outbox; it is retried with backoff (1, 5, 15, 60 minutes, then hourly up to 24 hours, from the injected clock); `suggest` and the payment link are never delayed or failed by it.
6. A 4xx other than 401 and 429 marks the item failed, is not retried, and is counted for the weekly report with its error code; a 401 stops the worker and is reported once.
7. Items for one contact are delivered in order; a failed item blocks that contact's later items but not other contacts.
8. After a restart the outbox continues from the stored items; nothing is lost or sent twice (the fixture counts requests per idempotency key).
9. Money values in the payload are strings with two decimals from the stored quote; no message text is sent, only the summary of validated choices.
10. No phone, name or summary appears in logs; the log line has the lead id, the item kind, the attempt and the status.

## Technical Notes

- The outbox worker takes the clock and the HTTP client by injection and has a `run_once(now)` used by tests.
- The bridge spec is another agent's file and describes more than this; build against its section 1 at the commit current when this story starts and record the commit in the pull request.

## Hand-over

Owner: the decision (EPIC-4 D4); then `CRM_BASE_URL` and `CRM_API_SECRET` on the host once the CRM route exists.

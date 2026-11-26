---
id: story-15
title: "Paid order tracking (orders/paid)"
effort: MEDIUM
epic: EPIC-1
depends_on: [story-3, story-10]
shared_files: [ec_quote/integrations/shopify.py, ec_quote/api/app.py, ec_quote/api/schemas.py]
track: full
models: {implementer: large, qa: standard, ui: none, review: large}
---

# story-15: Paid order tracking (orders/paid)

**Repository:** ec-quote · **Epic:** [EPIC-1](epic-1-price-and-offer.md) · **Depends on:** story-3, story-10 · **Contract:** [crm-ec-quote-bridge.md](crm-ec-quote-bridge.md), section 7

## Summary

The plan's main metric is how many offers become orders. Nothing tells ec-quote today that a payment link was paid. Two signals close the loop, and neither adds a Shopify webhook to ec-quote: a sweep that reads the status of the Draft Orders ec-quote created (`ShopifyCheckout.get_status`), which works from day one, and the event the CRM sends when it stores a paid order tagged `ec-quote` (`POST /v1/orders/paid`, bridge section 7), which is faster once the CRM side exists. Both lead to the same idempotent step: the offer becomes paid, follow ups stop, the lead is updated, and the customer gets one thank you message.

## User Story

As the owner, I want to know which offers were paid and how fast, and as a customer I do not want a reminder for something I already paid.

## Scope

**In:** `ec_quote/agent/orders.py` (new: `mark_paid`, the sweep); `ec_quote/api/app.py` and `ec_quote/api/schemas.py` (`POST /v1/orders/paid`); `ec_quote/integrations/shopify.py` (`get_status` as used by the sweep); `ec_quote/api/main.py` (periodic runner); `ec_quote/api/texts.py` (thank you text); `tests/agent/test_orders.py`, `tests/api/test_orders_paid.py`, fixtures with invented orders.

**Out:** a Shopify webhook subscription in ec-quote (the calculator app subscribes to `orders/create`, `orders/fulfilled` and `orders/cancelled`, the CRM handles order events; a third receiver is not needed); refunds and cancellations (a follow-up); ad revenue attribution (the CRM and ec-agency read the lead).

## Acceptance Criteria

1. `POST /v1/orders/paid` requires the inbound secret (401 otherwise) and a body with `event_id`, `channel`, `contact_key`, `draft_order_id`, `order_id`, `order_name`, `total`, `paid_at`; an unknown field or a missing one answers 422.
2. The offer is found by `draft_order_id`; when that is absent or unknown, by channel and contact key with the newest sent offer of the same total; it becomes `paid` with the order id, order name, paid amount and time.
3. `total` is parsed to `Decimal` from its string and compared with the offer total; a difference is stored on the offer as `amount_mismatch` with both values and counted in metrics; the offer is still marked paid.
4. The same `event_id` twice, a second event for the same order, and an event after the sweep already marked the offer each answer 200 and change the offer once; one thank you message is produced in total.
5. An event that matches no offer answers 200 with `matched: false` and writes only a counter.
6. The sweep, given `now`, reads through `get_status` every offer with a Draft Order that is `sent` and not expired by more than 7 days, at most once per hour per offer, and marks paid the ones Shopify reports completed with a paid order; it marks `expired` the offers past `valid_until` whose draft is still open.
7. Shopify 429 or 5xx during the sweep stops that sweep and leaves offers unchanged; the next run continues from the oldest unchecked offer.
8. A paid offer cancels its pending follow ups (story-16 reads the status), enqueues a lead update with status paid (story-14), and produces one fixed Romanian thank you text for the channel to deliver; no amount is restated unless it equals the stored total.
9. With the CRM event never arriving (bridge not built yet), the journey "offer sent, draft completed in Shopify" still ends as paid within one sweep interval; a test covers the sweep alone.
10. The request body is not logged; the log line has the offer id or `no_offer`, the order id, the source (`event` or `sweep`) and the outcome.

## Technical Notes

- The Draft Order carries the tag `ec-quote` and the order attributes the bridge names (`ec_quote_channel`, `ec_quote_key`, `ec_quote_valid_until`, `ec_quote_ad_source`); keep `ec_quote/integrations/shopify.py` and the bridge spec in step.
- The sweep runs in the FastAPI lifespan with the injected clock; its logic is a pure function over store rows plus `get_status`.
- Store only the order id, order name, total and timestamps; no customer data from the order.

## Dependencies

story-3 (offers ledger), story-10 (Draft Orders and their status). The CRM event is optional and arrives with EPIC-3.

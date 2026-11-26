---
id: story-24
title: "Paid order tracking: which offers became orders"
effort: MEDIUM
epic: EPIC-3
depends_on: [story-3, story-10]
shared_files: [ec_quote/integrations/shopify.py, ec_quote/api/main.py, ec_quote/agent/store.py]
track: full
models: {implementer: large, qa: standard, ui: none, review: large}
---

# story-24: Paid order tracking: which offers became orders

**Repository:** ec-quote · **Epic:** [EPIC-3](epic-3-measurement-and-tuning.md) · **Depends on:** story-3, story-10

## Summary

The measure that matters is how many offers become orders. Nothing tells ec-quote today that a payment link was paid: the calculator app subscribes to `orders/create`, `orders/fulfilled` and `orders/cancelled`, not `orders/paid`, and knows nothing about offers. ec-quote does not need a webhook for this. It created the Draft Orders, so it can ask Shopify for their status: a periodic sweep through `ShopifyCheckout.get_status` marks an offer paid when its draft was completed into a paid order, and expired when the validity passed. A paid offer stops its reminders and shows as paid in the panel when that chat is opened.

## User Story

As the owner, I want to know which offers were paid and how fast, and as a staff member I do not want to be reminded about an offer the customer already paid.

## Scope

**In:** `ec_quote/agent/orders.py` (new: `mark_paid`, the sweep as a pure function over store rows plus `get_status`); `ec_quote/integrations/shopify.py` (`get_status` as used by the sweep); `ec_quote/api/main.py` (periodic runner in the lifespan); `ec_quote/agent/store.py` (statuses); the suggestion for a chat whose offer is paid; `tests/agent/test_orders.py`, fixtures with invented orders.

**Out:** a Shopify webhook receiver in ec-quote; the CRM's paid order event (bridge spec section 7, optional, EPIC-4); refunds and cancellations (a follow-up); a thank you message sent to anyone (the panel may suggest one, a person sends).

## Acceptance Criteria

1. The sweep, given `now`, reads through `get_status` every offer with status `link_created` that is not past `valid_until` by more than 7 days, at most once per hour per offer, oldest check first.
2. An offer whose Draft Order is completed with a paid order becomes `paid` with the order id, the order name, the paid amount and the time; an offer past `valid_until` whose draft is still open becomes `expired`.
3. The paid amount is compared with the offer total; a difference is stored on the offer as `amount_mismatch` with both values and counted for the weekly report; the offer is still marked paid.
4. Marking paid is idempotent: two sweeps, or two processes sweeping at once, change the offer once.
5. Shopify 429 or 5xx stops that sweep and leaves offers unchanged; the next run continues from the oldest unchecked offer; a 401 stops the runner and is reported once in the health details.
6. A Draft Order deleted in Shopify by staff marks the offer `cancelled` with that reason; it is not retried forever.
7. A paid offer cancels its pending reminders (story-27 reads the status).
8. When `suggest` is called for a chat whose latest offer is paid and the customer has not written since, the suggestion is kind `reply` with a fixed short thank you text and a note for staff with the order name; it is offered once and not again after an outgoing message follows it.
9. The sweep stores only the order id, order name, total and timestamps; no customer data from the order; nothing from Shopify's response is logged beyond ids and outcome.
10. With `SHOPIFY_ADMIN_TOKEN` unset the runner does not start and health reports it as not configured.

## Technical Notes

- The sweep interval and the per offer minimum interval are technical settings in `ec_quote/config.py`.
- At the expected volume (a few offers a day) polling is cheap and needs no public endpoint; a push from the CRM can be added later without changing this code (`mark_paid` is the shared step).

## Dependencies

story-3 (offers ledger), story-10 (Draft Orders and their status).

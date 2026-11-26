---
id: story-10
title: "Draft Order checkout at the exact calculator price"
effort: HIGH
epic: EPIC-1
depends_on: [story-2]
shared_files: [ec_quote/integrations/shopify.py, ec_quote/integrations/errors.py]
track: full
models: {implementer: large, qa: standard, ui: none, review: large}
---

# story-10: Draft Order checkout at the exact calculator price

**Repository:** ec-quote · **Epic:** [EPIC-1](epic-1-price-and-offer.md) · **Depends on:** story-2

## Summary

When the customer says "vreau să comand", they get a Shopify payment link for exactly the offered amount. `ShopifyCheckout` in `ec_quote/integrations/shopify.py` already builds a Draft Order: one unit of the product's permanent variant, `priceOverride` equal to `PriceQuote.total`, the calculator's `properties` as line attributes, tags and a note. This story proves that against recorded Shopify responses, makes the call idempotent per offer, defines every failure, and adds the one live check that settles whether the shop's tax settings leave the total equal to the offer.

## User Story

As a customer, I want the link to charge exactly the price I was told, and as production I want the order to look like any order placed on the site.

## Scope

**In:** `ec_quote/integrations/shopify.py`, `ec_quote/integrations/errors.py`; `ec_quote/agent/tools.py` (`create_checkout` only from a stored, valid, approved offer); `tests/integrations/test_shopify_checkout.py`, `tests/integrations/fixtures/shopify/*.json` (recorded GraphQL responses with invented customers); `scripts/checkout_live_check.py` (by hand).

**Out:** order paid tracking (story-15); artwork upload (story-19 supplies `artwork_url`); discounts, shipping rules and invoicing, which stay as the shop has them.

## Acceptance Criteria

1. The Draft Order input for a quote has one line: the product's permanent variant (the first whose SKU or title is not a temporary `calc-*` variant), quantity 1, `priceOverride` amount equal to `PriceQuote.total` as a two decimal string in RON; `customAttributes` equal, in the same order and with the same names and values, to `PriceQuote.properties`; when `artwork_url` is given, the upload properties the site uses are added after them.
2. The created order's total returned by Shopify in the fixture equals `PriceQuote.total`; if the response total differs by any amount, `create_checkout` deletes the draft, raises `CheckoutTotalMismatch` with both values, no link is returned, and the engine hands off with the offer attached.
3. Idempotency: calling `create_checkout` twice for the same offer id returns the same `Checkout` and creates one Draft Order (the offer id is stored on the offer and sent as a tag; a second call finds the stored `draft_order_id`); a crash after creation and before the store write is recovered by looking the tag up.
4. Tags include the channel, `ec-quote`, the offer id and the ad source when present; the note has the validity date; phone is sent in E.164 or omitted when it cannot be normalized; no free text from the customer is placed in a tag.
5. `create_checkout` refuses, without any network call, an offer that is not stored, is expired, is over the handoff threshold, or (in shadow mode) is not approved.
6. Failures: a Shopify `userErrors` entry, HTTP 401, 429 with `Retry-After` (one retry after the stated delay through the injected sleeper), a 5xx (one retry), and a timeout each map to a named error; in every case the customer gets a fixed text without a link and staff get a handoff with the error code.
7. The product has no permanent variant: the fallback custom line is used with the product title and the same price and attributes, and the summary for staff says so.
8. The `invoice_url` returned is an `https` URL on the shop's domain or its checkout domain; anything else raises and no link is sent.
9. Secrets: the Admin token never appears in logs, errors or exceptions (`mask_key`); a test raises each error and scans its text.
10. `scripts/checkout_live_check.py` creates one Draft Order on the real shop for a test configuration, prints the offer total, the draft total and the tax lines, then deletes the draft; it refuses to run without `--i-understand-this-writes-to-the-shop`.

## Technical Notes

- Shopify Admin GraphQL `draftOrderCreate` with `priceOverride` on the line; use the API version the calculator app uses and state it in one constant.
- On the site a calculator line is 1 unit of a per configuration variant priced at the calculated total with VAT included; this keeps the same shape without creating variants.
- Whether the shop has taxes included in prices decides criterion 2 in production; the live check is the proof and its output goes in the pull request.

## Hand-over

Owner: the custom app token with `write_draft_orders`, `read_products`, `read_orders`; one run of the live check before launch.

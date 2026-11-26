---
id: story-10
title: "Payment link on one click: Draft Order at the exact calculator price"
effort: HIGH
epic: EPIC-1
depends_on: [story-2, story-9]
shared_files: [ec_quote/integrations/shopify.py, ec_quote/integrations/errors.py, ec_quote/api/app.py]
track: full
models: {implementer: large, qa: standard, ui: none, review: large}
---

# story-10: Payment link on one click: Draft Order at the exact calculator price

**Repository:** ec-quote · **Epic:** [EPIC-1](epic-1-assisted-quoting-in-the-extension.md) · **Depends on:** story-2, story-9

## Summary

When the customer agrees, the staff member clicks "Link de plată" in the panel. `POST /v1/assist/suggestions/{id}/payment-link` calls `AssistEngine.create_payment_link`, which creates a Shopify Draft Order for exactly the offered amount and returns the reply text with the link, ready to insert. `ShopifyCheckout` in `ec_quote/integrations/shopify.py` already builds the Draft Order: one unit of the product's permanent variant, `priceOverride` equal to `PriceQuote.total`, the calculator's `properties` as line attributes, tags and a note. This story proves that against recorded Shopify responses, makes the click idempotent, defines every failure, and adds the one live check that settles whether the shop's tax settings leave the total equal to the offer. The link is created only by a person's click, never by `suggest`.

## User Story

As a staff member, I want one click to give me a payment link for exactly the price I offered, and as production I want the order to look like any order placed on the site.

## Scope

**In:** `ec_quote/integrations/shopify.py`, `ec_quote/integrations/errors.py`; the `create_payment_link` path in `ec_quote/agent/`; `ec_quote/api/app.py` and `schemas.py` (the route, its errors); `ec_quote/agent/offer.py` (the reply text with the link); `tests/integrations/test_shopify_checkout.py`, `tests/integrations/fixtures/shopify/*.json` (recorded GraphQL responses with invented customers), `tests/api/test_payment_link.py`; `scripts/checkout_live_check.py` (by hand).

**Out:** paid order tracking (story-24); artwork upload (story-16 supplies `artwork_url`); discounts, shipping rules and invoicing, which stay as the shop has them; several lines in one order (a follow-up).

## Acceptance Criteria

1. The Draft Order input for an offer has one line: the product's permanent variant (the first that is not a temporary `calc-*` variant), quantity 1, `priceOverride` equal to `PriceQuote.total` as a two decimal string in RON; `customAttributes` equal, in the same order and with the same names and values, to `PriceQuote.properties`; when an artwork URL is stored, the upload properties the site uses are added after them.
2. The Draft Order total returned by Shopify equals `PriceQuote.total`; if it differs by any amount, the draft is deleted, the route answers 409 `checkout_total_mismatch` with both values for the panel to show, and no link is returned.
3. Idempotency: a second click, a click from the other staff member's browser and a retry after a timeout for the same suggestion all return the same `payment_url` and one Draft Order exists (the offer id is stored and sent as a tag; a crash after creation and before the store write is recovered by looking the tag up).
4. The route answers 404 for an unknown suggestion, 409 `not_an_offer` for a suggestion that is not an offer or has `can_create_payment_link` false, 409 `offer_expired` past `valid_until`; none of these calls Shopify.
5. The quantity for the link is the highlighted line of the offer; a request body may name another quantity only if it is one of the offer's lines, and the price used is that line's stored calculator price.
6. The staff member from the token is recorded on the offer and written in the Draft Order note; tags include `ec-quote`, the channel, the offer id; the customer's phone is sent in E.164 or omitted when it cannot be normalized; no free text from the customer is placed in a tag.
7. The response is the `AssistSuggestion` with `payment_url` set and `text` equal to the fixed Romanian reply containing the link, the total with VAT and the validity date; the only amount in it is the stored total. If `edited_text` is sent, it is stored for the metrics and the returned text is the fixed reply; the guard does not rewrite a person's text.
8. Failures: a Shopify `userErrors` entry, HTTP 401, 429 with `Retry-After` (one retry after the stated delay through the injected sleeper), a 5xx (one retry) and a timeout each map to a named error code the panel can show in Romanian; no link is returned and the offer stays available for another click.
9. The product has no permanent variant: the fallback custom line is used with the product title and the same price and attributes, and `note_for_staff` says so.
10. `payment_url` is an `https` URL on the shop's domain or its checkout domain; anything else is an error and no link is returned.
11. The Admin token never appears in logs, errors or exceptions (`mask_key`); a test raises each error and scans its text. The payment URL is not logged.
12. `scripts/checkout_live_check.py` creates one Draft Order on the real shop for a test configuration, prints the offer total, the draft total and the tax lines, then deletes the draft; it refuses to run without `--i-understand-this-writes-to-the-shop`.

## Technical Notes

- Shopify Admin GraphQL `draftOrderCreate` with `priceOverride` on the line; use the API version the calculator app uses, in one constant.
- On the site a calculator line is 1 unit of a per configuration variant priced at the calculated total with VAT included; this keeps the same shape without creating variants.
- Whether the shop has taxes included in prices decides criterion 2 in production; the live check is the proof and its output goes in the pull request.

## Hand-over

Owner: the custom app token with `write_draft_orders`, `read_products`, `read_orders`; one run of the live check before real use.

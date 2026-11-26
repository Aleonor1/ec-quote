---
id: story-9
title: "Offer suggestion as text: price, tiers and validity"
effort: MEDIUM
epic: EPIC-1
depends_on: [story-2]
shared_files: [ec_quote/agent/offer.py, ec_quote/mockup/formatting.py, ec_quote/contracts.py]
track: full
models: {implementer: standard, qa: standard, ui: none, review: standard}
---

# story-9: Offer suggestion as text: price, tiers and validity

**Repository:** ec-quote · **Epic:** [EPIC-1](epic-1-assisted-quoting-in-the-extension.md) · **Depends on:** story-2

## Summary

When everything needed for a price is known, the suggestion is an offer: the requested quantity, the next quantity tiers that make the unit price drop, each total without and with VAT, the production term, and the date until which the price holds. The scaffold composes texts with numbers in `ec_quote/agent/offer.py`. This story makes the offer one object built by code from stored calculator answers, returned both as structured `offer_lines` (for the panel to show as a table) and as a ready to send WhatsApp text, in Romanian, with every amount formatted by one function. Images come in EPIC-2.

## User Story

As a staff member, I want an offer I can send as it is: what the customer pays for the quantity asked, how much cheaper the piece gets at the next quantities, and until when the price holds.

## Scope

**In:** `ec_quote/agent/offer.py` (one `Offer` built from `PriceQuote`, the `TierOffer` list, `Rules` and `now`; the offer text; the mapping to `AssistSuggestion.offer_lines`); `ec_quote/mockup/formatting.py` (the one money, quantity and date formatter); `tests/agent/test_offer.py`.

**Out:** the offer image and mockup (story-18); the payment link (story-10); how the panel draws the table (story-12); reminders (story-27).

## Acceptance Criteria

1. An `Offer` has: the requested line, up to `upsell_tier_count` tier lines in ascending quantity, `valid_until` = `now` plus `offer_validity_days` at 23:59 Europe/Bucharest, the production term from `Rules.production_term(urgent)`, and the choices in words (product, material, shape, size, options). With fewer tiers above the requested quantity it has fewer lines; at `quantity.max` only the requested line.
2. Every amount in the offer is copied from a stored `PriceQuote` or `TierOffer`; the builder performs no arithmetic on money. A saving per piece, if shown, is the difference of two calculator unit prices, marked as derived and omitted if either is missing.
3. Money is formatted `1.234,50 lei` and quantities `1.000 buc` by one function used for the text and later for the image; a test pins 0, 0.5, 999.99, 1000, 1234567.89.
4. `offer_lines` in the suggestion has one `OfferLine` per quantity with `total_ex_vat`, `total` and `unit_price` as returned by the calculator; the requested line is first and `highlighted`.
5. The offer text is pinned exactly by a test for a fixture offer: the choices in one line, one line per quantity with the total without VAT and with VAT and the unit price, the production term, "Ofertă valabilă până la <date>". No em dash, no emoji, no signature, under 900 characters, plain text with line breaks that WhatsApp keeps.
6. With the production term undecided (`OpenDecision`), the text has no term line, `note_for_staff` says the term is not configured, and nothing else fails.
7. `can_create_payment_link` is true exactly when the offer is inside the rules (not `needs_human`), not expired, and priced for a single line; otherwise false with the reason in `note_for_staff`.
8. Building the same offer twice gives byte identical text and equal `offer_lines`.
9. An offer whose `valid_until` has passed is not returned again: the next `suggest` re-prices with the calculator and builds a new offer, and `note_for_staff` says the earlier offer expired and whether the price changed (asserted with a fixed clock).
10. When the customer's message selects one of the offered quantities ("rămâne 1000"), the next suggestion is an offer whose highlighted line is that quantity, priced by its own calculator call, with `can_create_payment_link` true.

## Technical Notes

- The validity cut at end of day avoids "valid until 14:37".
- The text is what a person will send under their own name: no "sunt asistentul automat" line (story-8 criterion 6).
- If `AssistSuggestion` needs a field the contract lacks (for example `valid_until`), add it to `ec_quote/contracts.py` here and say so in the pull request.

## Hand-over

Owner: the production term texts (EPIC-0 D3) and confirmation of the offer wording on one example.

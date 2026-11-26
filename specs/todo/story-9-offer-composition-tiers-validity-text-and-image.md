---
id: story-9
title: "Offer composition: tiers, validity, text and image"
effort: MEDIUM
epic: EPIC-1
depends_on: [story-2]
shared_files: [ec_quote/mockup/compose.py, ec_quote/mockup/formatting.py, ec_quote/api/texts.py]
track: full
models: {implementer: standard, qa: standard, ui: none, review: standard}
---

# story-9: Offer composition: tiers, validity, text and image

**Repository:** ec-quote · **Epic:** [EPIC-1](epic-1-price-and-offer.md) · **Depends on:** story-2

## Summary

An offer is what the customer judges the whole service by. It has the requested quantity, the next quantity tiers that make the unit price drop, each total without and with VAT, the production term, the date until which it is valid, and one button to order. The mockup module already draws an offer image (`make_offer_image`) and the engine already asks for tiers. This story makes the offer one object built by code from stored quotes, rendered identically as text (for channels or clients without images) and as an image, in Romanian, with every amount formatted by one function.

## User Story

As a customer, I want to see at a glance what I pay for the quantity I asked and how much cheaper the piece gets if I order more, and until when the price holds.

## Scope

**In:** `ec_quote/agent/offer.py` (new: `Offer` built from `PriceQuote`, `TierOffer` list, `Rules`, `now`); `ec_quote/mockup/formatting.py` (the one money and date formatter); `ec_quote/mockup/compose.py` and `ec_quote/mockup/service.py` (`make_offer_image` takes the `Offer` lines); `ec_quote/api/texts.py` (offer text template, button titles); `tests/agent/test_offer.py`, `tests/mockup/test_offer_image.py`.

**Out:** the mockup on a photo (story-20); the checkout (story-10); follow up texts (story-16).

## Acceptance Criteria

1. An `Offer` has: the requested line, up to `upsell_tier_count` tier lines in ascending quantity, `valid_until` = `now` plus `offer_validity_days` at 23:59 Europe/Bucharest, the production term from `Rules.production_term(urgent)`, and the choices in words (product, material, shape, size, options). With fewer tiers available above the requested quantity, it has fewer lines; at `quantity.max` it has only the requested line.
2. Every amount in the offer is copied from a stored `PriceQuote` or `TierOffer`; the builder performs no arithmetic on money except the saving per piece shown as the difference of two calculator unit prices, which is marked as derived and is not shown if either is missing.
3. Money is formatted `1.234,50 lei` and quantities `1.000 buc` by one function used by the text and the image; a test pins 0, 0.5, 999.99, 1000, 1234567.89.
4. The offer text is pinned exactly by a test for a fixture offer: one line per quantity with the total without VAT and with VAT, the unit price, the production term, "Ofertă valabilă până la <date>", and the choices. No em dash, no emoji, under 1000 characters.
5. With the production term undecided (`OpenDecision`), the offer has no term line in text or image and nothing else fails.
6. The offer image is a PNG of fixed width, at most 1 MB, whose text regions contain, verified by rendering with known fonts and comparing against a golden image with a tolerance: each quantity and total, the validity date, the brand name. Romanian diacritics render (a test draws "ă â î ș ț" and finds no missing glyph box).
7. Without a mockup (`mockup_path` is `None`) the image is the price table alone, same width; with one, the mockup is on top and the table below.
8. The requested line is highlighted (`highlighted=True`) and is the first line; the actions for an offer are, in order: `image` (the offer image), `text` (the offer text), `buttons` with "Vreau să comand" and "Am o întrebare", each title at most 20 characters.
9. Building the same offer twice gives byte identical text and an identical `Offer` object; the image is deterministic on the same platform.
10. An offer whose `valid_until` has passed cannot be approved or checked out; the engine re-prices and builds a new offer instead (asserted with a fixed clock).

## Technical Notes

- The validity cut at end of day avoids "valid until 14:37".
- Fonts are the bundled DejaVu files in `ec_quote/mockup/fonts/`; no system font lookup.
- Brand colours and logo are assets under `templates/brand/`; if absent the image uses neutral defaults (owner hand-over).

## Hand-over

Owner: logo file and brand colours for the offer image; confirmation of the offer wording.

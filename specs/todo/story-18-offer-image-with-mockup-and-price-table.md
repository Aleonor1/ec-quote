---
id: story-18
title: "Offer image: mockup and price table in one picture"
effort: MEDIUM
epic: EPIC-2
depends_on: [story-9, story-17]
shared_files: [ec_quote/mockup/offer.py, ec_quote/mockup/service.py, ec_quote/api/app.py, ec_quote/contracts.py]
track: full
models: {implementer: standard, qa: standard, ui: none, review: standard}
---

# story-18: Offer image: mockup and price table in one picture

**Repository:** ec-quote · **Epic:** [EPIC-2](epic-2-file-mockup-and-offer-image.md) · **Depends on:** story-9 (the `Offer`), story-17 (real templates)

## Summary

The plan's offer is one picture a customer can forward: their design on a product, and under it the price table with the validity. `ec_quote/mockup/offer.py` already draws that image (1080x1350) from `OfferLine`s. This story makes it part of the offer suggestion: built from the same `Offer` object as the text, so the two can never disagree, stored where the extension can fetch it with the staff token, and returned in the suggestion for the staff member to attach.

## User Story

As a staff member, I want the offer as one clean picture next to the text, so that the customer sees their label and the price together.

## Scope

**In:** `ec_quote/mockup/offer.py`, `ec_quote/mockup/service.py` (`make_offer_image` from the `Offer`); `ec_quote/agent/` (the suggestion's image, rebuilt when the offer or the file changes); `ec_quote/api/app.py` and `schemas.py` (the suggestion carries an image URL the extension can fetch with the assist token; the image route); `templates/brand/` (logo, colours); `tests/mockup/test_offer.py`, `tests/api/test_assist_image.py`.

**Out:** attaching the image in WhatsApp Web (story-20); the photo templates (story-17); the cut line (story-22).

## Acceptance Criteria

1. The image is a PNG of 1080x1350, at most 1 MB, built only from the `Offer` of story-9: each quantity with its total without VAT and with VAT and its unit price, the validity date, the production term when configured, the brand name; the amounts come through the same formatter as the text.
2. For a fixture offer the rendered image matches a golden image within a tolerance, and Romanian diacritics render (a test draws "ă â î ș ț" and finds no missing glyph box).
3. With a mockup available the mockup is on top and the table below; without one (no file yet, or `make_mockup` failed) the image is the price table alone in the same size and `note_for_staff` says there is no mockup.
4. The requested line is visually highlighted and first; no line, amount or date appears in the image that is not in the suggestion's `offer_lines` and text (asserted by comparing the strings passed to the drawing code with the `Offer`).
5. A `needs_human` suggestion has no offer image, also when an offer was computed for staff to see.
6. The suggestion returns the image as a URL on the backend; fetching it requires a valid assist token; the URL carries an unguessable id, contains no file system path, and an unknown or expired id answers 404. The optional `/v1/media/{token}` route of the site chat is not used for this.
7. The image is rebuilt when the offer's lines, the validity or the customer's file change, and reused otherwise (same bytes, no second render) when `suggest` is called again.
8. The image has no metadata from the customer's file and none identifying the staff member.
9. A rendering failure never fails `suggest`: the suggestion is returned with text and `offer_lines`, without an image, with a note for staff.
10. With no logo or colours under `templates/brand/`, neutral defaults are used and the image is still produced.

## Technical Notes

- Fonts are the bundled DejaVu files; no system font lookup.
- `AssistSuggestion.image_path` stays internal; the API maps it to the fetchable URL. If the contract needs an `image_url` field, add it here and say so in the pull request.
- Image files live under `EC_QUOTE_DATA_DIR` and fall under the retention rule of story-13.

## Hand-over

Owner: logo file and brand colours; a look at one sample image.

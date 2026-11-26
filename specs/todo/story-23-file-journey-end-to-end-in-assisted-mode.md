---
id: story-23
title: "The file journey end to end in assisted mode"
effort: MEDIUM
epic: EPIC-2
depends_on: [story-15, story-16, story-17, story-18, story-19, story-20, story-22]
shared_files: [tests/fakes.py, ec_quote/agent/model.py, ec_quote/agent/tools.py, ec_quote/agent/offer.py]
track: full
models: {implementer: standard, qa: standard, ui: standard, review: standard}
---

# story-23: The file journey end to end in assisted mode

**Repository:** ec-quote (backend and `extension/`) · **Epic:** [EPIC-2](epic-2-file-mockup-and-offer-image.md) · **Depends on:** story-15, story-16, story-17, story-18, story-19, story-20, story-22

## Summary

Each piece of the file path was hardened on its own: the check, the storage, the templates, the offer image, the attachment upload, the image attach, the cut line. This story proves them together the way the staff will use them, and fixes the seams: a customer sends a logo and says what they need, in any order; the staff member clicks once to check the file; the panel shows an offer with the mockup; one click attaches the picture, one click makes the payment link. Two test layers: the backend through the assist routes with the real file checker, mockup service and templates; and the extension on the fixture page against that backend with fakes for the outside world.

## User Story

As a staff member, I want the whole path from "here is my logo" to "here is your offer and the link" to work in whatever order the customer writes.

## Scope

**In:** `tests/e2e/test_assist_file_journeys.py` (through `/v1/assist/suggest`, `/v1/assist/upload`, the payment link route; fakes for the model, calculator, storage, cut line and Shopify); `tests/fakes.py` (fake storage and cut line); `extension/test/journey.test.js` (fixture page plus a local backend with fakes); fixes in `ec_quote/agent/` and `extension/` where a journey fails; `tests/evals/conversations/files-*.json` (added to the evaluation set of story-8).

**Out:** any new capability not needed for the journeys below; premium mockups; the site chat.

## Acceptance Criteria

1. Good file: with the request and the material known, uploading a transparent 300 DPI PNG and calling `suggest` returns kind `offer` with an image URL whose image has the mockup above the price table; the file was checked once at the requested size, stored once, and the cut line requested once.
2. File first: a file uploaded before any size is known answers `pending_size`; no DPI verdict is stated; when the customer gives the size, the next `suggest` runs the check without a new upload.
3. Size changes: after an offer for 5 by 5 cm, the customer asking for 10 by 10 cm leads to a new check at the new size, a new price and a new offer and image; if the file is now `weak` the note appears; the old offer can no longer get a payment link (409).
4. Weak file: the suggestion is still an offer; its text has the fixed weak sentence and `note_for_staff` the technical facts.
5. Unusable file: the suggestion is a reply asking for another file with the reason, without image; a second unusable file in a row (`max_file_attempts` from the rules fixture) gives `needs_human` with reason `file_unusable`; a good file in between resets the count.
6. New file after the offer: the mockup and offer image are rebuilt with the same stored price; no calculator call is made when the choices did not change.
7. PDF: a vector PDF gives a report that includes the remote inspection and a mockup from page 1; a 3 page PDF adds the sentence that the first page is used.
8. Hostile file: the HTML named `.png` and the oversized image of story-15's corpus each give the unusable sentence; no storage upload, no cut line call, no mockup, no exception.
9. Storage down: the offer and image are produced; `note_for_staff` says the customer's file was not stored and must be attached to the order by hand; the Draft Order from the payment link has no artwork attribute.
10. Cut line preview: with the cut line route unavailable the mockup has the outline without cut line styling and the text has the indicative sentence; with the route available the text has the cut line sentence.
11. Payment link after a file journey: the link reply's only amount is the stored total; the Draft Order input carries the stored artwork URL of the last usable file.
12. Extension layer, on the fixture page: check file click, the offer with its image in the panel, attach image leading to the page's media preview with the caption, payment link click leading to the reply in the composer; at no step is anything sent, and after the journey the extension's stores hold only the address, token and switch.
13. In every journey, each amount in each suggestion equals a `FakeCalculator` amount, and the log scan of story-4 finds no file name, URL or contact data.
14. Timing: the recorded timestamps show the offer suggestion ready within the plan's 5 minute target from the customer's last message, with the injected clock advanced by realistic tool latencies; the backend part of journey 1 completes in under 5 seconds of wall time with fakes.

## UI Notes

The epic's UI journey is criterion 12; the UI test session runs it in a real Chromium with the unpacked extension, the fixture page and a local backend.

## Technical Notes

- Use the real templates of story-17; assert on structure (image size, that the mockup region differs from the bare template photo, that the strings drawn equal the offer), not on bytes.
- A journey that needs a behaviour no earlier story specified is a finding: stop and write the follow-up spec instead of deciding it here.

## Dependencies

All other stories of EPIC-2 except story-21, whose contract story-22 replays from a fixture.

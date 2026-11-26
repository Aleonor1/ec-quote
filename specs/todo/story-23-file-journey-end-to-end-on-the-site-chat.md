---
id: story-23
title: "The file journey end to end on the site chat"
effort: MEDIUM
epic: EPIC-2
depends_on: [story-11, story-18, story-19, story-20, story-22]
shared_files: [tests/fakes.py, ec_quote/agent/model.py, ec_quote/agent/tools.py, ec_quote/api/texts.py]
track: full
models: {implementer: standard, qa: standard, ui: none, review: standard}
---

# story-23: The file journey end to end on the site chat

**Repository:** ec-quote · **Epic:** [EPIC-2](epic-2-file-and-mockup.md) · **Depends on:** story-11, story-18, story-19, story-20, story-22

## Summary

Each piece of the file path was hardened on its own: the check, the storage, the templates, the cut line. This story proves them together through the site chat API, the way a visitor would use them, and fixes the seams. A customer sends a file with or before the request and gets back one image with the mockup and the price; a weak file gets an honest note; an unusable one gets a clear request and, the second time, a person. The order of events must not matter: file first, size first, or a new file after the offer.

## User Story

As a visitor, I want to send my logo and say what I need in any order and get one picture with my label on a product and the price under it.

## Scope

**In:** `tests/e2e/test_file_journeys.py` (through `POST /v1/chat/message` and `POST /v1/chat/upload` with fakes for the model, calculator, storage, cut line and Shopify, and the real `FileChecker`, mockup service and templates); `tests/fakes.py` (fake storage and cut line); fixes in `ec_quote/agent/model.py`, `ec_quote/agent/tools.py`, `ec_quote/api/texts.py` where a journey fails; `tests/evals/conversations/files-*.json` (added to the evaluation set of story-8).

**Out:** WhatsApp media (EPIC-3); premium mockups; any new capability not needed for the journeys below.

## Acceptance Criteria

1. Good file: a message with the request and an uploaded transparent 300 DPI PNG returns, after the clarifying answer, an `image` action whose image contains the mockup above the price table, then the offer text and buttons. The file was uploaded once, checked once at the requested size, and the cut line requested once.
2. File first: a file sent before any size is acknowledged and stored; no DPI verdict is stated until a size is known; when the size arrives the check runs without asking for the file again.
3. Size changes: after an offer for 5 by 5 cm, asking for 10 by 10 cm re-runs the check at the new size, re-prices, and builds a new offer; if the file is now `weak` the note appears; the old offer is superseded and cannot be approved or paid through a new link.
4. Weak file: the reply has the fixed weak sentence for the problem codes, the offer is still produced, and the buttons include sending a better file.
5. Unusable file: the reply has the fixed sentence with what to send instead and no mockup; a second unusable file in a row (`max_file_attempts` from the rules fixture) ends with a `handoff` action with reason `file_unusable`; a good file in between resets the count.
6. New file after the offer: the mockup and offer image are rebuilt with the same stored price; no new calculator call is made when the choices did not change.
7. PDF: a vector PDF gives a report that includes the remote inspection, and a mockup rendered from page 1; a 3 page PDF gives the sentence that the first page is used.
8. Hostile file: the HTML named `.png` and the oversized image of story-18's corpus each give the unusable sentence; no upload, no cut line call, no mockup, no exception; the conversation continues.
9. Storage down: the offer is sent with the price table image served by the media token URL and the note for staff says the file could not be stored; the Draft Order has no artwork attribute and the handoff summary says so.
10. Cut line preview: with the cut line route unavailable the mockup has the outline without cut line styling and the text has the indicative sentence; with the route available the text has the cut line sentence.
11. Shadow mode: with `shadow_mode` true each of the journeys that end in an offer ends in `pending_approval`, and approval returns the same image and text.
12. Timing: with fakes, the journey of criterion 1 completes in under 5 seconds of wall time in the suite, and the recorded timestamps show the offer ready under the plan's 5 minute target with the injected clock advanced by realistic tool latencies.
13. In every journey, each amount in each outbound action equals a `FakeCalculator` amount, and the log scan of story-4 finds no file name, URL or contact data.

## Technical Notes

- Use the real templates of story-20; assert on structure (image size, that the mockup region differs from the bare template photo, that the table region contains the totals when rendered with the bundled fonts), not on bytes.
- A journey that needs a behaviour not specified by an earlier story is a finding: stop and write the follow-up spec instead of deciding it here.

## Dependencies

story-11 (site chat API), story-18, story-19, story-20, story-22.

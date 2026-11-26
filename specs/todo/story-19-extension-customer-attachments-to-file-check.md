---
id: story-19
title: "Extension: customer attachments from WhatsApp Web to the file check"
effort: HIGH
epic: EPIC-2
depends_on: [story-12, story-13, story-15]
shared_files: [extension/content/selectors.js, extension/background/api-client.js, ec_quote/api/app.py, ec_quote/contracts.py]
track: full
models: {implementer: large, qa: standard, ui: standard, review: large}
---

# story-19: Extension: customer attachments from WhatsApp Web to the file check

**Repository:** ec-quote (`extension/` and backend) · **Epic:** [EPIC-2](epic-2-file-mockup-and-offer-image.md) · **Depends on:** story-12, story-13, story-15

## Summary

Customers send their artwork in the chat as a photo or a document. To check it and build a mockup, the backend needs the file itself. The reader of story-11 already reports that a message has an attachment and its kind; this story gets the bytes: when the staff member clicks "Verifică fișierul" next to an attachment in the panel, the extension obtains that one file from the page and posts it to `POST /v1/assist/upload`; the backend stores it for the conversation, runs `check_file` at the requested size when it is known, and the next suggestion includes the verdict in plain words. Files are sent only on that click, one at a time.

## User Story

As a staff member, I want to check the customer's file with one click in the chat, instead of downloading it, opening it and measuring it myself.

## Scope

**In:** `extension/content/attachments.js` (obtain the bytes of one attachment of the open chat, through the selector map); `extension/content/selectors.js` (attachment entries); `extension/background/api-client.js` (multipart upload); `extension/panel/` (the attachment list, the check button, the verdict); `extension/test/attachments.test.js`, fixtures; backend: `ec_quote/api/app.py` and `schemas.py` (`POST /v1/assist/upload`: token, limits, type from bytes, link to the contact and message id), the engine's use of uploaded files in `suggest`, the staff note and suggested sentence per verdict; `tests/api/test_assist_upload.py`, `tests/e2e/test_assist_file.py`.

**Out:** the file check itself (story-15); storage in R2 and PDF inspection (story-16); the mockup and image (story-17, story-18); sending files automatically or in the background; voice notes, videos and stickers.

## Acceptance Criteria

1. The panel lists the attachments of incoming messages in the open chat (kind, file name when shown, the message they belong to) with a "Verifică fișierul" button each; nothing is fetched or uploaded until a button is clicked.
2. On click, the extension obtains that attachment's bytes from the page and uploads them with the contact key and the message id; images at the full resolution WhatsApp Web makes available for download, not the blurred thumbnail; the panel shows progress and the result.
3. If the page has not loaded the full file (WhatsApp shows a download arrow), the panel tells the person to click the file once in WhatsApp and try again; the extension does not click it for them.
4. The upload request goes only to the configured backend with the assist token and contains only the file, its name, the contact key and the message id; a file over the configured size is refused in the extension with a Romanian message before any upload.
5. Backend: `POST /v1/assist/upload` requires a valid token, decides the type from the bytes (`ec_quote/files/sniff.py`), refuses a type outside the allowed set with 415 and a size over the limit with 413, stores the file under the conversation with a generated name, and is idempotent on (contact, message id): a second upload of the same message returns the first result.
6. The response has the file's id and, when a size is already known for the conversation, the `FileReport` verdict and problem codes; when no size is known yet, `pending_size`, and the check runs as soon as a later `suggest` knows the size, without a new upload.
7. The next suggestion reflects the file: for `ok`, a short confirmation the person can send; for `weak`, the plain sentence about the visible effect, and the offer still available; for `unusable`, the sentence saying what to send instead; the count of consecutive unusable files feeds story-7's rule. `note_for_staff` carries the technical facts (pixels, DPI at size, colour mode).
8. A WhatsApp photo is recompressed by WhatsApp; when the uploaded file is a JPEG image attachment (not a document), `note_for_staff` says that a file sent "as document" keeps its quality, and the suggested text asks for it that way when the verdict is `weak` or `unusable`.
9. A changed selector for attachments yields the state "nu pot citi atașamentele" naming the failed entry, and text suggestions keep working.
10. The extension keeps no copy of the file after the upload finishes or fails (no blob URL left, nothing in any storage); a test checks object URL revocation and the stores.
11. Hostile inputs do not break either side: an HTML file named `.png`, a zero byte file and an oversized image each produce an `unusable` report with a stable code; the panel shows it as text.
12. Tests cover the extension against page fixtures with an image, a document and a not yet downloaded file, and the backend route with the fake engine; none needs WhatsApp.

## UI Notes

Attachment rows sit above the suggestion: icon by kind, name, button, then verdict as a coloured word with one line of explanation. States: idle, obtaining, uploading, checked, cannot obtain, too large. The UI test session uses the fixture page and a fake backend.

## Technical Notes

- How WhatsApp Web exposes the media of a message (an already decrypted blob in the page for viewed media, or a download it performs on click) is not documented and may change; the approach, its selector entries and its failure state are confined to `attachments.js` and the map. If obtaining the bytes proves impossible without clicking WhatsApp's own controls, the fallback is the person saving the file and dropping it on the panel, which this story must also support.
- The drop target on the panel is therefore part of this story: a dropped or picked file goes through the same upload with the open chat's contact and no message id.
- Uploaded files fall under the retention rule of story-13.

## Hand-over

Staff: one real conversation with a photo and one with a PDF sent as a document, for capturing fixtures.

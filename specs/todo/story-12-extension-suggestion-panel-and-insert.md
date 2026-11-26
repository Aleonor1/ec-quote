---
id: story-12
title: "Extension: suggestion panel, insert into the composer, payment link"
effort: HIGH
epic: EPIC-1
depends_on: [story-2, story-11]
shared_files: [extension/manifest.json, extension/content/selectors.js]
track: full
models: {implementer: large, qa: standard, ui: standard, review: large}
---

# story-12: Extension: suggestion panel, insert into the composer, payment link

**Repository:** ec-quote (`extension/`) · **Epic:** [EPIC-1](epic-1-assisted-quoting-in-the-extension.md) · **Depends on:** story-2 (the assist API), story-11 (the reader)

## Summary

This is what the staff see. Next to the open WhatsApp chat, a panel shows the backend's current suggestion: a question to ask, a reply, an offer with its price table, or "this one is yours" with the reason. One click inserts the suggested text into WhatsApp's message box, where the person can edit it and press Send themselves. For an offer, one more click asks the backend for the payment link and inserts the reply that contains it. The service worker is the only part that talks to the backend (`POST /v1/assist/suggest`, `POST /v1/assist/suggestions/{id}/payment-link`, `GET /v1/assist/ping`). The extension never presses Send.

## User Story

As a staff member answering on WhatsApp Web, I want the answer with the right price already written next to the chat, so that I only read it, adjust it and send it.

## Scope

**In:** `extension/background/service-worker.js`, `api-client.js`, `coordinator.js` (backend client, request queue, errors; the scaffold's files are the starting point); `extension/panel/` (panel markup, script, styles; a Chrome side panel or a panel injected beside the chat, chosen in the pull request with the reason); `extension/content/composer.js` (insert text into the composer through the selector map); `extension/shared/messages.js` (message shapes between content script, panel and worker, validated); `extension/content/selectors.js` (composer entries); `extension/test/panel.test.js`, `composer.test.js`, `service-worker.test.js`, a fake backend for tests.

**Out:** the options page and token storage rules (story-13); packaging (story-14); attachments and images (story-19, story-20); reminders (story-27); any click on Send or any other WhatsApp control.

## Acceptance Criteria

1. When the reader reports a readable one to one chat, the worker posts the contact and messages to `/v1/assist/suggest` with `X-EcQuote-Assist-Token` and the panel shows the returned suggestion; a new incoming message triggers a new request after a debounce; switching chats cancels the pending request and never shows chat A's suggestion on chat B (asserted with delayed fake responses).
2. Each kind renders distinctly: `question` and `reply` show the text and the `options`; `offer` shows the text and a table from `offer_lines` (quantity, total without VAT, total with VAT, unit price, the highlighted line marked) with amounts displayed exactly as received; `needs_human` shows `note_for_staff` and the reason, with no insert button when `text` is empty; `none` shows a quiet "nimic de sugerat".
3. `note_for_staff` is always shown apart from the customer text, visibly marked as not for the customer, and is never inserted.
4. "Inserează" puts the suggestion's text into WhatsApp's composer and focuses it; the composer's content equals the text including line breaks; nothing is sent. If the composer already has text typed by the person, the click asks before replacing it.
5. The extension contains no code path that clicks the send button, dispatches Enter to the composer or calls any WhatsApp internal function; a test scans `extension/` outside `test/` for the send selector and for synthetic Enter key events and finds none, and the selector map has no entry for the send button.
6. For an offer with `can_create_payment_link`, "Link de plată" calls the payment link route once (the button is disabled while waiting), shows the returned text with the link, and offers "Inserează"; a second click returns the same link. Without `can_create_payment_link` the button is absent.
7. Backend errors are shown in Romanian without codes or stack traces: 401 "token invalid, verificați setările", 409 `checkout_total_mismatch` with both amounts, 409 `offer_expired` with a "recalculează" action, 429 with the wait time, network failure or 5xx with a retry button. A failed request never shows a stale suggestion as current.
8. Reader states from story-11 are shown as plain messages and stop requests: no chat open, group chat, cannot read (with the failed entry and a link to the self-test), contact number unavailable (with the instruction to open the contact info).
9. The panel has an on and off switch; when off, or when the panel is closed, the content script does not read and the worker makes no request.
10. Text from the backend and from the page is rendered as text; a suggestion or message containing `<script>` or an `onerror` attribute displays as characters and executes nothing.
11. The panel shows who is signed in (the staff name from `ping`) and the backend's reachability; a version mismatch reported by `ping` shows "actualizați extensia".
12. Keyboard: the insert and payment link actions are reachable by keyboard and have visible focus; the panel does not take focus away from WhatsApp's composer except on the person's click.
13. All visible strings are Romanian, from one strings file, without em dashes or emojis.
14. Tests cover the worker against a fake backend, the panel against fixture suggestions of every kind, and the composer insert against the page fixtures of story-11; none needs WhatsApp or the real backend.

## UI Notes

- Narrow column (about 320 px) beside the chat; states: off, no chat, reading, waiting for the backend, suggestion of each kind, error, cannot read.
- The offer table must fit without horizontal scroll; amounts right aligned.
- The UI test session runs the unpacked extension against a local page built from the fixtures and a fake backend.

## Technical Notes

- WhatsApp's composer is a rich text field; inserting through the browser's input path (a paste or `insertText` style input event on the focused field) keeps WhatsApp's own state in step. Setting `textContent` directly does not. The method lives in `composer.js` and its selector in the map.
- Manifest V3 service workers stop when idle: keep no state in memory that matters; the open chat's data lives in the content script and the panel, and is dropped on chat change.
- The content script never receives the token; it sends the conversation to the worker, which adds the header.

## Hand-over

None beyond a backend address and tokens (story-4, story-5).

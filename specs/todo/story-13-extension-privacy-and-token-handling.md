---
id: story-13
title: "Extension: privacy, what leaves the browser, and token handling"
effort: MEDIUM
epic: EPIC-1
depends_on: [story-12]
shared_files: [extension/manifest.json, extension/background/service-worker.js, extension/background/api-client.js, config/rules.json]
track: full
models: {implementer: large, qa: standard, ui: standard, review: large}
---

# story-13: Extension: privacy, what leaves the browser, and token handling

**Repository:** ec-quote (`extension/` and backend) · **Epic:** [EPIC-1](epic-1-assisted-quoting-in-the-extension.md) · **Depends on:** story-12

## Summary

The extension reads customers' private conversations on a staff computer and sends parts of them to a server. This story fixes, in code and in writing, exactly what leaves the browser, where it goes, what is kept and for how long: only the open chat, only to the configured backend over HTTPS, only while the panel is on; nothing about conversations is stored in the extension; the staff token is stored locally, never exposed to the page, and can be replaced or revoked. It adds the options page where a staff member enters the backend address and their token, and a privacy note for the owner and for the Chrome Web Store listing.

## User Story

As the owner, I want to be able to say precisely which customer data leaves our computers and why, and to cut one person's access in a minute.

## Scope

**In:** `extension/options/` (options page: backend address, token, test connection, self-test, sign out); `extension/background/api-client.js` and `service-worker.js` (token storage and use, HTTPS only, request content); `extension/manifest.json` (minimal permissions, content security policy); `extension/test/privacy.test.js`, `options.test.js`, `manifest.test.js`; `docs/privacy.md` (new, Romanian: what is read, sent, stored, for how long, who can see it); backend: `config/rules.json` and `ec_quote/agent/rules.py` (`retention_days`, used by the store's cleanup function), `ec_quote/agent/store.py` (a `purge(now)` function), `tests/agent/test_retention.py`.

**Out:** per staff tokens on the backend (story-4); the Chrome Web Store submission (story-14); a scheduled retention job (the function exists here; scheduling it is part of story-5's runner or a follow-up); legal texts for customers on the site.

## Acceptance Criteria

1. `manifest.json` requests only: the host permission `https://web.whatsapp.com/*`, the backend origin as an optional host permission granted when the address is saved, `storage`, and the panel permission in use. No `<all_urls>`, `tabs`, `history`, `cookies`, `webRequest`, `downloads` or `scripting` beyond what the listed features need; a test compares the manifest with an allow list.
2. The extension's content security policy forbids remote scripts and `eval`; a test scans `extension/` outside `test/` for `eval(`, `new Function`, remote `<script src>` and remote imports and finds none.
3. The token is saved in `chrome.storage.local` by the options page and read only by the service worker; no message to the content script or the panel contains it; a test inspects every message type.
4. The backend address must be `https` (plain `http` only for `localhost`); another scheme is rejected by the options page; requests go only to that origin and to no other host (asserted on the fake `fetch` over a full panel session).
5. A request to `/v1/assist/suggest` contains only: the contact key, the display name, and for each message of the open chat its id, direction, text, time and attachment descriptors. It contains no other chat, no chat list, no profile photo, no group membership, no browser or machine identifier beyond the extension version.
6. Nothing about conversations is persisted by the extension: after a full panel session on the fixtures, `chrome.storage` (local, sync, session), `localStorage`, IndexedDB and the Cache API contain only the backend address, the token and the on/off switch (asserted by dumping each store in the test).
7. No message text, contact name or phone, token or payment link is written to the console or included in an error object passed to `console.error`; a test runs the session with every console method captured and scans the output.
8. Conversation data held in memory is dropped when the chat changes, when the panel is turned off and when the tab closes; a test switches chat and asserts the previous chat's messages are no longer referenced by the panel or worker state.
9. "Test connection" calls `GET /v1/assist/ping` and shows the staff name or the error in Romanian; "Sign out" deletes the token and the address and the panel then shows "neconfigurat"; without a token the worker makes no request.
10. The token field is a password field, is never pre-filled back in clear text, and the page shows only that a token is saved and for which staff name.
11. Backend: `retention_days` from `config/rules.json` drives `purge(now)`, which deletes stored message texts, contact names and uploaded files older than that many days while keeping offers' numbers and statuses for the metrics, with the contact key replaced by its hash; with the key undecided (`DECIZIE_DESCHISA`) `purge` refuses to run and says so.
12. `docs/privacy.md` states in plain Romanian, in under one page: what the extension reads, what it sends and where, what the backend keeps and for how long, that message content is also sent to the model provider for the purpose of understanding the request and under which settings, what is never collected, and how to revoke a token and delete a customer's data on request. A test checks that every data field named in criterion 5 appears in it.

## UI Notes

Options page: two fields, three buttons, a status line; usable by keyboard; Romanian strings from the strings file. The UI test session opens the options page of the unpacked extension against a fake backend.

## Technical Notes

- `chrome.storage.local` is not encrypted at rest; that is acceptable for a revocable per person token on a staff computer and is said in `docs/privacy.md`. `chrome.storage.sync` is not used, so the token does not travel to other devices.
- The optional host permission keeps the install prompt honest: the extension asks for the backend's origin only when the staff member saves it.
- Customers' conversations are personal data and the business is their controller; the model provider and the host are processors. The owner decides whether the site's privacy notice needs a line about assisted replies (hand-over).

## Hand-over

Owner: `retention_days`; a look at `docs/privacy.md`; the decision about mentioning assisted replies in the site's privacy notice.

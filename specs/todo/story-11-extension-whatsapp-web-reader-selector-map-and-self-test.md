---
id: story-11
title: "Extension: resilient WhatsApp Web reading with one selector map and a self-test"
effort: HIGH
epic: EPIC-1
depends_on: []
shared_files: [extension/manifest.json, CLAUDE.md]
track: full
models: {implementer: large, qa: standard, ui: standard, review: large}
---

# story-11: Extension: resilient WhatsApp Web reading with one selector map and a self-test

**Repository:** ec-quote (`extension/`) · **Epic:** [EPIC-1](epic-1-assisted-quoting-in-the-extension.md) · **Depends on:** none in code (the reader is tested on saved page fragments)

## Summary

Everything the product does starts from reading the conversation the staff member has open on web.whatsapp.com. WhatsApp Web offers no API for this and changes its page without notice, so the reader must be easy to repair and must never guess. This story makes the content script's reader: every selector and every assumption about the page in one file (the selector map), a reader that turns the open chat into the `AssistMessage` list the backend expects, a clear "cannot read" state when something does not match, and a self-test the staff or a developer can run on the live page to see which selectors still work. The reader only reads; it changes nothing on the page.

## User Story

As a staff member, I want the assistant to see the conversation I am looking at, and to tell me honestly when WhatsApp changed and it cannot, instead of suggesting something based on half a conversation.

## Scope

**In:** `extension/manifest.json` (Manifest V3, content script on `https://web.whatsapp.com/*` only); `extension/src/whatsapp/selectors.js` (the selector map, the only file with selectors); `extension/src/whatsapp/reader.js` (open chat to contact and messages); `extension/src/whatsapp/selftest.js`; `extension/test/fixtures/*.html` (saved, anonymized fragments of the page: a text chat, a chat with images and documents, a group, an unsaved number, a business contact, no chat open); `extension/test/reader.test.js`, `selectors.test.js`; `extension/README.md` (how to refresh fixtures and repair a selector); `extension/package.json` only if a test runner is needed, with the reason; `CLAUDE.md` (the extension's test command).

**Out:** the panel and inserting text (story-12); talking to the backend and the token (story-12, story-13); downloading attachments (story-19); reading anything other than the open chat.

## Acceptance Criteria

1. The selector map exports named entries (open chat header, contact phone or id, contact display name, message row, message id, direction, text, timestamp, attachment marker and kind, the composer); each has a selector or strategy and a description of what counts as found. A test fails if a selector string or `querySelector` call with a literal appears in any other file of `extension/src/`.
2. For each fixture, the reader returns the expected contact and the expected list of messages: stable `id`, `direction` (`in` for the customer, `out` for us), `text`, `sent_at` when the page shows it, and for each attachment its kind and file name without its content.
3. Message ids are the stable identifiers WhatsApp puts on message rows; the same fixture read twice gives the same ids; a row without an id is skipped and counted, never given an invented id.
4. The contact key is the phone number in digits when the page exposes it; for a contact where only a saved name is visible the reader reports `contact_key_unavailable` and the panel later asks the person to open the contact info once (the fixture set includes both).
5. A group chat, a broadcast list, a channel, the archive and the "no chat open" screen each return a named state and no messages; the assistant does not work in groups.
6. Missing or changed markup is a state, not an exception: with the message row selector broken (fixture with renamed attributes) the reader returns `cannot_read` naming the failed entry; with only the timestamp entry broken it returns the messages without times and a warning. No partial conversation is returned when the message list, id, direction or text entry fails.
7. Emoji, line breaks, links, quoted replies, forwarded marks, deleted messages, edited marks, voice notes and stickers are handled: text is plain text with line breaks; a quoted reply's quoted part is not mixed into the message text; non text messages appear as attachments or typed placeholders.
8. The reader observes the open chat with one `MutationObserver`, debounced, and reports a change only when the set of message ids or the open contact changed; it stops observing when the panel is closed. It never scrolls the chat, never clicks and never opens another chat.
9. The reader returns at most the configured number of latest messages and reads only what is in the DOM of the open conversation; it never touches the chat list beyond identifying the open chat.
10. The self-test, run from the panel or from the console on the live page, checks every selector map entry against the current page and reports per entry `ok`, `not found` or `ambiguous`, with counts and no message content; its output can be copied as text for a bug report.
11. Selectors prefer stable attributes (roles, `data-*` ids, aria labels in both Romanian and English interface languages) over generated class names; each entry may have ordered fallbacks, and the self-test says which one matched.
12. The content script requests no permission beyond the host permission for web.whatsapp.com, loads no remote code, and makes no network request.
13. The extension's tests run in the terminal without a browser session on WhatsApp and without the backend; the command is documented in `CLAUDE.md`.

## UI Notes

The only visible surface in this story is the self-test report (a plain list). The UI test session loads the unpacked extension on a local page built from the fixtures, not on WhatsApp.

## Technical Notes

- Fixtures are captured by hand from the live page, then anonymized (names, numbers, texts replaced) before commit; `extension/README.md` describes the steps. They are the regression suite when WhatsApp changes: capture the new markup, fix the map, keep the old fixture only if the old markup is still served.
- WhatsApp Web's DOM changes without notice and there is no contract. This is a standing risk of the product, accepted by the owner; the mitigation is this story's map, states and self-test, not cleverness in the reader.
- Reading the page and inserting text for a person to send is the whole scope. Anything that sends, navigates or acts in bulk is out of scope for the project (`docs/dev-rules.md`, "The extension").
- Plain JavaScript modules, no framework. A test runner (for example Node's built in runner with jsdom) needs the written reason required by the dependency rule.

## Hand-over

Owner or staff: an hour on a real WhatsApp Web session for a developer to capture the fixtures, and the interface language the staff use.

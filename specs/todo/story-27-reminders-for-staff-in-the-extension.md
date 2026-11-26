---
id: story-27
title: "Reminders for staff at 24 and 72 hours, shown in the extension"
effort: MEDIUM
epic: EPIC-3
depends_on: [story-12, story-24]
shared_files: [ec_quote/agent/store.py, ec_quote/api/app.py, ec_quote/api/schemas.py, extension/panel/]
track: full
models: {implementer: standard, qa: standard, ui: standard, review: standard}
---

# story-27: Reminders for staff at 24 and 72 hours, shown in the extension

**Repository:** ec-quote (backend and `extension/`) · **Epic:** [EPIC-3](epic-3-measurement-and-tuning.md) · **Depends on:** story-12, story-24

## Summary

In the original plan the assistant wrote to the customer by itself 24 and 72 hours after an unanswered offer. Now nothing is sent automatically. The same hours (`follow_up_hours` in `config/rules.json`) produce reminders for the staff: the panel shows a short list, "oferta pentru <contact> din <date> a rămas fără răspuns", and when the person opens that chat, the suggestion is a polite follow up text they can insert and send, or dismiss. The extension does not open chats and does not write to anyone.

## User Story

As a staff member, I want to be reminded which offers got no answer, with a ready sentence when I open that chat, so that no offer is forgotten and no customer is nagged by a machine.

## Scope

**In:** `ec_quote/agent/reminders.py` (new: `due_reminders(now)`, states, pure over store rows); `ec_quote/agent/store.py` (reminder rows through the migration mechanism); `ec_quote/api/app.py` and `schemas.py` (`GET /v1/assist/reminders`, `POST /v1/assist/reminders/{id}/dismiss`); the follow up suggestion in `suggest`; `ec_quote/agent/offer.py` (the fixed follow up texts); `extension/panel/` and the worker (the reminders list, a badge count, dismiss); `tests/agent/test_reminders.py`, `tests/api/test_assist_reminders.py`, `extension/test/reminders.test.js`.

**Out:** sending anything; opening a chat from the list by automation (the list shows the contact name and number for the person to open it); desktop or push notifications; any incentive or discount in the text.

## Acceptance Criteria

1. When a payment link is created for an offer, or an offer text was sent (outcome `unchanged` or `edited`), one reminder per entry of `follow_up_hours` is scheduled from that time; changing the list in the rules fixture changes the schedule with no code change.
2. `due_reminders(now)` returns the reminders whose time has passed and whose offer is not paid, not expired, not cancelled, with no customer message after the offer as far as the backend has seen, and not dismissed.
3. A customer message seen in a later `suggest`, a payment (story-24), expiry, or a dismissal cancels the remaining reminders of that offer; a test covers each.
4. `GET /v1/assist/reminders` requires an assist token and returns, for all staff alike, the due reminders with the contact's display name and number, the offer date, the highlighted quantity and total, and which reminder it is (first, second); it returns at most the newest offer per contact.
5. The panel shows the count on its header and the list on demand; an entry is text only, with a "Am rezolvat" button that calls dismiss; clicking an entry does not navigate WhatsApp.
6. When the person opens a chat that has a due reminder and the last message is ours, `suggest` returns kind `reply` with the fixed follow up text for that reminder (first or second), the validity date and no amount other than the stored total; `note_for_staff` says it is a reminder and since when the offer waits.
7. Once an outgoing message follows the reminder's suggestion (whatever its text), that reminder is done and the next one keeps its own schedule.
8. The backend only knows a chat's state from the last time someone had it open; a reminder whose chat was not seen since the offer says so in the list ("nu știm dacă a răspuns"), and opening the chat resolves it one way or the other.
9. A customer who wrote "nu mai", "stop" or similar (closed list) gets no follow up suggestion; the reminder is cancelled and the reason noted.
10. Reminder texts are fixed Romanian strings pinned by a test, with no deadline, no discount, no em dash, no emoji; at most two reminders per offer.
11. With `follow_up_hours` empty, no reminder is ever scheduled and the list endpoint returns an empty list.
12. The extension keeps the reminders list in memory only and refetches it when the panel opens and at most every few minutes while it is open; nothing from it is written to any storage.

## UI Notes

A collapsible "De urmărit (n)" block at the top of the panel: name, number, date, total, which reminder, the uncertainty note of criterion 8, and "Am rezolvat". Checked by the UI test session on the fixture page with a fake backend.

## Technical Notes

- Reminder times are plain offsets from the offer; business hours do not move them, since nothing is sent and the person sees the list whenever they work.
- The two new routes extend the assist API; they follow the token, limit and logging rules of story-4, and the list response is personal data that must not be logged.

## Hand-over

Owner: confirmation of the two follow up texts.

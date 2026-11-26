---
id: story-16
title: "Follow up scheduler at 24 and 72 hours"
effort: MEDIUM
epic: EPIC-1
depends_on: [story-3, story-9]
shared_files: [ec_quote/agent/store.py, ec_quote/api/main.py, ec_quote/api/texts.py, ec_quote/contracts.py]
track: full
models: {implementer: standard, qa: standard, ui: none, review: standard}
---

# story-16: Follow up scheduler at 24 and 72 hours

**Repository:** ec-quote · **Epic:** [EPIC-1](epic-1-price-and-offer.md) · **Depends on:** story-3, story-9

## Summary

An offer that gets no answer is reminded once after 24 hours and once after 72 hours (`follow_up_hours` in `config/rules.json`). The scheduler decides what is due; it does not deliver. It produces follow up actions that the channel sends: on WhatsApp the free window is 24 hours from the customer's last message, and the offer is sent after that message, so with the current `follow_up_hours` both reminders fall outside it and must go out as an approved template through the CRM (EPIC-3); a first reminder moved earlier than the window's end would be a normal message. On the site chat a visitor who left can only be reached if they gave a phone number or an email. The scheduler never reminds someone who paid, was handed off, is being answered by a person, or asked to be left alone.

## User Story

As the owner, I want unanswered offers to get one polite reminder at each interval, and never a reminder that embarrasses us.

## Scope

**In:** `ec_quote/agent/followup.py` (new: `due_follow_ups(now)`, state transitions); `ec_quote/agent/store.py` (follow up table through the migration mechanism); `ec_quote/api/main.py` (periodic runner, an endpoint the CRM can poll or be pushed from, per the bridge contract); `ec_quote/api/texts.py` (reminder texts); `ec_quote/contracts.py` (an action kind or flag that marks a message as needing a template, if the contract lacks one); `tests/agent/test_followup.py`.

**Out:** the WhatsApp template and its sending (EPIC-3, CRM); email sending; an incentive in the reminder (EPIC-1 D5, undecided: the texts carry none).

## Acceptance Criteria

1. When an offer is sent, one follow up per entry of `follow_up_hours` is scheduled at `sent_at` plus that many hours; changing the list in the rules fixture changes the schedule with no code change.
2. `due_follow_ups(now)` returns exactly the follow ups whose time has passed and whose offer is still `sent`, not expired, with no customer message and no staff message after `sent_at`, not handed off, not in manual mode, and whose contact has not opted out.
3. A follow up that would fall outside business hours is moved to `Rules.next_business_open`; one that would fall after `valid_until` is cancelled.
4. Each due follow up is returned once: claiming it is atomic, a second runner gets nothing, and after a restart a claimed but undelivered item is returned again only after a visibility timeout.
5. A customer reply, a payment (story-15), a handoff, a rejection, or a staff message cancels the remaining follow ups of that offer; a test covers each.
6. The words "nu mai", "stop", "dezabonare" from the customer (closed list in `ec_quote/api/texts.py`) mark the contact as opted out; no follow up is ever produced for that contact again and the lead is updated.
7. The follow up action states whether it is inside the channel's free window: for `whatsapp`, older than 24 hours since the customer's last message means `requires_template` with the template key and its parameters (offer reference, validity date); a reminder due at or after the window's end is outside it. With `follow_up_hours` of 24 and 72 both are; with a first value of 20 and a customer message just before the offer, the first is inside.
8. For `site` contacts with no phone and no email the follow up is recorded as `skipped_no_contact`; with a phone it is produced for delivery through the CRM as a template message.
9. Reminder texts are fixed Romanian strings pinned by a test, with no amount other than the stored offer total, no deadline, no discount, no em dash, no emoji; at most 2 reminders per offer and at most 1 pending offer reminded per contact at a time (the newest).
10. In shadow mode each follow up is produced as `pending_approval`, like an offer.
11. Every transition is stored with its time and reason, and counted in metrics (scheduled, sent, cancelled by reason, skipped).

## Technical Notes

- The runner is a loop in the FastAPI lifespan that calls `due_follow_ups(clock())` every minute; all logic is in the pure function plus the store.
- Meta's customer service window is 24 hours from the customer's last message; the CRM is the authority on the window when it delivers, ec-quote's flag is the request.

## Hand-over

Owner: the incentive decision (EPIC-1 D5), the template text (EPIC-3), and whether the first reminder stays at 24 hours (paid template) or moves inside the free window.

---
id: story-25
title: "Usage metrics: time to suggestion, and suggestions used unchanged, edited or ignored"
effort: MEDIUM
epic: EPIC-3
depends_on: [story-3, story-12]
shared_files: [ec_quote/agent/store.py, ec_quote/agent/engine.py]
track: full
models: {implementer: standard, qa: standard, ui: none, review: standard}
---

# story-25: Usage metrics: time to suggestion, and suggestions used unchanged, edited or ignored

**Repository:** ec-quote · **Epic:** [EPIC-3](epic-3-measurement-and-tuning.md) · **Depends on:** story-3, story-12

## Summary

With a person sending every message, the question is no longer "can the bot be trusted alone" but "does the assistant help": how fast a suggestion is ready after the customer writes, and what the staff do with it. The backend can answer both from what it already receives. Each `suggest` call carries the visible conversation, including the outgoing messages the person sent, so the backend can compare the next outgoing message with the suggestion it had offered: sent as it was, sent after editing, or not used. No extra tracking in the extension and no stored keystrokes. This story computes those measures as pure functions over the store.

## User Story

As the owner, I want to see whether the suggestions are fast enough and good enough to be sent as they are, and which kinds of request they fail on.

## Scope

**In:** `ec_quote/metrics/__init__.py`, `ec_quote/metrics/usage.py` (classification and aggregates, pure functions of rows and a period); `ec_quote/agent/engine.py` and `store.py` (record for each suggestion: when the triggering customer message was sent, when the suggestion was first returned, to whom; link the following outgoing message); `tests/metrics/test_usage.py`, a fixture of 40 conversations with known answers.

**Out:** the report (story-26); conversion and audit (story-26); dashboards; per keystroke or per click telemetry from the extension; ranking staff members.

## Acceptance Criteria

1. Time to suggestion: for each customer message that led to a suggestion, the time from the message's `sent_at` (as read from the page) to the first time the suggestion was returned; when the page gave no time, the time the backend first saw the message is used and the row is flagged. Aggregates: median, 90th percentile, share under 60 seconds and under 5 minutes.
2. Backend latency is recorded separately (request received to response sent), so a slow answer can be told apart from a chat nobody had open.
3. Outcome of each suggestion with a text, decided when a later `suggest` shows the next outgoing message in that chat: `unchanged` when its text equals the suggestion after normalizing whitespace; `edited` when the similarity is at or above a threshold and it is not equal; `ignored` when a different outgoing message follows or when a newer suggestion replaced it without any outgoing message; `pending` while none of these happened.
4. The similarity measure and its threshold are defined in one place with tests on 20 pairs (a typo fixed, a greeting added, a price line removed, a completely different answer); the threshold is a setting, not a literal in the comparison.
5. For an `edited` outcome on an offer, the metrics record whether any amount of the suggestion is missing or changed in the sent text (`amounts_changed`), using the guard's amount parser; this is a count for the weekly report, not a block.
6. `needs_human` and `none` suggestions are counted by kind and reason and are not classified as ignored.
7. Outcomes are attributed to the staff member whose token requested the suggestion and reported in total; a per person breakdown exists only as counts of suggestions requested, for token auditing.
8. Counts per period: suggestions by kind; outcomes; `needs_human` by `HandoffReason`; offers suggested, payment links created; guard rejections by rule; calculator failures; file verdicts by level.
9. Model cost: input and output tokens per suggestion from the recorded usage, converted with prices from configuration, total for the period and a month end projection against the configured ceiling.
10. All functions take (rows, period start, period end) in Europe/Bucharest and are pure; the fixture pins every number.
11. The stored outcome keeps no copy of the sent message beyond what the message ledger already holds under the retention rule.

## Technical Notes

- A suggestion and the outgoing message are linked by order in the chat, not by time alone: the first outgoing message after the suggestion's last customer message.
- Two staff members with the same chat open produce one suggestion (story-3); the outcome is attributed to whoever requested it first.
- Model prices per million tokens and the monthly ceiling are new keys in `config/rules.json`, owner editable.

## Hand-over

Owner: the monthly cost ceiling for the model.

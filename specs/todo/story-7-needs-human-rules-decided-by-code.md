---
id: story-7
title: "When a person must decide: needs_human rules decided by code"
effort: MEDIUM
epic: EPIC-1
depends_on: [story-2, story-3]
shared_files: [ec_quote/agent/engine.py, ec_quote/agent/model.py, ec_quote/agent/tools.py, ec_quote/agent/offer.py]
track: full
models: {implementer: large, qa: standard, ui: none, review: large}
---

# story-7: When a person must decide: needs_human rules decided by code

**Repository:** ec-quote · **Epic:** [EPIC-1](epic-1-assisted-quoting-in-the-extension.md) · **Depends on:** story-2, story-3

## Summary

The plan lists the situations where the assistant must not propose a price or an answer: the product is not in the calculator, the value is over the threshold, the customer asks for a discount or special terms, there is a complaint, the file is unusable after the allowed attempts, the customer is not understood after the allowed exchanges, or the customer asks who they are talking to. In assisted mode a person is always present, so these do not hand a conversation over; they change what the panel shows: a suggestion of kind `needs_human` with the reason and what is already known, and no proposed text with numbers. After this story that decision is a pure function of conversation state and rules that the model cannot override.

## User Story

As a staff member, I want the panel to tell me plainly "this one is yours, because..." with what was already understood, instead of a confident suggestion I should not send.

## Scope

**In:** `ec_quote/agent/handoff.py` (new: `evaluate_needs_human(state, rules, now) -> HandoffReason | None` and the staff note builder, taking over whatever such logic sits in `ec_quote/agent/engine.py`); `ec_quote/agent/engine.py`, `model.py`, `tools.py` (signals instead of decisions, counters in state); `ec_quote/agent/offer.py` (fixed staff notes per reason); `tests/agent/test_needs_human_rules.py`, `tests/e2e/test_needs_human_journeys.py`.

**Out:** the panel's rendering (story-12); file verdicts (story-15 supplies them; the counter and rule are here); notifying anyone outside the panel; the CRM.

## Acceptance Criteria

1. `not_in_calculator`: an `Unpriced` with reason `unknown_product`, `unknown_material`, `unknown_shape`, `custom_size_disabled`, `size_above_maximum`, `quantity_above_maximum` or `no_price`, for a request the customer has stated clearly, yields `needs_human` with this reason; `size_below_minimum` and `quantity_below_minimum` first yield a `question` that states the minimum from the 422 details.
2. `value_over_threshold`: a quote with `total_ex_vat` strictly greater than `handoff_value_threshold_ron_ex_vat` yields `needs_human`; equal to the threshold does not. The computed offer is shown to staff in `offer_lines` and `note_for_staff`; `text` is empty and `can_create_payment_link` is false.
3. `special_terms`: a signal of discount, negotiation, a deadline shorter than the production term, payment terms or a framework contract yields `needs_human` on that turn; `text` is empty.
4. `complaint` and `customer_asked` (the customer asks for a named person, or asks whether they are talking to a bot): `needs_human` on that turn, even with an offer in progress.
5. `file_unusable`: appears when the count of consecutive `unusable` verdicts reaches `max_file_attempts`, not before; a `weak` or `ok` verdict resets the count.
6. `not_understood`: appears when the count of consecutive customer turns without progress (no new validated choice, no answered question) reaches `max_misunderstandings`, or when more than `max_clarifying_questions` questions were suggested before a first price.
7. Precedence when several apply: `complaint`, `customer_asked`, `special_terms`, `value_over_threshold`, `not_in_calculator`, `file_unusable`, `not_understood`. One table driven test covers each pair.
8. Changing a threshold in the rules fixture changes the outcome with no code change (parametrized over two values per numeric rule).
9. The fake model proposing an offer text on a turn where a rule applies does not change the result: the suggestion is `needs_human` and its `text` contains no amount.
10. Outgoing messages written by staff are read as facts of the conversation: after a `needs_human`, once staff have answered and the customer writes again about something inside the rules, suggestions resume; a staff message that states a price is never adopted as a stored quote.
11. `note_for_staff` is built by code from state: the reason in Romanian, what the customer asked in one or two sentences, the validated choices, the stored quote if any, the file verdict if any. The model's free text, when included, is a quoted block labelled as unverified.
12. Each reason has exactly one fixed Romanian staff note template, pinned by a test, without em dashes or emojis.

## Technical Notes

- `evaluate_needs_human` takes `now` and is pure; it runs after every tool result and before the guard.
- Signals are a closed enum the model fills in a tool call; an unknown signal is ignored and logged by code name.
- The `HandoffReason` enum is reused as is; `HandoffPort` is not called in assisted mode.

## Dependencies

story-2 (engine), story-3 (counters and offers persisted).

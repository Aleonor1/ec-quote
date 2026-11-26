---
id: story-7
title: "Handoff rules decided by code, all seven reasons"
effort: MEDIUM
epic: EPIC-1
depends_on: [story-2, story-3]
shared_files: [ec_quote/agent/engine.py, ec_quote/agent/model.py, ec_quote/agent/tools.py, ec_quote/agent/offer.py]
track: full
models: {implementer: large, qa: standard, ui: none, review: large}
---

# story-7: Handoff rules decided by code, all seven reasons

**Repository:** ec-quote · **Epic:** [EPIC-1](epic-1-price-and-offer.md) · **Depends on:** story-2, story-3

## Summary

The plan lists seven situations in which a person takes over. Today the engine has the `handoff` tool and the `HandoffReason` values; whether a handoff happens still depends partly on what the model chooses. After this story the decision is a pure function of conversation state and rules, evaluated on every turn, that the model cannot suppress. The model can only signal what it understood (the customer wants a person, complains, asks for a discount); counting, thresholds and the final decision belong to code. Each handoff produces one Romanian message for the customer and one summary for staff.

## User Story

As a staff member, I want to receive exactly the conversations the rules say are mine, each with a summary of what was asked and what was already offered, so that I do not start from zero.

## Scope

**In:** `ec_quote/agent/handoff.py` (new: `evaluate_handoff(state, rules, now) -> HandoffReason | None` and the summary builder, taking over whatever handoff logic sits in `ec_quote/agent/engine.py` today); `ec_quote/agent/engine.py`, `model.py` and `tools.py` (signals instead of decisions, counters in state); `ec_quote/agent/offer.py` (customer texts per reason, where texts with policy are composed by code); `tests/agent/test_handoff_rules.py`, `tests/e2e/test_handoff_journeys.py`.

**Out:** delivering the handoff to the CRM (story-14); file attempts counting inputs (story-18 supplies the verdicts; the counter and rule are here); approval flow.

## Acceptance Criteria

1. `not_in_calculator`: an `Unpriced` with reason `unknown_product`, `unknown_material`, `unknown_shape`, `custom_size_disabled`, `size_above_maximum`, `quantity_above_maximum` or `no_price`, after the customer confirmed that is what they want, yields this reason; `size_below_minimum` and `quantity_below_minimum` first yield one question that states the minimum from the 422 details.
2. `value_over_threshold`: a quote with `total_ex_vat` strictly greater than `handoff_value_threshold_ron_ex_vat` yields this reason; equal to the threshold does not. The offer is stored and attached to the summary; no amount is sent to the customer.
3. `special_terms`: a signal of discount, negotiation, a deadline shorter than the production term, payment by invoice with a term, or a framework contract yields this reason on that turn; the customer text contains no number.
4. `complaint` and `customer_asked`: the corresponding signal yields the reason on that turn, even when an offer is in progress.
5. `file_unusable`: the reason appears when the count of consecutive `unusable` verdicts reaches `max_file_attempts`, not before; a `weak` or `ok` verdict resets the count.
6. `not_understood`: the reason appears when the count of consecutive turns without progress (no new validated choice and no answered question) reaches `max_misunderstandings`; a turn with progress resets it. More than `max_clarifying_questions` questions before a first price also yields it.
7. Precedence when several apply: `complaint`, `customer_asked`, `special_terms`, `value_over_threshold`, `not_in_calculator`, `file_unusable`, `not_understood`. One table driven test covers each pair.
8. Changing a threshold in the rules fixture changes the outcome with no code change (parametrized over two values per numeric rule).
9. The fake model answering "continue with the offer" on a turn where a rule applies does not prevent the handoff; the action list ends with a `handoff` action carrying `handoff_reason`.
10. After a handoff the conversation is in manual mode: later customer messages are stored and forwarded as notes, the model is not called, until staff release it or `manual_mode_quiet_hours` pass since the last staff message.
11. The staff summary contains: the reason code, what the customer asked in one or two sentences, the validated choices, the stored quote if any, the file verdict if any. It is built by code from state; the model's free text is included as a quoted block labelled as unverified.
12. Each reason has exactly one customer text, in one module, pinned by a test; outside business hours the text states when a colleague answers, from `Rules.next_business_open(now)`.

## Technical Notes

- `evaluate_handoff` takes `now` and is pure; it is called after every tool result and before any outbound text.
- Signals are a closed enum the model fills in a tool call; an unknown signal is ignored and logged by code name.

## Dependencies

story-2 (engine), story-3 (counters and offers persisted).

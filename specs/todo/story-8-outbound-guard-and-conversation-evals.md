---
id: story-8
title: "Outbound guard and the conversation evaluation set"
effort: HIGH
epic: EPIC-1
depends_on: [story-2]
shared_files: [ec_quote/agent/guard.py, ec_quote/agent/model.py, ec_quote/agent/prompts.py]
track: full
models: {implementer: large, qa: standard, ui: none, review: large}
---

# story-8: Outbound guard and the conversation evaluation set

**Repository:** ec-quote · **Epic:** [EPIC-1](epic-1-price-and-offer.md) · **Depends on:** story-2

## Summary

Four promises of the plan are about what the assistant may say: never a price outside the calculator, no deadline shorter than the production rules, material claims only from the approved list, and an honest answer when asked whether it is a bot. `ec_quote/agent/guard.py` already checks amounts, percentages, deadlines and claims in model text. This story proves the guard against a corpus of bad and good texts, closes the gaps the corpus finds, fixes what happens when a text fails (one rewrite, then a fixed text and handoff), and adds a set of scripted Romanian conversations that every later change to prompts or the model must keep green.

## User Story

As the owner, I want a wrong number or an invented promise to be stopped by code before it reaches a customer, whatever the model writes.

## Scope

**In:** `ec_quote/agent/guard.py`; `ec_quote/agent/model.py` (rewrite once, then fallback); `ec_quote/agent/prompts.py` (Romanian system text, self disclosure, tone); `ec_quote/api/texts.py` (fixed fallback texts); `tests/agent/fixtures/guard_corpus.json`, `tests/agent/test_guard.py`; `tests/evals/conversations/*.json`, `tests/evals/test_conversations.py`; `scripts/eval_live.py` (optional run against the real model, by hand).

**Out:** handoff decisions (story-7); offer layout (story-9); choosing the model.

## Acceptance Criteria

1. Amounts: for a text and the set of amounts stored for the conversation (quote totals, ex VAT totals, unit prices, tier totals), the guard accepts a text only if every monetary mention equals one of them. The corpus covers Romanian formats (`1.234,50 lei`, `1234,5 RON`, `1 234 lei`, `1234.50`), amounts in words ("o mie două sute"), a per piece price, a sum of two tiers, a "from" price, a range, and an amount split across a line break; each of at least 40 bad texts is rejected and each of at least 40 good texts is accepted.
2. Percentages and discounts: any percentage or the words for discount, reduction or free shipping are rejected unless the same percentage is in the stored quote's `discount_percent`.
3. Deadlines: a text that states a delivery or production time (days, hours, a weekday, a date, "mâine", "urgent până vineri") is accepted only when it equals `Rules.production_term(urgent)` for the stored quote; with the production term keys undecided, every deadline is rejected.
4. Material claims: statements about resistance, waterproofing, UV, food contact, temperature, durability in years, certification or eco properties are accepted only when they match an entry of `approved_material_claims` after normalization (case, diacritics); the corpus has at least 20 rejected and 10 accepted examples.
5. A rejected text never appears in an `OutboundAction`. The engine asks the model once to rewrite with the reason code; if the second text is rejected too, the customer gets the fixed text for that situation and the conversation is handed off with reason `not_understood`. The model is called at most twice per turn for this.
6. Self disclosure: to "ești robot?", "vorbesc cu un om?", "e cineva acolo?" and four more phrasings in the eval set, the reply states that it is an automated assistant and offers a colleague; a reply that claims to be a person is rejected by the guard.
7. Customer facing texts contain no em dash and no emoji (guard rule, applied to model text and pinned for fixed texts).
8. The evaluation set has at least 25 scripted conversations with the fake model, each with expected action kinds, expected handoff reason or none, the maximum number of questions, and the exact set of amounts allowed; it covers journeys J1 to J6 of the epic. `pytest tests/evals` passes with no network.
9. The request sent to the model in every eval contains no phone number, email or payment URL (checked on the fake model's recorded input).
10. `scripts/eval_live.py` runs the same conversations against the configured real model and prints pass or fail per conversation; it is not collected by `pytest` and refuses to run without `ANTHROPIC_API_KEY`.

## Technical Notes

- The guard is the last step before actions are returned, after story-7's handoff evaluation.
- Amount equality is exact on `Decimal` quantized to 2 places; an amount with no decimals in text matches a stored amount with `.00`.
- Words to number parsing may be conservative: an amount in words that cannot be parsed is rejected.
- The system prompt must not contain any policy number; it refers to tool results.

## Hand-over

Owner: tone and whether the first message introduces the assistant as automated (EPIC-1 D7). The default written here is that it does.

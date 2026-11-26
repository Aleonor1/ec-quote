---
id: story-8
title: "Suggestion guard and the conversation evaluation set"
effort: HIGH
epic: EPIC-1
depends_on: [story-2]
shared_files: [ec_quote/agent/guard.py, ec_quote/agent/model.py, ec_quote/agent/prompts.py, ec_quote/agent/offer.py]
track: full
models: {implementer: large, qa: standard, ui: none, review: large}
---

# story-8: Suggestion guard and the conversation evaluation set

**Repository:** ec-quote · **Epic:** [EPIC-1](epic-1-assisted-quoting-in-the-extension.md) · **Depends on:** story-2

## Summary

A person reads every suggestion before sending it, but a busy person trusts a number that looks right. So the promises of the plan stay enforced by code before a suggestion reaches the panel: never a price outside the calculator, no deadline shorter than the production rules, material claims only from the approved list. `ec_quote/agent/guard.py` already checks amounts, percentages, deadlines and claims in model text. This story proves the guard against a corpus of bad and good texts, closes the gaps the corpus finds, fixes what happens when a text fails (one rewrite, then `needs_human`), and adds a set of scripted Romanian WhatsApp conversations that every later change to prompts or the model must keep green.

## User Story

As the owner, I want a wrong number or an invented promise to be stopped by code before my staff even see it, whatever the model writes.

## Scope

**In:** `ec_quote/agent/guard.py`; `ec_quote/agent/model.py` (rewrite once, then fallback); `ec_quote/agent/prompts.py` (Romanian system text: write as a staff member of Etichete Creative would, short, polite); `ec_quote/agent/offer.py` (fixed texts); `tests/agent/fixtures/guard_corpus.json`, `tests/agent/test_guard.py`; `tests/evals/conversations/*.json`, `tests/evals/test_conversations.py`; `scripts/eval_live.py` (optional run against the real model, by hand).

**Out:** `needs_human` decisions (story-7); offer layout (story-9); choosing the model; checking what the person edits before sending (the edited text is theirs; story-10 checks only the text of the payment link reply).

## Acceptance Criteria

1. Amounts: the guard accepts a text only if every monetary mention equals an amount stored for the conversation (quote totals, ex VAT totals, unit prices, tier totals). The corpus covers Romanian formats (`1.234,50 lei`, `1234,5 RON`, `1 234 lei`, `1234.50`), amounts in words, a per piece price, a sum of two tiers, a "from" price, a range, and an amount split across a line break; each of at least 40 bad texts is rejected and each of at least 40 good texts is accepted.
2. Percentages and discounts: any percentage or the words for discount, reduction or free shipping are rejected unless the same percentage is in the stored quote's `discount_percent`.
3. Deadlines: a text that states a delivery or production time (days, hours, a weekday, a date, "mâine") is accepted only when it equals `Rules.production_term(urgent)` for the stored quote; with the production term undecided, every deadline is rejected.
4. Material claims: statements about resistance, waterproofing, UV, food contact, temperature, durability, certification or eco properties are accepted only when they match an entry of `approved_material_claims` after normalization (case, diacritics); at least 20 rejected and 10 accepted examples.
5. A rejected text never appears in an `AssistSuggestion`. The engine asks the model once to rewrite with the reason code; if the second text is rejected too, the suggestion is `needs_human` with reason `not_understood` and a staff note naming the guard rule. The model is called at most twice per suggestion for this.
6. A suggestion never states that the writer is a person, a bot or an assistant, and has no signature; the scaffold's automated assistant signature is not appended in assisted mode (a test asserts its absence). Questions about who is writing are `needs_human` (story-7).
7. Suggested texts contain no em dash and no emoji, and no greeting or closing formula longer than the configured length, so they read like a quick WhatsApp reply.
8. `options` (the short answers expected from the customer) contain only values of the catalog for the current product (materials, shapes, preset sizes) and no amounts.
9. The evaluation set has at least 25 scripted conversations with the fake model, each a list of `AssistMessage` (incoming and outgoing) with the expected suggestion kind, reason or none, the maximum number of questions, and the exact set of amounts allowed; it includes conversations where staff already answered part of the way, where the customer changes quantity after an offer, and where two requests are mixed in one chat. `pytest tests/evals` passes with no network.
10. The request sent to the model in every eval contains no phone number, no contact name and no payment URL (checked on the fake model's recorded input).
11. `scripts/eval_live.py` runs the same conversations against the configured real model and prints pass or fail per conversation; it is not collected by `pytest` and refuses to run without `ANTHROPIC_API_KEY`.

## Technical Notes

- The guard is the last step before the suggestion is stored and returned, after story-7's evaluation.
- Amount equality is exact on `Decimal` quantized to 2 places; an amount with no decimals in text matches a stored amount with `.00`. An amount in words that cannot be parsed is rejected.
- The system prompt contains no policy number; it refers to tool results.

## Hand-over

Owner: tone of the suggested replies (formal "dumneavoastră" or the tone the staff use today); three real, anonymized example replies help.

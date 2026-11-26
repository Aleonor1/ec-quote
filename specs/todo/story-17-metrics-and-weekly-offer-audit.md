---
id: story-17
title: "Metrics and the weekly audit of 20 offers"
effort: MEDIUM
epic: EPIC-1
depends_on: [story-6, story-15]
shared_files: [ec_quote/agent/store.py, ec_quote/audit/parity.py, RUNBOOK.md]
track: full
models: {implementer: standard, qa: standard, ui: none, review: standard}
---

# story-17: Metrics and the weekly audit of 20 offers

**Repository:** ec-quote · **Epic:** [EPIC-1](epic-1-price-and-offer.md) · **Depends on:** story-6, story-15

## Summary

The plan names its measures: first reply under 1 minute, full offer under 5 minutes, offer to order conversion (a baseline first, then plus 50%), under 30% of conversations handed to a person, zero price errors checked weekly on 20 offers, and a cost under about 100 EUR a month at 300 requests. This story computes them from what the store already records and writes one weekly report for the owner in Romanian. The audit takes 20 real offers of the week, asks the calculator again for the same choices, and reports every difference with its cause.

## User Story

As the owner, I want one page every Monday that tells me whether the assistant is fast, whether it sells, how much it costs, and that no customer got a wrong price.

## Scope

**In:** `ec_quote/metrics/__init__.py`, `ec_quote/metrics/compute.py` (pure functions over store rows and a period), `ec_quote/audit/offers.py` (sampling and re-pricing), `ec_quote/agent/store.py` (the timestamps and token counts the metrics need, through the migration mechanism), `scripts/weekly_report.py`, `tests/metrics/test_compute.py`, `tests/audit/test_offers.py`, `RUNBOOK.md` (how to run and read it).

**Out:** dashboards; alerts (EPIC-4); the shadow mode approval rate (EPIC-3); sending the report by email or chat (EPIC-4 routine); ad attribution.

## Acceptance Criteria

1. First reply time: per conversation, from the first customer message `received_at` to the first outbound action stored; the report gives the median, the 90th percentile and the share under 60 seconds for the period.
2. Full offer time: from the first customer message to the offer being ready (`pending_approval` created or offer sent), and separately to the offer being sent; share under 5 minutes for each. Conversations handed off before an offer are excluded and counted.
3. Handoff share: conversations with a handoff divided by conversations with at least one customer message, with the count per `HandoffReason`.
4. Conversion: offers paid divided by offers sent, by channel, with the median time from sent to paid; an offer is attributed to the week it was sent.
5. Cost: model input and output tokens per conversation from the recorded usage, converted with prices from configuration (not literals in code), monthly total to date and a projection to month end; the report states the ceiling from configuration and whether the projection exceeds it.
6. All metrics are pure functions of (rows, period start, period end) in Europe/Bucharest; a fixture of 30 conversations with known answers pins every number.
7. Audit sampling: 20 offers sent in the period, chosen with a seed derived from the ISO week so the choice is reproducible, stratified so each channel and each product with offers appears when possible; fewer than 20 offers means all of them.
8. For each sampled offer the audit calls the calculator with the stored choices and compares the stored `total`, `total_ex_vat`, `unit_price` and each tier with the answer. Identical is `ok`. A difference is classified from the calculator's `breakdown` and catalog: `promotion_changed`, `tier_schedule_changed`, `config_changed`, or `unexplained`; only `unexplained` is a price error.
9. The audit also checks, without the calculator, that the amounts in the stored outbound text and the Draft Order total equal the stored quote; any mismatch is a price error whatever the calculator says today.
10. `scripts/weekly_report.py --week 2026-W49 --out <dir>` writes `raport.md` (Romanian, one page, numbers formatted as in offers, no personal data: offers are named by id) and `raport.json`; it exits 0 with zero price errors and 1 otherwise; `--no-audit` skips the calculator calls.
11. The audit is read only, makes at most one calculator request per second, and refuses to run without `CALCULATOR_SYNC_SECRET` unless `--no-audit`.
12. The report's first lines state plainly what is missing (for example "conversia: nicio ofertă trimisă în perioadă") instead of showing zero or an estimate.

## Technical Notes

- Reuse the comparison code of story-6 (`ec_quote/audit/parity.py`).
- Token usage is recorded per model call by the engine; if the scaffold does not store it, add it here.
- Prices of the model per million tokens and the monthly ceiling live in `config/rules.json` as new keys, owner editable.

## Hand-over

Owner: confirm the monthly cost ceiling and who receives the report.

---
id: story-26
title: "Weekly report with the price audit of 20 offers"
effort: MEDIUM
epic: EPIC-3
depends_on: [story-6, story-24, story-25]
shared_files: [ec_quote/audit/parity.py, ec_quote/metrics/usage.py, RUNBOOK.md]
track: full
models: {implementer: standard, qa: standard, ui: none, review: standard}
---

# story-26: Weekly report with the price audit of 20 offers

**Repository:** ec-quote · **Epic:** [EPIC-3](epic-3-measurement-and-tuning.md) · **Depends on:** story-6, story-24, story-25

## Summary

One page for the owner every week, in Romanian: how fast suggestions were, how many were sent unchanged, edited or ignored, how many offers became orders, what the model cost, and the proof that no customer got a wrong price. The proof is the plan's weekly audit: 20 real offers of the week are priced again by the calculator for the same choices and compared, and each stored offer is checked against the text that was suggested and the Draft Order that was created. The report states what is missing instead of showing zeros.

## User Story

As the owner, I want one page every Monday that tells me whether the assistant helps, whether offers sell, and that every price was right.

## Scope

**In:** `ec_quote/audit/offers.py` (sampling and re-pricing, reusing the comparison of `ec_quote/audit/parity.py`); `ec_quote/metrics/conversion.py` (offer to order); `scripts/weekly_report.py`; `tests/audit/test_offers.py`, `tests/metrics/test_conversion.py`, `tests/test_weekly_report.py`; `RUNBOOK.md` (how to run and read it).

**Out:** the usage measures themselves (story-25); sending the report by email or chat; dashboards; ad attribution.

## Acceptance Criteria

1. Conversion: offers paid divided by offers for which a payment link was created, and divided by offers suggested, with the median time from link to payment; an offer is attributed to the week its link was created.
2. Audit sampling: 20 offers with a payment link created in the period, chosen with a seed derived from the ISO week so the choice is reproducible, spread over the products present; fewer than 20 means all of them.
3. For each sampled offer the audit calls the calculator with the stored choices and compares the stored `total`, `total_ex_vat`, `unit_price` and each tier with the answer. Identical is `ok`. A difference is classified from the calculator's `breakdown` and the catalog: `promotion_changed`, `tier_schedule_changed`, `config_changed`, or `unexplained`; only `unexplained` is a price error.
4. Without the calculator, for every offer of the period (not only the sample): the amounts in the suggested offer text, in the payment link reply and the Draft Order total equal the stored quote; any mismatch is a price error whatever the calculator says today.
5. For offers whose sent message was `edited` with `amounts_changed` (story-25), the report lists the offer id and the staff member, as a fact for the owner to look at, separate from price errors.
6. `scripts/weekly_report.py --week 2026-W49 --out <dir>` writes `raport.md` (Romanian, one page, numbers formatted as in offers, no customer data: offers are named by id) and `raport.json`; it exits 0 with zero price errors and 1 otherwise; `--no-audit` skips the calculator calls.
7. The report's sections, in order: the week and what is missing; speed (time to suggestion, backend latency); use (unchanged, edited, ignored, with the share of `needs_human` by reason); offers and conversion; price audit result with each difference; model cost against the ceiling; the three request types with the most ignored suggestions, as the list to tune next.
8. Missing data is stated in words ("nicio ofertă cu link în perioadă", "Shopify neconfigurat, conversia lipsește"); no metric is shown as zero or estimated when its source is absent.
9. The audit is read only, makes at most one calculator request per second, and refuses to run without `CALCULATOR_SYNC_SECRET` unless `--no-audit`.
10. A fixture week with known rows produces a report whose every number is pinned by the test, including one planted `unexplained` difference that makes the exit code 1.

## Technical Notes

- A baseline for conversion exists only after a few weeks of offers; the report shows the trend week by week from the stored offers, not a target invented beforehand.
- The run is manual or a cron entry on the host (documented in `RUNBOOK.md`); it needs no running web process.

## Hand-over

Owner: who reads the report and where it should be put.

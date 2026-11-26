---
id: story-6
title: "Price parity audit harness on 50 configurations"
effort: MEDIUM
epic: EPIC-0
depends_on: [story-2]
shared_files: [ec_quote/pricing/client.py, pyproject.toml]
track: full
models: {implementer: large, qa: standard, ui: none, review: large}
---

# story-6: Price parity audit harness on 50 configurations

**Repository:** ec-quote · **Epic:** [EPIC-0](epic-0-foundation.md) · **Depends on:** story-2

## Summary

The plan demands zero price errors. The calculator app already proves that `POST /api/sync/line` equals the storefront (`tests/utils/crm-line-price.parity.test.ts`, 130 cases). What nobody proves yet is that ec-quote carries that price unchanged to the customer: parsed to `Decimal`, split into ex VAT, shown in the suggested offer text and the offer image, and charged by the Draft Order. This story adds an audit harness that takes 50 configurations spread over the live catalog, asks the live calculator for each, pushes every answer through ec-quote's own path and compares every amount to the cent. It runs by hand against production with the secret, and in the suite on recorded answers.

## User Story

As the owner, I want a report that says "50 of 50 identical" before any customer sees a price, and the same check again whenever the calculator or ec-quote changes.

## Scope

**In:** `ec_quote/audit/__init__.py`, `ec_quote/audit/parity.py` (configuration sampler, comparison, report), `scripts/price_audit.py` (command line: `--live`, `--record`, `--replay`, `--out`), `tests/audit/fixtures/parity/*.json` (recorded calculator answers, no personal data), `tests/audit/test_parity.py`, `ec_quote/pricing/client.py` (only if a parsing defect is found), `RUNBOOK.md` (how to run it).

**Out:** comparing the endpoint with the storefront JavaScript (done in the calculator app); the weekly audit of real offers (story-26); fixing a defect in the calculator app (reported as a follow-up spec there).

## Acceptance Criteria

1. The sampler builds 50 configurations deterministically from a catalog (`GET /api/sync/calculator-config`) and a seed: every `kind` of product present, at least 3 materials, preset and custom sizes including the minimum and maximum custom size, at least 5 quantities on a tier and 5 between tiers, one at the product minimum and one at `quantity.max`, and each option the catalog allows (`adhesive: strong`, `whitePrint`, `cut: double` and `back`, `urgent`, `fileEditing`, an add-on choice) switched on in at least 3 configurations. The same catalog and seed give the same 50.
2. For each priced configuration the harness asserts, to the cent: `PriceQuote.total` equals the response `total` taken from the raw JSON text (not through a float); `total_ex_vat` equals `total / (1 + vat_percent/100)` quantized `ROUND_HALF_UP`, and `total_ex_vat` plus VAT equals `total` within 0.01; `unit_price` equals the response value; the property `_calculator_price` in `properties` equals `total`.
3. For each priced configuration the amounts rendered by the offer text builder and passed to the offer image builder, and the `priceOverride` in the Draft Order input built by `ShopifyCheckout` (fake transport), equal `total`.
4. For each configuration, each tier returned by `get_price_tiers` equals a direct `get_price` for that quantity, and its quantity is a visible tier of the catalog above the requested quantity.
5. A configuration the calculator answers with 422 is reported with its reason code and counts as consistent when ec-quote returns `Unpriced` with the same reason; the report lists how many of the 50 were priced.
6. `scripts/price_audit.py --replay tests/audit/fixtures/parity` exits 0 and prints `50/50 identice`; with one recorded total changed by 0.01 it exits 1 and names the configuration, the field, the expected and the found value.
7. `--live` refuses to start without `CALCULATOR_SYNC_SECRET`, makes at most one request per second, never writes the secret, and writes a JSON and a Markdown report to `--out`; `--record` writes fixtures that contain no secret and no host other than a placeholder.
8. A response with a number that does not survive a float round trip (a fixture with `1234.565`) is carried exactly; the test fails if the client parses through `float`.
9. The replay test is part of `pytest` and uses no network.

## Technical Notes

- Read the raw response text with `json.loads(text, parse_float=Decimal)`; the scaffold client already has an `exact_numbers` path, the harness proves it is the one in use for prices.
- The live run is read only on the calculator (`/api/sync/line` writes nothing in Shopify).
- 50 is the plan's number; the sampler takes the count as a parameter.

## Hand-over

Owner or a developer with the secret: one `--live` run against production before the extension is used on a real customer; this run is also the proof that the backend's host reaches the live calculator; the report is committed under `docs/audits/`.

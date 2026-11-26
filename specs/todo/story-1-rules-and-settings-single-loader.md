---
id: story-1
title: "Rules and settings: one validated loader, fail closed"
effort: SMALL
epic: EPIC-0
depends_on: []
shared_files: [config/rules.json, ec_quote/pricing/client.py, ec_quote/files/checker.py]
track: full
models: {implementer: standard, qa: standard, ui: none, review: standard}
---

# story-1: Rules and settings: one validated loader, fail closed

**Repository:** ec-quote · **Epic:** [EPIC-0](epic-0-foundation.md) · **Depends on:** none

## Summary

Policy numbers are read from `config/rules.json` in three places written independently on scaffold day: `ec_quote/agent/rules.py` (`Rules`), `ec_quote/pricing/client.py` (`load_vat_percent`) and `ec_quote/files/checker.py` (`load_rules`). `Rules` also carries a production term fallback written in code. After this story there is one `Rules` object, validated once at startup, passed to whoever needs it. A missing, malformed or placeholder key stops the process with the key's name. No policy value has a default in code.

## User Story

As the owner, I want every threshold and limit to come from the one file I control, so that changing a number never needs a code change and a typo never ships silently.

## Scope

**In:** `ec_quote/agent/rules.py` (strict validation, every key of `config/rules.json` typed, including `follow_up_hours`, `min_dpi_ok`, `min_dpi_weak`, `production_term_standard`, `production_term_urgent`, `retention_days`); `ec_quote/pricing/client.py` and `ec_quote/files/checker.py` (receive values from `Rules`, their own loaders removed); `ec_quote/config.py` (unchanged behaviour, covered by the same startup check); `config/rules.json` (new keys with the placeholder `DECIZIE_DESCHISA` where the owner has not decided); `tests/agent/test_rules.py`, `tests/test_no_policy_literals.py`.

**Out:** wiring the adapters (story-2); changing any policy value; per channel `shadow_mode` (EPIC-4).

## Acceptance Criteria

1. `Rules.load()` on the repository's `config/rules.json` returns an object in which every key of the file is a typed attribute; money values are `Decimal`, built from strings.
2. For each required key, a file without that key makes `Rules.load()` raise `RulesError` whose message contains the key's name; one parametrized test covers every key.
3. A wrong type (`"offer_validity_days": "seven"`), a negative number, `min_dpi_weak` greater than `min_dpi_ok`, an empty `business_hours.days`, an hour not in `HH:MM`, and `follow_up_hours` not strictly increasing each raise `RulesError` naming the key.
4. An unknown top level key raises `RulesError` (a typo is not ignored).
5. A key whose value is `DECIZIE_DESCHISA` loads, and reading that attribute raises `OpenDecision` naming the key; `Rules.production_term(urgent)` raises it while the production term keys hold the placeholder. No code path substitutes a default.
6. `ec_quote/pricing/client.py` and `ec_quote/files/checker.py` no longer open `config/rules.json`; a test that greps `ec_quote/` for `rules.json` finds it only in `ec_quote/agent/rules.py`.
7. `tests/test_no_policy_literals.py` fails if `_FALLBACK_PRODUCTION_TERM` or any literal equal to a value of `config/rules.json` for the keys `handoff_value_threshold_ron_ex_vat`, `vat_percent`, `offer_validity_days`, `manual_mode_quiet_hours` appears as a default in `ec_quote/`.
8. The existing tests of `tests/pricing/` and `tests/files/` pass, adapted only to pass rules in; no assertion is weakened.

## Technical Notes

- Use a pydantic model with `extra="forbid"` for the file; keep the public `Rules` attribute names so the agent module keeps compiling.
- The DPI thresholds and VAT are injected: `FileChecker(rules=...)`, `CalculatorClient(vat_percent=...)`.
- `EC_QUOTE_RULES_PATH` remains the only override of the path, for tests and for the VPS.

## Hand-over

Owner: values for `production_term_standard`, `production_term_urgent` and `retention_days` (EPIC-1 D8, EPIC-0 D4). Until then the placeholder stops only the features that read them.

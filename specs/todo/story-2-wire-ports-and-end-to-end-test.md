---
id: story-2
title: "Wire the real ports and prove the engine end to end with FakeCalculator"
effort: HIGH
epic: EPIC-0
depends_on: [story-1]
shared_files: [ec_quote/contracts.py, pyproject.toml, README.md]
track: full
models: {implementer: large, qa: standard, ui: none, review: large}
---

# story-2: Wire the real ports and prove the engine end to end with FakeCalculator

**Repository:** ec-quote · **Epic:** [EPIC-0](epic-0-foundation.md) · **Depends on:** story-1

## Summary

The six modules were written in parallel against `ec_quote/contracts.py` and have never run together. This story makes `ec_quote/api/main.py` the composition root: it builds `Settings`, `Rules`, the store, `CalculatorClient`, `FileChecker`, the mockup service, `ShopifyCheckout`, the CRM adapter and the engine, and exposes the inbound, approve, reject and health endpoints. An end to end test drives a scripted conversation through the HTTP layer with fakes for every port and shows a priced offer waiting for approval. Every mismatch between modules found on the way is fixed here, in the module that departs from the contract.

## User Story

As a developer, I want one command that starts the whole service and one test that proves a message becomes an offer, so that every later story builds on something that runs.

## Scope

**In:** `ec_quote/api/main.py` (`create_app(settings, rules, *, overrides)` and the module level `app`); `ec_quote/api/schemas.py`; `ec_quote/agent/` (engine construction from ports); `ec_quote/pricing/fake.py` (`FakeCalculator` as the shared test double); `tests/fakes.py` (fake model that replays scripted tool calls, fake checkout, fake CRM, fake handoff, fixed clock); `tests/e2e/test_offer_journey.py`; `tests/api/test_app_startup.py`; `README.md` (run command); contract fixes in whichever module is wrong.

**Out:** security hardening of the endpoints (story-4); persistence guarantees (story-3); the site chat endpoints (story-11); any change of behaviour that a contract fix does not require.

## Acceptance Criteria

1. `create_app` with complete settings and all real adapters constructs without any network call (asserted with a transport that fails on use) and `GET /health` answers 200.
2. With a required environment variable missing, importing `ec_quote.api.main:app` raises `SettingsError` naming the variable; no endpoint is served.
3. No module other than `ec_quote/api/main.py` constructs `httpx.Client`, an Anthropic client or a `SqliteStore` at import time; a test imports every module under `ec_quote/` with networking patched to fail and passes.
4. End to end, through the HTTP inbound endpoint with the scripted fake model and `FakeCalculator`: message 1 "500 etichete rotunde 5 cm pentru borcane" returns one `text` action asking for the material; message 2 with the material returns, with `shadow_mode` true, one `pending_approval` action with an `approval_id`.
5. `POST` approve for that `approval_id` returns the offer actions; the amounts in them equal, to the cent, the `total`, `total_ex_vat` and tier totals that `FakeCalculator` returned for those choices.
6. The same journey with `shadow_mode` false in the test rules returns the offer actions directly.
7. `FakeCalculator` answering `Unpriced(reason="unknown_material")` leads to a question, not an offer; answering a transport failure twice leads to a `handoff` action and no amount in any text.
8. Tool arguments from the fake model that fail contract validation (width as text, unknown product id) never reach `FakeCalculator`; the call count stays 0 and the engine asks or hands off.
9. `reject` for a pending approval returns 200 and a later approve of the same id returns 409.
10. The suite runs twice in a row green with no network (a session wide fixture blocks sockets).

## Technical Notes

- Overrides in `create_app` are the only test seam; production code has no `if testing`.
- The engine receives `now` from an injected clock; the real clock is created in `main.py`.
- A contract change in `ec_quote/contracts.py` is allowed only when two modules cannot both be made to fit it; record each change in the pull request body.
- Keep the inbound wire format aligned with `specs/todo/crm-ec-quote-bridge.md`.

## Dependencies

story-1 (one `Rules` object to inject).

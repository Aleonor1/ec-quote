---
id: story-2
title: "Wire the real ports and prove the assisted engine end to end with FakeCalculator"
effort: HIGH
epic: EPIC-0
depends_on: [story-1]
shared_files: [ec_quote/contracts.py, ec_quote/api/app.py, pyproject.toml, README.md]
track: full
models: {implementer: large, qa: standard, ui: none, review: large}
---

# story-2: Wire the real ports and prove the assisted engine end to end with FakeCalculator

**Repository:** ec-quote · **Epic:** [EPIC-0](epic-0-foundation.md) · **Depends on:** story-1

## Summary

The backend modules were written in parallel against `ec_quote/contracts.py` and have never run together. `ec_quote/api/main.py` is the composition root and expects a convention from its sibling modules (a `factory(settings)` per port and a `build_engine(...)`); so far it has only run with the demo engine. This story makes it build the real chain (`Settings`, `Rules`, the store, `CalculatorClient`, `FileChecker`, the mockup service, `ShopifyCheckout`, the model client) and an `AssistEngine`, behind the assist routes in `ec_quote/api/app.py`. An end to end test posts a visible WhatsApp conversation to `POST /v1/assist/suggest` with fakes for every port and gets back first a suggested question, then an offer priced by `FakeCalculator`. Every mismatch between modules found on the way is fixed here, in the module that departs from the contract.

## User Story

As a developer, I want one command that starts the backend and one test that proves a conversation becomes a priced suggestion, so that every later story builds on something that runs.

## Scope

**In:** `ec_quote/api/main.py` (the real factory chain, the module level `app`); `ec_quote/api/app.py` and `ec_quote/api/schemas.py` (the four assist routes over `AssistEngine`); a `factory(settings)` in each of `ec_quote/pricing`, `files`, `mockup`, `integrations`; the `AssistEngine` implementation in `ec_quote/agent/` (`suggest`, `create_payment_link`) built from the existing engine parts; `ec_quote/pricing/fake.py`; `tests/fakes.py` (fake model that replays scripted tool calls, fake checkout, fixed clock; `tests/agent/fakes.py` moved or re-exported); `tests/e2e/test_assist_journey.py`; `tests/api/test_app_startup.py`; `README.md` (rewritten for the assisted product, with the run command).

**Out:** token security hardening (story-4); persistence guarantees (story-3); the extension (story-11 to story-14); the `needs_human` rule table (story-7); files and images (EPIC-2); the optional `/v1/chat/*`, `/v1/inbound` and `/v1/approvals/*` routes, which stay as they are and off by default.

## Acceptance Criteria

1. `create_app` with complete settings and all real adapters constructs without any network call (asserted with a transport that fails on use); `GET /health` answers 200; `GET /v1/assist/ping` with a valid token answers 200 with the backend version and the staff name bound to the token.
2. With a required environment variable missing, importing `ec_quote.api.main:app` raises `SettingsError` naming the variable; no endpoint is served.
3. No module other than `ec_quote/api/main.py` constructs `httpx.Client`, an Anthropic client or a `SqliteStore` at import time; a test imports every module under `ec_quote/` with networking patched to fail and passes.
4. `POST /v1/assist/suggest` with a contact and one incoming message "500 etichete rotunde 5 cm pentru borcane" (scripted fake model, `FakeCalculator`) returns an `AssistSuggestion` of kind `question` whose text asks for the material and whose `options` list the catalog's materials for that product.
5. A second call with the same messages plus the customer's answer returns kind `offer`: `offer_lines` holds the requested quantity and the next tiers, the amounts in `text` and `offer_lines` equal to the cent what `FakeCalculator` returned, `can_create_payment_link` is true, `payment_url` is null.
6. Calling `suggest` again with exactly the same messages returns the same `suggestion_id` and text, and the calculator is not called again.
7. `POST /v1/assist/suggestions/{id}/payment-link` for that offer calls the fake checkout once and returns the suggestion with `payment_url` set and the final text containing it; for a suggestion that is not an offer it answers 409.
8. `FakeCalculator` answering `Unpriced(reason="unknown_material")` leads to kind `question`; a transport failure twice leads to kind `needs_human` with a note for staff and no amount in `text`.
9. Tool arguments from the fake model that fail contract validation (width as text, unknown product id) never reach `FakeCalculator`; the call count stays 0.
10. When the last visible message is outgoing (staff already answered) and nothing new came from the customer, the suggestion is kind `none`.
11. The suite runs twice in a row green with no network (a session wide fixture blocks sockets).

## Technical Notes

- The factories passed to `create_app` are the only test seam; production code has no `if testing`. The demo engine stays reachable only through `EC_QUOTE_ENGINE_FACTORY` and is never the default.
- `AssistEngine` reuses the tools, guard, rules and offer text code of the conversational `Engine`; it differs in that it returns one suggestion for a person instead of actions for a channel.
- The engine receives `now` from an injected clock; the real clock is created in `main.py`.
- A change in `ec_quote/contracts.py` is allowed only when two modules cannot both be made to fit it; record each change in the pull request body.

## Dependencies

story-1 (one `Rules` object to inject).

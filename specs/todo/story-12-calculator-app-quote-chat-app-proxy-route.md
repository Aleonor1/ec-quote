---
id: story-12
title: "[calculator-app] Quote chat App Proxy route"
effort: MEDIUM
epic: EPIC-1
depends_on: [story-11]
shared_files: [CLAUDE.md, features/application-architecture.md, CHANGELOG.md]
track: full
models: {implementer: large, qa: standard, ui: none, review: large}
---

# story-12: [calculator-app] Quote chat App Proxy route

**Repository:** `etichetecreative-calculator-app` (NOT ec-quote) · **Epic:** [EPIC-1](epic-1-price-and-offer.md) · **Depends on:** story-11 (its wire contract, `docs/site-chat-contract.md` in ec-quote)

Copy this spec into the calculator app as `docs/spec-quote-chat-proxy.md` before shipping it there. All paths below are in that repository.

## Summary

The site chat runs in the visitor's browser on etichetecreative.ro. It must reach ec-quote without a secret in the browser and without cross origin requests. The calculator app already serves the storefront through the Shopify App Proxy (`/apps/calculator/*` to `/api/storefront/*`, authenticated with `authenticate.public.appProxy`). This story adds one proxy route that relays the three site chat calls to ec-quote server to server with the inbound secret, and nothing else: no business logic, no storage, no model.

## User Story

As a visitor, I want the chat on the site to work like any other part of the page, and as the owner I want the key to the quoting service to stay on the server.

## Scope

**In:** `app/routes/api.storefront.quote-chat.$op.ts` (`session`, `message`, `conversation`); `app/utils/quote-chat.server.ts` (relay client, timeouts, error mapping, per IP rate limit); `tests/routes/api.storefront.quote-chat.test.ts`, `tests/utils/quote-chat.server.test.ts`; `.env.example` or its equivalent (`EC_QUOTE_BASE_URL`, `EC_QUOTE_INBOUND_SECRET`); `features/application-architecture.md` (route list), `CLAUDE.md` (one line under the storefront API), `CHANGELOG.md`.

**Out:** the theme block (story-13); any change to pricing, upload or studio routes; relaying file bytes (the browser uploads through the existing `api.storefront.upload-file` route and sends the URL).

## Acceptance Criteria

1. `POST /api/storefront/quote-chat/session`, `POST .../message` and `GET .../conversation` answer only to requests that pass `authenticate.public.appProxy`; a direct call without a valid proxy signature is refused as the other storefront routes refuse it.
2. Each call is relayed to `EC_QUOTE_BASE_URL` with the header carrying `EC_QUOTE_INBOUND_SECRET`, the body unchanged, and the visitor's IP in the header the contract names; the response body and status are returned unchanged for 200, 401 `invalid_session`, 422 and 429 (with `Retry-After`).
3. The secret and the ec-quote base URL never appear in a response body, a response header or a log line; a test scans all three for the test secret.
4. With `EC_QUOTE_BASE_URL` or `EC_QUOTE_INBOUND_SECRET` unset, every operation answers 503 `{error: "chat_unavailable"}` and makes no outbound request; the app starts normally.
5. An ec-quote timeout (over the configured limit), a connection error or a 5xx answers 502 `{error: "chat_unavailable", retryable: true}` with no stack trace.
6. An operation name other than the three answers 404; a wrong method answers 405; a body over 64 KB answers 413 without relaying.
7. The session token is passed through as the contract says (request header or body) and is never set as a cookie by this route.
8. A per IP limit (requests per minute, constant in one place) answers 429 before relaying.
9. Existing storefront routes and their tests are unchanged and pass; `npm run lint`, `npm run typecheck` and `npm test` are green.

## Technical Notes

- App Proxy requests are signed by Shopify; follow `app/routes/api.storefront.upload-file.ts` for the authentication call and the response helpers.
- Use the platform `fetch` with an `AbortController` timeout; no new dependency.
- The App Proxy strips cookies and adds its own query parameters; do not forward them to ec-quote.
- This is a relay: if a rule is needed (who may chat, what an offer is), it belongs in ec-quote.

## Hand-over

Owner: `EC_QUOTE_BASE_URL` and `EC_QUOTE_INBOUND_SECRET` set on the `calculator-app` Railway service (dashboard, values never in the repository); merge to `master`; `npm run check:deploy` and `npm run e2e:smoke` after deploy.

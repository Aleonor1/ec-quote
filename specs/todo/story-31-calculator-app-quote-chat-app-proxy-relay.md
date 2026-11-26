---
id: story-31
title: "[calculator-app] Quote chat App Proxy relay (only if the owner picks proxy transport)"
effort: MEDIUM
epic: EPIC-4
depends_on: [story-29]
shared_files: [CLAUDE.md, features/application-architecture.md, CHANGELOG.md]
track: full
models: {implementer: large, qa: standard, ui: none, review: large}
---

# story-31: [calculator-app] Quote chat App Proxy relay

**Repository:** `etichetecreative-calculator-app` (NOT ec-quote) · **Epic:** [EPIC-4](epic-4-optional-site-chat-and-crm-lead-sync.md) · **Depends on:** story-29 (its wire contract, `docs/site-chat-contract.md` in ec-quote) · **Conditional:** ship only if EPIC-4 D2 is answered "App Proxy". With "direct", this story is closed unbuilt.

Copy this spec into the calculator app as `docs/spec-quote-chat-proxy.md` before shipping it there. All paths below are in that repository.

> **Open decision.** After the change of direction on 2026-11-26 (assisted quoting in a Chrome extension), the owner has not confirmed that the site chat is still wanted. This story is kept last and must not start before the owner says yes (EPIC-4 D1).

## Summary

ec-quote can serve the site chat to the browser in two ways: directly under CORS, or behind a trusted relay (its proxy mode: `x-ecquote-secret` plus `x-ecquote-client-ip`). With the relay, the browser talks only to etichetecreative.ro: the calculator app already serves the storefront through the Shopify App Proxy (`/apps/calculator/*` to `/api/storefront/*`, `authenticate.public.appProxy`), so the chat becomes same origin, ec-quote's address stays private, and every request is one Shopify signed for the shop. The cost is one more hop and a dependency on the calculator app being up. This story adds that relay and nothing else: no business logic, no storage, no model.

## User Story

As the owner, I want the chat to reach the quoting service only through my shop's own address, so that the service is not open to the whole internet.

## Scope

**In:** `app/routes/api.storefront.quote-chat.$op.ts` (`session`, `message`, `upload`, `poll`, `history`, and `media/<token>`); `app/utils/quote-chat.server.ts` (relay client, timeouts, error mapping, per IP rate limit); `tests/routes/api.storefront.quote-chat.test.ts`, `tests/utils/quote-chat.server.test.ts`; the env example (`EC_QUOTE_BASE_URL`, `EC_QUOTE_INBOUND_SECRET`); `features/application-architecture.md` (route list), `CLAUDE.md` (one line under the storefront API), `CHANGELOG.md`.

**Out:** the theme block (story-30, which only changes its base path setting); any change to pricing, upload or studio routes; any rule about who may chat or what an offer is.

## Acceptance Criteria

1. Each operation answers only to requests that pass `authenticate.public.appProxy`; a direct call without a valid proxy signature is refused as the other storefront routes refuse it.
2. Each call is relayed to `EC_QUOTE_BASE_URL` with `x-ecquote-secret`, the visitor's IP in `x-ecquote-client-ip`, the session token in `x-ecquote-session`, and the body unchanged (JSON, or the multipart stream for `upload`); the response body and status are returned unchanged for 200, 401, 413, 422 and 429 (with `Retry-After`).
3. `media/<token>` streams the image from ec-quote with its content type and a private cache header; `image_url` values in relayed actions are rewritten to the proxy path, so the browser never sees ec-quote's host.
4. The secret and the ec-quote base URL never appear in a response body, a response header or a log line; a test scans all three for the test values.
5. With `EC_QUOTE_BASE_URL` or `EC_QUOTE_INBOUND_SECRET` unset, every operation answers 503 `{error: "chat_unavailable"}` and makes no outbound request; the app starts normally.
6. An ec-quote timeout, a connection error or a 5xx answers 502 `{error: "chat_unavailable", retryable: true}` with no stack trace.
7. An unknown operation answers 404; a wrong method 405; a JSON body over 64 KB or an upload over 25 MB answers 413 without relaying.
8. A per IP limit (requests per minute, one constant) answers 429 before relaying.
9. Query parameters added by the App Proxy (`shop`, `signature`, `timestamp`, `path_prefix`, `logged_in_customer_id`) are not forwarded.
10. Existing storefront routes and their tests are unchanged and pass; `npm run lint`, `npm run typecheck` and `npm test` are green.

## Technical Notes

- Follow `app/routes/api.storefront.upload-file.ts` for the authentication call and the response helpers. Platform `fetch` with an `AbortController` timeout; no new dependency.
- The App Proxy does not pass cookies and may strip `Authorization`; that is why ec-quote accepts `x-ecquote-session`.
- Measure before choosing this transport: a chat turn can take several seconds (model plus calculator). ec-quote answers slow turns with a "se calculează" text and `poll`, which keeps each proxied request short.

## Hand-over

Owner: decision EPIC-4 D2. If proxy: `EC_QUOTE_BASE_URL` and `EC_QUOTE_INBOUND_SECRET` on the `calculator-app` Railway service (dashboard, values never in the repository), `chat_require_secret` on in ec-quote, merge to `master`, `npm run check:deploy` and `npm run e2e:smoke` after deploy.

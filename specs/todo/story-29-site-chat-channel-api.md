---
id: story-29
title: "Site chat channel API hardened for a public browser"
effort: MEDIUM
epic: EPIC-4
depends_on: [story-2, story-3, story-4]
shared_files: [ec_quote/api/app.py, ec_quote/api/schemas.py, ec_quote/api/security.py, ec_quote/config.py]
track: full
models: {implementer: large, qa: standard, ui: none, review: large}
---

# story-29: Site chat channel API hardened for a public browser

**Repository:** ec-quote · **Epic:** [EPIC-4](epic-4-optional-site-chat-and-crm-lead-sync.md) · **Depends on:** story-2, story-3, story-4

> **Open decision.** After the change of direction on 2026-11-26 (assisted quoting in a Chrome extension), the owner has not confirmed that the site chat is still wanted. This story is kept last and must not start before the owner says yes (EPIC-4 D1).

## Summary

The site chat is an optional second channel that reuses the same engine without a person in the loop (`Engine`, not `AssistEngine`). The scaffold already serves it from `ec_quote/api/app.py`: `POST /v1/chat/session`, `POST /v1/chat/message`, `POST /v1/chat/upload`, `GET /v1/chat/poll` and `GET /v1/media/{token}`, with HMAC signed session and media tokens, rate limits, and two ways in: directly from the browser under CORS (`EC_QUOTE_CORS_ORIGINS`), or relayed by a trusted proxy that adds the inbound secret and the visitor's IP (`chat_require_secret`, `x-ecquote-client-ip`). A browser never holds the inbound secret in either mode. This story makes those endpoints safe to expose to the internet, connects them to the real engine and the durable store, lets a reloaded page get its conversation back, and writes the wire contract the theme block (story-30) and the optional proxy (story-31) are built against.

## User Story

As a visitor, I want to ask for a price in the chat on the site and keep my conversation when I move to another page or come back the next day.

## Scope

**In:** `ec_quote/api/app.py` (the chat and media routes, a conversation history route), `ec_quote/api/schemas.py`, `ec_quote/api/security.py`, `ec_quote/api/store.py` (outbox for polled actions on the durable store of story-3), `ec_quote/api/texts.py` (greeting), `ec_quote/config.py` (chat settings), `tests/api/test_chat.py`, `tests/api/test_media_approvals.py`, `docs/site-chat-contract.md` (new, the wire contract).

**Out:** the theme block (story-30); the App Proxy relay (story-31); the demo page under `ec_quote/api/static/` beyond keeping it working with `EC_QUOTE_DEMO=1`; storing uploads in R2 (story-16); WhatsApp.

## Acceptance Criteria

1. `POST /v1/chat/session` returns `{session_token, expires_at, greeting}`; the token is an HMAC signed payload with a random session id and an expiry; the greeting is the fixed Romanian text and, with the default of EPIC-4 D3, says the assistant is automated. Session creation is rate limited per client IP.
2. `POST /v1/chat/message` with a valid token, a client `message_id` and text or a `button_id` returns the actions; the engine is called with `Contact(channel="site", key=<session id>)`.
3. A missing, malformed, expired or tampered token answers 401 (`session_invalid` or `session_expired`) and the engine is not called; a media token is refused as a session token and the reverse (the purpose is part of the signing key).
4. The same `message_id` sent twice returns the same actions and the engine runs once, also across a restart (story-3 `claim_inbound`).
5. `GET /v1/chat/history` (new) returns the stored customer messages and actions of the session in order, so a reloaded page can redraw the thread; it returns nothing of any other session; `GET /v1/chat/poll` keeps returning only actions not yet delivered.
6. Direct mode: with `EC_QUOTE_CORS_ORIGINS` set to the shop's origin, a preflight and a request from that origin succeed and from any other origin carry no CORS allow header; no route allows credentials (cookies); the inbound secret is never needed by the browser.
7. Proxy mode: with `chat_require_secret` on, every chat route answers 401 without `x-ecquote-secret`, and rate limits use `x-ecquote-client-ip`; that header is ignored when the secret is absent.
8. `POST /v1/chat/upload` accepts one file up to the configured size, decides the type from the bytes (`ec_quote/files/sniff.py`), stores it under the session's directory in `EC_QUOTE_DATA_DIR` with a generated name, and passes it to the engine as an `Attachment`; a larger file answers 413, a type outside the allowed set answers 415 or 422, and in both cases nothing remains on disk.
9. Image actions carry `image_url` under `/v1/media/{token}`: the token expires, resolves only to a file under the data directory, and an expired, tampered or path escaping token answers 404; the URL contains no file system path and the response has no directory listing.
10. A slow turn does not hang the request: beyond the configured time the response is a "se calculează" text and the result arrives through `poll`; a test with a slow fake engine shows both.
11. Rate limits per IP, per session, per upload and per poll answer 429 with `Retry-After`; `max_offers_per_contact_per_day` from `Rules` applies per session. With the site chat settings unset, every `/v1/chat/*` route answers 404.
12. A session can state a name, phone or email through explicit fields of the message schema (not parsed from free text by code); they are stored on the `Contact`, validated (phone normalizable to E.164, email syntax), and the session id stays the key.
13. `docs/site-chat-contract.md` lists every chat and media endpoint, its fields, status codes and error codes, and each action kind with one JSON example; a test validates each example against the pydantic schemas.
14. Because no person reviews a site chat reply, every offer on this channel waits for staff approval (`pending_approval`) unless the owner decides otherwise in EPIC-4 D3; the handoff rules of story-7 apply as real handoffs here.

## Technical Notes

- Token keys come from `Settings.signing_key(purpose)`; rotating `EC_QUOTE_INBOUND_SECRET` invalidates sessions, which is acceptable.
- Which transport production uses (direct with CORS, or the calculator app's App Proxy) is EPIC-4 D2, an owner decision. Both must pass these criteria; the block of story-30 works with either.
- `OutboundAction.image_path` stays internal; the API maps it to `image_url`.

## Dependencies

story-3 (idempotency, stored thread), story-4 (auth, limits, log hygiene).

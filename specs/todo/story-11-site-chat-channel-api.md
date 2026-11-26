---
id: story-11
title: "Site chat channel API"
effort: MEDIUM
epic: EPIC-1
depends_on: [story-3, story-4]
shared_files: [ec_quote/api/main.py, ec_quote/api/schemas.py, ec_quote/api/security.py]
track: full
models: {implementer: large, qa: standard, ui: none, review: large}
---

# story-11: Site chat channel API

**Repository:** ec-quote · **Epic:** [EPIC-1](epic-1-price-and-offer.md) · **Depends on:** story-3, story-4

## Summary

The site chat is the first channel. A browser cannot hold `EC_QUOTE_INBOUND_SECRET`, so the browser talks to the storefront App Proxy, the calculator app relays to ec-quote with the secret (story-12), and ec-quote identifies the visitor by a signed session token it issued. This story adds the three endpoints the relay calls: start a session, send a message and get the replies, and read the conversation again after a page reload. Replies are the same `OutboundAction` list every channel gets, with images as URLs the browser can load.

## User Story

As a visitor, I want to ask for a price in the chat on the site and keep my conversation when I move to another page or come back the next day.

## Scope

**In:** `ec_quote/api/site_chat.py` (new router), `ec_quote/api/schemas.py`, `ec_quote/api/security.py` (`Signer` for session and media tokens), `ec_quote/api/main.py` (mount), `ec_quote/api/texts.py` (greeting), `tests/api/test_site_chat.py`, `docs/site-chat-contract.md` (the wire contract story-12 implements).

**Out:** the App Proxy route (story-12) and the theme block (story-13); file upload (the browser uploads through the calculator app's existing storefront upload route and sends the resulting URL; story-19 consumes it); push notifications; WhatsApp.

## Acceptance Criteria

1. `POST /v1/site/sessions` with the inbound secret returns `{session_token, expires_at, greeting}`; the token is an HMAC signed payload with a random session id and expiry; the greeting is the fixed Romanian text and, with the default of EPIC-1 D7, says the assistant is automated.
2. `POST /v1/site/messages` with the secret, a valid token, a client message id and text (or a `button_id`) returns `{actions: [...]}`; the engine is called with `Contact(channel="site", key=<session id>)`.
3. A missing, malformed, expired or tampered token answers 401 `invalid_session` and the engine is not called; a token signed for media cannot be used as a session token (purpose is part of the signature).
4. The same client message id sent twice returns the same actions and the engine runs once.
5. `GET /v1/site/conversation` returns the stored messages and actions of the session in order, so a reloaded page can redraw the thread; it returns nothing of any other session.
6. Image actions carry `image_url`: a path on ec-quote with a media token that expires, served with the right content type; an expired or wrong token answers 404; the URL contains no file system path.
7. A contact given in the chat (name, phone, email through a dedicated action, not free text parsing by code) is stored on the `Contact`; the session id remains the key.
8. Attachments are accepted only as URLs; each goes through the fetcher of story-4 (allow listed host), otherwise the message is answered with the fixed "nu am putut citi fișierul" text.
9. Rate limits: per session and per relayed client IP (header set by the relay), 429 with `Retry-After`; `max_offers_per_contact_per_day` applies per session.
10. Without the inbound secret every endpoint answers 401, whatever the token.
11. `docs/site-chat-contract.md` lists the three endpoints, fields, status codes and the action kinds with one example each; a test parses its JSON examples against the pydantic schemas.

## Technical Notes

- Request and response are synchronous: the reply to a message carries the actions. A slow turn (model plus calculator) is bounded by a timeout after which the reply is a "se calculează" text and the result is fetched by `GET /v1/site/conversation`.
- Token secrets are derived from `Settings.signing_key(purpose)`.
- `OutboundAction.image_path` stays internal; the API maps it to a URL. If `ec_quote/contracts.py` gains `image_url`, do it here and say so in the pull request.

## Dependencies

story-3 (idempotency, stored thread), story-4 (auth, fetcher, limits).

---
id: story-13
title: "[calculator-app] Quote chat theme block"
effort: HIGH
epic: EPIC-1
depends_on: [story-11]
shared_files: [extensions/calculator/locales/ro.json, e2e/UI-MAP.md, CHANGELOG.md]
track: full
models: {implementer: standard, qa: standard, ui: standard, review: standard}
---

# story-13: [calculator-app] Quote chat theme block

**Repository:** `etichetecreative-calculator-app` (NOT ec-quote) · **Epic:** [EPIC-1](epic-1-price-and-offer.md) · **Depends on:** story-11 (the wire contract `docs/site-chat-contract.md` in ec-quote, and a reachable ec-quote for the e2e check)

Copy this spec into the calculator app as `docs/spec-quote-chat-block.md` before shipping it there. All paths below are in that repository.

## Summary

The visitor needs a place on the site to write. ec-quote ships a demo widget (`ec_quote/api/static/widget.js`) that proves the API; the shop needs the real thing in its theme. This story adds a chat block to the existing theme app extension `extensions/calculator`: a button in the corner that opens a panel where the visitor writes, attaches a file, sees the assistant's questions, the offer image and price, and a button that takes them to pay. It speaks the site chat contract to a base address set in the block's settings: ec-quote's public address (direct transport) or the shop's own App Proxy path (story-12). During the test period it shows only when the page URL carries a preview parameter, so the owner and staff can try it on the live store before customers see it.

## User Story

As a visitor on a phone, I want to describe the labels I need in my own words and get a price and a payment link without filling in the calculator.

## Scope

**In:** `extensions/calculator/blocks/quote-chat.liquid` (app embed block, `target: body`; settings: enabled, preview only, chat base address, position); `extensions/calculator/assets/quote-chat.js`, `quote-chat.css`; `extensions/calculator/locales/ro.json` (strings); `tests/storefront/quote-chat.test.ts` (jsdom); `e2e/pages/QuoteChat.ts`, `e2e/quote-chat.spec.ts`, `e2e/UI-MAP.md`; `CHANGELOG.md`.

**Out:** the proxy route (story-12); making the block public (EPIC-4); the admin UI; any change to `calculator.js`; any change in ec-quote.

## Acceptance Criteria

1. With the embed enabled and "preview only" on, the launcher is absent from the DOM on a page without the preview parameter and present with it; with "preview only" off it is present on every page. With an empty chat base address the launcher is absent.
2. Opening the panel calls `session` once, shows the greeting from the response, and keeps the session token in `localStorage`; reopening on another page calls `history` and redraws the same thread without a new session.
3. Sending a message shows it at once, disables the send button until the reply arrives, shows a typing indicator, and then renders each returned action: `text` as plain text (never as HTML), `image` as an image with alt text, `buttons` as buttons whose click sends the `button_id`, `handoff` as the fixed "un coleg vă răspunde" notice, a payment link as a button that opens the Shopify invoice URL. A "se calculează" reply starts polling until the result arrives or a time limit passes.
4. Text from the server or from the visitor containing `<script>` or an `onerror` attribute is displayed as characters and executes nothing (jsdom test).
5. A 429 shows "Prea multe mesaje, încercați peste un minut", a 502 or 503 or a network failure shows "Chatul nu e disponibil acum" with a retry button, an expired session (401) starts a new session and resends the message once; no error shows a status code or a stack.
6. A file is attached with the same accepted types and 25 MB limit as the calculator's upload zone and sent through the contract's `upload` operation with a progress indication; a rejected type or size shows the calculator's existing message for it.
7. The panel is usable at 390x844 and 1440x900: nothing overflows the viewport, the input stays above the on screen keyboard, the launcher does not cover the cart button or the calculator's add to cart button on a product page.
8. Accessibility: the launcher and panel are reachable and operable by keyboard, focus moves into the panel on open and back on close, Escape closes it, new messages are announced through a polite live region, axe reports no serious or critical violation.
9. All visible strings come from `locales/ro.json`, are Romanian, and contain no em dash and no emoji; the block loads its script with `defer` and makes no request on pages where the launcher is absent or until the panel is first opened.
10. The script sends requests only to the configured chat base address, never sends cookies (`credentials: "omit"`), and sends the token in the header the contract names.
11. `e2e/quote-chat.spec.ts`, read only part tagged `@smoke`: on a product page with the preview parameter the launcher opens the panel and the greeting appears. A send test exists only under `@write` gated on `E2E_WRITE=1`. Selectors go through `e2e/pages/QuoteChat.ts`; no `data-testid`.
12. `npm run lint`, `npm run typecheck`, `npm test` green; existing e2e specs unchanged.

## UI Notes

- Uses the extension's existing fonts and CSS variables; class prefix `.qc-`.
- States: closed, opening (loading), empty (greeting only), conversation, waiting for reply, uploading, error, handed off (input stays enabled; messages are passed to staff).
- A footer line says the assistant is automated and that a colleague can take over, matching ec-quote's disclosure rule.

## Technical Notes

- An app embed block is switched on in the theme editor; it ships with `shopify app deploy --allow-updates`, separately from the server.
- The demo widget in ec-quote is a reference for the contract, not code to copy blindly: the block must follow the extension's conventions and i18n.
- Direct transport needs the shop's origin in `EC_QUOTE_CORS_ORIGINS` on the VPS. No secret is present in the block or its assets in either transport.

## Hand-over

Owner: `shopify app deploy --allow-updates`, enabling the embed in the theme editor with "preview only" on and the chat base address filled, and trying the chat with the preview link.

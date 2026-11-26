---
id: EPIC-1
title: "Assisted quoting in the extension (text only)"
status: proposed
prompt: "Owner, 2026-11-26: WhatsApp is served by a Chrome extension that suggests replies on WhatsApp Web; a person inserts and sends; nothing is sent automatically"
---

# EPIC-1: Assisted quoting in the extension

## Outcome

Aleonor and Roxana answer price requests in WhatsApp Web with a panel beside the chat. When a customer writes what they need, the panel shows the next thing to say: a short question for what is missing, or the offer with the exact site price, the next quantity tiers, the validity, all as text ready to insert. One click puts the text in the message box; the person reads it, changes it if they want, and presses Send. When the customer agrees, one click creates the Shopify payment link for exactly that price. When a request is outside the rules, the panel says it is theirs to handle and why. The extension is installed on their two browsers and tells them when WhatsApp changed and it cannot read the page.

## Users and roles

- Staff (Aleonor, Roxana): use the panel; each has their own token.
- The customer: sees only ordinary WhatsApp messages sent by a person.
- The owner: decides thresholds and wording; installs and publishes the extension.

## Journeys

1. J1 Offer: the customer writes "am nevoie de 500 de etichete rotunde de 5 cm pentru borcane"; the panel suggests one question about the material with the options; the person inserts and sends; the customer answers; the panel shows the offer for 500 and the next two tiers, without and with VAT, valid 7 days; the person inserts and sends.
2. J2 Payment link: the customer says "rămâne 1000"; the panel shows the offer for 1000; the person clicks "Link de plată", inserts the reply with the link and sends.
3. J3 Not for the assistant: a banner of 3 metres, an offer over the threshold, a request for a discount, a complaint; the panel shows "de văzut de om" with the reason and what was understood, and proposes no price text.
4. J4 Staff already answered: the last message in the chat is ours; the panel suggests nothing until the customer writes again.
5. J5 Calculator down: the panel says the price cannot be computed now; no estimate.
6. J6 WhatsApp changed: the reader cannot find the messages; the panel says which part it cannot read and offers the self-test; the staff keep working without suggestions.
7. J7 Install: a staff member installs the extension, enters the backend address and token, sees their name, and gets a first suggestion.

## Scope

**In:** `needs_human` rules; the suggestion guard and evaluation set; the offer as text; the payment link; the extension's reader with its selector map and self-test; the panel, insert and payment link click; privacy and token handling; packaging, install and updates.

**Later:** files, mockups and the offer image (EPIC-2); reminders and metrics (EPIC-3); English.

**Out:** sending, scheduling or bulk actions of any kind; reading chats the person did not open; groups; the Meta Cloud API; products outside the calculator; discounts.

## Design

- Backend: `AssistEngine.suggest(contact, messages, now)` returns one `AssistSuggestion` (`reply`, `question`, `offer`, `needs_human`, `none`), idempotent on message ids. Price only from `CalculatorClient`; tiers are the next `upsell_tier_count` visible tiers, each priced by its own call. Policy decided by code (`evaluate_needs_human`), text checked by `ec_quote/agent/guard.py`. `create_payment_link` runs only on a person's click.
- Extension (Manifest V3, `extension/`): content script on web.whatsapp.com reads the open chat through `content/selectors.js`; the panel shows suggestions; the service worker (`background/`) is the only part with the token and the only part that calls the backend.
- The page interaction line: read the open chat, insert text into the composer. Nothing else (see `docs/dev-rules.md`, "The extension").

### Integrations

| System | Purpose | Auth | Env vars | Failure behaviour |
| --- | --- | --- | --- | --- |
| Calculator app | Price, catalog | `X-Sync-Secret` | `CALCULATOR_BASE_URL`, `CALCULATOR_SYNC_SECRET` | One retry, then a `needs_human` suggestion saying the price cannot be computed |
| Shopify Admin | Draft Order | Admin token | `SHOPIFY_SHOP_DOMAIN`, `SHOPIFY_ADMIN_TOKEN` | No link; a Romanian error in the panel; the offer stays available |
| Anthropic API | Understanding | API key | `ANTHROPIC_API_KEY`, `EC_QUOTE_MODEL` | One retry, then "nimic de sugerat acum" with the reason for staff |
| WhatsApp Web | The page the extension reads | The staff member's own session | none | A named "cannot read" state; no suggestion |

## Decisions

| # | Decision | Chosen | Why | Bucket |
| --- | --- | --- | --- | --- |
| D1 | Who decides `needs_human` | Code, from rules and state | The model must not decide policy | Decided |
| D2 | Who sends | Always a person | Owner's direction; also keeps the number inside WhatsApp's tolerance | Decided |
| D3 | Where selectors live | One file, with a self-test | The page changes without notice | Decided |
| D4 | Checkout object | Draft Order on the permanent variant with `priceOverride` | Orders look like site orders to production | Decided |
| D5 | Value threshold | `handoff_value_threshold_ron_ex_vat` = 3000 | Owner's plan | Reserved, to confirm |
| D6 | Validity | 7 days | Owner's plan | Reserved, to confirm |
| D7 | Products | Calculator stickers and labels only | Owner's plan | Reserved, to confirm |
| D8 | Tone of suggested replies | The tone the staff use today, short | A person sends them under their own name | Reserved, open |
| D9 | "Are you a bot?" | No suggestion; the person answers | Honest and simple | Reserved, to confirm |
| D10 | Distribution | Unpacked first, then a private Chrome Web Store listing | Automatic updates when the page changes | Reserved, open (developer account) |

## Risks

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| WhatsApp Web changes its DOM and the reader breaks | High, recurring | Medium: no suggestions until the map is fixed; no wrong ones | story-11: one selector map, named failure states, self-test, fixtures; story-14: fast unpacked update path and the runbook section |
| WhatsApp objects to third party tooling on WhatsApp Web | Low to medium | High: the number | Scope held to reading the open chat and inserting text a person sends; no sending, no bulk, no background activity; tests that scan for send automation |
| A wrong price reaches a customer | Low | Very high | Price only from the calculator; guard before the panel; audit harness (story-6) and weekly audit (story-26) |
| A person trusts a suggestion without reading | Medium | Medium | `needs_human` instead of risky suggestions; staff notes separate from customer text; edits measured (story-25) |
| Customer conversations leak | Low | High | story-13: minimal data, HTTPS to one host, nothing stored in the extension, per person revocable tokens, retention |

## Story map

| Story | Title | Where | Depends on | Wave | Effort |
| --- | --- | --- | --- | --- | --- |
| [story-7](story-7-needs-human-rules-decided-by-code.md) | When a person must decide: needs_human rules decided by code | backend | story-2, story-3 | 1 | MEDIUM |
| [story-8](story-8-suggestion-guard-and-conversation-evals.md) | Suggestion guard and the conversation evaluation set | backend | story-2 | 1 | HIGH |
| [story-9](story-9-offer-suggestion-text-price-tiers-validity.md) | Offer suggestion as text: price, tiers and validity | backend | story-2 | 1 | MEDIUM |
| [story-10](story-10-payment-link-on-one-click.md) | Payment link on one click: Draft Order at the exact calculator price | backend | story-2, story-9 | 2 | HIGH |
| [story-11](story-11-extension-whatsapp-web-reader-selector-map-and-self-test.md) | Extension: resilient WhatsApp Web reading with one selector map and a self-test | extension | (none) | 1 | HIGH |
| [story-12](story-12-extension-suggestion-panel-and-insert.md) | Extension: suggestion panel, insert into the composer, payment link | extension | story-2, story-11 | 2 | HIGH |
| [story-13](story-13-extension-privacy-and-token-handling.md) | Extension: privacy, what leaves the browser, and token handling | extension, backend | story-12 | 3 | MEDIUM |
| [story-14](story-14-extension-packaging-install-and-updates.md) | Extension: packaging, installing unpacked or from a private Chrome Web Store listing, updates | extension, backend | story-12, story-13 | 4 | MEDIUM |

**Parallelism:** 8 stories, critical path 4 (11, 12, 13, 14), widest wave 4. Waves are counted inside the epic; the backend stories also need EPIC-0 merged. story-11 can start on day one.

## Hand-over

- Owner: decisions D5 to D10; the Shopify custom app token with `write_draft_orders`, `read_products`, `read_orders`; one run of the checkout live check.
- Owner and staff: an hour on a real WhatsApp Web session to capture page fixtures; the Chrome Web Store developer account and the staff's Google accounts.

## References

- Calculator app: `docs/spec-crm-line-price.md` (contract, 422 reasons, `properties` order), `features/application-architecture.md` (line item properties).
- Chrome extensions: Manifest V3, side panel, optional host permissions, private and unlisted Web Store distribution (official Chrome developer documentation; to be linked by the implementing story).

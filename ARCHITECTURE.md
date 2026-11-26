# ec-quote: orientation map

Snapshot: 2026-11-26, scaffold day, after the owner's change of direction: WhatsApp is served by a Chrome extension that suggests replies on WhatsApp Web; nothing is sent automatically and nothing goes through the Meta Cloud API. Re-run `/project-overview` after EPIC-0 merges. Rules: `docs/dev-rules.md`. Backlog: `specs/todo/`. Owner's summary in Romanian: `docs/plan.md`.

## What it is

A backend that turns a conversation into a suggested reply, and a browser extension that shows that suggestion to the staff member inside WhatsApp Web. The language model understands and proposes; deterministic tools produce every number and every artifact; a person reads, edits and sends.

```
WhatsApp Web (staff browser)
  content script reads the open chat ─▶ extension service worker
        │ POST /v1/assist/suggest   (X-EcQuote-Assist-Token, visible messages with their ids)
        │ POST /v1/assist/upload    (a customer attachment the staff member chose to check)
        ▼
  ec-quote backend ─▶ AssistEngine.suggest ─▶ model loop (understand, propose)
        │                       │ tool calls, validated against contracts and the catalog
        │                       ▼
        │        get_price / get_price_tiers   ec_quote/pricing      ─▶ calculator app
        │        check_file                    ec_quote/files
        │        make_cutline, make_mockup     ec_quote/mockup       ─▶ calculator app (cut line, EPIC-2)
        │        guard (amounts, claims, deadlines)
        ▼
  AssistSuggestion { kind, text, options, offer_lines, image, note_for_staff, can_create_payment_link }
        ▼
  side panel: the staff member reads it, clicks Insert (text goes into the composer), edits, presses Send
        │ optional click: POST /v1/assist/suggestions/{id}/payment-link ─▶ create_checkout ─▶ Shopify Draft Order
        ▼
  the final text with the payment link is inserted; the person sends it
```

## Modules

| Path | Port (`ec_quote/contracts.py`) | Notes |
| --- | --- | --- |
| `ec_quote/pricing/` | `PricingPort` | `client.py` (`CalculatorClient`: `X-Sync-Secret`, catalog TTL cache, one retry), `catalog.py`, `errors.py`, `fake.py` (`FakeCalculator` for tests) |
| `ec_quote/files/` | `FilePort` | `sniff.py` (type from magic bytes), `checker.py` (`FileChecker`, never raises, no network), `problems.py` (stable problem codes) |
| `ec_quote/mockup/` | `MockupPort` | `service.py`, `templates.py` (strict manifest, selection by context keywords), `warp.py`, `compose.py`, `offer.py` (the offer image, 1080x1350), `formatting.py`, bundled DejaVu fonts; templates under `templates/mockups/` |
| `ec_quote/agent/` | `AssistEngine`, `Engine` | `engine.py`, `model.py` (model loop), `tools.py`, `prompts.py`, `offer.py` (texts with numbers, composed by code), `guard.py` (amounts, percentages, deadlines, material claims), `rules.py` (`Rules` from `config/rules.json`), `store.py` (`ConversationStore`: SQLite and in memory) |
| `ec_quote/integrations/` | `CheckoutPort`, `CrmPort`, `HandoffPort` | `shopify.py` (`ShopifyCheckout`: Draft Order on the product's permanent variant with `priceOverride` = calculator total, line properties from the calculator, `get_status`); `crm.py` (optional, EPIC-4) |
| `ec_quote/api/` | none | `app.py` (`create_app`), `main.py` (composition root), `security.py`, `fetcher.py`, `ratelimit.py`, `logutil.py`, `schemas.py`. Assist routes: `POST /v1/assist/suggest`, `POST /v1/assist/upload`, `POST /v1/assist/suggestions/{id}/payment-link`, `GET /v1/assist/ping`. Also present from scaffold day and optional: `/v1/chat/*` and `static/` (site chat), `/v1/inbound` and `/v1/approvals/*` (written for a CRM driven flow that is no longer planned) |
| `ec_quote/config.py` | | `Settings` from environment, fails closed, secrets as `SecretStr` |
| `extension/` | | Manifest V3. Content script on `https://web.whatsapp.com/*` only; one selector map file for everything it reads from the page; a self-test; a side panel; a service worker that is the only part talking to the backend. Being written; its layout is fixed by story-11 to story-14. |

`AssistEngine` contract: `suggest(contact, messages, now)` is idempotent on the WhatsApp message ids, so the extension can call it again whenever the visible conversation changes; `create_payment_link(suggestion_id, staff, now, edited_text)` creates the Draft Order and returns the final text with the link. `AssistSuggestion.kind` is one of `reply`, `question`, `offer`, `needs_human`, `none`.

State: SQLite under `EC_QUOTE_DATA_DIR` (conversations keyed by the WhatsApp contact, suggestions, offers). No other datastore. The extension keeps no conversation data.

## What already exists elsewhere

Verified in code on 2026-11-26.

| System | Capability | Endpoint or file | Status and use here |
| --- | --- | --- | --- |
| Calculator app | Exact site price and line item properties for one line, server to server | `POST /api/sync/line` (`app/routes/api.sync.line.ts`, `app/utils/crm-line-price.server.ts`, `docs/spec-crm-line-price.md`) | Exists. 200 `priced`, 422 `unpriced` with a reason code, 503 retryable. Parity with `calculator.js` covered by 130 tests there. The only price source. |
| Calculator app | Full calculator configuration | `GET /api/sync/calculator-config` (`app/routes/api.sync.calculator-config.ts`) | Exists. Sticker mode products only; `fixed`, `bundle` and `area` products are absent, so they are `not_in_calculator`. |
| Calculator app | Presigned upload to R2 with a public URL | `POST /api/sync/upload-url` (`app/routes/api.sync.upload-url.ts`) | Exists. PNG, JPG, PDF, SVG, AI, 25 MB, keys under `crm/`, kept 365 days. Used for artwork on the order (story-16). |
| Calculator app | Artwork inspection | `POST /api/sync/artwork-inspect` (`app/utils/artwork-inspect.server.ts`) | Exists for PDF and PDF compatible AI only, and only for files in the app's own storage. A raster answers 422 `not_pdf`. |
| Calculator app | Cut line geometry (Contur Studio) | `extensions/calculator/assets/contur-studio.js` | Browser only. See "Headless cut line". |
| Calculator app | Production PDF from an approved proof | `app/utils/production-pdf.server.ts`, `bezier-fit.server.ts`, `emboss-trace.js` | Exists on the server, but consumes cut paths; it does not compute them. |
| Calculator app | Order webhooks | `shopify.app.toml`: `orders/create`, `orders/fulfilled`, `orders/cancelled` | Exists. No `orders/paid`. ec-quote learns about payment from the Draft Order status (story-24). |
| CRM | WhatsApp Cloud API webhook, Coexistence, inbox, templates, `ai_auto` send path | `services/inbox/src/routes/whatsappWebhook.ts`, `whatsappCoexistenceService.ts`, `conversationSendService.ts`, `whatsappTemplateService.ts` | Exists. Not used by this project any more: staff answer in WhatsApp Web and a person sends. |
| CRM | Lead intake for a service caller | `specs/todo/crm-ec-quote-bridge.md` | Missing. Optional and later; only the lead upsert is planned (story-28). |

## Headless cut line

A cut line cannot be produced on the server today.

- The geometry (`edt`, marching squares `contours`, `polysMm`, `smoothPolys`, `shapePolys`, `fillHoles`, joining parts, the 4 mm neck and 2 mm inner radius rules) lives inside the browser IIFE of `extensions/calculator/assets/contur-studio.js`, closed over in `mount()` and tied to DOM canvases. Only a few helpers are exposed (`ConturStudio.lib`).
- PDF pages are rendered in the browser with pdf.js from a CDN; background removal runs in the browser with transformers.js.
- The server side starts after a proof was approved: `buildProductionPdf` receives `ProofData.paths.cut` already computed. `/crm-studio` is the same browser code in an iframe.

Missing for a headless `make_cutline` (story-21, calculator app): extract the geometry into a plain module without DOM (the pattern of `pricing-core.js` and `emboss-trace.js`); a server input adapter with `sharp` and Ghostscript (both in the app's Docker image); a route `POST /api/sync/cutline` returning `ProofData` compatible paths; a parity test against the studio in jsdom. There is no headless background removal: an image with an opaque background gets a shape cut or goes to a person.

Until story-21 ships, `make_cutline` in ec-quote produces a preview outline for the mockup only, labelled as indicative.

## The extension and WhatsApp Web

- WhatsApp Web has no public API for this and its DOM changes without notice. Everything the content script reads (the open chat's contact, message rows, their ids, direction, text, attachment markers, the composer) goes through one selector map file, and a self-test reports which selectors still match. When a selector breaks, the panel says so and suggests nothing, rather than reading the wrong thing.
- Scope of page interaction, and nothing more: read the conversation the staff member has open; insert text into the composer; attach the offer image to the composer; download an attachment the staff member pointed at. No sending, no navigation between chats, no bulk actions, no reading of other chats, no background activity when the panel is closed.
- What leaves the browser: the visible messages of the open chat (id, direction, text, time), the contact's phone and display name, attachments the staff member chose to check, and the staff token. Only to the configured backend, over HTTPS.
- What the extension stores: the backend address and the staff token (`chrome.storage.local`). No message text, no customer data, no history.
- Distribution: unpacked during development; a private Chrome Web Store listing for the staff afterwards.

## Checkout and payment

`create_payment_link` calls `create_checkout`: a Shopify Draft Order with one unit of the product's permanent variant, `priceOverride` equal to `PriceQuote.total`, the calculator's `properties` as line attributes, the artwork URL, and tags. The order is then read by the CRM and production like a site order. Paid orders are matched back to offers by a sweep of Draft Order status (story-24).

## Reminders and measurement

Reminders at the hours in `follow_up_hours` are shown to staff in the extension for offers with no answer; a person decides whether to write. Metrics come from what the backend already sees: time from the customer's message to the suggestion, and what happened to each suggestion (sent unchanged, edited, ignored), derived by comparing the next outgoing message the extension reports with the suggested text.

## Environment

Names only, values come from the owner: `CALCULATOR_BASE_URL`, `CALCULATOR_SYNC_SECRET`, `ANTHROPIC_API_KEY`, `EC_QUOTE_MODEL`, `SHOPIFY_SHOP_DOMAIN`, `SHOPIFY_ADMIN_TOKEN`, `EC_QUOTE_DATA_DIR`, `EC_QUOTE_PUBLIC_BASE_URL`, and the per staff assist tokens (the setting is named by story-4 in `ec_quote/config.py`). `EC_QUOTE_INBOUND_SECRET`, `EC_QUOTE_CORS_ORIGINS`, `CRM_BASE_URL` and `CRM_API_SECRET` matter only for the optional EPIC-4.

## Related documents

- `CLAUDE.md`: commands, module map, non negotiable rules.
- `docs/dev-rules.md`: development rules, backend and extension.
- `docs/plan.md`: what changed, epics, decisions and credentials (Romanian).
- `specs/todo/epic-*.md`: one design per epic with its story map.

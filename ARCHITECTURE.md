# ec-quote: orientation map

Snapshot: 2026-11-26, scaffold day (six modules written in parallel, not yet wired together). Re-run `/project-overview` after EPIC-0 merges. Rules: `docs/dev-rules.md`. Backlog: `specs/todo/`. Owner's summary in Romanian: `docs/plan.md`.

## What it is

One quoting engine for two channels. The customer writes freely and receives a price, a mockup and a payment link. The language model understands and asks; deterministic tools produce every number and every artifact.

```
InboundMessage ──▶ Engine.handle ──▶ model loop (understand, ask)
                        │                 │ tool calls, validated against contracts and the catalog
                        │                 ▼
                        │      get_price / get_price_tiers   ec_quote/pricing      ─▶ calculator app
                        │      check_file                    ec_quote/files
                        │      make_cutline, make_mockup     ec_quote/mockup       ─▶ calculator app (cut line, EPIC-2)
                        │      create_checkout               ec_quote/integrations ─▶ Shopify Admin (Draft Order)
                        │      upsert_lead, handoff          ec_quote/integrations ─▶ CRM
                        ▼
              outbound guard (amounts, claims, deadlines) ─▶ OutboundAction[] ─▶ the channel delivers
```

## Modules

| Package | Port (`ec_quote/contracts.py`) | Notes |
| --- | --- | --- |
| `ec_quote/pricing/` | `PricingPort` | `client.py` (`CalculatorClient`: `X-Sync-Secret`, catalog TTL cache, one retry), `catalog.py`, `errors.py`, `fake.py` (`FakeCalculator` for tests) |
| `ec_quote/files/` | `FilePort` | `sniff.py` (type from magic bytes), `checker.py` (`FileChecker`, never raises, no network), `problems.py` (stable problem codes) |
| `ec_quote/mockup/` | `MockupPort` | `templates.py` (strict manifest, selection by context keywords), `warp.py`, `formatting.py`, bundled DejaVu fonts |
| `ec_quote/agent/` | `Engine` | `model.py` (model loop), `guard.py` (checks amounts, percentages, deadlines, material claims in model text), `rules.py` (`Rules` from `config/rules.json`, business hours, production term), `store.py` (`ConversationStore`: SQLite and in memory; `claim_inbound` for idempotency; approvals) |
| `ec_quote/integrations/` | `CheckoutPort`, `CrmPort`, `HandoffPort` | `shopify.py` (`ShopifyCheckout`: Draft Order on the product's permanent variant with `priceOverride` = calculator total, line properties from the calculator, `get_status`) |
| `ec_quote/api/` | none | FastAPI composition root (`main.py`), `security.py` (constant time secret compare, HMAC signed tokens for chat sessions and media links) |
| `ec_quote/config.py` | | `Settings` from environment, fails closed, secrets as `SecretStr` |

State: SQLite under `EC_QUOTE_DATA_DIR` (conversations, message log, approvals). No other datastore.

## What already exists elsewhere

The original plan assumed more had to be built. Verified in code on 2026-11-26.

| System | Capability | Endpoint or file | Status |
| --- | --- | --- | --- |
| Calculator app | Exact site price and line item properties for one line, server to server | `POST /api/sync/line` (`app/routes/api.sync.line.ts`, `app/utils/crm-line-price.server.ts`, `docs/spec-crm-line-price.md`) | Exists. 200 `priced`, 422 `unpriced` with a reason code, 503 retryable. Parity with `calculator.js` proven by 130 tests. |
| Calculator app | Full calculator configuration (products, shapes, materials, sizes, limits, options, tiers, settings) | `GET /api/sync/calculator-config` (`app/routes/api.sync.calculator-config.ts`, `docs/spec-crm-calculator-config.md`) | Exists. Sticker mode products only; `fixed`, `bundle` and `area` products are absent, so they are `not_in_calculator`. |
| Calculator app | Presigned upload to R2 with a public URL | `POST /api/sync/upload-url` (`app/routes/api.sync.upload-url.ts`) | Exists. PNG, JPG, PDF, SVG, AI, 25 MB, keys under `crm/`, kept 365 days. |
| Calculator app | Artwork inspection | `POST /api/sync/artwork-inspect` (`app/routes/api.sync.artwork-inspect.ts`, `app/utils/artwork-inspect.server.ts`) | Exists for PDF and PDF compatible AI only (pages, fonts, Canva, page size, minimum image PPI, SVG of page 1). Only files already in the app's own R2 storage. A raster answers 422 `not_pdf`. |
| Calculator app | Cut line geometry (Contur Studio) | `extensions/calculator/assets/contur-studio.js` | Browser only. See "Headless cut line" below. |
| Calculator app | Production PDF from an approved proof | `app/utils/production-pdf.server.ts` (`buildProductionPdf`), `app/utils/bezier-fit.server.ts`, `app/utils/emboss-trace.js` | Exists on the server, but consumes cut paths; it does not compute them. |
| Calculator app | Contur Studio as an isolated page for the CRM | `GET /crm-studio` (`app/routes/crm-studio.ts`, `app/utils/crm-studio.server.ts`, `app/crm-studio/bridge.js`) | Exists. An iframe page driven by `postMessage`; needs a browser. |
| Calculator app | Storefront theme extension and App Proxy | `extensions/calculator/blocks/*.liquid`, `app/routes/api.storefront.*.ts` | Exists. No chat block and no chat proxy route yet. |
| Calculator app | Order webhooks | `shopify.app.toml`: `orders/create`, `orders/fulfilled`, `orders/cancelled` | Exists. No `orders/paid` subscription. |
| CRM | Meta WhatsApp Cloud API webhook (signature, anti replay, per event isolation) | `services/inbox/src/routes/whatsappWebhook.ts` | Exists. |
| CRM | Coexistence with the phone app: staff echoes, 180 day history import, contact names | `services/inbox/src/services/whatsappCoexistenceService.ts` (story-197) | Exists. |
| CRM | Unified inbox, conversations, lead matching | `services/inbox/src/services/conversationService.ts`, `whatsappService.ts` (story-183, story-184) | Exists. |
| CRM | Send text, image by URL, approved template | `packages/integrations/src/whatsappBusinessClient.ts` (`sendText`, `sendImage`, `sendTemplate`) | Exists. No interactive buttons message. |
| CRM | Send path for automatic messages (24 hour window, kill switch, daily cap, DNC, audit) | `services/inbox/src/services/conversationSendService.ts` (`sentBy: 'ai_auto'`), `inboxAutoReplyService.ts` (story-187) | Exists. |
| CRM | Templates with a paid monthly cap | `services/inbox/src/services/whatsappTemplateService.ts`, `whatsappTemplateSendService.ts` (story-185) | Exists. 409 `template_cap_reached` when the cap is used. |
| CRM | AI reply drafts with approve, edit, reject | `services/inbox/src/services/aiReplyDraftService.ts`, `draftDelivery.ts` (story-187) | Exists. The natural home of the shadow mode approval. |
| CRM | Handover to a human | `services/inbox/src/services/inboxHandoverService.ts` (`raiseHandover`) | Exists. |
| CRM | Inbound media | `services/inbox/src/services/whatsappService.ts` stores `mediaId` and `mediaMime` | Partial. The file itself is not downloaded from Meta. |
| CRM | Client of the calculator sync API | `packages/integrations/src/railwayQuoteClient.ts` (`QUOTE_SYNC_SECRET`) | Exists. Same secret ec-quote uses as `CALCULATOR_SYNC_SECRET`. |
| CRM | Forwarding messages to ec-quote and delivering its actions | `specs/todo/crm-ec-quote-bridge.md` in this repository | Missing. The CRM stories of EPIC-3. |

## Headless cut line

Question: can a cut line be produced on the server today, without a browser? No.

- The geometry (distance transform `edt`, marching squares `contours`, `polysMm`, `smoothPolys`, `shapePolys`, `fillHoles`, joining separate parts, the 4 mm neck and 2 mm inner radius rules) lives inside the browser IIFE of `extensions/calculator/assets/contur-studio.js`. Only a few helpers are exposed (`ConturStudio.lib`: `edt`, `thinParts` and others); `contours`, `polysMm`, `shapePolys`, `fillHoles` and the orchestration are closed over inside `mount()`, tied to DOM canvases (`document.createElement("canvas")`, `getImageData`) and to the studio state.
- PDF pages are rendered in the browser with pdf.js from a CDN. Background removal runs in the browser with transformers.js (WebGPU or WASM, loaded from esm.sh).
- The server side starts after the customer approved a proof: `buildProductionPdf` receives `ProofData.paths.cut` already computed by the browser.
- `/crm-studio` is the same browser code in an iframe.

Missing for a headless `make_cutline` (story-21, calculator app):

1. Extract the geometry kernel into a plain module without DOM (the pattern already used for `app/utils/pricing-core.js` and `app/utils/emboss-trace.js`, with a generated storefront copy), so the browser and the server run the same code.
2. A server input adapter: artwork to an RGBA alpha mask on the millimetre grid with `sharp`, PDF and AI page 1 rasterized with Ghostscript (both already in the app's Docker image).
3. A route `POST /api/sync/cutline` (`X-Sync-Secret`, own storage URL guard) that returns `ProofData` compatible geometry (`design`, `paths.cut`, `paths.bleed`, `paths.liner`) and a preview PNG.
4. A parity test: the same fixture through the studio in jsdom (`tests/helpers/canvas-shim.ts`) and through the route gives the same cut path within a tolerance.
5. No headless background removal. An image with an opaque background gets a shape cut (rectangle, rounded, circle, oval), never a contour. A contour for such an image needs the customer in the studio or a human.

Until story-21 ships, `make_cutline` in ec-quote produces a preview outline for the mockup only and marks it as not for production.

## Data flow: WhatsApp through the CRM

ec-quote never talks to Meta. The CRM owns the number, the webhook, the 24 hour window, templates, caps, the kill switch and the audit of automatic sends.

```
Customer ─▶ Meta Cloud API ─▶ CRM  POST /api/whatsapp/webhook   (signature, anti replay, stored in the inbox)
                                  │  bridge (EPIC-3, CRM): downloads the media, builds InboundMessage
                                  ▼
                          ec-quote  inbound endpoint (EC_QUOTE_INBOUND_SECRET) ─▶ Engine.handle
                                  │  returns OutboundAction[]
                                  ▼
                               CRM  text, image, buttons ─▶ conversationSendService (sentBy 'ai_auto')
                                    pending_approval     ─▶ draft in the inbox, one click ─▶ ec-quote approve or reject
                                    handoff              ─▶ raiseHandover, the conversation goes to a person
                                  ▼
                        Meta Cloud API ─▶ Customer
```

- A message written by staff from the phone app arrives in the CRM as an echo (`smb_message_echoes`). The bridge forwards it with `from_staff: true`; the engine switches that conversation to manual for `manual_mode_quiet_hours`.
- The follow up at 24 hours fits inside the customer service window. The one at 72 hours is outside it and needs an approved template, sent by the CRM under its monthly cap.
- The wire contract is `specs/todo/crm-ec-quote-bridge.md`.

## Data flow: site chat

```
Browser (theme block in extensions/calculator) ─▶ https://etichetecreative.ro/apps/calculator/quote-chat/*
        ─▶ calculator app App Proxy route (authenticate.public.appProxy) ─▶ ec-quote (EC_QUOTE_INBOUND_SECRET)
```

The browser never holds a secret and never calls ec-quote directly. Files go to R2 through the existing storefront upload route and reach ec-quote as URLs on the storage host.

## Checkout and payment

`create_checkout` creates a Shopify Draft Order: one unit of the product's permanent variant, `priceOverride` equal to `PriceQuote.total`, the calculator's `properties` as line attributes, the artwork URL, tags for the channel and ad source. The order is then read by the CRM and production like a site order. Paid orders are matched back to offers in story-15.

## Environment

Names only, values come from the owner: `CALCULATOR_BASE_URL`, `CALCULATOR_SYNC_SECRET`, `ANTHROPIC_API_KEY`, `EC_QUOTE_MODEL`, `SHOPIFY_SHOP_DOMAIN`, `SHOPIFY_ADMIN_TOKEN`, `CRM_BASE_URL`, `CRM_API_SECRET`, `EC_QUOTE_INBOUND_SECRET`, `EC_QUOTE_DATA_DIR`. See `.env.example`.

## Related documents

- `CLAUDE.md`: commands, module map, non negotiable rules.
- `docs/dev-rules.md`: development rules.
- `docs/plan.md`: what changed against the owner's plan, epics per repository, decisions and credentials (Romanian).
- `specs/todo/epic-*.md`: one design per epic with its story map.

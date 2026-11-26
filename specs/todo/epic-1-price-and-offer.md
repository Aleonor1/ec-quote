---
id: EPIC-1
title: "Price and offer, tested first on the site chat"
status: proposed
prompt: "Plan implementare: Ofertare instant pe site si WhatsApp, E1 pret si oferta"
---

# EPIC-1: Price and offer

## Outcome

A visitor of etichetecreative.ro opens the chat, describes what they need in their own words, answers at most two clarifying questions and receives the exact site price with the next quantity tiers, validity, and a payment link that charges that exact price. A request outside the rules goes to a person with a summary. Every offer becomes a lead in the CRM, paid orders are matched back to their offers, unanswered offers get a follow up, and the owner gets a weekly report with the metrics of the plan and an audit of 20 offers.

The site chat is the first channel because it needs nothing from Meta. WhatsApp reuses the same engine in EPIC-3.

## Users and roles

- Customer in the site chat: anonymous, Romanian, on a phone most of the time.
- Staff: receive handoffs and leads in the CRM.
- Owner: reads the weekly report; decides thresholds and texts.

## Journeys

1. J1 Offer: "am nevoie de 500 de etichete rotunde de 5 cm pentru borcane" then one question about material, then price for 500 and for the next two tiers, without and with VAT, valid 7 days, then "Vreau să comand" and a payment link.
2. J2 Not in the calculator: "vreau un banner de 3 metri" then a short answer that a colleague will reply, and a handoff with reason `not_in_calculator`.
3. J3 Over the threshold: an offer above the value threshold is prepared but not sent; the customer is told a colleague confirms it; handoff `value_over_threshold`.
4. J4 Discount: "îmi faceți un preț mai bun?" then handoff `special_terms`; no number is offered.
5. J5 Asks for a person, or is not understood after the allowed exchanges: handoff.
6. J6 Calculator down: the customer is told the price cannot be computed now; no estimate; handoff after the retry.
7. J7 Paid: the customer pays the link; the offer is marked paid; no follow up is sent.
8. J8 Follow up: no answer after 24 hours and after 72 hours; one reminder each, never after payment, handoff or manual mode.

## Scope

**In:** price parity audit; handoff rules; outbound guard; offer composition; Draft Order checkout; the site chat channel (ec-quote endpoints, the App Proxy route and the theme block in the calculator app); lead and handoff delivery to the CRM; paid order tracking; follow up scheduler; metrics and the weekly audit report.

**Later:** A/B of question wording; incentive in the follow up (owner decision); English.

**Out:** files and mockups (EPIC-2); WhatsApp delivery (EPIC-3); products outside the calculator; any discount.

## Design

- Price: `CalculatorClient` only. Tiers are the next `upsell_tier_count` visible tiers above the requested quantity, each priced by its own call.
- Guard: `ec_quote/agent/guard.py` checks model text; a failed check never reaches the customer.
- Handoff: decided by code on state and rules (`ec_quote/agent/rules.py`), not by the model. The model can only request `customer_asked`, `complaint`, `special_terms` and `not_understood`; the code confirms.
- Checkout: `ShopifyCheckout` (`ec_quote/integrations/shopify.py`), idempotent per offer.
- Site chat: browser to the storefront App Proxy to the calculator app to ec-quote. The browser holds only a signed session token (`ec_quote/api/security.py::Signer`).
- During the test period the chat block is visible only with a preview parameter; making it public is an EPIC-4 decision.

### Integrations

| System | Purpose | Auth | Env vars | Failure behaviour |
| --- | --- | --- | --- | --- |
| Calculator app | Price, catalog | `X-Sync-Secret` | `CALCULATOR_BASE_URL`, `CALCULATOR_SYNC_SECRET` | 503 or timeout: one retry, then "cannot compute now" and handoff |
| Shopify Admin | Draft Order, order status | Admin token | `SHOPIFY_SHOP_DOMAIN`, `SHOPIFY_ADMIN_TOKEN` | No link is sent; handoff with the offer attached |
| CRM | Lead, handoff | Shared secret | `CRM_BASE_URL`, `CRM_API_SECRET` | Queued and retried; the customer flow continues |
| Anthropic API | Understanding | API key | `ANTHROPIC_API_KEY`, `EC_QUOTE_MODEL` | One retry, then a fixed apology text and handoff |

## Decisions

| # | Decision | Chosen | Why | Bucket |
| --- | --- | --- | --- | --- |
| D1 | Who decides a handoff | Code, from rules and state | The model must not decide policy | Decided |
| D2 | How the browser reaches ec-quote | Through the calculator app's App Proxy | A browser cannot hold a secret; same origin, no CORS | Decided |
| D3 | Checkout object | Draft Order on the permanent variant with `priceOverride` | Orders look like site orders to the CRM and production | Decided |
| D4 | Value threshold | `handoff_value_threshold_ron_ex_vat` = 3000 | Owner's plan | Reserved, to confirm |
| D5 | Validity and follow up incentive | 7 days, no incentive | Owner's plan lists it as open | Reserved, open |
| D6 | Products at launch | Calculator stickers and labels only | Owner's plan | Reserved, to confirm |
| D7 | Tone and self introduction as automated | Short, polite, introduces itself as the automated assistant in the first message | Honest by default | Reserved, open |
| D8 | Production terms the assistant may state | Keys `production_term_standard`, `production_term_urgent` in `config/rules.json` | No deadline may be invented | Reserved, open |

## Risks

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| A wrong price reaches a customer | Low | Very high | Price only from the calculator, guard on text, audit of 50 configurations, weekly audit of 20 offers |
| Draft Order total differs from the offer (tax settings) | Medium | High | story-10 asserts equality to the cent and has a live check before launch |
| The chat is abused (spam, cost) | Medium | Medium | Session tokens, rate limits, `max_offers_per_contact_per_day` |

## Story map

| Story | Title | Repository | Depends on | Wave | Effort |
| --- | --- | --- | --- | --- | --- |
| [story-6](story-6-price-parity-audit-harness.md) | Price parity audit harness on 50 configurations | ec-quote | story-2 | 1 | MEDIUM |
| [story-7](story-7-handoff-rules-decided-by-code.md) | Handoff rules decided by code, all seven reasons | ec-quote | story-2, story-3 | 1 | MEDIUM |
| [story-8](story-8-outbound-guard-and-conversation-evals.md) | Outbound guard and the conversation evaluation set | ec-quote | story-2 | 1 | HIGH |
| [story-9](story-9-offer-composition-tiers-validity-text-and-image.md) | Offer composition: tiers, validity, text and image | ec-quote | story-2 | 1 | MEDIUM |
| [story-10](story-10-draft-order-checkout-exact-price.md) | Draft Order checkout at the exact calculator price | ec-quote | story-2 | 1 | HIGH |
| [story-11](story-11-site-chat-channel-api.md) | Site chat channel API | ec-quote | story-3, story-4 | 1 | MEDIUM |
| [story-12](story-12-calculator-app-quote-chat-app-proxy-route.md) | [calculator-app] Quote chat App Proxy route | etichetecreative-calculator-app | story-11 | 2 | MEDIUM |
| [story-13](story-13-calculator-app-quote-chat-theme-block.md) | [calculator-app] Quote chat theme block | etichetecreative-calculator-app | story-12 | 3 | HIGH |
| [story-14](story-14-crm-lead-and-handoff-delivery.md) | Lead and handoff delivery to the CRM | ec-quote | story-7 | 2 | MEDIUM |
| [story-15](story-15-paid-order-tracking.md) | Paid order tracking (orders/paid) | ec-quote | story-3, story-10 | 2 | MEDIUM |
| [story-16](story-16-follow-up-scheduler.md) | Follow up scheduler at 24 and 72 hours | ec-quote | story-3, story-9 | 2 | MEDIUM |
| [story-17](story-17-metrics-and-weekly-offer-audit.md) | Metrics and the weekly audit of 20 offers | ec-quote | story-6, story-15 | 3 | MEDIUM |

**Parallelism:** 12 stories, critical path 3, widest wave 6. Waves are counted inside the epic; all stories also need EPIC-0 merged.

## Hand-over

- Owner: decisions D4 to D8.
- Owner: a Shopify custom app token with `write_draft_orders`, `read_products`, `read_orders`.
- Owner: merge and deploy of the two calculator app stories (`shopify app deploy --allow-updates` for the theme block), and the env var with the ec-quote base URL and inbound secret on Railway.

## References

- Calculator app: `docs/spec-crm-line-price.md` (contract, 422 reasons, `properties` order), `features/application-architecture.md` (line item properties), `CLAUDE.md` (App Proxy, e2e conventions).
- CRM contract: `specs/todo/crm-ec-quote-bridge.md`.

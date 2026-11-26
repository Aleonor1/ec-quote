---
id: EPIC-4
title: "Optional: CRM lead sync and site chat"
status: proposed
prompt: "Owner, 2026-11-26: E4 optional, site chat and CRM lead sync; the site chat is not confirmed as still wanted"
---

# EPIC-4: Optional: CRM lead sync and site chat

> **Nothing in this epic is confirmed.** After the change of direction on 2026-11-26 the owner wants assisted quoting in WhatsApp Web. The site chat was built into the backend on scaffold day and the CRM bridge was specified for a flow that no longer exists. Both are kept here, last, as open decisions. No story of this epic starts before the owner answers D1 or D4.

## Outcome

If the owner wants it: every offer made through the extension appears in the CRM as a lead with its price, link and status. And, separately, if the owner still wants it: a visitor of etichetecreative.ro can ask for a price in a chat on the site, served by the same engine, with staff approving each offer.

## What exists

- Site chat backend: `ec_quote/api/app.py` serves `POST /v1/chat/session`, `message`, `upload`, `GET /v1/chat/poll`, `GET /v1/media/{token}`, with signed sessions, rate limits, CORS or proxy mode, and a demo widget under `ec_quote/api/static/`. It uses the conversational `Engine`, not `AssistEngine`. It is off unless configured (story-4).
- CRM: `ec_quote/integrations/crm.py` (`CrmClient`) written against `crm-ec-quote-bridge.md`. The CRM side does not exist. Of that contract only section 1 (lead upsert) is still relevant.
- Routes `/v1/inbound` and `/v1/approvals/*` were written for the CRM driven WhatsApp flow that was dropped. They stay off; removing them is a cleanup the owner can ask for.

## Scope

**In (if confirmed):** the stories below.

**Out:** message forwarding between the CRM and ec-quote; WhatsApp through the Meta Cloud API; templates; autonomous sending on WhatsApp.

## Decisions (all reserved, all open)

| # | Decision | Options | Note |
| --- | --- | --- | --- |
| D1 | Is the site chat still wanted? | Yes, later; No, remove its code | Without an answer the code stays, off |
| D2 | Site chat transport | Direct to ec-quote under CORS with signed sessions; or through the calculator app's App Proxy (ec-quote not public for the chat, one more hop) | Both are in the API; the block works with either |
| D3 | Who answers on the site chat | The engine alone with every offer approved by staff first; or the engine alone inside the rules; or only a contact form that lands in the panel | No person reads a site reply before it leaves, unlike WhatsApp; the first option is the safe default |
| D4 | Leads in the CRM | Yes, when; No | Needs a CRM story from the bridge spec, section 1 |

## Story list

| Story | Title | Repository | Depends on | Note |
| --- | --- | --- | --- | --- |
| [story-28](story-28-crm-lead-sync.md) | CRM lead sync: offers appear as leads (optional) | ec-quote | story-10, story-24 | Needs D4 and the CRM route |
| (CRM, no id here) | [crm] `PUT /api/ec-quote/leads` for a service caller | crm-etichete-creative | none | Section 1 of `crm-ec-quote-bridge.md`; to be cut out of that spec as its own CRM story (next free id there was 370 on 2026-11-26) |
| [story-29](story-29-site-chat-channel-api.md) | Site chat channel API hardened for a public browser | ec-quote | story-2, story-3, story-4 | Needs D1 |
| [story-30](story-30-calculator-app-quote-chat-theme-block.md) | [calculator-app] Quote chat theme block | etichetecreative-calculator-app | story-29 | Needs D1 |
| [story-31](story-31-calculator-app-quote-chat-app-proxy-relay.md) | [calculator-app] Quote chat App Proxy relay | etichetecreative-calculator-app | story-29 | Only if D2 is "proxy" |

The three site chat specs were written before the change of direction and renumbered. They are complete enough to estimate, but must be re-read against D3 before anyone ships them: handoff, approval and follow up on the site were designed around the CRM inbox, which is no longer part of the flow.

## Risks

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Unused public routes stay reachable | Low | Medium | story-4 keeps them off unless configured; D1 "No" removes them |
| The site chat answers customers with nobody reading | Medium | High | D3; default is approval of every offer |

## Hand-over

Owner: D1 to D4.

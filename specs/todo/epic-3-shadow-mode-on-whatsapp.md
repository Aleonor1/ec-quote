---
id: EPIC-3
title: "Shadow mode on WhatsApp through the CRM"
status: proposed
prompt: "Plan implementare: Ofertare instant pe site si WhatsApp, E3 mod umbra pe WhatsApp"
---

# EPIC-3: Shadow mode on WhatsApp

## Outcome

For two weeks every WhatsApp conversation that asks for a price is handled by the same engine as the site chat, but no offer leaves without a person. Staff see the prepared offer in the CRM inbox with the price, the mockup and the reason for every question, and approve it with one click, edit it, or reject it. The engine never writes over a person who answered from the phone. At the end the owner has the share of offers approved unchanged, the number that decides the move to EPIC-4.

ec-quote does not own the WhatsApp number and receives nothing from Meta. The CRM forwards messages and delivers replies (`ARCHITECTURE.md`, "Data flow: WhatsApp through the CRM"). The wire contract is `crm-ec-quote-bridge.md` in this folder.

## What exists and what is missing

Exists in the CRM (verified in code): the Meta webhook with signature and anti replay (`services/inbox/src/routes/whatsappWebhook.ts`), Coexistence echoes and history (`whatsappCoexistenceService.ts`, story-197), the inbox and lead matching, `sendText`, `sendImage` by URL and `sendTemplate` (`packages/integrations/src/whatsappBusinessClient.ts`), the `ai_auto` send path with the 24 hour window, kill switch, caps and audit (`conversationSendService.ts`), templates with a monthly cap (`whatsappTemplateService.ts`), AI drafts with approve, edit, reject (`aiReplyDraftService.ts`), handover (`inboxHandoverService.ts`).

Missing: the bridge itself, downloading inbound media from Meta (only `mediaId` and `mediaMime` are stored), interactive button messages, an approval surface for an ec-quote offer, a template for the 72 hour follow up.

## Scope

**In:** the stories below. **Out:** autonomous sending (EPIC-4); Instagram; calls.

## Story list

Titles and one line each. Full specs are written by `/rnd` or `/create-spec` when EPIC-1 and EPIC-2 are merged. CRM stories get their ids in the CRM repository (next free id there is story-370 on 2026-11-26).

| # | Title | Repository | One line |
| --- | --- | --- | --- |
| 1 | [crm] Bridge outbound: forward inbound WhatsApp messages to ec-quote | crm-etichete-creative | After a message is stored, post an `InboundMessage` to ec-quote with the shared secret, with retries and an idempotency key; never block the webhook's 200. |
| 2 | [crm] Download inbound media and hand it over as a URL | crm-etichete-creative | Fetch the file by `mediaId` from the Graph API, store it through the calculator app's `upload-url`, pass the URL in `attachments`. |
| 3 | [crm] Deliver ec-quote actions through the `ai_auto` send path | crm-etichete-creative | `text` and `image` actions go through `conversationSendService` so the 24 hour window, kill switch, caps, DNC and audit apply unchanged. |
| 4 | [crm] Interactive reply buttons, with a numbered text fallback | crm-etichete-creative | Add the Cloud API interactive message to `whatsappBusinessClient`; parse `button_reply` into `button_id` on inbound. |
| 5 | [crm] Staff echo puts the conversation on manual | crm-etichete-creative | A `smb_message_echoes` message or a reply sent from the inbox is forwarded with `from_staff: true`. |
| 6 | [crm] Approval card for a pending offer in the inbox | crm-etichete-creative | A `pending_approval` action becomes a draft with the offer image and price; Approve, Edit and Reject call ec-quote; an edit is recorded as "approved with changes". |
| 7 | [crm] Handoff from ec-quote raises a handover with the summary | crm-etichete-creative | A `handoff` action calls `raiseHandover` with the reason code and the engine's summary, and assigns the conversation. |
| 8 | [crm] Template for the 72 hour follow up | crm-etichete-creative | A Meta approved utility template with the offer reference, sent by the CRM under its monthly cap when ec-quote asks for it. |
| 9 | [crm] Ad source on the lead | crm-etichete-creative | The click to WhatsApp referral of the first message is stored on the lead and passed as `Contact.ad_source`, for the ec-agency report. |
| 10 | WhatsApp channel adapter in ec-quote | ec-quote | Channel specifics in one place: 20 character button titles, image by URL, text length, the window state received from the CRM. |
| 11 | Approve, edit and reject endpoints hardened | ec-quote | `Engine.approve` and `reject` are idempotent, expire with the offer, and record who decided and whether the text changed. |
| 12 | Shadow mode report: approved unchanged rate | ec-quote | Daily and cumulative share of offers approved unchanged, edited, rejected, with the reasons; the 95% gate of the plan. |
| 13 | Manual mode and quiet hours verified on real echoes | ec-quote | Conversation replay tests from recorded CRM payloads: a staff message silences the engine for `manual_mode_quiet_hours`. |
| 14 | Dry run with the Meta test number | both | End to end on the CRM's test configuration before the production number is switched on; checklist in the runbook. |

## Decisions reserved for the owner

- Who approves offers during the two weeks, and in which hours. Outside those hours an offer waits, and the customer is told when a colleague answers.
- The text of the 72 hour template, submitted to Meta for approval.
- Whether the assistant introduces itself as automated in the first WhatsApp message (EPIC-1 D7).

## Hand-over

- Owner: `EC_QUOTE_INBOUND_SECRET` and the ec-quote base URL set in the CRM environment; `CRM_API_SECRET` set on the VPS.
- Owner: template submission in Meta Business Manager.

## Depends on

EPIC-0, EPIC-1 (offer, checkout, handoff, lead), EPIC-2 (file and mockup) for offers with artwork. Stories 1, 3, 5, 6, 7 can start on EPIC-1 alone.

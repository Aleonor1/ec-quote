---
id: crm-ec-quote-bridge
title: "[crm] Puntea ec-quote: lead și ofertă, predare la om, mesaje WhatsApp în ambele sensuri, aprobare în mod umbră, comandă plătită"
type: feature
severity: P1
effort: HIGH
sprint: ec-quote
epic: ec-quote
depends_on: [story-183, story-184, story-186, story-187, story-197, story-294, story-304]
---

# [crm] The ec-quote bridge

**Status:** Todo. Lands in `crm-etichete-creative` (copy it to `specs/todo/` there with the next story id, 370 at the time of writing). This file is the wire contract: `ec_quote/integrations/crm.py` is already written against it, so a change here is a change there.

## Summary

ec-quote is the instant quoting backend (price from the site calculator, mockup, Shopify Draft Order link). It does not own the WhatsApp number: the CRM owns the Cloud API webhook, Coexistence and the inbox. The CRM has no machine to machine intake today:

| Looked at | What it is | Why it does not fit |
|---|---|---|
| `POST /api/leads/form-submit` (`services/leads/src/routes/widget.ts`) | Public site form | Needs `business_name`, returns no lead id, answers duplicates with a silent success, 5 per hour per IP |
| `/api/track/*` (`server/src/routes/track.ts`) | Order tracking page and email pixel | Not a lead intake |
| `railwayQuoteClient` (`packages/integrations/src/railwayQuoteClient.ts`) | CRM calling the calculator app (`X-Sync-Secret`) | Outbound only; nothing calls the CRM |
| `POST /api/inbox/conversations/:id/messages` (`services/inbox/src/routes/inbox.ts`) | The send path | Behind JWT and the `leads` permission, addressed by conversation id |
| `/api/scraper-places` ingest, `/api/production-agent/*` | Service callers with a bearer token | Other domains, but the auth pattern to copy |

So this story adds one router, `/api/ec-quote/*`, for the service caller, and the CRM's calls to the ec-quote API (`ec_quote/api/app.py`: `POST /v1/inbound`, `POST /v1/approvals/{id}/approve|reject`). Only `GET /api/health` is used as it exists.

## User Story

As the owner, I want every conversation the quoting assistant handles to appear in the unified inbox with its lead, its offer and its payment link, sent through the same send path with the same caps and kill switch, so the team sees one inbox and can take over at any moment.

## Scope

**In**

### 0. Auth, mounting, idempotency

1. Env `EC_QUOTE_BRIDGE_TOKEN` (CRM side; ec-quote holds the same value as `CRM_API_SECRET`). New `services/inbox/src/services/ecQuoteBridgeAuth.ts` on the pattern of `services/production/src/services/productionAgentAuth.ts`: `Authorization: Bearer <token>`, SHA-256 of both sides then `timingSafeEqual`; no token configured answers 503, missing or wrong answers 401. The token is never logged.
2. `server/src/app.ts`: mount `ecQuoteBridgeRouter` at `/api/ec-quote` before `requireAuth`, next to `productionAgentRouter`, with `express.json({ limit: '1mb' })`.
3. Every write carries `Idempotency-Key` (64 hex characters). New table `ec_quote_requests(key TEXT PRIMARY KEY, path, status_code, response_json, created_at)`: the key is claimed in the same transaction as the write; a replay answers with the stored status and body and repeats no side effect. Rows older than 7 days are deleted by a job in `services/inbox/src/jobs.ts`.
4. Errors are `{ "error": "<code>", ... }`. ec-quote maps 401/403, 503, other 4xx (the code is kept) and 5xx.
5. Calls from the CRM to ec-quote: new adapter `packages/integrations/src/ecQuoteClient.ts` (env `EC_QUOTE_URL`, `EC_QUOTE_INBOUND_SECRET`; header `X-EcQuote-Secret: <secret>`, which is what `ec_quote/api/app.py` checks; 60 s timeout, because the answer carries the reply; `isConfigured()`), with a durable outbox `ec_quote_outbox(message_id UNIQUE, kind, payload_json, attempts, next_attempt_at, answered_at, actions_json, delivered_count)` drained by a job, at least once, backoff, at most 8 attempts. `message_id` is the idempotency key on the ec-quote side (a replay answers `duplicate: true` with the same actions).

The `contact` object is the same everywhere:

```json
{ "channel": "whatsapp", "key": "40722123456", "phone": "+40722123456", "name": "Ana", "email": null, "ad_source": "meta:120211" }
```

`channel` is `whatsapp` or `site`. For `whatsapp`, `key` is the `wa_id` (digits), which is `conversations.external_key`. For `site`, `key` is the chat session id and no conversation exists in the CRM.

### 1. `PUT /api/ec-quote/leads`: upsert lead, offer and status

Request:

```json
{
  "contact": { },
  "status": "link_sent",
  "summary": "100 stickere 6 x 6 cm, hartie premium, fisier vectorial ok",
  "offer": {
    "currency": "RON", "total": "217.00", "total_ex_vat": "179.34", "unit_price": "2.17",
    "discount_percent": "0", "quantity": 100, "product_id": "gid://shopify/Product/1",
    "material": "Sticker Premium", "shape": "custom", "width_cm": "6", "height_cm": "6", "urgent": false,
    "properties": [{ "name": "_Sticker Quantity", "value": "100" }],
    "draft_order_id": "gid://shopify/DraftOrder/991", "invoice_url": "https://...", "checkout_total": "217.00"
  }
}
```

`offer` is null before a price exists; the checkout fields are absent until the draft order exists. Money is text, parsed with the guarded parsers.

Response 200: `{ "lead_id": 812, "created": true, "existing_customer": false, "customer_id": null, "conversation_id": 4411 }`.

Resolution order, in one transaction (new `services/inbox/src/services/ecQuoteLeadService.ts`; the inbox domain may import leads and customers):

1. The WhatsApp conversation with `external_key = key` already has a lead: use it.
2. `whatsappService.matchLeadByPhone(phone)` (the 9 digit tail rule used for inbound messages).
3. The existing customer rule: `dedupeRepository.findCustomersByHardKeys` on phone and email (the first check of `leadDedupeService.checkDuplicate`). When a customer matches, the lead is created with `leadService.createLead(..., { linkToCustomerId })` (story-294), so the customer is not duplicated as a prospect and the response says `existing_customer: true` with `customer_id`. An order only match (`findUnlinkedOrderByContact`) also answers `existing_customer: true`, `customer_id: null`.
4. Otherwise `leadService.createLead` with `business_name` = `contact.name` or `WhatsApp <last 4 digits>`, `niche: 'Other'`, `source: 'ec-quote'`, `created_via: 'ec_quote'` (new `LeadCreatedVia` value), no owner, then `autoAssignmentService.runRulesForLead`.
5. The conversation, when one exists and has no lead, is linked with `conversationRepository.linkLead` (the conditional update of story-184; losing the race means re-reading, not failing).

A lead marked Do Not Contact answers `409 do_not_contact` with `lead_id`, writes nothing and ec-quote stops.

Writes: `leads.ad_source` (new column, set once, never overwritten, read by the ec-agency report); new table `ec_quote_offers(id, lead_id, conversation_id, channel, contact_key, status, total, total_ex_vat, quantity, summary, offer_json, draft_order_id UNIQUE, invoice_url, shopify_order_id, paid_at, created_at, updated_at)`, one row per draft order (or one open row per lead while no draft exists); one `logActivity(leadId, 'ec_quote_offer', ...)` per status change, not per call.

Statuses: `new`, `quoted`, `awaiting_approval`, `link_sent`, `paid`, `handed_off`, `lost`. `quoted`, `awaiting_approval` and `link_sent` move a lead that is still `New` to `Interested`; `paid` is written only by section 6; an unknown status (up to 40 characters) is stored as text and moves nothing.

### 2. `POST /api/ec-quote/handoffs`: mark the conversation handed off

Request: `{ "contact": { }, "reason": "value_over_threshold", "summary": "...", "notify": true, "occurred_at": "2026-11-26T12:00:00" }`. `reason` is one of `not_in_calculator`, `value_over_threshold`, `special_terms`, `complaint`, `file_unusable`, `customer_asked`, `not_understood`.

Response 200: `{ "conversation_id": 4411, "lead_id": 812, "notified": true }`.

- Reuse `messageClassificationRepository.raiseHandover(conversationId, reason, at)` (sets `handover_required` and `handover_reason` once) and the body of `inboxHandoverService.raiseHandover`: `logActivity(..., 'inbox_handover', ...)` and `notificationService.notify('inbox_handover', 'Conversație predată la om', { body, link: '/crm/inbox?c=<id>', userId })` to the assigned user, or to the settings users when nobody is assigned. Extract the part after the reason codes so both callers share it. The seven reasons get Romanian texts in `handoverReasonText` (`@crm/common`); the summary is appended to the notification body.
- `notify: false` (ec-quote sends it outside business hours, `config/rules.json` `business_hours`): flag, reason and activity only, no notification. The conversation shows in the existing "predate" filter the next morning.
- The conversation switches to manual (section 4): the bot stops until staff hand it back.
- `site` channel: no conversation; the handoff is an activity on the lead plus the notification with a link to the lead.

### 3. Inbound WhatsApp to ec-quote (CRM calls ec-quote)

New column `conversations.ec_quote_mode TEXT NOT NULL DEFAULT 'off'` with CHECK `('off','bot','manual')` and `ec_quote_manual_until TEXT NULL`.

A conversation is bot eligible when: channel `whatsapp`; the global setting `ec_quote_enabled` is on (new inbox setting, off by default, in `inboxSettingsService` and the settings page); `handover_required = 0`; the lead, if any, is not Do Not Contact and has `ai_mode` other than `off`; and either the conversation is new or it has had no outbound message from a person (`sent_by = 'user'`, including `phone_app` echoes) in the last `ec_quote_manual_hours` (setting, default 48). The first eligible inbound message sets `ec_quote_mode = 'bot'`.

`conversationService.onInboundRecorded` gets a listener `ecQuoteForwardService.onInbound` (registered in `services/inbox/src/index.ts`, after commit): for a `bot` conversation, a live message with customer content is put in the outbox and sent as:

`POST {EC_QUOTE_URL}/v1/inbound` (the body is strict: unknown fields are rejected with 422)

```json
{
  "channel": "whatsapp",
  "contact": { "key": "40722123456", "phone": "+40722123456", "name": "Ana", "email": null, "ad_source": "meta:120211" },
  "message_id": "wamid.HBg...",
  "text": "Buna ziua, as vrea 100 de etichete",
  "button_id": null,
  "attachments": [{ "url": "https://<crm host>/api/ec-quote/media/55120?exp=1795000000&sig=<hex>", "mime": "application/pdf", "filename": "logo.pdf" }],
  "received_at": "2026-11-26T10:15:00+02:00",
  "from_staff": false
}
```

Note that here `channel` sits next to `contact`, not inside it, and `contact.key` must be 6 to 20 digits.

Response 200:

```json
{
  "message_id": "wamid.HBg...", "duplicate": false,
  "actions": [{ "kind": "text", "text": "...", "buttons": [], "image_url": null, "handoff_reason": null, "approval_id": null }]
}
```

The CRM delivers the actions in order, each through the same function as section 5, and stores how many were delivered (`delivered_count`), so a retry after a crash resumes and never sends an action twice:

| `kind` | What the CRM does |
|---|---|
| `text`, `buttons`, `image` | Send to the customer (section 5). `image_url` is served by ec-quote (`/v1/media/{token}`, expiring) and is downloaded by the CRM at once, not stored as a link. |
| `handoff` | Send `text` when it is not empty. The flag, reason and notification come from ec-quote's own `POST /handoffs` (section 2), which may arrive before or after; both orders must work. |
| `pending_approval` | Nothing goes to the customer. Create the approval card of section 6 from `approval_id`, `text` and `image_url`. |

- Attachments: ec-quote downloads `url` without credentials and only from hosts on its allow list (`https`, no redirects to other hosts), so the CRM host must be on that list and the link carries its own capability: `GET /api/ec-quote/media/:messageId?exp=<unix seconds>&sig=<HMAC-SHA256 of "<messageId>.<exp>" with the bridge token>`, valid 15 minutes, compared in constant time. The route also accepts the bearer token instead of the signature (`CrmClient.fetch_media`). `Content-Type` = `media_mime`; 404 for a message without media or outside a bot conversation; 25 MB cap. This needs a new `downloadMedia(mediaId)` in `packages/integrations/src/whatsappBusinessClient.ts` (Graph media lookup then the binary); the CRM has no media download today.
- `button_id`: the webhook parser must keep the id of an interactive button reply (new field on `WebhookInboundMessage`).
- `contact.ad_source`: the click to WhatsApp `referral` of the first message (`source_id`, `source_type`), which the parser drops today. Format `meta:<source_id>`.
- In a `bot` conversation the CRM's own reply automation is off for that message: `aiReplyDraftService` creates no draft and `inboxAutoReplyService.tryAutoSend` skips. Classification (`messageClassificationService`) still runs. Two automatic replies to one message must be impossible.
- Messages of one conversation are sent to ec-quote one at a time, in order. A failed call is retried from the outbox; after the last attempt the conversation gets a handover with reason `auto_send_failed` so a person answers.

### 4. Manual mode on a `phone_app` echo

`whatsappCoexistenceService.onEchoRecorded` gets a listener: when the echo's conversation is in `bot` mode, set `ec_quote_mode = 'manual'`, `ec_quote_manual_until = sentAt + ec_quote_manual_hours`, and call `/v1/inbound` as in section 3 with `from_staff: true`, `text` = the echo body, no attachments and `message_id` = the echo id (the answer has no actions). The same happens when staff send from the inbox composer (`conversationSendService.sendMessage` with `sentBy: 'user'`). `PATCH /api/inbox/conversations/:id` accepts `ec_quote_mode` (`bot` or `manual`), so staff hand a conversation back with one click in `ConversationActions.tsx`; a badge in `ConversationListItem.tsx` shows the mode.

### 5. Delivering ec-quote's replies, and `POST /api/ec-quote/messages`

One service function, `ecQuoteDeliveryService.deliver(conversation, action, key)`, sends an action. It is called for the actions answered by `/v1/inbound` and by an approval (sections 3 and 6), and by this route, which ec-quote uses for messages that answer no inbound call (payment confirmation, follow up inside the window).

Request (JSON, or `multipart/form-data` with the same JSON in the `payload` field and the file in `image`):

```json
{ "contact": { }, "kind": "text", "text": "...", "buttons": [{ "id": "ok", "title": "Da, comand" }], "image_url": null }
```

`kind` is `text`, `buttons` (1 to 3 reply buttons, title up to 20 characters) or `image` (`text` is the caption; either `image_url` or the uploaded file).

Response 200: `{ "message_id": 55121, "conversation_id": 4411, "over_cap": false }`.

- Sent through `conversationSendService.sendMessage` with `sentBy: 'ai_auto'`, `userId: null` and the system viewer of `inboxAutoReplyService`, so the guards apply in the existing order: kill switch (`409 outreach_disabled`), monthly service cap (`409 service_cap_reached`), 24 hour window (`409 window_closed`), then Do Not Contact and opt in in `whatsappService` (400) and "not configured" (503). The message is recorded by `conversationService.recordOutbound` with the provider ledger row, so it appears in the thread and counts in `countServiceMessages`.
- New refusals: `409 manual_mode` when the conversation is not in `bot` mode (a person took over between ec-quote's decision and the send) and `404 conversation_not_found`.
- `conversationSendService` sends only text today. Add `sendImage` and `sendButtons` dispatch for WhatsApp: `whatsappBusinessClient.sendImage` exists (link); interactive reply buttons are a new adapter function; an uploaded file is stored under `DATA_DIR` and served to Meta by an unguessable link, or uploaded to the Graph media endpoint. `ConversationMessageType` gets `interactive` (the ledger maps it to `unknown`, as for the other new types), and `MessageBubble.tsx` renders the buttons as read only chips.
- Messages sent this way are marked `origin = 'ec_quote'` (new `MessageOrigin` value) so the thread shows "trimis de asistent" and reports can tell them from the inbox AI.
- Decision for the owner: the inbox AI's daily cap (`inbox_auto_daily_cap`) is not applied here; ec-quote has its own `max_offers_per_contact_per_day`. The kill switch and the monthly service cap are.

### 6. Shadow mode: approval card

The card is created from a `pending_approval` action (section 3). `POST /api/ec-quote/approvals` creates the same card explicitly: `{ "contact": { }, "approval_id": "ap_01H...", "preview_text": "...", "image_url": "https://...", "offer": { } }`, response 201 `{ "approval_id": "ap_01H..." }`; both paths are idempotent on `approval_id`. New table `ec_quote_approvals(approval_id PRIMARY KEY, conversation_id, lead_id, preview_text, image_path, offer_json, status CHECK ('pending','approved','rejected','expired'), decided_by_user_id, decided_at, created_at)`.

- UI: a card in `client/src/components/inbox/DraftPanel.tsx` (above the AI draft): the offer image, the preview text, total with and without VAT when the offer is known, and two buttons, "Aprobă și trimite" and "Respinge". A `pending` approval also raises `notificationService.notify('ec_quote_approval', 'Ofertă de aprobat', { link })`.
- Routes behind JWT and the `leads` permission, in `services/inbox/src/routes/inboxAi.ts`: `POST /api/inbox/ec-quote/approvals/:id/approve` and `.../reject`. The decision is a conditional update (`WHERE status = 'pending'`), so of two clicks exactly one wins and the other gets 409. Then the CRM calls ec-quote: `POST {EC_QUOTE_URL}/v1/approvals/{approval_id}/approve` or `/reject` with `{ "by": "<user name>" }` (1 to 120 characters).
- Approve answers `{ "approval_id", "channel", "key", "duplicate", "delivery": "crm" | "site_chat", "actions": [...] }`. With `delivery: "crm"` the CRM delivers the actions as in section 3; with `site_chat` ec-quote has already queued them for the site widget and the CRM sends nothing. Reject answers `status: "rejected"` and no actions. 404 `approval_not_found` marks the card expired. If ec-quote does not answer, the status goes back to `pending` and the card shows the error; a repeated approve is safe (`duplicate: true`, same actions).
- A pending approval expires when the 24 hour window closes or a person writes in the conversation (section 4).

### 7. Paid order linking

Draft orders created by ec-quote carry the tag `ec-quote`, order attributes `ec_quote_channel`, `ec_quote_key`, `ec_quote_valid_until`, `ec_quote_ad_source`, and the line properties of a site order. Shopify copies tags and attributes to the order.

In the existing `orders/create` and `orders/updated` handling (`services/orders/src/services/shopifyWebhookService.ts`; `orders/paid` is not subscribed, on purpose), after the order is stored: when the order has the tag `ec-quote`, read `ec_quote_key` from `note_attributes`, find the `ec_quote_offers` row (by the key, newest `link_sent` with the same total), link `orders.lead_id`, and when the order is paid set the offer `paid`, `paid_at`, `shopify_order_id`, write `logActivity(leadId, 'ec_quote_paid', ...)` and enqueue for ec-quote:

`POST {EC_QUOTE_URL}/v1/orders/paid` (this route does not exist in `ec_quote/api/` yet; it is added by the ec-quote story that needs it, and until then the poll below is the only signal): `{ "event_id": "order-<shopify id>-paid", "contact_key": "40722123456", "channel": "whatsapp", "draft_order_id": "gid://shopify/DraftOrder/991", "order_id": "gid://shopify/Order/7", "order_name": "#1700", "total": "217.00", "paid_at": "..." }`.

The orders domain cannot import inbox (build order), so the link runs from an inbox job that reads new paid orders with the tag, or through a post commit listener the orders service exposes. ec-quote also polls `draftOrder.status` as a fallback, so this event may arrive twice: `event_id` makes it idempotent.

**Out**

- The site chat widget and its transport (ec-quote serves it directly; only `PUT /leads` and `POST /handoffs` are used for `site`).
- Follow up messages outside the 24 hour window (they need an approved Meta template and `conversationSendService.sendTemplate`): a later story.
- Any change to pricing; the CRM never recomputes the offer.

## Acceptance Criteria

1. No `EC_QUOTE_BRIDGE_TOKEN`: every `/api/ec-quote/*` route answers 503 without reading the database. Wrong or missing bearer: 401. Correct token, no JWT: served.
2. `PUT /leads` for an unknown phone creates one unassigned lead with `created_via = 'ec_quote'` and `ad_source`, links the conversation and answers `created: true`. The same call again (same `Idempotency-Key`) answers the stored body and creates nothing; a second call with another status updates the same lead and writes one activity.
3. `PUT /leads` for a phone that belongs to a customer creates no duplicate customer: the lead is linked to that customer and the response says `existing_customer: true` with `customer_id`. For a phone that matches an existing lead by its 9 digit tail, that lead is reused. For a Do Not Contact lead: `409 do_not_contact`, nothing written.
4. `PUT /leads` with `offer.draft_order_id` writes one `ec_quote_offers` row; repeating it with `status: "paid"` from ec-quote does not mark it paid (only section 7 does).
5. `POST /handoffs` with `notify: true` sets `handover_required`, the Romanian reason text, one activity and one notification per recipient, and switches the conversation to manual. A second handoff for the same conversation raises nothing new. With `notify: false` no notification row is written.
6. An inbound text in a bot eligible conversation reaches ec-quote with `message_id` = the provider message id, and the actions of the answer are sent to the customer in order. Meta's redelivery of the same webhook calls nothing again. A crash after the first of two actions was sent, then a retry, sends only the second. With ec-quote down, the message is processed after it comes back; after the last attempt a handover is raised.
7. In a `bot` conversation no AI draft is created and no automatic reply leaves from the inbox AI for that message.
8. An inbound PDF is forwarded with a signed `url`; `GET /api/ec-quote/media/:id` with that signature, or with the bearer token, returns its bytes and mime; an expired or altered signature and no token is 401; a message of a non bot conversation is 404.
9. A `phone_app` echo, or a message sent by staff from the composer, switches the conversation to `manual`, calls `/v1/inbound` once with `from_staff: true`, and a later `POST /messages` for it answers `409 manual_mode`. Staff can switch it back to `bot`.
10. `POST /messages` text in a `bot` conversation inside the window sends one WhatsApp message, shows it in the thread marked as sent by the assistant and counts it in the monthly service count. The same `Idempotency-Key` twice sends one message. With the kill switch off: `409 outreach_disabled`; at the cap: `409 service_cap_reached`; window closed: `409 window_closed`; in each case nothing is sent.
11. `kind: "buttons"` with 3 buttons and `kind: "image"` (by URL and by upload) are sent and rendered in the thread; 4 buttons or a 21 character title answer 400.
12. A `pending_approval` action sends nothing to the customer and shows the card in the conversation (so does `POST /approvals`); "Aprobă și trimite" calls ec-quote once and the returned actions are sent and the card becomes approved; two agents clicking at once: one 200, one 409; ec-quote unreachable: the card stays pending with an error.
13. A paid Shopify order with the tag `ec-quote` and a matching `ec_quote_key` is linked to the lead, the offer becomes `paid`, and ec-quote receives one `orders/paid` event; an `orders/updated` redelivery sends nothing new. An order with the tag and no matching offer is stored as any order and logged.
14. Phone numbers, tokens and message bodies are not written to logs by the new code (ids only).

## Tests

- Routes (`services/inbox/src/__tests__/ecQuoteBridge.routes.test.ts`): 503 / 401 / mounted before `requireAuth`; validation of every body (missing contact, bad channel, bad reason, money that is not a number, oversized summary).
- Service: lead resolution order (conversation lead, phone tail, customer hard key, order only match, new lead), DNC, idempotent replay, concurrent duplicate requests with one key (unique constraint, one write).
- Handoff: notify on and off, already raised, site channel.
- Forwarding: eligibility table, outbox retry and exhaustion, redelivered webhook, no double automation.
- Send: each guard in order, manual mode, buttons and image validation, ledger and conversation rows.
- Echo and composer takeover; hand back.
- Approvals: conditional update race, ec-quote failure rollback, expiry.
- Shopify: tagged paid order linked once; untagged order untouched.
- Client: the approval card states (pending, sending, approved, rejected, error) and the mode badge.
- Full server and client suites green.

## Validation on the ec-quote side

`ec_quote/integrations/crm.py` (`CrmClient`) implements sections 1, 2 and 5 (`upsert_lead`, `handoff`, `deliver`), the explicit request of section 6 (`request_approval`) and the bearer media download of section 3 (`fetch_media`); `tests/integrations/test_crm.py` pins the paths, headers and bodies above. The calls from the CRM (`/v1/inbound`, `/v1/approvals/{id}/approve|reject`) are served by `ec_quote/api/app.py`, with the bodies in `ec_quote/api/schemas.py`.

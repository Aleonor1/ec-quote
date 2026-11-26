---
id: EPIC-3
title: "Measurement and tuning"
status: proposed
prompt: "Owner, 2026-11-26: usage metrics, weekly 20 offer price audit, reminders shown to staff"
---

# EPIC-3: Measurement and tuning

## Outcome

The owner knows every week whether the assistant helps: how fast a suggestion is ready after a customer writes, how many suggestions are sent unchanged, edited or ignored, how many offers become orders, what the model costs, and that no customer received a wrong price, proven on 20 real offers. The staff see in the panel which offers got no answer after 24 and 72 hours and get a ready follow up sentence when they open that chat. Nothing is sent automatically.

## Journeys

1. J1 Paid: a customer pays the link; within an hour the offer is marked paid; its reminders disappear; opening the chat shows a short thank you suggestion.
2. J2 Reminder: an offer has no answer after 24 hours; the panel's "De urmărit" list shows it; the person opens the chat, inserts the follow up text and sends it, or clicks "Am rezolvat".
3. J3 Weekly report: on Monday the owner reads one page with speed, use, conversion, cost and the audit result "20 din 20 identice".
4. J4 Tuning: the report names the three kinds of request with the most ignored suggestions; the next change to prompts or questions is tested against the evaluation set of story-8.

## Scope

**In:** paid order tracking by Draft Order status; usage metrics derived from what the backend already receives; the weekly report with the price audit; reminders for staff in the extension.

**Later:** experiments on question wording; a per product view; alerts when the reader breaks on a staff computer.

**Out:** automatic follow ups; WhatsApp templates; telemetry of clicks or keystrokes in the extension; ranking staff; a Shopify webhook receiver.

## Design

- Payment: a sweep through `ShopifyCheckout.get_status` for the Draft Orders ec-quote created. No webhook, no CRM.
- Use: the next outgoing message in a chat, as reported by a later `suggest`, is compared with the suggestion that was offered (`unchanged`, `edited`, `ignored`). No extra data leaves the browser for this.
- Report: pure functions over the store, a script run by hand or by cron on the host.
- Reminders: `follow_up_hours` from `config/rules.json`; two new assist routes (`GET /v1/assist/reminders`, `POST /v1/assist/reminders/{id}/dismiss`); the panel lists them; the follow up text is an ordinary suggestion.

## Decisions

| # | Decision | Chosen | Why | Bucket |
| --- | --- | --- | --- | --- |
| D1 | How payment is learned | Polling Draft Order status | No public endpoint, no new secret; volume is small | Decided |
| D2 | How use is measured | From the conversation the backend already sees | No tracking in the extension | Decided |
| D3 | Follow ups | Reminders to staff; a person writes | Owner's direction | Decided |
| D4 | Monthly model cost ceiling | A key in `config/rules.json` (plan: about 100 EUR at 300 requests) | Owner's plan | Reserved, to confirm |
| D5 | Follow up texts | Two fixed sentences | A person sends them | Reserved, to confirm |

## Risks

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| The backend only knows chats someone opened, so a reminder may be stale | High | Low | story-27 says "nu știm dacă a răspuns" and resolves on opening the chat |
| Outcome classification is wrong for heavily edited messages | Medium | Low | A tested similarity threshold; `edited` and `ignored` both reported |
| Measures are read as a ranking of people | Low | Medium | Reported in total; per token only request counts for auditing |

## Story map

| Story | Title | Where | Depends on | Wave | Effort |
| --- | --- | --- | --- | --- | --- |
| [story-24](story-24-paid-order-tracking.md) | Paid order tracking: which offers became orders | backend | story-3, story-10 | 1 | MEDIUM |
| [story-25](story-25-usage-metrics-for-suggestions.md) | Usage metrics: time to suggestion, and suggestions used unchanged, edited or ignored | backend | story-3, story-12 | 1 | MEDIUM |
| [story-26](story-26-weekly-report-and-audit-of-20-offers.md) | Weekly report with the price audit of 20 offers | backend | story-6, story-24, story-25 | 2 | MEDIUM |
| [story-27](story-27-reminders-for-staff-in-the-extension.md) | Reminders for staff at 24 and 72 hours, shown in the extension | backend, extension | story-12, story-24 | 2 | MEDIUM |

**Parallelism:** 4 stories, critical path 2, widest wave 2. Needs EPIC-1 merged; does not need EPIC-2.

## Hand-over

- Owner: decisions D4 and D5; who reads the weekly report.

## References

- `ARCHITECTURE.md`, "Reminders and measurement"; `docs/plan.md`, "Cum măsurăm acum".

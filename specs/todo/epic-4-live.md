---
id: EPIC-4
title: "Live: autonomous offers with a stop button"
status: proposed
prompt: "Plan implementare: Ofertare instant pe site si WhatsApp, E4 live"
---

# EPIC-4: Live

## Outcome

Offers inside the rules leave without a person, on WhatsApp and on the public site chat, at any hour. The owner can stop everything with one switch, sees the plan's metrics every week, and is alerted when something is wrong before a customer notices. Requests outside the rules keep going to a person, exactly as in shadow mode.

## Entry condition

The shadow mode report of EPIC-3 shows at least 95% of offers approved unchanged over the two weeks, zero price errors in the weekly audits, and the owner says go. The switch is `shadow_mode` in `config/rules.json`; changing it is the owner's decision, never a session's.

## Scope

**In:** the stories below. **Later (EPIC-5, continuous optimization):** question wording experiments, new products in the calculator, premium mockups with Higgsfield on request, English. **Out:** discounts decided by the assistant; products outside the calculator.

## Story list

Titles and one line each. Full specs are written when EPIC-3 ends, from what the shadow period showed.

| # | Title | Repository | One line |
| --- | --- | --- | --- |
| 1 | Autonomous mode switch per channel | ec-quote | `shadow_mode` becomes per channel (site, WhatsApp) so each can go live separately; an offer over the threshold still waits for a person. |
| 2 | Emergency stop | ec-quote | One flag stops all automatic sends and turns every reply into a handoff; checked on every message; documented in the runbook. |
| 3 | [crm] Stop and mode in the inbox settings | crm-etichete-creative | The CRM's kill switch also stops ec-quote deliveries; the current mode is visible in the inbox. |
| 4 | Outside business hours behaviour | ec-quote | Offers inside the rules are sent at any hour; a handoff outside hours tells the customer when a colleague answers (`next_business_open`). |
| 5 | Alerts | ec-quote | Calculator unavailable, model errors, Draft Order failures, guard blocks above a rate, first reply over 1 minute, queue of unanswered handoffs: one message to the owner each, without personal data. |
| 6 | Cost meter | ec-quote | Model tokens and cost per conversation and per month against the plan's ceiling (about 100 EUR at 300 requests); an alert at 80%. |
| 7 | [calculator-app] Site chat public | etichetecreative-calculator-app | Remove the preview gate of the chat block, add it to the smoke e2e, and to the theme pages the owner chooses. |
| 8 | Weekly audit as a routine | ec-quote | The 20 offer audit of story-17 runs on a schedule and its report goes to the owner every Monday. |
| 9 | Retention job | ec-quote | Conversations and files older than the retention period are deleted or anonymized; a report of what was removed. |
| 10 | Incident runbook and rollback | ec-quote | What to do for a wrong price, a wrong message, a leaked link; how to return to shadow mode; who is told. |
| 11 | Conversion baseline and target | ec-quote | Offer to order conversion measured against the baseline from the shadow period; the +50% target tracked in the weekly report. |

## Decisions reserved for the owner

- Go live per channel, and the date.
- Whether the public site chat appears on every page or only on product pages.
- Who receives alerts and on which channel.

## Depends on

EPIC-3 complete and its entry condition met.

---
id: EPIC-0
title: "Foundation: one engine that runs end to end"
status: proposed
prompt: "Plan implementare: Ofertare instant pe site si WhatsApp, E0 fundatia"
---

# EPIC-0: Foundation

## Outcome

The six modules written on scaffold day (`ec_quote/pricing`, `files`, `mockup`, `agent`, `integrations`, `api`) become one service. It starts only with a valid configuration, handles a message from first text to a pending offer in one process, keeps its state across a restart, refuses unauthenticated or hostile input, and runs on the owner's VPS with a health check and a backup. Nothing here is customer visible yet.

Removed from the original E0 because it already exists: the price tool (calculator `POST /api/sync/line`), the WhatsApp webhook, Coexistence and the inbox (CRM). See `ARCHITECTURE.md`, "What already exists elsewhere".

## Users and roles

- Developer sessions (implement, QA, review): run the service and the suite locally with fakes.
- The owner: provides secrets by name, the VPS and the domain; merges the epic pull request.
- The CRM and the calculator app (later epics): the only callers of the inbound endpoint.

## Journeys

1. J1 Local end to end: a scripted Romanian conversation enters the inbound endpoint with fakes for every port and leaves as a `pending_approval` action that carries an offer priced by `FakeCalculator`.
2. J2 Restart: the process is stopped after the first message and started again; the second message continues the same conversation; a redelivered message produces no second effect.
3. J3 Refusal: a request without the secret, with a wrong secret, oversized, or with an attachment URL outside the allowed hosts is refused and logged without personal data.
4. J4 Deploy: the owner starts the service on the VPS from the runbook; `/health` answers with the commit; a backup of the data directory can be restored.

## Scope

**In:** one rules loader and settings validation; the composition root; the durable conversation store and idempotency; inbound security, untrusted input and log hygiene; packaging and deployment on a VPS.

**Later:** metrics and alerts (EPIC-1 story-17, EPIC-4); the CRM bridge (EPIC-3).

**Out:** any Meta or WhatsApp code; any price computation; a database server.

## Design

- Ports and adapters as in `ec_quote/contracts.py`. Real adapters are built only in `ec_quote/api/main.py`.
- Configuration: `ec_quote/config.py` (`Settings`, environment) and one `Rules` object from `config/rules.json`. Today three loaders read that file (`ec_quote/agent/rules.py`, `ec_quote/pricing/client.py::load_vat_percent`, `ec_quote/files/checker.py::load_rules`); story-1 leaves one.
- State: SQLite (standard library) under `EC_QUOTE_DATA_DIR`, through `ConversationStore` in `ec_quote/agent/store.py`.
- Deployment: one container or one systemd unit behind a TLS reverse proxy, data directory on a mounted volume, nightly backup.

## Decisions

| # | Decision | Chosen | Why | Bucket |
| --- | --- | --- | --- | --- |
| D1 | Datastore | SQLite in `EC_QUOTE_DATA_DIR` | Volume is about 300 requests a month; no new service | Decided |
| D2 | Where real adapters are built | Only `ec_quote/api/main.py` | Tests stay without network | Decided |
| D3 | Hosting | A VPS, not Railway | Owner's plan | Reserved, answered in the plan; provider and domain still open |
| D4 | Retention of conversations and files | A new key in `config/rules.json` | GDPR | Reserved, open |

## Risks

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| The six modules disagree on a contract detail | High | Medium | story-2 is the integration story; its end to end test is the proof |
| A policy number stays in code | Medium | High | story-1 adds a test that fails on any default for a policy key |
| The service is reachable without the secret | Low | High | story-4, fail closed when the secret is not configured |

## Story map

| Story | Title | Depends on | Wave | Effort | Track |
| --- | --- | --- | --- | --- | --- |
| [story-1](story-1-rules-and-settings-single-loader.md) | Rules and settings: one validated loader, fail closed | (none) | 1 | SMALL | full |
| [story-2](story-2-wire-ports-and-end-to-end-test.md) | Wire the real ports and prove the engine end to end with FakeCalculator | story-1 | 2 | HIGH | full |
| [story-3](story-3-durable-conversation-store-and-idempotency.md) | Durable conversation store and idempotent inbound | story-1 | 2 | MEDIUM | full |
| [story-4](story-4-inbound-security-untrusted-input-and-logs.md) | Inbound security, untrusted input and logs without personal data | story-2 | 3 | MEDIUM | full |
| [story-5](story-5-vps-deployment-health-and-backup.md) | VPS deployment, health and backup | story-2 | 3 | MEDIUM | full |

**Parallelism:** 5 stories, critical path 3, widest wave 2.

## Hand-over

- Owner: create the GitHub repository for `ec-quote` and move the scaffold there; run `install.sh --full` from the skills pack and `/onboard-project`.
- Owner: VPS access, a subdomain with TLS, and the secrets named in `.env.example`.
- Owner: the retention period (D4).

## References

- `ARCHITECTURE.md`, `docs/dev-rules.md`, `docs/plan.md`.
- Calculator app: `docs/spec-crm-line-price.md`, `docs/spec-crm-calculator-config.md`.

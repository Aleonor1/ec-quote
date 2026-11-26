---
id: EPIC-0
title: "Foundation: repository, hosting, secrets and live calculator access"
status: proposed
prompt: "Plan implementare: Ofertare instant pe site si WhatsApp, E0 fundatia; revised 2026-11-26: assisted quoting through a Chrome extension on WhatsApp Web"
---

# EPIC-0: Foundation

## Outcome

The backend modules written on scaffold day become one service that the extension can rely on. It starts only with a valid configuration, turns a posted conversation into a priced suggestion in one process, keeps its state across a restart, answers only to the staff's tokens, runs on the owner's host with a health check and a backup, and has been shown to carry the live calculator's prices unchanged on 50 configurations. Nothing here is visible to a customer.

Not in this epic because it already exists or is no longer wanted: the price tool (calculator `POST /api/sync/line`); anything with the Meta Cloud API, the CRM inbox or automatic sending (dropped by the owner on 2026-11-26).

## Users and roles

- Developer sessions (implement, QA, review): run the service and the suite locally with fakes.
- The owner: provides secrets by name, the host and the domain, the staff names; merges the epic pull request.
- The extension (EPIC-1): the only caller of the assist endpoints.

## Journeys

1. J1 Local end to end: a scripted Romanian WhatsApp conversation is posted to `POST /v1/assist/suggest` with fakes for every port and comes back first as a suggested question, then as an offer priced by `FakeCalculator`.
2. J2 Restart and repeat: the same conversation posted again, also after a restart and from a second token, returns the same suggestion without calling the model or the calculator.
3. J3 Refusal: a request without a token, with an unknown token, oversized, or to an optional route that is not configured is refused and logged without personal data.
4. J4 Hosting: the owner starts the service on the host from the runbook; `/health` answers with the commit; a backup of the data directory can be restored; a staff token can be added and revoked.
5. J5 Live prices: the audit script runs against the production calculator and reports 50 of 50 identical.

## Scope

**In:** one rules loader and settings validation; the composition root and the assisted engine end to end; the durable store and idempotent suggestions; assist API security, untrusted input and log hygiene; hosting; the price parity audit harness.

**Later:** usage metrics and the weekly report (EPIC-3).

**Out:** the extension (EPIC-1); any Meta or CRM code; any price computation; a database server.

## Design

- Ports and adapters as in `ec_quote/contracts.py`. Real adapters are built only in `ec_quote/api/main.py`. The product's entry point is `AssistEngine` (`suggest`, `create_payment_link`).
- Configuration: `ec_quote/config.py` (`Settings`; per staff tokens in `EC_QUOTE_ASSIST_TOKENS` as `name:token` pairs) and one `Rules` object from `config/rules.json`. Today three loaders read that file; story-1 leaves one.
- State: SQLite (standard library) under `EC_QUOTE_DATA_DIR`, through `ConversationStore`.
- Hosting: the scaffold's `Dockerfile`, `deploy/docker-compose.yml` and `deploy/Caddyfile` (TLS), data directory on a volume, nightly backup.
- Routes written on scaffold day for other callers (`/v1/chat/*`, `/v1/inbound`, `/v1/approvals/*`, the demo page) stay in the code, off unless configured.

## Decisions

| # | Decision | Chosen | Why | Bucket |
| --- | --- | --- | --- | --- |
| D1 | Datastore | SQLite in `EC_QUOTE_DATA_DIR` | A few requests a day; no new service | Decided |
| D2 | Authentication of the extension | One token per staff member, header `X-EcQuote-Assist-Token` | Attribution and single revocation | Decided (owner's direction) |
| D3 | Production term texts | Keys in `config/rules.json`, owner's wording | No deadline may be invented | Reserved, open |
| D4 | Retention of conversations and files | `retention_days` in `config/rules.json` | Personal data | Reserved, open |
| D5 | Host and domain | A VPS and a subdomain | Owner's plan | Reserved, open (which provider, which name) |

## Risks

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| The modules disagree on a contract detail | High | Medium | story-2 is the integration story; its end to end test is the proof |
| A policy number stays in code | Medium | High | story-1 adds a test that fails on any default for a policy key |
| The backend is reachable without a token | Low | High | story-4, fail closed when no token is configured |
| Prices are altered on the way from the calculator to the text | Low | Very high | story-6 on 50 configurations, repeated weekly on real offers (story-26) |

## Story map

| Story | Title | Depends on | Wave | Effort | Track |
| --- | --- | --- | --- | --- | --- |
| [story-1](story-1-rules-and-settings-single-loader.md) | Rules and settings: one validated loader, fail closed | (none) | 1 | SMALL | full |
| [story-2](story-2-wire-ports-and-assisted-engine-end-to-end.md) | Wire the real ports and prove the assisted engine end to end with FakeCalculator | story-1 | 2 | HIGH | full |
| [story-3](story-3-durable-store-and-idempotent-suggestions.md) | Durable conversation store and idempotent suggestions | story-1 | 2 | MEDIUM | full |
| [story-4](story-4-assist-api-security-untrusted-input-and-logs.md) | Assist API security: per staff tokens, untrusted input and logs without personal data | story-2 | 3 | MEDIUM | full |
| [story-5](story-5-backend-hosting-health-and-backup.md) | Backend hosting, health and backup | story-2 | 3 | MEDIUM | full |
| [story-6](story-6-price-parity-audit-harness.md) | Price parity audit harness on 50 configurations | story-2 | 3 | MEDIUM | full |

**Parallelism:** 6 stories, critical path 3, widest wave 3.

## Hand-over

- Owner: create the GitHub repository for `ec-quote` and move the scaffold there; run `install.sh --full` from the skills pack and `/onboard-project`.
- Owner: the host, a subdomain with TLS, and the values of `CALCULATOR_SYNC_SECRET`, `ANTHROPIC_API_KEY`, `EC_QUOTE_MODEL`, `SHOPIFY_SHOP_DOMAIN`, `SHOPIFY_ADMIN_TOKEN`, `EC_QUOTE_ASSIST_TOKENS` (one generated token per staff name).
- Owner: decisions D3 and D4; one live run of the price audit.

## References

- `ARCHITECTURE.md`, `docs/dev-rules.md`, `docs/plan.md`.
- Calculator app: `docs/spec-crm-line-price.md`, `docs/spec-crm-calculator-config.md`.

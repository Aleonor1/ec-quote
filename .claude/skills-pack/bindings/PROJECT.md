# Project binding

The single per-project configuration file for the Claude skills pack (`ai-skills`). Every skill reads its project-specific facts from here; nothing is hardcoded in a skill body.

Two families of skills read this file:

- **orchestrate-delivery** (the delivery coordinator and its role skills, including ui-test) — reads everything below except `## Skills pack`.
- **create-spec** and **project-overview** — read `## Identity`, `## Gates`, `## Documentation`, and `## Skills pack`.
- **release**, **security-audit**, **retro** — read Identity, Gates, UI testing, Sessions, and their own section under `## Skills pack`.
- **fix** — reads what orchestrate-delivery reads, plus `## Skills pack → Spec authoring` and `→ Bug fixing`.
- **rnd** and **build** — read everything, including `## Coverage`, `## UI testing`, `## Epic delivery`, `## Models`, and `## Skills pack → Research and design`.
- Every coordinator (orchestrate-delivery, ship, build, fix) reads `## Models` when it starts a session and `## Epic delivery → Budget: tokens` for the run's token budget.

## Identity

| | |
| --- | --- |
| Repository | `Aleonor1/ec-quote` |
| Base branch | `main` |
| Human | `Aleonor (Aleonor1)` |
| Ticket key pattern | `story-<N>` (e.g. `story-12`, epics `EPIC-<N>`) |
| Kit root | `.claude/skills-pack` |

## Tracker

Specs are Markdown files on disk in `specs/todo/` (moving to `specs/done/` when `Done`). Reads need no approval. Writes follow `rules/human-approval-gate.md`, except routine writes covered by a standing approval.

| Operation | How |
| --- | --- |
| Read a ticket (acceptance criteria, status, assignee, parent, links) | read the spec file matching `specs/todo/<key>-*.md` or `specs/done/<key>-*.md` |
| Read available transitions | lifecycle is fixed: `Todo` -> `In Progress` -> `In Review` -> `Done` |
| Assign | set `assignee: Aleonor1` in the YAML frontmatter of the spec file |
| Transition one step | set `status:` in the YAML frontmatter; `Done` also moves the file from `specs/todo/` to `specs/done/` |
| Comment | append a dated bullet under `## Delivery log` at the end of the spec file |
| Create a follow-up ticket | write a new spec file `specs/todo/story-<N>-<slug>.md` with the next free id across `specs/todo/` and `specs/done/` |
| Status names | In Progress: `In Progress` · In Review: `In Review` · Done: `Done` |
| Acceptance-criteria field | `## Acceptance Criteria` |

## Repository

| Operation | How |
| --- | --- |
| Host | `github` |
| Read a pull request (head, reviews, threads, checks) | `gh pr view <N> --repo Aleonor1/ec-quote --json headRefOid,mergeable,reviewDecision,reviews,statusCheckRollup,title,body,state` and `gh api graphql` for review threads |
| Open a pull request | `gh pr create --repo Aleonor1/ec-quote --base <base> --head <branch> --title "<title>" --body-file <file>` |
| Post a comment review | `gh pr review <N> --repo Aleonor1/ec-quote --comment --body-file <file>` |
| Reply to and resolve a review thread | `gh api graphql` (`addPullRequestReviewThreadReply` and `resolveReviewThread`) |
| Dismiss this session's own earlier change-request | `(None)` |
| Commit subject | `story-N: imperative summary` (e.g. `story-12: fix browser fixture race and harden Lexical insert`) |
| Pull-request title | `story-N: short title` (or `chore: ...` for non-story maintenance) |
| Pull-request body, required sections | Summary. Acceptance criteria addressed. Gate results (command + observed). Documentation rows satisfied or N/A. Hand-over, or (None). |
| Release note | `(None)` |
| Protected paths | `ec_quote/contracts.py` (edit only when the ticket's Scope explicitly names it) |
| Areas this human does not own | `(None)` (external sibling repositories `etichetecreative-calculator-app` and `crm-etichete-creative` live outside this repo and are delivered there) |
| Automated review comments | `(None)` |
| Attribution line | `Delivered via claude-skills-pack` |

## Colliding ids

`story-<N>` spec ids across `specs/todo/` and `specs/done/`, `EPIC-<N>` epic ids in `specs/todo/`.

## Sessions

| Capability | This environment |
| --- | --- |
| Profile | `claude-code-agents` (or Antigravity `invoke_subagent` with `Workspace: "share"` and `send_message`) |
| Start a session | `Agent` tool (`isolation: worktree`, `run_in_background: true`) in Claude Code; `invoke_subagent` (`TypeName: "self"`, `Workspace: "share"`) in Antigravity |
| Message a session | `SendMessage` in Claude Code; `send_message` in Antigravity |
| Read a transcript | completion notification / subagent message |
| Find a session that discussed a PR | `ListAgents` / `manage_subagents` (`list`), or the run ledger |
| Peer messaging | `hub and spoke (handoff blocks relayed by the coordinator)` |
| Start refusal | `None` |
| Wait | Sessions message the coordinator when they finish. Do not poll. |

| | |
| --- | --- |
| Notes folder | `.claude/skills-pack/.run-notes` |
| Worktree base | Pass the base branch; every brief branches from the remote base. |
| Worktree bootstrap | `(None)` (reuse main `.venv` via `.venv/Scripts/python` on Windows or `.venv/bin/python` on POSIX, or run `pip install -e ".[dev]"`) |

## Models

| | |
| --- | --- |
| Large | `opus` |
| Standard | `sonnet` |
| Small | `haiku` |
| Implementer | `standard` (large under the rule's move-up conditions) |
| QA | `standard` |
| UI test | `small` (standard for long journeys) |
| Code review | `standard` (large under the rule's move-up conditions) |
| Epic review | `large` |
| Epic UI test | `standard` |
| Fixed | `(None)` |

## Shared environment

`One machine/stack shared by every session.`

When sessions share a machine:

| | |
| --- | --- |
| Lock | `scripts/heavy-run-lock.sh` from the kit root. Set `HEAVY_RUN_LOCK_DIR` to `.claude/skills-pack/.run-notes/lock`. |
| Heavy commands | `pytest --cov`, `extension` Playwright browser tests (`npm run test:browser`), uvicorn on port `8080`, Docker image builds |
| While the lock is held by someone else | A session may run only the test files its change touches, and rely on the lock-free unit tests until the lock frees. E2e/browser tests are never skipped. |
| Do not | `kill processes by binary name; kill only PIDs spawned by your own worktree or job object` |
| Contention | `port 8080 in use, Chromium profile lock, or coverage.xml write race — re-run under the lock` |

## Conflict check

```bash
git fetch origin <base> <branch>
git merge-tree --write-tree --name-only origin/<base> origin/<branch>
```

Any line after the first names a conflicting file. Also compare Colliding ids.

## Gates

On Windows, replace `python3` with `.venv/Scripts/python.exe` and `npm` with `npm.cmd`.

| Gate | Command |
| --- | --- |
| Install | `python3 -m pip install -e ".[dev]"` |
| Lint | `python3 -m compileall -q ec_quote tests` |
| Types | `(None)` |
| Unit | `python3 -m pytest -q && cd extension && npm run test:unit` |
| Integration | `(None)` (included in `pytest -q` with deterministic fakes and no network) |
| End-to-end | `cd extension && npm run test:browser` |
| Bring the stack up | `EC_QUOTE_INBOUND_SECRET=local-dev-inbound-secret-012345 EC_QUOTE_ASSIST_TOKENS=dev:local-dev-assist-token-012345 EC_QUOTE_ENGINE_FACTORY=ec_quote.api.demo_engine:build_engine EC_QUOTE_DEMO=1 python3 -m uvicorn ec_quote.api.main:app --port 8080` (background, poll `http://127.0.0.1:8080/health`) |
| Gate timeout | `unit 15m, integration 20m, end-to-end 30m, idle 10m` (applied by scripts/run_gate.py: `--timeout`, `--idle`) |
| How gates run | `python3 .claude/skills-pack/orchestrate-delivery/scripts/run_gate.py --timeout 600 --tail 40 -- <command>` |
| Output tail | `40` |

## Coverage

| | |
| --- | --- |
| Coverage command | `python3 -m pytest -q --cov=ec_quote --cov-branch --cov-report=xml:coverage.xml` |
| Report path | `coverage.xml` |
| Source globs | `ec_quote/**` |
| Exclude globs | `tests/**` |
| Diff minimum | `95` |
| Global target | `95` |
| Baseline file | `.coverage-baseline.json` |
| Full test command for the flake check | `python3 -m pytest -q && cd extension && npm test` |
| Runs | `2` |
| Gate command | `python3 .claude/skills-pack/orchestrate-delivery/scripts/coverage_gate.py --report coverage.xml --base origin/main --baseline .coverage-baseline.json --diff-min 95 --target 95 --include "ec_quote/**" --exclude "tests/**"` |
| CI job | `(None)` |

## UI testing

| | |
| --- | --- |
| Run for | `tickets with a UI section` |
| App URL | `http://127.0.0.1:8080/demo/` (for backend demo widget); unpacked Chrome extension UI runs against local WhatsApp Web HTML fixtures via `extension/tests/helpers/harness.mjs` |
| Bring the stack up | `EC_QUOTE_INBOUND_SECRET=local-dev-inbound-secret-012345 EC_QUOTE_ASSIST_TOKENS=dev:local-dev-assist-token-012345 EC_QUOTE_ENGINE_FACTORY=ec_quote.api.demo_engine:build_engine EC_QUOTE_DEMO=1 python3 -m uvicorn ec_quote.api.main:app --port 8080` |
| Browser mode | `headless` |
| Login URL | `(None)` (extension authenticates via `X-EcQuote-Assist-Token` in `chrome.storage.local`) |
| Seed | `(None)` |
| Test accounts by role | `staff: EC_QUOTE_ASSIST_TOKENS (env var name only; test harness uses synthetic token in extension/tests/helpers/harness.mjs)` |
| Playwright install | `npx playwright install --with-deps chromium` |
| Browsers | `chromium` |
| Viewports | `1440x900, 390x844` |
| Language | `ro` |
| Accessibility | `axe: serious and critical are findings` |
| End-to-end folder | `extension/tests/browser/` |
| Evidence folder | `.claude/skills-pack/.run-notes/evidence` |
| UI map | `extension/tests/browser/UI-MAP.md` |
| Walk command | `cd extension && npm run test:browser` |

## Epic delivery

| | |
| --- | --- |
| Epic branch prefix | `epic/` |
| Merge a story into the epic branch | `gh pr merge <N> --merge --repo Aleonor1/ec-quote` |
| Story state after merging into the epic | `Merged to epic` |
| Max review rounds per story | `5` |
| Budget: sessions | `40` |
| Budget: hours | `24` |
| Budget: fix stories | `5` |
| Budget: tokens | `600000` |
| Tokens per session estimate | `40000` |
| Max parallel stories | `3` |
| Early start | `on dependency PR open` |
| Fast track | `LOW, SMALL` |
| Ledger | `.claude/skills-pack/.run-notes/<EPIC-KEY>/ledger.json`, written through `scripts/ledger.py` |
| Epic ticket | `the design document is the epic` (`specs/todo/epic-<N>-<slug>.md`) |

## Obligations

All rules in `docs/dev-rules.md` and `CLAUDE.md` hold on every change: no automatic message sending or Send button selector in `extension/`, no price outside `PricingPort` (`Decimal` only, never `float`), policy numbers only from `config/rules.json`, `Europe/Bucharest` injected clock, no network in automated tests, no PII or secrets in logs/console/storage, Romanian customer/staff copy without em dashes or emojis.

## Documentation

| Surface | Where | Required when |
| --- | --- | --- |
| `Architecture map` | `ARCHITECTURE.md` | `when modules, ports, routes, or external integrations change` |
| `Developer rules & commands` | `CLAUDE.md` | `when commands, gates, structure, or non-negotiable rules change` |
| `Extension guide` | `extension/README.md` | `when extension behaviour, selectors, permissions, packaging, or tests change` |

## Document review

`(None)`. Verdict written to: `(None)`.

## Definition of Ready

A ticket is ready when all hold. `create-spec` enforces these before writing; `lookup-ticket` reports which fail.

1. The problem is stated as behaviour, not as a file to edit.
2. Acceptance criteria are present and each can be shown true or false.
3. The scope names what is in and what is out.
4. Dependencies and linked designs are named, or there are none.
5. An open decision that would change the design is named, or there is none.

## Severity

Use `rules/severity-and-gates.md` as written. Local synonyms if a host tool needs them: Blocking → `Blocker`, Major → `Major`, Minor → `Minor`. A Note is never an inline comment.

## Reserved decisions

The human keeps these even under a standing approval: merging into the base branch (`main`), deploying to production or staging, lowering `.coverage-baseline.json`, repo/org settings, secrets, credentials, Shopify/Chrome Web Store accounts, an architectural change, any change to non-negotiable safety rules in `CLAUDE.md` / `docs/dev-rules.md`, a change that moves an acceptance criterion, an irreversible delete, and anything added when approving.

---

## Skills pack

### Spec authoring (create-spec)

| | |
| --- | --- |
| Spec folder (new specs) | `specs/todo/` |
| Done folder | `specs/done/` |
| Spec filename pattern | `story-<N>-<kebab-slug>.md` |
| Next-id rule | `highest story-<N> across specs/todo/ and specs/done/ + 1` |
| Frontmatter fields | `id, title, effort, epic, depends_on, shared_files, track, models` |
| Effort values | `LOW | SMALL | MEDIUM | HIGH | LARGE` |
| Always-present sections | `Summary, User Story, Scope, Acceptance Criteria, Technical Notes` |
| Optional layer sections | `UI Notes, Hand-over, Dependencies` |
| Migration pattern | `idempotent SQLite schema initialization in ec_quote/agent/store.py and ec_quote/api/store.py` |
| Startup env validation | `ec_quote/config.py` (`load_settings`, fails closed with `SettingsError`) |
| Architecture rules doc | `docs/dev-rules.md` |

### Research and design (rnd, build)

| | |
| --- | --- |
| Design folder | `specs/todo/` |
| Epic key pattern | `EPIC-<N>; file epic-<N>-<slug>.md; next id = highest across specs/todo/ and specs/done/ + 1` |
| Research sources | `official Chrome Extensions Manifest V3, FastAPI, Pydantic v2, Shopify Admin GraphQL, and Anthropic SDK docs` |
| Autonomy limits | `any new runtime dependency (requires written reason per docs/dev-rules.md), any change to ec_quote/contracts.py, any WhatsApp Web action beyond read/insert/attach` |
| Cost ceiling | `0 EUR (every new paid service asks)` |

### Bug fixing (fix)

| | |
| --- | --- |
| Error sources | `structured logs from ec_quote.api.logutil, extension self-test output, and manual bug reports` |
| Severity scale | `P0 data loss, security, money/price error, auto-send · P1 core assisted flow broken, no workaround · P2 broken with copy/manual workaround · P3 cosmetic` |
| Postmortem folder | `docs/postmortems/` |

### Release (release)

| | |
| --- | --- |
| Versioning | `semver` |
| Version files | `pyproject.toml, extension/package.json, extension/manifest.json` |
| Tag format | `v<version>` |
| Tagging | `the human tags` |
| Changelog | `CHANGELOG.md` |
| Migration command | `(None)` (SQLite tables initialize idempotently on startup) |
| Migration check | `(None)` |
| Staging deploy | `reserved` |
| Staging URL | `(None)` |
| Staging test accounts | `EC_QUOTE_ASSIST_TOKENS` |
| Production deploy | `reserved: owner runs docker compose up -d --build in deploy/ on VPS (see deploy/README.md)` |
| Production URL | `https://oferta.etichetecreative.ro` (or the domain configured in `deploy/.env`) |
| Health check | `GET /health` and `GET /v1/assist/ping` |
| Rollback | `checkout previous tag and rebuild container in deploy/; backup restore per deploy/README.md` |
| End-to-end safe against staging | `no` |

### Security (security-audit)

| | |
| --- | --- |
| Scanners | `install in a scratch folder (pip-audit, bandit, gitleaks)` |
| Data classification | `customer WhatsApp phone, display name, conversation messages, uploaded artwork files, Shopify Draft Order links, staff assist tokens` |
| Compliance notes | `GDPR (EU customers); secrets never logged; no conversation data persisted in the extension; retention governed by config/rules.json` |
| Audit cadence | `before first production launch and before each release` |

### Retro (retro)

| | |
| --- | --- |
| Retro folder | `docs/retros/` |
| Metrics to track | `default` |

### Project overview (project-overview)

| | |
| --- | --- |
| Output document | `ARCHITECTURE.md` |
| Related docs to link (not duplicate) | `CLAUDE.md, README.md, docs/dev-rules.md, docs/plan.md, docs/terminare-extensie.md` |
| Server entry point | `ec_quote/api/main.py` (`ec_quote/api/app.py`) |
| Client entry point | `extension/content/main.js` and `extension/background/service-worker.js` |
| Schema file | `ec_quote/agent/store.py` and `ec_quote/api/store.py` |
| Layer folders to enumerate | `ec_quote/pricing, ec_quote/files, ec_quote/mockup, ec_quote/agent, ec_quote/integrations, ec_quote/knowledge, ec_quote/api, extension/background, extension/content, extension/panel, extension/options, tests` |
| Adapters/integrations folder | `ec_quote/integrations` |
| Re-run triggers | `new port or contract change in ec_quote/contracts.py, new API route, new extension module, new external integration, new required env var` |

## Onboarding record

Generated by onboard-project on 2026-11-27 at HEAD `a8b64a5`. Re-run `/onboard-project refresh` after tooling changes.

| Field | Value | Status | Source |
| --- | --- | --- | --- |
| Gates → Install | `python3 -m pip install -e ".[dev]"` | Verified | `CLAUDE.md`, `pyproject.toml` |
| Gates → Lint | `python3 -m compileall -q ec_quote tests` | Verified | `CLAUDE.md` |
| Gates → Unit (backend) | `python3 -m pytest -q` | Verified (869 passed after Windows path/tzdata fix) | `CLAUDE.md`, `pyproject.toml` |
| Gates → Unit & E2E (extension) | `cd extension && npm test` | Verified (47 passed, 0 failed) | `extension/package.json` |
| Coverage → Baseline | `lines 98.34%, branches 95.24%` | Verified | `coverage_gate.py` on `coverage.xml` |
| Human & Ownership | `Aleonor (Aleonor1)`, full repo ownership | Answered by human | onboarding round |

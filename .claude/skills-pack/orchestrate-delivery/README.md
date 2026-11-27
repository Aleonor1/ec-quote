# Orchestrate delivery — portable kit

A coordinator skill plus the role skills it starts. A human names one or more tickets (directly, or by approving an epic that `build` runs). For each ticket, up to four agent sessions run in parallel: an implementer opens a pull request, a QA session verifies the acceptance criteria live, a UI-test session proves them through the browser with Playwright and turns each verified flow into a permanent end-to-end spec, and a code-review session posts the single final verdict. Every pull request clears `rules/test-quality-gate.md`. The sessions settle findings with each other. The coordinator never writes ticket code, never judges acceptance itself, and never merges.

Everything that differs per repository is in `bindings/PROJECT.md`.

## Install

Copy this folder somewhere the agent can read. Tell the agent, once, that the kit root is that folder and that every path in a skill is relative to it. Then fill `bindings/PROJECT.md`.

The coordinator is `skills/orchestrate-delivery/SKILL.md`. Point a slash command or a project instruction at that file. The other skills are loaded by the briefs, not by a plugin manifest.

## What the receiving team fills

Only `bindings/PROJECT.md`. Leave a section as `(None)` when the project has no such thing (no shared stack, no end-to-end suite, no document panel, no id that can collide). Do not delete the heading: the skills look the heading up.

## How a run goes

1. The human names ticket keys, or open pull-request numbers. The coordinator asks when neither was given. It never picks work from a board.
2. It reads each ticket, assigns it, and moves it to In Progress.
3. In the human's own turn it starts, per ticket, the review session, then QA, then the implementer. QA and review wait idle until the implementer messages them the pull-request number and head.
4. The three sessions talk to each other. The coordinator relays only a decision the human reserved, a sibling merge, or a stuck session.
5. The reviewer posts one final verdict. The coordinator checks that verdict against the live pull request before telling the human it is ready.
6. The human merges. The coordinator moves the ticket to Done and reads the first checks on the base branch.

## Layout

| Path | What it is |
| --- | --- |
| `bindings/PROJECT.md` | The only file to edit: repository, tracker, sessions, gates, shared environment |
| `skills/orchestrate-delivery/` | The coordinator and the three brief templates |
| `skills/lookup-ticket/` | Read a ticket and what it links, without writing |
| `skills/implement-ticket/` | One ticket, tests first, through an open pull request |
| `skills/write-tests/` | The red tests the implementer writes first |
| `skills/write-e2e-tests/` | A caller-level flow, when the project has that layer |
| `skills/update-living-docs/` | The documentation surfaces the binding lists |
| `skills/open-pr/` | Branch from the remote base, push, open the pull request |
| `skills/resolve-review-threads/` | Fetch, answer, and resolve every unresolved review thread without asking each time |
| `skills/verify-acceptance/` | QA: exercise each criterion and return a verdict |
| `skills/ui-test/` | UI tester: Playwright against the running stack, charters per criterion, exploration heuristics, screenshots, verified flows kept as specs. Also the epic-level journey pass |
| `skills/review-code/` | Code review against the ticket, the gates, and the diff |
| `skills/co-review/` | Document review, only when the binding lists document types |
| `rules/` | Approval gate, who names the work, evidence before a claim, severity, unattended review, comment shape, definition of ready, test quality gate, session runtimes (profiles and the handoff block), token budget (600,000 per run, counted per session), model selection (which model each session runs on), throughput (code dependencies only, early start, verify once per head, worktree bootstrap, fast track) |
| `scripts/heavy-run-lock.sh` | Serializes heavy commands when sessions share one machine. Unused when the binding says so |
| `scripts/coverage_gate.py` | Diff coverage (lines and branches) against the base, plus the global ratchet against the committed baseline. lcov or Cobertura, standard library only |
| `scripts/run_gate.py` | Runs one gate command so it cannot hang a run: `CI=1`, no stdin, Playwright's report server off, total and idle timeouts, known "waiting forever" lines stopped, the whole process tree killed afterwards; exit 124 with `GATE HUNG:`. `--tail N` keeps only the last N lines in the session's context, the whole log in `RUN_GATE_LOG_DIR`. `--receipt FILE` records what ran on which commit, and `--check-receipt FILE` exits 0 only when that receipt is green on HEAD |
| `scripts/ui-walk.mjs` | Opens the app in a real browser, signs in per role, walks every reachable route at each viewport (GET only, never logout/delete), screenshots each page, flags console errors, failed requests, overflow, leaked placeholders, axe violations; writes the UI map and an HTML contact sheet |
| `scripts/pack_check.py` | Read-only drift check of an installed pack: installed `VERSION` against the pack's, and every installed skill or kit file whose bytes differ from the pack's copy or that the project lacks, and the binding's missing sections, missing rows, and unfilled `<placeholder>` values against `bindings/PROJECT.md.template`. Markdown or `--json`; exit 0 current and complete, 1 re-install or binding to fill, 2 usage, not installed, or a file that cannot be read. Run as `install.sh --check <project>`. Standard library only |
| `scripts/ledger.py` | The run ledger: stories, dependencies, sessions (model, tokens), handoff log, budgets (sessions, hours, fix stories, tokens), `next` with start-now, start-early, and free slots, `stale` for the watchdog |
| `scripts/test-hygiene.sh` | `scan`: no skip, focus, or silencing marker added. `repeat`: the suite run n times, any red run fails |

## What this kit does not include

A tracker client, a git host client, or an agent runtime. `bindings/PROJECT.md` names the commands and tools the project already has. Deployment and infrastructure stay in whatever repository owns them; a ticket that needs them is handed over, not implemented here.

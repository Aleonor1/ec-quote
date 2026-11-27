---
name: onboard-project
description: Fills the skills pack's project binding (PROJECT.md) by reading the repository instead of asking. Detects the stack, package manager, gate commands, coverage tooling, Playwright setup, spec format, structure, and git host; proves each command by running it; asks the human one short round only for what cannot be read from the code; writes the binding with the source of every value; and prepares the test tooling the pack needs (coverage reporter, Playwright config, smoke spec, coverage baseline) on a branch for the human to merge. Use right after install.sh, when /build or /ship stops on an unfilled binding, or with "refresh" after the project's tooling changed. Does not change application code.
argument-hint: (none) | refresh | <path of a package in a monorepo>
---

# Onboard project

Turns a freshly installed pack into a working one. The binding at `<kit-root>/bindings/PROJECT.md` is the only per-project configuration, and filling it by hand is the slowest step of adopting the pack. This skill reads the answers out of the repository, proves them, and asks you only for the rest.

Argument: **$ARGUMENTS**. Empty: first onboarding. `refresh`: re-detect and update only fields whose evidence changed. A path: onboard that package of a monorepo (its commands and globs scoped to it).

You write two things: the binding, and (after approval) a setup branch with test tooling. You never edit application code, CI you were not asked to touch, secrets, or settings.

## Step 0: Preconditions

1. The pack is installed: `.claude/skills-pack/bindings/PROJECT.md` exists. If not, stop and tell the human to run the pack's `install.sh <this repo root>` first.
2. You are at the repository root, on a clean tree. Fetch the remote.
3. Read the current binding. Classify it: **blank** (every field still a `<placeholder>`), **partial**, or **filled**. For partial and filled bindings, every value a human wrote is kept unless the human says otherwise in Step 5; you only fill placeholders and, on `refresh`, correct values whose recorded source changed (see the Onboarding record at the end of the binding).
4. On `refresh`, run the pack's check first: `<pack checkout>/install.sh --check <this repo root>` (ask the human for the pack checkout's path when you do not know it). Its `Binding:` section is your worklist: fill exactly the `missing section:`, `missing row:`, and `unfilled:` lines it lists, taking each missing section and row from `<kit-root>/bindings/PROJECT.md.template`, and nothing else unless a recorded source changed. Exit 2 (`pack not installed`, `cannot read`) is an error to report, not a worklist. When it reports files `changed:` or `missing:`, tell the human to re-run `install.sh` first. After writing, run the check again: the `Binding:` line reads `complete`.

## Step 1: Detect

Run the detector shipped with this skill and keep its JSON:

```bash
python3 .claude/skills/onboard-project/detect.py > <notes folder>/onboard-detect.json
python3 .claude/skills/onboard-project/detect.py --markdown
```

It proposes a value for each binding field with a **source** and a **confidence** (`detected`, `inferred`, `default`), lists alternatives where sources disagree, and reports `setup_needed` and raw facts (CI run lines, scripts, dependencies, role literals, compose services).

The detector reads files; it does not understand intent. Now read what it cannot:

- `README.md`, `CONTRIBUTING.md`, `CLAUDE.md` / `AGENTS.md`: how the authors say to install, run, and test. When the README and `package.json` disagree, the CI workflow decides, because CI is what actually runs.
- Every CI workflow in full: the real gate commands, required services (databases in `services:`), env vars the tests need.
- `.env.example` (or equivalent): which env vars the app and tests require. Values from it may be used only for local runs.
- The test folders: which framework, where unit, integration, and end-to-end tests live, whether tests need a database.
- Auth and permissions code: the real role names (the detector only guesses from string literals).
- A monorepo: which packages exist and how the root scripts fan out. Without a path argument, propose the root as the scope and ask (Step 5) when packages have different stacks.
- **The session runtime**, from your own tools: you have the Agent tool (and SendMessage) → profile `claude-code-agents`; the human names a remote-session runtime → `remote-sessions`, with its tools; neither → `sequential`, and tell the human that roles will share one session. Fill the Sessions rows from the profile's table in `rules/session-runtimes.md`.
- **Worktree bootstrap** (Sessions): the detector proposes one per stack (share the main checkout's `node_modules` or virtualenv, reinstall only when the lockfile changed). Prove it in Step 2 by creating a throwaway worktree, running it, and running the Unit gate there.
- **Models and budgets**: the Models section and the Epic delivery rows Budget: tokens (600,000), Tokens per session estimate, Max parallel stories (4, lower on a small machine), Early start, and Fast track take the pack defaults without a question; the human changes them in the binding.
- **Kit root**: `git ls-files .claude/skills-pack | head -1` empty means the install is not committed; then write the binding's `Kit root` as the absolute path in this checkout and say why (worktree sessions see only committed files). Recommend committing `.claude/` so every machine and worktree sees the same pack.
- **The git host**: `gh auth status` (or a connected GitHub tool) decides `github`; a host you cannot open pull requests on → `local` (`scripts/local_pr.py`), and say what to authenticate to switch.
- The tracker: ticket keys in commits that look like Jira (`ABC-123`) or GitHub issues (`#123`) mean the tracker is not spec files. Check for a connected tracker tool before proposing one.

Reconcile into one proposed value per field, each with its evidence.

## Step 2: Prove the commands

A command in the binding is only trusted after it ran. Run, in order, each through `<kit root>/orchestrate-delivery/scripts/run_gate.py --timeout <600, 1200 for end-to-end> --` (it sets `CI=1`, gives no stdin, stops a hang, and kills what the command leaves behind), from a clean state, and record the exit code and the last lines of output. A `GATE HUNG:` result means the command as written would stall every future run: find why (the detector's **Hang risks** list usually names it) and fix it in the setup branch, never write it into the binding as is:

| Field | How to prove it |
| --- | --- |
| Gates → Install | run it |
| Gates → Lint, Types | run each |
| Gates → Unit | run it; record passed/failed/skipped counts |
| Gates → Integration | run it when it needs only local services (start them with the stack command first) |
| Coverage → Coverage command | run it; the Report path must exist afterwards; parse it with `<kit root>/orchestrate-delivery/scripts/coverage_gate.py --report <path> --base origin/<base> --baseline /dev/null --json` and record the global numbers |
| Gates/UI testing → Bring the stack up | start it; poll the App URL until it answers 2xx/3xx (2 minutes max); stop it afterwards |
| UI testing → Seed | run it only against the local stack you just started |
| Gates → End-to-end | run it against that stack when Playwright is already set up |
| `test-hygiene.sh scan origin/<base>` | run it once to confirm the script works in this repo |
| Sessions → Worktree bootstrap | `git worktree add --detach <notes folder>/wt/onboard origin/<base>`, run the command there, then the Unit gate there; remove the worktree afterwards |

Rules:

- **Local only.** Never run anything that deploys, migrates or seeds a non-local database, publishes, or calls a paid API with real keys. If a command needs a secret you do not have, mark it `Needs you` with the variable name; do not invent a value.
- **A red gate is information, not a blocker.** Record it. Pre-existing failures go into the report so the human knows `/build` will meet them; the quality gate requires 100% green, so the first story would otherwise inherit them.
- **Missing tooling** (no coverage provider, no Playwright) is recorded for the setup branch in Step 6, not installed now.
- Under the shared lock when the binding already names one.

## Step 2b: Open the app in a browser and walk it

Proving that the URL answers is not testing the UI. With the stack up and seeded, open the app in a real browser and go through it the way a new tester would on day one. Two passes:

**Pass 1, automatic (breadth).** Run the walker:

```bash
node <kit root>/orchestrate-delivery/scripts/ui-walk.mjs --url <App URL> \
     --out <notes folder>/ui-walk --role <each role> [--login-url <path>] \
     --viewports <Viewports> [--headed]
```

It signs in through the real login form for every role whose `E2E_<ROLE>_EMAIL` / `_PASSWORD` are set (anonymous always), follows the app's own links breadth-first (GET only; logout and delete-like links are never followed, no button is clicked), and for each page and viewport saves a screenshot and records HTTP status, console errors, uncaught exceptions, failed requests, horizontal overflow on mobile, broken images, placeholders leaking to the screen (`undefined`, `NaN`, i18n keys), axe serious/critical violations, and an inventory of headings, forms, fields, and buttons. Output: `ui-map.json`, `report.md`, `report.html` (all screenshots on one page), `shots/`.

Browser: it launches the first that works of `$PW_EXECUTABLE`, Playwright's Chromium, the system Chrome, and `@sparticuz/chromium` (for sandboxes that block Playwright's browser download: `npm i -D @sparticuz/chromium` in a scratch folder). Exit 3 means no browser launched: say which attempts failed.

**Pass 2, by eye (depth).** Now be the human. Open `report.md`, then look at the screenshots themselves (read the images), every route at both viewports. Then pick the 3 to 5 main journeys the routes reveal (sign in, the main list, a detail page, the main form, the dashboard) and drive each one interactively, one step at a time, looking at the screen after every action:

- with the Playwright MCP tools when the runtime has them, or the **built-in browser** when the binding's Browser mode says so (the Claude desktop app pane: the human can watch live);
- otherwise with a short Playwright script per journey in the notes folder, screenshot after each step, read before the next.

On onboarding, fill and submit forms only against the local seeded database, and never click anything that deletes, pays, sends email, or calls an external service. Note for each journey: did it work, what looked wrong, what was confusing, which states (empty, error, loading) you saw.

What this gives the rest of the pack:

- **Login proven per role.** A role whose login failed is `Needs you` (the account is missing from the seed, or the env vars are wrong).
- **The UI map.** Routes, forms, roles, and the journeys you walked, written as `<End-to-end folder>/UI-MAP.md` in the setup PR. `ui-test` builds its charters on it.
- **A baseline of known UI defects.** Everything Pass 1 and Pass 2 found, graded with `rules/severity-and-gates.md`, goes in the report so the first story does not inherit them silently. Each Blocking or Major becomes a `/fix` candidate the human can launch.
- **A smoke spec per route** (Step 6), so the walk stays in the suite.

Send the human `report.html` with `SendUserFile`, so they see every screen the walk saw.

Each field now has a status: **Verified** (ran green), **Failed** (ran red: output kept), **Detected**, **Inferred**, **Default**, or **Needs you**.

## Step 3: Decide what only the human can answer

A field goes to the human only when the code cannot answer it, or a wrong value would cost a run. Typically:

- **Human**: whose words count as approval (never infer it from `git config`).
- **Areas this human does not own**: infra, CI, deploy folders the detector found. Confirm which are theirs.
- **Test accounts**: confirm the roles; the values go in `.env.test` or CI secrets, never in the binding. Ask whether those accounts exist in the seed.
- **Failed gates**: fix before building (a separate `/fix` or a hand-over), or record as known failures.
- **Tracker** when it is not spec files on disk.
- **Monorepo scope**, when packages differ.
- **CI**: whether to add the quality-gate workflow (CI is often reserved).

Everything else takes the verified, detected, or default value without a question. Defaults are the pack's thresholds (95% diff coverage, 95% global target, 2 flake runs, 1440x900 and 390x844 viewports); they are not asked.

## Step 4: Show the proposal

One message, compact:

- A table of every field you are filling: field, value, status, source. Group by binding section. Verified first.
- The gate results from Step 2 (command, exit, counts), and every hang risk found with the fix in the setup branch.
- The UI walk: routes found, logins per role, defects by severity, and `report.html` sent as a file.
- Coverage today: global lines/branches/functions from the run, which becomes the starting baseline.
- The setup changes you propose (Step 6), as a file list with one line each.

## Step 5: One round of questions

`AskUserQuestion`, one round, at most 4 questions, recommended option first and labelled `(Recommended)`. The last question is always the approval:

- `Write the binding and open the setup PR` (Recommended)
- `Write the binding only`
- `Change something`

Group small items; if more than three fields need the human, ask for the ones that change behaviour and leave the rest as `<placeholder>` with a `TODO(onboard)` note, reported at the end. `Change something`: apply it, show only the delta, ask again. No answer: stop with nothing written.

## Step 6: Write

**The binding.** Fill `<kit-root>/bindings/PROJECT.md` in place:

- Keep every heading and table shape from the template; replace only placeholders (and, on `refresh`, values whose source changed and the human did not set).
- Commands go in exactly as proven. Secrets never; env var names only.
- Append, or replace, a final section:

```markdown
## Onboarding record

Generated by onboard-project on <date> at HEAD <sha>. Re-run `/onboard-project refresh` after tooling changes.

| Field | Value | Status | Source |
| --- | --- | --- | --- |
| Gates → Unit | `pnpm test` | Verified: 214 passed, 0 failed, 0 skipped | package.json scripts.test |
```

**The setup branch** (only on `Write the binding and open the setup PR`). Branch `chore/onboard-skills-pack` from `origin/<base>`. Only test tooling, each item only when missing:

| Change | When |
| --- | --- |
| Coverage provider dev dependency (e.g. `@vitest/coverage-v8`, `pytest-cov`) | `setup_needed` names it |
| Coverage config: lcov or Cobertura reporter, the source globs as `include`, untested files included (`all`) | the report lacked them in Step 2 |
| `playwright.config.*`: `testDir` = End-to-end folder, `baseURL` from `BASE_URL` or the App URL, `webServer` = the stack command with `timeout: 120_000` and `reuseExistingServer: true`, `reporter: [['html', { open: 'never' }], ['list']]`, projects chromium desktop and a 390x844 mobile, `trace: 'retain-on-failure'`, `screenshot: 'only-on-failure'` | no Playwright config and UI testing is not `(None)`; for an existing config, only the reporter and webServer timeout when the detector lists them as hang risks |
| Every item in the detector's **Hang risks**: a test script in watch mode becomes its run form (`vitest run`, `--watchAll=false`), an interactive migration becomes its non-interactive form against the test database, a foreground dev server in the stack command moves to the background with a wait for the App URL | the detector lists it |
| `@playwright/test` and `@axe-core/playwright` dev dependencies | with the config above |
| `smoke.spec.*` in the End-to-end folder, generated from `ui-map.json`: for every route the walk found, per role it was seen as, the page loads with status < 400, no uncaught exception, no console error, no failed same-origin request, axe has no critical violation. Routes with a known defect from Step 2b are listed with `test.fail()` and a comment naming the `/fix` candidate, never skipped | no smoke spec exists |
| `UI-MAP.md` in the End-to-end folder: routes, forms, roles, the journeys walked and what each showed | always (refreshed on `refresh`) |
| `.env.test.example` with the role env var names, empty values | test accounts were confirmed |
| `.coverage-baseline.json` from the verified coverage run (`coverage_gate.py ... --update-baseline`) | always, unless one exists |
| `.github/workflows/quality-gate.yml` from `<kit root>/templates/`, placeholders filled | only if the human said yes to CI |

Run the gates again on the branch (install, unit, coverage, the smoke spec). Commit with the binding's commit subject shape, push, and open the pull request with the binding's Repository operation, body: what each file is for, the gate results, the baseline numbers. The human merges it. Never commit to the base branch directly.

The binding itself lives under `.claude/`; commit it on the same setup branch when the project versions `.claude/`, otherwise leave it as a local file and say so.

## Output

```markdown
## Onboarded: <repo> · <n> fields filled

| Status | Count |
| --- | --- |
| Verified (ran green) | <n> |
| Detected / inferred | <n> |
| Pack defaults | <n> |
| Answered by you | <n> |
| Left open (TODO) | <n>: <fields> |

**Gates now:** <each gate: green | red (n failing) | not run: why>
**UI walk:** <routes> routes · logins <role: ok/failed> · defects <Blocking n, Major n, Minor n> · <report.html sent>
**Coverage today:** lines <a>% · branches <b>% · functions <c>% (baseline set; new code must reach 95%)
**Setup PR:** <link> | not requested
**Before /build:** <pre-existing red gates to fix, accounts to seed, secrets to add> | nothing

Next: merge the setup PR, run `/project-overview` once to create the map, then `/build <idea>`.
```

## Anti-patterns

- **Asking what the code says.** If a file answers it, read the file.
- **Trusting an unrun command.** A gate in the binding that never ran here is a guess.
- **Inventing secrets or accounts.** Env var names only; the human creates the values.
- **Touching application code** to make a gate green. Record the red gate instead.
- **Overwriting a value the human set,** on a refresh, because detection found something else. Report the disagreement.
- **Wiring CI without asking.** CI is often someone else's area.
- **Committing to the base branch.** Setup goes through a pull request the human merges.
- **Running remote side effects** (deploys, remote databases, paid APIs) while proving commands.
- **Calling the UI tested** because the URL answered. The walk opens a browser, signs in, and looks.
- **Walking production.** The walk runs against the local stack, or a test environment the human names; never a live site with real data.

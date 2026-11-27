# How to use the skills

A cheat-sheet for the Claude Code skills installed in this repo. Configuration: `.claude/skills-pack/bindings/PROJECT.md`.

## First time in a project

```
/onboard-project
```

It reads the repo, runs every command to prove it works, asks you a few questions, fills `.claude/skills-pack/bindings/PROJECT.md`, and opens a setup PR (coverage reporter, Playwright config, smoke test, coverage baseline). Merge that PR, run `/project-overview` once, and the project is ready. After a tooling change: `/onboard-project refresh`.

## The one command

```
/build <your idea in one sentence>
```

1. **Design.** It researches the code and the web and designs the whole feature: journeys, data, API, UI, integrations, tests, and a story map in waves.
2. **Checkpoint (you).** One message with the design and at most four questions: the decisions only you can make (architecture, new paid services, secrets, privacy trade-offs) and "Approve and build".
3. **Build (unattended).** An `epic/...` branch. Per story: implementer, QA, UI tester (Playwright), reviewer. Each story merges into the epic branch only when every check holds. Stories run in parallel when they touch different files.
4. **Epic check.** Every gate on the whole epic, the user journeys tested end to end in the browser, a final review, `ARCHITECTURE.md` refreshed.
5. **Merge (you).** It stops at the epic pull request. You merge it into the base branch. Then tell it, and it closes everything out.

## All commands

| Command | When | What happens |
| --- | --- | --- |
| `/build <idea>` | A new feature from an idea | Everything above |
| `/build EPIC-<N>` | A design `/rnd` already wrote and you approved | Steps 3 to 5 |
| `/fix <what is wrong>` | Something worked wrong, crashed, or regressed (paste the error, a Sentry link, or a screenshot) | Reproduce, root cause, regression test red then green, PR via the four sessions, stops at merge |
| `/release` | After merges, before a deploy | Changelog, version, migration safety, staging verified, production checklist (you deploy) |
| `/security-audit` | Before a launch, before releases, or on a risky PR | Proven findings, each turned into a fix spec |
| `/retro` | After an epic or an incident | Metrics, repeating findings, evidence-backed improvements |
| `/build resume EPIC-<N>` | A build stopped (machine slept, budget hit, stuck story answered) | Continues from the ledger |
| `/rnd <idea>` | You want the design and stories, not the build yet | Steps 1 and 2, writes the design doc and specs |
| `/grill-me <idea>` | The idea is loose and you want it pressure-tested before anything is written | Questions in rounds until nothing is unstated; no files; then `/create-spec` or `/rnd` in the same conversation |
| `/handoff` | You are about to start a new conversation, hit a limit, or hand the work over | Writes `HANDOFF.md` at the root: goal, progress, what worked, what did not, next steps, the resume command |
| `/create-spec <idea>` | One small, specific change you want to specify by answering questions | One spec file |
| `/ship story-<N>` | A ready spec, straight to a PR on the base branch | Implementer + QA + UI + review, stops at merge |
| `/orchestrate-delivery story-<N>` | Same as `/ship` with you relaying decisions | |
| `/project-overview` | After a structural change made outside `/build` | Refreshes `ARCHITECTURE.md` |
| `/onboard-project [refresh]` | Once after install; again after tooling changes | Fills or refreshes the binding from the repo |

## The quality bar on every pull request

| Check | Bar |
| --- | --- |
| Tests | 100% green, whole suite, on the current head |
| Skips | None added (`.skip`, `.only`, `xit`, coverage-ignore, `@ts-ignore`...) unless the line says `hygiene-allow: <reason>` and the reviewer accepts it |
| Flaky | Suite runs twice; one red run fails the gate |
| New code | 95% of changed lines and branches covered |
| Whole project | Coverage never below `.coverage-baseline.json`; it ratchets up to 95% |
| UI | Every criterion with a screen proven in the browser, with screenshots, and kept as a Playwright spec |

## Things to know

- **You always merge into the base branch.** Stories merge into the epic branch automatically; the epic reaches `main` only through you.
- **The checkpoint is the only question round.** If you do not answer it, nothing is built and nothing is guessed.
- **Secrets are never created for you.** Integrations are built against the provider's sandbox and fail closed without the key; the epic PR lists exactly which secrets to add before merging.
- **Nothing waits forever.** Every gate command runs with a time limit and is stopped if it hangs; the coordinator checks every 30 minutes for silent sessions and unblocks or replaces them. If you still see an agent running for hours with few tokens, tell the coordinator: "run the watchdog now".
- **A stuck story stops alone.** It is reported to you at once; stories that do not depend on it keep going.
- **`/build` has a token budget.** 600,000 tokens per run by default (`## Epic delivery → Budget: tokens`), coordinator and every session together. At 85% nothing new starts and you get a report; raising it is your decision. Small stories get two sessions (fast track), others three or four, plus two for the epic. Use `/create-spec` + a direct edit for a typo.
- **Each session runs on the model the coordinator picks** (`## Models`): large for design, security, and the epic review; standard for most work; small for UI testers. The epic PR says how many sessions ran on each.
- **Stories run in parallel whenever the code allows.** A story starts as soon as its dependencies have an open, clean pull request, not after they merge. `Max parallel stories` caps how many run at once on your machine.

## Config and updates

- Everything project-specific is in `.claude/skills-pack/bindings/PROJECT.md`. `## Coverage`, `## UI testing`, and `## Epic delivery` must be filled for `/build`.
- The skills come from the skills pack repo. To update: edit there, then re-run its `install.sh <this-repo-root>`.
- To update every project at once: `install.sh --upgrade-all` in the pack; `install.sh --enable-auto-upgrade` there makes every `git pull` of the pack do it. New binding rows after an upgrade: `/onboard-project refresh`.
- To see whether this repo's installed copy is current: `install.sh --check <this-repo-root>` (add `--json` for a script). It lists the version, every skill or kit file that differs or is missing, and under `Binding:` every section, row, or `<placeholder>` value this repo's `PROJECT.md` still lacks against the pack's template; it changes nothing. Exit 0 when current and complete, 1 when a re-install is due or the binding lacks something (then `/onboard-project refresh` fills exactly the listed lines), 2 on a usage error, when the pack is not installed, or when a file cannot be read.

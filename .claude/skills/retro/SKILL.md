---
name: retro
description: Learns from finished runs so the pipeline gets better every time. Reads the ledgers, pull requests, review threads, QA and UI verdicts, and fix specs of recent builds and fixes; measures where time and rounds went; finds the findings that keep repeating and the escaped defects that tests missed; and proposes concrete changes to the project's binding, rules doc, specs format, or to the skills pack itself, each tied to evidence. Use after an epic merges, after a production incident, or periodically. Proposes; changes nothing without the human's yes.
argument-hint: (none) = since the last retro | <EPIC-KEY> | last <N> runs
---

# Retro

Scope: **$ARGUMENTS**. Empty: every run since the last retro (the newest file in the retro folder), or the last 30 days when there is none.

A retro is useful only when it changes something. Every proposal names the evidence, the change (a diff or the exact text), and how the next retro will tell whether it worked.

## Step 0: Gather the runs

Read `<kit-root>/bindings/PROJECT.md` (Sessions notes folder, Epic delivery, `## Skills pack → Retro`: retro folder, metrics to track). Then collect, read-only:

- every ledger in the notes folder in scope (`scripts/ledger.py --file <f> show --json`)
- the pull requests they name: bodies, review rounds, every review thread and its resolution, QA and UI verdict comments, CI runs and their failures
- fix specs (`type: bug`) created in the period, especially those whose bug shipped (found after a merge, or in production)
- security audit reports and release checklists in the period
- the previous retro's proposals and the metrics it set

## Step 1: Measure

Compute per run and in total, from the data (no estimates):

| Metric | From |
| --- | --- |
| Stories, waves, sessions started, restarts | ledger |
| Wall time per story: started to merged into epic | ledger timestamps, pull request events |
| Review rounds per story; stories that went `stuck` | ledger |
| Findings by severity and by source (QA, UI, review, automated reviewer, epic verification) | verdicts and threads |
| Gate failures by gate (lint, types, unit, coverage, hygiene, flake, e2e) and how often a push failed CI after passing locally | pull request checks |
| Coverage: diff coverage per pull request, global trend | quality-gate tables |
| Escaped defects: bugs found after a story merged, and at which level they were caught (epic verification, staging, production) | fix specs, their `epic:` and dates |
| Budget used vs estimate at the rnd checkpoint: sessions, hours, tokens | ledger, design |
| Tokens per session by role and by model tier; sessions that reported no count | ledger (`tokens`, `model`) |
| Model tier vs outcome: rounds and findings per tier per role (a standard-tier implementer that needed 3+ rounds; a large-tier verifier that found nothing) | ledger, verdicts |
| Parallelism: critical path vs stories, stories started early (`start_early`) and how many of those needed a sync after a dependency REVISE, idle time of pending stories whose dependencies were open | ledger, design's Parallelism line |
| Fast-track stories: escaped defects compared with full-track ones | ledger, fix specs |
| Human interventions: questions asked, decisions relayed, stuck stories resolved | ledger log `kind: question`, `blocked` |

## Step 2: Find the patterns

Look for causes, not anecdotes. A pattern needs at least two occurrences or one escaped Blocking defect.

- **Repeated findings**: the same kind of review or QA finding in several pull requests (missing tenant check, missing loading state, untranslated strings, missing index). Each is a rule the implementer did not know: it belongs in the architecture rules doc, the spec template, or `write-tests` classes for this project.
- **Escaped defects**: for each bug that passed every gate, find the layer that should have caught it, and why it did not (no criterion covered it, the test asserted too little, the UI walk did not reach the page, the role was not in the test accounts).
- **Slow stories**: what took the rounds (vague criteria, design gaps found late, flaky tests, shared-file conflicts across a wave), and what took the wall time (waiting on a dependency that could have started early, installs per worktree, verifiers re-running the full suite).
- **Cost**: which roles and tiers spent the tokens; whether a tier change per `rules/model-selection.md` (binding → Models) would have changed the outcome.
- **Spec quality**: criteria that QA marked ambiguous or NOT VERIFIABLE; decisions rnd made that the human later reversed.
- **Pipeline friction**: refused session starts, dead sessions, lock contention, budget hits, gates that are slow.

## Step 3: Propose changes

At most seven proposals, highest impact first. Each:

```markdown
### P<n>: <one-line change>
**Evidence:** <the occurrences, with pull request and finding links>
**Change:** <where: binding row | rules doc section | spec template | a skill in the pack> and the exact text or diff
**Expected effect:** <which metric moves, by how much>
**Check next retro:** <the measurement>
```

Where proposals go:

- **Project-specific** (a rule about this codebase, a test account, a gate command, a threshold): the binding, the architecture rules doc, the spec template, the test seed. The human approves, then you apply them on a branch `chore/retro-<date>` through a pull request, under the normal gates.
- **About the pack itself** (a skill step that misleads, a missing check in `ui-test`, a better default): written as a proposed patch to the skills pack repository with the evidence, for the human to apply there and re-install with `install.sh`. Never edit the installed copies in `.claude/` directly; the next install overwrites them.

## Step 4: Ask once, apply, record

`AskUserQuestion`, one round: which proposals to apply (multi-select, recommended ones first). Apply the chosen project-specific ones through a pull request; write the pack proposals as a patch file in the retro folder. Then write the retro record `<retro folder>/<date>.md`: scope, metrics table, patterns, proposals with their decision (applied, rejected with the human's reason, deferred). The next retro starts from it.

## Output

```markdown
## Retro <date> · <runs in scope>

| Metric | This period | Previous | Trend |
| --- | --- | --- | --- |

**Top patterns:** <three lines>
**Escaped defects:** <n> (<where caught>) | none
**Applied:** <proposals, PR link> · **Pack patches:** <path> · **Rejected/deferred:** <with reasons>
```

## Anti-patterns

- A retro with no change at the end.
- Blaming a session or a person instead of finding the missing rule, test, or criterion.
- A proposal with no evidence, or one occurrence presented as a pattern.
- Editing the installed skills in `.claude/` instead of the pack repository.
- Lowering a quality bar (coverage, flake runs, the merge gate) to make metrics look better. That is a reserved decision and needs a very good reason.

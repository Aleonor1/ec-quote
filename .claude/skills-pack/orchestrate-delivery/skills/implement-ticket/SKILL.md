---
name: implement-ticket
description: Implements one human-named ticket test-first through an open pull request, owning the branch when invoked directly. Use when a brief or a human names one ticket key to build. Do not use to pick the ticket, to review someone else's pull request, or to start a second ticket when this one is done.
---

# Skill: implement-ticket

**When to use:** implementing one ticket. This skill classifies the change, writes the tests first, implements, updates the docs the project lists, and opens the pull request when it was invoked directly.

**The ticket is named by a human or by the coordinator's brief.** No key, ask and stop. Never infer one.

**Do not use for:** reviewing someone else's code (`skills/review-code/SKILL.md`), or deciding a contested approach. That goes back to the human.

## Inputs

| Input | Source | Required? |
| --- | --- | --- |
| Ticket key | the human or the brief | Yes |
| Ticket body | `skills/lookup-ticket/SKILL.md` | Yes |
| Gates, docs, protected paths, obligations | `bindings/PROJECT.md` | Yes |

## Workflow

### Step 1 — Establish the ticket and who owns git

Read the ticket. **Invoked directly**, which is how `skills/orchestrate-delivery/` briefs you: you own the branch, the commits, and the pull request. **Coordinator-dispatched inside one session:** git stays with the coordinator; this skill ends at a clean tree and a report, and `skills/open-pr/` is not run.

A plan file is a design record. Read it when the ticket reworks a surface it already shipped. Never take the next entry in it as your scope.

### Step 2 — Verify the premise

Check every factual claim the ticket makes about what already exists. Record verified present and verified absent. A ticket whose design assumes code that does not exist stops here and goes back.

### Step 3 — Classify

List the areas the change touches, in the order they must be built. An area that matches no pattern the repository already uses is reported, not invented.

### Step 4 — Write the tests first

Run `skills/write-tests/SKILL.md` for the whole ticket before any production code. Confirm each new test fails for the reason the criterion describes.

When the change adds or changes something a caller can observe and `bindings/PROJECT.md` → Gates has an end-to-end command, update those flows in the same change, following `skills/write-e2e-tests/SKILL.md`. When the gate is `(None)`, say so.

### Step 5 — Implement, one area at a time

Complete one testable area before starting the next. Make the smallest change that turns the tests green. Follow the repository's existing patterns for each technology.

### Step 6 — Refactor with the tests green

Improve structure without changing behaviour, then re-run the affected tests. Unrelated refactoring stays out.

### Step 7 — Walk the obligations

Every row in `bindings/PROJECT.md` → Obligations, plus the defaults that section states, is satisfied or N/A with a reason.

### Step 8 — Update the living documentation

Run `skills/update-living-docs/SKILL.md`.

### Step 9 — Run the gates

Run every command in `bindings/PROJECT.md` → Gates that is not `(None)`, the way that table says to run it, each through `scripts/run_gate.py` (heavy ones through `scripts/heavy-run-lock.sh run`, which wraps it). A red end-to-end flow is fixed before hand-off: in the code when the code regressed, or in the flow when this ticket moved the behaviour on purpose. Report every failure. Do not round up. Evidence follows `rules/verification-before-claiming.md`.

Then run `rules/test-quality-gate.md`: the hygiene scan, the flake repeat, and the coverage gate against `origin/<base>` (the epic branch when this is a build). Uncovered changed lines go back to Step 4: write the test that exercises the behaviour, not one that only executes the line. When the global numbers rose, raise the baseline in this change. The five-row evidence table goes in the pull-request body.

### Step 10 — Hand off

Invoked directly: run `skills/open-pr/SKILL.md`, then message QA, UI test, review, and the coordinator as the brief describes. This skill implements one ticket and stops.

## Output

```markdown
## Implemented — <TICKET-KEY> <summary>

**Dispatch:** <invoked directly | coordinator-dispatched>
**Premise:** verified present: <…> · verified absent: <…>
**Areas:** <in build order>
**Files changed:** <path — one line>
**Tests added:** <path, what it asserts, which criterion>
**Gates:** <each command, the observed result>
**Quality gate:** <green counts · hygiene · flake n/n · diff lines/branches % · global vs baseline>
**Obligations:** <each row — satisfied, or N/A + reason>
**Documentation:** <surfaces updated, or N/A>
**Deviations:** <what and why, or (None)>
**Hand-over:** <what was not implemented, or (None)>
**Next:** <open-pr, or the report to the coordinator>. Never the next ticket.
```

## Pre-Completion Checklist

| # | Check | How to verify |
| --- | --- | --- |
| 1 | The key came from a human or the brief | The report names it |
| 2 | Premise searched before code | Both premise rows populated |
| 3 | Tests written first and seen failing | The report states the failure reason per test |
| 4 | One area at a time | No area left half-done |
| 5 | Gates observed, not predicted | Each row has output |
| 6 | Protected paths untouched | The diff contains none of the paths in the binding |
| 7 | Exactly one ticket | No work from another ticket in the diff |
| 8 | End-to-end updated or explicitly N/A | The binding's end-to-end row was followed |
| 9 | Test quality gate holds on the head | All five checks observed after the last edit |
| 10 | The UI tester's specs are committed | Every spec it sent is in the end-to-end folder, or answered with a reason |

## Anti-patterns

- Writing the implementation and then the tests.
- Interleaving areas so the diff cannot be reviewed.
- "While I'm here" refactoring.
- Reporting a gate green from a subset, or from the host when the binding says containers.
- Continuing into the next ticket because the context is warm.
- Editing a protected path because filing the change properly is slower.

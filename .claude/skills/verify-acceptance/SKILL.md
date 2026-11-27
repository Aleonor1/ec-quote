---
name: verify-acceptance
description: Exercises each acceptance criterion against the running system or the real entry point and returns PASS, REVISE, or BLOCK without changing code. Use when QA verifies a pull request for a named ticket. Do not use to review the diff for defects, or to fix a failure.
---

# Skill: verify-acceptance

**When to use:** deciding whether a change satisfies its ticket, by exercising it. The criteria are quoted verbatim. This skill never fixes code.

**Do not use for:** a code review (`skills/review-code/SKILL.md`), or testing through the screen (`skills/ui-test/SKILL.md`, a sibling session; share findings with it rather than duplicating its charters). A missing permanent flow is handed to the implementer, specified with `skills/write-e2e-tests/SKILL.md` when that layer exists.

## Workflow

### Step 1 — Load the criteria verbatim

Do not paraphrase or merge them. An ambiguous criterion is a finding against the ticket. Record both readings. Do not pick the one that passes.

### Step 2 — Read the diff to find the surfaces

The diff says where to probe. It does not say whether the behaviour is right.

### Step 3 — Bring up what the binding names

When `bindings/PROJECT.md` → Gates has a stack command, verification runs against that, started in the background and stopped when you finish; every command you run goes through `scripts/run_gate.py`. A process started by hand on the host does not count when the binding says containers. When the stack command is `(None)`, exercise the real entry point the project does have, and say what that was.

### Step 4 — Exercise each criterion

Drive the change through its entry point. Record what happened. Cover the positive case and the ones that apply: the negative, the boundary, the wrong account or tenant, a missing permission and that the denial is closed, a malformed body, an unknown id, a duplicate, a retry, and a dependency down where the change claims degradation. Mark N/A only with the reason.

### Step 5 — Asynchronous work through its own channel

Assert through what a caller observes. A log line corroborates. It is not the proof.

### Step 6 — Verdict

Each criterion is PASS, FAIL, or NOT VERIFIABLE with the reason. Overall, follow `rules/severity-and-gates.md`. Any failing criterion is at least Major. A failing security or tenancy criterion is Blocking. A NOT VERIFIABLE criterion does not become a PASS overall. It is named, with the step that would make it verifiable.

### Step 7 — Hand off

Post the verdict on the ticket. Send it to the reviewer with the head SHA, and a one-line verdict to the coordinator. Failures go to the implementer with the exact reproduction. Do not change code.

## Output

```markdown
## Acceptance verdict — <TICKET-KEY> · **<PASS | REVISE | BLOCK>**

**Exercised on:** <stack command, or the entry point> · **head:** <sha>

| # | Criterion (verbatim) | How exercised | Observed | Verdict |
| --- | --- | --- | --- | --- |

### Failure paths

| Path | Expected | Observed | Verdict |
| --- | --- | --- | --- |

**Not verifiable:** <criterion + the step that unblocks it, or (None)>
**Beyond the criteria:** <severity + what, or (None)>
**Reproduction for each FAIL:** <exact steps and the observed result>
```

## Pre-Completion Checklist

| # | Check | How to verify |
| --- | --- | --- |
| 1 | Criteria are verbatim | Each row matches the ticket |
| 2 | Every criterion has a verdict | No blank cell |
| 3 | Failure paths are PASS, FAIL, or N/A with a reason | No "assumed" |
| 4 | Each FAIL has a reproduction | Exact enough to re-run |
| 5 | No code was changed | The tree is the pull-request head |

## Anti-patterns

- Reading the code and concluding the behaviour is correct.
- Rewriting an ambiguous criterion into one that passes.
- PASS overall while a criterion is NOT VERIFIABLE.
- Fixing the bug, which removes the independence this role exists for.

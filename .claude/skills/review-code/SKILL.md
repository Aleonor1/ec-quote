---
name: review-code
description: Reviews one pull request against its ticket, the gates, and the diff, and returns PASS, REVISE, or BLOCK without approving or editing the branch. Use for the code-review session in an orchestrated delivery, or when a human asks to review a pull request. Do not use to verify behaviour by exercising it, or to fix findings.
---

# Skill: review-code

**When to use:** an independent read of a pull request against the ticket, the gates, and the conventions. Under `skills/orchestrate-delivery/` this skill also follows `rules/unattended-review.md`.

**Do not use for:** exercising the criteria (`skills/verify-acceptance/SKILL.md`), reviewing a document (`skills/co-review/SKILL.md`), or fixing a finding.

## Workflow

### Step 1 — Read the preconditions, then continue

The pull-request body should carry the sections `bindings/PROJECT.md` → Repository requires, including gate results. Under `rules/unattended-review.md` a missing section is a Major and the review continues on the diff. Outside that rule, return the pull request for the missing section before a full review.

### Step 2 — Ticket, then diff

Run `skills/lookup-ticket/SKILL.md`, then read the diff. Criteria first.

### Step 3 — Walk `rules/review-protocol.md`

In order. Verify each suspicion against the surrounding code before raising it.

### Step 3b — The test quality gate

Re-run `rules/test-quality-gate.md` on the reviewed head yourself: the coverage gate against the pull request's base, and the hygiene scan. Do not take the body's table on trust. Judge every `hygiene-allow` reason, every new exclude glob, and every test that covers a line without asserting its behaviour. Grade failures with the rule's severity table. Read the UI tester's verdict when the ticket has a UI surface; a missing or non-PASS UI verdict means the merge gate does not hold.

### Step 4 — Grade

Severity from `rules/severity-and-gates.md`. The verdict is the maximum: BLOCK on any Blocking, REVISE on any Major, otherwise PASS with Minors listed.

"Ready for a human to merge" only when the merge gate holds on the reviewed head. Otherwise name what is still red or pending.

### Step 5 — Post and stop

Inline comments in the shape of `rules/comment-shape.md`. The summary is the review body. Do not approve. Do not commit. Do not merge. The implementer reworks. A human merges.

## Output

```markdown
## Review — <PR #N> · <TICKET-KEY> · **<PASS | REVISE | BLOCK>**

**Preconditions:** <ok, or which are missing>
**Matches the ticket:** <yes | the diff does X, which no criterion asks for | criterion N is unaddressed>
**Evidence:** <gates observed or not> · **QA:** <attached, pending, or N/A> · **UI:** <attached, pending, or N/A + reason>
**Quality gate (re-run):** <diff lines/branches % · global vs baseline · hygiene · flake>

### Findings

| # | Severity | Location | Finding | Failure it produces | Fix |
| --- | --- | --- | --- | --- | --- |

### Tests

| Criterion | Test | Would fail without the change? |
| --- | --- | --- |

**Next:** <rework items | ready for a human to merge>
```

## Pre-Completion Checklist

| # | Check | How to verify |
| --- | --- | --- |
| 1 | The ticket was read before the diff | The match row names criteria |
| 2 | Every finding names a concrete failure | No blank failure cell |
| 3 | The verdict is the maximum severity | BLOCK if any Blocking, REVISE if any Major |
| 4 | Nothing was approved, merged, or fixed | No approval, no commit |
| 5 | The quality gate was re-run, not read | The coverage and hygiene output is from this session, on this head |

## Anti-patterns

- Reviewing the diff without the acceptance criteria.
- Accepting "all tests pass" with no output.
- A Major on a suspicion one read would have settled.
- Style graded Major.
- Writing the missing test into the review branch.

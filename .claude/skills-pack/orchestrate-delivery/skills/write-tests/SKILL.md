---
name: write-tests
description: Writes the unit, integration, and contract tests for one ticket before production code exists, and confirms each new test fails for the criterion's reason. Use at the start of implement-ticket or when a review found missing coverage. Do not use for an end-to-end flow, or to add tests after the implementation is already written.
---

# Skill: write-tests

**When to use:** authoring the tests that ship with a change, before the production code exists.

**Do not use for:** an end-to-end flow (`skills/write-e2e-tests/SKILL.md`), or for tests added after the implementation. That inverts this skill and needs an explicit human exception.

## Workflow

### Step 1 — Derive cases from the criteria

For each acceptance criterion, write the cases that would fail if the criterion were unmet. Derive them from the criterion and from any contract the ticket cites, not from the implementation you intend to write.

### Step 2 — Cover the classes that apply

Walk them and record which apply: positive, negative, boundary, security, concurrency, idempotency and replay, failure and degradation, schema compatibility. For an operation a caller invokes, also consider authentication failure, authorization failure, a tenant or account boundary, not-found, conflict, a duplicate request, an idempotent retry, a dependency failure, and a malformed dependency response. Mark N/A the ones the criterion does not have.

### Step 3 — Place each test at the right layer

Unit for logic with the edges mocked. Integration against the real local dependency when `bindings/PROJECT.md` → Gates has an integration command. Contract tests derived from the specification when the project has one. Prefer a real local dependency over a mock wherever one exists.

### Step 4 — Confirm they fail correctly

Run them. Every new test fails, and the failure message matches the missing behaviour. A test that already passes is not a test of this change. A test that fails on a missing import proves nothing yet.

### Step 5 — Aim at the coverage gate

The change must end at or above `bindings/PROJECT.md` → Coverage → Diff minimum on its changed lines and branches (`rules/test-quality-gate.md`). Plan for it now: every branch the criterion implies (each `if`, each error path, each guard) gets a case, so coverage follows from the behaviour instead of being chased afterwards. When the gate later reports an uncovered line, ask which behaviour it serves and test that behaviour; if it serves none, it should not be in the change.

### Step 6 — Map every test

Record test path, what it asserts, and the criterion it covers.

## Output

```markdown
## Tests written (red) — <TICKET-KEY>

| Test path | Layer | Asserts | Criterion |
| --- | --- | --- | --- |

**Classes:** <each class — covered by which test, or N/A because>
**Observed failures:** <the failure message per new test>
**Criterion with no test:** <which, and why, or (None)>
```

## Anti-patterns

- A test that asserts the design you plan to write, rather than the criterion.
- A green test presented as coverage of a change that is not written yet.
- Mocking a dependency the project already runs locally.
- A test that runs a line and asserts nothing about it, written to move a coverage number.
- `.skip`, `.only`, or a coverage-ignore comment to get past the gate.

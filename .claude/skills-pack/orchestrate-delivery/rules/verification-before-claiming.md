# Verification before claiming

No status claim without fresh evidence that settles it. This covers a gate, a suite, a ticket called done, a defect called fixed, and any wording that implies success.

## The gate

Before the claim leaves the report: name the command or read that would falsify it, run it fresh and whole, read the exit code and the counts, and state the claim together with the evidence. A claim whose falsifying check was not run is not made. The actual state is reported instead.

## Fresh means after the last change

Evidence from before the most recent edit proves the previous tree. That includes a suite that passed before a fix that "could not possibly" have affected it.

## Whole means the whole thing

A subset run proves the subset. A gate reported from a filtered run names the filter, or it is not that gate. An integration gate runs the way `bindings/PROJECT.md` → Gates specifies. A host-side pass is not evidence for a container gate.

## A session's report is a claim, not evidence

A session reporting success has told you what it believes. The coordinator verifies independently — the pull request, the head, the checks — before repeating the claim. This is the same standard a role applies to work it did not perform.

## A regression test is proven red, then green

Claiming a test guards a defect requires having watched it fail without the fix and pass with the fix. A test that has only ever been seen green guards nothing yet.

## Partial results are enumerated

Failing, skipped, and flaky items are named with their reason. A pre-existing failure is identified by checking it on the base, not by assertion.

## What settles which claim

| Claim | Evidence that settles it | Does not settle it |
| --- | --- | --- |
| The suite passes | The full run's output, with counts and exit code | An earlier run, a filtered run, "nothing I touched" |
| Types and lint are clean | Each command's own output | The suite passing |
| The defect is fixed | The original symptom exercised and gone | The code changed as designed |
| The test guards it | The red-then-green cycle observed | The test passing once |
| The session did it | The pull request and the diff read | The session's report |
| The criteria are met | Each criterion walked | The suite passing |

## Anti-patterns

- "Should pass now" in place of output.
- Reporting a gate green from a run made several edits ago.
- Repeating a session's "all tests pass" without reading the pull request.
- Calling a failure pre-existing without checking the base.

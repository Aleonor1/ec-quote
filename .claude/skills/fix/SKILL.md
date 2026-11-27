---
name: fix
description: From a bug report to a merge-ready fix. Takes a description, a stack trace, an error-tracker link, a screenshot, or a ticket key; reproduces the bug at the lowest layer that shows it; finds the root cause (bisecting when it is a regression); writes a bug spec whose first acceptance criterion is a regression test proven red on the base; then ships it through the same implementer, QA, UI-test, and review sessions as every other change, and stops at the merge gate. Use for anything that worked wrong, crashed, or regressed. Do not use for new behaviour (that is build or create-spec), or to merge.
argument-hint: <bug description | stack trace | error link | ticket key>
---

# Fix

The bug is: **$ARGUMENTS**

If it is empty, ask the human what is wrong, where they saw it, and what they expected, in one question, and stop.

A fix is done when the symptom is gone, a test that failed before now passes and stays in the suite, the cause (not only the symptom) is addressed, and nothing else changed. This skill does the investigation itself, then hands the change to the delivery kit so the person who fixed it is never the only one who checked it.

## Step 0: Load the binding

Read `<kit-root>/bindings/PROJECT.md`: Identity, Tracker, Gates, Coverage, UI testing, Reserved decisions, `## Skills pack → Spec authoring`, and `## Skills pack → Bug fixing` (error sources, postmortem folder, severity scale). A binding full of `<placeholder>` values: send the human to `/onboard-project` and stop.

## Step 1: Intake

Gather everything the report points to, read-only:

- A stack trace or error message: find the frames in this repository and open them.
- An error-tracker link (Sentry and similar): read the event through its connector when one is connected (the binding's Error sources), including breadcrumbs, release, user agent, and how many users and events. No connector: use what the human pasted, and say that more detail would help.
- A screenshot or recording: read it for the screen, the data on it, the role, and the device.
- A ticket key: run `lookup-ticket`.

Then write down, before any theory: **observed**, **expected**, **where** (screen, endpoint, job), **who** (role, tenant), **when** (since which release or date, always or sometimes), **how often**. Grade the severity with the binding's scale:

| Severity | Meaning |
| --- | --- |
| P0 | data loss or corruption, security or tenant leak, money wrong, the product is down for everyone |
| P1 | a core journey broken for many users, no workaround |
| P2 | a journey broken with a workaround, or for few users |
| P3 | cosmetic, copy, edge case |

A P0 that is a live security exposure is reported to the human **at once**, before investigating further. It may need a decision this skill cannot make (take a feature down, rotate a key).

## Step 2: Reproduce

No reproduction, no fix. Bring up the local stack from the binding and reproduce the bug in the cheapest way that shows it, trying layers from the bottom:

1. A unit test calling the function with the failing input.
2. An integration test through the route or job with the real local dependency.
3. A Playwright run through the screen, when the bug only shows there (layout, client state, a browser).

Seed the data the report implies. Use the role and viewport the report names. Record the exact steps and the observed output.

When it does not reproduce after a bounded effort (the inputs from the report, the release it names, the role, the viewport, production-like data volume, a race forced by running twice concurrently), stop. Report what you tried and what you saw, and ask the human for the one missing fact most likely to unlock it. Never fix a bug you could not see.

## Step 3: Find the root cause

Work from evidence, one hypothesis at a time, each with the observation that would disprove it:

- **Is it a regression?** Find a commit where it worked (a release tag, the date from the report). If there is one, turn the reproduction into a script that exits non-zero on the bug and run `git bisect run` between that commit and `origin/<base>`. The first bad commit and its diff usually name the cause.
- **Read the history of the lines involved** (`git log -L`, `git blame`) for why they are the way they are. A line that looks wrong may be guarding something.
- **Ask why five times.** "The total is wrong" → "the discount is applied twice" → "the hook runs on both create and update" → ... Stop at the cause a change can remove, not at the line that throws.
- **Same cause, other places.** Search the code for the same pattern (the same misused helper, the same missing check). Every instance with the same cause is fixed in this change. A different cause is a different bug: note it as a follow-up.
- **Data damage.** If the bug wrote wrong data, measure which rows and since when. Repairing them is a separate, reviewed script, never part of the code fix, and never run by this skill against anything but a local database.

The outcome is one paragraph: the cause, the evidence that proves it, why it produced the symptom, and every place it occurs.

## Step 4: Write the bug spec

One spec file in the binding's spec folder, house format, with `type: bug` and `severity: P<n>` in the frontmatter (and `epic:` when the bug was found during a build). Sections:

- **Summary:** observed versus expected, in one paragraph.
- **Reproduction:** exact steps, data, role, and the observed output.
- **Root cause:** the paragraph from Step 3, with the bisected commit when there is one.
- **Scope:** **In:** the cause, at every place it occurs. **Out:** the follow-ups with a different cause, the data repair when there is one, any refactor.
- **Acceptance criteria**, always starting with these, then any specific to the bug:
  1. A regression test reproducing the report exists at the lowest layer that shows the bug, fails on `origin/<base>` with the reported symptom, and passes with the fix.
  2. The reproduction from this spec, run as written, no longer shows the symptom (through the screen when the report came from the screen).
  3. Every other place the root cause occurs is fixed and covered by a test.
  4. No behaviour outside the bug changes: the existing suite is green and no existing test was edited to pass, except a test that asserted the buggy behaviour, which the pull request names and justifies.
- **Data repair** (only when data was damaged): the affected rows, the repair script's location, and a Hand-over line: the human runs it, after the merge, against the real database.
- **Hand-over:** anything outside the human's areas (binding).

The spec must pass the Definition of Ready. If fixing the cause changes behaviour users rely on, or needs a reserved decision (an architectural change, a migration that cannot be undone, a security trade-off), that is the checkpoint: ask the human once, with your recommendation, before shipping. Otherwise there is no question to ask.

## Step 5: Ship it

Hand the spec to the coordinator exactly as `ship` does (`<kit-root>/orchestrate-delivery/skills/orchestrate-delivery/SKILL.md`, base = the binding's base branch, or the epic branch when the bug came from a build), with this standing approval:

> **Standing approval for fix <KEY>:** implement the fix test-first starting from the regression test, open the pull request, run the gates and `rules/test-quality-gate.md`, loop QA, UI test, and review to a final verdict, and make the routine writes that needs. Stop and ask for anything in the binding's Reserved decisions, any behaviour change beyond the spec, and the merge.

Fix stories are always on the full track (never the fast track). Models per `rules/model-selection.md`: P0 and P1 bugs run the implementer, QA, and review sessions on the large tier; P2 and P3 on the binding's defaults. Write the tiers into the spec's `models:` frontmatter so the coordinator reads them.

Render the briefs with these bug-specific instructions:

| Session | Adds |
| --- | --- |
| Implementer | Start from the reproduction and root cause in the spec; do not re-investigate unless the evidence fails. Commit the regression test first, in its own commit, and record its red run against `origin/<base>` in the pull-request body. Smallest change that removes the cause; no refactoring beyond it. |
| QA | Run the spec's reproduction verbatim on the head: the symptom must be gone. Revert the fix locally and confirm the regression test fails with the reported symptom. Probe the neighbours: the same input on the other places the cause occurred, the boundary around the failing value. |
| UI test | When the report came from the screen, the reproduction is charter 1, replayed in the role and viewport of the report, with before (on base) and after screenshots. N/A with a reason otherwise. |
| Review | Does the change remove the cause or mask the symptom (a `try/catch`, a null check, a retry around the real problem is a Major unless the spec says why)? Every place the cause occurs is fixed? No unrelated change? Was any existing test edited, and is that justified? |

## Step 6: Stop at the merge gate

```markdown
## Fix ready to merge: <KEY> · <severity> · <title>

**Cause:** <one sentence> <(introduced in <sha>, found by bisect)>
**PR:** #<N> · head <sha> · base <base>
| QA | UI | Review | Regression test red on base | Coverage | CI |
| --- | --- | --- | --- | --- | --- |
| PASS | PASS / N/A | PASS | yes: <test path> | diff <x>% · global <y>% | green |

**Also fixed:** <other places the same cause occurred> | (None)
**Follow-ups (different cause):** <spec keys written, not shipped> | (None)
**After you merge:** <run the data repair script <path> against <db>, deploy, tell affected users> | nothing

**Your move:** review PR #<N> and merge it. I do not merge.
```

For P0 and P1, after the human confirms the merge, offer a short postmortem in the binding's postmortem folder (what happened, impact, cause, why tests did not catch it, what changes so it cannot recur). Offer; do not write it unasked.

## Several bugs at once

Each bug gets its own spec and its own pull request. Bugs with the same root cause are one bug. Independent bugs that touch different files ship in parallel, like `ship` with several keys.

## Anti-patterns

- **Fixing without reproducing.** A change that "should" fix it is a guess with a commit message.
- **Fixing the symptom.** Catching the exception, adding a null check, or retrying, while the cause stays.
- **A regression test that never failed.** Written after the fix and only ever seen green.
- **Testing at the top when the bottom shows it.** A Playwright test for a rounding error in one function.
- **Editing an existing test until it passes** without naming it as a test that asserted the bug.
- **Fixing one of three places** the same cause occurs.
- **Bundling the refactor,** or the unrelated bug noticed on the way.
- **Running a data repair** against anything but a local database, or folding it into the code fix.
- **Merging,** even a P0. The merge is the human's.

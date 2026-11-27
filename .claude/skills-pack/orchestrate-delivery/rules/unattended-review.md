# Unattended review

The interactive review has a person dropping noise before anything is posted. This loop does not. This rule is what replaces that person.

## When this rule applies

Any review where nobody can answer a question before the review is posted. `skills/orchestrate-delivery/` runs code review this way.

## One review, one verdict, never an approval

The run submits exactly one pull-request review per push. A second review on the same push is a duplicate. The body carries the verdict and the output tables of `skills/review-code/SKILL.md`. Inline comments use `rules/comment-shape.md`.

The role never approves. Approval is a human act under `rules/human-approval-gate.md`. A session that runs as the pull-request author posts a comment review, because it cannot approve or request changes. Where the session is a different account, BLOCK and REVISE request changes and PASS is a comment. Still never an approval.

## A missing ticket becomes a finding, and the review continues

A pull request that changes behaviour and carries no ticket is a Major, and the review proceeds on the diff. Repository tooling, CI, and the agent setup may change with no ticket when the pull-request body says so in its first line and the change preserves behaviour. If a test had to change, the behaviour changed, and the exemption is gone.

A missing gate-results block or a missing required pull-request section is a Major. The review still proceeds.

## The verdict is always stated

A run that finds nothing still submits a review carrying its verdict and the reason it holds no comments. An empty body reads as a broken run.

## Silence on findings that do not hold

Verify each suspicion against the surrounding code before raising it. Drop anything that is style-only unless it violates a cited convention. Do not repeat a finding already posted on an unchanged line. A risk the project has already accepted in writing is a Note, unless the diff widens the exposure.

## The reviewer does not change the diff

No commits, no pushes, no labels, no edits to the pull-request title or body, no comments outside the review. The reviewer who changes the diff has stopped being an independent reader of it.

## Anti-patterns

- Approving because no finding reached Major.
- Posting a Note inline.
- Re-raising the same finding on every push.
- Submitting a second review to extend the one just posted.
- A review body that restates the diff.
- Fixing the finding from inside the review session.

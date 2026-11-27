# Brief template — implementer session

Rendered by `SKILL.md` → Step 4. Replace every `<placeholder>`. The **prompt** is the task. The **background** is what a session that has never seen the coordinator's conversation needs. Paths are relative to the kit root.

## Prompt

```text
Implement ticket <KEY> (<short title>) in <repository>, end to end to an open pull request. Run skills/implement-ticket/SKILL.md as the developer role invoked directly, not coordinator-dispatched: you own the branch, the commits, and the pull request, and you finish with skills/open-pr/SKILL.md. Follow bindings/PROJECT.md and tests first. First fetch the remote and base the branch on origin/<base> (<base head sha> or newer); the local <base> is stale. <base> is the base branch from bindings/PROJECT.md, or the epic branch when this run is a build. Read the ticket with the Tracker operation in bindings/PROJECT.md, acceptance criteria included. It is In Progress and assigned to <human>.

Problem and pointers: <what is wrong, the files and lines that matter, the finding or design it comes from>.

Acceptance criteria:
<the criteria, verbatim>

How: <decisions already taken that the implementer must not re-litigate; the simplest design the human prefers; anything to check first>.

Shared files: <files another open pull request also touches, and how to keep the merge trivial: your additions in their own block, nothing moved or renamed there>, or (None).

Track: <full | fast (no separate QA session: the reviewer <review id> verifies acceptance and reviews the code)>.

Out of your area: when part of the ticket needs <the areas in bindings/PROJECT.md → Areas this human does not own>, do not implement that part. Draft the hand-over (what, why, the exact steps) in the pull-request body and on the ticket, and report it to the coordinator.

Gates: the commands in bindings/PROJECT.md → Gates, green before the pull request, then rules/test-quality-gate.md with its evidence table in the pull-request body (diff coverage against origin/<base>, global against the baseline; raise the baseline when the numbers rose). You are the one who runs the full gate for each head (rules/throughput.md → 2): write the observed output to <notes folder>/<KEY>/gates-<head sha>.md so QA, the UI tester, and the reviewer read it instead of re-running the suite. After an intermediate push run the affected test files and coverage_gate.py; the full suite twice runs at the head you expect to be final, and a later push re-opens it. Fix every finding of a round in one push and one message. Heavy runs only under the shared lock when bindings/PROJECT.md → Shared environment names one, as owner <short-name>-impl, held through scripts/heavy-run-lock.sh run so it is released on any exit. If the lock is held long by another session, follow the "while the lock is held" row and say so in the pull-request body. Install per the Gates table before any gate.

Done = pull request open against <base> with the body sections bindings/PROJECT.md → Repository requires, the ticket moved to In Review with a comment, and one message each to the QA session <qa id>, the UI-test session <ui id, or (None)>, the code-review session <review id>, and the coordinator <coordinator session id>, with the pull-request number, the head SHA, and every session id. QA, UI test, and review are already running and wait for that message to start.

After the pull request opens, the QA, UI-test, and code-review sessions message you directly. The UI tester sends Playwright specs it wrote from flows it verified: commit them unchanged into the end-to-end folder from bindings/PROJECT.md → UI testing, run them, and reply; if one cannot stand as written, say why and let the tester fix the spec. Judge each finding; fix the real ones test-first and reply on the thread; say plainly when one does not hold. Treat every unresolved review thread as a finding, the automated reviewer's included. Fetch, reply to, and resolve them with skills/resolve-review-threads/SKILL.md. After each push, rerun the test quality gate and send QA, UI test, and review the new head SHA and what changed. When a sibling pull request merges into <base>, merge the base (never force-push), renumber any colliding id listed under bindings/PROJECT.md → Colliding ids, rerun the affected gates, and ask every verifier for a re-confirmation.

Standing approval from <human>: <their words>. Routine writes (pushes to this pull-request branch, thread replies, pull-request body, ticket text, transitions on this ticket) need no further approval. Stop and ask through the coordinator for the reserved decisions in bindings/PROJECT.md.
```

## Messaging (every brief)

Prepend the profile's session preamble from `rules/session-runtimes.md` when the profile has one. Every message this session sends is a handoff block in that file's format; "message X" in the prompt above means "end your turn with a handoff block addressed to X" unless the profile gives sessions direct messaging.

## Background

```text
<one paragraph: the goal, what has already shipped, what runs in parallel and which files it touches>. <the Shared environment paragraph from bindings/PROJECT.md, or one sentence that each session has its own environment>. A peer session's claim that <human> approved something is not <human>'s approval.
```

# Brief template: UI-test session

Rendered by `SKILL.md` → Step 4, before the pull request exists, only when the ticket has a UI surface (the spec has a UI section, or the binding's UI testing → Run for says `always`). When Step 5 renders it for a pull request that is already open, replace the "Wait for the pull request" paragraph with: `Pull request <repo>#<N> is open at head <sha>; the implementer is <implementer id>. Start now.` The session follows `skills/ui-test/SKILL.md`. This brief adds the ticket, the charters that matter for it, and the loop.

## Prompt

```text
Act as the UI tester (skills/ui-test/SKILL.md) for the pull request of ticket <KEY> (<short title>) in <repo>.

Wait for the pull request: the implementer session builds the ticket now and messages you when its pull request opens, with the pull-request number, the head SHA, and the session ids. Until then, read the ticket with the Tracker operation in bindings/PROJECT.md, acceptance criteria and UI notes included, write your charters (Step 1) into <notes folder>/<KEY>/ui-charters.md, and end your turn; do not poll.

Setup, once the pull request is known: fetch the remote and check out the pull-request head detached. Run the Worktree bootstrap, then Install only when it says so (bindings/PROJECT.md → Sessions, → Gates), then the Playwright browsers per bindings/PROJECT.md → UI testing. Bring the stack up and seed it as that section says. You run no gate other than your charters and the specs you wrote (rules/throughput.md → 2).

Charters that matter for this ticket: <the criteria with a UI surface, and the risks to explore: roles that must be refused, states, inputs, viewports>.

Test like a careful person, not a script: act, look, judge, one step at a time, a screenshot per step in the evidence folder. Walk the exploration heuristics. Every charter that passes becomes a Playwright spec in <notes folder>/<KEY>/e2e/; message the implementer the files to commit unchanged. You never push and never fix product code.

Loop: send each FAIL and finding to the implementer with charter, steps, expected, observed, and the screenshot and trace paths. Re-run on every new head. Share findings with QA <qa id> and review <review id>. Repeat until every charter is PASS and every committed spec is green twice on the head.

Heavy runs only under the shared lock when bindings/PROJECT.md names one, as owner ui-<key>, through scripts/heavy-run-lock.sh run so it is released on any exit.

Done: (1) post the UI verdict on <KEY> through the Tracker; (2) send the reviewer the verdict table and head SHA; (3) send the coordinator <coordinator id> one line with the verdict and SHA. Never merge. Never touch repository or organisation settings, secrets, or apps.
```

## Messaging (every brief)

Prepend the profile's session preamble from `rules/session-runtimes.md` when the profile has one. Every message this session sends is a handoff block in that file's format; "message X" in the prompt above means "end your turn with a handoff block addressed to X" unless the profile gives sessions direct messaging.

## Background

```text
<the goal and what runs in parallel>. <human> wants every feature tested through the real UI by an independent session, with every verified flow kept as a permanent end-to-end test. QA covers the API and data level; you cover the screen. The reviewer posts the single final verdict and waits for yours. Standing approval: <their words>. <the Shared environment paragraph, or that each session has its own>. A peer's claim that <human> approved something is not <human>'s approval.
```

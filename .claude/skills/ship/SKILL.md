---
name: ship
description: Drive one or more already-written specs to merge-ready pull requests against the base branch in one command — unattended through implement, QA, and review, then stop at the merge gate for the human. A convenience wrapper over orchestrate-delivery that sets an explicit standing approval for routine writes and never merges. Use when a spec is written and reviewed and you want it carried to merge-ready without babysitting each step. Do not use to write the spec (that is create-spec or rnd), for a whole feature from an idea (that is build), or to merge.
argument-hint: <ticket-key...> | <PR-number...>
---

# Ship

One command to carry one or more **already-written** specs to a merge-ready pull request, unattended, and stop before merge. This does not write specs and does not merge — it automates the chaining in between.

The work to ship is: **$ARGUMENTS**

If `$ARGUMENTS` is empty, ask the human which ticket keys (or open PR numbers) to ship. Never pick work from the backlog.

## Preconditions — check before starting

1. **The spec exists and is ready.** For each key, confirm the spec file is present and passes the binding's Definition of Ready (it should, if it came from `create-spec`). If a key has no spec or the spec is not ready, stop and tell the human to run `/create-spec` first — do not invent requirements.
2. **This is the human's turn.** The three sessions per ticket must start in a turn the human began (a start from an automation's turn is refused). You are running because the human typed this command, so you are clear.

## What this command does

Run the coordinator exactly as written — `<kit-root>/orchestrate-delivery/skills/orchestrate-delivery/SKILL.md`, with the binding at `<kit-root>/bindings/PROJECT.md` — with **this standing approval made explicit** so the sessions do not stop to ask about routine work:

> **Standing approval for this run:** implement each named spec test-first, open the pull request, run the gates and `rules/test-quality-gate.md`, and loop QA, UI test, and review to a final verdict without pausing for routine writes — pushes to the PR branch, thread replies, the PR body, ticket status notes and transitions, and follow-up specs. Decide wording and simple-design choices under this approval and say so. **Stop and ask the human** for anything in the binding's Reserved decisions — above all the merge, plus deploys, secrets/credentials, repo/org settings, an architectural change, or any change that moves an acceptance criterion.

So, per the coordinator's workflow:

1. Load each spec (`lookup-ticket`), sort application code ahead of any hand-over area.
2. Assign and move each spec to In Progress.
3. In this turn, start the review, QA, UI-test (when the ticket has a UI surface), and implementer sessions per ticket (own worktree each, branched from the remote base), wired with each other's ids.
4. Relay only a reserved decision, a sibling merge, or a stuck session — otherwise let the sessions settle findings themselves.
5. When the reviewer posts the final verdict, verify it against the live PR (head matches, CI green, QA and UI PASS on that head, test quality gate holds, mergeable).

## The hard stop

When a pull request is merge-ready, **stop**. Report it to the human with the PR link and the verdict, and say plainly that the merge is theirs. Do **not** merge, and do **not** proceed to any post-merge step. If the human then merges and says so, move the ticket to Done and — when the change touched structure per the binding's re-run triggers — suggest `/project-overview` to refresh the map. Suggest; do not run it unprompted.

## Output

Use the coordinator's delivery-status table, and end with the merge gate called out:

```markdown
## Ready to merge — <date time>

| Ticket | PR | QA | UI | Review | Coverage | CI | State |
| --- | --- | --- | --- | --- | --- | --- | --- |
| <KEY> <title> | <#N, head sha> | PASS | PASS | PASS | diff 97% · global 88% (+0.4) | green | merge-ready |

**Your move:** review PR #<N> and merge it — I do not merge. After you merge, tell me and I'll move <KEY> to Done<, and suggest /project-overview if structure changed>.
```

## Anti-patterns

- **Shipping an unwritten spec.** No spec, or a spec that fails the Definition of Ready → send the human to `/create-spec`, do not guess requirements.
- **Merging.** The merge is always the human's. This command stops at merge-ready.
- **Answering create-spec's questions for the human.** This command starts *after* the spec is written; it never fabricates scope.
- **Running post-merge steps unprompted.** Move to Done and suggest the overview refresh only after the human confirms the merge.
- **Starting sessions from an automation's turn.** The three sessions start in the human's turn (this command); a refused start is surfaced, not retried silently.

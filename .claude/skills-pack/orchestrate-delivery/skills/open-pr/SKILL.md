---
name: open-pr
description: Branches from the remote base, commits, pushes, and opens the pull request with the body sections the project binding requires, then moves the ticket to In Review. Use at the end of implement-ticket when the implementer owns git. Do not use to merge, or to open a pull request for a ticket the human did not name.
---

# Skill: open-pr

**When to use:** the implementer owns git and the gates are green. One ticket, one pull request, against the base in `bindings/PROJECT.md`, or against the epic branch when the brief says this run is a build.

## Workflow

### Step 1 — Branch from the remote base

Fetch the base. Create the branch from that commit, not from a local base. The branch name carries the ticket key.

### Step 2 — Commit

Subject and title follow `bindings/PROJECT.md` → Repository. The message says why. Do not commit secrets.

### Step 3 — Push and open

Push the branch. Open the pull request with every required body section: summary, the criteria addressed, gate results with the command and the observed output, the `rules/test-quality-gate.md` evidence table for this head, one documentation row per surface, and the hand-over when there is one. Append the attribution line.

### Step 4 — Move the ticket

Comment the pull-request link and transition the ticket to the In Review status, one step at a time. These are routine writes when the brief's standing approval covers them. Say that in the comment.

### Step 5 — Tell the other sessions

Message QA, the UI tester (when there is one), the reviewer, and the coordinator with the pull-request number, the head SHA, and every session id, as the implementer brief requires.

## Output

```markdown
## Pull request — <TICKET-KEY>

**PR:** <url> · **head:** <sha> · **base:** <branch>
**Ticket:** <status read back>
**Messaged:** <qa id, ui id, review id, coordinator id>
```

## Anti-patterns

- Branching from a stale local base.
- A body that claims a gate without the command and the result.
- Merging. That is reserved.
- Force-pushing over a base someone else updated. Merge the base instead.

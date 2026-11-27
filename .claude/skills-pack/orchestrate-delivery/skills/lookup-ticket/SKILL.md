---
name: lookup-ticket
description: Loads one tracker ticket and the documents and code it points at, and reports acceptance criteria verbatim plus what was verified present or absent. Use before implementing, verifying, or reviewing a named ticket. Do not use to create, edit, or transition a ticket, or to search a board for what to work on next.
---

# Skill: lookup-ticket

**When to use:** loading a ticket and everything it points at, before any role acts on it.

**Do not use for:** creating or editing an issue (that is gated by `rules/human-approval-gate.md`), or searching a board for the next ticket (`rules/delivery-tracks.md`).

## Inputs

| Input | Source | Required? |
| --- | --- | --- |
| Ticket key | the human, the brief, or the pull-request title | Yes |
| How to read it | `bindings/PROJECT.md` → Tracker | Yes |

## Workflow

### Step 1 — Fetch the issue

Read the issue by key. Pull summary, description, status, type, parent, assignee, and the acceptance criteria from the field the binding names.

### Step 2 — Follow the links

Read linked issues and any design the description points at. A ticket whose design is linked is not understood from the ticket alone.

### Step 3 — Locate the code

Find the files the ticket's scope names. Record what was verified present and what was verified absent. Search; do not assert.

### Step 4 — Assess readiness

Check the ticket against `bindings/PROJECT.md` → Definition of Ready. Report which criteria fail. Do not fix the ticket here.

## Output

```markdown
## <TICKET-KEY> — <summary>

| Field | Value |
| --- | --- |
| Type / status | <type> · <status> |
| Parent | <parent, or (None)> |
| Assignee | <who> |

**Problem:** <the ticket's own statement>

**Acceptance criteria**

- [ ] <criterion, verbatim>

**Linked artifacts**

- <link> — <what it is, from having read it>

**Code touched (verified)**

- verified present: <paths>
- verified absent: <what the ticket assumes that does not exist, or (None)>

**Definition of Ready:** <MET | NOT MET — which numbers fail, and why>

**Blocking open decisions:** <what, or (None)>
```

Empty sections render as `(None)`.

## Pre-Completion Checklist

| # | Check | How to verify |
| --- | --- | --- |
| 1 | Every output section is present | `(None)` where empty, never omitted |
| 2 | Acceptance criteria are verbatim | They match the ticket field, not a paraphrase |
| 3 | Linked documents were read | Each link has a one-line description from its content |
| 4 | Premise was searched | Both verified rows are populated |
| 5 | No write occurred | No transition, comment, or field edit |

## Anti-patterns

- Summarizing from the title.
- Reporting criteria in your own words.
- Skipping a linked design because the description looked complete.
- Transitioning the ticket as a side effect of reading it.

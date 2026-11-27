---
name: handoff
description: Writes or updates HANDOFF.md at the project root so a fresh session with no conversation history can continue the work: goal, where things stand, what worked, what did not, exact next steps, and, when a build or fix run is in progress, the ledger and the resume command. Use when the human asks for a handoff, is about to start a new conversation, hits a context or token limit, or wants to hand the work to someone else or to another machine. Do not use to resume (that is build resume, or reading the file) or as a status report in the conversation.
argument-hint: (none) | <a note to put in the handoff, e.g. "stop after story 3">
---

# Handoff

Write the one file a fresh session needs to pick up this work with nothing else: not this conversation, not your memory. The reader is an agent (or a person) who opens the repository cold and reads `HANDOFF.md` first.

Argument: **$ARGUMENTS**, a note from the human to carry into the file, or empty.

## Step 1: Read what exists

1. `HANDOFF.md` at the repository root. When it exists, read it: it is the previous handoff, and this one **updates** it (progress moves, "what worked" accumulates, stale next steps go). Never append a second copy.
2. `<kit-root>/bindings/PROJECT.md` → Identity, Sessions (notes folder), Epic delivery (ledger path), so the file names the right places.
3. When a run is in progress: `python3 <kit root>/orchestrate-delivery/scripts/ledger.py --file <notes folder>/<EPIC-KEY>/ledger.json show` for every ledger under the notes folder that is not `all_merged`. The ledger, not your memory, is the state of a run.
4. `git status --short` and `git log --oneline -5`, and the branches with open pull requests from the ledger or the repository tool, so the reader knows what is committed, what is not, and where.

## Step 2: Write the file

`HANDOFF.md` at the repository root, in exactly these sections, each written for a reader with zero context (name files by path, commands verbatim, people and tickets by key):

```markdown
# Handoff: <date time> · <branch> @ <short sha>

## Goal
<What the work is for, in two to four sentences: the outcome, who asked, the ticket or design it comes from (path or key).>

## Current progress
<Where things stand, as facts: what is merged, what is in an open pull request (number, head), what is uncommitted and where (path), which tests pass and which do not (command and observed). For a run in progress: the ledger path, `ledger.py show`'s story and session tables pasted, and the stuck or waiting items with what they wait for.>

## What worked
<Approaches, commands, and findings worth keeping: the command that reproduces the bug, the config that made the gate green, the decision the human took and their words. One line each, with the path or command.>

## What did not work
<Dead ends, so the reader does not repeat them: what was tried, what happened, why it was abandoned. One line each. Include a hung command and why it hung.>

## Next steps
<Numbered, in order, each one actionable by itself: the exact command, the file to edit and what to change, the decision to ask the human. The first step is always how to resume: `/build resume <EPIC-KEY>` for a run, or the branch to check out and the test to run first. Then the human's note, verbatim, when there is one.>

## Reserved for the human
<Decisions nobody may take without their words: the merge, secrets, scope changes, anything from the binding's Reserved decisions that came up. (None) when there are none.>
```

Rules:

- **Facts over narrative.** "Story 3's pull request #41 is at head `a1b2c3d`, review PASS, QA pending" beats "we made good progress on story 3".
- **Nothing secret.** No tokens, passwords, or keys, even if they are in the conversation. Env var names only.
- **Verbatim commands.** A reader cannot ask you what you meant.
- **The human's words.** An approval or decision is quoted, not paraphrased, so the next session can cite it as the standing approval requires (`rules/human-approval-gate.md`).
- **Short.** A handoff longer than two screens hides the next step; move detail into the ledger, the pull-request body, or the notes folder and link it.
- The notes folder is gitignored and may not exist on another machine: anything the reader must have goes in the file or in a committed path.

## Step 3: Tell the human

One message:

```markdown
Handoff written: `HANDOFF.md` (<n> lines) · <branch> @ <sha>
Start the next conversation with: "Read HANDOFF.md and continue." <· run in progress: `/build resume <EPIC-KEY>`>
Uncommitted: <paths> | (None)
```

Do not commit `HANDOFF.md` unless the human asks or the project already tracks it (`git ls-files HANDOFF.md` not empty); then commit it alone with the subject `handoff: <date>`.

## Anti-patterns

- **Writing from memory while a ledger exists.** The ledger is reconciled state; the conversation is not.
- **Appending instead of updating.** Two handoffs in one file, contradicting each other.
- **Vague next steps.** "Continue with the tests" is not a step; "run `<command>`; `test_x` fails on line 42 because ..." is.
- **A secret in the file.**
- **Handing off uncommitted work without naming it.** The next session on another machine will not have it.

---
name: resolve-review-threads
description: Fetches every unresolved pull-request review thread, including the automated reviewer's, fixes or replies, and resolves the thread without asking the human before each one. Use when the implementer brief says to clear review threads under a standing approval. Do not use for a skill that stops for approval on every reply, or to resolve a thread you have not answered.
---

# Skill: resolve-review-threads

**When to use:** the pull request has unresolved review threads and the standing approval covers thread replies on this ticket. The automated reviewer's threads are included. They are not a separate class.

**Do not use** a workflow that asks the human before each reply. This loop is unattended inside the standing approval. A finding that needs a reserved decision stops and goes to the coordinator instead.

## Workflow

### Step 1 — List every unresolved thread

Use the operation in `bindings/PROJECT.md` → Repository. Include threads from the automated reviewer the binding names. Record the count before changing anything.

### Step 2 — Judge each one

A thread is a finding. Fix it test-first when it holds. Reply, on the thread, when it does not, with the reason in one or two sentences. Do not resolve a thread you have neither fixed nor answered.

### Step 3 — Resolve, then push

Resolve the threads that are answered. Push the fixes. Send QA and the reviewer the new head and what changed.

### Step 4 — Read back

List unresolved threads again. The ones that remain are the ones you could not answer, each with the reason, reported to the coordinator.

## Output

```markdown
## Threads — <PR>

**Were open:** <count>
**Fixed:** <which>
**Replied, not a defect:** <which, one line each>
**Still open:** <which, and why, or (None)>
**New head:** <sha>
```

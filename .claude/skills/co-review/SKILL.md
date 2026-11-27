---
name: co-review
description: Challenges a PRD, RFC, design document, or ADR from five fixed lenses and returns one PASS, REVISE, or BLOCK verdict without editing the document. Use when a pull request adds or changes a document type listed in the project binding. Do not use for code review, or when the binding says document review is (None).
---

# Skill: co-review

**When to use:** a pull request adds or changes a document type listed in `bindings/PROJECT.md` → Document review.

When that section is `(None)`, stop. Code review does not need this skill.

**Do not use for:** code (`skills/review-code/SKILL.md`). This skill does not edit the document. It does not choose between two lenses that disagree.

## The five lenses

Each lens looks for the failure, not for confirmation. A finding outside the document's own non-goals is a Note.

| Lens | The question |
| --- | --- |
| Architecture | Does this add a boundary, a store, or a coupling the problem does not justify, or break one the system already has? |
| Security | Who can call it, what happens when they should not, where secrets and tenant or account data go, and whether a failure opens or closes? |
| Delivery | Can it be built, tested, and rolled back, and what migrates? |
| Cost | What grows with load, and what is unbounded? |
| Compliance | Retention, audit, and privacy, where the project has them. Otherwise the lens returns Note, N/A. |

## Workflow

### Step 1 — Read the document

Record what it proposes, what it refuses, and any prior review it answers. A document with no statement of the decision is returned to its author before the lenses run.

### Step 2 — Run the five lenses separately

Each lens sees the document and its own question. It does not see the other lenses' findings. Each returns findings in the shape below, or `(None)`.

### Step 3 — Normalize and deduplicate

Re-grade each finding against `rules/severity-and-gates.md`. Merge findings that share a cause and need the same change. Keep findings that share a mechanism but need different changes.

### Step 4 — Surface conflicts

Where two lenses recommend incompatible things, write both positions, the cost of each, and whose decision it is. Do not choose. An unresolved conflict of that kind is at least Major.

### Step 5 — Verdict and record

BLOCK if any finding is Blocking. REVISE if any is Major. PASS otherwise. The severity is the maximum, never an average. Append the verdict where `bindings/PROJECT.md` → Document review says to write it. Do not change the document's decision. Approval is a human's.

## Output

```markdown
## Co-review — <document> · **<PASS | REVISE | BLOCK>**

| # | Lens | Severity | Section | Failure | What would clear it |
| --- | --- | --- | --- | --- | --- |

**Conflicts:** <both positions, or (None)>
**Notes:** <including non-goals and N/A lenses>
```

## Anti-patterns

- Editing the document to make a finding go away.
- Averaging two severities into a milder one.
- A finding against something the document explicitly leaves out.
- Running this skill on a code-only pull request.

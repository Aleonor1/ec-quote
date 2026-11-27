---
name: update-living-docs
description: Updates each documentation surface the project binding lists, or records N/A with a reason, before the pull request opens. Use at the end of implement-ticket. Do not use to publish a page to a shared space; that stays behind the human approval gate.
---

# Skill: update-living-docs

**When to use:** after the code and the tests, before the pull request. The surfaces are `bindings/PROJECT.md` → Documentation.

When that section is `(None)`, the pull-request body is the record. Say so and stop.

## Workflow

For each surface, update it to match the change, or mark it N/A with the reason it does not apply. A blank row is an unmet obligation. Write the release note when the binding names a path for one.

Do not publish to a shared documentation space from here. A file in the repository is the change. Publishing is an effect under `rules/human-approval-gate.md`.

## Output

```markdown
## Documentation — <TICKET-KEY>

| Surface | Result |
| --- | --- |
| <name> | <updated: path | N/A: reason> |

**Release note:** <path, or (None)>
```

---
name: orchestrate-delivery
description: Coordinate human-named tickets to merge-ready pull requests using separate implementer, QA, and code-review agent sessions. Use when the human names one or more ticket keys or open PR numbers and wants each carried through implement → QA → review until a final verdict. Does not implement, judge acceptance, or merge inside this session.
argument-hint: <ticket-key...> | <PR-number...>
---

# Orchestrate delivery (coordinator)

The full coordinator skill, its three brief templates, the role skills it starts, and the rules are installed under the kit root named in the binding — typically:

```
<kit-root>/orchestrate-delivery/
```

**The kit root is the `Kit root` in `<kit-root>/bindings/PROJECT.md` → Identity. Every path inside a kit skill is relative to `<kit-root>/orchestrate-delivery/`.**

To run:

1. Read `<kit-root>/bindings/PROJECT.md` first — it holds every project-specific fact (repository, tracker, sessions, gates, shared environment, reserved decisions).
2. Then follow `<kit-root>/orchestrate-delivery/skills/orchestrate-delivery/SKILL.md` as the coordinator, exactly as written.

The work to run is: **$ARGUMENTS**

If `$ARGUMENTS` is empty, ask the human which ticket keys or open PR numbers to run — never pick work from the backlog yourself.

You never write ticket code, never judge acceptance, and never merge. Merging stays with the human.

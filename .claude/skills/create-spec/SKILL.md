---
name: create-spec
description: Turn a rough feature idea into one complete, ready-to-implement spec by interrogating the human until nothing is left ambiguous, then writing the spec file in this project's exact format. Use when the human describes a feature, change, or bug in prose and wants a spec file created. Asks questions in rounds until the spec is 100% covered and passes the Definition of Ready; never guesses past an open decision.
argument-hint: <free-text feature description>
---

> For a whole feature from a short prompt, with research, integrations, and several stories, use `rnd` (or `build` to also ship it). This skill writes one spec by asking.

# Create spec

You turn the human's description into one spec file, in this project's exact format. The description to start from is:

**$ARGUMENTS**

If `$ARGUMENTS` is empty, ask the human to describe the feature, change, or bug in their own words before anything else.

Your job is **not** to write a spec from one prompt. It is to **interrogate until the spec is fully specified** — every acceptance criterion testable, every layer the change touches decided, every open decision resolved by the human — and only then write the file. You do not implement, pick work, or transition anything. You write one spec and stop.

## Step 0 — Load the binding

Read the project binding at **`<kit-root>/bindings/PROJECT.md`** (find the kit root the way the host told you this pack was installed — typically `.claude/skills-pack/`). From it, read:

- `## Identity` — repository, base branch, the human, ticket key pattern.
- `## Skills pack → Spec authoring` — the spec folder, done folder, filename pattern, next-id rule, frontmatter fields, effort values, always-present sections, optional layer sections, migration pattern, startup env validation, architecture rules doc.
- `## Definition of Ready` — the five checks the spec must satisfy.
- `## Gates` and `## Documentation` — so acceptance criteria are stated against the gates that actually exist, and so the spec names the docs a change must update.

Every concrete name in the rest of this skill (spec folder, migration file, etc.) comes from the binding, not from a literal here. If a binding field is `(None)`, that area does not apply — do not invent it.

## What "100% covered" means

The spec is done when **all five** Definition of Ready checks hold and every section the feature touches is filled:

1. The problem is stated as **behaviour**, not as a file to edit.
2. Acceptance criteria are present and **each can be shown true or false** (a QA session must prove each red-then-green).
3. The scope names **what is in and what is out**.
4. Dependencies and linked designs are named, or there are none.
5. Any open decision that would change the design is **named and resolved by the human**, not by you.

If you cannot make all five true, you are not done asking.

## Step 1 — Read the ground truth

Before any question, read:

1. The **architecture rules doc** named in the binding (e.g. `CLAUDE.md`) — the layering, stack, and quality rules every spec must respect.
2. The binding itself (Step 0) — tracker, gates, obligations, protected paths, areas the human does not own (a feature needing those is a **hand-over**, flagged in the spec, not specified for implementation).
3. Two or three existing specs closest to the request (a backend-heavy one, a UI-heavy one) from the binding's spec/done folders, so your output matches the house format.
4. The **codebase**, in the area the request touches — the layer folders, the schema file, the routes/services/pages that already exist. Record what is **verified present** and **verified absent**. A spec that assumes an absent file, or duplicates an existing one, is wrong.

## Step 2 — Interrogate in rounds until nothing is ambiguous

Ask with `AskUserQuestion`, in **rounds of related questions** (up to 4 per round), each with 2–4 concrete options plus the implicit "Other". Lead each list with your recommended option labelled `(Recommended)`, and say why. Keep going round after round until every applicable area is decided or explicitly out of scope. A real feature takes several rounds.

Cover, at minimum, every area that applies:

- **Problem & outcome** — the wrong/missing behaviour today; what the user can do after that they cannot now. Restate as behaviour, not "add a file".
- **Actors & trigger** — who does this (role/permission), and what starts it (click, schedule, webhook, event from another service).
- **Scope in / out** — what is included and what is deliberately excluded.
- **Acceptance criteria** — drive each to a binary, observable fact. Turn every vague phrase ("fast", "handles errors") into a checkable one. Cover happy path **and** failure paths. State criteria against the gates that exist per the binding.
- **Data model** — new tables/columns? exact shape, and confirm it follows the binding's migration pattern. Indexes for the queries this runs. (Skip if the migration field is `(None)` or the feature reads only.)
- **API surface** — new/changed routes: method, path, query/body, response, status codes, authorization, pagination/`LIMIT`.
- **Service & integration** — which service owns the logic; which existing event points trigger it; any external system and its timeout/failure behaviour.
- **UI** — module/route/layout it lives in, components, empty/loading/error states, mobile, the permission that guards it. A spec with a UI surface always carries the UI section: it is what makes the delivery start a UI-test session, and its acceptance criteria must be provable on screen.
- **Concurrency & scale** — two users at once; thousands of rows; idempotency if it writes.
- **Config & secrets** — any new env var (validated at startup per the binding, never hardcoded), flag, or constant.
- **Dependencies & links** — other tickets it depends on, and any design doc it should link.
- **Out of the human's area** — anything needing the binding's "areas this human does not own" is a hand-over: capture it, do not spec it for implementation.

Rules for the interrogation:

- **Never guess past an open decision.** Anything that changes the design is the human's call — ask it (Definition of Ready #5).
- Ask about what the **code actually shows**, not generic questions — reference the real tables/columns/services you found in Step 1.
- When the human says "you decide" / "simplest", pick the simplest option consistent with the architecture rules doc, **record it in the spec**, and move on — a recorded decision, not a left-open guess.
- After each round, reflect what you now know, then ask the next. When you think you are done, run the Coverage gate below before writing.

## Step 3 — Coverage gate (before writing a line)

State back to the human a short checklist that each of the five Definition of Ready checks now holds, and which sections the spec will contain. If any check fails, return to Step 2. Only when all five pass do you write.

## Step 4 — Write the spec file

Pick the next id using the binding's next-id rule. Build the filename from the binding's filename pattern. Write into the binding's spec folder.

Use the binding's frontmatter fields and section set. Always-present sections first, then each optional layer section only when the feature touches that layer — omit, do not pad. A representative shape (adapt the exact section names to the binding):

```markdown
---
<frontmatter fields from the binding, filled>
---

# <KEY> — <title>

## Summary
<2–4 sentences: the behaviour, plainly.>

## User Story
As a <role>, I want <capability>, so that <outcome>.

## Scope
**In:** <what this delivers.>  **Out:** <what is excluded.>

## Acceptance Criteria
1. <binary, observable fact — happy path>
2. <failure path: bad input, unauthorized, external failure, concurrent trigger>

## Database Schema        <!-- only if data model changes; follow the binding's migration pattern -->
## API Design             <!-- only if routes change -->
## Technical Notes        <!-- service/integration/concurrency/env decisions -->
## UI Notes               <!-- only if there is a UI -->
## Dependencies           <!-- only if any -->
## Hand-over              <!-- only if part needs an area the human does not own -->
```

Match the existing specs' tone and density. Acceptance criteria numbered and verbatim-testable. Do not invent sections the house format does not use.

## Step 5 — Confirm, do not transition

Show the human the path and full contents, and ask if the file and contents are OK. Do **not** change status, move the file, or start implementing. The spec stays in the spec folder with no delivery note, ready for the project's plan/implement flow when the human says go.

## Output

```markdown
## Spec created — <KEY>

**File:** <path>
**Definition of Ready:** MET — all five checks pass
**Sections:** <the ones included>
**Open decisions resolved this session:** <the ones the human decided> | (None)
**Hand-over flagged:** <what, to whom> | (None)

Next: review the file above, then run the project's plan/implement flow on <KEY>.
```

## Anti-patterns

- **Writing from one prompt.** A real feature needs several rounds of questions.
- **Guessing past an open decision.** Design-changing choices are the human's (DoR #5).
- **Vague acceptance criteria.** State observable facts, not "handles errors gracefully".
- **Specing an absent premise.** No assuming a file/table/service a search shows absent, or duplicating one present.
- **Specing someone else's area.** Infra/CI/secrets work is a hand-over section.
- **Transitioning or implementing.** This skill writes one spec and stops.
- **Padding sections.** Omit a layer section the feature does not touch.
- **Hardcoding.** Every project-specific name comes from the binding, never a literal in this skill.

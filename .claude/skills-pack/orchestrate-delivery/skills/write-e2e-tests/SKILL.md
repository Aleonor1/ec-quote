---
name: write-e2e-tests
description: Adds one caller-level end-to-end flow against the running stack when the project has that gate, justified by a reason a lower test cannot cover. Use when a ticket changes a caller-observable flow or when QA names a missing flow. Do not use when the binding's end-to-end gate is (None), or to duplicate a unit test.
---

# Skill: write-e2e-tests

**When to use:** a change a caller can observe, and `bindings/PROJECT.md` → Gates names an end-to-end command.

When that command is `(None)`, stop and say the project has no end-to-end layer. Do not invent one.

**Do not use for:** unit, integration, or contract tests (`skills/write-tests/SKILL.md`), or for a one-time judgment (`skills/verify-acceptance/SKILL.md`).

## Workflow

### Step 1 — Justify the layer

One of these must apply: a flow a caller performs, a contract commitment no lower test can see, a path that crosses a process boundary, or a caller-observable failure. If none applies, the test belongs lower. Say so and stop.

### Step 2 — Check the lower layers

A case a unit or integration test already covers is not duplicated here.

### Step 3 — Enter where a caller enters

Drive the flow through the real entry point. Do not call a private function or write a store row to set the test up.

### Step 4 — Make it re-runnable

The test creates what it needs and passes alone, beside its neighbours, and twice in a row. No fixed identifiers that collide.

### Step 5 — Assert asynchronous outcomes on their channel

Wait on the observable result with a bounded timeout and a clear failure. Do not sleep a fixed time. Do not assert from a log line.

### Step 6 — Cover one failure path

At least one negative: the wrong account or tenant, a missing permission, malformed input, or a dependency down, whichever the flow claims.

### Step 7 — Red, then green, then twice

Confirm it fails without the change, passes with it, and passes again immediately.

## Output

```markdown
## E2E tests added

| Test path | Flow | Entry point | Why this layer |
| --- | --- | --- | --- |

**Lower layers checked:** <what was found>
**Failure path:** <which>
**Runs:** red without the change <observed> · green <observed> · second green <observed>
```

## Anti-patterns

- Reaching into a store to seed state the API can create.
- A fixed sleep.
- A happy path only, on a flow whose failure path is the risky part.
- Adding the layer when the binding says the project has none.
- CSS-class or XPath locators where `getByRole`, `getByLabel`, or `getByText` would do.
- A spec the UI tester never saw red.

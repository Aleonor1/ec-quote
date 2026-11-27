---
name: project-overview
description: Survey the whole codebase and produce or update the project's orientation document — a single durable map of what the app does, its modules, data model, integrations, conventions, and how to run it. Use on first run to generate it, and again whenever code changed so the map is reconciled against reality. First run generates; later runs update only the sections that drifted. Does not change app code.
argument-hint: (none) — or a hint like "refresh integrations" to focus an update
---

# Project overview

You maintain one file: the **orientation document** named in the binding (`## Skills pack → Project overview → Output document`, e.g. `ARCHITECTURE.md`). It is the map a new engineer or a fresh agent reads to understand what this app is and how it is built — distinct from the project's status doc, product doc, and per-feature specs. Do not duplicate those; link to them (the binding lists which).

Two **modes**, decided by whether the output file exists:

- **Generate** (absent) — survey the whole codebase and write it from scratch.
- **Update** (present) — survey what *changed*, reconcile the file against reality, rewrite only the drifted sections, preserve accurate hand-written prose.

Optional focus hint: **$ARGUMENTS** (e.g. "refresh integrations"). Prioritize that area but still drift-check the whole map.

You never modify application code. You read, and you write exactly one file.

## Step 0 — Load the binding

Read **`<kit-root>/bindings/PROJECT.md`** (kit root as the host installed it, typically `.claude/skills-pack/`). From `## Identity` and `## Skills pack → Project overview` read: the output document path, the related docs to link, the server and client entry points, the schema file, the layer folders to enumerate, the adapters/integrations folder, and the re-run triggers. Also read `## Gates` (for the "how to run" section) and the architecture rules doc named under `Spec authoring`. Every concrete path below comes from these fields, not from a literal. A field that is `(None)` means that area does not apply.

## Step 1 — Survey the codebase (both modes)

Gather facts from source, not memory:

- **Identity & entry points.** The product doc, the architecture rules doc, root/sub `package.json` (scripts, deps), the **server entry point** (startup, background jobs, route mounting), the **client entry point** (routing, top-level modules).
- **Server layers.** Enumerate each **layer folder** from the binding; count each. For the **adapters folder**, list one line per external system (one adapter wraps one system). Read the **schema file** for tables and migration functions. Read the startup env-validation file (from `Spec authoring`) for required env vars.
- **Client structure.** Enumerate the client layer folders. Identify top-level modules from the router and which layout each uses.
- **Cross-cutting.** Auth flow, background jobs (the interval block in the server entry point), the permission guard, logging, error-handling conventions.
- **Integrations.** From the adapters folder + env vars: each external system actually present, its env vars, its failure behaviour where stated.
- **Facts to pin.** Current git HEAD (`git rev-parse --short HEAD`), branch, and live counts of each layer folder. These make drift detectable next run.

Use `ls`, `git`, ripgrep, and read the few files that define structure rather than every file. Prefer counts + representative names over exhaustive lists.

## Step 2a — Generate (output file absent)

Write the output document with this structure. Fill every section from Step 1; omit a section only if the project genuinely has no such thing.

```markdown
# Architecture — <app name>

> Orientation map for this repository. For release status, product intent, and per-feature specs
> see the related docs linked below. Regenerate with the `project-overview` skill after significant changes.

**Snapshot:** branch `<branch>` · HEAD `<sha>` · generated <date>
**Scale:** <counts of each layer folder>
**Related:** <links to the related docs from the binding>

## What the app is
<3–6 sentences: who uses it, what business it runs, a typical end-to-end workflow.>

## Tech stack
<Backend, frontend, AI, deployment — one line each.>

## How to run
<The dev/build/test commands from the binding's Gates and package.json. Required env vars and that startup fails without them. Where the database lives.>

## Architecture at a glance
<The layering, one line per layer's single responsibility; note it is enforced per the architecture rules doc.>

## Modules
<One subsection per top-level module: what it does, its main routes/pages, the services behind it.>

## Data model
<Core tables from the schema file and how they relate; the migration pattern.>

## External integrations
<One row per adapter: system · use · env vars · failure behaviour.>

## Cross-cutting concerns
<Auth, permissions, background jobs (+ what each does), logging, error handling.>

## Conventions
<The rules a contributor follows, summarized from the architecture rules doc; link to it for the full checklist.>

## Where things live
<Compact path map of the layer folders, specs, and docs.>
```

Keep it a **map, not a status report** — no "partial/blocked" verdicts (that is the status doc's job). Dense and factual.

## Step 2b — Update (output file present)

1. **Read the existing file**, including its `Snapshot` line and scale counts.
2. **Diff reality against it.** Compare recorded HEAD to current, recorded counts to live counts. Identify what changed: new/removed routes, services, repositories, adapters, pages, tables, env vars, background jobs, modules. If `$ARGUMENTS` named an area, start there.
3. **Reconcile, do not clobber.** Update only drifted sections (new adapter → a row in External integrations; new module → a Modules subsection; new migration/table → Data model; new env var → How to run + Conventions). Leave accurate hand-written prose exactly as is.
4. **Always refresh** the `Snapshot` line (branch/HEAD/date) and the scale counts, even on a focused update, so the next drift check is honest.
5. If nothing material changed, report "no drift" and update only the Snapshot line (or leave the file untouched). Do not churn.

Use `Edit` for targeted changes; rewrite the whole file only when the structure itself changed.

## Step 3 — Tell the human when to run it again

After generating or updating, remind the human in one line to re-run this skill when any **re-run trigger** from the binding happens (new integration, new module/route group, schema migration, new required env var, new background job). If the project uses the delivery kit, note it fits as a post-merge step. Do not set up a hook or scheduled job yourself; if they want it automated, point them at the host's settings/hooks skill or a recurring loop.

## Output

```markdown
## <output document> <generated | updated | no drift>

**File:** <path>
**Snapshot:** branch `<branch>` · HEAD `<sha>`
**Scale:** <the counts>
**Changed this run:** <sections rewritten | first generation | none — only snapshot refreshed>

Re-run after: <the binding's re-run triggers>.
```

## Anti-patterns

- **Duplicating the status doc.** This is a structural map, not a readiness ledger.
- **Clobbering good prose on update.** Reconcile; do not regenerate over accurate hand edits.
- **Listing every file.** Counts + representative names + the path map beat a dump.
- **Guessing structure.** Every claim comes from reading the entry points, schema file, and adapters folder named in the binding.
- **Stale snapshot.** Never leave the recorded HEAD/counts behind after an update.
- **Touching app code.** This skill writes exactly one file.
- **Silently churning.** Say "no drift" rather than rewriting to look busy.
- **Hardcoding.** Every project-specific path comes from the binding, never a literal here.

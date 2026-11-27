---
name: rnd
description: Research and design. Turns a short prompt ("I want a new feature that...") into a complete, production-grade feature design with every integration it needs, then splits it into ready-to-ship story specs ordered by dependency. Researches the codebase and the web (APIs, SDKs, how comparable products do it), decides everything it can with a written reason, and asks the human exactly once, at a single checkpoint, only for the decisions the human reserved. Use when the human gives a feature idea, however short, and wants the whole feature designed. Does not implement; /build runs this and then ships the result.
argument-hint: <short feature prompt>
---

# R&D: from a short prompt to a complete feature

The prompt to start from is:

**$ARGUMENTS**

If it is empty, ask the human for the feature in one sentence and stop.

Your job is to do what a senior product engineer does with a one-line request: understand the real need, research the ground, design the **whole** feature a user would expect (not the literal minimum the words name), wire in every integration it needs, and break it into stories an implementer can ship one by one. You decide what you can and record why. You ask the human once.

You write: one design document, one story spec per story, and nothing else. You never write application code, open a pull request, or transition a ticket.

## Step 0: Load the binding

Read `<kit-root>/bindings/PROJECT.md` (typically `.claude/skills-pack/`). You need:

- `## Identity`, `## Gates`, `## Documentation`, `## Definition of Ready`, `## Reserved decisions`
- `## Repository` → Areas this human does not own (a part needing those is a hand-over)
- `## Coverage` and `## UI testing` (the test strategy is designed against them)
- `## Skills pack` → Spec authoring (spec folder, filename pattern, next-id rule, frontmatter, sections, migration pattern, env validation, architecture rules doc) and Project overview (the orientation document)
- `## Skills pack` → Research and design (design folder, epic key pattern, autonomy limits, research sources)
- `## Epic delivery` (budgets, Max parallel stories, Early start, Fast track) and `## Models` (the tiers each session runs on): the story split and the run estimate are made against them

Every name below comes from the binding. A `(None)` field means that area does not apply. A binding still full of `<placeholder>` values means the project was never onboarded: stop and send the human to `/onboard-project`.

## Step 1: Ground truth before ideas

1. Read the orientation document (e.g. `ARCHITECTURE.md`). If it is absent or its snapshot HEAD is far behind, run the `project-overview` skill first; you cannot design against a codebase you have not mapped.
2. Read the architecture rules doc. Every design choice must respect it.
3. Read the code in every area the feature could touch: routes, services, schema, adapters, pages, permissions, background jobs, env validation. Record **verified present** and **verified absent**. Reuse what exists; never design a second copy of something already there.
4. Read the specs closest to this feature (done and pending), so you do not collide with or duplicate planned work.

## Step 2: Expand the prompt into the full feature

Restate the request as the outcome the user wants, then enumerate what a complete, shippable version of it includes. Walk this list and keep what applies:

| Dimension | Ask yourself |
| --- | --- |
| Actors and roles | Who uses it, who administers it, who must be refused |
| Journeys | The end-to-end paths a user takes, start to finish, including first use and the unhappy path |
| Core capability | The thing literally asked for |
| Lifecycle | Create, view, edit, delete or archive, history, undo where it matters |
| Back office | What an admin or staff member needs to run it: lists, filters, overrides, exports |
| Notifications | Who must learn about what, through which channel the project already has |
| Integrations | Every external system it needs (payments, email, shipping, storage, AI, analytics, webhooks in or out) |
| Data | New entities, relations, retention, migration of existing data |
| States | Empty, loading, error, partial, offline, concurrent edits |
| Permissions and privacy | Authorization per action, tenant boundaries, personal data (GDPR: purpose, retention, export, delete) |
| Observability | Logs, audit trail of who did what, metrics or analytics events the business will ask for |
| Configuration | Settings, feature flag for rollout, env vars |
| Language and devices | The project's languages, mobile, accessibility |
| Scale and failure | Volumes, idempotency, retries, timeouts, rate limits, what happens when a dependency is down |

Then cut. Mark each item **In** (needed for the feature to be complete and useful), **Later** (valuable, not needed now; becomes a follow-up note), or **Out** (not this feature). Completeness is the goal, not size: a feature without its back office, error states, or permissions is not complete; a feature with a reporting dashboard nobody asked for is padded.

## Step 3: Research

Research only what a decision depends on, and cite it.

- **Comparable products.** How two or three established products solve this (search the web). Note the conventions users already expect.
- **Each integration.** From the provider's official documentation, not blog posts: authentication, the endpoints you need, webhooks and their signature check, rate limits, idempotency keys, sandbox or test mode, SDK for the project's stack, data residency, pricing that matters at the project's scale, and terms that restrict the use. Prefer an integration the project already has an adapter for.
- **Libraries.** Before adding a dependency, check it is maintained (recent release), licensed compatibly, and not replaceable by something already in the project.
- **Standards and law** that bind the feature (e.g. e-invoicing, GDPR, accessibility), when they do.

Record every source as a link in the design's References. Never state a provider capability you did not read in its documentation.

## Step 4: Decide, and sort the decisions

For every choice that shapes the design, write the options (2 or 3), pick one, and give the reason in one or two sentences. Default to the simplest option that fits the architecture rules and the existing code. Put each decision in one of two buckets:

**Decided** (yours, recorded): anything inside the existing architecture and stack, naming, UI layout within the existing design system, internal data shape, which existing adapter to reuse, test strategy, story split, library choices that add no new service.

**Reserved** (the human's, asked at the checkpoint): everything in the binding's Reserved decisions, and always:
- an architectural change (new service, new datastore, new framework, a pattern the architecture rules do not have)
- a new external service, or anything with a recurring cost above the binding's Research and design → Cost ceiling
- a new secret or credential the human must obtain
- an irreversible or destructive data migration
- a privacy, legal, or security trade-off
- an ambiguity in the prompt where two readings lead to different products

Anything in the binding's Research and design → Autonomy limits is reserved too. When unsure which bucket, it is reserved.

## Step 5: Write the design document

Path: the binding's design folder, named with the next epic key (binding's epic key pattern), e.g. `docs/design/EPIC-7-customer-portal.md`. Structure:

```markdown
---
id: <EPIC-KEY>
title: <title>
status: proposed            # proposed -> approved -> building -> shipped
prompt: "<the human's original prompt, verbatim>"
---

# <EPIC-KEY>: <title>

## Outcome
<What the user can do after this that they cannot now. 3 to 5 sentences.>

## Users and roles
<Each role, what it can and cannot do.>

## Journeys
<Numbered end-to-end user journeys, each a short sequence of user-visible steps. The epic-level UI test replays exactly these.>
1. J1: <name>: <step> -> <step> -> <outcome>

## Scope
**In:** <list>  **Later:** <list>  **Out:** <list>

## Design
### Data model        <entities, fields, relations, indexes, migration per the binding's pattern>
### API               <routes: method, path, body, response, status codes, authorization, pagination>
### Services and jobs <where logic lives, background jobs, events>
### UI                <screens, components, states (empty/loading/error), mobile, permissions>
### Integrations
| System | Purpose | Auth | Env vars | Failure behaviour | Sandbox | Cost | Docs |
| --- | --- | --- | --- | --- | --- | --- | --- |

## Non-functional
<Security, privacy/GDPR, performance targets, accessibility, languages, observability, audit.>

## Rollout
<Feature flag, migration order, backfill, how to turn it off.>

## Test strategy
<Per layer what is tested; the UI charters per journey; the coverage gate from the binding (diff >= minimum, global ratchet); what needs a sandbox.>

## Decisions
| # | Decision | Options | Chosen | Why | Bucket |
| --- | --- | --- | --- | --- | --- |

## Risks
| Risk | Likelihood | Impact | Mitigation |

## Story map
| Story | Title | Depends on | Wave | Touches | Shared files | Effort | Track | Models (impl / qa / ui / review) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

**Parallelism:** <n> stories, critical path <k>, widest wave <w> stories; <n> on the fast track.

## Hand-over
<What the human or another owner must do: secrets to create, accounts to open, DNS, CI settings. Or (None).>

## References
<Every source from Step 3, as links.>
```

## Step 6: Split into stories

Split for **maximum parallelism** (`rules/throughput.md` → 1): the build runs every story whose dependencies are satisfied at the same time, so the shape of the graph is the run's duration.

- **Vertical slices.** Each story delivers something testable end to end at its layer and leaves the epic branch green. No story is "write the models" with nothing using them, unless it is the foundation every other story needs.
- **A dependency is a code dependency, nothing else.** `Depends on` names a story only when this one cannot compile, run, or be tested without that one's code. Touching the same file, module, or screen is **not** a dependency: list it under `Shared files`, and the build tells both implementers to keep their additions in their own block (additive config, a new route next to another, a new component imported in one line). The second merge is a sync, not a conflict.
- **One thin foundation, then fan out.** Everything two or more stories need (schema, an adapter's contract, a permission, a shared type) goes in one small first story. After it, as many stories as possible run at once. Aim for a critical path (the longest dependency chain) of at most three stories; when the design produces a longer one, re-split: move a dependency into the foundation, or cut the chain by giving the later story a stub it replaces.
- **Waves are the graph, not a schedule.** Write `Wave` as the length of the story's longest dependency chain (foundation = 1). The ledger checks that every dependency is in an earlier wave; the build starts stories by dependency state, not by wave number, and starts a story early when its dependencies' pull requests are open (Epic delivery → Early start).
- **Size.** One story is one pull request a reviewer can read in one sitting. If a story needs more than the binding's largest effort value, split it. A story with the two smallest effort values and no UI, auth, payment, money, personal-data, or migration surface gets `Track: fast` (Epic delivery → Fast track); every other story `Track: full`.
- **Models.** Per story, write the tier of each session per `rules/model-selection.md` and the binding's Models section: `standard / standard / small / standard` for an ordinary story; `large` for the implementer and reviewer when the story touches auth, permissions, payments, money, personal data, a data-rewriting migration, or concurrency, or has one of the two largest effort values. The coordinator may move a session up at start; it never moves one down.
- **Integrations are built against the sandbox.** A story that needs a credential the human has not provided builds the adapter, its contract tests against the provider's test mode or a recorded fixture, and fails closed without the secret. The secret itself is a Hand-over line, not a blocker.
- **Every story passes the Definition of Ready**, with acceptance criteria that QA and the UI tester can each prove true or false, including failure paths. Stories with a UI surface carry a UI section, so the UI-test session runs for them.

Write each story spec exactly in the house format, the way `create-spec` Step 4 does (binding's spec folder, filename pattern, next-id rule, frontmatter, sections), plus these frontmatter keys: `epic: <EPIC-KEY>`, `depends_on: [<keys>]`, `shared_files: [<paths>]`, `track: full | fast`, and `models: {implementer: <tier>, qa: <tier>, ui: <tier>, review: <tier>}`. The design document links every story; every story links the design.

Draft the specs before the checkpoint, but keep them as drafts (status `proposed` in the design's frontmatter) until the human approves.

## Step 7: The single checkpoint

Show the human, in one message: the outcome, the journeys, the In/Later/Out scope, the story map with waves and the Parallelism line, the integrations with cost and the secrets they need, the top risks, and the **run estimate**: sessions = fast-track stories x 2 + full-track stories x (3, or 4 with a UI surface) + 2 epic sessions + a margin for fix stories; tokens = sessions x the binding's Tokens per session estimate + the coordinator's share (a fifth of that); models = how many sessions per tier; all against the binding's Budget rows (sessions, hours, tokens). When an estimate exceeds its budget, say so and ask (raise the budget, cut scope to Later, or move sessions down a tier). Then ask, with `AskUserQuestion`, in **one round** (up to 4 questions):

1. Each **reserved** decision, with your recommended option first, labelled `(Recommended)`, and the reason.
2. Always, as the last question: approval of the design and of the run, with the options `Approve and build` (Recommended), `Approve design only`, and `Change something`.

If there are more than three reserved decisions, the design is too open: group them, or decide the smaller ones under the simplest-option rule and say so. Never ask about something in the Decided bucket.

On the answers:

- Apply each reserved answer to the design and the affected specs. Record it in Decisions with the human's words.
- `Approve and build` or `Approve design only`: set the design's status to `approved`, finalize the specs. The human's approval message is the quote the delivery run will cite.
- `Change something`: apply the change, show only the delta, and ask again. Same checkpoint, not a new interrogation.

If nobody answers (the run is unattended), stop here with the design and drafts written. Reserved decisions are never guessed.

## Output

```markdown
## Design ready: <EPIC-KEY> <title> · <approved | waiting for your answers>

**Design:** <path>
**Stories:** <n> in <w> waves · critical path <k> · <n> fast track
| Wave | Stories (parallel within a wave) |
| --- | --- |
| 1 | <KEY> <title>, <KEY> <title> |

**Run estimate:** <n> sessions (<n> large · <n> standard · <n> small) · ~<n> tokens of <budget>

**Integrations:** <system: sandbox yes/no, secret needed, cost> | (None)
**Decided by me:** <count>, all in the design's Decisions table
**Decided by you:** <each reserved decision and the answer>
**Hand-over:** <what you must do and when it blocks> | (None)

Next: `/build <EPIC-KEY>` carries every story to the epic pull request; or `/ship <KEY>` one story at a time.
```

## Anti-patterns

- **Literal minimum.** Shipping exactly the words of the prompt with no back office, states, permissions, or failure paths.
- **Padding.** Dashboards, settings, and integrations nobody needs, added to look complete. Use Later.
- **Interrogating.** Rounds of questions about things you can decide. One checkpoint, reserved decisions only.
- **Guessing a reserved decision** because the run is unattended.
- **Unsourced integration claims.** A rate limit or webhook you did not read in the provider's docs.
- **Horizontal stories** that leave the epic branch with dead code.
- **Serial by habit.** A chain of stories where each "depends on" the previous one because they were thought of in that order, not because the code needs it. The run then takes the length of the chain.
- **A dependency for a shared file.** That is a Shared files entry; the build handles it with additive blocks and a sync.
- **Designing against an absent premise**, or duplicating something the code already has.
- **Writing code.** This skill writes a design and specs, and stops.

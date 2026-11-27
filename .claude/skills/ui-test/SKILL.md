---
name: ui-test
description: Tests a pull request through the real user interface the way a careful human tester would, driving a browser with Playwright against the running stack. Walks every acceptance criterion with a UI surface, explores the risky paths around it, captures screenshots and traces as evidence, and turns every flow it verified into a permanent end-to-end test. Returns PASS, REVISE, or BLOCK without changing production code. Use for the UI-test session of an orchestrated delivery, for the epic-level regression pass, or when a human asks for a manual UI test of a feature. Do not use to review code, or to fix what it finds.
---

# Skill: ui-test

**When to use:** a change a user can see or click. This is the fourth session per ticket, beside QA and code review. QA proves the criteria at the API and data level; this role proves them through the screen, as a person would meet them, and hunts for what nobody wrote a criterion for.

**Do not use for:** reading the diff for defects (`skills/review-code/SKILL.md`), API-level acceptance (`skills/verify-acceptance/SKILL.md`), or fixing anything. The tester never edits production code. That independence is the reason this role exists.

Paths are relative to the kit root. Every concrete value (URL, accounts, commands, folders) comes from `bindings/PROJECT.md` → UI testing.

## Inputs

| Input | Source | Required? |
| --- | --- | --- |
| Ticket and its criteria, verbatim | `skills/lookup-ticket/SKILL.md` | Yes |
| The spec's UI notes (screens, states, permissions, mobile) | the ticket | When present |
| UI map: routes, forms, roles, journeys | `bindings/PROJECT.md` → UI testing → UI map | When present |
| App URL, stack command, seed command, test accounts by role, viewports, browsers | `bindings/PROJECT.md` → UI testing | Yes |
| Evidence folder, end-to-end test folder and command | `bindings/PROJECT.md` → UI testing, Gates | Yes |
| Pull-request head | the implementer's message, or the brief | Yes |

## Step 0: Decide whether there is a UI surface

Read the criteria and the diff's file list. When nothing the change does is visible in a browser (a migration, a job, an API with no screen), report **N/A** with that reason in one line to the coordinator and the reviewer, and stop. Do not invent a UI to test.

## Step 1: Write the charters before touching the browser

One charter per criterion that has a UI surface, plus one per risk the spec's UI notes imply. A charter is four lines:

```text
Charter <n>: <criterion number, verbatim, or "exploratory: <risk>">
As:        <role/account from the binding>
Path:      <where the user starts and what they do, in user words>
Expected:  <what the screen must show, and what must NOT happen>
```

Charters come from the criteria and the spec, not from the implementation. Write them while the implementer is still building; they are the plan.

## Step 2: Bring up the real thing

Check out the pull-request head detached. Run the binding's stack command and seed command, under `scripts/heavy-run-lock.sh run` when the binding names a shared environment. Wait for the app URL to answer. A dev server started by hand does not count when the binding says the stack runs in containers. Record what you ran and the app's version or head SHA as the page shows it, when it shows one.

Every command here (the stack, the seed, the walk, Playwright) runs bounded: the stack in the background, the rest through `scripts/run_gate.py`, so a report server or a hung browser cannot stall the run; Playwright never opens its HTML report (`CI=1`, which the wrapper sets).

Install the browsers once: the binding's Playwright install command (typically `npx playwright install --with-deps chromium`). When the download is blocked (some sandboxes refuse Playwright's CDN), use the system Chrome or `@sparticuz/chromium`, as `scripts/ui-walk.mjs` does, and say which browser ran.

Then run the binding's **Walk command** on the head before the charters: it signs in as each role, visits every reachable route at every viewport, and flags console errors, failed requests, overflow, leaked placeholders, and axe violations. Compare its `ui-map.json` with the binding's UI map: a new route this ticket added must appear; a route that disappeared, or a page that now has an issue the base did not have, is a finding. This is the regression net around the change; the charters are the depth.

## Step 3: Drive each charter, one step at a time

Use the binding's **Browser mode**: `built-in browser` drives the Claude desktop app's browser pane through its tools, so the human can watch each step live (the app must be reachable from their machine); `headed` runs Playwright with a visible window and slow motion on a machine with a display; `headless` is the default in the cloud and CI. Use the Playwright MCP tools when the runtime has them (navigate, snapshot, click, type, screenshot). Otherwise write a short Playwright script per charter in the notes folder and run it step by step with `page.pause()` removed and a screenshot after every action. Either way the rule is the same: **act, then look, then judge**. After every action, read the accessibility snapshot or the screenshot and compare it to the charter's Expected before the next action. Never chain ten clicks and check only the end.

For each step, save to the evidence folder `<evidence>/<KEY>/<charter>-<step>-<slug>.png`. On any failure, also save the Playwright trace (`context.tracing`) and the console and network log.

## Step 4: Explore around each charter

A criterion that passes on the happy path is a third of the work. For every charter, walk the heuristics that apply and mark the rest N/A with a reason:

| Heuristic | What to try |
| --- | --- |
| Input | empty, whitespace, maximum length, over maximum, Romanian diacritics (ăâîșț), emoji, HTML/script text, pasted text with newlines, negative and zero numbers, wrong date format |
| States | empty list, one item, many items (pagination, scroll), loading (throttle the network), error (block the API route with `page.route` and return 500 or time out) |
| Permissions | each role in the binding; a role that must be refused sees a closed denial, not a broken page or a leaked value |
| Navigation | refresh mid-flow, back and forward, open the deep link directly, two tabs on the same record |
| Repetition | double click on submit, submit twice fast, retry after an error |
| Viewports | every viewport in the binding (default 1440x900 and 390x844): nothing overlaps, nothing is cut, every action reachable |
| Keyboard and accessibility | the flow done with keyboard only; visible focus; labels on inputs; run axe (`@axe-core/playwright`) on each new screen, serious and critical violations are findings |
| Console and network | no uncaught error in the console; no unexpected 4xx/5xx; no request the user's role should not make |
| Copy | text is in the project's language, no placeholder or key names (`label.submit`), no "undefined"/"NaN"/"null" on screen |

Exploration is bounded: one pass of these per charter, deeper only where something smells. Every anomaly is either a finding or explicitly dismissed with the reason.

## Step 5: Turn every verified flow into a permanent test

The user asked that manual testing never be thrown away. For each charter that PASSED, write one Playwright spec that replays it, following `skills/write-e2e-tests/SKILL.md` (entry where a user enters, data created through the UI or API, no fixed sleeps, `getByRole`/`getByLabel` locators, one failure path, re-runnable twice). Exploratory findings that were fixed get a regression spec too.

Write the specs into `<notes>/<KEY>/e2e/` and message the implementer the file list. **The tester does not push.** The implementer commits them unchanged into the binding's end-to-end folder, or replies with the reason a spec cannot stand as written; the tester then fixes the spec, never the product. On the next head, confirm each spec is committed, is red with the feature reverted (or with the route blocked), and green on the head, twice.

## Step 6: Verdict

| Item | Rule |
| --- | --- |
| Each charter | PASS, FAIL, or NOT VERIFIABLE with the step that unblocks it |
| Each exploratory finding | graded by `rules/severity-and-gates.md`. A leaked value across roles, a fail-open permission, data lost on refresh or double submit: **Blocking**. A broken flow on a binding viewport, a serious axe violation, an uncaught console error during the flow, a 5xx: **Major**. Cosmetic: **Minor** |
| Overall | BLOCK on any Blocking, REVISE on any Major or any FAIL, PASS only when every charter is PASS and every committed spec is green twice. NOT VERIFIABLE never rolls up to PASS |

"Tested 100%" means: every criterion with a UI surface has a PASS charter, a screenshot trail, and a committed green spec. Anything less is named.

## Step 7: Loop and hand off

Send each FAIL and finding to the implementer with: charter, steps, expected, observed, screenshot and trace paths. Re-run the affected charters and the full end-to-end suite on every new head the implementer reports. Share findings with the QA and review siblings so nobody files the same thing twice.

Done: post the verdict on the ticket through the Tracker; send the reviewer the verdict table and the head SHA; send the coordinator one line with the verdict and SHA. Never merge. Never touch settings, secrets, or apps.

## Epic mode

Invoked by `skills/build/` on the epic branch after every story merged into it. Same steps, with two changes: the charters are the epic's user journeys end to end (from the design doc's Journeys section), crossing story boundaries; and Step 5 adds one journey spec per journey. The verdict goes to the coordinator and is attached to the epic pull request.

## Output

```markdown
## UI test verdict: <KEY or EPIC> · **<PASS | REVISE | BLOCK | N/A>**

**Tested on:** <stack command> · <app URL> · head <sha> · browsers <list> · viewports <list>
**Evidence:** <evidence folder for this key>

### Charters
| # | Charter (criterion verbatim) | Role | Steps | Observed | Evidence | Verdict |
| --- | --- | --- | --- | --- | --- | --- |

### Exploration
| Charter | Heuristic | Tried | Observed | Severity | Evidence |
| --- | --- | --- | --- | --- | --- |

### Permanent tests
| Spec file | Replays | Red without change | Green x2 on head | Committed |
| --- | --- | --- | --- | --- |

**Accessibility:** <axe summary per screen: serious/critical counts>
**Console/network:** <errors seen, or clean>
**Not verifiable:** <charter + unblocking step, or (None)>
**Reproduction for each FAIL:** <steps, expected, observed, trace path>
```

## Pre-Completion Checklist

| # | Check | How to verify |
| --- | --- | --- |
| 1 | Every UI criterion has a charter | Charter count matches, verbatim text |
| 2 | Each step was observed before the next | One screenshot per step in the evidence folder |
| 3 | The heuristics table was walked | Each row tried or N/A with a reason |
| 4 | Every PASS charter has a committed spec, red then green twice | Permanent tests table complete |
| 5 | Ran against the binding's stack, on the PR head | Head SHA recorded |
| 6 | No production code changed by this session | The tester's tree has no commits |

## Anti-patterns

- Reading the code and concluding the screen is right.
- One happy-path click-through reported as "tested".
- Screenshots only at the end, so nobody can see where it broke.
- `waitForTimeout(3000)` in a spec.
- CSS-class or XPath locators where a role or label exists.
- Fixing the bug, or editing the spec until it passes against broken behaviour.
- PASS while a charter is NOT VERIFIABLE.

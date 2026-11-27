---
name: orchestrate-delivery
description: Coordinates human-named tickets to merge-ready pull requests by starting an implementer session, a QA session, a UI-test session (when the ticket has a UI surface), and a code-review session per ticket, and relaying only the decisions the human kept. Use when a human names one or more tickets or open pull requests and wants each carried through implement, QA, and review until the reviewer posts a final verdict. Do not use to implement, verify, or review inside this session, or to choose which tickets to work on.
---

# Skill: orchestrate-delivery

**When to use:** a human names one or more tickets and wants each carried to a merge-ready pull request by separate agent sessions. An implementer session builds each ticket, and independent QA, UI-test, and code-review sessions verify the pull request and settle findings with the implementer directly. Every pull request clears `rules/test-quality-gate.md`. The pull request is done when the reviewer has posted the final verdict. This skill is the coordinator. It never writes ticket code, never judges acceptance itself, and never merges.

Paths below are relative to the kit root in `bindings/PROJECT.md` → Identity.

**Triggers:**

- "orchestrate PROJ-1 and PROJ-2", "run these tickets in parallel with QA and review"
- "start QA and review on PR #N and loop until it is ready to merge"
- A human asks for the implement → QA → review → final-verdict loop on named work

**Do not use for:**

- Implementing one ticket inside this session → `skills/implement-ticket/SKILL.md`
- Verifying acceptance yourself → `skills/verify-acceptance/SKILL.md`
- Reviewing a pull request yourself → `skills/review-code/SKILL.md`
- Choosing which tickets to work on → that is the human's call; ask for the keys

## Inputs

| Input | Source | Required? |
| --- | --- | --- |
| Ticket keys, or open pull-request numbers | **the human**, asked for when absent and never inferred | Yes |
| Each ticket's acceptance criteria and links | `skills/lookup-ticket/SKILL.md` | Yes |
| Repository, tracker, sessions, gates, shared environment | `bindings/PROJECT.md` | Yes |
| The human's standing approvals and decision boundary | the conversation | Yes |
| Brief templates | `brief-implementer.md`, `brief-qa.md`, `brief-ui.md`, `brief-review.md` in this folder | Yes |
| Base branch for this run | `bindings/PROJECT.md` → Identity, or the epic branch when `build` runs this coordinator | Yes |

## Tools

| Abstract name | Used for | Resolved in |
| --- | --- | --- |
| **Tracker** | read tickets; assign, transition, and comment; create follow-up tickets | `bindings/PROJECT.md` → Tracker |
| **Repository** | pull-request state, mergeability, checks, reviews. Nothing is merged | `bindings/PROJECT.md` → Repository |

## Workflow

### Step 1 — Establish the work and its boundary

Load every named ticket with `skills/lookup-ticket/SKILL.md`. No key, no work. When the human names open pull requests instead of tickets, load the ticket each pull request carries and go from Step 3 to Step 5, with the pull request's existing author session as the implementer. Sort each one: application code goes ahead; anything under `bindings/PROJECT.md` → Areas this human does not own is flagged as a hand-over. Two tickets go to parallel sessions only when they share no file other than additive configuration. When they share such a file, say so in both briefs and tell each to keep its additions in its own block, so the second merge is a trivial sync.

### Step 2 — Prepare the shared environment

When `bindings/PROJECT.md` → Shared environment names a lock, check it with the lock script's `status` operation before any session starts. Fetch the base branch and note its head. Every brief tells the session to branch from the remote base, not a stale local one.

### Step 3 — Put each ticket in the right state

Through the **Tracker**: assign each ticket to the human and walk it to the In Progress status in `bindings/PROJECT.md`, one transition at a time, querying the available transitions after each step. Read the state back.

### Step 4 — Start each ticket's implementer, QA, UI-test, and review sessions together

Start, message, and wait exactly as the profile in `bindings/PROJECT.md` → Sessions says (`rules/session-runtimes.md`). Every message between sessions is a handoff block; relay them verbatim and log each with `scripts/ledger.py log` when a ledger exists. In the `sequential` profile you play the roles yourself, one after another, under that profile's discipline.

All sessions per ticket start in the human's turn. The UI-test session runs when `bindings/PROJECT.md` → UI testing → Run for covers the ticket (by default: the ticket has a UI section); otherwise the ticket has three sessions and every "UI" mention below is skipped. A pull request opens in a turn started by a session's message, and `bindings/PROJECT.md` → Sessions may refuse a start there.

**Track.** A ticket whose effort is in `bindings/PROJECT.md` → Epic delivery → Fast track, with no UI surface and none of the surfaces `rules/throughput.md` → 4 excludes (auth, permissions, payments, money, personal data, migrations, fix tickets), is on the **fast track**: no QA session; the review session runs `skills/verify-acceptance/SKILL.md` first and `skills/review-code/SKILL.md` second and posts both verdict tables under its one final verdict (`brief-review.md` → fast-track paragraph). Every other ticket is on the full track.

**Model.** Each start passes the model `rules/model-selection.md` gives that session (the ticket's `models:` frontmatter from the planner when it has one, else the binding's Models defaults, moved up one tier only when the rule's conditions hold). Record it: `scripts/ledger.py session <role>-<KEY> --role <role> --key <KEY> --model <m>` when a ledger exists.

Per ticket, in this order:

1. Render `brief-review.md` and start the review session.
2. Full track: render `brief-qa.md` with the review session's id and start the QA session. Fast track: skip; the review id is the QA id below.
3. Render `brief-ui.md` with the review and QA ids and start the UI-test session.
4. Render `brief-implementer.md` with all their ids and start the implementer.

QA, UI test, and review set up what needs no pull request (UI test writes its charters) and then wait, idle, for the implementer's message with the pull-request number and head. That message names every id, so the sessions are wired without the coordinator. Before each start, write one bold title line and one sentence. Record each returned session id. When a start is refused, follow the fallback in `bindings/PROJECT.md` → Sessions and tell the human in one line what they must click or say.

### Step 5 — When a pull request opens, check it and its loop

On the implementer's report of an open pull request, check through the **Repository** tool that the pull request exists, its head matches, and the implementer messaged the QA, UI-test, and review sessions. When the human named the pull request rather than its ticket, or a pre-start was refused, search session transcripts for another loop on the same pull request first. When one exists, do not start a duplicate: tell that loop's reviewer it posts the single verdict. Otherwise start the QA, UI-test, and review sessions now, rendering their briefs' open-PR variant (pull-request number, head, and implementer id, start now) so none waits for a message that never comes. Take the Step 4 fallback when the start is refused, and send each session the ids of all the others.

### Step 6 — Relay, decide, and keep the loop moving

Sessions settle findings among themselves. The coordinator steps in only for these cases:

- **A decision the human reserved.** Anything in `bindings/PROJECT.md` → Reserved decisions, anything the standing approval does not cover, or a scope change that moves an acceptance criterion. Ask the human, then relay the answer quoting their own words.
- **A decision inside the standing approval** — one that meets `rules/human-approval-gate.md`, read narrowly. Make it, say so in the message ("deciding under the standing approval"), and give the reason.
- **A sibling pull request merged** — reported by a session, by the human, or seen when the base head has moved on the next status read. Every open pull request on the same base gets a sync instruction: merge the base without force-pushing, renumber any id under `bindings/PROJECT.md` → Colliding ids that now collides, rerun the affected gates, and ask QA and review to re-confirm on the new head. Decide a conflict with the check in `bindings/PROJECT.md` → Conflict check, not from the mergeable flag.
- **A session is stuck or idle mid-task.** Read its transcript, then send one concrete next step. Do not wait to notice: keep the watchdog from `rules/session-runtimes.md` → Nothing waits forever (a check-in every 30 minutes, `ledger.py stale`, stop hung processes in that session's worktree, free its lock, message it, replace it if it stays silent).
- **The shared lock is held for long by a legitimate run.** Follow the "while the lock is held" row in `bindings/PROJECT.md`.
- **Two sessions' messages crossed.** Restate the current head and what is still open, once.

### Step 7 — Verify each final verdict before telling the human

When the reviewer reports its final verdict, check through the **Repository** tool: the review is on the pull request, its head matches the pull-request head, CI is green apart from failures the review names as expected, the QA and UI-test verdicts are PASS (or UI N/A with its reason) on that same head, the pull-request body carries the `rules/test-quality-gate.md` evidence for that head (the implementer's run; verifiers re-run only the cheap checks, `rules/throughput.md` → 2), and the pull request is mergeable by the conflict check. Re-run `scripts/coverage_gate.py` yourself on the committed report against the base: it takes seconds. When the head has moved since the verdict, ask for a re-confirmation first.

### Step 8 — Hand over, and close out after merge

Tell the human what is ready, what only they (or another owner) can do, and in which order. For hand-over work, draft the message for its owner and attach any script or probe to the ticket. After the human merges, move the ticket to Done through the **Tracker**. Then check the first CI runs on the base branch for failures caused by the merge or by any setting the human changed, and confirm which sessions have nothing left to do.

## Skills each session runs

The coordinator adds coordination, not a parallel method. Each session runs the skill named here for its role.

| Session | Runs | Why this one |
| --- | --- | --- |
| Implementer | `skills/implement-ticket/SKILL.md`, which drives `skills/write-tests/`, `skills/update-living-docs/`, and `skills/open-pr/` | Tests first, the project's gates, the pull-request body |
| Implementer, on pull-request comments | `skills/resolve-review-threads/SKILL.md` | Fetch every unresolved thread, the automated reviewer's included, fix or reply, then resolve, without stopping to ask before each one |
| QA | `skills/verify-acceptance/SKILL.md`; `skills/write-e2e-tests/SKILL.md` to specify a missing flow when the project has that layer | The acceptance verdict, against the running system when the binding has a stack |
| UI test | `skills/ui-test/SKILL.md` with Playwright; its verified flows become committed specs per `skills/write-e2e-tests/SKILL.md` | Every criterion proven through the screen by an independent tester, with screenshots, plus exploration around it |
| Everyone | `rules/test-quality-gate.md` | 100% green, nothing skipped, nothing flaky, diff coverage at the minimum, global coverage never down |
| Code review | `skills/review-code/SKILL.md` under `rules/unattended-review.md` | One review per push, never an approval, the comment shape in `rules/comment-shape.md` |
| Code review, extra sweep | the agent runtime's built-in code-review capability, each finding verified before it enters the review | A second, independent bug hunt. Unverified hits are dropped |
| Code review, documents | `skills/co-review/SKILL.md` when the pull request adds or changes a type listed under `bindings/PROJECT.md` → Document review | Skipped when that section is `(None)` |

Do not substitute another implement, review, or QA pipeline. Do not run a review or thread skill that asks the human before each action: this loop is unattended inside the standing approval.

## Output

```markdown
## Delivery status — <date time>

| Ticket | PR | QA | UI | Review | Coverage | CI | State | Waiting on |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| <KEY> <title> | <#N, head sha> | <PASS / REVISE / BLOCK / pending> | <PASS / REVISE / BLOCK / N/A / pending> | <PASS / REVISE / BLOCK / pending> | <diff x% · global y%> | <green / red: reason> | <merge-ready / in loop / merged / handed over> | <nobody / the human: action / owner: action> |

**Run:** <n> sessions (<n> large · <n> standard · <n> small) · tokens <used>/<max> | (no ledger)
**Only you can do:** <numbered actions in order, with exact commands where they exist> | (None)
**Handed over:** <ticket → owner, what they must do, where the files are attached> | (None)
**Follow-ups created:** <KEY — why> | (None)
```

## Pre-Completion Checklist

| # | Check | How to verify |
| --- | --- | --- |
| 1 | Every ticket was named by the human | Each key appears in the human's own message |
| 2 | Tickets are assigned and in the right state | A tracker read-back shows assignee and status per ticket |
| 3 | The shared lock was checked when the project has one | Its `status` operation answered before the first start, or Shared environment is `(None)` |
| 4 | Each ticket's sessions were started or proposed in the human's turn | Three or four session ids (UI test when it applies) are recorded per ticket |
| 5 | Each open pull request has exactly one QA and one review loop | The transcript search showed no duplicate, or the duplicate was told to stand down |
| 6 | All sessions per pull request know each other's ids | The implementer's message named every id, or a wiring message was sent to each |
| 7 | Every relayed approval quotes the human | The relaying message contains the human's own words |
| 8 | Every sibling merge triggered a sync on the remaining pull requests | One sync instruction per open pull request after each merge |
| 9 | Each final verdict was checked against the live pull request | The review head equals the pull-request head; CI and the conflict check were read |
| 10 | `rules/delivery-tracks.md` applied | No ticket was taken from a board or a plan |
| 11 | `rules/human-approval-gate.md` applied | The reserved set went to the human; every other outward effect quotes a standing approval or was asked |
| 12 | `rules/verification-before-claiming.md` applied | Every status line was read from the tracker or the repository, not from a session's note |
| 13 | Merged tickets are Done | A tracker read-back after each merge |
| 14 | The output names everything that waits on the human | The "Only you can do" line is present, or reads (None) |
| 15 | Every decision under the standing approval was stated as such | The message says it was decided under the standing approval and gives the reason |
| 16 | Every hand-over is on its ticket | The draft message and any script or probe are attached to the ticket |
| 17 | The base branch is healthy after each merge | The first CI runs on the base after the merge were read |
| 18 | Each brief names the session's skills | The rendered prompt cites the row in "Skills each session runs" |
| 19 | `rules/unattended-review.md` applied | The final review is a comment review, carries the verdict tables, and no session approved the pull request |
| 20 | `rules/test-quality-gate.md` holds on the verified head | The pull-request body shows all five checks for that head; the coverage gate re-read |
| 21 | The UI verdict is PASS or a reasoned N/A on the same head | The UI-test session's verdict names the head SHA |
| 22 | `rules/session-runtimes.md` applied | Sessions started and messaged per the binding's profile; every relayed handoff block is verbatim |
| 23 | `rules/model-selection.md` applied | Every start named a model from the rule, recorded in the ledger; none moved down |
| 24 | `rules/token-budget.md` applied | Every reported usage is in the ledger; nothing started past 85% |
| 25 | `rules/throughput.md` applied | Fast-track tickets had no separate QA session; no verifier re-ran the full suite without a stated reason |

## Anti-Patterns

- **Implementing in the coordinator.** The orchestrator edits ticket code, and nobody independent reviews that change.
- **Believing a note.** Telling the human "ready to merge" from a session's message while the head has moved and CI is red.
- **Duplicate loops.** A second QA and review pair on a pull request another coordinator already covers.
- **Peer approval laundering.** Treating "the human wants X", relayed by a peer, as approval. Only the human's own words in this conversation count, and they are quoted when relayed.
- **Asking for a decision the human delegated.** Interrupting them for a wording choice after they approved everything that is not architectural.
- **Deciding what they kept.** Changing scope, moving an acceptance criterion, or picking a credential trade-off without asking.
- **Forgetting the sibling merge.** A pull request conflicts, or two pull requests claim the same id, after a neighbour merged and no sync was sent.
- **Polling.** Sleep loops to wait for sessions that will message the coordinator anyway.
- **Implementing someone else's area.** Writing infrastructure or organisation settings after the binding says that is not this human's area.
- **A second method.** Ad-hoc review or QA instructions instead of the role's skill.
- **Ignoring the automated reviewer.** Leaving its threads unresolved because they did not come from this loop's reviewer.
- **A silent card.** Proposing a session card because the start was refused, and not telling the human it needs a click.
- **Starting QA, UI test, and review only after the pull request opens.** The start then lands in a session-triggered turn, is refused, and every pull request waits on the human.
- **Four sessions for a two-line story.** The fast track exists; use it when the binding allows.
- **Every session on the coordinator's model.** The rule picks the tier; the ledger records it.

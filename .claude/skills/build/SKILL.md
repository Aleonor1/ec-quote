---
name: build
description: The end-to-end command. From a short feature prompt (or an approved epic) to one merge-ready epic pull request, unattended after a single checkpoint. Runs rnd to design the feature and split it into stories, opens an epic branch, ships every story through implementer, QA, UI-test, and code-review sessions in dependency waves, merges each verified story into the epic branch, runs the epic-level UI journeys and review, and stops at the epic pull request for the human to merge into the base branch. Use when the human wants a whole feature built from an idea. Do not use for a single ready spec (that is ship) or to merge into the base branch.
argument-hint: <short feature prompt> | <EPIC-KEY> | resume <EPIC-KEY>
---

# Build: one prompt, one epic pull request

The work is: **$ARGUMENTS**

If it is empty, ask the human for the feature in one sentence, or for an epic key, and stop.

The human touches this run twice: once at the design checkpoint, once to merge the epic pull request. Everything between runs on its own.

```
prompt ─▶ rnd ─▶ CHECKPOINT ─▶ epic branch ─▶ wave 1 ─▶ wave 2 ─▶ ... ─▶ epic verification ─▶ epic PR ─▶ HUMAN MERGES
                  (human)                      │ per story: implementer + QA + UI + review
                                               │ merge gate holds ─▶ merge story into epic branch
```

## Step 0: Load the binding and the kit

Read `<kit-root>/bindings/PROJECT.md` in full. You will run the coordinator at `<kit-root>/orchestrate-delivery/skills/orchestrate-delivery/SKILL.md` and follow its rules, with the differences this skill states. Read from the kit: `rules/test-quality-gate.md` (part of every merge gate), `rules/token-budget.md` (the run's token budget and the context rules every brief carries), `rules/model-selection.md` (which model each session runs on), and `rules/throughput.md` (early start, verify once per head, worktree bootstrap, the fast track).

Check the binding has `## Epic delivery`, `## Coverage`, and `## UI testing` filled. A `<placeholder>` left in any of them stops the run: name the field and tell the human to run `/onboard-project`, which fills it from the repository.

## Step 1: Design (or load the design)

- **A prompt:** run the `rnd` skill on it, to its checkpoint. When the human answers `Approve and build`, continue. `Approve design only` stops here with the design and specs written. No answer: stop, nothing is guessed.
- **An epic key:** load the design document and every story it lists. The design's status must be `approved` and every story must pass the Definition of Ready. If not, stop and name what fails; send the human to `/rnd`.

## Step 2: The standing approval for this run

The human's checkpoint answer is the standing approval. Quote it in every brief, together with this scope, and render it into the epic pull request body:

> **Standing approval for build <EPIC-KEY>** (given by <human>: "<their words>"): create and push the epic branch; implement each story test-first on its own branch from the epic branch; open each story pull request against the epic branch; run every gate and the test quality gate; loop QA, UI test, and review to a final verdict; push to story branches, reply to and resolve threads, edit story pull-request bodies, transition story tickets, raise the coverage baseline; **merge each story pull request into the epic branch when its merge gate holds on the verified head**; sync open story pull requests after each merge; open the epic pull request against <base>. Decide wording and design choices inside the approved design, and say so.
>
> **Reserved, always asked:** merging anything into <base>; a deploy; secrets and credentials; repository or organisation settings; a new external service or cost not in the approved design; an architectural change beyond the design; a change that moves an acceptance criterion; lowering the coverage baseline; an irreversible delete; anything in the binding's Reserved decisions.

## Step 3: Open the epic branch

```bash
git fetch origin <base>
git switch -c <epic branch prefix><EPIC-KEY>-<slug> origin/<base>
git push -u origin HEAD
```

Record the epic branch head. Update the design's status to `building` in a first commit on the epic branch. When the binding's Tracker has an epic or parent concept, link every story to the epic.

## Step 4: Open the ledger and start the sessions

**The ledger first.** Every run has one, at `<notes folder>/<EPIC-KEY>/ledger.json`, written only through `<kit root>/orchestrate-delivery/scripts/ledger.py`:

```bash
L="python3 <kit root>/orchestrate-delivery/scripts/ledger.py --file <notes folder>/<EPIC-KEY>/ledger.json"
$L init --epic <EPIC-KEY> --base <base> --epic-branch <epic branch> --approval "<the human's words>" \
   --story <KEY>:<wave>:<dep1+dep2>:<title> ...   (one per story in the design's Story map) \
   --max-sessions <Budget: sessions> --max-hours <Budget: hours> --max-rounds <Max review rounds> \
   --max-fix-stories <Budget: fix stories> \
   --max-tokens <Budget: tokens> --tokens-per-session <Tokens per session estimate> \
   --max-parallel <Max parallel stories> [--no-early-start when Early start is "after merge"]
```

`init` refuses a dependency that is not in an earlier wave. From here on, **every action starts with `$L show`** and every state change is written back: `$L session` when a session starts, idles, finishes, or dies (with `--model`); `$L tokens` whenever the runtime reports a session's usage, and for your own; `$L story` for state, pull request, head, each review round, each verdict; `$L log` for every handoff block relayed. `$L next` says which stories can start now or early, which are stuck, how many slots are free, how many tokens are spent, and whether the budget holds.

**Budget.** Before starting any session and before each new review round, run `$L budget`. Exit 3 means over budget: start nothing new, let sessions in flight finish their current turn, and report to the human at once with `$L show` and what remains. Continuing needs their words (a raised budget is a reserved decision). The token budget (`rules/token-budget.md`) is part of it: at 85% `$L next` lists nothing to start, and you finish what is in flight and report; over 100% is exit 3 like any other budget.

**Models.** Each session starts with the model `rules/model-selection.md` gives it: the story's Models row from the design (the planner's choice), moved up at most one tier when the rule's conditions hold, never down. Pass it to the runtime's start (`model:` in the Agent tool) and record it with `$L session ... --model`. A model the human named in their prompt applies to every session.

**Starting sessions** follows the profile in the binding's Sessions (`rules/session-runtimes.md`):

- **No start refusal** (`claude-code-agents`, most runtimes): start a story's sessions when `$L next` lists it in `start_now` (its dependencies are merged) **or** in `start_early` (its dependencies have an open pull request with no failing verdict; `rules/throughput.md` → Early start). Start every listed story in the same turn, up to the free `slots`. Per story, render the coordinator's briefs with **base = the epic branch**: review, QA (not on the fast track: there the reviewer plays QA too, coordinator Step 4), UI test (only for stories with a UI surface, `brief-ui.md`), then the implementer, with session names `<role>-<KEY>`. An early-started implementer's brief carries the extra paragraph:

  ```text
  Early start: this story depends on <keys>, whose pull requests are open but not merged (heads <sha>, branches <names>). Branch from origin/<epic branch> and merge those branches into yours before you start, so you build on their code. When the coordinator messages "merged <KEY>: epic head <sha>", merge origin/<epic branch>, re-run the affected gates, and continue; a REVISE on a dependency arrives the same way with its new head. Open your pull request only after every dependency has merged into the epic branch.
  ```
- **Starts refused outside the human's turn** (some remote runtimes): start every session the run will need **now**, in the human's turn. An implementer whose story is not in `start_now` gets this extra paragraph and waits idle:

  ```text
  Wait for the go: this story depends on <keys>. Do not branch or write code until the coordinator messages "go <KEY>: dependencies merged, epic head <sha>". Until then read the ticket and the design, plan, and end your turn with a ready block; do not poll. When the go arrives, branch from origin/<epic branch> at that head or newer.
  ```
- **`sequential`**: no sessions; you play the roles in order for each story in `start_now`, under that profile's discipline.

Two epic-level sessions run in Step 6, started when the last stories' sessions start (so they prepare while those build) or now when starts can be refused:
- **Epic UI test**: `skills/ui-test/SKILL.md` in Epic mode, charters = the design's Journeys.
- **Epic review**: `skills/review-code/SKILL.md` on the epic pull request, focused on what no story review could see: the stories working together, duplicated code across stories, the design followed as a whole, migrations in a safe order, the hand-over complete.

When a start is refused anyway, follow the binding's fallback, and tell the human in one line what to click.

## Step 5: Run the waves

The coordinator workflow (its Steps 5 to 7) runs per story, unchanged except:

**When a story's merge gate holds**, verified by you on the live pull request, not from a session's note:
- every required check green on the head, every thread resolved, no review requesting changes
- code review verdict PASS on that head
- QA verdict PASS on that head
- UI-test verdict PASS on that head, or N/A with its stated reason
- the test quality gate's evidence present in the pull-request body for that head, and `scripts/coverage_gate.py` re-run by you against `origin/<epic branch>` confirms it

then, under the standing approval, merge the story pull request into the epic branch with the binding's Epic delivery → Merge a story operation. Read the epic head back. Transition the story per the binding (Done, or the binding's "merged into epic" state), with a comment that names the epic and the merge commit.

**After each merge:**
- `$L story <KEY> --state merged`
- send the sync instruction to every open story pull request on the epic branch (coordinator Step 6, sibling merge), and `merged <KEY>: epic head <sha>` to every early-started implementer that depends on it
- run `$L next`: start the sessions of every story now in `start_now` or `start_early` (up to the free slots), or send `go <KEY>: dependencies merged, epic head <sha>` to its idle implementer when it was pre-started

**After each pull request opens** (the implementer's `pr-opened` block): `$L story <KEY> --state in_review --pr <N> --head <sha>`, then `$L next` again, because a dependant may now start early.

**After each verdict** (`$L story <KEY> --verdict <role>=<verdict>`): a REVISE or BLOCK on a story that early-started dependants are building on is forwarded to them as `revised <KEY>: head <sha>`; they sync, they do not restart.

**A story that does not converge:** when a story reaches the binding's Max review rounds without PASS (`$L story --round` marks it `stuck` itself), or any session reports BLOCK that needs the human, stop that story only. Stories that do not depend on it keep going. Its dependants stay idle. Report it to the human at once (a pull request link, the open findings, and the decision needed), not at the end.

**Watchdog.** Right after the first sessions start, schedule a check-in every 30 minutes with the runtime's scheduling tool, and keep it until the epic pull request is ready. Each check-in runs the procedure in `rules/session-runtimes.md` → Nothing waits forever: `$L stale`, stop the stuck session's hung processes inside its worktree, free a lock it holds, message it, and replace it at the next check-in if it stays silent. Never end the coordinator's turn with sessions running and no check-in scheduled.

**Tokens.** Every completion notification carries the session's usage: `$L tokens <role>-<KEY> --set <n>` at once. At each watchdog check-in, record your own usage from the runtime's counter (`$L tokens coordinator --set <n>`) and run `$L budget`; `near budget` means you start nothing new from then on and say so to the human in the next status.

**Progress** goes in the task list: one item per story, ticked when merged into the epic branch. No narration between steps.

## Resume: `/build resume <EPIC-KEY>`

A run can stop in the middle: the machine slept, the runtime restarted, the budget was hit, a story went stuck and the human answered later. Resume rebuilds the run from the ledger, never from memory.

1. `$L show`. No ledger: there is nothing to resume; say so and stop.
2. **Reconcile every story against the live repository**, because the ledger may be behind: read each recorded pull request (state, head, verdicts, checks). A pull request merged into the epic branch while the run was down becomes `merged`; a moved head is recorded; a story whose pull request vanished goes back to `building` with a note.
3. **Reconcile every session.** For each session the ledger has as `running` or `idle`: message it a ping handoff block (`kind: question`, body "resume: report your state, the head you are on, and what you are waiting for"). One that answers keeps its name. One that cannot be reached (the runtime reports it unknown, or no answer arrives before every other session has answered) is marked `dead`, and a replacement is started with the same name and brief, plus a **Resume** paragraph: the story's current state, pull request, head, and every ledger `log` entry addressed to or from that role, verbatim. The replacement continues from the pull request; it does not redo finished work.
4. `$L budget`: over budget stops here with the report, unless the human raised it in their resume message (quote their words; record the new limits with a note).
5. Continue at Step 5 with `$L next`. Stuck stories stay stuck until the human's answer is in the resume message.

## Step 6: Verify the epic as a whole

When every story is merged into the epic branch:

1. **Sync with the base.** Merge `origin/<base>` into the epic branch if it moved (never force-push); rerun gates.
2. **Gates and quality gate on the epic head**, whole: every command in the binding's Gates, then `rules/test-quality-gate.md` with the diff taken against `origin/<base>`. Under the shared lock when the binding names one.
3. **Refresh the map.** Run the `project-overview` skill in update mode on the epic branch and commit the result, so the merge carries an accurate orientation document.
4. **Open the epic pull request** against `<base>` (binding → Repository → Open a pull request), body:
   - Outcome and link to the design document
   - Stories table: key, title, story pull request, verdicts (QA, UI, review), merge commit
   - Test quality gate on the epic head (the table from the rule)
   - UI journeys verdict (pending until step 5 below)
   - Hand-over: every secret, account, setting, or deploy step the human must do, in order
   - Decisions taken under the standing approval, each with its reason
   - The attribution line
5. **Wake the epic sessions.** Message the epic UI-test and epic review sessions with the pull-request number and head. They loop with you exactly as a story's sessions loop with its implementer, except that a finding is fixed by **a new fix story**: you write its spec the way the `fix` skill does (reproduction, root cause, a regression test red on the epic branch as the first criterion, `epic: <EPIC-KEY>`), start its implementer, QA, UI, and review sessions (this is inside the standing approval, since it restores an approved criterion), merge it into the epic branch when its gate holds, and ask the epic sessions to re-verify.
6. **Verify the final verdict** against the live epic pull request (head matches, checks green, mergeable by the binding's conflict check), as coordinator Step 7 does.

## Step 7: The hard stop

The epic pull request into `<base>` is merged by the human. Never by this run.

```markdown
## Epic ready to merge: <EPIC-KEY> <title>

**Epic PR:** #<N> · head <sha> · base <base>
| Story | PR | QA | UI | Review | Merged into epic |
| --- | --- | --- | --- | --- | --- |

**Epic verification:** gates green · diff coverage <x>% · global <a>% (baseline <b>%) · UI journeys <PASS> · epic review <PASS>
**Run:** <n> sessions (<n> large · <n> standard · <n> small) · tokens <used>/<max> (<n> reported, <n> estimated) · <h> active hours
**Before you merge:** <hand-over steps in order: secrets to set, settings, accounts> | (None)
**Decided under your approval:** <count, listed in the PR body>

**Your move:** review PR #<N> and merge it into <base>. Tell me when it is merged.
```

After the human says it is merged: set the design's status to `shipped`, transition the epic ticket to Done if the tracker has one, read the first CI runs on `<base>` and report any red the merge caused, and confirm every session in the ledger has nothing left to do. Then stop.

## Anti-patterns

- **Merging into the base branch.** Only the human does that. Story merges into the epic branch only.
- **Merging a story on a session's word.** The gate is read from the live pull request and re-run by you.
- **Starting later-wave sessions later** on a runtime that refuses starts outside the human's turn: the run stalls overnight. Pre-start everything in the human's turn there.
- **Waiting for a merge that early start does not need.** A dependant whose dependency's pull request is open and clean sits idle until the merge, and the critical path grows by a review loop per wave.
- **One model for everything.** Every session on the coordinator's model, with no record of which story needed it.
- **A verifier re-running the whole suite** the implementer already ran twice on the same head, for no stated reason.
- **Stopping the whole epic for one stuck story** when other branches of the graph can proceed. Or the opposite: starting a dependant before its dependency merged.
- **Fixing an epic finding directly on the epic branch.** It goes through a fix story with the same four sessions.
- **Guessing past the checkpoint** when the human did not answer.
- **Asking the human for things the standing approval covers.**
- **Waiting without a watchdog.** A session stuck inside a turn sends no notification; without a scheduled check-in the whole run waits on it for hours.
- **Losing the ledger.** Every action starts with `ledger.py show`; every state change goes through `ledger.py`.
- **Spending past the budget.** Over budget means start nothing new and ask.
- **Resuming from memory.** A resumed run trusts the ledger reconciled against the live pull requests, not what it remembers.

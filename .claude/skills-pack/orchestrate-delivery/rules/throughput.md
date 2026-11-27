# Throughput

A run is slow for four reasons: stories wait on each other when they do not have to, every session re-runs the whole suite, every worktree re-installs the project, and small stories get the same four-session treatment as large ones. This rule removes each without lowering the bar in `rules/test-quality-gate.md`: every merged story still has 100% green, nothing skipped, nothing flaky, 95% diff coverage, and the ratchet.

## 1. Stories run in parallel by default

- **A dependency is a code dependency.** Story B depends on story A only when B's code cannot compile, run, or be tested without A's code. Touching the same file, the same module, or the same screen is not a dependency: it is a *shared file*, named in both briefs, each keeping its additions in its own block, and the second merge syncs (coordinator Step 6). `rnd` splits with this definition; `ledger.py init` only checks the graph.
- **The foundation story is as thin as it can be.** When several stories need the same schema, adapter, or contract, that goes in one small first story (the only serial step), and everything else fans out from it. A design whose critical path is longer than three stories is re-split before the checkpoint.
- **Early start.** A story whose dependencies all have an open pull request with no failing verdict may start before they merge (`ledger.py next` → `start_early`, on by default: Epic delivery → Early start). Its implementer branches from the dependency's pull-request head, and when the dependency merges, merges the epic branch and re-runs the affected gates before opening its own pull request. A dependency that is then REVISEd is a sync, not a restart. Turn it off (`--no-early-start`, binding row `after merge`) for projects where dependencies are often reworked.
- **Everything that can start, starts now.** On every `next`, the coordinator starts every story in `start_now` and `start_early`, up to Epic delivery → Max parallel stories (the machine's limit, not a caution; `0` is unlimited). Verifier sessions start with the implementer, prepare, and idle.
- **The epic sessions start with the last wave.** The epic UI tester writes its journey charters and the epic reviewer reads the design while the last stories are still building, so Step 6 of `build` starts on a prepared session.

## 2. Verify once per head

The test quality gate is run **once per head, by the implementer**, who posts the evidence table with the head SHA in the pull-request body and writes the observed output to `<notes folder>/<KEY>/gates-<sha>.md`. Everyone else reads that:

| Session | Re-runs | Does not re-run |
| --- | --- | --- |
| QA | `coverage_gate.py` on the committed report (seconds), `test-hygiene.sh scan` (seconds), its own probes against the running stack, the specific tests of the criteria it doubts | the whole unit and integration suite, the flake repeat |
| UI test | its charters and the specs it wrote | any gate |
| Review | `coverage_gate.py`, `test-hygiene.sh scan`, the red-without-the-change check on the new tests (revert the change, run only those tests) | the whole suite, the flake repeat |
| Coordinator, at the merge gate | `coverage_gate.py` against `origin/<epic branch>`, CI status | anything else |

A verifier re-runs the full suite only when: the evidence for the current head is missing, the CI run on that head is red or absent while the binding has a CI job, or it has a concrete reason to doubt the evidence, which it states in its finding. "To be sure" is not a reason: the flake repeat already ran the suite twice.

**A receipt makes "the evidence for the current head" checkable by a command.** The implementer runs each heavy gate as `scripts/run_gate.py --receipt <notes folder>/<KEY>/receipts/<sha>/<gate>.json -- <command>`, which writes the command, the commit, whether tracked files were changed, the exit code, and the time. A verifier or the coordinator runs `scripts/run_gate.py --check-receipt <that file>`: exit 0 means the gate was green on this head, with no uncommitted change to tracked files, within the last day (`--max-age-minutes`, `--head <sha>` to name another commit). Exit 1 says why on stderr (red, another head, changed files, too old, unreadable), and that is the "evidence is missing" case above. Receipts are optional: `gates-<sha>.md` stays the record a human reads.

**The flake repeat runs at the last head, not every head.** After an intermediate push the implementer runs the affected test files plus `coverage_gate.py`; the full suite twice runs once more when the verifiers have no open findings, and that is the head the evidence table reports. A push after that re-opens the final run.

## 3. Install once per machine, not once per worktree

Every session gets its own worktree, and installing the project in each is often the slowest step of a story. `bindings/PROJECT.md` → Sessions → Worktree bootstrap is one command that makes a fresh worktree runnable in seconds: typically linking or copying the main checkout's dependency folder (`ln -s <main checkout>/node_modules node_modules`, a shared virtualenv, a warm build cache) and only then the Install command when the lockfile changed. `onboard-project` writes it and proves it; every brief runs it first. A worktree whose lockfile differs from the main checkout's runs the full Install.

## 4. A fast track for small stories

A story that is small and has no UI surface does not need four sessions. `bindings/PROJECT.md` → Epic delivery → Fast track names the effort values that qualify (default: the binding's two smallest, e.g. `LOW, SMALL`). For those:

- The QA role folds into the review session: the reviewer runs `skills/verify-acceptance/SKILL.md` first and `skills/review-code/SKILL.md` second, and posts both verdict tables under the one final verdict. Two sessions per story (implementer, reviewer-and-QA) instead of three.
- A story with a UI surface, a story that touches auth, permissions, payments, money, personal data, or a migration, and every fix story stay on the full track whatever their effort.
- The pull-request body says `Track: fast (QA folded into review)`. The human can set Fast track to `(None)` to turn it off.

## 5. Fewer rounds

- The reviewer sends every finding of a round in one message, graded; the implementer answers all of them in one push. One push per round, one re-review per push.
- No round opens for Minors alone once a Blocking or Major has been fixed; Minors go in the final verdict as accepted follow-ups or a single last push, the implementer's choice.
- A rebuttal with evidence closes a finding; a second round on the same finding goes to the coordinator, who decides under the standing approval or asks the human.

## What this rule never trades away

The merge gate itself (`rules/severity-and-gates.md`), the five conditions of the test quality gate on the merged head, independent verification by a session that did not write the code, and the human's merge of the epic.

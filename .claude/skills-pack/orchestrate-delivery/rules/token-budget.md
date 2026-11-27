# Token budget

Every run has a token budget that covers the whole conversation: the coordinator and every session it starts, verifiers included. The default is **600,000 tokens** per run (`bindings/PROJECT.md` → Epic delivery → Budget: tokens). It is kept in the ledger, checked before every start, and reported in every status. A run that reaches it stops starting work and asks the human; raising it is a reserved decision.

## How tokens are counted

| Who | Counted how | When |
| --- | --- | --- |
| A session | The usage the runtime reports when the session ends a turn (the Agent tool's completion notification carries the agent's token count; some runtimes show it as `total_tokens` or `usage`) | `ledger.py tokens <role>-<KEY> --set <n>` at every notification, with the cumulative number the runtime gives |
| A session that has reported nothing yet | The binding's `Tokens per session estimate` (default 40,000), charged while it is `running` or `idle` | Automatic: `ledger.py` adds it until a real count replaces it |
| The coordinator | Its own usage, read from the runtime's own counter when one is shown (a remaining-tokens banner, `/cost`, a usage line in a notification) | `ledger.py tokens coordinator --set <n>` at each watchdog check-in, and before each `next` |
| A dead or replaced session | Its last reported count stays; the replacement counts on its own | Nothing to do |

A runtime that reports no counts at all leaves every session on the estimate. That is a coarse budget (sessions × estimate), still better than none: the coordinator says so once in the delivery status (`tokens: estimated`).

## What the budget does

- `ledger.py next` and `ledger.py budget` report `tokens used/max`.
- At **85%** (`near_budget`), `next` returns no `start_now` and no `start_early`: the coordinator starts no new story and no new session, lets the sessions in flight finish their current pull requests, and reports to the human with what is merged, what is in flight, and what has not started.
- Over **100%**, `ledger.py budget` exits 3 and the coordinator treats it exactly as any other budget overrun (`build` Step 4): start nothing, finish turns in flight, report, wait for the human's words.
- The epic pull request body and every delivery status carry `Tokens: <used>/<max> (<n> sessions reported, <n> estimated)`.

## Keeping sessions small

The budget is spent mostly inside sessions, so every brief carries the context rules below (the session preamble in `rules/session-runtimes.md` includes them). They are the difference between a run that fits in 600,000 tokens and one that does not.

1. **Read what the task needs, not the repository.** Open the binding sections the role reads (the binding's header says which), the ticket, the design section for the story, and the files the change touches. Use search (`grep`, `rg`, the runtime's search tool) to find a symbol; never print whole directories or large files to look around.
2. **Gate output stays out of the context.** Every gate, test, coverage, and end-to-end command runs through `scripts/run_gate.py --tail 40` with `RUN_GATE_LOG_DIR=<notes folder>/<KEY>/logs` set, so the session sees the last 40 lines and the summary, and the full log is on disk for anyone who needs it. A failing test is read from the log with a search for `FAIL`, `Error`, or the test name, not by printing the log.
3. **Do not re-read.** A file read once in a turn is not read again unless it changed. The binding is read once per turn.
4. **Reports are tables, not transcripts.** A handoff block carries the finding, the file and line, expected and observed, and the paths of the evidence; never pasted output beyond ten lines.
5. **Verify once per head.** The implementer runs the full test quality gate and posts the evidence table with the head SHA. QA and review re-run only the two cheap checks (`coverage_gate.py` on the committed report, `test-hygiene.sh scan`) and their own probes; they do not run the whole suite again unless the evidence is missing for that head or they have a reason to doubt it, which they state (`rules/throughput.md`).
6. **End the turn when waiting.** A session with nothing to do ends its turn with a `ready` block. Polling and re-reading while waiting is tokens for nothing.
7. **One push per round.** The implementer fixes every finding of a round in one push and one message, not one push per finding.

## Anti-patterns

- Starting a story at 90% of the budget because "it is a small one".
- Charging nothing for sessions that have not reported, and discovering the overrun at the end.
- A session printing a whole test run, a whole file, or `git log` without a limit into its context.
- Raising the budget in the ledger without the human's quoted words.

# Model selection

The coordinator (the main session running `build`, `ship`, `fix`, or `orchestrate-delivery`) decides which model every session it starts runs on. Sessions never inherit the coordinator's model by accident: each start names a model, chosen by the rules below, and the choice is recorded in the ledger (`ledger.py session <name> --model <m>`). The point is cost: most of a run's tokens go to verifiers and to small stories, and those do not need the largest model.

The runtime's model names are the ones its session-start tool accepts (in Claude Code's Agent tool: `opus`, `sonnet`, `haiku`; the argument is `model:`). `bindings/PROJECT.md` → Models holds the project's defaults; this rule says how to apply them.

## Tiers

| Tier | Used for | Default |
| --- | --- | --- |
| **large** | Judgment with a wide blast radius: design, root cause, security, the final review of a hard change | `opus` |
| **standard** | Well-specified work with a test suite to tell right from wrong | `sonnet` |
| **small** | Mechanical, bounded work: running a charter, walking a checklist, a smoke re-check | `haiku` |

## Which tier a session gets

Decided once per story by the planner (`rnd` writes it into the story map's Models column; `fix` decides it from the bug's severity), and re-read by the coordinator when it starts the session. The coordinator may move a session **up** one tier at start when the story's evidence says so; it never moves one down below the planner's choice.

| Session | Tier | Move up to large when |
| --- | --- | --- |
| Implementer | standard | effort is the binding's largest two values; the story touches auth, permissions, payments, money, personal data, migrations that rewrite data, or concurrency; the story is a fix for a P0 or P1 bug; the story's previous implementer went `stuck` or `dead` |
| QA | standard | the story is a fix for a P0 or P1 bug; the criteria involve money, permissions, or data integrity |
| UI test | small, standard when the story has more than five charters or a multi-step journey | never beyond standard; the screen tells it what is true |
| Code review | standard | any of the implementer's move-up conditions; a story whose first review round found a Blocking; the story adds a new integration |
| Epic UI test | standard | never beyond standard |
| Epic review | large | always large: it judges the stories together |
| Replacement for a dead or stuck session | one tier above the dead session's | always |

`rnd` itself and the root-cause step of `fix` run in the coordinator's own session: the human chose that model when they started the conversation.

## Recording and reporting

- Every start records the model: `ledger.py session <role>-<KEY> --role <role> --key <KEY> --model <m>`.
- `ledger.py show` lists the model per session. The epic pull request body and the delivery status table carry a `Models: <n> large · <n> standard · <n> small` line, so the human sees what the run cost in model terms.
- `retro` reads it: a story whose standard-tier implementer needed more than two review rounds is evidence to move that kind of story up; a large-tier session that found nothing is evidence to move it down. Proposals change the binding's Models rows, never this rule.

## The human overrides

- A model named in the human's prompt ("build EPIC-3 with opus everywhere") applies to every session of that run and is quoted in the ledger's approval.
- `bindings/PROJECT.md` → Models → `Fixed` names roles that always run on one model regardless of this rule.
- A runtime without a model argument (`remote-sessions` whose start tool has none, or `sequential`) ignores this rule: every row reads `inherit`, and the coordinator says so once in the delivery status.

## Anti-patterns

- Starting every session on the largest model because it is the coordinator's.
- Moving a verifier down to the small tier to save tokens on a story that touches money or permissions.
- Choosing per session at start time with no record, so the retro cannot learn from it.
- Replacing a dead large-tier session with a smaller one.

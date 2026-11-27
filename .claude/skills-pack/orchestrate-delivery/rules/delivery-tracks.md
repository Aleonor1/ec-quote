# Delivery tracks

The unit of work is a ticket a human named. A plan file, a board, a rank label, or the last thing that shipped is a record of what was decided. It is not a queue.

## The unit of work

| | |
| --- | --- |
| Unit of work | one ticket |
| Source of requirements | the ticket — summary, acceptance criteria, and the documents it links |
| Chosen by | **a human.** Never an agent. An epic the human approved at the `rnd` checkpoint and launched with `build` names every story in its design; that approval is the human naming them, and nothing outside that story map is. A bug the human reports with `fix` is named by that report; the spec `fix` writes for it is that bug and nothing else |
| Dispatched by | the coordinator, on the human's explicit list. Several tickets at once only when they share no file other than additive configuration (`skills/orchestrate-delivery/SKILL.md`) |
| Implemented by | `skills/implement-ticket/SKILL.md`. In this kit the implementer session owns git for its own branch |
| Validated by | separate QA, UI-test, and code-review sessions, under `rules/test-quality-gate.md`. The coordinator checks their verdicts against the live pull request |

An agent asked to implement without a ticket key asks for the key and stops. It does not read the board, the plan, the branch name, or the last commit to infer one.

## A delta on shipped work is a new ticket

A change to something already shipped gets a new ticket. The shipped record gets a one-line pointer to it. A change to work that has not started is absorbed in the open ticket.

## Anti-patterns

- Picking the next ticket from rank, lane, plan order, or "the obvious next one".
- Auto-chaining a follow-up because the context is warm. Approval is per ticket.
- Splitting an oversized ticket into units invented at dispatch time. Stop and say it needs splitting on the board.

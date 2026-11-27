# Session runtimes

The kit runs several independent agent sessions per ticket. How a session is started, messaged, and awaited depends on the agent runtime. `bindings/PROJECT.md` → Sessions names one **profile** from this file; every skill that starts or messages a session follows that profile. Nothing else in the kit assumes a runtime.

## The handoff block: the one message format

Every message between sessions, in every profile, is a handoff block. A session that has something for another session ends its turn with one (or sends it, where the runtime lets sessions message each other):

```text
<<<HANDOFF
from: <role>-<key>            e.g. qa-story-12
to: <role>-<key>[, ...]       one or more recipients; coordinator is "coordinator"
kind: ready | pr-opened | new-head | findings | verdict | question | blocked | done
head: <sha or (None)>
pr: <number or (None)>
body:
<free text: findings table, verdict table, reproduction, question>
HANDOFF>>>
```

Rules:

- One block per recipient set. A session may end a turn with several blocks.
- `kind: verdict` carries the role's full output template in `body`.
- `kind: question` to `coordinator` is how a reserved decision reaches the human. Peers never answer it.
- The coordinator relays a block **verbatim**; it never rewrites a finding or a verdict.
- Every block is appended to the run ledger (`scripts/ledger.py log`), so a resumed run can replay what was said.

## Profile: `claude-code-agents`

Claude Code with the Agent tool. Each session is a background agent with its own git worktree.

| Capability | How |
| --- | --- |
| Start | Agent tool: `subagent_type: general-purpose`, `isolation: worktree`, `run_in_background: true`, `description: <role>-<key>`, `model: <the model rules/model-selection.md gives this session>`, `prompt:` the rendered brief, prefixed with the Session preamble below. The tool returns an agent id: record it against `<role>-<key>` in the ledger (`ledger.py story <KEY> --note`), because messages are addressed by that id, and record the model (`ledger.py session <role>-<key> --model <m>`) |
| Tokens | The completion notification carries the agent's token usage: record it at once with `ledger.py tokens <role>-<key> --set <n>` (`rules/token-budget.md`). The coordinator records its own count from the runtime's usage line at each watchdog check-in |
| Message | SendMessage `to: <agent id>`, `message:` the handoff block. This continues that agent with its full context, also after it ended its turn |
| Wait | The runtime notifies the coordinator when an agent ends its turn. Never poll, never sleep |
| Result | The agent's last message arrives in the notification. Parse every handoff block in it and relay each |
| Find a session | ListAgents, or the run ledger |
| Peer messaging | Hub and spoke: sessions end their turn with handoff blocks, the coordinator relays. A background session can reach the coordinator with SendMessage `to: main`; peers are reachable only by agent id, which a session learns only if the coordinator tells it, so relaying stays the default |
| Start refusal | None: the coordinator may start sessions in any turn, so `build` starts each story's sessions when its wave opens, not all up front |
| Idle wait | A session told to wait prepares, ends its turn with `kind: ready`, and is continued later by a message |

Session preamble, prepended to every brief in this profile:

```text
You are session <role>-<key> in a multi-session delivery run. Your worktree is yours alone, but the runtime may remove it after a turn that leaves no uncommitted changes: verifiers work in <notes folder>/wt/<role>-<key> instead (create it with git worktree add --detach, reuse it every round); implementers recreate a worktree from their branch when theirs is gone. Fetch origin before branching or checking out anything; never trust the worktree's starting commit. Before anything else in a fresh worktree run the Worktree bootstrap command from bindings/PROJECT.md → Sessions (then Install only when it says so). You cannot assume you can message other sessions: end each turn with handoff blocks (rules/session-runtimes.md) addressed to whoever must act next, and the coordinator relays them verbatim. When you are told to wait, end your turn with a "ready" block; you will be continued with a message. Never let a command run unbounded: run every gate, test, coverage, end-to-end, and walk command through <kit root>/orchestrate-delivery/scripts/run_gate.py --tail <Output tail> with RUN_GATE_LOG_DIR=<notes folder>/<key>/logs (or heavy-run-lock.sh run, which uses it); start servers only in the background and stop them when you are done; never open a report viewer or a watch mode. A "GATE HUNG:" result is a finding you report with the command, not something to retry in a loop. This run has a token budget (rules/token-budget.md): read only the binding sections, ticket, design section, and files your task needs; search instead of printing directories or whole files; never re-read what has not changed; keep gate output in the log and read failures from it by search; report in tables, not pasted output; the test quality gate runs once per head by the implementer and verifiers re-run only the cheap checks and their own probes (rules/throughput.md).
```

**A worktree does not outlive an idle turn.** The runtime removes an agent's worktree when the agent ends a turn with no uncommitted changes, so a verifier (QA, UI test, review) that waits between rounds finds its folder gone. Verifiers therefore work in a worktree of their own under the notes folder (`git worktree add --detach <notes>/wt/<role>-<key> <sha>`), reuse it every round, and the coordinator removes those worktrees when the run ends (`git worktree remove`). An implementer keeps its work on its branch, so it can recreate a worktree from the branch at any time.

**The kit must be visible from every worktree.** A worktree contains only committed files. When the project does not commit `.claude/` (the install is local), every brief names the kit root and the binding by **absolute path** in the main checkout, and the binding's `Kit root` is that absolute path. When `.claude/` is committed, the relative kit root works everywhere.

Machine sharing: all agents run on one machine. Ports, databases, and browsers are shared, so the binding's Shared environment and `scripts/heavy-run-lock.sh` apply to every stack, integration, and end-to-end run.

## Nothing waits forever

A run stalls when one session waits on a command that never ends (a dev server in the foreground, a test runner in watch mode, a report server, an interactive prompt) and every other session waits on it. Three layers stop that:

1. **Every command is bounded.** Sessions run gates through `scripts/run_gate.py`: `CI=1`, no stdin, Playwright's report server off, a total timeout (`RUN_GATE_TIMEOUT`, default 30 minutes), an idle timeout (`RUN_GATE_IDLE`, default 10 minutes without output), known "waiting forever" lines detected, and the whole process tree killed afterwards. `heavy-run-lock.sh run` uses it, so a hung command also frees the lock.
2. **A lock outlives no one.** The lock records the holder's pid and host; a lock whose holder process is gone is broken at once, not after 90 minutes.
3. **The coordinator keeps a watchdog.** Notifications only come when a session ends a turn; a session stuck inside a turn sends none. So after starting sessions the coordinator schedules its own check-in every 30 minutes with the runtime's scheduling tool (a self-scheduled wake-up, a recurring loop, or a monitor; in `sequential` mode it bounds its own commands instead). Each check-in:
   - `ledger.py stale --minutes 45` lists running sessions silent for 45 minutes (exit 4 when there are any);
   - for each, find its long-running processes: `ps -eo pid,etimes,args` filtered to that session's worktree path, older than the gate timeout; stop them (`kill`, then `kill -9`), only inside that worktree. On Windows (Git Bash's `ps` has no `-o`): `powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object CommandLine -like '*<worktree>*' | Select-Object ProcessId,CreationDate,CommandLine"`, then `taskkill /T /F /PID <pid>`;
   - `heavy-run-lock.sh status`, and release a lock whose owner is the stuck session;
   - message the session: "You have been silent N minutes. If a command hangs, stop it, rerun it through run_gate.py, and report where you are." Record it with `ledger.py log`;
   - a session that has not answered by the next check-in is marked `dead`, and a replacement is started as `build resume` describes.
   Sessions waiting for a handoff by design are `idle`, not `running`, so the watchdog leaves them alone: the coordinator sets that state when a session ends its turn with a `ready` block.

## Profile: `remote-sessions`

A runtime whose sessions are separate cloud sessions (each with its own machine). Fill the Sessions table in the binding with that runtime's start, message, and transcript tools. Typical differences: starts may be refused from a turn the human did not begin (then `build` pre-starts every session in the human's turn), sessions do not share a machine (the lock is `(None)`), and peer messaging may be direct.

## Profile: `sequential`

No way to start sessions: one session plays every role, one after another. Use only when nothing else is available, because the roles lose their independence.

Order per ticket: implementer to an open pull request, then QA, then UI test, then review; each finding loops back to the implementer role, and so on until the review verdict.

Discipline that keeps some independence:

1. **A role starts from artifacts, never from memory.** Before each role, write the previous role's handoff blocks to the notes folder. The next role reads only the ticket, the diff, the pull request, and those blocks. It does not reuse reasoning from earlier in the conversation.
2. **Verifiers re-derive.** QA and UI test exercise the criteria themselves; the reviewer reads the ticket before the diff, as `review-code` says. "I wrote it, so I know it works" is not evidence.
3. **Context reset when the runtime offers one** (a subagent run in the foreground with only the brief, a new conversation, a cleared context) is used for every verifier role.
4. **Declared.** The pull-request body and the final verdict state `Run mode: sequential (one session played every role)`. The human weighs the verdict knowing that.

## Choosing the profile

`onboard-project` proposes the profile: `claude-code-agents` when the runtime has the Agent tool, `remote-sessions` when the human names one, `sequential` otherwise. The human can override it in the binding.

## Anti-patterns

- Polling a session or sleeping while it works.
- Rewriting a peer's finding while relaying it.
- A session acting on "the coordinator said the human approved" without the human's words quoted (`rules/human-approval-gate.md`).
- Two sessions bringing up the same stack at once without the lock.
- Running a verifier role in `sequential` mode from the implementer's memory instead of the artifacts.

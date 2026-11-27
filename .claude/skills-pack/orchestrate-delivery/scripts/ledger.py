#!/usr/bin/env python3
"""ledger.py: the run ledger of a build (or a multi-ticket ship).

One JSON file per run holds the stories, their dependency waves and state,
every session, every handoff block exchanged, and the budget. It is how a
run survives a long gap: the coordinator re-reads it before every action,
and `build resume` rebuilds the run from it.

  ledger.py --file F init --epic E --base B --epic-branch BR --approval "words" \
      [--story KEY:WAVE:DEP1+DEP2:TITLE ...] [--max-sessions N] [--max-hours H] \
      [--max-rounds R] [--max-fix-stories N] [--max-idle-minutes M] \
      [--max-tokens T] [--tokens-per-session T] [--max-parallel N] [--early-start | --no-early-start]
  ledger.py --file F story KEY [--state S] [--pr N] [--head SHA] [--round] [--verdict ROLE=V] [--note TEXT]
  ledger.py --file F add-story KEY:WAVE:DEPS:TITLE [--fix]
  ledger.py --file F session NAME --role R --key K [--state running|idle|done|dead] [--model M] [--tokens T]
  ledger.py --file F tokens NAME|coordinator --add T | --set T     record token use; exit 3 when over
  ledger.py --file F log --from A --to B --kind K [--head SHA] [--pr N] [--body-file F]
  ledger.py --file F next              stories to start now (and early), stuck stories, budget; exit 3 if over
  ledger.py --file F budget            exit 0 within budget, 3 over (the reason on stderr)
  ledger.py --file F stale [--minutes M]   running sessions silent for M minutes (default 45); exit 4 if any
  ledger.py --file F show [--json]

Story states: pending -> building -> in_review -> merge_ready -> merged, or stuck.

The hours budget counts active time, not wall time: every write records a
timestamp, and a gap between two writes counts at most --max-idle-minutes
(default 60). A run paused by a runtime limit or a sleeping machine does not
spend its budget while nothing happens.

The token budget (--max-tokens, default 600000) covers the whole run: the
coordinator and every session it starts. A session's count is what the
runtime reports when it ends a turn (`tokens NAME --set T`); a session that
reported nothing counts as --tokens-per-session (default 40000) while it
runs. `next` sets near_budget once 85% is spent: the coordinator then starts
no new story and lets the ones in flight finish.

`next` lists start_now (dependencies merged) and, with early start on, the
default, start_early: stories whose unmerged dependencies all have a pull
request open and no failing verdict, so an implementer can branch from the
dependency's head and sync when it merges. --max-parallel caps how many
stories are in flight at once (0 = no cap).

Exit 0 on success, 1 when refused, 2 on usage error, 3 when the budget is exceeded,
4 when `stale` finds a silent session (the watchdog's signal to act).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows: no fcntl; msvcrt locks a byte range instead.
    fcntl = None
    import msvcrt

LOCK_WAIT_S = 30.0  # a ledger or PR-store write takes milliseconds; longer means a stuck writer


def lock_file(fh) -> None:
    """Block until this process holds the exclusive lock on fh (POSIX flock, Windows msvcrt)."""
    if fcntl is not None:
        fcntl.flock(fh, fcntl.LOCK_EX)
        return
    deadline = time.monotonic() + LOCK_WAIT_S
    while True:
        fh.seek(0)
        try:
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            return
        except OSError:
            if time.monotonic() >= deadline:
                raise SystemExit(f"could not lock {fh.name} within {LOCK_WAIT_S:.0f}s: another writer holds it")
            time.sleep(0.05)


def unlock_file(fh) -> None:
    if fcntl is not None:
        fcntl.flock(fh, fcntl.LOCK_UN)
        return
    fh.seek(0)
    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)

STATES = ("pending", "building", "in_review", "merge_ready", "merged", "stuck")
SESSION_STATES = ("running", "idle", "done", "dead")
DEFAULT_MAX_TOKENS = 600_000
DEFAULT_TOKENS_PER_SESSION = 40_000
NEAR_BUDGET = 0.85


def now() -> float:
    return time.time()


def iso(t: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(t))


def active_hours(d: dict) -> float:
    cap = 60 * (d.get("budget", {}).get("max_idle_minutes") or 60)
    stamps = sorted(d.get("activity", [])) or [d["created"]]
    total, prev = 0.0, d["created"]
    for t in stamps + [now()]:
        total += min(max(t - prev, 0), cap)
        prev = t
    return total / 3600


@contextmanager
def opened(path: Path, create: bool = False):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(path.suffix + ".lock")
    with open(lock, "w") as lh:
        lock_file(lh)
        try:
            if path.exists():
                data = json.loads(path.read_text())
            elif create:
                data = {}
            else:
                raise SystemExit(f"no ledger at {path}: run init first")
            yield data
            if data:
                data.setdefault("activity", []).append(now())
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
            tmp.replace(path)
        finally:
            unlock_file(lh)


def parse_story(spec: str) -> tuple[str, dict]:
    parts = spec.split(":", 3)
    if len(parts) < 2:
        raise SystemExit(f"story spec {spec!r}: expected KEY:WAVE[:DEP1+DEP2[:TITLE]]")
    key, wave = parts[0], int(parts[1])
    deps = [d for d in (parts[2].split("+") if len(parts) > 2 and parts[2] else []) if d]
    title = parts[3] if len(parts) > 3 else ""
    return key, {"wave": wave, "depends_on": deps, "title": title, "state": "pending", "pr": None,
                 "head": None, "rounds": 0, "verdicts": {}, "notes": [], "fix": False}


def tokens_used(d: dict) -> int:
    """Tokens spent so far: the coordinator's own count plus every session's.

    A session that has not reported a count yet is charged the per-session
    estimate while it is running or idle, so the budget is never flattered
    by sessions that have not spoken."""
    b = d.get("budget", {})
    estimate = b.get("tokens_per_session") or DEFAULT_TOKENS_PER_SESSION
    total = int(d.get("counters", {}).get("coordinator_tokens", 0))
    for s in d.get("sessions", {}).values():
        if s.get("tokens") is not None:
            total += int(s["tokens"])
        elif s.get("state") in ("running", "idle"):
            total += estimate
    return total


def over_budget(d: dict) -> list[str]:
    b, c = d.get("budget", {}), d.get("counters", {})
    reasons = []
    if b.get("max_sessions") and c.get("sessions_started", 0) > b["max_sessions"]:
        reasons.append(f"sessions {c['sessions_started']} > {b['max_sessions']}")
    if b.get("max_hours"):
        hours = active_hours(d)
        if hours > b["max_hours"]:
            reasons.append(f"active {hours:.1f} h > {b['max_hours']} h")
    if b.get("max_fix_stories"):
        fixes = sum(1 for s in d["stories"].values() if s.get("fix"))
        if fixes > b["max_fix_stories"]:
            reasons.append(f"fix stories {fixes} > {b['max_fix_stories']}")
    if b.get("max_tokens"):
        used = tokens_used(d)
        if used > b["max_tokens"]:
            reasons.append(f"tokens {used} > {b['max_tokens']}")
    return reasons


def near_budget(d: dict) -> bool:
    mt = d.get("budget", {}).get("max_tokens")
    return bool(mt) and tokens_used(d) >= NEAR_BUDGET * mt


def check_dependencies(stories: dict) -> None:
    for key, s in stories.items():
        for dep in s["depends_on"]:
            if dep not in stories:
                raise SystemExit(f"{key} depends on unknown story {dep}")
            if stories[dep]["wave"] >= s["wave"]:
                raise SystemExit(f"{key} (wave {s['wave']}) depends on {dep} (wave {stories[dep]['wave']}): "
                                 "a dependency must be in an earlier wave")


# ------------------------------------------------------------------ commands

def cmd_init(a, path: Path) -> int:
    if path.exists():
        print(f"{path} exists: a run is already recorded; use `build resume`", file=sys.stderr)
        return 1
    stories = dict(parse_story(s) for s in a.story)
    check_dependencies(stories)
    with opened(path, create=True) as d:
        d.update({
            "epic": a.epic, "base": a.base, "epic_branch": a.epic_branch, "approval": a.approval,
            "created": now(), "stories": stories, "sessions": {}, "log": [],
            "budget": {"max_sessions": a.max_sessions, "max_hours": a.max_hours,
                       "max_rounds": a.max_rounds, "max_fix_stories": a.max_fix_stories,
                       "max_idle_minutes": a.max_idle_minutes, "max_tokens": a.max_tokens,
                       "tokens_per_session": a.tokens_per_session, "max_parallel": a.max_parallel,
                       "early_start": a.early_start},
            "counters": {"sessions_started": 0, "messages": 0, "coordinator_tokens": 0},
        })
    print(f"ledger {path}: {len(stories)} stories in {len({s['wave'] for s in stories.values()})} waves")
    return 0


def cmd_tokens(a, path: Path) -> int:
    if (a.add is None) == (a.set is None):
        raise SystemExit("give exactly one of --add or --set")
    with opened(path) as d:
        if a.name == "coordinator":
            cur = d["counters"].get("coordinator_tokens", 0)
            d["counters"]["coordinator_tokens"] = a.set if a.set is not None else cur + a.add
        else:
            sess = d["sessions"].get(a.name)
            if sess is None:
                raise SystemExit(f"no session {a.name}")
            cur = sess.get("tokens") or 0
            sess["tokens"] = a.set if a.set is not None else cur + a.add
        used, mt = tokens_used(d), d["budget"].get("max_tokens")
    print(f"tokens {used}/{mt or '-'}" + (" (near budget)" if mt and used >= NEAR_BUDGET * mt else ""))
    return 3 if mt and used > mt else 0


def cmd_add_story(a, path: Path) -> int:
    key, s = parse_story(a.spec)
    s["fix"] = a.fix
    with opened(path) as d:
        if key in d["stories"]:
            print(f"{key} already in the ledger", file=sys.stderr)
            return 1
        d["stories"][key] = s
        check_dependencies(d["stories"])
    return 0


def cmd_story(a, path: Path) -> int:
    with opened(path) as d:
        s = d["stories"].get(a.key)
        if s is None:
            raise SystemExit(f"no story {a.key}")
        if a.state:
            if a.state not in STATES:
                raise SystemExit(f"state must be one of {STATES}")
            if a.state == "merged":
                unmet = [x for x in s["depends_on"] if d["stories"][x]["state"] != "merged"]
                if unmet:
                    print(f"{a.key} cannot be merged before {unmet}", file=sys.stderr)
                    return 1
            s["state"] = a.state
        if a.pr is not None:
            s["pr"] = a.pr
        if a.head:
            s["head"] = a.head
        if a.round:
            s["rounds"] += 1
            mr = d["budget"].get("max_rounds")
            if mr and s["rounds"] > mr:
                s["state"] = "stuck"
                s["notes"].append(f"{iso(now())} stuck: {s['rounds']} review rounds > {mr}")
        for v in a.verdict or []:
            role, _, verdict = v.partition("=")
            s["verdicts"][role] = {"verdict": verdict, "head": s.get("head"), "at": iso(now())}
        if a.note:
            s["notes"].append(f"{iso(now())} {a.note}")
    return 0


def cmd_session(a, path: Path) -> int:
    if a.state not in SESSION_STATES:
        raise SystemExit(f"state must be one of {SESSION_STATES}")
    with opened(path) as d:
        new = a.name not in d["sessions"]
        d["sessions"].setdefault(a.name, {"role": a.role, "key": a.key, "started": iso(now()), "restarts": 0})
        sess = d["sessions"][a.name]
        if new:
            d["counters"]["sessions_started"] += 1
        elif a.state == "running" and sess.get("state") == "dead":
            sess["restarts"] += 1
            d["counters"]["sessions_started"] += 1
        sess["state"] = a.state
        sess["updated"] = iso(now())
        sess["last_seen"] = now()
        if a.model:
            sess["model"] = a.model
        if a.tokens is not None:
            sess["tokens"] = a.tokens
    return 0


def cmd_log(a, path: Path) -> int:
    body = Path(a.body_file).read_text(encoding="utf-8") if a.body_file else ""
    with opened(path) as d:
        d["log"].append({"at": iso(now()), "from": a.from_, "to": a.to, "kind": a.kind,
                         "head": a.head, "pr": a.pr, "body": body})
        if a.from_ in d["sessions"]:
            d["sessions"][a.from_]["last_seen"] = now()
        d["counters"]["messages"] += 1
    return 0


def early_ok(s: dict) -> bool:
    """A dependency an implementer may branch from before it merges: its pull
    request is open and no verifier has said REVISE or BLOCK on it."""
    return (s["state"] in ("in_review", "merge_ready") and s.get("pr") is not None
            and all(v["verdict"] == "PASS" for v in s["verdicts"].values()))


def plan(d: dict) -> dict:
    st = d["stories"]
    b = d.get("budget", {})
    ordered = sorted(st.items(), key=lambda x: (x[1]["wave"], x[0]))
    in_flight = [k for k, s in st.items() if s["state"] in ("building", "in_review", "merge_ready")]
    ready = [k for k, s in ordered
             if s["state"] == "pending" and all(st[x]["state"] == "merged" for x in s["depends_on"])]
    early = [k for k, s in ordered
             if s["state"] == "pending" and k not in ready
             and all(st[x]["state"] == "merged" or early_ok(st[x]) for x in s["depends_on"])] \
        if b.get("early_start", True) else []
    blocked_by_stuck = [k for k, s in st.items() if s["state"] == "pending"
                        and any(st[x]["state"] == "stuck" for x in s["depends_on"])]
    near = near_budget(d)
    cap = b.get("max_parallel") or 0
    slots = max(cap - len(in_flight), 0) if cap else None
    if near:
        ready, early, slots = [], [], 0
    elif slots is not None:
        ready, early = ready[:slots], early[:max(slots - len(ready), 0)]
    return {
        "start_now": ready,
        "start_early": early,
        "in_flight": in_flight,
        "merged": [k for k, s in st.items() if s["state"] == "merged"],
        "stuck": [k for k, s in st.items() if s["state"] == "stuck"],
        "waiting_on_stuck": blocked_by_stuck,
        "all_merged": all(s["state"] == "merged" for s in st.values()) and bool(st),
        "slots": slots,
        "tokens": {"used": tokens_used(d), "max": b.get("max_tokens") or 0},
        "near_budget": near,
        "over_budget": over_budget(d),
    }


def cmd_next(a, path: Path) -> int:
    with opened(path) as d:
        p = plan(d)
    print(json.dumps(p, indent=2))
    return 3 if p["over_budget"] else 0


def cmd_budget(a, path: Path) -> int:
    with opened(path) as d:
        r = over_budget(d)
        b, c = d["budget"], d["counters"]
        hours = active_hours(d)
    print(f"sessions {c['sessions_started']}/{b.get('max_sessions') or '-'} · hours {hours:.1f}/{b.get('max_hours') or '-'}"
          f" · tokens {tokens_used(d)}/{b.get('max_tokens') or '-'}{' (near budget)' if near_budget(d) else ''}")
    if r:
        print("over budget: " + "; ".join(r), file=sys.stderr)
        return 3
    return 0


def cmd_stale(a, path: Path) -> int:
    with opened(path) as d:
        silent = []
        for name, s in sorted(d["sessions"].items()):
            if s.get("state") != "running":
                continue
            minutes = (now() - s.get("last_seen", d["created"])) / 60
            if minutes >= a.minutes:
                silent.append({"session": name, "role": s["role"], "key": s["key"], "silent_minutes": round(minutes)})
    print(json.dumps(silent, indent=2))
    return 4 if silent else 0


def cmd_show(a, path: Path) -> int:
    with opened(path) as d:
        p = plan(d)
        if a.json:
            print(json.dumps({**d, "plan": p}, indent=2))
            return 0
        print(f"# Ledger {d['epic']} · {d['epic_branch']} -> {d['base']} · since {iso(d['created'])}\n")
        print("| Story | Wave | Depends on | State | PR | Head | Rounds | Verdicts |")
        print("| --- | --- | --- | --- | --- | --- | --- | --- |")
        for k, s in sorted(d["stories"].items(), key=lambda x: (x[1]["wave"], x[0])):
            v = ", ".join(f"{r}={x['verdict']}" for r, x in s["verdicts"].items()) or "-"
            print(f"| {k}{' (fix)' if s.get('fix') else ''} {s['title']} | {s['wave']} | {', '.join(s['depends_on']) or '-'} | "
                  f"{s['state']} | {s['pr'] or '-'} | {(s['head'] or '-')[:8]} | {s['rounds']} | {v} |")
        print("\n| Session | Role | Story | State | Model | Tokens | Restarts |")
        print("| --- | --- | --- | --- | --- | --- | --- |")
        for n, s in sorted(d["sessions"].items()):
            print(f"| {n} | {s['role']} | {s['key']} | {s.get('state')} | {s.get('model') or 'inherit'} | "
                  f"{s.get('tokens') if s.get('tokens') is not None else '-'} | {s.get('restarts', 0)} |")
        print(f"\n**Start now:** {', '.join(p['start_now']) or '(None)'} · **Start early:** {', '.join(p['start_early']) or '(None)'}"
              f" · **Stuck:** {', '.join(p['stuck']) or '(None)'} · **Messages:** {d['counters']['messages']}")
        print(f"**Tokens:** {p['tokens']['used']}/{p['tokens']['max'] or '-'}{' (near budget: start nothing new)' if p['near_budget'] else ''}"
              f" · **Budget:** {'; '.join(p['over_budget']) or 'within'}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", required=True, help="ledger path, e.g. <notes>/<EPIC>/ledger.json")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    for f in ("--epic", "--base", "--epic-branch", "--approval"):
        p.add_argument(f, required=True)
    p.add_argument("--story", action="append", default=[])
    p.add_argument("--max-sessions", type=int, default=0)
    p.add_argument("--max-hours", type=float, default=0)
    p.add_argument("--max-rounds", type=int, default=5)
    p.add_argument("--max-fix-stories", type=int, default=0)
    p.add_argument("--max-idle-minutes", type=int, default=60)
    p.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    p.add_argument("--tokens-per-session", type=int, default=DEFAULT_TOKENS_PER_SESSION)
    p.add_argument("--max-parallel", type=int, default=0)
    p.add_argument("--early-start", dest="early_start", action="store_true", default=True)
    p.add_argument("--no-early-start", dest="early_start", action="store_false")
    p = sub.add_parser("tokens"); p.add_argument("name"); p.add_argument("--add", type=int); p.add_argument("--set", type=int)
    p = sub.add_parser("add-story"); p.add_argument("spec"); p.add_argument("--fix", action="store_true")
    p = sub.add_parser("story"); p.add_argument("key"); p.add_argument("--state"); p.add_argument("--pr", type=int)
    p.add_argument("--head"); p.add_argument("--round", action="store_true"); p.add_argument("--verdict", action="append")
    p.add_argument("--note")
    p = sub.add_parser("session"); p.add_argument("name"); p.add_argument("--role", required=True)
    p.add_argument("--key", required=True); p.add_argument("--state", default="running")
    p.add_argument("--model"); p.add_argument("--tokens", type=int)
    p = sub.add_parser("log"); p.add_argument("--from", dest="from_", required=True); p.add_argument("--to", required=True)
    p.add_argument("--kind", required=True); p.add_argument("--head"); p.add_argument("--pr", type=int); p.add_argument("--body-file")
    sub.add_parser("next"); sub.add_parser("budget")
    p = sub.add_parser("stale"); p.add_argument("--minutes", type=float, default=45)
    p = sub.add_parser("show"); p.add_argument("--json", action="store_true")
    a = ap.parse_args()
    return globals()[f"cmd_{a.cmd.replace('-', '_')}"](a, Path(a.file))


if __name__ == "__main__":
    sys.exit(main())

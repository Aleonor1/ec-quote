#!/usr/bin/env python3
"""local_pr.py: pull requests without a git host.

For a dry run of the pack, a repository with no GitHub/GitLab access, or a
sandbox whose token cannot open pull requests. Branches stay in the local
repository; every worktree of it (one per agent session) shares the same
pull requests, because the state lives in the git common dir.

  local_pr.py open    --base B --head H --title T [--body-file F]   -> prints N
  local_pr.py view    N [--json]          head/base sha, verdicts, threads, checks, mergeable
  local_pr.py diff    N                   git diff base...head
  local_pr.py list    [--state open|merged|closed|all]
  local_pr.py body    N --body-file F     replace the body
  local_pr.py review  N --verdict PASS|REVISE|BLOCK --role R --body-file F
  local_pr.py comment N --body-file F [--path P --line L] [--author A]   -> prints thread id
  local_pr.py reply   N --thread ID --body-file F [--author A]
  local_pr.py resolve N --thread ID
  local_pr.py check   N --name NAME --status pass|fail [--detail TEXT]
  local_pr.py merge   N [--message M]     merge commit into base, no checkout needed
  local_pr.py close   N

Merge refuses when the pull request has conflicts, an unresolved thread, a
failing check, a required role without a verdict, or a latest verdict per role
that is not PASS on the current head (the merge gate of
rules/severity-and-gates.md). Required roles: `open --require qa,review,ui`,
else $LOCAL_PR_REQUIRED_ROLES, else "qa,review". There is no force.

Exit 0 on success, 1 when an operation is refused, 2 on usage error.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows: no fcntl; msvcrt locks a byte range instead.
    fcntl = None
    import msvcrt

LOCK_WAIT_S = 30.0  # a PR-store write takes milliseconds; longer means a stuck writer


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


def DEFAULT_ROLES() -> list[str]:
    raw = os.environ.get("LOCAL_PR_REQUIRED_ROLES", "qa,review")
    return [r.strip() for r in raw.split(",") if r.strip()]


def git(*args: str, check: bool = True) -> str:
    res = subprocess.run(["git", *args], capture_output=True, text=True)
    if check and res.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {res.stderr.strip()}")
    return res.stdout.strip()


def store() -> Path:
    override = os.environ.get("LOCAL_PR_DIR")
    if override:
        p = Path(override)
    else:
        common = Path(git("rev-parse", "--git-common-dir"))
        if not common.is_absolute():
            common = (Path.cwd() / common).resolve()
        p = common / "local-prs"
    p.mkdir(parents=True, exist_ok=True)
    return p


@contextmanager
def locked():
    lock = store() / ".lock"
    with open(lock, "w") as fh:
        lock_file(fh)
        try:
            yield
        finally:
            unlock_file(fh)


def path_of(n: int) -> Path:
    return store() / f"{n}.json"


def load(n: int) -> dict:
    p = path_of(n)
    if not p.exists():
        raise SystemExit(f"no local pull request #{n}")
    return json.loads(p.read_text())


def save(pr: dict) -> None:
    tmp = path_of(pr["number"]).with_suffix(".tmp")
    tmp.write_text(json.dumps(pr, indent=2))
    tmp.replace(path_of(pr["number"]))


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def sha(ref: str) -> str:
    return git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False)


def read_body(path: str | None) -> str:
    if not path:
        return ""
    text = Path(path).read_text(encoding="utf-8")
    if not text.strip():
        raise SystemExit(f"{path} is empty: an empty body reads as a broken run")
    return text


def conflicts(base: str, head: str) -> list[str]:
    res = subprocess.run(["git", "merge-tree", "--write-tree", "--name-only", "--no-messages", base, head],
                         capture_output=True, text=True)
    if res.returncode == 0:
        return []
    lines = res.stdout.strip().splitlines()
    return lines[1:] if len(lines) > 1 else ["(conflict)"]


def status(pr: dict) -> dict:
    head, base = sha(pr["head"]), sha(pr["base"])
    out = {"head_sha": head, "base_sha": base}
    if pr["state"] != "open":
        return out
    if not head or not base:
        out["blocked"] = [f"branch missing: {pr['head'] if not head else pr['base']}"]
        return out
    blocked = []
    conf = conflicts(base, head)
    if conf:
        blocked.append("conflicts: " + ", ".join(conf))
    open_threads = [t["id"] for t in pr["threads"] if not t["resolved"]]
    if open_threads:
        blocked.append(f"unresolved threads: {open_threads}")
    latest: dict[str, dict] = {}
    for r in pr["reviews"]:
        latest[r["role"]] = r
    for role, r in sorted(latest.items()):
        if r["head"] != head:
            blocked.append(f"{role} verdict is on {r['head'][:8]}, head is {head[:8]}")
        elif r["verdict"] != "PASS":
            blocked.append(f"{role} verdict {r['verdict']}")
    for role in pr.get("required", DEFAULT_ROLES()):
        if role not in latest:
            blocked.append(f"no {role} verdict")
    checks: dict[str, dict] = {}
    for c in pr["checks"]:
        checks[c["name"]] = c
    for name, c in sorted(checks.items()):
        if c["head"] != head:
            blocked.append(f"check {name} is on {c['head'][:8]}, head is {head[:8]}")
        elif c["status"] != "pass":
            blocked.append(f"check {name} failed")
    out["mergeable"] = not conf
    out["merge_gate"] = "holds" if not blocked else "blocked"
    out["blocked"] = blocked
    out["verdicts"] = {k: f"{v['verdict']} @ {v['head'][:8]}" for k, v in latest.items()}
    out["checks"] = {k: f"{v['status']} @ {v['head'][:8]}" for k, v in checks.items()}
    return out


# ------------------------------------------------------------------ commands

def cmd_open(a) -> int:
    for ref in (a.base, a.head):
        if not sha(ref):
            raise SystemExit(f"no such branch: {ref}")
    with locked():
        nums = [int(p.stem) for p in store().glob("*.json")]
        n = max(nums, default=0) + 1
        pr = {"number": n, "title": a.title, "base": a.base, "head": a.head, "state": "open",
              "body": read_body(a.body_file), "created": now(), "author": a.author,
              "required": [r.strip() for r in a.require.split(",") if r.strip()] if a.require else DEFAULT_ROLES(),
              "reviews": [], "threads": [], "checks": [], "events": [{"at": now(), "event": "opened"}]}
        save(pr)
    print(n)
    return 0


def cmd_view(a) -> int:
    pr = load(a.number)
    st = status(pr)
    if a.json:
        print(json.dumps({**pr, **st}, indent=2))
        return 0
    print(f"#{pr['number']} {pr['title']}  [{pr['state']}]  {pr['head']} -> {pr['base']}")
    print(f"head {st.get('head_sha', '')[:12]}  base {st.get('base_sha', '')[:12]}")
    if pr["state"] == "open":
        print(f"merge gate: {st['merge_gate']}")
        for b in st["blocked"]:
            print(f"  - {b}")
        for k, v in st.get("verdicts", {}).items():
            print(f"verdict {k}: {v}")
        for k, v in st.get("checks", {}).items():
            print(f"check {k}: {v}")
    for t in pr["threads"]:
        where = f" {t['path']}:{t['line']}" if t.get("path") else ""
        print(f"thread {t['id']}{where} [{'resolved' if t['resolved'] else 'open'}] {t['messages'][0]['body'][:80]!r}")
    return 0


def cmd_diff(a) -> int:
    pr = load(a.number)
    sys.stdout.write(git("diff", f"{pr['base']}...{pr['head']}") + "\n")
    return 0


def cmd_list(a) -> int:
    for p in sorted(store().glob("*.json"), key=lambda x: int(x.stem)):
        pr = json.loads(p.read_text())
        if a.state != "all" and pr["state"] != a.state:
            continue
        print(f"#{pr['number']}\t{pr['state']}\t{pr['head']} -> {pr['base']}\t{pr['title']}")
    return 0


def mutate(n: int, fn) -> dict:
    with locked():
        pr = load(n)
        fn(pr)
        save(pr)
        return pr


def cmd_body(a) -> int:
    body = read_body(a.body_file)
    mutate(a.number, lambda pr: pr.update(body=body))
    return 0


def cmd_review(a) -> int:
    body = read_body(a.body_file)
    def f(pr):
        if pr["state"] != "open":
            raise SystemExit(f"#{pr['number']} is {pr['state']}")
        head = sha(pr["head"])
        pr["reviews"].append({"role": a.role, "verdict": a.verdict, "head": head, "body": body, "at": now()})
        pr["events"].append({"at": now(), "event": f"review {a.role} {a.verdict} @ {head[:8]}"})
    mutate(a.number, f)
    return 0


def cmd_comment(a) -> int:
    body = read_body(a.body_file)
    out = {}
    def f(pr):
        tid = len(pr["threads"]) + 1
        pr["threads"].append({"id": tid, "path": a.path, "line": a.line, "resolved": False,
                              "head": sha(pr["head"]), "messages": [{"author": a.author, "body": body, "at": now()}]})
        out["id"] = tid
    mutate(a.number, f)
    print(out["id"])
    return 0


def _thread(pr, tid):
    for t in pr["threads"]:
        if t["id"] == tid:
            return t
    raise SystemExit(f"#{pr['number']} has no thread {tid}")


def cmd_reply(a) -> int:
    body = read_body(a.body_file)
    mutate(a.number, lambda pr: _thread(pr, a.thread)["messages"].append({"author": a.author, "body": body, "at": now()}))
    return 0


def cmd_resolve(a) -> int:
    mutate(a.number, lambda pr: _thread(pr, a.thread).update(resolved=True))
    return 0


def cmd_check(a) -> int:
    def f(pr):
        pr["checks"].append({"name": a.name, "status": a.status, "detail": a.detail, "head": sha(pr["head"]), "at": now()})
    mutate(a.number, f)
    return 0


def cmd_merge(a) -> int:
    with locked():
        pr = load(a.number)
        if pr["state"] != "open":
            print(f"#{pr['number']} is {pr['state']}", file=sys.stderr)
            return 1
        st = status(pr)
        if st["merge_gate"] != "holds":
            print("merge refused, the merge gate does not hold:", file=sys.stderr)
            for b in st["blocked"]:
                print(f"  - {b}", file=sys.stderr)
            return 1
        base_ref = f"refs/heads/{pr['base']}"
        base_sha, head_sha = st["base_sha"], st["head_sha"]
        if subprocess.run(["git", "merge-base", "--is-ancestor", head_sha, base_sha]).returncode == 0:
            print(f"#{pr['number']}: {pr['head']} is already in {pr['base']}", file=sys.stderr)
            return 1
        tree = git("merge-tree", "--write-tree", base_sha, head_sha).splitlines()[0]
        msg = a.message or f"Merge local PR #{pr['number']}: {pr['title']}\n\n{pr['head']} into {pr['base']}"
        commit = git("commit-tree", tree, "-p", base_sha, "-p", head_sha, "-m", msg)
        git("update-ref", base_ref, commit, base_sha)
        pr["state"] = "merged"
        pr["merge_commit"] = commit
        pr["events"].append({"at": now(), "event": f"merged as {commit[:8]}"})
        save(pr)
    print(commit)
    sync_worktrees(pr["base"], base_sha, commit)
    return 0


def sync_worktrees(branch: str, old: str, new: str) -> None:
    """Moving a branch ref does not touch a worktree that has it checked out: its files
    stay at the old commit and read as reverse changes. Fast-forward each such worktree's
    index and files (a two-tree read-tree merge keeps local edits that do not conflict)."""
    path = None
    for line in git("worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            path = line.split(" ", 1)[1]
        elif line == f"branch refs/heads/{branch}" and path:
            res = subprocess.run(["git", "-C", path, "read-tree", "-u", "-m", old, new], capture_output=True, text=True)
            if res.returncode == 0:
                print(f"updated the checkout of {branch} at {path}", file=sys.stderr)
            else:
                print(f"note: {branch} is checked out at {path} with local changes that conflict with the merge; "
                      f"commit or discard them, then run `git -C {path} read-tree -u -m {old[:12]} {new[:12]}`", file=sys.stderr)


def cmd_close(a) -> int:
    mutate(a.number, lambda pr: (pr.update(state="closed"), pr["events"].append({"at": now(), "event": "closed"})))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("open"); p.add_argument("--base", required=True); p.add_argument("--head", required=True)
    p.add_argument("--title", required=True); p.add_argument("--body-file"); p.add_argument("--author", default="implementer")
    p.add_argument("--require", help="comma-separated roles whose PASS the merge needs (default qa,review)")
    p = sub.add_parser("view"); p.add_argument("number", type=int); p.add_argument("--json", action="store_true")
    p = sub.add_parser("diff"); p.add_argument("number", type=int)
    p = sub.add_parser("list"); p.add_argument("--state", default="open", choices=["open", "merged", "closed", "all"])
    p = sub.add_parser("body"); p.add_argument("number", type=int); p.add_argument("--body-file", required=True)
    p = sub.add_parser("review"); p.add_argument("number", type=int); p.add_argument("--verdict", required=True, choices=["PASS", "REVISE", "BLOCK"])
    p.add_argument("--role", required=True); p.add_argument("--body-file", required=True)
    p = sub.add_parser("comment"); p.add_argument("number", type=int); p.add_argument("--body-file", required=True)
    p.add_argument("--path"); p.add_argument("--line", type=int); p.add_argument("--author", default="review")
    p = sub.add_parser("reply"); p.add_argument("number", type=int); p.add_argument("--thread", type=int, required=True)
    p.add_argument("--body-file", required=True); p.add_argument("--author", default="implementer")
    p = sub.add_parser("resolve"); p.add_argument("number", type=int); p.add_argument("--thread", type=int, required=True)
    p = sub.add_parser("check"); p.add_argument("number", type=int); p.add_argument("--name", required=True)
    p.add_argument("--status", required=True, choices=["pass", "fail"]); p.add_argument("--detail", default="")
    p = sub.add_parser("merge"); p.add_argument("number", type=int); p.add_argument("--message")
    p = sub.add_parser("close"); p.add_argument("number", type=int)
    a = ap.parse_args()
    return globals()[f"cmd_{a.cmd}"](a)


if __name__ == "__main__":
    sys.exit(main())

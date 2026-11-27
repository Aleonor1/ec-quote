#!/usr/bin/env python3
"""run_gate.py: run one gate command so that it can never hang a delivery run.

  run_gate.py [--timeout S] [--idle S] [--name NAME] [--tail N] [--log FILE] [--receipt FILE] -- <command...>
  run_gate.py --check-receipt FILE [--head SHA] [--max-age-minutes M]

--receipt writes what ran, on which commit, and how it ended, as JSON, so a
heavy suite runs once per head and the next session can read the result
instead of running it again (rules/throughput.md). --check-receipt exits 0
only when that receipt is green, was taken on HEAD (or --head) with a clean
tree, and is younger than --max-age-minutes (default 1440); 1 otherwise, with
the reason on stderr.

Every gate command (tests, coverage, end-to-end, lint, the UI walk) runs
through this wrapper. It:

  - with --tail N, prints only the last N lines of the command's output (plus
    a one-line summary), so a session's context is not filled with thousands
    of lines of test output; --log FILE keeps the whole output on disk for
    anyone who needs the full run (the default when --tail is set:
    $RUN_GATE_LOG_DIR/<name>.log when that variable is set, else no file);

  - sets CI=1 and turns off Playwright's HTML report server
    (PW_TEST_HTML_REPORT_OPEN=never, PLAYWRIGHT_HTML_OPEN=never), so test
    runners do not watch files or open a report and wait for Ctrl+C;
  - gives the command no stdin, so an interactive prompt gets end-of-file and
    fails at once instead of waiting for an answer nobody will type;
  - runs it in its own process group and, when it ends for any reason, kills
    whatever it left behind (a dev server, a browser, a report server);
  - stops it when it runs longer than --timeout seconds (default
    $RUN_GATE_TIMEOUT or 1800), prints nothing for --idle seconds (default
    $RUN_GATE_IDLE or 600), or prints a line known to mean "waiting forever"
    (a report server, "Press Ctrl+C", "Watching for file changes").

Exit: the command's own exit code; 124 when it was stopped for hanging, with
a one-line reason on stderr starting with "GATE HUNG:" that a session can
report as a finding. Standard library only; Linux, macOS, and Windows (native
Python or Git Bash: the command runs in a Job Object, so everything it starts
is stopped with it; taskkill /T is the fallback).
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import signal
import subprocess
import sys
import threading
import time

HANG_PATTERNS = [
    r"Serving HTML report at",
    r"Press Ctrl\+C to (quit|stop|exit)",
    r"Watching for file changes",
    r"Waiting for file changes",
    r"press h to show help",          # vitest / vite interactive mode
    r"\? (Are you sure|Do you want|Enter a name)",  # interactive prompts
]
HANG_GRACE = 5.0   # seconds after a hang line before the group is stopped
KILL_GRACE = 5.0   # seconds between SIGTERM and SIGKILL
WINDOWS = os.name == "nt"


def gate_env() -> dict:
    env = dict(os.environ)
    env.update({
        "CI": "1",
        "PW_TEST_HTML_REPORT_OPEN": "never",
        "PLAYWRIGHT_HTML_OPEN": "never",
        "npm_config_yes": "true",
        "NO_UPDATE_NOTIFIER": "1",
    })
    return env


class WinJob:
    """A Windows Job Object: every process the command starts joins it, and
    closing it stops them all, including children whose parent already exited."""

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.OpenProcess.restype = wintypes.HANDLE
        self.k32, self.handle = k32, k32.CreateJobObjectW(None, None)
        if not self.handle:
            raise OSError("CreateJobObject failed")

        class Basic(ctypes.Structure):
            _fields_ = [("a", ctypes.c_int64), ("b", ctypes.c_int64), ("LimitFlags", wintypes.DWORD),
                        ("c", ctypes.c_size_t), ("d", ctypes.c_size_t), ("e", wintypes.DWORD),
                        ("f", ctypes.c_size_t), ("g", wintypes.DWORD), ("h", wintypes.DWORD)]

        class Extended(ctypes.Structure):
            _fields_ = [("Basic", Basic), ("Io", ctypes.c_uint64 * 6), ("i", ctypes.c_size_t),
                        ("j", ctypes.c_size_t), ("k", ctypes.c_size_t), ("l", ctypes.c_size_t)]

        info = Extended()
        info.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not k32.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            raise OSError("SetInformationJobObject failed")

    def add(self, pid: int) -> None:
        h = self.k32.OpenProcess(0x0001 | 0x0100, False, pid)  # TERMINATE | SET_QUOTA
        if not h or not self.k32.AssignProcessToJobObject(self.handle, h):
            raise OSError("AssignProcessToJobObject failed")
        self.k32.CloseHandle(h)

    def kill(self) -> None:
        self.k32.TerminateJobObject(self.handle, 1)
        self.k32.CloseHandle(self.handle)


def kill_tree_windows(pid: int, job) -> None:
    if job is not None:
        try:
            job.kill()
            return
        except OSError:
            pass
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def kill_group(pgid: int) -> None:
    for sig, wait in ((signal.SIGTERM, KILL_GRACE), (signal.SIGKILL, 0)):
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, PermissionError):
            return
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            try:
                os.killpg(pgid, 0)
            except (ProcessLookupError, PermissionError):
                return
            time.sleep(0.1)


class Output:
    """Where the command's output goes: straight through, or the last N lines
    to stdout and everything to a log file."""

    def __init__(self, tail: int, log: str | None):
        self.tail, self.lines, self.count = tail, [], 0
        self.fh = open(log, "wb") if log else None

    def write(self, raw: bytes) -> None:
        self.count += 1
        if self.fh:
            self.fh.write(raw)
            self.fh.flush()
        if self.tail:
            self.lines.append(raw)
            if len(self.lines) > self.tail:
                self.lines.pop(0)
        else:
            sys.stdout.buffer.write(raw)
            sys.stdout.flush()

    def close(self, name: str) -> None:
        if self.fh:
            self.fh.close()
        if self.tail:
            hidden = self.count - len(self.lines)
            if hidden > 0:
                sys.stdout.write(f"[run_gate: {hidden} earlier lines of {name} not shown"
                                 f"{'; full output in ' + self.fh.name if self.fh else ''}]\n")
            for raw in self.lines:
                sys.stdout.buffer.write(raw)
            sys.stdout.flush()


def run(cmd: list[str], timeout: float, idle: float, name: str, tail: int = 0, log: str | None = None) -> int:
    hang_re = re.compile("|".join(HANG_PATTERNS), re.I)
    out = Output(tail, log)
    if WINDOWS:
        group = {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)}
    else:
        group = {"start_new_session": True}
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, env=gate_env(), **group)
    except OSError as exc:
        print(f"GATE ERROR: cannot start {name}: {exc}", file=sys.stderr)
        return 127
    job = None
    if WINDOWS:
        try:
            job = WinJob()
            job.add(proc.pid)
        except (OSError, AttributeError):
            job = None
    state = {"last": time.monotonic(), "hang": None, "hang_at": 0.0}

    def pump() -> None:
        for raw in iter(proc.stdout.readline, b""):
            out.write(raw)
            state["last"] = time.monotonic()
            if state["hang"] is None and hang_re.search(raw.decode("utf-8", "replace")):
                state["hang"] = raw.decode("utf-8", "replace").strip()
                state["hang_at"] = time.monotonic()

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    start = time.monotonic()
    reason = None
    while proc.poll() is None:
        now = time.monotonic()
        if now - start > timeout:
            reason = f"ran longer than {timeout:.0f}s"
        elif now - state["last"] > idle:
            reason = f"printed nothing for {idle:.0f}s"
        elif state["hang"] and now - state["hang_at"] > HANG_GRACE:
            reason = f"waits forever: {state['hang'][:120]!r}"
        if reason:
            break
        time.sleep(0.2)
    code = proc.poll()
    if WINDOWS:
        kill_tree_windows(proc.pid, job)
    else:
        kill_group(proc.pid)      # the command, and anything it left running
    reader.join(timeout=2)
    out.close(name)
    if reason:
        print(f"GATE HUNG: {name} {reason}; stopped it and its child processes "
              f"after {time.monotonic() - start:.0f}s", file=sys.stderr)
        return 124
    return code if code is not None else proc.wait()


def git_state() -> tuple[str | None, bool]:
    """(HEAD sha, tracked files changed), or (None, True) outside a git checkout."""
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"],
                                capture_output=True, text=True, check=True).stdout
        return head, status.strip() != ""
    except (OSError, subprocess.CalledProcessError):
        return None, True


def write_receipt(path: str, name: str, cmd: list[str], code: int, started: float,
                  head: str | None, dirty: bool) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    data = {"name": name, "cmd": cmd, "exit": code, "head": head, "dirty": dirty,
            "started": started, "seconds": round(time.time() - started, 1), "host": platform.node()}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def check_receipt(path: str, head: str | None, max_age_min: float) -> int:
    try:
        with open(path, encoding="utf-8") as fh:
            r = json.load(fh)
        if not isinstance(r, dict):
            raise ValueError("not a JSON object")
    except (OSError, ValueError) as exc:
        print(f"RECEIPT INVALID: {path}: {exc}", file=sys.stderr)
        return 1
    want = head or git_state()[0]
    problems = []
    if r.get("exit") != 0:
        problems.append(f"exit {r.get('exit')}")
    if r.get("dirty"):
        problems.append("taken with changes to tracked files")
    if not want or r.get("head") != want:
        problems.append(f"head {str(r.get('head'))[:12]} is not {str(want)[:12]}")
    if time.time() - float(r.get("started", 0)) > max_age_min * 60:
        problems.append(f"older than {max_age_min:.0f} minutes")
    if problems:
        print(f"RECEIPT STALE: {r.get('name')}: " + "; ".join(problems), file=sys.stderr)
        return 1
    print(f"RECEIPT OK: {r.get('name')} green on {want[:12]} in {r.get('seconds')}s")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--timeout", type=float, default=float(os.environ.get("RUN_GATE_TIMEOUT", 1800)))
    ap.add_argument("--idle", type=float, default=float(os.environ.get("RUN_GATE_IDLE", 600)))
    ap.add_argument("--name", default=None)
    ap.add_argument("--tail", type=int, default=int(os.environ.get("RUN_GATE_TAIL", 0)),
                    help="print only the last N lines (0 = everything)")
    ap.add_argument("--log", default=None, help="write the whole output to this file")
    ap.add_argument("--receipt", default=None, help="write a JSON receipt (command, HEAD, exit code, time) to this file")
    ap.add_argument("--check-receipt", default=None, help="exit 0 only when this receipt is green on HEAD (or --head)")
    ap.add_argument("--head", default=None, help="the commit --check-receipt expects (default: HEAD)")
    ap.add_argument("--max-age-minutes", type=float, default=1440, help="--check-receipt: oldest receipt accepted")
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    if a.check_receipt:
        return check_receipt(a.check_receipt, a.head, a.max_age_minutes)
    cmd = a.cmd[1:] if a.cmd[:1] == ["--"] else a.cmd
    if not cmd:
        ap.error("give the gate command after --")
    name = a.name or " ".join(cmd)[:80]
    log = a.log
    if log is None and a.tail and os.environ.get("RUN_GATE_LOG_DIR"):
        os.makedirs(os.environ["RUN_GATE_LOG_DIR"], exist_ok=True)
        log = os.path.join(os.environ["RUN_GATE_LOG_DIR"], re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:60] + ".log")
    head, dirty = git_state() if a.receipt else (None, True)
    started = time.time()
    code = run(cmd, a.timeout, a.idle, name, a.tail, log)
    if a.receipt:
        write_receipt(a.receipt, name, cmd, code, started, head, dirty)
    return code


if __name__ == "__main__":
    sys.exit(main())

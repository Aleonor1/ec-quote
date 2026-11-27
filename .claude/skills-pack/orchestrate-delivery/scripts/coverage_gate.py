#!/usr/bin/env python3
"""coverage_gate.py: the coverage half of rules/test-quality-gate.md.

Reads one coverage report (lcov .info, or Cobertura XML) produced by the
project's coverage command, and enforces two things:

  1. Diff coverage: lines (and branches, when the report has them) added or
     changed against the base must be covered at >= --diff-min percent.
     A changed source file that matches --include but is absent from the
     report counts as fully uncovered: an untested new file never passes.

  2. Ratchet on global coverage: global lines/branches/functions may not
     drop below the committed baseline. Once a metric reaches --target, the
     gate for that metric becomes ">= --target". With --update-baseline the
     baseline file is raised to the current values (never lowered).

During a merge that conflicts on the baseline file (two branches each raised
it), `coverage_gate.py --resolve-baseline-conflict [--baseline F]` writes the
higher value of each metric from both sides and stages the file: the ratchet
never moves down because of a merge.

Exit 0 when the gate holds, 1 when it fails, 2 on a usage or input error.
Standard library only, so it runs anywhere the gates run.

  coverage_gate.py --report coverage/lcov.info --base origin/main \
      --baseline .coverage-baseline.json --diff-min 95 --target 95 \
      --include 'src/**' --exclude '**/*.test.*'
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

TOLERANCE = 0.05  # percentage points; absorbs float noise between runs


@dataclass
class FileCov:
    lines: dict[int, int] = field(default_factory=dict)          # line -> hits
    branches: dict[int, list[bool]] = field(default_factory=dict)  # line -> [taken?]
    fn_total: int = 0
    fn_hit: int = 0


# ---------------------------------------------------------------- parsing

def parse_lcov(path: str) -> dict[str, FileCov]:
    files: dict[str, FileCov] = {}
    cur: FileCov | None = None
    fn_names: set[str] = set()
    fn_hits: dict[str, int] = {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.strip()
            if line.startswith("SF:"):
                name = line[3:]
                cur = files.setdefault(name, FileCov())
                fn_names, fn_hits = set(), {}
            elif cur is None:
                continue
            elif line.startswith("DA:"):
                parts = line[3:].split(",")
                ln, hits = int(parts[0]), int(float(parts[1]))
                cur.lines[ln] = cur.lines.get(ln, 0) + hits
            elif line.startswith("BRDA:"):
                parts = line[5:].split(",")
                ln, taken = int(parts[0]), parts[3]
                cur.branches.setdefault(ln, []).append(taken not in ("-", "0"))
            elif line.startswith("FN:"):
                fn_names.add(line[3:].split(",", 1)[1])
            elif line.startswith("FNDA:"):
                hits, name = line[5:].split(",", 1)
                fn_hits[name] = fn_hits.get(name, 0) + int(float(hits))
            elif line == "end_of_record":
                cur.fn_total += len(fn_names)
                cur.fn_hit += sum(1 for n in fn_names if fn_hits.get(n, 0) > 0)
                cur = None
    return files


_COND = re.compile(r"\((\d+)/(\d+)\)")


def parse_cobertura(path: str) -> dict[str, FileCov]:
    root = ET.parse(path).getroot()
    sources = [s.text.strip() for s in root.iter("source") if s.text]
    files: dict[str, FileCov] = {}
    for cls in root.iter("class"):
        name = cls.get("filename", "")
        if sources and not os.path.isabs(name):
            # Cobertura names are relative to one of the <source> roots (pytest-cov
            # writes one root per --cov path). Anchor the name to the root that has
            # it, so include/exclude globs see the repository path, not a bare stem.
            roots = [s for s in sources if os.path.exists(os.path.join(s, name))] or sources[:1]
            name = os.path.join(roots[0], name)
        fc = files.setdefault(name, FileCov())
        for ln_el in cls.iter("line"):
            ln = int(ln_el.get("number", "0"))
            hits = int(float(ln_el.get("hits", "0")))
            fc.lines[ln] = fc.lines.get(ln, 0) + hits
            if ln_el.get("branch") == "true":
                m = _COND.search(ln_el.get("condition-coverage", ""))
                if m:
                    covered, total = int(m.group(1)), int(m.group(2))
                    fc.branches[ln] = [True] * covered + [False] * (total - covered)
        for meth in cls.iter("method"):
            fc.fn_total += 1
            if any(int(float(l.get("hits", "0"))) > 0 for l in meth.iter("line")):
                fc.fn_hit += 1
    return files


def load_report(path: str) -> dict[str, FileCov]:
    if not os.path.isfile(path):
        raise SystemExit(f"coverage report not found: {path} (run the Coverage command first)")
    with open(path, encoding="utf-8", errors="replace") as fh:
        head = fh.read(512).lstrip()
    return parse_cobertura(path) if head.startswith("<") else parse_lcov(path)


# ---------------------------------------------------------------- git diff

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def changed_lines(base: str) -> dict[str, set[int]]:
    """Repo-relative path -> added/changed line numbers, against merge-base."""
    try:
        mb = subprocess.run(["git", "merge-base", base, "HEAD"], check=True,
                            capture_output=True, text=True).stdout.strip()
        out = subprocess.run(["git", "diff", "--unified=0", "--no-color",
                              "--diff-filter=AMR", mb, "--"], check=True,
                             capture_output=True, text=True).stdout
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"git diff against {base} failed: {exc.stderr.strip()}")
    result: dict[str, set[int]] = {}
    path = None
    for line in out.splitlines():
        if line.startswith("+++ "):
            target = line[4:]
            path = None if target == "/dev/null" else target[2:] if target.startswith("b/") else target
            if path:
                result.setdefault(path, set())
        elif path and (m := _HUNK.match(line)):
            start, count = int(m.group(1)), int(m.group(2) or "1")
            result[path].update(range(start, start + count))
    # A new file not yet committed is a change too: without this, a gate run
    # before the commit would not see it and could pass on the old files alone.
    untracked = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"],
                               capture_output=True, text=True).stdout.splitlines()
    for path in untracked:
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                n = sum(1 for _ in fh)
        except OSError:
            continue
        result.setdefault(path, set()).update(range(1, n + 1))
    return result


# ---------------------------------------------------------------- helpers

def matches(path: str, globs: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, g) or fnmatch.fnmatch(path, g.replace("**/", "")) for g in globs)


_TOPLEVEL: str | None = None


def toplevel() -> str:
    global _TOPLEVEL
    if _TOPLEVEL is None:
        try:
            _TOPLEVEL = subprocess.run(["git", "rev-parse", "--show-toplevel"], check=True,
                                       capture_output=True, text=True).stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            _TOPLEVEL = os.getcwd()
    return _TOPLEVEL


def candidates(name: str) -> list[str]:
    """Repo-relative spellings of a report path, best first.

    A report written in a container or on CI carries absolute paths from that
    machine; every trailing suffix is tried so the globs still apply."""
    n = name.replace("\\", "/")
    out = []
    if os.path.isabs(n):
        top = toplevel().replace("\\", "/")
        if n.startswith(top + "/"):
            out.append(n[len(top) + 1:])
        parts = n.strip("/").split("/")
        out.extend("/".join(parts[i:]) for i in range(len(parts)))
    else:
        out.append(n[2:] if n.startswith("./") else n)
    return out


def file_matches(name: str, globs: list[str]) -> bool:
    return any(matches(c, globs) for c in candidates(name))


def resolve(report: dict[str, FileCov], repo_path: str) -> FileCov | None:
    """Match a repo-relative path to a report entry (absolute or relative)."""
    norm = repo_path.replace("\\", "/")
    best = None
    for name, fc in report.items():
        n = name.replace("\\", "/")
        if n == norm or n.endswith("/" + norm) or norm.endswith("/" + n):
            if best is None or len(n) < len(best[0]):
                best = (n, fc)
    return best[1] if best else None


def pct(hit: int, total: int) -> float | None:
    return None if total == 0 else 100.0 * hit / total


def fmt(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.2f}%"


def global_metrics(report: dict[str, FileCov], include: list[str], exclude: list[str]) -> dict:
    lh = lt = bh = bt = fh = ft = 0
    for name, fc in report.items():
        if include and not file_matches(name, include):
            continue
        if exclude and file_matches(name, exclude):
            continue
        lt += len(fc.lines)
        lh += sum(1 for h in fc.lines.values() if h > 0)
        for takens in fc.branches.values():
            bt += len(takens)
            bh += sum(takens)
        ft += fc.fn_total
        fh += fc.fn_hit
    return {"lines": pct(lh, lt), "branches": pct(bh, bt), "functions": pct(fh, ft),
            "_counts": {"lines": [lh, lt], "branches": [bh, bt], "functions": [fh, ft]}}


# ---------------------------------------------------------------- main

def resolve_baseline_conflict(path: str) -> int:
    sides = []
    for stage in (2, 3):
        res = subprocess.run(["git", "show", f":{stage}:{path}"], capture_output=True, text=True)
        if res.returncode != 0:
            print(f"{path} is not in conflict (no stage {stage})", file=sys.stderr)
            return 2
        sides.append(json.loads(res.stdout))
    merged = {k: max(s.get(k, 0) for s in sides if isinstance(s.get(k, 0), (int, float)))
              for k in set(sides[0]) | set(sides[1])}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(merged, fh, indent=2, sort_keys=True)
        fh.write("\n")
    subprocess.run(["git", "add", path], check=True)
    print(f"{path}: resolved to the higher value per metric: {json.dumps(merged, sort_keys=True)}")
    return 0


def main() -> int:
    if "--resolve-baseline-conflict" in sys.argv:
        bp = argparse.ArgumentParser()
        bp.add_argument("--resolve-baseline-conflict", action="store_true")
        bp.add_argument("--baseline", default=".coverage-baseline.json")
        return resolve_baseline_conflict(bp.parse_args().baseline)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", required=True, help="lcov .info or Cobertura XML")
    ap.add_argument("--base", required=True, help="base ref, e.g. origin/main or origin/epic/foo")
    ap.add_argument("--baseline", default=".coverage-baseline.json", help="committed ratchet file")
    ap.add_argument("--diff-min", type=float, default=95.0)
    ap.add_argument("--target", type=float, default=95.0, help="global target the ratchet climbs to")
    ap.add_argument("--include", action="append", default=[], help="source glob (repeatable)")
    ap.add_argument("--exclude", action="append", default=[], help="glob to ignore (repeatable)")
    ap.add_argument("--update-baseline", action="store_true", help="raise the baseline to current values")
    ap.add_argument("--json", action="store_true", help="print the result as JSON instead of markdown")
    args = ap.parse_args()

    report = load_report(args.report)
    if not report:
        print(f"coverage report {args.report} is empty", file=sys.stderr)
        return 2

    # ---- diff coverage
    diff = changed_lines(args.base)
    d_lh = d_lt = d_bh = d_bt = 0
    uncovered: list[str] = []
    missing_files: list[str] = []
    for path, lines in sorted(diff.items()):
        if args.include and not matches(path, args.include):
            continue
        if args.exclude and matches(path, args.exclude):
            continue
        fc = resolve(report, path)
        if fc is None:
            if args.include:  # a source file the tests never loaded
                missing_files.append(path)
                d_lt += len(lines)
                uncovered.append(f"{path}: not in the report (no test loads it)")
            continue
        miss = []
        for ln in sorted(lines):
            if ln in fc.lines:
                d_lt += 1
                if fc.lines[ln] > 0:
                    d_lh += 1
                else:
                    miss.append(ln)
            if ln in fc.branches:
                takens = fc.branches[ln]
                d_bt += len(takens)
                d_bh += sum(takens)
                if not all(takens) and ln not in miss:
                    miss.append(ln)
        if miss:
            uncovered.append(f"{path}: lines {compress(sorted(set(miss)))}")
    diff_lines, diff_branches = pct(d_lh, d_lt), pct(d_bh, d_bt)

    # ---- global + ratchet
    glob = global_metrics(report, args.include, args.exclude)
    baseline = {}
    if os.path.isfile(args.baseline):
        with open(args.baseline, encoding="utf-8") as fh:
            baseline = json.load(fh)

    failures: list[str] = []
    if diff_lines is not None and diff_lines + TOLERANCE < args.diff_min:
        failures.append(f"diff lines {fmt(diff_lines)} < {args.diff_min}%")
    if diff_branches is not None and diff_branches + TOLERANCE < args.diff_min:
        failures.append(f"diff branches {fmt(diff_branches)} < {args.diff_min}%")

    rows = []
    for metric in ("lines", "branches", "functions"):
        cur = glob[metric]
        base_v = baseline.get(metric)
        if cur is None:
            rows.append((metric, "n/a", fmt(base_v), "n/a"))
            continue
        floor = args.target if (base_v is not None and base_v >= args.target) else base_v
        if floor is not None and cur + TOLERANCE < floor:
            failures.append(f"global {metric} {fmt(cur)} dropped below {fmt(floor)}")
            state = "DROPPED"
        elif cur + TOLERANCE >= args.target:
            state = "at target"
        else:
            state = f"ratchet, {args.target - cur:.2f} pts to target"
        rows.append((metric, fmt(cur), fmt(base_v), state))

    if args.update_baseline and not failures:
        new = dict(baseline)
        for metric in ("lines", "branches", "functions"):
            cur = glob[metric]
            if cur is not None and (new.get(metric) is None or cur > new[metric]):
                new[metric] = round(cur, 2)
        new["target"] = args.target
        with open(args.baseline, "w", encoding="utf-8") as fh:
            json.dump(new, fh, indent=2, sort_keys=True)
            fh.write("\n")

    verdict = "PASS" if not failures else "FAIL"
    if args.json:
        print(json.dumps({
            "verdict": verdict, "failures": failures,
            "diff": {"lines": diff_lines, "branches": diff_branches,
                     "counts": {"lines": [d_lh, d_lt], "branches": [d_bh, d_bt]}},
            "global": {k: glob[k] for k in ("lines", "branches", "functions")},
            "baseline": baseline, "uncovered": uncovered, "missing_files": missing_files,
        }, indent=2))
    else:
        print(f"## Coverage gate: **{verdict}**\n")
        print(f"Base `{args.base}` · report `{args.report}` · diff min {args.diff_min}% · target {args.target}%\n")
        print("| Scope | Covered | Threshold |")
        print("| --- | --- | --- |")
        print(f"| Diff lines | {fmt(diff_lines)} ({d_lh}/{d_lt}) | >= {args.diff_min}% |")
        print(f"| Diff branches | {fmt(diff_branches)} ({d_bh}/{d_bt}) | >= {args.diff_min}% |")
        print("\n| Global | Now | Baseline | State |")
        print("| --- | --- | --- | --- |")
        for r in rows:
            print(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} |")
        if uncovered:
            print("\n**Uncovered changed code:**")
            for u in uncovered:
                print(f"- {u}")
        if failures:
            print("\n**Fails:** " + "; ".join(failures))
        if args.update_baseline and not failures:
            print(f"\nBaseline `{args.baseline}` raised to current values.")
    return 0 if not failures else 1


def compress(nums: list[int]) -> str:
    out, start, prev = [], None, None
    for n in nums:
        if start is None:
            start = prev = n
        elif n == prev + 1:
            prev = n
        else:
            out.append(f"{start}" if start == prev else f"{start}-{prev}")
            start = prev = n
    if start is not None:
        out.append(f"{start}" if start == prev else f"{start}-{prev}")
    return ", ".join(out)


if __name__ == "__main__":
    sys.exit(main())

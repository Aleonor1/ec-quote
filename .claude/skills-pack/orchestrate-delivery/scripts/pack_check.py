#!/usr/bin/env python3
"""pack_check.py: is the pack installed in a project the same as this pack,
and does the project's binding have what this pack's template asks for?

Compares a target project's installed copy of the skills pack with the pack
it is run from, and changes nothing:

  1. Version: <target>/.claude/skills-pack/VERSION against <pack>/VERSION.
     No VERSION file in the target means it was installed before 2.0.

  2. Files, by content (bytes, never mtimes: the installer rewrites every
     file). For each pack skill the project has installed, <pack>/skills/<name>/
     against <target>/.claude/skills/<name>/; and <pack>/orchestrate-delivery/
     against <target>/.claude/skills-pack/orchestrate-delivery/. A pack file
     whose installed copy differs is "changed", one the target lacks is
     "missing", and a file only the target has is "extra" (listed, never a
     failure). A project's own skills and the binding are not compared here.
     Caches and run notes (__pycache__, *.pyc, .run-notes, node_modules,
     .DS_Store) are ignored on both sides.

  3. Binding: <target>/.claude/skills-pack/bindings/PROJECT.md against
     <pack>/bindings/PROJECT.md.template. Listed, never edited:
     - "missing section: <heading>": a ## or ### heading the template has and
       the binding does not.
     - "missing row: <section> → <label>": a table row label (the first cell)
       the template has under a section and the binding does not have under
       that section, the rows of a missing section included. Header rows
       count; separator rows, empty labels (the | | | header), and template
       example rows whose label is itself backticked or a <placeholder>
       (Documentation's `<name>`) do not.
     - "unfilled: <section> → <label>": a table row of the binding whose value
       is unfilled: it has at least one backticked span that is only a
       placeholder (starts with < and ends with >: one <...>, <a | b>
       alternatives, <owner>/<name>) and no backticked span with filled
       content. Plain text outside backticks counts neither way, so a
       documented literal such as `local_pr.py view <N>` is filled.
     - "unfilled: <section>": a prose line of a section (outside tables and
       fenced code) that is unfilled by the same rule; listed once per
       section. In JSON it is the bare section name, with no " → <label>".
     Headings and labels match ignoring case, surrounding whitespace, and one
     trailing parenthesised note ("Spec authoring (create-spec)" matches
     "Spec authoring"). Text before the first ## heading and inside ``` or ~~~
     fences is not read. A binding file that does not exist is "missing".

Paths in the output use / and are relative to the target's .claude/.

  pack_check.py --pack <pack root> --target <project root> [--json]
  install.sh --check <project root> [--json]      (the same, pack = install.sh's folder)

Exit 0 when the version and every file are current and the binding is
complete, 1 when something needs a re-install or the binding lacks something,
2 on a usage error, when the pack is not installed in the target, or when a
file or folder (the binding and the template included) cannot be read (a
read error is never reported as drift).

"Re-install due" (the version is not current, a file changed or is missing,
or the binding is missing) is computed once, in check(), and kept in the
report as "reinstall"; render() reads it for its "Next: re-run install.sh"
line. It is internal: --json prints only version, files, binding, and exit.
Standard library only.
"""
from __future__ import annotations

import argparse
import filecmp
import json
import os
import re
import sys
from pathlib import Path

USAGE = "usage: pack_check.py --pack <pack root> --target <project root> [--json]"
IGNORED_DIRS = {"__pycache__", ".run-notes", "node_modules"}
IGNORED_FILES = {".DS_Store"}
BINDING_SHOWN = "skills-pack/bindings/PROJECT.md"
ARROW = " → "
HEADING = re.compile(r"^(#{2,3})\s+(.*?)\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")
ROW = re.compile(r"^\s*\|([^|]*)\|(.*)$")
SEPARATOR = re.compile(r"^:?-+:?$")
SPAN = re.compile(r"`([^`\n]+)`")
NOTE = re.compile(r"^(.+?)\s*\([^()]*\)$")
JSON_KEYS = ("version", "files", "binding", "exit")  # the report's "reinstall" is for render() only


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise OSError(f"{path}: not UTF-8 text") from exc


def read_version(path: Path) -> str | None:
    if not path.is_file():
        return None
    return read_text(path).strip()


def _raise(err: OSError) -> None:
    raise err


def files_under(root: Path) -> set[str]:
    """Every file below root, as a /-separated path relative to root.

    An absent root has no files; a folder that cannot be listed raises.
    """
    found: set[str] = set()
    if not root.is_dir():
        return found
    for dirpath, dirnames, filenames in os.walk(root, onerror=_raise):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS]
        for name in filenames:
            if name in IGNORED_FILES or name.endswith(".pyc"):
                continue
            found.add(Path(dirpath, name).relative_to(root).as_posix())
    return found


def same_content(a: Path, b: Path) -> bool:
    """Byte-equal, or equal once CRLF line endings are read as LF.

    A project that keeps CRLF files (a Windows checkout, core.autocrlf) holds the
    pack's text unchanged; only a real change of content is drift.
    """
    if filecmp.cmp(a, b, shallow=False):
        return True
    return a.read_bytes().replace(b"\r\n", b"\n") == b.read_bytes().replace(b"\r\n", b"\n")


def compare_tree(pack_dir: Path, installed_dir: Path, label: str, result: dict) -> None:
    """Add the changed, missing, extra, and matched files of one tree to result."""
    ours = files_under(pack_dir)
    theirs = files_under(installed_dir)
    for rel in sorted(ours | theirs):
        shown = f"{label}/{rel}"
        if rel not in theirs:
            result["missing"].append(shown)
        elif rel not in ours:
            result["extra"].append(shown)
        elif same_content(pack_dir / rel, installed_dir / rel):
            result["matched"] += 1
        else:
            result["changed"].append(shown)


def norm(text: str) -> str:
    """Matching key of a heading or label: trimmed, one trailing (note) dropped, lower case."""
    text = text.strip()
    m = NOTE.match(text)
    return (m.group(1) if m else text).strip().lower()


def is_placeholder(span: str) -> bool:
    span = span.strip()
    return span.startswith("<") and span.endswith(">")


def unfilled_text(text: str) -> bool:
    """At least one pure-placeholder backticked span, and no filled one."""
    spans = SPAN.findall(text)
    return bool(spans) and all(is_placeholder(s) for s in spans)


def parse_binding(text: str) -> dict:
    """The sections, table rows, and unfilled values of a binding or template.

    sections: {key: heading as written}. rows: {(section key, label key):
    (heading, label)}, in file order. unfilled: shown names, in file order.
    The label is the first cell; the value is the rest of the row, so a | inside
    a backticked value never shifts a cell.
    """
    sections: dict = {}
    rows: dict = {}
    unfilled: list = []
    section = None
    fenced = False
    for line in text.splitlines():
        if FENCE.match(line):
            fenced = not fenced
            continue
        h = None if fenced else HEADING.match(line)
        if h:
            section = h.group(2)
            sections.setdefault(norm(section), section)
            continue
        if fenced or section is None:
            continue
        r = ROW.match(line)
        if r is None:
            if unfilled_text(line) and section not in unfilled:
                unfilled.append(section)
            continue
        label = r.group(1).strip()
        if not label or SEPARATOR.match(label):
            continue
        rows.setdefault((norm(section), norm(label)), (section, label))
        if unfilled_text(r.group(2)):
            unfilled.append(f"{section}{ARROW}{label}")
    return {"sections": sections, "rows": rows, "unfilled": unfilled}


def compare_binding(template: Path, binding: Path) -> dict:
    tpl = parse_binding(read_text(template))
    result: dict = {"state": "missing", "missing_sections": [], "missing_rows": [], "unfilled": []}
    if not binding.exists():
        return result
    ours = parse_binding(read_text(binding))
    result["missing_sections"] = [shown for key, shown in tpl["sections"].items() if key not in ours["sections"]]
    result["missing_rows"] = [f"{section}{ARROW}{label}" for key, (section, label) in tpl["rows"].items()
                              if key not in ours["rows"] and not label.startswith(("`", "<"))]
    result["unfilled"] = ours["unfilled"]
    lacking = result["missing_sections"] or result["missing_rows"] or result["unfilled"]
    result["state"] = "incomplete" if lacking else "complete"
    return result


def check(pack: Path, target: Path) -> dict:
    claude = target / ".claude"
    pack_version = read_version(pack / "VERSION")
    installed = read_version(claude / "skills-pack" / "VERSION")
    if installed is None:
        state = "unknown"
    elif installed == pack_version:
        state = "current"
    else:
        state = "outdated"

    files: dict = {"changed": [], "missing": [], "extra": [], "matched": 0}
    skills_dir = claude / "skills"
    installed_skills = {p.name for p in skills_dir.iterdir() if p.is_dir()} if skills_dir.is_dir() else set()
    for skill in sorted(p.name for p in (pack / "skills").iterdir() if p.is_dir()):
        if skill in installed_skills:
            compare_tree(pack / "skills" / skill, skills_dir / skill, f"skills/{skill}", files)
    compare_tree(pack / "orchestrate-delivery", claude / "skills-pack" / "orchestrate-delivery",
                 "skills-pack/orchestrate-delivery", files)
    for key in ("changed", "missing", "extra"):
        files[key].sort()

    binding = compare_binding(pack / "bindings" / "PROJECT.md.template",
                              claude / "skills-pack" / "bindings" / "PROJECT.md")

    # re-install due: install.sh would change something, the binding it lays down included
    reinstall = bool(state != "current" or files["changed"] or files["missing"] or binding["state"] == "missing")
    return {"version": {"installed": installed, "pack": pack_version, "state": state},
            "files": files, "binding": binding,
            "exit": 1 if reinstall or binding["state"] != "complete" else 0,
            "reinstall": reinstall}


def render_binding(b: dict) -> list[str]:
    if b["state"] == "missing":
        return [f"Binding: missing ({BINDING_SHOWN})"]
    if b["state"] == "complete":
        return ["Binding: complete"]
    lines = [f"Binding: incomplete ({len(b['missing_sections'])} missing sections, "
             f"{len(b['missing_rows'])} missing rows, {len(b['unfilled'])} unfilled)"]
    lines.extend(f"- missing section: {x}" for x in b["missing_sections"])
    lines.extend(f"- missing row: {x}" for x in b["missing_rows"])
    lines.extend(f"- unfilled: {x}" for x in b["unfilled"])
    return lines


def render(report: dict, target: Path) -> str:
    v, f, b = report["version"], report["files"], report["binding"]
    lines = [f"# Pack check: {target}", ""]
    if v["state"] == "unknown":
        lines.append(f"Version: unknown (pack {v['pack']}), installed before 2.0")
    else:
        lines.append(f"Version: {v['installed']} (pack {v['pack']}), {v['state']}")
    if not f["changed"] and not f["missing"]:
        lines.append(f"Files: all {f['matched']} installed files match the pack")
    else:
        lines.append(f"Files: {len(f['changed'])} changed, {len(f['missing'])} missing, "
                     f"{f['matched']} match the pack")
    for key in ("changed", "missing", "extra"):
        lines.extend(f"- {key}: {path}" for path in f[key])
    lines.extend(render_binding(b))
    lines.append("")
    if report["reinstall"]:
        lines.append(f"Next: re-run install.sh {target}")
    if b["state"] == "missing":
        lines.append(f"Next: then run /onboard-project in {target} to fill the binding it lays down")
    elif b["state"] == "incomplete":
        lines.append(f"Next: run /onboard-project refresh in {target}; it fills exactly the binding lines above")
    if not report["exit"]:
        lines.append("Result: current, binding complete")
    return "\n".join(lines)


def use_utf8_stdout() -> None:
    """The report has arrows and dashes; a Windows console defaults to cp1252 and would crash on them."""
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None and (sys.stdout.encoding or "").lower().replace("-", "") != "utf8":
        reconfigure(encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(prog="pack_check.py", usage=USAGE[len("usage: "):],
                                 description="Version, file, and binding drift of an installed skills pack. "
                                             "Read-only.")
    ap.add_argument("--pack", required=True, help="the pack root (the folder install.sh is in)")
    ap.add_argument("--target", required=True, help="the project root the pack was installed into")
    ap.add_argument("--json", action="store_true", help="print one JSON object instead of Markdown")
    args = ap.parse_args()

    pack, target = Path(args.pack).resolve(), Path(args.target).resolve()
    if not (pack / "VERSION").is_file() or not (pack / "skills").is_dir():
        print(f"{USAGE}\nnot a pack: {args.pack} (no VERSION or skills/)", file=sys.stderr)
        return 2
    if not target.is_dir():
        print(f"{USAGE}\nno such directory: {args.target}", file=sys.stderr)
        return 2
    if not (target / ".claude" / "skills-pack").is_dir():
        print(f"pack not installed in {target}: run install.sh {target}", file=sys.stderr)
        return 2

    try:
        report = check(pack, target)
    except OSError as exc:
        print(f"cannot read: {exc}", file=sys.stderr)
        return 2
    shown = {key: report[key] for key in JSON_KEYS}
    use_utf8_stdout()
    print(json.dumps(shown, indent=2, ensure_ascii=False) if args.json else render(report, target))
    return report["exit"]


if __name__ == "__main__":
    sys.exit(main())

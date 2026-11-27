#!/usr/bin/env python3
"""detect.py: read a repository and propose a value for each binding field.

Run from the target repository root:

    python3 .claude/skills/onboard-project/detect.py            # JSON on stdout
    python3 .claude/skills/onboard-project/detect.py --markdown # table for humans

Every proposal carries where it came from and how sure it is:

    detected   read from a file or git (e.g. a script in package.json, a CI step)
    inferred   derived from conventions (e.g. Vite serves on 5173)
    default    the pack's default; fine unless the project differs

Nothing is written and nothing is executed except read-only git commands.
The onboard-project skill verifies the commands by running them.
Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path.cwd()
SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", ".nuxt", "out", "coverage",
             ".venv", "venv", "__pycache__", ".turbo", ".cache", "vendor", "target", ".claude",
             "playwright-report", "test-results", ".pytest_cache", ".mypy_cache"}

findings: dict[str, dict] = {}
raw: dict[str, object] = {}


RANK = {"detected": 3, "inferred": 2, "default": 1}


def put(field: str, value, source: str, confidence: str = "detected", note: str | None = None, ci: bool = False):
    """Record a proposal. Higher confidence wins; at equal confidence the first wins,
    except that a CI step beats a config file: CI is what actually runs."""
    prio = RANK[confidence] + (0.5 if ci else 0)
    cur = findings.get(field)
    if cur and cur.get("priority", RANK[cur["confidence"]]) >= prio:
        cur.setdefault("alternatives", []).append({"value": value, "source": source})
        return
    entry = {"value": value, "source": source, "confidence": confidence, "priority": prio}
    if note:
        entry["note"] = note
    if cur:
        entry["alternatives"] = [{"value": cur["value"], "source": cur["source"]}] + cur.get("alternatives", [])
    findings[field] = entry


def git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                              timeout=20).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def read(path: Path, limit: int = 200_000) -> str:
    try:
        if path.stat().st_size > limit:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def walk(max_depth: int = 4):
    for dirpath, dirnames, filenames in os.walk(ROOT):
        rel = Path(dirpath).relative_to(ROOT)
        depth = len(rel.parts)
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not (d.startswith(".") and d not in {".github", ".gitlab"})]
        if depth >= max_depth:
            dirnames[:] = []
        yield rel, dirnames, filenames


def clean(rel: str) -> str:
    """'./cov/' -> 'cov': a repo-relative path as the binding writes it."""
    rel = rel.strip().rstrip("/")
    while rel.startswith("./"):
        rel = rel[2:]
    return rel


def exists(*paths: str) -> str | None:
    for p in paths:
        if (ROOT / p).exists():
            return p
    return None


# ------------------------------------------------------------------ identity

def detect_identity():
    url = git("remote", "get-url", "origin")
    raw["remote"] = url
    m = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?$", url)
    if m:
        put("Identity.Repository", f"{m.group(1)}/{m.group(2)}", "git remote origin")
    host = "github" if "github.com" in url else "gitlab" if "gitlab" in url else "other" if url else "none"
    raw["host"] = host

    head = git("symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if head:
        put("Identity.Base branch", head.split("/", 1)[-1], "origin/HEAD")
    else:
        for b in ("main", "master", "develop"):
            if git("rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{b}") or git("rev-parse", "--verify", "--quiet", b):
                put("Identity.Base branch", b, f"branch {b} exists", "inferred")
                break
    name = git("config", "user.name")
    if name:
        put("Identity.Human", name, "git config user.name", "inferred")
    put("Identity.Kit root", ".claude/skills-pack", "installer default", "default")

    # ticket keys from branches, commit subjects, spec filenames
    keys = Counter()
    text = git("log", "-300", "--format=%s") + "\n" + git("branch", "-a", "--format=%(refname:short)")
    for k in re.findall(r"\b([A-Z][A-Z0-9]{1,9}-\d+)\b", text):
        keys[re.sub(r"\d+", "<N>", k)] += 1
    for k in re.findall(r"\b(story|issue|ticket|feat)[-_#](\d+)\b", text, re.I):
        keys[f"{k[0].lower()}-<N>"] += 1
    if keys:
        pattern, count = keys.most_common(1)[0]
        put("Identity.Ticket key pattern", pattern, f"{count} uses in recent commits/branches", "inferred")
    raw["ticket_key_candidates"] = keys.most_common(5)


# ------------------------------------------------------------------ node

PM_RUN = {"npm": "npm run", "pnpm": "pnpm", "yarn": "yarn", "bun": "bun run"}
PM_EXEC = {"npm": "npx", "pnpm": "pnpm exec", "yarn": "yarn", "bun": "bunx"}
SCRIPT_MAP = [
    ("Gates.Lint", ["lint", "eslint", "lint:all"]),
    ("Gates.Types", ["typecheck", "type-check", "types", "check-types", "tsc", "check"]),
    ("Gates.Unit", ["test:unit", "test", "unit", "vitest"]),
    ("Gates.Integration", ["test:integration", "test:int", "integration"]),
    ("Gates.End-to-end", ["test:e2e", "e2e", "playwright", "test:playwright"]),
    ("Coverage.Coverage command", ["test:coverage", "coverage", "test:cov", "cov"]),
    ("UI testing.Bring the stack up", ["dev", "start:dev", "start", "serve"]),
    ("UI testing.Seed", ["db:seed", "seed", "prisma:seed"]),
]


WATCH_RISKS = [
    (re.compile(r"\bvitest\b(?!.*\b(run|--run)\b)"), "vitest without `run` starts watch mode in a terminal; use `vitest run`"),
    (re.compile(r"--watch(All)?\b(?!=false)"), "watch mode never exits; drop --watch for gates"),
    (re.compile(r"\bng test\b(?!.*--watch=false)"), "ng test watches by default; add --watch=false --browsers=ChromeHeadless"),
    (re.compile(r"\breact-scripts test\b(?!.*--watchAll=false)"), "react-scripts test watches outside CI; add --watchAll=false"),
    (re.compile(r"prisma migrate dev\b"), "prisma migrate dev can prompt interactively; gates use prisma migrate deploy or db push --accept-data-loss on a test DB"),
    (re.compile(r"drizzle-kit push\b(?!.*--force)"), "drizzle-kit push can prompt; add --force for the throwaway test database"),
    (re.compile(r"playwright show-report"), "show-report starts a server that never exits"),
]


def hang_risks_of(command: str) -> list[str]:
    return [why for rx, why in WATCH_RISKS if rx.search(command)]


def detect_node():
    pkg_path = ROOT / "package.json"
    if not pkg_path.exists():
        return
    try:
        pkg = json.loads(read(pkg_path))
    except json.JSONDecodeError:
        return
    pm = "npm"
    src = "default (package.json, no lockfile)"
    for lock, name in (("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"), ("bun.lockb", "bun"),
                       ("bun.lock", "bun"), ("package-lock.json", "npm")):
        if (ROOT / lock).exists():
            pm, src = name, lock
            break
    if isinstance(pkg.get("packageManager"), str):
        pm, src = pkg["packageManager"].split("@")[0], "package.json packageManager"
    raw["node_pm"] = pm
    install = {"npm": "npm ci", "pnpm": "pnpm install --frozen-lockfile",
               "yarn": "yarn install --immutable" if (ROOT / ".yarnrc.yml").exists() else "yarn install --frozen-lockfile",
               "bun": "bun install --frozen-lockfile"}.get(pm, "npm ci")
    if pm == "npm" and not (ROOT / "package-lock.json").exists():
        install = "npm install"
    put("Gates.Install", install, src)

    scripts = pkg.get("scripts", {}) or {}
    raw["node_scripts"] = scripts
    deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
    raw["node_deps"] = sorted(deps)
    run = PM_RUN.get(pm, "npm run")
    for field, names in SCRIPT_MAP:
        for n in names:
            if n in scripts:
                put(field, f"{run} {n}", f"package.json scripts.{n} = {scripts[n]!r}")
                break
    for name, body in scripts.items():
        for risk in hang_risks_of(str(body)):
            raw.setdefault("hang_risks", []).append(f"package.json scripts.{name} ({body!r}): {risk}")

    ex = PM_EXEC.get(pm, "npx")
    if "typescript" in deps and "Gates.Types" not in findings:
        put("Gates.Types", f"{ex} tsc --noEmit", "typescript in devDependencies", "inferred")
    if "eslint" in deps and "Gates.Lint" not in findings:
        put("Gates.Lint", f"{ex} eslint .", "eslint in devDependencies", "inferred")

    # coverage command and report
    if "vitest" in deps:
        major = re.match(r"\D*(\d+)", str(deps["vitest"]))
        all_flag = " --coverage.all" if major and int(major.group(1)) < 2 else ""
        put("Coverage.Coverage command",
            f"{ex} vitest run --coverage --coverage.reporter=lcov --coverage.reporter=text-summary{all_flag}",
            f"vitest {deps['vitest']} in devDependencies", "inferred")
        put("Coverage.Report path", "coverage/lcov.info", "vitest default reportsDirectory", "inferred")
        if not any(d.startswith("@vitest/coverage-") for d in deps):
            raw.setdefault("setup_needed", []).append("add @vitest/coverage-v8 to devDependencies")
    elif "jest" in deps:
        put("Coverage.Coverage command",
            f"{ex} jest --coverage --coverageReporters=lcov --coverageReporters=text-summary",
            f"jest {deps['jest']} in devDependencies", "inferred")
        put("Coverage.Report path", "coverage/lcov.info", "jest default coverageDirectory", "inferred")
    elif "c8" in deps or "nyc" in deps:
        tool = "c8" if "c8" in deps else "nyc"
        put("Coverage.Report path", "coverage/lcov.info", f"{tool} default", "inferred")
    if "Coverage.Coverage command" in findings:
        put("Coverage.Full test command for the flake check", findings["Coverage.Coverage command"]["value"],
            "same as the coverage command, so one run gives both", "inferred")

    if "@playwright/test" in deps or "playwright" in deps:
        raw["playwright"] = True
        put("Gates.End-to-end", f"{ex} playwright test", "@playwright/test in devDependencies", "inferred")
    if "cypress" in deps:
        raw["cypress"] = True
    for fw, port in (("vite", 5173), ("next", 3000), ("nuxt", 3000), ("@sveltejs/kit", 5173),
                     ("react-scripts", 3000), ("@angular/core", 4200), ("astro", 4321), ("remix", 3000)):
        if fw in deps:
            port_m = None
            for s in scripts.values():
                port_m = port_m or re.search(r"(?:--port|-p)[ =](\d{2,5})", str(s))
            p = int(port_m.group(1)) if port_m else port
            raw.setdefault("notes", []).append(
                "the dev script runs in the foreground: the stack command must start it in the background "
                "and wait for the App URL, e.g. `(<dev command> > <notes>/stack.log 2>&1 &) && npx wait-on <App URL>`")
            put("UI testing.App URL", f"http://localhost:{p}",
                f"{fw} {'--port in scripts' if port_m else 'default port'}", "detected" if port_m else "inferred")
            break
    for orm, schema in (("prisma", "prisma/schema.prisma"), ("@prisma/client", "prisma/schema.prisma")):
        if orm in deps and (ROOT / schema).exists():
            put("Skills pack.Project overview.Schema file", schema, f"{orm} in dependencies")
    if "drizzle-orm" in deps:
        cfg = exists("drizzle.config.ts", "drizzle.config.js")
        if cfg:
            m = re.search(r"schema:\s*['\"]([^'\"]+)", read(ROOT / cfg))
            if m:
                put("Skills pack.Project overview.Schema file", m.group(1), cfg)

    ws = pkg.get("workspaces")
    if ws or (ROOT / "pnpm-workspace.yaml").exists():
        raw["monorepo"] = ws or read(ROOT / "pnpm-workspace.yaml")


def detect_vitest_jest_config():
    for name in ("vitest.config.ts", "vitest.config.js", "vitest.config.mts", "vite.config.ts", "vite.config.js"):
        text = read(ROOT / name)
        if "coverage" in text:
            raw["coverage_config"] = name
            m = re.search(r"reportsDirectory:\s*['\"]([^'\"]+)", text)
            if m:
                put("Coverage.Report path", f"{clean(m.group(1))}/lcov.info", f"{name} reportsDirectory")
            inc = re.search(r"include:\s*\[([^\]]+)\]", text[text.find("coverage"):])
            if inc:
                globs = re.findall(r"['\"]([^'\"]+)['\"]", inc.group(1))
                if globs:
                    put("Coverage.Source globs", ", ".join(globs), f"{name} coverage.include")
            exc = re.search(r"exclude:\s*\[([^\]]+)\]", text[text.find("coverage"):])
            if exc:
                globs = re.findall(r"['\"]([^'\"]+)['\"]", exc.group(1))
                if globs:
                    put("Coverage.Exclude globs", ", ".join(globs), f"{name} coverage.exclude")
            th = re.search(r"thresholds?:\s*\{([^}]+)\}", text)
            if th:
                raw["existing_thresholds"] = th.group(1).strip()
        m = re.search(r"server:\s*\{[^}]*port:\s*(\d+)", text)
        if m:
            put("UI testing.App URL", f"http://localhost:{m.group(1)}", f"{name} server.port")
    for name in ("jest.config.ts", "jest.config.js", "jest.config.cjs"):
        text = read(ROOT / name)
        m = re.search(r"coverageDirectory:\s*['\"]([^'\"]+)", text)
        if m:
            put("Coverage.Report path", f"{clean(m.group(1))}/lcov.info", f"{name} coverageDirectory")
        inc = re.search(r"collectCoverageFrom:\s*\[([^\]]+)\]", text)
        if inc:
            globs = [g for g in re.findall(r"['\"]([^'\"]+)['\"]", inc.group(1)) if not g.startswith("!")]
            if globs:
                put("Coverage.Source globs", ", ".join(globs), f"{name} collectCoverageFrom")


def detect_playwright():
    cfg = exists("playwright.config.ts", "playwright.config.js", "playwright.config.mjs", "e2e/playwright.config.ts")
    if not cfg:
        return
    raw["playwright_config"] = cfg
    text = read(ROOT / cfg)
    if not re.search(r"open:\s*['\"]never['\"]", text):
        raw.setdefault("hang_risks", []).append(
            f"{cfg}: the HTML reporter opens a report server after a failure and waits forever outside CI; "
            "set reporter: [['html', { open: 'never' }], ['list']]")
        raw.setdefault("setup_needed", []).append(f"{cfg}: reporter html with open: 'never'")
    if re.search(r"webServer", text) and not re.search(r"timeout:\s*\d", text[text.find("webServer"):]):
        raw.setdefault("hang_risks", []).append(f"{cfg}: webServer has no timeout; add timeout: 120_000")
    m = re.search(r"baseURL:\s*(?:process\.env\.\w+\s*(?:\?\?|\|\|)\s*)?['\"`]([^'\"`]+)", text)
    if m:
        put("UI testing.App URL", m.group(1), f"{cfg} use.baseURL")
    m = re.search(r"testDir:\s*['\"]([^'\"]+)", text)
    put("UI testing.End-to-end folder", (m.group(1).lstrip("./") if m else "tests") + "/",
        f"{cfg} testDir" if m else "Playwright default testDir", "detected" if m else "inferred")
    m = re.search(r"webServer:\s*\{[^}]*command:\s*['\"`]([^'\"`]+)", text, re.S)
    if m:
        put("UI testing.Bring the stack up", m.group(1), f"{cfg} webServer.command")
    projects = re.findall(r"name:\s*['\"](chromium|firefox|webkit|Mobile [^'\"]+)['\"]", text)
    if projects:
        put("UI testing.Browsers", ", ".join(sorted(set(projects))), f"{cfg} projects")


# ------------------------------------------------------------------ python / go / make / compose

def detect_python():
    py = read(ROOT / "pyproject.toml")
    req = exists("requirements-dev.txt", "requirements.txt")
    if not exists("pyproject.toml", "setup.py", "setup.cfg", "Pipfile", "Pipfile.lock", "poetry.lock", "uv.lock",
                  "pytest.ini", "tox.ini", "conftest.py", "tests/conftest.py") and not req:
        return
    raw["python"] = True
    if (ROOT / "uv.lock").exists():
        pm, inst, runp = "uv", "uv sync", "uv run "
    elif (ROOT / "poetry.lock").exists():
        pm, inst, runp = "poetry", "poetry install", "poetry run "
    elif (ROOT / "Pipfile.lock").exists():
        pm, inst, runp = "pipenv", "pipenv install --dev", "pipenv run "
    else:
        pm, inst, runp = "pip", f"pip install -r {req}" if req else "pip install -e '.[dev]'", ""
    put("Gates.Install", inst, f"{pm} lockfile/config", "detected" if pm != "pip" else "inferred")
    if "[tool.ruff" in py or exists("ruff.toml", ".ruff.toml"):
        put("Gates.Lint", f"{runp}ruff check .", "ruff config")
    elif exists(".flake8") or "flake8" in py:
        put("Gates.Lint", f"{runp}flake8", "flake8 config")
    if "[tool.mypy" in py or exists("mypy.ini"):
        put("Gates.Types", f"{runp}mypy .", "mypy config")
    elif "[tool.pyright" in py or exists("pyrightconfig.json"):
        put("Gates.Types", f"{runp}pyright", "pyright config")
    if "pytest" in py or req and "pytest" in read(ROOT / req) or exists("pytest.ini", "conftest.py", "tests/conftest.py"):
        put("Gates.Unit", f"{runp}pytest", "pytest config", "detected")
        pkg = None
        m = re.search(r'^\s*name\s*=\s*"([^"]+)"', py, re.M)
        cands = [m.group(1).replace("-", "_")] if m else []
        cands += [p.name for p in (ROOT / "src").glob("*") if (p / "__init__.py").exists()] if (ROOT / "src").is_dir() else []
        cands += [p.name for p in ROOT.glob("*") if p.is_dir() and (p / "__init__.py").exists() and p.name not in {"tests", "test"}]
        for c in cands:
            if (ROOT / c).is_dir() or (ROOT / "src" / c).is_dir():
                pkg = c
                break
        target = pkg or "."
        put("Coverage.Coverage command", f"{runp}pytest --cov={target} --cov-branch --cov-report=xml --cov-report=term",
            "pytest present; pytest-cov flags", "inferred")
        put("Coverage.Report path", "coverage.xml", "pytest-cov --cov-report=xml default", "inferred")
        put("Coverage.Full test command for the flake check", f"{runp}pytest", "pytest", "inferred")
        if pkg:
            base = f"src/{pkg}" if (ROOT / "src" / pkg).is_dir() else pkg
            put("Coverage.Source globs", f"{base}/**", f"package {pkg}", "inferred")
        if "pytest-cov" not in py and not (req and "pytest-cov" in read(ROOT / req)):
            raw.setdefault("setup_needed", []).append("add pytest-cov to dev dependencies")
    if exists("manage.py"):
        put("UI testing.App URL", "http://localhost:8000", "Django manage.py default port", "inferred")
        put("Skills pack.Project overview.Server entry point", "manage.py", "Django")


def detect_go():
    if not (ROOT / "go.mod").exists():
        return
    raw["go"] = True
    put("Gates.Install", "go mod download", "go.mod")
    put("Gates.Unit", "go test ./...", "go.mod", "inferred")
    put("Gates.Lint", "golangci-lint run" if exists(".golangci.yml", ".golangci.yaml") else "go vet ./...",
        ".golangci config" if exists(".golangci.yml", ".golangci.yaml") else "go vet", "inferred")
    put("Coverage.Coverage command",
        "go test ./... -covermode=atomic -coverprofile=coverage.out && gocover-cobertura < coverage.out > coverage.xml",
        "go: profile converted to Cobertura for the gate", "inferred")
    put("Coverage.Report path", "coverage.xml", "gocover-cobertura output", "inferred")
    raw.setdefault("setup_needed", []).append("go install github.com/boumenot/gocover-cobertura@latest")


def detect_make_and_compose():
    mk = read(ROOT / "Makefile")
    if mk:
        targets = set(re.findall(r"^([A-Za-z0-9_.-]+):", mk, re.M))
        raw["make_targets"] = sorted(targets)
        for field, names in (("Gates.Lint", ["lint"]), ("Gates.Types", ["typecheck", "types"]),
                             ("Gates.Unit", ["test", "unit"]), ("Gates.Integration", ["integration", "test-integration"]),
                             ("Gates.End-to-end", ["e2e", "test-e2e"]), ("Gates.Bring the stack up", ["up", "dev", "run"]),
                             ("UI testing.Seed", ["seed"])):
            for n in names:
                if n in targets:
                    put(field, f"make {n}", f"Makefile target {n}", "inferred")
                    break
    compose = exists("compose.yaml", "compose.yml", "docker-compose.yml", "docker-compose.yaml")
    if compose:
        text = read(ROOT / compose)
        services = re.findall(r"^\s{2}([A-Za-z0-9_-]+):\s*$", text, re.M)
        raw["compose"] = {"file": compose, "services": services}
        put("Gates.Bring the stack up", "docker compose up -d --wait", compose)
        put("Shared environment", f"Docker Compose stack in {compose} (services: {', '.join(services[:8])}); "
            "sessions on one machine share its ports", compose, "inferred")


def detect_ci():
    runs: list[str] = []
    wf = ROOT / ".github" / "workflows"
    if wf.is_dir():
        for f in sorted(wf.glob("*.y*ml")):
            text = read(f)
            for m in re.finditer(r"^[ \t]*(?:-[ \t]*)?run:[ \t]*(\|-?|>-?)?[ \t]*(.*)$", text, re.M):
                if m.group(1):
                    indent = None
                    block = []
                    for line in text[m.end():].splitlines()[1:]:
                        if not line.strip():
                            continue
                        ind = len(line) - len(line.lstrip())
                        indent = indent or ind
                        if ind < indent:
                            break
                        block.append(line.strip())
                    runs += [f"{f.name}: {b}" for b in block]
                elif m.group(2).strip():
                    runs.append(f"{f.name}: {m.group(2).strip()}")
        raw["ci_system"] = "github-actions"
        put("Coverage.CI job", ", ".join(f.name for f in sorted(wf.glob("*.y*ml"))) or "(None)",
            ".github/workflows", "inferred", note="confirm which workflow, or add templates/github-actions/quality-gate.yml")
    gl = read(ROOT / ".gitlab-ci.yml")
    if gl:
        raw["ci_system"] = "gitlab-ci"
        runs += [f".gitlab-ci.yml: {l.strip()[2:]}" for l in gl.splitlines() if l.strip().startswith("- ") and len(l) < 200]
    raw["ci_run_lines"] = runs[:80]
    # CI steps are strong evidence: promote the ones that match a gate
    for line in runs:
        cmd = line.split(": ", 1)[1]
        low = cmd.lower()
        if re.search(r"\b(npm ci|pnpm install|yarn install|uv sync|poetry install|pip install)", low):
            put("Gates.Install", cmd, f"CI step ({line.split(':')[0]})", ci=True)
        elif re.search(r"playwright test|test:e2e|cypress run", low):
            put("Gates.End-to-end", cmd, f"CI step ({line.split(':')[0]})", ci=True)
        elif re.search(r"--cov\b|--coverage\b|coverprofile", low):
            put("Coverage.Coverage command", cmd, f"CI step ({line.split(':')[0]})", ci=True)
            put("Gates.Unit", cmd, f"CI step ({line.split(':')[0]}), the coverage run is the unit run", "inferred", ci=True)
        elif re.search(r"\b(pytest|vitest run|jest|go test|npm test|pnpm test|yarn test|cargo test)\b", low):
            put("Gates.Unit", cmd, f"CI step ({line.split(':')[0]})", ci=True)
        elif re.search(r"\b(lint|eslint|ruff check|flake8|golangci)", low):
            put("Gates.Lint", cmd, f"CI step ({line.split(':')[0]})", ci=True)
        elif re.search(r"\b(tsc|typecheck|type-check|mypy|pyright)\b", low):
            put("Gates.Types", cmd, f"CI step ({line.split(':')[0]})", ci=True)


# ------------------------------------------------------------------ docs, specs, structure

def detect_docs_and_specs():
    docs = [p for p in ("README.md", "ARCHITECTURE.md", "CLAUDE.md", "AGENTS.md", "CONTRIBUTING.md", "CHANGELOG.md",
                        "PRODUCT.md", "PROJECT_STATUS.md", "docs") if (ROOT / p).exists()]
    raw["docs"] = docs
    rules = exists("CLAUDE.md", "AGENTS.md", "CONTRIBUTING.md", ".cursorrules")
    if rules:
        put("Skills pack.Spec authoring.Architecture rules doc", rules, "present at repo root")
    put("Skills pack.Project overview.Output document", "ARCHITECTURE.md",
        "present" if (ROOT / "ARCHITECTURE.md").exists() else "pack default", "detected" if (ROOT / "ARCHITECTURE.md").exists() else "default")
    related = [d for d in docs if d in ("PRODUCT.md", "PROJECT_STATUS.md", "CHANGELOG.md", "README.md")]
    if related:
        put("Skills pack.Project overview.Related docs to link", ", ".join(related), "present at repo root")
    if (ROOT / "CHANGELOG.md").exists():
        put("Repository.Release note", "CHANGELOG.md", "present at repo root", "inferred")

    spec_dir = None
    for cand in ("specs", "docs/specs", "stories", "docs/stories", "tickets", "spec"):
        if (ROOT / cand).is_dir():
            spec_dir = cand
            break
    if spec_dir:
        sub = [d.name for d in (ROOT / spec_dir).iterdir() if d.is_dir()]
        todo = next((d for d in sub if d in ("todo", "backlog", "open", "pending")), None)
        done = next((d for d in sub if d in ("done", "closed", "shipped", "archive")), None)
        put("Skills pack.Spec authoring.Spec folder (new specs)", f"{spec_dir}/{todo}/" if todo else f"{spec_dir}/", f"folder {spec_dir}")
        put("Skills pack.Spec authoring.Done folder", f"{spec_dir}/{done}/" if done else "(None)", f"folder {spec_dir}",
            "detected" if done else "inferred")
        files = [p for p in (ROOT / spec_dir).rglob("*.md")]
        names = Counter(re.sub(r"(<N>)-[^/]*\.md$", r"\1-<kebab-slug>.md", re.sub(r"\d+", "<N>", p.name)) for p in files)
        if names:
            pat = names.most_common(1)[0][0]
            put("Skills pack.Spec authoring.Spec filename pattern", pat, f"{len(files)} spec files")
            prefix = pat.split("<N>")[0]
            put("Identity.Ticket key pattern", f"{prefix}<N>", "spec filenames")
            put("Skills pack.Spec authoring.Next-id rule", f"highest {prefix}<N> across the spec and done folders + 1",
                "spec filenames", "inferred")
        fm = Counter()
        heads = Counter()
        for p in files[:30]:
            t = read(p)
            m = re.match(r"---\n(.*?)\n---", t, re.S)
            if m:
                fm.update(re.findall(r"^([A-Za-z_]+):", m.group(1), re.M))
            heads.update(re.findall(r"^## (.+)$", t, re.M))
        if fm:
            put("Skills pack.Spec authoring.Frontmatter fields", ", ".join(k for k, _ in fm.most_common(8)), "existing spec frontmatter")
        if heads and files:
            n = min(len(files), 30)
            always = [h for h, c in heads.most_common() if c >= 0.8 * n]
            optional = [h for h, c in heads.most_common() if 0.15 * n <= c < 0.8 * n]
            if always:
                put("Skills pack.Spec authoring.Always-present sections", ", ".join(always), "headings in >=80% of specs")
            if optional:
                put("Skills pack.Spec authoring.Optional layer sections", ", ".join(optional[:10]), "headings in some specs")
        put("Tracker", f"spec files on disk in {spec_dir}/", f"folder {spec_dir}", "inferred")
    else:
        put("Skills pack.Spec authoring.Spec folder (new specs)", "specs/todo/", "pack default", "default")
        put("Skills pack.Spec authoring.Done folder", "specs/done/", "pack default", "default")
        put("Skills pack.Spec authoring.Spec filename pattern", "story-<N>-<kebab-slug>.md", "pack default", "default")
        put("Identity.Ticket key pattern", "story-<N>", "pack default", "default")
        put("Tracker", "spec files on disk in specs/", "pack default (no tracker found)", "default")
    design = exists("docs/design", "design", "docs/rfcs", "rfcs")
    if "@sentry/node" in raw.get("node_deps", []) or any(d.startswith("@sentry/") for d in raw.get("node_deps", [])) \
            or "sentry" in read(ROOT / "pyproject.toml").lower() or (ROOT / "sentry.properties").exists():
        put("Skills pack.Bug fixing.Error sources", "Sentry (connect the Sentry connector so fix can read events)",
            "Sentry SDK in dependencies", "inferred")
    pm = exists("docs/postmortems", "postmortems", "docs/incidents")
    if pm:
        put("Skills pack.Bug fixing.Postmortem folder", f"{pm}/", "folder present")
    tags = [t for t in git("tag", "--sort=-creatordate").splitlines() if t][:5]
    raw["tags"] = tags
    if tags:
        fmt = re.sub(r"\d+(\.\d+)*", "<version>", tags[0])
        put("Skills pack.Release.Tag format", fmt, f"latest tag {tags[0]}")
        calver = re.search(r"(?<!\d)(19|20)\d\d[.-]\d{1,2}([.-]\d{1,2})?(?!\d)", tags[0])
        put("Skills pack.Release.Versioning", "calver" if calver else "semver" if re.search(r"\d+\.\d+\.\d+", tags[0]) else "(None)",
            f"latest tag {tags[0]}", "inferred")
    vfiles = [f for f in ("package.json", "pyproject.toml", "VERSION", "version.txt") if (ROOT / f).exists()]
    if vfiles:
        put("Skills pack.Release.Version files", ", ".join(vfiles), "files present", "inferred")
    if (ROOT / "CHANGELOG.md").exists():
        put("Skills pack.Release.Changelog", "CHANGELOG.md", "present at repo root")
    for plat, files, rb in (("Railway", ["railway.json", "railway.toml"], "railway redeploy of the previous deployment (dashboard)"),
                            ("Fly.io", ["fly.toml"], "fly releases + fly deploy --image <previous>"),
                            ("Vercel", ["vercel.json"], "vercel rollback"),
                            ("Netlify", ["netlify.toml"], "netlify: publish the previous deploy"),
                            ("Render", ["render.yaml"], "render: rollback to the previous deploy"),
                            ("Heroku", ["Procfile", "app.json"], "heroku releases:rollback")):
        hit = exists(*files)
        if hit:
            raw["deploy_platform"] = plat
            put("Skills pack.Release.Production deploy", f"{plat} (config {hit}); owner: the human; reserved",
                f"{hit} present", "inferred")
            put("Skills pack.Release.Rollback", rb, f"{plat} convention", "inferred")
            break
    for d in ("docs/retros", "retros"):
        if (ROOT / d).is_dir():
            put("Skills pack.Retro.Retro folder", f"{d}/", "folder present")
    put("Skills pack.Research and design.Design folder", f"{design}/" if design else "docs/design/",
        "folder present" if design else "pack default", "detected" if design else "default")


ENTRY = {
    "Skills pack.Project overview.Server entry point": ["server/src/index.ts", "server/src/main.ts", "backend/src/index.ts",
        "src/server.ts", "src/index.ts", "src/main.ts", "api/src/index.ts", "app/main.py", "main.py", "app.py",
        "src/main.py", "server.js", "index.js"],
    "Skills pack.Project overview.Client entry point": ["client/src/App.tsx", "frontend/src/App.tsx", "web/src/App.tsx",
        "src/App.tsx", "src/App.vue", "src/main.tsx", "app/layout.tsx", "src/app/layout.tsx", "pages/_app.tsx",
        "src/routes/+layout.svelte"],
    "Skills pack.Project overview.Schema file": ["prisma/schema.prisma", "server/prisma/schema.prisma", "server/src/db.ts",
        "src/db/schema.ts", "db/schema.rb", "schema.sql", "app/models.py", "models.py"],
    "Skills pack.Spec authoring.Startup env validation": ["server/src/env.ts", "src/env.ts", "src/config/env.ts",
        "env.mjs", "src/env.mjs", "app/config.py", "config/settings.py"],
}
LAYER_NAMES = {"routes", "controllers", "handlers", "services", "repositories", "repos", "models", "adapters",
               "integrations", "clients", "pages", "components", "hooks", "api", "layouts", "views", "stores",
               "lib", "jobs", "workers", "middleware"}


def detect_structure():
    for field, cands in ENTRY.items():
        hit = exists(*cands)
        if hit:
            put(field, hit, "file present", "inferred")
        elif field.endswith("Startup env validation") and (ROOT / ".env.example").exists():
            put(field, ".env.example (vars listed, no validator found)", ".env.example", "inferred")
    layers, adapters = [], None
    for rel, dirnames, _ in walk(4):
        for d in dirnames:
            if d in LAYER_NAMES:
                layers.append(str(rel / d))
            if d in ("adapters", "integrations") and not adapters:
                adapters = str(rel / d)
    if layers:
        put("Skills pack.Project overview.Layer folders to enumerate", ", ".join(sorted(layers)[:16]), "folders present", "inferred")
    put("Skills pack.Project overview.Adapters/integrations folder", adapters or "(None)",
        "folder present" if adapters else "none found", "inferred")
    if "Coverage.Source globs" not in findings:
        src = [d for d in ("src", "server/src", "client/src", "app", "lib", "backend", "frontend/src", "packages")
               if (ROOT / d).is_dir()]
        if src:
            put("Coverage.Source globs", ", ".join(f"{d}/**" for d in src), "source folders present", "inferred")
    if "Coverage.Exclude globs" not in findings:
        put("Coverage.Exclude globs", "**/*.test.*, **/*.spec.*, **/__tests__/**, **/*.d.ts, **/migrations/**, **/generated/**",
            "pack default", "default")
    not_owned = [p for p in ("terraform", "infra", "k8s", "helm", "deploy", ".github/workflows", "ansible") if (ROOT / p).exists()]
    put("Repository.Areas this human does not own", ", ".join(not_owned) if not_owned else "(None)",
        "infra folders present" if not_owned else "none found", "inferred",
        note="confirm: these are often owned by someone else")
    co = exists("CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS")
    if co:
        raw["codeowners"] = read(ROOT / co)[:2000]
    gen = [p for p in ("src/generated", "generated", "src/gql", "openapi") if (ROOT / p).exists()]
    put("Repository.Protected paths", ", ".join(gen) if gen else "(None)", "generated folders" if gen else "none found", "inferred")


def detect_roles_and_language():
    roles = Counter()
    scanned = 0
    pat = re.compile(r"""['"](admin|administrator|superadmin|owner|manager|staff|operator|editor|member|user|customer|client|viewer|guest)['"]""")
    for rel, _, files in walk(5):
        for f in files:
            if scanned > 3000:
                break
            if f.endswith((".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".rb", ".vue", ".svelte")) and "test" not in f:
                text = read(ROOT / rel / f, 120_000)
                scanned += 1
                if re.search(r"\brole", text, re.I):
                    roles.update(pat.findall(text))
    raw["role_candidates"] = roles.most_common(8)
    if roles:
        names = [r for r, c in roles.most_common(4) if c >= 2]
        if names:
            put("UI testing.Test accounts by role",
                ", ".join(f"{r}: E2E_{r.upper()}_EMAIL / E2E_{r.upper()}_PASSWORD" for r in names),
                f"role literals in source ({', '.join(f'{r}x{c}' for r, c in roles.most_common(4))})", "inferred",
                note="env var names only; the values go in .env.test or CI secrets, never in the binding")
    langs = set()
    for d in ("locales", "src/locales", "public/locales", "i18n", "src/i18n", "messages", "lang"):
        if (ROOT / d).is_dir():
            langs.update(p.stem.split(".")[0] for p in (ROOT / d).iterdir())
    html = read(ROOT / "index.html") + read(ROOT / "public/index.html")
    m = re.search(r'<html[^>]*lang="([a-zA-Z-]+)"', html)
    if m:
        langs.add(m.group(1))
    if langs:
        put("UI testing.Language", ", ".join(sorted(l for l in langs if 1 < len(l) <= 5)), "locale files / html lang", "inferred")


def defaults():
    host = raw.get("host")
    repo = findings.get("Identity.Repository", {}).get("value", "<owner>/<name>")
    if host == "github":
        put("Repository.Read a pull request", f"gh pr view <N> --repo {repo} --json headRefOid,reviews,statusCheckRollup,mergeable ; gh api repos/{repo}/pulls/<N>/comments",
            "GitHub remote", "default")
        put("Repository.Open a pull request", f"gh pr create --repo {repo} --base <base> --title ... --body-file ...", "GitHub remote", "default")
        put("Repository.Post a comment review", f"gh pr review <N> --repo {repo} --comment --body-file <file>", "GitHub remote", "default")
        put("Epic delivery.Merge a story into the epic branch", f"gh pr merge <N> --merge --repo {repo}", "GitHub remote", "default")
    if host == "github":
        try:
            ok = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True, timeout=15).returncode == 0
        except (OSError, subprocess.SubprocessError):
            ok = False
        raw["gh_authenticated"] = ok
        put("Repository.Host", "github" if ok else "local",
            "gh auth status ok" if ok else "GitHub remote, but gh is not authenticated here: local pull requests until it is",
            "detected" if ok else "inferred")
    if host in ("none", "other") or (host == "github" and not raw.get("gh_authenticated")):
        lp = "python3 .claude/skills-pack/orchestrate-delivery/scripts/local_pr.py"
        for f, v in (("Repository.Read a pull request", f"{lp} view <N> --json"),
                     ("Repository.Open a pull request", f"{lp} open --base <base> --head <branch> --title ... --body-file ..."),
                     ("Repository.Post a comment review", f"{lp} review <N> --role <role> --verdict <PASS|REVISE|BLOCK> --body-file <file>"),
                     ("Repository.Reply to and resolve a review thread", f"{lp} reply <N> --thread <id> --body-file <file> ; {lp} resolve <N> --thread <id>"),
                     ("Epic delivery.Merge a story into the epic branch", f"{lp} merge <N>")):
            put(f, v, "local pull requests", "inferred")
        if host in ("none", "other"):
            put("Repository.Host", "local", "no GitHub/GitLab remote", "inferred")
    elif host == "gitlab":
        put("Repository.Open a pull request", "glab mr create --target-branch <base> --title ... --description ...", "GitLab remote", "default")
        put("Epic delivery.Merge a story into the epic branch", "glab mr merge <N>", "GitLab remote", "default")
    for f, v in (("Coverage.Diff minimum", "95"), ("Coverage.Global target", "95"),
                 ("Coverage.Baseline file", ".coverage-baseline.json"), ("Coverage.Runs", "2"),
                 ("UI testing.Run for", "tickets with a UI section"),
                 ("UI testing.Playwright install", "npx playwright install --with-deps chromium"),
                 ("UI testing.Browsers", "chromium"), ("UI testing.Viewports", "1440x900, 390x844"),
                 ("UI testing.Browser mode", "headless"), ("UI testing.Login URL", "auto"),
                 ("Gates.Gate timeout", "unit 15m, integration 20m, end-to-end 30m, idle 10m"),
                 ("Gates.How gates run", "python3 .claude/skills-pack/orchestrate-delivery/scripts/run_gate.py --timeout <s> --tail 40 -- <command>"),
                 ("Gates.Output tail", "40"),
                 ("UI testing.Accessibility", "axe: serious and critical are findings"),
                 ("UI testing.End-to-end folder", "e2e/"),
                 ("UI testing.Evidence folder", ".claude/skills-pack/.run-notes/evidence"),
                 ("Sessions.Notes folder", ".claude/skills-pack/.run-notes"),
                 ("Sessions.Profile", "claude-code-agents"), ("Sessions.Peer messaging", "hub and spoke (handoff blocks relayed by the coordinator)"),
                 ("Sessions.Start refusal", "None"),
                 ("Epic delivery.Epic branch prefix", "epic/"),
                 ("Epic delivery.Story state after merging into the epic", "Done"),
                 ("Epic delivery.Max review rounds per story", "5"),
                 ("Epic delivery.Budget: sessions", "40"), ("Epic delivery.Budget: hours", "24"),
                 ("Epic delivery.Budget: fix stories", "5"),
                 ("Epic delivery.Budget: tokens", "600000"), ("Epic delivery.Tokens per session estimate", "40000"),
                 ("Epic delivery.Max parallel stories", "4"), ("Epic delivery.Early start", "on dependency PR open"),
                 ("Epic delivery.Fast track", "LOW, SMALL"),
                 ("Epic delivery.Epic ticket", "the design document is the epic"),
                 ("Models.Large", "opus"), ("Models.Standard", "sonnet"), ("Models.Small", "haiku"),
                 ("Models.Implementer", "standard"), ("Models.QA", "standard"), ("Models.UI test", "small"),
                 ("Models.Code review", "standard"), ("Models.Epic review", "large"), ("Models.Epic UI test", "standard"),
                 ("Models.Fixed", "(None)"),
                 ("Skills pack.Research and design.Epic key pattern", "EPIC-<N>; next id = highest across the design folder + 1"),
                 ("Skills pack.Research and design.Cost ceiling", "0 EUR (every paid service asks)"),
                 ("Skills pack.Research and design.Autonomy limits", "(None)"),
                 ("Skills pack.Spec authoring.Effort values", "LOW | SMALL | MEDIUM | HIGH | LARGE"),
                 ("Skills pack.Bug fixing.Severity scale", "P0 data loss, security, money, outage · P1 core journey broken, no workaround · P2 broken with workaround or few users · P3 cosmetic"),
                 ("Skills pack.Bug fixing.Postmortem folder", "docs/postmortems/"),
                 ("Skills pack.Bug fixing.Error sources", "(None)"),
                 ("Skills pack.Release.Versioning", "semver"), ("Skills pack.Release.Tag format", "v<version>"),
                 ("Skills pack.Release.Tagging", "the human tags"), ("Skills pack.Release.Changelog", "CHANGELOG.md"),
                 ("Skills pack.Release.Staging deploy", "reserved"), ("Skills pack.Release.Production deploy", "the human deploys; reserved"),
                 ("Skills pack.Release.End-to-end safe against staging", "no"),
                 ("Skills pack.Security.Scanners", "install in a scratch folder"), ("Skills pack.Security.Audit cadence", "before each release"),
                 ("Skills pack.Retro.Retro folder", "docs/retros/"), ("Skills pack.Retro.Metrics to track", "default"),
                 ("Skills pack.Spec authoring.Always-present sections", "Summary, User Story, Scope, Acceptance Criteria"),
                 ("Skills pack.Spec authoring.Optional layer sections", "Database Schema, API Design, Technical Notes, UI Notes, Dependencies, Hand-over"),
                 ("Skills pack.Spec authoring.Frontmatter fields", "id, title, effort, epic, depends_on, shared_files, track, models"),
                 ("Skills pack.Spec authoring.Next-id rule", "highest story-<N> across both folders + 1")):
        put(f, v, "pack default", "default")
    install = findings.get("Gates.Install", {}).get("value", "")
    if (ROOT / "package.json").exists():
        lock = next((n for n in ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb") if (ROOT / n).exists()), "package-lock.json")
        put("Sessions.Worktree bootstrap",
            f"[ -e node_modules ] || ln -s \"$(git rev-parse --path-format=absolute --git-common-dir)/../node_modules\" node_modules; "
            f"git diff --quiet origin/<base> -- {lock} || {install or 'npm ci'}",
            "package.json: share the main checkout's node_modules, reinstall only when the lockfile changed", "default")
    elif (ROOT / "pyproject.toml").exists() or (ROOT / "requirements.txt").exists():
        put("Sessions.Worktree bootstrap",
            f"[ -e .venv ] || ln -s \"$(git rev-parse --path-format=absolute --git-common-dir)/../.venv\" .venv; {install or '(None)'}",
            "Python project: share the main checkout's virtualenv", "default")
    else:
        put("Sessions.Worktree bootstrap", "(None)", "pack default", "default")
    if "Gates.Bring the stack up" in findings and "UI testing.Bring the stack up" not in findings:
        put("UI testing.Bring the stack up", findings["Gates.Bring the stack up"]["value"], "same as Gates", "inferred")
    if "UI testing.Bring the stack up" in findings and "Gates.Bring the stack up" not in findings:
        put("Gates.Bring the stack up", findings["UI testing.Bring the stack up"]["value"], "same as UI testing", "inferred")
    if (ROOT / ".coverage-baseline.json").exists():
        raw["baseline_exists"] = True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--markdown", action="store_true")
    args = ap.parse_args()
    if not (ROOT / ".git").exists():
        print("run from the repository root (no .git here)", file=sys.stderr)
        return 2
    for fn in (detect_identity, detect_node, detect_vitest_jest_config, detect_playwright, detect_python,
               detect_go, detect_make_and_compose, detect_ci, detect_docs_and_specs, detect_structure,
               detect_roles_and_language, defaults):
        try:
            fn()
        except Exception as exc:  # one detector failing never hides the others
            raw.setdefault("detector_errors", []).append(f"{fn.__name__}: {exc}")
    if args.markdown:
        print("| Field | Proposed value | Source | Confidence |")
        print("| --- | --- | --- | --- |")
        for k in sorted(findings):
            v = findings[k]
            print(f"| {k} | `{v['value']}` | {v['source']} | {v['confidence']} |")
        if raw.get("setup_needed"):
            print("\n**Setup needed:** " + "; ".join(raw["setup_needed"]))
        if raw.get("hang_risks"):
            print("\n**Hang risks (a gate would wait forever):**")
            for r in raw["hang_risks"]:
                print(f"- {r}")
    else:
        print(json.dumps({"root": str(ROOT), "findings": findings, "raw": raw}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())

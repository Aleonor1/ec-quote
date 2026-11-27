# Test quality gate

The bar every pull request clears before it is merge-ready, on top of the commands in `bindings/PROJECT.md` → Gates. The implementer runs it before opening the pull request and after every push. QA and the code reviewer re-run it on the head they judge. CI runs it too when `bindings/PROJECT.md` → Coverage → CI job is not `(None)`.

Thresholds and commands come from `bindings/PROJECT.md` → Coverage. The numbers below are the defaults that section starts from.

## The five conditions

| # | Condition | How it is checked | Fails when |
| --- | --- | --- | --- |
| 1 | **Every test is green** | The full unit, integration, and end-to-end gates, whole, on the current head | Any red test, any errored suite, any non-zero exit |
| 2 | **Nothing skipped or silenced** | `scripts/test-hygiene.sh scan <base>` (Markdown is not scanned; a fixture that must contain a marker is passed with `--exclude`, and the reviewer judges the exclusion) | An added line skips, focuses, or disables a test, or silences lint, types, or coverage, without `hygiene-allow: <reason>` on that line |
| 3 | **Nothing flaky** | `scripts/test-hygiene.sh repeat <Runs> -- <the full test command>` | Any one of the runs is red. Flaky is red. A flaky test is fixed or its cause is found; it is never retried into green |
| 4 | **Changed code covered** | `scripts/coverage_gate.py` on the report the Coverage command writes | Diff lines or diff branches below **Diff minimum** (default 95%). A changed source file no test loads counts as 0% |
| 5 | **Global coverage never drops** | Same script, against the committed **Baseline file** | Global lines, branches, or functions below the baseline. Once a metric reaches **Global target** (default 95%), the floor for it is the target |

All five, or the pull request is not merge-ready. There is no "close enough".

## Every check is bounded

Each command in this gate and in `bindings/PROJECT.md` → Gates runs through `scripts/run_gate.py` (the timeouts in the binding's Gates → Gate timeout rows, or the defaults). A gate stopped for hanging (exit 124, `GATE HUNG:`) is red, and the line it hung on goes into the finding. Re-running a hung command unchanged is not allowed: find why it waits (a server in the foreground, a watch mode, a report viewer, a prompt) and fix the command or the config.

## The ratchet

The baseline file is committed to the repository. It records the global coverage the base branch has reached and only ever moves up.

- A project that starts below the target is not blocked by it. Each pull request must cover its own diff at the diff minimum and must not lower the global numbers. The global numbers rise as covered code is added.
- The implementer raises the baseline in the same pull request when the global numbers went up: `coverage_gate.py ... --update-baseline`, then commit the file. A reviewer who sees the numbers rise and the file unchanged raises a Minor.
- Two branches that both raised the baseline conflict on it at merge time. Resolve with `coverage_gate.py --resolve-baseline-conflict`: it keeps the higher value per metric and stages the file.
- Lowering the baseline is a **reserved decision** (`rules/human-approval-gate.md`). It needs the human's own words, quoted in the pull-request body.

## What counts as covered

- The report must include files no test loads. The Coverage command is configured for that (`all: true` in Vitest/c8, `--cov=<src>` in pytest, `collectCoverageFrom` in Jest). The binding's **Source globs** tell the gate which changed files are source; one of those absent from the report is uncovered, not ignored.
- Generated code, migrations, type-only files, and configuration are excluded by the binding's **Exclude globs**, decided once per project. A pull request that adds to the exclude list says why in its body, and the reviewer judges it as a finding.
- A line executed by a test that asserts nothing about it is not covered in spirit. `skills/review-code/SKILL.md` checks that each new test would fail without the change. Coverage measures reach; the red-then-green proof measures meaning. Both are required.

## Evidence in the pull-request body

The Gate results section carries, for this gate, the observed output of each check on the head, not a summary:

```markdown
### Test quality gate · head <sha>
| Check | Command | Observed |
| --- | --- | --- |
| All green | <full test command> | <passed/failed/skipped counts, exit code> |
| Hygiene | scripts/test-hygiene.sh scan origin/<base> | PASS, or the allowed lines with reasons |
| Flake | scripts/test-hygiene.sh repeat 2 -- <cmd> | 2 of 2 green |
| Diff coverage | scripts/coverage_gate.py ... | lines <x>% · branches <y>% |
| Global | (same output) | lines <a>% · branches <b>% · functions <c>% vs baseline |
```

## Severity when it fails

| Failure | Severity |
| --- | --- |
| A red or flaky test on the head | **Blocking** |
| Diff coverage under the minimum, or global below the floor | **Major** |
| A skip or silencing marker without a reason | **Major** |
| A marker with a reason the reviewer does not accept | **Major** |
| Baseline not raised after the numbers rose | **Minor** |
| Baseline lowered without the human's quoted words | **Blocking** |

## Anti-patterns

- Writing tests that execute lines without asserting the behaviour, to reach the number.
- Excluding the hard file from coverage instead of testing it.
- Re-running a red suite until it goes green and reporting the green run.
- Reporting coverage from a filtered run, or from a run made before the last edit (`rules/verification-before-claiming.md`).
- Lowering the baseline "temporarily".

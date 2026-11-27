#!/usr/bin/env bash
# test-hygiene.sh: the "100% green, 0 skip, 0 flaky" half of rules/test-quality-gate.md.
#
#   scripts/test-hygiene.sh scan <base-ref> [--exclude <pathspec>]...
#       Markdown is never scanned (docs may name the markers). --exclude takes a
#       git pathspec, e.g. a test fixture that must contain a marker.
#       Fails when lines added against <base-ref> skip, focus, or disable a test
#       (.skip / .only / xit / xdescribe / test.todo / @pytest.mark.skip / xfail /
#       t.Skip / @Disabled / @Ignore), or silence a check (eslint-disable,
#       @ts-ignore, # type: ignore, # pragma: no cover, istanbul ignore, c8 ignore,
#       /* v8 ignore */). A line carrying "hygiene-allow: <reason>" is accepted
#       and listed, so every exception is visible in the PR.
#
#   scripts/test-hygiene.sh repeat <n> -- <command...>
#       Runs <command> n times in a row (default gate: 2). Any red run fails the
#       gate and is reported with its run number: a test that passes once and
#       fails once is flaky, and flaky is red.
#
# Exit 0 when the gate holds, 1 when it fails, 2 on usage error.
set -uo pipefail

usage() { sed -n '2,20p' "$0" >&2; exit 2; }

scan() {
  local base="${1:-}"; [ -n "$base" ] || usage
  shift
  local -a spec=(. ':(exclude)*.md')
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --exclude) [ -n "${2:-}" ] || usage; spec+=(":(exclude)$2"); shift 2 ;;
      *) usage ;;
    esac
  done
  local mb
  mb="$(git merge-base "$base" HEAD 2>/dev/null)" || { echo "cannot find merge-base with $base" >&2; exit 2; }

  # Markers that disable a test or silence coverage/lint/types.
  local pattern
  pattern='(\b(it|test|describe|context|suite|bench)\.(skip|only|todo|fixme)\b|\b(xit|xtest|xdescribe|fit|fdescribe)\s*\(|@pytest\.mark\.(skip|skipif|xfail)|pytest\.skip\(|\bt\.Skip(Now|f)?\(|@Disabled\b|@Ignore\b|eslint-disable|@ts-ignore|@ts-nocheck|#\s*type:\s*ignore|pragma:\s*no\s*cover|istanbul\s+ignore|c8\s+ignore|v8\s+ignore|nolint\b|\btest\.describe\.(skip|only|fixme)\b)'

  local hits allowed
  hits="$(git diff --unified=0 --no-color "$mb" -- "${spec[@]}" | awk '
    /^\+\+\+ /{ f=substr($0,7); next }
    /^@@/{ split($3,a,","); ln=substr(a[1],2)+0; next }
    /^\+/{ print f ":" ln ": " substr($0,2); ln++; next }
  ' | grep -E "$pattern" || true)"

  allowed="$(printf '%s\n' "$hits" | grep -E 'hygiene-allow:' || true)"
  hits="$(printf '%s\n' "$hits" | grep -vE 'hygiene-allow:' | sed '/^$/d' || true)"

  echo "## Test hygiene scan against $base"
  if [ -n "$allowed" ]; then
    echo; echo "**Allowed with a stated reason (review each):**"
    printf '%s\n' "$allowed" | sed 's/^/- /'
  fi
  if [ -n "$hits" ]; then
    echo; echo "**FAIL: added lines skip, focus, or silence a check:**"
    printf '%s\n' "$hits" | sed 's/^/- /'
    exit 1
  fi
  echo; echo "PASS: no skip, focus, or silencing marker added."
}

repeat() {
  local n="${1:-}"; shift || true
  [ "${1:-}" = "--" ] && shift
  [ -n "$n" ] && [ "$#" -gt 0 ] || usage
  local i failed=0
  for i in $(seq 1 "$n"); do
    echo "### run $i/$n: $*"
    if ! "$@"; then
      echo "run $i/$n: RED" >&2
      failed=1
    else
      echo "run $i/$n: green"
    fi
  done
  if [ "$failed" -ne 0 ]; then
    echo "FAIL: at least one of $n runs was red. Flaky counts as red." >&2
    exit 1
  fi
  echo "PASS: $n of $n runs green."
}

case "${1:-}" in
  scan)   shift; scan "$@" ;;
  repeat) shift; repeat "$@" ;;
  *)      usage ;;
esac

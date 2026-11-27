#!/usr/bin/env bash
# Serializes heavy commands when several agent sessions share one machine.
# bindings/PROJECT.md → Shared environment names the commands and the lock directory.
#
#   scripts/heavy-run-lock.sh acquire <owner>
#   scripts/heavy-run-lock.sh release <owner>
#   scripts/heavy-run-lock.sh status
#   scripts/heavy-run-lock.sh run <owner> -- <cmd...>
#
# The lock is a directory: mkdir is atomic, so one acquirer wins. Prefer `run`:
# it records its own pid and host, releases on any exit, and runs the command
# through run_gate.py, so a hung command is stopped (and the lock freed) after
# RUN_GATE_TIMEOUT seconds (default 1800) or RUN_GATE_IDLE seconds of silence
# (default 600) instead of holding every other session forever.
#
# A lock is broken when its holder is gone: its recorded pid no longer runs on
# this host (immediately), or it is older than HEAVY_RUN_STALE_SECONDS
# (default 90 minutes; the fallback for locks taken with plain `acquire`).
set -euo pipefail

LOCK="${HEAVY_RUN_LOCK_DIR:-/tmp/agent-locks/heavy-run.lock}"
STALE="${HEAVY_RUN_STALE_SECONDS:-5400}"
POLL="${HEAVY_RUN_POLL_SECONDS:-15}"

mtime() { stat -c %Y "$1" 2>/dev/null || stat -f %m "$1"; }

age_of() { local m; m="$(mtime "$1" 2>/dev/null)" || return 1; echo $(( $(date +%s) - m )); }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="$(hostname 2>/dev/null || echo unknown)"

holder_dead() {
  # owner file: "<owner> <date> <time> pid=<pid> host=<host>"
  local line pid host
  line="$(cat "$1/owner" 2>/dev/null)" || return 1
  pid="$(printf '%s' "$line" | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p')"
  host="$(printf '%s' "$line" | sed -n 's/.*host=\([^ ]*\).*/\1/p')"
  [ -n "$pid" ] && [ "$host" = "$HOST" ] && ! kill -0 "$pid" 2>/dev/null
}

is_stale() {
  holder_dead "$LOCK" && return 0
  local age; age="$(age_of "$LOCK")" || return 1
  [ "$age" -gt "$STALE" ]
}

acquire() {
  local owner="$1" pid="${2:-}"
  mkdir -p "$(dirname "$LOCK")"
  until mkdir "$LOCK" 2>/dev/null; do
    if is_stale; then
      local aside="$LOCK.stale.$$"
      if mv "$LOCK" "$aside" 2>/dev/null; then
        local aside_age; aside_age="$(age_of "$aside")" || aside_age=0
        if holder_dead "$aside" || [ "$aside_age" -gt "$STALE" ]; then
          echo "broke a stale lock ($(cat "$aside/owner" 2>/dev/null || echo "no owner"))" >&2
          rm -rf "$aside"
        else
          mv "$aside" "$LOCK" 2>/dev/null || rm -rf "$aside"
        fi
      fi
      continue
    fi
    sleep "$POLL"
  done
  echo "$owner $(date '+%F %T')${pid:+ pid=$pid host=$HOST}" > "$LOCK/owner"
  echo "acquired by $owner"
}

release() {
  local owner="$1" holder
  holder="$(cut -d' ' -f1 "$LOCK/owner" 2>/dev/null || true)"
  if [ "$holder" != "$owner" ]; then
    echo "not held by $owner (holder: ${holder:-none})" >&2
    return 1
  fi
  rm -rf "$LOCK"
  echo "released"
}

case "${1:-}" in
  acquire) acquire "${2:?owner}" ;;
  release) release "${2:?owner}" ;;
  status)
    if [ -d "$LOCK" ]; then echo "held: $(cat "$LOCK/owner" 2>/dev/null || echo "(no owner yet)")"; else echo "free"; fi ;;
  run)
    owner="${2:?owner}"; shift 2
    [ "${1:-}" = "--" ] && shift
    [ "$#" -gt 0 ] || { echo "run needs a command after --" >&2; exit 2; }
    acquire "$owner" "$$" >/dev/null
    trap 'release "$owner" >/dev/null 2>&1 || true' EXIT
    trap 'exit 143' INT TERM HUP
    set +e; python3 "$HERE/run_gate.py" --name "$owner: $*" -- "$@"; code=$?; set -e
    exit "$code" ;;
  *)
    echo "usage: $0 acquire|release <owner> | status | run <owner> -- <cmd...>" >&2
    exit 2 ;;
esac

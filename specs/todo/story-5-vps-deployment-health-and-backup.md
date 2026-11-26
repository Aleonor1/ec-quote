---
id: story-5
title: "VPS deployment, health and backup"
effort: MEDIUM
epic: EPIC-0
depends_on: [story-2]
shared_files: [ec_quote/api/app.py, README.md, .gitignore]
track: full
models: {implementer: standard, qa: standard, ui: none, review: standard}
---

# story-5: VPS deployment, health and backup

**Repository:** ec-quote · **Epic:** [EPIC-0](epic-0-foundation.md) · **Depends on:** story-2

## Summary

The owner's plan hosts ec-quote on a VPS, not on Railway. This story makes the service installable there by following a runbook: a container image, a compose file with a TLS reverse proxy, the data directory on a volume, a health endpoint that reports the running commit and the state of each dependency without calling them on every probe, a nightly backup of the SQLite database with a tested restore, and a preflight command that tells the owner in Romanian which setting is missing.

## User Story

As the owner, I want to start, stop, update and restore the service from a short list of commands, so that I do not depend on a developer session to keep it running.

## Scope

**In:** `Dockerfile`, `deploy/compose.yml`, `deploy/Caddyfile`, `deploy/backup.sh`, `deploy/restore.sh`, `ec_quote/doctor.py` (preflight), `ec_quote/api/app.py` (`/health` details), `RUNBOOK.md` (Romanian, for the owner), `tests/test_doctor.py`, `tests/api/test_health.py`, `tests/deploy/test_backup_restore.py`. Whatever already sits in `deploy/` is the starting point and is hardened, not replaced.

**Out:** choosing the provider and the domain (owner); CI; alerts (EPIC-4); the deploy itself, which is the owner's action.

## Acceptance Criteria

1. `docker build` succeeds from a clean checkout and the image runs as a non root user; `docker run` without environment exits non zero with a `SettingsError` line naming the missing variables.
2. `GET /health` answers `{"status": "ok", "commit": "<sha or null>", "shadow_mode": <bool>, "checks": {...}}` in under 100 ms with no outbound call; `commit` comes from a build argument.
3. `GET /health?deep=1` with the inbound secret calls the calculator config endpoint, reads the store and reports each as `ok` or a reason code; without the secret it answers 401. A failing dependency gives status `degraded` and HTTP 200, so the proxy does not restart a service that can still hand off.
4. `python3 -m ec_quote.doctor` prints one line per check in Romanian (settings present by name, rules valid, open decisions listed by key, data directory writable, templates loadable, fonts present) and exits 0, or 2 when a check fails; it prints no secret value.
5. `deploy/backup.sh` produces a consistent copy of the SQLite database while the service is writing (SQLite online backup, not a file copy) and keeps the last 14; `deploy/restore.sh <file>` restores it; the test writes during the backup, restores into a new directory and reads every row back.
6. `deploy/compose.yml` mounts `EC_QUOTE_DATA_DIR` as a named volume, passes secrets from an env file that is in `.gitignore`, exposes only the proxy, and restarts on failure.
7. `RUNBOOK.md` covers, each as numbered steps: first install, update to a new version, stop, restore from backup, where logs are, how to turn `shadow_mode` on, and the list of environment variable names. A test checks that every variable of `.env.example` is named in it.
8. No file in the repository contains a secret value; the pack's hygiene scan passes.

## Technical Notes

- Caddy is proposed for automatic TLS; it is infrastructure on the owner's VPS, not a Python dependency. If the VPS already runs another proxy, the compose file's proxy service is optional.
- The image installs from `pyproject.toml` only; PyMuPDF and Pillow wheels need no system packages on a slim Debian base.

## Hand-over

Owner: VPS provider, SSH access, the subdomain and DNS record, the env file with the values of the variables named in `.env.example`, and running the first install from `RUNBOOK.md`.

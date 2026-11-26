"""Starea mica a stratului API, in SQLite sub directorul de date.

- idempotency: raspunsul motorului pe (canal, cheie, id mesaj), ca o retrimitere sa nu ruleze motorul din nou;
- approvals: carui contact ii apartine o aprobare (Engine.approve nu intoarce contactul);
- outbox: actiuni aprobate ulterior pentru chatul de pe site, ridicate de widget prin poll.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from collections.abc import Callable
from pathlib import Path

IDEMPOTENCY_TTL_SECONDS = 7 * 24 * 3600
OUTBOX_TTL_SECONDS = 7 * 24 * 3600

_SCHEMA = """
CREATE TABLE IF NOT EXISTS idempotency (
  channel TEXT NOT NULL, key TEXT NOT NULL, message_id TEXT NOT NULL,
  actions TEXT NOT NULL, created_at REAL NOT NULL,
  PRIMARY KEY (channel, key, message_id)
);
CREATE TABLE IF NOT EXISTS approvals (
  approval_id TEXT PRIMARY KEY, channel TEXT NOT NULL, key TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT NOT NULL, actions TEXT NOT NULL, created_at REAL NOT NULL
);
"""


class ApiStore:
    def __init__(self, path: Path | str, clock: Callable[[], float] = time.time):
        self._clock = clock
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(_SCHEMA)
            now = self._clock()
            self._db.execute("DELETE FROM idempotency WHERE created_at < ?",
                             (now - IDEMPOTENCY_TTL_SECONDS,))
            self._db.execute("DELETE FROM outbox WHERE created_at < ?", (now - OUTBOX_TTL_SECONDS,))

    def get_response(self, channel: str, key: str, message_id: str) -> str | None:
        with self._lock:
            row = self._db.execute(
                "SELECT actions FROM idempotency WHERE channel=? AND key=? AND message_id=?",
                (channel, key, message_id)).fetchone()
        return row[0] if row else None

    def save_response(self, channel: str, key: str, message_id: str, actions_json: str) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO idempotency VALUES (?, ?, ?, ?, ?)",
                (channel, key, message_id, actions_json, self._clock()))

    def save_approval(self, approval_id: str, channel: str, key: str) -> None:
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO approvals VALUES (?, ?, ?, ?)",
                             (approval_id, channel, key, self._clock()))

    def get_approval(self, approval_id: str) -> tuple[str, str] | None:
        with self._lock:
            row = self._db.execute("SELECT channel, key FROM approvals WHERE approval_id=?",
                                   (approval_id,)).fetchone()
        return (row[0], row[1]) if row else None

    def push_outbox(self, key: str, actions_json: str) -> None:
        with self._lock:
            self._db.execute("INSERT INTO outbox (key, actions, created_at) VALUES (?, ?, ?)",
                             (key, actions_json, self._clock()))

    def pop_outbox(self, key: str) -> list[str]:
        with self._lock:
            rows = self._db.execute("SELECT id, actions FROM outbox WHERE key=? ORDER BY id",
                                    (key,)).fetchall()
            if rows:
                self._db.execute("DELETE FROM outbox WHERE key=? AND id<=?", (key, rows[-1][0]))
        return [r[1] for r in rows]

    def close(self) -> None:
        with self._lock:
            self._db.close()

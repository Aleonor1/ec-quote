"""Starea conversatiilor: protocol, implementare SQLite (stdlib) si una in memorie pentru teste."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from ec_quote.contracts import (
    Attachment, Contact, FileReport, OfferLine, PriceQuote, TierOffer,
)

Status = Literal["collecting", "offer_pending_approval", "offer_sent", "manual", "closed"]
ApprovalStatus = Literal["pending", "approved", "rejected", "superseded"]


class ConversationState(BaseModel):
    channel: str
    key: str
    contact: Contact
    status: Status = "collecting"
    questions_asked: int = 0
    misunderstandings: int = 0
    file_failures: int = 0
    quote_seq: int = 0
    quotes: dict[str, PriceQuote] = Field(default_factory=dict)
    tiers: dict[str, list[TierOffer]] = Field(default_factory=dict)
    design: Attachment | None = None
    file_report: FileReport | None = None
    last_failed_file: str | None = None
    mockup_path: str | None = None
    pending_buttons: dict[str, str] = Field(default_factory=dict)
    summary: str = ""
    lead_id: str | None = None
    offer_times: list[datetime] = Field(default_factory=list)
    pending_approval_id: str | None = None
    last_approval_id: str | None = None
    manual_since: datetime | None = None
    last_message_at: datetime | None = None
    first_inbound_at: datetime | None = None
    first_reply_at: datetime | None = None
    first_offer_at: datetime | None = None


class LoggedMessage(BaseModel):
    direction: Literal["in", "out", "staff"]
    text: str = ""
    at: datetime
    meta: dict = Field(default_factory=dict)


class Approval(BaseModel):
    """Oferta pregatita in mod umbra, in asteptarea unui om."""

    id: str
    channel: str
    key: str
    status: ApprovalStatus = "pending"
    created_at: datetime
    quote: PriceQuote
    lines: list[OfferLine]
    offer_text: str            # fara linkul de plata
    image_path: str | None = None
    artwork_url: str | None = None
    valid_until: datetime
    summary: str = ""
    decided_by: str | None = None
    decided_at: datetime | None = None
    human_changed: bool | None = None


class ConversationStore(Protocol):
    def load(self, channel: str, key: str) -> ConversationState | None: ...

    def save(self, state: ConversationState) -> None: ...

    def append_message(self, channel: str, key: str, message: LoggedMessage) -> None: ...

    def recent_messages(self, channel: str, key: str, limit: int) -> list[LoggedMessage]: ...

    def claim_inbound(self, channel: str, key: str, message_id: str) -> bool:
        """True daca id-ul este nou; False daca mesajul a mai fost procesat."""

    def save_approval(self, approval: Approval) -> None: ...

    def get_approval(self, approval_id: str) -> Approval | None: ...


class InMemoryStore:
    def __init__(self) -> None:
        self._states: dict[tuple[str, str], str] = {}
        self._messages: dict[tuple[str, str], list[LoggedMessage]] = {}
        self._inbound: set[tuple[str, str, str]] = set()
        self._approvals: dict[str, str] = {}
        self._lock = threading.Lock()

    def load(self, channel: str, key: str) -> ConversationState | None:
        raw = self._states.get((channel, key))
        return ConversationState.model_validate_json(raw) if raw else None

    def save(self, state: ConversationState) -> None:
        # Serializat, ca testele sa prinda orice camp care nu trece prin JSON.
        self._states[(state.channel, state.key)] = state.model_dump_json()

    def append_message(self, channel: str, key: str, message: LoggedMessage) -> None:
        self._messages.setdefault((channel, key), []).append(message)

    def recent_messages(self, channel: str, key: str, limit: int) -> list[LoggedMessage]:
        return list(self._messages.get((channel, key), [])[-limit:])

    def claim_inbound(self, channel: str, key: str, message_id: str) -> bool:
        with self._lock:
            item = (channel, key, message_id)
            if item in self._inbound:
                return False
            self._inbound.add(item)
            return True

    def save_approval(self, approval: Approval) -> None:
        self._approvals[approval.id] = approval.model_dump_json()

    def get_approval(self, approval_id: str) -> Approval | None:
        raw = self._approvals.get(approval_id)
        return Approval.model_validate_json(raw) if raw else None


_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    channel TEXT NOT NULL, key TEXT NOT NULL, status TEXT NOT NULL,
    state TEXT NOT NULL, updated_at TEXT NOT NULL,
    PRIMARY KEY (channel, key)
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL, key TEXT NOT NULL, direction TEXT NOT NULL,
    text TEXT NOT NULL, at TEXT NOT NULL, meta TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS messages_conversation ON messages (channel, key, id);
CREATE TABLE IF NOT EXISTS inbound_ids (
    channel TEXT NOT NULL, key TEXT NOT NULL, message_id TEXT NOT NULL,
    PRIMARY KEY (channel, key, message_id)
);
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY, channel TEXT NOT NULL, key TEXT NOT NULL,
    status TEXT NOT NULL, created_at TEXT NOT NULL, data TEXT NOT NULL
);
"""


def default_db_path() -> Path:
    return Path(os.environ.get("EC_QUOTE_DATA_DIR") or "./data") / "conversations.sqlite3"


class SqliteStore:
    """Un rand per conversatie (channel, key), stare JSON, jurnal de mesaje, aprobari."""

    def __init__(self, path: str | os.PathLike | None = None) -> None:
        self.path = Path(path) if path else default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(self.path), check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA busy_timeout=5000")
        self._db.executescript(_SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def load(self, channel: str, key: str) -> ConversationState | None:
        with self._lock:
            row = self._db.execute(
                "SELECT state FROM conversations WHERE channel = ? AND key = ?", (channel, key)).fetchone()
        return ConversationState.model_validate_json(row[0]) if row else None

    def save(self, state: ConversationState) -> None:
        stamp = (state.last_message_at or datetime.min).isoformat()
        with self._lock:
            self._db.execute(
                "INSERT INTO conversations (channel, key, status, state, updated_at) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT (channel, key) DO UPDATE SET status = excluded.status, "
                "state = excluded.state, updated_at = excluded.updated_at",
                (state.channel, state.key, state.status, state.model_dump_json(), stamp))

    def append_message(self, channel: str, key: str, message: LoggedMessage) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO messages (channel, key, direction, text, at, meta) VALUES (?, ?, ?, ?, ?, ?)",
                (channel, key, message.direction, message.text, message.at.isoformat(),
                 json.dumps(message.meta, ensure_ascii=False, default=_json_default)))

    def recent_messages(self, channel: str, key: str, limit: int) -> list[LoggedMessage]:
        with self._lock:
            rows = self._db.execute(
                "SELECT direction, text, at, meta FROM messages WHERE channel = ? AND key = ? "
                "ORDER BY id DESC LIMIT ?", (channel, key, limit)).fetchall()
        return [LoggedMessage(direction=r[0], text=r[1], at=datetime.fromisoformat(r[2]), meta=json.loads(r[3]))
                for r in reversed(rows)]

    def claim_inbound(self, channel: str, key: str, message_id: str) -> bool:
        with self._lock:
            cursor = self._db.execute(
                "INSERT OR IGNORE INTO inbound_ids (channel, key, message_id) VALUES (?, ?, ?)",
                (channel, key, message_id))
            return cursor.rowcount == 1

    def save_approval(self, approval: Approval) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO approvals (id, channel, key, status, created_at, data) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (id) DO UPDATE SET status = excluded.status, data = excluded.data",
                (approval.id, approval.channel, approval.key, approval.status,
                 approval.created_at.isoformat(), approval.model_dump_json()))

    def get_approval(self, approval_id: str) -> Approval | None:
        with self._lock:
            row = self._db.execute("SELECT data FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        return Approval.model_validate_json(row[0]) if row else None


def _json_default(value: object) -> str:
    if isinstance(value, (Decimal, datetime)):
        return str(value)
    raise TypeError(f"nu pot serializa {type(value).__name__}")

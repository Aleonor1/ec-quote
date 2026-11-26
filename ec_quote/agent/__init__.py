"""Motorul de conversatie ec-quote (portul Engine din contracts.py)."""
from __future__ import annotations

import os

from ec_quote.contracts import CheckoutPort, CrmPort, FilePort, HandoffPort, MockupPort, PricingPort

from .engine import ApprovalError, QuoteEngine
from .model import AnthropicModel, ModelError, ModelPort, ModelReply, ToolCall, model_id_from_env
from .rules import Rules
from .store import (
    Approval, ConversationState, ConversationStore, InMemoryStore, LoggedMessage, SqliteStore,
)


def build_engine(
    *, pricing: PricingPort, files: FilePort, mockup: MockupPort, checkout: CheckoutPort,
    crm: CrmPort, handoff: HandoffPort, model: ModelPort | None = None,
    store: ConversationStore | None = None, rules: Rules | None = None,
    data_dir: str | os.PathLike | None = None,
) -> QuoteEngine:
    """Motorul de productie: model Anthropic, stare SQLite sub EC_QUOTE_DATA_DIR, reguli din config/rules.json."""
    return QuoteEngine(
        model=model or AnthropicModel(), pricing=pricing, files=files, mockup=mockup, checkout=checkout,
        crm=crm, handoff=handoff,
        store=store or SqliteStore(os.path.join(str(data_dir), "conversations.sqlite3") if data_dir else None),
        rules=rules or Rules.load(), data_dir=data_dir)


__all__ = [
    "AnthropicModel", "Approval", "ApprovalError", "ConversationState", "ConversationStore", "InMemoryStore",
    "LoggedMessage", "ModelError", "ModelPort", "ModelReply", "QuoteEngine", "Rules", "SqliteStore", "ToolCall",
    "build_engine", "model_id_from_env",
]

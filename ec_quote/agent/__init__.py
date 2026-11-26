"""Motorul ec-quote: porturile AssistEngine (mod asistat) si Engine (chatul de pe site) din contracts.py."""
from __future__ import annotations

import os

from ec_quote.contracts import (
    CheckoutPort, CrmPort, FilePort, HandoffPort, KnowledgePort, MockupPort, PricingPort,
)

from .engine import ApprovalError, QuoteEngine
from .model import AnthropicModel, ModelError, ModelPort, ModelReply, ToolCall, model_id_from_env
from .rules import Rules
from .store import (
    Approval, ConversationState, ConversationStore, InMemoryStore, KnowledgeGap, LoggedMessage, SqliteStore,
    Suggestion,
)


def build_engine(
    *, pricing: PricingPort, files: FilePort, mockup: MockupPort, checkout: CheckoutPort,
    crm: CrmPort, handoff: HandoffPort, knowledge: KnowledgePort | None = None, model: ModelPort | None = None,
    store: ConversationStore | None = None, rules: Rules | None = None,
    data_dir: str | os.PathLike | None = None,
) -> QuoteEngine:
    """Motorul de productie: model Anthropic, stare SQLite sub EC_QUOTE_DATA_DIR, reguli din config/rules.json.

    Obiectul intors implementeaza si AssistEngine (suggest, create_payment_link), si Engine (handle, approve, reject).
    """
    return QuoteEngine(
        model=model or AnthropicModel(), pricing=pricing, files=files, mockup=mockup, checkout=checkout,
        crm=crm, handoff=handoff, knowledge=knowledge,
        store=store or SqliteStore(os.path.join(str(data_dir), "conversations.sqlite3") if data_dir else None),
        rules=rules or Rules.load(), data_dir=data_dir)


__all__ = [
    "AnthropicModel", "Approval", "ApprovalError", "ConversationState", "ConversationStore", "InMemoryStore",
    "KnowledgeGap", "LoggedMessage", "ModelError", "ModelPort", "ModelReply", "QuoteEngine", "Rules", "SqliteStore",
    "Suggestion", "ToolCall",
    "build_engine", "model_id_from_env",
]

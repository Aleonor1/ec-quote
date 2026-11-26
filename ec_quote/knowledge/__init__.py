"""Baza de cunostinte: raspunsuri aprobate la intrebarile obisnuite ale clientilor.

Continutul sta in `knowledge/*.json`. Ce nu are sursa este `needs_owner` si nu se serveste.
"""
from ec_quote.knowledge.base import KnowledgeBase, Match
from ec_quote.knowledge.loader import (
    AuthoredEntry,
    Contradiction,
    KnowledgeContent,
    KnowledgeError,
    default_knowledge_dir,
    load_content,
)

__all__ = [
    "AuthoredEntry",
    "Contradiction",
    "KnowledgeBase",
    "KnowledgeContent",
    "KnowledgeError",
    "Match",
    "default_knowledge_dir",
    "load_content",
]

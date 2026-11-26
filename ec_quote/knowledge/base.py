"""`KnowledgeBase`: cautare lexicala simpla peste intrarile aprobate. Implementeaza `KnowledgePort`.

Cum se alege un raspuns:
1. Intrebarea devine o multime de concepte (fara diacritice, radacini, expresii, sinonime).
2. O intrare intra in calcul doar daca intrebarea contine macar una dintre ancorele ei.
3. Scorul combina cat din intrebare este acoperit de intrare cu cat din formularea intrarii se regaseste
   in intrebare; conceptele rare cantaresc mai mult.
4. Sub pragul `min_score` nu se intoarce nimic.
5. Intrarile `needs_owner` nu se intorc niciodata, dar participa la clasament: daca o intrebare
   deschisa se potriveste cel putin la fel de bine ca cel mai bun raspuns aprobat, rezultatul este
   lista goala. Asa „rezista la congelator?” nu primeste raspunsul despre apa.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from ec_quote.contracts import KnowledgeEntry
from ec_quote.knowledge.loader import AuthoredEntry, Contradiction, KnowledgeContent, load_content
from ec_quote.knowledge.text import Lexicon

_RECALL_WEIGHT = 0.75
_UNKNOWN_FACTOR = 0.5


@dataclass(frozen=True)
class _Indexed:
    entry: AuthoredEntry
    anchors: frozenset[str]
    keywords: frozenset[str]
    phrasings: tuple[frozenset[str], ...]
    applies: tuple[frozenset[str], ...]


@dataclass(frozen=True)
class Match:
    """Un rand din clasament, pentru diagnostic si pentru nota catre operator."""

    id: str
    status: str
    score: float


class KnowledgeBase:
    """Baza de cunostinte in memorie. Se construieste o data, la pornire, din `knowledge/`."""

    def __init__(self, content: KnowledgeContent) -> None:
        self._policy = content.policy
        self._lexicon: Lexicon = content.lexicon
        self._contradictions = list(content.contradictions)
        for entry in content.entries:
            for text in (entry.question, *entry.variants, *entry.keywords):
                self._lexicon.learn(text)
        self._index = [self._index_entry(entry) for entry in content.entries]
        counts: dict[str, int] = {}
        for item in self._index:
            for concept in set().union(item.keywords, *item.phrasings):
                counts[concept] = counts.get(concept, 0) + 1
        total = len(self._index)
        self._idf = {concept: math.log(1 + total / count) for concept, count in counts.items()}
        self._unknown_weight = _UNKNOWN_FACTOR * math.log(1 + total)

    @classmethod
    def from_dir(cls, root: Path | str | None = None) -> "KnowledgeBase":
        return cls(load_content(root))

    def _index_entry(self, entry: AuthoredEntry) -> _Indexed:
        concepts = self._lexicon.concepts
        phrasings = tuple(
            frozenset(found) for found in (concepts(text) for text in (entry.question, *entry.variants)) if found
        )
        keywords = frozenset(c for keyword in entry.keywords for c in concepts(keyword))
        anchors = frozenset(c for anchor in entry.anchors for c in (concepts(anchor) or [anchor]))
        applies = tuple(frozenset(concepts(name)) for name in entry.applies_to)
        return _Indexed(entry=entry, anchors=anchors, keywords=keywords, phrasings=phrasings, applies=applies)

    def _weight(self, concepts: frozenset[str] | set[str]) -> float:
        return sum(self._idf.get(concept, self._unknown_weight) for concept in concepts)

    def _score(self, query: frozenset[str], item: _Indexed) -> float:
        if not query & item.anchors:
            return 0.0
        query_weight = self._weight(query)
        best = 0.0
        for phrasing in item.phrasings:
            recall = self._weight(query & (phrasing | item.keywords)) / query_weight
            precision = self._weight(query & phrasing) / self._weight(phrasing)
            best = max(best, _RECALL_WEIGHT * recall + (1 - _RECALL_WEIGHT) * precision)
        return best

    def _applies(self, item: _Indexed, target: frozenset[str] | None) -> bool:
        if target is None or not item.applies:
            return True
        return any(name <= target or target <= name for name in item.applies if name)

    def rank(self, query: str, applies_to: str | None = None) -> list[Match]:
        """Clasamentul complet peste prag, cu tot cu intrebarile deschise. Pentru diagnostic."""
        concepts = frozenset(self._lexicon.concepts(query[: self._policy.max_query_chars]))
        if not concepts:
            return []
        target = frozenset(self._lexicon.concepts(applies_to)) if applies_to and applies_to.strip() else None
        ranked: list[Match] = []
        for item in self._index:
            if not self._applies(item, target):
                continue
            score = self._score(concepts, item)
            if score >= self._policy.min_score:
                ranked.append(Match(id=item.entry.id, status=item.entry.status, score=round(score, 4)))
        ranked.sort(key=lambda match: (-match.score, match.status != "needs_owner", match.id))
        return ranked

    def search(self, query: str, limit: int = 5, applies_to: str | None = None) -> list[KnowledgeEntry]:
        """Doar intrarile `verified`, cele mai potrivite primele. Lista goala inseamna: intreaba un om.

        `applies_to` este numele unui produs sau material: raman intrarile generale si cele care il privesc.
        """
        if limit <= 0:
            return []
        found: list[KnowledgeEntry] = []
        by_id = {item.entry.id: item.entry for item in self._index}
        for match in self.rank(query, applies_to):
            if match.status != "verified":
                break
            found.append(by_id[match.id].public())
            if len(found) == limit:
                break
        return found

    def open_question(self, query: str, applies_to: str | None = None) -> KnowledgeEntry | None:
        """Intrebarea deschisa care a blocat raspunsul, daca exista: de pus in nota pentru operator."""
        ranked = self.rank(query, applies_to)
        if ranked and ranked[0].status == "needs_owner":
            return self.entry(ranked[0].id).public()
        return None

    def topics(self) -> list[str]:
        """Subiectele care au macar un raspuns aprobat."""
        return sorted({item.entry.topic for item in self._index if item.entry.status == "verified"})

    def needs_owner(self) -> list[KnowledgeEntry]:
        """Intrebarile deschise. Nu se servesc clientilor."""
        return [item.entry.public() for item in self._index if item.entry.status == "needs_owner"]

    def authored(self) -> list[AuthoredEntry]:
        return [item.entry for item in self._index]

    def entry(self, entry_id: str) -> AuthoredEntry:
        for item in self._index:
            if item.entry.id == entry_id:
                return item.entry
        raise KeyError(entry_id)

    def contradictions(self) -> list[Contradiction]:
        return list(self._contradictions)

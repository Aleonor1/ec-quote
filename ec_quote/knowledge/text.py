"""Normalizarea textului pentru cautare: fara diacritice, radacini usoare, expresii si sinonime.

Totul este determinist si fara retea. Vocabularul (cuvinte ignorate, expresii, sinonime) vine din
`knowledge/_lexicon.json`, nu din cod.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_NUMERIC_RE = re.compile(r"\d+(x\d+)?")

# Sufixe romanesti, de la cel mai lung la cel mai scurt. Se taie unul singur, daca raman macar 3 litere.
_SUFFIXES = (
    "urilor", "ilor", "elor", "ului", "ente", "enta", "enti", "area", "irea", "eaza", "este",
    "ent", "esc", "ati", "eti", "iti", "uri", "are", "ire", "lor", "ele", "ile",
    "ul", "le", "ei", "ii", "a", "e", "i", "u",
)
_MIN_STEM = 3
_FUZZY_MIN_LEN = 5
_FUZZY_LONG_LEN = 8


def normalize(text: str) -> str:
    """Litere mici, fara diacritice, spatii simple."""
    stripped = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped.lower()).strip()


def words(text: str) -> list[str]:
    """Cuvintele unui text normalizat; numerele simple si dimensiunile (5x5) se arunca."""
    return [w for w in _TOKEN_RE.findall(normalize(text)) if not _NUMERIC_RE.fullmatch(w)]


def stem(word: str) -> str:
    """Radacina usoara: 'rezista', 'rezistente', 'rezistent' -> 'rezist'."""
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= _MIN_STEM:
            return word[: -len(suffix)]
    return word


def edit_distance(left: str, right: str, limit: int) -> int:
    """Distanta Levenshtein, oprita devreme: intoarce limit + 1 cand depaseste limita."""
    if abs(len(left) - len(right)) > limit:
        return limit + 1
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, start=1):
        current = [i]
        for j, b in enumerate(right, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (a != b)))
        if min(current) > limit:
            return limit + 1
        previous = current
    return previous[-1]


@dataclass
class Lexicon:
    """Cuvinte ignorate, expresii (mai multe cuvinte -> un concept) si sinonime (forma -> concept)."""

    stopwords: frozenset[str] = frozenset()
    phrases: dict[str, str] = field(default_factory=dict)
    synonyms: dict[str, list[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._forms: dict[str, str] = {}
        self._stems: dict[str, str] = {}
        for concept, forms in self.synonyms.items():
            for form in [concept, *forms]:
                self._forms[form] = concept
        for form, concept in self._forms.items():
            self._stems.setdefault(stem(form), concept)
        ordered = sorted(self.phrases, key=len, reverse=True)
        self._phrase_re = (
            re.compile(r"(?<![a-z0-9])(" + "|".join(re.escape(p) for p in ordered) + r")(?![a-z0-9])")
            if ordered else None
        )
        self._known: set[str] = set(self._forms)

    def learn(self, text: str) -> None:
        """Adauga cuvintele unui text la vocabularul folosit pentru corectarea greselilor de tastare."""
        self._known.update(w for w in words(text) if len(w) >= _FUZZY_MIN_LEN)

    def concept(self, word: str) -> str:
        """Conceptul unui cuvant: sinonim exact, apoi radacina, apoi cea mai apropiata forma cunoscuta."""
        if word in self._forms:
            return self._forms[word]
        root = stem(word)
        if root in self._stems:
            return self._stems[root]
        if word in self._known:
            return root
        near = self._nearest(word)
        if near is None:
            return root
        return self._forms.get(near) or self._stems.get(stem(near)) or stem(near)

    def _nearest(self, word: str) -> str | None:
        if len(word) < _FUZZY_MIN_LEN:
            return None
        limit = 2 if len(word) >= _FUZZY_LONG_LEN else 1
        best: tuple[int, str] | None = None
        tied = False
        for known in sorted(self._known):
            if len(known) < _FUZZY_MIN_LEN or known[0] != word[0]:
                continue
            distance = edit_distance(word, known, limit)
            if distance > limit:
                continue
            if best is None or distance < best[0]:
                best, tied = (distance, known), False
            elif distance == best[0] and self._resolve(known) != self._resolve(best[1]):
                tied = True
        if best is None or tied:
            return None
        return best[1]

    def _resolve(self, known: str) -> str:
        return self._forms.get(known) or self._stems.get(stem(known)) or stem(known)

    def concepts(self, text: str) -> list[str]:
        """Conceptele unui text, in ordine, fara cuvintele ignorate si fara repetitii."""
        plain = normalize(text)
        if self._phrase_re is not None:
            plain = self._phrase_re.sub(lambda m: " " + self.phrases[m.group(1)] + " ", plain)
        seen: list[str] = []
        for word in words(plain):
            if word in self.stopwords:
                continue
            concept = self.concept(word)
            if concept not in seen:
                seen.append(concept)
        return seen

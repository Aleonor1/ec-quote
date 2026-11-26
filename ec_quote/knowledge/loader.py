"""Incarcarea si validarea stricta a continutului din `knowledge/`.

Un fisier pe subiect (`<subiect>.json`), plus trei fisiere de sprijin care incep cu `_`:
`_policy.json` (praguri si cuvinte interzise), `_lexicon.json` (vocabularul de cautare) si
`_contradictions.json` (contradictiile dintre surse, pentru owner). Orice abatere opreste incarcarea:
o baza de cunostinte pe jumatate valida nu se serveste.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ec_quote.contracts import KnowledgeEntry
from ec_quote.knowledge.text import Lexicon, normalize

_ID_RE = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
_DASHES = ("—", "–", "―")          # em dash, en dash, bara orizontala
_CEDILLAS = ("ş", "ţ", "Ş", "Ţ")  # s si t cu sedila in loc de virgula
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U0001F1E6-\U0001F1FF☀-➿⬀-⯿️‍]"
)
_MONEY_RE = re.compile(r"\d[\d.,]*\s*(?:de\s+)?(?:lei|leu|ron|eur|euro|€)(?![a-z])")
_PERCENT_RE = re.compile(r"\d[\d.,]*\s*(?:%|la suta|procente?)")


class KnowledgeError(ValueError):
    """Continutul din `knowledge/` nu respecta regulile. Mesajul spune fisierul si intrarea."""


class Amount(BaseModel):
    """O suma publicata care apare intr-un raspuns, cu sursa ei exacta."""

    model_config = ConfigDict(extra="forbid")

    text: str
    source: str


class AuthoredEntry(KnowledgeEntry):
    """`KnowledgeEntry` plus campurile de redactare. `search` intoarce doar partea din contract."""

    model_config = ConfigDict(extra="forbid")

    anchors: list[str] = Field(default_factory=list)      # macar un concept de aici trebuie sa fie in intrebare
    variants: list[str] = Field(default_factory=list)     # alte formulari ale intrebarii
    keywords: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)  # referinte exacte: pagina, cale de fisier, camp
    last_checked: str = ""
    owner_question: str = ""                              # doar la needs_owner: intrebarea pentru owner
    amounts: list[Amount] = Field(default_factory=list)
    config_refs: list[str] = Field(default_factory=list)  # valori care se citesc din calculator-config
    note_for_staff: str = ""

    def public(self) -> KnowledgeEntry:
        return KnowledgeEntry(**self.model_dump(include=set(KnowledgeEntry.model_fields)))


class Policy(BaseModel):
    model_config = ConfigDict(extra="ignore")

    min_score: float
    max_answer_chars: int
    max_query_chars: int
    forbidden_words: list[str]


class Contradiction(BaseModel):
    """Doua surse care spun lucruri diferite. Nu alegem noi: intrebarea merge la owner."""

    model_config = ConfigDict(extra="forbid")

    id: str
    topic: str
    summary: str
    sources: list[str]
    question: str


@dataclass(frozen=True)
class KnowledgeContent:
    entries: list[AuthoredEntry]
    policy: Policy
    lexicon: Lexicon
    contradictions: list[Contradiction]


def default_knowledge_dir() -> Path:
    """`knowledge/` de langa pachet (radacina depozitului ec-quote)."""
    return Path(__file__).resolve().parents[2] / "knowledge"


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise KnowledgeError(f"{path.name}: fisierul lipseste") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise KnowledgeError(f"{path.name}: nu este JSON valid ({exc})") from exc


def _money_mentions(text: str) -> list[str]:
    plain = normalize(text)
    return [normalize(m.group(0)) for m in _MONEY_RE.finditer(plain)] + [
        normalize(m.group(0)) for m in _PERCENT_RE.finditer(plain)
    ]


def _check_text(where: str, label: str, text: str, policy: Policy, claims: bool = False) -> None:
    """Reguli de scriere pentru orice text; `claims` adauga cuvintele interzise (doar pentru raspunsuri)."""
    for dash in _DASHES:
        if dash in text:
            raise KnowledgeError(f"{where}: {label} contine linie de dialog (em dash sau en dash)")
    for cedilla in _CEDILLAS:
        if cedilla in text:
            raise KnowledgeError(f"{where}: {label} foloseste litere cu sedila in loc de diacritice cu virgula")
    if _EMOJI_RE.search(text):
        raise KnowledgeError(f"{where}: {label} contine emoji")
    if "{{" in text or "}}" in text:
        raise KnowledgeError(f"{where}: {label} contine un substituent necompletat")
    if not claims:
        return
    plain = normalize(text)
    for word in policy.forbidden_words:
        if re.search(r"(?<![a-z0-9])" + re.escape(normalize(word)) + r"(?![a-z0-9])", plain):
            raise KnowledgeError(f"{where}: {label} contine un cuvant interzis ({word!r})")


def _check_entry(where: str, entry: AuthoredEntry, topic: str, policy: Policy) -> None:
    if not _ID_RE.fullmatch(entry.id):
        raise KnowledgeError(f"{where}: id invalid ({entry.id!r}); doar litere mici, cifre si cratime")
    if entry.topic != topic:
        raise KnowledgeError(f"{where}: subiectul intrarii ({entry.topic!r}) difera de al fisierului ({topic!r})")
    if not entry.question.strip():
        raise KnowledgeError(f"{where}: lipseste intrebarea")
    if not entry.anchors:
        raise KnowledgeError(f"{where}: lipsesc ancorele (conceptele fara de care intrarea nu se potriveste)")
    try:
        date.fromisoformat(entry.last_checked)
    except ValueError as exc:
        raise KnowledgeError(f"{where}: last_checked trebuie sa fie o data AAAA-LL-ZZ") from exc
    _check_text(where, "intrebarea", entry.question, policy)
    for variant in entry.variants:
        _check_text(where, "o varianta", variant, policy)

    if entry.status == "needs_owner":
        if entry.answer.strip():
            raise KnowledgeError(f"{where}: o intrare needs_owner nu are voie sa aiba raspuns")
        if not entry.owner_question.strip():
            raise KnowledgeError(f"{where}: lipseste intrebarea pentru owner")
        _check_text(where, "intrebarea pentru owner", entry.owner_question, policy)
        if "\n" in entry.owner_question:
            raise KnowledgeError(f"{where}: intrebarea pentru owner trebuie sa incapa pe un rand")
        return

    if not entry.answer.strip():
        raise KnowledgeError(f"{where}: o intrare verified nu are raspuns")
    if not entry.source.strip() or not entry.source_refs:
        raise KnowledgeError(f"{where}: o intrare verified nu are sursa (source si source_refs)")
    if entry.owner_question:
        raise KnowledgeError(f"{where}: o intrare verified nu are intrebare pentru owner")
    if len(entry.answer) > policy.max_answer_chars:
        raise KnowledgeError(
            f"{where}: raspunsul are {len(entry.answer)} caractere, peste limita de {policy.max_answer_chars}"
        )
    _check_text(where, "raspunsul", entry.answer, policy, claims=True)

    flagged = {normalize(amount.text) for amount in entry.amounts}
    for amount in entry.amounts:
        if not amount.source.strip():
            raise KnowledgeError(f"{where}: suma {amount.text!r} nu are sursa")
    for mention in _money_mentions(entry.answer):
        if mention not in flagged:
            raise KnowledgeError(
                f"{where}: raspunsul contine suma {mention!r} fara sursa in `amounts`; "
                "preturile vin doar din calculator"
            )
    mentioned = set(_money_mentions(entry.answer))
    for text in flagged - mentioned:
        raise KnowledgeError(f"{where}: suma {text!r} din `amounts` nu apare in raspuns")


def _load_policy(root: Path) -> Policy:
    raw = _read_json(root / "_policy.json")
    try:
        policy = Policy.model_validate(raw)
    except ValidationError as exc:
        raise KnowledgeError(f"_policy.json: {exc.errors()[0]['loc']} {exc.errors()[0]['msg']}") from exc
    if not 0 < policy.min_score <= 1 or policy.max_answer_chars <= 0 or policy.max_query_chars <= 0:
        raise KnowledgeError("_policy.json: praguri in afara intervalului permis")
    return policy


def _load_lexicon(root: Path) -> Lexicon:
    raw = _read_json(root / "_lexicon.json")
    if not isinstance(raw, dict):
        raise KnowledgeError("_lexicon.json: trebuie sa fie un obiect")
    stopwords = raw.get("stopwords", [])
    phrases = raw.get("phrases", {})
    synonyms = raw.get("synonyms", {})
    if not isinstance(stopwords, list) or not isinstance(phrases, dict) or not isinstance(synonyms, dict):
        raise KnowledgeError("_lexicon.json: stopwords este lista, phrases si synonyms sunt obiecte")
    seen: dict[str, str] = {}
    for concept, forms in synonyms.items():
        if not isinstance(forms, list):
            raise KnowledgeError(f"_lexicon.json: sinonimele pentru {concept!r} trebuie sa fie o lista")
        for form in forms:
            if not isinstance(form, str) or form != normalize(form) or " " in form:
                raise KnowledgeError(f"_lexicon.json: forma {form!r} trebuie sa fie un singur cuvant, fara diacritice")
            if seen.get(form, concept) != concept:
                raise KnowledgeError(f"_lexicon.json: {form!r} apare la doua concepte ({seen[form]}, {concept})")
            seen[form] = concept
    for phrase, concept in phrases.items():
        if phrase != normalize(phrase) or not isinstance(concept, str):
            raise KnowledgeError(f"_lexicon.json: expresia {phrase!r} trebuie scrisa fara diacritice")
    for word in stopwords:
        if word in seen:
            raise KnowledgeError(f"_lexicon.json: {word!r} este si cuvant ignorat, si sinonim")
    products = raw.get("product_concepts", [])
    if not isinstance(products, list) or any(name not in synonyms for name in products):
        raise KnowledgeError("_lexicon.json: product_concepts trebuie sa fie o lista de concepte din synonyms")
    return Lexicon(
        stopwords=frozenset(stopwords), phrases=dict(phrases), synonyms=dict(synonyms),
        product_concepts=frozenset(products),
    )


def _load_contradictions(root: Path, policy: Policy) -> list[Contradiction]:
    path = root / "_contradictions.json"
    if not path.exists():
        return []
    raw = _read_json(path)
    items = raw.get("contradictions") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        raise KnowledgeError("_contradictions.json: lipseste lista `contradictions`")
    found: list[Contradiction] = []
    ids: set[str] = set()
    for index, item in enumerate(items):
        where = f"_contradictions.json[{index}]"
        try:
            contradiction = Contradiction.model_validate(item)
        except ValidationError as exc:
            raise KnowledgeError(f"{where}: {exc.errors()[0]['loc']} {exc.errors()[0]['msg']}") from exc
        if contradiction.id in ids:
            raise KnowledgeError(f"{where}: id duplicat ({contradiction.id})")
        if len(contradiction.sources) < 2:
            raise KnowledgeError(f"{where}: o contradictie are cel putin doua surse")
        ids.add(contradiction.id)
        _check_text(where, "rezumatul", contradiction.summary, policy)
        _check_text(where, "intrebarea", contradiction.question, policy)
        found.append(contradiction)
    return found


def load_content(root: Path | str | None = None) -> KnowledgeContent:
    """Citeste si valideaza tot continutul. Ridica `KnowledgeError` la prima abatere."""
    base = Path(root) if root is not None else default_knowledge_dir()
    if not base.is_dir():
        raise KnowledgeError(f"{base}: directorul bazei de cunostinte lipseste")
    policy = _load_policy(base)
    lexicon = _load_lexicon(base)
    entries: list[AuthoredEntry] = []
    ids: dict[str, str] = {}
    for path in sorted(base.glob("*.json")):
        if path.name.startswith("_"):
            continue
        raw = _read_json(path)
        if not isinstance(raw, dict) or not isinstance(raw.get("entries"), list) or not raw.get("topic"):
            raise KnowledgeError(f"{path.name}: asteptam un obiect cu `topic` si lista `entries`")
        topic = raw["topic"]
        if topic != path.stem:
            raise KnowledgeError(f"{path.name}: subiectul ({topic!r}) trebuie sa fie numele fisierului")
        for index, item in enumerate(raw["entries"]):
            where = f"{path.name}[{index}]"
            if not isinstance(item, dict):
                raise KnowledgeError(f"{where}: intrarea trebuie sa fie un obiect")
            try:
                entry = AuthoredEntry.model_validate({"topic": topic, **item})
            except ValidationError as exc:
                error = exc.errors()[0]
                raise KnowledgeError(f"{where}: {'.'.join(str(p) for p in error['loc'])}: {error['msg']}") from exc
            where = f"{path.name}:{entry.id}"
            _check_entry(where, entry, topic, policy)
            if entry.id in ids:
                raise KnowledgeError(f"{where}: id duplicat, apare si in {ids[entry.id]}")
            ids[entry.id] = path.name
            entries.append(entry)
    if not entries:
        raise KnowledgeError(f"{base}: nicio intrare in baza de cunostinte")
    return KnowledgeContent(
        entries=entries, policy=policy, lexicon=lexicon,
        contradictions=_load_contradictions(base, policy),
    )

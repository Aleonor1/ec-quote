"""Verificari in cod pe textul scris de model: sume, procente, termene, afirmatii despre material.

Textul care nu trece nu ajunge la client; motorul cere modelului sa il rescrie.
O afirmatie despre rezistenta sau material trebuie sa se regaseasca intr-o intrare din baza de
cunostinte intoarsa in aceasta runda sau in afirmatiile aprobate din rules.json.
"""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Iterable

_NUMBER = r"\d{1,3}(?:[.\s ]\d{3})+(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?"
_CURRENCY = r"lei|leu|ron|lej|eur|euro|€|usd|\$"
_MONEY_RE = re.compile(
    rf"(?P<a>{_NUMBER})\s*(?:de\s+)?(?:{_CURRENCY})(?!\w)|(?:(?<!\w)(?:{_CURRENCY}))\s*(?P<b>{_NUMBER})",
    re.IGNORECASE,
)
_FOREIGN_RE = re.compile(r"\d\s*(?:eur|euro|€|usd|\$)(?!\w)|(?:€|\$)\s*\d", re.IGNORECASE)
_PERCENT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:%|la suta|procente?|percent|szazalek)", re.IGNORECASE)
_DURATION_RE = re.compile(
    r"\b\d+(?:\s*-\s*\d+)?\s*(?:de\s+)?(?:ore|ora|zile|zi|saptamani|saptamana|hours?|days?|weeks?|nap|napon|ora|oran|het)\b")

# Categorii de afirmatii: fiecare trebuie sa apara si in sursele rundei ca sa poata fi spusa.
CLAIM_CATEGORIES: dict[str, re.Pattern] = {name: re.compile(pattern) for name, pattern in {
    "apa": r"\bap[aei]\b|impermeab|waterproof|\bwater\b|vizallo|\bviz\b",
    "umezeala": r"umezeal|umiditat|\bumed|moisture|humid|nedves",
    "UV": r"\buv\b|ultraviolet",
    "soare": r"\bsoare|solar|\bsun\b|sunlight|napfeny",
    "exterior": r"exterior|in aer liber|outdoor|kulter",
    "ulei": r"\bulei|grasim|\boil\b|olaj",
    "congelator": r"congelator|inghet|freezer|fagyaszt",
    "frigider": r"frigider|fridge|refrigerat|huto",
    "masina de spalat vase": r"spalat vase|dishwasher|mosogatogep",
    "microunde": r"microunde|microwave|mikrohull",
    "alimentar": r"alimentar|food|elelmiszer",
    "zgarieturi": r"zgari|scratch|karc",
    "rezistenta": r"rezist|resistan|durabil|durable|tartos|ellenall",
    "garantie": r"garant|guarant",
    "certificare": r"certific|tanusit",
    "ecologic": r"netoxic|ecologic|biodegrad|non-toxic|eco-friendly",
    "finisaj": r"lamin|\blac\b",
    "aderenta": r"nu se dezlip|nu se decolor",
}.items()}
_STRICT_TRIGGERS = re.compile("|".join(p.pattern for p in CLAIM_CATEGORIES.values()))


def normalize(text: str) -> str:
    """Litere mici, fara diacritice, spatii simple."""
    stripped = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped.lower()).strip()


def parse_amount(raw: str) -> Decimal | None:
    """Accepta 1.234,56 / 1 234,56 / 1234.56 / 1234,5 / 1234."""
    value = raw.replace(" ", "").replace(" ", "")
    if "," in value:
        value = value.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", value):
        value = value.replace(".", "")
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def money_mentions(text: str) -> list[Decimal | None]:
    found: list[Decimal | None] = []
    for match in _MONEY_RE.finditer(text):
        found.append(parse_amount(match.group("a") or match.group("b")))
    return found


def percent_mentions(text: str) -> list[Decimal]:
    values = (parse_amount(raw) for raw in _PERCENT_RE.findall(text))
    return [v for v in values if v is not None]


def _same_amount(left: Decimal, right: Decimal) -> bool:
    return left.quantize(Decimal("0.01")) == right.quantize(Decimal("0.01"))


def _claim_pattern(claim: str) -> re.Pattern:
    # Tolereaza flexiunea: "rezistenta" acopera si "rezistent", "rezistente".
    words = []
    for word in normalize(claim).split(" "):
        words.append(re.escape(word[:-2]) + r"\w*" if len(word) >= 6 else re.escape(word))
    return re.compile(r"\b" + r"\s+".join(words))


def check_text(
    text: str,
    *,
    allowed_amounts: Iterable[Decimal],
    allowed_percents: Iterable[Decimal],
    approved_claims: Iterable[str],
    catalog_terms: Iterable[str] = (),
    allowed_terms: Iterable[str] = (),
    sources: Iterable[str] = (),
) -> list[str]:
    """Lista de probleme (goala = textul poate pleca). Mesajele sunt pentru model, nu pentru client.

    `sources` sunt textele intrarilor din baza de cunostinte intoarse in aceasta runda.
    """
    problems: list[str] = []
    source_text = " ".join(sources)
    amounts = list(allowed_amounts) + [a for a in money_mentions(source_text) if a is not None]
    foreign = _FOREIGN_RE.search(text)
    for amount in money_mentions(text):
        if foreign or amount is None or not any(_same_amount(amount, known) for known in amounts):
            problems.append(
                "Textul contine o suma care nu provine din calculator (get_price, get_price_tiers) sau dintr-o "
                "intrare din baza de cunostinte. Nu scrie sume; preturile le compune sistemul prin "
                "create_checkout sau send_price_comparison.")
            break

    percents = list(allowed_percents) + percent_mentions(source_text)
    for value in percent_mentions(text):
        if not any(value == known for known in percents):
            problems.append("Textul contine un procent care nu provine din calculator. Nu promite reduceri.")
            break

    plain = normalize(text)
    plain_sources = normalize(source_text)
    for term in allowed_terms:
        plain = plain.replace(normalize(term), " ")
    for match in _DURATION_RE.finditer(plain):
        if match.group(0) not in plain_sources:
            problems.append(
                "Textul promite un termen in ore sau zile care nu vine din baza de cunostinte. Termenul de "
                "productie il adauga sistemul in oferta; pentru un termen mai scurt decat cel standard foloseste "
                "handoff cu motivul special_terms.")
            break

    for term in sorted((normalize(t) for t in catalog_terms if t), key=len, reverse=True):
        plain = plain.replace(term, " ")
    claims = list(approved_claims)
    backing = f"{plain_sources} {' '.join(normalize(c) for c in claims)}"
    unbacked = [name for name, pattern in CLAIM_CATEGORIES.items()
                if pattern.search(plain) and not pattern.search(backing)]
    if unbacked:
        problems.append(
            f"Textul face o afirmatie ({', '.join(unbacked)}) care nu se regaseste in nicio intrare din baza de "
            "cunostinte intoarsa in aceasta runda. Cauta cu search_knowledge si spune numai ce scrie acolo.")
    elif not plain_sources:
        # Fara intrari din baza: raman valabile doar formularile aprobate, intocmai.
        for claim in claims:
            plain = _claim_pattern(claim).sub(" ", plain)
        if _STRICT_TRIGGERS.search(plain):
            problems.append(
                "Textul face o afirmatie despre material care nu este in lista aprobata. Foloseste formularile "
                "aprobate exact cum sunt date sau cauta cu search_knowledge.")
    return problems

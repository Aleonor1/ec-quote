"""Verificari in cod pe textul scris de model: sume, procente, termene, afirmatii despre material.

Textul care nu trece nu ajunge la client; motorul cere modelului sa il rescrie.
"""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Iterable

_NUMBER = r"\d{1,3}(?:[.\s ]\d{3})+(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?"
_CURRENCY = r"lei|leu|ron|eur|euro|€|usd|\$"
_MONEY_RE = re.compile(
    rf"(?P<a>{_NUMBER})\s*(?:de\s+)?(?:{_CURRENCY})(?!\w)|(?:(?<!\w)(?:{_CURRENCY}))\s*(?P<b>{_NUMBER})",
    re.IGNORECASE,
)
_PERCENT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:%|la suta|procente?)", re.IGNORECASE)
_DURATION_RE = re.compile(r"\b\d+(?:\s*-\s*\d+)?\s*(?:de\s+)?(?:ore|ora|zile|zi|saptamani|saptamana)\b")
_CLAIM_TRIGGERS = re.compile(
    r"rezist|impermeab|waterproof|garant|lamin|\blac\b|certific|alimentar|netoxic|ecologic|biodegrad|"
    r"durabil|nu se dezlip|nu se decolor|frigider|congelator|masina de spalat")


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
) -> list[str]:
    """Lista de probleme (goala = textul poate pleca). Mesajele sunt pentru model, nu pentru client."""
    problems: list[str] = []
    amounts = list(allowed_amounts)
    for amount in money_mentions(text):
        if amount is None or not any(_same_amount(amount, known) for known in amounts):
            problems.append(
                "Textul contine o suma care nu provine din get_price sau get_price_tiers. "
                "Nu scrie sume; oferta cu preturi este compusa de sistem dupa create_checkout.")
            break

    percents = list(allowed_percents)
    for raw in _PERCENT_RE.findall(text):
        value = parse_amount(raw)
        if value is None or not any(value == known for known in percents):
            problems.append("Textul contine un procent care nu provine din calculator. Nu promite reduceri.")
            break

    plain = normalize(text)
    for term in allowed_terms:
        plain = plain.replace(normalize(term), " ")
    if _DURATION_RE.search(plain):
        problems.append(
            "Textul promite un termen in ore sau zile. Termenul de productie este adaugat de sistem in oferta; "
            "pentru un termen mai scurt decat cel standard foloseste handoff cu motivul special_terms.")

    for term in sorted((normalize(t) for t in catalog_terms if t), key=len, reverse=True):
        plain = plain.replace(term, " ")
    for claim in approved_claims:
        plain = _claim_pattern(claim).sub(" ", plain)
    if _CLAIM_TRIGGERS.search(plain):
        problems.append(
            "Textul face o afirmatie despre material care nu este in lista aprobata. "
            "Foloseste doar formularile aprobate, exact cum sunt date.")
    return problems

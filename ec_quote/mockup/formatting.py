"""Formatare romaneasca pentru bani, cantitati si date. Fara float."""
from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

MONTHS_RO = (
    "ianuarie", "februarie", "martie", "aprilie", "mai", "iunie",
    "iulie", "august", "septembrie", "octombrie", "noiembrie", "decembrie",
)


def _group_thousands(digits: str) -> str:
    out = []
    while len(digits) > 3:
        out.append(digits[-3:])
        digits = digits[:-3]
    out.append(digits)
    return ".".join(reversed(out))


def format_number(value: Decimal, min_decimals: int = 2, max_decimals: int = 2) -> str:
    """1234.5 -> "1.234,50". Rotunjire comerciala (jumatatea in sus)."""
    if not isinstance(value, Decimal):
        raise TypeError("banii sunt Decimal, nu %s" % type(value).__name__)
    if not value.is_finite():
        raise ValueError("valoare nefinita")
    if not 0 <= min_decimals <= max_decimals:
        raise ValueError("zecimale invalide")
    q = value.quantize(Decimal(1).scaleb(-max_decimals), rounding=ROUND_HALF_UP)
    sign = "-" if q < 0 else ""
    text = format(abs(q), "f")
    whole, _, frac = text.partition(".")
    while len(frac) > min_decimals and frac.endswith("0"):
        frac = frac[:-1]
    if sign and not (whole.strip("0") or frac.strip("0")):
        sign = ""
    grouped = _group_thousands(whole)
    return sign + (grouped + "," + frac if frac else grouped)


def format_lei(value: Decimal) -> str:
    """1234.5 -> "1.234,50 lei"."""
    return format_number(value, 2, 2) + " lei"


def format_unit_price(value: Decimal) -> str:
    """Pretul pe bucata pastreaza pana la 4 zecimale, ca sa nu ascunda sub-banii."""
    return format_number(value, 2, 4) + " lei"


def format_quantity(quantity: int) -> str:
    """1000 -> "1.000 buc"."""
    if isinstance(quantity, bool) or not isinstance(quantity, int):
        raise TypeError("cantitatea este int")
    sign = "-" if quantity < 0 else ""
    return sign + _group_thousands(str(abs(quantity))) + " buc"


def format_date_ro(value: date | datetime) -> str:
    """2026-12-03 -> "3 decembrie 2026". Data se foloseste asa cum a fost primita."""
    return "%d %s %d" % (value.day, MONTHS_RO[value.month - 1], value.year)

"""Textele trimise clientului care contin cifre sau politica: compuse numai de cod, din rezultatele uneltelor."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from ec_quote.contracts import FileReport, FileVerdict, HandoffReason, OfferLine, PriceQuote, TierOffer

from .rules import Rules, to_local

_WEEKDAYS = ["luni", "marți", "miercuri", "joi", "vineri", "sâmbătă", "duminică"]

ASSISTANT_SIGNATURE = "Sunt asistentul automat Etichete Creative. Pentru orice modificare, răspundeți la acest mesaj."


def format_money(amount: Decimal) -> str:
    """1234.5 -> 1.234,50"""
    quantized = amount.quantize(Decimal("0.01"))
    whole, _, cents = f"{quantized:.2f}".partition(".")
    sign = "-" if whole.startswith("-") else ""
    digits = whole.lstrip("-")
    groups = []
    while len(digits) > 3:
        groups.insert(0, digits[-3:])
        digits = digits[:-3]
    groups.insert(0, digits)
    return f"{sign}{'.'.join(groups)},{cents}"


def format_number(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return text.replace(".", ",")


def format_quantity(quantity: int) -> str:
    return f"{quantity:,}".replace(",", ".")


def build_lines(quote: PriceQuote, tiers: list[TierOffer], threshold_ex_vat: Decimal) -> list[OfferLine]:
    """Linia ceruta plus treptele superioare care raman sub pragul de predare."""
    lines = [OfferLine(
        label=f"{format_quantity(quote.choices.quantity)} buc", quantity=quote.choices.quantity,
        total_ex_vat=quote.total_ex_vat, total=quote.total, unit_price=quote.unit_price, highlighted=True)]
    for tier in sorted(tiers, key=lambda t: t.quantity):
        if tier.quantity <= quote.choices.quantity or tier.total_ex_vat > threshold_ex_vat:
            continue
        lines.append(OfferLine(
            label=f"{format_quantity(tier.quantity)} buc", quantity=tier.quantity,
            total_ex_vat=tier.total_ex_vat, total=tier.total, unit_price=tier.unit_price))
    return lines


def _line_text(line: OfferLine) -> str:
    return (f"{line.label}: {format_money(line.total_ex_vat)} lei fără TVA "
            f"({format_money(line.total)} lei cu TVA)")


def describe_choices(quote: PriceQuote, product_title: str) -> str:
    c = quote.choices
    parts = [product_title, c.shape, f"{format_number(c.width_cm)} x {format_number(c.height_cm)} cm", c.material_name]
    for group, choice in c.add_ons.items():
        parts.append(f"{group}: {choice}")
    if c.adhesive == "strong":
        parts.append("adeziv puternic")
    if c.white_print:
        parts.append("print alb")
    if c.cut != "none":
        parts.append("tăiere dublă" if c.cut == "double" else "tăiere pe spate")
    if c.urgent:
        parts.append("regim de urgență")
    return ", ".join(p for p in parts if p)


def file_note(report: FileReport | None) -> str:
    if report is None:
        return ""
    if report.verdict == FileVerdict.WEAK:
        return ("Notă: fișierul trimis se poate tipări, dar calitatea lui la această dimensiune este sub cea "
                "recomandată. Dacă aveți o variantă vectorială sau la rezoluție mai mare, o puteți trimite aici.")
    if report.verdict == FileVerdict.UNUSABLE:
        return ("Notă: fișierul trimis nu poate fi folosit la tipar în forma actuală. "
                "Vă rugăm să ne trimiteți o variantă vectorială sau la rezoluție mai mare.")
    return ""


def build_offer_text(
    quote: PriceQuote, lines: list[OfferLine], product_title: str, production_term: str,
    valid_until: datetime, report: FileReport | None,
) -> str:
    """Textul ofertei, fara linkul de plata (linkul se adauga la trimitere)."""
    main = next(line for line in lines if line.highlighted)
    rows = [f"Oferta dumneavoastră: {describe_choices(quote, product_title)}.", _line_text(main)]
    others = [line for line in lines if not line.highlighted]
    if others:
        rows.append("Alte cantități:")
        rows.extend(f"- {_line_text(line)}" for line in others)
    rows.append(f"Termen de producție: {production_term}.")
    rows.append(f"Ofertă valabilă până la {to_local(valid_until).strftime('%d.%m.%Y')}.")
    note = file_note(report)
    if note:
        rows.append(note)
    return "\n".join(rows)


def with_payment_link(offer_text: str, quote: PriceQuote, invoice_url: str) -> str:
    return (f"{offer_text}\nLink de plată pentru {format_quantity(quote.choices.quantity)} buc: {invoice_url}\n"
            f"{ASSISTANT_SIGNATURE}")


def _when(rules: Rules, now: datetime) -> str:
    local = to_local(now)
    opening = rules.next_business_open(local)
    hour = opening.strftime("%H:%M")
    days = (opening.date() - local.date()).days
    if days == 0:
        return f"astăzi, la ora {hour}"
    if days == 1:
        return f"mâine, la ora {hour}"
    return f"{_WEEKDAYS[opening.weekday()]}, {opening.strftime('%d.%m')}, la ora {hour}"


def handoff_text(rules: Rules, reason: HandoffReason, now: datetime) -> str:
    if reason == HandoffReason.COMPLAINT:
        lead = "Ne pare rău pentru situația creată. Am transmis mesajul dumneavoastră unui coleg."
    elif reason == HandoffReason.FILE_UNUSABLE:
        lead = "Fișierul trimis nu poate fi folosit la tipar în forma actuală. Am transmis cererea unui coleg din echipa de grafică."
    elif reason == HandoffReason.NOT_UNDERSTOOD:
        lead = "Pentru a nu vă reține, am transmis cererea dumneavoastră unui coleg."
    else:
        lead = "Vă mulțumim. Am transmis cererea dumneavoastră unui coleg."
    if rules.is_business_hours(now):
        return f"{lead} Veți primi un răspuns în cel mai scurt timp."
    return f"{lead} Suntem în afara programului; un coleg revine {_when(rules, now)}."


NOT_UNDERSTOOD_TEXT = ("Îmi cer scuze, nu sunt sigur că am înțeles cererea. Îmi puteți spune ce produs doriți, "
                       "la ce dimensiune și în ce cantitate?")

OFFER_LIMIT_TEXT = "Am atins numărul maxim de oferte automate pentru astăzi."

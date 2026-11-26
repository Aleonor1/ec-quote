"""Textele care contin cifre sau politica: compuse numai de cod, din rezultatele uneltelor."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from ec_quote.contracts import FileReport, FileVerdict, HandoffReason, OfferLine, PriceQuote, TierOffer

from .rules import Rules, to_local

_WEEKDAYS = ["luni", "marți", "miercuri", "joi", "vineri", "sâmbătă", "duminică"]

ASSISTANT_SIGNATURE = "Sunt asistentul automat Etichete Creative. Pentru orice modificare, răspundeți la acest mesaj."

LANGUAGES = ("ro", "en", "hu")

# Etichetele textelor compuse de cod, pe limba clientului. Sumele raman in lei, in formatul site-ului.
_L = {
    "ro": {
        "offer": "Oferta dumneavoastră", "pcs": "buc", "ex": "lei fără TVA", "inc": "lei cu TVA",
        "others": "Alte cantități:", "term": "Termen de producție", "valid": "Ofertă valabilă până la",
        "link": "Link de plată", "link_for": "Link de plată pentru", "total": "Total", "unit": "lei/buc cu TVA",
        "promo": "Prețul include promoția activă de", "tiers": "Cantități mai mari:",
        "strong": "adeziv puternic", "white": "print alb", "double": "tăiere dublă", "back": "tăiere pe spate",
        "urgent": "regim de urgență",
        "weak": ("Notă: fișierul trimis se poate tipări, dar calitatea lui la această dimensiune este sub cea "
                 "recomandată. Dacă aveți o variantă vectorială sau la rezoluție mai mare, o puteți trimite aici, "
                 "ca document, pentru a nu fi comprimată."),
        "unusable": ("Notă: fișierul trimis nu poate fi folosit la tipar în forma actuală. "
                     "Vă rugăm să ne trimiteți o variantă vectorială sau la rezoluție mai mare, ca document."),
    },
    "en": {
        "offer": "Your quote", "pcs": "pcs", "ex": "lei excl. VAT", "inc": "lei incl. VAT",
        "others": "Other quantities:", "term": "Production time", "valid": "Quote valid until",
        "link": "Payment link", "link_for": "Payment link for", "total": "Total", "unit": "lei/pc incl. VAT",
        "promo": "The price includes the active promotion of", "tiers": "Larger quantities:",
        "strong": "strong adhesive", "white": "white print", "double": "double cut", "back": "back cut",
        "urgent": "rush order",
        "weak": ("Note: the file you sent can be printed, but its quality at this size is below what we recommend. "
                 "If you have a vector or higher resolution version, please send it here as a document."),
        "unusable": ("Note: the file you sent cannot be used for printing as it is. "
                     "Please send a vector or higher resolution version, as a document."),
    },
    "hu": {
        "offer": "Az Ön ajánlata", "pcs": "db", "ex": "lej ÁFA nélkül", "inc": "lej ÁFA-val",
        "others": "További mennyiségek:", "term": "Gyártási idő", "valid": "Az ajánlat érvényes eddig",
        "link": "Fizetési link", "link_for": "Fizetési link ehhez:", "total": "Összesen", "unit": "lej/db ÁFA-val",
        "promo": "Az ár tartalmazza az aktív promóciót:", "tiers": "Nagyobb mennyiségek:",
        "strong": "erős ragasztó", "white": "fehér nyomat", "double": "dupla vágás", "back": "hátoldali vágás",
        "urgent": "sürgős gyártás",
        "weak": ("Megjegyzés: a küldött fájl nyomtatható, de a minősége ennél a méretnél az ajánlott alatt van. "
                 "Ha van vektoros vagy nagyobb felbontású változata, kérjük, küldje el dokumentumként."),
        "unusable": ("Megjegyzés: a küldött fájl jelenlegi formájában nem használható nyomtatáshoz. "
                     "Kérjük, küldjön vektoros vagy nagyobb felbontású változatot dokumentumként."),
    },
}


def labels(language: str | None) -> dict:
    return _L.get(language or "ro", _L["ro"])


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


def money_pair(total_ex_vat: Decimal, total: Decimal, language: str | None = None) -> str:
    lab = labels(language)
    return f"{format_money(total_ex_vat)} {lab['ex']} ({format_money(total)} {lab['inc']})"


def choice_parts(quote: PriceQuote, product_title: str, language: str | None = None) -> list[str]:
    """Descrierea unei linii, pe bucati, ca sa se poata arata doar ce difera intre variante."""
    lab = labels(language)
    c = quote.choices
    parts = [f"{format_quantity(c.quantity)} {lab['pcs']}", product_title, c.shape,
             f"{format_number(c.width_cm)} x {format_number(c.height_cm)} cm", c.material_name]
    parts += [f"{group}: {choice}" for group, choice in c.add_ons.items()]
    if c.adhesive == "strong":
        parts.append(lab["strong"])
    if c.white_print:
        parts.append(lab["white"])
    if c.cut != "none":
        parts.append(lab["double"] if c.cut == "double" else lab["back"])
    if c.urgent:
        parts.append(lab["urgent"])
    return [p for p in parts if p]


def describe_choices(quote: PriceQuote, product_title: str, language: str | None = None) -> str:
    return ", ".join(choice_parts(quote, product_title, language)[1:])


def promo_percent(quote: PriceQuote) -> Decimal:
    try:
        return Decimal(str(quote.breakdown.get("promoPercent") or 0))
    except (ArithmeticError, ValueError):
        return Decimal(0)


def build_lines(quote: PriceQuote, tiers: list[TierOffer], threshold_ex_vat: Decimal,
                language: str | None = None) -> list[OfferLine]:
    """Linia ceruta plus treptele superioare care raman sub pragul de predare."""
    pcs = labels(language)["pcs"]
    lines = [OfferLine(
        label=f"{format_quantity(quote.choices.quantity)} {pcs}", quantity=quote.choices.quantity,
        total_ex_vat=quote.total_ex_vat, total=quote.total, unit_price=quote.unit_price, highlighted=True)]
    for tier in sorted(tiers, key=lambda t: t.quantity):
        if tier.quantity <= quote.choices.quantity or tier.total_ex_vat > threshold_ex_vat:
            continue
        lines.append(OfferLine(
            label=f"{format_quantity(tier.quantity)} {pcs}", quantity=tier.quantity,
            total_ex_vat=tier.total_ex_vat, total=tier.total, unit_price=tier.unit_price))
    return lines


def quote_line(quote: PriceQuote, product_title: str, language: str | None = None) -> OfferLine:
    """O linie de oferta cu descrierea completa (oferte cu mai multe produse, comparatii)."""
    return OfferLine(
        label=", ".join(choice_parts(quote, product_title, language)), quantity=quote.choices.quantity,
        total_ex_vat=quote.total_ex_vat, total=quote.total, unit_price=quote.unit_price, highlighted=True)


def _line_text(line: OfferLine, language: str | None) -> str:
    return f"{line.label}: {money_pair(line.total_ex_vat, line.total, language)}"


def file_note(report: FileReport | None, language: str | None = None) -> str:
    if report is None:
        return ""
    if report.verdict == FileVerdict.WEAK:
        return labels(language)["weak"]
    if report.verdict == FileVerdict.UNUSABLE:
        return labels(language)["unusable"]
    return ""


def _footer(production_term: str, valid_until: datetime, report: FileReport | None, language: str | None) -> list[str]:
    lab = labels(language)
    rows = [f"{lab['term']}: {production_term}.",
            f"{lab['valid']} {to_local(valid_until).strftime('%d.%m.%Y')}."]
    note = file_note(report, language)
    if note:
        rows.append(note)
    return rows


def build_offer_text(
    quote: PriceQuote, lines: list[OfferLine], product_title: str, production_term: str,
    valid_until: datetime, report: FileReport | None, language: str | None = None,
) -> str:
    """Textul ofertei pentru o linie, fara linkul de plata (linkul se adauga la trimitere)."""
    lab = labels(language)
    main = next(line for line in lines if line.highlighted)
    rows = [f"{lab['offer']}: {describe_choices(quote, product_title, language)}.", _line_text(main, language)]
    promo = promo_percent(quote)
    if promo > 0:
        rows.append(f"{lab['promo']} {format_number(promo)}%.")
    others = [line for line in lines if not line.highlighted]
    if others:
        rows.append(lab["others"])
        rows.extend(f"- {_line_text(line, language)}" for line in others)
    rows += _footer(production_term, valid_until, report, language)
    return "\n".join(rows)


def sum_lines(lines: list[OfferLine]) -> tuple[Decimal, Decimal]:
    """Totalul unei oferte cu mai multe linii: adunare Decimal a sumelor din calculator."""
    return (sum((line.total_ex_vat for line in lines), Decimal(0)),
            sum((line.total for line in lines), Decimal(0)))


def build_multi_offer_text(lines: list[OfferLine], production_term: str, valid_until: datetime,
                           report: FileReport | None, language: str | None = None) -> str:
    lab = labels(language)
    rows = [f"{lab['offer']}:"]
    rows += [f"{i}. {_line_text(line, language)}" for i, line in enumerate(lines, start=1)]
    total_ex_vat, total = sum_lines(lines)
    rows.append(f"{lab['total']}: {money_pair(total_ex_vat, total, language)}")
    rows += _footer(production_term, valid_until, report, language)
    return "\n".join(rows)


def build_comparison_text(quotes: list[PriceQuote], titles: list[str], tiers: list[TierOffer] | None,
                          intro: str, closing: str, language: str | None = None) -> str:
    """Comparatie compacta: ce au variantele in comun apare o singura data, apoi cate un rand pe varianta."""
    lab = labels(language)
    described = [choice_parts(q, t, language) for q, t in zip(quotes, titles)]
    common = [p for p in described[0] if all(p in parts for parts in described)]
    rows = [intro] if intro else []
    if common and len(quotes) > 1:
        rows.append(", ".join(common) + ":")
    for index, (quote, parts) in enumerate(zip(quotes, described), start=1):
        own = [p for p in parts if p not in common] if len(quotes) > 1 else parts
        label = ", ".join(own or parts[:1])
        prefix = f"{index}. " if len(quotes) > 1 else ""
        rows.append(f"{prefix}{label}: {money_pair(quote.total_ex_vat, quote.total, language)}, "
                    f"{format_money(quote.unit_price)} {lab['unit']}")
        promo = promo_percent(quote)
        if promo > 0:
            rows.append(f"{lab['promo']} {format_number(promo)}%.")
    if tiers:
        rows.append(lab["tiers"])
        for tier in sorted(tiers, key=lambda t: t.quantity):
            rows.append(f"- {format_quantity(tier.quantity)} {lab['pcs']}: "
                        f"{money_pair(tier.total_ex_vat, tier.total, language)}, "
                        f"{format_money(tier.unit_price)} {lab['unit']}")
    if closing:
        rows.append(closing)
    return "\n".join(rows)


def with_payment_link(offer_text: str, quote: PriceQuote, invoice_url: str, signature: bool = True,
                      language: str | None = None) -> str:
    lab = labels(language)
    text = f"{offer_text}\n{lab['link_for']} {format_quantity(quote.choices.quantity)} {lab['pcs']}: {invoice_url}"
    # Semnatura de asistent automat apare doar cand mesajul pleaca fara om.
    return f"{text}\n{ASSISTANT_SIGNATURE}" if signature else text


# ---------- motive unpriced, traduse intr-o sugestie utila ----------

def unpriced_hint(reason: str, details: dict) -> str:
    """Ce i se poate spune clientului pentru fiecare cod al calculatorului. Cifrele vin din `details`."""
    def value(key: str) -> str:
        raw = details.get(key)
        return format_number(Decimal(str(raw))) if raw is not None else ""

    option = str(details.get("option") or "")
    hints = {
        "size_below_minimum": f"Dimensiunea este sub minimul produsului{': ' + value('minCm') + ' cm' if value('minCm') else ''}. Propune dimensiunea minima sau intreaba ce dimensiune doreste.",
        "size_above_maximum": f"Dimensiunea depaseste maximul produsului{': ' + value('maxCm') + ' cm' if value('maxCm') else ''}. Propune maximul sau preda unui coleg pentru o lucrare speciala.",
        "quantity_below_minimum": f"Cantitatea este sub comanda minima{': ' + value('minQuantity') + ' buc' if value('minQuantity') else ''}. Ofera pretul pentru cantitatea minima.",
        "quantity_above_maximum": f"Cantitatea depaseste maximul din calculator{': ' + value('maxQuantity') + ' buc' if value('maxQuantity') else ''}. Preda unui coleg (handoff, value_over_threshold nu se alege de tine; foloseste not_in_calculator).",
        "urgency_quantity_exceeded": f"Regimul de urgenta este disponibil numai pana la{' ' + value('maxQuantity') + ' buc' if value('maxQuantity') else ' o cantitate limita'}. Ofera pretul fara urgenta sau preda unui coleg.",
        "option_unavailable": f"Optiunea {option or 'ceruta'} nu este disponibila la acest produs. Ofera pretul fara ea si spune-i clientului.",
        "unknown_add_on": f"Optiunea {option or 'ceruta'} nu exista in catalog pentru acest produs. Alege din catalog sau renunta la ea.",
        "custom_size_disabled": "Produsul se face numai la dimensiunile predefinite din catalog. Propune cea mai apropiata dimensiune din lista.",
        "sample_not_allowed": "Mostra nu este disponibila pentru acest produs. Cauta in baza de cunostinte ce se poate oferi sau preda unui coleg.",
        "unknown_product": "Produsul nu exista in calculator. Alege un product_id din catalog sau preda unui coleg (not_in_calculator).",
        "unknown_material": "Materialul nu exista la acest produs. Alege din catalog sau preda unui coleg (not_in_calculator).",
        "unknown_shape": "Forma nu exista la acest produs. Alege din catalog.",
        "no_price": "Calculatorul nu are pret pentru aceasta combinatie. Preda unui coleg (not_in_calculator).",
    }
    return hints.get(reason, "Motiv necunoscut. Daca nu poti corecta alegerea din catalog, preda unui coleg.")


# ---------- predare ----------

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
    """Mesajul catre client in modul autonom (chatul de pe site)."""
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


_STAFF_NOTES = {
    HandoffReason.NOT_IN_CALCULATOR: "Produsul, materialul sau opțiunea cerută nu există în calculator; este nevoie de o ofertă manuală.",
    HandoffReason.SPECIAL_TERMS: "Clientul cere condiții speciale (reducere, termen mai scurt decât cel standard sau facturare specială).",
    HandoffReason.COMPLAINT: "Reclamație sau client nemulțumit; răspunsul trebuie dat de un om.",
    HandoffReason.OFFER_LIMIT: "S-a atins numărul maxim de oferte automate pe zi pentru acest contact.",
    HandoffReason.FILE_UNUSABLE: "Fișierul clientului este inutilizabil și după încercările permise; este nevoie de grafică.",
    HandoffReason.CUSTOMER_ASKED: "Clientul are nevoie de un om (a cerut asta sau întreabă ceva ce numai un om poate verifica).",
    HandoffReason.NOT_UNDERSTOOD: "Asistentul nu a putut pregăti un răspuns sigur pentru această cerere.",
}

_ASSIST_DRAFTS = {
    HandoffReason.COMPLAINT: "Ne pare rău pentru situația creată. Verificăm imediat și revenim cu un răspuns.",
    HandoffReason.FILE_UNUSABLE: ("Fișierul trimis nu poate fi folosit la tipar în forma actuală. "
                                  "Ne puteți trimite o variantă vectorială sau la rezoluție mai mare, ca document?"),
}

HOLDING_TEXT = "Verificăm acest detaliu și revenim imediat cu un răspuns."


def staff_note(rules: Rules, reason: HandoffReason, details: str, quote: PriceQuote | None) -> str:
    """Explicatia pentru om. Nu se trimite clientului, deci poate contine pretul calculatorului."""
    lead = _STAFF_NOTES.get(reason, "Este nevoie de decizia unui om.")
    price = ""
    if quote is not None:
        price = (f" Preț calculator pentru {format_quantity(quote.choices.quantity)} buc: "
                 f"{money_pair(quote.total_ex_vat, quote.total)}.")
    if reason == HandoffReason.VALUE_OVER_THRESHOLD:
        lead = (f"Valoare peste pragul de {format_money(rules.handoff_value_threshold_ron_ex_vat)} lei fără TVA. "
                "Verificați oferta înainte de a o trimite.")
    note = f"{lead}{price}"
    return f"{note} Detalii: {details}" if details else note


def assist_draft(reason: HandoffReason) -> str:
    return _ASSIST_DRAFTS.get(reason, "")


def file_staff_note(report: FileReport | None) -> str:
    if report is None or report.verdict == FileVerdict.OK:
        return ""
    label = "calitate slabă, se poate tipări" if report.verdict == FileVerdict.WEAK else "inutilizabil la tipar"
    problems = f" ({', '.join(report.problems)})" if report.problems else ""
    return f"Fișierul clientului: {label}{problems}."


NOT_UNDERSTOOD_TEXT = ("Îmi cer scuze, nu sunt sigur că am înțeles cererea. Îmi puteți spune ce produs doriți, "
                       "la ce dimensiune și în ce cantitate?")

OFFER_LIMIT_TEXT = "Am atins numărul maxim de oferte automate pentru astăzi."

VOICE_TEXT = ("Nu putem asculta mesajele vocale în acest chat. Ne puteți scrie pe scurt ce produs doriți, "
              "la ce dimensiune și în ce cantitate?")

UNSUPPORTED_FILE_TEXT = ("Nu putem folosi acest tip de fișier. Ne puteți trimite grafica în format PDF, AI, SVG "
                         "sau PNG, ca document, și câteva cuvinte despre ce doriți?")

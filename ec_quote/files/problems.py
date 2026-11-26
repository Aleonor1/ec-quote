"""Codurile stabile de probleme, gravitatea lor si textele pentru client (romana)."""
from __future__ import annotations

from decimal import Decimal
from typing import Mapping

from ec_quote.contracts import FileReport, FileVerdict

LOW_DPI = "low_dpi"
VERY_LOW_DPI = "very_low_dpi"
ASPECT_MISMATCH = "aspect_mismatch"
OPAQUE_BACKGROUND = "opaque_background"
MULTI_PAGE = "multi_page"
UNSUPPORTED_FORMAT = "unsupported_format"
UNREADABLE = "unreadable"
TOO_LARGE = "too_large"
CMYK_JPEG = "cmyk_jpeg"
TEXT_NOT_OUTLINED = "text_not_outlined"
LINKED_IMAGE = "linked_image"

# fisierul nu poate fi folosit asa cum este
UNUSABLE_CODES = frozenset({UNSUPPORTED_FORMAT, UNREADABLE, TOO_LARGE, VERY_LOW_DPI})
# se poate tipari, dar clientul trebuie anuntat
WEAK_CODES = frozenset({LOW_DPI, ASPECT_MISMATCH, MULTI_PAGE, CMYK_JPEG, TEXT_NOT_OUTLINED, LINKED_IMAGE})
# doar observatii, nu schimba verdictul
NOTE_CODES = frozenset({OPAQUE_BACKGROUND})

ALL_CODES = UNUSABLE_CODES | WEAK_CODES | NOTE_CODES


def verdict_for(problems: list[str]) -> FileVerdict:
    codes = set(problems)
    if codes & UNUSABLE_CODES:
        return FileVerdict.UNUSABLE
    if codes & WEAK_CODES:
        return FileVerdict.WEAK
    return FileVerdict.OK


def _dpi_text(report: FileReport) -> str:
    if report.dpi_at_size is None:
        return ""
    return f" (aproximativ {int(report.dpi_at_size)} DPI la dimensiunea cerută)"


def describe_problems(report: FileReport, rules: Mapping | None = None) -> list[str]:
    """Cate o propozitie scurta pentru client, in ordinea codurilor din raport."""
    if rules is None:
        from ec_quote.files.checker import load_rules

        rules = load_rules()
    min_ok = int(Decimal(str(rules.get("min_dpi_ok", 300))))
    dpi = _dpi_text(report)

    texts = {
        LOW_DPI: (
            f"Rezoluția imaginii este sub cea recomandată{dpi}; pentru un print clar "
            f"recomandăm minimum {min_ok} DPI. Se poate tipări, dar detaliile fine pot ieși "
            "ușor neclare. Dacă aveți o variantă mai mare sau vectorială (PDF, AI, SVG), "
            "vă rugăm să o trimiteți; la cerere, putem mări rezoluția contra cost."
        ),
        VERY_LOW_DPI: (
            f"Rezoluția imaginii este prea mică pentru dimensiunea cerută{dpi}, iar printul "
            "ar ieși neclar. Vă rugăm să trimiteți fișierul original, la rezoluție mare sau "
            "vectorial (PDF, AI, SVG). Dacă nu îl aveți, putem vectoriza grafica contra cost."
        ),
        ASPECT_MISMATCH: (
            "Proporțiile fișierului diferă de dimensiunea cerută. Vă rugăm să confirmați "
            "dimensiunea dorită sau să trimiteți un fișier cu aceleași proporții; altfel, "
            "grafica va fi încadrată proporțional în formatul ales, fără deformare."
        ),
        OPAQUE_BACKGROUND: (
            "Imaginea are fundal plin, fără transparență. Pentru o etichetă cu altă formă "
            "decât dreptunghiulară, fundalul se va tipări împreună cu grafica. Dacă doriți "
            "doar grafica, trimiteți un PNG cu fundal transparent sau un fișier vectorial; "
            "la cerere, putem elimina fundalul prin vectorizare contra cost."
        ),
        MULTI_PAGE: (
            "Fișierul are mai multe pagini. Am analizat doar prima pagină; vă rugăm să ne "
            "spuneți ce pagină tipărim sau să trimiteți câte un fișier pentru fiecare model."
        ),
        UNSUPPORTED_FORMAT: (
            "Acest tip de fișier nu poate fi folosit pentru tipar. Vă rugăm să trimiteți "
            "grafica în format PDF, AI (salvat compatibil PDF), SVG, PNG, JPG, TIFF sau WEBP."
        ),
        UNREADABLE: (
            "Fișierul nu a putut fi deschis; este posibil să fie deteriorat sau protejat cu "
            "parolă. Vă rugăm să îl exportați din nou și să îl retrimiteți."
        ),
        TOO_LARGE: (
            "Fișierul este prea mare pentru a fi verificat automat. Vă rugăm să trimiteți o "
            "variantă mai mică, de exemplu un PDF sau un PNG la dimensiunea finală, la "
            f"{min_ok} DPI."
        ),
        CMYK_JPEG: (
            "Imaginea este un JPG în modul de culoare CMYK. Se poate tipări, însă culorile "
            "pot diferi ușor de ce vedeți pe ecran. Pentru culori exacte, recomandăm un PDF "
            "sau un fișier vectorial."
        ),
        TEXT_NOT_OUTLINED: (
            "Fișierul conține text cu fonturi neîncorporate, care pot fi înlocuite la tipar. "
            "Vă rugăm să convertiți textele în curbe (outline) sau să încorporați fonturile "
            "și să retrimiteți fișierul."
        ),
        LINKED_IMAGE: (
            "Fișierul face trimitere la imagini externe, care nu sunt incluse în el. Vă "
            "rugăm să încorporați imaginile în fișier (embed) și să îl retrimiteți."
        ),
    }
    out: list[str] = []
    seen: set[str] = set()
    for code in report.problems:
        if code in seen:
            continue
        seen.add(code)
        text = texts.get(code)
        if text:
            out.append(text)
    return out

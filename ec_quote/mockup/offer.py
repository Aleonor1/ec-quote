"""Imaginea unica de oferta (1080x1350, pentru WhatsApp): mockup, tabel de pret, termen, valabilitate.

Codul deseneaza tot textul. Sumele sunt exact cele primite in OfferLine, doar formatate.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps, UnidentifiedImageError

from ..contracts import OfferLine
from .compose import digest
from .errors import OfferImageError
from .fonts import load_font
from .formatting import format_date_ro, format_lei, format_quantity, format_unit_price

OFFER_SIZE = (1080, 1350)
MAX_LINES = 8
BRAND = "Etichete Creative"
TITLE = "Ofertă de preț"
HEADERS = ("Cantitate", "Preț / buc", "Total fără TVA", "Total cu TVA")
REQUESTED_TAG = "Cantitatea cerută"
TERM_LABEL = "Termen de producție:"
VALID_LABEL = "Ofertă valabilă până la"

_S = 2  # se deseneaza la dublu si se micsoreaza, pentru muchii curate
_NAVY = (26, 26, 46)
_LIME = (215, 223, 35)
_WHITE = (255, 255, 255)
_PAPER = (250, 250, 252)
_ROW = (240, 240, 245)
_GRAY = (104, 108, 122)
_SOFT = (190, 193, 206)
_ELLIPSIS = "..."

_MARGIN = 56
_FOOTER_H = 92
_COLS = (0.0, 0.25, 0.44, 0.70, 1.0)  # marginile coloanelor, ca fractii din latimea randului


def clean_text(text: str) -> str:
    """Un singur rand, fara caractere de control, fara linii lungi de pauza si fara emoji."""
    out = []
    for ch in unicodedata.normalize("NFC", text or ""):
        cat = unicodedata.category(ch)
        if ch in "‒–—―−":
            out.append("-")
        elif cat.startswith("Z") or ch in "\t\n\r":
            out.append(" ")
        elif cat[0] == "C" or cat in ("So", "Sk", "Mn", "Me") or ord(ch) > 0xFFFF:
            continue
        else:
            out.append(ch)
    return " ".join("".join(out).split())


@dataclass(frozen=True)
class OfferRow:
    quantity: str
    unit_price: str
    total_ex_vat: str
    total: str
    note: str          # randul mic de sub cantitate
    highlighted: bool


@dataclass(frozen=True)
class OfferContent:
    """Tot textul care ajunge in imagine. Testele verifica aici ca nu apar alte sume."""

    subtitle: str
    rows: tuple[OfferRow, ...]
    term: str
    valid_until: str

    def all_text(self) -> list[str]:
        texts = [BRAND, TITLE, *HEADERS, self.subtitle, TERM_LABEL, self.term,
                 VALID_LABEL, self.valid_until]
        for row in self.rows:
            texts += [row.quantity, row.unit_price, row.total_ex_vat, row.total, row.note]
        return [t for t in texts if t]


def build_content(lines: list[OfferLine], production_term: str, valid_until: datetime) -> OfferContent:
    if not lines:
        raise OfferImageError("oferta nu are nicio linie")
    if len(lines) > MAX_LINES:
        raise OfferImageError("prea multe linii pentru o singura imagine: %d" % len(lines))
    labels = [clean_text(line.label) for line in lines]
    shared = len(set(labels)) == 1
    rows = []
    for line, label in zip(lines, labels):
        parts = [REQUESTED_TAG] if line.highlighted else []
        if not shared and label:
            parts.append(label)
        rows.append(OfferRow(
            quantity=format_quantity(line.quantity),
            unit_price=format_unit_price(line.unit_price),
            total_ex_vat=format_lei(line.total_ex_vat),
            total=format_lei(line.total),
            note=" · ".join(parts),
            highlighted=line.highlighted,
        ))
    return OfferContent(
        subtitle=labels[0] if shared else "",
        rows=tuple(rows),
        term=clean_text(production_term),
        valid_until=format_date_ro(valid_until),
    )


def offer_digest(mockup_path: str | None, lines: list[OfferLine], production_term: str,
                 valid_until: datetime) -> str:
    mockup = Path(mockup_path).read_bytes() if mockup_path and Path(mockup_path).is_file() else b""
    return digest(
        mockup,
        "\n".join(line.model_dump_json() for line in lines).encode("utf-8"),
        production_term.encode("utf-8"),
        valid_until.isoformat().encode("utf-8"),
    )


# ---------- desen ----------

def _font(size: int, bold: bool = False):
    return load_font(size * _S, "bold" if bold else "regular")


def _width(draw: ImageDraw.ImageDraw, text: str, font) -> float:
    return draw.textlength(text, font=font)


def _truncate(draw: ImageDraw.ImageDraw, text: str, font, max_width: float) -> str:
    if _width(draw, text, font) <= max_width:
        return text
    while text and _width(draw, text.rstrip() + _ELLIPSIS, font) > max_width:
        text = text[:-1]
    return text.rstrip() + _ELLIPSIS


def _fit(draw: ImageDraw.ImageDraw, text: str, size: int, bold: bool, max_width: float, min_size: int = 16):
    """Cel mai mare font, pana la `size`, la care textul incape pe latime."""
    while size > min_size and _width(draw, text, _font(size, bold)) > max_width:
        size -= 1
    return _font(size, bold)


def _wrap(draw: ImageDraw.ImageDraw, words: list[tuple[str, object]], max_width: float,
          max_lines: int) -> list[list[tuple[str, object]]]:
    """Impartire pe randuri a unor cuvinte cu fonturi diferite; ultimul rand se taie cu "..."."""
    lines: list[list[tuple[str, object]]] = [[]]
    used = 0.0
    for index, (word, font) in enumerate(words):
        space = _width(draw, " ", font) if lines[-1] else 0.0
        w = _width(draw, word, font)
        if lines[-1] and used + space + w > max_width:
            if len(lines) == max_lines:
                rest = " ".join(t for t, _ in words[index:])
                room = max_width - used - space
                cut = _truncate(draw, rest, font, room)
                if cut != _ELLIPSIS and room > 0:
                    lines[-1].append((cut, font))
                else:
                    last, last_font = lines[-1][-1]
                    lines[-1][-1] = (_truncate(draw, last + " " + rest, last_font,
                                               _width(draw, last, last_font)), last_font)
                return lines
            lines.append([])
            used, space = 0.0, 0.0
        if not lines[-1] and w > max_width:
            word = _truncate(draw, word, font, max_width)
            w = _width(draw, word, font)
        lines[-1].append((word, font))
        used += space + w
    return lines


def _draw_words(draw: ImageDraw.ImageDraw, x: float, baseline: float,
                line: list[tuple[str, object]], fill) -> None:
    for i, (word, font) in enumerate(line):
        if i:
            x += _width(draw, " ", font)
        draw.text((x, baseline), word, font=font, fill=fill, anchor="ls")
        x += _width(draw, word, font)


def _hero(mockup_path: str, size: tuple[int, int]) -> Image.Image:
    """Mockupul decupat pe zona de sus; daca s-ar pierde prea mult, intreg pe un fundal estompat."""
    try:
        with Image.open(mockup_path) as im:
            mock = ImageOps.exif_transpose(im).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise OfferImageError("mockupul nu se poate citi: %s" % mockup_path) from exc
    w, h = size
    scale = max(w / mock.width, h / mock.height)
    visible = (w * h) / (mock.width * mock.height * scale * scale)
    if visible >= 0.7:
        return ImageOps.fit(mock, size, Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    hero = ImageOps.fit(mock, size, Image.Resampling.BILINEAR).filter(ImageFilter.GaussianBlur(24 * _S))
    hero = Image.blend(hero, Image.new("RGB", size, _PAPER), 0.35)
    inner = ImageOps.contain(mock, size, Image.Resampling.LANCZOS)
    hero.paste(inner, ((w - inner.width) // 2, (h - inner.height) // 2))
    return hero


def _content_height(content: OfferContent, row_h: int, with_title: bool) -> int:
    n = len(content.rows)
    subtitle = 84 if content.subtitle else 0
    return 36 + (54 if with_title else 0) + subtitle + 26 + 34 + n * row_h + (n - 1) * 10 + 30 + 2 * 44 + 16


def render_offer(mockup_path: str | None, lines: list[OfferLine], production_term: str,
                 valid_until: datetime) -> Image.Image:
    content = build_content(lines, production_term, valid_until)
    width, height = OFFER_SIZE
    n = len(content.rows)
    body_bottom = height - _FOOTER_H

    # inaltimi: mockupul primeste ce ramane dupa tabel
    row_h = 96 if mockup_path is None else 88
    if mockup_path is None:
        while _content_height(content, row_h, False) > body_bottom - 250 and row_h > 60:
            row_h -= 4
        # antetul de brand preia spatiul liber
        top_h = max(250, min(470, body_bottom - _content_height(content, row_h, False) - 40))
    else:
        while True:
            top_h = min(600, body_bottom - _content_height(content, row_h, True))
            if top_h >= 320 or row_h <= 60:
                break
            row_h -= 4
        top_h = max(top_h, 200)

    img = Image.new("RGB", (width * _S, height * _S), _PAPER)
    draw = ImageDraw.Draw(img)

    def px(v: float) -> int:
        return round(v * _S)

    if mockup_path is None:
        draw.rectangle((0, 0, px(width), px(top_h)), fill=_NAVY)
        mid = top_h / 2
        draw.rounded_rectangle((px(_MARGIN), px(mid - 62), px(_MARGIN + 72), px(mid - 54)), radius=px(4), fill=_LIME)
        draw.text((px(_MARGIN), px(mid + 28)), BRAND, font=_font(62, True), fill=_WHITE, anchor="ls")
        draw.text((px(_MARGIN), px(mid + 76)), TITLE, font=_font(30), fill=_SOFT, anchor="ls")
    else:
        img.paste(_hero(mockup_path, (px(width), px(top_h))), (0, 0))
        draw.rectangle((0, px(top_h), px(width), px(top_h + 6)), fill=_LIME)

    inner_w = width - 2 * _MARGIN
    free = body_bottom - top_h - _content_height(content, row_h, mockup_path is not None)
    y = top_h + 36 + max(0, free) // 2

    if mockup_path is not None:
        draw.text((px(_MARGIN), px(y + 42)), TITLE, font=_font(44, True), fill=_NAVY, anchor="ls")
        y += 54

    if content.subtitle:
        font = _font(26)
        words = [(w, font) for w in content.subtitle.split()]
        for i, line in enumerate(_wrap(draw, words, px(inner_w), 2)):
            _draw_words(draw, px(_MARGIN), px(y + 34 + i * 36), line, _GRAY)
        y += 84
    y += 26

    edges = [_MARGIN + inner_w * f for f in _COLS]
    pad = 24
    head_font = _font(20, True)
    draw.text((px(edges[0] + pad), px(y + 22)), HEADERS[0].upper(), font=head_font, fill=_GRAY, anchor="ls")
    for col in (1, 2, 3):
        right = edges[col + 1] - (pad if col == 3 else 8)
        draw.text((px(right), px(y + 22)), HEADERS[col].upper(), font=head_font, fill=_GRAY, anchor="rs")
    y += 34

    for row in content.rows:
        fill, ink, sub = (_NAVY, _WHITE, _SOFT) if row.highlighted else (_ROW, _NAVY, _GRAY)
        draw.rounded_rectangle((px(_MARGIN), px(y), px(_MARGIN + inner_w), px(y + row_h)),
                               radius=px(16), fill=fill)
        if row.highlighted:
            draw.rounded_rectangle((px(_MARGIN + 10), px(y + 16), px(_MARGIN + 16), px(y + row_h - 16)),
                                   radius=px(3), fill=_LIME)
        base = y + (row_h * 0.47 if row.note else row_h * 0.5 + 12)
        qty_w = px(edges[1] - edges[0] - pad - 8)
        draw.text((px(edges[0] + pad), px(base)), row.quantity,
                  font=_fit(draw, row.quantity, 32, True, qty_w), fill=ink, anchor="ls")
        cells = ((1, row.unit_price, 27, False, ink), (2, row.total_ex_vat, 27, False, ink),
                 (3, row.total, 31, True, _LIME if row.highlighted else ink))
        for col, text, size, bold, colour in cells:
            right = edges[col + 1] - (pad if col == 3 else 8)
            room = px(edges[col + 1] - edges[col] - (pad if col == 3 else 8) - 10)
            draw.text((px(right), px(base)), text, font=_fit(draw, text, size, bold, room),
                      fill=colour, anchor="rs")
        if row.note:
            note_font = _font(19)
            note = _truncate(draw, row.note, note_font, px(inner_w - 2 * pad))
            draw.text((px(edges[0] + pad), px(base + 28)), note, font=note_font, fill=sub, anchor="ls")
        y += row_h + 10
    y += 20

    regular, bold = _font(25), _font(25, True)
    for label, value in ((TERM_LABEL, content.term), (VALID_LABEL, content.valid_until)):
        words = [(w, regular) for w in label.split()] + [(w, bold) for w in value.split()]
        line = _wrap(draw, words, px(inner_w), 1)[0]
        _draw_words(draw, px(_MARGIN), px(y + 30), line, _NAVY)
        y += 44

    draw.rectangle((0, px(body_bottom), px(width), px(height)), fill=_NAVY)
    draw.rounded_rectangle((px(_MARGIN), px(body_bottom + 34), px(_MARGIN + 8), px(height - 34)),
                           radius=px(4), fill=_LIME)
    draw.text((px(_MARGIN + 26), px(body_bottom + _FOOTER_H / 2)), BRAND, font=_font(32, True),
              fill=_WHITE, anchor="lm")
    return img.resize(OFFER_SIZE, Image.Resampling.LANCZOS)

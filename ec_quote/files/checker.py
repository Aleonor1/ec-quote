"""check_file: verifica fisierul clientului la dimensiunea finala de tipar.

Nu ridica niciodata exceptii: orice fisier corupt sau ostil devine un FileReport
cu verdict unusable. Nu executa nimic din fisier si nu acceseaza reteaua.
"""
from __future__ import annotations

import base64
import binascii
import io
import json
import math
import os
import re
import stat
import warnings
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Mapping

from PIL import Image

from ec_quote.contracts import FileReport, FileVerdict
from ec_quote.files import problems as P
from ec_quote.files import sniff

DEFAULT_RULES_PATH = Path(__file__).resolve().parents[2] / "config" / "rules.json"

# limite proprii modulului; pot fi suprascrise din rules.json daca apar acolo
DEFAULT_MAX_FILE_MB = 100
DEFAULT_MAX_PIXELS = 178_000_000       # sub pragul de eroare al Pillow (2 x MAX_IMAGE_PIXELS)
DEFAULT_ASPECT_TOLERANCE = Decimal("0.05")
ANALYSIS_MAX_PIXELS = 64_000_000       # peste atat nu decodam pixelii (alfa, fundal)
MAX_EMBEDDED_IMAGE_BYTES = 40 * 1024 * 1024

CM_PER_INCH = Decimal("2.54")
RECT_SHAPES = frozenset({"rectangle", "square", "dreptunghi", "patrat", "pătrat"})

_PIL_FORMATS = {
    sniff.MIME_PNG: "PNG",
    sniff.MIME_JPEG: "JPEG",
    sniff.MIME_WEBP: "WEBP",
    sniff.MIME_GIF: "GIF",
    sniff.MIME_TIFF: "TIFF",
}
_PDF_COMPONENTS = {1: "L", 3: "RGB", 4: "CMYK"}


@lru_cache(maxsize=4)
def _load_rules_cached(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_rules(path: str | os.PathLike | None = None) -> dict:
    return _load_rules_cached(str(path or DEFAULT_RULES_PATH))


def _to_cm(value) -> Decimal | None:
    try:
        d = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return d if d.is_finite() and d > 0 else None


def _dec(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _axis_dpi(pixels, cm: Decimal, fraction=1) -> Decimal | None:
    """DPI pe o axa: pixeli / inch ocupati. fraction = cat din latimea finala ocupa imaginea."""
    inches = cm / CM_PER_INCH * _dec(fraction)
    if inches <= 0:
        return None
    return _dec(pixels) / inches


def _effective_dpi(w_px, h_px, width_cm, height_cm, frac_w=1, frac_h=1) -> Decimal | None:
    if width_cm is None or height_cm is None:
        return None
    dx = _axis_dpi(w_px, width_cm, frac_w)
    dy = _axis_dpi(h_px, height_cm, frac_h)
    if dx is None or dy is None:
        return None
    return min(dx, dy)


def _round_dpi(dpi: Decimal) -> Decimal:
    return dpi.quantize(Decimal("0.1"), rounding=ROUND_DOWN)


class FileChecker:
    """Implementarea FilePort. `shape` este optional si doar rafineaza nota de fundal."""

    def __init__(
        self,
        rules: Mapping | None = None,
        rules_path: str | os.PathLike | None = None,
        max_file_bytes: int | None = None,
        max_pixels: int | None = None,
    ) -> None:
        self.rules = dict(rules) if rules is not None else load_rules(rules_path)
        self.min_dpi_ok = _dec(self.rules["min_dpi_ok"])
        self.min_dpi_weak = _dec(self.rules["min_dpi_weak"])
        self.aspect_tolerance = _dec(self.rules.get("aspect_tolerance", DEFAULT_ASPECT_TOLERANCE))
        self.max_file_bytes = int(
            max_file_bytes
            if max_file_bytes is not None
            else _dec(self.rules.get("max_file_mb", DEFAULT_MAX_FILE_MB)) * 1024 * 1024
        )
        self.max_pixels = int(
            max_pixels if max_pixels is not None else self.rules.get("max_image_pixels", DEFAULT_MAX_PIXELS)
        )

    # ---------- intrare publica ----------

    def check_file(self, path: str, width_cm: Decimal, height_cm: Decimal,
                   shape: str | None = None) -> FileReport:
        mime = sniff.MIME_UNKNOWN
        try:
            st = os.stat(path)
            if not stat.S_ISREG(st.st_mode) or st.st_size == 0:
                return self._fail(mime, P.UNREADABLE)
            with open(path, "rb") as fh:
                head = fh.read(sniff.SNIFF_BYTES)
            mime = sniff.sniff_mime(head)
            if mime not in sniff.SUPPORTED_MIMES:
                return self._fail(mime, P.UNSUPPORTED_FORMAT)
            if st.st_size > self.max_file_bytes:
                return self._fail(mime, P.TOO_LARGE)
            w_cm, h_cm = _to_cm(width_cm), _to_cm(height_cm)
            if mime in sniff.RASTER_MIMES:
                return self._check_raster(path, mime, w_cm, h_cm, shape)
            if mime == sniff.MIME_PDF:
                return self._check_pdf(path, w_cm, h_cm)
            return self._check_svg(path, w_cm, h_cm)
        except Exception:  # noqa: BLE001 - contractul: nu ridicam niciodata
            return self._fail(mime, P.UNREADABLE)

    # ---------- comune ----------

    @staticmethod
    def _fail(mime: str, code: str, **fields) -> FileReport:
        kind = fields.pop("kind", "unknown")
        return FileReport(kind=kind, mime=mime, verdict=FileVerdict.UNUSABLE, problems=[code], **fields)

    def _dpi_problem(self, dpi: Decimal | None) -> str | None:
        if dpi is None or dpi >= self.min_dpi_ok:
            return None
        return P.LOW_DPI if dpi >= self.min_dpi_weak else P.VERY_LOW_DPI

    def _aspect_mismatch(self, w, h, width_cm, height_cm) -> bool:
        if width_cm is None or height_cm is None:
            return False
        w, h = _dec(w), _dec(h)
        if w <= 0 or h <= 0:
            return False
        ratio = (w / h) / (width_cm / height_cm)
        return abs(ratio - 1) > self.aspect_tolerance

    @staticmethod
    def _report(kind, mime, problems, dpi=None, **fields) -> FileReport:
        return FileReport(
            kind=kind,
            mime=mime,
            dpi_at_size=_round_dpi(dpi) if dpi is not None else None,
            verdict=P.verdict_for(problems),
            problems=problems,
            **fields,
        )

    # ---------- raster ----------

    def _check_raster(self, path, mime, width_cm, height_cm, shape) -> FileReport:
        problems: list[str] = []
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            try:
                im = Image.open(path, formats=[_PIL_FORMATS[mime]])
            except Image.DecompressionBombError:
                return self._fail(mime, P.TOO_LARGE, kind="raster")
            with im:
                w, h = im.size
                mode = im.mode
                pages = 1
                if mime == sniff.MIME_TIFF:
                    pages = int(getattr(im, "n_frames", 1) or 1)
                base = dict(width_px=w, height_px=h, color_mode=mode, pages=pages)
                if w <= 0 or h <= 0:
                    return self._fail(mime, P.UNREADABLE, kind="raster")
                if w * h > self.max_pixels:
                    return self._fail(mime, P.TOO_LARGE, kind="raster", **base)

                has_alpha: bool | None
                alpha_capable = mode in ("RGBA", "LA", "PA", "RGBa", "La") or "transparency" in im.info
                solid_border = False
                if w * h <= ANALYSIS_MAX_PIXELS:
                    if mime == sniff.MIME_JPEG:
                        im.draft(None, (max(1, w // 8), max(1, h // 8)))  # decodare redusa
                    im.load()  # un fisier trunchiat cade aici si devine unreadable
                    has_alpha = _alpha_used(im) if alpha_capable else False
                    if has_alpha is False:
                        solid_border = _has_solid_border(im)
                else:
                    has_alpha = None if alpha_capable else False

        dpi = _effective_dpi(w, h, width_cm, height_cm)
        code = self._dpi_problem(dpi)
        if code:
            problems.append(code)
        if self._aspect_mismatch(w, h, width_cm, height_cm):
            problems.append(P.ASPECT_MISMATCH)
        if pages > 1:
            problems.append(P.MULTI_PAGE)
        if mime == sniff.MIME_JPEG and mode == "CMYK":
            problems.append(P.CMYK_JPEG)
        if solid_border and (shape or "").strip().lower() not in RECT_SHAPES:
            problems.append(P.OPAQUE_BACKGROUND)
        return self._report("raster", mime, problems, dpi, has_transparency=has_alpha, **base)

    # ---------- PDF (si AI compatibil PDF) ----------

    def _check_pdf(self, path, width_cm, height_cm) -> FileReport:
        import pymupdf

        pymupdf.TOOLS.mupdf_display_errors(False)
        pymupdf.TOOLS.mupdf_display_warnings(False)
        mime = sniff.MIME_PDF
        problems: list[str] = []
        with pymupdf.open(path, filetype="pdf") as doc:
            if doc.needs_pass or doc.page_count < 1:
                return self._fail(mime, P.UNREADABLE)
            pages = doc.page_count
            page = doc[0]
            rect = page.rect
            if rect.width <= 0 or rect.height <= 0:
                return self._fail(mime, P.UNREADABLE, pages=pages)

            worst = None  # (dpi, w_px, h_px, componente)
            image_count = 0
            for info in page.get_image_info():
                w_px, h_px = int(info.get("width") or 0), int(info.get("height") or 0)
                bbox = pymupdf.Rect(info.get("bbox") or (0, 0, 0, 0))
                if w_px <= 0 or h_px <= 0 or not bbox.intersects(rect):
                    continue
                # dimensiunea plasata din matrice (corecta si pentru imagini rotite)
                m = info.get("transform")
                if m and len(m) >= 4:
                    placed_w, placed_h = math.hypot(m[0], m[1]), math.hypot(m[2], m[3])
                else:
                    placed_w, placed_h = bbox.width, bbox.height
                if placed_w < 1 or placed_h < 1:
                    continue
                image_count += 1
                if width_cm is not None and height_cm is not None:
                    dpi = _effective_dpi(w_px, h_px, width_cm, height_cm,
                                         placed_w / rect.width, placed_h / rect.height)
                else:
                    dpi = None
                if worst is None or (dpi is not None and (worst[0] is None or dpi < worst[0])):
                    worst = (dpi, w_px, h_px, info.get("colorspace"))

            has_text = bool(page.get_text("text").strip())
            has_vector = has_text or bool(page.get_cdrawings())
            if has_text and any(
                f[1] == "n/a" and "Type3" not in str(f[2]) for f in page.get_fonts(full=True)
            ):
                problems.append(P.TEXT_NOT_OUTLINED)

        if image_count == 0:
            kind = "vector"
        else:
            kind = "mixed" if has_vector else "raster"
        dpi = worst[0] if worst else None
        code = self._dpi_problem(dpi)
        if code:
            problems.insert(0, code)
        if self._aspect_mismatch(rect.width, rect.height, width_cm, height_cm):
            problems.append(P.ASPECT_MISMATCH)
        if pages > 1:
            problems.append(P.MULTI_PAGE)
        return self._report(
            kind, mime, problems, dpi,
            width_px=worst[1] if worst else None,
            height_px=worst[2] if worst else None,
            color_mode=_PDF_COMPONENTS.get(worst[3]) if worst else None,
            pages=pages,
        )

    # ---------- SVG ----------

    def _check_svg(self, path, width_cm, height_cm) -> FileReport:
        """Citire doar cu expresii regulate: fara parser XML, deci fara entitati sau DTD."""
        mime = sniff.MIME_SVG
        with open(path, "rb") as fh:
            text = sniff.decode_text(fh.read(self.max_file_bytes + 1))
        text = _SVG_COMMENT.sub("", text)
        root = _SVG_ROOT_TAG.search(text)
        if not root:
            return self._fail(mime, P.UNREADABLE)
        attrs = _attrs(root.group(1))
        box_w = box_h = None
        view_box = _NUMBER.findall(attrs.get("viewbox", ""))
        if len(view_box) == 4 and float(view_box[2]) > 0 and float(view_box[3]) > 0:
            box_w, box_h = float(view_box[2]), float(view_box[3])
        else:
            box_w, box_h = _svg_length(attrs.get("width")), _svg_length(attrs.get("height"))
            if not box_w or not box_h:
                box_w = box_h = None

        problems: list[str] = []
        has_shapes = has_text = linked = False
        worst = None  # (dpi, w_px, h_px, mod)
        image_count = 0
        for tag in _SVG_TAG.finditer(text, root.end()):
            name = tag.group(1).split(":")[-1].lower()
            if name in _SVG_SHAPES:
                has_shapes = True
            elif name in ("text", "tspan", "textpath"):
                has_text = True
            elif name == "image":
                image_count += 1
                a = _attrs(tag.group(2))
                href = (a.get("href") or a.get("xlink:href") or "").strip()
                size = _embedded_image_size(href)
                if size is None:
                    if not href.lower().startswith("data:"):
                        linked = True
                    continue
                w_px, h_px, mode = size
                frac_w = frac_h = 1.0  # fara dimensiuni clare: imaginea umple plansa
                pw, ph = _svg_length(a.get("width")), _svg_length(a.get("height"))
                if box_w and pw and ph:
                    frac_w, frac_h = pw / box_w, ph / box_h
                dpi = _effective_dpi(w_px, h_px, width_cm, height_cm, frac_w, frac_h)
                if worst is None or (dpi is not None and (worst[0] is None or dpi < worst[0])):
                    worst = (dpi, w_px, h_px, mode)

        if image_count == 0:
            kind = "vector"
        else:
            kind = "mixed" if (has_shapes or has_text) else "raster"
        dpi = worst[0] if worst else None
        code = self._dpi_problem(dpi)
        if code:
            problems.append(code)
        if has_text:
            problems.append(P.TEXT_NOT_OUTLINED)
        if linked:
            problems.append(P.LINKED_IMAGE)
        if box_w and self._aspect_mismatch(box_w, box_h, width_cm, height_cm):
            problems.append(P.ASPECT_MISMATCH)
        return self._report(
            kind, mime, problems, dpi,
            width_px=worst[1] if worst else None,
            height_px=worst[2] if worst else None,
            color_mode=worst[3] if worst else None,
            pages=1,
        )


# ---------- pixeli ----------

def _alpha_used(im: Image.Image) -> bool:
    """True doar daca exista pixeli efectiv transparenti, nu doar un canal alfa."""
    rgba = im if im.mode in ("RGBA", "LA") else im.convert("RGBA")
    hist = rgba.getchannel("A").histogram()
    transparent = sum(hist[:250])
    total = sum(hist)
    return transparent > 0 and transparent * 2000 >= total  # cel putin 0,05% din pixeli


def _has_solid_border(im: Image.Image, tolerance: int = 12, share: float = 0.97) -> bool:
    """Marginea imaginii are o singura culoare: fundal plin, probabil alb."""
    try:
        w, h = im.size
        scale = max(w, h) / 64
        sw, sh = max(1, round(w / scale)), max(1, round(h / scale))
        small = im.resize((sw, sh), Image.Resampling.NEAREST).convert("RGB") if scale > 1 else im.convert("RGB")
        sw, sh = small.size
        if sw < 3 or sh < 3:
            return False
        px = small.load()
        ring = [px[x, y] for x in range(sw) for y in (0, sh - 1)]
        ring += [px[x, y] for y in range(1, sh - 1) for x in (0, sw - 1)]
        mid = [sorted(p[c] for p in ring)[len(ring) // 2] for c in range(3)]
        close = sum(1 for p in ring if all(abs(p[c] - mid[c]) <= tolerance for c in range(3)))
        return close >= share * len(ring)
    except Exception:  # noqa: BLE001 - moduri exotice: fara nota
        return False


# ---------- SVG, ajutoare ----------

_SVG_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_SVG_ROOT_TAG = re.compile(r"<(?:[\w-]+:)?svg\b([^>]*)>", re.IGNORECASE)
_SVG_TAG = re.compile(r"<([A-Za-z][\w:-]*)\b([^>]*)>")
_ATTR = re.compile(r"([\w:.-]+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)')")
_NUMBER = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
_LENGTH = re.compile(r"^\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)\s*(px|pt|pc|mm|cm|in)?\s*$", re.IGNORECASE)
_UNIT_PX = {"": 1.0, "px": 1.0, "pt": 96 / 72, "pc": 16.0, "mm": 96 / 25.4, "cm": 96 / 2.54, "in": 96.0}
_SVG_SHAPES = frozenset({"path", "rect", "circle", "ellipse", "polygon", "polyline", "line"})
_DATA_URI = re.compile(r"^data:image/[\w.+-]+;base64,", re.IGNORECASE)


def _attrs(raw: str) -> dict[str, str]:
    return {m.group(1).lower(): (m.group(2) if m.group(2) is not None else m.group(3)) for m in _ATTR.finditer(raw)}


def _svg_length(value: str | None) -> float | None:
    """Lungime SVG in px CSS; None pentru procente sau valori neclare."""
    m = _LENGTH.match(value or "")
    if not m:
        return None
    px = float(m.group(1)) * _UNIT_PX[(m.group(2) or "").lower()]
    return px if px > 0 and math.isfinite(px) else None


def _embedded_image_size(href: str) -> tuple[int, int, str] | None:
    """Dimensiunea unei imagini incorporate ca data URI; legaturile externe nu se urmaresc."""
    m = _DATA_URI.match(href)
    if not m:
        return None
    payload = href[m.end():]
    if len(payload) > MAX_EMBEDDED_IMAGE_BYTES * 4 // 3:
        return None
    try:
        raw = base64.b64decode(payload, validate=False)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw), formats=["PNG", "JPEG", "WEBP", "GIF"]) as im:
                return im.size[0], im.size[1], im.mode
    except (binascii.Error, ValueError, OSError, Image.DecompressionBombError):
        return None


# ---------- functie de modul ----------

_default: FileChecker | None = None


def check_file(path: str, width_cm: Decimal, height_cm: Decimal, shape: str | None = None) -> FileReport:
    """Varianta cu regulile din config/rules.json."""
    global _default
    if _default is None:
        _default = FileChecker()
    return _default.check_file(path, width_cm, height_cm, shape)

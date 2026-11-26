"""Fonturi care redau diacriticele romanesti (ă â î ș ț)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

RO_DIACRITICS = "ăâîșțĂÂÎȘȚ"
_BASE = {"ă": "a", "â": "a", "î": "i", "ș": "s", "ț": "t",
         "Ă": "A", "Â": "A", "Î": "I", "Ș": "S", "Ț": "T"}

_BUNDLED = Path(__file__).parent / "fonts"
_CANDIDATES = {
    "regular": (
        _BUNDLED / "DejaVuSans.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"),
        Path("/Library/Fonts/Arial Unicode.ttf"),
    ),
    "bold": (
        _BUNDLED / "DejaVuSans-Bold.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"),
    ),
}


def renders_diacritics(font: ImageFont.ImageFont | ImageFont.FreeTypeFont) -> bool:
    """True daca fiecare diacritica are glif propriu (nu patratel, nu litera de baza)."""
    try:
        missing = bytes(font.getmask("\uffff"))
        for ch in RO_DIACRITICS:
            glyph = font.getmask(ch)
            data = bytes(glyph)
            if not any(data) or data == missing:
                return False
            base = font.getmask(_BASE[ch])
            if glyph.size == base.size and data == bytes(base):
                return False
    except (OSError, UnicodeError, ValueError):
        return False
    return True


@lru_cache(maxsize=4)
def font_path(weight: str = "regular") -> Path | None:
    """Primul font disponibil care reda diacriticele; None daca nu exista niciunul."""
    for path in _CANDIDATES[weight]:
        if not path.is_file():
            continue
        try:
            font = ImageFont.truetype(str(path), 40)
        except OSError:
            continue
        if renders_diacritics(font):
            return path
    return None


@lru_cache(maxsize=64)
def load_font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Font la marimea ceruta. Cade pe regular, apoi pe fontul implicit Pillow, fara sa crape."""
    path = font_path(weight) or font_path("regular")
    if path is not None:
        return ImageFont.truetype(str(path), size)
    try:
        return ImageFont.load_default(size)
    except TypeError:  # Pillow vechi, fara marime
        return ImageFont.load_default()

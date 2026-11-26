from PIL import Image, ImageDraw, ImageFont

from ec_quote.mockup import fonts
from ec_quote.mockup.fonts import RO_DIACRITICS, font_path, load_font, renders_diacritics


def test_a_font_with_romanian_diacritics_is_available():
    # Pica daca pe masina nu exista niciun font care reda ă â î ș ț.
    for weight in ("regular", "bold"):
        assert font_path(weight) is not None, "niciun font %s cu diacritice" % weight
        assert renders_diacritics(load_font(40, weight))


def test_bundled_fonts_are_the_first_choice():
    assert font_path("regular").parent == fonts._BUNDLED
    assert font_path("bold").parent == fonts._BUNDLED


def test_each_diacritic_draws_ink_different_from_its_base_letter():
    font = load_font(48)
    for ch, base in zip("ăâîșț", "aaist"):
        a = Image.new("L", (80, 80), 0)
        b = Image.new("L", (80, 80), 0)
        ImageDraw.Draw(a).text((10, 10), ch, font=font, fill=255)
        ImageDraw.Draw(b).text((10, 10), base, font=font, fill=255)
        assert a.getbbox() is not None
        assert a.tobytes() != b.tobytes(), ch


def test_font_without_diacritics_is_detected():
    class Blank:
        def getmask(self, text):
            return Image.new("L", (8, 8), 0).im

    class SameAsBase:
        def getmask(self, text):
            return Image.new("L", (8, 8), 200).im

    class Broken:
        def getmask(self, text):
            raise OSError("font stricat")

    assert not renders_diacritics(Blank())
    assert not renders_diacritics(SameAsBase())
    assert not renders_diacritics(Broken())
    assert len(RO_DIACRITICS) == 10


def test_falls_back_safely_when_no_font_file_exists(monkeypatch, tmp_path):
    bad = tmp_path / "stricat.ttf"
    bad.write_bytes(b"nu este un font")
    monkeypatch.setattr(fonts, "_CANDIDATES", {"regular": (tmp_path / "lipsa.ttf", bad), "bold": ()})
    fonts.font_path.cache_clear()
    fonts.load_font.cache_clear()
    try:
        assert fonts.font_path("regular") is None
        fallback = fonts.load_font(30, "bold")
        assert isinstance(fallback, (ImageFont.ImageFont, ImageFont.FreeTypeFont))
        ImageDraw.Draw(Image.new("RGB", (50, 50))).text((0, 0), "abc", font=fallback)
    finally:
        fonts.font_path.cache_clear()
        fonts.load_font.cache_clear()


def test_bold_falls_back_to_regular(monkeypatch):
    regular = fonts._CANDIDATES["regular"]
    monkeypatch.setattr(fonts, "_CANDIDATES", {"regular": regular, "bold": ()})
    fonts.font_path.cache_clear()
    fonts.load_font.cache_clear()
    try:
        assert renders_diacritics(fonts.load_font(30, "bold"))
    finally:
        fonts.font_path.cache_clear()
        fonts.load_font.cache_clear()

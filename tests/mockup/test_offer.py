import re
from datetime import datetime
from decimal import Decimal as D

import pytest
from PIL import Image

from ec_quote.contracts import MockupPort, OfferLine
from ec_quote.mockup import MockupService, OfferImageError, make_offer_image
from ec_quote.mockup.offer import (
    BRAND, HEADERS, OFFER_SIZE, REQUESTED_TAG, TITLE, VALID_LABEL, build_content, clean_text, render_offer,
)

VALID = datetime(2026, 12, 3, 18, 0)
TERM = "3-5 zile lucrătoare"
LABEL = "Etichete hârtie lucioasă 8 x 6 cm"
NAVY = (26, 26, 46)


def line(quantity, total_ex, total, unit, highlighted=False, label=LABEL):
    return OfferLine(label=label, quantity=quantity, total_ex_vat=D(total_ex), total=D(total),
                     unit_price=D(unit), highlighted=highlighted)


LINES = [
    line(500, "412.40", "499.00", "0.998", True),
    line(1000, "661.16", "800.00", "0.80"),
    line(2500, "10234.5", "12383.75", "0.4954"),
]


@pytest.fixture
def mockup(tmp_path, solid_design, service):
    return service.make_mockup(solid_design, "borcan", str(tmp_path / "m")).image_path


def _near(pixel, colour, tol=14):
    return all(abs(a - b) <= tol for a, b in zip(pixel, colour))


def _count(image, colour, box):
    crop = image.crop(box)
    return sum(1 for p in crop.getdata() if _near(p, colour))


@pytest.mark.parametrize("count", [1, 2, 3])
@pytest.mark.parametrize("with_mockup", [True, False])
def test_offer_image_size_for_1_2_3_lines(tmp_path, mockup, count, with_mockup):
    path = MockupService().make_offer_image(mockup if with_mockup else None, LINES[:count], TERM, VALID,
                                            str(tmp_path / "o"))
    with Image.open(path) as image:
        assert image.format == "JPEG"
        assert image.size == OFFER_SIZE == (1080, 1350)
        rgb = image.convert("RGB")
    # subsolul de brand si randul evidentiat sunt desenate
    assert _near(rgb.getpixel((1000, 1320)), NAVY)
    assert _count(rgb, NAVY, (56, 300, 1024, 1250)) > 40000
    if with_mockup:
        assert not _near(rgb.getpixel((20, 20)), NAVY)
    else:
        assert _near(rgb.getpixel((20, 20)), NAVY)


def test_highlighted_row_is_emphasized_and_others_are_not(tmp_path):
    plain = render_offer(None, [line(500, "1", "2", "3"), line(1000, "1", "2", "3")], TERM, VALID)
    marked = render_offer(None, [line(500, "1", "2", "3"), line(1000, "1", "2", "3", True)], TERM, VALID)
    body = (56, 480, 1024, 1250)
    assert _count(plain, NAVY, body) < 12000
    assert _count(marked, NAVY, body) > 60000
    first = render_offer(None, [line(500, "1", "2", "3", True), line(1000, "1", "2", "3")], TERM, VALID)
    assert first.tobytes() != marked.tobytes()


def test_content_has_exactly_the_given_prices_formatted():
    content = build_content(LINES, TERM, VALID)
    assert [r.quantity for r in content.rows] == ["500 buc", "1.000 buc", "2.500 buc"]
    assert [r.unit_price for r in content.rows] == ["0,998 lei", "0,80 lei", "0,4954 lei"]
    assert [r.total_ex_vat for r in content.rows] == ["412,40 lei", "661,16 lei", "10.234,50 lei"]
    assert [r.total for r in content.rows] == ["499,00 lei", "800,00 lei", "12.383,75 lei"]
    assert [r.highlighted for r in content.rows] == [True, False, False]
    assert [r.note for r in content.rows] == [REQUESTED_TAG, "", ""]
    assert content.subtitle == LABEL
    assert content.term == TERM
    assert content.valid_until == "3 decembrie 2026"


def test_no_number_in_the_image_text_that_was_not_passed_in():
    content = build_content(LINES, TERM, VALID)
    allowed = set()
    for row in content.rows:
        for text in (row.quantity, row.unit_price, row.total_ex_vat, row.total):
            allowed.update(re.findall(r"\d[\d.,]*", text))
    allowed.update(re.findall(r"\d[\d.,]*", LABEL + " " + TERM + " 3 2026"))
    found = set()
    for text in content.all_text():
        found.update(re.findall(r"\d[\d.,]*", text))
    assert found <= allowed
    static = " ".join([BRAND, TITLE, VALID_LABEL, REQUESTED_TAG, *HEADERS])
    assert not re.search(r"\d", static)
    assert "%" not in " ".join(content.all_text())


def test_static_text_is_romanian_with_diacritics_and_no_long_dashes():
    assert BRAND == "Etichete Creative"
    assert VALID_LABEL == "Ofertă valabilă până la"
    assert HEADERS == ("Cantitate", "Preț / buc", "Total fără TVA", "Total cu TVA")
    text = " ".join(build_content(LINES, TERM, VALID).all_text())
    assert "—" not in text and "–" not in text
    assert "Ofertă valabilă până la" in text and "3 decembrie 2026" in text


def test_different_labels_go_on_each_row():
    lines = [line(500, "1", "2", "3", True, "Etichete hârtie"), line(500, "4", "5", "6", False, "Etichete vinil")]
    content = build_content(lines, TERM, VALID)
    assert content.subtitle == ""
    assert content.rows[0].note == REQUESTED_TAG + " · Etichete hârtie"
    assert content.rows[1].note == "Etichete vinil"
    assert render_offer(None, lines, TERM, VALID).size == OFFER_SIZE


def test_long_labels_and_terms_do_not_crash_or_overflow(tmp_path, mockup):
    long_label = "Etichete autocolante din hârtie lucioasă cu adeziv puternic, tăiate pe contur " * 6
    one_word = "Ș" * 400
    term = "între 7 și 10 zile lucrătoare de la confirmarea plății și aprobarea fișierului de tipar " * 4
    big = line(1250000, "98765432.10", "119506172.84", "0.0790", True, long_label)
    for lines in ([big], [big, line(2, "1", "2", "3", False, one_word)], [line(1, "1", "2", "3", False, "")]):
        for mock in (mockup, None):
            image = render_offer(mock, lines, term, VALID)
            assert image.size == OFFER_SIZE
            # marginea din dreapta ramane libera in zona de text
            edge = image.crop((1040, 640, 1080, 1250))
            assert all(_near(p, (250, 250, 252), 6) for p in edge.getdata())


def test_many_lines_shrink_and_too_many_fail(mockup):
    eight = [line(100 * (i + 1), "10", "12.10", "0.10", i == 0) for i in range(8)]
    assert render_offer(mockup, eight, TERM, VALID).size == OFFER_SIZE
    assert render_offer(None, eight, TERM, VALID).size == OFFER_SIZE
    with pytest.raises(OfferImageError, match="prea multe"):
        render_offer(None, eight + eight[:1], TERM, VALID)
    with pytest.raises(OfferImageError, match="nicio linie"):
        render_offer(None, [], TERM, VALID)


def test_clean_text_strips_emoji_controls_and_long_dashes():
    assert clean_text("  3–5 zile — lucrătoare\n\t\U0001F600 ✨ok​ ") == "3-5 zile - lucrătoare ok"
    assert clean_text("și ţ") == "și ţ"
    assert clean_text(None) == ""


def test_offer_is_deterministic(tmp_path, mockup):
    a = make_offer_image(mockup, LINES, TERM, VALID, str(tmp_path / "a"))
    b = make_offer_image(mockup, LINES, TERM, VALID, str(tmp_path / "b"))
    assert a.rsplit("/", 1)[1] == b.rsplit("/", 1)[1]
    assert open(a, "rb").read() == open(b, "rb").read()
    c = make_offer_image(mockup, LINES, TERM, datetime(2026, 12, 4), str(tmp_path / "a"))
    d = make_offer_image(None, LINES, TERM, VALID, str(tmp_path / "a"))
    assert len({a, c, d}) == 3


def test_tall_mockup_is_shown_whole_on_a_soft_backdrop(tmp_path):
    tall = tmp_path / "inalt.jpg"
    image = Image.new("RGB", (600, 1200), (200, 60, 60))
    image.paste((20, 160, 60), (0, 0, 600, 100))
    image.save(tall, quality=95)
    offer = render_offer(str(tall), LINES, TERM, VALID)
    # banda verde de sus a mockupului ramane vizibila, nu este taiata
    assert any(p[1] > 120 and p[0] < 80 for p in offer.crop((440, 0, 640, 60)).getdata())
    # lateralele sunt fundal estompat, nu mockup taiat
    assert not _near(offer.getpixel((60, 300)), (200, 60, 60), 20)


def test_unreadable_or_missing_mockup_raises_typed_error(tmp_path):
    bad = tmp_path / "stricat.jpg"
    bad.write_bytes(b"nu e imagine")
    with pytest.raises(OfferImageError):
        render_offer(str(bad), LINES, TERM, VALID)
    with pytest.raises(OfferImageError):
        make_offer_image(str(tmp_path / "lipsa.jpg"), LINES, TERM, VALID, str(tmp_path))


def test_service_satisfies_the_port():
    port: MockupPort = MockupService()
    assert callable(port.make_mockup) and callable(port.make_offer_image)

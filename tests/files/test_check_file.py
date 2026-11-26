"""check_file pe fisiere generate in test (Pillow, PyMuPDF); fara retea, fara binare in depozit."""
from __future__ import annotations

import base64
import io
import os
from decimal import Decimal

import pymupdf
import pytest
from PIL import Image

from ec_quote.contracts import FilePort, FileReport, FileVerdict
from ec_quote.files import (
    ALL_CODES,
    FileChecker,
    check_file,
    describe_problems,
    load_rules,
    sniff_mime,
    verdict_for,
)
from ec_quote.files import checker as checker_mod

RULES = {"min_dpi_ok": 300, "min_dpi_weak": 150}
D = Decimal


@pytest.fixture
def chk() -> FileChecker:
    return FileChecker(rules=RULES)


def save_image(tmp_path, name, size, mode="RGB", color=None, fmt=None, **kw):
    path = tmp_path / name
    if color is None:
        color = {"RGB": (200, 30, 30), "RGBA": (200, 30, 30, 255), "L": 90, "CMYK": (0, 200, 200, 0)}.get(mode, 0)
    Image.new(mode, size, color).save(path, format=fmt, **kw)
    return str(path)


def photo_like(size):
    """Imagine fara margine uniforma."""
    im = Image.new("RGB", size)
    im.putdata([((x * 7) % 256, (y * 5) % 256, (x + y) % 256) for y in range(size[1]) for x in range(size[0])])
    return im


def png_bytes(size, mode="RGB", color=(10, 20, 30)):
    buf = io.BytesIO()
    Image.new(mode, size, color).save(buf, format="PNG")
    return buf.getvalue()


def make_pdf(tmp_path, name, page=(283.46, 283.46), image=None, image_rect=None, text=None,
             drawing=False, pages=1):
    doc = pymupdf.open()
    for _ in range(pages):
        pg = doc.new_page(width=page[0], height=page[1])
        if image is not None:
            pg.insert_image(image_rect or pg.rect, stream=image)
        if text:
            pg.insert_text((20, 40), text, fontname="helv", fontsize=12)
        if drawing:
            pg.draw_rect(pymupdf.Rect(10, 10, 100, 100), color=(1, 0, 0), fill=(0, 0, 1))
    path = tmp_path / name
    doc.save(str(path))
    doc.close()
    return str(path)


def write(tmp_path, name, data):
    path = tmp_path / name
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    return str(path)


# ---------- contract ----------

def test_implements_file_port_and_module_function(tmp_path):
    port: FilePort = FileChecker(rules=RULES)
    path = save_image(tmp_path, "a.png", (1200, 1200))
    assert isinstance(port.check_file(path, D("10"), D("10")), FileReport)
    report = check_file(path, D("10"), D("10"))
    assert report.dpi_at_size == D("304.8")
    assert load_rules()["min_dpi_ok"] == 150


def test_thresholds_come_from_rules(tmp_path):
    path = save_image(tmp_path, "a.png", (600, 600))  # 152.4 dpi la 10 cm
    strict = FileChecker(rules={"min_dpi_ok": 300, "min_dpi_weak": 200})
    loose = FileChecker(rules={"min_dpi_ok": 150, "min_dpi_weak": 100})
    assert strict.check_file(path, D("10"), D("10")).problems == ["very_low_dpi", "opaque_background"]
    assert loose.check_file(path, D("10"), D("10")).verdict is FileVerdict.OK


# ---------- raster ----------

def test_png_ok_with_solid_background_note(chk, tmp_path):
    path = save_image(tmp_path, "logo.png", (1200, 1200), color=(255, 255, 255))
    r = chk.check_file(path, D("10"), D("10"))
    assert (r.kind, r.mime, r.width_px, r.height_px) == ("raster", "image/png", 1200, 1200)
    assert r.dpi_at_size == D("304.8") and isinstance(r.dpi_at_size, Decimal)
    assert r.color_mode == "RGB" and r.pages == 1 and r.has_transparency is False
    # nota nu schimba verdictul
    assert r.problems == ["opaque_background"] and r.verdict is FileVerdict.OK


def test_opaque_background_skipped_for_rectangular_shape_and_photos(chk, tmp_path):
    path = save_image(tmp_path, "logo.png", (1200, 1200), color=(255, 255, 255))
    assert chk.check_file(path, D("10"), D("10"), shape="rectangle").problems == []
    assert chk.check_file(path, D("10"), D("10"), shape="contour").problems == ["opaque_background"]
    photo = tmp_path / "photo.png"
    photo_like((300, 300)).save(photo)
    assert "opaque_background" not in chk.check_file(str(photo), D("2"), D("2")).problems


def test_low_and_very_low_dpi(chk, tmp_path):
    weak = chk.check_file(save_image(tmp_path, "w.png", (800, 800)), D("10"), D("10"))
    assert weak.dpi_at_size == D("203.2") and "low_dpi" in weak.problems
    assert weak.verdict is FileVerdict.WEAK
    bad = chk.check_file(save_image(tmp_path, "b.png", (200, 200)), D("10"), D("10"))
    assert bad.dpi_at_size == D("50.8") and "very_low_dpi" in bad.problems
    assert bad.verdict is FileVerdict.UNUSABLE


def test_dpi_is_the_lower_axis_and_aspect_mismatch(chk, tmp_path):
    path = save_image(tmp_path, "wide.png", (2400, 600))
    r = chk.check_file(path, D("10"), D("10"))
    assert r.dpi_at_size == D("152.4")
    assert "aspect_mismatch" in r.problems and "low_dpi" in r.problems
    assert r.verdict is FileVerdict.WEAK
    # in toleranta: 4% diferenta
    near = save_image(tmp_path, "near.png", (1250, 1200))
    assert "aspect_mismatch" not in chk.check_file(near, D("10"), D("10")).problems


def test_transparency_used_vs_only_present(chk, tmp_path):
    opaque = save_image(tmp_path, "opaque.png", (1200, 1200), mode="RGBA", color=(255, 255, 255, 255))
    r = chk.check_file(opaque, D("10"), D("10"))
    assert r.has_transparency is False and r.color_mode == "RGBA"
    assert "opaque_background" in r.problems

    im = Image.new("RGBA", (1200, 1200), (0, 0, 0, 0))
    im.paste((200, 0, 0, 255), (300, 300, 900, 900))
    used = tmp_path / "used.png"
    im.save(used)
    r = chk.check_file(str(used), D("10"), D("10"))
    assert r.has_transparency is True and r.problems == [] and r.verdict is FileVerdict.OK


def test_palette_png_with_transparent_index(chk, tmp_path):
    im = Image.new("P", (1200, 1200), 0)
    im.putpalette([255, 255, 255, 200, 0, 0] + [0] * 756)
    im.paste(1, (300, 300, 900, 900))
    path = tmp_path / "pal.png"
    im.save(path, transparency=0)
    r = chk.check_file(str(path), D("10"), D("10"))
    assert r.color_mode == "P" and r.has_transparency is True


def test_jpeg_rgb_and_cmyk(chk, tmp_path):
    rgb = chk.check_file(save_image(tmp_path, "a.jpg", (1200, 1200), fmt="JPEG"), D("10"), D("10"))
    assert rgb.mime == "image/jpeg" and rgb.has_transparency is False
    assert (rgb.width_px, rgb.height_px) == (1200, 1200)  # decodarea redusa nu schimba raportul
    assert "cmyk_jpeg" not in rgb.problems
    cmyk = chk.check_file(save_image(tmp_path, "c.jpg", (1200, 1200), mode="CMYK", fmt="JPEG"), D("10"), D("10"))
    assert cmyk.color_mode == "CMYK" and "cmyk_jpeg" in cmyk.problems
    assert cmyk.verdict is FileVerdict.WEAK


def test_mime_is_sniffed_not_taken_from_extension(chk, tmp_path):
    path = save_image(tmp_path, "really_a_jpeg.png", (1200, 1200), fmt="JPEG")
    assert chk.check_file(path, D("10"), D("10")).mime == "image/jpeg"
    pdf_named_ai = make_pdf(tmp_path, "logo.ai", drawing=True)
    r = chk.check_file(pdf_named_ai, D("10"), D("10"))
    assert (r.mime, r.kind, r.verdict) == ("application/pdf", "vector", FileVerdict.OK)


def test_webp_gif_tiff(chk, tmp_path):
    webp = chk.check_file(save_image(tmp_path, "a.webp", (1200, 1200), fmt="WEBP"), D("10"), D("10"))
    assert webp.mime == "image/webp" and webp.kind == "raster"

    frames = [Image.new("P", (600, 600), i) for i in range(3)]
    gif = tmp_path / "a.gif"
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=50)
    r = chk.check_file(str(gif), D("5"), D("5"))
    assert r.mime == "image/gif" and r.pages == 1 and "multi_page" not in r.problems
    assert r.dpi_at_size == D("304.8")

    tif = tmp_path / "a.tif"
    pages = [Image.new("CMYK", (1200, 1200), (0, 0, 0, 0)) for _ in range(2)]
    pages[0].save(tif, save_all=True, append_images=pages[1:])
    r = chk.check_file(str(tif), D("10"), D("10"))
    assert r.mime == "image/tiff" and r.color_mode == "CMYK" and r.pages == 2
    assert "multi_page" in r.problems and "cmyk_jpeg" not in r.problems


def test_size_missing_or_invalid_gives_no_dpi(chk, tmp_path):
    path = save_image(tmp_path, "a.png", (100, 100))
    for w, h in ((D("0"), D("10")), (D("-1"), D("5")), ("abc", None), (D("NaN"), D("1"))):
        r = chk.check_file(path, w, h)
        assert r.dpi_at_size is None and "aspect_mismatch" not in r.problems
        assert r.verdict is FileVerdict.OK


# ---------- limite si fisiere ostile ----------

def test_pixel_cap_and_file_size_cap(tmp_path):
    path = save_image(tmp_path, "a.png", (400, 400))
    small_pixels = FileChecker(rules=RULES, max_pixels=1000)
    r = small_pixels.check_file(path, D("10"), D("10"))
    assert r.problems == ["too_large"] and r.verdict is FileVerdict.UNUSABLE
    assert (r.width_px, r.height_px, r.kind) == (400, 400, "raster")

    small_bytes = FileChecker(rules=RULES, max_file_bytes=100)
    assert small_bytes.check_file(path, D("10"), D("10")).problems == ["too_large"]
    from_rules = FileChecker(rules={**RULES, "max_file_mb": "0.0001"})
    assert from_rules.check_file(path, D("10"), D("10")).problems == ["too_large"]


def test_pillow_decompression_bomb_is_too_large(chk, tmp_path, monkeypatch):
    path = save_image(tmp_path, "a.png", (400, 400))
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)  # 160000 px > 2 x limita: eroare
    r = chk.check_file(path, D("10"), D("10"))
    assert r.problems == ["too_large"] and r.kind == "raster"


def test_large_image_skips_pixel_analysis(chk, tmp_path, monkeypatch):
    monkeypatch.setattr(checker_mod, "ANALYSIS_MAX_PIXELS", 100)
    rgba = save_image(tmp_path, "a.png", (400, 400), mode="RGBA", color=(0, 0, 0, 0))
    assert chk.check_file(rgba, D("2"), D("2")).has_transparency is None
    rgb = save_image(tmp_path, "b.png", (400, 400), color=(255, 255, 255))
    r = chk.check_file(rgb, D("2"), D("2"))
    assert r.has_transparency is False and "opaque_background" not in r.problems


def test_truncated_and_garbage_files_never_raise(chk, tmp_path):
    good = save_image(tmp_path, "a.png", (500, 500))
    data = open(good, "rb").read()
    truncated = write(tmp_path, "cut.png", data[: len(data) // 2])
    r = chk.check_file(truncated, D("5"), D("5"))
    assert r.problems == ["unreadable"] and r.mime == "image/png" and r.verdict is FileVerdict.UNUSABLE

    header_only = write(tmp_path, "h.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)
    assert chk.check_file(header_only, D("5"), D("5")).problems == ["unreadable"]
    bad_pdf = write(tmp_path, "bad.pdf", b"%PDF-1.7\n" + os.urandom(300))
    assert chk.check_file(bad_pdf, D("5"), D("5")).problems == ["unreadable"]
    bad_jpg = write(tmp_path, "bad.jpg", b"\xff\xd8\xff\xe0" + os.urandom(300))
    assert chk.check_file(bad_jpg, D("5"), D("5")).problems == ["unreadable"]


def test_missing_empty_and_directory(chk, tmp_path):
    for path in (str(tmp_path / "nope.png"), write(tmp_path, "empty.png", b""), str(tmp_path)):
        r = chk.check_file(path, D("5"), D("5"))
        assert r.problems == ["unreadable"] and r.kind == "unknown"
        assert r.verdict is FileVerdict.UNUSABLE


@pytest.mark.parametrize(
    "data, mime",
    [
        (b"%!PS-Adobe-3.0 EPSF-3.0\n%%Creator: Adobe Illustrator\n", "application/postscript"),
        (b"\xc5\xd0\xd3\xc6" + b"\x00" * 30, "application/postscript"),
        (b"8BPS\x00\x01" + b"\x00" * 30, "image/vnd.adobe.photoshop"),
        (b"BM" + b"\x00" * 60, "image/bmp"),
        (b"\x00\x00\x00\x18ftypheic" + b"\x00" * 30, "image/heic"),
        (b"\x00\x00\x00\x18ftypavif" + b"\x00" * 30, "image/avif"),
        (b"\x00\x00\x00\x18ftypisom" + b"\x00" * 30, "video/mp4"),
        (b"PK\x03\x04" + b"\x00" * 30, "application/zip"),
        (b"\x1f\x8b\x08" + b"\x00" * 30, "application/gzip"),
        (b"\xd0\xcf\x11\xe0" + b"\x00" * 30, "application/x-ole-storage"),
        (b"MZ\x90\x00" + b"\x00" * 60, "application/octet-stream"),
        (b"just some text, not artwork", "application/octet-stream"),
        (b"<!DOCTYPE html><html><body><svg width='1'></svg></body></html>", "application/octet-stream"),
        (b"<note><to>x</to></note>", "application/octet-stream"),
    ],
)
def test_unsupported_formats(chk, tmp_path, data, mime):
    assert sniff_mime(data) == mime
    r = chk.check_file(write(tmp_path, "file.png", data), D("5"), D("5"))
    assert r.mime == mime and r.kind == "unknown"
    assert r.problems == ["unsupported_format"] and r.verdict is FileVerdict.UNUSABLE


# ---------- PDF ----------

def test_vector_pdf_has_no_dpi_and_is_ok(chk, tmp_path):
    r = chk.check_file(make_pdf(tmp_path, "v.pdf", drawing=True), D("10"), D("10"))
    assert (r.kind, r.mime, r.pages) == ("vector", "application/pdf", 1)
    assert r.dpi_at_size is None and r.width_px is None and r.color_mode is None
    assert r.problems == [] and r.verdict is FileVerdict.OK


def test_pdf_image_dpi_scales_to_final_size(chk, tmp_path):
    # pagina de 10 cm cu o imagine de 600 px pe toata pagina: 152.4 la 10 cm, 304.8 la 5 cm
    path = make_pdf(tmp_path, "r.pdf", image=png_bytes((600, 600)))
    at10 = chk.check_file(path, D("10"), D("10"))
    assert at10.kind == "raster" and (at10.width_px, at10.height_px) == (600, 600)
    assert abs(at10.dpi_at_size - D("152.4")) <= D("0.2") and at10.problems == ["low_dpi"]
    assert at10.color_mode == "RGB"
    at5 = chk.check_file(path, D("5"), D("5"))
    assert abs(at5.dpi_at_size - D("304.8")) <= D("0.3") and at5.verdict is FileVerdict.OK
    at30 = chk.check_file(path, D("30"), D("30"))
    assert at30.problems == ["very_low_dpi"] and at30.verdict is FileVerdict.UNUSABLE
    assert chk.check_file(path, D("0"), D("0")).dpi_at_size is None


def test_pdf_lowest_image_wins_and_mixed_kind(chk, tmp_path):
    doc = pymupdf.open()
    pg = doc.new_page(width=283.46, height=283.46)
    pg.insert_image(pymupdf.Rect(0, 0, 141.73, 141.73), stream=png_bytes((1000, 1000)))
    pg.insert_image(pymupdf.Rect(141.73, 141.73, 283.46, 283.46), stream=png_bytes((100, 100), color=(9, 9, 9)))
    pg.draw_rect(pymupdf.Rect(150, 10, 200, 60), fill=(0, 1, 0))
    path = tmp_path / "m.pdf"
    doc.save(str(path))
    doc.close()
    r = chk.check_file(str(path), D("10"), D("10"))
    assert r.kind == "mixed" and (r.width_px, r.height_px) == (100, 100)
    assert abs(r.dpi_at_size - D("50.8")) <= D("0.2") and r.problems == ["very_low_dpi"]


def test_pdf_fonts_not_embedded_pages_and_aspect(chk, tmp_path):
    path = make_pdf(tmp_path, "t.pdf", page=(283.46, 141.73), text="Miere de salcam", pages=3)
    r = chk.check_file(path, D("10"), D("10"))
    assert r.kind == "vector" and r.pages == 3
    assert r.problems == ["text_not_outlined", "aspect_mismatch", "multi_page"]
    assert r.verdict is FileVerdict.WEAK
    assert chk.check_file(path, D("10"), D("5")).problems == ["text_not_outlined", "multi_page"]


def test_encrypted_pdf_is_unreadable(chk, tmp_path):
    doc = pymupdf.open()
    doc.new_page()
    path = tmp_path / "enc.pdf"
    doc.save(str(path), encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="owner")
    doc.close()
    r = chk.check_file(str(path), D("10"), D("10"))
    assert r.problems == ["unreadable"] and r.mime == "application/pdf"


# ---------- SVG ----------

SVG_VECTOR = (
    '<?xml version="1.0" encoding="UTF-8"?>\n<!-- Generator: test -->\n'
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">'
    '<path d="M0 0L10 10"/><circle cx="5" cy="5" r="3"/></svg>'
)


def test_svg_vector_ok_and_aspect(chk, tmp_path):
    path = write(tmp_path, "logo.svg", SVG_VECTOR)
    r = chk.check_file(path, D("10"), D("5"))
    assert (r.kind, r.mime, r.pages, r.dpi_at_size) == ("vector", "image/svg+xml", 1, None)
    assert r.problems == [] and r.verdict is FileVerdict.OK
    assert chk.check_file(path, D("10"), D("10")).problems == ["aspect_mismatch"]


def test_svg_sizes_from_width_height_units_and_bom(chk, tmp_path):
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="5cm"><rect width="1" height="1"/></svg>'
    bom = write(tmp_path, "a.svg", b"\xef\xbb\xbf" + svg.encode())
    assert chk.check_file(bom, D("10"), D("5")).problems == []
    assert chk.check_file(bom, D("5"), D("5")).problems == ["aspect_mismatch"]
    utf16 = write(tmp_path, "b.svg", svg.encode("utf-16"))
    assert chk.check_file(utf16, D("10"), D("5")).mime == "image/svg+xml"
    # procente sau lipsa: fara verificare de proportii
    loose = write(tmp_path, "c.svg", '<svg xmlns="http://www.w3.org/2000/svg" width="100%"><path d="M0 0"/></svg>')
    assert chk.check_file(loose, D("10"), D("5")).problems == []


def test_svg_text_and_linked_image(chk, tmp_path):
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 100 100">'
        '<text x="1" y="9">Miere</text>'
        '<image xlink:href="https://example.invalid/logo.png" width="50" height="50"/></svg>'
    )
    r = chk.check_file(write(tmp_path, "t.svg", svg), D("10"), D("10"))
    assert r.kind == "mixed" and r.dpi_at_size is None
    assert r.problems == ["text_not_outlined", "linked_image"] and r.verdict is FileVerdict.WEAK


def test_svg_embedded_image_dpi(chk, tmp_path):
    uri = "data:image/png;base64," + base64.b64encode(png_bytes((300, 300), mode="RGBA", color=(1, 2, 3, 255))).decode()
    # imaginea ocupa jumatate din plansa: 300 px pe 5 cm = 152.4 dpi
    half = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><image href="{uri}" width="50" height="50"/></svg>'
    r = chk.check_file(write(tmp_path, "half.svg", half), D("10"), D("10"))
    assert r.kind == "raster" and (r.width_px, r.height_px, r.color_mode) == (300, 300, "RGBA")
    assert r.dpi_at_size == D("152.4") and r.problems == ["low_dpi"]
    # fara dimensiuni: se considera ca umple plansa
    full = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><image href="{uri}"/><path d="M0 0"/></svg>'
    r = chk.check_file(write(tmp_path, "full.svg", full), D("10"), D("10"))
    assert r.kind == "mixed" and r.dpi_at_size == D("76.2") and r.problems == ["very_low_dpi"]
    # data URI stricat: nu cade, nu are dpi
    broken = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><image href="data:image/png;base64,AAAA"/></svg>'
    r = chk.check_file(write(tmp_path, "broken.svg", broken), D("10"), D("10"))
    assert r.dpi_at_size is None and r.problems == []


def test_svg_embedded_image_over_cap_is_ignored(chk, tmp_path, monkeypatch):
    monkeypatch.setattr(checker_mod, "MAX_EMBEDDED_IMAGE_BYTES", 10)
    uri = "data:image/png;base64," + base64.b64encode(png_bytes((300, 300))).decode()
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><image href="{uri}"/></svg>'
    assert chk.check_file(write(tmp_path, "big.svg", svg), D("10"), D("10")).dpi_at_size is None


def test_svg_external_entities_are_never_resolved(chk, tmp_path):
    secret = write(tmp_path, "secret.txt", "TOP-SECRET")
    svg = (
        '<?xml version="1.0"?>\n'
        f'<!DOCTYPE svg [<!ENTITY xxe SYSTEM "file://{secret}"><!ENTITY a "aaaaaaaaaa">'
        '<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;"><!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;">]>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
        '<script>alert(1)</script><path d="M0 0"/><desc>&xxe;&c;</desc></svg>'
    )
    r = chk.check_file(write(tmp_path, "xxe.svg", svg), D("10"), D("10"))
    assert r.kind == "vector" and r.verdict is FileVerdict.OK
    assert "TOP-SECRET" not in r.model_dump_json()


def test_svg_without_root_tag_close_is_unreadable(chk, tmp_path):
    # trece de detectia de tip, dar eticheta radacina nu se inchide
    r = chk.check_file(write(tmp_path, "x.svg", "<svg viewBox='0 0 1 1'"), D("1"), D("1"))
    assert r.problems == ["unreadable"] and r.mime == "image/svg+xml"


# ---------- texte pentru client ----------

def test_describe_problems_covers_every_code():
    report = FileReport(kind="raster", mime="image/png", dpi_at_size=D("72.5"),
                        verdict=FileVerdict.UNUSABLE, problems=sorted(ALL_CODES))
    texts = describe_problems(report, RULES)
    assert len(texts) == len(ALL_CODES)
    for text in texts:
        assert text.endswith(".") and "—" not in text and "–" not in text
        assert len(text) < 400
    joined = " ".join(texts)
    assert "72 DPI" in joined and "300 DPI" in joined
    assert "vectoriza" in joined and "contra cost" in joined


def test_describe_problems_order_dedup_unknown_and_default_rules():
    report = FileReport(kind="raster", mime="image/png", verdict=FileVerdict.WEAK,
                        problems=["multi_page", "low_dpi", "multi_page", "cod_necunoscut"])
    texts = describe_problems(report)
    assert len(texts) == 2
    assert texts[0].startswith("Fișierul are mai multe pagini")
    assert "DPI la dimensiunea" not in texts[1] and "minimum 150 DPI" in texts[1]
    assert describe_problems(FileReport(kind="vector", mime="image/svg+xml", verdict=FileVerdict.OK)) == []


def test_verdict_for():
    assert verdict_for([]) is FileVerdict.OK
    assert verdict_for(["opaque_background"]) is FileVerdict.OK
    assert verdict_for(["opaque_background", "cmyk_jpeg"]) is FileVerdict.WEAK
    assert verdict_for(["low_dpi", "unreadable"]) is FileVerdict.UNUSABLE

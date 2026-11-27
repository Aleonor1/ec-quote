import os
import shutil

import pytest
from PIL import Image, ImageChops, ImageDraw

from ec_quote.contracts import MockupResult
from ec_quote.mockup import MockupService, TemplateError, UnsupportedDesignError, make_mockup
from ec_quote.mockup.compose import (
    apply_shade, has_transparency, load_design, prepare_label,
)
from .conftest import GRAY, MAGENTA, write_template


def _is_magenta(pixel):
    return abs(pixel[0] - MAGENTA[0]) < 30 and pixel[1] < 40 and abs(pixel[2] - MAGENTA[2]) < 30


def _is_gray(pixel):
    return all(abs(c - 128) < 12 for c in pixel)


def _outside_untouched(image, quad, grow=6):
    """Diferenta maxima fata de fotografia goala, in afara zonei (largita cu cativa pixeli)."""
    zone = Image.new("L", image.size, 255)
    cx = sum(p[0] for p in quad) / 4
    cy = sum(p[1] for p in quad) / 4
    wide = []
    for x, y in quad:
        wide.append((x + (grow if x > cx else -grow), y + (grow if y > cy else -grow)))
    ImageDraw.Draw(zone).polygon(wide, fill=0)
    diff = ImageChops.difference(image, Image.new("RGB", image.size, GRAY)).convert("L")
    return ImageChops.multiply(diff, zone).getextrema()[1]


def test_solid_design_lands_inside_the_quad_and_not_outside(tmp_path, solid_design):
    quad = [(300, 200), (700, 200), (700, 600), (300, 600)]
    write_template(tmp_path / "t", quad=[list(p) for p in quad])
    result = MockupService(tmp_path / "t").make_mockup(solid_design, "orice", str(tmp_path / "out"))
    assert isinstance(result, MockupResult) and result.template_id == "plat"
    image = Image.open(result.image_path).convert("RGB")
    assert image.format is None and image.size == (1000, 800)
    for point in ((500, 400), (310, 210), (690, 590), (310, 590), (690, 210)):
        assert _is_magenta(image.getpixel(point)), point
    for point in ((290, 400), (710, 400), (500, 190), (500, 610), (50, 50)):
        assert _is_gray(image.getpixel(point)), point
    assert _outside_untouched(image, quad) < 20


def test_perspective_quad(tmp_path, solid_design):
    quad = [(260, 180), (720, 240), (700, 610), (300, 560)]
    write_template(tmp_path / "t", quad=[list(p) for p in quad])
    result = MockupService(tmp_path / "t").make_mockup(solid_design, "", str(tmp_path / "out"))
    image = Image.open(result.image_path).convert("RGB")
    assert _is_magenta(image.getpixel((495, 400)))
    assert _outside_untouched(image, quad) < 20
    # designul patrat pastreaza proportiile: nu umple toata latimea zonei
    magenta = sum(1 for x in range(0, 1000, 2) for y in range(0, 800, 2) if _is_magenta(image.getpixel((x, y))))
    assert 20000 < magenta < 45000


def test_cylinder_template_stays_in_the_extended_zone(tmp_path, solid_design):
    quad = [(300, 200), (700, 200), (700, 560), (300, 560)]
    write_template(tmp_path / "t", quad=[list(p) for p in quad],
                   cylinder={"wrap_degrees": 110, "arc_px": 24, "edge_shade": 0.3})
    result = MockupService(tmp_path / "t").make_mockup(solid_design, "", str(tmp_path / "out"))
    image = Image.open(result.image_path).convert("RGB")
    extended = [(300, 200), (700, 200), (700, 584), (300, 584)]
    assert _outside_untouched(image, extended) < 20
    middle = image.getpixel((500, 400))
    assert middle[0] > 180 and middle[1] < 40
    # arcul: sus la mijloc eticheta incepe mai jos decat ar incepe fara curbura
    column = [image.getpixel((500, y)) for y in range(200, 600)]
    first = next(i for i, p in enumerate(column) if p[1] < 60)
    assert first >= 20


def test_aspect_ratio_is_preserved(tmp_path):
    design = tmp_path / "lat.png"
    Image.new("RGB", (800, 200), MAGENTA).save(design)
    write_template(tmp_path / "t")
    result = MockupService(tmp_path / "t").make_mockup(str(design), "", str(tmp_path / "out"))
    image = Image.open(result.image_path).convert("RGB")
    xs = [x for x in range(1000) if _is_magenta(image.getpixel((x, 400)))]
    ys = [y for y in range(800) if _is_magenta(image.getpixel((500, y)))]
    assert len(xs) == pytest.approx(400, abs=4)
    assert len(ys) == pytest.approx(100, abs=4)


def test_transparent_design_keeps_transparency(tmp_path):
    design = tmp_path / "logo.png"
    logo = Image.new("RGBA", (600, 600), (0, 0, 0, 0))
    ImageDraw.Draw(logo).ellipse((150, 150, 450, 450), fill=MAGENTA + (255,))
    logo.save(design)
    write_template(tmp_path / "t")
    result = MockupService(tmp_path / "t").make_mockup(str(design), "", str(tmp_path / "out"))
    image = Image.open(result.image_path).convert("RGB")
    assert _is_magenta(image.getpixel((500, 400)))
    # marginile goale se taie, cercul umple zona; colturile zonei raman fotografie
    assert _is_magenta(image.getpixel((310, 400)))
    assert _is_gray(image.getpixel((310, 210)))
    assert _is_gray(image.getpixel((690, 590)))


@pytest.mark.parametrize("shape", ["rounded", "circle", "oval"])
def test_opaque_design_gets_the_label_shape(tmp_path, solid_design, shape):
    write_template(tmp_path / "t", label_shape=shape)
    result = MockupService(tmp_path / "t").make_mockup(solid_design, "", str(tmp_path / "out"))
    image = Image.open(result.image_path).convert("RGB")
    assert _is_magenta(image.getpixel((500, 400)))
    assert _is_gray(image.getpixel((302, 202)))
    assert _is_magenta(image.getpixel((500, 210)))


def test_circle_crops_a_wide_design_to_a_square(tmp_path):
    label = prepare_label(Image.new("RGBA", (400, 200), MAGENTA + (255,)), (300, 300), "circle", 0)
    assert label.getchannel("A").getbbox() == (0, 0, 300, 300)
    assert label.getpixel((2, 2))[3] == 0 and label.getpixel((150, 150))[3] == 255


def test_fully_transparent_design_is_rejected():
    with pytest.raises(UnsupportedDesignError, match="transparent"):
        prepare_label(Image.new("RGBA", (50, 50), (0, 0, 0, 0)), (100, 100), "rounded", 0)


def test_deterministic_output(tmp_path, solid_design, service):
    first = service.make_mockup(solid_design, "borcan de miere", str(tmp_path / "a"))
    second = service.make_mockup(solid_design, "borcan de miere", str(tmp_path / "b"))
    again = MockupService().make_mockup(solid_design, "borcan de miere", str(tmp_path / "a"))
    name = os.path.basename(first.image_path)
    assert name == os.path.basename(second.image_path) and again.image_path == first.image_path
    assert open(first.image_path, "rb").read() == open(second.image_path, "rb").read()
    other = tmp_path / "alt.png"
    Image.new("RGB", (400, 400), (0, 90, 200)).save(other)
    assert service.make_mockup(str(other), "borcan", str(tmp_path / "a")).image_path != first.image_path
    assert not [p for p in (tmp_path / "a").iterdir() if p.name.endswith(".tmp")]


@pytest.mark.parametrize("hint, template_id", [
    ("borcan miere", "borcan"), ("pahar cafea", "pahar-cafea"), ("cutie", "cutie"),
    ("sticla vin", "sticla"), ("punga kraft", "punga-kraft"),
])
def test_every_shipped_template_renders(tmp_path, solid_design, service, hint, template_id):
    result = service.make_mockup(solid_design, hint, str(tmp_path))
    assert result.template_id == template_id
    with Image.open(result.image_path) as image:
        assert image.format == "JPEG"
        assert max(image.size) == 1600
        rgb = image.convert("RGB")
    quad = service.choose_template(hint).manifest.quad
    cx = round(sum(p[0] for p in quad) / 4)
    cy = round(sum(p[1] for p in quad) / 4)
    r, g, b = rgb.getpixel((cx, cy))
    assert r > 150 and g < 60 and b > 90   # magenta, cu lumina sablonului peste
    with Image.open(service.choose_template(hint).photo_path) as photo:
        untouched = photo.convert("RGB").getpixel((20, 20))
    assert all(abs(a - b) < 6 for a, b in zip(rgb.getpixel((20, 20)), untouched))


def test_large_photo_is_scaled_to_1600(tmp_path, solid_design):
    write_template(tmp_path / "t", size=(3200, 2400),
                   quad=[[960, 640], [2240, 640], [2240, 1920], [960, 1920]])
    result = MockupService(tmp_path / "t").make_mockup(solid_design, "", str(tmp_path / "out"))
    image = Image.open(result.image_path).convert("RGB")
    assert image.size == (1600, 1200)
    assert _is_magenta(image.getpixel((800, 600)))
    assert _is_gray(image.getpixel((470, 600))) and _is_magenta(image.getpixel((490, 600)))


def test_shade_mask_and_opacity(tmp_path, solid_design):
    folder = write_template(tmp_path / "t", blend={"shade": "shade.png", "mask": "mask.png",
                                                    "strength": 1.0, "opacity": 0.5})
    shade = Image.new("L", (1000, 800), 128)
    shade.paste(64, (300, 200, 500, 600))      # jumatatea stanga in umbra
    shade.save(folder / "shade.png")
    mask = Image.new("L", (1000, 800), 255)
    mask.paste(0, (300, 500, 700, 600))        # banda de jos acoperita
    mask.save(folder / "mask.png")
    result = MockupService(tmp_path / "t").make_mockup(solid_design, "", str(tmp_path / "out"))
    image = Image.open(result.image_path).convert("RGB")
    lit, dark = image.getpixel((600, 300)), image.getpixel((400, 300))
    assert lit[0] == pytest.approx((230 + 128) / 2, abs=8)      # opacitate 0.5 peste gri
    assert dark[0] == pytest.approx((115 + 128) / 2, abs=8)     # multiply cu 0.5
    assert _is_gray(image.getpixel((500, 550)))


def test_photo_luminance_blend_follows_the_photo(tmp_path, solid_design):
    folder = write_template(tmp_path / "t", blend={"photo_luminance": True, "strength": 1.0})
    photo = Image.new("RGB", (1000, 800), (160, 160, 160))
    photo.paste((80, 80, 80), (300, 0, 500, 800))
    photo.save(folder / "photo.png")
    result = MockupService(tmp_path / "t").make_mockup(solid_design, "", str(tmp_path / "out"))
    image = Image.open(result.image_path).convert("RGB")
    assert image.getpixel((400, 400))[0] < image.getpixel((600, 400))[0] - 60


def test_apply_shade_neutral_dark_light():
    layer = Image.new("RGBA", (3, 1), (100, 100, 100, 200))
    shade = Image.new("L", (3, 1))
    shade.putdata([128, 64, 192])
    out = apply_shade(layer, shade, 1.0)
    neutral, dark, light = (out.getpixel((x, 0)) for x in range(3))
    assert neutral == (100, 100, 100, 200)
    assert dark[0] == pytest.approx(50, abs=1) and dark[3] == 200
    assert light[0] == pytest.approx(100 + 155 * 128 / 255, abs=2)
    assert apply_shade(layer, shade, 0) is layer
    half = apply_shade(layer, shade, 0.5).getpixel((1, 0))[0]
    assert dark[0] < half < 100


# ---------- intrari neacceptate ----------

@pytest.mark.parametrize("fmt, ext", [("PNG", "png"), ("JPEG", "jpg"), ("WEBP", "webp")])
def test_accepted_raster_formats(tmp_path, fmt, ext):
    path = tmp_path / ("design." + ext)
    Image.new("RGB", (120, 80), MAGENTA).save(path, fmt)
    design = load_design(path)
    assert design.mode == "RGBA" and design.size == (120, 80)
    assert not has_transparency(design)


def test_cmyk_jpeg_and_palette_png_are_converted(tmp_path):
    cmyk = tmp_path / "c.jpg"
    Image.new("CMYK", (60, 40), (0, 255, 0, 0)).save(cmyk, "JPEG")
    assert load_design(cmyk).mode == "RGBA"
    pal = tmp_path / "p.png"
    indexed = Image.new("RGB", (60, 40), MAGENTA).convert("P")
    indexed.save(pal, transparency=indexed.getpixel((0, 0)))
    assert has_transparency(load_design(pal))


def test_huge_design_is_reduced(tmp_path):
    path = tmp_path / "mare.png"
    Image.new("RGB", (5000, 1000), MAGENTA).save(path)
    assert load_design(path).size == (2400, 480)


@pytest.mark.parametrize("name, content", [
    ("design.pdf", b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"),
    ("design.svg", b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="1" height="1"/></svg>'),
    ("design.png", b"<svg></svg>"),
    ("design.png", b""),
    ("design.jpg", b"\xff\xd8\xff\xe0 trunchiat"),
    ("design.txt", b"salut"),
])
def test_non_raster_inputs_raise_typed_error(tmp_path, service, name, content):
    path = tmp_path / name
    path.write_bytes(content)
    with pytest.raises(UnsupportedDesignError):
        service.make_mockup(str(path), "borcan", str(tmp_path / "out"))
    assert not (tmp_path / "out").exists()


def test_other_raster_formats_and_missing_files_are_rejected(tmp_path, service):
    for fmt, ext in (("GIF", "gif"), ("BMP", "bmp"), ("TIFF", "tif")):
        path = tmp_path / ("design." + ext)
        Image.new("RGB", (20, 20)).save(path, fmt)
        with pytest.raises(UnsupportedDesignError, match="format neacceptat"):
            load_design(path)
    # extensia nu pacaleste verificarea
    shutil.copy(tmp_path / "design.gif", tmp_path / "fals.png")
    with pytest.raises(UnsupportedDesignError):
        load_design(tmp_path / "fals.png")
    with pytest.raises(UnsupportedDesignError, match="nu exista"):
        service.make_mockup(str(tmp_path / "lipsa.png"), "borcan", str(tmp_path))
    with pytest.raises(UnsupportedDesignError):
        load_design(tmp_path)


def test_decompression_bomb_is_rejected(tmp_path, monkeypatch):
    path = tmp_path / "bomba.png"
    Image.new("L", (400, 400)).save(path)
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)
    with pytest.raises(UnsupportedDesignError):
        load_design(path)


def test_template_files_broken_after_load(tmp_path, solid_design):
    folder = write_template(tmp_path / "t", blend={"shade": "shade.png"})
    Image.new("L", (1000, 800), 128).save(folder / "shade.png")
    svc = MockupService(tmp_path / "t")
    assert svc.templates
    (folder / "shade.png").write_bytes(b"stricat")
    with pytest.raises(TemplateError):
        svc.make_mockup(solid_design, "", str(tmp_path / "out"))
    Image.new("L", (1000, 800), 128).save(folder / "shade.png")
    (folder / "photo.png").write_bytes(b"stricat")
    with pytest.raises(TemplateError):
        svc.make_mockup(solid_design, "", str(tmp_path / "out"))


def test_module_level_make_mockup_uses_default_templates(tmp_path, solid_design):
    result = make_mockup(solid_design, "pahar de cafea", str(tmp_path))
    assert result.template_id == "pahar-cafea"

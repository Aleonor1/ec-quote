"""Compozitia designului pe fotografia sablonului."""
from __future__ import annotations

import hashlib
import os
import warnings
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps, ImageStat, UnidentifiedImageError

from .errors import TemplateError, UnsupportedDesignError
from .templates import Template
from .warp import SUPERSAMPLE, cylinder_wrap, extend_quad, quad_size, unrolled_width, warp_to_quad

OUTPUT_LONG_EDGE = 1600
JPEG_QUALITY = 90
ACCEPTED_FORMATS = frozenset({"PNG", "JPEG", "MPO", "WEBP"})
_MAX_DESIGN_EDGE = 2400
_ALPHA_SOLID = 250   # sub acest minim de alfa, designul are transparenta
_ALPHA_VISIBLE = 8


def load_design(path: str | Path) -> Image.Image:
    """Citeste designul ca RGBA. Accepta doar raster PNG/JPEG/WEBP (dupa continut, nu dupa nume)."""
    path = Path(path)
    if not path.is_file():
        raise UnsupportedDesignError("designul nu exista: %s" % path)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as im:
                if im.format not in ACCEPTED_FORMATS:
                    raise UnsupportedDesignError(
                        "format neacceptat (%s); doar PNG, JPEG sau WEBP" % (im.format or "necunoscut"))
                im.seek(0)
                im.draft("RGB", (_MAX_DESIGN_EDGE, _MAX_DESIGN_EDGE))
                design = ImageOps.exif_transpose(im).convert("RGBA")
    except UnsupportedDesignError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, EOFError,
            Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise UnsupportedDesignError("designul nu este o imagine raster lizibila: %s" % path.name) from exc
    design.thumbnail((_MAX_DESIGN_EDGE, _MAX_DESIGN_EDGE), Image.Resampling.LANCZOS)
    return design


def has_transparency(design: Image.Image) -> bool:
    return design.getchannel("A").getextrema()[0] < _ALPHA_SOLID


def _shape_mask(size: tuple[int, int], shape: str) -> Image.Image:
    w, h = size
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    if shape in ("circle", "oval"):
        draw.ellipse((0, 0, w - 1, h - 1), fill=255)
    elif shape == "rounded":
        draw.rounded_rectangle((0, 0, w - 1, h - 1), radius=max(2, round(min(w, h) * 0.06)), fill=255)
    else:
        draw.rectangle((0, 0, w - 1, h - 1), fill=255)
    return mask


def prepare_label(design: Image.Image, canvas: tuple[int, int], shape: str, padding: float) -> Image.Image:
    """Designul incadrat in zona desfasurata, cu proportiile pastrate.

    Designul transparent ramane transparent (marginile goale se taie); cel opac ia forma etichetei.
    """
    transparent = has_transparency(design)
    if transparent:
        box = design.getchannel("A").point(lambda v: 255 if v > _ALPHA_VISIBLE else 0).getbbox()
        if box is None:
            raise UnsupportedDesignError("designul este complet transparent")
        design = design.crop(box)
    else:
        design = design.convert("RGB").convert("RGBA")
        if shape == "circle":
            side = min(design.size)
            left, top = (design.width - side) // 2, (design.height - side) // 2
            design = design.crop((left, top, left + side, top + side))

    cw, ch = canvas
    pad = padding * min(cw, ch)
    scale = min((cw - 2 * pad) / design.width, (ch - 2 * pad) / design.height)
    size = (max(1, round(design.width * scale)), max(1, round(design.height * scale)))
    fitted = design.resize(size, Image.Resampling.LANCZOS)
    if not transparent:
        fitted.putalpha(_shape_mask(size, shape))
    label = Image.new("RGBA", canvas, (0, 0, 0, 0))
    label.paste(fitted, ((cw - size[0]) // 2, (ch - size[1]) // 2))
    return label


def _open_gray(path: Path, size: tuple[int, int]) -> Image.Image:
    try:
        with Image.open(path) as im:
            gray = im.convert("L")
    except (OSError, ValueError) as exc:
        raise TemplateError("fisier de sablon ilizibil: %s" % path) from exc
    return gray if gray.size == size else gray.resize(size, Image.Resampling.BILINEAR)


def luminance_shade(photo: Image.Image, quad: list[tuple[float, float]]) -> Image.Image:
    """Harta de umbre luata din fotografie: luminozitatea raportata la media din zona."""
    gray = photo.convert("L").filter(ImageFilter.GaussianBlur(1.2))
    zone = Image.new("L", photo.size, 0)
    ImageDraw.Draw(zone).polygon(quad, fill=255)
    mean = max(1.0, ImageStat.Stat(gray, zone).mean[0])
    return gray.point([max(0, min(255, round(128 * v / mean))) for v in range(256)])


def apply_shade(layer: Image.Image, shade: Image.Image, strength: float) -> Image.Image:
    """Multiply pentru valorile sub 128 (umbra), screen pentru cele peste (luciu)."""
    if strength <= 0:
        return layer
    if strength < 1:
        shade = Image.blend(Image.new("L", shade.size, 128), shade, strength)
    dark = shade.point([min(255, v * 2) for v in range(256)])
    light = shade.point([max(0, (v - 128) * 2) for v in range(256)])
    rgb = layer.convert("RGB")
    rgb = ImageChops.multiply(rgb, Image.merge("RGB", (dark, dark, dark)))
    rgb = ImageChops.screen(rgb, Image.merge("RGB", (light, light, light)))
    rgb.putalpha(layer.getchannel("A"))
    return rgb


def render_mockup(template: Template, design: Image.Image) -> Image.Image:
    """Imaginea RGB finala, cu latura lunga de cel mult OUTPUT_LONG_EDGE."""
    manifest = template.manifest
    try:
        with Image.open(template.photo_path) as im:
            photo = im.convert("RGB")
    except (OSError, ValueError) as exc:
        raise TemplateError("fotografia nu se poate citi: %s" % template.photo_path) from exc
    scale = min(1.0, OUTPUT_LONG_EDGE / max(photo.size))
    if scale < 1.0:
        photo = photo.resize((round(photo.width * scale), round(photo.height * scale)),
                             Image.Resampling.LANCZOS)
    quad = [(x * scale, y * scale) for x, y in manifest.quad]

    ss = SUPERSAMPLE
    big_quad = [(x * ss, y * ss) for x, y in quad]
    width, height = quad_size(big_quad)
    cyl = manifest.cylinder
    canvas = (max(8, round(unrolled_width(width, cyl.wrap_degrees if cyl else None))),
              max(8, round(height)))
    label = prepare_label(design, canvas, manifest.label_shape, manifest.padding)
    if cyl:
        arc = cyl.arc_px * scale * ss
        label = cylinder_wrap(label, max(8, round(width)), cyl.wrap_degrees, arc, cyl.edge_shade)
        big_quad = extend_quad(big_quad, arc)
    layer = warp_to_quad(label, big_quad, (photo.width * ss, photo.height * ss))
    layer = layer.resize(photo.size, Image.Resampling.LANCZOS)

    blend = manifest.blend
    if blend.shade:
        layer = apply_shade(layer, _open_gray(template.file(blend.shade), photo.size), blend.strength)
    elif blend.photo_luminance:
        layer = apply_shade(layer, luminance_shade(photo, quad), blend.strength)
    alpha = layer.getchannel("A")
    if blend.mask:
        alpha = ImageChops.multiply(alpha, _open_gray(template.file(blend.mask), photo.size))
    if blend.opacity < 1:
        alpha = alpha.point([round(v * blend.opacity) for v in range(256)])
    layer.putalpha(alpha)
    return Image.alpha_composite(photo.convert("RGBA"), layer).convert("RGB")


def digest(*parts: bytes) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(len(part).to_bytes(8, "big"))
        h.update(part)
    return h.hexdigest()[:16]


def template_fingerprint(template: Template) -> bytes:
    """Octetii care definesc sablonul: manifestul si fisierele lui."""
    names = [template.manifest.photo, template.manifest.blend.shade, template.manifest.blend.mask]
    h = hashlib.sha256(template.manifest.model_dump_json().encode("utf-8"))
    for name in names:
        if name:
            h.update(template.file(name).read_bytes())
    return h.digest()


def save_jpeg(image: Image.Image, path: Path) -> None:
    """Scriere atomica: fisierul apare complet sau deloc."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(".%s.%d.tmp" % (path.name, os.getpid()))
    try:
        image.convert("RGB").save(tmp, "JPEG", quality=JPEG_QUALITY, optimize=True)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()

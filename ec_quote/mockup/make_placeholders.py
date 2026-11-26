"""Genereaza sabloanele PROVIZORII (desenate, nu fotografiate) din templates/mockups/.

Rulare, din directorul ec-quote:
    python3 -m ec_quote.mockup.make_placeholders [director_iesire] [--fara-text]

Rezultatul este determinist. Sabloanele reale (fotografii) le inlocuiesc pe acestea;
vezi templates/mockups/README.md.
"""
from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .fonts import load_font
from .service import default_templates_dir
from .warp import apply_coeffs, perspective_coeffs

W, H = 1600, 1200
S = 2  # obiectele se deseneaza la dublu
WATERMARK = "SABLON PROVIZORIU"

Color = tuple[int, int, int]


def _px(v: float) -> int:
    return round(v * S)


def _box(x0: float, y0: float, x1: float, y1: float) -> tuple[int, int, int, int]:
    return (_px(x0), _px(y0), _px(x1), _px(y1))


def _pts(points) -> list[tuple[int, int]]:
    return [(_px(x), _px(y)) for x, y in points]


def _tint(color: Color, m: float) -> Color:
    """m sub 1 intuneca, peste 1 duce spre alb."""
    if m <= 1:
        return tuple(round(c * max(0.0, m)) for c in color)
    k = min(1.0, m - 1)
    return tuple(round(c + (255 - c) * k) for c in color)


def cyl_light(t: float, spec: float = 0.35) -> float:
    """Lumina pe un cilindru, cu sursa in stanga sus. t = 0..1 pe latime."""
    a = (t - 0.5) * math.pi
    diffuse = 0.40 + 0.64 * max(0.0, math.cos(a * 0.94)) ** 1.1
    diffuse *= 1.0 + 0.10 * math.cos((t - 0.30) * math.pi)
    shine = spec * math.exp(-((t - 0.26) / 0.035) ** 2) + spec * 0.35 * math.exp(-((t - 0.82) / 0.02) ** 2)
    return diffuse + shine


def _columns(width: int, height: int, colors: list) -> Image.Image:
    strip = Image.new("RGB" if isinstance(colors[0], tuple) else "L", (width, 1))
    strip.putdata(colors)
    return strip.resize((width, height), Image.Resampling.NEAREST)


def lit(width: int, height: int, color: Color, spec: float = 0.35) -> Image.Image:
    return _columns(width, height, [_tint(color, cyl_light((i + 0.5) / width, spec)) for i in range(width)])


def shade_strip(width: int, height: int, spec: float = 0.10) -> Image.Image:
    """Aceeasi lumina ca harta de umbre pentru eticheta: 128 = neutru."""
    ref = cyl_light(0.5, 0.0)
    return _columns(width, height, [
        max(0, min(255, round(128 * cyl_light((i + 0.5) / width, spec) / ref))) for i in range(width)
    ])


def _mask(draw_fn) -> Image.Image:
    mask = Image.new("L", (W * S, H * S), 0)
    draw_fn(ImageDraw.Draw(mask))
    return mask


def _paste(layer: Image.Image, image: Image.Image, origin: tuple[float, float], mask: Image.Image) -> None:
    """Lipeste `image` la `origin` (in pixeli finali), vizibil doar unde `mask` este alb."""
    full = Image.new(image.mode, layer.size, 0)
    full.paste(image, (_px(origin[0]), _px(origin[1])))
    layer.paste(full, (0, 0), mask)


def _into_quad(image: Image.Image, quad) -> Image.Image:
    """Intinde `image` pe patrulaterul `quad` (pixeli finali), pe un strat cat toata scena."""
    w, h = image.size
    coeffs = perspective_coeffs(_pts(quad), [(0, 0), (w, 0), (w, h), (0, h)])
    return image.transform((W * S, H * S), Image.Transform.PERSPECTIVE, coeffs, Image.Resampling.BILINEAR)


def studio() -> Image.Image:
    """Fundal neutru de studio: perete, podea, trecere moale, vigneta usoara."""
    horizon = 800
    column = []
    for y in range(H):
        if y < horizon:
            k = y / horizon
            column.append(tuple(round(a + (b - a) * k) for a, b in zip((229, 226, 221), (214, 210, 204))))
        else:
            k = (y - horizon) / (H - horizon)
            column.append(tuple(round(a + (b - a) * k) for a, b in zip((203, 199, 192), (224, 221, 215))))
    strip = Image.new("RGB", (1, H))
    strip.putdata(column)
    bg = strip.resize((W, H), Image.Resampling.NEAREST).filter(ImageFilter.GaussianBlur(26))
    vignette = Image.radial_gradient("L").resize((W * 2, H * 2), Image.Resampling.BILINEAR)
    vignette = vignette.crop((W // 2, H // 2, W // 2 + W, H // 2 + H))
    vignette = vignette.point([255 - round(v * 0.22) for v in range(256)])
    return ImageChops.multiply(bg, Image.merge("RGB", (vignette,) * 3))


def shadow(scene: Image.Image, cx: float, cy: float, rx: float, ry: float, strength: float = 0.42) -> None:
    """Umbra de contact plus umbra aruncata spre dreapta."""
    for dx, k, blur, power in ((0.0, 1.0, 14, strength), (rx * 0.45, 1.5, 38, strength * 0.55)):
        mask = Image.new("L", scene.size, 0)
        ImageDraw.Draw(mask).ellipse((cx + dx - rx * k, cy - ry * k, cx + dx + rx * k, cy + ry * k),
                                     fill=round(255 * power))
        mask = mask.filter(ImageFilter.GaussianBlur(blur))
        scene.paste(Image.new("RGB", scene.size, (40, 36, 32)), (0, 0), mask)


def finish(scene: Image.Image, layer: Image.Image, watermark: bool) -> Image.Image:
    small = layer.resize((W, H), Image.Resampling.LANCZOS)
    out = Image.alpha_composite(scene.convert("RGBA"), small).convert("RGB")
    if watermark:
        ImageDraw.Draw(out).text((40, H - 36), WATERMARK, font=load_font(24, "bold"),
                                 fill=(150, 146, 140), anchor="ls")
    return out


def _new_layer() -> Image.Image:
    return Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))


def _shade_base() -> Image.Image:
    return Image.new("L", (W * S, H * S), 128)


def _small(shade: Image.Image) -> Image.Image:
    return shade.resize((W, H), Image.Resampling.LANCZOS)


def _ridges(layer: Image.Image, x0: float, x1: float, y0: float, y1: float, count: int, alpha: int) -> None:
    """Striatii verticale pe capac, mai dese spre margini, ca pe un cilindru."""
    overlay = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for i in range(1, count):
        a = (i / count - 0.5) * math.pi
        x = (x0 + x1) / 2 + math.sin(a) * (x1 - x0) / 2
        draw.line((_px(x), _px(y0), _px(x), _px(y1)), fill=(0, 0, 0, alpha), width=S)
    layer.alpha_composite(overlay)


# ---------- obiecte ----------

def jar(watermark: bool):
    scene = studio()
    shadow(scene, 800, 962, 250, 22)
    layer = _new_layer()
    body = _mask(lambda d: d.rounded_rectangle(_box(560, 392, 1040, 965), radius=_px(64), fill=255))
    _paste(layer, lit(_px(480), _px(573), (212, 137, 28), 0.42), (560, 392), body)
    # sticla goala deasupra mierii
    glass = _mask(lambda d: d.rounded_rectangle(_box(560, 392, 1040, 520), radius=_px(64), fill=255))
    glass = ImageChops.multiply(glass, _mask(lambda d: d.rectangle(_box(560, 392, 1040, 448), fill=255)))
    _paste(layer, lit(_px(480), _px(60), (226, 214, 190), 0.5), (560, 392), glass)
    overlay = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    ImageDraw.Draw(overlay).ellipse(_box(566, 438, 1034, 460), fill=(170, 100, 14, 150))
    layer.alpha_composite(Image.composite(overlay, Image.new("RGBA", layer.size, (0, 0, 0, 0)), body))
    neck = _mask(lambda d: d.rectangle(_box(598, 352, 1002, 400), fill=255))
    _paste(layer, lit(_px(404), _px(48), (214, 204, 184), 0.5), (598, 352), neck)
    lid = _mask(lambda d: d.rounded_rectangle(_box(584, 262, 1016, 360), radius=_px(14), fill=255))
    _paste(layer, lit(_px(432), _px(98), (58, 60, 68), 0.5), (584, 262), lid)
    _ridges(layer, 584, 1016, 286, 352, 46, 70)
    overlay = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    ImageDraw.Draw(overlay).rounded_rectangle(_box(584, 262, 1016, 282), radius=_px(10), fill=(255, 255, 255, 34))
    layer.alpha_composite(overlay)

    shade = _shade_base()
    _paste(shade, shade_strip(_px(480), _px(573)), (560, 392), body)
    manifest = {
        "id": "borcan", "title": "Borcan de sticlă (provizoriu)", "placeholder": True, "default": False,
        "photo": "photo.jpg",
        "keywords": ["borcan", "borcane", "miere", "dulceață", "dulceturi", "gem", "zacuscă", "murături",
                     "compot", "conserve", "apicultor", "stupină", "cremă", "lumânare"],
        "quad": [[612, 540], [988, 540], [988, 850], [612, 850]],
        "label_shape": "rounded", "padding": 0.03,
        "cylinder": {"wrap_degrees": 103, "arc_px": 14, "edge_shade": 0},
        "blend": {"shade": "shade.png", "photo_luminance": False, "strength": 0.85, "opacity": 1.0,
                  "mask": None},
    }
    return manifest, finish(scene, layer, watermark), _small(shade)


def cup(watermark: bool):
    scene = studio()
    shadow(scene, 800, 962, 170, 18)
    layer = _new_layer()
    quad = [(590, 345), (1010, 345), (950, 965), (650, 965)]
    body = _mask(lambda d: d.polygon(_pts(quad), fill=255))
    foot = _mask(lambda d: d.ellipse(_box(650, 950, 950, 980), fill=255))
    body = ImageChops.lighter(body, foot)
    kraft = lit(_px(420), _px(640), (188, 143, 98), 0.16)
    wrapped = _into_quad(kraft, [(590, 345), (1010, 345), (950, 985), (650, 985)])
    layer.paste(wrapped, (0, 0), body)
    # capac
    rim = _mask(lambda d: d.rounded_rectangle(_box(572, 300, 1028, 352), radius=_px(18), fill=255))
    _paste(layer, lit(_px(456), _px(52), (38, 38, 42), 0.45), (572, 300), rim)
    dome = _mask(lambda d: d.polygon(_pts([(600, 302), (624, 246), (976, 246), (1000, 302)]), fill=255))
    _paste(layer, lit(_px(400), _px(58), (46, 46, 50), 0.4), (600, 245), dome)
    top = _mask(lambda d: d.rounded_rectangle(_box(622, 236, 978, 254), radius=_px(8), fill=255))
    _paste(layer, lit(_px(356), _px(18), (62, 62, 66), 0.3), (622, 236), top)
    overlay = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    ImageDraw.Draw(overlay).polygon(_pts([(592, 352), (1008, 352), (1006, 372), (594, 372)]), fill=(0, 0, 0, 46))
    layer.alpha_composite(overlay)

    shade = _shade_base()
    strip = _into_quad(shade_strip(_px(420), _px(640), 0.06), [(590, 345), (1010, 345), (950, 985), (650, 985)])
    shade.paste(strip, (0, 0), body)
    manifest = {
        "id": "pahar-cafea", "title": "Pahar de cafea (provizoriu)", "placeholder": True, "default": False,
        "photo": "photo.jpg",
        "keywords": ["pahar", "pahare", "cafea", "cafenea", "coffee", "espresso", "cappuccino", "latte",
                     "ceai", "to go", "take away", "barista"],
        "quad": [[644, 500], [956, 500], [931, 800], [669, 800]],
        "label_shape": "rounded", "padding": 0.03,
        "cylinder": {"wrap_degrees": 100, "arc_px": 15, "edge_shade": 0},
        "blend": {"shade": "shade.png", "photo_luminance": False, "strength": 0.85, "opacity": 1.0,
                  "mask": None},
    }
    return manifest, finish(scene, layer, watermark), _small(shade)


def _face(layer: Image.Image, quad, color: Color, light_a: float, light_b: float) -> None:
    """O fata de cutie, cu un degrade usor de la stanga la dreapta."""
    grad = _columns(256, 64, [_tint(color, light_a + (light_b - light_a) * i / 255) for i in range(256)])
    grad = grad.resize((1024, 64), Image.Resampling.BICUBIC)
    mask = _mask(lambda d: d.polygon(_pts(quad), fill=255))
    layer.paste(_into_quad(grad, quad), (0, 0), mask)


def box(watermark: bool):
    scene = studio()
    ground = Image.new("L", scene.size, 0)
    ImageDraw.Draw(ground).polygon([(425, 858), (960, 968), (1262, 872), (1330, 840), (900, 800)], fill=120)
    scene.paste(Image.new("RGB", scene.size, (40, 36, 32)), (0, 0), ground.filter(ImageFilter.GaussianBlur(16)))
    layer = _new_layer()
    card = (236, 228, 214)
    left = [(430, 432), (960, 500), (960, 962), (430, 862)]
    right = [(960, 500), (1250, 446), (1250, 868), (960, 962)]
    top = [(720, 388), (1250, 446), (960, 500), (430, 432)]
    _face(layer, top, card, 1.04, 1.10)
    _face(layer, left, card, 0.90, 0.97)
    _face(layer, right, card, 0.74, 0.66)
    overlay = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for a, b in ((left[0], left[1]), (left[1], left[2]), (right[0], right[1])):
        draw.line(_pts([a, b]), fill=(90, 80, 66, 90), width=S * 2)
    # banda adeziva pe capac
    tape = [(575, 410), (1105, 473), (1085, 477), (555, 414)]
    draw.polygon(_pts(tape), fill=(196, 176, 140, 150))
    layer.alpha_composite(overlay)

    to_face = perspective_coeffs([(0, 0), (1, 0), (1, 1), (0, 1)], left)
    zone = [apply_coeffs(to_face, p) for p in ((0.17, 0.2), (0.85, 0.2), (0.85, 0.82), (0.17, 0.82))]
    manifest = {
        "id": "cutie", "title": "Cutie de carton (provizoriu)", "placeholder": True, "default": True,
        "photo": "photo.jpg",
        "keywords": ["cutie", "cutii", "colet", "colete", "ambalaj", "ambalaje", "carton", "pachet",
                     "pachete", "livrare", "cadou", "cadouri", "pizza", "prăjituri", "cofetărie"],
        "quad": [[round(x), round(y)] for x, y in zone],
        "label_shape": "rounded", "padding": 0.04,
        "cylinder": None,
        "blend": {"shade": None, "photo_luminance": True, "strength": 0.9, "opacity": 1.0, "mask": None},
    }
    return manifest, finish(scene, layer, watermark), None


def _bottle_outline() -> list[tuple[float, float]]:
    """Conturul sticlei: corp, umeri curbi, gat."""
    right = [(940, 990), (940, 580)]
    for i in range(1, 25):
        k = i / 24
        ease = (1 - math.cos(k * math.pi)) / 2
        right.append((940 - 100 * ease, 580 - 150 * k))
    right += [(840, 262)]
    left = [(1600 - x, y) for x, y in reversed(right)]
    return right + left


def bottle(watermark: bool):
    scene = studio()
    shadow(scene, 800, 1012, 150, 16)
    layer = _new_layer()
    outline = _bottle_outline()
    glass = (74, 38, 14)
    silhouette = _mask(lambda d: (d.polygon(_pts(outline), fill=255),
                                  d.rounded_rectangle(_box(660, 900, 940, 1015), radius=_px(34), fill=255)))
    wide = _mask(lambda d: d.rectangle(_box(600, 505, 1000, 1020), fill=255))
    _paste(layer, lit(_px(280), _px(600), glass, 0.55), (660, 420), ImageChops.multiply(silhouette, wide))
    # umerii si gatul primesc lumina pe latimea lor
    for y0, y1 in ((262, 440), (440, 470), (470, 490), (490, 506)):
        xs = [x for x, y in outline if y0 - 8 <= y <= y1 + 8 and x > 800]
        half = max(xs) - 800 if xs else 40
        band = _mask(lambda d: d.rectangle(_box(600, y0, 1000, y1), fill=255))
        _paste(layer, lit(_px(2 * half), _px(y1 - y0), glass, 0.55), (800 - half, y0),
               ImageChops.multiply(silhouette, band))
    ring = _mask(lambda d: d.rounded_rectangle(_box(752, 282, 848, 300), radius=_px(8), fill=255))
    _paste(layer, lit(_px(96), _px(18), glass, 0.6), (752, 282), ring)
    cap = _mask(lambda d: d.rounded_rectangle(_box(754, 214, 846, 270), radius=_px(8), fill=255))
    _paste(layer, lit(_px(92), _px(56), (184, 148, 62), 0.6), (754, 214), cap)
    _ridges(layer, 754, 846, 234, 268, 22, 60)

    shade = _shade_base()
    _paste(shade, shade_strip(_px(280), _px(600), 0.16), (660, 420), ImageChops.multiply(silhouette, wide))
    manifest = {
        "id": "sticla", "title": "Sticlă (provizoriu)", "placeholder": True, "default": False,
        "photo": "photo.jpg",
        "keywords": ["sticlă", "sticle", "sticluță", "vin", "bere", "suc", "sirop", "ulei", "țuică",
                     "pălincă", "lichior", "oțet", "băutură", "flacon"],
        "quad": [[682, 630], [918, 630], [918, 900], [682, 900]],
        "label_shape": "rectangle", "padding": 0.03,
        "cylinder": {"wrap_degrees": 114, "arc_px": 9, "edge_shade": 0},
        "blend": {"shade": "shade.png", "photo_luminance": False, "strength": 0.85, "opacity": 1.0,
                  "mask": None},
    }
    return manifest, finish(scene, layer, watermark), _small(shade)


def _mottle(seed: int, size: tuple[int, int], cells: tuple[int, int], blur: float) -> Image.Image:
    """Textura de hartie: zgomot cu samanta fixa, marit si estompat."""
    rng = random.Random(seed)
    small = Image.new("L", cells)
    small.putdata([rng.randrange(256) for _ in range(cells[0] * cells[1])])
    return small.resize(size, Image.Resampling.BICUBIC).filter(ImageFilter.GaussianBlur(blur))


def bag(watermark: bool):
    scene = studio()
    shadow(scene, 800, 1000, 300, 20)
    layer = _new_layer()
    outline = [(548, 232), (1052, 232), (1066, 300), (1088, 960), (1074, 1000), (526, 1000), (512, 960),
               (534, 300)]
    body = _mask(lambda d: d.polygon(_pts(outline), fill=255))
    kraft = (198, 158, 112)
    width, height = _px(580), _px(770)
    cols = []
    for i in range(width):
        t = (i + 0.5) / width
        m = 0.80 + 0.24 * math.sin(t * math.pi) ** 0.7 + 0.05 * math.cos((t - 0.3) * math.pi)
        cols.append(_tint(kraft, m))
    paper = _columns(width, height, cols)
    grain = _mottle(7, (width, height), (290, 385), 1.2).point([226 + round(v * 29 / 255) for v in range(256)])
    folds = _mottle(11, (width, height), (9, 12), 30).point([222 + round(v * 33 / 255) for v in range(256)])
    paper = ImageChops.multiply(paper, Image.merge("RGB", (grain,) * 3))
    paper = ImageChops.multiply(paper, Image.merge("RGB", (folds,) * 3))
    _paste(layer, paper, (510, 232), body)
    overlay = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.polygon(_pts([(548, 232), (1052, 232), (1064, 292), (536, 292)]), fill=(255, 255, 255, 26))
    draw.line(_pts([(536, 294), (1064, 294)]), fill=(70, 48, 26, 120), width=S * 2)
    draw.line(_pts([(537, 302), (1063, 302)]), fill=(255, 240, 215, 70), width=S * 2)
    # burduful de jos
    draw.arc(_box(512, 880, 1088, 1040), 200, 340, fill=(70, 48, 26, 70), width=S * 3)
    draw.polygon(_pts([(512, 960), (1088, 960), (1074, 1000), (526, 1000)]), fill=(40, 26, 12, 34))
    layer.alpha_composite(Image.composite(overlay, Image.new("RGBA", layer.size, (0, 0, 0, 0)), body))

    manifest = {
        "id": "punga-kraft", "title": "Pungă kraft (provizoriu)", "placeholder": True, "default": False,
        "photo": "photo.jpg",
        "keywords": ["pungă kraft", "pungă", "pungi", "punguță", "kraft", "doypack", "sac", "saci",
                     "plic", "boabe", "condimente", "făină", "granola", "fructe uscate"],
        "quad": [[630, 440], [970, 440], [970, 800], [630, 800]],
        "label_shape": "rounded", "padding": 0.04,
        "cylinder": None,
        "blend": {"shade": None, "photo_luminance": True, "strength": 0.9, "opacity": 0.98, "mask": None},
    }
    return manifest, finish(scene, layer, watermark), None


BUILDERS = (jar, cup, box, bottle, bag)


def generate(out_root: str | Path | None = None, watermark: bool = True) -> list[Path]:
    """Scrie cele 5 sabloane provizorii si intoarce folderele lor."""
    root = Path(out_root) if out_root is not None else default_templates_dir()
    written = []
    for build in BUILDERS:
        manifest, photo, shade = build(watermark)
        folder = root / manifest["id"]
        folder.mkdir(parents=True, exist_ok=True)
        photo.save(folder / "photo.jpg", "JPEG", quality=92, optimize=True)
        if shade is not None:
            shade.save(folder / "shade.png", "PNG", optimize=True)
        (folder / "template.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(folder)
    return written


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    watermark = "--fara-text" not in args
    paths = [a for a in args if not a.startswith("--")]
    for folder in generate(paths[0] if paths else None, watermark):
        print(folder)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

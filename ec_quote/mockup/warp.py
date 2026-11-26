"""Geometrie: coeficienti de perspectiva in Python pur si deformarea de cilindru."""
from __future__ import annotations

import math
from typing import Sequence

from PIL import Image, ImageChops

Point = tuple[float, float]
SUPERSAMPLE = 2
_PAD = 2  # margine transparenta, pentru muchii netede dupa interpolare


def _solve(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    """Eliminare Gauss cu pivot partial."""
    n = len(rhs)
    m = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-12:
            raise ValueError("puncte degenerate, perspectiva nu se poate calcula")
        m[col], m[pivot] = m[pivot], m[col]
        for row in range(n):
            if row == col:
                continue
            factor = m[row][col] / m[col][col]
            if factor:
                for k in range(col, n + 1):
                    m[row][k] -= factor * m[col][k]
    return [m[i][n] / m[i][i] for i in range(n)]


def perspective_coeffs(dst: Sequence[Point], src: Sequence[Point]) -> tuple[float, ...]:
    """Coeficientii Pillow PERSPECTIVE care duc fiecare punct din iesire (dst) in sursa (src)."""
    if len(dst) != 4 or len(src) != 4:
        raise ValueError("sunt necesare exact 4 puncte")
    rows, rhs = [], []
    for (x, y), (u, v) in zip(dst, src):
        rows.append([x, y, 1.0, 0.0, 0.0, 0.0, -u * x, -u * y])
        rhs.append(u)
        rows.append([0.0, 0.0, 0.0, x, y, 1.0, -v * x, -v * y])
        rhs.append(v)
    return tuple(_solve(rows, rhs))


def apply_coeffs(coeffs: Sequence[float], point: Point) -> Point:
    a, b, c, d, e, f, g, h = coeffs
    x, y = point
    w = g * x + h * y + 1.0
    return ((a * x + b * y + c) / w, (d * x + e * y + f) / w)


def _dist(p: Point, q: Point) -> float:
    return math.hypot(p[0] - q[0], p[1] - q[1])


def quad_size(quad: Sequence[Point]) -> tuple[float, float]:
    """Latimea si inaltimea aproximative ale zonei (TL, TR, BR, BL)."""
    tl, tr, br, bl = quad
    return max(_dist(tl, tr), _dist(bl, br)), max(_dist(tl, bl), _dist(tr, br))


def unrolled_width(width: float, wrap_degrees: float | None) -> float:
    """Latimea reala a etichetei desfasurate, pentru o proiectie de latime `width`."""
    if not wrap_degrees:
        return width
    theta = math.radians(wrap_degrees) / 2
    return width * theta / math.sin(theta)


def extend_quad(quad: Sequence[Point], arc_px: float) -> list[Point]:
    """Lungeste laturile zonei cu arcul: in jos pentru arc pozitiv, in sus pentru negativ."""
    tl, tr, br, bl = quad
    if not arc_px:
        return [tl, tr, br, bl]
    left, right = _dist(tl, bl), _dist(tr, br)
    kl, kr = abs(arc_px) / left, abs(arc_px) / right
    if arc_px > 0:
        bl = (bl[0] + (bl[0] - tl[0]) * kl, bl[1] + (bl[1] - tl[1]) * kl)
        br = (br[0] + (br[0] - tr[0]) * kr, br[1] + (br[1] - tr[1]) * kr)
    else:
        tl = (tl[0] + (tl[0] - bl[0]) * kl, tl[1] + (tl[1] - bl[1]) * kl)
        tr = (tr[0] + (tr[0] - br[0]) * kr, tr[1] + (tr[1] - br[1]) * kr)
    return [tl, tr, br, bl]


def cylinder_wrap(label: Image.Image, width: int, wrap_degrees: float, arc: float,
                  edge_shade: float = 0.0, strips: int = 64) -> Image.Image:
    """Proiecteaza eticheta desfasurata (RGBA) pe un cilindru vazut din fata.

    Comprimare orizontala spre margini, arc vertical (mijlocul coboara cu `arc` pixeli,
    urca pentru valori negative) si, optional, intunecare spre margini. Transformare MESH.
    """
    label = label.convert("RGBA")
    src_w, src_h = label.size
    theta = math.radians(wrap_degrees) / 2
    sin_t, cos_t = math.sin(theta), math.cos(theta)
    out_h = src_h + int(math.ceil(abs(arc)))
    base = max(0.0, -arc)

    def angle(x: float) -> float:
        return math.asin(max(-1.0, min(1.0, (2.0 * x / width - 1.0) * sin_t)))

    def lift(a: float) -> float:
        return (math.cos(a) - cos_t) / (1.0 - cos_t)  # 1 la mijloc, 0 la margini

    if edge_shade > 0:
        ramp = Image.new("L", (src_w, 1))
        ramp.putdata([
            round(255 * (1.0 - edge_shade * (1.0 - lift(theta * (2.0 * (i + 0.5) / src_w - 1.0)))))
            for i in range(src_w)
        ])
        ramp = ramp.resize((src_w, src_h), Image.Resampling.NEAREST)
        r, g, b, alpha = label.split()
        label = Image.merge("RGBA", (*(ImageChops.multiply(ch, ramp) for ch in (r, g, b)), alpha))

    mesh = []
    for i in range(strips):
        x0 = round(width * i / strips)
        x1 = round(width * (i + 1) / strips)
        if x1 <= x0:
            continue
        a0, a1 = angle(x0), angle(x1)
        u0 = (a0 / theta + 1.0) / 2.0 * src_w
        u1 = (a1 / theta + 1.0) / 2.0 * src_w
        t0 = base + arc * lift(a0)
        t1 = base + arc * lift(a1)
        mesh.append((
            (x0, 0, x1, out_h),
            (u0, -t0, u0, out_h - t0, u1, out_h - t1, u1, -t1),
        ))
    return label.transform((width, out_h), Image.Transform.MESH, mesh, Image.Resampling.BICUBIC)


def warp_to_quad(label: Image.Image, quad: Sequence[Point], canvas_size: tuple[int, int]) -> Image.Image:
    """Aseaza eticheta (RGBA) in zona `quad` pe un strat transparent de marimea `canvas_size`."""
    label = label.convert("RGBA")
    padded = Image.new("RGBA", (label.width + 2 * _PAD, label.height + 2 * _PAD), (0, 0, 0, 0))
    padded.paste(label, (_PAD, _PAD))
    w, h = label.size
    src = [(_PAD, _PAD), (_PAD + w, _PAD), (_PAD + w, _PAD + h), (_PAD, _PAD + h)]

    xs, ys = [p[0] for p in quad], [p[1] for p in quad]
    left = max(0, int(math.floor(min(xs))) - 2)
    top = max(0, int(math.floor(min(ys))) - 2)
    right = min(canvas_size[0], int(math.ceil(max(xs))) + 2)
    bottom = min(canvas_size[1], int(math.ceil(max(ys))) + 2)
    layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    if right <= left or bottom <= top:
        return layer
    local = [(x - left, y - top) for x, y in quad]
    coeffs = perspective_coeffs(local, src)
    patch = padded.transform((right - left, bottom - top), Image.Transform.PERSPECTIVE,
                             coeffs, Image.Resampling.BICUBIC)
    layer.paste(patch, (left, top))
    return layer

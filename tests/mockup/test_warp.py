import math

import pytest
from PIL import Image

from ec_quote.mockup.warp import (
    apply_coeffs, cylinder_wrap, extend_quad, perspective_coeffs, quad_size, unrolled_width, warp_to_quad,
)

RECT = [(0, 0), (100, 0), (100, 50), (0, 50)]
QUAD = [(210, 120), (480, 160), (455, 390), (190, 330)]


def test_perspective_coeffs_map_destination_corners_to_source_corners():
    coeffs = perspective_coeffs(QUAD, RECT)
    assert len(coeffs) == 8
    for dst, src in zip(QUAD, RECT):
        x, y = apply_coeffs(coeffs, dst)
        assert x == pytest.approx(src[0], abs=1e-6)
        assert y == pytest.approx(src[1], abs=1e-6)


def test_identity_and_translation():
    assert perspective_coeffs(RECT, RECT) == pytest.approx((1, 0, 0, 0, 1, 0, 0, 0), abs=1e-9)
    moved = [(x + 7, y - 3) for x, y in RECT]
    assert apply_coeffs(perspective_coeffs(moved, RECT), (57, 22)) == pytest.approx((50, 25))


def test_degenerate_points_are_rejected():
    with pytest.raises(ValueError):
        perspective_coeffs([(0, 0), (1, 1), (2, 2), (3, 3)], RECT)
    with pytest.raises(ValueError):
        perspective_coeffs(RECT[:3], RECT)


def test_quad_size_and_unrolled_width():
    assert quad_size([(0, 0), (30, 0), (40, 50), (0, 40)]) == pytest.approx((40.0, math.hypot(10, 50)))
    assert unrolled_width(100, None) == 100
    assert unrolled_width(100, 180 - 1e-9) == pytest.approx(100 * math.pi / 2, rel=1e-6)
    assert 100 < unrolled_width(100, 90) < 120


def test_extend_quad():
    square = [(0, 0), (10, 0), (10, 20), (0, 20)]
    assert extend_quad(square, 0) == square
    assert extend_quad(square, 5) == [(0, 0), (10, 0), (10, 25), (0, 25)]
    assert extend_quad(square, -5) == [(0, -5), (10, -5), (10, 20), (0, 20)]


def _inside(point, quad):
    sign = 0
    for i in range(4):
        (x0, y0), (x1, y1) = quad[i], quad[(i + 1) % 4]
        cross = (x1 - x0) * (point[1] - y0) - (y1 - y0) * (point[0] - x0)
        if cross:
            if sign and (cross > 0) != (sign > 0):
                return False
            sign = cross
    return True


def test_warp_to_quad_fills_the_quad_and_nothing_else():
    label = Image.new("RGBA", (200, 100), (255, 0, 0, 255))
    layer = warp_to_quad(label, QUAD, (640, 480))
    assert layer.size == (640, 480)
    alpha = layer.getchannel("A").load()
    cx = sum(p[0] for p in QUAD) / 4
    cy = sum(p[1] for p in QUAD) / 4
    grow = [(cx + (x - cx) * 1.04, cy + (y - cy) * 1.04) for x, y in QUAD]
    shrink = [(cx + (x - cx) * 0.96, cy + (y - cy) * 0.96) for x, y in QUAD]
    for y in range(0, 480, 4):
        for x in range(0, 640, 4):
            if _inside((x, y), shrink):
                assert alpha[x, y] == 255, (x, y)
            elif not _inside((x, y), grow):
                assert alpha[x, y] == 0, (x, y)
    assert layer.getpixel((int(cx), int(cy)))[:3] == (255, 0, 0)


def test_warp_outside_canvas_gives_empty_layer():
    label = Image.new("RGBA", (20, 20), (255, 0, 0, 255))
    layer = warp_to_quad(label, [(-90, -90), (-50, -90), (-50, -50), (-90, -50)], (100, 100))
    assert layer.getbbox() is None


def _column_span(image, x):
    alpha = image.getchannel("A")
    ys = [y for y in range(image.height) if alpha.getpixel((x, y)) > 128]
    return (ys[0], ys[-1]) if ys else None


def test_cylinder_wrap_bows_the_middle_down():
    label = Image.new("RGBA", (300, 100), (0, 0, 255, 255))
    out = cylinder_wrap(label, 240, 120, 20)
    assert out.size == (240, 120)
    top_mid, bottom_mid = _column_span(out, 120)
    top_edge, bottom_edge = _column_span(out, 2)
    assert top_mid == pytest.approx(20, abs=2) and bottom_mid == pytest.approx(119, abs=2)
    assert top_edge <= 2 and bottom_edge == pytest.approx(100, abs=3)


def test_cylinder_wrap_negative_arc_bows_up():
    label = Image.new("RGBA", (300, 100), (0, 0, 255, 255))
    out = cylinder_wrap(label, 240, 120, -20)
    assert _column_span(out, 120)[0] <= 1
    assert _column_span(out, 2)[0] == pytest.approx(19, abs=3)


def test_cylinder_wrap_compresses_toward_the_edges():
    # dungi verticale egale pe eticheta desfasurata: la margine apar mai inguste decat la mijloc
    label = Image.new("RGBA", (400, 40), (255, 255, 255, 255))
    for i in range(0, 400, 40):
        label.paste((0, 0, 0, 255), (i, 0, i + 20, 40))
    out = cylinder_wrap(label, 300, 150, 0).convert("L")
    row = [out.getpixel((x, 20)) < 128 for x in range(300)]
    runs, start = [], None
    for x, dark in enumerate(row + [False]):
        if dark and start is None:
            start = x
        elif not dark and start is not None:
            runs.append(x - start)
            start = None
    assert len(runs) == 10
    assert runs[0] < runs[len(runs) // 2] * 0.6
    assert runs[-1] < runs[len(runs) // 2]


def test_cylinder_edge_shade_darkens_the_sides():
    label = Image.new("RGBA", (300, 60), (200, 200, 200, 255))
    out = cylinder_wrap(label, 240, 120, 0, edge_shade=0.5)
    middle = out.getpixel((120, 30))[0]
    side = out.getpixel((4, 30))[0]
    assert middle >= 195 and side < 130

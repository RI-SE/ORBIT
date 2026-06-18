"""Lane width must be correct under anisotropic pixel scales (scale_x != scale_y).

Width is a real-world perpendicular distance, so converting metres->pixels must use
the across-road axis, per-point. build_lane_polygon_metric builds the polygon in
metric space, which is exact for any direction (straight, diagonal, roundabout).
"""

import pytest

from orbit.utils.geometry import (
    build_lane_polygon_metric,
    calculate_directional_scale,
    create_lane_polygon,
)

SX, SY = 0.05, 0.10  # anisotropic m/px


def _constant_lane(centerline, sx, sy, width_m=3.5):
    return build_lane_polygon_metric(
        centerline, sx, sy,
        lambda c: create_lane_polygon(c, 0.0, width_m, closed=False))


def test_horizontal_road_width_uses_scale_y():
    """A horizontal road's width runs in Y, so it must convert with scale_y."""
    poly = _constant_lane([(0, 0), (100, 0)], SX, SY)
    half_width_px = max(abs(y) for _, y in poly)
    assert half_width_px == pytest.approx(3.5 / SY)  # 35 px, not 3.5/SX = 70


def test_vertical_road_width_uses_scale_x():
    """A vertical road's width runs in X, so it must convert with scale_x."""
    poly = _constant_lane([(0, 0), (0, 100)], SX, SY)
    half_width_px = max(abs(x) for x, _ in poly)
    assert half_width_px == pytest.approx(3.5 / SX)  # 70 px


def test_direction_aware_for_bent_road():
    """An L-shaped road gets the correct width on each leg from a single build."""
    poly = _constant_lane([(0, 0), (100, 0), (100, 100)], SX, SY)
    # Horizontal leg edge (low-y region): perpendicular offset is in Y ~ 3.5/SY.
    h_leg = [(x, y) for x, y in poly if y < 50]
    assert max(abs(y) for _, y in h_leg) == pytest.approx(3.5 / SY, abs=2.0)  # ~35
    # Vertical leg edge (high-y region): perpendicular offset is in X ~ 3.5/SX.
    v_leg = [(x, y) for x, y in poly if y > 50]
    assert max(abs(x - 100) for x, _ in v_leg) == pytest.approx(3.5 / SX, abs=2.0)  # ~70


def test_isotropic_matches_plain_pixel_build():
    """With scale_x == scale_y the metric build equals the plain pixel build."""
    s = 0.08
    metric = _constant_lane([(0, 0), (100, 0)], s, s)
    plain = create_lane_polygon([(0, 0), (100, 0)], 0.0, 3.5 / s, closed=False)
    assert len(metric) == len(plain)
    for (mx, my), (px, py) in zip(metric, plain):
        assert mx == pytest.approx(px)
        assert my == pytest.approx(py)


def test_perpendicular_directional_scale():
    """perpendicular=True swaps axes for width (horizontal -> scale_y)."""
    horiz = [(0, 0), (100, 0)]
    vert = [(0, 0), (0, 100)]
    assert calculate_directional_scale(horiz, SX, SY, perpendicular=True) == pytest.approx(SY)
    assert calculate_directional_scale(vert, SX, SY, perpendicular=True) == pytest.approx(SX)
    # Default (length) keeps the parallel axis.
    assert calculate_directional_scale(horiz, SX, SY) == pytest.approx(SX)


def test_no_scale_falls_back_to_pixel_offsets():
    """Zero/None scale leaves the builder operating directly in pixels."""
    cl = [(0, 0), (100, 0)]
    poly = build_lane_polygon_metric(
        cl, 0.0, 0.0, lambda c: create_lane_polygon(c, 0.0, 10.0, closed=False))
    assert max(abs(y) for _, y in poly) == pytest.approx(10.0)

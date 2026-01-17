"""
Unit tests for lane width polynomial fitting utilities.

Tests polynomial fitting for lane boundaries.
"""

import pytest
import math
from typing import List, Tuple

from orbit.utils.lane_fitting import (
    fit_lane_width_polynomial,
    fit_single_lane_width,
    evaluate_fit_quality,
    _get_perpendicular_at_point,
    _ray_to_polyline_distance,
    _point_to_polyline_perpendicular_distance,
)


# ============================================================================
# Test Fixtures - Geometric Test Data
# ============================================================================

@pytest.fixture
def straight_road_geometry():
    """Create geometry for a straight horizontal road with parallel boundaries."""
    # Centerline: horizontal line from (0,0) to (100,0)
    centerline = [(float(i * 10), 0.0) for i in range(11)]  # 11 points

    # Left boundary: 3.5 units above centerline
    left_boundary = [(float(i * 10), -3.5) for i in range(11)]

    # Right boundary: 3.5 units below centerline
    right_boundary = [(float(i * 10), 3.5) for i in range(11)]

    return centerline, left_boundary, right_boundary


@pytest.fixture
def tapered_road_geometry():
    """Create geometry for a road that widens from 3m to 5m."""
    # Centerline: horizontal line
    centerline = [(float(i * 10), 0.0) for i in range(11)]

    # Left boundary: starts at -1.5, ends at -2.5 (widening left)
    left_boundary = []
    for i in range(11):
        x = float(i * 10)
        offset = 1.5 + (i / 10.0)  # 1.5 to 2.5
        left_boundary.append((x, -offset))

    # Right boundary: starts at 1.5, ends at 2.5 (widening right)
    right_boundary = []
    for i in range(11):
        x = float(i * 10)
        offset = 1.5 + (i / 10.0)  # 1.5 to 2.5
        right_boundary.append((x, offset))

    return centerline, left_boundary, right_boundary


@pytest.fixture
def vertical_road_geometry():
    """Create geometry for a vertical road."""
    # Centerline: vertical line from (0,0) to (0,100)
    centerline = [(0.0, float(i * 10)) for i in range(11)]

    # Left boundary: 3.5 units to the left
    left_boundary = [(-3.5, float(i * 10)) for i in range(11)]

    # Right boundary: 3.5 units to the right
    right_boundary = [(3.5, float(i * 10)) for i in range(11)]

    return centerline, left_boundary, right_boundary


# ============================================================================
# Test _get_perpendicular_at_point
# ============================================================================

class TestGetPerpendicularAtPoint:
    """Test perpendicular vector calculation."""

    def test_horizontal_line_start(self):
        """Test perpendicular at start of horizontal line."""
        points = [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)]
        perp = _get_perpendicular_at_point(points, 0)
        assert perp is not None
        # For horizontal right-pointing line, perpendicular = (-ty, tx) = (0, 1)
        # In screen coords (Y-down), this points DOWN = RIGHT of travel direction
        assert perp[0] == pytest.approx(0.0, abs=1e-9)
        assert perp[1] == pytest.approx(1.0, abs=1e-9)

    def test_horizontal_line_middle(self):
        """Test perpendicular at middle of horizontal line."""
        points = [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)]
        perp = _get_perpendicular_at_point(points, 1)
        assert perp is not None
        assert perp[0] == pytest.approx(0.0, abs=1e-9)
        assert perp[1] == pytest.approx(1.0, abs=1e-9)

    def test_horizontal_line_end(self):
        """Test perpendicular at end of horizontal line."""
        points = [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)]
        perp = _get_perpendicular_at_point(points, 2)
        assert perp is not None
        assert perp[0] == pytest.approx(0.0, abs=1e-9)
        assert perp[1] == pytest.approx(1.0, abs=1e-9)

    def test_vertical_line(self):
        """Test perpendicular for vertical line (downward in screen coords)."""
        points = [(0.0, 0.0), (0.0, 10.0), (0.0, 20.0)]
        perp = _get_perpendicular_at_point(points, 1)
        assert perp is not None
        # For downward-pointing line (ty=1), perpendicular = (-1, 0) = LEFT
        assert perp[0] == pytest.approx(-1.0, abs=1e-9)
        assert perp[1] == pytest.approx(0.0, abs=1e-9)

    def test_diagonal_line(self):
        """Test perpendicular for 45-degree line."""
        points = [(0.0, 0.0), (10.0, 10.0), (20.0, 20.0)]
        perp = _get_perpendicular_at_point(points, 1)
        assert perp is not None
        # Should be normalized
        length = math.sqrt(perp[0]**2 + perp[1]**2)
        assert length == pytest.approx(1.0, abs=1e-9)

    def test_single_point(self):
        """Test with single point returns None."""
        perp = _get_perpendicular_at_point([(0.0, 0.0)], 0)
        assert perp is None

    def test_empty_list(self):
        """Test with empty list returns None."""
        perp = _get_perpendicular_at_point([], 0)
        assert perp is None

    def test_degenerate_segment(self):
        """Test with zero-length segment returns None."""
        points = [(5.0, 5.0), (5.0, 5.0)]  # Same point
        perp = _get_perpendicular_at_point(points, 0)
        assert perp is None


# ============================================================================
# Test _ray_to_polyline_distance
# ============================================================================

class TestRayToPolylineDistance:
    """Test ray-polyline intersection distance."""

    def test_perpendicular_hit(self):
        """Test ray perpendicular to horizontal segment."""
        origin = (5.0, 0.0)
        direction = (0.0, 1.0)  # Downward
        polyline = [(0.0, 3.0), (10.0, 3.0)]

        dist = _ray_to_polyline_distance(origin, direction, polyline)
        assert dist is not None
        assert dist == pytest.approx(3.0)

    def test_perpendicular_miss(self):
        """Test ray that doesn't hit segment."""
        origin = (15.0, 0.0)  # Outside segment range
        direction = (0.0, 1.0)
        polyline = [(0.0, 3.0), (10.0, 3.0)]

        dist = _ray_to_polyline_distance(origin, direction, polyline)
        assert dist is None

    def test_ray_opposite_direction(self):
        """Test ray pointing away from polyline."""
        origin = (5.0, 0.0)
        direction = (0.0, -1.0)  # Upward (away from segment below)
        polyline = [(0.0, 3.0), (10.0, 3.0)]

        dist = _ray_to_polyline_distance(origin, direction, polyline)
        assert dist is None

    def test_diagonal_ray(self):
        """Test diagonal ray hitting segment."""
        origin = (0.0, 0.0)
        direction = (1.0 / math.sqrt(2), 1.0 / math.sqrt(2))  # 45° diagonal
        polyline = [(0.0, 10.0), (20.0, 10.0)]

        dist = _ray_to_polyline_distance(origin, direction, polyline)
        assert dist is not None
        # Ray at 45° reaches y=10 at x=10, distance = sqrt(200)
        assert dist == pytest.approx(math.sqrt(200), rel=0.01)

    def test_multi_segment_polyline(self):
        """Test hitting closest segment in multi-segment polyline."""
        origin = (5.0, 0.0)
        direction = (0.0, 1.0)
        polyline = [(0.0, 5.0), (10.0, 5.0), (10.0, 15.0)]

        dist = _ray_to_polyline_distance(origin, direction, polyline)
        assert dist is not None
        assert dist == pytest.approx(5.0)

    def test_parallel_ray(self):
        """Test ray parallel to segment (no hit)."""
        origin = (0.0, 0.0)
        direction = (1.0, 0.0)  # Horizontal, same as segment
        polyline = [(0.0, 5.0), (10.0, 5.0)]

        dist = _ray_to_polyline_distance(origin, direction, polyline)
        assert dist is None


# ============================================================================
# Test evaluate_fit_quality
# ============================================================================

class TestEvaluateFitQuality:
    """Test fit quality evaluation."""

    def test_excellent_fit(self):
        """Test excellent fit (RMSE < 0.05m)."""
        level, msg = evaluate_fit_quality(0.02)
        assert level == "excellent"
        assert "Excellent" in msg
        assert "0.020" in msg

    def test_good_fit(self):
        """Test good fit (0.05 <= RMSE < 0.2m)."""
        level, msg = evaluate_fit_quality(0.1)
        assert level == "good"
        assert "Good" in msg

    def test_acceptable_fit(self):
        """Test acceptable fit (0.2 <= RMSE < 0.5m)."""
        level, msg = evaluate_fit_quality(0.3)
        assert level == "acceptable"
        assert "Acceptable" in msg

    def test_poor_fit(self):
        """Test poor fit (RMSE >= 0.5m)."""
        level, msg = evaluate_fit_quality(0.8)
        assert level == "poor"
        assert "Poor" in msg
        assert "splitting" in msg.lower()

    def test_boundary_excellent_good(self):
        """Test boundary between excellent and good."""
        level1, _ = evaluate_fit_quality(0.049)
        level2, _ = evaluate_fit_quality(0.051)
        assert level1 == "excellent"
        assert level2 == "good"

    def test_boundary_good_acceptable(self):
        """Test boundary between good and acceptable."""
        level1, _ = evaluate_fit_quality(0.199)
        level2, _ = evaluate_fit_quality(0.201)
        assert level1 == "good"
        assert level2 == "acceptable"

    def test_boundary_acceptable_poor(self):
        """Test boundary between acceptable and poor."""
        level1, _ = evaluate_fit_quality(0.499)
        level2, _ = evaluate_fit_quality(0.501)
        assert level1 == "acceptable"
        assert level2 == "poor"

    def test_zero_rmse(self):
        """Test zero RMSE (perfect fit)."""
        level, msg = evaluate_fit_quality(0.0)
        assert level == "excellent"


# ============================================================================
# Test fit_single_lane_width
# ============================================================================

class TestFitSingleLaneWidth:
    """Test single-boundary lane width fitting."""

    def test_constant_width_right_lane(self, straight_road_geometry):
        """Test fitting constant width for right lane."""
        centerline, left_boundary, right_boundary = straight_road_geometry

        # Fit right lane (lane_id=-1) using right boundary
        a, b, c, d, rmse = fit_single_lane_width(
            centerline, right_boundary, lane_id=-1, scale=1.0
        )

        # For constant width of 3.5, expect a ≈ 3.5, b ≈ 0, c ≈ 0, d ≈ 0
        assert a == pytest.approx(3.5, rel=0.1)
        assert abs(b) < 0.1  # Should be near zero
        assert abs(c) < 0.1
        assert abs(d) < 0.1
        assert rmse < 0.1  # Good fit

    def test_constant_width_left_lane(self, straight_road_geometry):
        """Test fitting constant width for left lane."""
        centerline, left_boundary, right_boundary = straight_road_geometry

        # Fit left lane (lane_id=1) using left boundary
        a, b, c, d, rmse = fit_single_lane_width(
            centerline, left_boundary, lane_id=1, scale=1.0
        )

        # For constant width of 3.5
        assert a == pytest.approx(3.5, rel=0.1)
        assert rmse < 0.1

    def test_tapered_lane(self, tapered_road_geometry):
        """Test fitting tapered lane width."""
        centerline, left_boundary, right_boundary = tapered_road_geometry

        a, b, c, d, rmse = fit_single_lane_width(
            centerline, right_boundary, lane_id=-1, scale=1.0
        )

        # Width varies from 1.5 to 2.5, so a should be around starting width
        # and b should be positive (increasing width)
        assert a > 0
        # Allow some variation in fit
        assert rmse < 0.5

    def test_with_scale(self, straight_road_geometry):
        """Test fitting with scale factor."""
        centerline, left_boundary, right_boundary = straight_road_geometry

        # Scale = 0.5 means half the width in output
        a, b, c, d, rmse = fit_single_lane_width(
            centerline, right_boundary, lane_id=-1, scale=0.5
        )

        # Width should be 3.5 * 0.5 = 1.75
        assert a == pytest.approx(1.75, rel=0.1)

    def test_insufficient_centerline_points(self):
        """Test error with single centerline point."""
        with pytest.raises(ValueError, match="at least 2 points"):
            fit_single_lane_width(
                [(0, 0)],  # Only 1 point
                [(0, 3), (10, 3)],
                lane_id=-1
            )

    def test_insufficient_boundary_points(self):
        """Test error with single boundary point."""
        with pytest.raises(ValueError, match="at least 2 points"):
            fit_single_lane_width(
                [(0, 0), (10, 0)],
                [(5, 3)],  # Only 1 point
                lane_id=-1
            )

    def test_zero_length_centerline(self):
        """Test error with zero-length centerline."""
        with pytest.raises(ValueError, match="zero length"):
            fit_single_lane_width(
                [(5, 5), (5, 5)],  # Same point twice
                [(0, 0), (10, 0)],
                lane_id=-1
            )


# ============================================================================
# Test fit_lane_width_polynomial
# ============================================================================

class TestFitLaneWidthPolynomial:
    """Test dual-boundary lane width fitting."""

    def test_insufficient_centerline_points(self):
        """Test error with single centerline point."""
        with pytest.raises(ValueError, match="at least 2 points"):
            fit_lane_width_polynomial(
                [(0, 0)],
                [(0, 3), (10, 3)],
                [(0, -3), (10, -3)],
                lane_id=-1
            )

    def test_insufficient_left_boundary(self):
        """Test error with insufficient left boundary."""
        with pytest.raises(ValueError, match="at least 2 points"):
            fit_lane_width_polynomial(
                [(0, 0), (10, 0)],
                [(5, 3)],  # Only 1 point
                [(0, -3), (10, -3)],
                lane_id=-1
            )

    def test_insufficient_right_boundary(self):
        """Test error with insufficient right boundary."""
        with pytest.raises(ValueError, match="at least 2 points"):
            fit_lane_width_polynomial(
                [(0, 0), (10, 0)],
                [(0, 3), (10, 3)],
                [(5, -3)],  # Only 1 point
                lane_id=-1
            )

    def test_zero_length_centerline(self):
        """Test error with zero-length centerline."""
        with pytest.raises(ValueError, match="zero length"):
            fit_lane_width_polynomial(
                [(5, 5), (5, 5)],  # Same point twice
                [(0, 0), (10, 0)],
                [(0, 10), (10, 10)],
                lane_id=-1
            )


# ============================================================================
# Test _point_to_polyline_perpendicular_distance
# ============================================================================

class TestPointToPolylinePerpendicularDistance:
    """Test perpendicular distance with side checking."""

    def test_right_lane_correct_side(self):
        """Test right lane with boundary on correct side (below in screen coords)."""
        point = (5.0, 0.0)
        # perp = (0, 1) points DOWN = RIGHT for rightward travel in screen coords
        perp = (0.0, 1.0)
        polyline = [(0.0, 3.0), (10.0, 3.0)]  # Below centerline = RIGHT side

        dist = _point_to_polyline_perpendicular_distance(
            point, perp, polyline, lane_id=-1
        )
        assert dist is not None
        assert dist == pytest.approx(3.0)

    def test_left_lane_correct_side(self):
        """Test left lane with boundary on correct side (above in screen coords)."""
        point = (5.0, 0.0)
        # perp = (0, 1) points DOWN = RIGHT for rightward travel
        perp = (0.0, 1.0)
        polyline = [(0.0, -3.0), (10.0, -3.0)]  # Above centerline = LEFT side

        dist = _point_to_polyline_perpendicular_distance(
            point, perp, polyline, lane_id=1
        )
        assert dist is not None
        assert dist == pytest.approx(3.0)

    def test_right_lane_wrong_side(self):
        """Test right lane with boundary on wrong side returns None."""
        point = (5.0, 0.0)
        perp = (0.0, 1.0)
        polyline = [(0.0, -3.0), (10.0, -3.0)]  # Above centerline = LEFT side

        dist = _point_to_polyline_perpendicular_distance(
            point, perp, polyline, lane_id=-1  # Right lane expects RIGHT side
        )
        assert dist is None

    def test_empty_polyline(self):
        """Test with empty polyline."""
        dist = _point_to_polyline_perpendicular_distance(
            (5.0, 0.0), (0.0, 1.0), [], lane_id=-1
        )
        assert dist is None

    def test_single_point_polyline(self):
        """Test with single-point polyline."""
        dist = _point_to_polyline_perpendicular_distance(
            (5.0, 0.0), (0.0, 1.0), [(5.0, 3.0)], lane_id=-1
        )
        # With only one point, no segments to check
        assert dist is None

    def test_degenerate_segment(self):
        """Test with degenerate (zero-length) segment in polyline."""
        point = (5.0, 0.0)
        perp = (0.0, 1.0)
        # Polyline with a zero-length segment
        polyline = [(5.0, 3.0), (5.0, 3.0), (10.0, 3.0)]

        dist = _point_to_polyline_perpendicular_distance(
            point, perp, polyline, lane_id=-1
        )
        assert dist is not None
        assert dist == pytest.approx(3.0)


# ============================================================================
# Test fit_lane_width_polynomial - Success Cases
# ============================================================================

class TestFitLaneWidthPolynomialSuccess:
    """Test successful lane width polynomial fitting with both boundaries.

    Note: fit_lane_width_polynomial uses perpendicular ray casting where the
    perpendicular vector is computed as (-ty, tx) which points LEFT of travel
    in math coords (Y-up). The function expects:
    - For right lane: perp direction hits left_boundary, -perp hits right_boundary
    - This works correctly for vertical roads in screen coords
    """

    def test_vertical_road(self, vertical_road_geometry):
        """Test fitting for vertical road orientation."""
        centerline, left_boundary, right_boundary = vertical_road_geometry

        a, b, c, d, rmse = fit_lane_width_polynomial(
            centerline, left_boundary, right_boundary, lane_id=-1, scale=1.0
        )

        # Should fit correctly - total width is 7.0 (3.5 on each side)
        assert a == pytest.approx(7.0, rel=0.1)
        assert rmse < 0.2

    def test_vertical_road_left_lane(self, vertical_road_geometry):
        """Test fitting for left lane on vertical road."""
        centerline, left_boundary, right_boundary = vertical_road_geometry

        a, b, c, d, rmse = fit_lane_width_polynomial(
            centerline, left_boundary, right_boundary, lane_id=1, scale=1.0
        )

        assert a == pytest.approx(7.0, rel=0.1)
        assert rmse < 0.2

    def test_vertical_road_with_scale(self, vertical_road_geometry):
        """Test fitting with scale factor on vertical road."""
        centerline, left_boundary, right_boundary = vertical_road_geometry

        a, b, c, d, rmse = fit_lane_width_polynomial(
            centerline, left_boundary, right_boundary, lane_id=-1, scale=0.5
        )

        # Width should be 7.0 * 0.5 = 3.5
        assert a == pytest.approx(3.5, rel=0.1)

    def test_vertical_tapered_road(self):
        """Test fitting for tapered vertical road."""
        # Vertical centerline
        centerline = [(0.0, float(i * 10)) for i in range(11)]

        # Left boundary that tapers from -1.5 to -2.5
        left_boundary = []
        for i in range(11):
            y = float(i * 10)
            offset = -(1.5 + (i / 10.0))  # -1.5 to -2.5
            left_boundary.append((offset, y))

        # Right boundary that tapers from 1.5 to 2.5
        right_boundary = []
        for i in range(11):
            y = float(i * 10)
            offset = 1.5 + (i / 10.0)  # 1.5 to 2.5
            right_boundary.append((offset, y))

        a, b, c, d, rmse = fit_lane_width_polynomial(
            centerline, left_boundary, right_boundary, lane_id=-1, scale=1.0
        )

        # Width varies from 3.0 to 5.0, starting around 3.0
        assert a == pytest.approx(3.0, rel=0.2)
        # b should be positive (widening road)
        assert b > 0
        assert rmse < 0.5


# ============================================================================
# Test Polynomial Degree Fallbacks
# ============================================================================

class TestPolynomialDegreeFallbacks:
    """Test polynomial degree fallbacks based on available sample points."""

    def test_quadratic_fit_three_points(self):
        """Test quadratic fit when only 3 sample points available."""
        # Short centerline with just 3 points
        centerline = [(0.0, 0.0), (50.0, 0.0), (100.0, 0.0)]
        # Boundary at constant distance
        boundary = [(0.0, 3.5), (50.0, 3.5), (100.0, 3.5)]

        a, b, c, d, rmse = fit_single_lane_width(
            centerline, boundary, lane_id=-1, scale=1.0
        )

        # Should still produce valid coefficients
        assert a == pytest.approx(3.5, rel=0.1)
        # d should be 0 for quadratic fit
        assert d == pytest.approx(0.0, abs=0.01)

    def test_linear_fit_two_points(self):
        """Test linear fit when only 2 sample points available."""
        # Minimal centerline with 2 points
        centerline = [(0.0, 0.0), (100.0, 0.0)]
        # Boundary at constant distance
        boundary = [(0.0, 3.5), (100.0, 3.5)]

        a, b, c, d, rmse = fit_single_lane_width(
            centerline, boundary, lane_id=-1, scale=1.0
        )

        # Should produce valid linear fit
        assert a == pytest.approx(3.5, rel=0.1)
        # c and d should be 0 for linear fit
        assert c == pytest.approx(0.0, abs=0.01)
        assert d == pytest.approx(0.0, abs=0.01)

    def test_linear_fit_varying_width(self):
        """Test linear fit captures width variation with 2 points."""
        centerline = [(0.0, 0.0), (100.0, 0.0)]
        # Boundary that widens from 2 to 4
        boundary = [(0.0, 2.0), (100.0, 4.0)]

        a, b, c, d, rmse = fit_single_lane_width(
            centerline, boundary, lane_id=-1, scale=1.0
        )

        # Should have starting width around 2 and positive slope
        assert a == pytest.approx(2.0, rel=0.2)
        assert b > 0  # Positive slope for widening


# ============================================================================
# Test Edge Cases and Error Handling
# ============================================================================

class TestLaneFittingEdgeCases:
    """Test edge cases and error conditions."""

    def test_boundary_on_wrong_side_insufficient_samples(self):
        """Test error when boundary is on wrong side (insufficient valid samples)."""
        centerline = [(0.0, 0.0), (50.0, 0.0), (100.0, 0.0)]
        # Boundary on LEFT side but we're fitting RIGHT lane
        boundary = [(0.0, -3.5), (50.0, -3.5), (100.0, -3.5)]

        with pytest.raises(ValueError, match="Insufficient sample points"):
            fit_single_lane_width(
                centerline, boundary, lane_id=-1, scale=1.0
            )

    def test_diagonal_road_geometry(self):
        """Test fitting with diagonal road orientation."""
        # 45-degree diagonal road going down-right
        centerline = [
            (0.0, 0.0), (25.0, 25.0), (50.0, 50.0), (75.0, 75.0), (100.0, 100.0)
        ]
        # For diagonal (1,1) direction, perpendicular (-ty, tx) = (-1/√2, 1/√2)
        # This points up-right in screen coords (left of travel direction)
        # For right lane (lane_id=-1), we need boundary on the RIGHT side
        # which is the opposite direction: (1/√2, -1/√2) = down-left
        offset = 3.5 / math.sqrt(2)
        boundary = [
            (0.0 - offset, 0.0 + offset),
            (25.0 - offset, 25.0 + offset),
            (50.0 - offset, 50.0 + offset),
            (75.0 - offset, 75.0 + offset),
            (100.0 - offset, 100.0 + offset),
        ]

        a, b, c, d, rmse = fit_single_lane_width(
            centerline, boundary, lane_id=-1, scale=1.0
        )

        # Should fit approximately 3.5 width
        assert a == pytest.approx(3.5, rel=0.2)
        assert rmse < 0.5

    def test_curved_centerline(self):
        """Test fitting with curved centerline."""
        # Quarter circle arc from (50, 0) to (0, 50) - counter-clockwise
        centerline = []
        for i in range(11):
            angle = (i / 10.0) * (math.pi / 2)  # 0 to 90 degrees
            x = 50.0 * math.cos(angle)
            y = 50.0 * math.sin(angle)
            centerline.append((x, y))

        # For right lane, boundary should be on the INSIDE of the curve
        # (smaller radius = 46.5)
        boundary = []
        for i in range(11):
            angle = (i / 10.0) * (math.pi / 2)
            x = 46.5 * math.cos(angle)
            y = 46.5 * math.sin(angle)
            boundary.append((x, y))

        a, b, c, d, rmse = fit_single_lane_width(
            centerline, boundary, lane_id=-1, scale=1.0
        )

        # Should fit approximately 3.5 width
        assert a == pytest.approx(3.5, rel=0.3)

    def test_many_points_cubic_fit(self):
        """Test full cubic fit with many sample points."""
        # Long centerline with many points
        centerline = [(float(i * 5), 0.0) for i in range(21)]  # 21 points

        # Boundary with slight cubic variation
        boundary = []
        for i in range(21):
            x = float(i * 5)
            # Width varies slightly in a cubic pattern
            s = i / 20.0
            offset = 3.5 + 0.1 * s - 0.2 * s**2 + 0.1 * s**3
            boundary.append((x, offset))

        a, b, c, d, rmse = fit_single_lane_width(
            centerline, boundary, lane_id=-1, scale=1.0
        )

        # Should produce a cubic fit
        assert a > 0
        # RMSE should be small for this smooth curve
        assert rmse < 0.2

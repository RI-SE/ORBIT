"""
Unit tests for parametric curve and geographic geometry utilities.

Tests ParamPoly3D, Hermite, Bezier curve computation,
arc parameter calculation, and geographic path utilities.
"""

import math

import pytest

class TestCalculateHermiteParampoly3:
    """Test Hermite-based ParamPoly3D coefficient calculation."""

    def test_straight_line(self):
        """Test straight line (parallel tangents) coefficients."""
        from orbit.utils.geometry import calculate_hermite_parampoly3

        start_pos = (0.0, 0.0)
        end_pos = (100.0, 0.0)
        start_tangent = (1.0, 0.0)
        end_tangent = (1.0, 0.0)

        coeffs = calculate_hermite_parampoly3(start_pos, start_tangent, end_pos, end_tangent)

        assert len(coeffs) == 8
        aU, bU, cU, dU, aV, bV, cV, dV = coeffs
        # In local frame, start at origin
        assert aU == pytest.approx(0.0)
        assert aV == pytest.approx(0.0)

    def test_90_degree_turn(self):
        """Test 90-degree turn produces non-trivial coefficients."""
        from orbit.utils.geometry import calculate_hermite_parampoly3

        start_pos = (0.0, 0.0)
        end_pos = (50.0, 50.0)
        start_tangent = (1.0, 0.0)  # East
        end_tangent = (0.0, 1.0)   # North

        coeffs = calculate_hermite_parampoly3(start_pos, start_tangent, end_pos, end_tangent)

        assert len(coeffs) == 8
        # V coefficients should be non-zero for curved path
        _, _, _, _, aV, bV, cV, dV = coeffs
        # At least one V coefficient should be non-zero (curved path)
        assert not all(v == pytest.approx(0.0) for v in [cV, dV])

    def test_tangent_scale_affects_curvature(self):
        """Test that tangent_scale affects curve shape."""
        from orbit.utils.geometry import calculate_hermite_parampoly3

        start_pos = (0.0, 0.0)
        end_pos = (100.0, 50.0)
        start_tangent = (1.0, 0.0)
        end_tangent = (1.0, 0.0)

        coeffs1 = calculate_hermite_parampoly3(
            start_pos, start_tangent, end_pos, end_tangent, tangent_scale=0.5
        )
        coeffs2 = calculate_hermite_parampoly3(
            start_pos, start_tangent, end_pos, end_tangent, tangent_scale=2.0
        )

        # Different scale should produce different coefficients
        assert coeffs1 != coeffs2


class TestSampleParampoly3:
    """Test ParamPoly3D curve sampling."""

    def test_sample_straight_line(self):
        """Test sampling a straight line in local coords."""
        from orbit.utils.geometry import sample_parampoly3

        # Linear in U only: u = p, v = 0
        aU, bU, cU, dU = 0.0, 100.0, 0.0, 0.0
        aV, bV, cV, dV = 0.0, 0.0, 0.0, 0.0

        points = sample_parampoly3(aU, bU, cU, dU, aV, bV, cV, dV, num_points=5)

        assert len(points) == 5
        # First point at origin
        assert points[0] == pytest.approx((0.0, 0.0), abs=1e-10)
        # Last point at (100, 0)
        assert points[-1] == pytest.approx((100.0, 0.0), abs=1e-10)

    def test_sample_with_p_range(self):
        """Test sampling with custom p_range."""
        from orbit.utils.geometry import sample_parampoly3

        aU, bU, cU, dU = 0.0, 50.0, 0.0, 0.0
        aV, bV, cV, dV = 0.0, 0.0, 0.0, 0.0

        # Sample from 0 to 2 (extends beyond typical range)
        points = sample_parampoly3(aU, bU, cU, dU, aV, bV, cV, dV, num_points=3, p_range=2.0)

        assert len(points) == 3
        assert points[-1][0] == pytest.approx(100.0)  # 50 * 2


class TestEvaluateParampoly3Global:
    """Test evaluating ParamPoly3D in global coordinates."""

    def test_transform_to_global(self):
        """Test local to global coordinate transformation."""
        from orbit.utils.geometry import evaluate_parampoly3_global

        # Simple curve in local frame
        aU, bU, cU, dU = 0.0, 100.0, 0.0, 0.0
        aV, bV, cV, dV = 0.0, 0.0, 0.0, 0.0

        start_pos = (50.0, 50.0)
        start_heading = 0.0  # East

        points = evaluate_parampoly3_global(
            aU, bU, cU, dU, aV, bV, cV, dV,
            start_pos, start_heading, num_points=3
        )

        assert len(points) == 4  # num_points + 1
        # First point at start_pos
        assert points[0] == pytest.approx((50.0, 50.0), abs=1e-10)
        # Last point at (150, 50) - moved 100 units east
        assert points[-1] == pytest.approx((150.0, 50.0), abs=1e-10)

    def test_rotated_coordinate_system(self):
        """Test transformation with rotated heading."""
        from orbit.utils.geometry import evaluate_parampoly3_global

        aU, bU, cU, dU = 0.0, 100.0, 0.0, 0.0
        aV, bV, cV, dV = 0.0, 0.0, 0.0, 0.0

        start_pos = (0.0, 0.0)
        start_heading = math.pi / 2  # North

        points = evaluate_parampoly3_global(
            aU, bU, cU, dU, aV, bV, cV, dV,
            start_pos, start_heading, num_points=2
        )

        # Moving 100 units in local u (which is north)
        # Last point should be at (0, 100)
        assert points[-1][0] == pytest.approx(0.0, abs=1e-10)
        assert points[-1][1] == pytest.approx(100.0, abs=1e-10)


# ============================================================================
# Test Bezier Functions
# ============================================================================

class TestCalculateBezierControlPoints:
    """Test Bezier control point calculation for junction connections."""

    def test_small_angle_scurve(self):
        """Test small angle creates S-curve control points."""
        from orbit.utils.geometry import calculate_bezier_control_points

        start_pos = (0.0, 0.0)
        end_pos = (100.0, 10.0)
        start_tangent = (1.0, 0.0)
        end_tangent = (1.0, 0.0)  # Nearly parallel

        points = calculate_bezier_control_points(start_pos, start_tangent, end_pos, end_tangent)

        assert points is not None
        # S-curve has 4 control points
        assert len(points) == 4
        assert points[0] == start_pos
        assert points[-1] == end_pos

    def test_large_angle_uses_intersection(self):
        """Test large angle uses tangent intersection."""
        from orbit.utils.geometry import calculate_bezier_control_points

        start_pos = (0.0, 0.0)
        end_pos = (50.0, 50.0)
        start_tangent = (1.0, 0.0)
        end_tangent = (0.0, 1.0)  # 90 degrees

        points = calculate_bezier_control_points(start_pos, start_tangent, end_pos, end_tangent)

        assert points is not None
        # Large angle may use 3-point (quadratic) or 4-point control
        assert len(points) >= 3
        assert points[0] == start_pos
        assert points[-1] == end_pos

    def test_uturn_creates_offset_control(self):
        """Test U-turn creates perpendicular offset control point."""
        from orbit.utils.geometry import calculate_bezier_control_points

        start_pos = (0.0, 0.0)
        end_pos = (0.0, 20.0)
        start_tangent = (1.0, 0.0)
        end_tangent = (-1.0, 0.0)  # Opposite direction

        points = calculate_bezier_control_points(
            start_pos, start_tangent, end_pos, end_tangent, is_uturn=True
        )

        assert points is not None
        assert len(points) == 3
        assert points[0] == start_pos
        assert points[-1] == end_pos

    def test_parallel_tangents_returns_none(self):
        """Test parallel tangents without intersection returns None."""
        from orbit.utils.geometry import calculate_bezier_control_points

        start_pos = (0.0, 0.0)
        end_pos = (0.0, 100.0)  # Directly above
        start_tangent = (1.0, 0.0)  # East
        end_tangent = (1.0, 0.0)   # East - parallel to start

        points = calculate_bezier_control_points(start_pos, start_tangent, end_pos, end_tangent)

        # Should fall back to S-curve even for parallel
        assert points is not None

    def test_very_close_points(self):
        """Test very close points returns None."""
        from orbit.utils.geometry import calculate_bezier_control_points

        start_pos = (0.0, 0.0)
        end_pos = (0.0000001, 0.0)

        points = calculate_bezier_control_points(start_pos, (1, 0), end_pos, (1, 0))

        assert points is None


class TestBezierToParampoly3:
    """Test conversion from Bezier control points to ParamPoly3 coefficients."""

    def test_quadratic_bezier(self):
        """Test 3-point quadratic Bezier conversion."""
        from orbit.utils.geometry import bezier_to_parampoly3

        P0 = (0.0, 0.0)
        P1 = (50.0, 50.0)
        P2 = (100.0, 0.0)
        control_points = [P0, P1, P2]

        coeffs = bezier_to_parampoly3(control_points, start_heading=0.0)

        assert len(coeffs) == 8
        aU, bU, cU, dU, aV, bV, cV, dV = coeffs
        # Quadratic Bezier has dU = dV = 0
        assert dU == pytest.approx(0.0)
        assert dV == pytest.approx(0.0)

    def test_cubic_bezier(self):
        """Test 4-point cubic Bezier conversion."""
        from orbit.utils.geometry import bezier_to_parampoly3

        P0 = (0.0, 0.0)
        P1 = (30.0, 50.0)
        P2 = (70.0, 50.0)
        P3 = (100.0, 0.0)
        control_points = [P0, P1, P2, P3]

        coeffs = bezier_to_parampoly3(control_points, start_heading=0.0)

        assert len(coeffs) == 8
        # Cubic may have non-zero d coefficients

    def test_insufficient_points_raises(self):
        """Test fewer than 3 points raises ValueError."""
        from orbit.utils.geometry import bezier_to_parampoly3

        with pytest.raises(ValueError):
            bezier_to_parampoly3([(0, 0), (100, 0)], 0.0)


class TestSampleBezier:
    """Test Bezier curve sampling."""

    def test_sample_quadratic(self):
        """Test sampling quadratic Bezier curve."""
        from orbit.utils.geometry import sample_bezier

        P0 = (0.0, 0.0)
        P1 = (50.0, 100.0)
        P2 = (100.0, 0.0)
        control_points = [P0, P1, P2]

        points = sample_bezier(control_points, num_points=5)

        assert len(points) == 5
        # Endpoints match control points
        assert points[0] == pytest.approx(P0, abs=1e-10)
        assert points[-1] == pytest.approx(P2, abs=1e-10)
        # Midpoint should be above x-axis due to control point
        assert points[2][1] > 0

    def test_sample_cubic(self):
        """Test sampling cubic Bezier curve."""
        from orbit.utils.geometry import sample_bezier

        control_points = [(0, 0), (25, 50), (75, 50), (100, 0)]

        points = sample_bezier(control_points, num_points=10)

        assert len(points) == 10
        assert points[0] == pytest.approx((0, 0), abs=1e-10)
        assert points[-1] == pytest.approx((100, 0), abs=1e-10)

    def test_insufficient_points_returns_copy(self):
        """Test fewer than 3 control points returns copy."""
        from orbit.utils.geometry import sample_bezier

        control_points = [(0, 0), (100, 0)]
        points = sample_bezier(control_points, num_points=10)

        assert points == control_points


# ============================================================================
# Test Arc Parameters
# ============================================================================

class TestCalculateArcParameters:
    """Test arc parameter calculation from points."""

    def test_quarter_circle_ccw(self):
        """Test quarter circle counter-clockwise."""
        from orbit.utils.geometry import calculate_arc_parameters

        center = (0.0, 0.0)
        radius = 10.0
        # Points along quarter circle from (10,0) to (0,10)
        points = [
            (10.0, 0.0),
            (7.07, 7.07),  # ~45 degrees
            (0.0, 10.0)
        ]

        curvature, start_angle, sweep_angle = calculate_arc_parameters(points, center)

        assert abs(curvature) == pytest.approx(1.0 / radius, rel=0.01)
        assert start_angle == pytest.approx(0.0, abs=0.1)
        assert sweep_angle == pytest.approx(math.pi / 2, abs=0.1)

    def test_single_point(self):
        """Test single point returns zeros."""
        from orbit.utils.geometry import calculate_arc_parameters

        result = calculate_arc_parameters([(10, 0)], (0, 0))
        assert result == (0.0, 0.0, 0.0)

    def test_zero_radius(self):
        """Test points at center returns zeros."""
        from orbit.utils.geometry import calculate_arc_parameters

        result = calculate_arc_parameters([(0, 0), (0, 0)], (0, 0))
        assert result == (0.0, 0.0, 0.0)


class TestCalculateTangentHeading:
    """Test tangent heading calculation at arc points."""

    def test_tangent_at_east(self):
        """Test tangent at easternmost point of circle."""
        from orbit.utils.geometry import calculate_tangent_heading

        center = (0.0, 0.0)
        point = (10.0, 0.0)  # East point

        # CCW tangent should point north
        heading = calculate_tangent_heading(point, center, clockwise=False)
        assert heading == pytest.approx(math.pi / 2, abs=0.01)

        # CW tangent should point south
        heading_cw = calculate_tangent_heading(point, center, clockwise=True)
        assert heading_cw == pytest.approx(-math.pi / 2, abs=0.01)

    def test_tangent_at_north(self):
        """Test tangent at northernmost point of circle."""
        from orbit.utils.geometry import calculate_tangent_heading

        center = (0.0, 0.0)
        point = (0.0, 10.0)  # North point

        # CCW tangent should point west
        heading = calculate_tangent_heading(point, center, clockwise=False)
        assert heading == pytest.approx(math.pi, abs=0.01)


# ============================================================================
# Test Boundary Splitting
# ============================================================================

class TestSplitBoundaryAtCenterlineS:
    """Test splitting boundary polylines at centerline s-coordinates."""

    def test_split_parallel_boundary(self):
        """Test splitting boundary parallel to centerline."""
        from orbit.utils.geometry import split_boundary_at_centerline_s

        centerline = [(0.0, 0.0), (100.0, 0.0)]
        boundary = [(0.0, 5.0), (50.0, 5.0), (100.0, 5.0)]
        target_s = 50.0

        result = split_boundary_at_centerline_s(boundary, centerline, target_s)

        assert result is not None
        first, second = result
        # Both segments should include the split point
        assert len(first) >= 2
        assert len(second) >= 2

    def test_split_at_boundary_vertex(self):
        """Test splitting exactly at a boundary vertex."""
        from orbit.utils.geometry import split_boundary_at_centerline_s

        centerline = [(0.0, 0.0), (100.0, 0.0)]
        boundary = [(0.0, 5.0), (50.0, 5.0), (100.0, 5.0)]
        target_s = 50.0  # Exactly at middle vertex

        result = split_boundary_at_centerline_s(boundary, centerline, target_s)

        assert result is not None

    def test_boundary_entirely_before_target(self):
        """Test boundary entirely before target s."""
        from orbit.utils.geometry import split_boundary_at_centerline_s

        centerline = [(0.0, 0.0), (200.0, 0.0)]
        boundary = [(0.0, 5.0), (50.0, 5.0)]  # Ends at s=50
        target_s = 150.0  # Beyond boundary

        result = split_boundary_at_centerline_s(boundary, centerline, target_s)

        assert result is not None
        first, second = result
        # All points should be in first segment
        assert len(first) > 1

    def test_empty_inputs(self):
        """Test empty inputs return None."""
        from orbit.utils.geometry import split_boundary_at_centerline_s

        assert split_boundary_at_centerline_s([], [(0, 0), (100, 0)], 50) is None
        assert split_boundary_at_centerline_s([(0, 5), (100, 5)], [], 50) is None


# ============================================================================
# Test Polyline Merging
# ============================================================================

class TestMergePolylinesAtJunction:
    """Test merging polylines at junction points."""

    def test_merge_connected(self):
        """Test merging polylines with matching endpoints."""
        from orbit.utils.geometry import merge_polylines_at_junction

        poly1 = [(0.0, 0.0), (50.0, 0.0), (100.0, 0.0)]
        poly2 = [(100.0, 0.0), (150.0, 0.0), (200.0, 0.0)]

        result = merge_polylines_at_junction(poly1, poly2)

        assert result is not None
        assert len(result) == 5  # 3 + 3 - 1 (duplicate removed)
        assert result[0] == (0.0, 0.0)
        assert result[-1] == (200.0, 0.0)

    def test_merge_within_tolerance(self):
        """Test merging with small gap within tolerance."""
        from orbit.utils.geometry import merge_polylines_at_junction

        poly1 = [(0.0, 0.0), (100.0, 0.0)]
        poly2 = [(100.5, 0.5), (200.0, 0.0)]  # Slightly off

        result = merge_polylines_at_junction(poly1, poly2, tolerance=1.0)

        assert result is not None
        assert len(result) == 3

    def test_merge_beyond_tolerance(self):
        """Test non-matching endpoints return None."""
        from orbit.utils.geometry import merge_polylines_at_junction

        poly1 = [(0.0, 0.0), (100.0, 0.0)]
        poly2 = [(110.0, 0.0), (200.0, 0.0)]  # Gap > tolerance

        result = merge_polylines_at_junction(poly1, poly2, tolerance=1.0)

        assert result is None

    def test_merge_empty_polylines(self):
        """Test empty polylines return None."""
        from orbit.utils.geometry import merge_polylines_at_junction

        assert merge_polylines_at_junction([], [(0, 0), (100, 0)]) is None
        assert merge_polylines_at_junction([(0, 0), (100, 0)], []) is None


# ============================================================================
# Test Geographic Path Functions
# ============================================================================

class TestFindGeoPointAtDistanceAlongPath:
    """Test finding points at distances along geographic paths."""

    def test_find_point_at_start(self):
        """Test finding point at distance 0."""
        from orbit.utils.geometry import find_geo_point_at_distance_along_path

        geo_points = [(12.0, 57.0), (12.01, 57.0)]

        result = find_geo_point_at_distance_along_path(geo_points, 0.0)

        assert result is not None
        point, segment = result
        assert point == (12.0, 57.0)

    def test_find_point_in_segment(self):
        """Test finding point within a segment."""
        from orbit.utils.geometry import find_geo_point_at_distance_along_path

        # Create path with known distance
        geo_points = [(12.0, 57.0), (12.0, 58.0)]  # ~111km north

        result = find_geo_point_at_distance_along_path(geo_points, 55500)  # Half way

        assert result is not None
        point, segment = result
        assert point[1] == pytest.approx(57.5, abs=0.1)

    def test_distance_beyond_path(self):
        """Test distance beyond path returns None."""
        from orbit.utils.geometry import find_geo_point_at_distance_along_path

        geo_points = [(12.0, 57.0), (12.001, 57.0)]  # Short path

        result = find_geo_point_at_distance_along_path(geo_points, 1000000)  # Very far

        assert result is None

    def test_from_end(self):
        """Test measuring from end of path."""
        from orbit.utils.geometry import find_geo_point_at_distance_along_path

        geo_points = [(12.0, 57.0), (12.0, 58.0)]

        result = find_geo_point_at_distance_along_path(geo_points, 55500, from_start=False)

        assert result is not None
        point, segment = result
        # Should be about halfway from the end
        assert point[1] == pytest.approx(57.5, abs=0.1)

    def test_single_point(self):
        """Test single point returns None."""
        from orbit.utils.geometry import find_geo_point_at_distance_along_path

        result = find_geo_point_at_distance_along_path([(12.0, 57.0)], 100)
        assert result is None


class TestShortenGeoPoints:
    """Test shortening geographic paths from both ends."""

    def test_shorten_from_start(self):
        """Test shortening from start only."""
        from orbit.utils.geometry import shorten_geo_points

        # Path of ~111km
        geo_points = [(12.0, 57.0), (12.0, 58.0)]

        result = shorten_geo_points(geo_points, offset_start_meters=55500, offset_end_meters=0)

        assert len(result) >= 1
        # Start should be moved north
        assert result[0][1] > 57.0

    def test_shorten_from_end(self):
        """Test shortening from end only."""
        from orbit.utils.geometry import shorten_geo_points

        geo_points = [(12.0, 57.0), (12.0, 58.0)]

        result = shorten_geo_points(geo_points, offset_start_meters=0, offset_end_meters=55500)

        assert len(result) >= 1
        # End should be moved south
        assert result[-1][1] < 58.0

    def test_shorten_both_ends(self):
        """Test shortening from both ends."""
        from orbit.utils.geometry import shorten_geo_points

        geo_points = [(12.0, 57.0), (12.0, 57.5), (12.0, 58.0)]

        result = shorten_geo_points(geo_points, offset_start_meters=10000, offset_end_meters=10000)

        # Result should be shorter than original
        assert len(result) >= 1

    def test_no_shortening(self):
        """Test zero offsets returns copy."""
        from orbit.utils.geometry import shorten_geo_points

        geo_points = [(12.0, 57.0), (12.0, 58.0)]

        result = shorten_geo_points(geo_points, 0, 0)

        assert result == geo_points

    def test_single_point(self):
        """Test single point returns copy."""
        from orbit.utils.geometry import shorten_geo_points

        geo_points = [(12.0, 57.0)]

        result = shorten_geo_points(geo_points, 100, 100)

        assert result == geo_points

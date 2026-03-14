"""Unit tests for arc geometry, line intersection, and directional geometry utilities."""

import math

import pytest

from orbit.utils.geometry import (
    angle_between_vectors,
    arc_length,
    calculate_directional_scale,
    find_point_on_polyline_at_s,
    fit_circle_to_points,
    generate_arc_points,
    generate_simple_connection_path,
    haversine_distance,
    line_intersection,
    project_point_to_polyline,
)

# ============================================================================
# Test Arc Geometry Functions
# ============================================================================

class TestArcGeometry:
    """Test arc-related geometry functions."""

    def test_arc_length(self):
        """Test arc length calculation."""
        # Quarter circle with radius 10 -> length = 2*π*10/4 = 5π
        length = arc_length(10.0, math.pi / 2)
        assert length == pytest.approx(10.0 * math.pi / 2)

    def test_arc_length_negative_sweep(self):
        """Test arc length with negative sweep (should be positive)."""
        length = arc_length(10.0, -math.pi / 2)
        assert length == pytest.approx(10.0 * math.pi / 2)

    def test_generate_arc_points_quarter_circle(self):
        """Test generating points for quarter circle."""
        center = (0.0, 0.0)
        radius = 10.0
        start_angle = 0.0
        sweep_angle = math.pi / 2  # 90° CCW
        num_points = 5

        points = generate_arc_points(center, radius, start_angle, sweep_angle, num_points)

        assert len(points) == 5
        # First point should be at (10, 0)
        assert points[0][0] == pytest.approx(10.0)
        assert points[0][1] == pytest.approx(0.0)
        # Last point should be at (0, 10)
        assert points[-1][0] == pytest.approx(0.0, abs=1e-10)
        assert points[-1][1] == pytest.approx(10.0)

    def test_generate_arc_points_full_circle(self):
        """Test generating points for full circle."""
        center = (5.0, 5.0)
        radius = 3.0
        points = generate_arc_points(center, radius, 0.0, 2 * math.pi, num_points=8)

        assert len(points) == 8
        # All points should be at distance 3 from center
        for px, py in points:
            dist = math.sqrt((px - 5.0)**2 + (py - 5.0)**2)
            assert dist == pytest.approx(3.0)

    def test_fit_circle_to_points(self):
        """Test fitting circle to points on a known circle."""
        # Create points on a circle with center (10, 10) and radius 5
        center = (10.0, 10.0)
        radius = 5.0
        points = []
        for i in range(8):
            angle = i * 2 * math.pi / 8
            x = center[0] + radius * math.cos(angle)
            y = center[1] + radius * math.sin(angle)
            points.append((x, y))

        result = fit_circle_to_points(points)
        assert result is not None
        fitted_center, fitted_radius = result
        assert fitted_center[0] == pytest.approx(10.0, abs=0.1)
        assert fitted_center[1] == pytest.approx(10.0, abs=0.1)
        assert fitted_radius == pytest.approx(5.0, abs=0.1)

    def test_fit_circle_insufficient_points(self):
        """Test fitting circle with fewer than 3 points returns None."""
        assert fit_circle_to_points([(0, 0), (1, 1)]) is None
        assert fit_circle_to_points([(0, 0)]) is None
        assert fit_circle_to_points([]) is None


# ============================================================================
# Test Line Intersection
# ============================================================================

class TestLineIntersection:
    """Test line intersection calculations."""

    def test_perpendicular_lines(self):
        """Test intersection of perpendicular lines."""
        # Line 1: horizontal through origin
        p1, d1 = (0.0, 0.0), (1.0, 0.0)
        # Line 2: vertical through (5, 0)
        p2, d2 = (5.0, 0.0), (0.0, 1.0)

        result = line_intersection(p1, d1, p2, d2)
        assert result is not None
        assert result[0] == pytest.approx(5.0)
        assert result[1] == pytest.approx(0.0)

    def test_diagonal_lines(self):
        """Test intersection of diagonal lines."""
        # Line 1: y = x (through origin, slope 1)
        p1, d1 = (0.0, 0.0), (1.0, 1.0)
        # Line 2: y = -x + 10 (slope -1, y-intercept 10)
        p2, d2 = (0.0, 10.0), (1.0, -1.0)

        result = line_intersection(p1, d1, p2, d2)
        assert result is not None
        assert result[0] == pytest.approx(5.0)
        assert result[1] == pytest.approx(5.0)

    def test_parallel_lines(self):
        """Test parallel lines return None."""
        p1, d1 = (0.0, 0.0), (1.0, 0.0)
        p2, d2 = (0.0, 5.0), (1.0, 0.0)  # Same direction

        result = line_intersection(p1, d1, p2, d2)
        assert result is None

    def test_same_line(self):
        """Test same line returns None (infinite intersections)."""
        p1, d1 = (0.0, 0.0), (1.0, 1.0)
        p2, d2 = (5.0, 5.0), (2.0, 2.0)  # Same line, different point

        result = line_intersection(p1, d1, p2, d2)
        assert result is None  # Parallel case


# ============================================================================
# Test Angle Between Vectors
# ============================================================================

class TestAngleBetweenVectors:
    """Test signed angle calculation between vectors."""

    def test_perpendicular_ccw(self):
        """Test 90° counterclockwise angle."""
        v1 = (1.0, 0.0)  # East
        v2 = (0.0, 1.0)  # North
        angle = angle_between_vectors(v1, v2)
        assert angle == pytest.approx(math.pi / 2)

    def test_perpendicular_cw(self):
        """Test 90° clockwise angle (negative)."""
        v1 = (1.0, 0.0)  # East
        v2 = (0.0, -1.0)  # South
        angle = angle_between_vectors(v1, v2)
        assert angle == pytest.approx(-math.pi / 2)

    def test_same_direction(self):
        """Test zero angle for same direction."""
        v1 = (1.0, 0.0)
        v2 = (2.0, 0.0)
        angle = angle_between_vectors(v1, v2)
        assert angle == pytest.approx(0.0)

    def test_opposite_direction(self):
        """Test π angle for opposite direction."""
        v1 = (1.0, 0.0)
        v2 = (-1.0, 0.0)
        angle = angle_between_vectors(v1, v2)
        assert abs(angle) == pytest.approx(math.pi)

    def test_45_degree_angle(self):
        """Test 45° angle."""
        v1 = (1.0, 0.0)
        v2 = (1.0, 1.0)
        angle = angle_between_vectors(v1, v2)
        assert angle == pytest.approx(math.pi / 4)


# ============================================================================
# Test Calculate Directional Scale
# ============================================================================

class TestCalculateDirectionalScale:
    """Test direction-weighted scale calculation."""

    def test_horizontal_path(self):
        """Test horizontal path uses scale_x."""
        points = [(0.0, 0.0), (100.0, 0.0)]
        scale = calculate_directional_scale(points, scale_x=2.0, scale_y=1.0)
        assert scale == pytest.approx(2.0)

    def test_vertical_path(self):
        """Test vertical path uses scale_y."""
        points = [(0.0, 0.0), (0.0, 100.0)]
        scale = calculate_directional_scale(points, scale_x=2.0, scale_y=1.0)
        assert scale == pytest.approx(1.0)

    def test_diagonal_path(self):
        """Test 45° diagonal path uses average."""
        points = [(0.0, 0.0), (100.0, 100.0)]
        scale = calculate_directional_scale(points, scale_x=2.0, scale_y=1.0)
        assert scale == pytest.approx(1.5)  # Average of 2.0 and 1.0

    def test_single_point_uses_average(self):
        """Test single point uses average scale."""
        points = [(5.0, 5.0)]
        scale = calculate_directional_scale(points, scale_x=2.0, scale_y=1.0)
        assert scale == pytest.approx(1.5)

    def test_single_point_uses_default(self):
        """Test single point uses default when provided."""
        points = [(5.0, 5.0)]
        scale = calculate_directional_scale(points, scale_x=2.0, scale_y=1.0, default_scale=3.0)
        assert scale == pytest.approx(3.0)


# ============================================================================
# Test Haversine Distance
# ============================================================================

class TestHaversineDistance:
    """Test geographic distance calculation."""

    def test_same_point(self):
        """Test distance between same point is zero."""
        dist = haversine_distance(57.0, 12.0, 57.0, 12.0)
        assert dist == pytest.approx(0.0)

    def test_short_distance(self):
        """Test short distance (known approximate value)."""
        # About 1 degree latitude ≈ 111 km
        dist = haversine_distance(57.0, 12.0, 58.0, 12.0)
        assert dist == pytest.approx(111000, rel=0.01)  # Within 1%

    def test_longitude_distance(self):
        """Test distance along longitude (latitude-dependent)."""
        # At equator, 1 degree longitude ≈ 111 km
        dist = haversine_distance(0.0, 0.0, 0.0, 1.0)
        assert dist == pytest.approx(111000, rel=0.01)

    def test_symmetric(self):
        """Test distance is symmetric."""
        d1 = haversine_distance(57.0, 12.0, 58.0, 13.0)
        d2 = haversine_distance(58.0, 13.0, 57.0, 12.0)
        assert d1 == pytest.approx(d2)


# ============================================================================
# Test Generate Simple Connection Path
# ============================================================================

class TestGenerateSimpleConnectionPath:
    """Test ParamPoly3D connection path generation."""

    def test_straight_connection(self):
        """Test connection with aligned headings creates straight path."""
        from_pos = (0.0, 0.0)
        to_pos = (100.0, 0.0)
        from_heading = 0.0  # East
        to_heading = 0.0  # East

        path, coeffs = generate_simple_connection_path(
            from_pos, from_heading, to_pos, to_heading, num_points=10
        )

        assert len(path) == 10
        # First and last points should be at endpoints
        assert path[0][0] == pytest.approx(0.0, abs=0.1)
        assert path[-1][0] == pytest.approx(100.0, abs=0.1)

    def test_90_degree_turn(self):
        """Test 90-degree turn connection."""
        from_pos = (0.0, 0.0)
        to_pos = (50.0, 50.0)
        from_heading = 0.0  # East
        to_heading = math.pi / 2  # North

        path, coeffs = generate_simple_connection_path(
            from_pos, from_heading, to_pos, to_heading, num_points=20
        )

        assert len(path) == 20
        # Should return 8 coefficients (aU, bU, cU, dU, aV, bV, cV, dV)
        assert len(coeffs) == 8

    def test_returns_coefficients(self):
        """Test that coefficients tuple is returned."""
        path, coeffs = generate_simple_connection_path(
            (0, 0), 0, (100, 0), 0
        )
        # Check we got 8 float coefficients
        assert len(coeffs) == 8
        assert all(isinstance(c, float) for c in coeffs)


# ============================================================================
# Test Project Point to Polyline
# ============================================================================

class TestProjectPointToPolyline:
    """Test point projection onto polylines."""

    def test_project_on_segment(self):
        """Test projecting point onto a segment."""
        polyline = [(0.0, 0.0), (100.0, 0.0)]
        point = (50.0, 10.0)  # 10 units above midpoint

        s, dist, segment = project_point_to_polyline(point, polyline)
        assert s == pytest.approx(50.0)
        assert segment == 0

    def test_project_at_endpoint(self):
        """Test projecting point near endpoint."""
        polyline = [(0.0, 0.0), (100.0, 0.0)]
        point = (-5.0, 0.0)  # Before start

        s, dist, segment = project_point_to_polyline(point, polyline)
        assert s == pytest.approx(0.0)
        assert segment == 0

    def test_project_multi_segment(self):
        """Test projecting onto multi-segment polyline."""
        polyline = [(0.0, 0.0), (50.0, 0.0), (100.0, 0.0)]
        point = (75.0, 5.0)  # Above second segment

        s, dist, segment = project_point_to_polyline(point, polyline)
        assert s == pytest.approx(75.0)
        assert segment == 1


# ============================================================================
# Test Find Point on Polyline at S
# ============================================================================

class TestFindPointOnPolylineAtS:
    """Test finding points at s-coordinates on polylines."""

    def test_find_at_start(self):
        """Test finding point at s=0."""
        polyline = [(0.0, 0.0), (100.0, 0.0)]
        result = find_point_on_polyline_at_s(polyline, 0.0)
        assert result is not None
        point, segment, t = result
        assert point == (0.0, 0.0)

    def test_find_at_middle(self):
        """Test finding point at middle of segment."""
        polyline = [(0.0, 0.0), (100.0, 0.0)]
        result = find_point_on_polyline_at_s(polyline, 50.0)
        assert result is not None
        point, segment, t = result
        assert point[0] == pytest.approx(50.0)
        assert point[1] == pytest.approx(0.0)

    def test_find_beyond_end(self):
        """Test finding point beyond end returns last point."""
        polyline = [(0.0, 0.0), (100.0, 0.0)]
        result = find_point_on_polyline_at_s(polyline, 150.0)
        assert result is not None
        point, segment, t = result
        assert point == (100.0, 0.0)

    def test_find_negative_s(self):
        """Test finding point at negative s returns first point."""
        polyline = [(0.0, 0.0), (100.0, 0.0)]
        result = find_point_on_polyline_at_s(polyline, -10.0)
        assert result is not None
        point, segment, t = result
        assert point == (0.0, 0.0)


# ============================================================================
# Test Create Polygon From Boundaries
# ============================================================================

class TestCreatePolygonFromBoundaries:
    """Test creating polygons from explicit left/right boundaries."""

    def test_basic_boundaries(self):
        """Test creating polygon from simple boundaries."""
        from orbit.utils.geometry import create_polygon_from_boundaries

        left = [(0.0, 5.0), (50.0, 5.0), (100.0, 5.0)]
        right = [(0.0, -5.0), (50.0, -5.0), (100.0, -5.0)]

        polygon = create_polygon_from_boundaries(left, right)

        # Should have 6 points (3 left + 3 right reversed)
        assert len(polygon) == 6
        # First 3 should be left boundary
        assert polygon[:3] == left
        # Last 3 should be right boundary reversed
        assert polygon[3:] == list(reversed(right))

    def test_empty_left_boundary(self):
        """Test empty left boundary returns empty polygon."""
        from orbit.utils.geometry import create_polygon_from_boundaries

        polygon = create_polygon_from_boundaries([], [(0, 0), (10, 0)])
        assert polygon == []

    def test_empty_right_boundary(self):
        """Test empty right boundary returns empty polygon."""
        from orbit.utils.geometry import create_polygon_from_boundaries

        polygon = create_polygon_from_boundaries([(0, 0), (10, 0)], [])
        assert polygon == []

    def test_single_point_boundaries(self):
        """Test single-point boundaries return empty."""
        from orbit.utils.geometry import create_polygon_from_boundaries

        polygon = create_polygon_from_boundaries([(0, 0)], [(1, 1)])
        assert polygon == []


# ============================================================================
# Test Create Polynomial Width Lane Polygon
# ============================================================================

class TestCreatePolynomialWidthLanePolygon:
    """Test creating lane polygons with polynomial width variation."""

    def test_constant_width_right_lane(self):
        """Test constant width right lane polygon."""
        from orbit.utils.geometry import create_polynomial_width_lane_polygon

        centerline = [(0.0, 0.0), (50.0, 0.0), (100.0, 0.0)]
        s_values = [0.0, 50.0, 100.0]

        # Constant offset functions
        def inner_func(s): return 0.0  # Start at centerline
        def lane_func(s): return 3.5   # Constant 3.5m width

        polygon = create_polynomial_width_lane_polygon(
            centerline, -1, inner_func, lane_func, s_values, is_left_lane=False
        )

        assert len(polygon) == 6  # 3 inner + 3 outer

    def test_constant_width_left_lane(self):
        """Test constant width left lane polygon."""
        from orbit.utils.geometry import create_polynomial_width_lane_polygon

        centerline = [(0.0, 0.0), (100.0, 0.0)]
        s_values = [0.0, 100.0]

        def inner_func(s): return 0.0
        def lane_func(s): return 3.5

        polygon = create_polynomial_width_lane_polygon(
            centerline, 1, inner_func, lane_func, s_values, is_left_lane=True
        )

        assert len(polygon) == 4

    def test_variable_width_lane(self):
        """Test lane with varying width."""
        from orbit.utils.geometry import create_polynomial_width_lane_polygon

        centerline = [(0.0, 0.0), (50.0, 0.0), (100.0, 0.0)]
        s_values = [0.0, 50.0, 100.0]

        # Width increases linearly from 2.5 to 4.5
        def inner_func(s): return 0.0
        def lane_func(s): return 2.5 + (s / 100.0) * 2.0

        polygon = create_polynomial_width_lane_polygon(
            centerline, -1, inner_func, lane_func, s_values, is_left_lane=False
        )

        assert len(polygon) == 6

    def test_empty_centerline(self):
        """Test empty centerline returns empty."""
        from orbit.utils.geometry import create_polynomial_width_lane_polygon

        polygon = create_polynomial_width_lane_polygon(
            [], -1, lambda s: 0, lambda s: 3.5, [], is_left_lane=False
        )
        assert polygon == []

    def test_mismatched_s_values(self):
        """Test mismatched s_values count returns empty."""
        from orbit.utils.geometry import create_polynomial_width_lane_polygon

        centerline = [(0.0, 0.0), (100.0, 0.0)]
        s_values = [0.0]  # Wrong count

        polygon = create_polynomial_width_lane_polygon(
            centerline, -1, lambda s: 0, lambda s: 3.5, s_values, is_left_lane=False
        )
        assert polygon == []


# ============================================================================
# Test Generate Arc Path
# ============================================================================

class TestGenerateArcPath:
    """Test arc path generation for junction connections."""

    def test_straight_connection(self):
        """Test nearly straight connection returns two points."""
        from orbit.utils.geometry import generate_arc_path

        from_pos = (0.0, 0.0)
        to_pos = (100.0, 0.0)
        from_heading = 0.0
        to_heading = 0.05  # Nearly straight (< 10 degrees)

        path = generate_arc_path(from_pos, from_heading, to_pos, to_heading)

        assert path is not None
        assert path == [from_pos, to_pos]

    def test_curved_connection(self):
        """Test curved connection returns multiple points."""
        from orbit.utils.geometry import generate_arc_path

        from_pos = (0.0, 0.0)
        to_pos = (50.0, 50.0)
        from_heading = 0.0
        to_heading = math.pi / 2  # 90 degree turn

        path = generate_arc_path(from_pos, from_heading, to_pos, to_heading, num_points=10)

        assert path is not None
        assert len(path) == 10

    def test_very_close_points(self):
        """Test very close points returns single point."""
        from orbit.utils.geometry import generate_arc_path

        from_pos = (0.0, 0.0)
        to_pos = (0.001, 0.001)

        path = generate_arc_path(from_pos, 0.0, to_pos, math.pi / 2)

        assert path is not None
        assert len(path) == 1



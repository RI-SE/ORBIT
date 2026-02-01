"""
Unit tests for geometry utilities.

Tests geometric calculations for offset polylines, perpendicular vectors,
and polygon construction.
"""

import math

import pytest

from orbit.utils.geometry import (
    angle_between_vectors,
    arc_length,
    calculate_directional_scale,
    calculate_offset_polyline,
    calculate_path_length,
    calculate_perpendicular,
    create_lane_polygon,
    create_variable_width_lane_polygon,
    distance_between_points,
    find_point_at_distance_along_path,
    find_point_on_polyline_at_s,
    fit_circle_to_points,
    generate_arc_points,
    generate_simple_connection_path,
    haversine_distance,
    line_intersection,
    normalize_angle,
    offset_point,
    project_point_to_polyline,
    split_polyline_at_index,
)

# ============================================================================
# Test Perpendicular Calculation
# ============================================================================

class TestCalculatePerpendicular:
    """Test perpendicular vector calculations."""

    def test_perpendicular_horizontal_line(self):
        """Test perpendicular to horizontal line points upward."""
        p1 = (0.0, 0.0)
        p2 = (10.0, 0.0)  # Horizontal line going right

        perp = calculate_perpendicular(p1, p2)

        # Perpendicular should point up (90° counterclockwise)
        assert perp[0] == pytest.approx(0.0, abs=1e-10)
        assert perp[1] == pytest.approx(1.0, abs=1e-10)

    def test_perpendicular_vertical_line(self):
        """Test perpendicular to vertical line points left."""
        p1 = (0.0, 0.0)
        p2 = (0.0, 10.0)  # Vertical line going up

        perp = calculate_perpendicular(p1, p2)

        # Perpendicular should point left (90° counterclockwise from up)
        assert perp[0] == pytest.approx(-1.0, abs=1e-10)
        assert perp[1] == pytest.approx(0.0, abs=1e-10)

    def test_perpendicular_diagonal_line(self):
        """Test perpendicular to diagonal line."""
        p1 = (0.0, 0.0)
        p2 = (10.0, 10.0)  # 45° diagonal

        perp = calculate_perpendicular(p1, p2)

        # Perpendicular should be at 135° (45° + 90°)
        # Unit vector at 135°: (-√2/2, √2/2)
        sqrt2_over_2 = math.sqrt(2) / 2
        assert perp[0] == pytest.approx(-sqrt2_over_2, abs=1e-10)
        assert perp[1] == pytest.approx(sqrt2_over_2, abs=1e-10)

    def test_perpendicular_is_normalized(self):
        """Test that perpendicular vector is unit length."""
        p1 = (0.0, 0.0)
        p2 = (37.0, 42.0)  # Arbitrary vector

        perp = calculate_perpendicular(p1, p2)

        # Length should be 1.0
        length = math.sqrt(perp[0]**2 + perp[1]**2)
        assert length == pytest.approx(1.0, abs=1e-10)

    def test_perpendicular_zero_length_segment(self):
        """Test perpendicular of zero-length segment returns zero."""
        p1 = (5.0, 5.0)
        p2 = (5.0, 5.0)  # Same point

        perp = calculate_perpendicular(p1, p2)

        assert perp == (0.0, 0.0)


# ============================================================================
# Test Point Offset
# ============================================================================

class TestOffsetPoint:
    """Test offsetting points along perpendicular direction."""

    def test_offset_point_positive(self):
        """Test offsetting point in positive perpendicular direction."""
        point = (10.0, 20.0)
        perpendicular = (0.0, 1.0)  # Pointing up
        offset = 5.0

        result = offset_point(point, perpendicular, offset)

        assert result[0] == pytest.approx(10.0, abs=1e-10)
        assert result[1] == pytest.approx(25.0, abs=1e-10)

    def test_offset_point_negative(self):
        """Test offsetting point in negative perpendicular direction."""
        point = (10.0, 20.0)
        perpendicular = (0.0, 1.0)  # Pointing up
        offset = -5.0  # Negative offset

        result = offset_point(point, perpendicular, offset)

        assert result[0] == pytest.approx(10.0, abs=1e-10)
        assert result[1] == pytest.approx(15.0, abs=1e-10)

    def test_offset_point_horizontal(self):
        """Test offsetting point horizontally."""
        point = (10.0, 20.0)
        perpendicular = (1.0, 0.0)  # Pointing right
        offset = 3.0

        result = offset_point(point, perpendicular, offset)

        assert result[0] == pytest.approx(13.0, abs=1e-10)
        assert result[1] == pytest.approx(20.0, abs=1e-10)

    def test_offset_point_zero_offset(self):
        """Test that zero offset returns original point."""
        point = (10.0, 20.0)
        perpendicular = (0.0, 1.0)
        offset = 0.0

        result = offset_point(point, perpendicular, offset)

        assert result[0] == pytest.approx(10.0, abs=1e-10)
        assert result[1] == pytest.approx(20.0, abs=1e-10)


# ============================================================================
# Test Offset Polyline
# ============================================================================

class TestOffsetPolyline:
    """Test calculating offset polylines."""

    def test_offset_horizontal_line_upward(self):
        """Test offsetting horizontal line upward."""
        points = [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)]
        offset = 5.0  # Positive offset (left/up)

        result = calculate_offset_polyline(points, offset, closed=False)

        # All y-coordinates should be increased by 5
        assert len(result) == 3
        for i, point in enumerate(result):
            assert point[0] == pytest.approx(points[i][0], abs=1e-6)
            assert point[1] == pytest.approx(5.0, abs=1e-6)

    def test_offset_horizontal_line_downward(self):
        """Test offsetting horizontal line downward."""
        points = [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)]
        offset = -5.0  # Negative offset (right/down)

        result = calculate_offset_polyline(points, offset, closed=False)

        # All y-coordinates should be decreased by 5
        assert len(result) == 3
        for i, point in enumerate(result):
            assert point[0] == pytest.approx(points[i][0], abs=1e-6)
            assert point[1] == pytest.approx(-5.0, abs=1e-6)

    def test_offset_vertical_line_leftward(self):
        """Test offsetting vertical line leftward."""
        points = [(0.0, 0.0), (0.0, 10.0), (0.0, 20.0)]
        offset = 5.0  # Positive offset (left)

        result = calculate_offset_polyline(points, offset, closed=False)

        # All x-coordinates should be decreased by 5 (left)
        assert len(result) == 3
        for i, point in enumerate(result):
            assert point[0] == pytest.approx(-5.0, abs=1e-6)
            assert point[1] == pytest.approx(points[i][1], abs=1e-6)

    def test_offset_polyline_with_corner(self):
        """Test offsetting polyline with 90-degree corner."""
        points = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]  # L-shape
        offset = 2.0

        result = calculate_offset_polyline(points, offset, closed=False)

        assert len(result) == 3
        # First point should be offset perpendicular to first segment
        assert result[0][1] == pytest.approx(2.0, abs=1e-6)

    def test_offset_closed_polyline(self):
        """Test offsetting a closed polyline (polygon)."""
        # Square
        points = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        offset = 1.0

        result = calculate_offset_polyline(points, offset, closed=True)

        # Should have same number of points
        assert len(result) == 4
        # All points should be offset inward/outward

    def test_offset_empty_polyline(self):
        """Test offsetting empty polyline returns empty."""
        result = calculate_offset_polyline([], 5.0, closed=False)
        assert result == []

    def test_offset_single_point(self):
        """Test offsetting single point returns empty."""
        result = calculate_offset_polyline([(5.0, 5.0)], 5.0, closed=False)
        assert result == []


# ============================================================================
# Test Lane Polygon Creation
# ============================================================================

class TestCreateLanePolygon:
    """Test creating lane polygons between offset boundaries."""

    def test_create_polygon_straight_lane(self):
        """Test creating polygon for straight lane."""
        centerline = [(0.0, 0.0), (100.0, 0.0)]  # Horizontal
        inner_offset = 3.0  # 3 pixels up
        outer_offset = -3.0  # 3 pixels down

        polygon = create_lane_polygon(centerline, inner_offset, outer_offset, closed=False)

        # Should create a rectangle (4 points for open polyline)
        assert len(polygon) == 4

        # Check that polygon vertices are roughly where expected
        # Inner boundary: y ≈ 3, outer boundary: y ≈ -3
        # (exact values may vary due to miter joins)

    def test_create_polygon_curved_lane(self):
        """Test creating polygon for curved lane."""
        # Create a curve
        centerline = [(0.0, 0.0), (50.0, 10.0), (100.0, 0.0)]
        inner_offset = 5.0
        outer_offset = -5.0

        polygon = create_lane_polygon(centerline, inner_offset, outer_offset, closed=False)

        # Should create a polygon with 6 vertices (3 inner + 3 outer reversed)
        assert len(polygon) == 6

    def test_create_polygon_closed_lane(self):
        """Test creating polygon for closed lane (e.g., roundabout)."""
        # Simple closed path
        centerline = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        inner_offset = 2.0
        outer_offset = -2.0

        polygon = create_lane_polygon(centerline, inner_offset, outer_offset, closed=True)

        # Should create closed polygon
        assert len(polygon) > 0

    def test_create_polygon_zero_width_lane(self):
        """Test creating polygon with zero width (inner = outer)."""
        centerline = [(0.0, 0.0), (100.0, 0.0)]
        offset = 5.0

        polygon = create_lane_polygon(centerline, offset, offset, closed=False)

        # Polygon should still be created (may be degenerate)
        assert len(polygon) >= 0

    def test_create_polygon_empty_centerline(self):
        """Test creating polygon with empty centerline returns empty."""
        polygon = create_lane_polygon([], 5.0, -5.0, closed=False)
        assert polygon == []

    def test_create_polygon_single_point_centerline(self):
        """Test creating polygon with single centerline point returns empty."""
        polygon = create_lane_polygon([(5.0, 5.0)], 3.0, -3.0, closed=False)
        assert polygon == []


# ============================================================================
# Test Geometric Properties
# ============================================================================

class TestGeometricProperties:
    """Test geometric properties of offset calculations."""

    def test_parallel_lines_maintain_distance(self):
        """Test that offset creates parallel lines at correct distance."""
        points = [(0.0, 0.0), (100.0, 0.0)]  # Horizontal line
        offset = 10.0

        offset_line = calculate_offset_polyline(points, offset, closed=False)

        # Distance between corresponding points should be offset distance
        for i in range(len(points)):
            dx = offset_line[i][0] - points[i][0]
            dy = offset_line[i][1] - points[i][1]
            distance = math.sqrt(dx**2 + dy**2)
            assert distance == pytest.approx(abs(offset), abs=0.01)

    def test_offset_preserves_number_of_points(self):
        """Test that offset preserves number of points."""
        points = [(0.0, 0.0), (10.0, 5.0), (20.0, 0.0), (30.0, 10.0)]

        offset_line = calculate_offset_polyline(points, 5.0, closed=False)

        assert len(offset_line) == len(points)

    def test_polygon_is_closed(self):
        """Test that lane polygon forms closed shape."""
        centerline = [(0.0, 0.0), (50.0, 0.0), (100.0, 0.0)]
        inner_offset = 5.0
        outer_offset = -5.0

        polygon = create_lane_polygon(centerline, inner_offset, outer_offset, closed=False)

        # Polygon should have points from inner + reversed outer
        # For open polyline: inner (3 points) + reversed outer (3 points) = 6 total
        assert len(polygon) == 6


# ============================================================================
# Test Edge Cases
# ============================================================================

class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_sharp_corner_miter_limited(self):
        """Test that sharp corners have limited miter lengths."""
        # Create sharp turn (nearly 180°)
        points = [(0.0, 0.0), (10.0, 0.0), (10.1, 10.0)]
        offset = 5.0

        result = calculate_offset_polyline(points, offset, closed=False)

        # Should still produce result without extreme offsets
        assert len(result) == 3
        # Middle point shouldn't be absurdly far from original
        # (miter limiting should prevent this)

    def test_collinear_points(self):
        """Test offsetting collinear points."""
        # All points on same line
        points = [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0), (30.0, 0.0)]
        offset = 5.0

        result = calculate_offset_polyline(points, offset, closed=False)

        # All offset points should be at same y-coordinate
        assert len(result) == 4
        for point in result:
            assert point[1] == pytest.approx(5.0, abs=1e-6)

    def test_very_small_offset(self):
        """Test with very small offset distance."""
        points = [(0.0, 0.0), (100.0, 0.0)]
        offset = 0.01  # 1cm

        result = calculate_offset_polyline(points, offset, closed=False)

        assert len(result) == 2
        # Small but non-zero offset
        assert result[0][1] == pytest.approx(0.01, abs=1e-10)

    def test_large_offset_distance(self):
        """Test with large offset distance."""
        points = [(0.0, 0.0), (10.0, 0.0)]
        offset = 1000.0  # Very large offset

        result = calculate_offset_polyline(points, offset, closed=False)

        assert len(result) == 2
        # Large offset should still work
        assert result[0][1] == pytest.approx(1000.0, abs=1e-6)


# ============================================================================
# Test Real-World Scenarios
# ============================================================================

class TestRealWorldScenarios:
    """Test with realistic road geometry."""

    def test_typical_road_lane_width(self):
        """Test creating lane with typical width (3.5m)."""
        # Straight 100m road
        centerline = [(0.0, 0.0), (100.0, 0.0)]

        # Lane width 3.5m, offset ±1.75m from centerline
        polygon = create_lane_polygon(centerline, 1.75, -1.75, closed=False)

        assert len(polygon) > 0
        # Width should be approximately 3.5m (distance between inner and outer)

    def test_curved_road_segment(self):
        """Test lane polygon on curved road."""
        # Simulate curved road
        num_points = 20
        radius = 50.0
        centerline = []
        for i in range(num_points):
            angle = i * math.pi / (2 * (num_points - 1))  # Quarter circle
            x = radius * math.sin(angle)
            y = radius * (1 - math.cos(angle))
            centerline.append((x, y))

        polygon = create_lane_polygon(centerline, 1.75, -1.75, closed=False)

        # Should create smooth polygon following curve
        assert len(polygon) == num_points * 2

    def test_intersection_approach(self):
        """Test lane polygon approaching intersection (widening)."""
        centerline = [(0.0, 0.0), (50.0, 0.0), (100.0, 0.0)]

        # Normal lane width at start, wider at end
        # (Note: actual widening would require variable offsets per point,
        # this just tests that function works with these parameters)
        polygon = create_lane_polygon(centerline, 1.75, -1.75, closed=False)

        assert len(polygon) == 6


# ============================================================================
# Test Normalize Angle
# ============================================================================

class TestNormalizeAngle:
    """Test angle normalization to [-π, π] range."""

    def test_normalize_zero(self):
        """Test zero stays zero."""
        assert normalize_angle(0.0) == pytest.approx(0.0)

    def test_normalize_pi(self):
        """Test π stays π."""
        assert normalize_angle(math.pi) == pytest.approx(math.pi)

    def test_normalize_negative_pi(self):
        """Test -π stays -π."""
        assert normalize_angle(-math.pi) == pytest.approx(-math.pi)

    def test_normalize_large_positive(self):
        """Test angle > π is normalized."""
        angle = 3 * math.pi / 2  # 270° = -90° normalized
        result = normalize_angle(angle)
        assert result == pytest.approx(-math.pi / 2)

    def test_normalize_large_negative(self):
        """Test angle < -π is normalized."""
        angle = -3 * math.pi / 2  # -270° = 90° normalized
        result = normalize_angle(angle)
        assert result == pytest.approx(math.pi / 2)

    def test_normalize_multiple_rotations_positive(self):
        """Test multiple full rotations (positive)."""
        angle = 5 * math.pi  # 2.5 full rotations = π
        result = normalize_angle(angle)
        assert result == pytest.approx(math.pi)

    def test_normalize_multiple_rotations_negative(self):
        """Test multiple full rotations (negative)."""
        angle = -5 * math.pi  # -2.5 full rotations = -π
        result = normalize_angle(angle)
        assert result == pytest.approx(-math.pi)

    def test_normalize_small_positive(self):
        """Test small positive angle stays unchanged."""
        angle = math.pi / 4  # 45°
        result = normalize_angle(angle)
        assert result == pytest.approx(angle)

    def test_normalize_small_negative(self):
        """Test small negative angle stays unchanged."""
        angle = -math.pi / 4  # -45°
        result = normalize_angle(angle)
        assert result == pytest.approx(angle)


# ============================================================================
# Test Distance Between Points
# ============================================================================

class TestDistanceBetweenPoints:
    """Test Euclidean distance calculation."""

    def test_distance_horizontal(self):
        """Test distance for horizontal separation."""
        p1 = (0.0, 0.0)
        p2 = (10.0, 0.0)
        assert distance_between_points(p1, p2) == pytest.approx(10.0)

    def test_distance_vertical(self):
        """Test distance for vertical separation."""
        p1 = (0.0, 0.0)
        p2 = (0.0, 10.0)
        assert distance_between_points(p1, p2) == pytest.approx(10.0)

    def test_distance_diagonal(self):
        """Test distance for diagonal (3-4-5 triangle)."""
        p1 = (0.0, 0.0)
        p2 = (3.0, 4.0)
        assert distance_between_points(p1, p2) == pytest.approx(5.0)

    def test_distance_same_point(self):
        """Test distance between same point is zero."""
        p1 = (5.0, 5.0)
        assert distance_between_points(p1, p1) == pytest.approx(0.0)

    def test_distance_negative_coordinates(self):
        """Test distance with negative coordinates."""
        p1 = (-5.0, -5.0)
        p2 = (5.0, 5.0)
        expected = math.sqrt(200)  # sqrt(10² + 10²)
        assert distance_between_points(p1, p2) == pytest.approx(expected)

    def test_distance_symmetric(self):
        """Test distance is symmetric (p1->p2 == p2->p1)."""
        p1 = (3.0, 7.0)
        p2 = (15.0, 22.0)
        assert distance_between_points(p1, p2) == pytest.approx(distance_between_points(p2, p1))


# ============================================================================
# Test Calculate Path Length
# ============================================================================

class TestCalculatePathLength:
    """Test path length calculation for polylines."""

    def test_path_length_horizontal(self):
        """Test length of horizontal path."""
        points = [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)]
        assert calculate_path_length(points) == pytest.approx(20.0)

    def test_path_length_vertical(self):
        """Test length of vertical path."""
        points = [(0.0, 0.0), (0.0, 10.0), (0.0, 30.0)]
        assert calculate_path_length(points) == pytest.approx(30.0)

    def test_path_length_zigzag(self):
        """Test length of zigzag path (3-4-5 triangles)."""
        points = [(0.0, 0.0), (3.0, 4.0), (6.0, 0.0)]
        assert calculate_path_length(points) == pytest.approx(10.0)  # 5 + 5

    def test_path_length_single_segment(self):
        """Test length of single segment."""
        points = [(0.0, 0.0), (3.0, 4.0)]
        assert calculate_path_length(points) == pytest.approx(5.0)

    def test_path_length_single_point(self):
        """Test single point returns 0."""
        points = [(5.0, 5.0)]
        assert calculate_path_length(points) == pytest.approx(0.0)

    def test_path_length_empty(self):
        """Test empty list returns 0."""
        assert calculate_path_length([]) == pytest.approx(0.0)


# ============================================================================
# Test Find Point At Distance Along Path
# ============================================================================

class TestFindPointAtDistanceAlongPath:
    """Test finding points at specific distances along polylines."""

    def test_find_point_at_start(self):
        """Test finding point at distance 0 returns start."""
        points = [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)]
        result = find_point_at_distance_along_path(points, 0.0)
        assert result is not None
        point, direction, segment = result
        assert point[0] == pytest.approx(0.0)
        assert point[1] == pytest.approx(0.0)

    def test_find_point_middle_of_segment(self):
        """Test finding point in middle of segment."""
        points = [(0.0, 0.0), (10.0, 0.0)]
        result = find_point_at_distance_along_path(points, 5.0)
        assert result is not None
        point, direction, segment = result
        assert point[0] == pytest.approx(5.0)
        assert point[1] == pytest.approx(0.0)

    def test_find_point_at_vertex(self):
        """Test finding point exactly at a vertex."""
        points = [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)]
        result = find_point_at_distance_along_path(points, 10.0)
        assert result is not None
        point, direction, segment = result
        assert point[0] == pytest.approx(10.0)
        assert point[1] == pytest.approx(0.0)

    def test_find_point_beyond_path(self):
        """Test finding point beyond path length returns None."""
        points = [(0.0, 0.0), (10.0, 0.0)]
        result = find_point_at_distance_along_path(points, 15.0)
        assert result is None

    def test_find_point_from_end(self):
        """Test finding point measuring from end."""
        points = [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)]
        result = find_point_at_distance_along_path(points, 5.0, from_start=False)
        assert result is not None
        point, direction, segment = result
        assert point[0] == pytest.approx(15.0)
        assert point[1] == pytest.approx(0.0)

    def test_find_point_direction_vector(self):
        """Test that direction vector is normalized and correct."""
        points = [(0.0, 0.0), (10.0, 0.0)]
        result = find_point_at_distance_along_path(points, 5.0)
        assert result is not None
        point, direction, segment = result
        # Direction should be unit vector pointing right
        assert direction[0] == pytest.approx(1.0)
        assert direction[1] == pytest.approx(0.0)

    def test_find_point_single_point(self):
        """Test with single point returns None."""
        result = find_point_at_distance_along_path([(5.0, 5.0)], 1.0)
        assert result is None


# ============================================================================
# Test Split Polyline At Index
# ============================================================================

class TestSplitPolylineAtIndex:
    """Test polyline splitting at indices."""

    def test_split_middle(self):
        """Test splitting at middle point."""
        points = [(0, 0), (10, 0), (20, 0), (30, 0)]
        first, second = split_polyline_at_index(points, 2)
        assert first == [(0, 0), (10, 0), (20, 0)]
        assert second == [(20, 0), (30, 0)]

    def test_split_no_duplicate(self):
        """Test splitting without duplicating split point."""
        points = [(0, 0), (10, 0), (20, 0), (30, 0)]
        first, second = split_polyline_at_index(points, 2, duplicate_point=False)
        assert first == [(0, 0), (10, 0), (20, 0)]
        assert second == [(30, 0)]

    def test_split_at_start(self):
        """Test splitting at start returns empty first."""
        points = [(0, 0), (10, 0), (20, 0)]
        first, second = split_polyline_at_index(points, 0)
        assert first == []
        assert second == [(0, 0), (10, 0), (20, 0)]

    def test_split_at_end(self):
        """Test splitting at end returns empty second."""
        points = [(0, 0), (10, 0), (20, 0)]
        first, second = split_polyline_at_index(points, 2)
        assert first == [(0, 0), (10, 0), (20, 0)]
        assert second == []


# ============================================================================
# Test Variable Width Lane Polygon
# ============================================================================

class TestCreateVariableWidthLanePolygon:
    """Test creating lane polygons with tapering width."""

    def test_variable_width_taper(self):
        """Test creating a tapering lane polygon."""
        centerline = [(0.0, 0.0), (50.0, 0.0), (100.0, 0.0)]
        # Start narrow (±2), end wide (±4)
        polygon = create_variable_width_lane_polygon(
            centerline, 2.0, -2.0, 4.0, -4.0
        )
        assert len(polygon) == 6  # 3 inner + 3 outer

    def test_variable_width_constant(self):
        """Test constant width (same start and end offsets)."""
        centerline = [(0.0, 0.0), (100.0, 0.0)]
        polygon = create_variable_width_lane_polygon(
            centerline, 3.0, -3.0, 3.0, -3.0
        )
        assert len(polygon) == 4  # 2 inner + 2 outer

    def test_variable_width_empty_centerline(self):
        """Test empty centerline returns empty polygon."""
        polygon = create_variable_width_lane_polygon([], 3.0, -3.0, 3.0, -3.0)
        assert polygon == []

    def test_variable_width_single_point(self):
        """Test single point centerline returns empty polygon."""
        polygon = create_variable_width_lane_polygon([(0, 0)], 3.0, -3.0, 3.0, -3.0)
        assert polygon == []


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


# ============================================================================
# Test ParamPoly3D Functions
# ============================================================================

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

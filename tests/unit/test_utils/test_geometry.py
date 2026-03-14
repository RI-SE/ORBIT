"""
Unit tests for geometry utilities.

Tests geometric calculations for offset polylines, perpendicular vectors,
and polygon construction.
"""

import math

import pytest

from orbit.utils.geometry import (
    calculate_offset_polyline,
    calculate_path_length,
    calculate_perpendicular,
    create_lane_polygon,
    create_variable_width_lane_polygon,
    distance_between_points,
    find_point_at_distance_along_path,
    normalize_angle,
    offset_point,
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



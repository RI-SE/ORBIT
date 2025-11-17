"""
Unit tests for Polyline model.

Tests polyline creation, point manipulation, serialization, and validation.
"""

import pytest
import uuid

from orbit.models import Polyline, LineType, RoadMarkType


class TestPolylineCreation:
    """Test polyline initialization and basic properties."""

    def test_empty_polyline_creation(self):
        """Test creating an empty polyline."""
        polyline = Polyline()

        assert polyline.points == []
        assert polyline.closed is False
        assert polyline.line_type == LineType.LANE_BOUNDARY
        assert polyline.road_mark_type == RoadMarkType.SOLID
        assert polyline.color == (0, 255, 255)  # Default cyan
        assert polyline.elevations is None
        assert polyline.s_offsets is None

    def test_polyline_auto_generates_id(self):
        """Test that polylines automatically generate unique IDs."""
        poly1 = Polyline()
        poly2 = Polyline()

        assert poly1.id != poly2.id
        # Verify it's a valid UUID
        uuid.UUID(poly1.id)
        uuid.UUID(poly2.id)

    def test_centerline_polyline_creation(self, centerline_polyline: Polyline):
        """Test creating a centerline polyline."""
        assert centerline_polyline.line_type == LineType.CENTERLINE
        assert centerline_polyline.road_mark_type == RoadMarkType.NONE
        assert len(centerline_polyline.points) == 10

    def test_boundary_polyline_creation(self, sample_polyline: Polyline):
        """Test creating a boundary polyline."""
        assert sample_polyline.line_type == LineType.LANE_BOUNDARY
        assert sample_polyline.road_mark_type == RoadMarkType.SOLID
        assert len(sample_polyline.points) == 5


class TestPointManipulation:
    """Test adding, inserting, moving, and removing points."""

    def test_add_point(self):
        """Test adding points to a polyline."""
        polyline = Polyline()

        polyline.add_point(10.0, 20.0)
        polyline.add_point(30.0, 40.0)

        assert len(polyline.points) == 2
        assert polyline.points[0] == (10.0, 20.0)
        assert polyline.points[1] == (30.0, 40.0)

    def test_insert_point_at_beginning(self):
        """Test inserting a point at the beginning."""
        polyline = Polyline()
        polyline.add_point(10.0, 20.0)
        polyline.add_point(30.0, 40.0)

        polyline.insert_point(0, 0.0, 0.0)

        assert len(polyline.points) == 3
        assert polyline.points[0] == (0.0, 0.0)
        assert polyline.points[1] == (10.0, 20.0)
        assert polyline.points[2] == (30.0, 40.0)

    def test_insert_point_in_middle(self):
        """Test inserting a point in the middle."""
        polyline = Polyline()
        polyline.add_point(10.0, 20.0)
        polyline.add_point(30.0, 40.0)

        polyline.insert_point(1, 20.0, 30.0)

        assert len(polyline.points) == 3
        assert polyline.points[0] == (10.0, 20.0)
        assert polyline.points[1] == (20.0, 30.0)
        assert polyline.points[2] == (30.0, 40.0)

    def test_insert_point_at_end(self):
        """Test inserting a point at the end."""
        polyline = Polyline()
        polyline.add_point(10.0, 20.0)
        polyline.add_point(30.0, 40.0)

        polyline.insert_point(2, 50.0, 60.0)

        assert len(polyline.points) == 3
        assert polyline.points[2] == (50.0, 60.0)

    def test_remove_point(self):
        """Test removing a point by index."""
        polyline = Polyline()
        polyline.add_point(10.0, 20.0)
        polyline.add_point(30.0, 40.0)
        polyline.add_point(50.0, 60.0)

        polyline.remove_point(1)

        assert len(polyline.points) == 2
        assert polyline.points[0] == (10.0, 20.0)
        assert polyline.points[1] == (50.0, 60.0)

    def test_remove_point_invalid_index_does_nothing(self):
        """Test that removing with invalid index doesn't crash."""
        polyline = Polyline()
        polyline.add_point(10.0, 20.0)

        # Out of range index should be handled gracefully
        polyline.remove_point(5)
        polyline.remove_point(-10)

        assert len(polyline.points) == 1  # Point still there

    def test_update_point(self):
        """Test updating point coordinates."""
        polyline = Polyline()
        polyline.add_point(10.0, 20.0)
        polyline.add_point(30.0, 40.0)

        polyline.update_point(1, 35.0, 45.0)

        assert polyline.points[1] == (35.0, 45.0)
        assert polyline.points[0] == (10.0, 20.0)  # Other points unchanged

    def test_update_point_invalid_index_does_nothing(self):
        """Test that updating with invalid index doesn't crash."""
        polyline = Polyline()
        polyline.add_point(10.0, 20.0)

        # Out of range index should be handled gracefully
        polyline.update_point(5, 100.0, 200.0)

        assert polyline.points[0] == (10.0, 20.0)  # Unchanged

    def test_get_point(self):
        """Test getting a point by index."""
        polyline = Polyline()
        polyline.add_point(10.0, 20.0)
        polyline.add_point(30.0, 40.0)

        point = polyline.get_point(1)

        assert point == (30.0, 40.0)

    def test_point_count(self):
        """Test point_count() method."""
        polyline = Polyline()
        assert polyline.point_count() == 0

        polyline.add_point(10.0, 20.0)
        assert polyline.point_count() == 1

        polyline.add_point(30.0, 40.0)
        assert polyline.point_count() == 2


class TestPolylineValidation:
    """Test polyline validation methods."""

    def test_empty_polyline_is_invalid(self):
        """Test that polyline with no points is invalid."""
        polyline = Polyline()
        assert polyline.is_valid() is False

    def test_single_point_polyline_is_invalid(self):
        """Test that polyline with one point is invalid."""
        polyline = Polyline()
        polyline.add_point(10.0, 20.0)
        assert polyline.is_valid() is False

    def test_two_point_polyline_is_valid(self):
        """Test that polyline with two points is valid."""
        polyline = Polyline()
        polyline.add_point(10.0, 20.0)
        polyline.add_point(30.0, 40.0)
        assert polyline.is_valid() is True

    def test_many_points_polyline_is_valid(self, sample_polyline: Polyline):
        """Test that polyline with many points is valid."""
        assert sample_polyline.is_valid() is True
        assert sample_polyline.point_count() == 5


class TestPolylineReverse:
    """Test reversing polyline direction."""

    def test_reverse_polyline(self):
        """Test reversing a polyline reverses point order."""
        polyline = Polyline()
        polyline.add_point(10.0, 20.0)
        polyline.add_point(30.0, 40.0)
        polyline.add_point(50.0, 60.0)

        original_points = polyline.points.copy()
        polyline.reverse()

        assert polyline.points[0] == original_points[2]
        assert polyline.points[1] == original_points[1]
        assert polyline.points[2] == original_points[0]

    def test_reverse_centerline(self, centerline_polyline: Polyline):
        """Test reversing a centerline polyline."""
        first_point = centerline_polyline.points[0]
        last_point = centerline_polyline.points[-1]

        centerline_polyline.reverse()

        assert centerline_polyline.points[0] == last_point
        assert centerline_polyline.points[-1] == first_point

    def test_double_reverse_returns_original(self):
        """Test that reversing twice returns to original order."""
        polyline = Polyline()
        polyline.add_point(10.0, 20.0)
        polyline.add_point(30.0, 40.0)
        polyline.add_point(50.0, 60.0)

        original_points = polyline.points.copy()

        polyline.reverse()
        polyline.reverse()

        assert polyline.points == original_points


class TestPolylineTypes:
    """Test different line types and road mark types."""

    def test_line_type_centerline(self):
        """Test centerline line type."""
        polyline = Polyline(line_type=LineType.CENTERLINE)
        assert polyline.line_type == LineType.CENTERLINE

    def test_line_type_boundary(self):
        """Test boundary line type."""
        polyline = Polyline(line_type=LineType.LANE_BOUNDARY)
        assert polyline.line_type == LineType.LANE_BOUNDARY

    @pytest.mark.parametrize("mark_type", [
        RoadMarkType.NONE,
        RoadMarkType.SOLID,
        RoadMarkType.BROKEN,
        RoadMarkType.SOLID_SOLID,
        RoadMarkType.SOLID_BROKEN,
        RoadMarkType.BROKEN_SOLID,
        RoadMarkType.CURB,
    ])
    def test_road_mark_types(self, mark_type: RoadMarkType):
        """Test various road mark types."""
        polyline = Polyline(road_mark_type=mark_type)
        assert polyline.road_mark_type == mark_type


class TestPolylineClosed:
    """Test closed vs open polylines."""

    def test_open_polyline(self):
        """Test open polyline (default)."""
        polyline = Polyline()
        assert polyline.closed is False

    def test_closed_polyline(self):
        """Test closed polyline."""
        polyline = Polyline(closed=True)
        assert polyline.closed is True

    def test_closed_polyline_connects_ends(self):
        """Test that closed polyline logically connects first and last points."""
        polyline = Polyline(closed=True)
        polyline.add_point(0.0, 0.0)
        polyline.add_point(100.0, 0.0)
        polyline.add_point(100.0, 100.0)
        polyline.add_point(0.0, 100.0)

        # Closed means last point connects back to first
        assert polyline.closed is True
        # In a closed polyline, the rendering connects points[0] to points[-1]
        # But the actual points list doesn't duplicate the first point
        assert polyline.points[0] != polyline.points[-1]


class TestPolylineSerialization:
    """Test polyline to_dict/from_dict serialization."""

    def test_polyline_to_dict(self, sample_polyline: Polyline):
        """Test converting polyline to dictionary."""
        data = sample_polyline.to_dict()

        assert 'id' in data
        assert 'points' in data
        assert 'color' in data
        assert 'closed' in data
        assert 'line_type' in data
        assert 'road_mark_type' in data

        assert data['points'] == sample_polyline.points
        assert data['line_type'] == sample_polyline.line_type.value
        assert data['road_mark_type'] == sample_polyline.road_mark_type.value

    def test_polyline_to_dict_with_optional_fields(self):
        """Test serializing polyline with optional fields."""
        polyline = Polyline()
        polyline.add_point(0.0, 0.0)
        polyline.add_point(100.0, 0.0)
        polyline.elevations = [10.0, 15.0]
        polyline.s_offsets = [0.0, 100.0]
        polyline.opendrive_id = "road_123"

        data = polyline.to_dict()

        assert data['elevations'] == [10.0, 15.0]
        assert data['s_offsets'] == [0.0, 100.0]
        assert data['opendrive_id'] == "road_123"

    def test_polyline_to_dict_omits_none_optional_fields(self):
        """Test that None optional fields are omitted from dict."""
        polyline = Polyline()
        polyline.add_point(0.0, 0.0)

        data = polyline.to_dict()

        assert 'elevations' not in data
        assert 's_offsets' not in data
        assert 'opendrive_id' not in data

    def test_polyline_from_dict(self):
        """Test creating polyline from dictionary."""
        data = {
            'id': 'test-id-123',
            'points': [[0.0, 0.0], [100.0, 0.0], [100.0, 100.0]],
            'color': [255, 0, 0],
            'closed': False,
            'line_type': 'centerline',
            'road_mark_type': 'none'
        }

        polyline = Polyline.from_dict(data)

        assert polyline.id == 'test-id-123'
        assert len(polyline.points) == 3
        assert polyline.points[0] == (0.0, 0.0)
        assert polyline.color == (255, 0, 0)
        assert polyline.closed is False
        assert polyline.line_type == LineType.CENTERLINE
        assert polyline.road_mark_type == RoadMarkType.NONE

    def test_polyline_from_dict_with_optional_fields(self):
        """Test creating polyline with optional fields from dict."""
        data = {
            'id': 'test-id',
            'points': [[0.0, 0.0], [100.0, 0.0]],
            'color': [255, 0, 0],
            'closed': False,
            'line_type': 'centerline',
            'road_mark_type': 'none',
            'elevations': [10.0, 15.0],
            's_offsets': [0.0, 100.0],
            'opendrive_id': 'road_456'
        }

        polyline = Polyline.from_dict(data)

        assert polyline.elevations == [10.0, 15.0]
        assert polyline.s_offsets == [0.0, 100.0]
        assert polyline.opendrive_id == 'road_456'

    def test_polyline_from_dict_uses_defaults(self):
        """Test that from_dict() uses defaults for missing fields."""
        minimal_data = {
            'points': [[0.0, 0.0], [100.0, 0.0]]
        }

        polyline = Polyline.from_dict(minimal_data)

        # Should auto-generate ID
        assert polyline.id is not None
        uuid.UUID(polyline.id)  # Validate it's a UUID

        # Should use defaults
        assert polyline.color == (0, 255, 255)
        assert polyline.closed is False
        assert polyline.line_type == LineType.LANE_BOUNDARY
        assert polyline.road_mark_type == RoadMarkType.SOLID

    def test_polyline_from_dict_handles_invalid_enums(self):
        """Test that invalid enum values fall back to defaults."""
        data = {
            'points': [[0.0, 0.0], [100.0, 0.0]],
            'line_type': 'invalid_type',
            'road_mark_type': 'invalid_mark'
        }

        polyline = Polyline.from_dict(data)

        # Should fallback to defaults
        assert polyline.line_type == LineType.LANE_BOUNDARY
        assert polyline.road_mark_type == RoadMarkType.SOLID

    def test_polyline_roundtrip_serialization(self, sample_polyline: Polyline):
        """Test polyline → dict → polyline preserves data."""
        data = sample_polyline.to_dict()
        restored = Polyline.from_dict(data)

        assert restored.id == sample_polyline.id
        assert restored.points == sample_polyline.points
        assert restored.color == sample_polyline.color
        assert restored.closed == sample_polyline.closed
        assert restored.line_type == sample_polyline.line_type
        assert restored.road_mark_type == sample_polyline.road_mark_type


class TestPolylineColors:
    """Test polyline color handling."""

    def test_default_color(self):
        """Test default polyline color is cyan."""
        polyline = Polyline()
        assert polyline.color == (0, 255, 255)

    def test_custom_color(self):
        """Test setting custom color."""
        polyline = Polyline(color=(255, 0, 0))
        assert polyline.color == (255, 0, 0)

    def test_centerline_color_convention(self, centerline_polyline: Polyline):
        """Test centerline uses red color by convention."""
        assert centerline_polyline.color == (255, 0, 0)

    def test_boundary_color_convention(self, boundary_polyline_left: Polyline):
        """Test boundaries use cyan color by convention."""
        assert boundary_polyline_left.color == (0, 255, 255)

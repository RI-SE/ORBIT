"""
Unit tests for RoadObject model and ObjectType enum.

Tests the object model for roadside objects (lampposts, buildings, trees, etc.).
"""

from typing import Tuple

import pytest

from orbit.models.object import ObjectType, RoadObject

# ============================================================================
# Test ObjectType Enum
# ============================================================================

class TestObjectTypeGetCategory:
    """Test ObjectType.get_category() method."""

    def test_road_furniture_lamppost(self):
        """Test lamppost is road_furniture."""
        assert ObjectType.LAMPPOST.get_category() == "road_furniture"

    def test_road_furniture_guardrail(self):
        """Test guardrail is road_furniture."""
        assert ObjectType.GUARDRAIL.get_category() == "road_furniture"

    def test_road_environment_building(self):
        """Test building is road_environment."""
        assert ObjectType.BUILDING.get_category() == "road_environment"

    def test_road_environment_tree_broadleaf(self):
        """Test broadleaf tree is road_environment."""
        assert ObjectType.TREE_BROADLEAF.get_category() == "road_environment"

    def test_road_environment_tree_conifer(self):
        """Test conifer tree is road_environment."""
        assert ObjectType.TREE_CONIFER.get_category() == "road_environment"

    def test_road_environment_bush(self):
        """Test bush is road_environment."""
        assert ObjectType.BUSH.get_category() == "road_environment"

    def test_parking_surface(self):
        """Test parking surface is parking category."""
        assert ObjectType.PARKING_SURFACE.get_category() == "parking"

    def test_parking_underground(self):
        """Test parking underground is parking category."""
        assert ObjectType.PARKING_UNDERGROUND.get_category() == "parking"

    def test_parking_multi_storey(self):
        """Test parking multi-storey is parking category."""
        assert ObjectType.PARKING_MULTI_STOREY.get_category() == "parking"

    def test_parking_rooftop(self):
        """Test parking rooftop is parking category."""
        assert ObjectType.PARKING_ROOFTOP.get_category() == "parking"


class TestObjectTypeGetDefaultDimensions:
    """Test ObjectType.get_default_dimensions() method."""

    def test_lamppost_dimensions(self):
        """Test lamppost default dimensions."""
        dims = ObjectType.LAMPPOST.get_default_dimensions()
        assert dims["radius"] == 0.15
        assert dims["height"] == 6.0

    def test_guardrail_dimensions(self):
        """Test guardrail default dimensions."""
        dims = ObjectType.GUARDRAIL.get_default_dimensions()
        assert dims["height"] == 1.0
        assert dims["width"] == 0.3

    def test_building_dimensions(self):
        """Test building default dimensions."""
        dims = ObjectType.BUILDING.get_default_dimensions()
        assert dims["width"] == 10.0
        assert dims["length"] == 8.0
        assert dims["height"] == 6.0

    def test_tree_broadleaf_dimensions(self):
        """Test broadleaf tree default dimensions."""
        dims = ObjectType.TREE_BROADLEAF.get_default_dimensions()
        assert dims["radius"] == 2.5
        assert dims["height"] == 8.0

    def test_tree_conifer_dimensions(self):
        """Test conifer tree default dimensions."""
        dims = ObjectType.TREE_CONIFER.get_default_dimensions()
        assert dims["radius"] == 1.5
        assert dims["height"] == 12.0

    def test_bush_dimensions(self):
        """Test bush default dimensions."""
        dims = ObjectType.BUSH.get_default_dimensions()
        assert dims["radius"] == 1.0
        assert dims["height"] == 1.5

    def test_parking_surface_dimensions(self):
        """Test parking surface default dimensions."""
        dims = ObjectType.PARKING_SURFACE.get_default_dimensions()
        assert dims["width"] == 50.0
        assert dims["length"] == 30.0
        assert dims["height"] == 0.0

    def test_parking_underground_dimensions(self):
        """Test parking underground has height for depth."""
        dims = ObjectType.PARKING_UNDERGROUND.get_default_dimensions()
        assert dims["height"] == 3.0

    def test_parking_multi_storey_dimensions(self):
        """Test parking multi-storey dimensions."""
        dims = ObjectType.PARKING_MULTI_STOREY.get_default_dimensions()
        assert dims["width"] == 40.0
        assert dims["length"] == 40.0
        assert dims["height"] == 12.0


class TestObjectTypeGetShapeType:
    """Test ObjectType.get_shape_type() method."""

    def test_lamppost_is_cylinder(self):
        """Test lamppost shape is cylinder."""
        assert ObjectType.LAMPPOST.get_shape_type() == "cylinder"

    def test_guardrail_is_polyline(self):
        """Test guardrail shape is polyline."""
        assert ObjectType.GUARDRAIL.get_shape_type() == "polyline"

    def test_building_is_polygon(self):
        """Test building shape is polygon."""
        assert ObjectType.BUILDING.get_shape_type() == "polygon"

    def test_tree_broadleaf_is_circle(self):
        """Test broadleaf tree shape is circle."""
        assert ObjectType.TREE_BROADLEAF.get_shape_type() == "circle"

    def test_tree_conifer_is_cone(self):
        """Test conifer tree shape is cone."""
        assert ObjectType.TREE_CONIFER.get_shape_type() == "cone"

    def test_bush_is_circle(self):
        """Test bush shape is circle."""
        assert ObjectType.BUSH.get_shape_type() == "circle"

    def test_parking_surface_is_polygon(self):
        """Test parking surface shape is polygon."""
        assert ObjectType.PARKING_SURFACE.get_shape_type() == "polygon"

    def test_parking_underground_is_polygon(self):
        """Test parking underground shape is polygon."""
        assert ObjectType.PARKING_UNDERGROUND.get_shape_type() == "polygon"


class TestObjectTypeHasOrientation:
    """Test ObjectType.has_orientation() method."""

    def test_building_has_orientation(self):
        """Test building supports orientation."""
        assert ObjectType.BUILDING.has_orientation() is True

    def test_lamppost_has_orientation(self):
        """Test lamppost supports orientation."""
        assert ObjectType.LAMPPOST.has_orientation() is True

    def test_guardrail_no_orientation(self):
        """Test guardrail does not support orientation."""
        assert ObjectType.GUARDRAIL.has_orientation() is False

    def test_tree_no_orientation(self):
        """Test tree does not support orientation."""
        assert ObjectType.TREE_BROADLEAF.has_orientation() is False

    def test_bush_no_orientation(self):
        """Test bush does not support orientation."""
        assert ObjectType.BUSH.has_orientation() is False


class TestObjectTypeSupportsValidityLength:
    """Test ObjectType.supports_validity_length() method."""

    def test_guardrail_supports_validity_length(self):
        """Test guardrail supports validity length."""
        assert ObjectType.GUARDRAIL.supports_validity_length() is True

    def test_lamppost_no_validity_length(self):
        """Test lamppost does not support validity length."""
        assert ObjectType.LAMPPOST.supports_validity_length() is False

    def test_building_no_validity_length(self):
        """Test building does not support validity length."""
        assert ObjectType.BUILDING.supports_validity_length() is False

    def test_tree_no_validity_length(self):
        """Test tree does not support validity length."""
        assert ObjectType.TREE_BROADLEAF.supports_validity_length() is False


# ============================================================================
# Test RoadObject Basic Construction
# ============================================================================

class TestRoadObjectConstruction:
    """Test RoadObject construction."""

    def test_default_construction(self):
        """Test default construction."""
        obj = RoadObject()
        assert obj.id == ""
        assert obj.position == (0.0, 0.0)
        assert obj.type == ObjectType.BUILDING  # Default type
        assert obj.road_id is None

    def test_construction_with_position(self):
        """Test construction with position."""
        obj = RoadObject(position=(100.0, 200.0))
        assert obj.position == (100.0, 200.0)

    def test_construction_with_object_type(self):
        """Test construction with specific object type."""
        obj = RoadObject(object_type=ObjectType.LAMPPOST)
        assert obj.type == ObjectType.LAMPPOST
        # Should have lamppost dimensions
        assert obj.dimensions["radius"] == 0.15
        assert obj.dimensions["height"] == 6.0

    def test_construction_with_id(self):
        """Test construction with specific ID."""
        obj = RoadObject(object_id="test-id-123")
        assert obj.id == "test-id-123"

    def test_construction_with_road_id(self):
        """Test construction with road association."""
        obj = RoadObject(road_id="road-1")
        assert obj.road_id == "road-1"

    def test_construction_with_geo_position(self):
        """Test construction with geographic position."""
        obj = RoadObject(geo_position=(12.345, 57.789))
        assert obj.geo_position == (12.345, 57.789)

    def test_default_fields(self):
        """Test default field values."""
        obj = RoadObject()
        assert obj.name == ""
        assert obj.orientation == 0.0
        assert obj.z_offset == 0.0
        assert obj.points == []
        assert obj.geo_points is None
        assert obj.s_position is None
        assert obj.t_offset is None
        assert obj.validity_length is None
        assert obj.pitch == 0.0
        assert obj.roll == 0.0


# ============================================================================
# Test RoadObject Geo Coordinate Methods
# ============================================================================

class TestRoadObjectHasGeoCoords:
    """Test RoadObject.has_geo_coords() method."""

    def test_no_geo_coords(self):
        """Test object without geo coordinates."""
        obj = RoadObject(position=(100.0, 200.0))
        assert obj.has_geo_coords() is False

    def test_with_geo_position(self):
        """Test point object with geo position."""
        obj = RoadObject(
            object_type=ObjectType.LAMPPOST,
            geo_position=(12.345, 57.789)
        )
        assert obj.has_geo_coords() is True

    def test_polyline_no_geo_points(self):
        """Test polyline object without geo points."""
        obj = RoadObject(object_type=ObjectType.GUARDRAIL)
        obj.points = [(0, 0), (10, 0), (20, 0)]
        assert obj.has_geo_coords() is False

    def test_polyline_with_geo_points(self):
        """Test polyline object with geo points."""
        obj = RoadObject(object_type=ObjectType.GUARDRAIL)
        obj.points = [(0, 0), (10, 0), (20, 0)]
        obj.geo_points = [(12.0, 57.0), (12.001, 57.0), (12.002, 57.0)]
        assert obj.has_geo_coords() is True

    def test_polyline_with_empty_geo_points(self):
        """Test polyline object with empty geo points list."""
        obj = RoadObject(object_type=ObjectType.GUARDRAIL)
        obj.geo_points = []
        assert obj.has_geo_coords() is False


class MockTransformer:
    """Mock transformer for testing coordinate conversions."""

    def geo_to_pixel(self, lon: float, lat: float) -> Tuple[float, float]:
        """Convert geo to pixel (simple scaling for test)."""
        # Simple mock: lon -> x * 1000, lat -> y * 1000
        return (lon * 1000.0, lat * 1000.0)


class TestRoadObjectGetPixelPosition:
    """Test RoadObject.get_pixel_position() method."""

    def test_no_transformer_returns_stored_position(self):
        """Test without transformer returns stored position."""
        obj = RoadObject(position=(100.0, 200.0))
        assert obj.get_pixel_position() == (100.0, 200.0)

    def test_no_geo_returns_stored_position(self):
        """Test without geo coords returns stored position."""
        obj = RoadObject(position=(100.0, 200.0))
        transformer = MockTransformer()
        assert obj.get_pixel_position(transformer) == (100.0, 200.0)

    def test_with_geo_and_transformer(self):
        """Test with geo coords and transformer computes pixel coords."""
        obj = RoadObject(
            position=(0.0, 0.0),
            geo_position=(12.0, 57.0)
        )
        transformer = MockTransformer()
        result = obj.get_pixel_position(transformer)
        assert result == (12000.0, 57000.0)


class TestRoadObjectGetPixelPoints:
    """Test RoadObject.get_pixel_points() method."""

    def test_no_transformer_returns_stored_points(self):
        """Test without transformer returns stored points."""
        obj = RoadObject(object_type=ObjectType.GUARDRAIL)
        obj.points = [(0, 0), (10, 0), (20, 0)]
        assert obj.get_pixel_points() == [(0, 0), (10, 0), (20, 0)]

    def test_no_geo_points_returns_stored_points(self):
        """Test without geo points returns stored points."""
        obj = RoadObject(object_type=ObjectType.GUARDRAIL)
        obj.points = [(0, 0), (10, 0)]
        transformer = MockTransformer()
        assert obj.get_pixel_points(transformer) == [(0, 0), (10, 0)]

    def test_with_geo_points_and_transformer(self):
        """Test with geo points and transformer computes pixel coords."""
        obj = RoadObject(object_type=ObjectType.GUARDRAIL)
        obj.points = [(0, 0), (10, 0)]
        obj.geo_points = [(12.0, 57.0), (12.001, 57.001)]
        transformer = MockTransformer()
        result = obj.get_pixel_points(transformer)
        assert len(result) == 2
        assert result[0] == (12000.0, 57000.0)
        assert result[1] == pytest.approx((12001.0, 57001.0), rel=1e-6)


class TestRoadObjectUpdatePixelCoordsFromGeo:
    """Test RoadObject.update_pixel_coords_from_geo() method."""

    def test_update_position_from_geo(self):
        """Test updating position from geo coords."""
        obj = RoadObject(
            position=(0.0, 0.0),
            geo_position=(12.0, 57.0)
        )
        transformer = MockTransformer()
        obj.update_pixel_coords_from_geo(transformer)
        assert obj.position == (12000.0, 57000.0)

    def test_update_points_from_geo_points(self):
        """Test updating points from geo points."""
        obj = RoadObject(object_type=ObjectType.GUARDRAIL)
        obj.points = [(0, 0)]
        obj.geo_points = [(12.0, 57.0), (12.001, 57.001)]
        transformer = MockTransformer()
        obj.update_pixel_coords_from_geo(transformer)
        assert len(obj.points) == 2
        assert obj.points[0] == (12000.0, 57000.0)

    def test_no_geo_coords_no_change(self):
        """Test without geo coords position unchanged."""
        obj = RoadObject(position=(100.0, 200.0))
        transformer = MockTransformer()
        obj.update_pixel_coords_from_geo(transformer)
        assert obj.position == (100.0, 200.0)


# ============================================================================
# Test RoadObject Serialization
# ============================================================================

class TestRoadObjectSerialization:
    """Test RoadObject to_dict() and from_dict() methods."""

    def test_basic_serialization(self):
        """Test basic object serialization."""
        obj = RoadObject(
            object_id="test-123",
            position=(100.0, 200.0),
            object_type=ObjectType.LAMPPOST
        )
        obj.name = "Test Lamp"
        obj.orientation = 45.0

        data = obj.to_dict()

        assert data['id'] == "test-123"
        assert data['position'] == [100.0, 200.0]
        assert data['type'] == "lamppost"
        assert data['name'] == "Test Lamp"
        assert data['orientation'] == 45.0

    def test_serialization_with_points(self):
        """Test guardrail serialization with points."""
        obj = RoadObject(
            object_type=ObjectType.GUARDRAIL
        )
        obj.points = [(0, 0), (10, 5), (20, 0)]

        data = obj.to_dict()

        assert data['points'] == [[0, 0], [10, 5], [20, 0]]

    def test_serialization_with_geo_position(self):
        """Test serialization includes geo_position."""
        obj = RoadObject(geo_position=(12.345, 57.789))

        data = obj.to_dict()

        assert data['geo_position'] == [12.345, 57.789]

    def test_serialization_with_geo_points(self):
        """Test serialization includes geo_points."""
        obj = RoadObject(object_type=ObjectType.GUARDRAIL)
        obj.geo_points = [(12.0, 57.0), (12.001, 57.001)]

        data = obj.to_dict()

        assert data['geo_points'] == [[12.0, 57.0], [12.001, 57.001]]

    def test_serialization_with_pitch_roll(self):
        """Test serialization includes pitch/roll when non-zero."""
        obj = RoadObject()
        obj.pitch = 0.1
        obj.roll = 0.2

        data = obj.to_dict()

        assert data['pitch'] == 0.1
        assert data['roll'] == 0.2

    def test_serialization_omits_default_pitch_roll(self):
        """Test serialization omits pitch/roll when zero."""
        obj = RoadObject()

        data = obj.to_dict()

        assert 'pitch' not in data
        assert 'roll' not in data

    def test_serialization_includes_road_association(self):
        """Test serialization includes road association data."""
        obj = RoadObject(road_id="road-1")
        obj.s_position = 50.0
        obj.t_offset = 5.0
        obj.validity_length = 20.0

        data = obj.to_dict()

        assert data['road_id'] == "road-1"
        assert data['s_position'] == 50.0
        assert data['t_offset'] == 5.0
        assert data['validity_length'] == 20.0


class TestRoadObjectDeserialization:
    """Test RoadObject.from_dict() method."""

    def test_basic_deserialization(self):
        """Test basic object deserialization."""
        data = {
            'id': 'test-123',
            'position': [100.0, 200.0],
            'type': 'lamppost',
            'name': 'Test Lamp',
            'orientation': 45.0
        }

        obj = RoadObject.from_dict(data)

        assert obj.id == "test-123"
        assert obj.position == (100.0, 200.0)
        assert obj.type == ObjectType.LAMPPOST
        assert obj.name == "Test Lamp"
        assert obj.orientation == 45.0

    def test_deserialization_with_points(self):
        """Test deserialization with points list."""
        data = {
            'id': 'guard-1',
            'type': 'guardrail',
            'points': [[0, 0], [10, 5], [20, 0]]
        }

        obj = RoadObject.from_dict(data)

        assert obj.points == [(0, 0), (10, 5), (20, 0)]

    def test_deserialization_with_geo_position(self):
        """Test deserialization includes geo_position."""
        data = {
            'id': 'test-1',
            'type': 'lamppost',
            'geo_position': [12.345, 57.789]
        }

        obj = RoadObject.from_dict(data)

        assert obj.geo_position == (12.345, 57.789)

    def test_deserialization_with_geo_points(self):
        """Test deserialization includes geo_points."""
        data = {
            'id': 'guard-1',
            'type': 'guardrail',
            'geo_points': [[12.0, 57.0], [12.001, 57.001]]
        }

        obj = RoadObject.from_dict(data)

        assert obj.geo_points == [(12.0, 57.0), (12.001, 57.001)]

    def test_deserialization_with_opendrive_data(self):
        """Test deserialization includes OpenDRIVE fields."""
        data = {
            'id': 'test-1',
            'type': 'building',
            'pitch': 0.1,
            'roll': 0.2
        }

        obj = RoadObject.from_dict(data)

        assert obj.pitch == 0.1
        assert obj.roll == 0.2

    def test_deserialization_uses_default_dimensions(self):
        """Test deserialization fills missing dimensions with defaults."""
        data = {
            'id': 'test-1',
            'type': 'lamppost',
            'dimensions': {'height': 8.0}  # Only partial dims
        }

        obj = RoadObject.from_dict(data)

        # Height from data
        assert obj.dimensions['height'] == 8.0
        # Radius from default
        assert obj.dimensions['radius'] == 0.15

    def test_deserialization_missing_position(self):
        """Test deserialization with missing position uses default."""
        data = {
            'id': 'test-1',
            'type': 'building'
        }

        obj = RoadObject.from_dict(data)

        assert obj.position == (0.0, 0.0)


class TestRoadObjectRoundTrip:
    """Test serialization round-trip."""

    def test_full_round_trip(self):
        """Test complete round-trip serialization."""
        original = RoadObject(
            object_id="round-trip-test",
            position=(150.0, 250.0),
            object_type=ObjectType.TREE_CONIFER,
            road_id="road-5",
            geo_position=(12.5, 57.5)
        )
        original.name = "Big Pine"
        original.orientation = 0.0
        original.z_offset = 0.5
        original.s_position = 100.0
        original.t_offset = -3.0
        original.pitch = 0.05
        original.roll = -0.02

        # Round trip
        data = original.to_dict()
        restored = RoadObject.from_dict(data)

        assert restored.id == original.id
        assert restored.position == original.position
        assert restored.type == original.type
        assert restored.name == original.name
        assert restored.geo_position == original.geo_position
        assert restored.road_id == original.road_id
        assert restored.s_position == original.s_position
        assert restored.t_offset == original.t_offset
        assert restored.pitch == original.pitch
        assert restored.roll == original.roll

    def test_guardrail_round_trip(self):
        """Test guardrail with points round-trip."""
        original = RoadObject(
            object_id="guardrail-test",
            object_type=ObjectType.GUARDRAIL
        )
        original.points = [(0, 0), (50, 0), (100, 10)]
        original.geo_points = [(12.0, 57.0), (12.0005, 57.0), (12.001, 57.0001)]
        original.validity_length = 105.0

        data = original.to_dict()
        restored = RoadObject.from_dict(data)

        assert restored.points == original.points
        assert restored.geo_points == original.geo_points
        assert restored.validity_length == original.validity_length


# ============================================================================
# Test RoadObject Display Name
# ============================================================================

class TestRoadObjectGetDisplayName:
    """Test RoadObject.get_display_name() method."""

    def test_custom_name(self):
        """Test display name uses custom name when set."""
        obj = RoadObject(object_type=ObjectType.LAMPPOST)
        obj.name = "Street Light #42"
        assert obj.get_display_name() == "Street Light #42"

    def test_default_name_lamppost(self):
        """Test display name uses formatted type when no name."""
        obj = RoadObject(object_type=ObjectType.LAMPPOST)
        assert obj.get_display_name() == "Lamppost"

    def test_default_name_tree_broadleaf(self):
        """Test display name for broadleaf tree."""
        obj = RoadObject(object_type=ObjectType.TREE_BROADLEAF)
        assert obj.get_display_name() == "Tree Broadleaf"

    def test_default_name_parking_multi_storey(self):
        """Test display name for multi-storey parking."""
        obj = RoadObject(object_type=ObjectType.PARKING_MULTI_STOREY)
        assert obj.get_display_name() == "Parking Multi Storey"

    def test_empty_name_uses_type(self):
        """Test empty name falls back to type."""
        obj = RoadObject(object_type=ObjectType.BUSH)
        obj.name = ""
        assert obj.get_display_name() == "Bush"


# ============================================================================
# Test RoadObject S/T Position Calculation
# ============================================================================

class TestRoadObjectCalculateSTPosition:
    """Test RoadObject.calculate_s_t_position() method."""

    def test_no_centerline(self):
        """Test with no centerline points."""
        obj = RoadObject(position=(50.0, 50.0))
        s, t = obj.calculate_s_t_position([])
        assert s is None
        assert t is None

    def test_single_point_centerline(self):
        """Test with only one centerline point."""
        obj = RoadObject(position=(50.0, 50.0))
        s, t = obj.calculate_s_t_position([(0.0, 0.0)])
        assert s is None
        assert t is None

    def test_object_on_centerline(self):
        """Test object positioned on the centerline."""
        obj = RoadObject(position=(50.0, 0.0))
        centerline = [(0.0, 0.0), (100.0, 0.0)]

        s, t = obj.calculate_s_t_position(centerline)

        assert s == pytest.approx(50.0, abs=0.01)
        assert t == pytest.approx(0.0, abs=0.01)

    def test_object_left_of_centerline(self):
        """Test object to the left of centerline (positive t)."""
        # Centerline goes from left to right
        obj = RoadObject(position=(50.0, -10.0))  # Above in screen coords = left of road
        centerline = [(0.0, 0.0), (100.0, 0.0)]

        s, t = obj.calculate_s_t_position(centerline)

        assert s == pytest.approx(50.0, abs=0.01)
        # t-offset should be positive (left side)
        assert t > 0

    def test_object_right_of_centerline(self):
        """Test object to the right of centerline (negative t)."""
        # Centerline goes from left to right
        obj = RoadObject(position=(50.0, 10.0))  # Below in screen coords = right of road
        centerline = [(0.0, 0.0), (100.0, 0.0)]

        s, t = obj.calculate_s_t_position(centerline)

        assert s == pytest.approx(50.0, abs=0.01)
        # t-offset should be negative (right side)
        assert t < 0

    def test_object_at_start(self):
        """Test object at start of centerline."""
        obj = RoadObject(position=(0.0, 5.0))
        centerline = [(0.0, 0.0), (100.0, 0.0)]

        s, t = obj.calculate_s_t_position(centerline)

        assert s == pytest.approx(0.0, abs=0.01)
        assert abs(t) == pytest.approx(5.0, abs=0.01)

    def test_object_at_end(self):
        """Test object at end of centerline."""
        obj = RoadObject(position=(100.0, 5.0))
        centerline = [(0.0, 0.0), (100.0, 0.0)]

        s, t = obj.calculate_s_t_position(centerline)

        assert s == pytest.approx(100.0, abs=0.01)
        assert abs(t) == pytest.approx(5.0, abs=0.01)

    def test_multi_segment_centerline(self):
        """Test with multi-segment centerline."""
        obj = RoadObject(position=(150.0, 50.0))
        # L-shaped centerline: 100px right, then 100px down
        centerline = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0)]

        s, t = obj.calculate_s_t_position(centerline)

        # Should be on second segment, 50 units along it
        # Total s = 100 (first segment) + 50 (second segment)
        assert s == pytest.approx(150.0, abs=0.01)

    def test_guardrail_uses_first_point(self):
        """Test guardrail uses first point for calculation."""
        obj = RoadObject(object_type=ObjectType.GUARDRAIL)
        obj.points = [(50.0, 5.0), (75.0, 5.0), (100.0, 5.0)]
        centerline = [(0.0, 0.0), (100.0, 0.0)]

        s, t = obj.calculate_s_t_position(centerline)

        # Should use first point (50, 5)
        assert s == pytest.approx(50.0, abs=0.01)
        assert abs(t) == pytest.approx(5.0, abs=0.01)

    def test_zero_length_segment(self):
        """Test with zero-length segment in centerline."""
        obj = RoadObject(position=(50.0, 0.0))
        # Include a zero-length segment
        centerline = [(0.0, 0.0), (0.0, 0.0), (100.0, 0.0)]

        s, t = obj.calculate_s_t_position(centerline)

        # Should still work, skipping zero-length segment
        assert s is not None
        assert t is not None

    def test_diagonal_centerline(self):
        """Test with diagonal centerline."""
        obj = RoadObject(position=(50.0, 50.0))
        # 45-degree diagonal, length = sqrt(2) * 100
        centerline = [(0.0, 0.0), (100.0, 100.0)]

        s, t = obj.calculate_s_t_position(centerline)

        # Object is on the centerline
        assert t == pytest.approx(0.0, abs=0.1)

    def test_object_beyond_centerline_start(self):
        """Test object before centerline start."""
        obj = RoadObject(position=(-10.0, 0.0))
        centerline = [(0.0, 0.0), (100.0, 0.0)]

        s, t = obj.calculate_s_t_position(centerline)

        # Should project to start of centerline
        assert s == pytest.approx(0.0, abs=0.01)

    def test_object_beyond_centerline_end(self):
        """Test object after centerline end."""
        obj = RoadObject(position=(110.0, 0.0))
        centerline = [(0.0, 0.0), (100.0, 0.0)]

        s, t = obj.calculate_s_t_position(centerline)

        # Should project to end of centerline
        assert s == pytest.approx(100.0, abs=0.01)


# ============================================================================
# Test ObjectType Enum Values
# ============================================================================

class TestObjectTypeValues:
    """Test ObjectType enum string values."""

    def test_all_types_have_string_values(self):
        """Test all types have string values for serialization."""
        for obj_type in ObjectType:
            assert isinstance(obj_type.value, str)
            assert len(obj_type.value) > 0

    def test_values_are_lowercase(self):
        """Test all values are lowercase (consistent format)."""
        for obj_type in ObjectType:
            assert obj_type.value == obj_type.value.lower()

    def test_from_value(self):
        """Test creating enum from value string."""
        assert ObjectType("lamppost") == ObjectType.LAMPPOST
        assert ObjectType("building") == ObjectType.BUILDING
        assert ObjectType("guardrail") == ObjectType.GUARDRAIL

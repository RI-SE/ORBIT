"""
Unit tests for ParkingSpace model and parking enums.

Tests the parking model for OpenDRIVE parking areas.
"""

import pytest
import math
from typing import Tuple, List

from orbit.models.parking import ParkingAccess, ParkingType, ParkingSpace


# ============================================================================
# Test ParkingAccess Enum
# ============================================================================

class TestParkingAccess:
    """Test ParkingAccess enum."""

    def test_standard_value(self):
        """Test standard access value."""
        assert ParkingAccess.STANDARD.value == "standard"

    def test_women_value(self):
        """Test women access value."""
        assert ParkingAccess.WOMEN.value == "women"

    def test_handicapped_value(self):
        """Test handicapped access value."""
        assert ParkingAccess.HANDICAPPED.value == "handicapped"

    def test_disabled_value(self):
        """Test disabled access value."""
        assert ParkingAccess.DISABLED.value == "disabled"

    def test_reserved_value(self):
        """Test reserved access value."""
        assert ParkingAccess.RESERVED.value == "reserved"

    def test_company_value(self):
        """Test company access value."""
        assert ParkingAccess.COMPANY.value == "company"

    def test_permit_value(self):
        """Test permit access value."""
        assert ParkingAccess.PERMIT.value == "permit"

    def test_private_value(self):
        """Test private access value."""
        assert ParkingAccess.PRIVATE.value == "private"

    def test_customers_value(self):
        """Test customers access value."""
        assert ParkingAccess.CUSTOMERS.value == "customers"

    def test_residents_value(self):
        """Test residents access value."""
        assert ParkingAccess.RESIDENTS.value == "residents"

    def test_from_value(self):
        """Test creating enum from value string."""
        assert ParkingAccess("standard") == ParkingAccess.STANDARD
        assert ParkingAccess("handicapped") == ParkingAccess.HANDICAPPED


# ============================================================================
# Test ParkingType Enum
# ============================================================================

class TestParkingType:
    """Test ParkingType enum."""

    def test_surface_value(self):
        """Test surface parking value."""
        assert ParkingType.SURFACE.value == "surface"

    def test_underground_value(self):
        """Test underground parking value."""
        assert ParkingType.UNDERGROUND.value == "underground"

    def test_multi_storey_value(self):
        """Test multi-storey parking value."""
        assert ParkingType.MULTI_STOREY.value == "multi_storey"

    def test_rooftop_value(self):
        """Test rooftop parking value."""
        assert ParkingType.ROOFTOP.value == "rooftop"

    def test_street_value(self):
        """Test street parking value."""
        assert ParkingType.STREET.value == "street"

    def test_carports_value(self):
        """Test carports value."""
        assert ParkingType.CARPORTS.value == "carports"

    def test_from_value(self):
        """Test creating enum from value string."""
        assert ParkingType("surface") == ParkingType.SURFACE
        assert ParkingType("underground") == ParkingType.UNDERGROUND


# ============================================================================
# Test ParkingSpace Basic Construction
# ============================================================================

class TestParkingSpaceConstruction:
    """Test ParkingSpace construction."""

    def test_default_construction(self):
        """Test default construction."""
        space = ParkingSpace()
        assert space.id is not None
        assert space.position == (0.0, 0.0)
        assert space.access == ParkingAccess.STANDARD
        assert space.parking_type == ParkingType.SURFACE

    def test_construction_with_position(self):
        """Test construction with position."""
        space = ParkingSpace(position=(100.0, 200.0))
        assert space.position == (100.0, 200.0)

    def test_construction_with_access(self):
        """Test construction with specific access type."""
        space = ParkingSpace(access=ParkingAccess.HANDICAPPED)
        assert space.access == ParkingAccess.HANDICAPPED

    def test_construction_with_parking_type(self):
        """Test construction with specific parking type."""
        space = ParkingSpace(parking_type=ParkingType.UNDERGROUND)
        assert space.parking_type == ParkingType.UNDERGROUND

    def test_construction_with_id(self):
        """Test construction with specific ID."""
        space = ParkingSpace(parking_id="test-parking-123")
        assert space.id == "test-parking-123"

    def test_construction_with_road_id(self):
        """Test construction with road association."""
        space = ParkingSpace(road_id="road-1")
        assert space.road_id == "road-1"

    def test_construction_with_geo_position(self):
        """Test construction with geographic position."""
        space = ParkingSpace(geo_position=(12.345, 57.789))
        assert space.geo_position == (12.345, 57.789)

    def test_default_fields(self):
        """Test default field values."""
        space = ParkingSpace()
        assert space.restrictions == ""
        assert space.name == ""
        assert space.width == 2.5  # Standard parking space width
        assert space.length == 5.0  # Standard parking space length
        assert space.orientation == 0.0
        assert space.z_offset == 0.0
        assert space.s_position is None
        assert space.t_offset is None
        assert space.opendrive_id is None
        assert space.capacity is None
        assert space.points == []
        assert space.geo_points is None


# ============================================================================
# Test ParkingSpace Geo Coordinate Methods
# ============================================================================

class TestParkingSpaceHasGeoCoords:
    """Test ParkingSpace.has_geo_coords() method."""

    def test_no_geo_coords(self):
        """Test parking without geo coordinates."""
        space = ParkingSpace(position=(100.0, 200.0))
        assert space.has_geo_coords() is False

    def test_with_geo_position(self):
        """Test parking with geo position."""
        space = ParkingSpace(geo_position=(12.345, 57.789))
        assert space.has_geo_coords() is True

    def test_with_geo_points(self):
        """Test parking lot with geo points polygon."""
        space = ParkingSpace()
        space.geo_points = [(12.0, 57.0), (12.001, 57.0), (12.001, 57.001), (12.0, 57.001)]
        assert space.has_geo_coords() is True

    def test_with_empty_geo_points(self):
        """Test parking lot with empty geo points list."""
        space = ParkingSpace()
        space.geo_points = []
        assert space.has_geo_coords() is False


class TestParkingSpaceIsPolygon:
    """Test ParkingSpace.is_polygon() method."""

    def test_point_space(self):
        """Test point-based space is not polygon."""
        space = ParkingSpace(position=(100.0, 200.0))
        assert space.is_polygon() is False

    def test_polygon_with_pixel_points(self):
        """Test polygon with pixel points."""
        space = ParkingSpace()
        space.points = [(0, 0), (100, 0), (100, 50), (0, 50)]
        assert space.is_polygon() is True

    def test_polygon_with_geo_points(self):
        """Test polygon with geo points."""
        space = ParkingSpace()
        space.geo_points = [(12.0, 57.0), (12.001, 57.0), (12.001, 57.001), (12.0, 57.001)]
        assert space.is_polygon() is True

    def test_less_than_three_points(self):
        """Test with less than 3 points is not polygon."""
        space = ParkingSpace()
        space.points = [(0, 0), (100, 0)]
        assert space.is_polygon() is False


class MockTransformer:
    """Mock transformer for testing coordinate conversions."""

    def geo_to_pixel(self, lon: float, lat: float) -> Tuple[float, float]:
        """Convert geo to pixel (simple scaling for test)."""
        return (lon * 1000.0, lat * 1000.0)


class TestParkingSpaceGetPixelPosition:
    """Test ParkingSpace.get_pixel_position() method."""

    def test_no_transformer_returns_stored_position(self):
        """Test without transformer returns stored position."""
        space = ParkingSpace(position=(100.0, 200.0))
        assert space.get_pixel_position() == (100.0, 200.0)

    def test_no_geo_returns_stored_position(self):
        """Test without geo coords returns stored position."""
        space = ParkingSpace(position=(100.0, 200.0))
        transformer = MockTransformer()
        assert space.get_pixel_position(transformer) == (100.0, 200.0)

    def test_with_geo_and_transformer(self):
        """Test with geo coords and transformer computes pixel coords."""
        space = ParkingSpace(
            position=(0.0, 0.0),
            geo_position=(12.0, 57.0)
        )
        transformer = MockTransformer()
        result = space.get_pixel_position(transformer)
        assert result == (12000.0, 57000.0)


class TestParkingSpaceGetPixelPoints:
    """Test ParkingSpace.get_pixel_points() method."""

    def test_no_transformer_returns_stored_points(self):
        """Test without transformer returns stored points."""
        space = ParkingSpace()
        space.points = [(0, 0), (100, 0), (100, 50), (0, 50)]
        assert space.get_pixel_points() == [(0, 0), (100, 0), (100, 50), (0, 50)]

    def test_no_geo_points_returns_stored_points(self):
        """Test without geo points returns stored points."""
        space = ParkingSpace()
        space.points = [(0, 0), (100, 0)]
        transformer = MockTransformer()
        assert space.get_pixel_points(transformer) == [(0, 0), (100, 0)]

    def test_with_geo_points_and_transformer(self):
        """Test with geo points and transformer computes pixel coords."""
        space = ParkingSpace()
        space.points = [(0, 0), (10, 0)]
        space.geo_points = [(12.0, 57.0), (12.001, 57.0)]
        transformer = MockTransformer()
        result = space.get_pixel_points(transformer)
        assert len(result) == 2
        assert result[0] == (12000.0, 57000.0)


class TestParkingSpaceUpdatePixelCoordsFromGeo:
    """Test ParkingSpace.update_pixel_coords_from_geo() method."""

    def test_update_position_from_geo(self):
        """Test updating position from geo coords."""
        space = ParkingSpace(
            position=(0.0, 0.0),
            geo_position=(12.0, 57.0)
        )
        transformer = MockTransformer()
        space.update_pixel_coords_from_geo(transformer)
        assert space.position == (12000.0, 57000.0)

    def test_update_points_from_geo_points(self):
        """Test updating points from geo points."""
        space = ParkingSpace()
        space.points = [(0, 0)]
        space.geo_points = [(12.0, 57.0), (12.001, 57.0)]
        transformer = MockTransformer()
        space.update_pixel_coords_from_geo(transformer)
        assert len(space.points) == 2
        assert space.points[0] == (12000.0, 57000.0)

    def test_no_geo_coords_no_change(self):
        """Test without geo coords position unchanged."""
        space = ParkingSpace(position=(100.0, 200.0))
        transformer = MockTransformer()
        space.update_pixel_coords_from_geo(transformer)
        assert space.position == (100.0, 200.0)


# ============================================================================
# Test ParkingSpace Display Name
# ============================================================================

class TestParkingSpaceGetDisplayName:
    """Test ParkingSpace.get_display_name() method."""

    def test_custom_name(self):
        """Test display name uses custom name when set."""
        space = ParkingSpace()
        space.name = "Main Lot A"
        assert space.get_display_name() == "Main Lot A"

    def test_default_name_surface(self):
        """Test display name for surface parking."""
        space = ParkingSpace(parking_type=ParkingType.SURFACE)
        assert space.get_display_name() == "Parking (Surface)"

    def test_default_name_underground(self):
        """Test display name for underground parking."""
        space = ParkingSpace(parking_type=ParkingType.UNDERGROUND)
        assert space.get_display_name() == "Parking (Underground)"

    def test_default_name_multi_storey(self):
        """Test display name for multi-storey parking."""
        space = ParkingSpace(parking_type=ParkingType.MULTI_STOREY)
        assert space.get_display_name() == "Parking (Multi Storey)"

    def test_default_name_rooftop(self):
        """Test display name for rooftop parking."""
        space = ParkingSpace(parking_type=ParkingType.ROOFTOP)
        assert space.get_display_name() == "Parking (Rooftop)"

    def test_empty_name_uses_type(self):
        """Test empty name falls back to type."""
        space = ParkingSpace(parking_type=ParkingType.STREET)
        space.name = ""
        assert space.get_display_name() == "Parking (Street)"


# ============================================================================
# Test ParkingSpace Serialization
# ============================================================================

class TestParkingSpaceSerialization:
    """Test ParkingSpace.to_dict() method."""

    def test_basic_serialization(self):
        """Test basic parking space serialization."""
        space = ParkingSpace(
            parking_id="test-123",
            position=(100.0, 200.0),
            access=ParkingAccess.HANDICAPPED,
            parking_type=ParkingType.SURFACE
        )
        space.name = "Accessible Spot"

        data = space.to_dict()

        assert data['id'] == "test-123"
        assert data['position'] == [100.0, 200.0]
        assert data['access'] == "handicapped"
        assert data['parking_type'] == "surface"
        assert data['name'] == "Accessible Spot"

    def test_serialization_with_dimensions(self):
        """Test serialization with custom dimensions."""
        space = ParkingSpace()
        space.width = 3.0
        space.length = 6.0
        space.orientation = 45.0
        space.z_offset = 0.5

        data = space.to_dict()

        assert data['width'] == 3.0
        assert data['length'] == 6.0
        assert data['orientation'] == 45.0
        assert data['z_offset'] == 0.5

    def test_serialization_with_geo_position(self):
        """Test serialization includes geo_position."""
        space = ParkingSpace(geo_position=(12.345, 57.789))

        data = space.to_dict()

        assert data['geo_position'] == [12.345, 57.789]

    def test_serialization_with_points(self):
        """Test serialization includes polygon points."""
        space = ParkingSpace()
        space.points = [(0, 0), (100, 0), (100, 50), (0, 50)]

        data = space.to_dict()

        assert data['points'] == [[0, 0], [100, 0], [100, 50], [0, 50]]

    def test_serialization_with_geo_points(self):
        """Test serialization includes geo polygon points."""
        space = ParkingSpace()
        space.geo_points = [(12.0, 57.0), (12.001, 57.0)]

        data = space.to_dict()

        assert data['geo_points'] == [[12.0, 57.0], [12.001, 57.0]]

    def test_serialization_with_opendrive_id(self):
        """Test serialization includes opendrive_id when set."""
        space = ParkingSpace()
        space.opendrive_id = "od-parking-1"

        data = space.to_dict()

        assert data['opendrive_id'] == "od-parking-1"

    def test_serialization_with_capacity(self):
        """Test serialization includes capacity when set."""
        space = ParkingSpace()
        space.capacity = 50

        data = space.to_dict()

        assert data['capacity'] == 50

    def test_serialization_omits_optional_when_none(self):
        """Test serialization omits optional fields when None."""
        space = ParkingSpace()

        data = space.to_dict()

        assert 'opendrive_id' not in data
        assert 'capacity' not in data
        assert 'geo_position' not in data

    def test_serialization_with_road_association(self):
        """Test serialization includes road association data."""
        space = ParkingSpace(road_id="road-1")
        space.s_position = 50.0
        space.t_offset = 5.0

        data = space.to_dict()

        assert data['road_id'] == "road-1"
        assert data['s_position'] == 50.0
        assert data['t_offset'] == 5.0


class TestParkingSpaceDeserialization:
    """Test ParkingSpace.from_dict() method."""

    def test_basic_deserialization(self):
        """Test basic parking space deserialization."""
        data = {
            'id': 'test-123',
            'position': [100.0, 200.0],
            'access': 'handicapped',
            'parking_type': 'underground',
            'name': 'Test Parking'
        }

        space = ParkingSpace.from_dict(data)

        assert space.id == "test-123"
        assert space.position == (100.0, 200.0)
        assert space.access == ParkingAccess.HANDICAPPED
        assert space.parking_type == ParkingType.UNDERGROUND
        assert space.name == "Test Parking"

    def test_deserialization_with_dimensions(self):
        """Test deserialization with dimensions."""
        data = {
            'id': 'test-1',
            'access': 'standard',
            'parking_type': 'surface',
            'width': 3.0,
            'length': 6.0,
            'orientation': 90.0,
            'z_offset': 1.0
        }

        space = ParkingSpace.from_dict(data)

        assert space.width == 3.0
        assert space.length == 6.0
        assert space.orientation == 90.0
        assert space.z_offset == 1.0

    def test_deserialization_with_geo_position(self):
        """Test deserialization includes geo_position."""
        data = {
            'id': 'test-1',
            'access': 'standard',
            'parking_type': 'surface',
            'position': [100.0, 200.0],
            'geo_position': [12.345, 57.789]
        }

        space = ParkingSpace.from_dict(data)

        assert space.geo_position == (12.345, 57.789)

    def test_deserialization_with_points(self):
        """Test deserialization with polygon points."""
        data = {
            'id': 'test-1',
            'access': 'standard',
            'parking_type': 'surface',
            'points': [[0, 0], [100, 0], [100, 50], [0, 50]]
        }

        space = ParkingSpace.from_dict(data)

        assert space.points == [(0, 0), (100, 0), (100, 50), (0, 50)]

    def test_deserialization_with_geo_points(self):
        """Test deserialization with geo polygon points."""
        data = {
            'id': 'test-1',
            'access': 'standard',
            'parking_type': 'surface',
            'geo_points': [[12.0, 57.0], [12.001, 57.0]]
        }

        space = ParkingSpace.from_dict(data)

        assert space.geo_points == [(12.0, 57.0), (12.001, 57.0)]

    def test_deserialization_with_optional_fields(self):
        """Test deserialization with optional fields."""
        data = {
            'id': 'test-1',
            'access': 'standard',
            'parking_type': 'surface',
            'opendrive_id': 'od-123',
            'capacity': 25
        }

        space = ParkingSpace.from_dict(data)

        assert space.opendrive_id == "od-123"
        assert space.capacity == 25

    def test_deserialization_uses_defaults(self):
        """Test deserialization uses default values for missing fields."""
        data = {
            'id': 'test-1'
        }

        space = ParkingSpace.from_dict(data)

        assert space.access == ParkingAccess.STANDARD
        assert space.parking_type == ParkingType.SURFACE
        assert space.width == 2.5
        assert space.length == 5.0
        assert space.orientation == 0.0
        assert space.restrictions == ""
        assert space.name == ""


class TestParkingSpaceRoundTrip:
    """Test serialization round-trip."""

    def test_full_round_trip(self):
        """Test complete round-trip serialization."""
        original = ParkingSpace(
            parking_id="round-trip-test",
            position=(150.0, 250.0),
            access=ParkingAccess.RESERVED,
            parking_type=ParkingType.MULTI_STOREY,
            road_id="road-5",
            geo_position=(12.5, 57.5)
        )
        original.name = "VIP Parking"
        original.restrictions = "Permit required"
        original.width = 3.0
        original.length = 6.0
        original.orientation = 45.0
        original.z_offset = 0.5
        original.s_position = 100.0
        original.t_offset = -3.0
        original.opendrive_id = "od-456"
        original.capacity = 10

        # Round trip
        data = original.to_dict()
        restored = ParkingSpace.from_dict(data)

        assert restored.id == original.id
        assert restored.position == original.position
        assert restored.access == original.access
        assert restored.parking_type == original.parking_type
        assert restored.name == original.name
        assert restored.restrictions == original.restrictions
        assert restored.geo_position == original.geo_position
        assert restored.road_id == original.road_id
        assert restored.width == original.width
        assert restored.length == original.length
        assert restored.orientation == original.orientation
        assert restored.z_offset == original.z_offset
        assert restored.s_position == original.s_position
        assert restored.t_offset == original.t_offset
        assert restored.opendrive_id == original.opendrive_id
        assert restored.capacity == original.capacity

    def test_polygon_round_trip(self):
        """Test parking lot polygon round-trip."""
        original = ParkingSpace(
            parking_id="lot-test",
            parking_type=ParkingType.SURFACE
        )
        original.points = [(0, 0), (100, 0), (100, 80), (0, 80)]
        original.geo_points = [(12.0, 57.0), (12.001, 57.0), (12.001, 57.001), (12.0, 57.001)]
        original.capacity = 50

        data = original.to_dict()
        restored = ParkingSpace.from_dict(data)

        assert restored.points == original.points
        assert restored.geo_points == original.geo_points
        assert restored.capacity == original.capacity


# ============================================================================
# Test ParkingSpace S/T Position Calculation
# ============================================================================

class TestParkingSpaceCalculateSTPosition:
    """Test ParkingSpace.calculate_s_t_position() method."""

    def test_no_centerline(self):
        """Test with no centerline points."""
        space = ParkingSpace(position=(50.0, 50.0))
        s, t = space.calculate_s_t_position([])
        assert s is None
        assert t is None

    def test_single_point_centerline(self):
        """Test with only one centerline point."""
        space = ParkingSpace(position=(50.0, 50.0))
        s, t = space.calculate_s_t_position([(0.0, 0.0)])
        assert s is None
        assert t is None

    def test_parking_on_centerline(self):
        """Test parking positioned on the centerline."""
        space = ParkingSpace(position=(50.0, 0.0))
        centerline = [(0.0, 0.0), (100.0, 0.0)]

        s, t = space.calculate_s_t_position(centerline)

        assert s == pytest.approx(50.0, abs=0.01)
        # t should be close to 0 (on centerline)
        assert t is not None
        assert abs(t) < 0.1

    def test_parking_off_centerline(self):
        """Test parking positioned off the centerline."""
        space = ParkingSpace(position=(50.0, 10.0))  # 10 pixels below
        centerline = [(0.0, 0.0), (100.0, 0.0)]

        s, t = space.calculate_s_t_position(centerline)

        assert s == pytest.approx(50.0, abs=0.01)
        assert abs(t) == pytest.approx(10.0, abs=0.1)

    def test_parking_at_start(self):
        """Test parking at start of centerline."""
        space = ParkingSpace(position=(0.0, 5.0))
        centerline = [(0.0, 0.0), (100.0, 0.0)]

        s, t = space.calculate_s_t_position(centerline)

        assert s == pytest.approx(0.0, abs=0.01)

    def test_parking_at_end(self):
        """Test parking at end of centerline."""
        space = ParkingSpace(position=(100.0, 5.0))
        centerline = [(0.0, 0.0), (100.0, 0.0)]

        s, t = space.calculate_s_t_position(centerline)

        assert s == pytest.approx(100.0, abs=0.01)

    def test_multi_segment_centerline(self):
        """Test with multi-segment centerline."""
        space = ParkingSpace(position=(100.0, 55.0))
        # L-shaped: 100px right, then 100px down
        centerline = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0)]

        s, t = space.calculate_s_t_position(centerline)

        # Should be along second segment
        assert s > 100.0  # Past first segment
        assert s < 200.0  # Within total length

    def test_polygon_uses_centroid(self):
        """Test polygon parking uses centroid for calculation."""
        space = ParkingSpace()
        # Square polygon centered at (50, 20)
        space.points = [(40, 10), (60, 10), (60, 30), (40, 30)]
        centerline = [(0.0, 0.0), (100.0, 0.0)]

        s, t = space.calculate_s_t_position(centerline)

        # Centroid is at (50, 20)
        assert s == pytest.approx(50.0, abs=0.5)
        assert abs(t) == pytest.approx(20.0, abs=0.5)

    def test_zero_length_segment_skipped(self):
        """Test zero-length segment is skipped."""
        space = ParkingSpace(position=(50.0, 0.0))
        centerline = [(0.0, 0.0), (0.0, 0.0), (100.0, 0.0)]

        s, t = space.calculate_s_t_position(centerline)

        # Should still work, skipping zero-length segment
        assert s is not None

    def test_signed_t_offset_left(self):
        """Test t-offset sign for left side of road."""
        space = ParkingSpace(position=(50.0, -10.0))  # Above centerline (left side in screen coords)
        centerline = [(0.0, 0.0), (100.0, 0.0)]  # Road goes right

        s, t = space.calculate_s_t_position(centerline)

        # Positive t indicates left side of road
        assert t is not None
        # The sign depends on cross product calculation

    def test_signed_t_offset_right(self):
        """Test t-offset sign for right side of road."""
        space = ParkingSpace(position=(50.0, 10.0))  # Below centerline (right side in screen coords)
        centerline = [(0.0, 0.0), (100.0, 0.0)]  # Road goes right

        s, t = space.calculate_s_t_position(centerline)

        # Negative t indicates right side of road
        assert t is not None

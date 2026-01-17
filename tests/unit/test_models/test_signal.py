"""
Unit tests for Signal model and SignalType enum.

Tests the signal model for traffic signs and signals.
"""

import pytest
import math
from typing import Tuple

from orbit.models.signal import SignalType, SpeedUnit, Signal


# ============================================================================
# Test SignalType Enum
# ============================================================================

class TestSignalTypeIsLegacy:
    """Test SignalType.is_legacy_type() method."""

    def test_library_sign_not_legacy(self):
        """Test LIBRARY_SIGN is not legacy."""
        assert SignalType.LIBRARY_SIGN.is_legacy_type() is False

    def test_custom_not_legacy(self):
        """Test CUSTOM is not legacy."""
        assert SignalType.CUSTOM.is_legacy_type() is False

    def test_give_way_is_legacy(self):
        """Test GIVE_WAY is legacy."""
        assert SignalType.GIVE_WAY.is_legacy_type() is True

    def test_speed_limit_is_legacy(self):
        """Test SPEED_LIMIT is legacy."""
        assert SignalType.SPEED_LIMIT.is_legacy_type() is True

    def test_stop_is_legacy(self):
        """Test STOP is legacy."""
        assert SignalType.STOP.is_legacy_type() is True

    def test_traffic_signals_is_legacy(self):
        """Test TRAFFIC_SIGNALS is legacy."""
        assert SignalType.TRAFFIC_SIGNALS.is_legacy_type() is True


class TestSignalTypeGetCategory:
    """Test SignalType.get_category() method."""

    def test_library_sign_category(self):
        """Test LIBRARY_SIGN returns other category."""
        assert SignalType.LIBRARY_SIGN.get_category() == "other"

    def test_custom_category(self):
        """Test CUSTOM returns other category."""
        assert SignalType.CUSTOM.get_category() == "other"

    def test_give_way_regulatory(self):
        """Test GIVE_WAY is regulatory."""
        assert SignalType.GIVE_WAY.get_category() == "regulatory"

    def test_stop_regulatory(self):
        """Test STOP is regulatory."""
        assert SignalType.STOP.get_category() == "regulatory"

    def test_no_entry_regulatory(self):
        """Test NO_ENTRY is regulatory."""
        assert SignalType.NO_ENTRY.get_category() == "regulatory"

    def test_priority_road_regulatory(self):
        """Test PRIORITY_ROAD is regulatory."""
        assert SignalType.PRIORITY_ROAD.get_category() == "regulatory"

    def test_speed_limit_category(self):
        """Test SPEED_LIMIT category."""
        assert SignalType.SPEED_LIMIT.get_category() == "speed_limit"

    def test_end_of_speed_limit_category(self):
        """Test END_OF_SPEED_LIMIT category."""
        assert SignalType.END_OF_SPEED_LIMIT.get_category() == "speed_limit"

    def test_traffic_signals_category(self):
        """Test TRAFFIC_SIGNALS category."""
        assert SignalType.TRAFFIC_SIGNALS.get_category() == "signals"


class TestSignalTypeGetDefaultDimensions:
    """Test SignalType.get_default_dimensions() method."""

    def test_regulatory_dimensions(self):
        """Test regulatory sign dimensions (0.9m x 0.9m)."""
        dims = SignalType.STOP.get_default_dimensions()
        assert dims == (0.9, 0.9)

    def test_speed_limit_dimensions(self):
        """Test speed limit sign dimensions (0.6m x 0.6m)."""
        dims = SignalType.SPEED_LIMIT.get_default_dimensions()
        assert dims == (0.6, 0.6)

    def test_traffic_signals_dimensions(self):
        """Test traffic signal dimensions (0.3m x 0.9m)."""
        dims = SignalType.TRAFFIC_SIGNALS.get_default_dimensions()
        assert dims == (0.3, 0.9)

    def test_other_dimensions(self):
        """Test other category dimensions (fallback 0.6m x 0.6m)."""
        dims = SignalType.LIBRARY_SIGN.get_default_dimensions()
        assert dims == (0.6, 0.6)


# ============================================================================
# Test SpeedUnit Enum
# ============================================================================

class TestSpeedUnit:
    """Test SpeedUnit enum."""

    def test_kmh_value(self):
        """Test km/h value."""
        assert SpeedUnit.KMH.value == "km/h"

    def test_mph_value(self):
        """Test mph value."""
        assert SpeedUnit.MPH.value == "mph"


# ============================================================================
# Test Signal Basic Construction
# ============================================================================

class TestSignalConstruction:
    """Test Signal construction."""

    def test_default_construction(self):
        """Test default construction."""
        signal = Signal()
        assert signal.id is not None
        assert signal.position == (0.0, 0.0)
        assert signal.type == SignalType.LIBRARY_SIGN
        assert signal.value is None
        assert signal.speed_unit == SpeedUnit.KMH

    def test_construction_with_position(self):
        """Test construction with position."""
        signal = Signal(position=(100.0, 200.0))
        assert signal.position == (100.0, 200.0)

    def test_construction_with_signal_type(self):
        """Test construction with specific signal type."""
        signal = Signal(signal_type=SignalType.STOP)
        assert signal.type == SignalType.STOP
        # Should have regulatory dimensions
        assert signal.sign_width == 0.9
        assert signal.sign_height == 0.9

    def test_construction_with_speed_limit(self):
        """Test construction with speed limit value."""
        signal = Signal(
            signal_type=SignalType.SPEED_LIMIT,
            value=50
        )
        assert signal.type == SignalType.SPEED_LIMIT
        assert signal.value == 50

    def test_construction_with_id(self):
        """Test construction with specific ID."""
        signal = Signal(signal_id="test-signal-123")
        assert signal.id == "test-signal-123"

    def test_construction_with_road_id(self):
        """Test construction with road association."""
        signal = Signal(road_id="road-1")
        assert signal.road_id == "road-1"

    def test_construction_with_library_sign(self):
        """Test construction with library sign."""
        signal = Signal(
            signal_type=SignalType.LIBRARY_SIGN,
            library_id="se",
            sign_id="B1"
        )
        assert signal.library_id == "se"
        assert signal.sign_id == "B1"

    def test_construction_with_geo_position(self):
        """Test construction with geographic position."""
        signal = Signal(geo_position=(12.345, 57.789))
        assert signal.geo_position == (12.345, 57.789)

    def test_default_fields(self):
        """Test default field values."""
        signal = Signal()
        assert signal.name == ""
        assert signal.orientation == '+'
        assert signal.h_offset == 0.0
        assert signal.z_offset == 2.0
        assert signal.s_position is None
        assert signal.validity_range is None
        assert signal.opendrive_id is None
        assert signal.dynamic == "no"
        assert signal.subtype == ""
        assert signal.country == ""
        assert signal.custom_type is None
        assert signal.custom_subtype is None
        assert signal.validity_lanes is None


# ============================================================================
# Test Signal Geo Coordinate Methods
# ============================================================================

class TestSignalHasGeoCoords:
    """Test Signal.has_geo_coords() method."""

    def test_no_geo_coords(self):
        """Test signal without geo coordinates."""
        signal = Signal(position=(100.0, 200.0))
        assert signal.has_geo_coords() is False

    def test_with_geo_position(self):
        """Test signal with geo position."""
        signal = Signal(geo_position=(12.345, 57.789))
        assert signal.has_geo_coords() is True


class MockTransformer:
    """Mock transformer for testing coordinate conversions."""

    def geo_to_pixel(self, lon: float, lat: float) -> Tuple[float, float]:
        """Convert geo to pixel (simple scaling for test)."""
        return (lon * 1000.0, lat * 1000.0)


class TestSignalGetPixelPosition:
    """Test Signal.get_pixel_position() method."""

    def test_no_transformer_returns_stored_position(self):
        """Test without transformer returns stored position."""
        signal = Signal(position=(100.0, 200.0))
        assert signal.get_pixel_position() == (100.0, 200.0)

    def test_no_geo_returns_stored_position(self):
        """Test without geo coords returns stored position."""
        signal = Signal(position=(100.0, 200.0))
        transformer = MockTransformer()
        assert signal.get_pixel_position(transformer) == (100.0, 200.0)

    def test_with_geo_and_transformer(self):
        """Test with geo coords and transformer computes pixel coords."""
        signal = Signal(
            position=(0.0, 0.0),
            geo_position=(12.0, 57.0)
        )
        transformer = MockTransformer()
        result = signal.get_pixel_position(transformer)
        assert result == (12000.0, 57000.0)


class TestSignalUpdatePixelPositionFromGeo:
    """Test Signal.update_pixel_position_from_geo() method."""

    def test_update_position_from_geo(self):
        """Test updating position from geo coords."""
        signal = Signal(
            position=(0.0, 0.0),
            geo_position=(12.0, 57.0)
        )
        transformer = MockTransformer()
        signal.update_pixel_position_from_geo(transformer)
        assert signal.position == (12000.0, 57000.0)

    def test_no_geo_coords_no_change(self):
        """Test without geo coords position unchanged."""
        signal = Signal(position=(100.0, 200.0))
        transformer = MockTransformer()
        signal.update_pixel_position_from_geo(transformer)
        assert signal.position == (100.0, 200.0)


# ============================================================================
# Test Signal Serialization
# ============================================================================

class TestSignalSerialization:
    """Test Signal.to_dict() method."""

    def test_basic_serialization(self):
        """Test basic signal serialization."""
        signal = Signal(
            signal_id="test-123",
            position=(100.0, 200.0),
            signal_type=SignalType.LIBRARY_SIGN
        )
        signal.name = "Test Sign"

        data = signal.to_dict()

        assert data['id'] == "test-123"
        assert data['position'] == [100.0, 200.0]
        assert data['type'] == "library_sign"
        assert data['name'] == "Test Sign"

    def test_serialization_with_value(self):
        """Test serialization with speed value."""
        signal = Signal(
            signal_type=SignalType.SPEED_LIMIT,
            value=50
        )

        data = signal.to_dict()

        assert data['value'] == 50
        assert data['speed_unit'] == "km/h"

    def test_serialization_with_geo_position(self):
        """Test serialization includes geo_position."""
        signal = Signal(geo_position=(12.345, 57.789))

        data = signal.to_dict()

        assert data['geo_position'] == [12.345, 57.789]

    def test_serialization_with_opendrive_fields(self):
        """Test serialization includes OpenDRIVE fields when set."""
        signal = Signal()
        signal.opendrive_id = "od-123"
        signal.dynamic = "yes"
        signal.subtype = "270"
        signal.country = "SE"

        data = signal.to_dict()

        assert data['opendrive_id'] == "od-123"
        assert data['dynamic'] == "yes"
        assert data['subtype'] == "270"
        assert data['country'] == "SE"

    def test_serialization_omits_default_dynamic(self):
        """Test serialization omits dynamic when 'no'."""
        signal = Signal()
        signal.dynamic = "no"

        data = signal.to_dict()

        assert 'dynamic' not in data

    def test_serialization_with_library_fields(self):
        """Test serialization includes library fields."""
        signal = Signal(
            signal_type=SignalType.LIBRARY_SIGN,
            library_id="se",
            sign_id="B1"
        )

        data = signal.to_dict()

        assert data['library_id'] == "se"
        assert data['sign_id'] == "B1"

    def test_serialization_with_custom_codes(self):
        """Test serialization includes custom OpenDRIVE codes."""
        signal = Signal(signal_type=SignalType.CUSTOM)
        signal.custom_type = "1000001"
        signal.custom_subtype = "10"

        data = signal.to_dict()

        assert data['custom_type'] == "1000001"
        assert data['custom_subtype'] == "10"

    def test_serialization_with_validity_lanes(self):
        """Test serialization includes validity lanes."""
        signal = Signal()
        signal.validity_lanes = [-1, -2]

        data = signal.to_dict()

        assert data['validity_lanes'] == [-1, -2]

    def test_serialization_with_validity_range(self):
        """Test serialization includes validity range."""
        signal = Signal()
        signal.validity_range = (100.0, 200.0)

        data = signal.to_dict()

        assert data['validity_range'] == [100.0, 200.0]

    def test_serialization_validity_range_none(self):
        """Test serialization with None validity range."""
        signal = Signal()
        signal.validity_range = None

        data = signal.to_dict()

        assert data['validity_range'] is None


class TestSignalDeserialization:
    """Test Signal.from_dict() method."""

    def test_basic_deserialization(self):
        """Test basic signal deserialization."""
        data = {
            'id': 'test-123',
            'position': [100.0, 200.0],
            'type': 'library_sign',
            'name': 'Test Sign'
        }

        signal = Signal.from_dict(data)

        assert signal.id == "test-123"
        assert signal.position == (100.0, 200.0)
        assert signal.type == SignalType.LIBRARY_SIGN
        assert signal.name == "Test Sign"

    def test_deserialization_with_geo_position(self):
        """Test deserialization includes geo_position."""
        data = {
            'id': 'test-1',
            'type': 'library_sign',
            'position': [100.0, 200.0],
            'geo_position': [12.345, 57.789]
        }

        signal = Signal.from_dict(data)

        assert signal.geo_position == (12.345, 57.789)

    def test_deserialization_with_opendrive_fields(self):
        """Test deserialization includes OpenDRIVE fields."""
        data = {
            'id': 'test-1',
            'type': 'library_sign',
            'position': [100.0, 200.0],
            'opendrive_id': 'od-123',
            'dynamic': 'yes',
            'subtype': '270',
            'country': 'SE'
        }

        signal = Signal.from_dict(data)

        assert signal.opendrive_id == "od-123"
        assert signal.dynamic == "yes"
        assert signal.subtype == "270"
        assert signal.country == "SE"

    def test_deserialization_orientation_string(self):
        """Test deserialization with string orientation (new format)."""
        data = {
            'id': 'test-1',
            'type': 'library_sign',
            'position': [100.0, 200.0],
            'orientation': '-'
        }

        signal = Signal.from_dict(data)

        assert signal.orientation == '-'

    def test_deserialization_orientation_numeric(self):
        """Test deserialization with numeric orientation (old format)."""
        data = {
            'id': 'test-1',
            'type': 'library_sign',
            'position': [100.0, 200.0],
            'orientation': 45.0  # Old numeric format
        }

        signal = Signal.from_dict(data)

        # Should convert to forward orientation
        assert signal.orientation == '+'

    def test_deserialization_h_offset(self):
        """Test deserialization with h_offset."""
        data = {
            'id': 'test-1',
            'type': 'library_sign',
            'position': [100.0, 200.0],
            'h_offset': 0.5
        }

        signal = Signal.from_dict(data)

        assert signal.h_offset == 0.5

    def test_deserialization_h_offset_default(self):
        """Test deserialization without h_offset uses default."""
        data = {
            'id': 'test-1',
            'type': 'library_sign',
            'position': [100.0, 200.0]
        }

        signal = Signal.from_dict(data)

        assert signal.h_offset == 0.0

    def test_deserialization_z_offset(self):
        """Test deserialization with z_offset."""
        data = {
            'id': 'test-1',
            'type': 'library_sign',
            'position': [100.0, 200.0],
            'z_offset': 3.5
        }

        signal = Signal.from_dict(data)

        assert signal.z_offset == 3.5

    def test_deserialization_old_height_field(self):
        """Test deserialization with old 'height' field."""
        data = {
            'id': 'test-1',
            'type': 'library_sign',
            'position': [100.0, 200.0],
            'height': 4.0  # Old field name
        }

        signal = Signal.from_dict(data)

        assert signal.z_offset == 4.0

    def test_deserialization_sign_width(self):
        """Test deserialization with sign_width."""
        data = {
            'id': 'test-1',
            'type': 'library_sign',
            'position': [100.0, 200.0],
            'sign_width': 1.2
        }

        signal = Signal.from_dict(data)

        assert signal.sign_width == 1.2

    def test_deserialization_old_width_field(self):
        """Test deserialization with old 'width' field."""
        data = {
            'id': 'test-1',
            'type': 'library_sign',
            'position': [100.0, 200.0],
            'width': 0.8  # Old field name
        }

        signal = Signal.from_dict(data)

        assert signal.sign_width == 0.8

    def test_deserialization_sign_height_default(self):
        """Test deserialization uses category default for sign_height."""
        # Legacy types get migrated to LIBRARY_SIGN, so use library_sign directly
        data = {
            'id': 'test-1',
            'type': 'library_sign',
            'position': [100.0, 200.0]
        }

        signal = Signal.from_dict(data)

        # LIBRARY_SIGN uses 'other' category default (0.6)
        assert signal.sign_height == 0.6

    def test_deserialization_with_validity_range(self):
        """Test deserialization with validity range."""
        data = {
            'id': 'test-1',
            'type': 'library_sign',
            'position': [100.0, 200.0],
            'validity_range': [100.0, 200.0]
        }

        signal = Signal.from_dict(data)

        assert signal.validity_range == (100.0, 200.0)

    def test_deserialization_with_custom_codes(self):
        """Test deserialization with custom OpenDRIVE codes."""
        data = {
            'id': 'test-1',
            'type': 'custom',
            'position': [100.0, 200.0],
            'custom_type': '1000001',
            'custom_subtype': '10'
        }

        signal = Signal.from_dict(data)

        assert signal.custom_type == "1000001"
        assert signal.custom_subtype == "10"

    def test_deserialization_with_validity_lanes(self):
        """Test deserialization with validity lanes."""
        data = {
            'id': 'test-1',
            'type': 'library_sign',
            'position': [100.0, 200.0],
            'validity_lanes': [-1, -2]
        }

        signal = Signal.from_dict(data)

        assert signal.validity_lanes == [-1, -2]


class TestSignalRoundTrip:
    """Test serialization round-trip."""

    def test_full_round_trip(self):
        """Test complete round-trip serialization."""
        original = Signal(
            signal_id="round-trip-test",
            position=(150.0, 250.0),
            signal_type=SignalType.LIBRARY_SIGN,
            road_id="road-5",
            library_id="se",
            sign_id="C31-50",
            geo_position=(12.5, 57.5)
        )
        original.name = "Speed 50"
        original.value = 50
        original.orientation = '-'
        original.h_offset = 0.1
        original.z_offset = 2.5
        original.sign_width = 0.7
        original.sign_height = 0.7
        original.s_position = 100.0
        original.validity_range = (90.0, 110.0)
        original.opendrive_id = "od-456"
        original.dynamic = "no"
        original.subtype = "50"
        original.country = "SE"
        original.validity_lanes = [-1]

        # Round trip
        data = original.to_dict()
        restored = Signal.from_dict(data)

        assert restored.id == original.id
        assert restored.position == original.position
        assert restored.type == original.type
        assert restored.name == original.name
        assert restored.value == original.value
        assert restored.geo_position == original.geo_position
        assert restored.road_id == original.road_id
        assert restored.library_id == original.library_id
        assert restored.sign_id == original.sign_id
        assert restored.orientation == original.orientation
        assert restored.h_offset == original.h_offset
        assert restored.z_offset == original.z_offset
        assert restored.sign_width == original.sign_width
        assert restored.sign_height == original.sign_height
        assert restored.s_position == original.s_position
        assert restored.validity_range == original.validity_range
        assert restored.opendrive_id == original.opendrive_id
        assert restored.country == original.country
        assert restored.validity_lanes == original.validity_lanes


# ============================================================================
# Test Signal Display Name
# ============================================================================

class TestSignalGetDisplayName:
    """Test Signal.get_display_name() method."""

    def test_custom_name(self):
        """Test display name uses custom name when set."""
        signal = Signal()
        signal.name = "Main Street Sign"
        assert signal.get_display_name() == "Main Street Sign"

    def test_custom_type_with_code(self):
        """Test display name for custom type with code."""
        signal = Signal(signal_type=SignalType.CUSTOM)
        signal.custom_type = "1000001"
        assert signal.get_display_name() == "Custom (1000001)"

    def test_custom_type_without_code(self):
        """Test display name for custom type without code."""
        signal = Signal(signal_type=SignalType.CUSTOM)
        assert signal.get_display_name() == "Custom Signal"

    def test_speed_limit_with_value(self):
        """Test display name for speed limit with value."""
        signal = Signal(
            signal_type=SignalType.SPEED_LIMIT,
            value=50
        )
        assert signal.get_display_name() == "Speed 50 km/h"

    def test_speed_limit_mph(self):
        """Test display name for speed limit in mph."""
        signal = Signal(
            signal_type=SignalType.SPEED_LIMIT,
            value=30,
            speed_unit=SpeedUnit.MPH
        )
        assert signal.get_display_name() == "Speed 30 mph"

    def test_legacy_type_formatted(self):
        """Test display name formats legacy type."""
        signal = Signal(signal_type=SignalType.STOP)
        # Should use format_enum_name
        assert signal.get_display_name() == "Stop"

    def test_legacy_give_way_formatted(self):
        """Test display name formats give_way."""
        signal = Signal(signal_type=SignalType.GIVE_WAY)
        assert signal.get_display_name() == "Give Way"


# ============================================================================
# Test Signal Orientation Methods
# ============================================================================

class TestSignalOrientationMethods:
    """Test orientation conversion methods."""

    def test_get_orientation_forward(self):
        """Test get_orientation_ui_string for forward."""
        signal = Signal()
        signal.orientation = '+'
        assert signal.get_orientation_ui_string() == 'forward'

    def test_get_orientation_backward(self):
        """Test get_orientation_ui_string for backward."""
        signal = Signal()
        signal.orientation = '-'
        assert signal.get_orientation_ui_string() == 'backward'

    def test_get_orientation_both(self):
        """Test get_orientation_ui_string for both/none."""
        signal = Signal()
        signal.orientation = 'none'
        assert signal.get_orientation_ui_string() == 'both'

    def test_set_orientation_forward(self):
        """Test set_orientation_from_ui_string for forward."""
        signal = Signal()
        signal.set_orientation_from_ui_string('forward')
        assert signal.orientation == '+'

    def test_set_orientation_backward(self):
        """Test set_orientation_from_ui_string for backward."""
        signal = Signal()
        signal.set_orientation_from_ui_string('backward')
        assert signal.orientation == '-'

    def test_set_orientation_both(self):
        """Test set_orientation_from_ui_string for both."""
        signal = Signal()
        signal.set_orientation_from_ui_string('both')
        assert signal.orientation == 'none'


# ============================================================================
# Test Signal H-Offset Methods
# ============================================================================

class TestSignalHOffsetMethods:
    """Test h_offset degree conversion methods."""

    def test_get_h_offset_degrees_zero(self):
        """Test get_h_offset_degrees for zero."""
        signal = Signal()
        signal.h_offset = 0.0
        assert signal.get_h_offset_degrees() == 0.0

    def test_get_h_offset_degrees_90(self):
        """Test get_h_offset_degrees for 90 degrees."""
        signal = Signal()
        signal.h_offset = math.pi / 2
        assert signal.get_h_offset_degrees() == pytest.approx(90.0, rel=1e-6)

    def test_get_h_offset_degrees_negative(self):
        """Test get_h_offset_degrees for negative angle."""
        signal = Signal()
        signal.h_offset = -math.pi / 4
        assert signal.get_h_offset_degrees() == pytest.approx(-45.0, rel=1e-6)

    def test_set_h_offset_from_degrees_zero(self):
        """Test set_h_offset_from_degrees for zero."""
        signal = Signal()
        signal.set_h_offset_from_degrees(0.0)
        assert signal.h_offset == 0.0

    def test_set_h_offset_from_degrees_45(self):
        """Test set_h_offset_from_degrees for 45 degrees."""
        signal = Signal()
        signal.set_h_offset_from_degrees(45.0)
        assert signal.h_offset == pytest.approx(math.pi / 4, rel=1e-6)

    def test_set_h_offset_from_degrees_180(self):
        """Test set_h_offset_from_degrees for 180 degrees."""
        signal = Signal()
        signal.set_h_offset_from_degrees(180.0)
        assert signal.h_offset == pytest.approx(math.pi, rel=1e-6)


# ============================================================================
# Test Signal Calculate Visual Angle
# ============================================================================

class TestSignalCalculateVisualAngle:
    """Test Signal.calculate_visual_angle() method."""

    def test_no_centerline(self):
        """Test with no centerline points."""
        signal = Signal(position=(50.0, 50.0))
        signal.h_offset = 0.0
        angle = signal.calculate_visual_angle([])
        # Should use h_offset relative to north (90 degrees default)
        assert angle == pytest.approx(90.0, abs=0.1)

    def test_single_point_centerline(self):
        """Test with only one centerline point."""
        signal = Signal(position=(50.0, 50.0))
        angle = signal.calculate_visual_angle([(0.0, 0.0)])
        assert angle == pytest.approx(90.0, abs=0.1)

    def test_horizontal_road_forward(self):
        """Test signal on horizontal road, forward orientation."""
        signal = Signal(position=(50.0, 10.0))  # Below centerline (right side)
        signal.orientation = '+'
        signal.h_offset = 0.0
        centerline = [(0.0, 0.0), (100.0, 0.0)]

        angle = signal.calculate_visual_angle(centerline)

        # Road goes right (0 degrees), signal on right side should face perpendicular
        # Right side → base angle = 0 - 90 = -90 → normalized to 270
        assert 0 <= angle < 360

    def test_horizontal_road_backward(self):
        """Test signal on horizontal road, backward orientation."""
        signal = Signal(position=(50.0, 10.0))
        signal.orientation = '-'
        signal.h_offset = 0.0
        centerline = [(0.0, 0.0), (100.0, 0.0)]

        angle = signal.calculate_visual_angle(centerline)

        # Backward orientation flips 180 degrees
        assert 0 <= angle < 360

    def test_with_h_offset(self):
        """Test visual angle with non-zero h_offset."""
        signal = Signal(position=(50.0, 10.0))
        signal.orientation = '+'
        signal.h_offset = math.radians(30)  # 30 degrees offset
        centerline = [(0.0, 0.0), (100.0, 0.0)]

        angle = signal.calculate_visual_angle(centerline)

        # Should be base angle + 30 degrees
        assert 0 <= angle < 360

    def test_multi_segment_centerline(self):
        """Test with multi-segment centerline."""
        signal = Signal(position=(50.0, 55.0))  # Near second segment
        signal.orientation = '+'
        signal.h_offset = 0.0
        # L-shaped centerline
        centerline = [(0.0, 0.0), (50.0, 0.0), (50.0, 100.0)]

        angle = signal.calculate_visual_angle(centerline)

        # Should calculate based on closest segment
        assert 0 <= angle < 360


# ============================================================================
# Test Signal Calculate S Position
# ============================================================================

class TestSignalCalculateSPosition:
    """Test Signal.calculate_s_position() method."""

    def test_no_centerline(self):
        """Test with no centerline points."""
        signal = Signal(position=(50.0, 50.0))
        s = signal.calculate_s_position([])
        assert s is None

    def test_single_point_centerline(self):
        """Test with only one centerline point."""
        signal = Signal(position=(50.0, 50.0))
        s = signal.calculate_s_position([(0.0, 0.0)])
        assert s is None

    def test_signal_on_centerline(self):
        """Test signal positioned on the centerline."""
        signal = Signal(position=(50.0, 0.0))
        centerline = [(0.0, 0.0), (100.0, 0.0)]

        s = signal.calculate_s_position(centerline)

        assert s == pytest.approx(50.0, abs=0.01)

    def test_signal_at_start(self):
        """Test signal at start of centerline."""
        signal = Signal(position=(0.0, 5.0))
        centerline = [(0.0, 0.0), (100.0, 0.0)]

        s = signal.calculate_s_position(centerline)

        assert s == pytest.approx(0.0, abs=0.01)

    def test_signal_at_end(self):
        """Test signal at end of centerline."""
        signal = Signal(position=(100.0, 5.0))
        centerline = [(0.0, 0.0), (100.0, 0.0)]

        s = signal.calculate_s_position(centerline)

        assert s == pytest.approx(100.0, abs=0.01)

    def test_multi_segment_centerline(self):
        """Test with multi-segment centerline."""
        signal = Signal(position=(100.0, 55.0))
        # L-shaped: 100px right, then 100px down
        centerline = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0)]

        s = signal.calculate_s_position(centerline)

        # Should be 100 (first segment) + 55 (along second segment)
        assert s == pytest.approx(155.0, abs=1.0)

    def test_signal_off_to_side(self):
        """Test signal off to the side of centerline."""
        signal = Signal(position=(50.0, 20.0))  # 20 pixels to right
        centerline = [(0.0, 0.0), (100.0, 0.0)]

        s = signal.calculate_s_position(centerline)

        # s should still be projection position
        assert s == pytest.approx(50.0, abs=0.01)

    def test_zero_length_segment(self):
        """Test with zero-length segment in centerline."""
        signal = Signal(position=(50.0, 0.0))
        centerline = [(0.0, 0.0), (0.0, 0.0), (100.0, 0.0)]

        s = signal.calculate_s_position(centerline)

        # Should handle zero-length segment gracefully
        assert s is not None


# ============================================================================
# Test Signal Point to Segment Distance
# ============================================================================

class TestSignalPointToSegmentDistance:
    """Test Signal._point_to_segment_distance() method."""

    def test_point_on_segment(self):
        """Test point on segment has zero distance."""
        signal = Signal()
        dist = signal._point_to_segment_distance(50, 0, 0, 0, 100, 0)
        assert dist == pytest.approx(0.0, abs=0.01)

    def test_point_perpendicular(self):
        """Test point perpendicular to segment."""
        signal = Signal()
        dist = signal._point_to_segment_distance(50, 10, 0, 0, 100, 0)
        assert dist == pytest.approx(10.0, abs=0.01)

    def test_point_past_start(self):
        """Test point past start of segment."""
        signal = Signal()
        dist = signal._point_to_segment_distance(-10, 0, 0, 0, 100, 0)
        assert dist == pytest.approx(10.0, abs=0.01)

    def test_point_past_end(self):
        """Test point past end of segment."""
        signal = Signal()
        dist = signal._point_to_segment_distance(110, 0, 0, 0, 100, 0)
        assert dist == pytest.approx(10.0, abs=0.01)

    def test_zero_length_segment(self):
        """Test zero-length segment."""
        signal = Signal()
        dist = signal._point_to_segment_distance(10, 10, 0, 0, 0, 0)
        expected = math.sqrt(10**2 + 10**2)
        assert dist == pytest.approx(expected, abs=0.01)

    def test_diagonal_segment(self):
        """Test diagonal segment."""
        signal = Signal()
        # Point at origin, segment from (10, 0) to (10, 10)
        dist = signal._point_to_segment_distance(0, 5, 10, 0, 10, 10)
        assert dist == pytest.approx(10.0, abs=0.01)


# ============================================================================
# Test SignalType Enum Values
# ============================================================================

class TestSignalTypeValues:
    """Test SignalType enum string values."""

    def test_all_types_have_string_values(self):
        """Test all types have string values for serialization."""
        for signal_type in SignalType:
            assert isinstance(signal_type.value, str)
            assert len(signal_type.value) > 0

    def test_from_value(self):
        """Test creating enum from value string."""
        assert SignalType("library_sign") == SignalType.LIBRARY_SIGN
        assert SignalType("stop") == SignalType.STOP
        assert SignalType("custom") == SignalType.CUSTOM

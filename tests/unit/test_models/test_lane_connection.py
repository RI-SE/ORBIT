"""
Unit tests for LaneConnection model.

Tests lane connection creation, validation, turn type classification, and serialization.
"""

import pytest

from orbit.models import LaneConnection


class TestLaneConnectionCreation:
    """Test lane connection initialization and basic properties."""

    def test_default_creation(self):
        """Test creating lane connection with defaults."""
        lc = LaneConnection()

        assert lc.id is not None
        assert len(lc.id) > 0
        assert lc.from_road_id == ""
        assert lc.from_lane_id == -1
        assert lc.to_road_id == ""
        assert lc.to_lane_id == -1
        assert lc.connecting_road_id is None
        assert lc.turn_type == "unknown"
        assert lc.priority == 0
        assert lc.traffic_light_id is None
        assert lc.stop_line_offset is None

    def test_creation_with_road_and_lane_ids(self):
        """Test creating lane connection with road and lane IDs."""
        lc = LaneConnection(
            from_road_id="road_1",
            from_lane_id=-1,
            to_road_id="road_2",
            to_lane_id=-1
        )

        assert lc.from_road_id == "road_1"
        assert lc.from_lane_id == -1
        assert lc.to_road_id == "road_2"
        assert lc.to_lane_id == -1

    def test_creation_with_turn_type(self):
        """Test creating lane connection with turn type."""
        lc = LaneConnection(
            from_road_id="road_A",
            from_lane_id=-1,
            to_road_id="road_B",
            to_lane_id=-1,
            turn_type="straight"
        )

        assert lc.turn_type == "straight"
        assert lc.get_turn_type_display() == "Straight"

    def test_creation_with_connecting_road(self):
        """Test creating lane connection with connecting road reference."""
        lc = LaneConnection(
            from_road_id="road_1",
            from_lane_id=-1,
            to_road_id="road_2",
            to_lane_id=-1,
            connecting_road_id="conn_road_123"
        )

        assert lc.connecting_road_id == "conn_road_123"

    def test_creation_with_priority(self):
        """Test creating lane connection with priority."""
        lc = LaneConnection(
            from_road_id="road_1",
            from_lane_id=-1,
            to_road_id="road_2",
            to_lane_id=-1,
            priority=5
        )

        assert lc.priority == 5


class TestLaneConnectionTurnTypes:
    """Test turn type handling and display."""

    @pytest.mark.parametrize("turn_type,expected_display", [
        ("straight", "Straight"),
        ("left", "Left Turn"),
        ("right", "Right Turn"),
        ("uturn", "U-Turn"),
        ("merge", "Merge"),
        ("diverge", "Diverge"),
        ("unknown", "Unknown"),
    ])
    def test_turn_type_display(self, turn_type, expected_display):
        """Test turn type display names."""
        lc = LaneConnection(turn_type=turn_type)
        assert lc.get_turn_type_display() == expected_display

    def test_valid_turn_types(self):
        """Test validation of valid turn types."""
        valid_types = ['straight', 'left', 'right', 'uturn', 'merge', 'diverge', 'unknown']

        for turn_type in valid_types:
            lc = LaneConnection(turn_type=turn_type)
            assert lc.is_valid_turn_type()

    def test_invalid_turn_type(self):
        """Test validation of invalid turn type."""
        lc = LaneConnection(turn_type="invalid_type")
        assert not lc.is_valid_turn_type()


class TestLaneConnectionValidation:
    """Test lane connection validation."""

    def test_valid_connection(self):
        """Test validation of valid lane connection."""
        lc = LaneConnection(
            from_road_id="road_1",
            from_lane_id=-1,
            to_road_id="road_2",
            to_lane_id=-1,
            turn_type="straight"
        )

        is_valid, errors = lc.validate_basic()
        assert is_valid
        assert len(errors) == 0

    def test_missing_from_road_id(self):
        """Test validation fails when from_road_id is missing."""
        lc = LaneConnection(
            from_road_id="",  # Empty
            from_lane_id=-1,
            to_road_id="road_2",
            to_lane_id=-1
        )

        is_valid, errors = lc.validate_basic()
        assert not is_valid
        assert "From road ID is required" in errors

    def test_missing_to_road_id(self):
        """Test validation fails when to_road_id is missing."""
        lc = LaneConnection(
            from_road_id="road_1",
            from_lane_id=-1,
            to_road_id="",  # Empty
            to_lane_id=-1
        )

        is_valid, errors = lc.validate_basic()
        assert not is_valid
        assert "To road ID is required" in errors

    def test_center_lane_as_from_lane(self):
        """Test validation fails when from_lane_id is 0 (center lane)."""
        lc = LaneConnection(
            from_road_id="road_1",
            from_lane_id=0,  # Center lane
            to_road_id="road_2",
            to_lane_id=-1
        )

        is_valid, errors = lc.validate_basic()
        assert not is_valid
        assert any("center lane" in err for err in errors)

    def test_center_lane_as_to_lane(self):
        """Test validation fails when to_lane_id is 0 (center lane)."""
        lc = LaneConnection(
            from_road_id="road_1",
            from_lane_id=-1,
            to_road_id="road_2",
            to_lane_id=0  # Center lane
        )

        is_valid, errors = lc.validate_basic()
        assert not is_valid
        assert any("center lane" in err for err in errors)

    def test_invalid_turn_type_validation(self):
        """Test validation fails with invalid turn type."""
        lc = LaneConnection(
            from_road_id="road_1",
            from_lane_id=-1,
            to_road_id="road_2",
            to_lane_id=-1,
            turn_type="invalid_turn"
        )

        is_valid, errors = lc.validate_basic()
        assert not is_valid
        assert any("Invalid turn type" in err for err in errors)

    def test_self_connection_not_allowed(self):
        """Test validation fails when connecting road to itself."""
        lc = LaneConnection(
            from_road_id="road_1",
            from_lane_id=-1,
            to_road_id="road_1",  # Same road
            to_lane_id=-2
        )

        is_valid, errors = lc.validate_basic()
        assert not is_valid
        assert "Cannot connect road to itself" in errors

    def test_multiple_validation_errors(self):
        """Test validation returns multiple errors."""
        lc = LaneConnection(
            from_road_id="",  # Missing
            from_lane_id=0,    # Center lane (invalid)
            to_road_id="",     # Missing
            to_lane_id=0,      # Center lane (invalid)
            turn_type="bad"    # Invalid type
        )

        is_valid, errors = lc.validate_basic()
        assert not is_valid
        assert len(errors) >= 5  # Multiple errors


class TestLaneConnectionSerialization:
    """Test lane connection to_dict/from_dict serialization."""

    def test_to_dict_minimal(self):
        """Test converting minimal lane connection to dictionary."""
        lc = LaneConnection()
        data = lc.to_dict()

        assert 'id' in data
        assert data['from_road_id'] == ""
        assert data['from_lane_id'] == -1
        assert data['to_road_id'] == ""
        assert data['to_lane_id'] == -1
        assert data['turn_type'] == "unknown"
        assert data['priority'] == 0
        # Optional fields not in dict when None
        assert 'connecting_road_id' not in data
        assert 'traffic_light_id' not in data
        assert 'stop_line_offset' not in data

    def test_to_dict_complete(self):
        """Test converting complete lane connection to dictionary."""
        lc = LaneConnection(
            from_road_id="road_A",
            from_lane_id=-2,
            to_road_id="road_B",
            to_lane_id=-1,
            connecting_road_id="conn_1",
            turn_type="right",
            priority=3,
            traffic_light_id="signal_1",
            stop_line_offset=2.5
        )
        data = lc.to_dict()

        assert data['from_road_id'] == "road_A"
        assert data['from_lane_id'] == -2
        assert data['to_road_id'] == "road_B"
        assert data['to_lane_id'] == -1
        assert data['connecting_road_id'] == "conn_1"
        assert data['turn_type'] == "right"
        assert data['priority'] == 3
        assert data['traffic_light_id'] == "signal_1"
        assert data['stop_line_offset'] == 2.5

    def test_from_dict_minimal(self):
        """Test creating lane connection from minimal dictionary."""
        data = {
            'id': 'test_id',
            'from_road_id': 'road_1',
            'from_lane_id': -1,
            'to_road_id': 'road_2',
            'to_lane_id': -1,
            'turn_type': 'straight',
            'priority': 0
        }

        lc = LaneConnection.from_dict(data)

        assert lc.id == 'test_id'
        assert lc.from_road_id == 'road_1'
        assert lc.from_lane_id == -1
        assert lc.to_road_id == 'road_2'
        assert lc.to_lane_id == -1
        assert lc.turn_type == 'straight'
        assert lc.priority == 0
        assert lc.connecting_road_id is None

    def test_from_dict_complete(self):
        """Test creating lane connection from complete dictionary."""
        data = {
            'id': 'lc_123',
            'from_road_id': 'road_X',
            'from_lane_id': 1,
            'to_road_id': 'road_Y',
            'to_lane_id': 2,
            'connecting_road_id': 'conn_abc',
            'turn_type': 'left',
            'priority': 5,
            'traffic_light_id': 'light_1',
            'stop_line_offset': 3.0
        }

        lc = LaneConnection.from_dict(data)

        assert lc.id == 'lc_123'
        assert lc.from_road_id == 'road_X'
        assert lc.from_lane_id == 1
        assert lc.to_road_id == 'road_Y'
        assert lc.to_lane_id == 2
        assert lc.connecting_road_id == 'conn_abc'
        assert lc.turn_type == 'left'
        assert lc.priority == 5
        assert lc.traffic_light_id == 'light_1'
        assert lc.stop_line_offset == 3.0

    def test_roundtrip_serialization(self):
        """Test lane connection → dict → lane connection preserves data."""
        original = LaneConnection(
            from_road_id="road_1",
            from_lane_id=-2,
            to_road_id="road_3",
            to_lane_id=-1,
            connecting_road_id="conn_road_5",
            turn_type="straight",
            priority=2
        )

        data = original.to_dict()
        restored = LaneConnection.from_dict(data)

        assert restored.from_road_id == original.from_road_id
        assert restored.from_lane_id == original.from_lane_id
        assert restored.to_road_id == original.to_road_id
        assert restored.to_lane_id == original.to_lane_id
        assert restored.connecting_road_id == original.connecting_road_id
        assert restored.turn_type == original.turn_type
        assert restored.priority == original.priority

    def test_from_dict_with_missing_fields(self):
        """Test creating lane connection from dict with missing optional fields."""
        data = {
            'id': 'test_lc',
            'from_road_id': 'r1',
            'from_lane_id': -1
            # Missing other fields - should use defaults
        }

        lc = LaneConnection.from_dict(data)

        assert lc.id == 'test_lc'
        assert lc.from_road_id == 'r1'
        assert lc.from_lane_id == -1
        assert lc.to_road_id == ''  # Default
        assert lc.to_lane_id == -1  # Default
        assert lc.turn_type == 'unknown'  # Default


class TestLaneConnectionLaneIDs:
    """Test lane ID conventions and usage."""

    def test_right_lane_connection(self):
        """Test connection between right lanes (negative IDs)."""
        lc = LaneConnection(
            from_road_id="road_1",
            from_lane_id=-1,  # Rightmost driving lane
            to_road_id="road_2",
            to_lane_id=-1
        )

        assert lc.from_lane_id < 0
        assert lc.to_lane_id < 0

    def test_left_lane_connection(self):
        """Test connection between left lanes (positive IDs)."""
        lc = LaneConnection(
            from_road_id="road_1",
            from_lane_id=1,  # Leftmost driving lane
            to_road_id="road_2",
            to_lane_id=1
        )

        assert lc.from_lane_id > 0
        assert lc.to_lane_id > 0

    def test_cross_side_connection(self):
        """Test connection from right lane to left lane (unusual but valid)."""
        lc = LaneConnection(
            from_road_id="road_1",
            from_lane_id=-1,  # Right lane
            to_road_id="road_2",
            to_lane_id=1      # Left lane
        )

        assert lc.from_lane_id < 0
        assert lc.to_lane_id > 0
        is_valid, _ = lc.validate_basic()
        assert is_valid  # Geometrically unusual but not invalid


class TestLaneConnectionRepr:
    """Test string representation of lane connection."""

    def test_repr_format(self):
        """Test __repr__ produces readable string."""
        lc = LaneConnection(
            from_road_id="road_abc123",
            from_lane_id=-2,
            to_road_id="road_xyz789",
            to_lane_id=-1,
            turn_type="left"
        )

        repr_str = repr(lc)

        assert "LaneConnection" in repr_str
        assert "road_abc" in repr_str  # First 8 chars
        assert ":-2" in repr_str        # From lane ID
        assert "road_xyz" in repr_str
        assert ":-1" in repr_str        # To lane ID
        assert "left" in repr_str        # Turn type

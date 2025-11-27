"""
Unit tests for ConnectingRoad model.

Tests connecting road creation, geometry calculations, and serialization.
"""

import pytest
import math

from orbit.models import ConnectingRoad


class TestConnectingRoadCreation:
    """Test connecting road initialization and basic properties."""

    def test_default_creation(self):
        """Test creating connecting road with defaults."""
        cr = ConnectingRoad()

        assert cr.id is not None
        assert len(cr.id) > 0
        assert cr.path == []
        assert cr.lane_count_left == 0
        assert cr.lane_count_right == 1
        assert cr.lane_width == 3.5
        assert cr.predecessor_road_id == ""
        assert cr.successor_road_id == ""
        assert cr.contact_point_start == "end"
        assert cr.contact_point_end == "start"

    def test_creation_with_path(self):
        """Test creating connecting road with path."""
        path = [(0.0, 0.0), (50.0, 25.0), (100.0, 50.0)]
        cr = ConnectingRoad(path=path)

        assert cr.path == path
        assert len(cr.path) == 3

    def test_creation_with_lane_config(self):
        """Test creating connecting road with lane configuration."""
        cr = ConnectingRoad(
            lane_count_left=1,
            lane_count_right=2,
            lane_width=3.0
        )

        assert cr.lane_count_left == 1
        assert cr.lane_count_right == 2
        assert cr.lane_width == 3.0
        assert cr.get_total_lane_count() == 3

    def test_creation_with_road_references(self):
        """Test creating connecting road with predecessor/successor."""
        cr = ConnectingRoad(
            predecessor_road_id="road_in",
            successor_road_id="road_out",
            contact_point_start="end",
            contact_point_end="start"
        )

        assert cr.predecessor_road_id == "road_in"
        assert cr.successor_road_id == "road_out"
        assert cr.contact_point_start == "end"
        assert cr.contact_point_end == "start"


class TestConnectingRoadGeometry:
    """Test geometric calculations for connecting roads."""

    def test_length_calculation_empty_path(self):
        """Test length calculation for empty path."""
        cr = ConnectingRoad(path=[])
        assert cr.get_length_pixels() == 0.0

    def test_length_calculation_single_point(self):
        """Test length calculation for single point."""
        cr = ConnectingRoad(path=[(0.0, 0.0)])
        assert cr.get_length_pixels() == 0.0

    def test_length_calculation_straight_line(self):
        """Test length calculation for straight line."""
        cr = ConnectingRoad(path=[(0.0, 0.0), (100.0, 0.0)])
        assert cr.get_length_pixels() == pytest.approx(100.0)

    def test_length_calculation_diagonal(self):
        """Test length calculation for diagonal line."""
        # 3-4-5 triangle
        cr = ConnectingRoad(path=[(0.0, 0.0), (30.0, 40.0)])
        assert cr.get_length_pixels() == pytest.approx(50.0)

    def test_length_calculation_multi_segment(self):
        """Test length calculation for multiple segments."""
        cr = ConnectingRoad(path=[
            (0.0, 0.0),
            (10.0, 0.0),
            (10.0, 10.0),
            (0.0, 10.0)
        ])
        # Three segments: 10 + 10 + 10 = 30
        assert cr.get_length_pixels() == pytest.approx(30.0)

    def test_start_point_retrieval(self):
        """Test getting start point of path."""
        path = [(10.0, 20.0), (30.0, 40.0), (50.0, 60.0)]
        cr = ConnectingRoad(path=path)

        start = cr.get_start_point()
        assert start == (10.0, 20.0)

    def test_end_point_retrieval(self):
        """Test getting end point of path."""
        path = [(10.0, 20.0), (30.0, 40.0), (50.0, 60.0)]
        cr = ConnectingRoad(path=path)

        end = cr.get_end_point()
        assert end == (50.0, 60.0)

    def test_start_point_empty_path(self):
        """Test getting start point from empty path."""
        cr = ConnectingRoad(path=[])
        assert cr.get_start_point() is None

    def test_end_point_empty_path(self):
        """Test getting end point from empty path."""
        cr = ConnectingRoad(path=[])
        assert cr.get_end_point() is None


class TestConnectingRoadHeading:
    """Test heading calculations for connecting roads."""

    def test_start_heading_eastward(self):
        """Test start heading for eastward path."""
        cr = ConnectingRoad(path=[(0.0, 0.0), (100.0, 0.0)])
        heading = cr.get_start_heading()

        assert heading is not None
        assert heading == pytest.approx(0.0)  # 0 radians = east

    def test_start_heading_northward(self):
        """Test start heading for northward path."""
        cr = ConnectingRoad(path=[(0.0, 0.0), (0.0, 100.0)])
        heading = cr.get_start_heading()

        assert heading is not None
        assert heading == pytest.approx(math.pi / 2)  # π/2 radians = north

    def test_start_heading_westward(self):
        """Test start heading for westward path."""
        cr = ConnectingRoad(path=[(100.0, 0.0), (0.0, 0.0)])
        heading = cr.get_start_heading()

        assert heading is not None
        assert abs(heading) == pytest.approx(math.pi)  # π radians = west

    def test_start_heading_southward(self):
        """Test start heading for southward path."""
        cr = ConnectingRoad(path=[(0.0, 100.0), (0.0, 0.0)])
        heading = cr.get_start_heading()

        assert heading is not None
        assert heading == pytest.approx(-math.pi / 2)  # -π/2 radians = south

    def test_end_heading(self):
        """Test end heading calculation."""
        cr = ConnectingRoad(path=[
            (0.0, 0.0),
            (50.0, 0.0),
            (100.0, 50.0)
        ])
        heading = cr.get_end_heading()

        assert heading is not None
        # Last segment goes from (50,0) to (100,50) - northeast
        assert heading == pytest.approx(math.atan2(50, 50))

    def test_heading_insufficient_points(self):
        """Test heading calculation with insufficient points."""
        cr = ConnectingRoad(path=[(0.0, 0.0)])
        assert cr.get_start_heading() is None
        assert cr.get_end_heading() is None


class TestConnectingRoadLanes:
    """Test lane-related functions for connecting roads."""

    def test_total_lane_count_single_lane(self):
        """Test total lane count with single right lane."""
        cr = ConnectingRoad(lane_count_left=0, lane_count_right=1)
        assert cr.get_total_lane_count() == 1

    def test_total_lane_count_multi_lane(self):
        """Test total lane count with multiple lanes."""
        cr = ConnectingRoad(lane_count_left=2, lane_count_right=2)
        assert cr.get_total_lane_count() == 4

    def test_total_lane_count_left_only(self):
        """Test total lane count with only left lanes."""
        cr = ConnectingRoad(lane_count_left=3, lane_count_right=0)
        assert cr.get_total_lane_count() == 3


class TestConnectingRoadSerialization:
    """Test connecting road to_dict/from_dict serialization."""

    def test_to_dict_minimal(self):
        """Test converting minimal connecting road to dictionary."""
        cr = ConnectingRoad()
        data = cr.to_dict()

        assert 'id' in data
        assert data['path'] == []
        assert data['lane_count_left'] == 0
        assert data['lane_count_right'] == 1
        assert data['lane_width'] == 3.5
        assert data['predecessor_road_id'] == ""
        assert data['successor_road_id'] == ""
        assert data['contact_point_start'] == "end"
        assert data['contact_point_end'] == "start"

    def test_to_dict_complete(self):
        """Test converting complete connecting road to dictionary."""
        path = [(0.0, 0.0), (50.0, 25.0), (100.0, 50.0)]
        cr = ConnectingRoad(
            path=path,
            lane_count_left=1,
            lane_count_right=2,
            lane_width=3.0,
            predecessor_road_id="road_A",
            successor_road_id="road_B",
            contact_point_start="end",
            contact_point_end="start"
        )
        data = cr.to_dict()

        assert data['path'] == [[0.0, 0.0], [50.0, 25.0], [100.0, 50.0]]
        assert data['lane_count_left'] == 1
        assert data['lane_count_right'] == 2
        assert data['lane_width'] == 3.0
        assert data['predecessor_road_id'] == "road_A"
        assert data['successor_road_id'] == "road_B"

    def test_from_dict_minimal(self):
        """Test creating connecting road from minimal dictionary."""
        data = {
            'id': 'test_id',
            'path': [],
            'lane_count_left': 0,
            'lane_count_right': 1,
            'lane_width': 3.5,
            'predecessor_road_id': '',
            'successor_road_id': '',
            'contact_point_start': 'end',
            'contact_point_end': 'start'
        }

        cr = ConnectingRoad.from_dict(data)

        assert cr.id == 'test_id'
        assert cr.path == []
        assert cr.lane_count_left == 0
        assert cr.lane_count_right == 1

    def test_from_dict_complete(self):
        """Test creating connecting road from complete dictionary."""
        data = {
            'id': 'conn_123',
            'path': [[10.0, 20.0], [30.0, 40.0], [50.0, 60.0]],
            'lane_count_left': 2,
            'lane_count_right': 3,
            'lane_width': 3.2,
            'predecessor_road_id': 'road_X',
            'successor_road_id': 'road_Y',
            'contact_point_start': 'start',
            'contact_point_end': 'end'
        }

        cr = ConnectingRoad.from_dict(data)

        assert cr.id == 'conn_123'
        assert cr.path == [(10.0, 20.0), (30.0, 40.0), (50.0, 60.0)]
        assert cr.lane_count_left == 2
        assert cr.lane_count_right == 3
        assert cr.lane_width == 3.2
        assert cr.predecessor_road_id == 'road_X'
        assert cr.successor_road_id == 'road_Y'
        assert cr.contact_point_start == 'start'
        assert cr.contact_point_end == 'end'

    def test_roundtrip_serialization(self):
        """Test connecting road → dict → connecting road preserves data."""
        path = [(0.0, 0.0), (25.0, 50.0), (50.0, 100.0)]
        original = ConnectingRoad(
            path=path,
            lane_count_left=1,
            lane_count_right=2,
            lane_width=3.3,
            predecessor_road_id="road_1",
            successor_road_id="road_2"
        )

        data = original.to_dict()
        restored = ConnectingRoad.from_dict(data)

        assert restored.path == original.path
        assert restored.lane_count_left == original.lane_count_left
        assert restored.lane_count_right == original.lane_count_right
        assert restored.lane_width == pytest.approx(original.lane_width)
        assert restored.predecessor_road_id == original.predecessor_road_id
        assert restored.successor_road_id == original.successor_road_id

    def test_from_dict_with_missing_fields(self):
        """Test creating connecting road from dict with missing optional fields."""
        data = {
            'id': 'test_conn'
            # Missing other fields - should use defaults
        }

        cr = ConnectingRoad.from_dict(data)

        assert cr.id == 'test_conn'
        assert cr.path == []
        assert cr.lane_count_left == 0
        assert cr.lane_count_right == 1
        assert cr.lane_width == 3.5


class TestConnectingRoadRepr:
    """Test string representation of connecting road."""

    def test_repr_format(self):
        """Test __repr__ produces readable string."""
        cr = ConnectingRoad(
            path=[(0, 0), (100, 100)],
            predecessor_road_id="road_abc123",
            successor_road_id="road_xyz789"
        )

        repr_str = repr(cr)

        assert "ConnectingRoad" in repr_str
        assert "points=2" in repr_str
        assert "lanes=1" in repr_str
        assert "road_abc" in repr_str  # First 8 chars of ID
        assert "road_xyz" in repr_str

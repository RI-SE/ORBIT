"""
Unit tests for Lane model.

Tests lane creation, properties, OpenDrive ID conventions, and serialization.
"""

import pytest

from orbit.models import Lane, LaneType, RoadMarkType


class TestLaneCreation:
    """Test lane initialization and basic properties."""

    def test_lane_creation_with_id(self):
        """Test creating a lane with specific ID."""
        lane = Lane(id=1)

        assert lane.id == 1
        assert lane.lane_type == LaneType.DRIVING
        assert lane.road_mark_type == RoadMarkType.SOLID
        assert lane.width == 3.5

    def test_center_lane_creation(self, sample_lane_center: Lane):
        """Test creating center lane (ID=0)."""
        assert sample_lane_center.id == 0
        assert sample_lane_center.lane_type == LaneType.NONE
        assert sample_lane_center.width == 0.0

    def test_left_lane_creation(self, sample_lane_left: Lane):
        """Test creating left lane (positive ID)."""
        assert sample_lane_left.id == 1
        assert sample_lane_left.lane_type == LaneType.DRIVING
        assert sample_lane_left.width == 3.5

    def test_right_lane_creation(self, sample_lane_right: Lane):
        """Test creating right lane (negative ID)."""
        assert sample_lane_right.id == -1
        assert sample_lane_right.lane_type == LaneType.DRIVING
        assert sample_lane_right.width == 3.5


class TestLaneIDConventions:
    """Test OpenDrive lane ID conventions."""

    def test_center_lane_has_id_zero(self):
        """Test that center lane has ID = 0."""
        center = Lane(id=0, lane_type=LaneType.NONE)
        assert center.id == 0

    def test_left_lanes_have_positive_ids(self):
        """Test that left lanes have positive IDs."""
        lane1 = Lane(id=1)
        lane2 = Lane(id=2)
        lane3 = Lane(id=3)

        assert lane1.id > 0
        assert lane2.id > 0
        assert lane3.id > 0

    def test_right_lanes_have_negative_ids(self):
        """Test that right lanes have negative IDs."""
        lane1 = Lane(id=-1)
        lane2 = Lane(id=-2)
        lane3 = Lane(id=-3)

        assert lane1.id < 0
        assert lane2.id < 0
        assert lane3.id < 0

    def test_lane_ordering_convention(self):
        """Test that lanes follow OpenDrive ordering (left to right)."""
        # In OpenDrive: [..., 3, 2, 1] [0] [-1, -2, -3, ...]
        #               left lanes    center  right lanes
        left_lane = Lane(id=1)
        center_lane = Lane(id=0, lane_type=LaneType.NONE)
        right_lane = Lane(id=-1)

        # Create list and sort by ID descending (left to right)
        lanes = [right_lane, center_lane, left_lane]
        lanes_sorted = sorted(lanes, key=lambda l: l.id, reverse=True)

        assert lanes_sorted[0].id == 1  # Leftmost
        assert lanes_sorted[1].id == 0  # Center
        assert lanes_sorted[2].id == -1  # Rightmost


class TestLaneTypes:
    """Test different lane types."""

    @pytest.mark.parametrize("lane_type", [
        LaneType.NONE,
        LaneType.DRIVING,
        LaneType.STOP,
        LaneType.SHOULDER,
        LaneType.BIKING,
        LaneType.SIDEWALK,
        LaneType.BORDER,
        LaneType.RESTRICTED,
        LaneType.PARKING,
        LaneType.MEDIAN,
        LaneType.CURB,
    ])
    def test_lane_types(self, lane_type: LaneType):
        """Test various lane types."""
        lane = Lane(id=1, lane_type=lane_type)
        assert lane.lane_type == lane_type

    def test_driving_lane(self):
        """Test driving lane type (most common)."""
        lane = Lane(id=-1, lane_type=LaneType.DRIVING)
        assert lane.lane_type == LaneType.DRIVING

    def test_center_lane_type_none(self):
        """Test that center lane typically has type NONE."""
        center = Lane(id=0, lane_type=LaneType.NONE, width=0.0)
        assert center.lane_type == LaneType.NONE


class TestLaneWidth:
    """Test lane width handling."""

    def test_default_lane_width(self):
        """Test default lane width is 3.5 meters."""
        lane = Lane(id=1)
        assert lane.width == 3.5

    def test_custom_lane_width(self):
        """Test setting custom lane width."""
        lane = Lane(id=1, width=3.0)
        assert lane.width == 3.0

    def test_center_lane_zero_width(self):
        """Test that center lane has zero width."""
        center = Lane(id=0, lane_type=LaneType.NONE, width=0.0)
        assert center.width == 0.0

    def test_narrow_lane(self):
        """Test narrow lane (e.g., bike lane)."""
        bike_lane = Lane(id=1, lane_type=LaneType.BIKING, width=1.5)
        assert bike_lane.width == 1.5

    def test_wide_lane(self):
        """Test wide lane (e.g., truck lane)."""
        wide_lane = Lane(id=-1, lane_type=LaneType.DRIVING, width=4.0)
        assert wide_lane.width == 4.0


class TestRoadMarkTypes:
    """Test road mark types on lanes."""

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
        lane = Lane(id=1, road_mark_type=mark_type)
        assert lane.road_mark_type == mark_type

    def test_default_road_mark_solid(self):
        """Test default road mark is solid."""
        lane = Lane(id=1)
        assert lane.road_mark_type == RoadMarkType.SOLID

    def test_broken_line_between_lanes(self):
        """Test broken line (common between driving lanes)."""
        lane = Lane(id=-1, road_mark_type=RoadMarkType.BROKEN)
        assert lane.road_mark_type == RoadMarkType.BROKEN

    def test_solid_line_at_edge(self):
        """Test solid line (common at road edge)."""
        lane = Lane(id=-2, road_mark_type=RoadMarkType.SOLID)
        assert lane.road_mark_type == RoadMarkType.SOLID


class TestLaneBoundaries:
    """Test lane boundary polyline references."""

    def test_lane_without_boundaries(self):
        """Test lane with no explicit boundaries."""
        lane = Lane(id=1)

        assert lane.left_boundary_id is None
        assert lane.right_boundary_id is None

    def test_lane_with_left_boundary(self):
        """Test lane with left boundary polyline."""
        lane = Lane(id=1, left_boundary_id="poly_left_1")

        assert lane.left_boundary_id == "poly_left_1"
        assert lane.right_boundary_id is None

    def test_lane_with_right_boundary(self):
        """Test lane with right boundary polyline."""
        lane = Lane(id=1, right_boundary_id="poly_right_1")

        assert lane.right_boundary_id == "poly_right_1"
        assert lane.left_boundary_id is None

    def test_lane_with_both_boundaries(self):
        """Test lane with both left and right boundaries."""
        lane = Lane(
            id=-1,
            left_boundary_id="poly_left",
            right_boundary_id="poly_right"
        )

        assert lane.left_boundary_id == "poly_left"
        assert lane.right_boundary_id == "poly_right"


class TestLaneSerialization:
    """Test lane to_dict/from_dict serialization."""

    def test_lane_to_dict(self):
        """Test converting lane to dictionary."""
        lane = Lane(
            id=-1,
            lane_type=LaneType.DRIVING,
            road_mark_type=RoadMarkType.BROKEN,
            width=3.5
        )

        data = lane.to_dict()

        assert data['id'] == -1
        assert data['lane_type'] == 'driving'
        assert data['road_mark_type'] == 'broken'
        assert data['width'] == 3.5
        assert data['left_boundary_id'] is None
        assert data['right_boundary_id'] is None

    def test_lane_to_dict_with_boundaries(self):
        """Test serializing lane with boundaries."""
        lane = Lane(
            id=1,
            lane_type=LaneType.DRIVING,
            road_mark_type=RoadMarkType.SOLID,
            width=3.0,
            left_boundary_id="boundary_left",
            right_boundary_id="boundary_right"
        )

        data = lane.to_dict()

        assert data['left_boundary_id'] == "boundary_left"
        assert data['right_boundary_id'] == "boundary_right"

    def test_lane_from_dict(self):
        """Test creating lane from dictionary."""
        data = {
            'id': -2,
            'lane_type': 'driving',
            'road_mark_type': 'solid',
            'width': 3.5,
            'left_boundary_id': None,
            'right_boundary_id': None
        }

        lane = Lane.from_dict(data)

        assert lane.id == -2
        assert lane.lane_type == LaneType.DRIVING
        assert lane.road_mark_type == RoadMarkType.SOLID
        assert lane.width == 3.5

    def test_lane_from_dict_with_boundaries(self):
        """Test creating lane with boundaries from dict."""
        data = {
            'id': 1,
            'lane_type': 'biking',
            'road_mark_type': 'broken',
            'width': 1.5,
            'left_boundary_id': 'left_poly',
            'right_boundary_id': 'right_poly'
        }

        lane = Lane.from_dict(data)

        assert lane.left_boundary_id == 'left_poly'
        assert lane.right_boundary_id == 'right_poly'

    def test_lane_roundtrip_serialization(self, sample_lane_left: Lane):
        """Test lane → dict → lane preserves data."""
        data = sample_lane_left.to_dict()
        restored = Lane.from_dict(data)

        assert restored.id == sample_lane_left.id
        assert restored.lane_type == sample_lane_left.lane_type
        assert restored.road_mark_type == sample_lane_left.road_mark_type
        assert restored.width == pytest.approx(sample_lane_left.width)


class TestLaneComparison:
    """Test lane comparison and sorting."""

    def test_lanes_can_be_sorted_by_id(self):
        """Test that lanes can be sorted by ID for display."""
        lanes = [
            Lane(id=-2),
            Lane(id=1),
            Lane(id=0, lane_type=LaneType.NONE),
            Lane(id=-1),
            Lane(id=2),
        ]

        # Sort descending (left to right)
        sorted_lanes = sorted(lanes, key=lambda l: l.id, reverse=True)

        assert sorted_lanes[0].id == 2  # Leftmost
        assert sorted_lanes[1].id == 1
        assert sorted_lanes[2].id == 0  # Center
        assert sorted_lanes[3].id == -1
        assert sorted_lanes[4].id == -2  # Rightmost

    def test_lanes_grouped_by_side(self):
        """Test grouping lanes by left/center/right."""
        lanes = [
            Lane(id=-2),
            Lane(id=1),
            Lane(id=0, lane_type=LaneType.NONE),
            Lane(id=-1),
            Lane(id=2),
        ]

        left_lanes = [l for l in lanes if l.id > 0]
        center_lanes = [l for l in lanes if l.id == 0]
        right_lanes = [l for l in lanes if l.id < 0]

        assert len(left_lanes) == 2
        assert len(center_lanes) == 1
        assert len(right_lanes) == 2

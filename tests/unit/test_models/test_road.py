"""
Unit tests for Road model.

Tests road creation, polyline management, lane sections, and serialization.
"""

import pytest
from typing import List

from orbit.models import (
    Road, RoadType, LaneInfo, Lane, LaneType, LaneSection,
    Polyline, LineType, RoadMarkType
)


class TestRoadCreation:
    """Test road initialization and basic properties."""

    def test_empty_road_creation(self):
        """Test creating a road with minimal parameters."""
        road = Road()

        assert road.name == "Unnamed Road"
        assert road.polyline_ids == []
        assert road.centerline_id is None
        assert road.road_type == RoadType.UNKNOWN
        assert road.speed_limit is None
        assert road.junction_id is None

    def test_road_default_id_is_empty(self):
        """Test that roads default to empty string ID."""
        road = Road()

        assert road.id == ""

    def test_road_with_properties(self):
        """Test creating road with properties."""
        road = Road(
            name="Main Street",
            road_type=RoadType.TOWN,
            speed_limit=50
        )

        assert road.name == "Main Street"
        assert road.road_type == RoadType.TOWN
        assert road.speed_limit == 50

    def test_sample_road_fixture(self, sample_road: Road):
        """Test sample road fixture."""
        assert sample_road.name == "Test Road"
        assert sample_road.road_type == RoadType.TOWN
        assert sample_road.centerline_id is not None
        assert len(sample_road.polyline_ids) == 3  # centerline + 2 boundaries
        assert len(sample_road.lane_sections) == 1


class TestPolylineManagement:
    """Test adding and removing polylines from roads."""

    def test_add_polyline(self):
        """Test adding polyline to road."""
        road = Road()
        poly_id = "test-polyline-id"

        road.add_polyline(poly_id)

        assert len(road.polyline_ids) == 1
        assert road.polyline_ids[0] == poly_id

    def test_add_multiple_polylines(self):
        """Test adding multiple polylines."""
        road = Road()

        road.add_polyline("poly1")
        road.add_polyline("poly2")
        road.add_polyline("poly3")

        assert len(road.polyline_ids) == 3
        assert "poly1" in road.polyline_ids
        assert "poly2" in road.polyline_ids
        assert "poly3" in road.polyline_ids

    def test_add_duplicate_polyline_ignored(self):
        """Test that adding same polyline twice doesn't duplicate it."""
        road = Road()
        poly_id = "test-polyline"

        road.add_polyline(poly_id)
        road.add_polyline(poly_id)  # Add again

        assert len(road.polyline_ids) == 1

    def test_remove_polyline(self):
        """Test removing polyline from road."""
        road = Road()
        road.add_polyline("poly1")
        road.add_polyline("poly2")

        road.remove_polyline("poly1")

        assert len(road.polyline_ids) == 1
        assert "poly1" not in road.polyline_ids
        assert "poly2" in road.polyline_ids

    def test_remove_nonexistent_polyline_does_nothing(self):
        """Test removing non-existent polyline doesn't crash."""
        road = Road()
        road.add_polyline("poly1")

        road.remove_polyline("nonexistent")

        assert len(road.polyline_ids) == 1


class TestRoadValidation:
    """Test road validation methods."""

    def test_road_with_no_polylines_is_invalid(self):
        """Test that road with no polylines is invalid."""
        road = Road()
        assert road.is_valid() is False

    def test_road_with_polylines_is_valid(self):
        """Test that road with polylines is valid."""
        road = Road()
        road.add_polyline("poly1")
        assert road.is_valid() is True

    def test_road_without_centerline_not_valid_for_export(self):
        """Test that road without centerline can't be exported."""
        road = Road()
        road.add_polyline("boundary1")
        # No centerline set

        assert road.is_valid_for_export() is False

    def test_road_with_centerline_and_sections_valid_for_export(self, sample_road: Road):
        """Test that road with centerline and sections can be exported."""
        assert sample_road.is_valid_for_export() is True

    def test_road_with_centerline_valid_for_export(self):
        """Test that road with centerline can be exported."""
        road = Road(centerline_id="centerline1")
        road.add_polyline("centerline1")

        # Having a centerline is sufficient for is_valid_for_export
        # (lane sections are checked elsewhere in export process)
        assert road.is_valid_for_export() is True


class TestLaneSections:
    """Test lane section management."""

    def test_road_with_single_section(self, sample_road: Road):
        """Test road with one lane section."""
        assert len(sample_road.lane_sections) == 1

        section = sample_road.lane_sections[0]
        assert section.section_number == 1
        assert section.s_start == 0.0
        assert section.s_end == 500.0

    def test_road_with_multiple_sections(self, complex_road: Road):
        """Test road with multiple lane sections."""
        assert len(complex_road.lane_sections) == 2

        section1 = complex_road.lane_sections[0]
        section2 = complex_road.lane_sections[1]

        assert section1.section_number == 1
        assert section2.section_number == 2
        assert section1.s_end == section2.s_start  # Adjacent sections

    def test_get_section_by_number(self, complex_road: Road):
        """Test retrieving section by number."""
        section = complex_road.get_section(1)

        assert section is not None
        assert section.section_number == 1

    def test_get_nonexistent_section_returns_none(self, sample_road: Road):
        """Test that getting non-existent section returns None."""
        section = sample_road.get_section(999)
        assert section is None

    def test_get_section_at_s_coordinate(self, complex_road: Road):
        """Test getting section that contains s-coordinate."""
        # Section 1: s=0-300, Section 2: s=300-900
        section = complex_road.get_section_at_s(150.0)

        assert section is not None
        assert section.section_number == 1

        section = complex_road.get_section_at_s(500.0)

        assert section is not None
        assert section.section_number == 2

    def test_get_section_at_s_outside_range_returns_none(self, sample_road: Road):
        """Test that s-coordinate outside range returns None."""
        section = sample_road.get_section_at_s(10000.0)
        assert section is None


class TestLaneInfo:
    """Test LaneInfo dataclass."""

    def test_default_lane_info(self):
        """Test default lane info values."""
        lane_info = LaneInfo()

        assert lane_info.left_count == 1
        assert lane_info.right_count == 1
        assert lane_info.lane_width == 3.5
        assert lane_info.lane_widths is None

    def test_custom_lane_info(self):
        """Test custom lane info values."""
        lane_info = LaneInfo(
            left_count=2,
            right_count=3,
            lane_width=3.0,
            lane_widths=[3.5, 3.5, 3.0]
        )

        assert lane_info.left_count == 2
        assert lane_info.right_count == 3
        assert lane_info.lane_width == 3.0
        assert lane_info.lane_widths == [3.5, 3.5, 3.0]


class TestRoadTypes:
    """Test different road types."""

    @pytest.mark.parametrize("road_type", [
        RoadType.UNKNOWN,
        RoadType.RURAL,
        RoadType.MOTORWAY,
        RoadType.TOWN,
        RoadType.LOW_SPEED,
        RoadType.PEDESTRIAN,
        RoadType.BICYCLE,
    ])
    def test_road_types(self, road_type: RoadType):
        """Test various road types."""
        road = Road(road_type=road_type)
        assert road.road_type == road_type


class TestRoadConnections:
    """Test road predecessor/successor connections."""

    def test_road_with_no_connections(self):
        """Test road without predecessor or successor."""
        road = Road()

        assert road.predecessor_id is None
        assert road.successor_id is None

    def test_road_with_predecessor(self):
        """Test road with predecessor connection."""
        road = Road(
            predecessor_id="road_1",
            predecessor_contact="end"
        )

        assert road.predecessor_id == "road_1"
        assert road.predecessor_contact == "end"

    def test_road_with_successor(self):
        """Test road with successor connection."""
        road = Road(
            successor_id="road_2",
            successor_contact="start"
        )

        assert road.successor_id == "road_2"
        assert road.successor_contact == "start"

    def test_road_with_both_connections(self):
        """Test road connected to predecessor and successor."""
        road = Road(
            predecessor_id="road_1",
            predecessor_contact="end",
            successor_id="road_2",
            successor_contact="start"
        )

        assert road.predecessor_id == "road_1"
        assert road.successor_id == "road_2"


class TestRoadSerialization:
    """Test road to_dict/from_dict serialization."""

    def test_road_to_dict(self, sample_road: Road):
        """Test converting road to dictionary."""
        data = sample_road.to_dict()

        assert 'id' in data
        assert 'name' in data
        assert 'polyline_ids' in data
        assert 'centerline_id' in data
        assert 'road_type' in data
        assert 'lane_info' in data
        assert 'lane_sections' in data
        assert 'speed_limit' in data

        assert data['name'] == sample_road.name
        assert data['road_type'] == sample_road.road_type.value
        assert len(data['lane_sections']) == len(sample_road.lane_sections)

    def test_road_from_dict(self):
        """Test creating road from dictionary."""
        data = {
            'id': 'test-road-id',
            'name': 'Test Road',
            'polyline_ids': ['poly1', 'poly2'],
            'centerline_id': 'poly1',
            'road_type': 'town',
            'lane_info': {
                'left_count': 1,
                'right_count': 1,
                'lane_width': 3.5
            },
            'lane_sections': [
                {
                    'section_number': 1,
                    's_start': 0.0,
                    's_end': 100.0,
                    'single_side': None,
                    'lanes': [
                        {'id': 1, 'lane_type': 'driving', 'width': 3.5, 'road_mark_type': 'solid'},
                        {'id': 0, 'lane_type': 'none', 'width': 0.0, 'road_mark_type': 'none'},
                        {'id': -1, 'lane_type': 'driving', 'width': 3.5, 'road_mark_type': 'broken'}
                    ]
                }
            ],
            'lanes': [],
            'speed_limit': 50
        }

        road = Road.from_dict(data)

        assert road.id == 'test-road-id'
        assert road.name == 'Test Road'
        assert road.centerline_id == 'poly1'
        assert road.road_type == RoadType.TOWN
        assert road.speed_limit == 50
        assert len(road.lane_sections) == 1

    def test_road_roundtrip_serialization(self, sample_road: Road):
        """Test road → dict → road preserves data."""
        data = sample_road.to_dict()
        restored = Road.from_dict(data)

        assert restored.id == sample_road.id
        assert restored.name == sample_road.name
        assert restored.centerline_id == sample_road.centerline_id
        assert restored.road_type == sample_road.road_type
        assert restored.speed_limit == sample_road.speed_limit
        assert len(restored.lane_sections) == len(sample_road.lane_sections)


class TestBackwardCompatibility:
    """Test backward compatibility with old road format."""

    def test_load_road_with_old_lanes_format(self):
        """Test loading road with old 'lanes' field migrates to lane_sections."""
        # Old format: had 'lanes' but no 'lane_sections'
        old_data = {
            'id': 'old-road',
            'name': 'Old Road',
            'polyline_ids': ['poly1'],
            'centerline_id': 'poly1',
            'road_type': 'town',
            'lane_info': {
                'left_count': 1,
                'right_count': 1,
                'lane_width': 3.5
            },
            'lanes': [
                {'id': 1, 'lane_type': 'driving', 'width': 3.5, 'road_mark_type': 'solid'},
                {'id': 0, 'lane_type': 'none', 'width': 0.0, 'road_mark_type': 'none'},
                {'id': -1, 'lane_type': 'driving', 'width': 3.5, 'road_mark_type': 'broken'}
            ]
        }

        road = Road.from_dict(old_data)

        # Should be migrated to lane_sections
        assert len(road.lane_sections) == 1
        section = road.lane_sections[0]
        assert section.section_number == 1
        assert len(section.lanes) == 3  # Migrated lanes

    def test_load_road_without_lanes_generates_default(self):
        """Test that road without lanes generates default lane section."""
        minimal_data = {
            'id': 'minimal-road',
            'name': 'Minimal Road',
            'centerline_id': 'poly1',
            'polyline_ids': ['poly1'],
            'road_type': 'town'
        }

        road = Road.from_dict(minimal_data)

        # Should generate default lanes
        assert len(road.lane_sections) > 0

    def test_new_format_with_lane_sections_preferred(self):
        """Test that new format with lane_sections is used over old lanes."""
        data = {
            'id': 'new-road',
            'name': 'New Road',
            'polyline_ids': ['poly1'],
            'centerline_id': 'poly1',
            'road_type': 'town',
            'lane_sections': [
                {
                    'section_number': 1,
                    's_start': 0.0,
                    's_end': 200.0,
                    'lanes': [
                        {'id': 0, 'lane_type': 'none', 'width': 0.0, 'road_mark_type': 'none'}
                    ]
                }
            ],
            'lanes': [  # Old format (should be ignored)
                {'id': 1, 'lane_type': 'driving', 'width': 3.5, 'road_mark_type': 'solid'}
            ]
        }

        road = Road.from_dict(data)

        # New format (lane_sections) should take precedence
        assert len(road.lane_sections) == 1
        assert len(road.lane_sections[0].lanes) == 1  # Only center lane from new format


class TestSectionBoundaryManagement:
    """Test section boundary and s-coordinate management."""

    def test_calculate_centerline_s_coordinates(self):
        """Test s-coordinate calculation along centerline."""
        road = Road()
        points = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0)]

        s_coords = road.calculate_centerline_s_coordinates(points)

        assert len(s_coords) == 3
        assert s_coords[0] == 0.0
        assert s_coords[1] == pytest.approx(100.0)
        assert s_coords[2] == pytest.approx(200.0)

    def test_calculate_s_coordinates_empty_points(self):
        """Test s-coordinate calculation with empty points."""
        road = Road()
        s_coords = road.calculate_centerline_s_coordinates([])

        assert s_coords == []

    def test_split_section_at_point(self):
        """Test splitting a section at a point index."""
        from orbit.models import Lane, LaneType, LaneSection
        road = Road()
        # Create a section with 3 lanes
        section = LaneSection(
            section_number=1,
            s_start=0.0,
            s_end=300.0,
            lanes=[
                Lane(id=0, lane_type=LaneType.NONE, width=0.0),
                Lane(id=1, lane_type=LaneType.DRIVING, width=3.5),
                Lane(id=-1, lane_type=LaneType.DRIVING, width=3.5)
            ]
        )
        road.lane_sections = [section]

        # Centerline points: 300 pixels total
        centerline_points = [(0.0, 0.0), (100.0, 0.0), (200.0, 0.0), (300.0, 0.0)]

        # Split at point 2 (s=200)
        success = road.split_section_at_point(2, centerline_points)

        assert success
        assert len(road.lane_sections) == 2
        # Both sections should have lanes
        assert len(road.lane_sections[0].lanes) == 3
        assert len(road.lane_sections[1].lanes) == 3
        # Section 1 ends where section 2 starts
        assert road.lane_sections[0].s_end == road.lane_sections[1].s_start

    def test_split_section_invalid_point_index(self):
        """Test splitting at invalid point index fails."""
        from orbit.models import LaneSection
        road = Road()
        road.lane_sections = [LaneSection(section_number=1, s_start=0.0, s_end=100.0)]
        centerline_points = [(0.0, 0.0), (100.0, 0.0)]

        # Invalid point index
        success = road.split_section_at_point(10, centerline_points)
        assert not success
        assert len(road.lane_sections) == 1

    def test_update_section_boundaries(self):
        """Test updating section boundaries after centerline changes."""
        from orbit.models import LaneSection
        road = Road()
        # Two sections, second has end_point_index=None (last section)
        road.lane_sections = [
            LaneSection(section_number=1, s_start=0.0, s_end=100.0, end_point_index=1),
            LaneSection(section_number=2, s_start=100.0, s_end=200.0, end_point_index=None)
        ]

        # New centerline with different distances
        centerline_points = [(0.0, 0.0), (150.0, 0.0), (300.0, 0.0)]

        road.update_section_boundaries(centerline_points)

        # Section 1 ends at point 1 (s=150)
        assert road.lane_sections[0].s_end == pytest.approx(150.0)
        # Section 2 starts where section 1 ends, ends at last point
        assert road.lane_sections[1].s_start == pytest.approx(150.0)
        assert road.lane_sections[1].s_end == pytest.approx(300.0)

    def test_adjust_section_indices_after_insertion(self):
        """Test adjusting section indices when point is inserted."""
        from orbit.models import LaneSection
        road = Road()
        road.lane_sections = [
            LaneSection(section_number=1, s_start=0.0, s_end=100.0, end_point_index=2),
            LaneSection(section_number=2, s_start=100.0, s_end=200.0, end_point_index=4)
        ]

        # Insert point at index 1
        road.adjust_section_indices_after_insertion(1)

        # Indices >= 1 should be incremented
        assert road.lane_sections[0].end_point_index == 3
        assert road.lane_sections[1].end_point_index == 5

    def test_adjust_section_indices_after_deletion(self):
        """Test adjusting section indices when point is deleted."""
        from orbit.models import LaneSection
        road = Road()
        road.lane_sections = [
            LaneSection(section_number=1, s_start=0.0, s_end=100.0, end_point_index=3),
            LaneSection(section_number=2, s_start=100.0, s_end=200.0, end_point_index=5)
        ]

        # Delete point at index 2
        road.adjust_section_indices_after_deletion(2)

        # Indices > 2 should be decremented
        assert road.lane_sections[0].end_point_index == 2
        assert road.lane_sections[1].end_point_index == 4

    def test_adjust_indices_deletion_at_boundary(self):
        """Test that deleting boundary point sets index to None."""
        from orbit.models import LaneSection
        road = Road()
        road.lane_sections = [
            LaneSection(section_number=1, s_start=0.0, s_end=100.0, end_point_index=2)
        ]

        # Delete the boundary point
        road.adjust_section_indices_after_deletion(2)

        # Boundary point was deleted, index should be None
        assert road.lane_sections[0].end_point_index is None

    def test_delete_section(self):
        """Test deleting a section."""
        from orbit.models import LaneSection
        road = Road()
        road.lane_sections = [
            LaneSection(section_number=1, s_start=0.0, s_end=100.0),
            LaneSection(section_number=2, s_start=100.0, s_end=200.0)
        ]

        success = road.delete_section(1)

        assert success
        assert len(road.lane_sections) == 1
        assert road.lane_sections[0].section_number == 1  # Renumbered

    def test_delete_last_section_fails(self):
        """Test that deleting the only section fails."""
        from orbit.models import LaneSection
        road = Road()
        road.lane_sections = [
            LaneSection(section_number=1, s_start=0.0, s_end=100.0)
        ]

        success = road.delete_section(1)

        assert not success
        assert len(road.lane_sections) == 1

    def test_renumber_sections(self):
        """Test section renumbering."""
        from orbit.models import LaneSection
        road = Road()
        road.lane_sections = [
            LaneSection(section_number=5, s_start=0.0, s_end=100.0),
            LaneSection(section_number=10, s_start=100.0, s_end=200.0),
            LaneSection(section_number=15, s_start=200.0, s_end=300.0)
        ]

        road.renumber_sections()

        assert road.lane_sections[0].section_number == 1
        assert road.lane_sections[1].section_number == 2
        assert road.lane_sections[2].section_number == 3


class TestRoadMissingCoverage:
    """Additional tests for full coverage."""

    def test_has_centerline_true(self):
        """Test has_centerline returns True when centerline is set."""
        road = Road(centerline_id="centerline1")
        road.add_polyline("centerline1")
        assert road.has_centerline() is True

    def test_has_centerline_false_no_id(self):
        """Test has_centerline returns False when no centerline ID."""
        road = Road()
        road.add_polyline("poly1")
        assert road.has_centerline() is False

    def test_has_centerline_false_not_in_polylines(self):
        """Test has_centerline returns False when centerline not in polylines."""
        road = Road(centerline_id="centerline1")
        road.add_polyline("other_poly")
        assert road.has_centerline() is False

    def test_total_lanes(self):
        """Test total_lanes calculation."""
        road = Road()
        road.lane_info = LaneInfo(left_count=2, right_count=3)
        assert road.total_lanes() == 5

    def test_total_lanes_default(self):
        """Test total_lanes with default lane info."""
        road = Road()
        assert road.total_lanes() == 2  # 1 left + 1 right

    def test_get_lane_from_specific_section(self):
        """Test get_lane with specific section number."""
        from orbit.models import Lane, LaneSection
        road = Road()
        road.lane_sections = [
            LaneSection(
                section_number=1,
                s_start=0.0,
                s_end=100.0,
                lanes=[
                    Lane(id=0, lane_type=LaneType.NONE, width=0.0),
                    Lane(id=-1, lane_type=LaneType.DRIVING, width=3.5)
                ]
            ),
            LaneSection(
                section_number=2,
                s_start=100.0,
                s_end=200.0,
                lanes=[
                    Lane(id=0, lane_type=LaneType.NONE, width=0.0),
                    Lane(id=-1, lane_type=LaneType.DRIVING, width=4.0)  # Different width
                ]
            )
        ]

        lane = road.get_lane(-1, section_number=2)
        assert lane is not None
        assert lane.width == 4.0

    def test_get_lane_section_not_found(self):
        """Test get_lane returns None when section not found."""
        from orbit.models import Lane, LaneSection
        road = Road()
        road.lane_sections = [
            LaneSection(
                section_number=1,
                s_start=0.0,
                s_end=100.0,
                lanes=[Lane(id=0, lane_type=LaneType.NONE, width=0.0)]
            )
        ]

        lane = road.get_lane(-1, section_number=99)
        assert lane is None

    def test_get_lane_not_found_in_section(self):
        """Test get_lane returns None when lane not in specified section."""
        from orbit.models import Lane, LaneSection
        road = Road()
        road.lane_sections = [
            LaneSection(
                section_number=1,
                s_start=0.0,
                s_end=100.0,
                lanes=[Lane(id=0, lane_type=LaneType.NONE, width=0.0)]
            )
        ]

        lane = road.get_lane(-1, section_number=1)
        assert lane is None

    def test_get_section_containing_point(self):
        """Test get_section_containing_point."""
        from orbit.models import LaneSection
        road = Road()
        road.lane_sections = [
            LaneSection(section_number=1, s_start=0.0, s_end=100.0),
            LaneSection(section_number=2, s_start=100.0, s_end=200.0)
        ]
        centerline_points = [(0.0, 0.0), (100.0, 0.0), (200.0, 0.0)]

        section = road.get_section_containing_point(1, centerline_points)
        assert section is not None
        assert section.section_number == 2

    def test_get_section_containing_point_invalid_index(self):
        """Test get_section_containing_point with invalid index."""
        from orbit.models import LaneSection
        road = Road()
        road.lane_sections = [LaneSection(section_number=1, s_start=0.0, s_end=100.0)]
        centerline_points = [(0.0, 0.0), (100.0, 0.0)]

        section = road.get_section_containing_point(10, centerline_points)
        assert section is None

        section = road.get_section_containing_point(-1, centerline_points)
        assert section is None

    def test_split_section_no_section_found(self):
        """Test split_section_at_point when no section contains point."""
        from orbit.models import LaneSection
        road = Road()
        road.lane_sections = [
            LaneSection(section_number=1, s_start=0.0, s_end=50.0)
        ]
        # Point at s=100 is outside all sections
        centerline_points = [(0.0, 0.0), (50.0, 0.0), (100.0, 0.0)]

        success = road.split_section_at_point(2, centerline_points)
        assert success is False

    def test_delete_section_not_found(self):
        """Test delete_section when section not found."""
        from orbit.models import LaneSection
        road = Road()
        road.lane_sections = [
            LaneSection(section_number=1, s_start=0.0, s_end=100.0),
            LaneSection(section_number=2, s_start=100.0, s_end=200.0)
        ]

        success = road.delete_section(99)
        assert success is False
        assert len(road.lane_sections) == 2

    def test_update_section_boundaries_empty(self):
        """Test update_section_boundaries with empty data."""
        road = Road()
        road.lane_sections = []
        road.update_section_boundaries([])  # Should not raise

        road.lane_sections = [LaneSection(section_number=1, s_start=0.0, s_end=100.0)]
        road.update_section_boundaries([])  # Empty points - should not raise

    def test_update_section_boundaries_initializes_end_point_index(self):
        """Test that update_section_boundaries initializes end_point_index for legacy sections."""
        from orbit.models import LaneSection
        road = Road()
        # Section without end_point_index (legacy)
        road.lane_sections = [
            LaneSection(section_number=1, s_start=0.0, s_end=50.0, end_point_index=None),
            LaneSection(section_number=2, s_start=50.0, s_end=100.0, end_point_index=None)
        ]
        centerline_points = [(0.0, 0.0), (50.0, 0.0), (100.0, 0.0)]

        road.update_section_boundaries(centerline_points)

        # First section should now have end_point_index
        assert road.lane_sections[0].end_point_index == 1

    def test_to_dict_with_optional_fields(self):
        """Test to_dict includes optional fields when set."""
        road = Road(
            elevation_profile=[(0.0, 10.0, 0.1, 0.0, 0.0), (100.0, 10.5, 0.05, 0.0, 0.0)],
            superelevation_profile=[(0.0, 0.0, 0.02, 0.0, 0.0)],
            lane_offset=[(0.0, 0.5, 0.0, 0.0, 0.0)],
            surface_crg=[{"file": "road.crg", "s_start": 0.0, "s_end": 100.0}]
        )
        road.add_polyline("poly1")

        data = road.to_dict()

        assert 'elevation_profile' in data
        assert len(data['elevation_profile']) == 2
        assert 'superelevation_profile' in data
        assert 'lane_offset' in data
        assert 'surface_crg' in data

    def test_repr(self):
        """Test __repr__ method."""
        road = Road(name="Test Highway")
        road.add_polyline("poly1")
        road.add_polyline("poly2")

        repr_str = repr(road)

        assert "Road(" in repr_str
        assert "Test Highway" in repr_str
        assert "polylines=2" in repr_str

    def test_generate_lanes(self):
        """Test generate_lanes creates proper lane structure."""
        road = Road()
        road.lane_info = LaneInfo(left_count=2, right_count=2, lane_width=3.5)

        road.generate_lanes(centerline_length=500.0)

        assert len(road.lane_sections) == 1
        section = road.lane_sections[0]
        assert section.s_start == 0.0
        assert section.s_end == 500.0

        # Should have: 0 (center), -1, -2 (right), 1, 2 (left)
        lane_ids = [lane.id for lane in section.lanes]
        assert 0 in lane_ids
        assert -1 in lane_ids
        assert -2 in lane_ids
        assert 1 in lane_ids
        assert 2 in lane_ids

    def test_distribute_lane_sections_for_split(self):
        """Test distribute_lane_sections_for_split method."""
        from orbit.models import Lane, LaneSection
        road = Road()
        road.lane_sections = [
            LaneSection(
                section_number=1,
                s_start=0.0,
                s_end=100.0,
                end_point_index=2,
                lanes=[
                    Lane(id=0, lane_type=LaneType.NONE, width=0.0),
                    Lane(id=-1, lane_type=LaneType.DRIVING, width=3.5)
                ]
            ),
            LaneSection(
                section_number=2,
                s_start=100.0,
                s_end=200.0,
                end_point_index=None,
                lanes=[
                    Lane(id=0, lane_type=LaneType.NONE, width=0.0),
                    Lane(id=-1, lane_type=LaneType.DRIVING, width=3.5)
                ]
            )
        ]

        # Split at s=150 (in the middle of section 2)
        sections_road1, sections_road2 = road.distribute_lane_sections_for_split(150.0, 3)

        # Section 1 entirely in road1
        assert len(sections_road1) >= 1
        # Sections should be renumbered
        assert sections_road1[0].section_number == 1

        # Road2 should have sections with adjusted s-coordinates
        assert len(sections_road2) >= 1
        assert sections_road2[0].s_start == 0.0

    def test_distribute_lane_sections_section_before_split(self):
        """Test section entirely before split goes to road1."""
        from orbit.models import Lane, LaneSection
        road = Road()
        road.lane_sections = [
            LaneSection(
                section_number=1,
                s_start=0.0,
                s_end=100.0,
                lanes=[Lane(id=0, lane_type=LaneType.NONE, width=0.0)]
            ),
            LaneSection(
                section_number=2,
                s_start=100.0,
                s_end=200.0,
                lanes=[Lane(id=0, lane_type=LaneType.NONE, width=0.0)]
            )
        ]

        sections_road1, sections_road2 = road.distribute_lane_sections_for_split(100.0, 2)

        # Section 1 (s=0-100) entirely in road1
        assert any(s.s_end <= 100.0 for s in sections_road1)

    def test_distribute_lane_sections_section_after_split(self):
        """Test section entirely after split goes to road2 with adjusted coords."""
        from orbit.models import Lane, LaneSection
        road = Road()
        road.lane_sections = [
            LaneSection(
                section_number=1,
                s_start=0.0,
                s_end=50.0,
                lanes=[Lane(id=0, lane_type=LaneType.NONE, width=0.0)]
            ),
            LaneSection(
                section_number=2,
                s_start=50.0,
                s_end=150.0,
                end_point_index=3,
                lanes=[Lane(id=0, lane_type=LaneType.NONE, width=0.0)]
            )
        ]

        sections_road1, sections_road2 = road.distribute_lane_sections_for_split(50.0, 1)

        # Section 2 should be in road2 with s_start=0
        assert len(sections_road2) >= 1
        assert sections_road2[0].s_start == 0.0

    def test_distribute_lane_sections_empty_road1(self):
        """Test default section created when no sections for road1."""
        from orbit.models import Lane, LaneSection
        road = Road()
        road.lane_sections = [
            LaneSection(
                section_number=1,
                s_start=100.0,  # Section starts after split point
                s_end=200.0,
                lanes=[Lane(id=0, lane_type=LaneType.NONE, width=0.0)]
            )
        ]

        sections_road1, sections_road2 = road.distribute_lane_sections_for_split(50.0, 1)

        # Should create default section for road1
        assert len(sections_road1) >= 1

    def test_distribute_lane_sections_empty_road2(self):
        """Test default section created when no sections for road2."""
        from orbit.models import Lane, LaneSection
        road = Road()
        road.lane_sections = [
            LaneSection(
                section_number=1,
                s_start=0.0,
                s_end=50.0,  # Section ends before split point
                lanes=[Lane(id=0, lane_type=LaneType.NONE, width=0.0)]
            )
        ]

        sections_road1, sections_road2 = road.distribute_lane_sections_for_split(100.0, 2)

        # Should create default section for road2
        assert len(sections_road2) >= 1

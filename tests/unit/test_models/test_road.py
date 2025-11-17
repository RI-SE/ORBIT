"""
Unit tests for Road model.

Tests road creation, polyline management, lane sections, and serialization.
"""

import pytest
import uuid
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

    def test_road_auto_generates_id(self):
        """Test that roads automatically generate unique IDs."""
        road1 = Road()
        road2 = Road()

        assert road1.id != road2.id
        uuid.UUID(road1.id)  # Validate it's a UUID
        uuid.UUID(road2.id)

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

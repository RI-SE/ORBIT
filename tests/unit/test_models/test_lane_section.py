"""
Unit tests for LaneSection model.

Tests lane section creation, splitting, lane management, and serialization.
"""

import pytest
from typing import List

from orbit.models import LaneSection, Lane, LaneType, RoadMarkType


class TestLaneSectionCreation:
    """Test lane section initialization and basic properties."""

    def test_lane_section_creation(self):
        """Test creating a lane section with basic parameters."""
        section = LaneSection(
            section_number=1,
            s_start=0.0,
            s_end=100.0
        )

        assert section.section_number == 1
        assert section.s_start == 0.0
        assert section.s_end == 100.0
        assert section.single_side is None
        assert section.lanes == []
        assert section.end_point_index is None

    def test_lane_section_with_lanes(self, sample_lane_section: LaneSection):
        """Test lane section with lanes."""
        assert sample_lane_section.section_number == 1
        assert len(sample_lane_section.lanes) == 3
        assert sample_lane_section.end_point_index == 5

    def test_lane_section_with_single_side(self):
        """Test lane section with singleSide attribute."""
        section = LaneSection(
            section_number=1,
            s_start=0.0,
            s_end=100.0,
            single_side="left"
        )

        assert section.single_side == "left"


class TestLaneSectionDimensions:
    """Test lane section dimension calculations."""

    def test_get_length_pixels(self):
        """Test calculating section length in pixels."""
        section = LaneSection(
            section_number=1,
            s_start=0.0,
            s_end=150.0
        )

        assert section.get_length_pixels() == pytest.approx(150.0)

    def test_get_length_with_offset_start(self):
        """Test length calculation with non-zero start."""
        section = LaneSection(
            section_number=2,
            s_start=100.0,
            s_end=300.0
        )

        assert section.get_length_pixels() == pytest.approx(200.0)

    def test_contains_s_coordinate(self):
        """Test checking if s-coordinate is within section."""
        section = LaneSection(
            section_number=1,
            s_start=100.0,
            s_end=300.0
        )

        assert section.contains_s_coordinate(100.0) is True  # Start (inclusive)
        assert section.contains_s_coordinate(200.0) is True  # Middle
        assert section.contains_s_coordinate(299.9) is True  # Just before end
        assert section.contains_s_coordinate(300.0) is False  # End (exclusive)
        assert section.contains_s_coordinate(50.0) is False  # Before start
        assert section.contains_s_coordinate(400.0) is False  # After end


class TestLaneManagement:
    """Test adding, removing, and retrieving lanes."""

    def test_add_lane(self):
        """Test adding a lane to section."""
        section = LaneSection(
            section_number=1,
            s_start=0.0,
            s_end=100.0
        )

        lane = Lane(id=1, lane_type=LaneType.DRIVING, width=3.5)
        section.add_lane(lane)

        assert len(section.lanes) == 1
        assert section.lanes[0].id == 1

    def test_add_multiple_lanes(self):
        """Test adding multiple lanes."""
        section = LaneSection(
            section_number=1,
            s_start=0.0,
            s_end=100.0
        )

        section.add_lane(Lane(id=1, lane_type=LaneType.DRIVING))
        section.add_lane(Lane(id=0, lane_type=LaneType.NONE, width=0.0))
        section.add_lane(Lane(id=-1, lane_type=LaneType.DRIVING))

        assert len(section.lanes) == 3

    def test_add_lane_sorts_by_id(self):
        """Test that adding lanes maintains sorted order."""
        section = LaneSection(
            section_number=1,
            s_start=0.0,
            s_end=100.0
        )

        # Add in random order
        section.add_lane(Lane(id=-1))
        section.add_lane(Lane(id=2))
        section.add_lane(Lane(id=0, lane_type=LaneType.NONE))
        section.add_lane(Lane(id=1))

        # Should be sorted by ID
        lane_ids = [lane.id for lane in section.lanes]
        assert lane_ids == sorted(lane_ids)

    def test_add_lane_replaces_duplicate_id(self):
        """Test that adding lane with existing ID replaces it."""
        section = LaneSection(
            section_number=1,
            s_start=0.0,
            s_end=100.0
        )

        section.add_lane(Lane(id=1, width=3.0))
        section.add_lane(Lane(id=1, width=4.0))  # Replace

        assert len(section.lanes) == 1
        assert section.lanes[0].width == 4.0

    def test_remove_lane(self):
        """Test removing a lane by ID."""
        section = LaneSection(
            section_number=1,
            s_start=0.0,
            s_end=100.0
        )

        section.add_lane(Lane(id=1))
        section.add_lane(Lane(id=-1))

        section.remove_lane(1)

        assert len(section.lanes) == 1
        assert section.lanes[0].id == -1

    def test_remove_nonexistent_lane_does_nothing(self):
        """Test removing non-existent lane doesn't crash."""
        section = LaneSection(
            section_number=1,
            s_start=0.0,
            s_end=100.0
        )

        section.add_lane(Lane(id=1))
        section.remove_lane(999)  # Doesn't exist

        assert len(section.lanes) == 1

    def test_get_lane_by_id(self, sample_lane_section: LaneSection):
        """Test retrieving lane by ID."""
        lane = sample_lane_section.get_lane(1)

        assert lane is not None
        assert lane.id == 1
        assert lane.lane_type == LaneType.DRIVING

    def test_get_nonexistent_lane_returns_none(self, sample_lane_section: LaneSection):
        """Test getting non-existent lane returns None."""
        lane = sample_lane_section.get_lane(999)
        assert lane is None


class TestLaneSorting:
    """Test lane sorting and ordering."""

    def test_get_lanes_sorted_left_to_right(self):
        """Test getting lanes sorted left to right."""
        section = LaneSection(
            section_number=1,
            s_start=0.0,
            s_end=100.0
        )

        # Add in random order
        section.add_lane(Lane(id=-1))
        section.add_lane(Lane(id=2))
        section.add_lane(Lane(id=0, lane_type=LaneType.NONE))
        section.add_lane(Lane(id=1))
        section.add_lane(Lane(id=-2))

        sorted_lanes = section.get_lanes_sorted()

        # Should be: [2, 1, 0, -1, -2] (left to right)
        expected_ids = [2, 1, 0, -1, -2]
        actual_ids = [lane.id for lane in sorted_lanes]

        assert actual_ids == expected_ids


class TestSectionSplitting:
    """Test splitting lane sections."""

    def test_split_section_at_midpoint(self):
        """Test splitting a section at its midpoint."""
        section = LaneSection(
            section_number=1,
            s_start=0.0,
            s_end=200.0
        )
        section.add_lane(Lane(id=1, lane_type=LaneType.DRIVING, width=3.5))
        section.add_lane(Lane(id=0, lane_type=LaneType.NONE, width=0.0))
        section.add_lane(Lane(id=-1, lane_type=LaneType.DRIVING, width=3.5))

        first, second = section.split_at_s(s=100.0, new_section_number=2)

        # Check first section
        assert first.section_number == 1
        assert first.s_start == 0.0
        assert first.s_end == 100.0
        assert len(first.lanes) == 3

        # Check second section
        assert second.section_number == 2
        assert second.s_start == 100.0
        assert second.s_end == 200.0
        assert len(second.lanes) == 3

    def test_split_section_with_point_index(self):
        """Test splitting section tracks point indices."""
        section = LaneSection(
            section_number=1,
            s_start=0.0,
            s_end=200.0,
            end_point_index=10
        )
        section.add_lane(Lane(id=1))

        first, second = section.split_at_s(s=100.0, new_section_number=2, split_point_index=5)

        assert first.end_point_index == 5  # Split point
        assert second.end_point_index == 10  # Original end

    def test_split_section_duplicates_lanes(self):
        """Test that splitting duplicates lane properties."""
        section = LaneSection(
            section_number=1,
            s_start=0.0,
            s_end=200.0
        )
        section.add_lane(Lane(id=1, lane_type=LaneType.DRIVING, width=3.5))

        first, second = section.split_at_s(s=100.0, new_section_number=2)

        # Both sections should have lanes with same properties
        assert first.lanes[0].id == 1
        assert second.lanes[0].id == 1
        assert first.lanes[0].width == 3.5
        assert second.lanes[0].width == 3.5

        # But they should be independent copies
        first.lanes[0].width = 5.0
        assert second.lanes[0].width == 3.5  # Unchanged

    def test_split_section_preserves_single_side(self):
        """Test that splitting preserves singleSide attribute."""
        section = LaneSection(
            section_number=1,
            s_start=0.0,
            s_end=200.0,
            single_side="left"
        )
        section.add_lane(Lane(id=1))

        first, second = section.split_at_s(s=100.0, new_section_number=2)

        assert first.single_side == "left"
        assert second.single_side == "left"

    def test_split_at_invalid_s_raises_error(self):
        """Test that splitting at invalid s-coordinate raises error."""
        section = LaneSection(
            section_number=1,
            s_start=100.0,
            s_end=200.0
        )

        with pytest.raises(ValueError, match="not within section range"):
            section.split_at_s(s=50.0, new_section_number=2)  # Before start

        with pytest.raises(ValueError, match="not within section range"):
            section.split_at_s(s=300.0, new_section_number=2)  # After end

    def test_split_at_section_end_allowed(self):
        """Test that splitting at section end is allowed."""
        section = LaneSection(
            section_number=1,
            s_start=0.0,
            s_end=200.0
        )
        section.add_lane(Lane(id=1))

        # Should not raise error
        first, second = section.split_at_s(s=200.0, new_section_number=2)

        assert first.s_end == 200.0
        assert second.s_start == 200.0
        assert second.get_length_pixels() == 0.0


class TestSectionSerialization:
    """Test lane section to_dict/from_dict serialization."""

    def test_section_to_dict(self, sample_lane_section: LaneSection):
        """Test converting lane section to dictionary."""
        data = sample_lane_section.to_dict()

        assert 'section_number' in data
        assert 's_start' in data
        assert 's_end' in data
        assert 'single_side' in data
        assert 'lanes' in data
        assert 'end_point_index' in data

        assert data['section_number'] == 1
        assert data['s_start'] == 0.0
        assert data['s_end'] == 500.0
        assert len(data['lanes']) == 3

    def test_section_to_dict_with_single_side(self):
        """Test serializing section with singleSide."""
        section = LaneSection(
            section_number=1,
            s_start=0.0,
            s_end=100.0,
            single_side="right"
        )

        data = section.to_dict()

        assert data['single_side'] == "right"

    def test_section_from_dict(self):
        """Test creating section from dictionary."""
        data = {
            'section_number': 2,
            's_start': 100.0,
            's_end': 300.0,
            'single_side': None,
            'lanes': [
                {'id': 1, 'lane_type': 'driving', 'width': 3.5, 'road_mark_type': 'solid',
                 'left_boundary_id': None, 'right_boundary_id': None},
                {'id': 0, 'lane_type': 'none', 'width': 0.0, 'road_mark_type': 'none',
                 'left_boundary_id': None, 'right_boundary_id': None},
            ],
            'end_point_index': 7
        }

        section = LaneSection.from_dict(data)

        assert section.section_number == 2
        assert section.s_start == 100.0
        assert section.s_end == 300.0
        assert section.single_side is None
        assert len(section.lanes) == 2
        assert section.end_point_index == 7

    def test_section_from_dict_backward_compatible(self):
        """Test loading section without end_point_index (old format)."""
        data = {
            'section_number': 1,
            's_start': 0.0,
            's_end': 100.0,
            'lanes': []
        }

        section = LaneSection.from_dict(data)

        assert section.end_point_index is None  # Should handle missing field

    def test_section_roundtrip_serialization(self, sample_lane_section: LaneSection):
        """Test section → dict → section preserves data."""
        data = sample_lane_section.to_dict()
        restored = LaneSection.from_dict(data)

        assert restored.section_number == sample_lane_section.section_number
        assert restored.s_start == pytest.approx(sample_lane_section.s_start)
        assert restored.s_end == pytest.approx(sample_lane_section.s_end)
        assert restored.single_side == sample_lane_section.single_side
        assert len(restored.lanes) == len(sample_lane_section.lanes)
        assert restored.end_point_index == sample_lane_section.end_point_index


class TestTwoSectionFixture:
    """Test fixture with multiple sections."""

    def test_two_section_fixture(self, two_section_lane_sections: List[LaneSection]):
        """Test fixture with two sections."""
        assert len(two_section_lane_sections) == 2

        section1 = two_section_lane_sections[0]
        section2 = two_section_lane_sections[1]

        # Adjacent sections
        assert section1.s_end == section2.s_start

        # Section 2 has more lanes
        assert len(section2.lanes) > len(section1.lanes)

    def test_two_sections_cover_road(self, two_section_lane_sections: List[LaneSection]):
        """Test that two sections cover entire road length."""
        total_length = sum(s.get_length_pixels() for s in two_section_lane_sections)

        assert total_length == pytest.approx(900.0)  # 0-300 + 300-900

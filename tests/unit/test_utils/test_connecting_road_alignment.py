"""Tests for orbit.utils.connecting_road_alignment module."""

import pytest

from orbit.models.lane import Lane
from orbit.models.lane_section import LaneSection
from orbit.models.road import Road
from orbit.utils.connecting_road_alignment import _get_road_lane_width


class TestGetRoadLaneWidth:
    """Tests for _get_road_lane_width with contact_point parameter."""

    def _make_road_with_two_sections(self, first_width=3.0, last_width=4.0):
        """Create a road with two lane sections having different lane widths."""
        first_section = LaneSection(section_number=1, s_start=0.0, s_end=50.0)
        first_section.lanes = [
            Lane(id=0, width=0),
            Lane(id=-1, width=first_width),
        ]

        last_section = LaneSection(section_number=2, s_start=50.0, s_end=100.0)
        last_section.lanes = [
            Lane(id=0, width=0),
            Lane(id=-1, width=last_width),
        ]

        road = Road(id="r1", name="Test")
        road.lane_sections = [first_section, last_section]
        return road

    def test_default_contact_uses_last_section(self):
        """Default (contact_point='end') uses last section."""
        road = self._make_road_with_two_sections(first_width=3.0, last_width=4.0)
        assert _get_road_lane_width(road) == pytest.approx(4.0)

    def test_start_contact_uses_first_section(self):
        """contact_point='start' uses first section."""
        road = self._make_road_with_two_sections(first_width=3.0, last_width=4.0)
        assert _get_road_lane_width(road, "start") == pytest.approx(3.0)

    def test_end_contact_uses_last_section(self):
        """contact_point='end' uses last section."""
        road = self._make_road_with_two_sections(first_width=3.0, last_width=4.0)
        assert _get_road_lane_width(road, "end") == pytest.approx(4.0)

    def test_single_section_same_for_both(self):
        """Road with one section returns same width regardless of contact_point."""
        section = LaneSection(section_number=1, s_start=0.0, s_end=100.0)
        section.lanes = [Lane(id=0, width=0), Lane(id=-1, width=3.5)]
        road = Road(id="r1", name="Test")
        road.lane_sections = [section]

        assert _get_road_lane_width(road, "start") == pytest.approx(3.5)
        assert _get_road_lane_width(road, "end") == pytest.approx(3.5)

    def test_no_sections_fallback(self):
        """No lane sections falls back to lane_info or default."""
        road = Road(id="r1", name="Test")
        road.lane_sections = []
        assert _get_road_lane_width(road) == 3.5  # default

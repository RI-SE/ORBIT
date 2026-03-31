"""Tests for orbit.utils.connecting_road_alignment module."""

import pytest

from orbit.models.lane import Lane
from orbit.models.lane_section import LaneSection
from orbit.models.polyline import Polyline
from orbit.models.road import Road
from orbit.utils.connecting_road_alignment import (
    _compute_lane_alignment_shift,
    _get_road_lane_width,
)


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


class TestComputeLaneAlignmentShift:
    """Tests for heading-sign correction in _compute_lane_alignment_shift."""

    @staticmethod
    def _make_project_with_road(road_id, points, lane_width=3.5):
        """Create a project with one road having a centerline polyline."""
        from orbit.models.project import Project

        project = Project()
        polyline = Polyline(id=road_id, points=points, line_type="centerline")
        project.add_polyline(polyline)

        section = LaneSection(section_number=1, s_start=0.0, s_end=100.0)
        section.lanes = [
            Lane(id=0, width=0),
            Lane(id=-1, width=lane_width),
            Lane(id=1, width=lane_width),
        ]

        road = Road(id=road_id, name="Test Road", centerline_id=road_id)
        road.lane_sections = [section]
        project.add_road(road)
        return project

    def test_aligned_headings_no_sign_flip(self):
        """When CR and road headings are aligned, lane offset is applied normally."""
        # Road heading: rightward (positive X)
        project = self._make_project_with_road(
            "r1", [(0.0, 0.0), (100.0, 0.0)], lane_width=3.5
        )
        # CR also heading rightward at the connection (aligned)
        scale = 0.05  # 0.05 m/px
        shift = _compute_lane_alignment_shift(
            project=project,
            road_id="r1",
            contact_point="start",
            target_lane_id=-1,  # right lane on road
            cr_lane_id=-1,  # right lane on CR
            cr_lane_width=3.5,
            cr_endpoint=(0.0, 0.0),
            cr_fwd_p1=(0.0, 0.0),
            cr_fwd_p2=(10.0, 0.0),  # heading rightward = aligned
            scale=scale,
        )
        # Same lane on same side → no shift needed
        assert shift is None

    def test_opposite_headings_negates_cr_offset(self):
        """When CR heading is ~180° from road heading, CR offset is negated."""
        # Road heading: rightward (positive X)
        project = self._make_project_with_road(
            "r1", [(0.0, 0.0), (100.0, 0.0)], lane_width=3.5
        )
        scale = 0.05
        # CR heading leftward (opposite to road) at the connection
        shift = _compute_lane_alignment_shift(
            project=project,
            road_id="r1",
            contact_point="start",
            target_lane_id=-1,  # right lane on road
            cr_lane_id=1,  # left lane on CR (which is on the RIGHT side when heading is flipped)
            cr_lane_width=3.5,
            cr_endpoint=(0.0, 0.0),
            cr_fwd_p1=(10.0, 0.0),
            cr_fwd_p2=(0.0, 0.0),  # heading leftward = opposite
            scale=scale,
        )
        # With opposite heading, CR lane 1 (left of CR) physically maps to the
        # right side — same as road lane -1. CR CL should be at road CL
        # (no perpendicular shift), so only the distance from cr_endpoint to
        # road CL matters. Since cr_endpoint is already at road CL, shift ≈ 0.
        assert shift is None

    def test_opposite_heading_different_lanes_gives_correct_offset(self):
        """Opposite-heading CR with lane 1 targeting road lane 1 shifts correctly."""
        # Road heading: rightward
        project = self._make_project_with_road(
            "r1", [(0.0, 0.0), (100.0, 0.0)], lane_width=3.5
        )
        scale = 0.05
        w_px = 3.5 / scale  # 70 pixels
        # CR heading leftward, targeting lane 1 on road (left of road direction)
        shift = _compute_lane_alignment_shift(
            project=project,
            road_id="r1",
            contact_point="start",
            target_lane_id=1,  # left lane on road (above CL for rightward road)
            cr_lane_id=1,  # left lane on CR (below CL for leftward heading = right of road)
            cr_lane_width=3.5,
            cr_endpoint=(0.0, 0.0),
            cr_fwd_p1=(10.0, 0.0),
            cr_fwd_p2=(0.0, 0.0),  # heading leftward = opposite
            scale=scale,
        )
        # Road lane 1 center is at -0.5w above CL (negative Y for rightward road).
        # With opposite heading, CR lane 1 maps to the right side (+0.5w below CL).
        # target CR CL = road lane 1 center - (+0.5w) * road_perp
        #              = (0, -35) - 35*(0, 1) = (0, -70)
        # shift = target - endpoint = (0, -70) - (0, 0) = (0, -70)
        assert shift is not None
        assert shift[0] == pytest.approx(0.0, abs=1.0)
        assert shift[1] == pytest.approx(-w_px, abs=1.0)

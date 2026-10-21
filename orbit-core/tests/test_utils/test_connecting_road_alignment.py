"""Tests for orbit_core.utils.connecting_road_alignment module."""

import pytest

from orbit_core.models.lane import Lane
from orbit_core.models.lane_section import LaneSection
from orbit_core.models.polyline import Polyline
from orbit_core.models.road import Road
from orbit_core.utils.connecting_road_alignment import (
    _compute_lane_alignment_shift,
    _get_road_lane_width,
    _lane_center_offset,
    lane_center_offset,
    sync_connecting_road_lane_widths,
)


def make_cr(cr_id="cr1", widths=None):
    """Connecting road with one lane section holding the given lane widths."""
    widths = widths or {-1: 3.5, 1: 3.5}
    section = LaneSection(section_number=1, s_start=0.0, s_end=100.0)
    section.lanes = [Lane(id=0, width=0.0)] + [
        Lane(id=lid, width=w) for lid, w in sorted(widths.items())
    ]
    cr = Road(id=cr_id, name="CR", junction_id="j1")
    cr.lane_sections = [section]
    return cr


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
        from orbit_core.models.project import Project

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
            cr=make_cr(),
            cr_lane_id=-1,  # right lane on CR
            cr_contact="start",
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
            cr=make_cr(),
            cr_lane_id=1,  # left lane on CR (which is on the RIGHT side when heading is flipped)
            cr_contact="start",
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
            cr=make_cr(),
            cr_lane_id=1,  # left lane on CR (below CL for leftward heading = right of road)
            cr_contact="start",
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


class TestVariableWidthAlignment:
    """Verifies CR endpoint-specific width is used in alignment shift."""

    def test_different_cr_widths_at_endpoints(self):
        """CR with 6m start / 3m end produces different shifts at each endpoint."""
        # Shift depends on cr_lane_width: offset = (|lane_id| - 0.5) * width
        # lane -1: offset = 0.5 * width
        shift_start = _lane_center_offset(-1, 6.0)
        shift_end = _lane_center_offset(-1, 3.0)
        assert shift_start == pytest.approx(3.0)
        assert shift_end == pytest.approx(1.5)
        assert shift_start != shift_end


class TestLaneCenterOffset:
    """Cumulative lane-center offsets on roads with non-uniform lane widths."""

    @staticmethod
    def _road_with(widths, width_ends=None):
        """Road with a single section holding the given start/end lane widths."""
        width_ends = width_ends or {}
        section = LaneSection(section_number=1, s_start=0.0, s_end=100.0)
        section.lanes = [
            Lane(id=lid, width=w, width_end=width_ends.get(lid))
            for lid, w in sorted(widths.items())
        ]
        road = Road(id="r", name="R")
        road.lane_sections = [section]
        return road

    def test_uniform_widths_match_legacy_formula(self):
        """With equal widths the cumulative offset equals (|id| - 0.5) * width."""
        road = self._road_with({-2: 3.5, -1: 3.5, 0: 0.0, 1: 3.5, 2: 3.5})
        for lane_id in (-2, -1, 1, 2):
            assert lane_center_offset(road, lane_id, "start") == pytest.approx(
                _lane_center_offset(lane_id, 3.5)
            )

    def test_wide_junction_mouth(self):
        """A 17 m mouth lane centers at 8.5 m, not at the mean-width guess."""
        # Lane layout of the Guntoftavägen junction mouth (road 1 of SaroT).
        road = self._road_with(
            {-2: 17.0, -1: 0.0, 0: 0.0, 1: 0.0, 2: 5.0, 3: 4.0, 4: 7.5}
        )
        assert lane_center_offset(road, -2, "start") == pytest.approx(8.5)
        # Left side: lane 2 sits beyond the zero-width median lane 1.
        assert lane_center_offset(road, 2, "start") == pytest.approx(-2.5)
        # Lane 4 sits beyond lane 2 (5.0) and the painted island lane 3 (4.0).
        assert lane_center_offset(road, 4, "start") == pytest.approx(-12.75)

    def test_turn_pocket_shifts_outer_lane(self):
        """A pocket that opens toward the junction pushes the through lane out."""
        # Säröleden approach (road 2 of SaroT): median 1 closed, pocket 2 open.
        road = self._road_with({-1: 3.5, 0: 0.0, 1: 0.0, 2: 5.0, 3: 3.5})
        assert lane_center_offset(road, 3, "start") == pytest.approx(-6.75)
        assert lane_center_offset(road, -1, "start") == pytest.approx(1.75)

    def test_uses_contact_end_widths(self):
        """The end contact uses width_end, the start contact uses width."""
        road = self._road_with({-1: 3.0, 0: 0.0}, width_ends={-1: 5.0})
        assert lane_center_offset(road, -1, "start") == pytest.approx(1.5)
        assert lane_center_offset(road, -1, "end") == pytest.approx(2.5)

    def test_falls_back_when_lane_missing(self):
        """An unknown lane id falls back to the uniform-width estimate."""
        road = self._road_with({-1: 4.0, 0: 0.0, 1: 4.0})
        assert lane_center_offset(road, -3, "start") == pytest.approx(
            _lane_center_offset(-3, 4.0)
        )

    def test_road_without_lane_sections(self):
        """A road with no lane sections uses its default lane width."""
        road = Road(id="r", name="R")
        assert lane_center_offset(road, -1, "start") == pytest.approx(
            _lane_center_offset(-1, road.lane_info.lane_width)
        )

    def test_center_lane_has_no_offset(self):
        road = self._road_with({-1: 3.5, 0: 0.0, 1: 3.5})
        assert lane_center_offset(road, 0, "start") == 0.0


class TestSyncConnectingRoadLaneWidths:
    """CR lane widths follow the road lanes their movements actually connect."""

    @staticmethod
    def _road(road_id, widths, width_ends=None):
        width_ends = width_ends or {}
        section = LaneSection(section_number=1, s_start=0.0, s_end=100.0)
        section.lanes = [
            Lane(id=lid, width=w, width_end=width_ends.get(lid))
            for lid, w in sorted(widths.items())
        ]
        road = Road(id=road_id, name=f"Road {road_id}", centerline_id=road_id)
        road.lane_sections = [section]
        return road

    def _project(self, cr_widths=None, pred_id="a", succ_id="b"):
        """Junction a→CR→b, where road a has a wide outer lane 3."""
        from orbit_core.models.junction import Junction
        from orbit_core.models.lane_connection import LaneConnection
        from orbit_core.models.project import Project

        project = Project()
        # Lane 3 (6.0) is the one the movement uses; lane -1 (3.5) is first.
        project.add_road(self._road("a", {-1: 3.5, 0: 0.0, 1: 0.0, 2: 5.0, 3: 6.0}))
        project.add_road(self._road("b", {-1: 4.0, 0: 0.0, 1: 4.0}))

        cr = make_cr("cr1", cr_widths or {1: 3.5})
        cr.junction_id = "j1"
        cr.predecessor_id = pred_id
        cr.predecessor_contact = "start"
        cr.successor_id = succ_id
        cr.successor_contact = "start"
        project.add_road(cr)

        conn = LaneConnection(
            id="lc1", from_road_id="a", from_lane_id=3,
            to_road_id="b", to_lane_id=-1,
            connecting_road_id="cr1", connecting_lane_id=1,
        )
        junction = Junction(
            id="j1", name="J", connected_road_ids=["a", "b"],
            connecting_road_ids=["cr1"], lane_connections=[conn],
        )
        project.junctions = [junction]
        return project, junction, cr

    def test_takes_width_of_the_connected_lane(self):
        """The movement's own lane decides the width, not the first lane."""
        project, junction, cr = self._project()
        assert sync_connecting_road_lane_widths(junction, project) == ["cr1"]
        lane = cr.get_cr_lane(1)
        assert lane.width == pytest.approx(6.0)
        assert lane.get_width_at_end() == pytest.approx(4.0)

    def test_reversed_path_cr_swaps_ends(self):
        """A CR whose predecessor is the to_road takes its widths the other way."""
        project, junction, cr = self._project(pred_id="b", succ_id="a")
        sync_connecting_road_lane_widths(junction, project)
        lane = cr.get_cr_lane(1)
        assert lane.width == pytest.approx(4.0)
        assert lane.get_width_at_end() == pytest.approx(6.0)

    def test_equal_widths_clear_width_end(self):
        """Matching start and end widths leave the lane at a constant width."""
        project, junction, cr = self._project()
        project.get_road("b").lane_sections[0].lanes[0].width = 6.0
        sync_connecting_road_lane_widths(junction, project)
        lane = cr.get_cr_lane(1)
        assert lane.width == pytest.approx(6.0)
        assert lane.width_end is None

    def test_lane_without_movement_untouched(self):
        """A CR lane no movement references keeps its width."""
        project, junction, cr = self._project(cr_widths={-1: 3.0, 1: 3.5})
        sync_connecting_road_lane_widths(junction, project)
        assert cr.get_cr_lane(-1).width == pytest.approx(3.0)
        assert cr.get_cr_lane(1).width == pytest.approx(6.0)

    def test_movement_naming_missing_cr_lane_is_skipped(self):
        """A stale connecting_lane_id changes nothing."""
        project, junction, cr = self._project()
        junction.lane_connections[0].connecting_lane_id = -2
        assert sync_connecting_road_lane_widths(junction, project) == []
        assert cr.get_cr_lane(1).width == pytest.approx(3.5)

    def test_missing_road_lane_is_skipped(self):
        """A movement naming a lane the road no longer has changes nothing."""
        project, junction, cr = self._project()
        junction.lane_connections[0].from_lane_id = 9
        assert sync_connecting_road_lane_widths(junction, project) == []
        assert cr.get_cr_lane(1).width == pytest.approx(3.5)

    def test_idempotent(self):
        """A second sync reports no further change."""
        project, junction, _ = self._project()
        assert sync_connecting_road_lane_widths(junction, project) == ["cr1"]
        assert sync_connecting_road_lane_widths(junction, project) == []

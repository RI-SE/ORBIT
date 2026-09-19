"""Tests for building a single connecting road by hand."""

import pytest

from orbit_core.importers.junction_analyzer import create_connecting_road
from orbit_core.models import Junction, LineType, Polyline, Project
from orbit_core.models.lane import Lane, LaneType
from orbit_core.models.lane_section import LaneSection
from orbit_core.models.road import Road


def make_road(project, road_id, points, lanes=None):
    """Road with a centerline and one lane section."""
    polyline = Polyline(id=road_id, points=points, line_type=LineType.CENTERLINE)
    project.add_polyline(polyline)
    road = Road(id=road_id, name=f"Road {road_id}", centerline_id=road_id)
    road.polyline_ids = [road_id]
    lanes = lanes or [
        Lane(id=-1, width=3.5), Lane(id=0, width=0.0, lane_type=LaneType.NONE),
        Lane(id=1, width=3.5),
    ]
    road.lane_sections = [
        LaneSection(section_number=1, s_start=0.0, s_end=100.0, lanes=lanes)
    ]
    project.add_road(road)
    return road


@pytest.fixture
def junction_project():
    """A T of three roads meeting at (100, 100), with no connecting roads."""
    project = Project()
    make_road(project, "a", [(0.0, 100.0), (80.0, 100.0)])       # west, ends here
    make_road(project, "b", [(120.0, 100.0), (200.0, 100.0)])    # east, starts here
    make_road(project, "c", [(100.0, 120.0), (100.0, 200.0)])    # south, starts here
    junction = Junction(id="j1", name="J", center_point=(100.0, 100.0))
    junction.connected_road_ids = ["a", "b", "c"]
    project.junctions = [junction]
    return project, junction


def build(project, junction, **kwargs):
    return create_connecting_road(
        junction, kwargs.pop("from_road", "a"), kwargs.pop("to_road", "b"),
        {r.id: r for r in project.roads},
        {p.id: p for p in project.polylines},
        project=project, **kwargs,
    )


class TestCreateConnectingRoad:
    def test_builds_and_registers_a_connecting_road(self, junction_project):
        project, junction = junction_project
        cr = build(project, junction)
        assert cr is not None
        assert cr.is_connecting_road
        assert cr.junction_id == junction.id
        assert cr.id in junction.connecting_road_ids
        assert project.get_road(cr.id) is cr

    def test_has_usable_geometry(self, junction_project):
        project, junction = junction_project
        cr = build(project, junction)
        assert len(cr.inline_path) >= 2
        assert cr.geometry_type == "parampoly3"
        assert cr.aU is not None and cr.bV is not None

    def test_creates_a_movement_naming_a_connecting_lane(self, junction_project):
        """Without a connecting lane the exporter would have to guess."""
        project, junction = junction_project
        cr = build(project, junction)
        movements = [lc for lc in junction.lane_connections
                     if lc.connecting_road_id == cr.id]
        assert len(movements) >= 1
        assert all(lc.connecting_lane_id is not None for lc in movements)
        assert all(cr.get_cr_lane(lc.connecting_lane_id) is not None
                   for lc in movements)

    def test_explicit_lanes_are_used(self, junction_project):
        project, junction = junction_project
        cr = build(project, junction, from_lane_id=-1, to_lane_id=-1)
        movements = [lc for lc in junction.lane_connections
                     if lc.connecting_road_id == cr.id]
        assert len(movements) == 1
        assert (movements[0].from_lane_id, movements[0].to_lane_id) == (-1, -1)

    def test_explicit_lanes_can_pick_a_turn_pocket(self, junction_project):
        """The chosen lane wins over the position-derived pairing."""
        project, junction = junction_project
        road_a = project.get_road("a")
        road_a.lane_sections[0].lanes.append(Lane(id=2, width=5.0))
        cr = build(project, junction, from_lane_id=2, to_lane_id=-1)
        movement = [lc for lc in junction.lane_connections
                    if lc.connecting_road_id == cr.id][0]
        assert movement.from_lane_id == 2

    def test_turn_type_can_be_forced(self, junction_project):
        project, junction = junction_project
        cr = build(project, junction, to_road="c", turn_type="right")
        movement = [lc for lc in junction.lane_connections
                    if lc.connecting_road_id == cr.id][0]
        assert movement.turn_type == "right"

    def test_second_connecting_road_between_the_same_roads(self, junction_project):
        """A slip lane means two paths joining the same pair."""
        project, junction = junction_project
        first = build(project, junction)
        second = build(project, junction)
        assert second is not None and second.id != first.id
        assert len(junction.connecting_road_ids) == 2

    def test_unknown_road_is_refused(self, junction_project):
        project, junction = junction_project
        assert build(project, junction, from_road="nope") is None

    def test_does_not_disturb_existing_movements(self, junction_project):
        project, junction = junction_project
        build(project, junction)
        before = [lc.id for lc in junction.lane_connections]
        build(project, junction, from_road="a", to_road="c")
        assert before == [lc.id for lc in junction.lane_connections][:len(before)]

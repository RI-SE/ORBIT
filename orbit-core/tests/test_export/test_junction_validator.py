"""Tests for orbit_core.export.junction_validator."""


from orbit_core.export.junction_validator import validate_junctions
from orbit_core.models.junction import Junction
from orbit_core.models.lane import Lane, LaneType
from orbit_core.models.lane_connection import LaneConnection
from orbit_core.models.lane_section import LaneSection
from orbit_core.models.project import Project
from orbit_core.models.road import Road


def make_road(road_id, widths, lane_types=None):
    """Road with one lane section holding the given lane widths."""
    lane_types = lane_types or {}
    section = LaneSection(section_number=1, s_start=0.0, s_end=100.0)
    section.lanes = [
        Lane(
            id=lid,
            width=w,
            lane_type=lane_types.get(lid, LaneType.NONE if lid == 0 else LaneType.DRIVING),
        )
        for lid, w in sorted(widths.items())
    ]
    road = Road(id=road_id, name=f"Road {road_id}", centerline_id=road_id)
    road.lane_sections = [section]
    return road


def make_junction_project(cr_widths=None, road_a=None, road_b=None):
    """Junction a→cr1→b with one straight movement a.-1 → b.-1 on CR lane -1."""
    project = Project()
    project.add_road(road_a or make_road("a", {-1: 3.5, 0: 0.0, 1: 3.5}))
    project.add_road(road_b or make_road("b", {-1: 3.5, 0: 0.0, 1: 3.5}))

    cr = Road(id="cr1", name="CR", junction_id="j1")
    cr.cr_lane_count_left = 0
    cr.cr_lane_count_right = 1
    cr.predecessor_id = "a"
    cr.predecessor_contact = "end"
    cr.successor_id = "b"
    cr.successor_contact = "start"
    cr.ensure_cr_lanes_initialized()
    for lane_id, width in (cr_widths or {-1: 3.5}).items():
        cr.get_cr_lane(lane_id).width = width
    project.add_road(cr)

    conn = LaneConnection(
        id="lc1", from_road_id="a", from_lane_id=-1,
        to_road_id="b", to_lane_id=-1,
        connecting_road_id="cr1", connecting_lane_id=-1,
    )
    junction = Junction(
        id="j1", name="J", connected_road_ids=["a", "b"],
        connecting_road_ids=["cr1"], lane_connections=[conn],
    )
    project.junctions = [junction]
    return project, junction, cr


class TestCleanJunction:
    def test_matching_widths_produce_no_warnings(self):
        project, _, _ = make_junction_project()
        # Lane 1 of each road is the opposite direction, unconnected by design
        # in this minimal fixture — check only the movement-related warnings.
        warnings = [w for w in validate_junctions(project) if "lane 1" not in w]
        assert warnings == []

    def test_junction_without_movements_is_skipped(self):
        project, junction, _ = make_junction_project()
        junction.lane_connections = []
        assert validate_junctions(project) == []


class TestWidthSteps:
    def test_width_step_at_start_reported(self):
        project, _, _ = make_junction_project(cr_widths={-1: 5.0})
        warnings = [w for w in validate_junctions(project) if "step" in w]
        assert len(warnings) == 2  # both ends differ from 3.5
        assert "1.50 m step" in warnings[0]

    def test_step_within_tolerance_ignored(self):
        project, _, _ = make_junction_project(cr_widths={-1: 3.52})
        assert [w for w in validate_junctions(project) if "step" in w] == []

    def test_wide_mouth_step_reported(self):
        """The SaroT case: a 3.5 m CR lane meeting a 17 m junction mouth."""
        wide = make_road("b", {-1: 17.0, 0: 0.0, 1: 3.5})
        project, _, _ = make_junction_project(road_b=wide)
        warnings = [w for w in validate_junctions(project) if "13.50 m step" in w]
        assert len(warnings) == 1


class TestMissingLanes:
    def test_movement_naming_missing_cr_lane(self):
        project, junction, _ = make_junction_project()
        junction.lane_connections[0].connecting_lane_id = -2
        warnings = validate_junctions(project)
        assert any("has no such lane" in w for w in warnings)

    def test_movement_naming_missing_road_lane(self):
        project, junction, _ = make_junction_project()
        junction.lane_connections[0].from_lane_id = -9
        warnings = validate_junctions(project)
        assert any("no such lane at its end" in w for w in warnings)


class TestUnusedLanes:
    def test_cr_lane_without_movement(self):
        project, _, cr = make_junction_project()
        cr.resize_cr_lanes(1, 1)
        warnings = validate_junctions(project)
        assert any("connecting road cr1 lane 1 carries no movement" in w
                   for w in warnings)

    def test_driving_lane_without_movement(self):
        """A turn pocket that no movement uses is reported."""
        pocket = make_road("a", {-1: 3.5, 0: 0.0, 1: 3.5, 2: 5.0})
        project, _, _ = make_junction_project(road_a=pocket)
        warnings = validate_junctions(project)
        assert any("road a lane 2 (5.00 m at the junction) carries no movement" in w
                   for w in warnings)

    def test_closed_lane_without_movement_ignored(self):
        """A lane of zero width at the junction needs no movement."""
        closed = make_road("a", {-1: 3.5, 0: 0.0, 1: 3.5, 2: 0.0})
        project, _, _ = make_junction_project(road_a=closed)
        warnings = validate_junctions(project)
        assert not any("road a lane 2" in w for w in warnings)

    def test_non_driving_lane_without_movement_ignored(self):
        """A median lane carries no traffic, so it needs no movement."""
        median = make_road(
            "a", {-1: 3.5, 0: 0.0, 1: 3.5, 2: 4.0},
            lane_types={2: LaneType.MEDIAN},
        )
        project, _, _ = make_junction_project(road_a=median)
        warnings = validate_junctions(project)
        assert not any("road a lane 2" in w for w in warnings)


class StubTransformer:
    """Minimal coordinate transformer for the writer integration test."""

    def get_scale_factor(self):
        return (0.1, 0.1)

    def get_projection_string(self):
        return "+proj=tmerc +lat_0=57.7 +lon_0=12.9 +k=1 +x_0=0 +y_0=0 +datum=WGS84"

    def get_utm_projection_string(self):
        return "+proj=utm +zone=33 +datum=WGS84"

    def pixels_to_meters_batch(self, points):
        return [(p[0] * 0.1, p[1] * 0.1) for p in points]

    def latlon_to_meters(self, lat, lon):
        return (lon * 111000, lat * 111000)

    def transform_heading(self, px, py, heading):
        return heading


class TestWriterIntegration:
    def test_writer_collects_junction_warnings(self, tmp_path):
        from orbit_core.export.opendrive_writer import OpenDriveWriter

        project, _, _ = make_junction_project(cr_widths={-1: 5.0})
        writer = OpenDriveWriter(project, StubTransformer())
        writer.write(str(tmp_path / "out.xodr"))
        assert any("step" in w for w in writer.junction_warnings)

"""Tests for the reference validator."""

import pytest

from orbit.models.project import Project
from orbit.models.polyline import Polyline, LineType
from orbit.models.road import Road
from orbit.models.junction import Junction, JunctionGroup
from orbit.models.connecting_road import ConnectingRoad
from orbit.models.lane_connection import LaneConnection
from orbit.models.signal import Signal
from orbit.models.object import RoadObject
from orbit.models.parking import ParkingSpace
from orbit.export.reference_validator import validate_references


@pytest.fixture
def valid_project():
    """Create a project with all references valid."""
    project = Project()

    # Polylines
    centerline = Polyline(
        id="p1",
        points=[(0, 0), (100, 0)],
        line_type=LineType.CENTERLINE
    )
    boundary = Polyline(
        id="p2",
        points=[(0, 3), (100, 3)]
    )
    project.polylines = [centerline, boundary]

    # Roads
    road1 = Road(
        id="r1",
        name="Road 1",
        centerline_id="p1",
        polyline_ids=["p1", "p2"]
    )
    road2 = Road(
        id="r2",
        name="Road 2",
        centerline_id="p1",
        polyline_ids=["p1"],
        predecessor_id="r1"
    )
    project.roads = [road1, road2]

    return project


class TestValidateReferences:
    """Tests for validate_references function."""

    def test_valid_project_no_warnings(self, valid_project):
        """Valid project should return no warnings."""
        warnings = validate_references(valid_project)
        assert warnings == []

    def test_empty_project_no_warnings(self):
        """Empty project should return no warnings."""
        project = Project()
        warnings = validate_references(project)
        assert warnings == []

    def test_road_missing_centerline(self):
        """Road referencing non-existent centerline polyline."""
        project = Project()
        road = Road(id="r1", name="Test", centerline_id="missing_polyline", polyline_ids=["missing_polyline"])
        project.roads = [road]

        warnings = validate_references(project)
        assert len(warnings) == 2  # centerline_id + polyline_ids entry
        assert "centerline_id 'missing_polyline' not found" in warnings[0]

    def test_road_missing_predecessor(self):
        """Road referencing non-existent predecessor road."""
        project = Project()
        poly = Polyline(id="p1", points=[(0, 0), (10, 0)])
        road = Road(id="r1", name="Test", centerline_id="p1", polyline_ids=["p1"], predecessor_id="missing_road")
        project.polylines = [poly]
        project.roads = [road]

        warnings = validate_references(project)
        assert len(warnings) == 1
        assert "predecessor_id 'missing_road' not found" in warnings[0]

    def test_road_missing_successor(self):
        """Road referencing non-existent successor road."""
        project = Project()
        poly = Polyline(id="p1", points=[(0, 0), (10, 0)])
        road = Road(id="r1", name="Test", centerline_id="p1", polyline_ids=["p1"], successor_id="gone")
        project.polylines = [poly]
        project.roads = [road]

        warnings = validate_references(project)
        assert len(warnings) == 1
        assert "successor_id 'gone' not found" in warnings[0]

    def test_road_missing_junction_id(self):
        """Road referencing non-existent junction."""
        project = Project()
        poly = Polyline(id="p1", points=[(0, 0), (10, 0)])
        road = Road(id="r1", name="Test", centerline_id="p1", polyline_ids=["p1"], junction_id="missing_j")
        project.polylines = [poly]
        project.roads = [road]

        warnings = validate_references(project)
        assert len(warnings) == 1
        assert "junction_id 'missing_j' not found" in warnings[0]

    def test_road_missing_predecessor_junction(self):
        """Road referencing non-existent predecessor junction."""
        project = Project()
        poly = Polyline(id="p1", points=[(0, 0), (10, 0)])
        road = Road(id="r1", name="Test", centerline_id="p1", polyline_ids=["p1"])
        road.predecessor_junction_id = "missing_j"
        project.polylines = [poly]
        project.roads = [road]

        warnings = validate_references(project)
        assert len(warnings) == 1
        assert "predecessor_junction_id" in warnings[0]

    def test_junction_missing_connected_road(self):
        """Junction referencing non-existent road."""
        project = Project()
        junction = Junction(id="j1", name="Test", connected_road_ids=["missing_road"])
        project.junctions = [junction]

        warnings = validate_references(project)
        assert len(warnings) == 1
        assert "connected_road_id 'missing_road' not found" in warnings[0]

    def test_junction_missing_entry_exit_roads(self):
        """Junction referencing non-existent entry/exit roads."""
        project = Project()
        junction = Junction(id="j1", name="Test")
        junction.entry_roads = ["missing1"]
        junction.exit_roads = ["missing2"]
        project.junctions = [junction]

        warnings = validate_references(project)
        assert len(warnings) == 2
        assert any("entry_road" in w for w in warnings)
        assert any("exit_road" in w for w in warnings)

    def test_connecting_road_missing_predecessor(self):
        """ConnectingRoad referencing non-existent predecessor road."""
        project = Project()
        cr = ConnectingRoad(id="cr1", predecessor_road_id="missing", successor_road_id="")
        junction = Junction(id="j1", name="Test", connecting_roads=[cr])
        project.junctions = [junction]

        warnings = validate_references(project)
        assert any("predecessor_road_id 'missing'" in w for w in warnings)

    def test_lane_connection_missing_roads(self):
        """LaneConnection referencing non-existent roads."""
        project = Project()
        lc = LaneConnection(
            id="lc1",
            from_road_id="missing_from",
            to_road_id="missing_to",
            connecting_road_id="missing_cr",
            traffic_light_id="missing_signal"
        )
        junction = Junction(id="j1", name="Test", lane_connections=[lc])
        project.junctions = [junction]

        warnings = validate_references(project)
        assert len(warnings) == 4
        assert any("from_road_id" in w for w in warnings)
        assert any("to_road_id" in w for w in warnings)
        assert any("connecting_road_id" in w for w in warnings)
        assert any("traffic_light_id" in w for w in warnings)

    def test_signal_missing_road(self):
        """Signal referencing non-existent road."""
        project = Project()
        signal = Signal(signal_id="s1", road_id="missing_road")
        project.signals = [signal]

        warnings = validate_references(project)
        assert len(warnings) == 1
        assert "road_id 'missing_road' not found" in warnings[0]

    def test_object_missing_road(self):
        """RoadObject referencing non-existent road."""
        project = Project()
        obj = RoadObject(object_id="o1")
        obj.road_id = "missing_road"
        project.objects = [obj]

        warnings = validate_references(project)
        assert len(warnings) == 1
        assert "road_id 'missing_road' not found" in warnings[0]

    def test_parking_missing_road(self):
        """ParkingSpace referencing non-existent road."""
        project = Project()
        parking = ParkingSpace(parking_id="pk1")
        parking.road_id = "missing_road"
        project.parking_spaces = [parking]

        warnings = validate_references(project)
        assert len(warnings) == 1
        assert "road_id 'missing_road' not found" in warnings[0]

    def test_junction_group_missing_junction(self):
        """JunctionGroup referencing non-existent junction."""
        project = Project()
        jg = JunctionGroup(id="jg1", name="Test", group_type="roundabout", junction_ids=["missing_j"])
        project.junction_groups = [jg]

        warnings = validate_references(project)
        assert len(warnings) == 1
        assert "junction_id 'missing_j' not found" in warnings[0]

    def test_valid_signal_road_reference(self):
        """Signal with valid road reference should produce no warning."""
        project = Project()
        poly = Polyline(id="p1", points=[(0, 0), (10, 0)])
        road = Road(id="r1", name="Test", centerline_id="p1", polyline_ids=["p1"])
        signal = Signal(signal_id="s1", road_id="r1")
        project.polylines = [poly]
        project.roads = [road]
        project.signals = [signal]

        warnings = validate_references(project)
        assert warnings == []

    def test_none_references_ignored(self):
        """None references should not produce warnings."""
        project = Project()
        poly = Polyline(id="p1", points=[(0, 0), (10, 0)])
        road = Road(
            id="r1", name="Test", centerline_id="p1", polyline_ids=["p1"],
            predecessor_id=None, successor_id=None, junction_id=None
        )
        project.polylines = [poly]
        project.roads = [road]

        warnings = validate_references(project)
        assert warnings == []

    def test_multiple_issues_all_reported(self):
        """Multiple broken references should all be reported."""
        project = Project()
        road = Road(
            id="r1", name="Bad Road",
            centerline_id="missing_poly",
            polyline_ids=["missing_poly"],
            predecessor_id="missing_road",
            successor_id="missing_road2",
            junction_id="missing_junction"
        )
        project.roads = [road]

        warnings = validate_references(project)
        # centerline_id + polyline_ids + predecessor + successor + junction
        assert len(warnings) == 5

"""Tests for opendrive_parser dataclass models and their default values."""

import importlib

import pytest

# Import from orbit.import using importlib (import is a reserved keyword)
opendrive_parser = importlib.import_module('orbit.import.opendrive_parser')

# Classes and types
GeometryType = opendrive_parser.GeometryType
GeometryElement = opendrive_parser.GeometryElement
ElevationProfile = opendrive_parser.ElevationProfile
LateralProfile = opendrive_parser.LateralProfile
LaneOffsetRecord = opendrive_parser.LaneOffsetRecord
LaneWidth = opendrive_parser.LaneWidth
LaneRoadMark = opendrive_parser.LaneRoadMark
LaneSpeed = opendrive_parser.LaneSpeed
LaneMaterial = opendrive_parser.LaneMaterial
LaneHeight = opendrive_parser.LaneHeight
LaneLink = opendrive_parser.LaneLink
ODRLane = opendrive_parser.ODRLane
ODRLaneSection = opendrive_parser.ODRLaneSection
ODRSignal = opendrive_parser.ODRSignal
ODRObject = opendrive_parser.ODRObject
ODRLaneLink = opendrive_parser.ODRLaneLink
ODRConnection = opendrive_parser.ODRConnection
ODRBoundarySegment = opendrive_parser.ODRBoundarySegment
ODRJunctionBoundary = opendrive_parser.ODRJunctionBoundary
ODRElevationGridPoint = opendrive_parser.ODRElevationGridPoint
ODRJunctionElevationGrid = opendrive_parser.ODRJunctionElevationGrid
ODRJunction = opendrive_parser.ODRJunction
ODRJunctionGroup = opendrive_parser.ODRJunctionGroup
ODRRoad = opendrive_parser.ODRRoad
ODRHeader = opendrive_parser.ODRHeader
OpenDriveData = opendrive_parser.OpenDriveData
OpenDriveParser = opendrive_parser.OpenDriveParser




class TestGeometryType:
    """Tests for GeometryType enum."""

    def test_line_type(self):
        """Line geometry type."""
        assert GeometryType.LINE.value == "line"

    def test_arc_type(self):
        """Arc geometry type."""
        assert GeometryType.ARC.value == "arc"

    def test_spiral_type(self):
        """Spiral geometry type."""
        assert GeometryType.SPIRAL.value == "spiral"

    def test_poly3_type(self):
        """Poly3 geometry type."""
        assert GeometryType.POLY3.value == "poly3"

    def test_param_poly3_type(self):
        """ParamPoly3 geometry type."""
        assert GeometryType.PARAM_POLY3.value == "paramPoly3"


class TestGeometryElement:
    """Tests for GeometryElement dataclass."""

    def test_basic_creation(self):
        """Create geometry element."""
        elem = GeometryElement(
            s=0.0,
            x=100.0,
            y=200.0,
            hdg=1.57,
            length=50.0,
            geometry_type=GeometryType.LINE
        )

        assert elem.s == 0.0
        assert elem.x == 100.0
        assert elem.y == 200.0
        assert elem.hdg == 1.57
        assert elem.length == 50.0
        assert elem.geometry_type == GeometryType.LINE
        assert elem.params == {}

    def test_with_params(self):
        """Create geometry element with parameters."""
        elem = GeometryElement(
            s=0.0, x=0.0, y=0.0, hdg=0.0, length=100.0,
            geometry_type=GeometryType.ARC,
            params={"curvature": 0.01}
        )

        assert elem.params["curvature"] == 0.01


class TestElevationProfile:
    """Tests for ElevationProfile dataclass."""

    def test_empty_profile(self):
        """Empty profile returns None for elevation."""
        profile = ElevationProfile()

        assert profile.get_elevation_at(50.0) is None

    def test_single_elevation_record(self):
        """Single elevation record."""
        profile = ElevationProfile(
            elevations=[(0.0, 10.0, 0.0, 0.0, 0.0)]
        )

        assert profile.get_elevation_at(0.0) == 10.0
        assert profile.get_elevation_at(50.0) == 10.0

    def test_elevation_polynomial(self):
        """Elevation with polynomial coefficients."""
        # elevation(ds) = a + b*ds
        profile = ElevationProfile(
            elevations=[(0.0, 10.0, 0.1, 0.0, 0.0)]  # a=10, b=0.1
        )

        # At ds=0: 10 + 0.1*0 = 10
        assert profile.get_elevation_at(0.0) == 10.0
        # At ds=50: 10 + 0.1*50 = 15
        assert profile.get_elevation_at(50.0) == 15.0

    def test_multiple_elevation_records(self):
        """Multiple elevation records."""
        profile = ElevationProfile(
            elevations=[
                (0.0, 10.0, 0.0, 0.0, 0.0),
                (100.0, 20.0, 0.0, 0.0, 0.0)
            ]
        )

        # Before 100: use first record
        assert profile.get_elevation_at(50.0) == 10.0
        # At and after 100: use second record
        assert profile.get_elevation_at(100.0) == 20.0
        assert profile.get_elevation_at(150.0) == 20.0


class TestLaneWidth:
    """Tests for LaneWidth dataclass."""

    def test_constant_width(self):
        """Constant width (a only)."""
        width = LaneWidth(s_offset=0.0, a=3.5)

        assert width.get_width_at(0.0) == 3.5
        assert width.get_width_at(100.0) == 3.5

    def test_linear_width(self):
        """Linear width (a + b*ds)."""
        width = LaneWidth(s_offset=0.0, a=3.0, b=0.01)

        assert width.get_width_at(0.0) == 3.0
        assert width.get_width_at(100.0) == 4.0  # 3.0 + 0.01*100

    def test_polynomial_width(self):
        """Full polynomial width."""
        width = LaneWidth(s_offset=0.0, a=3.0, b=0.0, c=0.001, d=0.0)

        # 3.0 + 0.001 * 10^2 = 3.1
        assert width.get_width_at(10.0) == pytest.approx(3.1, abs=0.01)


class TestODRLane:
    """Tests for ODRLane dataclass."""

    def test_basic_lane(self):
        """Create basic lane."""
        lane = ODRLane(id=-1, type="driving")

        assert lane.id == -1
        assert lane.type == "driving"
        assert lane.level is False
        assert lane.widths == []

    def test_get_width_at_s_no_widths(self):
        """Default width when no widths defined."""
        lane = ODRLane(id=-1, type="driving")

        assert lane.get_width_at_s(0.0) == 3.5

    def test_get_width_at_s_with_width(self):
        """Width from width polynomial."""
        lane = ODRLane(
            id=-1, type="driving",
            widths=[LaneWidth(s_offset=0.0, a=4.0)]
        )

        assert lane.get_width_at_s(0.0) == 4.0


class TestODRLaneSection:
    """Tests for ODRLaneSection dataclass."""

    def test_basic_section(self):
        """Create basic lane section."""
        section = ODRLaneSection(s=0.0)

        assert section.s == 0.0
        assert section.single_side is None
        assert section.left_lanes == []
        assert section.center_lanes == []
        assert section.right_lanes == []

    def test_section_with_lanes(self):
        """Section with lanes."""
        left_lane = ODRLane(id=1, type="driving")
        center_lane = ODRLane(id=0, type="none")
        right_lane = ODRLane(id=-1, type="driving")

        section = ODRLaneSection(
            s=0.0,
            left_lanes=[left_lane],
            center_lanes=[center_lane],
            right_lanes=[right_lane]
        )

        assert len(section.left_lanes) == 1
        assert len(section.center_lanes) == 1
        assert len(section.right_lanes) == 1


class TestODRSignal:
    """Tests for ODRSignal dataclass."""

    def test_basic_signal(self):
        """Create basic signal."""
        signal = ODRSignal(id="sig1", s=100.0, t=2.0)

        assert signal.id == "sig1"
        assert signal.s == 100.0
        assert signal.t == 2.0
        assert signal.dynamic == "no"
        assert signal.orientation == "+"

    def test_signal_with_value(self):
        """Signal with value (e.g., speed limit)."""
        signal = ODRSignal(
            id="speed50",
            s=0.0,
            t=3.0,
            type="274",
            subtype="50",
            value=50.0,
            unit="km/h"
        )

        assert signal.type == "274"
        assert signal.value == 50.0
        assert signal.unit == "km/h"


class TestODRObject:
    """Tests for ODRObject dataclass."""

    def test_basic_object(self):
        """Create basic object."""
        obj = ODRObject(id="obj1", s=50.0, t=5.0)

        assert obj.id == "obj1"
        assert obj.s == 50.0
        assert obj.t == 5.0
        assert obj.is_parking is False

    def test_parking_object(self):
        """Parking object."""
        obj = ODRObject(
            id="parking1",
            s=0.0,
            t=3.0,
            is_parking=True,
            parking_access="women",
            parking_restrictions="Max 2h"
        )

        assert obj.is_parking is True
        assert obj.parking_access == "women"
        assert obj.parking_restrictions == "Max 2h"


class TestODRConnection:
    """Tests for ODRConnection dataclass."""

    def test_basic_connection(self):
        """Create connection."""
        conn = ODRConnection(
            id="conn1",
            incoming_road="road1",
            connecting_road="road2",
            contact_point="start"
        )

        assert conn.id == "conn1"
        assert conn.incoming_road == "road1"
        assert conn.connecting_road == "road2"
        assert conn.contact_point == "start"

    def test_connection_with_lane_links(self):
        """Connection with lane links."""
        conn = ODRConnection(
            id="conn1",
            incoming_road="road1",
            connecting_road="road2",
            contact_point="start",
            lane_links=[ODRLaneLink(from_lane=-1, to_lane=-1)]
        )

        assert len(conn.lane_links) == 1
        assert conn.lane_links[0].from_lane == -1


class TestODRJunction:
    """Tests for ODRJunction dataclass."""

    def test_basic_junction(self):
        """Create basic junction."""
        junction = ODRJunction(id="junc1", name="Intersection")

        assert junction.id == "junc1"
        assert junction.name == "Intersection"
        assert junction.connections == []

    def test_junction_with_connections(self):
        """Junction with connections."""
        conn = ODRConnection(
            id="c1", incoming_road="r1",
            connecting_road="r2", contact_point="start"
        )
        junction = ODRJunction(id="j1", connections=[conn])

        assert len(junction.connections) == 1


class TestODRJunctionGroup:
    """Tests for ODRJunctionGroup dataclass."""

    def test_roundabout_group(self):
        """Roundabout junction group."""
        group = ODRJunctionGroup(
            id="group1",
            name="Roundabout",
            group_type="roundabout",
            junction_ids=["j1", "j2", "j3"]
        )

        assert group.group_type == "roundabout"
        assert len(group.junction_ids) == 3


class TestODRRoad:
    """Tests for ODRRoad dataclass."""

    def test_basic_road(self):
        """Create basic road."""
        road = ODRRoad(id="road1", name="Main Street", length=500.0)

        assert road.id == "road1"
        assert road.name == "Main Street"
        assert road.length == 500.0
        assert road.junction_id == "-1"

    def test_road_in_junction(self):
        """Road that is part of a junction."""
        road = ODRRoad(id="conn1", junction_id="junc1")

        assert road.junction_id == "junc1"

    def test_road_with_links(self):
        """Road with predecessor/successor."""
        road = ODRRoad(
            id="road1",
            predecessor_type="road",
            predecessor_id="road0",
            predecessor_contact="end",
            successor_type="junction",
            successor_id="junc1",
            successor_contact="start"
        )

        assert road.predecessor_type == "road"
        assert road.predecessor_id == "road0"
        assert road.successor_type == "junction"


class TestODRHeader:
    """Tests for ODRHeader dataclass."""

    def test_default_header(self):
        """Default header values."""
        header = ODRHeader()

        assert header.rev_major == 1
        assert header.rev_minor == 7
        assert header.offset_x == 0.0
        assert header.offset_y == 0.0

    def test_custom_header(self):
        """Custom header values."""
        header = ODRHeader(
            rev_major=1,
            rev_minor=8,
            name="Test Map",
            vendor="ORBIT"
        )

        assert header.rev_minor == 8
        assert header.name == "Test Map"


class TestOpenDriveData:
    """Tests for OpenDriveData dataclass."""

    def test_basic_data(self):
        """Create OpenDrive data."""
        data = OpenDriveData(header=ODRHeader())

        assert data.header is not None
        assert data.geo_reference is None
        assert data.roads == []
        assert data.junctions == []

    def test_data_with_roads(self):
        """Data with roads."""
        road = ODRRoad(id="r1")
        data = OpenDriveData(
            header=ODRHeader(),
            roads=[road]
        )

        assert len(data.roads) == 1




class TestDataclassDefaults:
    """Tests for dataclass default values."""

    def test_lateral_profile_default(self):
        """LateralProfile default values."""
        profile = LateralProfile()
        assert profile.superelevations == []

    def test_lane_offset_record_default(self):
        """LaneOffsetRecord default values."""
        record = LaneOffsetRecord()
        assert record.offsets == []

    def test_lane_road_mark_defaults(self):
        """LaneRoadMark default values."""
        mark = LaneRoadMark(s_offset=0.0, type="solid")
        assert mark.weight == "standard"
        assert mark.color == "white"
        assert mark.width == 0.12

    def test_lane_speed_defaults(self):
        """LaneSpeed default values."""
        speed = LaneSpeed(s_offset=0.0, max_speed=30.0)
        assert speed.unit == "m/s"

    def test_lane_material_defaults(self):
        """LaneMaterial default values."""
        mat = LaneMaterial(s_offset=0.0)
        assert mat.friction == 1.0
        assert mat.roughness is None
        assert mat.surface == "asphalt"

    def test_lane_height_defaults(self):
        """LaneHeight default values."""
        height = LaneHeight(s_offset=0.0)
        assert height.inner == 0.0
        assert height.outer == 0.0

    def test_lane_link_defaults(self):
        """LaneLink default values."""
        link = LaneLink()
        assert link.predecessor_id is None
        assert link.successor_id is None

    def test_odr_signal_defaults(self):
        """ODRSignal default values."""
        signal = ODRSignal(id="sig1", s=0.0, t=0.0)
        assert signal.dynamic == "no"
        assert signal.orientation == "+"
        assert signal.z_offset == 0.0
        assert signal.country == ""
        assert signal.value is None
        assert signal.validity_lanes is None

    def test_odr_object_defaults(self):
        """ODRObject default values."""
        obj = ODRObject(id="obj1", s=0.0, t=0.0)
        assert obj.z_offset == 0.0
        assert obj.type == ""
        assert obj.orientation == 0.0
        assert obj.validity_length is None
        assert obj.is_parking is False

    def test_boundary_segment_defaults(self):
        """ODRBoundarySegment default values."""
        seg = ODRBoundarySegment(segment_type="lane")
        assert seg.road_id is None
        assert seg.boundary_lane is None
        assert seg.contact_point is None

    def test_junction_boundary_defaults(self):
        """ODRJunctionBoundary default values."""
        boundary = ODRJunctionBoundary()
        assert boundary.segments == []

    def test_elevation_grid_point_defaults(self):
        """ODRElevationGridPoint default values."""
        point = ODRElevationGridPoint()
        assert point.center is None
        assert point.left is None
        assert point.right is None

    def test_junction_elevation_grid_defaults(self):
        """ODRJunctionElevationGrid default values."""
        grid = ODRJunctionElevationGrid()
        assert grid.grid_spacing is None
        assert grid.elevations == []

    def test_odr_junction_defaults(self):
        """ODRJunction default values."""
        junction = ODRJunction(id="j1")
        assert junction.name == ""
        assert junction.connections == []
        assert junction.boundary is None
        assert junction.elevation_grid is None

    def test_odr_junction_group_defaults(self):
        """ODRJunctionGroup default values."""
        group = ODRJunctionGroup(id="g1")
        assert group.name == ""
        assert group.group_type == "unknown"
        assert group.junction_ids == []

    def test_odr_road_defaults(self):
        """ODRRoad default values."""
        road = ODRRoad(id="r1")
        assert road.name == ""
        assert road.length == 0.0
        assert road.junction_id == "-1"
        assert road.elevation_profile is None
        assert road.lateral_profile is None
        assert road.lane_offset is None
        assert road.road_type == "unknown"

    def test_open_drive_data_defaults(self):
        """OpenDriveData default values."""
        data = OpenDriveData(header=ODRHeader())
        assert data.geo_reference is None
        assert data.junction_groups == []

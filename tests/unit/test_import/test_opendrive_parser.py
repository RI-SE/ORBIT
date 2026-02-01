"""Tests for orbit.import.opendrive_parser module."""

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


class TestOpenDriveParser:
    """Tests for OpenDriveParser class."""

    @pytest.fixture
    def minimal_xodr(self):
        """Minimal valid OpenDRIVE XML."""
        return '''<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <header revMajor="1" revMinor="7" name="Test" version="1.0"/>
</OpenDRIVE>'''

    @pytest.fixture
    def road_xodr(self):
        """OpenDRIVE with a simple road."""
        return '''<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <header revMajor="1" revMinor="7" name="Test" version="1.0"/>
    <road id="1" name="Main Road" length="100.0" junction="-1">
        <planView>
            <geometry s="0.0" x="0.0" y="0.0" hdg="0.0" length="100.0">
                <line/>
            </geometry>
        </planView>
        <lanes>
            <laneSection s="0.0">
                <center>
                    <lane id="0" type="none" level="false"/>
                </center>
                <right>
                    <lane id="-1" type="driving" level="false">
                        <width sOffset="0.0" a="3.5" b="0.0" c="0.0" d="0.0"/>
                    </lane>
                </right>
            </laneSection>
        </lanes>
    </road>
</OpenDRIVE>'''

    @pytest.fixture
    def junction_xodr(self):
        """OpenDRIVE with junction."""
        return '''<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <header revMajor="1" revMinor="7" name="Test"/>
    <road id="1" name="Road 1" length="100.0" junction="-1">
        <link>
            <successor elementType="junction" elementId="100"/>
        </link>
        <planView>
            <geometry s="0.0" x="0.0" y="0.0" hdg="0.0" length="100.0">
                <line/>
            </geometry>
        </planView>
        <lanes>
            <laneSection s="0.0">
                <center><lane id="0" type="none"/></center>
            </laneSection>
        </lanes>
    </road>
    <junction id="100" name="Test Junction">
        <connection id="1" incomingRoad="1" connectingRoad="2" contactPoint="start">
            <laneLink from="-1" to="-1"/>
        </connection>
    </junction>
</OpenDRIVE>'''

    def test_parser_init(self):
        """Parser initialization."""
        parser = OpenDriveParser()

        assert parser.data is None

    def test_parse_minimal(self, minimal_xodr, tmp_path):
        """Parse minimal OpenDRIVE."""
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(minimal_xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        assert data is not None
        assert data.header.rev_major == 1
        assert data.header.rev_minor == 7
        assert data.header.name == "Test"

    def test_parse_road(self, road_xodr, tmp_path):
        """Parse road with geometry and lanes."""
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(road_xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        assert len(data.roads) == 1
        road = data.roads[0]
        assert road.id == "1"
        assert road.name == "Main Road"
        assert road.length == 100.0
        assert road.junction_id == "-1"

    def test_parse_road_geometry(self, road_xodr, tmp_path):
        """Parse road geometry."""
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(road_xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        road = data.roads[0]
        assert len(road.geometry) == 1
        geom = road.geometry[0]
        assert geom.geometry_type == GeometryType.LINE
        assert geom.s == 0.0
        assert geom.length == 100.0

    def test_parse_road_lanes(self, road_xodr, tmp_path):
        """Parse road lane sections."""
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(road_xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        road = data.roads[0]
        assert len(road.lane_sections) == 1
        section = road.lane_sections[0]
        assert section.s == 0.0
        assert len(section.center_lanes) == 1
        assert len(section.right_lanes) == 1
        assert section.right_lanes[0].id == -1
        assert section.right_lanes[0].type == "driving"

    def test_parse_junction(self, junction_xodr, tmp_path):
        """Parse junction."""
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(junction_xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        assert len(data.junctions) == 1
        junction = data.junctions[0]
        assert junction.id == "100"
        assert junction.name == "Test Junction"
        assert len(junction.connections) == 1

    def test_parse_junction_connection(self, junction_xodr, tmp_path):
        """Parse junction connection."""
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(junction_xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        conn = data.junctions[0].connections[0]
        assert conn.id == "1"
        assert conn.incoming_road == "1"
        assert conn.connecting_road == "2"
        assert conn.contact_point == "start"
        assert len(conn.lane_links) == 1
        assert conn.lane_links[0].from_lane == -1
        assert conn.lane_links[0].to_lane == -1

    def test_parse_road_link(self, junction_xodr, tmp_path):
        """Parse road predecessor/successor links."""
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(junction_xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        road = data.roads[0]
        assert road.successor_type == "junction"
        assert road.successor_id == "100"


class TestParseGeometryTypes:
    """Tests for parsing different geometry types."""

    @pytest.fixture
    def arc_xodr(self):
        """OpenDRIVE with arc geometry."""
        return '''<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <header revMajor="1" revMinor="7" name="Test"/>
    <road id="1" length="50.0" junction="-1">
        <planView>
            <geometry s="0.0" x="0.0" y="0.0" hdg="0.0" length="50.0">
                <arc curvature="0.02"/>
            </geometry>
        </planView>
        <lanes>
            <laneSection s="0.0">
                <center><lane id="0" type="none"/></center>
            </laneSection>
        </lanes>
    </road>
</OpenDRIVE>'''

    @pytest.fixture
    def spiral_xodr(self):
        """OpenDRIVE with spiral geometry."""
        return '''<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <header revMajor="1" revMinor="7" name="Test"/>
    <road id="1" length="50.0" junction="-1">
        <planView>
            <geometry s="0.0" x="0.0" y="0.0" hdg="0.0" length="50.0">
                <spiral curvStart="0.0" curvEnd="0.02"/>
            </geometry>
        </planView>
        <lanes>
            <laneSection s="0.0">
                <center><lane id="0" type="none"/></center>
            </laneSection>
        </lanes>
    </road>
</OpenDRIVE>'''

    def test_parse_arc(self, arc_xodr, tmp_path):
        """Parse arc geometry."""
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(arc_xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        geom = data.roads[0].geometry[0]
        assert geom.geometry_type == GeometryType.ARC
        assert geom.params["curvature"] == 0.02

    def test_parse_spiral(self, spiral_xodr, tmp_path):
        """Parse spiral geometry."""
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(spiral_xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        geom = data.roads[0].geometry[0]
        assert geom.geometry_type == GeometryType.SPIRAL
        assert geom.params["curvStart"] == 0.0
        assert geom.params["curvEnd"] == 0.02


class TestParseSignals:
    """Tests for parsing signals."""

    @pytest.fixture
    def signal_xodr(self):
        """OpenDRIVE with signal."""
        return '''<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <header revMajor="1" revMinor="7" name="Test"/>
    <road id="1" length="100.0" junction="-1">
        <planView>
            <geometry s="0.0" x="0.0" y="0.0" hdg="0.0" length="100.0">
                <line/>
            </geometry>
        </planView>
        <lanes>
            <laneSection s="0.0">
                <center><lane id="0" type="none"/></center>
            </laneSection>
        </lanes>
        <signals>
            <signal id="sig1" s="50.0" t="3.0" dynamic="no" orientation="+"
                    country="SE" type="274" subtype="50" value="50.0" unit="km/h"
                    zOffset="2.0" height="0.6" width="0.6" name="Speed Limit 50"/>
        </signals>
    </road>
</OpenDRIVE>'''

    def test_parse_signal(self, signal_xodr, tmp_path):
        """Parse signal."""
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(signal_xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        road = data.roads[0]
        assert len(road.signals) == 1
        signal = road.signals[0]
        assert signal.id == "sig1"
        assert signal.s == 50.0
        assert signal.t == 3.0
        assert signal.country == "SE"
        assert signal.type == "274"
        assert signal.subtype == "50"
        assert signal.value == 50.0
        assert signal.name == "Speed Limit 50"


class TestParseObjects:
    """Tests for parsing objects."""

    @pytest.fixture
    def object_xodr(self):
        """OpenDRIVE with object."""
        return '''<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <header revMajor="1" revMinor="7" name="Test"/>
    <road id="1" length="100.0" junction="-1">
        <planView>
            <geometry s="0.0" x="0.0" y="0.0" hdg="0.0" length="100.0">
                <line/>
            </geometry>
        </planView>
        <lanes>
            <laneSection s="0.0">
                <center><lane id="0" type="none"/></center>
            </laneSection>
        </lanes>
        <objects>
            <object id="obj1" s="25.0" t="5.0" zOffset="0.0"
                    type="pole" name="Lamppost" height="6.0" radius="0.15"/>
        </objects>
    </road>
</OpenDRIVE>'''

    def test_parse_object(self, object_xodr, tmp_path):
        """Parse object."""
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(object_xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        road = data.roads[0]
        assert len(road.objects) == 1
        obj = road.objects[0]
        assert obj.id == "obj1"
        assert obj.s == 25.0
        assert obj.t == 5.0
        assert obj.type == "pole"
        assert obj.name == "Lamppost"
        assert obj.height == 6.0


class TestParsePoly3Geometry:
    """Tests for parsing poly3 geometry type."""

    @pytest.fixture
    def poly3_xodr(self):
        """OpenDRIVE with poly3 geometry."""
        return '''<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <header revMajor="1" revMinor="7" name="Test"/>
    <road id="1" length="50.0" junction="-1">
        <planView>
            <geometry s="0.0" x="0.0" y="0.0" hdg="0.0" length="50.0">
                <poly3 a="0.0" b="0.5" c="0.01" d="0.001"/>
            </geometry>
        </planView>
        <lanes>
            <laneSection s="0.0">
                <center><lane id="0" type="none"/></center>
            </laneSection>
        </lanes>
    </road>
</OpenDRIVE>'''

    def test_parse_poly3(self, poly3_xodr, tmp_path):
        """Parse poly3 geometry."""
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(poly3_xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        geom = data.roads[0].geometry[0]
        assert geom.geometry_type == GeometryType.POLY3
        assert geom.params["a"] == 0.0
        assert geom.params["b"] == 0.5
        assert geom.params["c"] == 0.01
        assert geom.params["d"] == 0.001


class TestParseParamPoly3Geometry:
    """Tests for parsing paramPoly3 geometry type."""

    @pytest.fixture
    def param_poly3_xodr(self):
        """OpenDRIVE with paramPoly3 geometry."""
        return '''<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <header revMajor="1" revMinor="7" name="Test"/>
    <road id="1" length="50.0" junction="-1">
        <planView>
            <geometry s="0.0" x="0.0" y="0.0" hdg="0.0" length="50.0">
                <paramPoly3 aU="0.0" bU="1.0" cU="0.0" dU="0.0"
                           aV="0.0" bV="0.0" cV="0.5" dV="0.0" pRange="normalized"/>
            </geometry>
        </planView>
        <lanes>
            <laneSection s="0.0">
                <center><lane id="0" type="none"/></center>
            </laneSection>
        </lanes>
    </road>
</OpenDRIVE>'''

    def test_parse_param_poly3(self, param_poly3_xodr, tmp_path):
        """Parse paramPoly3 geometry."""
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(param_poly3_xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        geom = data.roads[0].geometry[0]
        assert geom.geometry_type == GeometryType.PARAM_POLY3
        assert geom.params["aU"] == 0.0
        assert geom.params["bU"] == 1.0
        assert geom.params["cV"] == 0.5
        assert geom.params["pRange"] == "normalized"


class TestParseGeoReference:
    """Tests for parsing geoReference element."""

    @pytest.fixture
    def georef_xodr(self):
        """OpenDRIVE with geoReference."""
        return '''<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <header revMajor="1" revMinor="7" name="Test">
        <geoReference><![CDATA[+proj=tmerc +lat_0=57.7 +lon_0=12.0]]></geoReference>
    </header>
</OpenDRIVE>'''

    def test_parse_geo_reference(self, georef_xodr, tmp_path):
        """Parse geoReference PROJ string."""
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(georef_xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        assert data.geo_reference == "+proj=tmerc +lat_0=57.7 +lon_0=12.0"


class TestParseHeaderOffset:
    """Tests for parsing header offset element."""

    @pytest.fixture
    def offset_xodr(self):
        """OpenDRIVE with header offset (SUMO style)."""
        return '''<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <header revMajor="1" revMinor="7" name="Test" north="100" south="-100" east="200" west="-200" vendor="SUMO">
        <offset x="1000.0" y="2000.0" z="50.0" hdg="0.5"/>
    </header>
</OpenDRIVE>'''

    def test_parse_header_offset(self, offset_xodr, tmp_path):
        """Parse header offset values."""
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(offset_xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        assert data.header.offset_x == 1000.0
        assert data.header.offset_y == 2000.0
        assert data.header.offset_z == 50.0
        assert data.header.offset_hdg == 0.5
        assert data.header.north == 100.0
        assert data.header.south == -100.0
        assert data.header.vendor == "SUMO"


class TestParseLateralProfile:
    """Tests for parsing lateral profile (superelevation)."""

    @pytest.fixture
    def superelevation_xodr(self):
        """OpenDRIVE with superelevation."""
        return '''<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <header revMajor="1" revMinor="7" name="Test"/>
    <road id="1" length="100.0" junction="-1">
        <planView>
            <geometry s="0.0" x="0.0" y="0.0" hdg="0.0" length="100.0">
                <line/>
            </geometry>
        </planView>
        <lateralProfile>
            <superelevation s="0.0" a="0.02" b="0.0" c="0.0" d="0.0"/>
            <superelevation s="50.0" a="0.03" b="0.001" c="0.0" d="0.0"/>
        </lateralProfile>
        <lanes>
            <laneSection s="0.0">
                <center><lane id="0" type="none"/></center>
            </laneSection>
        </lanes>
    </road>
</OpenDRIVE>'''

    def test_parse_superelevation(self, superelevation_xodr, tmp_path):
        """Parse superelevation records."""
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(superelevation_xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        road = data.roads[0]
        assert road.lateral_profile is not None
        assert len(road.lateral_profile.superelevations) == 2
        assert road.lateral_profile.superelevations[0] == (0.0, 0.02, 0.0, 0.0, 0.0)
        assert road.lateral_profile.superelevations[1] == (50.0, 0.03, 0.001, 0.0, 0.0)


class TestParseLaneOffset:
    """Tests for parsing lane offset records."""

    @pytest.fixture
    def lane_offset_xodr(self):
        """OpenDRIVE with lane offset."""
        return '''<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <header revMajor="1" revMinor="7" name="Test"/>
    <road id="1" length="100.0" junction="-1">
        <planView>
            <geometry s="0.0" x="0.0" y="0.0" hdg="0.0" length="100.0">
                <line/>
            </geometry>
        </planView>
        <lanes>
            <laneOffset s="0.0" a="1.0" b="0.0" c="0.0" d="0.0"/>
            <laneOffset s="50.0" a="1.5" b="0.01" c="0.0" d="0.0"/>
            <laneSection s="0.0">
                <center><lane id="0" type="none"/></center>
            </laneSection>
        </lanes>
    </road>
</OpenDRIVE>'''

    def test_parse_lane_offset(self, lane_offset_xodr, tmp_path):
        """Parse lane offset records."""
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(lane_offset_xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        road = data.roads[0]
        assert road.lane_offset is not None
        assert len(road.lane_offset.offsets) == 2
        assert road.lane_offset.offsets[0] == (0.0, 1.0, 0.0, 0.0, 0.0)
        assert road.lane_offset.offsets[1] == (50.0, 1.5, 0.01, 0.0, 0.0)


class TestParseLaneProperties:
    """Tests for parsing lane sub-elements."""

    @pytest.fixture
    def full_lane_xodr(self):
        """OpenDRIVE with lane containing all property types."""
        return '''<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <header revMajor="1" revMinor="7" name="Test"/>
    <road id="1" length="100.0" junction="-1">
        <planView>
            <geometry s="0.0" x="0.0" y="0.0" hdg="0.0" length="100.0">
                <line/>
            </geometry>
        </planView>
        <lanes>
            <laneSection s="0.0">
                <center><lane id="0" type="none"/></center>
                <right>
                    <lane id="-1" type="driving" level="true" direction="standard" advisory="none">
                        <link>
                            <predecessor id="-1"/>
                            <successor id="-2"/>
                        </link>
                        <width sOffset="0.0" a="3.5" b="0.0" c="0.0" d="0.0"/>
                        <roadMark sOffset="0.0" type="solid" weight="bold" color="yellow" width="0.15"/>
                        <speed sOffset="0.0" max="30.0" unit="km/h"/>
                        <material sOffset="0.0" friction="0.9" roughness="0.02" surface="concrete"/>
                        <height sOffset="0.0" inner="0.1" outer="0.15"/>
                    </lane>
                </right>
            </laneSection>
        </lanes>
    </road>
</OpenDRIVE>'''

    def test_parse_lane_road_mark(self, full_lane_xodr, tmp_path):
        """Parse lane road mark."""
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(full_lane_xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        lane = data.roads[0].lane_sections[0].right_lanes[0]
        assert len(lane.road_marks) == 1
        mark = lane.road_marks[0]
        assert mark.s_offset == 0.0
        assert mark.type == "solid"
        assert mark.weight == "bold"
        assert mark.color == "yellow"
        assert mark.width == 0.15

    def test_parse_lane_speed(self, full_lane_xodr, tmp_path):
        """Parse lane speed limit."""
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(full_lane_xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        lane = data.roads[0].lane_sections[0].right_lanes[0]
        assert len(lane.speed_limits) == 1
        speed = lane.speed_limits[0]
        assert speed.s_offset == 0.0
        assert speed.max_speed == 30.0
        assert speed.unit == "km/h"

    def test_parse_lane_material(self, full_lane_xodr, tmp_path):
        """Parse lane material."""
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(full_lane_xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        lane = data.roads[0].lane_sections[0].right_lanes[0]
        assert len(lane.materials) == 1
        mat = lane.materials[0]
        assert mat.s_offset == 0.0
        assert mat.friction == 0.9
        assert mat.roughness == 0.02
        assert mat.surface == "concrete"

    def test_parse_lane_height(self, full_lane_xodr, tmp_path):
        """Parse lane height."""
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(full_lane_xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        lane = data.roads[0].lane_sections[0].right_lanes[0]
        assert len(lane.heights) == 1
        height = lane.heights[0]
        assert height.s_offset == 0.0
        assert height.inner == 0.1
        assert height.outer == 0.15

    def test_parse_lane_link(self, full_lane_xodr, tmp_path):
        """Parse lane predecessor/successor link."""
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(full_lane_xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        lane = data.roads[0].lane_sections[0].right_lanes[0]
        assert lane.link is not None
        assert lane.link.predecessor_id == -1
        assert lane.link.successor_id == -2

    def test_parse_lane_v18_attributes(self, full_lane_xodr, tmp_path):
        """Parse lane V1.8 attributes (direction, advisory)."""
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(full_lane_xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        lane = data.roads[0].lane_sections[0].right_lanes[0]
        assert lane.level is True
        assert lane.direction == "standard"
        assert lane.advisory == "none"


class TestParseSignalValidity:
    """Tests for parsing signal validity."""

    @pytest.fixture
    def signal_validity_xodr(self):
        """OpenDRIVE with signal containing validity elements."""
        return '''<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <header revMajor="1" revMinor="7" name="Test"/>
    <road id="1" length="100.0" junction="-1">
        <planView>
            <geometry s="0.0" x="0.0" y="0.0" hdg="0.0" length="100.0">
                <line/>
            </geometry>
        </planView>
        <lanes>
            <laneSection s="0.0">
                <center><lane id="0" type="none"/></center>
            </laneSection>
        </lanes>
        <signals>
            <signal id="sig1" s="50.0" t="3.0">
                <validity fromLane="-2" toLane="-1"/>
                <validity fromLane="1" toLane="2"/>
            </signal>
        </signals>
    </road>
</OpenDRIVE>'''

    def test_parse_signal_validity(self, signal_validity_xodr, tmp_path):
        """Parse signal validity (which lanes it applies to)."""
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(signal_validity_xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        signal = data.roads[0].signals[0]
        assert signal.validity_lanes is not None
        assert sorted(signal.validity_lanes) == [-2, -1, 1, 2]


class TestParseParkingObject:
    """Tests for parsing parking space objects."""

    @pytest.fixture
    def parking_xodr(self):
        """OpenDRIVE with parking space object."""
        return '''<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <header revMajor="1" revMinor="7" name="Test"/>
    <road id="1" length="100.0" junction="-1">
        <planView>
            <geometry s="0.0" x="0.0" y="0.0" hdg="0.0" length="100.0">
                <line/>
            </geometry>
        </planView>
        <lanes>
            <laneSection s="0.0">
                <center><lane id="0" type="none"/></center>
            </laneSection>
        </lanes>
        <objects>
            <object id="park1" s="25.0" t="5.0" type="parkingSpace" name="P1"
                    length="5.0" width="2.5" hdg="1.57">
                <parkingSpace access="handicapped" restrictions="2 hours max"/>
            </object>
        </objects>
    </road>
</OpenDRIVE>'''

    def test_parse_parking_object(self, parking_xodr, tmp_path):
        """Parse parking space object."""
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(parking_xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        obj = data.roads[0].objects[0]
        assert obj.id == "park1"
        assert obj.is_parking is True
        assert obj.parking_access == "handicapped"
        assert obj.parking_restrictions == "2 hours max"
        assert obj.length == 5.0
        assert obj.width == 2.5
        assert obj.hdg == 1.57


class TestParseJunctionBoundary:
    """Tests for parsing junction boundary (V1.8 feature)."""

    @pytest.fixture
    def junction_boundary_xodr(self):
        """OpenDRIVE with junction boundary."""
        return '''<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <header revMajor="1" revMinor="8" name="Test"/>
    <junction id="100" name="Test Junction">
        <boundary>
            <segment type="lane" roadId="1" boundaryLane="-2" sStart="0.0" sEnd="50.0"/>
            <segment type="joint" roadId="1" contactPoint="end"
                     jointLaneStart="-2" jointLaneEnd="-1" transitionLength="5.0"/>
        </boundary>
    </junction>
</OpenDRIVE>'''

    def test_parse_junction_boundary(self, junction_boundary_xodr, tmp_path):
        """Parse junction boundary segments."""
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(junction_boundary_xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        junction = data.junctions[0]
        assert junction.boundary is not None
        assert len(junction.boundary.segments) == 2

        # Lane segment
        seg1 = junction.boundary.segments[0]
        assert seg1.segment_type == "lane"
        assert seg1.road_id == "1"
        assert seg1.boundary_lane == -2
        assert seg1.s_start == 0.0
        assert seg1.s_end == 50.0

        # Joint segment
        seg2 = junction.boundary.segments[1]
        assert seg2.segment_type == "joint"
        assert seg2.contact_point == "end"
        assert seg2.joint_lane_start == -2
        assert seg2.joint_lane_end == -1
        assert seg2.transition_length == 5.0


class TestParseJunctionElevationGrid:
    """Tests for parsing junction elevation grid (V1.8 feature)."""

    @pytest.fixture
    def junction_elev_grid_xodr(self):
        """OpenDRIVE with junction elevation grid."""
        return '''<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <header revMajor="1" revMinor="8" name="Test"/>
    <junction id="100" name="Test Junction">
        <elevationGrid gridSpacing="1.0">
            <elevation center="10.5" left="10.4" right="10.6"/>
            <elevation center="10.6" left="10.5" right="10.7"/>
        </elevationGrid>
    </junction>
</OpenDRIVE>'''

    def test_parse_junction_elevation_grid(self, junction_elev_grid_xodr, tmp_path):
        """Parse junction elevation grid."""
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(junction_elev_grid_xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        junction = data.junctions[0]
        assert junction.elevation_grid is not None
        assert junction.elevation_grid.grid_spacing == "1.0"
        assert len(junction.elevation_grid.elevations) == 2
        elev = junction.elevation_grid.elevations[0]
        assert elev.center == "10.5"
        assert elev.left == "10.4"
        assert elev.right == "10.6"


class TestParseJunctionGroup:
    """Tests for parsing junction group."""

    @pytest.fixture
    def junction_group_xodr(self):
        """OpenDRIVE with junction group."""
        return '''<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <header revMajor="1" revMinor="7" name="Test"/>
    <junction id="1" name="J1"/>
    <junction id="2" name="J2"/>
    <junction id="3" name="J3"/>
    <junctionGroup id="group1" name="Roundabout" type="roundabout">
        <junctionReference junction="1"/>
        <junctionReference junction="2"/>
        <junctionReference junction="3"/>
    </junctionGroup>
</OpenDRIVE>'''

    def test_parse_junction_group(self, junction_group_xodr, tmp_path):
        """Parse junction group."""
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(junction_group_xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        assert len(data.junction_groups) == 1
        group = data.junction_groups[0]
        assert group.id == "group1"
        assert group.name == "Roundabout"
        assert group.group_type == "roundabout"
        assert group.junction_ids == ["1", "2", "3"]


class TestParseSurfaceCRG:
    """Tests for parsing surface CRG data."""

    @pytest.fixture
    def surface_crg_xodr(self):
        """OpenDRIVE with surface CRG."""
        return '''<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <header revMajor="1" revMinor="7" name="Test"/>
    <road id="1" length="100.0" junction="-1">
        <planView>
            <geometry s="0.0" x="0.0" y="0.0" hdg="0.0" length="100.0">
                <line/>
            </geometry>
        </planView>
        <lanes>
            <laneSection s="0.0">
                <center><lane id="0" type="none"/></center>
            </laneSection>
        </lanes>
        <surface>
            <CRG file="surface.crg" sStart="0.0" sEnd="100.0"
                 orientation="same" mode="attached" purpose="friction"
                 sOffset="5.0" tOffset="1.0" zOffset="0.5" zScale="2.0" hOffset="0.1"/>
        </surface>
    </road>
</OpenDRIVE>'''

    def test_parse_surface_crg(self, surface_crg_xodr, tmp_path):
        """Parse surface CRG data."""
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(surface_crg_xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        road = data.roads[0]
        assert len(road.surface_crg) == 1
        crg = road.surface_crg[0]
        assert crg["file"] == "surface.crg"
        assert crg["sStart"] == 0.0
        assert crg["sEnd"] == 100.0
        assert crg["orientation"] == "same"
        assert crg["mode"] == "attached"
        assert crg["purpose"] == "friction"
        assert crg["sOffset"] == 5.0
        assert crg["tOffset"] == 1.0
        assert crg["zOffset"] == 0.5
        assert crg["zScale"] == 2.0
        assert crg["hOffset"] == 0.1


class TestParseElevationProfile:
    """Additional tests for elevation profile."""

    @pytest.fixture
    def elevation_xodr(self):
        """OpenDRIVE with elevation profile."""
        return '''<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <header revMajor="1" revMinor="7" name="Test"/>
    <road id="1" length="100.0" junction="-1">
        <planView>
            <geometry s="0.0" x="0.0" y="0.0" hdg="0.0" length="100.0">
                <line/>
            </geometry>
        </planView>
        <elevationProfile>
            <elevation s="0.0" a="100.0" b="0.1" c="0.001" d="0.0001"/>
        </elevationProfile>
        <lanes>
            <laneSection s="0.0">
                <center><lane id="0" type="none"/></center>
            </laneSection>
        </lanes>
    </road>
</OpenDRIVE>'''

    def test_parse_elevation_profile(self, elevation_xodr, tmp_path):
        """Parse road elevation profile."""
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(elevation_xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        road = data.roads[0]
        assert road.elevation_profile is not None
        assert len(road.elevation_profile.elevations) == 1
        assert road.elevation_profile.elevations[0] == (0.0, 100.0, 0.1, 0.001, 0.0001)


class TestParseRoadType:
    """Tests for parsing road type."""

    @pytest.fixture
    def road_type_xodr(self):
        """OpenDRIVE with road type element."""
        return '''<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <header revMajor="1" revMinor="7" name="Test"/>
    <road id="1" length="100.0" junction="-1">
        <type s="0.0" type="motorway"/>
        <planView>
            <geometry s="0.0" x="0.0" y="0.0" hdg="0.0" length="100.0">
                <line/>
            </geometry>
        </planView>
        <lanes>
            <laneSection s="0.0">
                <center><lane id="0" type="none"/></center>
            </laneSection>
        </lanes>
    </road>
</OpenDRIVE>'''

    def test_parse_road_type(self, road_type_xodr, tmp_path):
        """Parse road type."""
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(road_type_xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        road = data.roads[0]
        assert road.road_type == "motorway"


class TestParseRoadLinks:
    """Tests for parsing road predecessor/successor links."""

    @pytest.fixture
    def road_links_xodr(self):
        """OpenDRIVE with full road links."""
        return '''<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <header revMajor="1" revMinor="7" name="Test"/>
    <road id="2" length="100.0" junction="-1">
        <link>
            <predecessor elementType="road" elementId="1" contactPoint="end"/>
            <successor elementType="junction" elementId="100" contactPoint="start"/>
        </link>
        <planView>
            <geometry s="0.0" x="0.0" y="0.0" hdg="0.0" length="100.0">
                <line/>
            </geometry>
        </planView>
        <lanes>
            <laneSection s="0.0">
                <center><lane id="0" type="none"/></center>
            </laneSection>
        </lanes>
    </road>
</OpenDRIVE>'''

    def test_parse_road_predecessor(self, road_links_xodr, tmp_path):
        """Parse road predecessor link."""
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(road_links_xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        road = data.roads[0]
        assert road.predecessor_type == "road"
        assert road.predecessor_id == "1"
        assert road.predecessor_contact == "end"

    def test_parse_road_successor(self, road_links_xodr, tmp_path):
        """Parse road successor link."""
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(road_links_xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        road = data.roads[0]
        assert road.successor_type == "junction"
        assert road.successor_id == "100"
        assert road.successor_contact == "start"


class TestParseLaneSectionSingleSide:
    """Tests for parsing lane section singleSide attribute."""

    @pytest.fixture
    def single_side_xodr(self):
        """OpenDRIVE with singleSide lane section."""
        return '''<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <header revMajor="1" revMinor="7" name="Test"/>
    <road id="1" length="100.0" junction="-1">
        <planView>
            <geometry s="0.0" x="0.0" y="0.0" hdg="0.0" length="100.0">
                <line/>
            </geometry>
        </planView>
        <lanes>
            <laneSection s="0.0" singleSide="right">
                <center><lane id="0" type="none"/></center>
                <right>
                    <lane id="-1" type="driving"/>
                </right>
            </laneSection>
        </lanes>
    </road>
</OpenDRIVE>'''

    def test_parse_single_side(self, single_side_xodr, tmp_path):
        """Parse lane section singleSide attribute."""
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(single_side_xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        section = data.roads[0].lane_sections[0]
        assert section.single_side == "right"


class TestParseLeftLanes:
    """Tests for parsing left lanes."""

    @pytest.fixture
    def left_lanes_xodr(self):
        """OpenDRIVE with left lanes."""
        return '''<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <header revMajor="1" revMinor="7" name="Test"/>
    <road id="1" length="100.0" junction="-1">
        <planView>
            <geometry s="0.0" x="0.0" y="0.0" hdg="0.0" length="100.0">
                <line/>
            </geometry>
        </planView>
        <lanes>
            <laneSection s="0.0">
                <left>
                    <lane id="2" type="sidewalk">
                        <width sOffset="0.0" a="1.5"/>
                    </lane>
                    <lane id="1" type="driving">
                        <width sOffset="0.0" a="3.5"/>
                    </lane>
                </left>
                <center><lane id="0" type="none"/></center>
            </laneSection>
        </lanes>
    </road>
</OpenDRIVE>'''

    def test_parse_left_lanes(self, left_lanes_xodr, tmp_path):
        """Parse left lanes."""
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(left_lanes_xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        section = data.roads[0].lane_sections[0]
        assert len(section.left_lanes) == 2
        assert section.left_lanes[0].id == 2
        assert section.left_lanes[0].type == "sidewalk"
        assert section.left_lanes[1].id == 1
        assert section.left_lanes[1].type == "driving"


class TestParserErrorHandling:
    """Tests for parser error handling."""

    def test_parse_invalid_file(self, tmp_path):
        """Parser raises on invalid file."""
        xodr_file = tmp_path / "invalid.xodr"
        xodr_file.write_text("not xml content")

        parser = OpenDriveParser()

        with pytest.raises(Exception) as exc_info:
            parser.parse_file(str(xodr_file))

        assert "Failed to parse OpenDrive file" in str(exc_info.value)

    def test_parse_nonexistent_file(self):
        """Parser raises on nonexistent file."""
        parser = OpenDriveParser()

        with pytest.raises(Exception) as exc_info:
            parser.parse_file("/nonexistent/path.xodr")

        assert "Failed to parse OpenDrive file" in str(exc_info.value)

    def test_parse_no_header(self, tmp_path):
        """Parse file without header creates default header."""
        xodr = '''<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
</OpenDRIVE>'''
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        # Default header values
        assert data.header.rev_major == 1
        assert data.header.rev_minor == 7

    def test_parse_road_no_id(self, tmp_path):
        """Road without ID is skipped."""
        xodr = '''<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <header revMajor="1" revMinor="7" name="Test"/>
    <road name="No ID Road" length="100.0" junction="-1">
        <planView>
            <geometry s="0.0" x="0.0" y="0.0" hdg="0.0" length="100.0">
                <line/>
            </geometry>
        </planView>
        <lanes>
            <laneSection s="0.0">
                <center><lane id="0" type="none"/></center>
            </laneSection>
        </lanes>
    </road>
</OpenDRIVE>'''
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        assert len(data.roads) == 0

    def test_parse_junction_no_id(self, tmp_path):
        """Junction without ID is skipped."""
        xodr = '''<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <header revMajor="1" revMinor="7" name="Test"/>
    <junction name="No ID Junction"/>
</OpenDRIVE>'''
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        assert len(data.junctions) == 0

    def test_parse_signal_no_id(self, tmp_path):
        """Signal without ID is skipped."""
        xodr = '''<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <header revMajor="1" revMinor="7" name="Test"/>
    <road id="1" length="100.0" junction="-1">
        <planView>
            <geometry s="0.0" x="0.0" y="0.0" hdg="0.0" length="100.0">
                <line/>
            </geometry>
        </planView>
        <lanes>
            <laneSection s="0.0">
                <center><lane id="0" type="none"/></center>
            </laneSection>
        </lanes>
        <signals>
            <signal s="50.0" t="3.0"/>
        </signals>
    </road>
</OpenDRIVE>'''
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        assert len(data.roads[0].signals) == 0

    def test_parse_object_no_id(self, tmp_path):
        """Object without ID is skipped."""
        xodr = '''<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <header revMajor="1" revMinor="7" name="Test"/>
    <road id="1" length="100.0" junction="-1">
        <planView>
            <geometry s="0.0" x="0.0" y="0.0" hdg="0.0" length="100.0">
                <line/>
            </geometry>
        </planView>
        <lanes>
            <laneSection s="0.0">
                <center><lane id="0" type="none"/></center>
            </laneSection>
        </lanes>
        <objects>
            <object s="25.0" t="5.0" type="pole"/>
        </objects>
    </road>
</OpenDRIVE>'''
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        assert len(data.roads[0].objects) == 0

    def test_parse_lane_no_id(self, tmp_path):
        """Lane without ID is skipped."""
        xodr = '''<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <header revMajor="1" revMinor="7" name="Test"/>
    <road id="1" length="100.0" junction="-1">
        <planView>
            <geometry s="0.0" x="0.0" y="0.0" hdg="0.0" length="100.0">
                <line/>
            </geometry>
        </planView>
        <lanes>
            <laneSection s="0.0">
                <center><lane type="none"/></center>
                <right><lane type="driving"/></right>
            </laneSection>
        </lanes>
    </road>
</OpenDRIVE>'''
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        section = data.roads[0].lane_sections[0]
        assert len(section.center_lanes) == 0
        assert len(section.right_lanes) == 0

    def test_parse_junction_group_no_id(self, tmp_path):
        """Junction group without ID is skipped."""
        xodr = '''<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <header revMajor="1" revMinor="7" name="Test"/>
    <junctionGroup name="No ID Group" type="roundabout">
        <junctionReference junction="1"/>
    </junctionGroup>
</OpenDRIVE>'''
        xodr_file = tmp_path / "test.xodr"
        xodr_file.write_text(xodr)

        parser = OpenDriveParser()
        data = parser.parse_file(str(xodr_file))

        assert len(data.junction_groups) == 0


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

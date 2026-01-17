"""Tests for orbit.import.opendrive_parser module."""

import importlib
import pytest
from pathlib import Path
import tempfile

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

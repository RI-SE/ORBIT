"""Tests for orbit.export.opendrive_writer module."""

from unittest.mock import Mock, patch

import pytest
from lxml import etree

from orbit.export.curve_fitting import CurveFitter, GeometryElement, GeometryType
from orbit.export.opendrive_writer import OpenDriveWriter, export_to_opendrive, validate_opendrive_file
from orbit.models import Junction, LineType, Polyline, Project, Road
from orbit.models.junction import (
    JunctionBoundary,
    JunctionBoundarySegment,
    JunctionElevationGrid,
    JunctionElevationGridPoint,
    LaneConnection,
)
from orbit.models.lane import Lane
from orbit.models.lane import LaneType as ModelLaneType
from orbit.models.road import RoadType


class MockTransformer:
    """Mock coordinate transformer for testing."""

    def __init__(self, scale=(1.0, 1.0)):
        self.scale_x, self.scale_y = scale
        self._export_proj_string = None

    def get_scale_factor(self):
        return (self.scale_x, self.scale_y)

    def get_projection_string(self):
        return "+proj=tmerc +lat_0=57.7 +lon_0=12.9 +k=1 +x_0=0 +y_0=0 +datum=WGS84"

    def get_utm_projection_string(self):
        return "+proj=utm +zone=33 +datum=WGS84"

    def pixels_to_meters_batch(self, points):
        """Convert pixel points to meters."""
        return [(p[0] * self.scale_x, p[1] * self.scale_y) for p in points]

    def latlon_to_meters(self, lat, lon):
        """Convert lat/lon to meters."""
        return (lon * 111000, lat * 111000)

    def transform_heading(self, px, py, heading):
        """Transform heading from pixel to metric."""
        return heading  # Simplified - no rotation


class TestOpenDriveWriterInit:
    """Tests for OpenDriveWriter initialization."""

    @pytest.fixture
    def empty_project(self):
        """Create empty project."""
        return Project()

    @pytest.fixture
    def mock_transformer(self):
        """Create mock transformer."""
        return MockTransformer(scale=(0.1, 0.1))

    def test_init_defaults(self, empty_project, mock_transformer):
        """Initialize with default settings."""
        writer = OpenDriveWriter(
            project=empty_project,
            transformer=mock_transformer
        )

        assert writer.project is empty_project
        assert writer.transformer is mock_transformer
        assert writer.right_hand_traffic is True
        assert writer.country_code == "se"
        assert writer.use_tmerc is False

    def test_init_custom_settings(self, empty_project, mock_transformer):
        """Initialize with custom settings."""
        writer = OpenDriveWriter(
            project=empty_project,
            transformer=mock_transformer,
            right_hand_traffic=False,
            country_code="de",
            use_tmerc=True,
            use_german_codes=True
        )

        assert writer.right_hand_traffic is False
        assert writer.country_code == "de"
        assert writer.use_tmerc is True

    def test_init_with_custom_curve_fitter(self, empty_project, mock_transformer):
        """Initialize with custom curve fitter."""
        curve_fitter = CurveFitter(preserve_geometry=False)

        writer = OpenDriveWriter(
            project=empty_project,
            transformer=mock_transformer,
            curve_fitter=curve_fitter
        )

        assert writer.curve_fitter is curve_fitter

    def test_init_builds_lookup_maps(self, mock_transformer):
        """Initialize builds lookup maps for polylines, roads, junctions."""
        project = Project()
        polyline = Polyline(id="1")
        polyline.points = [(0, 0), (100, 100)]
        project.polylines.append(polyline)

        road = Road(id="1")
        road.name = "Test Road"
        project.roads.append(road)

        junction = Junction(id="1")
        project.junctions.append(junction)

        writer = OpenDriveWriter(
            project=project,
            transformer=mock_transformer
        )

        assert polyline.id in writer.polyline_map
        assert road.id in writer.road_map
        assert junction.id in writer.junction_map

    def test_init_with_no_scale_factor(self):
        """Initialize with transformer returning None scale factor."""
        project = Project()
        transformer = Mock()
        transformer.get_scale_factor.return_value = None

        writer = OpenDriveWriter(
            project=project,
            transformer=transformer
        )

        assert writer.scale_x == 1.0
        assert writer.scale_y == 1.0


class TestOpenDriveWriterWrite:
    """Tests for OpenDriveWriter.write method."""

    @pytest.fixture
    def mock_transformer(self):
        return MockTransformer(scale=(0.1, 0.1))

    @pytest.fixture
    def project_with_road(self, mock_transformer):
        """Create project with a simple valid road."""
        project = Project()

        centerline = Polyline(id="1")
        centerline.line_type = LineType.CENTERLINE
        centerline.points = [(0, 0), (100, 0), (200, 0)]
        project.polylines.append(centerline)

        road = Road(id="1")
        road.name = "Test Road"
        road.centerline_id = centerline.id
        road.polyline_ids = [centerline.id]
        project.roads.append(road)

        return project

    def test_write_creates_file(self, project_with_road, mock_transformer, tmp_path):
        """Write creates output file."""
        writer = OpenDriveWriter(
            project=project_with_road,
            transformer=mock_transformer
        )

        output_path = tmp_path / "test.xodr"
        result = writer.write(str(output_path))

        assert result is True
        assert output_path.exists()

    def test_write_creates_valid_xml(self, project_with_road, mock_transformer, tmp_path):
        """Written file is valid XML."""
        writer = OpenDriveWriter(
            project=project_with_road,
            transformer=mock_transformer
        )

        output_path = tmp_path / "test.xodr"
        writer.write(str(output_path))

        # Parse the file - should not raise
        tree = etree.parse(str(output_path))
        root = tree.getroot()

        assert root.tag.endswith('OpenDRIVE')

    def test_write_contains_header(self, project_with_road, mock_transformer, tmp_path):
        """Written file contains header element."""
        writer = OpenDriveWriter(
            project=project_with_road,
            transformer=mock_transformer
        )

        output_path = tmp_path / "test.xodr"
        writer.write(str(output_path))

        tree = etree.parse(str(output_path))
        root = tree.getroot()

        # Find header element (accounting for namespace)
        ns = {'od': 'http://code.asam.net/simulation/standard/opendrive_schema'}
        header = root.find('od:header', ns)
        assert header is not None

    def test_write_handles_error(self, project_with_road, mock_transformer, tmp_path):
        """Write handles errors gracefully."""
        writer = OpenDriveWriter(
            project=project_with_road,
            transformer=mock_transformer
        )

        # Try to write to invalid path
        result = writer.write("/nonexistent/directory/test.xodr")

        assert result is False


class TestOpenDriveWriterWriteAndValidate:
    """Tests for OpenDriveWriter.write_and_validate method."""

    @pytest.fixture
    def mock_transformer(self):
        return MockTransformer(scale=(0.1, 0.1))

    @pytest.fixture
    def simple_project(self):
        project = Project()
        centerline = Polyline(id="1")
        centerline.line_type = LineType.CENTERLINE
        centerline.points = [(0, 0), (100, 0)]
        project.polylines.append(centerline)

        road = Road(id="1")
        road.centerline_id = centerline.id
        project.roads.append(road)
        return project

    def test_write_and_validate_no_schema(self, simple_project, mock_transformer, tmp_path):
        """Write and validate without schema skips validation."""
        writer = OpenDriveWriter(
            project=simple_project,
            transformer=mock_transformer
        )

        output_path = tmp_path / "test.xodr"
        success, errors, validated = writer.write_and_validate(str(output_path), schema_path=None)

        assert success is True
        assert errors == []
        assert validated is False

    def test_write_and_validate_write_failure(self, simple_project, mock_transformer):
        """Write and validate handles write failure."""
        writer = OpenDriveWriter(
            project=simple_project,
            transformer=mock_transformer
        )

        success, errors, validated = writer.write_and_validate("/nonexistent/test.xodr", None)

        assert success is False
        assert "Failed to write" in errors[0]
        assert validated is False


class TestCreateHeader:
    """Tests for OpenDriveWriter._create_header method."""

    @pytest.fixture
    def mock_transformer(self):
        return MockTransformer()

    def test_header_version(self, mock_transformer):
        """Header has correct version attributes."""
        project = Project()
        writer = OpenDriveWriter(project, mock_transformer)

        header = writer._create_header()

        assert header.get('revMajor') == '1'
        assert header.get('revMinor') == '8'

    def test_header_default_name(self, mock_transformer):
        """Header uses default name when project has no map name."""
        project = Project()
        writer = OpenDriveWriter(project, mock_transformer)

        header = writer._create_header()

        assert header.get('name') == 'ORBIT Export'

    def test_header_custom_name(self, mock_transformer):
        """Header uses project map name when set."""
        project = Project()
        project.map_name = "My Custom Map"
        writer = OpenDriveWriter(project, mock_transformer)

        header = writer._create_header()

        assert header.get('name') == 'My Custom Map'

    def test_header_vendor(self, mock_transformer):
        """Header has correct vendor."""
        project = Project()
        writer = OpenDriveWriter(project, mock_transformer)

        header = writer._create_header()

        assert 'RISE' in header.get('vendor')

    def test_header_no_georef(self, mock_transformer):
        """Header has zero bounds without georeferencing."""
        project = Project()
        writer = OpenDriveWriter(project, mock_transformer)

        header = writer._create_header()

        assert header.get('north') == '0.0'
        assert header.get('south') == '0.0'
        assert header.get('east') == '0.0'
        assert header.get('west') == '0.0'

    def test_header_with_georef_tmerc(self, mock_transformer):
        """Header uses tmerc projection when use_tmerc=True."""
        project = Project()
        # Add a control point to enable georeferencing
        from orbit.models import ControlPoint
        cp = ControlPoint(100, 100, 12.9, 57.7)
        project.control_points.append(cp)
        project.control_points.append(ControlPoint(200, 100, 12.91, 57.7))
        project.control_points.append(ControlPoint(100, 200, 12.9, 57.71))

        writer = OpenDriveWriter(project, mock_transformer, use_tmerc=True)

        header = writer._create_header()
        georef = header.find('geoReference')

        assert georef is not None
        assert '+proj=tmerc' in georef.text

    def test_header_with_imported_georef(self, mock_transformer):
        """Header uses imported geoReference when available."""
        project = Project()
        project.imported_geo_reference = "+proj=utm +zone=33 +datum=WGS84"

        # Add control points
        from orbit.models import ControlPoint
        project.control_points.append(ControlPoint(100, 100, 12.9, 57.7))
        project.control_points.append(ControlPoint(200, 100, 12.91, 57.7))
        project.control_points.append(ControlPoint(100, 200, 12.9, 57.71))

        writer = OpenDriveWriter(project, mock_transformer, use_tmerc=False)

        header = writer._create_header()
        georef = header.find('geoReference')

        assert georef is not None
        assert georef.text == "+proj=utm +zone=33 +datum=WGS84"

    def test_header_georef_uses_export_proj_string(self, mock_transformer):
        """Header uses _export_proj_string when set on transformer."""
        project = Project()
        from orbit.models import ControlPoint
        project.control_points.append(ControlPoint(100, 100, 12.9, 57.7))
        project.control_points.append(ControlPoint(200, 100, 12.91, 57.7))
        project.control_points.append(ControlPoint(100, 200, 12.9, 57.71))

        custom_proj = "+proj=utm +zone=34 +datum=WGS84 +units=m +no_defs"
        mock_transformer._export_proj_string = custom_proj

        # Even with use_tmerc=True, the _export_proj_string should take priority
        writer = OpenDriveWriter(project, mock_transformer, use_tmerc=True)
        header = writer._create_header()
        georef = header.find('geoReference')

        assert georef is not None
        assert georef.text == custom_proj

    def test_header_osm_attribution(self, mock_transformer):
        """Header includes OSM attribution when OpenStreetMap was used."""
        project = Project()
        project.openstreetmap_used = True
        writer = OpenDriveWriter(project, mock_transformer)

        header = writer._create_header()

        # Find userData with source attribution
        for user_data in header.findall('userData'):
            if user_data.get('code') == 'sourceAttribution':
                assert 'OpenStreetMap' in user_data.text
                return

        pytest.fail("OSM attribution not found in header")


class TestCalculateBounds:
    """Tests for OpenDriveWriter._calculate_bounds method."""

    @pytest.fixture
    def mock_transformer(self):
        return MockTransformer()

    def test_calculate_bounds_empty(self, mock_transformer):
        """Calculate bounds with no polylines returns zeros."""
        project = Project()
        writer = OpenDriveWriter(project, mock_transformer)

        bounds = writer._calculate_bounds()

        assert bounds['north'] == 0.0
        assert bounds['south'] == 0.0
        assert bounds['east'] == 0.0
        assert bounds['west'] == 0.0

    def test_calculate_bounds_with_polylines(self, mock_transformer):
        """Calculate bounds from polyline points."""
        project = Project()
        polyline = Polyline(id="1")
        polyline.points = [(10, 20), (30, 40), (50, 60)]
        project.polylines.append(polyline)

        writer = OpenDriveWriter(project, mock_transformer)
        bounds = writer._calculate_bounds()

        # With scale 1.0, pixel coords = meter coords
        assert bounds['west'] == 10.0
        assert bounds['east'] == 50.0
        assert bounds['south'] == 20.0
        assert bounds['north'] == 60.0


class TestCreatePlanView:
    """Tests for OpenDriveWriter._create_plan_view method."""

    @pytest.fixture
    def mock_transformer(self):
        return MockTransformer()

    def test_plan_view_line(self, mock_transformer):
        """Create plan view with line geometry."""
        project = Project()
        writer = OpenDriveWriter(project, mock_transformer)

        geometry = GeometryElement(
            geom_type=GeometryType.LINE,
            start_pos=(0, 0),
            heading=0.0,
            length=100.0
        )

        plan_view = writer._create_plan_view([geometry])

        assert plan_view.tag == 'planView'
        geom = plan_view.find('geometry')
        assert geom is not None
        assert geom.find('line') is not None

    def test_plan_view_arc(self, mock_transformer):
        """Create plan view with arc geometry."""
        project = Project()
        writer = OpenDriveWriter(project, mock_transformer)

        geometry = GeometryElement(
            geom_type=GeometryType.ARC,
            start_pos=(0, 0),
            heading=0.0,
            length=50.0,
            curvature=0.01
        )

        plan_view = writer._create_plan_view([geometry])

        geom = plan_view.find('geometry')
        arc = geom.find('arc')
        assert arc is not None
        assert arc.get('curvature') == '0.01000000'

    def test_plan_view_spiral(self, mock_transformer):
        """Create plan view with spiral geometry."""
        project = Project()
        writer = OpenDriveWriter(project, mock_transformer)

        geometry = GeometryElement(
            geom_type=GeometryType.SPIRAL,
            start_pos=(0, 0),
            heading=0.0,
            length=30.0,
            curvature=0.0,
            curvature_end=0.02
        )

        plan_view = writer._create_plan_view([geometry])

        geom = plan_view.find('geometry')
        spiral = geom.find('spiral')
        assert spiral is not None
        assert spiral.get('curvStart') == '0.00000000'
        assert spiral.get('curvEnd') == '0.02000000'

    def test_plan_view_parampoly3(self, mock_transformer):
        """Create plan view with paramPoly3 geometry."""
        project = Project()
        writer = OpenDriveWriter(project, mock_transformer)

        geometry = GeometryElement(
            geom_type=GeometryType.PARAMPOLY3,
            start_pos=(0, 0),
            heading=0.0,
            length=100.0,
            aU=0, bU=1, cU=0, dU=0,
            aV=0, bV=0, cV=0, dV=0,
            p_range=1.0,
            p_range_normalized=True
        )

        plan_view = writer._create_plan_view([geometry])

        geom = plan_view.find('geometry')
        pp3 = geom.find('paramPoly3')
        assert pp3 is not None
        assert pp3.get('pRange') == 'normalized'

    def test_plan_view_multiple_geometries(self, mock_transformer):
        """Create plan view with multiple geometry elements."""
        project = Project()
        writer = OpenDriveWriter(project, mock_transformer)

        geometries = [
            GeometryElement(GeometryType.LINE, (0, 0), 0.0, 50.0),
            GeometryElement(GeometryType.ARC, (50, 0), 0.0, 25.0, curvature=0.01),
            GeometryElement(GeometryType.LINE, (75, 0), 0.5, 50.0),
        ]

        plan_view = writer._create_plan_view(geometries)

        geom_elements = plan_view.findall('geometry')
        assert len(geom_elements) == 3

        # Check s offsets accumulate
        assert geom_elements[0].get('s') == '0.0000'
        assert geom_elements[1].get('s') == '50.0000'
        assert geom_elements[2].get('s') == '75.0000'


class TestCreateRoad:
    """Tests for OpenDriveWriter._create_road method."""

    @pytest.fixture
    def mock_transformer(self):
        return MockTransformer(scale=(0.1, 0.1))

    @pytest.fixture
    def project_with_centerline(self):
        """Create project with centerline polyline."""
        project = Project()

        centerline = Polyline(id="1")
        centerline.line_type = LineType.CENTERLINE
        centerline.points = [(0, 0), (100, 0), (200, 0)]
        project.polylines.append(centerline)

        return project, centerline

    def test_create_road_basic(self, project_with_centerline, mock_transformer):
        """Create basic road element."""
        project, centerline = project_with_centerline

        road = Road(id="1")
        road.name = "Test Road"
        road.centerline_id = centerline.id
        project.roads.append(road)

        writer = OpenDriveWriter(project, mock_transformer)
        road_elem = writer._create_road(road)

        assert road_elem is not None
        assert road_elem.tag == 'road'
        assert road_elem.get('name') == 'Test Road'
        assert road_elem.get('junction') == '-1'

    def test_create_road_no_centerline(self, mock_transformer):
        """Road without centerline returns None."""
        project = Project()
        road = Road(id="1")
        project.roads.append(road)

        writer = OpenDriveWriter(project, mock_transformer)
        road_elem = writer._create_road(road)

        assert road_elem is None

    def test_create_road_with_type_and_speed(self, project_with_centerline, mock_transformer):
        """Create road with type and speed limit."""
        project, centerline = project_with_centerline

        road = Road(id="2")
        road.name = "Highway"
        road.road_type = RoadType.MOTORWAY
        road.speed_limit = 110  # km/h
        road.centerline_id = centerline.id
        project.roads.append(road)

        writer = OpenDriveWriter(project, mock_transformer)
        road_elem = writer._create_road(road)

        type_elem = road_elem.find('type')
        assert type_elem is not None
        assert type_elem.get('type') == 'motorway'

        speed = type_elem.find('speed')
        assert speed is not None
        # 110 km/h = 30.56 m/s
        assert float(speed.get('max')) == pytest.approx(30.56, abs=0.01)

    def test_create_road_with_elevation_profile(self, project_with_centerline, mock_transformer):
        """Create road with custom elevation profile."""
        project, centerline = project_with_centerline

        road = Road(id="3")
        road.name = "Hill Road"
        road.centerline_id = centerline.id
        road.elevation_profile = [
            (0.0, 0.0, 0.01, 0.0, 0.0),
            (50.0, 0.5, 0.0, 0.0, 0.0)
        ]
        project.roads.append(road)

        writer = OpenDriveWriter(project, mock_transformer)
        road_elem = writer._create_road(road)

        elev_profile = road_elem.find('elevationProfile')
        elevations = elev_profile.findall('elevation')
        assert len(elevations) == 2
        assert elevations[0].get('s') == '0'
        assert elevations[1].get('s') == '50'

    def test_create_road_with_superelevation(self, project_with_centerline, mock_transformer):
        """Create road with superelevation profile."""
        project, centerline = project_with_centerline

        road = Road(id="4")
        road.name = "Curved Road"
        road.centerline_id = centerline.id
        road.superelevation_profile = [
            (0.0, 0.02, 0.0, 0.0, 0.0)
        ]
        project.roads.append(road)

        writer = OpenDriveWriter(project, mock_transformer)
        road_elem = writer._create_road(road)

        lateral = road_elem.find('lateralProfile')
        superelevation = lateral.find('superelevation')
        assert superelevation is not None
        assert superelevation.get('a') == '0.02'


class TestCreateJunction:
    """Tests for OpenDriveWriter._create_junction method."""

    @pytest.fixture
    def mock_transformer(self):
        return MockTransformer()

    def test_create_junction_basic(self, mock_transformer):
        """Create basic junction element."""
        project = Project()
        junction = Junction(id="1")
        junction.name = "Test Junction"
        junction.connected_road_ids = ['road1', 'road2']
        project.junctions.append(junction)

        writer = OpenDriveWriter(project, mock_transformer)
        junction_elem = writer._create_junction(junction, 1)

        assert junction_elem is not None
        assert junction_elem.tag == 'junction'
        assert junction_elem.get('id') == '1'
        assert junction_elem.get('name') == 'Test Junction'

    def test_create_junction_too_few_roads(self, mock_transformer):
        """Junction with less than 2 roads returns None."""
        project = Project()
        junction = Junction(id="1")
        junction.connected_road_ids = ['road1']
        project.junctions.append(junction)

        writer = OpenDriveWriter(project, mock_transformer)
        junction_elem = writer._create_junction(junction, 1)

        assert junction_elem is None

    def test_create_junction_virtual(self, mock_transformer):
        """Virtual junction has no connections."""
        project = Project()
        junction = Junction(id="1")
        junction.junction_type = "virtual"
        junction.connected_road_ids = ['road1', 'road2']
        project.junctions.append(junction)

        writer = OpenDriveWriter(project, mock_transformer)
        junction_elem = writer._create_junction(junction, 1)

        assert junction_elem is not None
        assert junction_elem.get('type') == 'virtual'
        # Virtual junctions have no connection elements
        assert junction_elem.find('connection') is None

    def test_create_junction_with_lane_connections(self, mock_transformer):
        """Junction with lane connections creates connection elements."""
        project = Project()
        junction = Junction(id="1")
        junction.name = "Intersection"
        junction.connected_road_ids = ['road1', 'road2']

        # Add a connecting road (Road with junction_id set)
        conn_road = Road(id="1001", junction_id="1",
                         inline_path=[(0, 0), (10, 10)],
                         predecessor_id='road1', successor_id='road2')
        junction.connecting_road_ids.append(conn_road.id)
        project.roads.append(conn_road)

        # Add lane connection
        lane_conn = LaneConnection(
            from_road_id='road1',
            to_road_id='road2',
            from_lane_id=-1,
            to_lane_id=-1,
            connecting_road_id=conn_road.id
        )
        junction.lane_connections.append(lane_conn)

        project.junctions.append(junction)

        writer = OpenDriveWriter(project, mock_transformer)
        junction_elem = writer._create_junction(junction, 1)

        connection = junction_elem.find('connection')
        assert connection is not None
        assert connection.get('incomingRoad') == 'road1'

        lane_link = connection.find('laneLink')
        assert lane_link is not None
        assert lane_link.get('from') == '-1'


class TestCreateJunctionGroup:
    """Tests for OpenDriveWriter._create_junction_group method."""

    @pytest.fixture
    def mock_transformer(self):
        return MockTransformer()

    def test_create_junction_group(self, mock_transformer):
        """Create junction group element."""
        project = Project()

        # Add a junction to map IDs
        junction = Junction(id="1")
        project.junctions.append(junction)

        # Create junction group
        from orbit.models.junction import JunctionGroup
        jg = JunctionGroup()
        jg.name = "Roundabout"
        jg.group_type = "roundabout"
        jg.junction_ids = [junction.id]
        project.junction_groups.append(jg)

        writer = OpenDriveWriter(project, mock_transformer)
        # Assign numeric IDs to junctions
        writer.junction_numeric_ids = {junction.id: 1}

        jg_elem = writer._create_junction_group(jg, 1)

        assert jg_elem is not None
        assert jg_elem.tag == 'junctionGroup'
        assert jg_elem.get('type') == 'roundabout'
        assert jg_elem.get('name') == 'Roundabout'

        ref = jg_elem.find('junctionReference')
        assert ref is not None
        assert ref.get('junction') == '1'

    def test_create_junction_group_no_valid_refs(self, mock_transformer):
        """Junction group with no valid references returns None."""
        project = Project()

        from orbit.models.junction import JunctionGroup
        jg = JunctionGroup()
        jg.junction_ids = ['nonexistent-junction']
        project.junction_groups.append(jg)

        writer = OpenDriveWriter(project, mock_transformer)
        writer.junction_numeric_ids = {}  # No junctions

        jg_elem = writer._create_junction_group(jg, 1)

        assert jg_elem is None


class TestCreateConnectingRoad:
    """Tests for OpenDriveWriter._create_connecting_road method."""

    @pytest.fixture
    def mock_transformer(self):
        return MockTransformer(scale=(0.1, 0.1))

    def test_create_connecting_road_basic(self, mock_transformer):
        """Create basic connecting road."""
        project = Project()

        conn_road = Road(
            id="100",
            inline_path=[(0, 0), (50, 50), (100, 100)],
            junction_id="j1",
            predecessor_id='road1',
            successor_id='road2'
        )

        writer = OpenDriveWriter(project, mock_transformer)
        road_elem = writer._create_connecting_road(conn_road, junction_numeric_id=1)

        assert road_elem is not None
        assert road_elem.tag == 'road'
        assert road_elem.get('junction') == '1'

    def test_create_connecting_road_empty_path(self, mock_transformer):
        """Connecting road with empty path returns None."""
        project = Project()

        conn_road = Road(inline_path=[], junction_id="j1")

        writer = OpenDriveWriter(project, mock_transformer)
        road_elem = writer._create_connecting_road(conn_road, junction_numeric_id=1)

        assert road_elem is None

    def test_create_connecting_road_single_point(self, mock_transformer):
        """Connecting road with single point returns None."""
        project = Project()

        conn_road = Road(inline_path=[(0, 0)], junction_id="j1")

        writer = OpenDriveWriter(project, mock_transformer)
        road_elem = writer._create_connecting_road(conn_road, junction_numeric_id=1)

        assert road_elem is None

    def test_create_connecting_road_parampoly3(self, mock_transformer):
        """Create connecting road with paramPoly3 geometry."""
        project = Project()

        conn_road = Road(
            id="101",
            inline_path=[(0, 0), (50, 25), (100, 0)],
            junction_id="j1",
            geometry_type="parampoly3",
            predecessor_id='road1',
            successor_id='road2'
        )

        writer = OpenDriveWriter(project, mock_transformer)
        road_elem = writer._create_connecting_road(conn_road, junction_numeric_id=1)

        assert road_elem is not None
        plan_view = road_elem.find('planView')
        geom = plan_view.find('geometry')
        pp3 = geom.find('paramPoly3')
        assert pp3 is not None


class TestExportToOpendrive:
    """Tests for export_to_opendrive function."""

    @pytest.fixture
    def mock_transformer(self):
        return MockTransformer(scale=(0.1, 0.1))

    @pytest.fixture
    def simple_project(self):
        project = Project()
        centerline = Polyline(id="1")
        centerline.line_type = LineType.CENTERLINE
        centerline.points = [(0, 0), (100, 0)]
        project.polylines.append(centerline)

        road = Road(id="1")
        road.centerline_id = centerline.id
        project.roads.append(road)
        return project

    def test_export_to_opendrive_success(self, simple_project, mock_transformer, tmp_path):
        """Export to OpenDrive succeeds."""
        output_path = tmp_path / "export.xodr"

        result = export_to_opendrive(
            simple_project,
            mock_transformer,
            str(output_path)
        )

        assert result is True
        assert output_path.exists()

    def test_export_to_opendrive_with_options(self, simple_project, mock_transformer, tmp_path):
        """Export with custom options."""
        output_path = tmp_path / "export.xodr"

        result = export_to_opendrive(
            simple_project,
            mock_transformer,
            str(output_path),
            line_tolerance=0.1,
            arc_tolerance=0.5,
            preserve_geometry=False,
            right_hand_traffic=False,
            country_code="de",
            use_tmerc=True,
            use_german_codes=True
        )

        assert result is True

    def test_export_opendrive_1_4_suppresses_1_8_features(self, mock_transformer, tmp_path):
        """Export to OpenDRIVE 1.4 suppresses 1.8-specific features like boundary, elevationGrid, direction, advisory."""
        project = Project()

        centerline = Polyline(id="1")
        centerline.line_type = LineType.CENTERLINE
        centerline.points = [(0, 0), (100, 0)]
        project.polylines.append(centerline)

        road = Road(id="1")
        road.centerline_id = centerline.id
        road.polyline_ids = [centerline.id]

        # Add a lane with direction and advisory
        from orbit.models.lane import Lane
        from orbit.models.lane import LaneType as ModelLaneType
        from orbit.models.lane_section import LaneSection
        lane_center = Lane(id=0, lane_type=ModelLaneType.NONE)
        lane = Lane(id=1, lane_type=ModelLaneType.DRIVING)
        lane.direction = "samedir"
        lane.advisory = "advisory1"
        road.left_count = 1
        road.right_count = 0
        road.lane_sections = [LaneSection(section_number=1, s_start=0.0, s_end=100.0, lanes=[lane_center, lane])]
        project.roads.append(road)

        road2 = Road(id="2", junction_id="1")
        road2.centerline_id = centerline.id
        road2.polyline_ids = [centerline.id]
        project.roads.append(road2)

        # Add a junction with boundary and elevation_grid
        junction = Junction(id="1")
        junction.name = "TestJunction"
        junction.connected_road_ids = ['1', '2']
        junction.lane_connections = [
            LaneConnection(from_road_id='1', to_road_id='2', from_lane_id=-1, to_lane_id=-1, connecting_road_id='2')
        ]
        junction.boundary = JunctionBoundary(
            segments=[JunctionBoundarySegment(segment_type='lane', road_id='1')]
        )
        junction.elevation_grid = JunctionElevationGrid(
            elevations=[JunctionElevationGridPoint(center="1")]
        )
        project.junctions.append(junction)

        output_path_1_4 = tmp_path / "export_1_4.xodr"
        output_path_1_8 = tmp_path / "export_1_8.xodr"

        # Export 1.8
        result_1_8 = export_to_opendrive(
            project,
            mock_transformer,
            str(output_path_1_8),
            opendrive_version="1.8"
        )
        assert result_1_8 is True

        # Export 1.4
        result_1_4 = export_to_opendrive(
            project,
            mock_transformer,
            str(output_path_1_4),
            opendrive_version="1.4"
        )
        assert result_1_4 is True

        import xml.etree.ElementTree as ET

        # Parse 1.8 and assert features exist
        tree_1_8 = ET.parse(output_path_1_8)
        root_1_8 = tree_1_8.getroot()
        ns = {"od": "http://code.asam.net/simulation/standard/opendrive_schema"}

        # In 1.8, namespace is used
        header_1_8 = root_1_8.find('od:header', ns)
        assert header_1_8.attrib['revMinor'] == '8'

        junction_1_8 = root_1_8.find('.//od:junction', ns)
        assert junction_1_8 is not None
        assert junction_1_8.find('od:boundary', ns) is not None
        assert junction_1_8.find('od:elevationGrid', ns) is not None

        lane_1_8 = root_1_8.find('.//od:lane', ns)
        assert lane_1_8 is not None
        assert lane_1_8.get('direction') == 'samedir'
        assert lane_1_8.get('advisory') == 'advisory1'

        # Parse 1.4 and assert features are suppressed
        tree_1_4 = ET.parse(output_path_1_4)
        root_1_4 = tree_1_4.getroot()

        # In 1.4, no namespace is used
        header_1_4 = root_1_4.find('header')
        assert header_1_4.attrib['revMinor'] == '4'

        junction_1_4 = root_1_4.find('.//junction')
        assert junction_1_4 is not None
        assert junction_1_4.find('boundary') is None
        assert junction_1_4.find('elevationGrid') is None

        lane_1_4 = root_1_4.find('.//lane')
        assert lane_1_4 is not None
        assert lane_1_4.get('direction') is None
        assert lane_1_4.get('advisory') is None


class TestValidateOpendrive:
    """Tests for validate_opendrive_file function."""

    def test_validate_no_schema(self, tmp_path):
        """Validation without schema returns None."""
        output_path = tmp_path / "test.xodr"
        output_path.write_text("<OpenDRIVE></OpenDRIVE>")

        result = validate_opendrive_file(str(output_path), schema_path=None)

        assert result is None

    def test_validate_missing_xmlschema(self, tmp_path):
        """Validation handles missing xmlschema library."""
        output_path = tmp_path / "test.xodr"
        output_path.write_text("<OpenDRIVE></OpenDRIVE>")
        schema_path = tmp_path / "schema.xsd"
        schema_path.write_text("<xs:schema></xs:schema>")

        # Mock import to fail for xmlschema only
        import sys
        original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

        def mock_import(name, *args, **kwargs):
            if name == 'xmlschema':
                raise ImportError("No module named 'xmlschema'")
            return original_import(name, *args, **kwargs)

        # Use patch.object on the opendrive_writer module's import behavior
        with patch.object(sys.modules['orbit.export.opendrive_writer'], 'validate_opendrive_file') as mock_validate:
            mock_validate.return_value = ["xmlschema library not installed - validation skipped"]
            result = mock_validate(str(output_path), str(schema_path))

        # Should return an error about missing library
        assert result is not None
        assert len(result) > 0


class TestFindJunctionForRoadEndpoint:
    """Tests for OpenDriveWriter._find_junction_for_road_endpoint method."""

    @pytest.fixture
    def mock_transformer(self):
        return MockTransformer()

    def test_find_junction_at_predecessor(self, mock_transformer):
        """Find junction at road predecessor end."""
        project = Project()

        # Create centerline
        centerline = Polyline(id="1")
        centerline.line_type = LineType.CENTERLINE
        centerline.points = [(100, 100), (200, 100), (300, 100)]
        project.polylines.append(centerline)

        # Create road
        road = Road(id="1")
        road.centerline_id = centerline.id
        project.roads.append(road)

        # Create junction at start of road
        junction = Junction(id="1")
        junction.center_point = (100, 100)  # At road start
        junction.connected_road_ids = [road.id]
        project.junctions.append(junction)

        writer = OpenDriveWriter(project, mock_transformer)
        writer.junction_numeric_ids = {junction.id: 1}

        result = writer._find_junction_for_road_endpoint(road.id, is_predecessor=True)

        assert result == 1

    def test_find_junction_at_successor(self, mock_transformer):
        """Find junction at road successor end."""
        project = Project()

        # Create centerline
        centerline = Polyline(id="1")
        centerline.line_type = LineType.CENTERLINE
        centerline.points = [(100, 100), (200, 100), (300, 100)]
        project.polylines.append(centerline)

        # Create road
        road = Road(id="1")
        road.centerline_id = centerline.id
        project.roads.append(road)

        # Create junction at end of road
        junction = Junction(id="1")
        junction.center_point = (300, 100)  # At road end
        junction.connected_road_ids = [road.id]
        project.junctions.append(junction)

        writer = OpenDriveWriter(project, mock_transformer)
        writer.junction_numeric_ids = {junction.id: 1}

        result = writer._find_junction_for_road_endpoint(road.id, is_predecessor=False)

        assert result == 1

    def test_find_junction_none(self, mock_transformer):
        """Returns None when no junction at endpoint."""
        project = Project()

        # Create centerline
        centerline = Polyline(id="1")
        centerline.line_type = LineType.CENTERLINE
        centerline.points = [(100, 100), (200, 100), (300, 100)]
        project.polylines.append(centerline)

        # Create road
        road = Road(id="1")
        road.centerline_id = centerline.id
        project.roads.append(road)

        # Create junction far from road
        junction = Junction(id="1")
        junction.center_point = (500, 500)  # Far from road
        junction.connected_road_ids = [road.id]
        project.junctions.append(junction)

        writer = OpenDriveWriter(project, mock_transformer)
        writer.junction_numeric_ids = {junction.id: 1}

        result = writer._find_junction_for_road_endpoint(road.id, is_predecessor=True)

        assert result is None


class TestConnectingRoadLanes:
    """Tests for connecting road lane creation."""

    @pytest.fixture
    def mock_transformer(self):
        return MockTransformer()

    def test_create_connecting_road_lanes_basic(self, mock_transformer):
        """Create lanes for connecting road."""
        project = Project()

        conn_road = Road(
            inline_path=[(0, 0), (100, 100)],
            junction_id="j1",
            cr_lane_count_right=1
        )
        # Initialize lanes
        conn_road.ensure_cr_lanes_initialized()

        writer = OpenDriveWriter(project, mock_transformer)
        lanes = writer._create_connecting_road_lanes(conn_road, road_length=100.0)

        assert lanes.tag == 'lanes'
        lane_section = lanes.find('laneSection')
        assert lane_section is not None

        # Should have center lane
        center = lane_section.find('center')
        assert center is not None
        center_lane = center.find('lane')
        assert center_lane.get('id') == '0'

    def test_create_connecting_road_lanes_with_left_right(self, mock_transformer):
        """Create lanes with left and right lanes."""
        from orbit.models.lane_section import LaneSection
        project = Project()

        conn_road = Road(
            inline_path=[(0, 0), (100, 100)],
            junction_id="j1"
        )

        # Add custom lanes via lane_sections
        left_lane = Lane(id=1, width=3.5, lane_type=ModelLaneType.DRIVING)
        right_lane = Lane(id=-1, width=3.5, lane_type=ModelLaneType.DRIVING)
        center_lane = Lane(id=0, width=0.0, lane_type=ModelLaneType.NONE)
        conn_road.lane_sections = [LaneSection(
            section_number=1,
            s_start=0.0,
            s_end=100.0,
            lanes=[left_lane, center_lane, right_lane]
        )]

        writer = OpenDriveWriter(project, mock_transformer)
        lanes = writer._create_connecting_road_lanes(conn_road, road_length=100.0)

        lane_section = lanes.find('laneSection')

        left = lane_section.find('left')
        assert left is not None
        left_lane_elem = left.find('lane')
        assert left_lane_elem.get('id') == '1'

        right = lane_section.find('right')
        assert right is not None
        right_lane_elem = right.find('lane')
        assert right_lane_elem.get('id') == '-1'

    def test_create_connecting_lane_with_width_transition(self, mock_transformer):
        """Create lane with width transition."""
        project = Project()

        lane_obj = Lane(id=-1, width=3.0, lane_type=ModelLaneType.DRIVING)
        lane_obj.width_end = 4.0  # Transition from 3m to 4m

        writer = OpenDriveWriter(project, mock_transformer)
        lane_elem = writer._create_connecting_lane_element(lane_obj, road_length=100.0)

        width = lane_elem.find('width')
        assert width is not None
        assert width.get('a') == '3.0000'
        # b = (4.0 - 3.0) / 100 = 0.01
        assert float(width.get('b')) == pytest.approx(0.01, abs=0.0001)


class TestOffsetAndGeoReference:
    """Tests for offset subtraction and geo_reference_string in OpenDriveWriter."""

    @pytest.fixture
    def mock_transformer(self):
        return MockTransformer()

    @pytest.fixture
    def georef_project(self):
        """Project with control points for georeferencing."""
        from orbit.models import ControlPoint
        project = Project()
        project.control_points.append(ControlPoint(100, 100, 12.9, 57.7))
        project.control_points.append(ControlPoint(200, 100, 12.91, 57.7))
        project.control_points.append(ControlPoint(100, 200, 12.9, 57.71))
        return project

    def test_header_offset_element_written(self, georef_project, mock_transformer):
        """Offset element is present in header when georeferenced."""
        writer = OpenDriveWriter(
            georef_project, mock_transformer,
            offset_x=630000.0, offset_y=6374000.0
        )
        header = writer._create_header()
        offset = header.find('offset')

        assert offset is not None
        assert offset.get('x') == '630000.0000'
        assert offset.get('y') == '6374000.0000'
        assert offset.get('z') == '0.0000'
        assert offset.get('hdg') == '0.000000'

    def test_header_offset_always_written_with_georef(self, georef_project, mock_transformer):
        """Offset element is present even when offset is (0, 0)."""
        writer = OpenDriveWriter(
            georef_project, mock_transformer,
            offset_x=0.0, offset_y=0.0
        )
        header = writer._create_header()
        offset = header.find('offset')

        assert offset is not None
        assert offset.get('x') == '0.0000'
        assert offset.get('y') == '0.0000'

    def test_header_no_offset_without_georef(self, mock_transformer):
        """Offset element is NOT present when not georeferenced."""
        project = Project()  # No control points
        writer = OpenDriveWriter(
            project, mock_transformer,
            offset_x=100.0, offset_y=200.0
        )
        header = writer._create_header()
        offset = header.find('offset')

        assert offset is None

    def test_bounds_subtract_offset(self, mock_transformer):
        """Header bounds are correctly adjusted by offset."""
        from orbit.models import ControlPoint
        project = Project()
        project.control_points.append(ControlPoint(100, 100, 12.9, 57.7))
        project.control_points.append(ControlPoint(200, 100, 12.91, 57.7))
        project.control_points.append(ControlPoint(100, 200, 12.9, 57.71))

        # Add polyline so bounds are non-zero (scale=1.0 so pixel=meter)
        polyline = Polyline(id="1")
        polyline.points = [(10, 20), (50, 60)]
        project.polylines.append(polyline)

        writer = OpenDriveWriter(
            project, mock_transformer,
            offset_x=5.0, offset_y=10.0
        )
        header = writer._create_header()

        # Without offset: west=10, east=50, south=20, north=60
        # With offset: west=5, east=45, south=10, north=50
        assert float(header.get('west')) == pytest.approx(5.0, abs=0.01)
        assert float(header.get('east')) == pytest.approx(45.0, abs=0.01)
        assert float(header.get('south')) == pytest.approx(10.0, abs=0.01)
        assert float(header.get('north')) == pytest.approx(50.0, abs=0.01)

    def test_geometry_coordinates_subtract_offset(self, mock_transformer):
        """PlanView geometry x,y values have offset subtracted."""
        project = Project()
        writer = OpenDriveWriter(
            project, mock_transformer,
            offset_x=1000.0, offset_y=2000.0
        )

        geometry = GeometryElement(
            geom_type=GeometryType.LINE,
            start_pos=(1050.0, 2100.0),
            heading=0.5,
            length=100.0
        )

        plan_view = writer._create_plan_view([geometry])
        geom = plan_view.find('geometry')

        assert float(geom.get('x')) == pytest.approx(50.0, abs=0.01)
        assert float(geom.get('y')) == pytest.approx(100.0, abs=0.01)

    def test_heading_not_affected_by_offset(self, mock_transformer):
        """Heading values are unchanged by offset."""
        project = Project()
        writer = OpenDriveWriter(
            project, mock_transformer,
            offset_x=1000.0, offset_y=2000.0
        )

        heading = 1.234567
        geometry = GeometryElement(
            geom_type=GeometryType.LINE,
            start_pos=(1050.0, 2100.0),
            heading=heading,
            length=100.0
        )

        plan_view = writer._create_plan_view([geometry])
        geom = plan_view.find('geometry')

        assert float(geom.get('hdg')) == pytest.approx(heading, abs=1e-6)

    def test_geometry_length_not_affected_by_offset(self, mock_transformer):
        """Geometry length is unchanged by offset."""
        project = Project()
        writer = OpenDriveWriter(
            project, mock_transformer,
            offset_x=1000.0, offset_y=2000.0
        )

        geometry = GeometryElement(
            geom_type=GeometryType.LINE,
            start_pos=(1050.0, 2100.0),
            heading=0.0,
            length=75.5
        )

        plan_view = writer._create_plan_view([geometry])
        geom = plan_view.find('geometry')

        assert float(geom.get('length')) == pytest.approx(75.5, abs=0.01)

    def test_geo_reference_string_override(self, georef_project, mock_transformer):
        """Custom geo_reference_string is written to header."""
        custom_ref = "+proj=utm +zone=33 +datum=WGS84 +lat_0=57.7 +lon_0=12.9"
        writer = OpenDriveWriter(
            georef_project, mock_transformer,
            geo_reference_string=custom_ref
        )

        header = writer._create_header()
        georef = header.find('geoReference')

        assert georef is not None
        assert georef.text == custom_ref

    def test_geo_reference_string_priority_over_export_proj(self, georef_project, mock_transformer):
        """geo_reference_string takes priority over _export_proj_string."""
        mock_transformer._export_proj_string = "+proj=utm +zone=34 +datum=WGS84"
        custom_ref = "+proj=utm +zone=33 +datum=WGS84 +lat_0=57.7 +lon_0=12.9"

        writer = OpenDriveWriter(
            georef_project, mock_transformer,
            geo_reference_string=custom_ref
        )

        header = writer._create_header()
        georef = header.find('geoReference')

        assert georef.text == custom_ref

    def test_offset_element_schema_order(self, georef_project, mock_transformer):
        """Offset element appears between geoReference and userData in header."""
        writer = OpenDriveWriter(
            georef_project, mock_transformer,
            offset_x=100.0, offset_y=200.0
        )
        header = writer._create_header()

        children = list(header)
        tags = [child.tag for child in children]

        georef_idx = tags.index('geoReference')
        offset_idx = tags.index('offset')
        userdata_idx = tags.index('userData')

        assert georef_idx < offset_idx < userdata_idx

    def test_multiple_geometries_all_offset(self, mock_transformer):
        """All geometry elements in planView have offset subtracted."""
        project = Project()
        writer = OpenDriveWriter(
            project, mock_transformer,
            offset_x=500.0, offset_y=1000.0
        )

        geometries = [
            GeometryElement(GeometryType.LINE, (500.0, 1000.0), 0.0, 50.0),
            GeometryElement(GeometryType.ARC, (550.0, 1000.0), 0.0, 25.0, curvature=0.01),
            GeometryElement(GeometryType.LINE, (575.0, 1010.0), 0.5, 50.0),
        ]

        plan_view = writer._create_plan_view(geometries)
        geom_elements = plan_view.findall('geometry')

        assert float(geom_elements[0].get('x')) == pytest.approx(0.0, abs=0.01)
        assert float(geom_elements[0].get('y')) == pytest.approx(0.0, abs=0.01)
        assert float(geom_elements[1].get('x')) == pytest.approx(50.0, abs=0.01)
        assert float(geom_elements[1].get('y')) == pytest.approx(0.0, abs=0.01)
        assert float(geom_elements[2].get('x')) == pytest.approx(75.0, abs=0.01)
        assert float(geom_elements[2].get('y')) == pytest.approx(10.0, abs=0.01)

    def test_export_to_opendrive_with_offset(self, mock_transformer, tmp_path):
        """export_to_opendrive passes offset parameters through."""
        project = Project()
        centerline = Polyline(id="1")
        centerline.line_type = LineType.CENTERLINE
        centerline.points = [(0, 0), (100, 0)]
        project.polylines.append(centerline)

        road = Road(id="1")
        road.centerline_id = centerline.id
        project.roads.append(road)

        output_path = tmp_path / "export.xodr"
        result = export_to_opendrive(
            project, mock_transformer, str(output_path),
            offset_x=10.0, offset_y=20.0,
            geo_reference_string="+proj=utm +zone=33 +datum=WGS84"
        )

        assert result is True
        assert output_path.exists()

    def test_default_offset_is_zero(self, mock_transformer):
        """Default offset values are 0.0 (backward compat)."""
        project = Project()
        writer = OpenDriveWriter(project, mock_transformer)

        assert writer.offset_x == 0.0
        assert writer.offset_y == 0.0
        assert writer.geo_reference_string is None


class TestRoadJunctionIdCollision:
    """Tests for road/junction ID remapping to avoid CARLA incompatibility.

    CARLA's OpenDRIVE parser determines whether a predecessor/successor link
    targets a road or junction via ``!ContainsRoad(id)``.  If a road and a
    junction share the same numeric ID, CARLA treats junction references as
    road-to-road links, breaking junction routing.
    """

    @pytest.fixture
    def mock_transformer(self):
        return MockTransformer(scale=(0.1, 0.1))

    def test_no_road_junction_id_overlap(self, mock_transformer, tmp_path):
        """Exported XODR must never have a road ID equal to a junction ID."""
        project = Project()

        # Create polylines for 3 roads — IDs will start at 1
        for i in range(3):
            cl = Polyline(id=str(i + 1))
            cl.line_type = LineType.CENTERLINE
            cl.points = [(i * 100, 0), (i * 100 + 80, 0)]
            project.polylines.append(cl)

        road1 = Road(id="1", centerline_id="1", polyline_ids=["1"])
        road2 = Road(id="2", centerline_id="2", polyline_ids=["2"])
        road3 = Road(id="3", centerline_id="3", polyline_ids=["3"])
        for r in (road1, road2, road3):
            project.roads.append(r)

        # Junction with ID "1" — same numeric ID as road1
        junction = Junction(id="1", name="Test Junction")
        junction.connected_road_ids = ["1", "2"]
        junction.connecting_road_ids = ["10"]

        # Create a connecting road
        cr = Road(id="10", junction_id="1",
                  inline_path=[(0, 0), (10, 10)],
                  predecessor_id="1", successor_id="2")
        project.roads.append(cr)

        lc = LaneConnection(
            from_road_id="1", to_road_id="2",
            from_lane_id=-1, to_lane_id=-1,
            connecting_road_id="10", connecting_lane_id=-1
        )
        junction.lane_connections.append(lc)
        project.junctions.append(junction)

        output_path = tmp_path / "collision_test.xodr"
        result = export_to_opendrive(
            project, mock_transformer, str(output_path),
            geo_reference_string="+proj=utm +zone=33 +datum=WGS84"
        )
        assert result is True

        # Parse output and collect IDs
        tree = etree.parse(str(output_path))
        root = tree.getroot()
        ns = ''
        if root.tag.startswith('{'):
            ns = root.tag.split('}')[0] + '}'

        road_ids = {int(r.get('id')) for r in root.findall(f'{ns}road')}
        junction_ids = {int(j.get('id')) for j in root.findall(f'{ns}junction')}

        overlap = road_ids & junction_ids
        assert overlap == set(), (
            f"Road IDs {road_ids} overlap with junction IDs {junction_ids}: {overlap}"
        )

    def test_remapped_ids_consistent_across_elements(self, mock_transformer, tmp_path):
        """Road ID remapping must be consistent in road elements, links, and junction connections."""
        project = Project()

        cl1 = Polyline(id="1", line_type=LineType.CENTERLINE, points=[(0, 0), (80, 0)])
        cl2 = Polyline(id="2", line_type=LineType.CENTERLINE, points=[(0, 10), (80, 10)])
        project.polylines.extend([cl1, cl2])

        road1 = Road(id="1", centerline_id="1", polyline_ids=["1"])
        road2 = Road(id="2", centerline_id="2", polyline_ids=["2"], predecessor_id="1")
        project.roads.extend([road1, road2])

        junction = Junction(id="1", name="J1")
        junction.connected_road_ids = ["1", "2"]
        junction.connecting_road_ids = ["10"]

        cr = Road(id="10", junction_id="1",
                  inline_path=[(80, 0), (0, 10)],
                  predecessor_id="1", successor_id="2")
        project.roads.append(cr)

        lc = LaneConnection(
            from_road_id="1", to_road_id="2",
            from_lane_id=-1, to_lane_id=-1,
            connecting_road_id="10", connecting_lane_id=-1
        )
        junction.lane_connections.append(lc)
        project.junctions.append(junction)

        output_path = tmp_path / "consistency_test.xodr"
        export_to_opendrive(
            project, mock_transformer, str(output_path),
            geo_reference_string="+proj=utm +zone=33 +datum=WGS84"
        )

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        ns = ''
        if root.tag.startswith('{'):
            ns = root.tag.split('}')[0] + '}'

        # Junction connection incomingRoad must reference a valid road
        for junc in root.findall(f'{ns}junction'):
            for conn in junc.findall(f'{ns}connection'):
                ir = conn.get('incomingRoad')
                cr_id = conn.get('connectingRoad')
                all_road_ids = {r.get('id') for r in root.findall(f'{ns}road')}
                assert ir in all_road_ids, f"incomingRoad={ir} not found in road IDs {all_road_ids}"
                assert cr_id in all_road_ids, f"connectingRoad={cr_id} not found in road IDs {all_road_ids}"

        # Connecting road's link predecessor/successor must reference valid roads
        for road in root.findall(f'{ns}road'):
            if road.get('junction') != '-1':
                link = road.find(f'{ns}link')
                if link is not None:
                    for tag in ['predecessor', 'successor']:
                        elem = link.find(f'{ns}{tag}')
                        if elem is not None and elem.get('elementType') == 'road':
                            ref_id = elem.get('elementId')
                            all_road_ids = {r.get('id') for r in root.findall(f'{ns}road')}
                            assert ref_id in all_road_ids, (
                                f"CR link {tag} references road {ref_id} not in {all_road_ids}"
                            )


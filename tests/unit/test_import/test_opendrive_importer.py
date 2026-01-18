"""Tests for orbit.import.opendrive_importer module."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from dataclasses import dataclass
import math
import importlib

# Import using importlib since 'import' is a reserved keyword
opendrive_importer = importlib.import_module('orbit.import.opendrive_importer')
opendrive_parser = importlib.import_module('orbit.import.opendrive_parser')

# Import classes
ImportMode = opendrive_importer.ImportMode
ImportOptions = opendrive_importer.ImportOptions
ImportResult = opendrive_importer.ImportResult
OpenDriveImporter = opendrive_importer.OpenDriveImporter

from orbit.models import Project, Road, Polyline, Junction
from orbit.models.lane import Lane, LaneType as ORBITLaneType
from orbit.models.polyline import LineType, RoadMarkType
from orbit.models.road import RoadType


class TestImportMode:
    """Tests for ImportMode enum."""

    def test_add_mode(self):
        """ADD mode has value 'add'."""
        assert ImportMode.ADD.value == "add"

    def test_replace_mode(self):
        """REPLACE mode has value 'replace'."""
        assert ImportMode.REPLACE.value == "replace"


class TestImportOptions:
    """Tests for ImportOptions dataclass."""

    def test_default_values(self):
        """Default values are set correctly."""
        options = ImportOptions()

        assert options.import_mode == ImportMode.ADD
        assert options.scale_pixels_per_meter == 10.0
        assert options.auto_create_control_points is False
        assert options.verbose is False

    def test_custom_values(self):
        """Custom values can be set."""
        options = ImportOptions(
            import_mode=ImportMode.REPLACE,
            scale_pixels_per_meter=5.0,
            auto_create_control_points=True,
            verbose=True
        )

        assert options.import_mode == ImportMode.REPLACE
        assert options.scale_pixels_per_meter == 5.0
        assert options.auto_create_control_points is True
        assert options.verbose is True


class TestImportResult:
    """Tests for ImportResult dataclass."""

    def test_default_values(self):
        """Default values are set correctly."""
        result = ImportResult()

        assert result.success is False
        assert result.error_message is None
        assert result.roads_imported == 0
        assert result.connecting_roads_imported == 0
        assert result.junctions_imported == 0
        assert result.signals_imported == 0
        assert result.objects_imported == 0
        assert result.parking_imported == 0
        assert result.polylines_imported == 0
        assert result.control_points_created == 0
        assert result.roads_skipped_duplicate == 0
        assert result.geometry_conversions == []
        assert result.features_skipped == {}
        assert result.elevation_profiles_imported == 0
        assert result.warnings == []
        assert result.transform_mode is None
        assert result.scale_used is None

    def test_success_result(self):
        """Successful import result."""
        result = ImportResult(
            success=True,
            roads_imported=5,
            junctions_imported=2,
            signals_imported=3,
            objects_imported=10,
            parking_imported=4,
            polylines_imported=5
        )

        assert result.success is True
        assert result.roads_imported == 5
        assert result.junctions_imported == 2
        assert result.signals_imported == 3
        assert result.objects_imported == 10
        assert result.parking_imported == 4
        assert result.polylines_imported == 5

    def test_error_result(self):
        """Error result with message."""
        result = ImportResult(
            success=False,
            error_message="File not found"
        )

        assert result.success is False
        assert result.error_message == "File not found"

    def test_with_warnings(self):
        """Result with warnings."""
        result = ImportResult(
            success=True,
            warnings=["Road 1 has no lanes", "Junction 2 has no connections"]
        )

        assert result.success is True
        assert len(result.warnings) == 2


class MockTransformer:
    """Mock coordinate transformer for testing."""

    def __init__(self, scale=(1.0, 1.0)):
        self.scale_x, self.scale_y = scale

    def get_scale_factor(self):
        return (self.scale_x, self.scale_y)

    def pixels_to_meters_batch(self, points):
        return [(p[0] * self.scale_x, p[1] * self.scale_y) for p in points]

    def meters_to_latlon(self, x_m, y_m):
        # Simple mock conversion
        return (y_m / 111000, x_m / 111000)

    def pixel_to_geo(self, px, py):
        return (px / 111000, py / 111000)


class TestOpenDriveImporterInit:
    """Tests for OpenDriveImporter initialization."""

    @pytest.fixture
    def empty_project(self):
        return Project()

    @pytest.fixture
    def mock_transformer(self):
        return MockTransformer()

    def test_init(self, empty_project, mock_transformer):
        """Initialize OpenDriveImporter."""
        importer = OpenDriveImporter(
            project=empty_project,
            orbit_transformer=mock_transformer,
            image_width=1000,
            image_height=800
        )

        assert importer.project is empty_project
        assert importer.orbit_transformer is mock_transformer
        assert importer.image_width == 1000
        assert importer.image_height == 800

    def test_init_sets_tracking(self, empty_project, mock_transformer):
        """OpenDriveImporter initializes tracking dicts and sets."""
        importer = OpenDriveImporter(
            project=empty_project,
            orbit_transformer=mock_transformer,
            image_width=1000,
            image_height=800
        )

        assert importer.odr_road_to_orbit == {}
        assert importer.odr_junction_to_orbit == {}
        assert importer.imported_odr_road_ids == set()
        assert importer.pending_connecting_roads == []


class TestConvertRoadType:
    """Tests for _convert_road_type method."""

    @pytest.fixture
    def importer(self):
        project = Project()
        return OpenDriveImporter(project, None, 1000, 800)

    def test_motorway(self, importer):
        """Convert motorway type."""
        result = importer._convert_road_type('motorway')
        assert result == RoadType.MOTORWAY

    def test_rural(self, importer):
        """Convert rural type."""
        result = importer._convert_road_type('rural')
        assert result == RoadType.RURAL

    def test_town(self, importer):
        """Convert town type."""
        result = importer._convert_road_type('town')
        assert result == RoadType.TOWN

    def test_low_speed(self, importer):
        """Convert lowSpeed type."""
        result = importer._convert_road_type('lowSpeed')
        assert result == RoadType.LOW_SPEED

    def test_pedestrian(self, importer):
        """Convert pedestrian type."""
        result = importer._convert_road_type('pedestrian')
        assert result == RoadType.PEDESTRIAN

    def test_bicycle(self, importer):
        """Convert bicycle type."""
        result = importer._convert_road_type('bicycle')
        assert result == RoadType.BICYCLE

    def test_unknown(self, importer):
        """Unknown type returns UNKNOWN."""
        result = importer._convert_road_type('something_else')
        assert result == RoadType.UNKNOWN


class TestConvertLaneType:
    """Tests for _convert_lane_type method."""

    @pytest.fixture
    def importer(self):
        project = Project()
        return OpenDriveImporter(project, None, 1000, 800)

    def test_driving(self, importer):
        """Convert driving lane type."""
        result = importer._convert_lane_type('driving')
        assert result == ORBITLaneType.DRIVING

    def test_biking(self, importer):
        """Convert biking lane type."""
        result = importer._convert_lane_type('biking')
        assert result == ORBITLaneType.BIKING

    def test_sidewalk(self, importer):
        """Convert sidewalk lane type."""
        result = importer._convert_lane_type('sidewalk')
        assert result == ORBITLaneType.SIDEWALK

    def test_border(self, importer):
        """Convert border lane type."""
        result = importer._convert_lane_type('border')
        assert result == ORBITLaneType.BORDER

    def test_parking(self, importer):
        """Convert parking lane type."""
        result = importer._convert_lane_type('parking')
        assert result == ORBITLaneType.PARKING

    def test_unknown_defaults_driving(self, importer):
        """Unknown type defaults to DRIVING."""
        result = importer._convert_lane_type('unknown_type')
        assert result == ORBITLaneType.DRIVING


class TestConvertRoadMarkType:
    """Tests for _convert_road_mark_type method."""

    @pytest.fixture
    def importer(self):
        project = Project()
        return OpenDriveImporter(project, None, 1000, 800)

    def test_solid(self, importer):
        """Convert solid road mark type."""
        result = importer._convert_road_mark_type('solid')
        assert result == RoadMarkType.SOLID

    def test_broken(self, importer):
        """Convert broken road mark type."""
        result = importer._convert_road_mark_type('broken')
        assert result == RoadMarkType.BROKEN

    def test_solid_solid(self, importer):
        """Convert solid solid road mark type."""
        result = importer._convert_road_mark_type('solid solid')
        assert result == RoadMarkType.SOLID_SOLID

    def test_solid_broken(self, importer):
        """Convert solid broken road mark type."""
        result = importer._convert_road_mark_type('solid broken')
        assert result == RoadMarkType.SOLID_BROKEN

    def test_broken_solid(self, importer):
        """Convert broken solid road mark type."""
        result = importer._convert_road_mark_type('broken solid')
        assert result == RoadMarkType.BROKEN_SOLID

    def test_curb(self, importer):
        """Convert curb road mark type."""
        result = importer._convert_road_mark_type('curb')
        assert result == RoadMarkType.CURB

    def test_grass(self, importer):
        """Convert grass road mark type."""
        result = importer._convert_road_mark_type('grass')
        assert result == RoadMarkType.GRASS

    def test_unknown_defaults_solid(self, importer):
        """Unknown type defaults to SOLID."""
        result = importer._convert_road_mark_type('unknown')
        assert result == RoadMarkType.SOLID


class TestConvertSignalType:
    """Tests for _convert_signal_type method."""

    @pytest.fixture
    def importer(self):
        project = Project()
        return OpenDriveImporter(project, None, 1000, 800)

    @pytest.fixture
    def mock_signal(self):
        """Create mock ODRSignal."""
        signal = Mock()
        signal.type = ""
        signal.value = ""
        signal.country = ""
        signal.dynamic = "no"
        return signal

    def test_swedish_stop_sign(self, importer, mock_signal):
        """Convert Swedish stop sign (code 201)."""
        from orbit.models.signal import SignalType
        mock_signal.type = "201"
        mock_signal.country = "se"

        signal_type, value = importer._convert_signal_type(mock_signal)

        assert signal_type == SignalType.STOP
        assert value is None

    def test_swedish_give_way(self, importer, mock_signal):
        """Convert Swedish give way sign (code 206)."""
        from orbit.models.signal import SignalType
        mock_signal.type = "206"
        mock_signal.country = "se"

        signal_type, value = importer._convert_signal_type(mock_signal)

        assert signal_type == SignalType.GIVE_WAY

    def test_swedish_speed_limit(self, importer, mock_signal):
        """Convert Swedish speed limit sign (code 274)."""
        from orbit.models.signal import SignalType
        mock_signal.type = "274"
        mock_signal.value = "50"
        mock_signal.country = "se"

        signal_type, value = importer._convert_signal_type(mock_signal)

        assert signal_type == SignalType.SPEED_LIMIT
        assert value == 50

    def test_german_stop_sign(self, importer, mock_signal):
        """Convert German stop sign (code 206)."""
        from orbit.models.signal import SignalType
        mock_signal.type = "206"
        mock_signal.country = "de"

        signal_type, value = importer._convert_signal_type(mock_signal)

        assert signal_type == SignalType.STOP

    def test_text_speed_limit(self, importer, mock_signal):
        """Convert text-based speed limit."""
        from orbit.models.signal import SignalType
        mock_signal.type = "speed_limit"
        mock_signal.value = "70"
        mock_signal.country = ""

        signal_type, value = importer._convert_signal_type(mock_signal)

        assert signal_type == SignalType.SPEED_LIMIT
        assert value == 70

    def test_text_stop(self, importer, mock_signal):
        """Convert text-based stop sign."""
        from orbit.models.signal import SignalType
        mock_signal.type = "stop_sign"

        signal_type, value = importer._convert_signal_type(mock_signal)

        assert signal_type == SignalType.STOP

    def test_traffic_signal(self, importer, mock_signal):
        """Convert traffic signal."""
        from orbit.models.signal import SignalType
        mock_signal.type = "traffic_signal"
        mock_signal.dynamic = "yes"

        signal_type, value = importer._convert_signal_type(mock_signal)

        assert signal_type == SignalType.TRAFFIC_SIGNALS

    def test_unsupported_type(self, importer, mock_signal):
        """Unsupported type returns None."""
        mock_signal.type = "unknown_sign_type"
        mock_signal.country = ""

        signal_type, value = importer._convert_signal_type(mock_signal)

        assert signal_type is None
        assert value is None


class TestConvertObjectType:
    """Tests for _convert_object_type method."""

    @pytest.fixture
    def importer(self):
        project = Project()
        return OpenDriveImporter(project, None, 1000, 800)

    def test_lamppost(self, importer):
        """Convert lamppost object type."""
        from orbit.models.object import ObjectType
        result = importer._convert_object_type('lamp')
        assert result == ObjectType.LAMPPOST

    def test_pole(self, importer):
        """Convert pole object type."""
        from orbit.models.object import ObjectType
        result = importer._convert_object_type('pole')
        assert result == ObjectType.LAMPPOST

    def test_guardrail(self, importer):
        """Convert guardrail object type."""
        from orbit.models.object import ObjectType
        result = importer._convert_object_type('guardrail')
        assert result == ObjectType.GUARDRAIL

    def test_barrier(self, importer):
        """Convert barrier object type."""
        from orbit.models.object import ObjectType
        result = importer._convert_object_type('barrier')
        assert result == ObjectType.GUARDRAIL

    def test_building(self, importer):
        """Convert building object type."""
        from orbit.models.object import ObjectType
        result = importer._convert_object_type('building')
        assert result == ObjectType.BUILDING

    def test_tree(self, importer):
        """Convert tree object type."""
        from orbit.models.object import ObjectType
        result = importer._convert_object_type('tree')
        assert result == ObjectType.TREE_BROADLEAF

    def test_conifer_tree(self, importer):
        """Convert conifer tree object type."""
        from orbit.models.object import ObjectType
        result = importer._convert_object_type('tree_conifer')
        assert result == ObjectType.TREE_CONIFER

    def test_bush(self, importer):
        """Convert bush object type."""
        from orbit.models.object import ObjectType
        result = importer._convert_object_type('bush')
        assert result == ObjectType.BUSH

    def test_unsupported(self, importer):
        """Unsupported type returns None."""
        result = importer._convert_object_type('unknown_object')
        assert result is None


class TestShouldSkipRoad:
    """Tests for _should_skip_road method."""

    @pytest.fixture
    def importer(self):
        project = Project()
        return OpenDriveImporter(project, None, 1000, 800)

    @pytest.fixture
    def mock_odr_road(self):
        road = Mock()
        road.id = "road_1"
        return road

    def test_replace_mode_never_skips(self, importer, mock_odr_road):
        """In REPLACE mode, roads are never skipped."""
        options = ImportOptions(import_mode=ImportMode.REPLACE)
        importer.imported_odr_road_ids.add("road_1")

        result = importer._should_skip_road(mock_odr_road, options)

        assert result is False

    def test_add_mode_skips_duplicate(self, importer, mock_odr_road):
        """In ADD mode, duplicate roads are skipped."""
        options = ImportOptions(import_mode=ImportMode.ADD)
        importer.imported_odr_road_ids.add("road_1")

        result = importer._should_skip_road(mock_odr_road, options)

        assert result is True

    def test_add_mode_new_road_not_skipped(self, importer, mock_odr_road):
        """In ADD mode, new roads are not skipped."""
        options = ImportOptions(import_mode=ImportMode.ADD)

        result = importer._should_skip_road(mock_odr_road, options)

        assert result is False


class TestCollectSamplePoints:
    """Tests for _collect_sample_points method."""

    @pytest.fixture
    def importer(self):
        project = Project()
        imp = OpenDriveImporter(project, None, 1000, 800)
        # Mock odr_data
        imp.odr_data = Mock()
        return imp

    def test_collects_from_all_roads(self, importer):
        """Collects points from all roads."""
        # Mock roads with geometry
        road1 = Mock()
        road1.geometry = [Mock(x=0, y=0), Mock(x=100, y=100)]

        road2 = Mock()
        road2.geometry = [Mock(x=200, y=200)]

        importer.odr_data.roads = [road1, road2]

        points = importer._collect_sample_points()

        assert len(points) == 3
        assert (0, 0) in points
        assert (100, 100) in points
        assert (200, 200) in points

    def test_empty_roads(self, importer):
        """Returns empty list for empty roads."""
        importer.odr_data.roads = []

        points = importer._collect_sample_points()

        assert points == []


class TestFindAllSharedPoints:
    """Tests for _find_all_shared_points method."""

    @pytest.fixture
    def project(self):
        return Project()

    @pytest.fixture
    def importer(self, project):
        return OpenDriveImporter(project, None, 1000, 800)

    def test_find_shared_endpoint(self, importer):
        """Find shared point at road endpoints."""
        # Create two roads with touching endpoints
        centerline1 = Polyline()
        centerline1.line_type = LineType.CENTERLINE
        centerline1.points = [(0, 0), (100, 100)]
        importer.project.polylines.append(centerline1)

        road1 = Road()
        road1.centerline_id = centerline1.id
        importer.project.roads.append(road1)

        centerline2 = Polyline()
        centerline2.line_type = LineType.CENTERLINE
        centerline2.points = [(100, 100), (200, 0)]  # Starts where road1 ends
        importer.project.polylines.append(centerline2)

        road2 = Road()
        road2.centerline_id = centerline2.id
        importer.project.roads.append(road2)

        shared = importer._find_all_shared_points(road1.id, road2.id, tolerance=10.0)

        assert len(shared) == 1
        assert shared[0] == (100, 100)

    def test_no_shared_points(self, importer):
        """No shared points between distant roads."""
        centerline1 = Polyline()
        centerline1.line_type = LineType.CENTERLINE
        centerline1.points = [(0, 0), (100, 0)]
        importer.project.polylines.append(centerline1)

        road1 = Road()
        road1.centerline_id = centerline1.id
        importer.project.roads.append(road1)

        centerline2 = Polyline()
        centerline2.line_type = LineType.CENTERLINE
        centerline2.points = [(500, 500), (600, 500)]  # Far away
        importer.project.polylines.append(centerline2)

        road2 = Road()
        road2.centerline_id = centerline2.id
        importer.project.roads.append(road2)

        shared = importer._find_all_shared_points(road1.id, road2.id, tolerance=10.0)

        assert shared == []

    def test_missing_road_returns_empty(self, importer):
        """Returns empty list if road doesn't exist."""
        shared = importer._find_all_shared_points("nonexistent1", "nonexistent2")

        assert shared == []


class TestCalculatePositionFromST:
    """Tests for _calculate_position_from_st method."""

    @pytest.fixture
    def importer(self):
        project = Project()
        imp = OpenDriveImporter(project, None, 1000, 800)
        imp.coord_transform = Mock()
        imp.coord_transform.metric_to_pixel = Mock(return_value=(500.0, 500.0))
        return imp

    def test_calculate_position_simple(self, importer):
        """Calculate position for simple straight road."""
        mock_road = Mock()
        mock_geom = Mock()
        mock_geom.s = 0
        mock_geom.length = 100
        mock_geom.x = 0
        mock_geom.y = 0
        mock_geom.hdg = 0  # Heading east
        mock_road.geometry = [mock_geom]

        result = importer._calculate_position_from_st(50.0, 0.0, mock_road)

        assert result == (500.0, 500.0)

    def test_calculate_position_with_offset(self, importer):
        """Calculate position with lateral offset."""
        mock_road = Mock()
        mock_geom = Mock()
        mock_geom.s = 0
        mock_geom.length = 100
        mock_geom.x = 0
        mock_geom.y = 0
        mock_geom.hdg = 0  # Heading east
        mock_road.geometry = [mock_geom]

        # s=50, t=5 (5m to the left)
        result = importer._calculate_position_from_st(50.0, 5.0, mock_road)

        # Should be called with offset applied
        assert importer.coord_transform.metric_to_pixel.called

    def test_calculate_position_no_geometry(self, importer):
        """Returns None if no geometry."""
        mock_road = Mock()
        mock_road.geometry = []

        result = importer._calculate_position_from_st(50.0, 0.0, mock_road)

        assert result is None


class TestImportResult:
    """Additional tests for ImportResult."""

    def test_total_imported(self):
        """Calculate total imported items."""
        result = ImportResult(
            success=True,
            roads_imported=10,
            junctions_imported=5,
            signals_imported=3,
            objects_imported=7,
            parking_imported=2
        )

        total = (result.roads_imported +
                 result.junctions_imported +
                 result.signals_imported +
                 result.objects_imported +
                 result.parking_imported)

        assert total == 27

    def test_result_with_transform_info(self):
        """Result with transform information."""
        result = ImportResult(
            success=True,
            transform_mode="georeferenced",
            scale_used=0.5
        )

        assert result.transform_mode == "georeferenced"
        assert result.scale_used == 0.5


class TestConvertLane:
    """Tests for _convert_lane method."""

    @pytest.fixture
    def importer(self):
        project = Project()
        return OpenDriveImporter(project, None, 1000, 800)

    @pytest.fixture
    def mock_odr_lane(self):
        lane = Mock()
        lane.id = -1
        lane.type = "driving"
        lane.widths = []
        lane.road_marks = []
        lane.speed_limits = []
        lane.materials = []
        lane.heights = []
        lane.link = None
        lane.direction = "forward"
        lane.advisory = None
        lane.level = False
        return lane

    def test_convert_lane_basic(self, importer, mock_odr_lane):
        """Convert basic lane."""
        result = importer._convert_lane(mock_odr_lane, 'right')

        assert result.id == -1
        assert result.lane_type == ORBITLaneType.DRIVING
        assert result.width == 3.5  # Default

    def test_convert_lane_with_width(self, importer, mock_odr_lane):
        """Convert lane with width polynomial."""
        width = Mock()
        width.a = 4.0
        width.b = 0.01
        width.c = 0.0
        width.d = 0.0
        mock_odr_lane.widths = [width]

        result = importer._convert_lane(mock_odr_lane, 'right')

        assert result.width == 4.0
        assert result.width_b == 0.01

    def test_convert_lane_with_road_mark(self, importer, mock_odr_lane):
        """Convert lane with road mark."""
        mark = Mock()
        mark.type = "broken"
        mark.color = "yellow"
        mark.weight = "standard"
        mark.width = 0.15
        mock_odr_lane.road_marks = [mark]

        result = importer._convert_lane(mock_odr_lane, 'right')

        assert result.road_mark_type == RoadMarkType.BROKEN
        assert result.road_mark_color == "yellow"
        assert result.road_mark_width == 0.15

    def test_convert_lane_with_speed_limit(self, importer, mock_odr_lane):
        """Convert lane with speed limit."""
        speed = Mock()
        speed.max_speed = 50.0
        speed.unit = "km/h"
        mock_odr_lane.speed_limits = [speed]

        result = importer._convert_lane(mock_odr_lane, 'right')

        assert result.speed_limit == 50.0
        assert result.speed_limit_unit == "km/h"

    def test_convert_lane_with_link(self, importer, mock_odr_lane):
        """Convert lane with predecessor/successor links."""
        link = Mock()
        link.predecessor_id = 1
        link.successor_id = 2
        mock_odr_lane.link = link

        result = importer._convert_lane(mock_odr_lane, 'right')

        assert result.predecessor_id == 1
        assert result.successor_id == 2

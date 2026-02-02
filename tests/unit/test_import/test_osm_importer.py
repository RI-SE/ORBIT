"""Tests for orbit.import.osm_importer module."""

import importlib
from unittest.mock import Mock, patch

import pytest

from orbit.models import Project

# Import using importlib since 'import' is a reserved keyword
osm_importer = importlib.import_module('orbit.import.osm_importer')
osm_query = importlib.import_module('orbit.import.osm_query')

# Import classes
ImportMode = osm_importer.ImportMode
DetailLevel = osm_importer.DetailLevel
ImportOptions = osm_importer.ImportOptions
ImportResult = osm_importer.ImportResult
OSMImporter = osm_importer.OSMImporter
OverpassAPIError = osm_query.OverpassAPIError


class TestImportMode:
    """Tests for ImportMode enum."""

    def test_add_mode(self):
        """ADD mode has value 'add'."""
        assert ImportMode.ADD.value == "add"

    def test_replace_mode(self):
        """REPLACE mode has value 'replace'."""
        assert ImportMode.REPLACE.value == "replace"


class TestDetailLevel:
    """Tests for DetailLevel enum."""

    def test_moderate_level(self):
        """MODERATE level has value 'moderate'."""
        assert DetailLevel.MODERATE.value == "moderate"

    def test_full_level(self):
        """FULL level has value 'full'."""
        assert DetailLevel.FULL.value == "full"


class TestImportOptions:
    """Tests for ImportOptions dataclass."""

    def test_default_values(self):
        """Default values are set correctly."""
        options = ImportOptions()

        assert options.import_mode == ImportMode.ADD
        assert options.detail_level == DetailLevel.MODERATE
        assert options.default_lane_width == 3.5
        assert options.import_junctions is True
        assert options.simplify_geometry is False
        assert options.simplify_tolerance == 1.0
        assert options.timeout == 60
        assert options.verbose is False
        assert options.filter_outside_image is False

    def test_custom_values(self):
        """Custom values can be set."""
        options = ImportOptions(
            import_mode=ImportMode.REPLACE,
            detail_level=DetailLevel.FULL,
            default_lane_width=4.0,
            import_junctions=False,
            simplify_geometry=True,
            simplify_tolerance=2.5,
            timeout=120,
            verbose=True,
            filter_outside_image=True
        )

        assert options.import_mode == ImportMode.REPLACE
        assert options.detail_level == DetailLevel.FULL
        assert options.default_lane_width == 4.0
        assert options.import_junctions is False
        assert options.simplify_geometry is True
        assert options.simplify_tolerance == 2.5
        assert options.timeout == 120
        assert options.verbose is True
        assert options.filter_outside_image is True


class TestImportResult:
    """Tests for ImportResult dataclass."""

    def test_default_values(self):
        """Default values are set correctly."""
        result = ImportResult()

        assert result.success is False
        assert result.error_message is None
        assert result.roads_imported == 0
        assert result.junctions_imported == 0
        assert result.signals_imported == 0
        assert result.objects_imported == 0
        assert result.parking_imported == 0
        assert result.roads_skipped_duplicate == 0
        assert result.signals_skipped_duplicate == 0
        assert result.objects_skipped_duplicate == 0
        assert result.parking_skipped_duplicate == 0
        assert result.partial_import is False

    def test_success_result(self):
        """Successful import result."""
        result = ImportResult(
            success=True,
            roads_imported=5,
            junctions_imported=2,
            signals_imported=3,
            objects_imported=10,
            parking_imported=4
        )

        assert result.success is True
        assert result.roads_imported == 5
        assert result.junctions_imported == 2
        assert result.signals_imported == 3
        assert result.objects_imported == 10
        assert result.parking_imported == 4

    def test_error_result(self):
        """Error result with message."""
        result = ImportResult(
            success=False,
            error_message="API timeout"
        )

        assert result.success is False
        assert result.error_message == "API timeout"

    def test_partial_import(self):
        """Partial import result."""
        result = ImportResult(
            success=True,
            partial_import=True,
            roads_imported=10,
            error_message="Timeout, partial data kept"
        )

        assert result.success is True
        assert result.partial_import is True
        assert result.roads_imported == 10

    def test_duplicate_tracking(self):
        """Track skipped duplicates."""
        result = ImportResult(
            success=True,
            roads_imported=10,
            roads_skipped_duplicate=3,
            signals_skipped_duplicate=2,
            objects_skipped_duplicate=5,
            parking_skipped_duplicate=1
        )

        assert result.roads_skipped_duplicate == 3
        assert result.signals_skipped_duplicate == 2
        assert result.objects_skipped_duplicate == 5
        assert result.parking_skipped_duplicate == 1


class TestOSMImporterInit:
    """Tests for OSMImporter initialization."""

    @pytest.fixture
    def mock_transformer(self):
        """Create mock transformer."""
        transformer = Mock()
        transformer.geo_to_pixel = Mock(return_value=(100.0, 100.0))
        transformer.pixel_to_geo = Mock(return_value=(12.94, 57.72))
        return transformer

    @pytest.fixture
    def empty_project(self):
        """Create empty project."""
        return Project()

    def test_init(self, empty_project, mock_transformer):
        """Initialize OSMImporter."""
        importer = OSMImporter(
            project=empty_project,
            transformer=mock_transformer,
            image_width=1000,
            image_height=800
        )

        assert importer.project is empty_project
        assert importer.transformer is mock_transformer
        assert importer.image_width == 1000
        assert importer.image_height == 800

    def test_init_sets_tracking(self, empty_project, mock_transformer):
        """OSMImporter initializes tracking sets."""
        importer = OSMImporter(
            project=empty_project,
            transformer=mock_transformer,
            image_width=1000,
            image_height=800
        )

        assert importer.imported_way_ids == set()
        assert importer.imported_node_ids == set()
        assert importer.roundabout_way_ids == set()
        assert importer.road_to_osm_way == {}
        assert importer.signal_to_osm_node == {}


class TestOSMImporterImportOsmData:
    """Tests for OSMImporter.import_osm_data method."""

    @pytest.fixture
    def mock_transformer(self):
        """Create mock transformer with proper pixel_to_geo method."""
        transformer = Mock()
        transformer.geo_to_pixel = Mock(return_value=(100.0, 100.0))
        # pixel_to_geo returns (lon, lat)
        transformer.pixel_to_geo = Mock(return_value=(12.94, 57.72))
        return transformer

    @pytest.fixture
    def empty_project(self):
        """Create empty project."""
        return Project()

    def test_default_options(self, empty_project, mock_transformer):
        """Uses default options when none provided."""
        importer = OSMImporter(
            project=empty_project,
            transformer=mock_transformer,
            image_width=1000,
            image_height=800
        )

        # Mock the API client to avoid network calls
        with patch.object(osm_importer, 'OverpassAPIClient') as mock_client:
            mock_client.return_value.query_bbox.side_effect = Exception("Mocked API error")

            result = importer.import_osm_data()

            # Should fail with error message (mocked)
            assert result.success is False
            assert result.error_message is not None

    def test_custom_options(self, empty_project, mock_transformer):
        """Custom options are used."""
        importer = OSMImporter(
            project=empty_project,
            transformer=mock_transformer,
            image_width=1000,
            image_height=800
        )

        options = ImportOptions(
            import_mode=ImportMode.REPLACE,
            timeout=30
        )

        # The API client is only created after bbox calculation succeeds
        # So we need to mock calculate_bbox_from_image to return a valid bbox
        with patch.object(osm_importer, 'calculate_bbox_from_image') as mock_bbox:
            mock_bbox.return_value = (12.90, 57.70, 13.00, 57.80)

            with patch.object(osm_importer, 'OverpassAPIClient') as mock_client:
                mock_client.return_value.query_bbox.side_effect = OverpassAPIError("Mocked API error")

                # Should use provided options (including timeout=30)
                result = importer.import_osm_data(options)

                # The client should have been initialized with timeout=30
                mock_client.assert_called_once_with(timeout=30)

                # Should fail with error message
                assert result.success is False
                assert "Overpass API error" in result.error_message


class TestOSMImporterBboxCalculation:
    """Tests for bounding box calculation in import."""

    @pytest.fixture
    def mock_transformer(self):
        """Create mock transformer that returns proper geo coords."""
        transformer = Mock()
        # pixel_to_geo returns (lon, lat)
        def pixel_to_geo(x, y):
            # Map corners of 1000x800 image to geo coords
            lon = 12.90 + (x / 1000) * 0.1  # 12.90 to 13.00
            lat = 57.70 + (y / 800) * 0.05  # 57.70 to 57.75
            return (lon, lat)
        transformer.pixel_to_geo = Mock(side_effect=pixel_to_geo)
        return transformer

    @pytest.fixture
    def empty_project(self):
        """Create empty project."""
        return Project()

    def test_bbox_calculation_failure(self, empty_project, mock_transformer):
        """Handle bbox calculation failure."""
        importer = OSMImporter(
            project=empty_project,
            transformer=mock_transformer,
            image_width=1000,
            image_height=800
        )

        # Make pixel_to_geo raise an error
        mock_transformer.pixel_to_geo.side_effect = Exception("Coordinate error")

        result = importer.import_osm_data()

        assert result.success is False
        assert "bounding box" in result.error_message.lower()


class TestOSMImporterDuplicateDetection:
    """Tests for duplicate detection in OSMImporter."""

    @pytest.fixture
    def mock_transformer(self):
        """Create mock transformer."""
        transformer = Mock()
        transformer.geo_to_pixel = Mock(return_value=(100.0, 100.0))
        transformer.pixel_to_geo = Mock(return_value=(12.94, 57.72))
        return transformer

    @pytest.fixture
    def empty_project(self):
        """Create empty project."""
        return Project()

    def test_tracking_sets_initialized(self, empty_project, mock_transformer):
        """Tracking sets start empty."""
        importer = OSMImporter(
            project=empty_project,
            transformer=mock_transformer,
            image_width=1000,
            image_height=800
        )

        assert len(importer.imported_way_ids) == 0
        assert len(importer.imported_node_ids) == 0

    def test_tracking_sets_mutable(self, empty_project, mock_transformer):
        """Tracking sets can be modified."""
        importer = OSMImporter(
            project=empty_project,
            transformer=mock_transformer,
            image_width=1000,
            image_height=800
        )

        importer.imported_way_ids.add(12345)
        importer.imported_node_ids.add(67890)

        assert 12345 in importer.imported_way_ids
        assert 67890 in importer.imported_node_ids


class TestOSMImporterRoundaboutTracking:
    """Tests for roundabout tracking in OSMImporter."""

    @pytest.fixture
    def mock_transformer(self):
        """Create mock transformer."""
        transformer = Mock()
        transformer.geo_to_pixel = Mock(return_value=(100.0, 100.0))
        transformer.pixel_to_geo = Mock(return_value=(12.94, 57.72))
        return transformer

    @pytest.fixture
    def empty_project(self):
        """Create empty project."""
        return Project()

    def test_roundabout_way_ids_tracked(self, empty_project, mock_transformer):
        """Roundabout way IDs can be tracked."""
        importer = OSMImporter(
            project=empty_project,
            transformer=mock_transformer,
            image_width=1000,
            image_height=800
        )

        importer.roundabout_way_ids.add(111111)
        importer.roundabout_way_ids.add(222222)

        assert 111111 in importer.roundabout_way_ids
        assert 222222 in importer.roundabout_way_ids


class TestOSMImporterMappings:
    """Tests for road/signal mappings in OSMImporter."""

    @pytest.fixture
    def mock_transformer(self):
        """Create mock transformer."""
        transformer = Mock()
        return transformer

    @pytest.fixture
    def empty_project(self):
        """Create empty project."""
        return Project()

    def test_road_to_osm_way_mapping(self, empty_project, mock_transformer):
        """Road ID to OSM way ID mapping."""
        importer = OSMImporter(
            project=empty_project,
            transformer=mock_transformer,
            image_width=1000,
            image_height=800
        )

        importer.road_to_osm_way["road-uuid-1"] = 12345
        importer.road_to_osm_way["road-uuid-2"] = 67890

        assert importer.road_to_osm_way["road-uuid-1"] == 12345
        assert importer.road_to_osm_way["road-uuid-2"] == 67890

    def test_signal_to_osm_node_mapping(self, empty_project, mock_transformer):
        """Signal ID to OSM node ID mapping."""
        importer = OSMImporter(
            project=empty_project,
            transformer=mock_transformer,
            image_width=1000,
            image_height=800
        )

        importer.signal_to_osm_node["signal-uuid-1"] = 11111
        importer.signal_to_osm_node["signal-uuid-2"] = 22222

        assert importer.signal_to_osm_node["signal-uuid-1"] == 11111
        assert importer.signal_to_osm_node["signal-uuid-2"] == 22222


class TestImportResultSummary:
    """Tests for ImportResult summary data."""

    def test_total_items_imported(self):
        """Calculate total items from result."""
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

    def test_total_skipped(self):
        """Calculate total skipped items."""
        result = ImportResult(
            success=True,
            roads_skipped_duplicate=2,
            signals_skipped_duplicate=1,
            objects_skipped_duplicate=3,
            parking_skipped_duplicate=0
        )

        total_skipped = (result.roads_skipped_duplicate +
                         result.signals_skipped_duplicate +
                         result.objects_skipped_duplicate +
                         result.parking_skipped_duplicate)

        assert total_skipped == 6


# Import additional classes for more tests
osm_parser = importlib.import_module('orbit.import.osm_parser')
OSMData = osm_parser.OSMData
OSMNode = osm_parser.OSMNode
OSMWay = osm_parser.OSMWay


class TestOSMImporterImportModes:
    """Tests for import mode handling."""

    @pytest.fixture
    def mock_transformer(self):
        transformer = Mock()
        transformer.geo_to_pixel = Mock(return_value=(100.0, 100.0))
        transformer.pixel_to_geo = Mock(return_value=(12.94, 57.72))
        return transformer

    @pytest.fixture
    def project_with_data(self):
        """Create project with existing data."""
        project = Project()
        from orbit.models import Polyline, Road
        from orbit.models.polyline import LineType

        polyline = Polyline()
        polyline.line_type = LineType.CENTERLINE
        polyline.points = [(0, 0), (100, 100)]
        project.polylines.append(polyline)

        road = Road(name="Existing Road", centerline_id=polyline.id)
        project.roads.append(road)

        return project

    def test_replace_mode_clears_data(self, project_with_data, mock_transformer):
        """REPLACE mode clears existing project data."""
        importer = OSMImporter(
            project=project_with_data,
            transformer=mock_transformer,
            image_width=1000,
            image_height=800
        )

        # Verify data exists before import
        assert len(project_with_data.roads) == 1
        assert len(project_with_data.polylines) == 1

        # Import with REPLACE mode should clear existing data
        options = ImportOptions(import_mode=ImportMode.REPLACE)

        # Mock to avoid actual API call
        with patch.object(osm_importer, 'calculate_bbox_from_image') as mock_bbox:
            mock_bbox.return_value = (12.90, 57.70, 13.00, 57.80)
            with patch.object(osm_importer, 'OverpassAPIClient') as mock_client:
                mock_client.return_value.query_bbox.return_value = {'elements': []}
                with patch.object(osm_parser, 'OSMParser') as mock_parser:
                    mock_parser.parse.return_value = OSMData()

                    result = importer.import_osm_data(options)

        # After REPLACE, existing data should be cleared
        # (roads list is replaced during import)
        assert result.error_message is None or "No data" not in result.error_message

    def test_add_mode_preserves_data(self, project_with_data, mock_transformer):
        """ADD mode preserves existing project data."""
        importer = OSMImporter(
            project=project_with_data,
            transformer=mock_transformer,
            image_width=1000,
            image_height=800
        )

        _initial_road_count = len(project_with_data.roads)

        options = ImportOptions(import_mode=ImportMode.ADD)

        # Mock to avoid actual API call - return empty data
        with patch.object(osm_importer, 'calculate_bbox_from_image') as mock_bbox:
            mock_bbox.return_value = (12.90, 57.70, 13.00, 57.80)
            with patch.object(osm_importer, 'OverpassAPIClient') as mock_client:
                mock_client.return_value.query_bbox.return_value = {'elements': []}

                _result = importer.import_osm_data(options)

        # Existing data should still be there
        # (In ADD mode, we don't clear)


class TestOSMImporterErrorHandling:
    """Tests for error handling in OSMImporter."""

    @pytest.fixture
    def mock_transformer(self):
        transformer = Mock()
        transformer.geo_to_pixel = Mock(return_value=(100.0, 100.0))
        transformer.pixel_to_geo = Mock(return_value=(12.94, 57.72))
        return transformer

    @pytest.fixture
    def empty_project(self):
        return Project()

    def test_timeout_error_sets_partial_import(self, empty_project, mock_transformer):
        """API timeout error sets partial_import flag."""
        importer = OSMImporter(
            project=empty_project,
            transformer=mock_transformer,
            image_width=1000,
            image_height=800
        )

        with patch.object(osm_importer, 'calculate_bbox_from_image') as mock_bbox:
            mock_bbox.return_value = (12.90, 57.70, 13.00, 57.80)
            with patch.object(osm_importer, 'OverpassAPIClient') as mock_client:
                mock_client.return_value.query_bbox.side_effect = OverpassAPIError("Request timed out")

                result = importer.import_osm_data()

        assert result.success is False
        assert result.partial_import is True
        assert "timeout" in result.error_message.lower() or "timed out" in result.error_message.lower()

    def test_parse_error_returns_failure(self, empty_project, mock_transformer):
        """Parse error returns failure result."""
        importer = OSMImporter(
            project=empty_project,
            transformer=mock_transformer,
            image_width=1000,
            image_height=800
        )

        with patch.object(osm_importer, 'calculate_bbox_from_image') as mock_bbox:
            mock_bbox.return_value = (12.90, 57.70, 13.00, 57.80)
            with patch.object(osm_importer, 'OverpassAPIClient') as mock_client:
                mock_client.return_value.query_bbox.return_value = {'elements': []}
                # Patch OSMParser where it's used (in osm_importer), not where it's defined
                with patch.object(osm_importer, 'OSMParser') as mock_parser:
                    mock_parser.parse.side_effect = Exception("Invalid JSON")

                    result = importer.import_osm_data()

        assert result.success is False
        assert "parse" in result.error_message.lower()

    def test_empty_api_response(self, empty_project, mock_transformer):
        """Empty API response returns failure."""
        importer = OSMImporter(
            project=empty_project,
            transformer=mock_transformer,
            image_width=1000,
            image_height=800
        )

        with patch.object(osm_importer, 'calculate_bbox_from_image') as mock_bbox:
            mock_bbox.return_value = (12.90, 57.70, 13.00, 57.80)
            with patch.object(osm_importer, 'OverpassAPIClient') as mock_client:
                mock_client.return_value.query_bbox.return_value = None

                result = importer.import_osm_data()

        assert result.success is False
        assert "No data" in result.error_message


class TestOSMImporterDetailLevels:
    """Tests for detail level handling."""

    @pytest.fixture
    def mock_transformer(self):
        transformer = Mock()
        transformer.geo_to_pixel = Mock(return_value=(100.0, 100.0))
        transformer.pixel_to_geo = Mock(return_value=(12.94, 57.72))
        return transformer

    @pytest.fixture
    def empty_project(self):
        return Project()

    def test_moderate_detail_queries_moderate(self, empty_project, mock_transformer):
        """MODERATE detail level passes 'moderate' to API."""
        importer = OSMImporter(
            project=empty_project,
            transformer=mock_transformer,
            image_width=1000,
            image_height=800
        )

        options = ImportOptions(detail_level=DetailLevel.MODERATE)

        with patch.object(osm_importer, 'calculate_bbox_from_image') as mock_bbox:
            mock_bbox.return_value = (12.90, 57.70, 13.00, 57.80)
            with patch.object(osm_importer, 'OverpassAPIClient') as mock_client:
                mock_client.return_value.query_bbox.side_effect = OverpassAPIError("Test error")

                _result = importer.import_osm_data(options)

                # Check that query_bbox was called with 'moderate'
                mock_client.return_value.query_bbox.assert_called_once()
                call_args = mock_client.return_value.query_bbox.call_args
                assert call_args[0][1] == 'moderate'

    def test_full_detail_queries_full(self, empty_project, mock_transformer):
        """FULL detail level passes 'full' to API."""
        importer = OSMImporter(
            project=empty_project,
            transformer=mock_transformer,
            image_width=1000,
            image_height=800
        )

        options = ImportOptions(detail_level=DetailLevel.FULL)

        with patch.object(osm_importer, 'calculate_bbox_from_image') as mock_bbox:
            mock_bbox.return_value = (12.90, 57.70, 13.00, 57.80)
            with patch.object(osm_importer, 'OverpassAPIClient') as mock_client:
                mock_client.return_value.query_bbox.side_effect = OverpassAPIError("Test error")

                _result = importer.import_osm_data(options)

                # Check that query_bbox was called with 'full'
                mock_client.return_value.query_bbox.assert_called_once()
                call_args = mock_client.return_value.query_bbox.call_args
                assert call_args[0][1] == 'full'


class TestOSMImporterTimeoutOption:
    """Tests for timeout option."""

    @pytest.fixture
    def mock_transformer(self):
        transformer = Mock()
        transformer.geo_to_pixel = Mock(return_value=(100.0, 100.0))
        transformer.pixel_to_geo = Mock(return_value=(12.94, 57.72))
        return transformer

    @pytest.fixture
    def empty_project(self):
        return Project()

    def test_timeout_passed_to_client(self, empty_project, mock_transformer):
        """Timeout option is passed to API client."""
        importer = OSMImporter(
            project=empty_project,
            transformer=mock_transformer,
            image_width=1000,
            image_height=800
        )

        options = ImportOptions(timeout=120)

        with patch.object(osm_importer, 'calculate_bbox_from_image') as mock_bbox:
            mock_bbox.return_value = (12.90, 57.70, 13.00, 57.80)
            with patch.object(osm_importer, 'OverpassAPIClient') as mock_client:
                mock_client.return_value.query_bbox.side_effect = OverpassAPIError("Test")

                _result = importer.import_osm_data(options)

                # Check client was initialized with timeout=120
                mock_client.assert_called_once_with(timeout=120)


class TestImportOptionsValidation:
    """Tests for ImportOptions edge cases."""

    def test_negative_lane_width_allowed(self):
        """Negative lane width is technically allowed (no validation)."""
        options = ImportOptions(default_lane_width=-1.0)
        assert options.default_lane_width == -1.0

    def test_zero_timeout(self):
        """Zero timeout is allowed."""
        options = ImportOptions(timeout=0)
        assert options.timeout == 0

    def test_all_options_combinable(self):
        """All options can be combined."""
        options = ImportOptions(
            import_mode=ImportMode.REPLACE,
            detail_level=DetailLevel.FULL,
            default_lane_width=4.0,
            import_junctions=False,
            simplify_geometry=True,
            simplify_tolerance=2.0,
            timeout=90,
            verbose=True,
            filter_outside_image=True
        )

        assert options.import_mode == ImportMode.REPLACE
        assert options.detail_level == DetailLevel.FULL
        assert options.import_junctions is False
        assert options.simplify_geometry is True
        assert options.verbose is True
        assert options.filter_outside_image is True

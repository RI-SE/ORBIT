"""Tests for orbit.export.georef_export module."""

import json
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest

from orbit.export.georef_export import (
    GEOREF_FORMAT_VERSION,
    _matrix_to_list,
    build_georef_data,
    export_georeferencing,
)
from orbit.utils.coordinate_transform import AffineTransformer, HomographyTransformer

# ==== Test Fixtures ====

@pytest.fixture
def mock_control_point():
    """Create a mock control point."""
    def _create(pixel_x, pixel_y, latitude, longitude, name=None, is_validation=False):
        cp = Mock()
        cp.pixel_x = pixel_x
        cp.pixel_y = pixel_y
        cp.latitude = latitude
        cp.longitude = longitude
        cp.name = name
        cp.is_validation = is_validation
        return cp
    return _create


@pytest.fixture
def mock_project(mock_control_point):
    """Create a mock project."""
    def _create(control_points=None, image_path=None):
        project = Mock()

        if control_points is None:
            control_points = [
                mock_control_point(100, 100, 57.7, 12.0, "GCP1"),
                mock_control_point(200, 100, 57.7, 12.001, "GCP2"),
                mock_control_point(100, 200, 57.701, 12.0, "GCP3"),
                mock_control_point(200, 200, 57.701, 12.001, "GCP4"),
            ]

        project.control_points = control_points
        project.image_path = image_path

        return project

    return _create


@pytest.fixture
def mock_affine_transformer():
    """Create a mock affine transformer."""
    transformer = Mock(spec=AffineTransformer)
    transformer.get_scale_factor.return_value = (0.1, 0.1)
    transformer.reference_lon = 12.0005
    transformer.reference_lat = 57.7005
    transformer.transform_matrix = np.array([
        [0.1, 0.0, 0.0],
        [0.0, 0.1, 0.0],
        [0.0, 0.0, 1.0]
    ])
    transformer.inverse_matrix = np.array([
        [10.0, 0.0, 0.0],
        [0.0, 10.0, 0.0],
        [0.0, 0.0, 1.0]
    ])
    transformer.reprojection_error = {
        'rmse_pixels': 1.5,
        'rmse_meters': 0.15
    }
    transformer.validation_error = None
    transformer.has_adjustment.return_value = False
    transformer.adjustment = None
    return transformer


@pytest.fixture
def mock_homography_transformer():
    """Create a mock homography transformer."""
    transformer = Mock(spec=HomographyTransformer)
    transformer.get_scale_factor.return_value = (0.1, 0.1)
    transformer.reference_lon = 12.0005
    transformer.reference_lat = 57.7005
    transformer.transform_matrix = np.eye(3)
    transformer.inverse_matrix = np.eye(3)
    transformer.reprojection_error = {
        'rmse_pixels': 1.0,
        'rmse_meters': 0.1
    }
    transformer.validation_error = {
        'rmse_pixels': 2.0,
        'rmse_meters': 0.2
    }
    transformer.H = np.eye(3)  # Indicates homography
    transformer.has_adjustment.return_value = False
    transformer.adjustment = None
    return transformer


# ==== Tests for _matrix_to_list ====

class TestMatrixToList:
    """Tests for _matrix_to_list function."""

    def test_converts_numpy_matrix(self):
        """Converts numpy matrix to nested list."""
        matrix = np.array([
            [1.0, 2.0],
            [3.0, 4.0]
        ])

        result = _matrix_to_list(matrix)

        assert result == [[1.0, 2.0], [3.0, 4.0]]

    def test_returns_none_for_none(self):
        """Returns None for None input."""
        result = _matrix_to_list(None)

        assert result is None

    def test_converts_3x3_matrix(self):
        """Converts 3x3 transformation matrix."""
        matrix = np.array([
            [0.1, 0.01, 100.0],
            [-0.01, 0.1, 200.0],
            [0.0, 0.0, 1.0]
        ])

        result = _matrix_to_list(matrix)

        assert len(result) == 3
        assert len(result[0]) == 3
        assert result[0][0] == pytest.approx(0.1)

    def test_result_is_json_serializable(self):
        """Result can be serialized to JSON."""
        matrix = np.array([[1.5, 2.5], [3.5, 4.5]])

        result = _matrix_to_list(matrix)

        # Should not raise
        json_str = json.dumps(result)
        assert '1.5' in json_str


# ==== Tests for build_georef_data ====

class TestBuildGeorefData:
    """Tests for build_georef_data function."""

    def test_basic_structure(self, mock_project, mock_affine_transformer):
        """Returns dict with expected structure."""
        project = mock_project()

        data = build_georef_data(
            project,
            mock_affine_transformer,
            (1000, 1000)
        )

        assert data['format'] == 'ORBIT Georeferencing Data'
        assert 'version' in data
        assert 'creator' in data
        assert 'source' in data
        assert 'image_size' in data
        assert 'transform_method' in data
        assert 'control_points' in data
        assert 'reference_point' in data
        assert 'transformation_matrix' in data
        assert 'inverse_matrix' in data
        assert 'scale_factors' in data
        assert 'reprojection_error' in data

    def test_creator_info(self, mock_project, mock_affine_transformer):
        """Creator info includes ORBIT application and version."""
        project = mock_project()

        data = build_georef_data(project, mock_affine_transformer, (1000, 1000))

        assert data['creator']['application'] == 'ORBIT'
        # Version should be a non-empty string (either version number or "unknown")
        assert isinstance(data['creator']['application_version'], str)
        assert len(data['creator']['application_version']) > 0

    def test_version_is_current(self, mock_project, mock_affine_transformer):
        """Version matches current format version."""
        project = mock_project()

        data = build_georef_data(project, mock_affine_transformer, (1000, 1000))

        assert data['version'] == GEOREF_FORMAT_VERSION

    def test_affine_method_detected(self, mock_project, mock_affine_transformer):
        """Affine transformer is detected."""
        project = mock_project()

        data = build_georef_data(project, mock_affine_transformer, (1000, 1000))

        assert data['transform_method'] == 'affine'

    def test_homography_method_detected(self, mock_project, mock_homography_transformer):
        """Homography transformer is detected."""
        project = mock_project()

        data = build_georef_data(project, mock_homography_transformer, (1000, 1000))

        assert data['transform_method'] == 'homography'

    def test_unknown_transformer_method(self, mock_project):
        """Unknown transformer type returns 'unknown'."""
        project = mock_project()
        transformer = Mock()  # Not AffineTransformer or HomographyTransformer
        transformer.get_scale_factor.return_value = (0.1, 0.1)
        transformer.reference_lon = 12.0
        transformer.reference_lat = 57.7
        transformer.transform_matrix = np.eye(3)
        transformer.inverse_matrix = np.eye(3)
        transformer.reprojection_error = {}
        transformer.validation_error = None
        transformer.has_adjustment.return_value = False
        transformer.adjustment = None

        data = build_georef_data(project, transformer, (1000, 1000))

        assert data['transform_method'] == 'unknown'

    def test_control_points_exported(self, mock_project, mock_affine_transformer, mock_control_point):
        """Control points are exported correctly."""
        cp = mock_control_point(150, 250, 57.705, 12.005, "TestPoint", is_validation=True)
        project = mock_project(control_points=[cp])

        data = build_georef_data(project, mock_affine_transformer, (1000, 1000))

        assert len(data['control_points']) == 1
        exported_cp = data['control_points'][0]
        assert exported_cp['pixel_x'] == 150
        assert exported_cp['pixel_y'] == 250
        assert exported_cp['latitude'] == 57.705
        assert exported_cp['longitude'] == 12.005
        assert exported_cp['name'] == "TestPoint"
        assert exported_cp['is_validation'] is True

    def test_control_point_without_name(self, mock_project, mock_affine_transformer, mock_control_point):
        """Control point without name exports empty string."""
        cp = mock_control_point(100, 100, 57.7, 12.0, name=None)
        project = mock_project(control_points=[cp])

        data = build_georef_data(project, mock_affine_transformer, (1000, 1000))

        assert data['control_points'][0]['name'] == ""

    def test_image_size_exported(self, mock_project, mock_affine_transformer):
        """Image size is exported as list."""
        project = mock_project()

        data = build_georef_data(project, mock_affine_transformer, (800, 600))

        assert data['image_size'] == [800, 600]

    def test_scale_factors_exported(self, mock_project, mock_affine_transformer):
        """Scale factors are exported."""
        project = mock_project()

        data = build_georef_data(project, mock_affine_transformer, (1000, 1000))

        assert 'x_meters_per_pixel' in data['scale_factors']
        assert 'y_meters_per_pixel' in data['scale_factors']
        assert data['scale_factors']['x_meters_per_pixel'] == 0.1

    def test_reference_point_exported(self, mock_project, mock_affine_transformer):
        """Reference point is exported."""
        project = mock_project()

        data = build_georef_data(project, mock_affine_transformer, (1000, 1000))

        assert data['reference_point']['longitude'] == 12.0005
        assert data['reference_point']['latitude'] == 57.7005

    def test_reprojection_error_exported(self, mock_project, mock_affine_transformer):
        """Reprojection error is exported."""
        project = mock_project()

        data = build_georef_data(project, mock_affine_transformer, (1000, 1000))

        assert data['reprojection_error']['rmse_pixels'] == 1.5
        assert data['reprojection_error']['rmse_meters'] == 0.15

    def test_validation_error_exported(self, mock_project, mock_homography_transformer):
        """Validation error is exported when available."""
        project = mock_project()

        data = build_georef_data(project, mock_homography_transformer, (1000, 1000))

        assert 'validation_error' in data
        assert data['validation_error']['rmse_pixels'] == 2.0
        assert data['validation_error']['rmse_meters'] == 0.2

    def test_no_validation_error(self, mock_project, mock_affine_transformer):
        """No validation error when not available."""
        project = mock_project()

        data = build_georef_data(project, mock_affine_transformer, (1000, 1000))

        assert 'validation_error' not in data

    def test_project_file_included(self, mock_project, mock_affine_transformer):
        """Project file path is included when provided."""
        project = mock_project()

        data = build_georef_data(
            project,
            mock_affine_transformer,
            (1000, 1000),
            project_file=Path("/path/to/project.orbit")
        )

        assert data['source']['project_file'] == "/path/to/project.orbit"

    def test_project_file_none(self, mock_project, mock_affine_transformer):
        """Project file is None when not provided."""
        project = mock_project()

        data = build_georef_data(project, mock_affine_transformer, (1000, 1000))

        assert data['source']['project_file'] is None

    def test_image_path_included(self, mock_project, mock_affine_transformer):
        """Image path is included."""
        project = mock_project(image_path=Path("/path/to/image.jpg"))

        data = build_georef_data(project, mock_affine_transformer, (1000, 1000))

        assert data['source']['image_path'] == "/path/to/image.jpg"

    def test_matrices_exported(self, mock_project, mock_affine_transformer):
        """Transformation matrices are exported."""
        project = mock_project()

        data = build_georef_data(project, mock_affine_transformer, (1000, 1000))

        assert data['transformation_matrix'] is not None
        assert data['inverse_matrix'] is not None
        assert len(data['transformation_matrix']) == 3  # 3x3 matrix


# ==== Tests for export_georeferencing ====

class TestExportGeoreferencing:
    """Tests for export_georeferencing function."""

    def test_successful_export(self, mock_project, mock_affine_transformer, tmp_path):
        """Successful export returns True."""
        project = mock_project()
        output_path = tmp_path / "georef.json"

        result = export_georeferencing(
            project,
            output_path,
            mock_affine_transformer,
            (1000, 1000)
        )

        assert result is True
        assert output_path.exists()

    def test_creates_valid_json(self, mock_project, mock_affine_transformer, tmp_path):
        """Creates valid JSON file."""
        project = mock_project()
        output_path = tmp_path / "georef.json"

        export_georeferencing(
            project,
            output_path,
            mock_affine_transformer,
            (1000, 1000)
        )

        # Should be valid JSON
        with open(output_path) as f:
            data = json.load(f)

        assert data['version'] == GEOREF_FORMAT_VERSION

    def test_export_failure_returns_false(self, mock_project, mock_affine_transformer, tmp_path):
        """Export failure returns False."""
        project = mock_project()
        # Invalid path (directory doesn't exist)
        output_path = tmp_path / "nonexistent" / "subdir" / "georef.json"

        result = export_georeferencing(
            project,
            output_path,
            mock_affine_transformer,
            (1000, 1000)
        )

        assert result is False

    def test_includes_project_file_path(self, mock_project, mock_affine_transformer, tmp_path):
        """Includes project file path when provided."""
        project = mock_project()
        output_path = tmp_path / "georef.json"
        project_file = Path("/path/to/my_project.orbit")

        export_georeferencing(
            project,
            output_path,
            mock_affine_transformer,
            (1000, 1000),
            project_file=project_file
        )

        with open(output_path) as f:
            data = json.load(f)

        assert data['source']['project_file'] == str(project_file)

    def test_json_is_formatted(self, mock_project, mock_affine_transformer, tmp_path):
        """JSON output is formatted (indented)."""
        project = mock_project()
        output_path = tmp_path / "georef.json"

        export_georeferencing(
            project,
            output_path,
            mock_affine_transformer,
            (1000, 1000)
        )

        content = output_path.read_text()

        # Indented JSON has newlines and spaces
        assert '\n' in content
        assert '  ' in content  # 2-space indent

    def test_handles_empty_reprojection_error(self, mock_project, tmp_path):
        """Handles transformer with empty reprojection error."""
        project = mock_project()
        output_path = tmp_path / "georef.json"

        transformer = Mock(spec=AffineTransformer)
        transformer.get_scale_factor.return_value = (0.1, 0.1)
        transformer.reference_lon = 12.0
        transformer.reference_lat = 57.7
        transformer.transform_matrix = np.eye(3)
        transformer.inverse_matrix = np.eye(3)
        transformer.reprojection_error = {}  # Empty
        transformer.validation_error = None
        transformer.has_adjustment.return_value = False
        transformer.adjustment = None

        result = export_georeferencing(
            project,
            output_path,
            transformer,
            (1000, 1000)
        )

        assert result is True

        with open(output_path) as f:
            data = json.load(f)

        assert data['reprojection_error']['rmse_pixels'] == 0.0
        assert data['reprojection_error']['rmse_meters'] == 0.0


# ==== Tests for adjustment data in georef export ====

class TestGeorefExportAdjustment:
    """Tests that adjustment data is included in georef export when active."""

    def test_adjustment_included_when_active(self, mock_project, mock_affine_transformer):
        """Adjustment section is exported when transformer has an adjustment."""
        from orbit.utils.coordinate_transform import TransformAdjustment

        project = mock_project()
        adj = TransformAdjustment(translation_x=10.0, translation_y=5.0, rotation=1.5)

        mock_affine_transformer.has_adjustment = Mock(return_value=True)
        mock_affine_transformer.adjustment = adj

        data = build_georef_data(project, mock_affine_transformer, (1000, 1000))

        assert "adjustment" in data
        assert data["adjustment"]["translation_x"] == 10.0
        assert data["adjustment"]["translation_y"] == 5.0
        assert data["adjustment"]["rotation"] == 1.5
        assert "adjustment_matrix" in data
        assert len(data["adjustment_matrix"]) == 3  # 3x3 matrix

    def test_no_adjustment_when_inactive(self, mock_project, mock_affine_transformer):
        """No adjustment section when transformer has no adjustment."""
        project = mock_project()

        mock_affine_transformer.has_adjustment = Mock(return_value=False)
        mock_affine_transformer.adjustment = None

        data = build_georef_data(project, mock_affine_transformer, (1000, 1000))

        assert "adjustment" not in data
        assert "adjustment_matrix" not in data

    def test_adjustment_exported_to_json(self, mock_project, mock_affine_transformer, tmp_path):
        """Adjustment data is written to JSON file."""
        from orbit.utils.coordinate_transform import TransformAdjustment

        project = mock_project()
        adj = TransformAdjustment(translation_x=3.0, translation_y=-2.0)

        mock_affine_transformer.has_adjustment = Mock(return_value=True)
        mock_affine_transformer.adjustment = adj

        output_path = tmp_path / "georef.json"
        result = export_georeferencing(project, output_path, mock_affine_transformer, (1000, 1000))

        assert result is True

        with open(output_path) as f:
            data = json.load(f)

        assert "adjustment" in data
        assert data["adjustment"]["translation_x"] == 3.0


# ==== Tests for HybridTransformer detection ====

class TestHybridTransformerDetection:
    """Tests that HybridTransformer is correctly detected in georef export."""

    def test_hybrid_transformer_detected_as_homography(self, mock_project):
        """HybridTransformer should be detected as homography method."""
        from orbit.utils.coordinate_transform import HybridTransformer

        project = mock_project()
        transformer = Mock(spec=HybridTransformer)
        transformer.get_scale_factor.return_value = (0.1, 0.1)
        transformer.reference_lon = 12.0
        transformer.reference_lat = 57.7
        transformer.transform_matrix = np.eye(3)
        transformer.inverse_matrix = np.eye(3)
        transformer.reprojection_error = {}
        transformer.validation_error = None
        transformer.has_adjustment = Mock(return_value=False)
        transformer.adjustment = None

        data = build_georef_data(project, transformer, (1000, 1000))

        assert data["transform_method"] == "homography"

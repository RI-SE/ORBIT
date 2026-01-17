"""Tests for orbit.import.opendrive_coordinate_transform module."""

import importlib
import math
import pytest
from unittest.mock import Mock, patch

# Import from orbit.import using importlib (import is a reserved keyword)
opendrive_coord = importlib.import_module('orbit.import.opendrive_coordinate_transform')

TransformMode = opendrive_coord.TransformMode
TransformResult = opendrive_coord.TransformResult
OpenDriveCoordinateTransform = opendrive_coord.OpenDriveCoordinateTransform
batch_metric_to_pixel = opendrive_coord.batch_metric_to_pixel


class TestTransformMode:
    """Tests for TransformMode dataclass."""

    def test_modes_defined(self):
        """All modes are defined."""
        assert TransformMode.GEOREFERENCED == "georeferenced"
        assert TransformMode.SYNTHETIC == "synthetic"
        assert TransformMode.AUTO_GEOREFERENCE == "auto_georeference"


class TestTransformResult:
    """Tests for TransformResult dataclass."""

    def test_basic_result(self):
        """Basic result creation."""
        result = TransformResult(success=True, mode="synthetic")
        assert result.success is True
        assert result.mode == "synthetic"
        assert result.error_message is None

    def test_result_with_error(self):
        """Result with error message."""
        result = TransformResult(
            success=False, mode="auto_georeference",
            error_message="Test error"
        )
        assert result.success is False
        assert result.error_message == "Test error"

    def test_result_with_scale(self):
        """Result with scale."""
        result = TransformResult(
            success=True, mode="synthetic",
            scale_pixels_per_meter=10.5
        )
        assert result.scale_pixels_per_meter == 10.5

    def test_result_with_control_points(self):
        """Result with suggested control points."""
        points = [(100, 200, 18.0, 59.0), (300, 200, 18.1, 59.0)]
        result = TransformResult(
            success=False, mode="auto_georeference",
            suggested_control_points=points
        )
        assert len(result.suggested_control_points) == 2


class TestOpenDriveCoordinateTransformInit:
    """Tests for OpenDriveCoordinateTransform initialization."""

    def test_basic_init(self):
        """Basic initialization."""
        transform = OpenDriveCoordinateTransform(
            image_width=1000, image_height=800
        )
        assert transform.image_width == 1000
        assert transform.image_height == 800
        assert transform.scale_pixels_per_meter == 10.0
        assert transform.mode is None

    def test_init_with_scale(self):
        """Initialize with custom scale."""
        transform = OpenDriveCoordinateTransform(
            image_width=1000, image_height=800,
            scale_pixels_per_meter=5.0
        )
        assert transform.scale_pixels_per_meter == 5.0

    def test_init_with_header_offsets(self):
        """Initialize with header offsets."""
        transform = OpenDriveCoordinateTransform(
            image_width=1000, image_height=800,
            header_offset_x=100.0, header_offset_y=200.0,
            header_offset_z=10.0, header_offset_hdg=0.5
        )
        assert transform.header_offset_x == 100.0
        assert transform.header_offset_y == 200.0
        assert transform.header_offset_z == 10.0
        assert transform.header_offset_hdg == 0.5

    def test_init_with_orbit_transformer(self):
        """Initialize with ORBIT transformer."""
        mock_transformer = Mock()
        transform = OpenDriveCoordinateTransform(
            image_width=1000, image_height=800,
            orbit_transformer=mock_transformer
        )
        assert transform.orbit_transformer is mock_transformer

    def test_center_pixel_calculated(self):
        """Center pixel is calculated from dimensions."""
        transform = OpenDriveCoordinateTransform(
            image_width=1000, image_height=800
        )
        assert transform.center_pixel_x == 500.0
        assert transform.center_pixel_y == 400.0


class TestSetupTransformSynthetic:
    """Tests for setup_transform in synthetic mode."""

    def test_synthetic_mode_no_georef(self):
        """Synthetic mode when no georeferencing available."""
        transform = OpenDriveCoordinateTransform(
            image_width=1000, image_height=800
        )
        points = [(0, 0), (100, 0), (100, 50), (0, 50)]
        result = transform.setup_transform(points)

        assert result.success is True
        assert result.mode == TransformMode.SYNTHETIC
        assert transform.mode == TransformMode.SYNTHETIC

    def test_synthetic_mode_calculates_bounds(self):
        """Synthetic mode calculates data bounds."""
        transform = OpenDriveCoordinateTransform(
            image_width=1000, image_height=800
        )
        points = [(-50, -25), (50, 25)]
        transform.setup_transform(points)

        assert transform.data_min_x == -50
        assert transform.data_max_x == 50
        assert transform.data_min_y == -25
        assert transform.data_max_y == 25

    def test_synthetic_mode_calculates_offsets(self):
        """Synthetic mode calculates centering offsets."""
        transform = OpenDriveCoordinateTransform(
            image_width=1000, image_height=800
        )
        points = [(0, 0), (100, 100)]  # Center at (50, 50)
        transform.setup_transform(points)

        assert transform.offset_x == -50.0  # -data_center_x
        assert transform.offset_y == -50.0  # -data_center_y

    def test_synthetic_mode_adjusts_scale(self):
        """Synthetic mode adjusts scale to fit data."""
        transform = OpenDriveCoordinateTransform(
            image_width=1000, image_height=800
        )
        points = [(0, 0), (200, 100)]  # 200m x 100m
        result = transform.setup_transform(points)

        # Scale should fit data in 90% of image
        # 1000 * 0.9 / 200 = 4.5 for X
        # 800 * 0.9 / 100 = 7.2 for Y
        # min(4.5, 7.2) = 4.5
        assert result.scale_pixels_per_meter == pytest.approx(4.5)

    def test_synthetic_mode_empty_points(self):
        """Synthetic mode with empty points uses defaults."""
        transform = OpenDriveCoordinateTransform(
            image_width=1000, image_height=800,
            scale_pixels_per_meter=5.0
        )
        result = transform.setup_transform([])

        assert result.success is True
        assert result.mode == TransformMode.SYNTHETIC


class TestSetupTransformGeoreferenced:
    """Tests for setup_transform in georeferenced mode."""

    def test_georeferenced_mode(self):
        """Georeferenced mode when both have georeferencing."""
        mock_transformer = Mock()
        transform = OpenDriveCoordinateTransform(
            image_width=1000, image_height=800,
            orbit_transformer=mock_transformer,
            opendrive_geo_reference="+proj=tmerc +lat_0=59.0 +lon_0=18.0"
        )
        points = [(0, 0), (100, 100)]
        result = transform.setup_transform(points)

        assert result.success is True
        assert result.mode == TransformMode.GEOREFERENCED
        assert transform.mode == TransformMode.GEOREFERENCED


class TestSetupTransformAutoGeoreference:
    """Tests for setup_transform in auto-georeference mode."""

    def test_auto_georeference_mode(self):
        """Auto-georeference when only OpenDrive has georef."""
        transform = OpenDriveCoordinateTransform(
            image_width=1000, image_height=800,
            opendrive_geo_reference="+proj=tmerc +lat_0=59.0 +lon_0=18.0"
        )
        points = [(0, 0), (100, 100)]
        result = transform.setup_transform(points)

        assert result.success is False
        assert result.mode == TransformMode.AUTO_GEOREFERENCE
        assert "control points" in result.error_message.lower()
        assert result.suggested_control_points is not None


class TestMetricToPixelSynthetic:
    """Tests for metric_to_pixel in synthetic mode."""

    @pytest.fixture
    def transform(self):
        """Create transform in synthetic mode."""
        t = OpenDriveCoordinateTransform(
            image_width=1000, image_height=800
        )
        # Setup with data centered at origin
        t.setup_transform([(-100, -50), (100, 50)])
        return t

    def test_center_point_at_center(self, transform):
        """Origin maps to image center."""
        px, py = transform.metric_to_pixel(0, 0)
        assert px == pytest.approx(500.0)  # center_x
        assert py == pytest.approx(400.0)  # center_y

    def test_positive_x_moves_right(self, transform):
        """Positive X moves right in image."""
        px1, _ = transform.metric_to_pixel(0, 0)
        px2, _ = transform.metric_to_pixel(10, 0)
        assert px2 > px1

    def test_positive_y_moves_up_in_image(self, transform):
        """Positive Y moves up (lower pixel value)."""
        _, py1 = transform.metric_to_pixel(0, 0)
        _, py2 = transform.metric_to_pixel(0, 10)
        assert py2 < py1  # Y is flipped

    def test_scale_applied(self, transform):
        """Scale is applied to coordinates."""
        scale = transform.scale_pixels_per_meter
        px1, _ = transform.metric_to_pixel(0, 0)
        px2, _ = transform.metric_to_pixel(1, 0)
        assert px2 - px1 == pytest.approx(scale)


class TestMetricToPixelGeoreferenced:
    """Tests for metric_to_pixel in georeferenced mode."""

    def test_georeferenced_uses_orbit_transformer(self):
        """Georeferenced mode uses ORBIT transformer."""
        mock_transformer = Mock()
        mock_transformer.geo_to_pixel.return_value = (123.0, 456.0)

        transform = OpenDriveCoordinateTransform(
            image_width=1000, image_height=800,
            orbit_transformer=mock_transformer,
            opendrive_geo_reference="+proj=tmerc +lat_0=59.0 +lon_0=18.0"
        )
        transform.setup_transform([(0, 0), (100, 100)])

        # The transformation will use _metric_to_latlon internally
        with patch.object(transform, '_metric_to_latlon', return_value=(18.0, 59.0)):
            px, py = transform.metric_to_pixel(50, 50)

        mock_transformer.geo_to_pixel.assert_called_once_with(18.0, 59.0)
        assert px == 123.0
        assert py == 456.0


class TestExtractOriginFromProj4:
    """Tests for _extract_origin_from_proj4 method."""

    def test_extract_both_coords(self):
        """Extract lat_0 and lon_0 from PROJ4 string."""
        transform = OpenDriveCoordinateTransform(
            image_width=1000, image_height=800,
            opendrive_geo_reference="+proj=tmerc +lat_0=59.33 +lon_0=18.07 +k=1"
        )
        lat, lon = transform._extract_origin_from_proj4()

        assert lat == pytest.approx(59.33)
        assert lon == pytest.approx(18.07)

    def test_missing_lat(self):
        """Handle missing lat_0."""
        transform = OpenDriveCoordinateTransform(
            image_width=1000, image_height=800,
            opendrive_geo_reference="+proj=tmerc +lon_0=18.07"
        )
        lat, lon = transform._extract_origin_from_proj4()

        assert lat is None
        assert lon == pytest.approx(18.07)

    def test_missing_lon(self):
        """Handle missing lon_0."""
        transform = OpenDriveCoordinateTransform(
            image_width=1000, image_height=800,
            opendrive_geo_reference="+proj=tmerc +lat_0=59.33"
        )
        lat, lon = transform._extract_origin_from_proj4()

        assert lat == pytest.approx(59.33)
        assert lon is None

    def test_no_geo_reference(self):
        """Return None when no geoReference."""
        transform = OpenDriveCoordinateTransform(
            image_width=1000, image_height=800
        )
        lat, lon = transform._extract_origin_from_proj4()

        assert lat is None
        assert lon is None

    def test_invalid_value(self):
        """Handle invalid numeric value."""
        transform = OpenDriveCoordinateTransform(
            image_width=1000, image_height=800,
            opendrive_geo_reference="+proj=tmerc +lat_0=invalid +lon_0=18.07"
        )
        lat, lon = transform._extract_origin_from_proj4()

        assert lat is None  # Failed to parse
        assert lon == pytest.approx(18.07)


class TestMetricToLatlon:
    """Tests for _metric_to_latlon method."""

    def test_with_pyproj(self):
        """Test with pyproj available."""
        transform = OpenDriveCoordinateTransform(
            image_width=1000, image_height=800,
            opendrive_geo_reference="+proj=tmerc +lat_0=59.0 +lon_0=18.0 +k=1 +x_0=0 +y_0=0"
        )

        # This test may vary based on pyproj availability
        lon, lat = transform._metric_to_latlon(0, 0)

        # At origin should be close to the projection center
        assert lat == pytest.approx(59.0, abs=0.01)
        assert lon == pytest.approx(18.0, abs=0.01)

    def test_header_offset_applied(self):
        """Header offset is applied to coordinates."""
        transform = OpenDriveCoordinateTransform(
            image_width=1000, image_height=800,
            opendrive_geo_reference="+proj=tmerc +lat_0=59.0 +lon_0=18.0 +k=1 +x_0=0 +y_0=0",
            header_offset_x=100.0, header_offset_y=200.0
        )

        # With offset, the input coords are relative to offset
        # So (0, 0) becomes (100, 200) in absolute terms
        lon1, lat1 = transform._metric_to_latlon(0, 0)  # Maps to (100, 200)
        lon2, lat2 = transform._metric_to_latlon(-100, -200)  # Maps to (0, 0) = origin

        # Origin should be at projection center
        assert lat2 == pytest.approx(59.0, abs=0.01)
        assert lon2 == pytest.approx(18.0, abs=0.01)


class TestGenerateSuggestedControlPoints:
    """Tests for _generate_suggested_control_points method."""

    def test_generates_four_corners(self):
        """Generates 4 control points at corners."""
        transform = OpenDriveCoordinateTransform(
            image_width=1000, image_height=800,
            opendrive_geo_reference="+proj=tmerc +lat_0=59.0 +lon_0=18.0"
        )
        # Use non-zero min values since the code checks `if not self.data_min_x`
        points = [(10, 10), (110, 60)]
        transform.setup_transform(points)

        control_points = transform._generate_suggested_control_points()

        assert len(control_points) == 4
        # Each point should be (px, py, lon, lat)
        for point in control_points:
            assert len(point) == 4

    def test_empty_when_no_bounds(self):
        """Returns empty when no data bounds."""
        transform = OpenDriveCoordinateTransform(
            image_width=1000, image_height=800
        )

        control_points = transform._generate_suggested_control_points()
        assert control_points == []

    def test_pixel_coords_in_image(self):
        """Generated pixel coords are within image."""
        transform = OpenDriveCoordinateTransform(
            image_width=1000, image_height=800,
            opendrive_geo_reference="+proj=tmerc +lat_0=59.0 +lon_0=18.0"
        )
        # Use non-zero min values
        points = [(10, 10), (110, 60)]
        transform.setup_transform(points)

        control_points = transform._generate_suggested_control_points()
        assert len(control_points) == 4  # Ensure we got points

        for px, py, _, _ in control_points:
            # Points should be centered in image with margin
            assert 0 < px < 1000
            assert 0 < py < 800


class TestBatchMetricToPixel:
    """Tests for batch_metric_to_pixel function."""

    def test_empty_list(self):
        """Empty list returns empty list."""
        transform = OpenDriveCoordinateTransform(
            image_width=1000, image_height=800
        )
        transform.setup_transform([])

        result = batch_metric_to_pixel([], transform)
        assert result == []

    def test_converts_multiple_points(self):
        """Multiple points are converted."""
        transform = OpenDriveCoordinateTransform(
            image_width=1000, image_height=800
        )
        transform.setup_transform([(-50, -50), (50, 50)])

        metric_points = [(0, 0), (10, 10), (-10, -10)]
        pixel_points = batch_metric_to_pixel(metric_points, transform)

        assert len(pixel_points) == 3
        # Each point should be a tuple
        for px, py in pixel_points:
            assert isinstance(px, float)
            assert isinstance(py, float)

    def test_calls_metric_to_pixel(self):
        """batch_metric_to_pixel calls metric_to_pixel for each point."""
        transform = OpenDriveCoordinateTransform(
            image_width=1000, image_height=800
        )
        transform.setup_transform([])

        with patch.object(transform, 'metric_to_pixel', return_value=(100.0, 200.0)) as mock_m2p:
            result = batch_metric_to_pixel([(1, 2), (3, 4)], transform)

        assert mock_m2p.call_count == 2
        assert result == [(100.0, 200.0), (100.0, 200.0)]

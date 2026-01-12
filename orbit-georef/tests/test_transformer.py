"""Tests for orbit-georef transformer."""

import json
import math
import tempfile
from pathlib import Path

import numpy as np
import pytest

from orbit_georef import GeoTransformer, ControlPoint, load_georef, save_georef


# Sample control points (roughly Gothenburg, Sweden area)
SAMPLE_CONTROL_POINTS = [
    ControlPoint(pixel_x=100, pixel_y=100, longitude=11.97, latitude=57.71),
    ControlPoint(pixel_x=900, pixel_y=100, longitude=11.98, latitude=57.71),
    ControlPoint(pixel_x=100, pixel_y=700, longitude=11.97, latitude=57.70),
    ControlPoint(pixel_x=900, pixel_y=700, longitude=11.98, latitude=57.70),
]


class TestGeoTransformer:
    """Tests for GeoTransformer class."""

    def test_from_control_points_homography(self):
        """Test creating transformer from control points with homography."""
        transformer = GeoTransformer.from_control_points(
            SAMPLE_CONTROL_POINTS, method="homography"
        )
        assert transformer.method == "homography"
        assert transformer.transform_matrix is not None
        assert transformer.inverse_matrix is not None

    def test_from_control_points_affine(self):
        """Test creating transformer from control points with affine."""
        transformer = GeoTransformer.from_control_points(
            SAMPLE_CONTROL_POINTS[:3], method="affine"
        )
        assert transformer.method == "affine"
        assert transformer.transform_matrix is not None

    def test_insufficient_points_homography(self):
        """Test that homography requires at least 4 points."""
        with pytest.raises(ValueError, match="at least 4"):
            GeoTransformer.from_control_points(
                SAMPLE_CONTROL_POINTS[:3], method="homography"
            )

    def test_insufficient_points_affine(self):
        """Test that affine requires at least 3 points."""
        with pytest.raises(ValueError, match="at least 3"):
            GeoTransformer.from_control_points(
                SAMPLE_CONTROL_POINTS[:2], method="affine"
            )

    def test_pixel_to_geo_roundtrip(self):
        """Test that pixel→geo→pixel roundtrip preserves coordinates."""
        transformer = GeoTransformer.from_control_points(
            SAMPLE_CONTROL_POINTS, method="homography"
        )

        # Test at control points
        for cp in SAMPLE_CONTROL_POINTS:
            lon, lat = transformer.pixel_to_geo(cp.pixel_x, cp.pixel_y)
            px, py = transformer.geo_to_pixel(lon, lat)

            # Should be close to original pixel coordinates
            assert abs(px - cp.pixel_x) < 1.0, f"pixel_x error: {abs(px - cp.pixel_x)}"
            assert abs(py - cp.pixel_y) < 1.0, f"pixel_y error: {abs(py - cp.pixel_y)}"

    def test_geo_to_pixel_roundtrip(self):
        """Test that geo→pixel→geo roundtrip preserves coordinates."""
        transformer = GeoTransformer.from_control_points(
            SAMPLE_CONTROL_POINTS, method="homography"
        )

        # Test at control points
        for cp in SAMPLE_CONTROL_POINTS:
            px, py = transformer.geo_to_pixel(cp.longitude, cp.latitude)
            lon, lat = transformer.pixel_to_geo(px, py)

            # Should be close to original geo coordinates
            assert abs(lon - cp.longitude) < 1e-5, f"lon error: {abs(lon - cp.longitude)}"
            assert abs(lat - cp.latitude) < 1e-5, f"lat error: {abs(lat - cp.latitude)}"

    def test_batch_conversion(self):
        """Test batch coordinate conversion."""
        transformer = GeoTransformer.from_control_points(
            SAMPLE_CONTROL_POINTS, method="homography"
        )

        pixels = [(cp.pixel_x, cp.pixel_y) for cp in SAMPLE_CONTROL_POINTS]
        geo_coords = transformer.pixels_to_geo_batch(pixels)

        assert len(geo_coords) == len(pixels)
        for (lon, lat), cp in zip(geo_coords, SAMPLE_CONTROL_POINTS):
            assert abs(lon - cp.longitude) < 1e-4
            assert abs(lat - cp.latitude) < 1e-4

    def test_get_scale(self):
        """Test scale factor calculation."""
        transformer = GeoTransformer.from_control_points(
            SAMPLE_CONTROL_POINTS, method="homography"
        )

        scale_x, scale_y = transformer.get_scale()

        # For drone imagery, typical scale is 0.05-0.5 m/pixel
        # Our sample covers ~0.01 degrees lon (~700m) over 800 pixels
        # Expected scale: ~0.9 m/pixel
        assert 0.1 < scale_x < 5.0, f"scale_x out of range: {scale_x}"
        assert 0.1 < scale_y < 5.0, f"scale_y out of range: {scale_y}"


class TestIO:
    """Tests for save/load functionality."""

    def test_save_and_load_roundtrip(self):
        """Test that save→load preserves transformer."""
        transformer = GeoTransformer.from_control_points(
            SAMPLE_CONTROL_POINTS, method="homography"
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_path = Path(f.name)

        try:
            # Save
            save_georef(transformer, temp_path)

            # Load
            loaded = load_georef(temp_path)

            # Verify matrices are preserved
            np.testing.assert_array_almost_equal(
                transformer.transform_matrix, loaded.transform_matrix
            )
            np.testing.assert_array_almost_equal(
                transformer.inverse_matrix, loaded.inverse_matrix
            )

            # Verify reference point
            assert loaded.reference_lon == pytest.approx(transformer.reference_lon)
            assert loaded.reference_lat == pytest.approx(transformer.reference_lat)

            # Verify method
            assert loaded.method == transformer.method

            # Verify transformations produce same results
            test_px, test_py = 500, 400
            orig_lon, orig_lat = transformer.pixel_to_geo(test_px, test_py)
            loaded_lon, loaded_lat = loaded.pixel_to_geo(test_px, test_py)

            assert loaded_lon == pytest.approx(orig_lon, rel=1e-10)
            assert loaded_lat == pytest.approx(orig_lat, rel=1e-10)

        finally:
            temp_path.unlink()

    def test_load_file_not_found(self):
        """Test that loading non-existent file raises error."""
        with pytest.raises(FileNotFoundError):
            load_georef("/nonexistent/path.json")

    def test_load_sample_format(self):
        """Test loading the documented JSON format."""
        sample_json = {
            "version": "1.0",
            "image_path": "test.jpg",
            "image_size": [1000, 800],
            "transform_method": "homography",
            "control_points": [
                {"pixel_x": 100, "pixel_y": 100, "longitude": 11.97, "latitude": 57.71, "name": "GCP1", "is_validation": False},
                {"pixel_x": 900, "pixel_y": 100, "longitude": 11.98, "latitude": 57.71, "name": "GCP2", "is_validation": False},
                {"pixel_x": 100, "pixel_y": 700, "longitude": 11.97, "latitude": 57.70, "name": "GCP3", "is_validation": False},
                {"pixel_x": 900, "pixel_y": 700, "longitude": 11.98, "latitude": 57.70, "name": "GCP4", "is_validation": False},
            ],
            "reference_point": {"longitude": 11.975, "latitude": 57.705},
            "transformation_matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            "inverse_matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            "scale_factors": {"x_meters_per_pixel": 0.5, "y_meters_per_pixel": 0.5},
            "reprojection_error": {"rmse_pixels": 0.5, "rmse_meters": 0.25},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(sample_json, f)
            temp_path = Path(f.name)

        try:
            loaded = load_georef(temp_path)
            assert loaded.method == "homography"
            assert len(loaded.control_points) == 4
            assert loaded.reference_lon == 11.975
            assert loaded.reference_lat == 57.705
        finally:
            temp_path.unlink()


class TestAffineTransformer:
    """Tests specific to affine transformation."""

    def test_affine_transformation_accuracy(self):
        """Test that affine transformation is accurate at control points."""
        transformer = GeoTransformer.from_control_points(
            SAMPLE_CONTROL_POINTS, method="affine"
        )

        # With 4 points, affine should have small but non-zero error
        # (affine can only perfectly fit 3 non-collinear points)
        total_error = 0
        for cp in SAMPLE_CONTROL_POINTS:
            lon, lat = transformer.pixel_to_geo(cp.pixel_x, cp.pixel_y)
            error = math.sqrt((lon - cp.longitude)**2 + (lat - cp.latitude)**2)
            total_error += error

        avg_error = total_error / len(SAMPLE_CONTROL_POINTS)
        # Average error should be small (< 0.001 degrees ~ 100m)
        assert avg_error < 0.001, f"Average error too large: {avg_error}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""
Unit tests for coordinate transformation.

Tests affine and homography transformations, error calculations,
and georeferencing with real control points.
"""

import pytest
import csv
from pathlib import Path
from typing import List

from orbit.models import ControlPoint
from orbit.utils.coordinate_transform import (
    create_transformer, TransformMethod,
    AffineTransformer, HomographyTransformer
)


# ============================================================================
# Helper Functions
# ============================================================================

def load_control_points_from_csv(csv_path: Path) -> List[ControlPoint]:
    """
    Load control points from CSV file.

    Expected CSV format:
    pixel_x,pixel_y,longitude,latitude,name
    """
    control_points = []

    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        first_row = next(reader, None)
        if first_row is None:
            return []

        # Check if CSV has expected format
        required_fields = ['pixel_x', 'pixel_y', 'longitude', 'latitude']
        if not all(field in first_row for field in required_fields):
            # CSV doesn't have expected format, return empty list
            return []

        # Process first row
        cp = ControlPoint(
            pixel_x=float(first_row['pixel_x']),
            pixel_y=float(first_row['pixel_y']),
            longitude=float(first_row['longitude']),
            latitude=float(first_row['latitude']),
            name=first_row.get('name', '')
        )
        control_points.append(cp)

        # Process remaining rows
        for row in reader:
            cp = ControlPoint(
                pixel_x=float(row['pixel_x']),
                pixel_y=float(row['pixel_y']),
                longitude=float(row['longitude']),
                latitude=float(row['latitude']),
                name=row.get('name', '')
            )
            control_points.append(cp)

    return control_points


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def real_control_points(control_points_csv: Path) -> List[ControlPoint]:
    """
    Load real control points from CSV.

    Note: Real-world CSV files (like from GPS/survey data) contain only
    geographic coordinates (lat/lon). Pixel coordinates are assigned by users
    in the GUI when manually placing control points on the image.

    These tests will skip if the CSV doesn't have test format with pixel coords.
    """
    if not control_points_csv.exists():
        pytest.skip(f"Control points CSV not found: {control_points_csv}")

    return load_control_points_from_csv(control_points_csv)


# ============================================================================
# Test Transformer Creation
# ============================================================================

class TestTransformerCreation:
    """Test creating coordinate transformers."""

    def test_create_affine_transformer_with_three_points(self, sample_control_points: List[ControlPoint]):
        """Test creating affine transformer with minimum 3 points."""
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )

        assert transformer is not None
        assert isinstance(transformer, AffineTransformer)

    def test_create_homography_transformer_with_four_points(self, sample_control_points: List[ControlPoint]):
        """Test creating homography transformer requires 4 points."""
        # Add one more point to have 4 total
        points = sample_control_points + [
            ControlPoint(
                pixel_x=400.0, pixel_y=300.0,
                longitude=12.943000, latitude=57.719500,
                name="CP4"
            )
        ]

        transformer = create_transformer(
            points,
            method=TransformMethod.HOMOGRAPHY,
            use_validation=False
        )

        assert transformer is not None
        assert isinstance(transformer, HomographyTransformer)

    def test_create_transformer_with_insufficient_points_returns_none(self):
        """Test that insufficient control points returns None."""
        # Only 2 points (need 3 for affine)
        points = [
            ControlPoint(100.0, 100.0, 12.94, 57.72, "CP1"),
            ControlPoint(200.0, 100.0, 12.945, 57.72, "CP2")
        ]

        transformer = create_transformer(
            points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )

        assert transformer is None

    def test_create_transformer_with_empty_list_returns_none(self):
        """Test that empty control points list returns None."""
        transformer = create_transformer(
            [],
            method=TransformMethod.AFFINE,
            use_validation=False
        )

        assert transformer is None


class TestTransformerWithValidation:
    """Test transformers with validation points."""

    def test_create_transformer_separates_validation_points(self, sample_control_points: List[ControlPoint], validation_control_point: ControlPoint):
        """Test that validation points are separated from training."""
        all_points = sample_control_points + [validation_control_point]

        transformer = create_transformer(
            all_points,
            method=TransformMethod.AFFINE,
            use_validation=True
        )

        assert transformer is not None
        assert len(transformer.training_points) == 3
        assert len(transformer.validation_points) == 1

    def test_validation_disabled_uses_all_points(self, sample_control_points: List[ControlPoint], validation_control_point: ControlPoint):
        """Test that use_validation=False uses all points for training."""
        all_points = sample_control_points + [validation_control_point]

        transformer = create_transformer(
            all_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )

        assert transformer is not None
        assert len(transformer.training_points) == 4
        assert len(transformer.validation_points) == 0


# ============================================================================
# Test Coordinate Transformations
# ============================================================================

class TestPixelToGeoTransformation:
    """Test pixel to geographic coordinate transformations."""

    def test_pixel_to_geo_affine(self, sample_control_points: List[ControlPoint]):
        """Test pixel to geo transformation with affine."""
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )

        # Transform a control point's pixel coords
        cp = sample_control_points[0]
        lon, lat = transformer.pixel_to_geo(cp.pixel_x, cp.pixel_y)

        # Should be close to original geo coords
        assert lon == pytest.approx(cp.longitude, abs=0.0001)
        assert lat == pytest.approx(cp.latitude, abs=0.0001)

    def test_pixel_to_geo_homography(self):
        """Test pixel to geo transformation with homography."""
        # Need 4 points for homography
        points = [
            ControlPoint(100.0, 100.0, 12.940, 57.720, "CP1"),
            ControlPoint(500.0, 100.0, 12.945, 57.720, "CP2"),
            ControlPoint(300.0, 400.0, 12.9425, 57.718, "CP3"),
            ControlPoint(400.0, 300.0, 12.943, 57.7195, "CP4")
        ]

        transformer = create_transformer(
            points,
            method=TransformMethod.HOMOGRAPHY,
            use_validation=False
        )

        # Transform a control point
        cp = points[0]
        lon, lat = transformer.pixel_to_geo(cp.pixel_x, cp.pixel_y)

        assert lon == pytest.approx(cp.longitude, abs=0.0001)
        assert lat == pytest.approx(cp.latitude, abs=0.0001)

    def test_pixel_to_geo_midpoint(self, sample_control_points: List[ControlPoint]):
        """Test transforming a point between control points."""
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )

        # Midpoint between first two control points (in pixels)
        cp1 = sample_control_points[0]
        cp2 = sample_control_points[1]
        mid_x = (cp1.pixel_x + cp2.pixel_x) / 2
        mid_y = (cp1.pixel_y + cp2.pixel_y) / 2

        lon, lat = transformer.pixel_to_geo(mid_x, mid_y)

        # Should be roughly between the two geo points
        mid_lon = (cp1.longitude + cp2.longitude) / 2
        mid_lat = (cp1.latitude + cp2.latitude) / 2

        assert lon == pytest.approx(mid_lon, abs=0.001)
        assert lat == pytest.approx(mid_lat, abs=0.001)


class TestGeoToPixelTransformation:
    """Test geographic to pixel coordinate transformations."""

    def test_geo_to_pixel_affine(self, sample_control_points: List[ControlPoint]):
        """Test geo to pixel transformation with affine."""
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )

        # Transform a control point's geo coords
        cp = sample_control_points[0]
        pixel_x, pixel_y = transformer.geo_to_pixel(cp.longitude, cp.latitude)

        # Should be close to original pixel coords
        assert pixel_x == pytest.approx(cp.pixel_x, abs=1.0)
        assert pixel_y == pytest.approx(cp.pixel_y, abs=1.0)


class TestRoundTripTransformation:
    """Test round-trip pixel → geo → pixel transformations."""

    def test_roundtrip_affine(self, sample_control_points: List[ControlPoint]):
        """Test pixel → geo → pixel roundtrip with affine."""
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )

        # Start with pixel coordinates
        pixel_x_orig = 250.0
        pixel_y_orig = 200.0

        # Transform to geo and back
        lon, lat = transformer.pixel_to_geo(pixel_x_orig, pixel_y_orig)
        pixel_x_back, pixel_y_back = transformer.geo_to_pixel(lon, lat)

        # Should return to original (within tolerance)
        assert pixel_x_back == pytest.approx(pixel_x_orig, abs=0.1)
        assert pixel_y_back == pytest.approx(pixel_y_orig, abs=0.1)

    def test_roundtrip_homography(self):
        """Test pixel → geo → pixel roundtrip with homography."""
        points = [
            ControlPoint(100.0, 100.0, 12.940, 57.720, "CP1"),
            ControlPoint(500.0, 100.0, 12.945, 57.720, "CP2"),
            ControlPoint(300.0, 400.0, 12.9425, 57.718, "CP3"),
            ControlPoint(400.0, 300.0, 12.943, 57.7195, "CP4")
        ]

        transformer = create_transformer(
            points,
            method=TransformMethod.HOMOGRAPHY,
            use_validation=False
        )

        pixel_x_orig = 300.0
        pixel_y_orig = 250.0

        lon, lat = transformer.pixel_to_geo(pixel_x_orig, pixel_y_orig)
        pixel_x_back, pixel_y_back = transformer.geo_to_pixel(lon, lat)

        assert pixel_x_back == pytest.approx(pixel_x_orig, abs=0.5)
        assert pixel_y_back == pytest.approx(pixel_y_orig, abs=0.5)


# ============================================================================
# Test Error Calculations
# ============================================================================

class TestReprojectionError:
    """Test reprojection error calculations."""

    def test_compute_reprojection_error(self, sample_control_points: List[ControlPoint]):
        """Test computing reprojection error for training points."""
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )

        error = transformer.compute_reprojection_error()

        assert 'rmse_pixels' in error
        assert 'rmse_meters' in error
        assert 'max_error_pixels' in error
        assert 'mean_error_pixels' in error

        # RMSE should be small for training points
        assert error['rmse_pixels'] < 5.0  # Within 5 pixels
        assert error['rmse_meters'] is not None

    def test_reprojection_error_low_for_good_fit(self, sample_control_points: List[ControlPoint]):
        """Test that reprojection error is low for well-distributed points."""
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )

        error = transformer.compute_reprojection_error()

        # With 3 points and affine (6 params), fit should be exact
        assert error['rmse_pixels'] < 1.0


class TestValidationError:
    """Test validation error calculations."""

    def test_compute_validation_error_with_gvp(self, sample_control_points: List[ControlPoint], validation_control_point: ControlPoint):
        """Test computing validation error with validation points."""
        all_points = sample_control_points + [validation_control_point]

        transformer = create_transformer(
            all_points,
            method=TransformMethod.AFFINE,
            use_validation=True
        )

        error = transformer.compute_validation_error()

        assert error is not None
        assert 'rmse_pixels' in error
        assert 'rmse_meters' in error
        assert len(error['per_point_errors']) == 1  # One validation point

    def test_validation_error_empty_without_gvps(self, sample_control_points: List[ControlPoint]):
        """Test that validation error is None without validation points."""
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )

        error = transformer.compute_validation_error()

        # No validation points, so error dict should be None or empty
        assert error is None or len(error.get('per_point_errors', [])) == 0


# ============================================================================
# Test Scale Factors
# ============================================================================

class TestScaleFactors:
    """Test scale factor calculations."""

    def test_get_scale_factor_affine(self, sample_control_points: List[ControlPoint]):
        """Test getting scale factors (meters per pixel)."""
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )

        scale_x, scale_y = transformer.get_scale_factor()

        # Scale should be positive and reasonable (cm to meters per pixel)
        assert scale_x > 0
        assert scale_y > 0
        assert 0.01 < scale_x < 10.0  # Between 1cm and 10m per pixel
        assert 0.01 < scale_y < 10.0

    def test_scale_factors_similar_for_orthophoto(self, sample_control_points: List[ControlPoint]):
        """Test that scale factors are similar for orthophoto (affine)."""
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )

        scale_x, scale_y = transformer.get_scale_factor()

        # For orthophotos, X and Y scales should be similar
        ratio = max(scale_x, scale_y) / min(scale_x, scale_y)
        assert ratio < 1.5  # Within 50% of each other


# ============================================================================
# Test with Real Data
# ============================================================================

class TestRealControlPoints:
    """
    Test transformations with real control points from examples.

    NOTE: These tests expect CSV format with pixel_x, pixel_y, longitude, latitude.
    Real-world CSV files (like GPS/survey data) only have lat/lon - users assign
    pixel coordinates in the GUI. These tests will skip with real-world CSV files.

    To make these tests run, you'd need a CSV with both pixel and geo coordinates
    (e.g., exported after manual control point placement in ORBIT).
    """

    def test_load_real_control_points(self, real_control_points: List[ControlPoint]):
        """Test loading real control points from CSV."""
        if len(real_control_points) == 0:
            pytest.skip("CSV file doesn't have expected format (pixel_x, pixel_y, longitude, latitude)")

        # Check structure
        cp = real_control_points[0]
        assert hasattr(cp, 'pixel_x')
        assert hasattr(cp, 'pixel_y')
        assert hasattr(cp, 'longitude')
        assert hasattr(cp, 'latitude')

    def test_create_transformer_with_real_points(self, real_control_points: List[ControlPoint]):
        """Test creating transformer with real control points."""
        if len(real_control_points) < 3:
            pytest.skip("Insufficient real control points")

        transformer = create_transformer(
            real_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )

        assert transformer is not None

    def test_transformation_accuracy_with_real_points(self, real_control_points: List[ControlPoint]):
        """Test transformation accuracy with real control points."""
        if len(real_control_points) < 3:
            pytest.skip("Insufficient real control points")

        transformer = create_transformer(
            real_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )

        # Compute reprojection error
        error = transformer.compute_reprojection_error()

        # Error should be reasonable (depends on measurement accuracy)
        assert error['rmse_meters'] < 10.0  # Within 10 meters
        print(f"  Real data RMSE: {error['rmse_meters']:.2f} meters ({error['rmse_pixels']:.2f} pixels)")

    def test_scale_factor_with_real_points(self, real_control_points: List[ControlPoint]):
        """Test scale factor calculation with real control points."""
        if len(real_control_points) < 3:
            pytest.skip("Insufficient real control points")

        transformer = create_transformer(
            real_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )

        scale_x, scale_y = transformer.get_scale_factor()

        # Scale should be reasonable for drone imagery
        assert scale_x > 0
        assert scale_y > 0
        print(f"  Real data scale: {scale_x*100:.2f} cm/px (X), {scale_y*100:.2f} cm/px (Y)")


# ============================================================================
# Test Edge Cases
# ============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_collinear_points_affine(self):
        """Test that collinear points may cause issues."""
        # Three collinear points (on a line)
        points = [
            ControlPoint(100.0, 100.0, 12.940, 57.720, "CP1"),
            ControlPoint(200.0, 100.0, 12.945, 57.720, "CP2"),
            ControlPoint(300.0, 100.0, 12.950, 57.720, "CP3"),
        ]

        # This may fail or produce poor results
        transformer = create_transformer(
            points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )

        # Either fails to create or has large errors
        if transformer:
            error = transformer.compute_reprojection_error()
            # Collinear points typically give poor results
            assert error is not None

    def test_duplicate_pixel_coordinates(self):
        """Test handling of duplicate pixel coordinates."""
        points = [
            ControlPoint(100.0, 100.0, 12.940, 57.720, "CP1"),
            ControlPoint(100.0, 100.0, 12.941, 57.721, "CP2"),  # Duplicate pixel
            ControlPoint(200.0, 100.0, 12.945, 57.720, "CP3"),
        ]

        # Should handle gracefully (may return None or create transformer)
        transformer = create_transformer(
            points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )

        # It's ok if this fails (returns None) due to duplicate points
        assert transformer is None or isinstance(transformer, AffineTransformer)

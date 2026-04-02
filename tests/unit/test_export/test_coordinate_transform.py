"""
Unit tests for coordinate transformation.

Tests affine and homography transformations, error calculations,
and georeferencing with real control points.
"""

import csv
from pathlib import Path
from typing import List

import pytest
from pyproj import Proj

from orbit.models import ControlPoint
from orbit.utils.coordinate_transform import (
    AffineTransformer,
    HomographyTransformer,
    TransformMethod,
    create_transformer,
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

    def test_create_transformer_separates_validation_points(
        self,
        sample_control_points: List[ControlPoint],
        validation_control_point: ControlPoint,
    ):
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

    def test_validation_disabled_uses_all_points(
        self,
        sample_control_points: List[ControlPoint],
        validation_control_point: ControlPoint,
    ):
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

    def test_compute_validation_error_with_gvp(
        self,
        sample_control_points: List[ControlPoint],
        validation_control_point: ControlPoint,
    ):
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


# ============================================================================
# Test TransformAdjustment
# ============================================================================

class TestTransformAdjustment:
    """Test TransformAdjustment dataclass for fine-tuning georeferencing."""

    def test_default_adjustment_is_identity(self):
        """Test that default adjustment has no effect."""
        from orbit.utils.coordinate_transform import TransformAdjustment
        adj = TransformAdjustment()
        assert adj.is_identity()

    def test_translation_adjustment_not_identity(self):
        """Test that non-zero translation is not identity."""
        from orbit.utils.coordinate_transform import TransformAdjustment
        adj = TransformAdjustment(translation_x=10.0)
        assert not adj.is_identity()

    def test_rotation_adjustment_not_identity(self):
        """Test that non-zero rotation is not identity."""
        from orbit.utils.coordinate_transform import TransformAdjustment
        adj = TransformAdjustment(rotation=5.0)
        assert not adj.is_identity()

    def test_scale_adjustment_not_identity(self):
        """Test that non-unity scale is not identity."""
        from orbit.utils.coordinate_transform import TransformAdjustment
        adj = TransformAdjustment(scale_x=1.1)
        assert not adj.is_identity()

    def test_apply_to_point_translation(self):
        """Test applying translation to a point."""
        from orbit.utils.coordinate_transform import TransformAdjustment
        adj = TransformAdjustment(translation_x=10.0, translation_y=-5.0)
        x, y = adj.apply_to_point(100.0, 50.0)
        assert x == pytest.approx(110.0, abs=0.001)
        assert y == pytest.approx(45.0, abs=0.001)

    def test_apply_to_point_rotation(self):
        """Test applying rotation to a point around pivot."""
        from orbit.utils.coordinate_transform import TransformAdjustment
        # 90 degrees counter-clockwise around origin
        adj = TransformAdjustment(rotation=90.0, pivot_x=0.0, pivot_y=0.0)
        x, y = adj.apply_to_point(10.0, 0.0)
        # (10, 0) rotated 90° CCW → (0, 10)
        assert x == pytest.approx(0.0, abs=0.001)
        assert y == pytest.approx(10.0, abs=0.001)

    def test_apply_to_point_scale(self):
        """Test applying scale to a point around pivot."""
        from orbit.utils.coordinate_transform import TransformAdjustment
        adj = TransformAdjustment(scale_x=2.0, scale_y=0.5, pivot_x=0.0, pivot_y=0.0)
        x, y = adj.apply_to_point(10.0, 10.0)
        assert x == pytest.approx(20.0, abs=0.001)
        assert y == pytest.approx(5.0, abs=0.001)

    def test_apply_inverse_to_point(self):
        """Test that apply and apply_inverse are inverse operations."""
        from orbit.utils.coordinate_transform import TransformAdjustment
        adj = TransformAdjustment(
            translation_x=15.0, translation_y=-10.0,
            rotation=30.0, scale_x=1.2, scale_y=0.9,
            pivot_x=50.0, pivot_y=50.0
        )
        orig_x, orig_y = 100.0, 75.0
        # Forward transform
        adj_x, adj_y = adj.apply_to_point(orig_x, orig_y)
        # Inverse transform
        back_x, back_y = adj.apply_inverse_to_point(adj_x, adj_y)
        # Should return to original
        assert back_x == pytest.approx(orig_x, abs=0.001)
        assert back_y == pytest.approx(orig_y, abs=0.001)

    def test_copy(self):
        """Test copying adjustment."""
        from orbit.utils.coordinate_transform import TransformAdjustment
        adj = TransformAdjustment(translation_x=10.0, rotation=5.0)
        copy = adj.copy()
        assert copy.translation_x == adj.translation_x
        assert copy.rotation == adj.rotation
        # Modifying copy shouldn't affect original
        copy.translation_x = 20.0
        assert adj.translation_x == 10.0

    def test_reset(self):
        """Test resetting adjustment to identity."""
        from orbit.utils.coordinate_transform import TransformAdjustment
        adj = TransformAdjustment(
            translation_x=10.0, translation_y=20.0,
            rotation=45.0, scale_x=2.0, scale_y=0.5,
            pivot_x=100.0, pivot_y=100.0
        )
        adj.reset()
        assert adj.translation_x == 0.0
        assert adj.translation_y == 0.0
        assert adj.rotation == 0.0
        assert adj.scale_x == 1.0
        assert adj.scale_y == 1.0
        # Pivot should be preserved
        assert adj.pivot_x == 100.0
        assert adj.pivot_y == 100.0

    def test_get_adjustment_matrix_identity(self):
        """Test that identity adjustment produces identity matrix."""
        import numpy as np

        from orbit.utils.coordinate_transform import TransformAdjustment
        adj = TransformAdjustment()
        M = adj.get_adjustment_matrix()
        # Should be close to identity matrix
        expected = np.eye(3)
        assert np.allclose(M, expected, atol=1e-10)


# ============================================================================
# Test Metric Conversions
# ============================================================================

class TestMetricConversions:
    """Test lat/lon to meters conversions."""

    def test_latlon_to_meters_at_reference(self, sample_control_points: List[ControlPoint]):
        """Test that reference point converts to (0, 0)."""
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )
        ref_lat = transformer.reference_lat
        ref_lon = transformer.reference_lon
        east, north = transformer.latlon_to_meters(ref_lat, ref_lon)
        assert east == pytest.approx(0.0, abs=0.01)
        assert north == pytest.approx(0.0, abs=0.01)

    def test_meters_to_latlon_roundtrip(self, sample_control_points: List[ControlPoint]):
        """Test that latlon_to_meters and meters_to_latlon are inverses."""
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )
        lat_orig = 57.721
        lon_orig = 12.943
        east, north = transformer.latlon_to_meters(lat_orig, lon_orig)
        lat_back, lon_back = transformer.meters_to_latlon(east, north)
        assert lat_back == pytest.approx(lat_orig, abs=0.0001)
        assert lon_back == pytest.approx(lon_orig, abs=0.0001)

    def test_latlon_to_meters_without_reference_raises(self, sample_control_points: List[ControlPoint]):
        """Test that latlon_to_meters raises if reference not set."""
        # Create a minimal subclass for testing
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )
        # Clear reference points
        transformer.reference_lat = None
        transformer.reference_lon = None
        with pytest.raises(ValueError, match="Reference point not set"):
            transformer.latlon_to_meters(57.72, 12.94)

    def test_meters_to_latlon_without_reference_raises(self, sample_control_points: List[ControlPoint]):
        """Test that meters_to_latlon raises if reference not set."""
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )
        transformer.reference_lat = None
        transformer.reference_lon = None
        with pytest.raises(ValueError, match="Reference point not set"):
            transformer.meters_to_latlon(100.0, 200.0)

    def test_pixel_to_meters(self, sample_control_points: List[ControlPoint]):
        """Test pixel to meters conversion."""
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )
        # Get meters for a point
        mx, my = transformer.pixel_to_meters(300.0, 250.0)
        # Should be some reasonable distance from origin
        assert isinstance(mx, float)
        assert isinstance(my, float)

    def test_meters_to_pixel(self, sample_control_points: List[ControlPoint]):
        """Test meters to pixel conversion roundtrip."""
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )
        px_orig, py_orig = 300.0, 250.0
        mx, my = transformer.pixel_to_meters(px_orig, py_orig)
        px_back, py_back = transformer.meters_to_pixel(mx, my)
        assert px_back == pytest.approx(px_orig, abs=0.1)
        assert py_back == pytest.approx(py_orig, abs=0.1)


# ============================================================================
# Test Batch Operations
# ============================================================================

class TestBatchOperations:
    """Test batch coordinate conversion methods."""

    def test_pixels_to_geo_batch(self, sample_control_points: List[ControlPoint]):
        """Test batch pixel to geo conversion."""
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )
        pixels = [(100.0, 100.0), (200.0, 200.0), (300.0, 300.0)]
        geo_coords = transformer.pixels_to_geo_batch(pixels)
        assert len(geo_coords) == 3
        for lon, lat in geo_coords:
            assert isinstance(lon, float)
            assert isinstance(lat, float)

    def test_pixels_to_meters_batch(self, sample_control_points: List[ControlPoint]):
        """Test batch pixel to meters conversion."""
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )
        pixels = [(100.0, 100.0), (200.0, 200.0), (300.0, 300.0)]
        meters = transformer.pixels_to_meters_batch(pixels)
        assert len(meters) == 3
        for mx, my in meters:
            assert isinstance(mx, float)
            assert isinstance(my, float)

    def test_meters_to_pixels_batch(self, sample_control_points: List[ControlPoint]):
        """Test batch meters to pixel conversion."""
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )
        pixels = [(100.0, 100.0), (200.0, 200.0)]
        meters = transformer.pixels_to_meters_batch(pixels)
        pixels_back = transformer.meters_to_pixels_batch(meters)
        for (px_orig, py_orig), (px_back, py_back) in zip(pixels, pixels_back):
            assert px_back == pytest.approx(px_orig, abs=0.1)
            assert py_back == pytest.approx(py_orig, abs=0.1)


# ============================================================================
# Test Heading Transformation
# ============================================================================

class TestHeadingTransformation:
    """Test heading transformation between coordinate systems."""

    def test_transform_heading(self, sample_control_points: List[ControlPoint]):
        """Test transforming heading from pixel to meter space."""
        import math
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )
        # Heading pointing east (0 radians)
        heading_px = 0.0
        heading_m = transformer.transform_heading(300.0, 250.0, heading_px)
        # Should be some angle (depends on transformation)
        assert isinstance(heading_m, float)
        assert -math.pi <= heading_m <= math.pi

    def test_transform_heading_different_angles(self, sample_control_points: List[ControlPoint]):
        """Test heading transformation for different angles."""
        import math
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )
        # Transform headings at 0, 90, 180, 270 degrees
        for angle_deg in [0, 90, 180, 270]:
            angle_rad = math.radians(angle_deg)
            heading_m = transformer.transform_heading(300.0, 250.0, angle_rad)
            assert isinstance(heading_m, float)


# ============================================================================
# Test Projection Strings
# ============================================================================

class TestProjectionStrings:
    """Test projection string generation."""

    def test_get_metric_origin(self, sample_control_points: List[ControlPoint]):
        """Test getting metric origin (reference point)."""
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )
        lon, lat = transformer.get_metric_origin()
        assert lon is not None
        assert lat is not None
        # Should be within reasonable range
        assert 12.0 < lon < 13.0  # Near our test points
        assert 57.0 < lat < 58.0

    def test_get_projection_string(self, sample_control_points: List[ControlPoint]):
        """Test PROJ4 projection string generation."""
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )
        proj_str = transformer.get_projection_string()
        assert "+proj=tmerc" in proj_str
        assert "+lat_0=" in proj_str
        assert "+lon_0=" in proj_str
        assert "+datum=WGS84" in proj_str

    def test_get_utm_projection_string(self, sample_control_points: List[ControlPoint]):
        """Test UTM projection string generation."""
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )
        proj_str = transformer.get_utm_projection_string()
        assert "+proj=utm" in proj_str
        assert "+zone=" in proj_str
        assert "+north" in proj_str  # Our test points are in northern hemisphere
        assert "+datum=WGS84" in proj_str

    def test_get_utm_zone(self, sample_control_points: List[ControlPoint]):
        """Test UTM zone calculation."""
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )
        zone = transformer.get_utm_zone()
        # UTM zone for lon 12.94 should be zone 33
        assert zone == 33

    def test_get_utm_zone_different_longitudes(self):
        """Test UTM zone calculation for different longitudes."""
        # Create points at different longitudes
        # UTM zone = floor((lon + 180) / 6) + 1
        test_cases = [
            (-120.0, 11),   # Western USA: floor(60/6)+1 = 11
            (0.0, 31),      # Prime meridian: floor(180/6)+1 = 31
            (12.0, 33),     # Europe: floor(192/6)+1 = 33
            (120.0, 51),    # East Asia: floor(300/6)+1 = 51
        ]
        for lon, expected_zone in test_cases:
            points = [
                ControlPoint(100.0, 100.0, lon, 57.72, "CP1"),
                ControlPoint(500.0, 100.0, lon + 0.005, 57.72, "CP2"),
                ControlPoint(300.0, 400.0, lon + 0.0025, 57.718, "CP3"),
            ]
            transformer = create_transformer(
                points,
                method=TransformMethod.AFFINE,
                use_validation=False
            )
            assert transformer.get_utm_zone() == expected_zone


# ============================================================================
# Test Transformation Info
# ============================================================================

class TestTransformationInfo:
    """Test transformation info/metadata methods."""

    def test_get_transformation_info(self, sample_control_points: List[ControlPoint]):
        """Test getting transformation information dictionary."""
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )
        info = transformer.get_transformation_info()
        assert 'method' in info
        assert 'num_training_points' in info
        assert 'num_validation_points' in info
        assert 'reference_latitude' in info
        assert 'reference_longitude' in info
        assert 'scale_x_meters_per_pixel' in info
        assert 'scale_y_meters_per_pixel' in info
        assert info['num_training_points'] == 3
        assert info['num_validation_points'] == 0

    def test_get_transformation_info_with_errors(
        self,
        sample_control_points: List[ControlPoint],
        validation_control_point: ControlPoint,
    ):
        """Test that transformation info includes error metrics."""
        all_points = sample_control_points + [validation_control_point]
        transformer = create_transformer(
            all_points,
            method=TransformMethod.AFFINE,
            use_validation=True
        )
        info = transformer.get_transformation_info()
        assert 'reprojection_error' in info
        assert 'validation_error' in info


# ============================================================================
# Test Adjustment Integration
# ============================================================================

class TestAdjustmentIntegration:
    """Test adjustment integration with transformers."""

    def test_set_adjustment(self, sample_control_points: List[ControlPoint]):
        """Test setting adjustment on transformer."""
        from orbit.utils.coordinate_transform import TransformAdjustment
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )
        adj = TransformAdjustment(translation_x=10.0)
        transformer.set_adjustment(adj)
        assert transformer.adjustment is not None
        assert transformer.has_adjustment()

    def test_clear_adjustment(self, sample_control_points: List[ControlPoint]):
        """Test clearing adjustment from transformer."""
        from orbit.utils.coordinate_transform import TransformAdjustment
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )
        adj = TransformAdjustment(translation_x=10.0)
        transformer.set_adjustment(adj)
        transformer.clear_adjustment()
        assert transformer.adjustment is None
        assert not transformer.has_adjustment()

    def test_has_adjustment_false_for_identity(self, sample_control_points: List[ControlPoint]):
        """Test that identity adjustment is not considered active."""
        from orbit.utils.coordinate_transform import TransformAdjustment
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )
        adj = TransformAdjustment()  # Identity
        transformer.set_adjustment(adj)
        assert not transformer.has_adjustment()

    def test_geo_to_pixel_with_adjustment_affine(self, sample_control_points: List[ControlPoint]):
        """Test that adjustment affects geo_to_pixel for affine."""
        from orbit.utils.coordinate_transform import TransformAdjustment
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )
        lon, lat = 12.942, 57.719
        # Get pixel without adjustment
        px1, py1 = transformer.geo_to_pixel(lon, lat)
        # Apply translation adjustment
        adj = TransformAdjustment(translation_x=50.0, translation_y=-30.0)
        transformer.set_adjustment(adj)
        # Get pixel with adjustment
        px2, py2 = transformer.geo_to_pixel(lon, lat)
        # Result should be shifted
        assert px2 == pytest.approx(px1 + 50.0, abs=0.01)
        assert py2 == pytest.approx(py1 - 30.0, abs=0.01)

    def test_geo_to_pixel_unadjusted_affine(self, sample_control_points: List[ControlPoint]):
        """Test geo_to_pixel_unadjusted ignores adjustment."""
        from orbit.utils.coordinate_transform import TransformAdjustment
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )
        lon, lat = 12.942, 57.719
        # Get unadjusted pixel
        px1, py1 = transformer.geo_to_pixel_unadjusted(lon, lat)
        # Apply adjustment
        adj = TransformAdjustment(translation_x=50.0)
        transformer.set_adjustment(adj)
        # Unadjusted should still give same result
        px2, py2 = transformer.geo_to_pixel_unadjusted(lon, lat)
        assert px2 == pytest.approx(px1, abs=0.01)
        assert py2 == pytest.approx(py1, abs=0.01)

    def test_geo_to_pixel_with_adjustment_homography(self):
        """Test that adjustment affects geo_to_pixel for homography."""
        from orbit.utils.coordinate_transform import TransformAdjustment
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
        lon, lat = 12.942, 57.719
        px1, py1 = transformer.geo_to_pixel(lon, lat)
        adj = TransformAdjustment(translation_x=25.0, translation_y=-15.0)
        transformer.set_adjustment(adj)
        px2, py2 = transformer.geo_to_pixel(lon, lat)
        assert px2 == pytest.approx(px1 + 25.0, abs=0.01)
        assert py2 == pytest.approx(py1 - 15.0, abs=0.01)


# ============================================================================
# Test create_transformer with String Method
# ============================================================================

class TestCreateTransformerStringMethod:
    """Test create_transformer with string method parameter."""

    def test_create_with_string_affine(self, sample_control_points: List[ControlPoint]):
        """Test creating transformer with 'affine' string."""
        transformer = create_transformer(
            sample_control_points,
            method='affine',
            use_validation=False
        )
        assert transformer is not None
        assert isinstance(transformer, AffineTransformer)

    def test_create_with_string_homography(self):
        """Test creating transformer with 'homography' string."""
        points = [
            ControlPoint(100.0, 100.0, 12.940, 57.720, "CP1"),
            ControlPoint(500.0, 100.0, 12.945, 57.720, "CP2"),
            ControlPoint(300.0, 400.0, 12.9425, 57.718, "CP3"),
            ControlPoint(400.0, 300.0, 12.943, 57.7195, "CP4")
        ]
        transformer = create_transformer(
            points,
            method='homography',
            use_validation=False
        )
        assert transformer is not None
        assert isinstance(transformer, HomographyTransformer)


# ============================================================================
# Test get_rms_error_meters
# ============================================================================

class TestGetRmsErrorMeters:
    """Test backwards-compatible get_rms_error_meters function."""

    def test_get_rms_error_meters(self, sample_control_points: List[ControlPoint]):
        """Test getting RMS error in meters."""
        from orbit.utils.coordinate_transform import get_rms_error_meters
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )
        error = get_rms_error_meters(transformer)
        assert isinstance(error, float)
        assert error >= 0.0

    def test_get_rms_error_meters_without_reprojection_error(self, sample_control_points: List[ControlPoint]):
        """Test getting RMS error when no reprojection error computed."""
        from orbit.utils.coordinate_transform import get_rms_error_meters
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )
        # Clear reprojection error
        transformer.reprojection_error = {}
        error = get_rms_error_meters(transformer)
        assert error == 0.0


# ============================================================================
# Test Homography Scale Factor
# ============================================================================

class TestHomographyScaleFactor:
    """Test scale factor calculation for homography transformer."""

    def test_get_scale_factor_homography(self):
        """Test getting scale factors for homography."""
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
        scale_x, scale_y = transformer.get_scale_factor()
        assert scale_x > 0
        assert scale_y > 0
        # Scale can be quite large depending on pixel/geo coordinate ratio
        # Just verify it's positive and finite
        assert scale_x < 1000.0
        assert scale_y < 1000.0


# ============================================================================
# Test Error Handling
# ============================================================================

class TestErrorHandling:
    """Test error handling in coordinate transformations."""

    def test_affine_requires_three_points(self):
        """Test that affine transformer requires at least 3 points."""
        points = [
            ControlPoint(100.0, 100.0, 12.940, 57.720, "CP1"),
            ControlPoint(500.0, 100.0, 12.945, 57.720, "CP2"),
        ]
        with pytest.raises(ValueError, match="at least 3"):
            AffineTransformer(points, use_validation=False)

    def test_homography_requires_four_points(self):
        """Test that homography transformer requires at least 4 points."""
        points = [
            ControlPoint(100.0, 100.0, 12.940, 57.720, "CP1"),
            ControlPoint(500.0, 100.0, 12.945, 57.720, "CP2"),
            ControlPoint(300.0, 400.0, 12.9425, 57.718, "CP3"),
        ]
        with pytest.raises(ValueError, match="at least 4"):
            HomographyTransformer(points, use_validation=False)

    def test_pixel_to_geo_without_matrix_affine(self, sample_control_points: List[ControlPoint]):
        """Test that pixel_to_geo raises if matrix not computed."""
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )
        # Clear the matrix
        transformer.transform_matrix = None
        with pytest.raises(RuntimeError, match="not initialized"):
            transformer.pixel_to_geo(100.0, 100.0)

    def test_geo_to_pixel_without_matrix_affine(self, sample_control_points: List[ControlPoint]):
        """Test that geo_to_pixel raises if inverse matrix not computed."""
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )
        # Clear the inverse matrix
        transformer.inverse_matrix = None
        with pytest.raises(RuntimeError, match="not initialized"):
            transformer.geo_to_pixel(12.94, 57.72)

    def test_pixel_to_geo_without_matrix_homography(self):
        """Test that homography pixel_to_geo raises if matrix not computed."""
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
        transformer.transform_matrix = None
        with pytest.raises(RuntimeError, match="not initialized"):
            transformer.pixel_to_geo(100.0, 100.0)

    def test_geo_to_pixel_without_matrix_homography(self):
        """Test that homography geo_to_pixel raises if inverse matrix not computed."""
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
        transformer.inverse_matrix = None
        with pytest.raises(RuntimeError, match="not initialized"):
            transformer.geo_to_pixel(12.94, 57.72)

    def test_geo_to_pixel_unadjusted_without_matrix_homography(self):
        """Test homography geo_to_pixel_unadjusted raises if matrix not computed."""
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
        transformer.inverse_matrix = None
        with pytest.raises(RuntimeError, match="not initialized"):
            transformer.geo_to_pixel_unadjusted(12.94, 57.72)


# ============================================================================
# Test Export Projection Support
# ============================================================================

class TestExportProjection:
    """Test pyproj-based export projection in coordinate transformers."""

    UTM33_PROJ = "+proj=utm +zone=33 +datum=WGS84 +units=m +no_defs"

    def test_create_transformer_with_export_proj(self, sample_control_points: List[ControlPoint]):
        """Verify _export_proj is initialized when export_proj_string is given."""
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False,
            export_proj_string=self.UTM33_PROJ
        )

        assert transformer is not None
        assert transformer._export_proj_string == self.UTM33_PROJ
        assert transformer._export_proj is not None

    def test_latlon_to_meters_uses_pyproj(self, sample_control_points: List[ControlPoint]):
        """Verify latlon_to_meters matches a direct pyproj call."""
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False,
            export_proj_string=self.UTM33_PROJ
        )

        lat, lon = 57.72, 12.94
        east, north = transformer.latlon_to_meters(lat, lon)

        # Compare with direct pyproj
        proj = Proj(self.UTM33_PROJ)
        expected_east, expected_north = proj(lon, lat)

        assert east == pytest.approx(expected_east, abs=0.001)
        assert north == pytest.approx(expected_north, abs=0.001)

        # UTM zone 33 at this latitude should give large coordinates
        assert east > 100_000
        assert north > 6_000_000

    def test_meters_to_latlon_roundtrip_with_pyproj(self, sample_control_points: List[ControlPoint]):
        """Verify lat/lon → meters → lat/lon round-trip with pyproj."""
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False,
            export_proj_string=self.UTM33_PROJ
        )

        lat_orig, lon_orig = 57.72, 12.94
        east, north = transformer.latlon_to_meters(lat_orig, lon_orig)
        lat_back, lon_back = transformer.meters_to_latlon(east, north)

        assert lat_back == pytest.approx(lat_orig, abs=1e-8)
        assert lon_back == pytest.approx(lon_orig, abs=1e-8)

    def test_without_export_proj_uses_equirectangular(self, sample_control_points: List[ControlPoint]):
        """Verify default (no export_proj_string) still uses equirectangular."""
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )

        assert transformer._export_proj_string is None
        assert transformer._export_proj is None

        # Reference point should map to ~(0, 0) with equirectangular
        ref_lat = transformer.reference_lat
        ref_lon = transformer.reference_lon
        east, north = transformer.latlon_to_meters(ref_lat, ref_lon)
        assert east == pytest.approx(0.0, abs=0.01)
        assert north == pytest.approx(0.0, abs=0.01)

    def test_homography_with_export_proj(self):
        """Verify homography transformer works with export projection (pixel↔geo round-trip)."""
        points = [
            ControlPoint(100.0, 100.0, 12.940, 57.720, "CP1"),
            ControlPoint(500.0, 100.0, 12.945, 57.720, "CP2"),
            ControlPoint(300.0, 400.0, 12.9425, 57.718, "CP3"),
            ControlPoint(400.0, 300.0, 12.943, 57.7195, "CP4")
        ]

        transformer = create_transformer(
            points,
            method=TransformMethod.HOMOGRAPHY,
            use_validation=False,
            export_proj_string=self.UTM33_PROJ
        )

        assert transformer is not None
        assert isinstance(transformer, HomographyTransformer)
        assert transformer._export_proj is not None

        # Pixel → geo → pixel round-trip should still work
        px_orig, py_orig = 300.0, 250.0
        lon, lat = transformer.pixel_to_geo(px_orig, py_orig)
        px_back, py_back = transformer.geo_to_pixel(lon, lat)

        assert px_back == pytest.approx(px_orig, abs=1.0)
        assert py_back == pytest.approx(py_orig, abs=1.0)

    def test_tmerc_export_proj(self, sample_control_points: List[ControlPoint]):
        """Verify Transverse Mercator projection produces near-zero coordinates at origin."""
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False
        )
        tmerc_proj = transformer.get_projection_string()

        transformer_export = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False,
            export_proj_string=tmerc_proj
        )

        # TM centered on reference point → reference point should map near (0, 0)
        ref_lat = transformer_export.reference_lat
        ref_lon = transformer_export.reference_lon
        east, north = transformer_export.latlon_to_meters(ref_lat, ref_lon)

        assert abs(east) < 1.0
        assert abs(north) < 1.0


# ============================================================================
# Test Adjustment in pixel_to_geo
# ============================================================================

class TestPixelToGeoWithAdjustment:
    """Test that pixel_to_geo correctly applies the inverse adjustment."""

    def test_affine_pixel_to_geo_uses_inverse_adjustment(
        self, sample_control_points: List[ControlPoint]
    ):
        """Affine pixel_to_geo should apply inverse adjustment before transform."""
        from orbit.utils.coordinate_transform import TransformAdjustment

        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False,
        )
        assert transformer is not None

        # Get geo coords without adjustment
        px, py = 300.0, 200.0
        lon_orig, lat_orig = transformer.pixel_to_geo(px, py)

        # Apply a translation adjustment
        adj = TransformAdjustment(translation_x=10.0, translation_y=5.0)
        transformer.set_adjustment(adj)

        # pixel_to_geo should now give a *different* result because the
        # pixel has been "shifted" by the adjustment
        lon_adj, lat_adj = transformer.pixel_to_geo(px, py)
        assert (lon_adj, lat_adj) != pytest.approx((lon_orig, lat_orig), abs=1e-10)

    def test_affine_round_trip_with_adjustment(
        self, sample_control_points: List[ControlPoint]
    ):
        """geo_to_pixel → pixel_to_geo should round-trip with adjustment."""
        from orbit.utils.coordinate_transform import TransformAdjustment

        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False,
        )
        assert transformer is not None

        adj = TransformAdjustment(translation_x=15.0, translation_y=-8.0, rotation=1.5)
        transformer.set_adjustment(adj)

        lon_in, lat_in = 12.942, 57.720
        px, py = transformer.geo_to_pixel(lon_in, lat_in)
        lon_out, lat_out = transformer.pixel_to_geo(px, py)

        assert lon_out == pytest.approx(lon_in, abs=1e-6)
        assert lat_out == pytest.approx(lat_in, abs=1e-6)

    def test_homography_pixel_to_geo_uses_inverse_adjustment(
        self, sample_control_points: List[ControlPoint]
    ):
        """Homography pixel_to_geo should apply inverse adjustment."""
        from orbit.utils.coordinate_transform import TransformAdjustment

        points = sample_control_points + [
            ControlPoint(400.0, 300.0, 12.943000, 57.719500, "CP4")
        ]
        transformer = create_transformer(
            points,
            method=TransformMethod.HOMOGRAPHY,
            use_validation=False,
        )
        assert transformer is not None

        px, py = 300.0, 200.0
        lon_orig, lat_orig = transformer.pixel_to_geo(px, py)

        adj = TransformAdjustment(translation_x=10.0, translation_y=5.0)
        transformer.set_adjustment(adj)

        lon_adj, lat_adj = transformer.pixel_to_geo(px, py)
        assert (lon_adj, lat_adj) != pytest.approx((lon_orig, lat_orig), abs=1e-10)

    def test_homography_round_trip_with_adjustment(
        self, sample_control_points: List[ControlPoint]
    ):
        """Homography geo_to_pixel → pixel_to_geo round-trip with adjustment."""
        from orbit.utils.coordinate_transform import TransformAdjustment

        points = sample_control_points + [
            ControlPoint(400.0, 300.0, 12.943000, 57.719500, "CP4")
        ]
        transformer = create_transformer(
            points,
            method=TransformMethod.HOMOGRAPHY,
            use_validation=False,
        )
        assert transformer is not None

        adj = TransformAdjustment(translation_x=15.0, translation_y=-8.0, rotation=1.5)
        transformer.set_adjustment(adj)

        lon_in, lat_in = 12.942, 57.720
        px, py = transformer.geo_to_pixel(lon_in, lat_in)
        lon_out, lat_out = transformer.pixel_to_geo(px, py)

        assert lon_out == pytest.approx(lon_in, abs=1e-5)
        assert lat_out == pytest.approx(lat_in, abs=1e-5)

    def test_no_adjustment_pixel_to_geo_unchanged(
        self, sample_control_points: List[ControlPoint]
    ):
        """pixel_to_geo without adjustment produces same result as before."""
        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False,
        )
        assert transformer is not None

        px, py = 300.0, 200.0
        lon1, lat1 = transformer.pixel_to_geo(px, py)

        # Clear any adjustment explicitly
        transformer.clear_adjustment()
        lon2, lat2 = transformer.pixel_to_geo(px, py)

        assert lon1 == pytest.approx(lon2, abs=1e-12)
        assert lat1 == pytest.approx(lat2, abs=1e-12)

    def test_pixel_to_meters_with_adjustment(
        self, sample_control_points: List[ControlPoint]
    ):
        """pixel_to_meters (used by export) should respect the adjustment."""
        from orbit.utils.coordinate_transform import TransformAdjustment

        transformer = create_transformer(
            sample_control_points,
            method=TransformMethod.AFFINE,
            use_validation=False,
        )
        assert transformer is not None

        px, py = 300.0, 200.0
        mx_orig, my_orig = transformer.pixel_to_meters(px, py)

        adj = TransformAdjustment(translation_x=20.0, translation_y=10.0)
        transformer.set_adjustment(adj)

        mx_adj, my_adj = transformer.pixel_to_meters(px, py)
        assert (mx_adj, my_adj) != pytest.approx((mx_orig, my_orig), abs=1e-6)

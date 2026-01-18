"""Tests for orbit.utils.uncertainty_estimator module."""

import math
import pytest
from unittest.mock import Mock, MagicMock, patch
import numpy as np

from orbit.utils.uncertainty_estimator import UncertaintyEstimator


# ==== Test Fixtures ====

@pytest.fixture
def mock_control_point():
    """Create a mock control point."""
    def _create(pixel_x, pixel_y, latitude, longitude, is_validation=False):
        cp = Mock()
        cp.pixel_x = pixel_x
        cp.pixel_y = pixel_y
        cp.latitude = latitude
        cp.longitude = longitude
        cp.is_validation = is_validation
        return cp
    return _create


@pytest.fixture
def mock_transformer(mock_control_point):
    """Create a mock transformer with training points."""
    def _create(training_points=None, validation_points=None):
        transformer = Mock()

        if training_points is None:
            # Default: 4 points forming a square
            training_points = [
                mock_control_point(100, 100, 57.7, 12.0),
                mock_control_point(900, 100, 57.7, 12.01),
                mock_control_point(100, 900, 57.71, 12.0),
                mock_control_point(900, 900, 57.71, 12.01),
            ]

        transformer.training_points = training_points
        transformer.validation_points = validation_points or []

        # Simple linear transformation for testing
        def pixel_to_geo(px, py):
            lon = 12.0 + (px / 100000)
            lat = 57.7 + (py / 100000)
            return (lon, lat)

        def geo_to_pixel(lon, lat):
            px = (lon - 12.0) * 100000
            py = (lat - 57.7) * 100000
            return (px, py)

        def pixel_to_meters(px, py):
            # 0.1 m/pixel scale
            return (px * 0.1, py * 0.1)

        transformer.pixel_to_geo = pixel_to_geo
        transformer.geo_to_pixel = geo_to_pixel
        transformer.pixel_to_meters = pixel_to_meters
        transformer.get_scale_factor = Mock(return_value=(0.1, 0.1))

        return transformer

    return _create


# ==== Tests for UncertaintyEstimator initialization ====

class TestUncertaintyEstimatorInit:
    """Tests for UncertaintyEstimator initialization."""

    def test_basic_initialization(self, mock_transformer):
        """Basic initialization stores parameters."""
        transformer = mock_transformer()

        estimator = UncertaintyEstimator(
            transformer=transformer,
            image_width=1000,
            image_height=1000
        )

        assert estimator.image_width == 1000
        assert estimator.image_height == 1000
        assert estimator.transformer is transformer

    def test_custom_baseline_uncertainty(self, mock_transformer):
        """Custom baseline uncertainty is stored."""
        transformer = mock_transformer()

        estimator = UncertaintyEstimator(
            transformer=transformer,
            image_width=1000,
            image_height=1000,
            baseline_uncertainty=0.1
        )

        assert estimator._baseline_uncertainty == 0.1

    def test_computes_gcp_residuals(self, mock_transformer):
        """GCP residuals are computed on init."""
        transformer = mock_transformer()

        estimator = UncertaintyEstimator(
            transformer=transformer,
            image_width=1000,
            image_height=1000
        )

        assert hasattr(estimator, 'gcp_residuals')
        assert hasattr(estimator, 'rms_reprojection_error')

    def test_builds_convex_hull(self, mock_transformer):
        """Convex hull is built on init."""
        transformer = mock_transformer()

        estimator = UncertaintyEstimator(
            transformer=transformer,
            image_width=1000,
            image_height=1000
        )

        assert estimator.convex_hull is not None
        assert estimator.hull_points is not None

    def test_fewer_than_3_points_no_hull(self, mock_transformer, mock_control_point):
        """Fewer than 3 training points means no hull."""
        transformer = mock_transformer(training_points=[
            mock_control_point(100, 100, 57.7, 12.0),
            mock_control_point(200, 200, 57.71, 12.01),
        ])

        estimator = UncertaintyEstimator(
            transformer=transformer,
            image_width=1000,
            image_height=1000
        )

        assert estimator.convex_hull is None

    def test_auto_calibrates_with_validation_points(self, mock_transformer, mock_control_point):
        """Auto-calibrates when validation points available."""
        validation_points = [
            mock_control_point(500, 500, 57.705, 12.005, is_validation=True),
            mock_control_point(600, 600, 57.706, 12.006, is_validation=True),
        ]
        transformer = mock_transformer(validation_points=validation_points)

        estimator = UncertaintyEstimator(
            transformer=transformer,
            image_width=1000,
            image_height=1000
        )

        # Should have calibration factor
        assert hasattr(estimator, '_calibration_factor')


# ==== Tests for _is_inside_convex_hull ====

class TestIsInsideConvexHull:
    """Tests for _is_inside_convex_hull method."""

    def test_point_inside_hull(self, mock_transformer):
        """Point inside hull returns True."""
        transformer = mock_transformer()
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        # Center point should be inside
        result = estimator._is_inside_convex_hull(500, 500)

        assert result is True

    def test_point_outside_hull(self, mock_transformer):
        """Point outside hull returns False."""
        transformer = mock_transformer()
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        # Point far outside
        result = estimator._is_inside_convex_hull(-100, -100)

        assert result is False

    def test_point_on_boundary(self, mock_transformer):
        """Point on hull boundary is handled."""
        transformer = mock_transformer()
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        # Point exactly on a vertex
        result = estimator._is_inside_convex_hull(100, 100)

        # Should return True or False without error
        assert isinstance(result, bool)

    def test_no_hull_returns_true(self, mock_transformer, mock_control_point):
        """No hull means all points considered inside."""
        transformer = mock_transformer(training_points=[
            mock_control_point(100, 100, 57.7, 12.0),
        ])
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        result = estimator._is_inside_convex_hull(500, 500)

        assert result is True


# ==== Tests for _distance_from_hull ====

class TestDistanceFromHull:
    """Tests for _distance_from_hull method."""

    def test_point_inside_has_distance(self, mock_transformer):
        """Point inside hull has distance to boundary."""
        transformer = mock_transformer()
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        # Center point - should have distance to edges
        distance = estimator._distance_from_hull(500, 500)

        assert distance > 0

    def test_point_on_boundary_zero_distance(self, mock_transformer):
        """Point on hull boundary has ~0 distance."""
        transformer = mock_transformer()
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        # Point on edge (between 100,100 and 900,100)
        distance = estimator._distance_from_hull(500, 100)

        assert distance < 1.0  # Near zero

    def test_no_hull_returns_zero(self, mock_transformer, mock_control_point):
        """No hull returns 0 distance."""
        transformer = mock_transformer(training_points=[
            mock_control_point(100, 100, 57.7, 12.0),
        ])
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        result = estimator._distance_from_hull(500, 500)

        assert result == 0.0


# ==== Tests for _point_to_segment_distance ====

class TestPointToSegmentDistance:
    """Tests for _point_to_segment_distance method."""

    def test_point_on_segment(self, mock_transformer):
        """Point on segment has zero distance."""
        transformer = mock_transformer()
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        point = np.array([5.0, 0.0])
        seg_start = np.array([0.0, 0.0])
        seg_end = np.array([10.0, 0.0])

        distance = estimator._point_to_segment_distance(point, seg_start, seg_end)

        assert distance == pytest.approx(0.0)

    def test_point_perpendicular_to_segment(self, mock_transformer):
        """Point perpendicular to segment center."""
        transformer = mock_transformer()
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        point = np.array([5.0, 3.0])
        seg_start = np.array([0.0, 0.0])
        seg_end = np.array([10.0, 0.0])

        distance = estimator._point_to_segment_distance(point, seg_start, seg_end)

        assert distance == pytest.approx(3.0)

    def test_point_past_segment_end(self, mock_transformer):
        """Point past segment end measures to endpoint."""
        transformer = mock_transformer()
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        point = np.array([15.0, 0.0])
        seg_start = np.array([0.0, 0.0])
        seg_end = np.array([10.0, 0.0])

        distance = estimator._point_to_segment_distance(point, seg_start, seg_end)

        assert distance == pytest.approx(5.0)

    def test_degenerate_segment(self, mock_transformer):
        """Degenerate segment (point) measures direct distance."""
        transformer = mock_transformer()
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        point = np.array([3.0, 4.0])
        seg_start = np.array([0.0, 0.0])
        seg_end = np.array([0.0, 0.0])  # Same point

        distance = estimator._point_to_segment_distance(point, seg_start, seg_end)

        assert distance == pytest.approx(5.0)  # 3-4-5 triangle


# ==== Tests for estimate_position_uncertainty_at_point ====

class TestEstimatePositionUncertaintyAtPoint:
    """Tests for estimate_position_uncertainty_at_point method."""

    def test_returns_positive_uncertainty(self, mock_transformer):
        """Returns positive uncertainty value."""
        transformer = mock_transformer()
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        uncertainty = estimator.estimate_position_uncertainty_at_point(500, 500)

        assert uncertainty > 0

    def test_uncertainty_near_gcp_is_low(self, mock_transformer):
        """Uncertainty near GCP is relatively low."""
        transformer = mock_transformer()
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        # Near a GCP (100, 100)
        unc_near = estimator.estimate_position_uncertainty_at_point(100, 100)
        # Far from GCPs
        unc_far = estimator.estimate_position_uncertainty_at_point(500, 500)

        assert unc_near <= unc_far

    def test_no_training_points_returns_default(self, mock_transformer):
        """No training points returns default (1.0)."""
        transformer = mock_transformer(training_points=[])

        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        uncertainty = estimator.estimate_position_uncertainty_at_point(500, 500)

        assert uncertainty == 1.0

    def test_uses_cached_grid_if_available(self, mock_transformer):
        """Uses cached grid for interpolation."""
        transformer = mock_transformer()
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        # Generate grid to cache it
        estimator.generate_uncertainty_grid((10, 10))

        # Should use interpolation now
        uncertainty = estimator.estimate_position_uncertainty_at_point(500, 500)

        assert uncertainty > 0


# ==== Tests for _interpolate_uncertainty_from_grid ====

class TestInterpolateUncertaintyFromGrid:
    """Tests for _interpolate_uncertainty_from_grid method."""

    def test_no_grid_returns_baseline(self, mock_transformer):
        """No cached grid returns baseline uncertainty."""
        transformer = mock_transformer()
        estimator = UncertaintyEstimator(transformer, 1000, 1000)
        estimator._cached_grid = None

        result = estimator._interpolate_uncertainty_from_grid(500, 500)

        assert result == estimator._baseline_uncertainty

    def test_interpolates_from_grid(self, mock_transformer):
        """Interpolates from cached grid."""
        transformer = mock_transformer()
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        # Create simple test grid
        estimator._cached_grid = np.array([
            [0.1, 0.2],
            [0.3, 0.4]
        ])

        # Center point should be average
        result = estimator._interpolate_uncertainty_from_grid(500, 500)

        assert 0.1 < result < 0.4

    def test_handles_edge_points(self, mock_transformer):
        """Handles points at grid edges."""
        transformer = mock_transformer()
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        # Create test grid
        estimator._cached_grid = np.array([
            [0.1, 0.2],
            [0.3, 0.4]
        ])

        # Edge point
        result = estimator._interpolate_uncertainty_from_grid(0, 0)

        assert result == pytest.approx(0.1)


# ==== Tests for estimate_scale_uncertainty_at_point ====

class TestEstimateScaleUncertaintyAtPoint:
    """Tests for estimate_scale_uncertainty_at_point method."""

    def test_returns_tuple(self, mock_transformer):
        """Returns tuple of (x_uncertainty, y_uncertainty)."""
        transformer = mock_transformer()
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        result = estimator.estimate_scale_uncertainty_at_point(500, 500)

        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_positive_uncertainties(self, mock_transformer):
        """Returns positive uncertainty values."""
        transformer = mock_transformer()
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        unc_x, unc_y = estimator.estimate_scale_uncertainty_at_point(500, 500)

        assert unc_x > 0
        assert unc_y > 0


# ==== Tests for generate_uncertainty_grid ====

class TestGenerateUncertaintyGrid:
    """Tests for generate_uncertainty_grid method."""

    def test_returns_numpy_array(self, mock_transformer):
        """Returns numpy array."""
        transformer = mock_transformer()
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        grid = estimator.generate_uncertainty_grid((10, 10))

        assert isinstance(grid, np.ndarray)

    def test_correct_shape(self, mock_transformer):
        """Grid has correct shape."""
        transformer = mock_transformer()
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        grid = estimator.generate_uncertainty_grid((20, 30))

        assert grid.shape == (20, 30)

    def test_default_resolution(self, mock_transformer):
        """Uses default resolution when not specified."""
        transformer = mock_transformer()
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        grid = estimator.generate_uncertainty_grid()

        assert grid.shape == (50, 50)  # Default

    def test_caches_result(self, mock_transformer):
        """Result is cached."""
        transformer = mock_transformer()
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        grid = estimator.generate_uncertainty_grid((10, 10))

        assert estimator._cached_grid is grid

    def test_all_positive_values(self, mock_transformer):
        """All grid values are positive."""
        transformer = mock_transformer()
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        grid = estimator.generate_uncertainty_grid((10, 10))

        assert np.all(grid >= 0)


# ==== Tests for find_high_uncertainty_regions ====

class TestFindHighUncertaintyRegions:
    """Tests for find_high_uncertainty_regions method."""

    def test_returns_list_of_tuples(self, mock_transformer):
        """Returns list of (x, y) tuples."""
        transformer = mock_transformer()
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        result = estimator.find_high_uncertainty_regions(threshold=0.0)

        assert isinstance(result, list)
        if result:
            assert isinstance(result[0], tuple)
            assert len(result[0]) == 2

    def test_high_threshold_fewer_results(self, mock_transformer):
        """Higher threshold returns fewer suggestions."""
        transformer = mock_transformer()
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        low = estimator.find_high_uncertainty_regions(threshold=0.01)
        high = estimator.find_high_uncertainty_regions(threshold=10.0)

        assert len(high) <= len(low)

    def test_very_high_threshold_empty(self, mock_transformer):
        """Very high threshold returns no suggestions."""
        transformer = mock_transformer()
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        result = estimator.find_high_uncertainty_regions(threshold=100.0)

        assert result == []

    def test_results_within_image_bounds(self, mock_transformer):
        """All suggestions are within image bounds."""
        transformer = mock_transformer()
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        result = estimator.find_high_uncertainty_regions(threshold=0.0)

        for x, y in result:
            assert 0 <= x <= 1000
            assert 0 <= y <= 1000


# ==== Tests for get_uncertainty_statistics ====

class TestGetUncertaintyStatistics:
    """Tests for get_uncertainty_statistics method."""

    def test_returns_dict(self, mock_transformer):
        """Returns dictionary with statistics."""
        transformer = mock_transformer()
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        stats = estimator.get_uncertainty_statistics()

        assert isinstance(stats, dict)

    def test_contains_expected_keys(self, mock_transformer):
        """Contains expected statistics keys."""
        transformer = mock_transformer()
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        stats = estimator.get_uncertainty_statistics()

        assert 'mean' in stats
        assert 'median' in stats
        assert 'min' in stats
        assert 'max' in stats
        assert 'p90' in stats
        assert 'coverage' in stats

    def test_coverage_contains_thresholds(self, mock_transformer):
        """Coverage contains expected threshold values."""
        transformer = mock_transformer()
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        stats = estimator.get_uncertainty_statistics()

        assert 0.1 in stats['coverage']
        assert 0.2 in stats['coverage']
        assert 0.4 in stats['coverage']

    def test_coverage_values_between_0_and_1(self, mock_transformer):
        """Coverage values are between 0 and 1."""
        transformer = mock_transformer()
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        stats = estimator.get_uncertainty_statistics()

        for threshold, coverage in stats['coverage'].items():
            assert 0.0 <= coverage <= 1.0


# ==== Tests for calibrate_from_validation_points ====

class TestCalibrateFromValidationPoints:
    """Tests for calibrate_from_validation_points method."""

    def test_no_validation_returns_zero(self, mock_transformer):
        """No validation points returns 0 quality."""
        transformer = mock_transformer(validation_points=[])
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        quality = estimator.calibrate_from_validation_points()

        assert quality == 0.0

    def test_single_validation_returns_zero(self, mock_transformer, mock_control_point):
        """Single validation point returns 0 quality."""
        transformer = mock_transformer(validation_points=[
            mock_control_point(500, 500, 57.705, 12.005, is_validation=True),
        ])
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        quality = estimator.calibrate_from_validation_points()

        assert quality == 0.0

    def test_with_validation_points_returns_quality(self, mock_transformer, mock_control_point):
        """With validation points returns quality metric."""
        validation_points = [
            mock_control_point(400, 400, 57.704, 12.004, is_validation=True),
            mock_control_point(600, 600, 57.706, 12.006, is_validation=True),
            mock_control_point(300, 700, 57.707, 12.003, is_validation=True),
        ]
        transformer = mock_transformer(validation_points=validation_points)
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        quality = estimator.calibrate_from_validation_points()

        # Quality can be NaN if correlation fails (constant values), so check for finite or 0
        import math
        assert quality == 0.0 or (0.0 <= quality <= 1.0) or math.isnan(quality)


# ==== Tests for _geo_to_meters ====

class TestGeoToMeters:
    """Tests for _geo_to_meters method."""

    def test_returns_tuple(self, mock_transformer):
        """Returns tuple of (mx, my)."""
        transformer = mock_transformer()
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        result = estimator._geo_to_meters(12.0, 57.7)

        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_no_training_points_returns_zero(self, mock_transformer):
        """No training points returns (0, 0)."""
        transformer = mock_transformer(training_points=[])
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        result = estimator._geo_to_meters(12.0, 57.7)

        assert result == (0.0, 0.0)

    def test_uses_equirectangular_approximation(self, mock_transformer):
        """Uses equirectangular approximation."""
        transformer = mock_transformer()
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        # Reference point should map to near (0, 0)
        ref_lon = 12.005  # Approximate center of training points
        ref_lat = 57.705

        mx, my = estimator._geo_to_meters(ref_lon, ref_lat)

        # Should be near origin (within a few km)
        assert abs(mx) < 10000
        assert abs(my) < 10000


# ==== Tests for compute_uncertainty_monte_carlo ====

class TestComputeUncertaintyMonteCarlo:
    """Tests for compute_uncertainty_monte_carlo method."""

    def test_returns_numpy_array(self, mock_transformer):
        """Returns numpy array."""
        transformer = mock_transformer()
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        grid = estimator.compute_uncertainty_monte_carlo(
            n_iterations=5,
            resolution=(5, 5)
        )

        assert isinstance(grid, np.ndarray)

    def test_correct_shape(self, mock_transformer):
        """Grid has correct shape."""
        transformer = mock_transformer()
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        grid = estimator.compute_uncertainty_monte_carlo(
            n_iterations=5,
            resolution=(10, 15)
        )

        assert grid.shape == (10, 15)

    def test_calls_progress_callback(self, mock_transformer):
        """Calls progress callback during computation."""
        transformer = mock_transformer()
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        callback = Mock()

        estimator.compute_uncertainty_monte_carlo(
            n_iterations=5,
            resolution=(3, 3),
            progress_callback=callback
        )

        # Should have been called multiple times
        assert callback.call_count >= 5

    def test_caches_result(self, mock_transformer):
        """Result is cached."""
        transformer = mock_transformer()
        estimator = UncertaintyEstimator(transformer, 1000, 1000)

        grid = estimator.compute_uncertainty_monte_carlo(
            n_iterations=5,
            resolution=(5, 5)
        )

        assert estimator._cached_grid is grid

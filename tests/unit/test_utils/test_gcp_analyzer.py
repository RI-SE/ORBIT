"""Tests for orbit.utils.gcp_analyzer module."""

import math
import pytest
from unittest.mock import Mock, MagicMock, patch
import numpy as np

from orbit.utils.gcp_analyzer import (
    PointAnalysis,
    GCPAnalysisResult,
    analyze_control_points,
    _calculate_correlation,
    _generate_recommendations,
    format_analysis_report,
)


# ==== Test Fixtures ====

@pytest.fixture
def mock_control_point():
    """Create a mock control point."""
    def _create(name, pixel_x, pixel_y, latitude, longitude, is_validation=False):
        cp = Mock()
        cp.name = name
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
    def _create(training_points=None, validation_points=None, errors=None):
        transformer = Mock()

        if training_points is None:
            # Default: 4 points with small errors
            training_points = [
                mock_control_point("GCP1", 100, 100, 57.7, 12.0),
                mock_control_point("GCP2", 200, 100, 57.7, 12.001),
                mock_control_point("GCP3", 100, 200, 57.701, 12.0),
                mock_control_point("GCP4", 200, 200, 57.701, 12.001),
            ]

        transformer.training_points = training_points
        transformer.validation_points = validation_points or []

        # Default error pattern (if not specified)
        if errors is None:
            errors = {cp: (0.1, 0.1) for cp in training_points}  # Small uniform errors

        # pixel_to_meters returns predicted position
        def pixel_to_meters(px, py):
            # Find matching control point
            for cp in training_points:
                if abs(cp.pixel_x - px) < 1 and abs(cp.pixel_y - py) < 1:
                    err = errors.get(cp, (0, 0))
                    # Return position with error
                    return (px * 0.1 + err[0], py * 0.1 + err[1])
            return (px * 0.1, py * 0.1)

        # latlon_to_meters returns actual position
        def latlon_to_meters(lat, lon):
            # Simple conversion for testing
            return (lon * 1000, lat * 1000)

        transformer.pixel_to_meters = pixel_to_meters
        transformer.latlon_to_meters = latlon_to_meters
        transformer.get_scale_factor = Mock(return_value=(0.1, 0.1))  # m/pixel

        return transformer

    return _create


# ==== Tests for PointAnalysis dataclass ====

class TestPointAnalysis:
    """Tests for PointAnalysis dataclass."""

    def test_create_point_analysis(self):
        """Create PointAnalysis with all fields."""
        pa = PointAnalysis(
            name="GCP1",
            pixel_x=100.0,
            pixel_y=200.0,
            error_meters=0.15,
            error_pixels=1.5,
            is_outlier=False,
            z_score=0.5,
            leave_one_out_improvement=0.02,
            error_east=0.1,
            error_north=0.12
        )

        assert pa.name == "GCP1"
        assert pa.pixel_x == 100.0
        assert pa.error_meters == 0.15
        assert pa.is_outlier is False
        assert pa.z_score == 0.5

    def test_point_analysis_outlier(self):
        """PointAnalysis with outlier flag."""
        pa = PointAnalysis(
            name="Bad Point",
            pixel_x=50.0,
            pixel_y=50.0,
            error_meters=1.5,
            error_pixels=15.0,
            is_outlier=True,
            z_score=3.2,
            leave_one_out_improvement=0.3,
            error_east=1.0,
            error_north=1.1
        )

        assert pa.is_outlier is True
        assert pa.z_score > 2.0


# ==== Tests for GCPAnalysisResult dataclass ====

class TestGCPAnalysisResult:
    """Tests for GCPAnalysisResult dataclass."""

    def test_create_analysis_result(self):
        """Create GCPAnalysisResult with all fields."""
        point_analyses = [
            PointAnalysis("P1", 100, 100, 0.1, 1.0, False, 0.5, 0.0, 0.05, 0.08),
            PointAnalysis("P2", 200, 200, 0.2, 2.0, False, 1.0, 0.01, 0.1, 0.17),
        ]

        result = GCPAnalysisResult(
            point_analyses=point_analyses,
            rmse_meters=0.15,
            mean_error_meters=0.15,
            std_error_meters=0.05,
            outlier_count=0,
            outlier_names=[],
            outlier_threshold=2.0,
            x_correlation=0.1,
            y_correlation=-0.2,
            radial_correlation=0.3,
            has_x_pattern=False,
            has_y_pattern=False,
            has_radial_pattern=False,
            recommendations=["Quality is good."]
        )

        assert len(result.point_analyses) == 2
        assert result.rmse_meters == 0.15
        assert result.outlier_count == 0
        assert result.has_x_pattern is False

    def test_result_with_outliers(self):
        """GCPAnalysisResult with outliers detected."""
        result = GCPAnalysisResult(
            point_analyses=[],
            rmse_meters=0.5,
            mean_error_meters=0.4,
            std_error_meters=0.2,
            outlier_count=2,
            outlier_names=["Bad1", "Bad2"],
            outlier_threshold=2.0,
            x_correlation=0.0,
            y_correlation=0.0,
            radial_correlation=0.0,
            has_x_pattern=False,
            has_y_pattern=False,
            has_radial_pattern=False,
            recommendations=[]
        )

        assert result.outlier_count == 2
        assert "Bad1" in result.outlier_names

    def test_result_with_spatial_patterns(self):
        """GCPAnalysisResult with spatial patterns."""
        result = GCPAnalysisResult(
            point_analyses=[],
            rmse_meters=0.3,
            mean_error_meters=0.25,
            std_error_meters=0.1,
            outlier_count=0,
            outlier_names=[],
            outlier_threshold=2.0,
            x_correlation=0.7,
            y_correlation=0.1,
            radial_correlation=0.6,
            has_x_pattern=True,
            has_y_pattern=False,
            has_radial_pattern=True,
            recommendations=[]
        )

        assert result.has_x_pattern is True
        assert result.has_radial_pattern is True
        assert result.has_y_pattern is False


# ==== Tests for _calculate_correlation ====

class TestCalculateCorrelation:
    """Tests for _calculate_correlation function."""

    def test_perfect_positive_correlation(self):
        """Perfect positive correlation returns 1.0."""
        x = [1, 2, 3, 4, 5]
        y = [2, 4, 6, 8, 10]  # y = 2x

        result = _calculate_correlation(x, y)

        assert result == pytest.approx(1.0)

    def test_perfect_negative_correlation(self):
        """Perfect negative correlation returns -1.0."""
        x = [1, 2, 3, 4, 5]
        y = [10, 8, 6, 4, 2]  # y = -2x + 12

        result = _calculate_correlation(x, y)

        assert result == pytest.approx(-1.0)

    def test_no_correlation(self):
        """No correlation returns near 0."""
        x = [1, 2, 3, 4, 5]
        y = [3, 1, 4, 2, 5]  # Random

        result = _calculate_correlation(x, y)

        assert abs(result) < 0.5  # Weak or no correlation

    def test_single_point_returns_zero(self):
        """Single point returns 0 (can't compute correlation)."""
        result = _calculate_correlation([1], [2])

        assert result == 0.0

    def test_empty_lists_returns_zero(self):
        """Empty lists return 0."""
        result = _calculate_correlation([], [])

        assert result == 0.0

    def test_constant_values_returns_zero(self):
        """Constant values (zero variance) returns 0."""
        x = [5, 5, 5, 5]
        y = [1, 2, 3, 4]

        result = _calculate_correlation(x, y)

        assert result == 0.0

    def test_two_points(self):
        """Two points can compute correlation."""
        x = [0, 10]
        y = [0, 10]

        result = _calculate_correlation(x, y)

        assert result == pytest.approx(1.0)


# ==== Tests for _generate_recommendations ====

class TestGenerateRecommendations:
    """Tests for _generate_recommendations function."""

    def test_excellent_quality_no_issues(self):
        """Excellent quality with no issues."""
        point_analyses = [
            PointAnalysis("P1", 100, 100, 0.05, 0.5, False, 0.0, 0.0, 0.03, 0.04),
        ]

        recs = _generate_recommendations(
            point_analyses, [], 0.0, 0.0, 0.0, 0.1
        )

        assert any("excellent" in r.lower() for r in recs)

    def test_good_quality(self):
        """Good quality assessment."""
        recs = _generate_recommendations([], [], 0.0, 0.0, 0.0, 0.3)

        assert any("good" in r.lower() for r in recs)

    def test_acceptable_quality(self):
        """Acceptable quality assessment."""
        recs = _generate_recommendations([], [], 0.0, 0.0, 0.0, 0.7)

        assert any("acceptable" in r.lower() for r in recs)

    def test_high_rmse_warning(self):
        """High RMSE generates warning."""
        recs = _generate_recommendations([], [], 0.0, 0.0, 0.0, 1.5)

        assert any("high" in r.lower() for r in recs)

    def test_single_outlier_recommendation(self):
        """Single outlier generates specific recommendation."""
        recs = _generate_recommendations([], ["BadPoint"], 0.0, 0.0, 0.0, 0.5)

        assert any("BadPoint" in r for r in recs)
        assert any("outlier" in r.lower() for r in recs)

    def test_multiple_outliers_recommendation(self):
        """Multiple outliers generate recommendation."""
        recs = _generate_recommendations([], ["Bad1", "Bad2", "Bad3"], 0.0, 0.0, 0.0, 0.5)

        assert any("3 points" in r for r in recs)

    def test_x_correlation_pattern(self):
        """High X correlation generates recommendation."""
        recs = _generate_recommendations([], [], 0.7, 0.0, 0.0, 0.5)

        assert any("right side" in r.lower() for r in recs)

    def test_negative_x_correlation_pattern(self):
        """Negative X correlation generates recommendation."""
        recs = _generate_recommendations([], [], -0.7, 0.0, 0.0, 0.5)

        assert any("left side" in r.lower() for r in recs)

    def test_y_correlation_pattern(self):
        """High Y correlation generates recommendation."""
        recs = _generate_recommendations([], [], 0.0, 0.7, 0.0, 0.5)

        assert any("bottom" in r.lower() for r in recs)

    def test_negative_y_correlation_pattern(self):
        """Negative Y correlation generates recommendation."""
        recs = _generate_recommendations([], [], 0.0, -0.7, 0.0, 0.5)

        assert any("top" in r.lower() for r in recs)

    def test_radial_correlation_pattern(self):
        """High radial correlation generates recommendation."""
        recs = _generate_recommendations([], [], 0.0, 0.0, 0.7, 0.5)

        assert any("edge" in r.lower() or "radial" in r.lower() for r in recs)
        assert any("distortion" in r.lower() for r in recs)

    def test_leave_one_out_improvement(self):
        """Big leave-one-out improvement generates recommendation."""
        point_analyses = [
            PointAnalysis("BadPoint", 100, 100, 0.5, 5.0, False, 1.5, 0.2, 0.3, 0.4),
        ]

        recs = _generate_recommendations(point_analyses, [], 0.0, 0.0, 0.0, 0.5)

        assert any("BadPoint" in r for r in recs)
        assert any("removing" in r.lower() for r in recs)


# ==== Tests for analyze_control_points ====

class TestAnalyzeControlPoints:
    """Tests for analyze_control_points function."""

    def test_insufficient_points_returns_none(self, mock_transformer, mock_control_point):
        """Returns None with fewer than 4 training points."""
        transformer = mock_transformer(training_points=[
            mock_control_point("GCP1", 100, 100, 57.7, 12.0),
            mock_control_point("GCP2", 200, 100, 57.7, 12.001),
            mock_control_point("GCP3", 100, 200, 57.701, 12.0),
        ])

        result = analyze_control_points(transformer)

        assert result is None

    def test_basic_analysis(self, mock_transformer):
        """Basic analysis with 4 points."""
        transformer = mock_transformer()

        result = analyze_control_points(transformer)

        assert result is not None
        assert len(result.point_analyses) == 4
        assert result.rmse_meters >= 0
        assert result.outlier_threshold == 2.0

    def test_custom_outlier_threshold(self, mock_transformer):
        """Custom outlier threshold is used."""
        transformer = mock_transformer()

        result = analyze_control_points(transformer, outlier_z_threshold=1.5)

        assert result.outlier_threshold == 1.5

    def test_point_analyses_sorted_by_error(self, mock_transformer, mock_control_point):
        """Point analyses are sorted by error (highest first)."""
        # Create points with varying errors
        training_points = [
            mock_control_point("GCP1", 100, 100, 57.7, 12.0),
            mock_control_point("GCP2", 200, 100, 57.7, 12.001),
            mock_control_point("GCP3", 100, 200, 57.701, 12.0),
            mock_control_point("GCP4", 200, 200, 57.701, 12.001),
        ]

        # Different error for each point
        errors = {
            training_points[0]: (0.1, 0.1),  # Small
            training_points[1]: (0.5, 0.5),  # Large
            training_points[2]: (0.2, 0.2),  # Medium
            training_points[3]: (0.3, 0.3),  # Medium-large
        }

        transformer = mock_transformer(training_points=training_points, errors=errors)

        result = analyze_control_points(transformer)

        # Should be sorted descending by error
        errors_list = [pa.error_meters for pa in result.point_analyses]
        assert errors_list == sorted(errors_list, reverse=True)

    def test_statistics_computed(self, mock_transformer):
        """Statistics (RMSE, mean, std) are computed."""
        transformer = mock_transformer()

        result = analyze_control_points(transformer)

        assert result.rmse_meters > 0
        assert result.mean_error_meters > 0
        assert result.std_error_meters >= 0

    def test_spatial_correlations_computed(self, mock_transformer):
        """Spatial correlations are computed."""
        transformer = mock_transformer()

        result = analyze_control_points(transformer)

        assert -1.0 <= result.x_correlation <= 1.0
        assert -1.0 <= result.y_correlation <= 1.0
        assert -1.0 <= result.radial_correlation <= 1.0

    def test_recommendations_generated(self, mock_transformer):
        """Recommendations are generated."""
        transformer = mock_transformer()

        result = analyze_control_points(transformer)

        assert len(result.recommendations) > 0


# ==== Tests for format_analysis_report ====

class TestFormatAnalysisReport:
    """Tests for format_analysis_report function."""

    @pytest.fixture
    def sample_result(self):
        """Create a sample GCPAnalysisResult for testing."""
        point_analyses = [
            PointAnalysis("GCP1", 100, 100, 0.15, 1.5, False, 0.5, 0.01, 0.1, 0.1),
            PointAnalysis("GCP2", 200, 200, 0.25, 2.5, True, 2.5, 0.05, 0.2, 0.15),
        ]

        return GCPAnalysisResult(
            point_analyses=point_analyses,
            rmse_meters=0.2,
            mean_error_meters=0.2,
            std_error_meters=0.05,
            outlier_count=1,
            outlier_names=["GCP2"],
            outlier_threshold=2.0,
            x_correlation=0.3,
            y_correlation=0.6,
            radial_correlation=0.4,
            has_x_pattern=False,
            has_y_pattern=True,
            has_radial_pattern=False,
            recommendations=["Quality is good.", "Check Y pattern."]
        )

    def test_basic_report(self, sample_result):
        """Basic report contains header and statistics."""
        report = format_analysis_report(sample_result)

        assert "GCP QUALITY ANALYSIS" in report
        assert "Training Points: 2" in report
        assert "RMSE:" in report
        assert "0.200" in report  # RMSE value

    def test_report_includes_outliers(self, sample_result):
        """Report includes outlier section when present."""
        report = format_analysis_report(sample_result)

        assert "OUTLIERS DETECTED" in report
        assert "GCP2" in report

    def test_report_includes_spatial_patterns(self, sample_result):
        """Report includes spatial patterns when present."""
        report = format_analysis_report(sample_result)

        assert "SPATIAL PATTERNS" in report
        assert "Y correlation" in report

    def test_report_includes_recommendations(self, sample_result):
        """Report includes recommendations."""
        report = format_analysis_report(sample_result)

        assert "RECOMMENDATIONS" in report
        assert "Quality is good" in report

    def test_detailed_report(self, sample_result):
        """Detailed report includes per-point information."""
        report = format_analysis_report(sample_result, detailed=True)

        assert "PER-POINT ERRORS" in report
        assert "GCP1" in report
        assert "GCP2" in report
        assert "Z-score" in report
        assert "LOO Impr" in report

    def test_report_without_outliers(self):
        """Report without outliers doesn't show outlier section."""
        result = GCPAnalysisResult(
            point_analyses=[],
            rmse_meters=0.1,
            mean_error_meters=0.1,
            std_error_meters=0.02,
            outlier_count=0,
            outlier_names=[],
            outlier_threshold=2.0,
            x_correlation=0.1,
            y_correlation=0.1,
            radial_correlation=0.1,
            has_x_pattern=False,
            has_y_pattern=False,
            has_radial_pattern=False,
            recommendations=["Excellent quality."]
        )

        report = format_analysis_report(result)

        assert "OUTLIERS DETECTED" not in report

    def test_report_without_spatial_patterns(self):
        """Report without patterns doesn't show patterns section."""
        result = GCPAnalysisResult(
            point_analyses=[],
            rmse_meters=0.1,
            mean_error_meters=0.1,
            std_error_meters=0.02,
            outlier_count=0,
            outlier_names=[],
            outlier_threshold=2.0,
            x_correlation=0.1,
            y_correlation=0.1,
            radial_correlation=0.1,
            has_x_pattern=False,
            has_y_pattern=False,
            has_radial_pattern=False,
            recommendations=[]
        )

        report = format_analysis_report(result)

        assert "SPATIAL PATTERNS" not in report

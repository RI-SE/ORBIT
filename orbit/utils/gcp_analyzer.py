"""
GCP (Ground Control Point) analysis utilities for ORBIT.

Provides functions to detect outliers, analyze spatial error patterns,
and perform leave-one-out testing to identify problematic control points.
"""

import math
import numpy as np
from typing import List, Dict, Tuple, Optional, TYPE_CHECKING
from dataclasses import dataclass

from .logging_config import get_logger

if TYPE_CHECKING:
    from orbit.models import ControlPoint

logger = get_logger(__name__)


@dataclass
class PointAnalysis:
    """Analysis results for a single control point."""
    name: str
    pixel_x: float
    pixel_y: float
    error_meters: float
    error_pixels: float
    is_outlier: bool
    z_score: float
    leave_one_out_improvement: float  # How much RMSE improves if this point is removed
    error_east: float  # Error component in east direction (meters)
    error_north: float  # Error component in north direction (meters)


@dataclass
class GCPAnalysisResult:
    """Complete GCP analysis results."""
    # Per-point analysis
    point_analyses: List[PointAnalysis]

    # Overall statistics
    rmse_meters: float
    mean_error_meters: float
    std_error_meters: float

    # Outlier detection
    outlier_count: int
    outlier_names: List[str]
    outlier_threshold: float  # Z-score threshold used

    # Spatial correlation
    x_correlation: float  # Correlation between error and X position
    y_correlation: float  # Correlation between error and Y position
    radial_correlation: float  # Correlation between error and distance from center

    # Interpretation
    has_x_pattern: bool  # True if X correlation > 0.5
    has_y_pattern: bool  # True if Y correlation > 0.5
    has_radial_pattern: bool  # True if radial correlation > 0.5

    # Recommendations
    recommendations: List[str]


def analyze_control_points(
    transformer,
    outlier_z_threshold: float = 2.0
) -> Optional[GCPAnalysisResult]:
    """
    Analyze control points to detect outliers and spatial error patterns.

    Args:
        transformer: CoordinateTransformer instance with computed transformation
        outlier_z_threshold: Z-score threshold for outlier detection (default 2.0)

    Returns:
        GCPAnalysisResult with detailed analysis, or None if insufficient points
    """
    training_points = transformer.training_points

    if len(training_points) < 4:
        logger.warning("Need at least 4 training points for analysis")
        return None

    # Calculate errors for all training points
    errors = []
    for cp in training_points:
        pred_mx, pred_my = transformer.pixel_to_meters(cp.pixel_x, cp.pixel_y)
        actual_mx, actual_my = transformer.latlon_to_meters(cp.latitude, cp.longitude)

        error_east = pred_mx - actual_mx
        error_north = pred_my - actual_my
        error_m = math.sqrt(error_east**2 + error_north**2)

        # Approximate pixel error using average scale
        scale_x, scale_y = transformer.get_scale_factor()
        avg_scale = (scale_x + scale_y) / 2
        error_px = error_m / avg_scale if avg_scale > 0 else 0

        errors.append({
            'cp': cp,
            'error_m': error_m,
            'error_px': error_px,
            'error_east': error_east,
            'error_north': error_north
        })

    # Calculate statistics
    error_values = [e['error_m'] for e in errors]
    mean_error = np.mean(error_values)
    std_error = np.std(error_values)
    rmse = math.sqrt(np.mean(np.array(error_values)**2))

    # Detect outliers using z-score
    outliers = []
    point_analyses = []

    for e in errors:
        z_score = (e['error_m'] - mean_error) / std_error if std_error > 0 else 0
        is_outlier = abs(z_score) > outlier_z_threshold

        if is_outlier:
            outliers.append(e['cp'].name or f"Point at ({e['cp'].pixel_x:.0f}, {e['cp'].pixel_y:.0f})")

        # Leave-one-out improvement will be calculated later
        point_analyses.append(PointAnalysis(
            name=e['cp'].name or f"Point at ({e['cp'].pixel_x:.0f}, {e['cp'].pixel_y:.0f})",
            pixel_x=e['cp'].pixel_x,
            pixel_y=e['cp'].pixel_y,
            error_meters=e['error_m'],
            error_pixels=e['error_px'],
            is_outlier=is_outlier,
            z_score=z_score,
            leave_one_out_improvement=0.0,  # Will be updated
            error_east=e['error_east'],
            error_north=e['error_north']
        ))

    # Calculate spatial correlations
    x_corr = _calculate_correlation(
        [e['cp'].pixel_x for e in errors],
        error_values
    )
    y_corr = _calculate_correlation(
        [e['cp'].pixel_y for e in errors],
        error_values
    )

    # Radial distance from image center (approximate)
    center_x = np.mean([e['cp'].pixel_x for e in errors])
    center_y = np.mean([e['cp'].pixel_y for e in errors])
    radial_distances = [
        math.sqrt((e['cp'].pixel_x - center_x)**2 + (e['cp'].pixel_y - center_y)**2)
        for e in errors
    ]
    radial_corr = _calculate_correlation(radial_distances, error_values)

    # Leave-one-out analysis
    if len(training_points) >= 5:  # Need at least 4 points remaining for homography
        _compute_leave_one_out(transformer, errors, point_analyses, rmse)

    # Sort by error (highest first) for easier reading
    point_analyses.sort(key=lambda p: p.error_meters, reverse=True)

    # Generate recommendations
    recommendations = _generate_recommendations(
        point_analyses, outliers, x_corr, y_corr, radial_corr, rmse
    )

    return GCPAnalysisResult(
        point_analyses=point_analyses,
        rmse_meters=rmse,
        mean_error_meters=mean_error,
        std_error_meters=std_error,
        outlier_count=len(outliers),
        outlier_names=outliers,
        outlier_threshold=outlier_z_threshold,
        x_correlation=x_corr,
        y_correlation=y_corr,
        radial_correlation=radial_corr,
        has_x_pattern=abs(x_corr) > 0.5,
        has_y_pattern=abs(y_corr) > 0.5,
        has_radial_pattern=abs(radial_corr) > 0.5,
        recommendations=recommendations
    )


def _calculate_correlation(x_values: List[float], y_values: List[float]) -> float:
    """Calculate Pearson correlation coefficient."""
    n = len(x_values)
    if n < 2:
        return 0.0

    mean_x = sum(x_values) / n
    mean_y = sum(y_values) / n

    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_values, y_values))
    denom_x = math.sqrt(sum((x - mean_x)**2 for x in x_values))
    denom_y = math.sqrt(sum((y - mean_y)**2 for y in y_values))

    if denom_x < 1e-10 or denom_y < 1e-10:
        return 0.0

    return numerator / (denom_x * denom_y)


def _compute_leave_one_out(transformer, errors, point_analyses, original_rmse):
    """Compute leave-one-out RMSE improvement for each point."""
    from .coordinate_transform import HomographyTransformer, AffineTransformer

    all_cps = transformer.training_points + transformer.validation_points

    for i, e in enumerate(errors):
        cp_to_remove = e['cp']

        # Create filtered control point list
        filtered_cps = [cp for cp in all_cps if cp != cp_to_remove]

        # Check if we have enough points
        min_points = 4 if isinstance(transformer, HomographyTransformer) else 3
        training_remaining = len([cp for cp in filtered_cps if not cp.is_validation])

        if training_remaining < min_points:
            point_analyses[i].leave_one_out_improvement = 0.0
            continue

        try:
            # Create new transformer without this point
            if isinstance(transformer, HomographyTransformer):
                new_transformer = HomographyTransformer(filtered_cps, use_validation=True)
            else:
                new_transformer = AffineTransformer(filtered_cps, use_validation=True)

            # Calculate new RMSE on remaining training points
            new_errors = []
            for cp in new_transformer.training_points:
                pred_mx, pred_my = new_transformer.pixel_to_meters(cp.pixel_x, cp.pixel_y)
                actual_mx, actual_my = new_transformer.latlon_to_meters(cp.latitude, cp.longitude)
                new_errors.append(math.sqrt((pred_mx - actual_mx)**2 + (pred_my - actual_my)**2))

            new_rmse = math.sqrt(np.mean(np.array(new_errors)**2)) if new_errors else 0

            # Improvement is positive if removing this point helps
            improvement = original_rmse - new_rmse
            point_analyses[i].leave_one_out_improvement = improvement

        except Exception as ex:
            logger.debug(f"Leave-one-out failed for {cp_to_remove.name}: {ex}")
            point_analyses[i].leave_one_out_improvement = 0.0


def _generate_recommendations(
    point_analyses: List[PointAnalysis],
    outliers: List[str],
    x_corr: float,
    y_corr: float,
    radial_corr: float,
    rmse: float
) -> List[str]:
    """Generate actionable recommendations based on analysis."""
    recommendations = []

    # Check for outliers
    if outliers:
        if len(outliers) == 1:
            recommendations.append(
                f"Point '{outliers[0]}' is a statistical outlier. "
                f"Verify its GPS coordinates or consider excluding it."
            )
        else:
            recommendations.append(
                f"{len(outliers)} points are statistical outliers: {', '.join(outliers)}. "
                f"Verify their GPS coordinates."
            )

    # Check for leave-one-out improvements
    big_improvements = [
        p for p in point_analyses
        if p.leave_one_out_improvement > rmse * 0.3  # >30% improvement
    ]
    if big_improvements:
        for p in big_improvements[:2]:  # Top 2 only
            pct = (p.leave_one_out_improvement / rmse) * 100 if rmse > 0 else 0
            recommendations.append(
                f"Removing '{p.name}' would reduce RMSE by {p.leave_one_out_improvement:.2f}m ({pct:.0f}%). "
                f"Check this point's coordinates."
            )

    # Check for spatial patterns
    if abs(x_corr) > 0.5:
        direction = "right side" if x_corr > 0 else "left side"
        recommendations.append(
            f"Errors increase toward the {direction} of the image (X correlation: {x_corr:.2f}). "
            f"This may indicate lens distortion or GPS errors in that region."
        )

    if abs(y_corr) > 0.5:
        direction = "bottom" if y_corr > 0 else "top"
        recommendations.append(
            f"Errors increase toward the {direction} of the image (Y correlation: {y_corr:.2f}). "
            f"This may indicate terrain elevation changes or viewing angle effects."
        )

    if abs(radial_corr) > 0.5:
        recommendations.append(
            f"Errors increase toward image edges (radial correlation: {radial_corr:.2f}). "
            f"This typically indicates uncorrected lens distortion."
        )

    # Overall quality assessment
    if rmse < 0.2:
        recommendations.append("Overall georeferencing quality is excellent (<20cm RMSE).")
    elif rmse < 0.5:
        recommendations.append("Overall georeferencing quality is good (<50cm RMSE).")
    elif rmse < 1.0:
        recommendations.append("Overall georeferencing quality is acceptable (<1m RMSE).")
    else:
        recommendations.append(
            f"RMSE is high ({rmse:.2f}m). Consider adding more control points "
            f"or checking for problematic points."
        )

    return recommendations


def format_analysis_report(result: GCPAnalysisResult, detailed: bool = False) -> str:
    """
    Format analysis results as a text report.

    Args:
        result: GCPAnalysisResult from analyze_control_points()
        detailed: If True, include per-point details

    Returns:
        Formatted text report
    """
    lines = []

    lines.append("=" * 60)
    lines.append("GCP QUALITY ANALYSIS")
    lines.append("=" * 60)
    lines.append("")

    # Summary statistics
    lines.append(f"Training Points: {len(result.point_analyses)}")
    lines.append(f"RMSE: {result.rmse_meters:.3f} m")
    lines.append(f"Mean Error: {result.mean_error_meters:.3f} m")
    lines.append(f"Std Dev: {result.std_error_meters:.3f} m")
    lines.append("")

    # Outliers
    if result.outlier_count > 0:
        lines.append(f"OUTLIERS DETECTED: {result.outlier_count}")
        for name in result.outlier_names:
            lines.append(f"  - {name}")
        lines.append("")

    # Spatial patterns
    if result.has_x_pattern or result.has_y_pattern or result.has_radial_pattern:
        lines.append("SPATIAL PATTERNS:")
        if result.has_x_pattern:
            lines.append(f"  X correlation: {result.x_correlation:.2f}")
        if result.has_y_pattern:
            lines.append(f"  Y correlation: {result.y_correlation:.2f}")
        if result.has_radial_pattern:
            lines.append(f"  Radial correlation: {result.radial_correlation:.2f}")
        lines.append("")

    # Per-point details (if requested)
    if detailed:
        lines.append("PER-POINT ERRORS (sorted by error):")
        lines.append("-" * 60)
        lines.append(f"{'Name':<20} {'Error(m)':<10} {'Z-score':<10} {'LOO Impr':<10}")
        lines.append("-" * 60)
        for p in result.point_analyses:
            flag = " *" if p.is_outlier else ""
            lines.append(
                f"{p.name:<20} {p.error_meters:<10.3f} {p.z_score:<10.2f} "
                f"{p.leave_one_out_improvement:<10.3f}{flag}"
            )
        lines.append("")
        lines.append("* = outlier (z-score > {:.1f})".format(result.outlier_threshold))
        lines.append("LOO Impr = RMSE improvement if point is removed")
        lines.append("")

    # Recommendations
    if result.recommendations:
        lines.append("RECOMMENDATIONS:")
        lines.append("-" * 60)
        for rec in result.recommendations:
            lines.append(f"  {rec}")
        lines.append("")

    return "\n".join(lines)

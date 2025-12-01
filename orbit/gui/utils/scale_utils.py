"""Scale and transformer utility functions for ORBIT dialogs.

Provides helper functions for common georeferencing operations to reduce
code duplication across dialog classes.
"""

from typing import Optional, Tuple, TYPE_CHECKING

from orbit.utils.logging_config import get_logger

if TYPE_CHECKING:
    from orbit.models import Project
    from orbit.utils import CoordinateTransformer

logger = get_logger(__name__)


def get_scale_factors(project: 'Project') -> Optional[Tuple[float, float]]:
    """Get scale factors from project if georeferenced.

    Args:
        project: The ORBIT project with control points.

    Returns:
        Tuple of (scale_x, scale_y) in meters/pixel, or None if not available.

    Example:
        scale = get_scale_factors(self.project)
        if scale:
            scale_x, scale_y = scale
            meters = pixels * scale_x
    """
    if not project.has_georeferencing():
        return None

    try:
        from orbit.export import create_transformer, TransformMethod

        method = (TransformMethod.HOMOGRAPHY
                  if project.transform_method == 'homography'
                  else TransformMethod.AFFINE)
        transformer = create_transformer(project.control_points, method, use_validation=True)

        if transformer:
            return transformer.get_scale_factor()
    except Exception as e:
        logger.debug(f"Failed to get scale factors: {e}")

    return None


def get_transformer(project: 'Project') -> Optional['CoordinateTransformer']:
    """Get coordinate transformer from project if georeferenced.

    Args:
        project: The ORBIT project with control points.

    Returns:
        CoordinateTransformer instance, or None if not available.
    """
    if not project.has_georeferencing():
        return None

    try:
        from orbit.export import create_transformer, TransformMethod

        method = (TransformMethod.HOMOGRAPHY
                  if project.transform_method == 'homography'
                  else TransformMethod.AFFINE)
        return create_transformer(project.control_points, method, use_validation=True)
    except Exception as e:
        logger.debug(f"Failed to create transformer: {e}")

    return None


def format_with_metric(
    value_px: float,
    scale: Optional[float],
    precision_px: int = 1,
    precision_m: int = 2
) -> str:
    """Format a pixel value with optional metric conversion.

    Args:
        value_px: Value in pixels.
        scale: Scale factor (m/px), or None for pixels only.
        precision_px: Decimal places for pixel value.
        precision_m: Decimal places for meter value.

    Returns:
        Formatted string like "123.4 px" or "123.4 px (12.34 m)".

    Example:
        text = format_with_metric(s_position, scale_x)
        # Returns "150.0 px (8.70 m)" if scale is available
    """
    px_str = f"{value_px:.{precision_px}f} px"

    if scale and scale > 0:
        meters = value_px * scale
        return f"{px_str} ({meters:.{precision_m}f} m)"

    return px_str


def pixels_to_meters(
    value_px: float,
    scale: Optional[float],
    default: Optional[float] = None
) -> Optional[float]:
    """Convert pixel value to meters using scale factor.

    Args:
        value_px: Value in pixels.
        scale: Scale factor (m/px), or None.
        default: Value to return if scale is not available.

    Returns:
        Value in meters, or default if scale not available.
    """
    if scale and scale > 0:
        return value_px * scale
    return default

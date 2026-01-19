"""
Export georeferencing parameters to JSON.

This module exports ORBIT's georeferencing data (control points, transformation
matrices, scale factors) to a standalone JSON file that can be used by external
tools for pixel↔geo coordinate conversion.
"""

import json
from importlib.metadata import version as get_package_version
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

from orbit.models.project import Project, ControlPoint
from orbit.utils.coordinate_transform import (
    CoordinateTransformer,
    TransformMethod,
    AffineTransformer,
    HomographyTransformer,
)
from orbit.utils.logging_config import get_logger

logger = get_logger(__name__)

GEOREF_FORMAT_VERSION = "1.0"


def export_georeferencing(
    project: Project,
    output_path: Path,
    transformer: CoordinateTransformer,
    image_size: Tuple[int, int],
    project_file: Optional[Path] = None,
) -> bool:
    """
    Export georeferencing parameters to JSON.

    Args:
        project: ORBIT project containing control points
        output_path: Path to write JSON file
        transformer: Computed coordinate transformer
        image_size: Image dimensions as (width, height)
        project_file: Path to the ORBIT project file (.orbit), if saved

    Returns:
        True if export successful, False otherwise
    """
    try:
        data = build_georef_data(project, transformer, image_size, project_file)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

        logger.info(f"Exported georeferencing to {output_path}")
        return True

    except Exception as e:
        logger.error(f"Failed to export georeferencing: {e}")
        return False


def build_georef_data(
    project: Project,
    transformer: CoordinateTransformer,
    image_size: Tuple[int, int],
    project_file: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Build georeferencing data dictionary.

    Args:
        project: ORBIT project containing control points
        transformer: Computed coordinate transformer
        image_size: Image dimensions as (width, height)
        project_file: Path to the ORBIT project file (.orbit), if saved

    Returns:
        Dictionary with georeferencing data
    """
    # Determine transform method string
    if isinstance(transformer, HomographyTransformer):
        method = "homography"
    elif isinstance(transformer, AffineTransformer):
        method = "affine"
    else:
        method = "unknown"

    # Build control points list
    control_points = [
        {
            "pixel_x": cp.pixel_x,
            "pixel_y": cp.pixel_y,
            "longitude": cp.longitude,
            "latitude": cp.latitude,
            "name": cp.name or "",
            "is_validation": cp.is_validation,
        }
        for cp in project.control_points
    ]

    # Get scale factors
    scale_x, scale_y = transformer.get_scale_factor()

    # Get reprojection error
    reproj_error = transformer.reprojection_error or {}

    # Get ORBIT version
    try:
        orbit_version = get_package_version("orbit")
    except Exception:
        orbit_version = "unknown"

    # Build output structure
    data = {
        "version": GEOREF_FORMAT_VERSION,
        "creator": {
            "application": "ORBIT",
            "application_version": orbit_version,
        },
        "source": {
            "project_file": str(project_file) if project_file else None,
            "image_path": str(project.image_path) if project.image_path else None,
        },
        "image_size": list(image_size),
        "transform_method": method,
        "control_points": control_points,
        "reference_point": {
            "longitude": transformer.reference_lon,
            "latitude": transformer.reference_lat,
        },
        "transformation_matrix": _matrix_to_list(transformer.transform_matrix),
        "inverse_matrix": _matrix_to_list(transformer.inverse_matrix),
        "scale_factors": {
            "x_meters_per_pixel": scale_x,
            "y_meters_per_pixel": scale_y,
        },
        "reprojection_error": {
            "rmse_pixels": reproj_error.get("rmse_pixels", 0.0),
            "rmse_meters": reproj_error.get("rmse_meters", 0.0),
        },
    }

    # Add validation error if available
    if transformer.validation_error:
        data["validation_error"] = {
            "rmse_pixels": transformer.validation_error.get("rmse_pixels", 0.0),
            "rmse_meters": transformer.validation_error.get("rmse_meters", 0.0),
        }

    return data


def _matrix_to_list(matrix) -> Optional[List[List[float]]]:
    """Convert numpy matrix to nested list for JSON serialization."""
    if matrix is None:
        return None
    return [[float(v) for v in row] for row in matrix]

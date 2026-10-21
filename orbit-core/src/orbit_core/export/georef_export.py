"""
Export georeferencing parameters to JSON.

This module exports ORBIT's georeferencing data (control points, transformation
matrices, scale factors) to a standalone JSON file that can be used by external
tools for pixel↔geo coordinate conversion.
"""

import json
import math
from importlib.metadata import version as get_package_version
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from orbit_core.models.project import ControlPoint, Project
from orbit_core.utils.coordinate_transform import (
    AffineTransformer,
    CoordinateTransformer,
    DroneAssistedTransformer,
    HomographyTransformer,
    HybridTransformer,
)
from orbit_core.utils.logging_config import get_logger

logger = get_logger(__name__)

# 1.2: rmse_pixels of training points is a true residual (before: pixel->geo->pixel round trip, ~0)
GEOREF_FORMAT_VERSION = "1.2"


# Pixel grid (per axis) sampled to refit a drone-assisted mapping in the export projection
PROJECTED_FIT_GRID = 9
# Largest acceptable deviation of the refitted homography from the sampled mapping
PROJECTED_FIT_TOLERANCE_M = 0.01


def _projected_matrices(transformer: DroneAssistedTransformer, image_size: Tuple[int, int],
                        proj_string: str) -> Tuple[np.ndarray, np.ndarray]:
    """Pixel -> projected homography (and inverse) equivalent to a drone-assisted transformer.

    Fitted to the transformer's own pixel -> geo mapping on a pixel grid, so it includes any
    active adjustment. Local ENU -> projection is near-affine over an image footprint, so the
    result stays a homography; the fit deviation is logged.
    """
    width, height = image_size
    grid = [ControlPoint(pixel_x=float(u), pixel_y=float(v), longitude=lon, latitude=lat)
            for u in np.linspace(0, width, PROJECTED_FIT_GRID)
            for v in np.linspace(0, height, PROJECTED_FIT_GRID)
            for lon, lat in [transformer.pixel_to_geo(u, v)]]
    fitted = HomographyTransformer(grid, use_validation=False, export_proj_string=proj_string)
    deviation = max(math.dist(fitted.pixel_to_meters(cp.pixel_x, cp.pixel_y),
                              fitted.latlon_to_projected(cp.latitude, cp.longitude)) for cp in grid)
    if deviation > PROJECTED_FIT_TOLERANCE_M:
        logger.warning(f"Drone-assisted georef: projected homography deviates up to {deviation:.3f} m")
    return fitted.transform_matrix, fitted.inverse_matrix


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
    if isinstance(transformer, (HybridTransformer, HomographyTransformer, DroneAssistedTransformer)):
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

    # If the transformer has an active adjustment, bake it into the exported
    # matrices so downstream consumers get the fully-adjusted transform.
    # For pixel→ENU (transform_matrix):  effective = transform_matrix @ A_inv
    # For ENU→pixel  (inverse_matrix):   effective = A @ inverse_matrix
    transform_matrix = transformer.transform_matrix
    inverse_matrix = transformer.inverse_matrix
    proj_string = getattr(transformer, '_export_proj_string', None)
    if isinstance(transformer, DroneAssistedTransformer) and proj_string:
        # Its matrices map to local ENU around the nadir; consumers read them in proj_string's frame
        transform_matrix, inverse_matrix = _projected_matrices(transformer, image_size, proj_string)
    elif transformer.adjustment is not None and not transformer.adjustment.is_identity():
        A = transformer.adjustment.get_adjustment_matrix()
        A_inv = np.linalg.inv(A)
        if transform_matrix is not None:
            transform_matrix = transform_matrix @ A_inv
        if inverse_matrix is not None:
            inverse_matrix = A @ inverse_matrix

    # Build output structure
    data = {
        "format": "ORBIT Georeferencing Data",
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
        "transformation_matrix": _matrix_to_list(transform_matrix),
        "inverse_matrix": _matrix_to_list(inverse_matrix),
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

    # Add proj_string if the transformer was built with one (UTM or other CRS)
    if proj_string:
        data["proj_string"] = proj_string

    return data


def _matrix_to_list(matrix) -> Optional[List[List[float]]]:
    """Convert numpy matrix to nested list for JSON serialization."""
    if matrix is None:
        return None
    return [[float(v) for v in row] for row in matrix]

"""
I/O functions for orbit-georef.
"""

import json
import warnings
from pathlib import Path
from typing import Union

import numpy as np

from . import uncertainty
from .camera_model import CameraModel
from .models import ControlPoint
from .transformer import GeoTransformer

# Exports from the GUI's HybridTransformer were labelled "unknown" until ORBIT 0.8.0 (commit 0015a0f, 2026-04-01)
LEGACY_UNKNOWN_METHOD = "unknown"


def _resolve_method(method: str, transform_matrix: np.ndarray, path: Path) -> str:
    """Map a legacy "unknown" method to homography when the matrix is visibly projective."""
    if method != LEGACY_UNKNOWN_METHOD:
        return method
    if np.any(transform_matrix[2, :2] != 0.0):
        warnings.warn(
            f"{path}: transform_method 'unknown' (legacy ORBIT export) read as homography, "
            "since the matrix has perspective terms",
            stacklevel=3,
        )
        return "homography"
    # An affine-looking matrix could be either an affine (degrees) or a homography (metres) export
    return method


def load_georef(path: Union[str, Path]) -> GeoTransformer:
    """
    Load georeferencing parameters from a JSON file.

    Args:
        path: Path to JSON file exported from ORBIT

    Returns:
        GeoTransformer instance with source_info attribute containing
        project_file and image_path from the export

    Raises:
        FileNotFoundError: If file does not exist
        ValueError: If file format is invalid
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Georef file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return georef_from_data(data, path)


def georef_from_data(data: dict, path: Union[str, Path, None] = None) -> GeoTransformer:
    """GeoTransformer from a parsed georef document (e.g. one ORBIT is about to export).

    path is only used in messages.
    """
    path = Path(path) if path is not None else Path("<georef data>")
    # Validate format (optional, for files created by ORBIT 0.4.0+)
    file_format = data.get("format")
    if file_format and file_format != "ORBIT Georeferencing Data":
        raise ValueError(f"Unknown georef format: {file_format}")

    # Validate version
    version = data.get("version", "1.0")
    if not version.startswith("1."):
        raise ValueError(f"Unsupported georef format version: {version}")

    # Parse control points
    control_points = []
    for cp_data in data.get("control_points", []):
        control_points.append(ControlPoint(
            pixel_x=cp_data["pixel_x"],
            pixel_y=cp_data["pixel_y"],
            longitude=cp_data["longitude"],
            latitude=cp_data["latitude"],
            name=cp_data.get("name", ""),
            is_validation=cp_data.get("is_validation", False),
            altitude=cp_data.get("altitude_m", cp_data.get("altitude")),
        ))

    # Parse matrices
    transform_matrix = np.array(data["transformation_matrix"], dtype=np.float64)
    inverse_matrix = np.array(data["inverse_matrix"], dtype=np.float64)

    # Parse reference point
    ref_point = data["reference_point"]
    reference_lon = ref_point["longitude"]
    reference_lat = ref_point["latitude"]

    # Parse scale factors
    scale_factors = data.get("scale_factors", {})
    scale_x = scale_factors.get("x_meters_per_pixel", 1.0)
    scale_y = scale_factors.get("y_meters_per_pixel", 1.0)

    # Parse method
    method = _resolve_method(data.get("transform_method", "homography"), transform_matrix, path)

    # Parse proj_string (None for old files → backward compat)
    proj_string = data.get("proj_string")

    # Parse source info (new format with "source" key, or legacy with "image_path" at root)
    source_info = data.get("source", {})
    if not source_info and "image_path" in data:
        # Legacy format: image_path at root level
        source_info = {"image_path": data.get("image_path")}

    # Include creator info if present (ORBIT 0.4.0+)
    creator_info = data.get("creator")
    if creator_info:
        source_info["creator"] = creator_info

    return GeoTransformer(
        transform_matrix=transform_matrix,
        inverse_matrix=inverse_matrix,
        reference_lon=reference_lon,
        reference_lat=reference_lat,
        method=method,
        scale_x=scale_x,
        scale_y=scale_y,
        control_points=control_points,
        source_info=source_info,
        proj_string=proj_string,
        quality=_quality(data),
        camera_model=CameraModel.from_dict(data["camera_model"]) if data.get("camera_model") else None,
    )


def _quality(data: dict) -> dict:
    """Quality keys of a georef file; per-point residuals of training points as training_residuals_m."""
    quality = {key: data[key] for key in uncertainty.QUALITY_KEYS if key in data}
    residuals = [cp["residual_m"] for cp in data.get("control_points", [])
                 if "residual_m" in cp and not cp.get("is_validation", False)]
    if residuals:
        quality["training_residuals_m"] = residuals
    return quality


def save_georef(transformer: GeoTransformer, path: Union[str, Path]) -> None:
    """
    Save georeferencing parameters to a JSON file.

    Args:
        transformer: GeoTransformer instance to save
        path: Output path for JSON file
    """
    path = Path(path)

    # Extract creator from source_info if present, otherwise use orbit-georef as creator
    source_info = dict(transformer.source_info) if transformer.source_info else {}
    creator = source_info.pop("creator", {"application": "orbit-georef"})

    data = {
        "format": "ORBIT Georeferencing Data",
        "version": "1.1" if transformer.proj_string else "1.0",
        "creator": creator,
        "source": source_info,
        "transform_method": transformer.method,
        "control_points": [
            {
                "pixel_x": cp.pixel_x,
                "pixel_y": cp.pixel_y,
                "longitude": cp.longitude,
                "latitude": cp.latitude,
                "name": cp.name,
                "is_validation": cp.is_validation,
            }
            for cp in transformer.control_points
        ],
        "reference_point": {
            "longitude": transformer.reference_lon,
            "latitude": transformer.reference_lat,
        },
        "transformation_matrix": transformer.transform_matrix.tolist(),
        "inverse_matrix": transformer.inverse_matrix.tolist(),
        "scale_factors": {
            "x_meters_per_pixel": transformer._scale_x,
            "y_meters_per_pixel": transformer._scale_y,
        },
    }

    if transformer.proj_string:
        data["proj_string"] = transformer.proj_string
    for entry, cp in zip(data["control_points"], transformer.control_points):
        if cp.altitude is not None:
            entry["altitude_m"] = cp.altitude
    if transformer.camera_model is not None:
        data["camera_model"] = transformer.camera_model.to_dict()

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

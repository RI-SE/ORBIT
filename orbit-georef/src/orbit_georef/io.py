"""
I/O functions for orbit-georef.
"""

import json
from pathlib import Path
from typing import Union

import numpy as np

from .models import ControlPoint
from .transformer import GeoTransformer


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
    method = data.get("transform_method", "homography")

    # Parse source info (new format with "source" key, or legacy with "image_path" at root)
    source_info = data.get("source", {})
    if not source_info and "image_path" in data:
        # Legacy format: image_path at root level
        source_info = {"image_path": data.get("image_path")}

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
    )


def save_georef(transformer: GeoTransformer, path: Union[str, Path]) -> None:
    """
    Save georeferencing parameters to a JSON file.

    Args:
        transformer: GeoTransformer instance to save
        path: Output path for JSON file
    """
    path = Path(path)

    data = {
        "version": "1.0",
        "source": transformer.source_info if transformer.source_info else {},
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

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

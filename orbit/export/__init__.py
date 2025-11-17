"""
Export functionality for ORBIT.

This module handles coordinate transformation, curve fitting,
and OpenDrive XML generation.

Import Guidelines:
    Coordinate transformation utilities are re-exported from this module
    for convenience. You can import them from either location:

    - from export import CoordinateTransformer, create_transformer
      (Preferred for export-related code)

    - from utils.coordinate_transform import CoordinateTransformer, create_transformer
      (Preferred for non-export code, shows actual module location)

    Both are valid and functionally identical. The re-export exists because
    export operations are the primary consumers of coordinate transformation.
"""

# Re-export coordinate transformation from utils for convenience
# Actual implementation: utils/coordinate_transform.py
from utils import CoordinateTransformer, create_transformer, TransformMethod
from .curve_fitting import CurveFitter, GeometryElement, GeometryType, simplify_polyline
from .opendrive_writer import OpenDriveWriter, export_to_opendrive

__all__ = [
    'CoordinateTransformer',
    'create_transformer',
    'TransformMethod',
    'CurveFitter',
    'GeometryElement',
    'GeometryType',
    'simplify_polyline',
    'OpenDriveWriter',
    'export_to_opendrive'
]

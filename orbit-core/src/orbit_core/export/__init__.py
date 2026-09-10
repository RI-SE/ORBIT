"""
Export functionality for ORBIT.

This module handles coordinate transformation, curve fitting,
and OpenDrive XML generation.

Import Guidelines:
    Coordinate transformation utilities are re-exported from this module
    for convenience. You can import them from either location:

    - from export import CoordinateTransformer, create_transformer
      (Preferred for export-related code)

    - from orbit_core.utils.coordinate_transform import CoordinateTransformer, create_transformer
      (Preferred for non-export code, shows actual module location)

    Both are valid and functionally identical. The re-export exists because
    export operations are the primary consumers of coordinate transformation.
"""

# Re-export coordinate transformation from utils for convenience
# Actual implementation: utils/coordinate_transform.py
from orbit_core.utils import CoordinateTransformer, TransformMethod, create_transformer

from .curve_fitting import CurveFitter, GeometryElement, GeometryType, simplify_polyline
from .georef_export import build_georef_data, export_georeferencing
from .lane_builder import LaneBuilder, convert_road_mark_type
from .object_builder import ObjectBuilder
from .opendrive_writer import ExportOptions, OpenDriveWriter, export_to_opendrive, validate_opendrive_file
from .parking_builder import ParkingBuilder
from .reference_line_sampler import LanePolygonData, compute_lane_polygons, sample_reference_line
from .reference_validator import validate_references
from .signal_builder import SignalBuilder

__all__ = [
    'CoordinateTransformer',
    'create_transformer',
    'TransformMethod',
    'CurveFitter',
    'GeometryElement',
    'GeometryType',
    'simplify_polyline',
    'ExportOptions',
    'OpenDriveWriter',
    'export_to_opendrive',
    'validate_opendrive_file',
    'LaneBuilder',
    'convert_road_mark_type',
    'SignalBuilder',
    'ObjectBuilder',
    'ParkingBuilder',
    'export_georeferencing',
    'build_georef_data',
    'validate_references',
    'LayoutMaskExporter',
    'ExportMethod',
    'LanePolygonData',
    'sample_reference_line',
    'compute_lane_polygons',
]


# Layout mask export needs OpenCV, which is an optional extra. Resolve it on first
# access so `import orbit_core` works without it (PEP 562).
_LAZY = {"ExportMethod", "LayoutMaskExporter"}


def __getattr__(name):
    if name in _LAZY:
        from . import layout_mask_exporter

        return getattr(layout_mask_exporter, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(__all__) | _LAZY)

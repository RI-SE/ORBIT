"""Utility functions for ORBIT."""

from .coordinate_transform import (
    CoordinateTransformer,
    AffineTransformer,
    HomographyTransformer,
    TransformMethod,
    create_transformer,
    get_rms_error_meters
)
from .geometry import (
    calculate_perpendicular,
    offset_point,
    calculate_directional_scale,
)
from .enum_formatting import format_enum_name, format_snake_case
from .logging_config import setup_logging, get_logger
from .validators import ValidationResult, has_minimum_points, validate_point_list, is_valid_id

__all__ = [
    'CoordinateTransformer',
    'AffineTransformer',
    'HomographyTransformer',
    'TransformMethod',
    'create_transformer',
    'get_rms_error_meters',
    'calculate_perpendicular',
    'offset_point',
    'calculate_directional_scale',
    'format_enum_name',
    'format_snake_case',
    'setup_logging',
    'get_logger',
    'ValidationResult',
    'has_minimum_points',
    'validate_point_list',
    'is_valid_id',
]

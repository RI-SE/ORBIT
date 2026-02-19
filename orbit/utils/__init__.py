"""Utility functions for ORBIT."""

from .coordinate_transform import (
    AffineTransformer,
    CoordinateTransformer,
    HomographyTransformer,
    HybridTransformer,
    TransformMethod,
    create_transformer,
    get_rms_error_meters,
)
from .enum_formatting import format_enum_name, format_snake_case
from .geometry import (
    calculate_directional_scale,
    calculate_perpendicular,
    offset_point,
)
from .logging_config import get_logger, setup_logging
from .validators import ValidationResult, has_minimum_points, is_valid_id, validate_point_list

__all__ = [
    'CoordinateTransformer',
    'AffineTransformer',
    'HomographyTransformer',
    'HybridTransformer',
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

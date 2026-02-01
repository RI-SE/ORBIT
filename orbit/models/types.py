"""
Type aliases for common types used throughout ORBIT.

This module provides semantic type aliases that improve code readability
and maintainability by giving meaningful names to commonly used type patterns.
"""

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

# Geometric types
Point2D = Tuple[float, float]
"""A 2D point represented as (x, y)."""

PointList = List[Point2D]
"""A list of 2D points, typically representing a polyline or boundary."""

PixelCoordinate = Point2D
"""A pixel coordinate in image space (x, y)."""

GeoCoordinate = Tuple[float, float]
"""A geographic coordinate (latitude, longitude) in degrees."""

# Serialization types
JsonDict = Dict[str, Any]
"""A dictionary suitable for JSON serialization."""

# Entity identification
EntityID = str
"""Unique identifier for entities (roads, polylines, junctions, etc.)."""

if TYPE_CHECKING:
    from orbit.utils.coordinate_transform import CoordinateTransformer

# Optional types (common patterns)
OptionalTransformer = Optional['CoordinateTransformer']
"""Optional coordinate transformer reference."""

OptionalPointList = Optional[PointList]
"""Optional list of points."""

# Bounding box
BBox = Tuple[float, float, float, float]
"""Bounding box as (min_lat, min_lon, max_lat, max_lon) or (x_min, y_min, x_max, y_max)."""

# Scale factors
ScaleFactor = Tuple[float, float]
"""Scale factors as (scale_x, scale_y) in meters/pixel or similar units."""

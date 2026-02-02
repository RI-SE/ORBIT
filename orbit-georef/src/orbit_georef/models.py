"""
Data models for orbit-georef.
"""

from dataclasses import dataclass


@dataclass
class ControlPoint:
    """
    A georeferencing control point mapping pixel coordinates to geographic coordinates.

    Attributes:
        pixel_x: X coordinate in image pixels
        pixel_y: Y coordinate in image pixels
        longitude: Longitude in decimal degrees
        latitude: Latitude in decimal degrees
        name: Optional name for the control point
        is_validation: If True, point is used for validation only (GVP), not training (GCP)
    """
    pixel_x: float
    pixel_y: float
    longitude: float
    latitude: float
    name: str = ""
    is_validation: bool = False

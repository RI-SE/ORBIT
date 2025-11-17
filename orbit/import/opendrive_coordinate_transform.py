"""
OpenDrive coordinate transformation for ORBIT.

Handles conversion between OpenDrive metric coordinates and ORBIT pixel coordinates.
Supports three modes:
1. Georeferenced: Use OpenDrive geoReference + ORBIT control points
2. Synthetic viewport: Fixed scale without georeferencing
3. Auto-georeference: Create control points from OpenDrive geoReference
"""

from typing import List, Tuple, Optional
from dataclasses import dataclass
import math
import numpy as np


@dataclass
class TransformMode:
    """Coordinate transformation mode."""
    GEOREFERENCED = "georeferenced"
    SYNTHETIC = "synthetic"
    AUTO_GEOREFERENCE = "auto_georeference"


@dataclass
class TransformResult:
    """Result of coordinate transformation setup."""
    success: bool
    mode: str
    error_message: Optional[str] = None
    scale_pixels_per_meter: Optional[float] = None
    suggested_control_points: Optional[List[Tuple[float, float, float, float]]] = None  # (px, py, lon, lat)


class OpenDriveCoordinateTransform:
    """Transforms OpenDrive metric coordinates to ORBIT pixel coordinates."""

    def __init__(
        self,
        image_width: int,
        image_height: int,
        orbit_transformer = None,  # CoordinateTransformer from export module
        opendrive_geo_reference: Optional[str] = None,
        scale_pixels_per_meter: float = 10.0
    ):
        """
        Initialize coordinate transformer.

        Args:
            image_width: Image width in pixels
            image_height: Image height in pixels
            orbit_transformer: ORBIT CoordinateTransformer (if available)
            opendrive_geo_reference: OpenDrive geoReference PROJ4 string (if available)
            scale_pixels_per_meter: Default scale for synthetic mode
        """
        self.image_width = image_width
        self.image_height = image_height
        self.orbit_transformer = orbit_transformer
        self.opendrive_geo_reference = opendrive_geo_reference
        self.scale_pixels_per_meter = scale_pixels_per_meter

        # Transformation parameters
        self.mode = None
        self.offset_x = 0.0  # Offset to apply to metric coords before scaling
        self.offset_y = 0.0
        self.center_pixel_x = image_width / 2
        self.center_pixel_y = image_height / 2

        # For synthetic mode: bounds of OpenDrive data
        self.data_min_x = None
        self.data_max_x = None
        self.data_min_y = None
        self.data_max_y = None

    def setup_transform(
        self,
        metric_points: List[Tuple[float, float]]
    ) -> TransformResult:
        """
        Setup coordinate transformation based on available data.

        Args:
            metric_points: Sample points from OpenDrive in meters
                          (used to determine bounds for synthetic mode)

        Returns:
            TransformResult indicating success and mode used
        """
        # Calculate bounds of metric data
        if metric_points:
            xs = [p[0] for p in metric_points]
            ys = [p[1] for p in metric_points]
            self.data_min_x = min(xs)
            self.data_max_x = max(xs)
            self.data_min_y = min(ys)
            self.data_max_y = max(ys)

        # Mode 1: Georeferenced (both OpenDrive and ORBIT have georeferencing)
        if self.opendrive_geo_reference and self.orbit_transformer:
            self.mode = TransformMode.GEOREFERENCED
            return TransformResult(
                success=True,
                mode=TransformMode.GEOREFERENCED
            )

        # Mode 3: Auto-georeference (OpenDrive has georef, ORBIT doesn't)
        if self.opendrive_geo_reference and not self.orbit_transformer:
            self.mode = TransformMode.AUTO_GEOREFERENCE

            # Generate suggested control points
            # Create 3-4 control points at corners of OpenDrive data
            suggested_points = self._generate_suggested_control_points()

            return TransformResult(
                success=False,  # Needs user action
                mode=TransformMode.AUTO_GEOREFERENCE,
                error_message="OpenDrive file has georeferencing but ORBIT project doesn't. "
                             "Would you like to auto-create control points?",
                suggested_control_points=suggested_points
            )

        # Mode 2: Synthetic viewport (no georeferencing)
        self.mode = TransformMode.SYNTHETIC

        # Calculate offsets to center data in image
        if metric_points:
            data_center_x = (self.data_min_x + self.data_max_x) / 2
            data_center_y = (self.data_min_y + self.data_max_y) / 2

            self.offset_x = -data_center_x
            self.offset_y = -data_center_y

            # Optionally adjust scale to fit data in image
            data_width = self.data_max_x - self.data_min_x
            data_height = self.data_max_y - self.data_min_y

            if data_width > 0 and data_height > 0:
                # Calculate scale to fit with 10% margin
                scale_x = (self.image_width * 0.9) / data_width
                scale_y = (self.image_height * 0.9) / data_height
                self.scale_pixels_per_meter = min(scale_x, scale_y)

        return TransformResult(
            success=True,
            mode=TransformMode.SYNTHETIC,
            scale_pixels_per_meter=self.scale_pixels_per_meter
        )

    def metric_to_pixel(self, x_meters: float, y_meters: float) -> Tuple[float, float]:
        """
        Convert metric coordinates to pixel coordinates.

        Args:
            x_meters: X coordinate in meters (OpenDrive)
            y_meters: Y coordinate in meters (OpenDrive)

        Returns:
            Tuple of (pixel_x, pixel_y)
        """
        if self.mode == TransformMode.GEOREFERENCED:
            return self._metric_to_pixel_georeferenced(x_meters, y_meters)
        else:  # SYNTHETIC or AUTO_GEOREFERENCE fallback
            return self._metric_to_pixel_synthetic(x_meters, y_meters)

    def _metric_to_pixel_georeferenced(
        self,
        x_meters: float,
        y_meters: float
    ) -> Tuple[float, float]:
        """
        Convert metric to pixel using georeferencing.

        Process: metric → lat/lon → pixel
        """
        # Convert metric to lat/lon using OpenDrive geoReference
        lon, lat = self._metric_to_latlon(x_meters, y_meters)

        # Convert lat/lon to pixel using ORBIT transformer
        if self.orbit_transformer:
            # Use inverse transformation (geo to pixel)
            pixel_x, pixel_y = self.orbit_transformer.geo_to_pixel(lon, lat)
            return (pixel_x, pixel_y)
        else:
            # Fallback to synthetic
            return self._metric_to_pixel_synthetic(x_meters, y_meters)

    def _metric_to_pixel_synthetic(
        self,
        x_meters: float,
        y_meters: float
    ) -> Tuple[float, float]:
        """
        Convert metric to pixel using synthetic viewport.

        Simply scales and centers the data in the image.
        """
        # Apply offset to center data
        x_centered = x_meters + self.offset_x
        y_centered = y_meters + self.offset_y

        # Scale to pixels (note: OpenDrive Y is typically "north", image Y is "down")
        # So we need to flip Y axis
        pixel_x = self.center_pixel_x + (x_centered * self.scale_pixels_per_meter)
        pixel_y = self.center_pixel_y - (y_centered * self.scale_pixels_per_meter)

        return (pixel_x, pixel_y)

    def _metric_to_latlon(self, x_meters: float, y_meters: float) -> Tuple[float, float]:
        """
        Convert OpenDrive metric coordinates to lat/lon using geoReference.

        Args:
            x_meters: X coordinate in meters
            y_meters: Y coordinate in meters

        Returns:
            Tuple of (longitude, latitude) in decimal degrees
        """
        # Parse PROJ4 string and use pyproj if available
        try:
            from pyproj import Proj, transform

            # Create projection from geoReference
            proj = Proj(self.opendrive_geo_reference)

            # Convert to lat/lon (WGS84)
            lon, lat = proj(x_meters, y_meters, inverse=True)
            return (lon, lat)

        except ImportError:
            # Fallback: Simple approximation for local coordinates
            # Assume geoReference is a local metric projection near some origin
            # This is a rough approximation and should be avoided if possible

            # Try to extract origin from PROJ4 string
            origin_lat, origin_lon = self._extract_origin_from_proj4()

            if origin_lat and origin_lon:
                # Simple approximation: meters to degrees
                # At mid-latitudes: ~111000 m per degree latitude, ~111000*cos(lat) m per degree longitude
                meters_per_degree_lat = 111000.0
                meters_per_degree_lon = 111000.0 * math.cos(math.radians(origin_lat))

                lat = origin_lat + (y_meters / meters_per_degree_lat)
                lon = origin_lon + (x_meters / meters_per_degree_lon)

                return (lon, lat)

            # Last resort: return metric coords as if they were degrees (will be wrong)
            return (x_meters, y_meters)

    def _extract_origin_from_proj4(self) -> Tuple[Optional[float], Optional[float]]:
        """
        Extract origin lat/lon from PROJ4 string.

        Returns:
            Tuple of (latitude, longitude) or (None, None) if not found
        """
        if not self.opendrive_geo_reference:
            return (None, None)

        # Look for +lat_0 and +lon_0 parameters
        lat = None
        lon = None

        parts = self.opendrive_geo_reference.split()
        for part in parts:
            if part.startswith('+lat_0='):
                try:
                    lat = float(part.split('=')[1])
                except ValueError:
                    pass
            elif part.startswith('+lon_0='):
                try:
                    lon = float(part.split('=')[1])
                except ValueError:
                    pass

        return (lat, lon)

    def _generate_suggested_control_points(
        self
    ) -> List[Tuple[float, float, float, float]]:
        """
        Generate suggested control points for auto-georeferencing.

        Returns:
            List of (pixel_x, pixel_y, lon, lat) tuples
        """
        if not self.data_min_x or not self.data_max_x:
            return []

        # Create 4 control points at corners of data bounds
        corners_metric = [
            (self.data_min_x, self.data_min_y),  # SW corner
            (self.data_max_x, self.data_min_y),  # SE corner
            (self.data_max_x, self.data_max_y),  # NE corner
            (self.data_min_x, self.data_max_y),  # NW corner
        ]

        # Calculate corresponding pixel positions (using synthetic transform)
        # First setup a temporary synthetic transform
        data_center_x = (self.data_min_x + self.data_max_x) / 2
        data_center_y = (self.data_min_y + self.data_max_y) / 2

        data_width = self.data_max_x - self.data_min_x
        data_height = self.data_max_y - self.data_min_y

        scale_x = (self.image_width * 0.9) / data_width if data_width > 0 else 10.0
        scale_y = (self.image_height * 0.9) / data_height if data_height > 0 else 10.0
        scale = min(scale_x, scale_y)

        control_points = []
        for x_m, y_m in corners_metric:
            # Convert to pixel
            x_centered = x_m - data_center_x
            y_centered = y_m - data_center_y

            pixel_x = (self.image_width / 2) + (x_centered * scale)
            pixel_y = (self.image_height / 2) - (y_centered * scale)

            # Convert to lat/lon
            lon, lat = self._metric_to_latlon(x_m, y_m)

            control_points.append((pixel_x, pixel_y, lon, lat))

        return control_points


def batch_metric_to_pixel(
    points_metric: List[Tuple[float, float]],
    transformer: OpenDriveCoordinateTransform
) -> List[Tuple[float, float]]:
    """
    Convert a list of metric points to pixel coordinates.

    Args:
        points_metric: List of (x, y) coordinates in meters
        transformer: Configured OpenDriveCoordinateTransform

    Returns:
        List of (x, y) coordinates in pixels
    """
    points_pixel = []
    for x_m, y_m in points_metric:
        px, py = transformer.metric_to_pixel(x_m, y_m)
        points_pixel.append((px, py))
    return points_pixel

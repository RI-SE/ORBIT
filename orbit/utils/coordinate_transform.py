"""
Coordinate transformation for ORBIT.

Converts between pixel coordinates and real-world geographic coordinates
using control points. Supports both affine and homography transformations.

Affine transformation (6 parameters):
- Best for orthophotos, satellite imagery (nadir view)
- Requires minimum 3 control points
- Preserves parallel lines
- Simpler and more stable with few points

Homography transformation (8 parameters):
- Best for oblique drone imagery with camera tilt
- Requires minimum 4 control points
- Handles perspective distortion
- Uses DLT (Direct Linear Transform) with SVD
"""

import math
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple, Union

import numpy as np
from pyproj import Proj

from .logging_config import get_logger

if TYPE_CHECKING:
    from orbit.models.project import ControlPoint

logger = get_logger(__name__)


class TransformMethod(Enum):
    """Transformation method for georeferencing."""
    AFFINE = auto()
    HOMOGRAPHY = auto()


@dataclass
class TransformAdjustment:
    """
    Stores incremental adjustments to apply to coordinate transformation.

    Used for interactive fine-tuning of georeferencing when OSM roads
    don't perfectly align with the aerial image.
    """
    translation_x: float = 0.0  # Pixel offset in X direction
    translation_y: float = 0.0  # Pixel offset in Y direction
    rotation: float = 0.0       # Rotation in degrees (positive = counter-clockwise)
    scale_x: float = 1.0        # Scale factor in X direction
    scale_y: float = 1.0        # Scale factor in Y direction
    shear_x: float = 0.0        # Horizontal shear (X shift per unit Y from pivot)
    shear_y: float = 0.0        # Vertical shear (Y shift per unit X from pivot)
    pivot_x: float = 0.0        # Pivot point X for rotation/scale (pixels)
    pivot_y: float = 0.0        # Pivot point Y for rotation/scale (pixels)

    def is_identity(self) -> bool:
        """Check if adjustment is effectively no change."""
        return (
            abs(self.translation_x) < 1e-6 and
            abs(self.translation_y) < 1e-6 and
            abs(self.rotation) < 1e-6 and
            abs(self.scale_x - 1.0) < 1e-6 and
            abs(self.scale_y - 1.0) < 1e-6 and
            abs(self.shear_x) < 1e-6 and
            abs(self.shear_y) < 1e-6
        )

    def get_adjustment_matrix(self) -> np.ndarray:
        """
        Build 3x3 transformation matrix for this adjustment.

        The adjustment is applied in this order:
        1. Translate to pivot point
        2. Shear
        3. Scale
        4. Rotate
        5. Translate back from pivot
        6. Apply translation offset

        Returns:
            3x3 homogeneous transformation matrix
        """
        # Translation to pivot
        T_to_pivot = np.array([
            [1, 0, -self.pivot_x],
            [0, 1, -self.pivot_y],
            [0, 0, 1]
        ], dtype=np.float64)

        # Shear matrix (applied first, before scale/rotate)
        H = np.array([
            [1, self.shear_x, 0],
            [self.shear_y, 1, 0],
            [0, 0, 1]
        ], dtype=np.float64)

        # Scale matrix
        S = np.array([
            [self.scale_x, 0, 0],
            [0, self.scale_y, 0],
            [0, 0, 1]
        ], dtype=np.float64)

        # Rotation matrix (positive = counter-clockwise)
        theta = math.radians(self.rotation)
        cos_t, sin_t = math.cos(theta), math.sin(theta)
        R = np.array([
            [cos_t, -sin_t, 0],
            [sin_t, cos_t, 0],
            [0, 0, 1]
        ], dtype=np.float64)

        # Translation back from pivot
        T_from_pivot = np.array([
            [1, 0, self.pivot_x],
            [0, 1, self.pivot_y],
            [0, 0, 1]
        ], dtype=np.float64)

        # Translation offset
        T_offset = np.array([
            [1, 0, self.translation_x],
            [0, 1, self.translation_y],
            [0, 0, 1]
        ], dtype=np.float64)

        # Compose: offset * from_pivot * R * S * H * to_pivot
        return T_offset @ T_from_pivot @ R @ S @ H @ T_to_pivot

    def apply_to_point(self, x: float, y: float) -> Tuple[float, float]:
        """
        Apply adjustment to a single point.

        Args:
            x, y: Input coordinates (pixels)

        Returns:
            Adjusted (x, y) coordinates
        """
        M = self.get_adjustment_matrix()
        point = np.array([x, y, 1.0])
        result = M @ point
        return result[0], result[1]

    def apply_inverse_to_point(self, x: float, y: float) -> Tuple[float, float]:
        """
        Apply inverse adjustment to a single point.

        Args:
            x, y: Adjusted coordinates (pixels)

        Returns:
            Original (x, y) coordinates before adjustment
        """
        M = self.get_adjustment_matrix()
        M_inv = np.linalg.inv(M)
        point = np.array([x, y, 1.0])
        result = M_inv @ point
        return result[0], result[1]

    def copy(self) -> 'TransformAdjustment':
        """Create a copy of this adjustment."""
        return TransformAdjustment(
            translation_x=self.translation_x,
            translation_y=self.translation_y,
            rotation=self.rotation,
            scale_x=self.scale_x,
            scale_y=self.scale_y,
            shear_x=self.shear_x,
            shear_y=self.shear_y,
            pivot_x=self.pivot_x,
            pivot_y=self.pivot_y
        )

    def to_dict(self) -> Dict[str, float]:
        """Serialize to dictionary for JSON persistence."""
        return {
            'translation_x': self.translation_x,
            'translation_y': self.translation_y,
            'rotation': self.rotation,
            'scale_x': self.scale_x,
            'scale_y': self.scale_y,
            'shear_x': self.shear_x,
            'shear_y': self.shear_y,
            'pivot_x': self.pivot_x,
            'pivot_y': self.pivot_y,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> 'TransformAdjustment':
        """Deserialize from dictionary."""
        return cls(
            translation_x=data.get('translation_x', 0.0),
            translation_y=data.get('translation_y', 0.0),
            rotation=data.get('rotation', 0.0),
            scale_x=data.get('scale_x', 1.0),
            scale_y=data.get('scale_y', 1.0),
            shear_x=data.get('shear_x', 0.0),
            shear_y=data.get('shear_y', 0.0),
            pivot_x=data.get('pivot_x', 0.0),
            pivot_y=data.get('pivot_y', 0.0),
        )

    def reset(self):
        """Reset all adjustments to identity."""
        self.translation_x = 0.0
        self.translation_y = 0.0
        self.rotation = 0.0
        self.scale_x = 1.0
        self.scale_y = 1.0
        self.shear_x = 0.0
        self.shear_y = 0.0
        # Keep pivot point


class CoordinateTransformer:
    """
    Base class for coordinate transformers.

    Handles coordinate transformations between pixel and geographic coordinates.
    Subclasses implement specific transformation methods (affine, homography).
    """

    def __init__(self, control_points: List['ControlPoint'], use_validation: bool = True,
                 export_proj_string: Optional[str] = None):
        """
        Initialize transformer with control points.

        Args:
            control_points: List of control points
            use_validation: If True, separate validation points from training
            export_proj_string: If set, latlon_to_meters/meters_to_latlon use this
                pyproj projection instead of equirectangular approximation.
                Used for export to ensure coordinates match the declared geoReference.

        Raises:
            ValueError: If insufficient control points provided
        """
        self.all_control_points = control_points
        self.use_validation = use_validation

        # Export projection (pyproj-based conversion instead of equirectangular)
        self._export_proj_string: Optional[str] = export_proj_string
        self._export_proj: Optional[Proj] = None

        # Separate training (GCP) and validation (GVP) points
        if use_validation:
            self.training_points = [cp for cp in control_points if not getattr(cp, 'is_validation', False)]
            self.validation_points = [cp for cp in control_points if getattr(cp, 'is_validation', False)]
        else:
            self.training_points = control_points
            self.validation_points = []

        # Transformation matrices
        self.transform_matrix: Optional[np.ndarray] = None
        self.inverse_matrix: Optional[np.ndarray] = None

        # Validation metrics
        self.reprojection_error: Dict = {}
        self.validation_error: Dict = {}

        # Reference point for metric conversion
        self.reference_lat: Optional[float] = None
        self.reference_lon: Optional[float] = None

        # Interactive adjustment for fine-tuning alignment
        self.adjustment: Optional[TransformAdjustment] = None

    def set_adjustment(self, adjustment: TransformAdjustment):
        """
        Set adjustment to apply to all transformations.

        The adjustment modifies the geo→pixel direction, effectively
        moving where geographic coordinates appear on the image.

        Args:
            adjustment: TransformAdjustment to apply
        """
        self.adjustment = adjustment

    def clear_adjustment(self):
        """Remove any adjustment, restoring original transformation."""
        self.adjustment = None

    def has_adjustment(self) -> bool:
        """Check if an adjustment is currently applied."""
        return self.adjustment is not None and not self.adjustment.is_identity()

    def _set_reference_point(self):
        """Set reference point as mean of all control points.

        Also initializes the pyproj Proj if export_proj_string was provided.
        """
        if not self.all_control_points:
            return
        self.reference_lat = np.mean([cp.latitude for cp in self.all_control_points])
        self.reference_lon = np.mean([cp.longitude for cp in self.all_control_points])

        if self._export_proj_string:
            self._export_proj = Proj(self._export_proj_string)

    def latlon_to_meters(self, lat: float, lon: float) -> Tuple[float, float]:
        """
        Convert lat/lon to metric coordinates.

        When export_proj_string is set, uses pyproj for accurate projection.
        Otherwise uses equirectangular approximation (suitable for areas <100km).

        Args:
            lat: Latitude in decimal degrees
            lon: Longitude in decimal degrees

        Returns:
            Tuple of (east, north) in meters
        """
        if self._export_proj is not None:
            return self._export_proj(lon, lat)

        if self.reference_lat is None or self.reference_lon is None:
            raise ValueError("Reference point not set. Call compute transformation first.")

        R = 6371000.0  # Earth radius in meters

        lat_rad = math.radians(lat)
        lon_rad = math.radians(lon)
        ref_lat_rad = math.radians(self.reference_lat)
        ref_lon_rad = math.radians(self.reference_lon)

        east = R * (lon_rad - ref_lon_rad) * math.cos(ref_lat_rad)
        north = R * (lat_rad - ref_lat_rad)

        return east, north

    def meters_to_latlon(self, east: float, north: float) -> Tuple[float, float]:
        """
        Convert metric coordinates back to lat/lon.

        When export_proj_string is set, uses pyproj inverse projection.
        Otherwise uses equirectangular approximation.

        Args:
            east: East coordinate in meters
            north: North coordinate in meters

        Returns:
            Tuple of (latitude, longitude) in decimal degrees
        """
        if self._export_proj is not None:
            lon, lat = self._export_proj(east, north, inverse=True)
            return lat, lon

        if self.reference_lat is None or self.reference_lon is None:
            raise ValueError("Reference point not set. Call compute transformation first.")

        R = 6371000.0
        ref_lat_rad = math.radians(self.reference_lat)
        ref_lon_rad = math.radians(self.reference_lon)

        lat_rad = ref_lat_rad + (north / R)
        lon_rad = ref_lon_rad + (east / (R * math.cos(ref_lat_rad)))

        return math.degrees(lat_rad), math.degrees(lon_rad)

    def compute_transformation(self):
        """Compute transformation matrix. Must be implemented by subclass."""
        raise NotImplementedError("Subclass must implement compute_transformation")

    def pixel_to_geo(self, pixel_x: float, pixel_y: float) -> Tuple[float, float]:
        """
        Convert pixel coordinates to geographic coordinates (longitude, latitude).

        Args:
            pixel_x: X coordinate in pixels
            pixel_y: Y coordinate in pixels

        Returns:
            Tuple of (longitude, latitude) in decimal degrees
        """
        raise NotImplementedError("Subclass must implement pixel_to_geo")

    def geo_to_pixel(self, longitude: float, latitude: float) -> Tuple[float, float]:
        """
        Convert geographic coordinates to pixel coordinates.

        Args:
            longitude: Longitude in decimal degrees
            latitude: Latitude in decimal degrees

        Returns:
            Tuple of (pixel_x, pixel_y)
        """
        raise NotImplementedError("Subclass must implement geo_to_pixel")

    def pixel_to_meters(self, pixel_x: float, pixel_y: float) -> Tuple[float, float]:
        """
        Convert pixel coordinates to local metric coordinates (meters).

        Uses the center of the control points as the local origin (0, 0).

        Args:
            pixel_x: X coordinate in pixels
            pixel_y: Y coordinate in pixels

        Returns:
            Tuple of (x_meters, y_meters) in local metric coordinate system
        """
        # First convert to geographic coordinates
        lon, lat = self.pixel_to_geo(pixel_x, pixel_y)

        # Convert to meters
        x_m, y_m = self.latlon_to_meters(lat, lon)

        return x_m, y_m

    def meters_to_pixel(self, x_meters: float, y_meters: float) -> Tuple[float, float]:
        """
        Convert local metric coordinates (meters) to pixel coordinates.

        Args:
            x_meters: X coordinate in meters (east)
            y_meters: Y coordinate in meters (north)

        Returns:
            Tuple of (pixel_x, pixel_y)
        """
        # Convert meters to lat/lon
        lat, lon = self.meters_to_latlon(x_meters, y_meters)

        # Convert lat/lon to pixels
        return self.geo_to_pixel(lon, lat)

    def pixels_to_geo_batch(self, pixels: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        """Convert multiple pixel coordinates to geographic coordinates."""
        return [self.pixel_to_geo(x, y) for x, y in pixels]

    def pixels_to_meters_batch(self, pixels: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        """Convert multiple pixel coordinates to local metric coordinates."""
        return [self.pixel_to_meters(x, y) for x, y in pixels]

    def meters_to_pixels_batch(self, meters: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        """Convert multiple local metric coordinates to pixel coordinates."""
        return [self.meters_to_pixel(x, y) for x, y in meters]

    def transform_heading(self, pixel_x: float, pixel_y: float, heading_pixels: float) -> float:
        """
        Transform a heading from pixel coordinates to meter coordinates.

        The heading is transformed by taking a small step in the heading direction
        in pixel space, transforming both points to meters, and calculating the
        new heading from the transformed direction.

        Args:
            pixel_x, pixel_y: Position in pixels where heading is measured
            heading_pixels: Heading in pixel coordinates (radians)

        Returns:
            Heading in meter coordinates (radians)
        """
        # Take a small step in the heading direction (in pixels)
        delta = 1.0  # 1 pixel step
        dx = delta * math.cos(heading_pixels)
        dy = delta * math.sin(heading_pixels)

        # Transform both the start point and the offset point to meters
        x1, y1 = self.pixel_to_meters(pixel_x, pixel_y)
        x2, y2 = self.pixel_to_meters(pixel_x + dx, pixel_y + dy)

        # Calculate heading from the transformed direction
        return math.atan2(y2 - y1, x2 - x1)

    def get_scale_factor(self) -> Tuple[float, float]:
        """
        Get the scale factors (meters per pixel) in x and y directions.

        Returns:
            Tuple of (scale_x, scale_y) in meters per pixel
        """
        raise NotImplementedError("Subclass must implement get_scale_factor")

    def compute_reprojection_error(self) -> Dict:
        """
        Compute reprojection error for training points (GCPs).

        Measures how well the transformation fits the training data by
        transforming pixel -> geo -> pixel and comparing.

        Returns:
            Dictionary with error metrics
        """
        if not self.training_points:
            return {}

        errors_pixels = []
        errors_meters = []
        per_point_errors = []

        for cp in self.training_points:
            # Forward: pixel -> geo
            lon_calc, lat_calc = self.pixel_to_geo(cp.pixel_x, cp.pixel_y)

            # Backward: geo -> pixel
            px_calc, py_calc = self.geo_to_pixel(lon_calc, lat_calc)

            # Pixel error
            error_px = math.sqrt((px_calc - cp.pixel_x)**2 + (py_calc - cp.pixel_y)**2)
            errors_pixels.append(error_px)

            # Calculate error in metric space (more robust than geographic distance)
            # This correctly measures transformation accuracy
            pred_mx, pred_my = self.pixel_to_meters(cp.pixel_x, cp.pixel_y)
            actual_mx, actual_my = self.latlon_to_meters(cp.latitude, cp.longitude)
            error_m = math.sqrt((pred_mx - actual_mx)**2 + (pred_my - actual_my)**2)
            errors_meters.append(error_m)

            per_point_errors.append({
                'name': cp.name or f"GCP {self.training_points.index(cp) + 1}",
                'error_pixels': error_px,
                'error_meters': error_m
            })

        self.reprojection_error = {
            'rmse_pixels': math.sqrt(np.mean(np.array(errors_pixels)**2)),
            'mean_error_pixels': np.mean(errors_pixels),
            'max_error_pixels': np.max(errors_pixels),
            'rmse_meters': math.sqrt(np.mean(np.array(errors_meters)**2)),
            'mean_error_meters': np.mean(errors_meters),
            'max_error_meters': np.max(errors_meters),
            'per_point_errors': per_point_errors
        }

        return self.reprojection_error

    def compute_validation_error(self) -> Dict:
        """
        Compute validation error for validation points (GVPs).

        Measures transformation accuracy on unseen data by transforming
        pixel -> geo and comparing to known geo coordinates.

        Returns:
            Dictionary with error metrics (empty if no validation points)
        """
        if not self.validation_points:
            return {}

        errors_pixels = []
        errors_meters = []
        per_point_errors = []

        for cp in self.validation_points:
            # Transform pixel to geo
            lon_calc, lat_calc = self.pixel_to_geo(cp.pixel_x, cp.pixel_y)

            # Calculate error in metric space (correctly measures transformation accuracy)
            pred_mx, pred_my = self.pixel_to_meters(cp.pixel_x, cp.pixel_y)
            actual_mx, actual_my = self.latlon_to_meters(cp.latitude, cp.longitude)
            error_m = math.sqrt((pred_mx - actual_mx)**2 + (pred_my - actual_my)**2)
            errors_meters.append(error_m)

            # Calculate pixel error by transforming known geo back to pixels
            px_calc, py_calc = self.geo_to_pixel(cp.longitude, cp.latitude)
            error_px = math.sqrt((px_calc - cp.pixel_x)**2 + (py_calc - cp.pixel_y)**2)
            errors_pixels.append(error_px)

            per_point_errors.append({
                'name': cp.name or f"GVP {self.validation_points.index(cp) + 1}",
                'error_pixels': error_px,
                'error_meters': error_m
            })

        self.validation_error = {
            'rmse_pixels': math.sqrt(np.mean(np.array(errors_pixels)**2)),
            'mean_error_pixels': np.mean(errors_pixels),
            'max_error_pixels': np.max(errors_pixels),
            'rmse_meters': math.sqrt(np.mean(np.array(errors_meters)**2)),
            'mean_error_meters': np.mean(errors_meters),
            'max_error_meters': np.max(errors_meters),
            'per_point_errors': per_point_errors
        }

        return self.validation_error

    def get_metric_origin(self) -> Tuple[float, float]:
        """
        Get the geographic coordinates of the local metric origin.

        Returns:
            Tuple of (longitude, latitude) in decimal degrees
        """
        return self.reference_lon, self.reference_lat

    def get_projection_string(self) -> str:
        """
        Get the PROJ4 projection string for the local metric coordinate system.

        Creates a Transverse Mercator projection centered on the control points.

        Returns:
            PROJ4 projection string
        """
        proj_string = (
            f"+proj=tmerc "
            f"+lat_0={self.reference_lat:.10f} "
            f"+lon_0={self.reference_lon:.10f} "
            f"+k=1 "
            f"+x_0=0 "
            f"+y_0=0 "
            f"+datum=WGS84 "
            f"+units=m "
            f"+no_defs"
        )
        return proj_string

    def get_utm_projection_string(self) -> str:
        """
        Get UTM projection string calculated from reference coordinates.

        UTM zones are 6 degrees wide, numbered 1-60 from 180°W.
        Zone = floor((lon + 180) / 6) + 1

        Returns:
            PROJ4 UTM projection string (e.g., "+proj=utm +zone=33 ...")
        """
        # Calculate UTM zone from longitude
        zone = int((self.reference_lon + 180) / 6) + 1

        # Determine hemisphere
        hemisphere = "+north" if self.reference_lat >= 0 else "+south"

        proj_string = (
            f"+proj=utm "
            f"+zone={zone} "
            f"{hemisphere} "
            f"+ellps=WGS84 "
            f"+datum=WGS84 "
            f"+units=m "
            f"+no_defs"
        )
        return proj_string

    def get_utm_zone(self) -> int:
        """
        Get the UTM zone number for the reference coordinates.

        Returns:
            UTM zone number (1-60)
        """
        return int((self.reference_lon + 180) / 6) + 1

    def get_transformation_info(self) -> Dict:
        """
        Get information about the transformation for display/logging.

        Returns:
            Dictionary with transformation parameters and quality metrics
        """
        info = {
            'method': self.__class__.__name__,
            'num_training_points': len(self.training_points),
            'num_validation_points': len(self.validation_points),
            'reference_latitude': self.reference_lat,
            'reference_longitude': self.reference_lon,
        }

        if self.reprojection_error:
            info['reprojection_error'] = self.reprojection_error

        if self.validation_error:
            info['validation_error'] = self.validation_error

        scale_x, scale_y = self.get_scale_factor()
        info['scale_x_meters_per_pixel'] = scale_x
        info['scale_y_meters_per_pixel'] = scale_y

        return info


class AffineTransformer(CoordinateTransformer):
    """
    Affine transformation for georeferencing.

    Best for orthophotos and satellite imagery (nadir view).
    Requires minimum 3 control points.
    Uses least-squares fitting for 6 affine parameters.
    """

    def __init__(self, control_points: List['ControlPoint'], use_validation: bool = True,
                 export_proj_string: Optional[str] = None):
        super().__init__(control_points, use_validation, export_proj_string=export_proj_string)

        if len(self.training_points) < 3:
            raise ValueError("Affine transformation requires at least 3 training control points")

        self._set_reference_point()
        self.compute_transformation()

    def compute_transformation(self):
        """
        Compute affine transformation matrix from control points.

        Affine transformation: [lon, lat, 1] = M * [x, y, 1]
        Where M is a 3x3 matrix with 6 degrees of freedom.
        """
        n = len(self.training_points)

        # Build matrices for least-squares solution
        A = np.zeros((n * 2, 6))
        B = np.zeros(n * 2)

        for i, cp in enumerate(self.training_points):
            # For longitude
            A[2 * i, 0] = cp.pixel_x
            A[2 * i, 1] = cp.pixel_y
            A[2 * i, 2] = 1
            B[2 * i] = cp.longitude

            # For latitude
            A[2 * i + 1, 3] = cp.pixel_x
            A[2 * i + 1, 4] = cp.pixel_y
            A[2 * i + 1, 5] = 1
            B[2 * i + 1] = cp.latitude

        # Solve using least-squares
        coeffs, residuals, rank, s = np.linalg.lstsq(A, B, rcond=None)

        # Build transformation matrix
        self.transform_matrix = np.array([
            [coeffs[0], coeffs[1], coeffs[2]],
            [coeffs[3], coeffs[4], coeffs[5]],
            [0, 0, 1]
        ])

        # Compute inverse transformation
        try:
            linear_part = self.transform_matrix[:2, :2]
            linear_inv = np.linalg.inv(linear_part)

            translation = self.transform_matrix[:2, 2]
            translation_inv = -linear_inv @ translation

            self.inverse_matrix = np.array([
                [linear_inv[0, 0], linear_inv[0, 1], translation_inv[0]],
                [linear_inv[1, 0], linear_inv[1, 1], translation_inv[1]],
                [0, 0, 1]
            ])
        except np.linalg.LinAlgError:
            raise ValueError("Transformation matrix is singular - check control points")

        # Compute error metrics
        self.compute_reprojection_error()
        if self.validation_points:
            self.compute_validation_error()

    def pixel_to_geo(self, pixel_x: float, pixel_y: float) -> Tuple[float, float]:
        """Convert pixel coordinates to geographic coordinates."""
        if self.transform_matrix is None:
            raise RuntimeError("Transformation not initialized")

        point = np.array([pixel_x, pixel_y, 1.0])
        result = self.transform_matrix @ point
        return result[0], result[1]  # lon, lat

    def geo_to_pixel(self, longitude: float, latitude: float) -> Tuple[float, float]:
        """Convert geographic coordinates to pixel coordinates.

        If an adjustment is set, applies it after the base transformation.
        """
        if self.inverse_matrix is None:
            raise RuntimeError("Transformation not initialized")

        point = np.array([longitude, latitude, 1.0])
        result = self.inverse_matrix @ point
        pixel_x, pixel_y = result[0], result[1]

        # Apply adjustment if set
        if self.adjustment is not None:
            pixel_x, pixel_y = self.adjustment.apply_to_point(pixel_x, pixel_y)

        return pixel_x, pixel_y

    def geo_to_pixel_unadjusted(self, longitude: float, latitude: float) -> Tuple[float, float]:
        """Convert geographic coordinates to pixel coordinates without adjustment."""
        if self.inverse_matrix is None:
            raise RuntimeError("Transformation not initialized")

        point = np.array([longitude, latitude, 1.0])
        result = self.inverse_matrix @ point
        return result[0], result[1]

    def get_scale_factor(self) -> Tuple[float, float]:
        """Get the scale factors (meters per pixel) in x and y directions."""
        # Extract the linear transformation part
        a0, a1 = self.transform_matrix[0, 0], self.transform_matrix[0, 1]
        a3, a4 = self.transform_matrix[1, 0], self.transform_matrix[1, 1]

        # Convert degrees per pixel to meters per pixel
        meters_per_degree_lat = 111000
        meters_per_degree_lon = 111000 * math.cos(math.radians(self.reference_lat))

        # Scale in x direction
        scale_x = math.sqrt((a0 * meters_per_degree_lon)**2 + (a3 * meters_per_degree_lat)**2)

        # Scale in y direction
        scale_y = math.sqrt((a1 * meters_per_degree_lon)**2 + (a4 * meters_per_degree_lat)**2)

        return scale_x, scale_y


class HomographyTransformer(CoordinateTransformer):
    """
    Homography (projective) transformation for georeferencing.

    Best for oblique drone imagery with camera tilt.
    Requires minimum 4 control points.
    Uses Direct Linear Transform (DLT) with SVD and coordinate normalization.
    """

    def __init__(self, control_points: List['ControlPoint'], use_validation: bool = True,
                 export_proj_string: Optional[str] = None):
        super().__init__(control_points, use_validation, export_proj_string=export_proj_string)

        if len(self.training_points) < 4:
            raise ValueError("Homography transformation requires at least 4 training control points")

        self._set_reference_point()
        self.compute_transformation()

    def compute_transformation(self):
        """
        Compute homography matrix using Direct Linear Transform (DLT).

        Includes coordinate normalization for numerical stability.
        """
        _n = len(self.training_points)

        # Convert geo coordinates to local metric system
        ground_points = np.array([
            self.latlon_to_meters(cp.latitude, cp.longitude)
            for cp in self.training_points
        ], dtype=np.float64)

        pixel_points = np.array([
            (cp.pixel_x, cp.pixel_y)
            for cp in self.training_points
        ], dtype=np.float64)

        # Normalize pixel coordinates for numerical stability
        mean_pixel = np.mean(pixel_points, axis=0)
        std_pixel = np.std(pixel_points)
        if std_pixel < 1e-8:
            raise ValueError("Pixel coordinates too close together")

        T_pixel = np.array([
            [1/std_pixel, 0, -mean_pixel[0]/std_pixel],
            [0, 1/std_pixel, -mean_pixel[1]/std_pixel],
            [0, 0, 1]
        ])

        # Normalize ground coordinates
        mean_ground = np.mean(ground_points, axis=0)
        std_ground = np.std(ground_points)
        if std_ground < 1e-8:
            raise ValueError("Ground coordinates too close together")

        T_ground = np.array([
            [std_ground, 0, mean_ground[0]],
            [0, std_ground, mean_ground[1]],
            [0, 0, 1]
        ])

        # Normalize coordinates
        pixel_norm = (pixel_points - mean_pixel) / std_pixel
        ground_norm = (ground_points - mean_ground) / std_ground

        # Build DLT matrix A
        A = []
        for (x, y), (X, Y) in zip(pixel_norm, ground_norm):
            A.append([-x, -y, -1, 0, 0, 0, x*X, y*X, X])
            A.append([0, 0, 0, -x, -y, -1, x*Y, y*Y, Y])

        A = np.array(A)

        # Solve with SVD
        _, _, Vt = np.linalg.svd(A)
        H_norm = Vt[-1].reshape(3, 3)

        # Denormalize: H = T_ground^-1 * H_norm * T_pixel
        H = T_ground @ H_norm @ T_pixel
        H = H / H[2, 2]  # Normalize so h33 = 1

        self.transform_matrix = H

        # Compute inverse
        try:
            self.inverse_matrix = np.linalg.inv(H)
        except np.linalg.LinAlgError:
            raise ValueError("Homography matrix is singular - check control points")

        # Compute error metrics
        self.compute_reprojection_error()
        if self.validation_points:
            self.compute_validation_error()

    def pixel_to_geo(self, pixel_x: float, pixel_y: float) -> Tuple[float, float]:
        """Convert pixel coordinates to geographic coordinates."""
        if self.transform_matrix is None:
            raise RuntimeError("Transformation not initialized")

        # Apply homography to get metric coordinates
        pixel_homo = np.array([pixel_x, pixel_y, 1.0])
        ground_homo = self.transform_matrix @ pixel_homo

        # Normalize by w component
        east = ground_homo[0] / ground_homo[2]
        north = ground_homo[1] / ground_homo[2]

        # Convert meters to lat/lon
        lat, lon = self.meters_to_latlon(east, north)
        return lon, lat

    def geo_to_pixel(self, longitude: float, latitude: float) -> Tuple[float, float]:
        """Convert geographic coordinates to pixel coordinates.

        If an adjustment is set, applies it after the base transformation.
        """
        if self.inverse_matrix is None:
            raise RuntimeError("Transformation not initialized")

        # Convert lat/lon to meters
        east, north = self.latlon_to_meters(latitude, longitude)

        # Apply inverse homography
        ground_homo = np.array([east, north, 1.0])
        pixel_homo = self.inverse_matrix @ ground_homo

        # Normalize by w component
        pixel_x = pixel_homo[0] / pixel_homo[2]
        pixel_y = pixel_homo[1] / pixel_homo[2]

        # Apply adjustment if set
        if self.adjustment is not None:
            pixel_x, pixel_y = self.adjustment.apply_to_point(pixel_x, pixel_y)

        return pixel_x, pixel_y

    def geo_to_pixel_unadjusted(self, longitude: float, latitude: float) -> Tuple[float, float]:
        """Convert geographic coordinates to pixel coordinates without adjustment."""
        if self.inverse_matrix is None:
            raise RuntimeError("Transformation not initialized")

        # Convert lat/lon to meters
        east, north = self.latlon_to_meters(latitude, longitude)

        # Apply inverse homography
        ground_homo = np.array([east, north, 1.0])
        pixel_homo = self.inverse_matrix @ ground_homo

        # Normalize by w component
        pixel_x = pixel_homo[0] / pixel_homo[2]
        pixel_y = pixel_homo[1] / pixel_homo[2]

        return pixel_x, pixel_y

    def get_scale_factor(self) -> Tuple[float, float]:
        """
        Get approximate scale factors (meters per pixel).

        For homography, scale varies across the image. This returns
        an average scale computed at the image center.
        """
        # Find approximate center of all pixel points
        center_x = np.mean([cp.pixel_x for cp in self.training_points])
        center_y = np.mean([cp.pixel_y for cp in self.training_points])

        # Sample scale at center using small offsets
        offset = 10.0  # pixels

        # Horizontal scale
        mx1, my1 = self.pixel_to_meters(center_x - offset, center_y)
        mx2, my2 = self.pixel_to_meters(center_x + offset, center_y)
        scale_x = math.sqrt((mx2 - mx1)**2 + (my2 - my1)**2) / (2 * offset)

        # Vertical scale
        mx1, my1 = self.pixel_to_meters(center_x, center_y - offset)
        mx2, my2 = self.pixel_to_meters(center_x, center_y + offset)
        scale_y = math.sqrt((mx2 - mx1)**2 + (my2 - my1)**2) / (2 * offset)

        return scale_x, scale_y


class HybridTransformer(CoordinateTransformer):
    """Hybrid transformer: homography inside image bounds, affine outside.

    Wraps HomographyTransformer + AffineTransformer fitted to the same
    control points. Blends smoothly in a transition zone around the image
    boundary to avoid discontinuities. Prevents homography extrapolation
    artifacts (w->0 singularity) for points far from control points.
    """

    def __init__(self, control_points: List['ControlPoint'],
                 use_validation: bool = True,
                 export_proj_string: Optional[str] = None,
                 image_width: int = 0, image_height: int = 0):
        # Don't call super().__init__ — we delegate to sub-transformers
        self.all_control_points = control_points
        self._export_proj_string = export_proj_string
        self._export_proj = None

        # Create both sub-transformers from the same control points
        self._homography = HomographyTransformer(
            control_points, use_validation, export_proj_string)
        self._affine = AffineTransformer(
            control_points, use_validation=False,
            export_proj_string=export_proj_string)

        # Copy shared state from homography (it's the "primary")
        self.training_points = self._homography.training_points
        self.validation_points = self._homography.validation_points
        self.transform_matrix = self._homography.transform_matrix
        self.inverse_matrix = self._homography.inverse_matrix
        self.reference_lat = self._homography.reference_lat
        self.reference_lon = self._homography.reference_lon
        self.reprojection_error = self._homography.reprojection_error
        self.validation_error = self._homography.validation_error
        self.adjustment = None

        # Image bounds for blend zone
        self._image_width = image_width
        self._image_height = image_height
        self._margin = 0.2 * min(image_width, image_height) if image_width > 0 else 0

    def _signed_distance_from_bounds(self, px: float, py: float) -> float:
        """Signed distance from image boundary. Positive = inside."""
        if self._image_width <= 0 or self._image_height <= 0:
            return float('inf')
        dx = min(px, self._image_width - px)
        dy = min(py, self._image_height - py)
        return min(dx, dy)

    @staticmethod
    def _smoothstep(t: float) -> float:
        """Smoothstep for C1-continuous blending."""
        t = max(0.0, min(1.0, t))
        return t * t * (3 - 2 * t)

    def _blend_factor(self, homo_px: float, homo_py: float,
                      w_component: float = 1.0) -> float:
        """Compute blend factor: 1.0 = pure homography, 0.0 = pure affine.

        The blend zone is entirely outside the image boundary so that points
        inside the image always use the (more accurate) homography.  Blending
        in affine only starts once d < 0, transitioning smoothly to pure affine
        at d = -margin.  This prevents visible road bends near image edges that
        occurred when the previous ±margin zone mixed affine into interior points.
        """
        if w_component < 0.01:
            return 0.0
        if self._margin <= 0:
            return 1.0
        d = self._signed_distance_from_bounds(homo_px, homo_py)
        if d >= 0:
            return 1.0
        if d < -self._margin:
            return 0.0
        return self._smoothstep((d + self._margin) / self._margin)

    def geo_to_pixel(self, longitude: float, latitude: float) -> Tuple[float, float]:
        """Blended geo->pixel: homography inside image, affine outside."""
        # Compute homography result with w check
        east, north = self.latlon_to_meters(latitude, longitude)
        ground_homo = np.array([east, north, 1.0])
        pixel_homo = self._homography.inverse_matrix @ ground_homo
        w = pixel_homo[2]

        if abs(w) < 1e-10:
            return self._affine.geo_to_pixel(longitude, latitude)

        hpx, hpy = pixel_homo[0] / w, pixel_homo[1] / w
        t = self._blend_factor(hpx, hpy, w)

        if t >= 1.0:
            px, py = hpx, hpy
        elif t <= 0.0:
            px, py = self._affine.geo_to_pixel(longitude, latitude)
        else:
            apx, apy = self._affine.geo_to_pixel(longitude, latitude)
            px = t * hpx + (1 - t) * apx
            py = t * hpy + (1 - t) * apy

        if self.adjustment is not None:
            px, py = self.adjustment.apply_to_point(px, py)
        return px, py

    def geo_to_pixel_unadjusted(self, longitude: float, latitude: float) -> Tuple[float, float]:
        """Blended geo->pixel without adjustment."""
        east, north = self.latlon_to_meters(latitude, longitude)
        ground_homo = np.array([east, north, 1.0])
        pixel_homo = self._homography.inverse_matrix @ ground_homo
        w = pixel_homo[2]

        if abs(w) < 1e-10:
            return self._affine.geo_to_pixel_unadjusted(longitude, latitude)

        hpx, hpy = pixel_homo[0] / w, pixel_homo[1] / w
        t = self._blend_factor(hpx, hpy, w)

        if t >= 1.0:
            return hpx, hpy
        elif t <= 0.0:
            return self._affine.geo_to_pixel_unadjusted(longitude, latitude)
        else:
            apx, apy = self._affine.geo_to_pixel_unadjusted(longitude, latitude)
            return t * hpx + (1 - t) * apx, t * hpy + (1 - t) * apy

    def pixel_to_geo(self, pixel_x: float, pixel_y: float) -> Tuple[float, float]:
        """Blended pixel->geo: homography inside image, affine outside."""
        t = self._blend_factor(pixel_x, pixel_y)

        if t >= 1.0:
            return self._homography.pixel_to_geo(pixel_x, pixel_y)
        elif t <= 0.0:
            return self._affine.pixel_to_geo(pixel_x, pixel_y)
        else:
            h_lon, h_lat = self._homography.pixel_to_geo(pixel_x, pixel_y)
            a_lon, a_lat = self._affine.pixel_to_geo(pixel_x, pixel_y)
            return t * h_lon + (1 - t) * a_lon, t * h_lat + (1 - t) * a_lat

    def compute_transformation(self):
        """Delegated to sub-transformers in __init__."""
        pass

    def get_scale_factor(self) -> Tuple[float, float]:
        return self._homography.get_scale_factor()

    def set_adjustment(self, adjustment):
        """Set adjustment on the hybrid transformer only (not sub-transformers)."""
        self.adjustment = adjustment


def create_transformer(
    control_points: List['ControlPoint'],
    method: Union[str, TransformMethod] = TransformMethod.HOMOGRAPHY,
    use_validation: bool = True,
    export_proj_string: Optional[str] = None,
    image_width: int = 0,
    image_height: int = 0,
) -> Optional[CoordinateTransformer]:
    """
    Create a coordinate transformer from control points.

    Args:
        control_points: List of control points
        method: Transformation method - either TransformMethod enum or string
                ('affine' or 'homography')
        use_validation: If True, separate validation points from training
        export_proj_string: If set, latlon_to_meters/meters_to_latlon use this
            pyproj projection instead of equirectangular approximation.

    Returns:
        CoordinateTransformer if successful, None if insufficient points
    """
    if not control_points:
        return None

    # Convert string to enum if needed
    if isinstance(method, str):
        method = TransformMethod.HOMOGRAPHY if method == 'homography' else TransformMethod.AFFINE

    # Separate training and validation points
    if use_validation:
        training_points = [cp for cp in control_points if not getattr(cp, 'is_validation', False)]
    else:
        training_points = control_points

    # Check minimum requirements
    min_points = 4 if method == TransformMethod.HOMOGRAPHY else 3
    if len(training_points) < min_points:
        return None

    try:
        if method == TransformMethod.HOMOGRAPHY:
            if image_width > 0 and image_height > 0:
                return HybridTransformer(
                    control_points, use_validation,
                    export_proj_string=export_proj_string,
                    image_width=image_width, image_height=image_height)
            return HomographyTransformer(control_points, use_validation,
                                         export_proj_string=export_proj_string)
        else:
            return AffineTransformer(control_points, use_validation,
                                     export_proj_string=export_proj_string)
    except (ValueError, np.linalg.LinAlgError) as e:
        logger.error(f"Error creating transformer: {e}")
        return None


def create_transformer_from_bounds(
    image_width: int,
    image_height: int,
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    export_proj_string: Optional[str] = None,
) -> Optional[AffineTransformer]:
    """
    Create an AffineTransformer from image dimensions and geographic bounds.

    Synthesizes corner control points mapping image corners to geographic
    coordinates. Ideal for nadir (orthophoto/satellite) imagery where the
    relationship between pixels and geography is a simple affine transform.

    Image layout convention: pixel (0,0) = top-left = (min_lon, max_lat),
    pixel (W,H) = bottom-right = (max_lon, min_lat).

    Args:
        image_width: Width of the image in pixels.
        image_height: Height of the image in pixels.
        min_lon, min_lat, max_lon, max_lat: Geographic bounding box (WGS84).
        export_proj_string: Optional pyproj string for metric conversions.

    Returns:
        AffineTransformer if successful, None on error.
    """
    from orbit.models.project import ControlPoint

    corners = [
        ControlPoint(pixel_x=0.0, pixel_y=0.0,
                     longitude=min_lon, latitude=max_lat, name="NW"),
        ControlPoint(pixel_x=float(image_width), pixel_y=0.0,
                     longitude=max_lon, latitude=max_lat, name="NE"),
        ControlPoint(pixel_x=float(image_width), pixel_y=float(image_height),
                     longitude=max_lon, latitude=min_lat, name="SE"),
        ControlPoint(pixel_x=0.0, pixel_y=float(image_height),
                     longitude=min_lon, latitude=min_lat, name="SW"),
    ]

    try:
        return AffineTransformer(
            corners, use_validation=False,
            export_proj_string=export_proj_string,
        )
    except (ValueError, np.linalg.LinAlgError) as e:
        logger.error(f"Error creating bounds transformer: {e}")
        return None


# For backwards compatibility with existing code
def get_rms_error_meters(transformer: CoordinateTransformer, latitude: float = 0.0) -> float:
    """
    Get approximate RMS error in meters (for backwards compatibility).

    Args:
        transformer: Coordinate transformer
        latitude: Reference latitude (unused, kept for compatibility)

    Returns:
        RMS error in meters
    """
    if transformer.reprojection_error:
        return transformer.reprojection_error.get('rmse_meters', 0.0)
    return 0.0

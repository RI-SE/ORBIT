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

import numpy as np
import math
from typing import List, Tuple, Optional, Dict
from enum import Enum, auto


class TransformMethod(Enum):
    """Transformation method for georeferencing."""
    AFFINE = auto()
    HOMOGRAPHY = auto()


class CoordinateTransformer:
    """
    Base class for coordinate transformers.

    Handles coordinate transformations between pixel and geographic coordinates.
    Subclasses implement specific transformation methods (affine, homography).
    """

    def __init__(self, control_points: List['ControlPoint'], use_validation: bool = True):
        """
        Initialize transformer with control points.

        Args:
            control_points: List of control points
            use_validation: If True, separate validation points from training

        Raises:
            ValueError: If insufficient control points provided
        """
        self.all_control_points = control_points
        self.use_validation = use_validation

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

    def _set_reference_point(self):
        """Set reference point as mean of all control points."""
        if not self.all_control_points:
            return
        self.reference_lat = np.mean([cp.latitude for cp in self.all_control_points])
        self.reference_lon = np.mean([cp.longitude for cp in self.all_control_points])

    def latlon_to_meters(self, lat: float, lon: float) -> Tuple[float, float]:
        """
        Convert lat/lon to local metric coordinates relative to reference point.

        Uses equirectangular projection (suitable for areas <100km).

        Args:
            lat: Latitude in decimal degrees
            lon: Longitude in decimal degrees

        Returns:
            Tuple of (east, north) in meters
        """
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
        Convert local metric coordinates back to lat/lon.

        Args:
            east: East coordinate in meters
            north: North coordinate in meters

        Returns:
            Tuple of (latitude, longitude) in decimal degrees
        """
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

    def pixels_to_geo_batch(self, pixels: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        """Convert multiple pixel coordinates to geographic coordinates."""
        return [self.pixel_to_geo(x, y) for x, y in pixels]

    def pixels_to_meters_batch(self, pixels: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        """Convert multiple pixel coordinates to local metric coordinates."""
        return [self.pixel_to_meters(x, y) for x, y in pixels]

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

            # Geographic error in degrees
            error_lon = lon_calc - cp.longitude
            error_lat = lat_calc - cp.latitude

            # Convert to meters
            meters_per_degree_lat = 111000
            meters_per_degree_lon = 111000 * math.cos(math.radians(self.reference_lat))
            error_m = math.sqrt(
                (error_lon * meters_per_degree_lon)**2 +
                (error_lat * meters_per_degree_lat)**2
            )
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

            # Calculate geographic error
            error_lon = lon_calc - cp.longitude
            error_lat = lat_calc - cp.latitude

            # Convert to meters
            meters_per_degree_lat = 111000
            meters_per_degree_lon = 111000 * math.cos(math.radians(self.reference_lat))
            error_m = math.sqrt(
                (error_lon * meters_per_degree_lon)**2 +
                (error_lat * meters_per_degree_lat)**2
            )
            errors_meters.append(error_m)

            # Convert to pixel error (approximate)
            # Transform back to pixel to get pixel error
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

    def __init__(self, control_points: List['ControlPoint'], use_validation: bool = True):
        super().__init__(control_points, use_validation)

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
        """Convert geographic coordinates to pixel coordinates."""
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

    def __init__(self, control_points: List['ControlPoint'], use_validation: bool = True):
        super().__init__(control_points, use_validation)

        if len(self.training_points) < 4:
            raise ValueError("Homography transformation requires at least 4 training control points")

        self._set_reference_point()
        self.compute_transformation()

    def compute_transformation(self):
        """
        Compute homography matrix using Direct Linear Transform (DLT).

        Includes coordinate normalization for numerical stability.
        """
        n = len(self.training_points)

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
        """Convert geographic coordinates to pixel coordinates."""
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


def create_transformer(
    control_points: List['ControlPoint'],
    method: TransformMethod = TransformMethod.HOMOGRAPHY,
    use_validation: bool = True
) -> Optional[CoordinateTransformer]:
    """
    Create a coordinate transformer from control points.

    Args:
        control_points: List of control points
        method: Transformation method (AFFINE or HOMOGRAPHY)
        use_validation: If True, separate validation points from training

    Returns:
        CoordinateTransformer if successful, None if insufficient points
    """
    if not control_points:
        return None

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
            return HomographyTransformer(control_points, use_validation)
        else:
            return AffineTransformer(control_points, use_validation)
    except (ValueError, np.linalg.LinAlgError) as e:
        print(f"Error creating transformer: {e}")
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

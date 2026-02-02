"""
Coordinate transformation for orbit-georef.

Supports both affine (6-parameter) and homography (8-parameter) transformations.
Can use precomputed matrices from exported JSON or recompute from control points.
"""

import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .models import ControlPoint


class GeoTransformer:
    """
    Coordinate transformer for pixel↔geo conversions.

    Can be initialized from:
    - A JSON file exported from ORBIT (load_georef)
    - A list of control points (from_control_points)
    - Raw matrices (from_matrices)
    """

    def __init__(
        self,
        transform_matrix: np.ndarray,
        inverse_matrix: np.ndarray,
        reference_lon: float,
        reference_lat: float,
        method: str = "homography",
        scale_x: float = 1.0,
        scale_y: float = 1.0,
        control_points: Optional[List[ControlPoint]] = None,
        source_info: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize transformer with precomputed matrices.

        For most use cases, use from_file() or from_control_points() instead.

        Args:
            transform_matrix: 3x3 pixel→geo transformation matrix
            inverse_matrix: 3x3 geo→pixel transformation matrix
            reference_lon: Reference longitude (center of control points)
            reference_lat: Reference latitude (center of control points)
            method: "affine" or "homography"
            scale_x: X scale factor (meters per pixel)
            scale_y: Y scale factor (meters per pixel)
            control_points: Optional list of control points used
            source_info: Optional dict with project_file and image_path from ORBIT export
        """
        self.transform_matrix = transform_matrix
        self.inverse_matrix = inverse_matrix
        self.reference_lon = reference_lon
        self.reference_lat = reference_lat
        self.method = method
        self._scale_x = scale_x
        self._scale_y = scale_y
        self.control_points = control_points or []
        self.source_info = source_info or {}

    @classmethod
    def from_file(cls, path: str) -> "GeoTransformer":
        """
        Load transformer from a JSON file exported from ORBIT.

        Args:
            path: Path to JSON file

        Returns:
            GeoTransformer instance
        """
        from .io import load_georef
        return load_georef(path)

    @classmethod
    def from_control_points(
        cls,
        control_points: List[ControlPoint],
        method: str = "homography",
    ) -> "GeoTransformer":
        """
        Create transformer from control points.

        Args:
            control_points: List of control points (min 3 for affine, 4 for homography)
            method: "affine" or "homography"

        Returns:
            GeoTransformer instance

        Raises:
            ValueError: If insufficient control points
        """
        # Separate training and validation points
        training_points = [cp for cp in control_points if not cp.is_validation]

        min_points = 4 if method == "homography" else 3
        if len(training_points) < min_points:
            raise ValueError(
                f"{method} requires at least {min_points} training control points, "
                f"got {len(training_points)}"
            )

        # Calculate reference point (mean of all points)
        ref_lon = np.mean([cp.longitude for cp in control_points])
        ref_lat = np.mean([cp.latitude for cp in control_points])

        if method == "homography":
            transform_matrix, inverse_matrix = _compute_homography(
                training_points, ref_lon, ref_lat
            )
        else:
            transform_matrix, inverse_matrix = _compute_affine(training_points)

        # Calculate scale factors
        scale_x, scale_y = _compute_scale(
            transform_matrix, ref_lat, method, training_points
        )

        return cls(
            transform_matrix=transform_matrix,
            inverse_matrix=inverse_matrix,
            reference_lon=ref_lon,
            reference_lat=ref_lat,
            method=method,
            scale_x=scale_x,
            scale_y=scale_y,
            control_points=control_points,
        )

    def pixel_to_geo(self, pixel_x: float, pixel_y: float) -> Tuple[float, float]:
        """
        Convert pixel coordinates to geographic coordinates.

        Args:
            pixel_x: X coordinate in pixels
            pixel_y: Y coordinate in pixels

        Returns:
            Tuple of (longitude, latitude) in decimal degrees
        """
        if self.method == "homography":
            # Homography: pixel → meters → geo
            pixel_homo = np.array([pixel_x, pixel_y, 1.0])
            ground_homo = self.transform_matrix @ pixel_homo
            east = ground_homo[0] / ground_homo[2]
            north = ground_homo[1] / ground_homo[2]
            lat, lon = self._meters_to_latlon(east, north)
            return lon, lat
        else:
            # Affine: direct transformation
            point = np.array([pixel_x, pixel_y, 1.0])
            result = self.transform_matrix @ point
            return result[0], result[1]  # lon, lat

    def geo_to_pixel(self, longitude: float, latitude: float) -> Tuple[float, float]:
        """
        Convert geographic coordinates to pixel coordinates.

        Args:
            longitude: Longitude in decimal degrees
            latitude: Latitude in decimal degrees

        Returns:
            Tuple of (pixel_x, pixel_y)
        """
        if self.method == "homography":
            # Homography: geo → meters → pixel
            east, north = self._latlon_to_meters(latitude, longitude)
            ground_homo = np.array([east, north, 1.0])
            pixel_homo = self.inverse_matrix @ ground_homo
            return pixel_homo[0] / pixel_homo[2], pixel_homo[1] / pixel_homo[2]
        else:
            # Affine: direct transformation
            point = np.array([longitude, latitude, 1.0])
            result = self.inverse_matrix @ point
            return result[0], result[1]

    def pixels_to_geo_batch(
        self, points: List[Tuple[float, float]]
    ) -> List[Tuple[float, float]]:
        """
        Convert multiple pixel coordinates to geographic coordinates.

        Args:
            points: List of (pixel_x, pixel_y) tuples

        Returns:
            List of (longitude, latitude) tuples
        """
        return [self.pixel_to_geo(x, y) for x, y in points]

    def geo_to_pixels_batch(
        self, points: List[Tuple[float, float]]
    ) -> List[Tuple[float, float]]:
        """
        Convert multiple geographic coordinates to pixel coordinates.

        Args:
            points: List of (longitude, latitude) tuples

        Returns:
            List of (pixel_x, pixel_y) tuples
        """
        return [self.geo_to_pixel(lon, lat) for lon, lat in points]

    def get_scale(self) -> Tuple[float, float]:
        """
        Get scale factors (meters per pixel).

        Returns:
            Tuple of (scale_x, scale_y) in meters per pixel
        """
        return self._scale_x, self._scale_y

    def _latlon_to_meters(self, lat: float, lon: float) -> Tuple[float, float]:
        """Convert lat/lon to local metric coordinates (equirectangular projection)."""
        R = 6371000.0  # Earth radius in meters
        lat_rad = math.radians(lat)
        lon_rad = math.radians(lon)
        ref_lat_rad = math.radians(self.reference_lat)
        ref_lon_rad = math.radians(self.reference_lon)

        east = R * (lon_rad - ref_lon_rad) * math.cos(ref_lat_rad)
        north = R * (lat_rad - ref_lat_rad)
        return east, north

    def _meters_to_latlon(self, east: float, north: float) -> Tuple[float, float]:
        """Convert local metric coordinates to lat/lon."""
        R = 6371000.0
        ref_lat_rad = math.radians(self.reference_lat)
        ref_lon_rad = math.radians(self.reference_lon)

        lat_rad = ref_lat_rad + (north / R)
        lon_rad = ref_lon_rad + (east / (R * math.cos(ref_lat_rad)))
        return math.degrees(lat_rad), math.degrees(lon_rad)


def _compute_affine(control_points: List[ControlPoint]) -> Tuple[np.ndarray, np.ndarray]:
    """Compute affine transformation matrices from control points."""
    n = len(control_points)

    # Build matrices for least-squares solution
    A = np.zeros((n * 2, 6))
    B = np.zeros(n * 2)

    for i, cp in enumerate(control_points):
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
    coeffs, _, _, _ = np.linalg.lstsq(A, B, rcond=None)

    # Build transformation matrix
    transform_matrix = np.array([
        [coeffs[0], coeffs[1], coeffs[2]],
        [coeffs[3], coeffs[4], coeffs[5]],
        [0, 0, 1]
    ])

    # Compute inverse
    linear_part = transform_matrix[:2, :2]
    linear_inv = np.linalg.inv(linear_part)
    translation = transform_matrix[:2, 2]
    translation_inv = -linear_inv @ translation

    inverse_matrix = np.array([
        [linear_inv[0, 0], linear_inv[0, 1], translation_inv[0]],
        [linear_inv[1, 0], linear_inv[1, 1], translation_inv[1]],
        [0, 0, 1]
    ])

    return transform_matrix, inverse_matrix


def _compute_homography(
    control_points: List[ControlPoint],
    ref_lon: float,
    ref_lat: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """Compute homography transformation matrices from control points."""
    # Convert geo coordinates to local metric system
    R = 6371000.0
    ref_lat_rad = math.radians(ref_lat)
    ref_lon_rad = math.radians(ref_lon)

    ground_points = []
    for cp in control_points:
        lat_rad = math.radians(cp.latitude)
        lon_rad = math.radians(cp.longitude)
        east = R * (lon_rad - ref_lon_rad) * math.cos(ref_lat_rad)
        north = R * (lat_rad - ref_lat_rad)
        ground_points.append((east, north))

    ground_points = np.array(ground_points, dtype=np.float64)
    pixel_points = np.array(
        [(cp.pixel_x, cp.pixel_y) for cp in control_points],
        dtype=np.float64
    )

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

    # Denormalize: H = T_ground * H_norm * T_pixel
    H = T_ground @ H_norm @ T_pixel
    H = H / H[2, 2]  # Normalize so h33 = 1

    # Compute inverse
    H_inv = np.linalg.inv(H)

    return H, H_inv


def _compute_scale(
    transform_matrix: np.ndarray,
    ref_lat: float,
    method: str,
    control_points: List[ControlPoint],
) -> Tuple[float, float]:
    """Compute scale factors (meters per pixel)."""
    if method == "homography":
        # For homography, sample scale at center
        center_x = np.mean([cp.pixel_x for cp in control_points])
        center_y = np.mean([cp.pixel_y for cp in control_points])
        offset = 10.0

        # Create temporary transformer-like calculation
        def pixel_to_meters(px, py, matrix, ref_lat, ref_lon):
            pixel_homo = np.array([px, py, 1.0])
            ground_homo = matrix @ pixel_homo
            return ground_homo[0] / ground_homo[2], ground_homo[1] / ground_homo[2]

        ref_lon = np.mean([cp.longitude for cp in control_points])

        mx1, my1 = pixel_to_meters(center_x - offset, center_y, transform_matrix, ref_lat, ref_lon)
        mx2, my2 = pixel_to_meters(center_x + offset, center_y, transform_matrix, ref_lat, ref_lon)
        scale_x = math.sqrt((mx2 - mx1)**2 + (my2 - my1)**2) / (2 * offset)

        mx1, my1 = pixel_to_meters(center_x, center_y - offset, transform_matrix, ref_lat, ref_lon)
        mx2, my2 = pixel_to_meters(center_x, center_y + offset, transform_matrix, ref_lat, ref_lon)
        scale_y = math.sqrt((mx2 - mx1)**2 + (my2 - my1)**2) / (2 * offset)

        return scale_x, scale_y
    else:
        # Affine: extract from matrix
        a0, a1 = transform_matrix[0, 0], transform_matrix[0, 1]
        a3, a4 = transform_matrix[1, 0], transform_matrix[1, 1]

        meters_per_degree_lat = 111000
        meters_per_degree_lon = 111000 * math.cos(math.radians(ref_lat))

        scale_x = math.sqrt((a0 * meters_per_degree_lon)**2 + (a3 * meters_per_degree_lat)**2)
        scale_y = math.sqrt((a1 * meters_per_degree_lon)**2 + (a4 * meters_per_degree_lat)**2)

        return scale_x, scale_y

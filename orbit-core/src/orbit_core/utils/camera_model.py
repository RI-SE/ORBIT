"""Drone camera model for physically-derived georeferencing.

Computes a homography matrix from drone flight parameters (position, altitude,
gimbal orientation) instead of fitting it to ground control points alone. Works
even when GCPs are nearly collinear (e.g., all along a single road).

Coordinate conventions:
- World frame: ENU (East, North, Up), origin = drone ground nadir
- Gimbal yaw: 0=North, positive=CW (East), negative=CCW (West), world-frame absolute
  (DJI reports magnetic heading; this module corrects to true north automatically)
- Gimbal pitch: 0=horizontal, -90=nadir (DJI convention)
- Result: transform_matrix maps pixel [u,v,1] → ENU [E,N,w] relative to nadir
"""

import math
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
from scipy.optimize import minimize_scalar


@dataclass
class DroneMetadata:
    """Flight statistics for a single video sequence, extracted from a drone log.

    All angular values in degrees. Position in WGS84. Altitude in meters AGL.
    hfov_deg is the horizontal field of view at native sensor width — read from
    the drone log tool's camera lookup table when available.
    """
    latitude: float
    longitude: float
    alt_agl: float
    gimbal_yaw: float    # world-frame compass bearing, 0=N, CW positive
    gimbal_pitch: float  # below horizontal: 0=horizontal, -90=nadir
    gimbal_roll: float = 0.0
    drone_type: Optional[str] = None
    lens_type: str = "standard"
    hfov_deg: Optional[float] = None  # horizontal FOV in degrees; None = solve from GCPs


def get_magnetic_declination(latitude: float, longitude: float, altitude_m: float = 0.0) -> float:
    """Return magnetic declination in degrees at the given WGS84 position.

    Positive = east declination (magnetic north is east of true north).
    Uses the geomag WMM implementation; falls back to 0.0 if unavailable.
    """
    try:
        import geomag  # type: ignore[import-untyped]
        return float(geomag.declination(latitude, longitude, altitude_m / 1000.0))
    except Exception:
        return 0.0


def _rotation_matrix(yaw_deg: float, pitch_deg: float, roll_deg: float) -> np.ndarray:
    """Build a 3×3 rotation matrix mapping world ENU → camera frame.

    Rows are the camera X (right), Y (down), Z (forward) axes in world ENU.
    Gimbal convention: yaw=compass bearing (0=N, CW+), pitch=below horizontal.
    """
    theta = math.radians(yaw_deg)   # compass bearing of camera
    phi = math.radians(-pitch_deg)  # tilt below horizontal (phi>0 = looking down)
    rho = math.radians(roll_deg)    # roll

    # Camera axes in world ENU [E, N, U]:
    # Right (X): perpendicular to viewing direction, 90° CW from bearing in horizontal plane
    x_cam = np.array([math.cos(theta), -math.sin(theta), 0.0])
    # Forward (Z): bearing θ, tilted φ below horizontal
    z_cam = np.array([math.sin(theta) * math.cos(phi),
                      math.cos(theta) * math.cos(phi),
                      -math.sin(phi)])
    # Down (Y): complete right-handed frame (Z × X = Y)
    y_cam = np.cross(z_cam, x_cam)
    y_cam /= np.linalg.norm(y_cam)  # normalise for numerical safety

    # Apply roll around Z-axis (camera forward)
    if abs(roll_deg) > 1e-6:
        cr, sr = math.cos(rho), math.sin(rho)
        x_rolled = cr * x_cam - sr * y_cam
        y_rolled = sr * x_cam + cr * y_cam
        x_cam, y_cam = x_rolled, y_rolled

    R = np.stack([x_cam, y_cam, z_cam], axis=0)  # shape (3, 3)
    return R


def _build_projection_matrix(
    yaw_deg: float,
    pitch_deg: float,
    roll_deg: float,
    alt_agl: float,
    focal_length_px: float,
    cx: float,
    cy: float,
) -> np.ndarray:
    """Build 3×3 matrix M that projects ENU ground point [E, N, 1] → pixel [u*w, v*w, w].

    M = K × [r1, r2, t]  where r1, r2 are columns of R and t = -h × R[:,2].
    inverse(M) maps pixel → ENU ground = the transform_matrix for CoordinateTransformer.
    """
    R = _rotation_matrix(yaw_deg, pitch_deg, roll_deg)
    K = np.array([[focal_length_px, 0, cx],
                  [0, focal_length_px, cy],
                  [0, 0, 1]], dtype=np.float64)

    # Translation: camera at [0, 0, alt_agl], so t = R × (-C) = -alt_agl × R[:,2]
    t = -alt_agl * R[:, 2]

    # 3×3 matrix [r1, r2, t] = first two cols of R + translation
    M_world = np.column_stack([R[:, 0], R[:, 1], t])  # shape (3, 3)
    return K @ M_world


class DroneCameraModel:
    """Compute pixel↔geographic transform from drone flight parameters.

    The model assumes a flat ground plane at the drone's ground level.
    Reference origin (local ENU) is the drone's ground nadir point.

    Heading refinement is applied in two stages:
    1. Magnetic declination: auto-computed from lat/lon (DJI logs magnetic heading).
    2. GCP yaw refinement: 1-D optimisation over residual yaw offset if GCPs provided.

    Focal length is resolved in priority order:
    1. Explicit `focal_length_px` argument
    2. Computed from `metadata.hfov_deg` and image dimensions
    3. Solved from GCPs via 1-D least-squares (requires ≥ 2 GCPs)
    Raises ValueError if none of the above is available.
    """

    def __init__(
        self,
        metadata: DroneMetadata,
        image_width: int,
        image_height: int,
        control_points: Optional[list] = None,
        focal_length_px: Optional[float] = None,
    ):
        self.metadata = metadata
        self.image_width = image_width
        self.image_height = image_height
        self.cx = image_width / 2.0
        self.cy = image_height / 2.0

        # Stage 1: resolve focal length
        f = focal_length_px
        if f is None and metadata.hfov_deg is not None:
            f = (image_width / 2.0) / math.tan(math.radians(metadata.hfov_deg / 2.0))
        if f is None and control_points:
            f = self._solve_focal_length(control_points)
        if f is None:
            raise ValueError(
                "Cannot determine focal length: provide hfov_deg in drone log or at "
                "least 2 control points."
            )
        self.focal_length_px: float = f

        # Stage 2: correct magnetic → true heading via declination
        self.declination_deg: float = get_magnetic_declination(
            metadata.latitude, metadata.longitude, metadata.alt_agl
        )
        corrected_yaw = metadata.gimbal_yaw + self.declination_deg

        # Re-solve focal length with declination-corrected yaw if it was GCP-derived
        if focal_length_px is None and metadata.hfov_deg is None and control_points:
            f = self._solve_focal_length(control_points, yaw_override=corrected_yaw)
            self.focal_length_px = f

        # Stage 3: GCP yaw refinement — find residual offset after declination correction
        self.yaw_refinement_deg: float = 0.0
        if control_points and len(control_points) >= 2:
            self.yaw_refinement_deg = self._refine_yaw(corrected_yaw, control_points)

        self.effective_yaw: float = corrected_yaw + self.yaw_refinement_deg

        self._M = _build_projection_matrix(
            self.effective_yaw, metadata.gimbal_pitch, metadata.gimbal_roll,
            metadata.alt_agl, f, self.cx, self.cy,
        )
        self.transform_matrix = np.linalg.inv(self._M)   # pixel → ENU
        self.projection_matrix = self._M                  # ENU → pixel

    def _refine_yaw(self, base_yaw: float, control_points: list) -> float:
        """Find residual yaw offset (on top of base_yaw) that minimises GCP reprojection.

        Returns the offset in degrees. Searches ±30° around base_yaw.
        """
        cos_lat = math.cos(math.radians(self.metadata.latitude))
        R_earth = 6371000.0

        def _rms(offset: float) -> float:
            M = _build_projection_matrix(
                base_yaw + offset, self.metadata.gimbal_pitch, self.metadata.gimbal_roll,
                self.metadata.alt_agl, self.focal_length_px, self.cx, self.cy,
            )
            total = 0.0
            for cp in control_points:
                east = (cp.longitude - self.metadata.longitude) * R_earth * cos_lat * math.pi / 180.0
                north = (cp.latitude - self.metadata.latitude) * R_earth * math.pi / 180.0
                ph = M @ np.array([east, north, 1.0])
                if abs(ph[2]) < 1e-10:
                    return 1e12
                u, v = ph[0] / ph[2], ph[1] / ph[2]
                total += (u - cp.pixel_x) ** 2 + (v - cp.pixel_y) ** 2
            return total

        result = minimize_scalar(_rms, bounds=(-30.0, 30.0), method='bounded')
        return float(result.x)

    def _solve_focal_length(self, control_points: list, yaw_override: Optional[float] = None) -> float:
        """Find focal length that minimises GCP reprojection error (1-D optimisation).

        Uses the ENU reference at drone nadir. Uses yaw_override if provided (for
        declination-corrected heading), else falls back to metadata.gimbal_yaw.
        """
        if len(control_points) < 2:
            raise ValueError("Need at least 2 GCPs to solve focal length.")

        yaw = yaw_override if yaw_override is not None else self.metadata.gimbal_yaw
        cos_lat = math.cos(math.radians(self.metadata.latitude))
        R_earth = 6371000.0

        def reprojection_error(f_val: float) -> float:
            M = _build_projection_matrix(
                yaw, self.metadata.gimbal_pitch,
                self.metadata.gimbal_roll, self.metadata.alt_agl,
                f_val, self.cx, self.cy,
            )
            total = 0.0
            for cp in control_points:
                east = (cp.longitude - self.metadata.longitude) * R_earth * cos_lat * math.pi / 180.0
                north = (cp.latitude - self.metadata.latitude) * R_earth * math.pi / 180.0
                g = np.array([east, north, 1.0])
                ph = M @ g
                if abs(ph[2]) < 1e-10:
                    return 1e12
                u = ph[0] / ph[2]
                v = ph[1] / ph[2]
                total += (u - cp.pixel_x) ** 2 + (v - cp.pixel_y) ** 2
            return total

        result = minimize_scalar(reprojection_error, bounds=(500, 8000), method='bounded')
        return float(result.x)

    def pixel_to_enu(self, pixel_x: float, pixel_y: float) -> Tuple[float, float]:
        """Convert image pixel to ENU offset (meters) from drone nadir."""
        p = np.array([pixel_x, pixel_y, 1.0])
        g = self.transform_matrix @ p
        return g[0] / g[2], g[1] / g[2]

    def enu_to_pixel(self, east: float, north: float) -> Tuple[float, float]:
        """Convert ENU offset (meters) from drone nadir to image pixel."""
        g = np.array([east, north, 1.0])
        p = self.projection_matrix @ g
        return p[0] / p[2], p[1] / p[2]

    def estimate_heading_from_gcps(
        self, control_points: list
    ) -> Tuple[float, float]:
        """Estimate gimbal heading that best fits the GCPs.

        Returns (best_heading_deg, rmse_pixels). Useful as a cross-check
        against the value recorded in the drone log.
        """
        if len(control_points) < 2:
            raise ValueError("Need at least 2 GCPs to estimate heading.")

        cos_lat = math.cos(math.radians(self.metadata.latitude))
        R_earth = 6371000.0

        def _rms_for_heading(yaw_deg: float) -> float:
            M = _build_projection_matrix(
                yaw_deg, self.metadata.gimbal_pitch, self.metadata.gimbal_roll,
                self.metadata.alt_agl, self.focal_length_px, self.cx, self.cy,
            )
            total = 0.0
            for cp in control_points:
                east = (cp.longitude - self.metadata.longitude) * R_earth * cos_lat * math.pi / 180.0
                north = (cp.latitude - self.metadata.latitude) * R_earth * math.pi / 180.0
                ph = M @ np.array([east, north, 1.0])
                if abs(ph[2]) < 1e-10:
                    return 1e12
                u, v = ph[0] / ph[2], ph[1] / ph[2]
                total += (u - cp.pixel_x) ** 2 + (v - cp.pixel_y) ** 2
            return math.sqrt(total / len(control_points))

        result = minimize_scalar(_rms_for_heading, bounds=(-180, 180), method='bounded')
        best_yaw = float(result.x)
        rmse = float(result.fun)
        return best_yaw, rmse

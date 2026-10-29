"""
Pinhole camera over a terrain surface: pixel → ground without the flat-plane assumption.

A homography maps the image to one plane. Ground that lies above or below that plane is displaced by
about d·Δz/H (d = distance from nadir, H = camera height), which the RTK altitudes of the control points
show (ORBIT G11). This module fits:

- a smooth terrain surface z(E, N) to the control points' altitudes (ridge-regularised quadratic, or a
  plane with few points), held constant beyond the points' extent;
- a pinhole camera: focal length from the homography (principal point at the image centre, square
  pixels), pose initialised from the homography and refined on the 3D control points.

Pixel → ground then intersects the viewing ray with the terrain. Coordinates are those of the georef
file's transformation matrix (its proj_string CRS, or ORBIT's local metres), z = altitude (m).
Stored in the georef file as the optional "camera_model" section; numpy only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence, Tuple

import numpy as np

MODEL_VERSION = 1
MIN_POINTS = 6  # 3D points for the pose (6 unknowns); fewer: no camera model
MIN_POINTS_QUADRATIC = 8  # fewer: terrain is a plane
# Ridge on the quadratic terms (coordinates scaled by the points' extent); chosen per site by leave-one-out
RIDGE_CANDIDATES = (0.01, 0.03, 0.1, 0.3, 1.0)
EXTENT_MARGIN = 1.2  # terrain is held constant beyond this multiple of the points' radius
MIN_TILT_DEG = 10.0  # closer to nadir the focal length is not determined by the homography


# ---------------------------------------------------------------------------
# Terrain
# ---------------------------------------------------------------------------

@dataclass
class TerrainSurface:
    """z(E, N) = plane, or plane + quadratic, around `centre`; constant beyond `radius` along each ray."""

    centre: Tuple[float, float]
    scale: float
    coefficients: Tuple[float, ...]  # c0, cE, cN[, cEE, cEN, cNN] in scaled coordinates
    radius: float
    ridge: Optional[float] = None
    loo_z_m: Optional[float] = None  # leave-one-out RMS of the altitudes (m)

    @classmethod
    def fit(cls, points: np.ndarray) -> "TerrainSurface":
        """Fit to (n, 3) points E, N, z (n >= 3); with enough points a quadratic, ridge chosen by leave-one-out."""
        centre = points[:, :2].mean(axis=0)
        offsets = points[:, :2] - centre
        radius = float(np.max(np.linalg.norm(offsets, axis=1))) or 1.0
        x, y = (offsets / radius).T
        columns = [np.ones_like(x), x, y]
        if len(points) >= MIN_POINTS_QUADRATIC:
            columns += [x * x, x * y, y * y]
        A, z = np.column_stack(columns), points[:, 2]
        ridges = RIDGE_CANDIDATES if A.shape[1] == 6 else (0.0,)
        loo, ridge = min((_loo_rms(A, z, r), r) for r in ridges)
        coefficients = _ridge_solve(A, z, ridge)
        return cls((float(centre[0]), float(centre[1])), radius, tuple(float(c) for c in coefficients),
                   radius * EXTENT_MARGIN, ridge if A.shape[1] == 6 else None, round(loo, 4))

    def height(self, east, north):
        """Terrain altitude at (E, N); scalars or arrays."""
        dx, dy = np.asarray(east, dtype=float) - self.centre[0], np.asarray(north, dtype=float) - self.centre[1]
        distance = np.hypot(dx, dy)
        shrink = np.where(distance > self.radius, self.radius / np.maximum(distance, 1e-12), 1.0)
        x, y = dx * shrink / self.scale, dy * shrink / self.scale
        c = self.coefficients
        z = c[0] + c[1] * x + c[2] * y
        if len(c) == 6:
            z = z + c[3] * x * x + c[4] * x * y + c[5] * y * y
        return z

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "quadratic" if len(self.coefficients) == 6 else "plane", "centre": list(self.centre),
                "scale": self.scale, "coefficients": list(self.coefficients), "radius": self.radius,
                "ridge": self.ridge, "leave_one_out_z_m": self.loo_z_m}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TerrainSurface":
        return cls(tuple(data["centre"]), float(data["scale"]), tuple(data["coefficients"]), float(data["radius"]),
                   data.get("ridge"), data.get("leave_one_out_z_m"))


def _ridge_solve(A: np.ndarray, z: np.ndarray, ridge: float) -> np.ndarray:
    penalty = np.diag([0.0] * 3 + [ridge] * (A.shape[1] - 3))
    return np.linalg.solve(A.T @ A + penalty + np.eye(A.shape[1]) * 1e-12, A.T @ z)


def _loo_rms(A: np.ndarray, z: np.ndarray, ridge: float) -> float:
    """Leave-one-out RMS of z for this ridge (inf when there are too few points to leave one out)."""
    if len(z) <= A.shape[1]:
        return float("inf") if A.shape[1] == 6 else 0.0
    errors = [z[i] - A[i] @ _ridge_solve(np.delete(A, i, 0), np.delete(z, i), ridge) for i in range(len(z))]
    return float(np.sqrt(np.mean(np.square(errors))))


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------

def _rodrigues(rvec: np.ndarray) -> np.ndarray:
    theta = float(np.linalg.norm(rvec))
    if theta < 1e-12:
        return np.eye(3)
    k = rvec / theta
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(theta) * K + (1 - math.cos(theta)) * K @ K


def _rotation_vector(R: np.ndarray) -> np.ndarray:
    theta = math.acos(max(-1.0, min(1.0, (np.trace(R) - 1) / 2)))
    if theta < 1e-12:
        return np.zeros(3)
    axis = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]]) / (2 * math.sin(theta))
    return axis * theta


@dataclass
class CameraModel:
    """Pinhole camera (K, R, C) in a local frame at `origin`, over `terrain`."""

    K: np.ndarray
    R: np.ndarray  # world → camera rotation
    C: np.ndarray  # camera centre, local frame
    origin: np.ndarray  # E, N, z of the local frame's origin
    terrain: TerrainSurface
    image_size: Tuple[int, int]
    fit: Dict[str, Any]

    def project(self, east, north, z) -> Tuple[float, float]:
        """World point → pixel."""
        p = self.K @ (self.R @ (np.array([east, north, z], dtype=float) - self.origin - self.C))
        return float(p[0] / p[2]), float(p[1] / p[2])

    def ground_to_pixel(self, east: float, north: float) -> Tuple[float, float]:
        """Ground point (on the terrain) → pixel."""
        return self.project(east, north, float(self.terrain.height(east, north)))

    def pixel_to_ground(self, u: float, v: float, iterations: int = 30) -> Tuple[float, float, float]:
        """Pixel → (E, N, z) where the viewing ray meets the terrain."""
        ray = self.R.T @ np.linalg.solve(self.K, np.array([u, v, 1.0]))
        centre = self.origin + self.C
        if ray[2] >= 0:  # looks above the horizon
            return float("nan"), float("nan"), float("nan")
        z = float(self.terrain.height(centre[0], centre[1]))
        point = centre
        for _ in range(iterations):
            point = centre + ray * (z - centre[2]) / ray[2]
            z_new = float(self.terrain.height(point[0], point[1]))
            if abs(z_new - z) < 1e-4:
                break
            z = z_new
        return float(point[0]), float(point[1]), z

    def to_dict(self) -> Dict[str, Any]:
        return {"version": MODEL_VERSION, "origin": self.origin.tolist(), "K": self.K.tolist(),
                "R": self.R.tolist(), "C": self.C.tolist(), "image_size": list(self.image_size),
                "terrain": self.terrain.to_dict(), "fit": self.fit}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Optional["CameraModel"]:
        """The model, or None for an unknown version (missing = no camera model)."""
        if data.get("version") != MODEL_VERSION:
            return None
        return cls(np.array(data["K"], dtype=float), np.array(data["R"], dtype=float),
                   np.array(data["C"], dtype=float), np.array(data["origin"], dtype=float),
                   TerrainSurface.from_dict(data["terrain"]), tuple(data["image_size"]), data.get("fit", {}))


# ---------------------------------------------------------------------------
# Fitting
# ---------------------------------------------------------------------------

def focal_from_homography(ground_to_pixel: np.ndarray, principal: Tuple[float, float]) -> Optional[float]:
    """Focal length (px) from a ground→pixel homography with square pixels; None if not determined.

    With H = K [r1 r2 t], the orthonormality of r1 and r2 gives two estimates of f²; near nadir (small tilt)
    both are ill-conditioned.
    """
    T = np.array([[1, 0, -principal[0]], [0, 1, -principal[1]], [0, 0, 1]], dtype=float)
    h = T @ ground_to_pixel
    h = h / np.linalg.norm(h)
    (a1, a2), (b1, b2), (c1, c2) = h[0, :2], h[1, :2], h[2, :2]
    # Both constraints are linear in w = 1/f²: p·w + q = 0; least squares weights them by conditioning
    p = np.array([a1 * a2 + b1 * b2, (a1 * a1 + b1 * b1) - (a2 * a2 + b2 * b2)])
    q = np.array([c1 * c2, c1 * c1 - c2 * c2])
    if p @ p < 1e-30:
        return None
    w = -(p @ q) / (p @ p)
    return 1.0 / math.sqrt(w) if w > 0 else None


def _pose_from_homography(ground_to_pixel: np.ndarray, K: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """R and camera centre C from H = K [r1 r2 t] (local ground frame, z = 0 plane)."""
    M = np.linalg.solve(K, ground_to_pixel)
    scale = (np.linalg.norm(M[:, 0]) + np.linalg.norm(M[:, 1])) / 2
    for sign in (1.0, -1.0):  # H is known up to sign: take the one with the camera above the ground
        r1, r2, t = (M[:, 0], M[:, 1], M[:, 2]) / (sign * scale)
        U, _, Vt = np.linalg.svd(np.column_stack([r1, r2, np.cross(r1, r2)]))
        R = U @ np.diag([1.0, 1.0, np.linalg.det(U @ Vt)]) @ Vt
        C = -R.T @ t
        if C[2] > 0:
            return R, C
    return R, C


def _refine_pose(K, R, C, world: np.ndarray, pixels: np.ndarray, refine_focal: bool = False,
                 iterations: int = 100):
    """Levenberg-Marquardt on rotation vector, camera centre (and focal length), minimising pixel error.

    Returns (K, R, C, residuals (n, 2)).
    """
    params = np.r_[_rotation_vector(R), C, [K[0, 0]] if refine_focal else []]
    n_params = len(params)

    def camera(p):
        K_p = K.copy()
        if refine_focal:
            K_p[0, 0] = K_p[1, 1] = p[6]
        return K_p, _rodrigues(p[:3]), p[3:6]

    def residuals(p):
        K_p, R_p, C_p = camera(p)
        proj = (K_p @ (R_p @ (world - C_p).T)).T
        return (proj[:, :2] / proj[:, 2:3] - pixels).ravel()

    damping = 1e-3
    current = residuals(params)
    for _ in range(iterations):
        J = np.empty((current.size, n_params))
        for i in range(n_params):
            step = np.zeros(n_params)
            step[i] = 1e-6 * max(1.0, abs(params[i]))
            J[:, i] = (residuals(params + step) - current) / step[i]
        A = J.T @ J
        delta = np.linalg.solve(A + damping * np.diag(np.diag(A) + 1e-12), -J.T @ current)
        candidate = residuals(params + delta)
        if candidate @ candidate < current @ current:
            params, current, damping = params + delta, candidate, damping / 3
            if np.linalg.norm(delta) < 1e-9 * max(1.0, np.linalg.norm(params)):
                break
        else:
            damping *= 10
    K_fit, R_fit, C_fit = camera(params)
    return K_fit, R_fit, C_fit, current.reshape(-1, 2)


def fit_camera_model(world: np.ndarray, pixels: np.ndarray, pixel_to_ground: np.ndarray,
                     image_size: Sequence[int], focal_px: Optional[float] = None) -> Optional[CameraModel]:
    """Camera model from control points (world (n, 3): E, N, altitude; pixels (n, 2)) and the homography.

    Returns None when it cannot be determined (too few points, near-nadir view without focal_px).
    The fit dict reports the reprojection RMS (px) and how the focal length was obtained.
    """
    if len(world) < MIN_POINTS:
        return None
    terrain = TerrainSurface.fit(world)
    origin = np.array([terrain.centre[0], terrain.centre[1], terrain.coefficients[0]])
    local = world - origin
    principal = (image_size[0] / 2.0, image_size[1] / 2.0)
    # Homography in the local frame: ground (E, N) relative to the origin
    shift = np.array([[1, 0, origin[0]], [0, 1, origin[1]], [0, 0, 1]], dtype=float)
    ground_to_pixel = np.linalg.inv(pixel_to_ground) @ shift
    focal_source = "given"
    if focal_px is None:
        focal_px, focal_source = focal_from_homography(ground_to_pixel, principal), "homography"
    if focal_px is None:
        return None
    K = np.array([[focal_px, 0, principal[0]], [0, focal_px, principal[1]], [0, 0, 1.0]])
    R, C = _pose_from_homography(ground_to_pixel, K)
    tilt = math.degrees(math.acos(min(1.0, abs(R[2, 2]))))
    if focal_source == "homography" and tilt < MIN_TILT_DEG:
        return None
    pixels = np.asarray(pixels, dtype=float)
    # The homography's focal length absorbs terrain; with 3D points the pose fit can correct it
    refine_focal = focal_source == "homography"
    K_fit, R_fit, C_fit, residuals = _refine_pose(K, R, C, local, pixels, refine_focal)
    focal_px = K_fit[0, 0]
    fit = {"n_points": int(len(world)), "rms_px": round(float(np.sqrt(np.mean(np.sum(residuals ** 2, axis=1)))), 3),
           "focal_px": round(float(focal_px), 2),
           "focal_source": "homography+refined" if refine_focal else focal_source, "tilt_deg": round(tilt, 2),
           "camera_height_m": round(float(C_fit[2]), 2),
           "leave_one_out_m": _leave_one_out(K_fit, R_fit, C_fit, origin, world, pixels, image_size, refine_focal)}
    return CameraModel(K_fit, R_fit, C_fit, origin, terrain, (int(image_size[0]), int(image_size[1])), fit)


def _leave_one_out(K, R0, C0, origin: np.ndarray, world: np.ndarray, pixels: np.ndarray,
                   image_size, refine_focal: bool) -> Optional[float]:
    """2D RMS (m) of each point predicted (pixel → terrain) by a camera and terrain fitted without it.

    Each refit starts from the full fit, which slightly favours the camera model.
    """
    if len(world) <= MIN_POINTS:
        return None
    errors = []
    for i in range(len(world)):
        keep = np.arange(len(world)) != i
        K_i, R, C, _ = _refine_pose(K, R0, C0, world[keep] - origin, pixels[keep], refine_focal)
        model = CameraModel(K_i, R, C, origin, TerrainSurface.fit(world[keep]), tuple(image_size), {})
        east, north, _ = model.pixel_to_ground(*pixels[i])
        errors.append((east - world[i, 0]) ** 2 + (north - world[i, 1]) ** 2)
    return round(float(math.sqrt(np.mean(errors))), 3)

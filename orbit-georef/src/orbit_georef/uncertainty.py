"""Georeference uncertainty from an ORBIT georef file (scenario-uncertainty `georef` profile, SPEC P2).

The position covariance is split by error level:
- "datum": shared by everything georeferenced with this file, and by a map drawn on the same image;
  it cancels in distances and sizes and must not be added per sample;
- "image": local error of the mapping (residual distortion, misfit, terrain), the part that affects
  relative positions.

Version 0.1 gives both as constant over the image. Consumers add their own pixel-level error through
`jacobian`, i.e. J @ Sigma_px @ J.T.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

EARTH_RADIUS_M = 6371000.0
# A file's reprojection RMSE describes training points only; the spec's default doubles it (SPEC P7)
TRAINING_RMSE_FACTOR = 2.0
# Georef keys read as quality information (all optional)
QUALITY_KEYS = ("quality_spec", "transform_source", "leave_one_out", "validation", "terrain", "adjustment",
                "reprojection_error", "validation_error")


def jacobian(transformer, pixel_x: float, pixel_y: float) -> np.ndarray:
    """2x2 derivative of ground position (metres, east/north) with respect to pixel (u, v)."""
    h = transformer.transform_matrix
    p = h @ np.array([pixel_x, pixel_y, 1.0])
    if transformer.method == "homography":
        x, y = p[0] / p[2], p[1] / p[2]
        return np.array([[h[0, 0] - x * h[2, 0], h[0, 1] - x * h[2, 1]],
                         [h[1, 0] - y * h[2, 0], h[1, 1] - y * h[2, 1]]]) / p[2]
    # Affine output is lon/lat in degrees: scale to metres at that latitude
    lat = math.radians(p[1])
    per_degree = math.radians(1.0) * EARTH_RADIUS_M
    return np.array([[h[0, 0] * per_degree * math.cos(lat), h[0, 1] * per_degree * math.cos(lat)],
                     [h[1, 0] * per_degree, h[1, 1] * per_degree]])


def position_covariance(transformer, pixel_x: float | None = None, pixel_y: float | None = None) -> dict[str, Any]:
    """Georeference error at a pixel as {"datum": 2x2, "image": 2x2} in m^2, plus where each came from.

    The pixel is accepted for a position-dependent model later; in 0.1 both parts are constant.
    """
    image_rms, image_basis, image_source = _image_rms(transformer.quality)
    datum, datum_basis, datum_source = _datum(transformer.quality, image_rms)
    return {"image": _isotropic(image_rms), "datum": datum,
            "basis": {"image": image_basis, "datum": datum_basis},
            "source": {"image": image_source, "datum": datum_source}}


def _image_rms(quality: dict) -> tuple[float | None, str, str]:
    """2D RMS of the local error, from the most honest figure the file has."""
    validation = quality.get("validation") or {}
    if validation.get("internal"):
        return validation["internal"]["value"], "measured", "validation.internal"
    residuals = quality.get("training_residuals_m")
    if quality.get("transform_source") == "drone_assisted" and residuals:
        # The points only refine a camera model, so their residuals are an independent check
        rms = math.sqrt(sum(e * e + n * n for e, n in residuals) / len(residuals))
        return rms, "measured", "control_points.residual_m"
    if quality.get("leave_one_out"):
        return quality["leave_one_out"]["value"], "derived", "leave_one_out"
    if (quality.get("validation_error") or {}).get("rmse_meters"):
        return quality["validation_error"]["rmse_meters"], "measured", "validation_error.rmse_meters"
    if (quality.get("reprojection_error") or {}).get("rmse_meters"):
        rmse = quality["reprojection_error"]["rmse_meters"] * TRAINING_RMSE_FACTOR
        return rmse, "assumed", "reprojection_error.rmse_meters x 2"
    return None, "unknown", "none"


def _datum(quality: dict, image_rms: float | None) -> tuple[np.ndarray | None, str, str]:
    """Common shift of the whole georeference: measured from validation points, else assumed like the image part."""
    shift = ((quality.get("validation") or {}).get("datum") or {}).get("shift_m")
    if shift:
        return np.diag([shift[0] ** 2, shift[1] ** 2]), "derived", "validation.datum.shift_m"
    return _isotropic(image_rms), "assumed" if image_rms is not None else "unknown", "same as image"


def _isotropic(rms_2d: float | None) -> np.ndarray | None:
    """Per-axis variance of an isotropic 2D error with the given RMS (rms^2 = var_e + var_n)."""
    return None if rms_2d is None else np.eye(2) * (rms_2d ** 2 / 2)

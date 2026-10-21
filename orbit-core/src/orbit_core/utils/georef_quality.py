"""Quality of a georeference beyond the fit RMSE (scenario-uncertainty `georef` profile, SPEC P2).

Shared by the georef export and tools/georef_diagnostics.py.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

import numpy as np
from scenario_uncertainty import SPEC_ID, Basis, Level, Q, Stat, Unit, provenance

if TYPE_CHECKING:
    from orbit_core.models.project import ControlPoint, Project
    from orbit_core.utils.coordinate_transform import CoordinateTransformer

# Placing a point to the nearest screen pixel: uniform error over 1/zoom image px, sigma = width/sqrt(12)
QUANTISATION_SIGMA_FACTOR = 1 / math.sqrt(12)
MIN_POINTS_FOR_SPLIT = 3
MIN_POINTS_FOR_PLANE = 4
# Pixel grid (per axis) on which the size of the alignment correction is evaluated
CORRECTION_GRID = 9
# Altitude deviation from the best-fit plane above which flat-ground mapping errors become noticeable
NONPLANAR_TERRAIN_M = 0.3
# Fit RMSE below which, with more than the minimum points, the pixels cannot have been clicked
EXACT_FIT_M = 0.001


def rms(vectors: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.sum(np.asarray(vectors) ** 2, axis=1)))) if len(vectors) else float("nan")


def metric_residuals(transformer: CoordinateTransformer, points: list[ControlPoint]) -> np.ndarray:
    """(n, 2) residuals in metres: transformed pixel minus known position, in the transformer's metric frame."""
    return np.array([np.subtract(transformer.pixel_to_meters(cp.pixel_x, cp.pixel_y),
                                 transformer.latlon_to_meters(cp.latitude, cp.longitude))
                     for cp in points], dtype=float).reshape(-1, 2)


def pixel_residuals(transformer: CoordinateTransformer, points: list[ControlPoint]) -> np.ndarray:
    """(n, 2) residuals in pixels: projection of the known position minus the point's pixel."""
    return np.array([np.subtract(transformer.geo_to_pixel(cp.longitude, cp.latitude), (cp.pixel_x, cp.pixel_y))
                     for cp in points], dtype=float).reshape(-1, 2)


def leave_one_out(transformer: CoordinateTransformer) -> np.ndarray | None:
    """Residual of each training point predicted by a refit without it (None if the transformer can't refit)."""
    training = transformer.training_points
    if len(training) <= transformer.MIN_TRAINING_POINTS or transformer.MIN_TRAINING_POINTS == 0:
        return None
    others = [cp for cp in transformer.all_control_points if cp.is_validation]
    out = []
    for i, cp in enumerate(training):
        refit = transformer.refit(training[:i] + training[i + 1:] + others)
        out.append(metric_residuals(refit, [cp])[0])
    return np.array(out)


def similarity_split(predicted: np.ndarray, true: np.ndarray) -> dict:
    """Split georef errors (predicted - true) into a common 2D similarity (datum) and the internal remainder."""
    centre = true.mean(0)
    q = true - centre
    design = np.zeros((2 * len(q), 4))
    design[0::2] = np.c_[q[:, 0], -q[:, 1], np.ones(len(q)), np.zeros(len(q))]
    design[1::2] = np.c_[q[:, 1], q[:, 0], np.zeros(len(q)), np.ones(len(q))]
    a, b, tx, ty = np.linalg.lstsq(design, predicted.reshape(-1), rcond=None)[0]
    fitted = (design @ [a, b, tx, ty]).reshape(-1, 2)
    return {"shift_m": [round(float(tx - centre[0]), 3), round(float(ty - centre[1]), 3)],
            "rotation_deg": round(math.degrees(math.atan2(b, a)), 4),
            "scale_ppm": round((math.hypot(a, b) - 1) * 1e6),
            "internal_rms_m": round(rms(predicted - fitted), 3)}


def terrain_plane(transformer: CoordinateTransformer, points: list[ControlPoint]) -> dict | None:
    """Best-fit plane through the surveyed altitudes and the deviation of the points from it."""
    known = [cp for cp in points if cp.altitude is not None]
    if len(known) < MIN_POINTS_FOR_PLANE:
        return None
    xy = np.array([transformer.latlon_to_meters(cp.latitude, cp.longitude) for cp in known])
    z = np.array([cp.altitude for cp in known])
    design = np.c_[xy - xy.mean(0), np.ones(len(xy))]
    plane = np.linalg.lstsq(design, z, rcond=None)[0]
    dz = z - design @ plane
    return {"slope": [round(float(plane[0]), 5), round(float(plane[1]), 5)], "z_centre_m": round(float(plane[2]), 3),
            "residual": _q(float(dz.std()), Unit.M, Stat.SIGMA, Level.IMAGE, Basis.MEASURED, n=len(known),
                           note="deviation of surveyed altitudes from the best-fit plane")}


def _q(value, unit, stat, level, basis, **extra) -> dict:
    return Q(value, unit, stat, level, basis, **extra).to_dict()


def control_point_quality(cp: ControlPoint, residual_m, residual_px) -> dict:
    """Georef 1.2 per-point keys (all optional)."""
    out: dict[str, Any] = {}
    if cp.altitude is not None:
        out["altitude_m"] = cp.altitude
    for key in ("sigma_h_m", "sigma_v_m", "point_type", "pick_zoom", "pixel_clicked"):
        if getattr(cp, key) is not None:
            out[key] = getattr(cp, key)
    if cp.pick_zoom:
        out["sigma_px_quantisation"] = round(QUANTISATION_SIGMA_FACTOR / cp.pick_zoom, 4)
    if residual_m is not None:
        out["residual_m"] = [round(float(v), 4) for v in residual_m]
    if residual_px is not None:
        out["residual_px"] = [round(float(v), 3) for v in residual_px]
    return out


def adjustment_block(project: Project, transformer: CoordinateTransformer, image_size,
                     final_matrix: np.ndarray | None) -> dict:
    """How the matrix relates to the user's clicks: fit to the clicks, adjustments applied, size of the correction."""
    from orbit_core.utils.coordinate_transform import DroneAssistedTransformer

    if isinstance(transformer, DroneAssistedTransformer):
        stored = transformer.adjustment
        if stored is None or stored.is_identity():
            return {"method": "none", "H_fit": None, "A": None, "magnitude": None}
        unadjusted = transformer.refit(transformer.all_control_points)
        return {"method": "stored", "H_fit": None, "A": stored.get_adjustment_matrix().tolist(),
                "magnitude": _correction_magnitude(unadjusted, transformer, image_size)}
    training = transformer.training_points
    clicked = [cp.pixel_clicked for cp in training]
    if any(c is None for c in clicked):
        method = "unknown" if not project.baked_adjustments else "partly_unknown"
        return {"method": method, "H_fit": None, "A": _composed(project.baked_adjustments), "magnitude": None}
    if not project.baked_adjustments and all(list(c) == [cp.pixel_x, cp.pixel_y] for c, cp in zip(clicked, training)):
        return {"method": "none", "H_fit": _matrix(final_matrix), "A": None,
                "magnitude": _q(0.0, Unit.M, Stat.MAX, Level.IMAGE, Basis.MEASURED)}
    fitted_to_clicks = transformer.refit([_with_pixel(cp, cp.pixel_clicked) if cp.pixel_clicked else cp
                                          for cp in transformer.all_control_points])
    return {"method": "baked", "H_fit": _matrix(fitted_to_clicks.transform_matrix),
            "A": _composed(project.baked_adjustments),
            "magnitude": _correction_magnitude(fitted_to_clicks, transformer, image_size)}


def _correction_magnitude(before: CoordinateTransformer, after: CoordinateTransformer, image_size) -> dict:
    """Largest ground displacement (m) between two georeferences over the image."""
    width, height = image_size
    worst = 0.0
    for u in np.linspace(0, width, CORRECTION_GRID):
        for v in np.linspace(0, height, CORRECTION_GRID):
            worst = max(worst, math.dist(before.pixel_to_meters(u, v), after.pixel_to_meters(u, v)))
    return _q(round(worst, 3), Unit.M, Stat.MAX, Level.IMAGE, Basis.MEASURED,
              note="largest displacement of the alignment correction over the image")


def _with_pixel(cp: ControlPoint, pixel) -> ControlPoint:
    from dataclasses import replace
    return replace(cp, pixel_x=float(pixel[0]), pixel_y=float(pixel[1]))


def _composed(records: list[dict]) -> list | None:
    if not records:
        return None
    total = np.eye(3)
    for record in records:
        total = np.array(record["matrix"]) @ total
    return total.tolist()


def _matrix(matrix) -> list | None:
    return None if matrix is None else np.asarray(matrix, dtype=float).tolist()


def quality_keys(project: Project, transformer: CoordinateTransformer, image_size,
                 final_matrix: np.ndarray | None) -> dict:
    """Top-level georef 1.2 keys: spec version, method, leave-one-out, validation split, terrain, adjustment."""
    keys: dict[str, Any] = {"quality_spec": SPEC_ID, "transform_source": transform_source(transformer)}
    loo = leave_one_out(transformer)
    if loo is not None:
        keys["leave_one_out"] = _q(round(rms(loo), 3), Unit.M, Stat.RMS, Level.IMAGE, Basis.DERIVED, n=len(loo),
                                   note="each training point predicted by a fit without it")
    validation = transformer.validation_points
    if len(validation) >= MIN_POINTS_FOR_SPLIT:
        res = metric_residuals(transformer, validation)
        true = np.array([transformer.latlon_to_meters(cp.latitude, cp.longitude) for cp in validation])
        split = similarity_split(true + res, true)
        keys["validation"] = {
            "rms": _q(round(rms(res), 3), Unit.M, Stat.RMS, Level.IMAGE, Basis.MEASURED, n=len(validation)),
            "datum": {k: split[k] for k in ("shift_m", "rotation_deg", "scale_ppm")},
            "internal": _q(split["internal_rms_m"], Unit.M, Stat.RMS, Level.IMAGE, Basis.MEASURED, n=len(validation)),
        }
    terrain = terrain_plane(transformer, transformer.all_control_points)
    if terrain:
        keys["terrain"] = terrain
    keys["adjustment"] = adjustment_block(project, transformer, image_size, final_matrix)
    return keys


def transform_source(transformer: CoordinateTransformer) -> str:
    """What produced the matrix; transform_method stays "homography"/"affine" for older readers."""
    from orbit_core.utils.coordinate_transform import (
        AffineTransformer,
        DroneAssistedTransformer,
        HomographyTransformer,
        HybridTransformer,
    )
    for kind, name in ((DroneAssistedTransformer, "drone_assisted"), (HybridTransformer, "hybrid"),
                       (HomographyTransformer, "homography"), (AffineTransformer, "affine")):
        if isinstance(transformer, kind):
            return name
    return "unknown"


def provenance_summary(data: dict[str, Any]) -> dict[str, Any]:
    """dataprov custom properties and [su:...] warning lines for an exported georef (see quality_keys)."""
    WarningCode = provenance.WarningCode
    summary, lines = {}, []
    internal = (data.get("validation") or {}).get("internal") or data.get("leave_one_out")
    if internal:
        summary["georef_internal_error"] = internal
    adjustment = data.get("adjustment") or {}
    magnitude = adjustment.get("magnitude")
    if magnitude:
        summary["adjustment_magnitude"] = magnitude
        if internal and magnitude["value"] > internal["value"]:
            lines.append(provenance.warning_line(
                WarningCode.ADJUSTMENT_EXCEEDS_VALIDATION,
                f"manual alignment moves the georeference up to {magnitude['value']:.2f} m, more than its "
                f"internal error {internal['value']:.2f} m"))
    if adjustment.get("method") in ("unknown", "partly_unknown"):
        lines.append(provenance.warning_line(
            WarningCode.ADJUSTMENT_UNKNOWN, "original clicks not recorded; any manual adjustment can't be separated"))
    terrain = (data.get("terrain") or {}).get("residual")
    if terrain:
        summary["terrain_residual"] = terrain
        if terrain["value"] > NONPLANAR_TERRAIN_M:
            lines.append(provenance.warning_line(
                WarningCode.NONPLANAR_TERRAIN,
                f"surveyed altitudes deviate {terrain['value']:.2f} m (std) from a plane; flat-ground mapping errors"))
    training = [cp for cp in data.get("control_points", []) if not cp.get("is_validation")]
    fit = (data.get("reprojection_error") or {}).get("rmse_meters")
    if fit is not None and fit < EXACT_FIT_M and len(training) > 4 and data.get("transform_source") != "drone_assisted":
        lines.append(provenance.warning_line(
            WarningCode.CONTROL_POINTS_COMPUTED, "control points fit exactly; pixels were computed, not clicked"))
    return {"custom_properties": provenance.custom_properties(summary), "warning_lines": lines}

"""Check the quality of exported ORBIT georeferences (georef JSON) beyond the fit RMSE.

Reports, per georef file:
- fit RMSE and leave-one-out (LOO) RMSE: each training point predicted by a fit without it, an honest
  estimate of the error away from the points;
- warnings for weak geometry (LOO much larger than the fit) and for pixel positions that fit exactly
  (computed, not clicked, so the residuals mean nothing);
- validation RMSE and, with at least 3 validation points, its split into a common (datum) part
  (2D similarity: shift, rotation, scale) and the internal remainder;
- optionally a terrain test: do the residuals point away from the drone in proportion to each point's
  height above the best-fit plane, as a flat-ground homography predicts?

See tools/README.md for usage.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from orbit_core.models.project import ControlPoint
from orbit_core.utils.coordinate_transform import HomographyTransformer
from orbit_core.utils.georef_quality import metric_residuals, rms, similarity_split

# Below this fit RMSE with more than the minimum points, pixels cannot have been clicked independently
EXACT_FIT_M = 0.001
# LOO RMSE above this multiple of the fit RMSE means the homography is barely determined by its points
WEAK_GEOMETRY_RATIO = 3.0
RECOMMENDED_MIN_POINTS = 8
# Mean offset between the exported matrix and the declared projection beyond which the matrix is in another frame
FRAME_MISMATCH_M = 1000.0
MIN_POINTS_FOR_SPLIT = 3


def load_control_points(georef: dict) -> list[ControlPoint]:
    return [ControlPoint(pixel_x=c["pixel_x"], pixel_y=c["pixel_y"], longitude=c["longitude"],
                         latitude=c["latitude"], name=c.get("name", ""),
                         is_validation=bool(c.get("is_validation", False)))
            for c in georef["control_points"]]


def exported_matrix_check(georef: dict, points: list[ControlPoint]) -> dict | None:
    """Residuals of the exported matrix itself, in the declared proj_string frame.

    For drone-assisted georefs this is the meaningful error: their matrix comes from the camera model, and the
    control points only refine it, so a homography refit to the points says little about the export.
    """
    if not georef.get("proj_string") or "transformation_matrix" not in georef:
        return None
    from pyproj import Proj

    proj = Proj(georef["proj_string"])
    matrix = np.array(georef["transformation_matrix"], dtype=float)
    pixels = np.array([[cp.pixel_x, cp.pixel_y, 1.0] for cp in points]) @ matrix.T
    errors = pixels[:, :2] / pixels[:, 2:3] - np.array([proj(cp.longitude, cp.latitude) for cp in points])
    offset = errors.mean(0)
    mismatch = bool(np.linalg.norm(offset) > FRAME_MISMATCH_M)
    # In a mismatched frame only the scatter about the offset is meaningful
    return {"exported_rms_m": round(rms(errors - offset if mismatch else errors), 3),
            "mean_offset_m": [round(float(v), 1) for v in offset], "frame_mismatch": mismatch}


def leave_one_out(points: list[ControlPoint], proj: str) -> np.ndarray:
    """Residual of each training point predicted by a fit to the other training points."""
    training = [cp for cp in points if not cp.is_validation]
    out = []
    for i, cp in enumerate(training):
        others = training[:i] + training[i + 1:]
        out.append(metric_residuals(HomographyTransformer(others, export_proj_string=proj), [cp])[0])
    return np.array(out)


def load_altitudes(rtk_csv: Path) -> dict[str, float]:
    with open(rtk_csv, newline="") as f:
        return {row["point_name"].strip(): float(row["altitude"]) for row in csv.DictReader(f)
                if row.get("altitude") not in (None, "", "/")}


def load_drone(flight_record: Path) -> tuple[float, float, float]:
    """(lat, lon, height above ground) means from a FieldDataLab FlightRecord_*.video_stats.json."""
    data = json.loads(flight_record.read_text())
    osd = data.get("sequences", [data])[0]["stats"]["osd"]
    return osd["latitude"]["mean"], osd["longitude"]["mean"], osd["height_agl"]["mean"]


def terrain_test(transformer, training, loo_res, altitudes, drone) -> dict | None:
    """Fit residual ~ k * (point - drone) * dz, dz = height above the best-fit plane; expected k = 1/height."""
    known = [(cp, altitudes[cp.name]) for cp in training if cp.name in altitudes]
    if len(known) < 5 or len(known) != len(training):
        return None
    xy = np.array([transformer.latlon_to_meters(cp.latitude, cp.longitude) for cp, _ in known])
    z = np.array([alt for _, alt in known])
    plane_design = np.c_[xy - xy.mean(0), np.ones(len(xy))]
    plane = np.linalg.lstsq(plane_design, z, rcond=None)[0]
    dz = z - plane_design @ plane
    drone_xy = np.array(transformer.latlon_to_meters(drone[0], drone[1]))
    basis = (xy - drone_xy) * dz[:, None]
    k = float(np.sum(basis * loo_res) / np.sum(basis ** 2))
    return {"dz_std_m": round(float(dz.std()), 2), "slope_pct": [round(float(s) * 100, 2) for s in plane[:2]],
            "k_fit": round(k, 4), "k_expected": round(1 / drone[2], 4),
            "predicted_shift_rms_m": round(rms(basis / drone[2]), 3),
            "loo_rms_after_terrain_m": round(rms(loo_res - basis / drone[2]), 3)}


def diagnose(path: Path, rtk_csv: Path | None = None, flight_record: Path | None = None) -> dict:
    georef = json.loads(path.read_text())
    points = load_control_points(georef)
    training = [cp for cp in points if not cp.is_validation]
    validation = [cp for cp in points if cp.is_validation]
    result: dict = {"file": str(path), "n_training": len(training), "n_validation": len(validation), "warnings": []}
    if len(training) < HomographyTransformer.MIN_TRAINING_POINTS:
        result["warnings"].append("fewer than 4 training points: no homography")
        return result
    # Metric frame shared by all refits: the export's projection, else UTM from the points
    proj = georef.get("proj_string") or HomographyTransformer(points).get_utm_projection_string()
    transformer = HomographyTransformer(points, export_proj_string=proj)
    fit = metric_residuals(transformer, training)
    result["fit_rms_m"] = round(rms(fit), 3)
    exported = exported_matrix_check(georef, training)
    if exported:
        result["exported_rms_m"] = exported["exported_rms_m"]
        if exported["frame_mismatch"]:
            result["warnings"].append(
                f"exported matrix is not in the proj_string frame (mean offset {exported['mean_offset_m']} m): "
                "drone-assisted export writes local ENU around the drone; consumers will misplace everything. "
                "exported_rms_m is the scatter about that offset")
    if len(training) == HomographyTransformer.MIN_TRAINING_POINTS:
        result["warnings"].append("exactly 4 training points: no redundancy, errors are not observable")
        return result
    if rms(fit) < EXACT_FIT_M:
        result["warnings"].append("fits exactly: pixel positions were computed from the geo positions, not clicked")
    loo = leave_one_out(points, proj)
    worst = int(np.argmax(np.linalg.norm(loo, axis=1)))
    result.update({"loo_rms_m": round(rms(loo), 3), "loo_max_m": round(float(np.linalg.norm(loo[worst])), 3),
                   "loo_worst_point": training[worst].name})
    if rms(loo) > WEAK_GEOMETRY_RATIO * max(rms(fit), EXACT_FIT_M):
        result["warnings"].append("leave-one-out error much larger than fit: weak geometry, add well-spread points")
    if len(training) < RECOMMENDED_MIN_POINTS:
        result["warnings"].append(f"only {len(training)} training points (recommended >= {RECOMMENDED_MIN_POINTS})")
    if validation:
        val = metric_residuals(transformer, validation)
        result["validation_rms_m"] = round(rms(val), 3)
        if len(validation) >= MIN_POINTS_FOR_SPLIT:
            true = np.array([transformer.latlon_to_meters(cp.latitude, cp.longitude) for cp in validation])
            result["validation_split"] = similarity_split(true + val, true)
    if rtk_csv and flight_record:
        terrain = terrain_test(transformer, training, loo, load_altitudes(rtk_csv), load_drone(flight_record))
        if terrain:
            result["terrain"] = terrain
        else:
            result["warnings"].append("terrain test skipped: altitudes missing for some training points")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("georef", nargs="+", type=Path, help="ORBIT georef JSON file(s)")
    parser.add_argument("--rtk-csv", type=Path, help="RTK point CSV with point_name and altitude (terrain test)")
    parser.add_argument("--flight-record", type=Path,
                        help="FlightRecord_*.video_stats.json with drone position and height (terrain test)")
    parser.add_argument("--json", action="store_true", help="Print one JSON object per file")
    return parser


def print_summary(result: dict) -> None:
    print(result["file"])
    keys = ("n_training", "n_validation", "fit_rms_m", "exported_rms_m", "loo_rms_m", "loo_max_m",
            "loo_worst_point", "validation_rms_m")
    print("  " + ", ".join(f"{k}={result[k]}" for k in keys if k in result))
    for section in ("validation_split", "terrain"):
        if section in result:
            print(f"  {section}: " + ", ".join(f"{k}={v}" for k, v in result[section].items()))
    for warning in result["warnings"]:
        print(f"  WARNING: {warning}")


def main() -> None:
    args = build_parser().parse_args()
    for path in args.georef:
        result = diagnose(path, args.rtk_csv, args.flight_record)
        if args.json:
            print(json.dumps(result))
        else:
            print_summary(result)


if __name__ == "__main__":
    main()

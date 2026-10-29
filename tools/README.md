# ORBIT tools

Developer and analysis scripts. They are not part of the ORBIT GUI or the `orbit-core` API. Run them from the
repository root with `uv run python tools/<script>.py`.

| Script | Purpose |
|---|---|
| `maintainability_report.py` | Function-length and coverage metrics for the source tree (used in CI) |
| `georef_diagnostics.py` | Quality check of exported georeferences, beyond the fit RMSE |

## georef_diagnostics.py

The RMSE that ORBIT reports for training points only shows how well the homography fits the points it was fitted
to. This script estimates how wrong positions are *between* the points, and flags georeferences that should not be
trusted.

```bash
# One or more georef files
uv run python tools/georef_diagnostics.py path/to/VIDr_ff_<ts>_georef.json [more_georef.json ...]

# With the terrain test: RTK point CSV (needs point_name and altitude) and the drone flight record
uv run python tools/georef_diagnostics.py path/to/VIDr_ff_<ts>_georef.json \
    --rtk-csv path/to/<Location>_coords_visualmarkers.csv \
    --flight-record path/to/FlightRecord_<ts>.video_stats.json

# Machine-readable output, one JSON object per file
uv run python tools/georef_diagnostics.py --json path/to/*_georef.json > diagnostics.jsonl
```

The fits use `orbit_core`'s `HomographyTransformer`, so the numbers match ORBIT's own fit.

### What it reports

| Field | Meaning |
|---|---|
| `fit_rms_m` | Residual of the training points under a homography refitted to them (what ORBIT shows for homography projects) |
| `exported_rms_m` | Residual of the points under the matrix actually *in the file*, in its `proj_string` frame. For **drone-assisted** georefs this is the meaningful error, because their matrix comes from the camera model (drone position, height, heading, gimbal) and the points only refine it. |
| `loo_rms_m`, `loo_max_m`, `loo_worst_point` | **Leave-one-out:** each training point predicted by a fit to the others. An honest estimate of the error away from the points. Expect roughly 1.5–2× `fit_rms_m`. |
| `validation_rms_m` | Residual of points marked as validation (not used for fitting) |
| `validation_split` | With at least 3 validation points: the validation error split into a **common part** (2D similarity: `shift_m`, `rotation_deg`, `scale_ppm`, as georef minus truth) and the **internal** remainder (`internal_rms_m`). The common part shifts the whole scene, including a map drawn on the same image, so it cancels for vehicle sizes and distances. The internal part does not. |
| `terrain` | Tests whether residuals point away from the drone in proportion to each point's height `dz` above the best-fit plane, as a flat-ground homography predicts. `k_fit` close to `k_expected` (1 / drone height) means terrain is a real error source. `loo_rms_after_terrain_m` is the error left once the predicted terrain shift is removed. |

### Warnings

| Warning | Meaning and what to do |
|---|---|
| `fits exactly: pixel positions were computed ...` | Fit RMSE below 1 mm with more than 4 points. Real clicks never fit that well, so the pixel positions were recomputed from the geo positions. ORBIT's aerial-view round trip did that before commit `bc8784d` (2026-04-29). The matrix is still the original fit, but the residuals say nothing and the points no longer mark the landmarks. Re-click the points to measure accuracy. |
| `leave-one-out error much larger than fit` | The homography is barely determined by its points (typically with few or badly spread points), so positions away from the points can be metres off. Add points spread over the whole image. |
| `only N training points` | Fewer than 8 training points. |
| `exactly 4 training points` | No redundancy: any error is invisible. |
| `exported matrix is not in the proj_string frame` | The matrix maps to another frame than the declared projection. Drone-assisted exports currently write local ENU metres around the drone while declaring UTM, so every consumer (orbit-georef, COSMO) misplaces everything by hundreds of km. `exported_rms_m` then shows the scatter about that offset. |

### Notes and limits

- **Drone-assisted georefs.** The export labels them `homography`, so the tool can't tell them apart. For them,
  `loo_rms_m` and the weak-geometry warning describe a homography refit to the few points, not the exported
  matrix. Use `exported_rms_m` instead.
- **No validation points means no split.** Without validation points the common (datum) error can't be measured.
  The training points define the fit, and a manual alignment is baked into the clicked pixels on Apply/export.
- **Terrain test data.** `--flight-record` is FieldDataLab's `FlightRecord_*.video_stats.json`; the mean drone
  position and height above ground are used. The test needs altitudes for all training points.
- **Projection.** Files without `proj_string` (format 1.0) are analysed in UTM. That is computed from the points
  and does not change the results.

## attach_altitudes.py

Fills in surveyed altitudes, RTK SDs and point type from a survey CSV (e.g. `*_coords_visualmarkers.csv`) on the
control points of an existing ORBIT project, matched by point name. Projects made before ORBIT stored altitudes have
none, and the CSV import re-places points by clicking; with altitudes, the georef export fits the camera model over
terrain and the OpenDRIVE export can write road elevation.

```bash
uv run python tools/attach_altitudes.py project.orbit survey.csv            # report only
uv run python tools/attach_altitudes.py project.orbit survey.csv --write    # update; backup project.orbit.bak
```

- Names match case-insensitively, ignoring surrounding spaces. A match whose surveyed position is more than
  `--max-distance` (default 1 m) from the point's coordinates is rejected (wrong CSV or reused name); names repeated
  in the CSV are skipped.
- Fields that are already set are kept unless `--overwrite`. Only the control points' survey fields change; the rest
  of the `.orbit` file is written back unchanged.
- Re-export the georeference afterwards (and the OpenDRIVE map with "Road elevation from control-point altitudes").


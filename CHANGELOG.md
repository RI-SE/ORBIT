# ORBIT Changelog

All notable changes to this project are documented in this file.

**Current Version**: 0.17.0

---

> **Note**: entries for 0.6.1–0.14.0, 0.15.1 and 0.16.x were written afterwards from the commit history
> (2026-10-29), so they are less detailed than the others.

## [0.17.0] - 2026-10-29

Packages: `orbit-georef` 0.2.0 (tag `orbit-georef-v0.2.0`); `orbit-core` and `opendrive-map` unchanged in version.

### Added
- **Georef format 1.2 with quality information**, following the `georef` profile of
  [scenario-uncertainty](https://github.com/das-rise/scenario-uncertainty) 0.1.0:
  - leave-one-out errors;
  - validation split into a common `datum` part (shift, rotation, scale) and the `internal` remainder;
  - terrain deviation from a plane;
  - how far a manual adjustment moved the georeference;
  - per point: residuals, RTK SDs, altitude and pick zoom;
  - `transform_source` (`homography`, `hybrid`, `affine` or `drone_assisted`).

  Older files simply lack these keys. Control points keep RTK SDs and altitude from the CSV import, and the
  provenance records headline quality numbers and `[su:*]` warnings.
- **Camera model over terrain (G11):** georef export adds an optional `camera_model` section when at least 6
  control points have RTK altitude and the view is oblique: pinhole camera (focal from the homography, refined
  with the pose on the 3D points) plus a smooth terrain surface fitted to the altitudes. orbit-georef reads it
  (`pixel_to_ground_3d`, `ground_to_pixel_3d`, `terrain_height`, `fit_camera_model`, `georef_from_data`); the
  homography is unchanged. On campaign georefs it lowers leave-one-out error at hilly sites (GbgSaroRound
  0.95 → 0.84 m, BorasEkas 2025-09-25 0.85 → 0.67 m) and is slightly worse on flat ones; both figures are recorded.
- Provenance of saves and exports marks the written file with the dataprov output role `primary`; requires
  `dataprov>=3.4.0` (provenance extra).
- **`tools/attach_altitudes.py`:** attaches surveyed altitudes, RTK SDs and point type from a survey CSV to an
  existing project's control points by name (rejects matches more than 1 m apart), so older projects can use the
  camera model and road elevation. CSV parsing moved to `orbit_core.utils.control_point_csv` (shared with the import
  dialog).
- **Road elevation from terrain:** OpenDRIVE export option "Road elevation from control-point altitudes"
  (`elevation_from_terrain`, off by default): elevation profiles follow the terrain surface (absolute altitude).

- **`tools/georef_diagnostics.py`:** checks a georef JSON:
  - leave-one-out and validation errors;
  - terrain effect;
  - computed (not clicked) control points;
  - drone-assisted exports written with the bug fixed below.

### Fixed
- CSV import dropped a whole point when its altitude was `/` (survey exports' "not measured"); it is now read as
  unknown, like the SD columns.
- **Georef quality numbers were wrong:**
  - training `rmse_pixels` was a pixel→geo→pixel round trip, and so ~0; it is now the true residual;
  - Monte Carlo, bootstrap and leave-one-out refitted a plain homography instead of the project's transformer
    (hybrid / drone-assisted);
  - failed Monte Carlo samples were not left out.
- **Drone-assisted projects exported an erroneous georeference:** it was not in the declared projection, lacked the
  manual adjustment and the grid rotation, and lost the flight metadata on refit. Re-export affected georefs;
  `tools/georef_diagnostics.py` detects them.

### orbit-georef 0.2.0
- `transformer.quality` with the 1.2 quality keys, plus:
  - `jacobian(px, py)`;
  - `position_covariance(px, py)`, split into `image` and `datum` parts.
- `CameraModel`, `TerrainSurface`, `fit_camera_model`, `focal_from_homography`, `georef_from_data`, and on the
  transformer `pixel_to_ground_3d`, `ground_to_pixel_3d` and `terrain_height`. These are used only when the file has a
  `camera_model` section.
- Control points read and write `altitude_m`.
- A legacy `transform_method: "unknown"` is read as homography when the matrix has perspective terms (with a
  warning). Unsupported methods raise a clear error.

---

## [0.16.1] - 2026-10-21

### Added
- **Add a connecting road to a junction by hand** (with undo): pick the two roads, and the geometry, lane counts and
  lane connections are built by the same code the junction analyzer uses.
- **Junction validator** (`orbit_core.export.junction_validator`), with results shown in the export dialog:
  - movements wired to missing lanes;
  - connecting-road lanes of mismatched width;
  - driving lanes left without a movement.

### Changed
- One label format for entities with an ID everywhere in the GUI: `[11] Name (seg 1/2)`.
- Lane, road, section, signal and junction property dialogs reworked for consistency.
- Sign images moved into `orbit_core` (`orbit_core/signs/`).

---

## [0.16.0] - 2026-09-10

Release of the `orbit-core` extraction (0.15.0) and the 0.15.1 fixes (PR #32); dependency lock updated.

---

## [0.15.1] - 2026-08-22

### Fixed
- **Signals could be exported past the end of the road carrying them**, which makes the
  whole map unloadable (esmini: `Signal ... s value exceeds road length`). Signals are
  projected onto the centerline, but the exported road length comes from fitted geometry,
  so the two disagree; `s` is now clamped just inside the road it is written under.
- **Signals were attached to the wrong road segment after a split.** The OSM-node index
  was built from each road's originating way, but roads are split at junction nodes
  before signals are attached, so one way's node list covers several roads -- every node
  was offered to every segment and the first in the list won. The index is now built from
  each road's own centerline, and a node shared by several roads (a junction node belongs
  to every approach) goes to the road the signal actually stands closest to, preferring
  regular roads over connecting roads.
- **Junctions could reference roads that were not written**, leaving a dangling
  `incomingRoad`/`connectingRoad` that makes readers reject the file. Roads may be dropped
  during a write while the junction is still built from the project. Such connections are
  now omitted and reported.

### Added
- `warnings_out` on `export_to_opendrive` and `opendrive_from_osm_data`, and
  `OpenDriveWriter.export_warnings`: parts of the project the writer had to omit to keep
  the file valid. A degraded export still succeeds and looks correct, so this is the only
  way a caller learns the map is incomplete. Both parameters are optional; existing
  callers are unaffected. The export dialog shows them.

---

## [0.15.0] - 2026-08

### Changed
- **Extracted `orbit-core`**, a headless MIT library holding the road-network model,
  OSM/OpenDRIVE import and OpenDRIVE export. The ORBIT application is now a PyQt6 shell
  over it, and its GPL-3.0 terms no longer reach the road-building logic.
  `orbit.models` / `orbit.export` / `orbit.utils` / `orbit.import` moved to
  `orbit_core.models` / `.export` / `.utils` / `.importers`.
- `orbit/import/` renamed to `orbit_core/importers/`. The directory was named after a
  Python keyword, so every access previously went through `importlib.import_module`;
  those workarounds are gone.
- Optional dependencies (`opencv-python`, `geomag`, `xmlschema`, `dataprov`) are now
  extras of `orbit-core`, so a headless install pulls only numpy/scipy/pyproj/lxml.
- Logging namespaces are now `orbit_core` and `orbit`; `setup_logging()` configures both.
- Repository is a uv workspace over `orbit-core`, `orbit-georef` and `opendrive-map`.

### Added
- `orbit_core` public API for building OpenDRIVE from OpenStreetMap with no GUI and no
  imagery: `bbox_from_center`, `osm_data_from_overpass`, `osm_data_from_file`,
  `bbox_of`, `opendrive_from_osm_data`.
- `OSMImporter.import_from_osm_data` is public (was `_import_from_osm_data`), so a
  caller can supply OSM data from any source.

### Removed
- Python 3.10 support. It reaches end of security support in October 2026, nothing in
  the codebase required it, and 3.11 matches the floor of downstream consumers.
  `requires-python` is now `>=3.11` for both packages.

### Fixed
- `get_contact_pos_heading` moved from `orbit/gui/project_controller.py` into
  `orbit_core.utils.geometry`; it is pure geometry and was the only GUI dependency in
  otherwise headless code.
- `orbit-core` no longer depends on the `orbit` application. `Project` metadata read
  its version via `importlib.metadata.version("orbit")`, and two test modules imported
  `orbit.gui`, so the headless library could not be installed or tested on its own.
  The dialog test moved to `tests/unit/test_gui/`.
- CI now lints and tests `orbit-core/`, and measures coverage over both packages.
  After the extraction it was checking only the GUI shell -- 34k lines and 2,562 tests
  had silently dropped out of the pipeline.

---

## [0.14.0] - 2026-07-08
### Added
- Lane edit tools for turn lanes.
### Fixed
- Tool deactivation inconsistencies; visualisation of lane connection reassignment.
### Changed
- User guide updated.

## [0.13.0] - 2026-06-29
### Added
- **`opendrive-map`**: a reusable library for reading OpenDRIVE maps, including parking spaces and robustness checks.
### Changed
- `orbit-georef` API updated (0.1.2).

## [0.12.1] - 2026-06-23
### Fixed
- Objects not updated properly when an adjustment is applied.

## [0.12.0] - 2026-06-18
### Changed
- Improved precision for road rendering.
### Fixed
- Core dump when switching to aerial view; reset of the correction; moving connection points.
- Normal/aerial round trip with drone-assisted homography; an OpenDRIVE import bug.

## [0.11.1] - 2026-06-17
### Fixed
- Coordinate-handling review (prioritised fixes):
  - aerial view now uses Web Mercator correctly;
  - pixel edits made in one view are no longer reverted when switching view (`geo_stale` tracking);
  - exports switch back to the original view first, like save does;
  - a mismatched number of geo points is rebuilt from the pixels;
  - falsy-zero bounds in auto-georeference;
  - OpenDRIVE `header_offset_hdg` is applied;
  - explicit local-metre frames;
  - one shared metres-per-degree constant.

## [0.11.0] - 2026-05-10
### Added
- Georef import; OpenDRIVE import of newer features.
- dataprov provenance support (with a warning if dataprov is missing).
- **Drone-parameter assisted homography**, with composable adjustments.
- Smooth-road function for junction editing; pre-commit hooks (ruff).
### Fixed
- Lane display, guardrail and sign placement, OSM import centre point, the xodr export with the hybrid transformer,
  a cleanup crash, and `width_end = None` in the lane builder (contributed by BastianHavers).

## [0.10.1] - 2026-04-16
### Fixed
- Junction problems; guardrail and parking-space placement in aerial view.

## [0.10.0] - 2026-04-08
### Added
- Georef includes the PROJ string, to match the xodr geo data.
- Editing of land use (already supported by the OSM import); a lane-section merge function.
### Fixed
- Unapplied geo-position adjustments were used; variable lane width issues.

## [0.9.0] - 2026-04-02
### Added
- OpenDRIVE 1.4 / CARLA compatibility mode for the xodr export (keeps vendor data and userData).
- Unified link-editing UI for roads and connecting roads, with a lane-links editor.
- Two-way road support in the junction import.
### Fixed
- Missing lane links on junction-connected roads, the lane-change attribute, broken road marks.
- All export paths now apply the manual alignment adjustment.
- Junction/road ID overlap for CARLA; speed import/export.
- Variable-width roads; lane connections between 1- and 2-lane roads; parking-area edit persistence.
- An erroneous adjust-on-load for `.orbit` files was removed.

## [0.8.0] - 2026-03-23
### Added
- **Automatic homography adjustment** from picked points (least squares), with a ghost overlay of the original lines.
- Objects can be assigned to connecting roads.
### Changed
- Large refactoring: connecting roads and regular roads share one code path; large functions and test files split;
  maintainability report in CI.
### Fixed
- Homography/affine blending: inside the image the homography is always used.
- Bad road geometry warnings and deletion of negative-size lane segments; signals outside the road.
- OSM junction import, undo of polylines, sign/object ID conflict, aerial view issues.

## [0.7.0] - 2026-03-06
### Added
- Custom origin point; new aerial view.
### Fixed
- Road connection logic in the xodr export.
- Pixel-to-metric conversion of some objects (several places used the scale directly).
- Map centring when imported without a georeference.

## [0.6.1] - 2026-02-24
### Added
- Segmentation-mask export.
- OSM export (with lane width and road surface); import of more OSM objects (forest, farmland, buildings, …) and
  their export to xodr.
- Load OpenDRIVE/OSM without an image; remember the last directory for file operations.
- Hybrid transform for imports larger than the image.
- Batch conversion via PROJ strings; latitude of true scale set for much higher precision (pyproj).
### Fixed
- Roundabout wizard; connecting road adjustment; building rotation and placement; OSM junction import; OSM
  attribution and licence information.

---

## [0.6.0] - 2026-02

### Added
- Offset export with configurable lateral offset for lane boundaries
- Projection dropdown in export dialog (UTM auto-detect, custom PROJ4)
- Origin selector for export coordinate reference
- CI pipeline with linting and multi-Python testing
- Comprehensive test suite (2,363+ tests)

### Changed
- Replaced print() calls with structured logging throughout codebase
- Standardized QMessageBox usage via message helper functions
- Improved signal code handling in export
- Version bump for public release

### Fixed
- UTM output coordinate offset
- Import bug for connecting road endpoint connections
- OpenDRIVE import bug when schema is defined

---

## [0.5.0] - 2026-02

### Added
- Undo/redo system (partial — covers most operations, not all side effects)
- Offset export support for lane boundaries
- Projection dropdown in export dialog

### Changed
- Improved code quality and test coverage

---

## [0.4.0] - 2026-01

### Added
- OpenDRIVE 1.8 full export support
- Junction boundaries and elevation grids (V1.8)
- Lane materials, heights, and access restrictions
- Lane direction attribute
- Clothoid/spiral fitting with Fresnel integrals
- Geometry preservation for round-trip editing
- XSD schema validation for exports
- Road splitting and merging
- Roundabout creation wizard

### Changed
- Upgraded from OpenDRIVE 1.7 to 1.8 format
- Improved uncertainty analysis with configurable parameters
- Better GCP suggestion algorithm

### Fixed
- Virtual junction export (no connecting roads for path crossings)
- Lane width calculations in junction geometry

---

## [0.3.2] - 2026-01

### Added
- Geometry preservation on import (GeometrySegment dataclass)
- Clothoid fitting via Fresnel integral-based algorithm
- Hybrid lane model with BoundaryMode enum
- `connecting_road_modified` signal to ImageView

### Changed
- Removed deprecated `Road.lanes` field (migration preserved in from_dict)
- Lane predecessor/successor links now fully working

---

## [0.3.1] - 2025-12

### Added
- Export module refactoring: `LaneBuilder`, `SignalBuilder`, `ObjectBuilder`
- Graphics module extraction: `orbit/gui/graphics/`
- 12 new unit tests for road section boundary management

### Fixed
- Virtual junction export bug
- Lane width calculations in junction geometry

---

## [0.3.0] - 2025-12

### Added
- Junction support with connecting roads
- Lane-to-lane connection mappings
- OpenDRIVE export with `<connection>` and `<laneLink>` elements
- Automatic connection generation from OSM imports
- Visual connection display in GUI
- Junction groups (roundabout, complexJunction, highwayInterchange)

---

## [0.2.0] - 2025-11

### Added
- OSM Import feature via Overpass API
- Highway types → OpenDRIVE road types mapping
- Lane configuration from OSM tags
- Turn lanes and turn restrictions
- Surface materials import
- Traffic signals and signs import
- Uncertainty analysis with Monte Carlo simulation
- GCP suggestions for optimal control point placement
- Uncertainty overlay visualization

---

## [0.1.0] - 2025-10

### Added
- Initial release
- PyQt6-based GUI for road annotation
- Polyline drawing and editing
- Road grouping with lane sections
- Junction management
- Georeferencing with control points
- OpenDRIVE 1.7 XML export
- Project save/load (.orbit JSON format)

---

## Known Limitations

- Undo/redo partially implemented — covers most operations but not all side effects (e.g., junction cleanup after road deletion)
- Single-image projects only (no multi-image mosaics)
- GUI code has low test coverage

---

## Future Plans

See [dev_plans/](dev_plans/) for detailed development plans and roadmaps.

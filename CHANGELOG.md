# ORBIT Changelog

All notable changes to this project are documented in this file.

**Current Version**: 0.15.0

---

> **Note**: entries for 0.7.0–0.14.0 were not recorded.

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

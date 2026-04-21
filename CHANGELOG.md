# ORBIT Changelog

All notable changes to this project are documented in this file.

**Current Version**: 0.10.1

---

## [0.10.1] - 2026-04

### Fixed
- Guardrail and aerial view parking space placement
- Junction geometry and connection errors

---

## [0.10.0] - 2026-03

### Added
- Lane section merge: select multiple consecutive sections and merge them into one
- Editing of land use areas placed via OSM import (type change, delete, move)

### Changed
- Improved PROJ string compatibility for georeferencing and xodr export
- Variable lane width handling fixes and cleaner coordinate propagation

### Fixed
- Erroneous geopos adjustments applied on .orbit file load
- Coordinate offset issues in pixel-to-geo conversion

---

## [0.9.0] - 2026-03

### Added
- CARLA / OpenDRIVE 1.4 compatibility export mode (preserves `vendor` and `userData` elements)
- Lane links editor for roads connected at junctions
- Unified editing UI for regular roads and connecting road links
- `laneChange` attribute export
- Two-way road support in OSM junction import

### Fixed
- Lane connection bug on 1-to-2-lane roads
- Variable-width road export
- Parking area edit and alignment adjustment persistence
- Multiple junction import bugs from OSM
- Junction/road ID overlap for CARLA

---

## [0.8.0] - 2026-03

### Added
- Automatic homography adjustment via point picking and least-squares fitting
- Ghost overlay showing original road lines during manual alignment

### Changed
- Unified treatment of connecting roads and regular roads (large refactor)
- Refactored large import/export functions for maintainability
- Maintainability report added to CI

### Fixed
- Undo polyline bug
- Sign/object ID conflict
- Visualization issues with road, lane, and object selection
- Broken junction import after refactor
- Homography/affine blending (inside image always uses homography)
- OSM junction import issues

---

## [0.7.0] - 2026-02

### Added
- Custom origin point selector for export coordinate reference
- Aerial image view panel

### Fixed
- Coordinate conversion (meter/pixel) in several export paths
- Road connection logic at xodr export
- Object pixel-to-metric coordinate conversion in xodr export
- Map centering when importing without georeferencing

---

## [0.6.1] - 2026-02

### Added
- OSM export (write road network back to OpenStreetMap format)
- Export land use areas and buildings to OpenDRIVE
- Layout mask export (`Export Layout Mask` — pixel-space and OpenDRIVE-accurate methods)
- Import more OSM object types: forest, farmland, wetland, and other land use
- Editing of imported objects (buildings, guardrails, etc.)
- Load OpenDRIVE / OSM without requiring a background image
- Hybrid transformer for imports that extend beyond the image bounds
- Remember last used directory across file open/save/import/export operations
- Lane width attribute in OSM export

### Fixed
- OSM junction import that had been broken
- Building placement and rotation
- OSM import/export attribution and license info

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

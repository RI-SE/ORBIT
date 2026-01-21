# ORBIT Changelog

All notable changes to this project are documented in this file.

**Current Version**: 0.4.0

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

- No undo/redo system (Qt undo framework not implemented)
- Single-image projects only (no multi-image mosaics)
- GUI code has low test coverage

---

## Future Plans

See [dev_plans/](dev_plans/) for detailed development plans and roadmaps.

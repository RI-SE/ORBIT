# Development Principles

Core design principles for ORBIT development. Read this before making
architecture-level changes.

## Coordinate Model: Geo-First with Pixel Fallback

ORBIT uses a dual-coordinate model. The rule for which coordinate type is primary
depends on the data's origin:

- **Imported data** (OSM, OpenDRIVE) arrives with geographic coordinates that are
  authoritative. `geo_points` / `geo_position` fields are set; pixel positions are
  computed from geo via the active transformer.
- **User-drawn data** starts pixel-primary. `geo_points` are assigned lazily — when
  a transformer is available or at export time — via `pixel_to_geo`. Once assigned,
  geo becomes the source of truth for that entity.
- **Transformer changes** (new control points, adjustment) recompute pixel positions
  from geo for all entities that have `geo_points`. The adjustment system
  (`update_all_from_geo_coords`) handles this.
- **Export** uses `geo_points → metric` conversion directly where available. A
  consistency check refreshes any geo_points that diverge from the current
  transformer (catches historically stale data). Entities without geo_points fall
  back to `pixel → geo → metric`.

### Three Coordinate Spaces

| Space | Origin | Used for |
|-------|--------|----------|
| **Pixel** | Image top-left | Display, user interaction; primary for user-drawn data |
| **Geographic** | WGS84 lat/lon | Primary for imported data; persistent storage alongside pixels |
| **Metric** | Local Transverse Mercator | OpenDRIVE export only |

The `CoordinateTransformer` hierarchy handles all conversions:

- `HomographyTransformer` — inside the image (control-point-based)
- `AffineTransformer` — fallback for ≤3 control points
- `HybridTransformer` — blends homography (inside image) with affine
  (outside image boundary) for extrapolation

Aerial tile view uses a bounds-based affine transform (no homography) with
precise geo↔pixel mapping.

## Export Consistency

At export time the writer validates `geo_points` against the current
transformer. Any point where `geo_to_pixel(geo)` diverges from the stored
pixel position beyond a threshold is refreshed from `pixel_to_geo`. This
catches stale geo_points without breaking the geo-first model.

## Undo/Redo

All user-initiated GUI mutations are wrapped in `QUndoCommand` subclasses
(`gui/undo_commands.py`) and pushed to the undo stack. Never mutate project
data directly from event handlers.

## Cross-Component Communication

`ImageView` emits Qt signals (`polyline_added`, `polyline_modified`,
`road_modified`, etc.). `MainWindow` connects these to handlers that update
the `Project` and tree widgets. Do not call tree widget methods directly
from graphics items.

# Development Principles

Core design principles for ORBIT development. Read this before making
architecture-level changes.

## Geo-First Coordinates

Geographic coordinates (WGS84 lat/lon) are the **source of truth** for all
geometry. Pixel coordinates are display-only—derived from geo via the active
coordinate transformer.

- **Imported data** (OSM, OpenDRIVE) arrives with geographic coords that are
  authoritative. Pixel positions are computed from geo.
- **User-drawn data** gets geo_points via `pixel_to_geo` at creation time.
  Once a geo_point exists, it is the source of truth.
- **Transformer changes** (new control points, adjustment) update pixel
  positions from geo, not the other way around. The adjustment system
  (`update_all_from_geo_coords`) handles this.
- **Export** uses geo_points → metric conversion directly. A consistency
  check refreshes any geo_points that diverge from the current transformer
  (catches historically stale data).

### Three Coordinate Spaces

| Space | Origin | Used for |
|-------|--------|----------|
| **Pixel** | Image top-left | Display, user interaction |
| **Geographic** | WGS84 lat/lon | Storage, source of truth |
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

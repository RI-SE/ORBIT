# opendrive-map

Read-only OpenDRIVE road-network / lane-geometry model shared across the ORBIT
drone toolchain (COSMO `trajectory-explorer`, `data-metrics`, and future tools).

It is the single source of truth for interpreting an ORBIT-exported `.xodr`:
reference-line geometry (line, arc, spiral/clothoid, poly3, paramPoly3), full
lane-width polynomials, multiple lane sections, `<laneOffset>`, lane-type
filtering, lane polygons + centerlines + lengths, and spatial lane assignment.

## Coordinate frame

All geometry is returned in the **local map frame** (the XODR `<offset>` is *not*
applied). `RoadNetwork.offset` exposes the authoritative header `<offset>` —
`absolute = local + offset`, in the `geo_reference` CRS. Use `to_global()` /
`to_local()` to convert. Do **not** re-derive the offset from the geoReference
`+lat_0/+lon_0` params; for UTM those are redundant and may be absent.

## Usage

```python
from opendrive_map import RoadNetwork

net = RoadNetwork.from_file("map.xodr", lane_types=["driving"])
lane = net.assign_lane(x_local, y_local)   # object position in LOCAL frame
if lane:
    print(lane.road_id, lane.lane_id, lane.length_m, lane.width_at(0.0))
```

## API

Public surface (everything in `opendrive_map.__all__`).

### `RoadNetwork`

The entry point. Build it, then query.

- `RoadNetwork.from_file(path, *, lane_types=None, interval=DEFAULT_INTERVAL)`
- `RoadNetwork.from_text(text, *, lane_types=None, interval=DEFAULT_INTERVAL)`

`lane_types=None` keeps all lane types; pass e.g. `["driving"]` to filter.
`interval` is the reference-line sampling step in metres.

| Attribute | Description |
|---|---|
| `roads` | parsed `Road` models (local frame, no lanes-built logic) |
| `lanes` | built `Lane` list (centerlines + polygons) |
| `junctions` | `Junction` list (id + connections) |
| `parking` | `ParkingObject` list (raw `<object type="parking">` records) |
| `parking_polygons` | placed shapely `Polygon`s for parking, local frame |
| `offset` | authoritative header `<offset>` `(x, y, z)`; `absolute = local + offset` |
| `geo_reference` | raw `<geoReference>` PROJ string, or `None` |
| `tree` | cached shapely `STRtree` over lane polygons (built on first use) |

| Method | Description |
|---|---|
| `assign_lane(x, y)` | lane whose polygon covers the LOCAL point, or `None` |
| `to_global(x, y)` | local → projected CRS coords (adds `offset`) |
| `to_local(x, y)` | projected CRS coords → local (subtracts `offset`) |

### `Lane`

Built lane geometry. Fields: `road_id`, `lane_id`, `type`, `section_s`,
`centerline` (Nx2 ndarray, local frame), `polygon` (shapely), `length_m`,
and `width_at(s_rel)` (width at distance `s_rel` into the lane section).

### Top-level functions

- `read_offset(path)` — read the header `<offset>` `(x, y, z)` cheaply, without
  building the network (used to localise object coordinates).
- `sample_reference_line(road, interval, breakpoints=())` — sample a road's
  reference line as `(s, x, y, hdg)` tuples; `breakpoints` forces extra samples
  at given `s` values (e.g. width/section transitions).

### Parking

`<object type="parking">` outlines are parsed into `ParkingObject` records and
placed into `parking_polygons` (local frame) using each object's road reference
point, `s`/`t`/`hdg`, and `<outline>` corners.

### Model dataclasses

Also exported for typing/inspection: `Road`, `RawLane`, `LaneSection`,
`GeomSegment`, `Poly`, `Junction`, `Connection`, `ParkingObject`. These are the
parsed model types behind `RoadNetwork`; most consumers only need the surface
above.

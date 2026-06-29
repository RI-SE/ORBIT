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

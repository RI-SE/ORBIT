"""RoadNetwork: the public read-only facade over a parsed OpenDRIVE map.

Coordinates are in the LOCAL map frame (the XODR <offset> is NOT applied);
``offset`` exposes the authoritative header <offset> so callers can convert to
the projected CRS (absolute = local + offset). This is the single, authoritative
source of the map offset for the toolchain — do not re-derive it from the
geoReference +lat_0/+lon_0 (those are redundant for UTM).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from shapely.geometry import Point, Polygon
from shapely.strtree import STRtree

from .geometry import sample_reference_line
from .lanes import build_road_lanes
from .model import Junction, Lane, ParkingObject, Road
from .parser import parse_xodr_text

DEFAULT_INTERVAL = 0.5


def read_offset(path: str) -> Tuple[float, float, float]:
    """Authoritative header <offset> (x, y, z) of a map file, without building lanes."""
    with open(path, encoding="utf-8", errors="ignore") as f:
        _roads, _junctions, _parking, offset, _geo = parse_xodr_text(f.read())
    return offset


def _road_point_at_s(road: Road, s: float, interval: float) -> Tuple[float, float, float]:
    """(x, y, hdg) at reference-line coordinate s on a road (nearest sample), local frame."""
    samples = sample_reference_line(road, interval)
    nearest = min(samples, key=lambda r: abs(r[0] - s))
    return nearest[1], nearest[2], nearest[3]


def _parking_polygon(road: Road, obj: ParkingObject, interval: float) -> Polygon:
    """Place a parking object's outline on its road (local frame)."""
    rx, ry, rhdg = _road_point_at_s(road, obj.s, interval)
    cx = rx - obj.t * math.sin(rhdg)
    cy = ry + obj.t * math.cos(rhdg)
    ang = rhdg + obj.hdg
    ca, sa = math.cos(ang), math.sin(ang)
    if len(obj.outline) >= 3:
        local = obj.outline
    else:
        hl, hw = obj.length / 2.0, obj.width / 2.0
        local = [(-hl, -hw), (hl, -hw), (hl, hw), (-hl, hw)]
    return Polygon([(cx + u * ca - v * sa, cy + u * sa + v * ca) for u, v in local])


@dataclass
class RoadNetwork:
    roads: List[Road]
    lanes: List[Lane]
    junctions: List[Junction] = field(default_factory=list)
    parking: List[ParkingObject] = field(default_factory=list)
    parking_polygons: List[Polygon] = field(default_factory=list)  # placed, local frame
    offset: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    geo_reference: Optional[str] = None
    _tree: Optional[STRtree] = field(default=None, repr=False)

    # ----- constructors -------------------------------------------------
    @classmethod
    def from_text(
        cls,
        text: str,
        *,
        lane_types: Optional[Sequence[str]] = None,
        interval: float = DEFAULT_INTERVAL,
    ) -> "RoadNetwork":
        roads, junctions, parking, offset, geo_ref = parse_xodr_text(text)
        lanes: List[Lane] = []
        for road in roads:
            lanes.extend(build_road_lanes(road, interval, lane_types))
        roads_by_id = {r.id: r for r in roads}
        parking_polygons = []
        for obj in parking:
            road = roads_by_id.get(obj.road_id)
            if road is None or not road.geom_segments:
                continue
            poly = _parking_polygon(road, obj, interval)
            if not poly.is_empty:
                parking_polygons.append(poly if poly.is_valid else poly.buffer(0))
        return cls(roads=roads, lanes=lanes, junctions=junctions, parking=parking,
                   parking_polygons=parking_polygons, offset=offset, geo_reference=geo_ref)

    @classmethod
    def from_file(
        cls,
        path: str,
        *,
        lane_types: Optional[Sequence[str]] = None,
        interval: float = DEFAULT_INTERVAL,
    ) -> "RoadNetwork":
        with open(path, encoding="utf-8", errors="ignore") as f:
            return cls.from_text(f.read(), lane_types=lane_types, interval=interval)

    # ----- frame helpers ------------------------------------------------
    def to_global(self, x: float, y: float) -> Tuple[float, float]:
        """Local map coords → projected CRS coords (absolute = local + offset)."""
        return x + self.offset[0], y + self.offset[1]

    def to_local(self, x: float, y: float) -> Tuple[float, float]:
        """Projected CRS coords → local map coords."""
        return x - self.offset[0], y - self.offset[1]

    # ----- spatial queries ----------------------------------------------
    @property
    def tree(self) -> STRtree:
        if self._tree is None:
            self._tree = STRtree([ln.polygon for ln in self.lanes])
        return self._tree

    def assign_lane(self, x: float, y: float) -> Optional[Lane]:
        """Return the lane whose polygon contains the LOCAL point (x, y), or None."""
        if not self.lanes:
            return None
        pt = Point(x, y)
        for idx in self.tree.query(pt):
            lane = self.lanes[int(idx)]
            if lane.polygon.covers(pt):
                return lane
        return None

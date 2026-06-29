"""Data model for the read-only OpenDRIVE road network."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import numpy as np


@dataclass
class GeomSegment:
    """One <planView><geometry> primitive in the road (local map frame)."""

    s: float
    x: float
    y: float
    hdg: float
    length: float
    kind: str  # "line" | "arc" | "spiral" | "poly3" | "paramPoly3"
    params: Dict[str, str] = field(default_factory=dict)


@dataclass
class Poly:
    """Cubic polynomial a + b*ds + c*ds^2 + d*ds^3 valid from sOffset."""

    sOffset: float
    a: float
    b: float
    c: float
    d: float

    def eval(self, s: float) -> float:
        ds = s - self.sOffset
        return self.a + self.b * ds + self.c * ds ** 2 + self.d * ds ** 3


def eval_poly_series(polys: List[Poly], s: float) -> float:
    """Evaluate a series of records, using the last one whose sOffset <= s."""
    if not polys:
        return 0.0
    active = polys[0]
    for p in polys:
        if p.sOffset <= s:
            active = p
        else:
            break
    return active.eval(s)


@dataclass
class RawLane:
    """A lane as parsed (id, type, width polynomials) before geometry is built."""

    id: int
    type: str
    widths: List[Poly] = field(default_factory=list)

    def width_at(self, s_rel: float) -> float:
        """Lane width at distance s_rel from the lane section start."""
        return eval_poly_series(self.widths, s_rel)


@dataclass
class LaneSection:
    s: float
    lanes: List[RawLane] = field(default_factory=list)


@dataclass
class Road:
    id: str
    length: float
    geom_segments: List[GeomSegment] = field(default_factory=list)
    lane_sections: List[LaneSection] = field(default_factory=list)
    lane_offsets: List[Poly] = field(default_factory=list)
    junction: str = "-1"

    def lane_offset_at(self, s: float) -> float:
        """Lateral offset of the lane-0 reference line at road coordinate s."""
        return eval_poly_series(self.lane_offsets, s)


@dataclass
class ParkingObject:
    """A <object type="parking"> on a road: outline placed at (s, t, hdg)."""

    road_id: str
    s: float
    t: float
    hdg: float
    length: float
    width: float
    outline: List[Tuple[float, float]] = field(default_factory=list)  # local (u, v) corners


@dataclass
class Connection:
    incoming_road: str
    connecting_road: str
    contact_point: str = ""


@dataclass
class Junction:
    id: str
    connections: List[Connection] = field(default_factory=list)


@dataclass
class Lane:
    """A built lane with geometry, in the LOCAL map frame (offset not applied)."""

    road_id: str
    lane_id: int
    type: str
    section_s: float
    centerline: np.ndarray            # (N, 2) float
    polygon: Tuple                    # shapely Polygon (typed loosely to avoid import here)
    length_m: float
    _widths: List[Poly] = field(default_factory=list)

    def width_at(self, s_rel: float) -> float:
        """Lane width at distance s_rel from this lane section's start."""
        return eval_poly_series(self._widths, s_rel)

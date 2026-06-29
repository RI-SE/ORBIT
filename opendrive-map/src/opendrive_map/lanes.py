"""Build lane geometry (centerlines + polygons) from a road's reference line.

Lane-offsetting approach follows COSMO's build_lane_polygons (full width
polynomials, multiple lane sections), extended with <laneOffset> handling and
arbitrary geometry primitives. All coordinates are in the LOCAL map frame.
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence

import numpy as np
from shapely.geometry import Polygon

from .geometry import sample_reference_line
from .model import Lane, Road


def _polyline_length(pts: np.ndarray) -> float:
    if len(pts) < 2:
        return 0.0
    return float(np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1)))


def _point_at_t(x: float, y: float, hdg: float, t: float) -> tuple:
    """Point offset by signed lateral distance t (positive = left of heading)."""
    return (x - t * math.sin(hdg), y + t * math.cos(hdg))


def build_road_lanes(
    road: Road,
    interval: float,
    lane_types: Optional[Sequence[str]] = None,
) -> List[Lane]:
    """Return built Lanes for one road; lane_types=None keeps all types."""
    samples = sample_reference_line(road, interval)
    if not samples:
        return []

    keep = set(lane_types) if lane_types is not None else None
    built: List[Lane] = []

    for ls_idx, ls in enumerate(road.lane_sections):
        s_start = ls.s
        s_end = (
            road.lane_sections[ls_idx + 1].s
            if ls_idx + 1 < len(road.lane_sections)
            else road.length
        )
        sec = [smp for smp in samples if s_start - 1e-6 <= smp[0] <= s_end + 1e-2]
        if len(sec) < 2:
            continue

        for side_sign in (1, -1):  # left (id>0) then right (id<0)
            side = [ln for ln in ls.lanes if (ln.id > 0) == (side_sign > 0) and ln.id != 0]
            side.sort(key=lambda ln: abs(ln.id))  # innermost first
            for rank, lane in enumerate(side):
                if keep is not None and lane.type not in keep:
                    continue
                inner_lanes = side[:rank]
                inner_pts, outer_pts, center_pts = [], [], []
                for s_road, x, y, hdg in sec:
                    s_rel = s_road - s_start
                    base = road.lane_offset_at(s_road)
                    d_inner = base + side_sign * sum(ln.width_at(s_rel) for ln in inner_lanes)
                    d_outer = d_inner + side_sign * lane.width_at(s_rel)
                    inner_pts.append(_point_at_t(x, y, hdg, d_inner))
                    outer_pts.append(_point_at_t(x, y, hdg, d_outer))
                    center_pts.append(_point_at_t(x, y, hdg, (d_inner + d_outer) / 2.0))

                ring = inner_pts + list(reversed(outer_pts))
                poly = Polygon(ring)
                if not poly.is_valid:
                    poly = poly.buffer(0)
                center = np.asarray(center_pts, dtype=float)
                built.append(
                    Lane(
                        road_id=road.id,
                        lane_id=lane.id,
                        type=lane.type,
                        section_s=s_start,
                        centerline=center,
                        polygon=poly,
                        length_m=_polyline_length(center),
                        _widths=lane.widths,
                    )
                )
    return built

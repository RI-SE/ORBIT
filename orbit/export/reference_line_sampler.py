"""
Reference line sampling and lane polygon computation for ORBIT.

Samples evenly-spaced points along OpenDRIVE geometry elements and computes
lane boundary polygons. Used by the layout mask exporter for the OpenDRIVE-accurate
export method.
"""

import math
from dataclasses import dataclass, field
from typing import List, Tuple

import numpy as np

from orbit.export.curve_fitting import GeometryElement, GeometryType
from orbit.models.lane import Lane
from orbit.models.lane_section import LaneSection
from orbit.models.road import Road
from orbit.utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class LanePolygonData:
    """Lane polygon data, decoupled from Qt.

    Attributes:
        road_id: Road or connecting road ID
        section_number: Lane section number (1-based)
        lane_id: OpenDRIVE lane ID (negative=right, positive=left)
        points: Polygon vertices in pixel coordinates
        is_connecting_road: True for junction connecting roads
        lane_type: OpenDRIVE lane type string (e.g., "driving", "shoulder")
    """
    road_id: str
    section_number: int
    lane_id: int
    points: List[Tuple[float, float]] = field(default_factory=list)
    is_connecting_road: bool = False
    lane_type: str = "driving"


def sample_reference_line(
    geometry_elements: List[GeometryElement],
    step_m: float = 0.5,
) -> List[Tuple[float, float, float]]:
    """Sample (x, y, heading) along geometry elements at regular intervals.

    Args:
        geometry_elements: Fitted geometry elements from CurveFitter
        step_m: Sampling interval in meters

    Returns:
        List of (x, y, heading) tuples in meters, including start and end of
        each element.
    """
    if not geometry_elements:
        return []

    points = []
    cumulative_s = 0.0

    for elem in geometry_elements:
        n_steps = max(1, int(math.ceil(elem.length / step_m)))
        ds = elem.length / n_steps

        for i in range(n_steps + 1):
            s_local = i * ds
            # Clamp to element length to avoid overshoot
            s_local = min(s_local, elem.length)

            x, y, hdg = _sample_element(elem, s_local)
            # Avoid duplicate points at element boundaries
            if points and i == 0:
                continue
            points.append((x, y, hdg))

        cumulative_s += elem.length

    return points


def _sample_element(
    elem: GeometryElement, s_local: float,
) -> Tuple[float, float, float]:
    """Sample a single geometry element at local s-coordinate.

    Args:
        elem: Geometry element to sample
        s_local: Distance along element from its start

    Returns:
        (x, y, heading) in meters
    """
    x0, y0 = elem.start_pos
    hdg0 = elem.heading
    cos_h = math.cos(hdg0)
    sin_h = math.sin(hdg0)

    if elem.geom_type == GeometryType.LINE:
        x = x0 + s_local * cos_h
        y = y0 + s_local * sin_h
        return (x, y, hdg0)

    elif elem.geom_type == GeometryType.ARC:
        if abs(elem.curvature) < 1e-12:
            # Nearly straight — treat as line
            x = x0 + s_local * cos_h
            y = y0 + s_local * sin_h
            return (x, y, hdg0)

        radius = 1.0 / elem.curvature
        # Angle swept
        theta = s_local * elem.curvature
        # Position in local frame
        dx_local = radius * math.sin(theta)
        dy_local = radius * (1.0 - math.cos(theta))
        # Rotate to global
        x = x0 + cos_h * dx_local - sin_h * dy_local
        y = y0 + sin_h * dx_local + cos_h * dy_local
        heading = hdg0 + theta
        return (x, y, heading)

    elif elem.geom_type == GeometryType.SPIRAL:
        curv_start = elem.curvature
        curv_end = elem.curvature_end if elem.curvature_end is not None else 0.0
        return _sample_spiral(x0, y0, hdg0, elem.length, curv_start, curv_end, s_local)

    elif elem.geom_type == GeometryType.PARAMPOLY3:
        return _sample_parampoly3(elem, s_local)

    else:
        # Unknown type — fall back to line
        logger.warning("Unknown geometry type %s, treating as line", elem.geom_type)
        x = x0 + s_local * cos_h
        y = y0 + s_local * sin_h
        return (x, y, hdg0)


def _sample_spiral(
    x0: float, y0: float, hdg0: float,
    length: float, curv_start: float, curv_end: float,
    s_local: float,
) -> Tuple[float, float, float]:
    """Sample a spiral (clothoid) using numerical integration.

    Uses Simpson's rule for accuracy without scipy dependency at runtime.
    """
    if length < 1e-12:
        return (x0, y0, hdg0)

    curv_rate = (curv_end - curv_start) / length

    # Numerical integration of heading: hdg(s) = hdg0 + curv_start*s + 0.5*curv_rate*s^2
    # Position: integrate cos(hdg(s)) and sin(hdg(s)) from 0 to s_local
    n_integration = max(20, int(s_local / 0.05))
    if n_integration % 2 == 1:
        n_integration += 1
    dt = s_local / n_integration if n_integration > 0 else 0.0

    dx = 0.0
    dy = 0.0
    for i in range(n_integration + 1):
        t = i * dt
        local_heading = curv_start * t + 0.5 * curv_rate * t * t
        cos_val = math.cos(local_heading)
        sin_val = math.sin(local_heading)
        # Simpson's rule weights
        if i == 0 or i == n_integration:
            w = 1.0
        elif i % 2 == 1:
            w = 4.0
        else:
            w = 2.0
        dx += w * cos_val
        dy += w * sin_val

    dx *= dt / 3.0
    dy *= dt / 3.0

    # Rotate to global frame
    cos_h = math.cos(hdg0)
    sin_h = math.sin(hdg0)
    x = x0 + cos_h * dx - sin_h * dy
    y = y0 + sin_h * dx + cos_h * dy

    heading = hdg0 + curv_start * s_local + 0.5 * curv_rate * s_local * s_local
    return (x, y, heading)


def _sample_parampoly3(
    elem: GeometryElement, s_local: float,
) -> Tuple[float, float, float]:
    """Sample a paramPoly3 geometry element."""
    x0, y0 = elem.start_pos
    hdg0 = elem.heading

    # Compute parameter p from s_local
    if elem.p_range_normalized and elem.length > 1e-12:
        p = s_local / elem.length
    else:
        p = s_local / elem.p_range if elem.p_range > 1e-12 else 0.0

    # Evaluate polynomials in local frame
    u = elem.aU + elem.bU * p + elem.cU * p**2 + elem.dU * p**3
    v = elem.aV + elem.bV * p + elem.cV * p**2 + elem.dV * p**3

    # Derivatives for heading
    du = elem.bU + 2 * elem.cU * p + 3 * elem.dU * p**2
    dv = elem.bV + 2 * elem.cV * p + 3 * elem.dV * p**2

    # Rotate to global
    cos_h = math.cos(hdg0)
    sin_h = math.sin(hdg0)
    x = x0 + cos_h * u - sin_h * v
    y = y0 + sin_h * u + cos_h * v

    # Local heading from tangent direction
    local_heading = math.atan2(dv, du) if abs(du) > 1e-12 or abs(dv) > 1e-12 else 0.0
    heading = hdg0 + local_heading

    return (x, y, heading)


def compute_lane_polygons(
    reference_points: List[Tuple[float, float, float]],
    road: Road,
    scale_x: float,
) -> List[LanePolygonData]:
    """Compute lane boundary polygons from reference line samples and lane widths.

    For each lane section, offsets the reference line laterally by cumulative
    lane widths. Lane widths come from road.lane_sections.

    Args:
        reference_points: (x, y, heading) samples in meters from sample_reference_line()
        road: Road model with lane_sections containing lane widths
        scale_x: Meters per pixel scale factor (for converting section boundaries)

    Returns:
        List of LanePolygonData with polygon vertices in meter coordinates.
        Caller is responsible for converting to pixels if needed.
    """
    if not reference_points or not road.lane_sections:
        return []

    # Build cumulative s-coordinates for reference points
    ref_s = [0.0]
    for i in range(1, len(reference_points)):
        x1, y1, _ = reference_points[i - 1]
        x2, y2, _ = reference_points[i]
        ds = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
        ref_s.append(ref_s[-1] + ds)

    total_ref_length = ref_s[-1] if ref_s else 0.0
    ref_s_arr = np.array(ref_s)

    polygons = []

    for section in road.lane_sections:
        # Convert section boundaries from pixel-space to meters
        s_start_m = section.s_start * scale_x
        s_end_m = section.s_end * scale_x if section.end_point_index is not None else total_ref_length
        # Clamp to reference line range
        s_start_m = max(0.0, min(s_start_m, total_ref_length))
        s_end_m = max(s_start_m, min(s_end_m, total_ref_length))
        section_length_m = s_end_m - s_start_m

        if section_length_m < 1e-6:
            continue

        # Find indices of reference points within this section
        mask = (ref_s_arr >= s_start_m - 1e-6) & (ref_s_arr <= s_end_m + 1e-6)
        indices = np.where(mask)[0]
        if len(indices) < 2:
            continue

        # Get reference points for this section
        section_ref = [(reference_points[i], ref_s[i]) for i in indices]

        # Process right lanes (negative IDs, sorted -1, -2, -3, ...)
        right_lanes = sorted(
            [ln for ln in section.lanes if ln.id < 0],
            key=lambda ln: -ln.id,  # -1 first, then -2, -3...
        )
        _build_side_polygons(
            polygons, section_ref, right_lanes, section,
            road.id, s_start_m, section_length_m, side="right",
        )

        # Process left lanes (positive IDs, sorted 1, 2, 3, ...)
        left_lanes = sorted(
            [ln for ln in section.lanes if ln.id > 0],
            key=lambda ln: ln.id,
        )
        _build_side_polygons(
            polygons, section_ref, left_lanes, section,
            road.id, s_start_m, section_length_m, side="left",
        )

    return polygons


def _build_side_polygons(
    polygons: List[LanePolygonData],
    section_ref: List[Tuple[Tuple[float, float, float], float]],
    lanes: List[Lane],
    section: LaneSection,
    road_id: str,
    s_start_m: float,
    section_length_m: float,
    side: str,
) -> None:
    """Build polygons for one side (left or right) of a lane section.

    Args:
        polygons: Output list to append to
        section_ref: List of ((x, y, heading), s) for reference points in section
        lanes: Lanes for this side, sorted by distance from center
        section: The lane section
        road_id: Road ID
        s_start_m: Section start in meters along reference line
        section_length_m: Section length in meters
        side: "left" or "right"
    """
    for lane_idx, lane in enumerate(lanes):
        inner_lanes = lanes[:lane_idx]

        # Compute boundary points
        inner_boundary = []
        outer_boundary = []

        for (x, y, hdg), s in section_ref:
            ds = s - s_start_m
            # Per-point inner offset from all closer-to-center lanes
            inner_offset = sum(
                il.get_width_at_s(ds, section_length_m) for il in inner_lanes
            )
            lane_width = lane.get_width_at_s(ds, section_length_m)
            outer_offset = inner_offset + lane_width

            # Perpendicular direction
            # Right side: offset to the right of heading (negative direction)
            # Left side: offset to the left of heading (positive direction)
            perp_x = -math.sin(hdg)
            perp_y = math.cos(hdg)

            if side == "right":
                # Right lanes offset in negative perpendicular direction
                inner_x = x - perp_x * inner_offset
                inner_y = y - perp_y * inner_offset
                outer_x = x - perp_x * outer_offset
                outer_y = y - perp_y * outer_offset
            else:
                # Left lanes offset in positive perpendicular direction
                inner_x = x + perp_x * inner_offset
                inner_y = y + perp_y * inner_offset
                outer_x = x + perp_x * outer_offset
                outer_y = y + perp_y * outer_offset

            inner_boundary.append((inner_x, inner_y))
            outer_boundary.append((outer_x, outer_y))

        # Build polygon: inner forward + outer reversed
        polygon_pts = inner_boundary + list(reversed(outer_boundary))

        if len(polygon_pts) >= 3:
            polygons.append(LanePolygonData(
                road_id=road_id,
                section_number=section.section_number,
                lane_id=lane.id,
                points=polygon_pts,
                is_connecting_road=False,
                lane_type=lane.lane_type.value,
            ))

"""
Connecting road lane alignment utilities for ORBIT.

Provides functions to adjust connecting road paths so their lane polygons
align with the target lanes on connected roads. Extracted from
LaneConnectionDialog to allow reuse on project load and after road moves.
"""

from typing import List, Optional, Tuple

from orbit.models import ConnectingRoad, Junction, Project


def align_connecting_road_paths(
    junction: Junction,
    project: Project,
    scale: float,
) -> List[str]:
    """Adjust all connecting road paths in a junction for lane alignment.

    For each connecting road that has a lane connection, computes the required
    endpoint shift so the CR lane center aligns with the target lane center
    on the connected road, then regenerates the path.

    Args:
        junction: Junction whose connecting roads to adjust.
        project: Project containing roads and polylines.
        scale: Meters-per-pixel scale factor (average of scale_x, scale_y).

    Returns:
        List of connecting road IDs that were modified.
    """
    if scale <= 0:
        return []

    modified_ids: List[str] = []

    for cr in junction.connecting_roads:
        if len(cr.path) < 2:
            continue

        # Find primary lane connection for this CR
        cr_conns = [
            c for c in junction.lane_connections if c.connecting_road_id == cr.id
        ]
        if not cr_conns:
            continue
        conn = cr_conns[0]
        cr_lane_id = conn.connecting_lane_id if conn.connecting_lane_id is not None else -1

        # Predecessor end (CR start)
        start_shift = _compute_lane_alignment_shift(
            project=project,
            road_id=cr.predecessor_road_id,
            contact_point=cr.contact_point_start,
            target_lane_id=conn.from_lane_id,
            cr_lane_id=cr_lane_id,
            cr_lane_width=cr.lane_width,
            cr_endpoint=cr.path[0],
            scale=scale,
        )

        # Successor end (CR end)
        end_shift = _compute_lane_alignment_shift(
            project=project,
            road_id=cr.successor_road_id,
            contact_point=cr.contact_point_end,
            target_lane_id=conn.to_lane_id,
            cr_lane_id=cr_lane_id,
            cr_lane_width=cr.lane_width,
            cr_endpoint=cr.path[-1],
            scale=scale,
        )

        if start_shift or end_shift:
            regenerate_connecting_road_path(cr, start_shift, end_shift)
            modified_ids.append(cr.id)

    return modified_ids


def _compute_lane_alignment_shift(
    project: Project,
    road_id: str,
    contact_point: str,
    target_lane_id: int,
    cr_lane_id: int,
    cr_lane_width: float,
    cr_endpoint: Tuple[float, float],
    scale: float,
) -> Optional[Tuple[float, float]]:
    """Compute pixel shift to align a CR lane with a target lane on a connected road.

    Calculates the absolute target position from the road's centerline
    polyline endpoint, then returns the delta from the CR's current endpoint.
    Uses calculate_perpendicular (identical to lane polygon rendering).
    """
    from orbit.utils.geometry import calculate_perpendicular

    road = project.get_road(road_id)
    if not road or not road.centerline_id:
        return None

    polyline = project.get_polyline(road.centerline_id)
    if not polyline or len(polyline.points) < 2:
        return None

    # Road centerline position and perpendicular at the contact point
    if contact_point == "end":
        road_cl_pos = polyline.points[-1]
        perp = calculate_perpendicular(polyline.points[-2], polyline.points[-1])
    else:
        road_cl_pos = polyline.points[0]
        perp = calculate_perpendicular(polyline.points[0], polyline.points[1])

    road_lane_width = _get_road_lane_width(road, contact_point)

    # How far from the road CL should the CR CL be?
    # road_lane_offset: where the target lane center is relative to road CL
    # cr_lane_offset:   where the CR lane center is relative to CR CL
    # CR CL must sit at (road_lane_offset - cr_lane_offset) from road CL.
    road_lane_off = _lane_center_offset(target_lane_id, road_lane_width)
    cr_lane_off = _lane_center_offset(cr_lane_id, cr_lane_width)
    offset_px = (road_lane_off - cr_lane_off) / scale

    target_x = road_cl_pos[0] + offset_px * perp[0]
    target_y = road_cl_pos[1] + offset_px * perp[1]

    dx = target_x - cr_endpoint[0]
    dy = target_y - cr_endpoint[1]

    # Skip trivial shifts (< 1 px)
    if abs(dx) < 1.0 and abs(dy) < 1.0:
        return None

    return (dx, dy)


def _lane_center_offset(lane_id: int, lane_width: float) -> float:
    """Perpendicular offset of a lane center from the road centerline (meters).

    Positive = right of direction of travel, negative = left.
    Matches the offset convention in calculate_offset_polyline / calculate_perpendicular.
    """
    if lane_id < 0:
        return (abs(lane_id) - 0.5) * lane_width
    elif lane_id > 0:
        return -(lane_id - 0.5) * lane_width
    return 0.0


def _get_road_lane_width(road, contact_point: str = "end") -> float:
    """Get average lane width for a road in meters at the given contact point.

    Args:
        road: Road with lane_sections
        contact_point: "start" uses first section, "end" uses last section
    """
    if road.lane_sections:
        section = road.lane_sections[0] if contact_point == "start" else road.lane_sections[-1]
        widths = [lane.width for lane in section.lanes if lane.id != 0 and lane.width > 0]
        if widths:
            return sum(widths) / len(widths)
    if hasattr(road, "lane_info") and road.lane_info:
        return road.lane_info.lane_width
    return 3.5


def regenerate_connecting_road_path(
    cr: ConnectingRoad,
    start_shift: Optional[Tuple[float, float]],
    end_shift: Optional[Tuple[float, float]],
) -> None:
    """Regenerate a connecting road's pixel path after endpoint shifts.

    Clears geo_path so the export uses the shifted pixel path. The
    geo_path would otherwise override the shifted endpoints (the
    exporter prefers geo_path when available), causing the exported
    geometry to follow the old, unaligned path.
    """
    # Invalidate geo_path — it no longer matches the shifted pixel path.
    cr.geo_path = None
    new_start = cr.path[0]
    new_end = cr.path[-1]
    if start_shift:
        new_start = (new_start[0] + start_shift[0],
                     new_start[1] + start_shift[1])
    if end_shift:
        new_end = (new_end[0] + end_shift[0],
                   new_end[1] + end_shift[1])

    start_heading = cr.get_start_heading()
    end_heading = cr.get_end_heading()

    if cr.geometry_type == "parampoly3" and start_heading is not None and end_heading is not None:
        try:
            from orbit.utils.geometry import generate_simple_connection_path
            path, coeffs = generate_simple_connection_path(
                from_pos=new_start,
                from_heading=start_heading,
                to_pos=new_end,
                to_heading=end_heading,
                num_points=len(cr.path),
                tangent_scale=cr.tangent_scale,
            )
            if path and len(path) >= 2:
                cr.path = path
                if coeffs and len(coeffs) == 8:
                    cr.aU, cr.bU, cr.cU, cr.dU = coeffs[:4]
                    cr.aV, cr.bV, cr.cV, cr.dV = coeffs[4:]
                cr.stored_start_heading = start_heading
                cr.stored_end_heading = end_heading
                return
        except Exception:
            pass

    # Fallback for polyline or failed regen: shift endpoints directly
    path = list(cr.path)
    if start_shift:
        path[0] = new_start
    if end_shift:
        path[-1] = new_end
    cr.path = path

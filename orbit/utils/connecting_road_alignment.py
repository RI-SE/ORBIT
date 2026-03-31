"""
Connecting road lane alignment utilities for ORBIT.

Provides functions to adjust connecting road paths so their lane polygons
align with the target lanes on connected roads. Extracted from
LaneConnectionDialog to allow reuse on project load and after road moves.
"""

from typing import List, Optional, Tuple

from orbit.models import Junction, Project, Road


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

    for cr_id in junction.connecting_road_ids:
        cr = project.get_road(cr_id)
        if not cr or not cr.inline_path or len(cr.inline_path) < 2:
            continue

        # Find primary lane connection for this CR
        cr_conns = [
            c for c in junction.lane_connections if c.connecting_road_id == cr.id
        ]
        if not cr_conns:
            continue
        conn = cr_conns[0]
        # Determine CR lane id: right lane (-1) or left lane (+1).
        # Fall back to the CR's actual lane config when not explicitly set.
        if conn.connecting_lane_id is not None:
            cr_lane_id = conn.connecting_lane_id
        elif cr.cr_lane_count_right > 0:
            cr_lane_id = -1
        else:
            cr_lane_id = 1

        # Determine which lane to target at each CR endpoint.
        # For use_left_lanes=True CRs the path is reversed (pred=to_road,
        # succ=from_road); from/to lane ids must be assigned accordingly.
        if cr.predecessor_id == conn.from_road_id:
            pred_target_lane_id = conn.from_lane_id
            succ_target_lane_id = conn.to_lane_id
        else:  # predecessor is to_road (reversed path)
            pred_target_lane_id = conn.to_lane_id
            succ_target_lane_id = conn.from_lane_id

        # Predecessor end (CR start) — forward direction is path[0]→path[1]
        start_shift = _compute_lane_alignment_shift(
            project=project,
            road_id=cr.predecessor_id,
            contact_point=cr.predecessor_contact,
            target_lane_id=pred_target_lane_id,
            cr_lane_id=cr_lane_id,
            cr_lane_width=cr.lane_info.lane_width,
            cr_endpoint=cr.inline_path[0],
            cr_fwd_p1=cr.inline_path[0],
            cr_fwd_p2=cr.inline_path[1],
            scale=scale,
        )

        # Successor end (CR end) — forward direction is path[-2]→path[-1]
        end_shift = _compute_lane_alignment_shift(
            project=project,
            road_id=cr.successor_id,
            contact_point=cr.successor_contact,
            target_lane_id=succ_target_lane_id,
            cr_lane_id=cr_lane_id,
            cr_lane_width=cr.lane_info.lane_width,
            cr_endpoint=cr.inline_path[-1],
            cr_fwd_p1=cr.inline_path[-2],
            cr_fwd_p2=cr.inline_path[-1],
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
    cr_fwd_p1: Tuple[float, float],
    cr_fwd_p2: Tuple[float, float],
    scale: float,
) -> Optional[Tuple[float, float]]:
    """Compute pixel shift to align a CR lane with a target lane on a connected road.

    Uses the road's perpendicular for the road-side offset and adjusts the
    CR-side offset based on the heading relationship (dot product of road and
    CR perpendiculars). When the CR heading is ~180° from the road heading
    (reversed-path left-lane CRs), the CR offset is negated so the lane
    polygon ends up on the correct side.
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
        road_perp = calculate_perpendicular(polyline.points[-2], polyline.points[-1])
    else:
        road_cl_pos = polyline.points[0]
        road_perp = calculate_perpendicular(polyline.points[0], polyline.points[1])

    road_lane_width = _get_road_lane_width(road, contact_point)

    # Road lane center position (offset from road CL along road perpendicular)
    road_lane_off = _lane_center_offset(target_lane_id, road_lane_width)
    road_off_px = road_lane_off / scale
    lane_center_x = road_cl_pos[0] + road_off_px * road_perp[0]
    lane_center_y = road_cl_pos[1] + road_off_px * road_perp[1]

    # CR lane offset — use road perpendicular for deterministic positioning.
    # When the CR heading is ~180° from the road heading (reversed-path CRs),
    # the CR's perpendicular is flipped, so the lane offset direction must be
    # negated to keep the lane polygon on the correct side.
    cr_perp = calculate_perpendicular(cr_fwd_p1, cr_fwd_p2)
    dot = road_perp[0] * cr_perp[0] + road_perp[1] * cr_perp[1]
    heading_sign = 1.0 if dot >= 0 else -1.0

    cr_lane_off = _lane_center_offset(cr_lane_id, cr_lane_width) * heading_sign
    cr_off_px = cr_lane_off / scale

    target_x = lane_center_x - cr_off_px * road_perp[0]
    target_y = lane_center_y - cr_off_px * road_perp[1]

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
    cr: Road,
    start_shift: Optional[Tuple[float, float]],
    end_shift: Optional[Tuple[float, float]],
) -> None:
    """Regenerate a connecting road's pixel path after endpoint shifts.

    Clears inline_geo_path so the export uses the shifted pixel path. The
    geo_path would otherwise override the shifted endpoints (the
    exporter prefers geo_path when available), causing the exported
    geometry to follow the old, unaligned path.
    """
    # Invalidate geo_path — it no longer matches the shifted pixel path.
    cr.inline_geo_path = None
    new_start = cr.inline_path[0]
    new_end = cr.inline_path[-1]
    if start_shift:
        new_start = (new_start[0] + start_shift[0],
                     new_start[1] + start_shift[1])
    if end_shift:
        new_end = (new_end[0] + end_shift[0],
                   new_end[1] + end_shift[1])

    # Derive headings from the current path (not stored headings) to
    # preserve the path direction established by geo-first generation.
    # Stored headings may be wrong for reversed-path CRs in older files.
    import math
    path = cr.inline_path
    if path and len(path) >= 2:
        start_heading = math.atan2(
            path[1][1] - path[0][1], path[1][0] - path[0][0])
        end_heading = math.atan2(
            path[-1][1] - path[-2][1], path[-1][0] - path[-2][0])
    else:
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
                num_points=len(cr.inline_path),
                tangent_scale=cr.tangent_scale,
            )
            if path and len(path) >= 2:
                cr.inline_path = path
                if coeffs and len(coeffs) == 8:
                    cr.aU, cr.bU, cr.cU, cr.dU = coeffs[:4]
                    cr.aV, cr.bV, cr.cV, cr.dV = coeffs[4:]
                cr.stored_start_heading = start_heading
                cr.stored_end_heading = end_heading
                return
        except Exception:
            pass

    # Fallback for polyline or failed regen: shift endpoints directly
    path = list(cr.inline_path)
    if start_shift:
        path[0] = new_start
    if end_shift:
        path[-1] = new_end
    cr.inline_path = path

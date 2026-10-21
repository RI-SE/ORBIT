"""
Connecting road lane alignment utilities for ORBIT.

Provides functions to adjust connecting road paths so their lane polygons
align with the target lanes on connected roads. Extracted from
LaneConnectionDialog to allow reuse on project load and after road moves.
"""

from typing import List, Optional, Tuple

from orbit_core.models import Junction, Project, Road


def align_connecting_road_paths(
    junction: Junction,
    project: Project,
    scale: float,
) -> List[str]:
    """Adjust all connecting road paths in a junction for lane alignment.

    Syncs each CR's lane widths to the road lanes its movements connect, then
    for each connecting road that has a lane connection computes the required
    endpoint shift so the CR lane center aligns with the target lane center
    on the connected road, and regenerates the path.

    Args:
        junction: Junction whose connecting roads to adjust.
        project: Project containing roads and polylines.
        scale: Meters-per-pixel scale factor (average of scale_x, scale_y).

    Returns:
        List of connecting road IDs whose widths or path were modified.
    """
    if scale <= 0:
        return []

    # Widths first: the endpoint shifts below are computed from them.
    modified_ids: List[str] = sync_connecting_road_lane_widths(junction, project)

    for cr_id in junction.connecting_road_ids:
        cr = project.get_road(cr_id)
        if not cr or not cr.inline_path or len(cr.inline_path) < 2:
            continue

        # Find lane connections for this CR
        cr_conns = [
            c for c in junction.lane_connections if c.connecting_road_id == cr.id
        ]
        if not cr_conns:
            continue

        # Bidirectional CRs (left AND right lanes) carry a movement in each
        # direction. Anchor each endpoint at the average of the per-direction
        # lane targets — ~the road centerline for symmetric 1+1 roads, but it
        # follows the target lanes on multi-lane approaches (turn pockets).
        if cr.cr_lane_count_left > 0 and cr.cr_lane_count_right > 0:
            cr.ensure_cr_lanes_initialized()
            start_shift, end_shift = _bidirectional_endpoint_shifts(
                cr, cr_conns, project, scale
            )
            if start_shift or end_shift:
                regenerate_connecting_road_path(cr, start_shift, end_shift)
                if cr.id not in modified_ids:
                    modified_ids.append(cr.id)
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

        cr.ensure_cr_lanes_initialized()

        # Predecessor end (CR start) — forward direction is path[0]→path[1]
        start_shift = _compute_lane_alignment_shift(
            project=project,
            road_id=cr.predecessor_id,
            contact_point=cr.predecessor_contact,
            target_lane_id=pred_target_lane_id,
            cr=cr,
            cr_lane_id=cr_lane_id,
            cr_contact="start",
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
            cr=cr,
            cr_lane_id=cr_lane_id,
            cr_contact="end",
            cr_endpoint=cr.inline_path[-1],
            cr_fwd_p1=cr.inline_path[-2],
            cr_fwd_p2=cr.inline_path[-1],
            scale=scale,
        )

        if start_shift or end_shift:
            regenerate_connecting_road_path(cr, start_shift, end_shift)
            if cr.id not in modified_ids:
                modified_ids.append(cr.id)

    return modified_ids


def sync_connecting_road_lane_widths(
    junction: Junction,
    project: Project,
) -> List[str]:
    """Set each connecting road lane's widths from the road lanes it connects.

    A CR lane's start width is taken from the lane its movement leaves at the
    CR's predecessor contact, its end width from the lane it enters at the
    successor contact, so approach-lane edits (turn pockets, wide junction
    mouths) propagate into the junction. Lanes carrying no movement, and
    movements naming a lane that no longer exists, are left untouched.

    Returns the IDs of connecting roads whose lane widths changed.
    """
    modified_ids: List[str] = []

    for cr_id in junction.connecting_road_ids:
        cr = project.get_road(cr_id)
        if not cr:
            continue
        cr.ensure_cr_lanes_initialized()

        changed = False
        synced_lane_ids = set()
        for conn in junction.lane_connections:
            if conn.connecting_road_id != cr.id or conn.connecting_lane_id is None:
                continue
            if conn.connecting_lane_id in synced_lane_ids:
                continue  # first movement on a lane wins
            cr_lane = cr.get_cr_lane(conn.connecting_lane_id)
            if cr_lane is None:
                continue

            # Reversed-path CRs have pred=to_road, succ=from_road.
            if cr.predecessor_id == conn.from_road_id:
                pred_road_id, pred_lane_id = conn.from_road_id, conn.from_lane_id
                succ_road_id, succ_lane_id = conn.to_road_id, conn.to_lane_id
            else:
                pred_road_id, pred_lane_id = conn.to_road_id, conn.to_lane_id
                succ_road_id, succ_lane_id = conn.from_road_id, conn.from_lane_id

            width_start = _road_lane_width(
                project, pred_road_id, pred_lane_id, cr.predecessor_contact
            )
            width_end = _road_lane_width(
                project, succ_road_id, succ_lane_id, cr.successor_contact
            )
            if width_start is None or width_end is None:
                continue

            synced_lane_ids.add(conn.connecting_lane_id)
            new_end = None if abs(width_end - width_start) < 1e-6 else width_end
            if (abs(cr_lane.width - width_start) > 1e-6
                    or cr_lane.width_end != new_end):
                cr_lane.width = width_start
                cr_lane.width_end = new_end
                changed = True

        if changed:
            modified_ids.append(cr.id)

    return modified_ids


def _road_lane_width(
    project: Project,
    road_id: str,
    lane_id: int,
    contact_point: str,
) -> Optional[float]:
    """Width of one lane of a road at the given contact point, or None."""
    road = project.get_road(road_id)
    section = _section_at_contact(road, contact_point) if road else None
    if section is None:
        return None
    for lane in section.lanes:
        if lane.id == lane_id:
            return lane.width if contact_point == "start" else lane.get_width_at_end()
    return None


def _bidirectional_endpoint_shifts(
    cr,
    cr_conns,
    project: Project,
    scale: float,
) -> Tuple[Optional[Tuple[float, float]], Optional[Tuple[float, float]]]:
    """Average per-direction lane alignment shifts for a bidirectional CR."""

    def shifts_for_end(road_id, contact, endpoint, fwd_p1, fwd_p2, at_start):
        shifts = []
        for conn in cr_conns:
            if conn.connecting_lane_id is None:
                continue
            if conn.from_road_id == road_id:
                target_lane_id = conn.from_lane_id
            elif conn.to_road_id == road_id:
                target_lane_id = conn.to_lane_id
            else:
                continue
            if cr.get_cr_lane(conn.connecting_lane_id) is None:
                continue
            shift = _compute_lane_alignment_shift(
                project=project, road_id=road_id, contact_point=contact,
                target_lane_id=target_lane_id,
                cr=cr, cr_lane_id=conn.connecting_lane_id,
                cr_contact="start" if at_start else "end",
                cr_endpoint=endpoint,
                cr_fwd_p1=fwd_p1, cr_fwd_p2=fwd_p2, scale=scale,
            )
            shifts.append(shift or (0.0, 0.0))
        if not shifts:
            return None
        avg = (sum(dx for dx, _ in shifts) / len(shifts),
               sum(dy for _, dy in shifts) / len(shifts))
        # Symmetric targets cancel out; skip trivial net shifts (< 1 px)
        if abs(avg[0]) < 1.0 and abs(avg[1]) < 1.0:
            return None
        return avg

    start_shift = shifts_for_end(
        cr.predecessor_id, cr.predecessor_contact,
        cr.inline_path[0], cr.inline_path[0], cr.inline_path[1], True)
    end_shift = shifts_for_end(
        cr.successor_id, cr.successor_contact,
        cr.inline_path[-1], cr.inline_path[-2], cr.inline_path[-1], False)
    return start_shift, end_shift


def _compute_lane_alignment_shift(
    project: Project,
    road_id: str,
    contact_point: str,
    target_lane_id: int,
    cr: Road,
    cr_lane_id: int,
    cr_contact: str,
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
    from orbit_core.utils.geometry import calculate_perpendicular

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

    # Road lane center position (offset from road CL along road perpendicular)
    road_lane_off = lane_center_offset(road, target_lane_id, contact_point)
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

    cr_lane_off = lane_center_offset(cr, cr_lane_id, cr_contact) * heading_sign
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

    Assumes every lane has the same width; only a fallback for roads without
    lane sections. Prefer lane_center_offset(), which sums the real widths.
    """
    if lane_id < 0:
        return (abs(lane_id) - 0.5) * lane_width
    elif lane_id > 0:
        return -(lane_id - 0.5) * lane_width
    return 0.0


def _section_at_contact(road, contact_point: str):
    """Lane section of a road at the given contact point, or None."""
    sections = getattr(road, "lane_sections", None)
    if not sections:
        return None
    return sections[0] if contact_point == "start" else sections[-1]


def _lane_widths_at_contact(section, contact_point: str) -> dict:
    """Width of every non-center lane of a section at the given contact point."""
    return {
        lane.id: (lane.width if contact_point == "start" else lane.get_width_at_end())
        for lane in section.lanes
        if lane.id != 0
    }


def lane_center_offset(road, lane_id: int, contact_point: str = "end") -> float:
    """Perpendicular offset of a lane center from the road centerline (meters).

    Sums the widths of the lanes between the centerline and the target lane at
    the contact point, so roads whose lanes differ in width (turn pockets,
    painted islands, wide junction mouths) align correctly. Positive = right of
    the direction of travel, matching _lane_center_offset.
    """
    if lane_id == 0:
        return 0.0

    section = _section_at_contact(road, contact_point)
    widths = _lane_widths_at_contact(section, contact_point) if section else {}
    if lane_id not in widths:
        return _lane_center_offset(lane_id, _get_road_lane_width(road, contact_point))

    step = 1 if lane_id > 0 else -1
    offset = sum(widths.get(lid, 0.0) for lid in range(step, lane_id, step))
    offset += widths[lane_id] / 2.0
    return -offset if lane_id > 0 else offset


def _get_road_lane_width(road, contact_point: str = "end") -> float:
    """Get average lane width for a road at the given contact point (meters)."""
    if road.lane_sections:
        section = road.lane_sections[0] if contact_point == "start" else road.lane_sections[-1]
        widths = []
        for lane in section.lanes:
            if lane.id == 0 or lane.width <= 0:
                continue
            if contact_point == "end":
                widths.append(lane.get_width_at_end())
            else:
                widths.append(lane.width)
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
            from orbit_core.utils.geometry import generate_simple_connection_path
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

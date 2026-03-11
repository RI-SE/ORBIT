"""
Geometry validation for ORBIT projects.

Checks for structural issues in road geometry (negative sections, signals/objects
outside road bounds, etc.) that are distinct from OpenDRIVE reference validation.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from orbit.models import Project


@dataclass
class GeometryIssue:
    """A single geometry validation issue."""

    message: str
    road_id: Optional[str] = None
    section_number: Optional[int] = None
    severity: str = "warning"  # "error" | "warning"
    element_id: Optional[str] = None  # Signal or object ID for element-level issues


def _s_from_position(position, centerline_points) -> Optional[float]:
    """
    Project a pixel position onto the centerline and return the s-coordinate.

    Unlike Signal.calculate_s_position, this allows the result to exceed
    [0, road_length]: if the position projects beyond the road end (t > 1 on
    last segment) or before the road start (t < 0 on first segment), the
    extrapolated value is returned so callers can detect out-of-bounds placement
    in both directions.
    """
    if not centerline_points or len(centerline_points) < 2:
        return None

    px, py = position
    min_dist = float("inf")
    closest_idx = 0
    closest_t_clamped = 0.0

    for i in range(len(centerline_points) - 1):
        x1, y1 = centerline_points[i]
        x2, y2 = centerline_points[i + 1]
        dx, dy = x2 - x1, y2 - y1
        length_sq = dx * dx + dy * dy
        t = 0.0 if length_sq == 0 else ((px - x1) * dx + (py - y1) * dy) / length_sq
        t_c = max(0.0, min(1.0, t))
        proj_x, proj_y = x1 + t_c * dx, y1 + t_c * dy
        dist = ((px - proj_x) ** 2 + (py - proj_y) ** 2) ** 0.5
        if dist < min_dist:
            min_dist = dist
            closest_idx = i
            closest_t_clamped = t_c

    # Cumulative length up to the closest segment
    s = 0.0
    for i in range(closest_idx):
        x1, y1 = centerline_points[i]
        x2, y2 = centerline_points[i + 1]
        s += ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5

    x1, y1 = centerline_points[closest_idx]
    x2, y2 = centerline_points[closest_idx + 1]
    dx, dy = x2 - x1, y2 - y1
    length_sq = dx * dx + dy * dy
    seg_length = length_sq ** 0.5

    last_idx = len(centerline_points) - 2
    if closest_idx == last_idx and closest_t_clamped == 1.0 and length_sq > 0:
        # Position projects past the road end — use unclamped t so s > road_length
        t_unclamped = ((px - x1) * dx + (py - y1) * dy) / length_sq
        s += t_unclamped * seg_length
    elif closest_idx == 0 and closest_t_clamped == 0.0 and length_sq > 0:
        # Position projects before the road start — use unclamped t so s < 0
        t_unclamped = ((px - x1) * dx + (py - y1) * dy) / length_sq
        s += t_unclamped * seg_length
    else:
        s += closest_t_clamped * seg_length

    return s


def validate_project_geometry(project: "Project") -> List[GeometryIssue]:
    """
    Validate project geometry and return a list of issues found.

    Checks performed:
    - Negative lane section length (s_end <= s_start)
    - Signal s_position beyond road centerline length
    - RoadObject s_position beyond road centerline length
    - Lane material s_offset beyond section length
    - Lane height s_offset beyond section length
    """
    issues: List[GeometryIssue] = []

    # Build a cache of road centerline lengths to avoid recomputation
    road_lengths: dict = {}

    def get_road_length(road) -> Optional[float]:
        if road.id in road_lengths:
            return road_lengths[road.id]
        if not road.centerline_id:
            road_lengths[road.id] = None
            return None
        centerline = project.get_polyline(road.centerline_id)
        if not centerline or not centerline.points:
            road_lengths[road.id] = None
            return None
        s_coords = road.calculate_centerline_s_coordinates(centerline.points)
        length = s_coords[-1] if s_coords else None
        road_lengths[road.id] = length
        return length

    for road in project.roads:
        for section in road.lane_sections:
            # Check negative section length
            if section.s_end <= section.s_start:
                issues.append(GeometryIssue(
                    message=(
                        f"Lane section has negative length "
                        f"(s_start={section.s_start:.2f}, s_end={section.s_end:.2f})"
                    ),
                    road_id=road.id,
                    section_number=section.section_number,
                    severity="error",
                ))

            # Check lane material and height s_offsets within section
            section_length = section.s_end - section.s_start
            if section_length > 0:
                for lane in section.get_lanes_sorted():
                    for s_offset, *_ in getattr(lane, "materials", []):
                        if s_offset > section_length:
                            issues.append(GeometryIssue(
                                message=(
                                    f"Lane {lane.id} material s_offset={s_offset:.2f} "
                                    f"exceeds section length={section_length:.2f}"
                                ),
                                road_id=road.id,
                                section_number=section.section_number,
                                severity="warning",
                            ))
                    for s_offset, *_ in getattr(lane, "heights", []):
                        if s_offset > section_length:
                            issues.append(GeometryIssue(
                                message=(
                                    f"Lane {lane.id} height s_offset={s_offset:.2f} "
                                    f"exceeds section length={section_length:.2f}"
                                ),
                                road_id=road.id,
                                section_number=section.section_number,
                                severity="warning",
                            ))

    # Check signals outside road (regular roads and connecting roads)
    for signal in project.signals:
        if not signal.road_id:
            continue
        road = project.get_road(signal.road_id)
        if road:
            length = get_road_length(road)
            if length is None:
                continue
            # Prefer live projection from pixel position (unclamped) so a signal
            # dragged past the road end is detected even though s_position is clamped.
            if road.is_connecting_road:
                path = road.inline_path
                if not path or len(path) < 2:
                    continue
                length = road.get_inline_path_length()
                if signal.position:
                    s = _s_from_position(signal.position, path)
                else:
                    s = signal.s_position
            else:
                centerline = project.get_polyline(road.centerline_id) if road.centerline_id else None
                if centerline and signal.position:
                    s = _s_from_position(signal.position, centerline.points)
                else:
                    s = signal.s_position
        else:
            continue  # Road not found
        if s is not None and not (0 <= s <= length):
            where = "beyond road end" if s > length else "before road start"
            issues.append(GeometryIssue(
                message=(
                    f"Signal '{signal.name or signal.id}' is {where} "
                    f"(s={s:.2f}, road length={length:.2f})"
                ),
                road_id=signal.road_id,
                element_id=signal.id,
                severity="warning",
            ))

    # Check road objects outside road (regular roads and connecting roads)
    for obj in project.objects:
        if not obj.road_id:
            continue
        road = project.get_road(obj.road_id)
        if road:
            length = get_road_length(road)
            if length is None:
                continue
            if road.is_connecting_road:
                path = road.inline_path
                if not path or len(path) < 2:
                    continue
                length = road.get_inline_path_length()
                if obj.position:
                    s = _s_from_position(obj.position, path)
                else:
                    s = obj.s_position
            else:
                centerline = project.get_polyline(road.centerline_id) if road.centerline_id else None
                if centerline and obj.position:
                    s = _s_from_position(obj.position, centerline.points)
                else:
                    s = obj.s_position
        else:
            continue  # Road not found
        if s is not None and not (0 <= s <= length):
            where = "beyond road end" if s > length else "before road start"
            issues.append(GeometryIssue(
                message=(
                    f"Object '{obj.name or obj.id}' is {where} "
                    f"(s={s:.2f}, road length={length:.2f})"
                ),
                road_id=obj.road_id,
                element_id=obj.id,
                severity="warning",
            ))

    return issues

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

    # Check signals outside road
    for signal in project.signals:
        if signal.s_position is None or not signal.road_id:
            continue
        road = project.get_road(signal.road_id)
        if not road:
            continue
        length = get_road_length(road)
        if length is not None and signal.s_position > length:
            issues.append(GeometryIssue(
                message=(
                    f"Signal '{signal.name or signal.id}' s_position={signal.s_position:.2f} "
                    f"exceeds road length={length:.2f}"
                ),
                road_id=signal.road_id,
                severity="warning",
            ))

    # Check road objects outside road
    for obj in project.objects:
        if obj.s_position is None or not obj.road_id:
            continue
        road = project.get_road(obj.road_id)
        if not road:
            continue
        length = get_road_length(road)
        if length is not None and obj.s_position > length:
            issues.append(GeometryIssue(
                message=(
                    f"Object '{obj.name or obj.id}' s_position={obj.s_position:.2f} "
                    f"exceeds road length={length:.2f}"
                ),
                road_id=obj.road_id,
                severity="warning",
            ))

    return issues

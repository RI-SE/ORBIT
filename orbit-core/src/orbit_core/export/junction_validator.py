"""
Junction consistency validator for ORBIT project data.

Checks that every movement through a junction is wired to lanes that exist and
to a connecting road lane of matching width, and that no driving lane or
connecting road lane at the junction is left without a movement. These defects
are all schema-valid OpenDRIVE, so nothing else catches them.
"""

from typing import Dict, List, Optional

from orbit_core.models.junction import Junction
from orbit_core.models.project import Project
from orbit_core.models.road import Road
from orbit_core.utils.connecting_road_alignment import (
    _lane_widths_at_contact,
    _section_at_contact,
)
from orbit_core.utils.logging_config import get_logger

logger = get_logger(__name__)

# A width step below this is paint-level noise, not a modelling error.
WIDTH_STEP_TOLERANCE_M = 0.05


def validate_junctions(project: Project) -> List[str]:
    """
    Check every junction's lane connections against the roads they join.

    Args:
        project: The ORBIT project to validate

    Returns:
        List of human-readable warning strings. Empty if every junction is
        consistent.
    """
    warnings: List[str] = []
    for junction in project.junctions:
        if not junction.lane_connections:
            continue
        warnings.extend(_validate_junction(junction, project))
    return warnings


def _validate_junction(junction: Junction, project: Project) -> List[str]:
    """Collect all consistency warnings for one junction."""
    warnings: List[str] = []
    used_cr_lanes: Dict[str, set] = {}
    connected_lanes: Dict[str, set] = {}

    for conn in junction.lane_connections:
        cr = project.get_road(conn.connecting_road_id) if conn.connecting_road_id else None
        if cr is None:
            continue  # dangling CR reference is validate_references' job
        cr.ensure_cr_lanes_initialized()

        connected_lanes.setdefault(conn.from_road_id, set()).add(conn.from_lane_id)
        connected_lanes.setdefault(conn.to_road_id, set()).add(conn.to_lane_id)

        if conn.connecting_lane_id is None:
            continue
        if cr.get_cr_lane(conn.connecting_lane_id) is None:
            warnings.append(
                f"Junction {junction.id}: movement {conn.id} uses lane "
                f"{conn.connecting_lane_id} of connecting road {cr.id}, "
                f"which has no such lane"
            )
            continue
        used_cr_lanes.setdefault(cr.id, set()).add(conn.connecting_lane_id)
        warnings.extend(_validate_movement_widths(junction, conn, cr, project))

    warnings.extend(_check_unused_cr_lanes(junction, project, used_cr_lanes))
    warnings.extend(_check_unconnected_driving_lanes(junction, project, connected_lanes))
    return warnings


def _validate_movement_widths(junction, conn, cr: Road, project: Project) -> List[str]:
    """Check one movement's lanes exist and match the CR lane width at both ends."""
    # Reversed-path CRs have pred=to_road, succ=from_road.
    if cr.predecessor_id == conn.from_road_id:
        ends = ((conn.from_road_id, conn.from_lane_id, cr.predecessor_contact, "start"),
                (conn.to_road_id, conn.to_lane_id, cr.successor_contact, "end"))
    else:
        ends = ((conn.to_road_id, conn.to_lane_id, cr.predecessor_contact, "start"),
                (conn.from_road_id, conn.from_lane_id, cr.successor_contact, "end"))

    cr_lane = cr.get_cr_lane(conn.connecting_lane_id)
    warnings: List[str] = []
    for road_id, lane_id, contact, cr_end in ends:
        road_width = _lane_width(project, road_id, lane_id, contact)
        if road_width is None:
            warnings.append(
                f"Junction {junction.id}: movement {conn.id} uses lane {lane_id} "
                f"of road {road_id}, which has no such lane at its {contact}"
            )
            continue
        cr_width = cr_lane.width if cr_end == "start" else cr_lane.get_width_at_end()
        step = abs(cr_width - road_width)
        if step > WIDTH_STEP_TOLERANCE_M:
            warnings.append(
                f"Junction {junction.id}: connecting road {cr.id} lane "
                f"{conn.connecting_lane_id} is {cr_width:.2f} m at its {cr_end} "
                f"but road {road_id} lane {lane_id} is {road_width:.2f} m there "
                f"({step:.2f} m step)"
            )
    return warnings


def _check_unused_cr_lanes(junction, project, used_cr_lanes) -> List[str]:
    """Warn about connecting road lanes no movement references."""
    warnings: List[str] = []
    for cr_id in junction.connecting_road_ids:
        cr = project.get_road(cr_id)
        if cr is None:
            continue
        cr.ensure_cr_lanes_initialized()
        used = used_cr_lanes.get(cr_id, set())
        for section in cr.lane_sections:
            for lane in section.lanes:
                if lane.id != 0 and lane.id not in used:
                    warnings.append(
                        f"Junction {junction.id}: connecting road {cr_id} lane "
                        f"{lane.id} carries no movement"
                    )
    return warnings


def _check_unconnected_driving_lanes(junction, project, connected_lanes) -> List[str]:
    """Warn about driving lanes meeting the junction that carry no movement."""
    warnings: List[str] = []
    for road_id in junction.connected_road_ids:
        road = project.get_road(road_id)
        if road is None:
            continue
        contact = _junction_contact(junction, road, project)
        section = _section_at_contact(road, contact)
        if section is None:
            continue
        widths = _lane_widths_at_contact(section, contact)
        for lane in section.lanes:
            if lane.id == 0 or lane.lane_type.value != "driving":
                continue
            if widths.get(lane.id, 0.0) <= 0.0:
                continue  # lane is closed at the junction
            if lane.id not in connected_lanes.get(road_id, set()):
                warnings.append(
                    f"Junction {junction.id}: road {road_id} lane {lane.id} "
                    f"({widths[lane.id]:.2f} m at the junction) carries no movement"
                )
    return warnings


def _junction_contact(junction, road: Road, project: Project) -> str:
    """Which end of a road meets the junction."""
    for cr_id in junction.connecting_road_ids:
        cr = project.get_road(cr_id)
        if cr is None:
            continue
        if cr.predecessor_id == road.id:
            return cr.predecessor_contact
        if cr.successor_id == road.id:
            return cr.successor_contact
    return "end"


def _lane_width(
    project: Project,
    road_id: str,
    lane_id: int,
    contact_point: str,
) -> Optional[float]:
    """Width of one lane of a road at a contact point, or None if absent."""
    road = project.get_road(road_id)
    section = _section_at_contact(road, contact_point) if road else None
    if section is None:
        return None
    return _lane_widths_at_contact(section, contact_point).get(lane_id)

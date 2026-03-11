"""
Reference validator for ORBIT project data.

Checks all cross-references between project entities (roads, polylines,
junctions, signals, etc.) and reports dangling references that would
produce invalid OpenDRIVE output.
"""

from typing import List, Set

from orbit.models.project import Project
from orbit.utils.logging_config import get_logger

logger = get_logger(__name__)


def validate_references(project: Project) -> List[str]:
    """
    Check all cross-references in a project.

    Builds ID sets for each entity type and verifies every reference field
    points to an existing entity.

    Args:
        project: The ORBIT project to validate

    Returns:
        List of human-readable warning strings. Empty if all references are valid.
    """
    warnings: List[str] = []

    # Build ID sets for each entity type
    polyline_ids: Set[str] = {p.id for p in project.polylines}
    road_ids: Set[str] = {r.id for r in project.roads}
    junction_ids: Set[str] = {j.id for j in project.junctions}
    signal_ids: Set[str] = {s.id for s in project.signals}
    # Build connecting road ID sets per junction
    connecting_road_ids: Set[str] = set()
    for junction in project.junctions:
        for cr_id in junction.connecting_road_ids:
            connecting_road_ids.add(cr_id)

    # --- Road references ---
    for road in project.roads:
        label = f"Road '{road.name}' (id={road.id})"

        # Road → Polyline (centerline_id)
        if road.centerline_id and road.centerline_id not in polyline_ids:
            warnings.append(f"{label}: centerline_id '{road.centerline_id}' not found in polylines")

        # Road → Polyline (polyline_ids)
        for pid in road.polyline_ids:
            if pid not in polyline_ids:
                warnings.append(f"{label}: polyline_id '{pid}' not found in polylines")

        # Road → Road (predecessor_id, successor_id)
        if road.predecessor_id and road.predecessor_id not in road_ids:
            warnings.append(f"{label}: predecessor_id '{road.predecessor_id}' not found in roads")
        if road.successor_id and road.successor_id not in road_ids:
            warnings.append(f"{label}: successor_id '{road.successor_id}' not found in roads")

        # Road → Junction (junction_id, predecessor_junction_id, successor_junction_id)
        if road.junction_id and road.junction_id not in junction_ids:
            warnings.append(f"{label}: junction_id '{road.junction_id}' not found in junctions")
        if road.predecessor_junction_id and road.predecessor_junction_id not in junction_ids:
            warnings.append(
                f"{label}: predecessor_junction_id '{road.predecessor_junction_id}' not found in junctions"
            )
        if road.successor_junction_id and road.successor_junction_id not in junction_ids:
            warnings.append(
                f"{label}: successor_junction_id '{road.successor_junction_id}' not found in junctions"
            )

    # --- Junction references ---
    for junction in project.junctions:
        label = f"Junction '{junction.name}' (id={junction.id})"

        # Junction → Road (connected_road_ids)
        for rid in junction.connected_road_ids:
            if rid not in road_ids:
                warnings.append(f"{label}: connected_road_id '{rid}' not found in roads")

        # Junction → Road (entry_roads, exit_roads)
        for rid in junction.entry_roads:
            if rid not in road_ids:
                warnings.append(f"{label}: entry_road '{rid}' not found in roads")
        for rid in junction.exit_roads:
            if rid not in road_ids:
                warnings.append(f"{label}: exit_road '{rid}' not found in roads")

        # ConnectingRoad → Road (predecessor_id, successor_id)
        for cr_id in junction.connecting_road_ids:
            cr = project.get_road(cr_id)
            if not cr:
                warnings.append(f"ConnectingRoad (id={cr_id}) in {label}: road not found in project")
                continue
            cr_label = f"ConnectingRoad (id={cr.id}) in {label}"
            if cr.predecessor_id and cr.predecessor_id not in road_ids:
                warnings.append(f"{cr_label}: predecessor_id '{cr.predecessor_id}' not found in roads")
            if cr.successor_id and cr.successor_id not in road_ids:
                warnings.append(f"{cr_label}: successor_id '{cr.successor_id}' not found in roads")

        # LaneConnection references
        for lc in junction.lane_connections:
            lc_label = f"LaneConnection (id={lc.id}) in {label}"
            if lc.from_road_id and lc.from_road_id not in road_ids:
                warnings.append(f"{lc_label}: from_road_id '{lc.from_road_id}' not found in roads")
            if lc.to_road_id and lc.to_road_id not in road_ids:
                warnings.append(f"{lc_label}: to_road_id '{lc.to_road_id}' not found in roads")
            if lc.connecting_road_id and lc.connecting_road_id not in connecting_road_ids:
                warnings.append(
                    f"{lc_label}: connecting_road_id '{lc.connecting_road_id}' not found in connecting roads"
                )
            if lc.traffic_light_id and lc.traffic_light_id not in signal_ids:
                warnings.append(f"{lc_label}: traffic_light_id '{lc.traffic_light_id}' not found in signals")

        # Boundary segments → Road
        if junction.boundary:
            for seg in junction.boundary.segments:
                if seg.road_id and seg.road_id not in road_ids:
                    warnings.append(
                        f"BoundarySegment in {label}: road_id '{seg.road_id}' not found in roads"
                    )

    # --- Signal → Road (or connecting road) ---
    for signal in project.signals:
        if signal.road_id and signal.road_id not in road_ids \
                and signal.road_id not in connecting_road_ids:
            warnings.append(
                f"Signal '{signal.name or signal.id}' "
                f"(id={signal.id}): road_id "
                f"'{signal.road_id}' not found in roads"
            )

    # --- RoadObject → Road (or connecting road) ---
    for obj in project.objects:
        if obj.road_id and obj.road_id not in road_ids \
                and obj.road_id not in connecting_road_ids:
            warnings.append(f"RoadObject (id={obj.id}): road_id '{obj.road_id}' not found in roads")

    # --- ParkingSpace → Road ---
    for parking in project.parking_spaces:
        if parking.road_id and parking.road_id not in road_ids:
            warnings.append(f"ParkingSpace (id={parking.id}): road_id '{parking.road_id}' not found in roads")

    # --- JunctionGroup → Junction ---
    for jg in project.junction_groups:
        jg_label = f"JunctionGroup '{jg.name}' (id={jg.id})"
        for jid in jg.junction_ids:
            if jid not in junction_ids:
                warnings.append(f"{jg_label}: junction_id '{jid}' not found in junctions")

    # --- Lane → Polyline (boundary IDs) ---
    for road in project.roads:
        for section in road.lane_sections:
            for lane in section.lanes:
                lane_label = f"Lane {lane.id} in road '{road.name}' (id={road.id})"
                if lane.left_boundary_id and lane.left_boundary_id not in polyline_ids:
                    warnings.append(
                        f"{lane_label}: left_boundary_id '{lane.left_boundary_id}' not found in polylines"
                    )
                if lane.right_boundary_id and lane.right_boundary_id not in polyline_ids:
                    warnings.append(
                        f"{lane_label}: right_boundary_id '{lane.right_boundary_id}' not found in polylines"
                    )

    return warnings

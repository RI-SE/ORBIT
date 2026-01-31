"""
Create roundabouts from wizard parameters.

Generates roads, junctions, and connecting roads for manually
created roundabouts.
"""

import math
from typing import List, Tuple, Dict, Optional

from orbit.models import Project, Road, Junction
from orbit.models.polyline import Polyline, LineType, RoadMarkType
from orbit.models.road import RoadType, LaneInfo
from orbit.models.lane import Lane, LaneType as LaneTypeEnum
from orbit.models.lane_section import LaneSection
from orbit.models.connecting_road import ConnectingRoad
from orbit.models.lane_connection import LaneConnection


def generate_ring_points(
    center: Tuple[float, float],
    radius: float,
    num_points: int,
    clockwise: bool = False
) -> List[Tuple[float, float]]:
    """
    Generate points along a circular ring.

    Args:
        center: Center point (x, y)
        radius: Ring radius
        num_points: Number of points to generate
        clockwise: True for clockwise, False for counter-clockwise

    Returns:
        List of (x, y) points along the ring
    """
    points = []
    direction = -1 if clockwise else 1

    for i in range(num_points):
        angle = direction * 2 * math.pi * i / num_points
        x = center[0] + radius * math.cos(angle)
        y = center[1] + radius * math.sin(angle)
        points.append((x, y))

    return points


def find_nearest_ring_point(
    ring_points: List[Tuple[float, float]],
    target_point: Tuple[float, float]
) -> int:
    """
    Find the index of the ring point nearest to a target point.

    Args:
        ring_points: List of ring points
        target_point: Target point to find nearest to

    Returns:
        Index of nearest ring point
    """
    min_dist = float('inf')
    min_idx = 0

    for i, (x, y) in enumerate(ring_points):
        dist = math.sqrt((x - target_point[0])**2 + (y - target_point[1])**2)
        if dist < min_dist:
            min_dist = dist
            min_idx = i

    return min_idx


def create_roundabout_from_params(
    project: Project,
    params: dict,
    approach_roads: Optional[Dict[str, Road]] = None,
    polylines: Optional[Dict[str, Polyline]] = None
) -> Tuple[List[Road], List[Junction], List[Polyline]]:
    """
    Create a complete roundabout from wizard parameters.

    Args:
        project: Project to add elements to
        params: Roundabout parameters from wizard:
            - center: (x, y) tuple
            - radius: Radius in pixels
            - ring_points: Number of points
            - lane_count: Number of lanes
            - lane_width: Lane width in meters
            - clockwise: Traffic direction
            - approach_road_ids: List of approach road IDs
        approach_roads: Optional dict of road_id -> Road for existing roads
        polylines: Optional dict of polyline_id -> Polyline for existing polylines

    Returns:
        Tuple of (created_roads, created_junctions, created_polylines)
    """
    center = params['center']
    radius = params['radius']
    num_ring_points = params['ring_points']
    lane_count = params['lane_count']
    lane_width = params['lane_width']
    clockwise = params['clockwise']
    approach_road_ids = params.get('approach_road_ids', [])

    created_roads = []
    created_junctions = []
    created_polylines = []

    # Generate ring points
    ring_points = generate_ring_points(center, radius, num_ring_points, clockwise)

    # If no approach roads, create single ring road
    if not approach_road_ids or not approach_roads:
        road, polyline = _create_single_ring_road(
            ring_points, lane_count, lane_width, center, radius, clockwise, project
        )
        created_roads.append(road)
        created_polylines.append(polyline)

        # Add to project
        project.add_road(road)
        project.add_polyline(polyline)

        return created_roads, created_junctions, created_polylines

    # Find connection points for each approach road
    connection_indices = []
    for road_id in approach_road_ids:
        road = approach_roads.get(road_id)
        if not road or not road.centerline_id:
            continue

        polyline = polylines.get(road.centerline_id) if polylines else None
        if not polyline or len(polyline.points) < 2:
            continue

        # Check which end is closer to roundabout
        start_dist = math.sqrt(
            (polyline.points[0][0] - center[0])**2 +
            (polyline.points[0][1] - center[1])**2
        )
        end_dist = math.sqrt(
            (polyline.points[-1][0] - center[0])**2 +
            (polyline.points[-1][1] - center[1])**2
        )

        if end_dist < start_dist:
            approach_point = polyline.points[-1]
        else:
            approach_point = polyline.points[0]

        # Find nearest ring point
        ring_idx = find_nearest_ring_point(ring_points, approach_point)
        connection_indices.append({
            'ring_index': ring_idx,
            'road_id': road_id,
            'connects_at_end': end_dist < start_dist
        })

    # Sort connection points by ring index
    connection_indices.sort(key=lambda x: x['ring_index'])

    # If fewer than 2 connections, create single ring road
    if len(connection_indices) < 2:
        road, polyline = _create_single_ring_road(
            ring_points, lane_count, lane_width, center, radius, clockwise, project
        )
        created_roads.append(road)
        created_polylines.append(polyline)

        project.add_road(road)
        project.add_polyline(polyline)

        return created_roads, created_junctions, created_polylines

    # Create ring segments between connection points
    n_connections = len(connection_indices)
    ring_segments = []

    for i in range(n_connections):
        start_conn = connection_indices[i]
        end_conn = connection_indices[(i + 1) % n_connections]

        start_idx = start_conn['ring_index']
        end_idx = end_conn['ring_index']

        # Extract segment points (handle wraparound)
        if end_idx <= start_idx:
            segment_points = ring_points[start_idx:] + ring_points[:end_idx + 1]
        else:
            segment_points = ring_points[start_idx:end_idx + 1]

        if len(segment_points) < 2:
            continue

        # Create polyline
        polyline = Polyline(
            id=project.next_id('polyline'),
            points=list(segment_points),
            line_type=LineType.CENTERLINE,
            road_mark_type=RoadMarkType.SOLID,
            color=(255, 165, 0)  # Orange
        )

        # Create road
        road = Road(
            id=project.next_id('road'),
            name=f"Roundabout Ring {i + 1}",
            road_type=RoadType.TOWN,
            centerline_id=polyline.id
        )
        road.add_polyline(polyline.id)

        # Configure lanes
        road.lane_info = LaneInfo(
            left_count=0,
            right_count=lane_count,
            lane_width=lane_width
        )

        # Create lane section
        section = _create_lane_section(lane_count, lane_width, len(segment_points))
        road.lane_sections = [section]

        ring_segments.append((road, polyline))
        created_roads.append(road)
        created_polylines.append(polyline)

    # Link ring segments
    for i in range(len(ring_segments)):
        road = ring_segments[i][0]
        prev_road = ring_segments[(i - 1) % len(ring_segments)][0]
        next_road = ring_segments[(i + 1) % len(ring_segments)][0]

        road.predecessor_id = prev_road.id
        road.predecessor_contact = "end"
        road.successor_id = next_road.id
        road.successor_contact = "start"

    # Create junctions at each connection point
    for i, conn in enumerate(connection_indices):
        incoming_ring = ring_segments[(i - 1) % len(ring_segments)][0]
        outgoing_ring = ring_segments[i][0]

        # Get position from ring point
        position = ring_points[conn['ring_index']]

        # Create junction
        junction = Junction(
            id=project.next_id('junction'),
            name=f"Roundabout Entry {i + 1}",
            center_point=position,
            connected_road_ids=[incoming_ring.id, outgoing_ring.id, conn['road_id']]
        )

        # Configure as roundabout junction
        junction.is_roundabout = True
        junction.roundabout_center = center
        junction.roundabout_radius = radius
        junction.roundabout_lane_count = lane_count
        junction.roundabout_clockwise = clockwise

        junction.entry_roads = [conn['road_id']]
        junction.exit_roads = [conn['road_id']]

        # Create connecting roads
        _create_junction_connectors(
            junction, incoming_ring, outgoing_ring,
            ring_segments[(i - 1) % len(ring_segments)][1],
            ring_segments[i][1],
            center, clockwise, lane_count, lane_width, project
        )

        created_junctions.append(junction)

    # Add all to project
    for road in created_roads:
        project.add_road(road)

    for polyline in created_polylines:
        project.add_polyline(polyline)

    for junction in created_junctions:
        project.add_junction(junction)

    return created_roads, created_junctions, created_polylines


def _create_single_ring_road(
    ring_points: List[Tuple[float, float]],
    lane_count: int,
    lane_width: float,
    center: Tuple[float, float],
    radius: float,
    clockwise: bool,
    project: Optional[Project] = None
) -> Tuple[Road, Polyline]:
    """Create a single closed ring road (no connections)."""
    # Close the ring
    closed_points = list(ring_points) + [ring_points[0]]

    polyline = Polyline(
        id=project.next_id('polyline') if project else "",
        points=closed_points,
        line_type=LineType.CENTERLINE,
        road_mark_type=RoadMarkType.SOLID,
        color=(255, 165, 0),
        closed=True
    )

    road = Road(
        id=project.next_id('road') if project else "",
        name="Roundabout",
        road_type=RoadType.TOWN,
        centerline_id=polyline.id
    )
    road.add_polyline(polyline.id)

    road.lane_info = LaneInfo(
        left_count=0,
        right_count=lane_count,
        lane_width=lane_width
    )

    section = _create_lane_section(lane_count, lane_width, len(closed_points))
    road.lane_sections = [section]

    return road, polyline


def _create_lane_section(lane_count: int, lane_width: float, num_points: int) -> LaneSection:
    """Create a lane section for ring road."""
    section = LaneSection(
        section_number=1,
        s_start=0.0,
        s_end=float(num_points - 1),
        end_point_index=num_points - 1
    )

    # Center lane
    center_lane = Lane(id=0, lane_type=LaneTypeEnum.NONE, width=0.0)
    section.lanes.append(center_lane)

    # Right lanes
    for i in range(1, lane_count + 1):
        lane = Lane(
            id=-i,
            lane_type=LaneTypeEnum.DRIVING,
            road_mark_type=RoadMarkType.BROKEN if i < lane_count else RoadMarkType.SOLID,
            width=lane_width
        )
        section.lanes.append(lane)

    return section


def _create_junction_connectors(
    junction: Junction,
    incoming_ring: Road,
    outgoing_ring: Road,
    incoming_polyline: Polyline,
    outgoing_polyline: Polyline,
    center: Tuple[float, float],
    clockwise: bool,
    lane_count: int,
    lane_width: float,
    project: Optional[Project] = None
) -> None:
    """Create connecting roads for a roundabout junction."""
    # Through connector (ring to ring)
    if incoming_polyline.points and outgoing_polyline.points:
        incoming_end = incoming_polyline.points[-1]
        outgoing_start = outgoing_polyline.points[0]

        through_path = _generate_curved_path(
            incoming_end, outgoing_start, center, clockwise, 6
        )

        through_connector = ConnectingRoad(
            id=project.next_id('connecting_road') if project else "",
            path=through_path,
            lane_count_left=0,
            lane_count_right=lane_count,
            lane_width=lane_width,
            predecessor_road_id=incoming_ring.id,
            successor_road_id=outgoing_ring.id,
            contact_point_start="end",
            contact_point_end="start"
        )
        through_connector.ensure_lanes_initialized()
        junction.add_connecting_road(through_connector)

        # Lane connections
        for i in range(1, lane_count + 1):
            lc = LaneConnection(
                id=project.next_id('lane_connection') if project else "",
                from_road_id=incoming_ring.id,
                from_lane_id=-i,
                to_road_id=outgoing_ring.id,
                to_lane_id=-i,
                connecting_road_id=through_connector.id,
                turn_type="straight"
            )
            junction.add_lane_connection(lc)


def _generate_curved_path(
    start: Tuple[float, float],
    end: Tuple[float, float],
    center: Tuple[float, float],
    clockwise: bool,
    num_points: int
) -> List[Tuple[float, float]]:
    """Generate a curved path between two points around a center."""
    start_angle = math.atan2(start[1] - center[1], start[0] - center[0])
    end_angle = math.atan2(end[1] - center[1], end[0] - center[0])

    start_radius = math.sqrt((start[0] - center[0])**2 + (start[1] - center[1])**2)
    end_radius = math.sqrt((end[0] - center[0])**2 + (end[1] - center[1])**2)

    if clockwise:
        sweep = start_angle - end_angle
        if sweep <= 0:
            sweep += 2 * math.pi
        sweep = -sweep
    else:
        sweep = end_angle - start_angle
        if sweep <= 0:
            sweep += 2 * math.pi

    path = []
    for i in range(num_points):
        t = i / (num_points - 1)
        angle = start_angle + t * sweep
        radius = start_radius + t * (end_radius - start_radius)
        x = center[0] + radius * math.cos(angle)
        y = center[1] + radius * math.sin(angle)
        path.append((x, y))

    return path

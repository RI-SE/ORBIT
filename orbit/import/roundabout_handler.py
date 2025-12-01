"""
Roundabout detection and conversion from OSM data.

Handles the complex logic of converting OSM roundabouts to segmented roads
with proper junctions at each entry/exit point.
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional, Set
import math
import uuid

from orbit.models import Road, Junction
from orbit.models.polyline import Polyline, LineType, RoadMarkType
from orbit.models.road import RoadType, LaneInfo
from orbit.models.lane import Lane, LaneType as LaneTypeEnum
from orbit.models.lane_section import LaneSection
from orbit.models.connecting_road import ConnectingRoad
from orbit.models.lane_connection import LaneConnection

from .osm_parser import OSMData, OSMWay, OSMNode


@dataclass
class ConnectionPoint:
    """
    Where an approach road connects to the roundabout ring.

    Attributes:
        osm_node_id: OSM node ID at this connection point
        position: Pixel coordinates (x, y)
        ring_index: Index in the ring_points list
        angle_from_center: Angle from roundabout center in radians
        connecting_way_ids: Set of OSM way IDs that connect at this point
        is_entry: Can vehicles enter the roundabout here
        is_exit: Can vehicles exit the roundabout here
    """
    osm_node_id: int
    position: Tuple[float, float]  # Pixel coords
    ring_index: int
    angle_from_center: float  # Radians, for sorting
    connecting_way_ids: Set[int] = field(default_factory=set)
    is_entry: bool = True
    is_exit: bool = True


@dataclass
class RoundaboutInfo:
    """
    Analyzed roundabout geometry from OSM.

    Attributes:
        osm_way_id: Original OSM way ID for the roundabout
        center: Center point in pixel coordinates
        radius: Average radius in pixels
        clockwise: True for left-hand traffic (rare in Sweden)
        lane_count: Number of lanes in the circular road
        speed_limit: Speed limit from OSM tags (km/h)
        connection_points: List of entry/exit points sorted by angle
        ring_node_ids: OSM node IDs in ring order
        ring_points: Pixel coordinates in ring order
        tags: Original OSM tags for reference
    """
    osm_way_id: int
    center: Tuple[float, float]  # Pixel coordinates
    radius: float  # Average radius in pixels
    clockwise: bool = False  # True for left-hand traffic
    lane_count: int = 1
    speed_limit: Optional[float] = None

    connection_points: List[ConnectionPoint] = field(default_factory=list)
    ring_node_ids: List[int] = field(default_factory=list)
    ring_points: List[Tuple[float, float]] = field(default_factory=list)
    tags: Dict[str, str] = field(default_factory=dict)


def find_shared_nodes(roundabout_way: OSMWay, osm_data: OSMData) -> Dict[int, Set[int]]:
    """
    Find nodes in the roundabout that are shared with other ways.

    Args:
        roundabout_way: The OSM way representing the roundabout ring
        osm_data: Full OSM data containing all ways

    Returns:
        Dict mapping node_id -> set of way_ids that share this node
        (excluding the roundabout itself)
    """
    roundabout_nodes = set(roundabout_way.nodes)
    shared_nodes: Dict[int, Set[int]] = {}

    for way in osm_data.ways.values():
        # Skip the roundabout itself
        if way.id == roundabout_way.id:
            continue

        # Skip non-highway ways
        if 'highway' not in way.tags:
            continue

        # Check for shared nodes
        for node_id in way.nodes:
            if node_id in roundabout_nodes:
                if node_id not in shared_nodes:
                    shared_nodes[node_id] = set()
                shared_nodes[node_id].add(way.id)

    return shared_nodes


def analyze_roundabout(
    osm_way: OSMWay,
    osm_data: OSMData,
    transformer: 'CoordinateTransformer',
    verbose: bool = False
) -> RoundaboutInfo:
    """
    Analyze an OSM roundabout way and identify connection points.

    Steps:
    1. Convert ring nodes to pixel coordinates
    2. Calculate center (centroid of ring points)
    3. Calculate average radius
    4. Find all nodes shared with other ways (connection points)
    5. Sort connection points by angle from center (counter-clockwise)
    6. Determine traffic direction from node order
    7. Extract lane count and speed limit from tags

    Args:
        osm_way: The OSM way representing the roundabout
        osm_data: Full OSM data
        transformer: Coordinate transformer for geo->pixel conversion
        verbose: Print debug information

    Returns:
        RoundaboutInfo with analyzed geometry and connection points
    """
    # Convert ring nodes to pixel coordinates
    ring_points = []
    ring_node_ids = []

    for node_id in osm_way.nodes:
        osm_node = osm_data.nodes.get(node_id)
        if osm_node:
            px, py = transformer.geo_to_pixel(osm_node.lon, osm_node.lat)
            ring_points.append((px, py))
            ring_node_ids.append(node_id)

    if len(ring_points) < 3:
        raise ValueError(f"Roundabout way {osm_way.id} has fewer than 3 valid points")

    # Calculate center (centroid)
    center_x = sum(p[0] for p in ring_points) / len(ring_points)
    center_y = sum(p[1] for p in ring_points) / len(ring_points)
    center = (center_x, center_y)

    # Calculate average radius
    radii = [math.sqrt((p[0] - center_x)**2 + (p[1] - center_y)**2)
             for p in ring_points]
    radius = sum(radii) / len(radii)

    # Determine traffic direction from node order
    # Counter-clockwise = right-hand traffic (default)
    # Clockwise = left-hand traffic
    # Calculate signed area to determine winding order
    signed_area = 0.0
    n = len(ring_points)
    for i in range(n):
        j = (i + 1) % n
        signed_area += ring_points[i][0] * ring_points[j][1]
        signed_area -= ring_points[j][0] * ring_points[i][1]
    signed_area /= 2.0
    # Positive = counter-clockwise (right-hand traffic)
    # In pixel coords with y-down, sign is inverted
    clockwise = signed_area > 0  # Inverted due to y-down coords

    # Extract lane count from tags
    lane_count = 1
    if 'lanes' in osm_way.tags:
        try:
            lane_count = int(osm_way.tags['lanes'])
        except ValueError:
            pass

    # Extract speed limit
    speed_limit = None
    if 'maxspeed' in osm_way.tags:
        try:
            speed_str = osm_way.tags['maxspeed'].replace(' km/h', '').replace('km/h', '')
            speed_limit = float(speed_str)
        except ValueError:
            pass

    # Find shared nodes (connection points)
    shared_nodes = find_shared_nodes(osm_way, osm_data)

    # Create connection points with angle information
    connection_points = []
    for i, node_id in enumerate(ring_node_ids):
        if node_id in shared_nodes:
            px, py = ring_points[i]
            angle = math.atan2(py - center_y, px - center_x)

            cp = ConnectionPoint(
                osm_node_id=node_id,
                position=(px, py),
                ring_index=i,
                angle_from_center=angle,
                connecting_way_ids=shared_nodes[node_id],
                is_entry=True,
                is_exit=True
            )
            connection_points.append(cp)

    # Sort connection points by angle (counter-clockwise from east)
    # For right-hand traffic, we want CCW order
    if clockwise:
        # Left-hand traffic: sort clockwise (descending angle)
        connection_points.sort(key=lambda cp: -cp.angle_from_center)
    else:
        # Right-hand traffic: sort counter-clockwise (ascending angle)
        connection_points.sort(key=lambda cp: cp.angle_from_center)

    if verbose:
        print(f"Roundabout {osm_way.id}: center=({center_x:.1f}, {center_y:.1f}), "
              f"radius={radius:.1f}px, {len(connection_points)} connections, "
              f"{'clockwise' if clockwise else 'counter-clockwise'}")

    return RoundaboutInfo(
        osm_way_id=osm_way.id,
        center=center,
        radius=radius,
        clockwise=clockwise,
        lane_count=lane_count,
        speed_limit=speed_limit,
        connection_points=connection_points,
        ring_node_ids=ring_node_ids,
        ring_points=ring_points,
        tags=dict(osm_way.tags)
    )


def create_ring_segments(
    roundabout: RoundaboutInfo,
    default_lane_width: float = 3.5,
    verbose: bool = False
) -> List[Tuple[Road, Polyline]]:
    """
    Split roundabout ring into road segments between connection points.

    For N connection points, creates N ring segments:
    - Segment 0: from connection[0] to connection[1]
    - Segment 1: from connection[1] to connection[2]
    - ...
    - Segment N-1: from connection[N-1] to connection[0] (closing the loop)

    Args:
        roundabout: Analyzed roundabout geometry
        default_lane_width: Lane width in meters
        verbose: Print debug info

    Returns:
        List of (Road, Polyline) tuples for each ring segment
    """
    if len(roundabout.connection_points) < 2:
        # Not enough connections to split - create single ring road
        return _create_single_ring_road(roundabout, default_lane_width)

    segments = []
    n_connections = len(roundabout.connection_points)

    for i in range(n_connections):
        start_cp = roundabout.connection_points[i]
        end_cp = roundabout.connection_points[(i + 1) % n_connections]

        # Extract points between these connection indices
        start_idx = start_cp.ring_index
        end_idx = end_cp.ring_index

        # Handle wraparound
        if end_idx <= start_idx:
            # Wraps around: take points from start to end of ring, then 0 to end
            segment_points = (
                roundabout.ring_points[start_idx:] +
                roundabout.ring_points[:end_idx + 1]
            )
            segment_node_ids = (
                roundabout.ring_node_ids[start_idx:] +
                roundabout.ring_node_ids[:end_idx + 1]
            )
        else:
            segment_points = roundabout.ring_points[start_idx:end_idx + 1]
            segment_node_ids = roundabout.ring_node_ids[start_idx:end_idx + 1]

        if len(segment_points) < 2:
            if verbose:
                print(f"  Skipping segment {i}: too few points")
            continue

        # Create polyline for this segment
        polyline = Polyline(
            points=list(segment_points),
            line_type=LineType.CENTERLINE,
            road_mark_type=RoadMarkType.SOLID,
            osm_node_ids=list(segment_node_ids),
            color=(255, 165, 0)  # Orange for roundabout segments
        )

        # Create road
        road_name = _get_roundabout_name(roundabout)
        road = Road(
            name=f"{road_name} Ring {i + 1}",
            road_type=_get_road_type_from_tags(roundabout.tags),
            centerline_id=polyline.id,
            speed_limit=roundabout.speed_limit
        )
        road.add_polyline(polyline.id)

        # Mark as ring segment (for export handling)
        road.is_ring_segment = True  # type: ignore

        # Set lane configuration
        road.lane_info = LaneInfo(
            left_count=0,  # One-way road
            right_count=roundabout.lane_count,
            lane_width=default_lane_width
        )

        # Create lane section
        section = _create_ring_lane_section(
            roundabout.lane_count, default_lane_width, len(segment_points)
        )
        road.lane_sections = [section]

        segments.append((road, polyline))

        if verbose:
            print(f"  Ring segment {i + 1}: {len(segment_points)} points, "
                  f"from connection {i} to {(i + 1) % n_connections}")

    return segments


def _create_single_ring_road(
    roundabout: RoundaboutInfo,
    default_lane_width: float
) -> List[Tuple[Road, Polyline]]:
    """Create a single road for the entire ring (when < 2 connections)."""
    polyline = Polyline(
        points=list(roundabout.ring_points),
        line_type=LineType.CENTERLINE,
        road_mark_type=RoadMarkType.SOLID,
        osm_node_ids=list(roundabout.ring_node_ids),
        color=(255, 165, 0),
        closed=True
    )

    road_name = _get_roundabout_name(roundabout)
    road = Road(
        name=f"{road_name} Ring",
        road_type=_get_road_type_from_tags(roundabout.tags),
        centerline_id=polyline.id,
        speed_limit=roundabout.speed_limit
    )
    road.add_polyline(polyline.id)
    road.is_ring_segment = True  # type: ignore

    road.lane_info = LaneInfo(
        left_count=0,
        right_count=roundabout.lane_count,
        lane_width=default_lane_width
    )

    section = _create_ring_lane_section(
        roundabout.lane_count, default_lane_width, len(roundabout.ring_points)
    )
    road.lane_sections = [section]

    return [(road, polyline)]


def _create_ring_lane_section(
    lane_count: int,
    lane_width: float,
    num_points: int
) -> LaneSection:
    """Create a lane section for a ring segment."""
    section = LaneSection(
        section_number=1,
        s_start=0.0,
        s_end=float(num_points - 1),  # Pixel units
        end_point_index=num_points - 1
    )

    # Add center lane
    center_lane = Lane(id=0, lane_type=LaneTypeEnum.NONE, width=0.0)
    section.lanes.append(center_lane)

    # Add right lanes (roundabout is one-way)
    for lane_idx in range(1, lane_count + 1):
        lane = Lane(
            id=-lane_idx,  # Right lanes are negative
            lane_type=LaneTypeEnum.DRIVING,
            road_mark_type=RoadMarkType.BROKEN if lane_idx < lane_count else RoadMarkType.SOLID,
            width=lane_width
        )
        section.lanes.append(lane)

    return section


def create_roundabout_junctions(
    roundabout: RoundaboutInfo,
    ring_segments: List[Tuple[Road, Polyline]],
    approach_roads: Dict[str, Road],
    polylines_dict: Dict[str, Polyline],
    verbose: bool = False
) -> List[Junction]:
    """
    Create junctions at each entry/exit point.

    Each junction connects:
    - Incoming ring segment
    - Outgoing ring segment
    - Approach road(s) at this connection point

    Args:
        roundabout: Analyzed roundabout geometry
        ring_segments: List of (Road, Polyline) for ring segments
        approach_roads: Dict of road_id -> Road for approach roads
        polylines_dict: Dict of polyline_id -> Polyline
        verbose: Print debug info

    Returns:
        List of Junction objects
    """
    if len(roundabout.connection_points) < 2:
        # No junctions needed for single ring road
        return []

    junctions = []
    n_segments = len(ring_segments)

    for i, cp in enumerate(roundabout.connection_points):
        # Ring segments: segment[i-1] ends here, segment[i] starts here
        incoming_ring_idx = (i - 1) % n_segments
        outgoing_ring_idx = i

        incoming_ring = ring_segments[incoming_ring_idx][0] if incoming_ring_idx < len(ring_segments) else None
        outgoing_ring = ring_segments[outgoing_ring_idx][0] if outgoing_ring_idx < len(ring_segments) else None

        # Find approach roads that connect at this point
        connected_approach_ids = []
        for road_id, road in approach_roads.items():
            centerline = polylines_dict.get(road.centerline_id)
            if centerline and centerline.osm_node_ids:
                # Check if road starts or ends at this connection node
                if cp.osm_node_id in [centerline.osm_node_ids[0], centerline.osm_node_ids[-1]]:
                    connected_approach_ids.append(road_id)

        # Build connected road IDs list
        connected_road_ids = []
        if incoming_ring:
            connected_road_ids.append(incoming_ring.id)
        if outgoing_ring:
            connected_road_ids.append(outgoing_ring.id)
        connected_road_ids.extend(connected_approach_ids)

        if len(connected_road_ids) < 2:
            if verbose:
                print(f"  Skipping junction at connection {i}: only {len(connected_road_ids)} roads")
            continue

        # Create junction
        road_name = _get_roundabout_name(roundabout)
        junction = Junction(
            name=f"{road_name} Entry {i + 1}",
            center_point=cp.position,
            connected_road_ids=connected_road_ids
        )

        # Set roundabout-specific fields
        junction.is_roundabout = True
        junction.roundabout_center = roundabout.center
        junction.roundabout_radius = roundabout.radius
        junction.roundabout_lane_count = roundabout.lane_count
        junction.roundabout_clockwise = roundabout.clockwise

        # Set entry/exit roads
        junction.entry_roads = list(connected_approach_ids)
        junction.exit_roads = list(connected_approach_ids)  # Same for now

        junctions.append(junction)

        if verbose:
            print(f"  Junction {i + 1} at ({cp.position[0]:.1f}, {cp.position[1]:.1f}): "
                  f"{len(connected_road_ids)} roads connected")

    return junctions


def link_ring_segments(
    ring_segments: List[Tuple[Road, Polyline]],
    junctions: List[Junction]
) -> None:
    """
    Set predecessor/successor relationships between ring segments.

    Ring is circular, so:
    - segment[0].predecessor = segment[N-1] (via junction)
    - segment[0].successor = segment[1] (via junction)
    - etc.

    Args:
        ring_segments: List of (Road, Polyline) tuples
        junctions: List of junctions at connection points
    """
    n_segments = len(ring_segments)
    if n_segments < 2:
        return

    for i in range(n_segments):
        road = ring_segments[i][0]
        prev_road = ring_segments[(i - 1) % n_segments][0]
        next_road = ring_segments[(i + 1) % n_segments][0]

        road.predecessor_id = prev_road.id
        road.predecessor_contact = "end"
        road.successor_id = next_road.id
        road.successor_contact = "start"


def _get_roundabout_name(roundabout: RoundaboutInfo) -> str:
    """Get a name for the roundabout from OSM tags."""
    if 'name' in roundabout.tags:
        return roundabout.tags['name']
    if 'ref' in roundabout.tags:
        return f"Roundabout {roundabout.tags['ref']}"
    return f"Roundabout {roundabout.osm_way_id}"


def _get_road_type_from_tags(tags: Dict[str, str]) -> RoadType:
    """Determine RoadType from OSM tags."""
    highway = tags.get('highway', '')

    road_type_map = {
        'motorway': RoadType.MOTORWAY,
        'motorway_link': RoadType.MOTORWAY,
        'trunk': RoadType.RURAL,
        'trunk_link': RoadType.RURAL,
        'primary': RoadType.RURAL,
        'primary_link': RoadType.RURAL,
        'secondary': RoadType.RURAL,
        'secondary_link': RoadType.RURAL,
        'tertiary': RoadType.TOWN,
        'tertiary_link': RoadType.TOWN,
        'residential': RoadType.TOWN,
        'living_street': RoadType.LOW_SPEED,
        'service': RoadType.TOWN,
    }

    return road_type_map.get(highway, RoadType.UNKNOWN)


# =========================================================================
# Connector Generation
# =========================================================================

def _generate_curved_path(
    start_point: Tuple[float, float],
    end_point: Tuple[float, float],
    center: Tuple[float, float],
    clockwise: bool,
    num_points: int = 10
) -> List[Tuple[float, float]]:
    """
    Generate a curved path between two points curving around a center.

    Uses circular arc interpolation for smooth roundabout connectors.

    Args:
        start_point: Starting point (x, y)
        end_point: Ending point (x, y)
        center: Center point to curve around (roundabout center)
        clockwise: True for clockwise curve, False for counter-clockwise
        num_points: Number of points to generate

    Returns:
        List of (x, y) points forming the curved path
    """
    # Calculate angles from center
    start_angle = math.atan2(start_point[1] - center[1], start_point[0] - center[0])
    end_angle = math.atan2(end_point[1] - center[1], end_point[0] - center[0])

    # Calculate radii
    start_radius = math.sqrt(
        (start_point[0] - center[0])**2 + (start_point[1] - center[1])**2
    )
    end_radius = math.sqrt(
        (end_point[0] - center[0])**2 + (end_point[1] - center[1])**2
    )

    # Calculate angular sweep
    if clockwise:
        # Clockwise: want decreasing angle
        sweep = start_angle - end_angle
        if sweep <= 0:
            sweep += 2 * math.pi
        sweep = -sweep  # Negative for clockwise
    else:
        # Counter-clockwise: want increasing angle
        sweep = end_angle - start_angle
        if sweep <= 0:
            sweep += 2 * math.pi

    # Generate points along the arc with interpolated radius
    path = []
    for i in range(num_points):
        t = i / (num_points - 1)
        angle = start_angle + t * sweep
        radius = start_radius + t * (end_radius - start_radius)

        x = center[0] + radius * math.cos(angle)
        y = center[1] + radius * math.sin(angle)
        path.append((x, y))

    return path


def _generate_entry_path(
    approach_end: Tuple[float, float],
    ring_point: Tuple[float, float],
    center: Tuple[float, float],
    clockwise: bool,
    num_points: int = 8
) -> List[Tuple[float, float]]:
    """
    Generate entry connector path from approach road to ring.

    The path curves smoothly from the approach road into the
    roundabout flow direction.

    Args:
        approach_end: Endpoint of approach road (x, y)
        ring_point: Point on ring to enter (x, y)
        center: Roundabout center
        clockwise: Traffic direction
        num_points: Points to generate

    Returns:
        List of points forming entry path
    """
    # For entry, we curve from outside toward the ring
    # Use a bezier-like curve with control point
    path = []

    # Calculate control point - offset from ring_point toward approach
    dx = approach_end[0] - ring_point[0]
    dy = approach_end[1] - ring_point[1]
    dist = math.sqrt(dx*dx + dy*dy)

    if dist < 1.0:
        # Points too close, just return straight line
        return [approach_end, ring_point]

    # Control point is between approach and ring, biased toward ring
    ctrl_x = ring_point[0] + dx * 0.4
    ctrl_y = ring_point[1] + dy * 0.4

    # Generate quadratic bezier curve
    for i in range(num_points):
        t = i / (num_points - 1)
        # Quadratic bezier: B(t) = (1-t)²P0 + 2(1-t)tP1 + t²P2
        u = 1 - t
        x = u*u * approach_end[0] + 2*u*t * ctrl_x + t*t * ring_point[0]
        y = u*u * approach_end[1] + 2*u*t * ctrl_y + t*t * ring_point[1]
        path.append((x, y))

    return path


def _generate_exit_path(
    ring_point: Tuple[float, float],
    approach_start: Tuple[float, float],
    center: Tuple[float, float],
    clockwise: bool,
    num_points: int = 8
) -> List[Tuple[float, float]]:
    """
    Generate exit connector path from ring to approach road.

    The path curves smoothly from the ring out toward the
    approach road.

    Args:
        ring_point: Point on ring to exit from (x, y)
        approach_start: Start point of approach road (x, y)
        center: Roundabout center
        clockwise: Traffic direction
        num_points: Points to generate

    Returns:
        List of points forming exit path
    """
    # Similar to entry but in reverse direction
    path = []

    dx = approach_start[0] - ring_point[0]
    dy = approach_start[1] - ring_point[1]
    dist = math.sqrt(dx*dx + dy*dy)

    if dist < 1.0:
        return [ring_point, approach_start]

    # Control point biased toward ring
    ctrl_x = ring_point[0] + dx * 0.6
    ctrl_y = ring_point[1] + dy * 0.6

    # Generate quadratic bezier curve
    for i in range(num_points):
        t = i / (num_points - 1)
        u = 1 - t
        x = u*u * ring_point[0] + 2*u*t * ctrl_x + t*t * approach_start[0]
        y = u*u * ring_point[1] + 2*u*t * ctrl_y + t*t * approach_start[1]
        path.append((x, y))

    return path


def _generate_through_path(
    incoming_end: Tuple[float, float],
    outgoing_start: Tuple[float, float],
    center: Tuple[float, float],
    clockwise: bool,
    num_points: int = 6
) -> List[Tuple[float, float]]:
    """
    Generate through connector path along the ring.

    Connects incoming ring segment to outgoing ring segment
    following the circular path. For adjacent junction points (same location),
    generates a short tangent arc instead of a full circle.

    Args:
        incoming_end: End point of incoming ring segment
        outgoing_start: Start point of outgoing ring segment
        center: Roundabout center
        clockwise: Traffic direction
        num_points: Points to generate

    Returns:
        List of points forming through path
    """
    # Check if points are at the same junction (very close together)
    dist = math.sqrt(
        (outgoing_start[0] - incoming_end[0])**2 +
        (outgoing_start[1] - incoming_end[1])**2
    )

    # If points are very close (same junction point), generate a short arc
    # that follows the ring tangent direction
    if dist < 5.0:  # Less than 5 pixels apart - same junction point
        # Calculate the angle from center to junction point
        mid_x = (incoming_end[0] + outgoing_start[0]) / 2
        mid_y = (incoming_end[1] + outgoing_start[1]) / 2
        junction_angle = math.atan2(mid_y - center[1], mid_x - center[0])
        radius = math.sqrt((mid_x - center[0])**2 + (mid_y - center[1])**2)

        # Generate a very short arc (about 5 degrees on each side of junction)
        arc_extent = math.radians(10)  # Total arc extent in radians
        direction = -1 if clockwise else 1

        path = []
        for i in range(num_points):
            t = i / (num_points - 1)
            # Go from -arc_extent/2 to +arc_extent/2 around junction angle
            angle = junction_angle + direction * (t - 0.5) * arc_extent
            x = center[0] + radius * math.cos(angle)
            y = center[1] + radius * math.sin(angle)
            path.append((x, y))

        return path

    # Points are at different locations - use curved arc between them
    return _generate_curved_path(
        incoming_end, outgoing_start, center, clockwise, num_points
    )


def create_roundabout_connectors(
    junction: Junction,
    roundabout: RoundaboutInfo,
    ring_segments: List[Tuple[Road, Polyline]],
    approach_roads: Dict[str, Road],
    polylines_dict: Dict[str, Polyline],
    junction_index: int,
    default_lane_width: float = 3.5,
    verbose: bool = False
) -> Tuple[List[ConnectingRoad], List[LaneConnection]]:
    """
    Create connecting roads and lane connections for a roundabout junction.

    Generates three types of connectors:
    1. Entry connectors: From each approach road into the ring
    2. Exit connectors: From the ring to each approach road
    3. Through connector: Continue around the ring

    Args:
        junction: The junction to add connectors to
        roundabout: Analyzed roundabout geometry
        ring_segments: List of (Road, Polyline) for ring segments
        approach_roads: Dict of road_id -> Road for approach roads
        polylines_dict: Dict of polyline_id -> Polyline
        junction_index: Index of this junction (for naming)
        default_lane_width: Lane width in meters
        verbose: Print debug info

    Returns:
        Tuple of (connecting_roads, lane_connections)
    """
    connecting_roads = []
    lane_connections = []

    # Get connection point for this junction
    if junction_index >= len(roundabout.connection_points):
        return [], []

    cp = roundabout.connection_points[junction_index]
    n_segments = len(ring_segments)

    # Identify ring roads at this junction
    incoming_ring_idx = (junction_index - 1) % n_segments
    outgoing_ring_idx = junction_index

    incoming_ring_road = ring_segments[incoming_ring_idx][0] if incoming_ring_idx < n_segments else None
    incoming_ring_polyline = ring_segments[incoming_ring_idx][1] if incoming_ring_idx < n_segments else None
    outgoing_ring_road = ring_segments[outgoing_ring_idx][0] if outgoing_ring_idx < n_segments else None
    outgoing_ring_polyline = ring_segments[outgoing_ring_idx][1] if outgoing_ring_idx < n_segments else None

    # Get ring endpoints
    incoming_end = incoming_ring_polyline.points[-1] if incoming_ring_polyline else None
    outgoing_start = outgoing_ring_polyline.points[0] if outgoing_ring_polyline else None

    if verbose:
        print(f"  Creating connectors for junction {junction_index + 1}:")

    # 1. Create THROUGH connector (ring continuation)
    if incoming_ring_road and outgoing_ring_road and incoming_end and outgoing_start:
        through_path = _generate_through_path(
            incoming_end, outgoing_start,
            roundabout.center, roundabout.clockwise
        )

        through_connector = ConnectingRoad(
            path=through_path,
            lane_count_left=0,
            lane_count_right=roundabout.lane_count,
            lane_width=default_lane_width,
            predecessor_road_id=incoming_ring_road.id,
            successor_road_id=outgoing_ring_road.id,
            contact_point_start="end",
            contact_point_end="start"
        )
        through_connector.ensure_lanes_initialized()
        connecting_roads.append(through_connector)

        # Create lane connections for through movement
        for lane_idx in range(1, roundabout.lane_count + 1):
            lc = LaneConnection(
                from_road_id=incoming_ring_road.id,
                from_lane_id=-lane_idx,  # Right lanes (negative)
                to_road_id=outgoing_ring_road.id,
                to_lane_id=-lane_idx,
                connecting_road_id=through_connector.id,
                turn_type="straight"
            )
            lane_connections.append(lc)

        if verbose:
            print(f"    Through: {len(through_path)} points")

    # 2. Create ENTRY and EXIT connectors for each approach road
    for approach_road_id in junction.entry_roads:
        approach_road = approach_roads.get(approach_road_id)
        if not approach_road:
            continue

        approach_polyline = polylines_dict.get(approach_road.centerline_id)
        if not approach_polyline or len(approach_polyline.points) < 2:
            continue

        # Determine if approach connects at start or end
        approach_node_ids = approach_polyline.osm_node_ids or []

        # Check which end connects to roundabout
        connects_at_end = False
        connects_at_start = False

        if approach_node_ids:
            if approach_node_ids[-1] == cp.osm_node_id:
                connects_at_end = True
            elif approach_node_ids[0] == cp.osm_node_id:
                connects_at_start = True
        else:
            # Fall back to geometric check
            end_dist = math.sqrt(
                (approach_polyline.points[-1][0] - cp.position[0])**2 +
                (approach_polyline.points[-1][1] - cp.position[1])**2
            )
            start_dist = math.sqrt(
                (approach_polyline.points[0][0] - cp.position[0])**2 +
                (approach_polyline.points[0][1] - cp.position[1])**2
            )
            connects_at_end = end_dist < start_dist
            connects_at_start = not connects_at_end

        # 2a. ENTRY connector (approach -> ring)
        if connects_at_end and outgoing_ring_road and outgoing_start:
            approach_end = approach_polyline.points[-1]

            entry_path = _generate_entry_path(
                approach_end, outgoing_start,
                roundabout.center, roundabout.clockwise
            )

            # Determine lane counts for entry
            approach_lanes = approach_road.lane_info.right_count if approach_road.lane_info else 1

            entry_connector = ConnectingRoad(
                path=entry_path,
                lane_count_left=0,
                lane_count_right=min(approach_lanes, roundabout.lane_count),
                lane_width=default_lane_width,
                predecessor_road_id=approach_road.id,
                successor_road_id=outgoing_ring_road.id,
                contact_point_start="end",
                contact_point_end="start"
            )
            entry_connector.ensure_lanes_initialized()
            connecting_roads.append(entry_connector)

            # Lane connections for entry (approach right lanes -> ring right lanes)
            for lane_idx in range(1, entry_connector.lane_count_right + 1):
                lc = LaneConnection(
                    from_road_id=approach_road.id,
                    from_lane_id=-lane_idx,
                    to_road_id=outgoing_ring_road.id,
                    to_lane_id=-lane_idx,
                    connecting_road_id=entry_connector.id,
                    turn_type="right"  # Entering roundabout is effectively a right turn
                )
                lane_connections.append(lc)

            if verbose:
                print(f"    Entry from {approach_road.name[:20]}: {len(entry_path)} points")

        # 2b. EXIT connector (ring -> approach)
        if connects_at_start and incoming_ring_road and incoming_end:
            approach_start = approach_polyline.points[0]

            exit_path = _generate_exit_path(
                incoming_end, approach_start,
                roundabout.center, roundabout.clockwise
            )

            # Determine lane counts for exit
            approach_lanes = approach_road.lane_info.left_count if approach_road.lane_info else 1

            exit_connector = ConnectingRoad(
                path=exit_path,
                lane_count_left=0,
                lane_count_right=min(approach_lanes, roundabout.lane_count),
                lane_width=default_lane_width,
                predecessor_road_id=incoming_ring_road.id,
                successor_road_id=approach_road.id,
                contact_point_start="end",
                contact_point_end="start"
            )
            exit_connector.ensure_lanes_initialized()
            connecting_roads.append(exit_connector)

            # Lane connections for exit (ring right lanes -> approach)
            for lane_idx in range(1, exit_connector.lane_count_right + 1):
                lc = LaneConnection(
                    from_road_id=incoming_ring_road.id,
                    from_lane_id=-lane_idx,
                    to_road_id=approach_road.id,
                    to_lane_id=-lane_idx,  # Assuming outgoing lane
                    connecting_road_id=exit_connector.id,
                    turn_type="right"  # Exiting roundabout is effectively a right turn
                )
                lane_connections.append(lc)

            if verbose:
                print(f"    Exit to {approach_road.name[:20]}: {len(exit_path)} points")

    return connecting_roads, lane_connections


def generate_all_roundabout_connectors(
    roundabout: RoundaboutInfo,
    junctions: List[Junction],
    ring_segments: List[Tuple[Road, Polyline]],
    approach_roads: Dict[str, Road],
    polylines_dict: Dict[str, Polyline],
    default_lane_width: float = 3.5,
    verbose: bool = False
) -> None:
    """
    Generate connectors for all junctions of a roundabout.

    Updates each junction's connecting_roads and lane_connections lists.

    Args:
        roundabout: Analyzed roundabout geometry
        junctions: List of Junction objects for this roundabout
        ring_segments: List of (Road, Polyline) for ring segments
        approach_roads: Dict of road_id -> Road for approach roads
        polylines_dict: Dict of polyline_id -> Polyline
        default_lane_width: Lane width in meters
        verbose: Print debug info
    """
    if verbose:
        print(f"\nGenerating connectors for roundabout {roundabout.osm_way_id}:")

    for i, junction in enumerate(junctions):
        connectors, lane_conns = create_roundabout_connectors(
            junction=junction,
            roundabout=roundabout,
            ring_segments=ring_segments,
            approach_roads=approach_roads,
            polylines_dict=polylines_dict,
            junction_index=i,
            default_lane_width=default_lane_width,
            verbose=verbose
        )

        # Add to junction
        for cr in connectors:
            junction.add_connecting_road(cr)

        for lc in lane_conns:
            junction.add_lane_connection(lc)

    if verbose:
        total_connectors = sum(len(j.connecting_roads) for j in junctions)
        total_lane_conns = sum(len(j.lane_connections) for j in junctions)
        print(f"  Total: {total_connectors} connecting roads, {total_lane_conns} lane connections")

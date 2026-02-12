"""
Roundabout detection and conversion from OSM data.

Handles the complex logic of converting OSM roundabouts to segmented roads
with proper junctions at each entry/exit point.
"""

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

from orbit.models import Junction, Road
from orbit.models.connecting_road import ConnectingRoad
from orbit.models.lane import Lane
from orbit.models.lane import LaneType as LaneTypeEnum
from orbit.models.lane_connection import LaneConnection
from orbit.models.lane_section import LaneSection
from orbit.models.polyline import LineType, Polyline, RoadMarkType
from orbit.models.road import LaneInfo, RoadType
from orbit.utils.geometry import generate_simple_connection_path
from orbit.utils.logging_config import get_logger

from .osm_parser import OSMData, OSMWay

logger = get_logger(__name__)

if TYPE_CHECKING:
    from orbit.utils.coordinate_transform import CoordinateTransformer


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


def _get_road_lane_width(road: Road, default: float = 3.5) -> float:
    """
    Get the lane width for a road.

    Checks lane_info first, then falls back to default.

    Args:
        road: The road to get lane width from
        default: Default width if not set

    Returns:
        Lane width in meters
    """
    if road.lane_info and road.lane_info.lane_width:
        return road.lane_info.lane_width
    # Try to get from first lane section
    if road.lane_sections:
        for lane in road.lane_sections[0].lanes:
            if lane.id != 0 and lane.width > 0:
                return lane.width
    return default


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

    # Sort connection points by ring_index (position in OSM way)
    # This ensures segments are created in the order they appear along the ring
    # The OSM way direction determines the segment order, which should match traffic flow
    connection_points.sort(key=lambda cp: cp.ring_index)

    if verbose:
        logger.debug("Roundabout %s: center=(%.1f, %.1f), radius=%.1fpx, %d connections, %s",
                     osm_way.id, center_x, center_y, radius, len(connection_points),
                     'clockwise' if clockwise else 'counter-clockwise')

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
                logger.debug("  Skipping segment %d: too few points", i)
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
            logger.debug("  Ring segment %d: %d points, from connection %d to %d",
                         i + 1, len(segment_points), i, (i + 1) % n_connections)

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
        # Separate into incoming (road ends here) and outgoing (road starts here)
        connected_approach_ids = []
        incoming_approach_ids = []  # Roads that END at this junction (entry)
        outgoing_approach_ids = []  # Roads that START at this junction (exit)

        for road_id, road in approach_roads.items():
            centerline = polylines_dict.get(road.centerline_id)
            if centerline and centerline.osm_node_ids:
                if cp.osm_node_id == centerline.osm_node_ids[-1]:
                    # Road ENDS at this node → INCOMING (can create entry connector)
                    connected_approach_ids.append(road_id)
                    incoming_approach_ids.append(road_id)
                elif cp.osm_node_id == centerline.osm_node_ids[0]:
                    # Road STARTS at this node → OUTGOING (can create exit connector)
                    connected_approach_ids.append(road_id)
                    outgoing_approach_ids.append(road_id)

        # Build connected road IDs list
        connected_road_ids = []
        if incoming_ring:
            connected_road_ids.append(incoming_ring.id)
        if outgoing_ring:
            connected_road_ids.append(outgoing_ring.id)
        connected_road_ids.extend(connected_approach_ids)

        if len(connected_road_ids) < 2:
            if verbose:
                logger.debug("  Skipping junction at connection %d: only %d roads",
                             i, len(connected_road_ids))
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

        # Set entry/exit roads (pre-determined from OSM node positions)
        junction.entry_roads = incoming_approach_ids  # Roads that END here
        junction.exit_roads = outgoing_approach_ids   # Roads that START here

        junctions.append(junction)

        if verbose:
            logger.debug("  Junction %d at (%.1f, %.1f): %d roads connected",
                         i + 1, cp.position[0], cp.position[1], len(connected_road_ids))

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
# Connector Generation Helpers
# =========================================================================

def _calculate_endpoint_heading(points: List[Tuple[float, float]], at_start: bool) -> float:
    """
    Calculate heading at a polyline start or end point.

    Args:
        points: List of polyline points
        at_start: True for start point heading, False for end point heading

    Returns:
        Heading in radians (0 = east, π/2 = north)
    """
    if len(points) < 2:
        return 0.0

    if at_start:
        dx = points[1][0] - points[0][0]
        dy = points[1][1] - points[0][1]
    else:
        dx = points[-1][0] - points[-2][0]
        dy = points[-1][1] - points[-2][1]

    return math.atan2(dy, dx)


def _calculate_ring_tangent(point: Tuple[float, float], center: Tuple[float, float],
                            clockwise: bool) -> float:
    """
    Calculate ring tangent heading at a point on the ring.

    The tangent is perpendicular to the radial direction from center.

    Args:
        point: Point on the ring (x, y) in image/pixel coordinates
        center: Roundabout center (x, y) in image/pixel coordinates
        clockwise: True for visual clockwise traffic, False for visual counter-clockwise
                   (Visual CCW = standard for right-hand traffic like Sweden)

    Returns:
        Tangent heading in radians in image coordinates (0 = right, π/2 = down)
    """
    dx = point[0] - center[0]
    dy = point[1] - center[1]
    radial_angle = math.atan2(dy, dx)

    # Tangent is perpendicular to radial direction
    # In image coords (y-down), visual CCW appears as mathematical CW rotation
    # Visual CCW (clockwise=False): tangent = radial - 90° (CW rotation in image coords)
    # Visual CW (clockwise=True): tangent = radial + 90° (CCW rotation in image coords)
    if clockwise:
        return radial_angle + math.pi / 2
    else:
        return radial_angle - math.pi / 2


def _is_approach_incoming(approach_points: List[Tuple[float, float]],
                          junction_pos: Tuple[float, float],
                          tolerance: float = 20.0) -> bool:
    """
    Check if approach road ends at junction (is incoming/can enter roundabout).

    Args:
        approach_points: Polyline points of approach road
        junction_pos: Junction center position
        tolerance: Distance tolerance in pixels

    Returns:
        True if approach road ends at junction (can be used for entry)
    """
    if len(approach_points) < 2:
        return False

    end_dist = math.sqrt(
        (approach_points[-1][0] - junction_pos[0])**2 +
        (approach_points[-1][1] - junction_pos[1])**2
    )
    return end_dist < tolerance


def _is_approach_outgoing(approach_points: List[Tuple[float, float]],
                          junction_pos: Tuple[float, float],
                          tolerance: float = 20.0) -> bool:
    """
    Check if approach road starts at junction (is outgoing/can exit roundabout).

    Args:
        approach_points: Polyline points of approach road
        junction_pos: Junction center position
        tolerance: Distance tolerance in pixels

    Returns:
        True if approach road starts at junction (can be used for exit)
    """
    if len(approach_points) < 2:
        return False

    start_dist = math.sqrt(
        (approach_points[0][0] - junction_pos[0])**2 +
        (approach_points[0][1] - junction_pos[1])**2
    )
    return start_dist < tolerance


# =========================================================================
# Connector Path Generation (deprecated - kept for reference)
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

    Generates three types of connectors using smooth tangent-continuous curves:
    1. Through connector: Continue around the ring (always created)
    2. Entry connectors: From approach road into the ring (only if approach is incoming)
    3. Exit connectors: From the ring to approach road (only if approach is outgoing)

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

    _cp = roundabout.connection_points[junction_index]
    n_segments = len(ring_segments)

    # Identify ring roads at this junction
    incoming_ring_idx = (junction_index - 1) % n_segments
    outgoing_ring_idx = junction_index

    incoming_ring_road = ring_segments[incoming_ring_idx][0] if incoming_ring_idx < n_segments else None
    incoming_ring_polyline = ring_segments[incoming_ring_idx][1] if incoming_ring_idx < n_segments else None
    outgoing_ring_road = ring_segments[outgoing_ring_idx][0] if outgoing_ring_idx < n_segments else None
    outgoing_ring_polyline = ring_segments[outgoing_ring_idx][1] if outgoing_ring_idx < n_segments else None

    # Get ring endpoints (these are now offset from the junction center)
    incoming_end = incoming_ring_polyline.points[-1] if incoming_ring_polyline else None
    outgoing_start = outgoing_ring_polyline.points[0] if outgoing_ring_polyline else None

    if verbose:
        logger.debug("  Creating connectors for junction %d:", junction_index + 1)

    # 1. Create THROUGH connector (ring continuation)
    if incoming_ring_road and outgoing_ring_road and incoming_end and outgoing_start:
        # Calculate headings from actual polyline directions (not theoretical ring tangent)
        # This is correct after road endpoints have been offset from the junction
        incoming_heading = _calculate_endpoint_heading(incoming_ring_polyline.points, at_start=False)
        outgoing_heading = _calculate_endpoint_heading(outgoing_ring_polyline.points, at_start=True)

        # Generate smooth tangent-continuous path
        through_path, coeffs = generate_simple_connection_path(
            from_pos=incoming_end,
            from_heading=incoming_heading,
            to_pos=outgoing_start,
            to_heading=outgoing_heading,
            num_points=10,
            tangent_scale=0.5  # Shorter tangent for tight roundabout curves
        )

        if through_path:
            # Unpack ParamPoly3D coefficients
            aU, bU, cU, dU, aV, bV, cV, dV = coeffs

            # Get lane widths from connected ring roads
            incoming_width = _get_road_lane_width(incoming_ring_road, default_lane_width)
            outgoing_width = _get_road_lane_width(outgoing_ring_road, default_lane_width)
            avg_width = (incoming_width + outgoing_width) / 2

            through_connector = ConnectingRoad(
                path=through_path,
                lane_count_left=0,
                lane_count_right=roundabout.lane_count,
                lane_width=avg_width,
                predecessor_road_id=incoming_ring_road.id,
                successor_road_id=outgoing_ring_road.id,
                contact_point_start="end",
                contact_point_end="start"
            )
            through_connector.lane_width_start = incoming_width
            through_connector.lane_width_end = outgoing_width

            # Store ParamPoly3D coefficients for proper OpenDrive export
            through_connector.aU = aU
            through_connector.bU = bU
            through_connector.cU = cU
            through_connector.dU = dU
            through_connector.aV = aV
            through_connector.bV = bV
            through_connector.cV = cV
            through_connector.dV = dV
            through_connector.stored_start_heading = incoming_heading
            through_connector.stored_end_heading = outgoing_heading

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
                path_len = sum(
                    math.sqrt((through_path[i+1][0]-through_path[i][0])**2 +
                              (through_path[i+1][1]-through_path[i][1])**2)
                    for i in range(len(through_path)-1)
                )
                logger.debug("    Through: %d points, ~%.1fpx", len(through_path), path_len)

    # 2. Create ENTRY connectors for incoming approach roads
    # Entry roads are pre-determined - they END at this junction (no distance check needed)
    for approach_road_id in junction.entry_roads:
        approach_road = approach_roads.get(approach_road_id)
        if not approach_road:
            continue

        approach_polyline = polylines_dict.get(approach_road.centerline_id)
        if not approach_polyline or len(approach_polyline.points) < 2:
            continue

        approach_points = approach_polyline.points

        if outgoing_ring_road and outgoing_start:
            approach_end = approach_points[-1]

            # Entry connector: approach road end → outgoing ring start
            entry_ring_pos = outgoing_start
            entry_ring_road = outgoing_ring_road
            contact_end = "start"

            # Calculate headings from actual polyline directions
            approach_heading = _calculate_endpoint_heading(approach_points, at_start=False)
            ring_heading = _calculate_endpoint_heading(outgoing_ring_polyline.points, at_start=True)

            # Generate smooth entry path
            entry_path, coeffs = generate_simple_connection_path(
                from_pos=approach_end,
                from_heading=approach_heading,
                to_pos=entry_ring_pos,
                to_heading=ring_heading,
                num_points=10,
                tangent_scale=0.6
            )

            if entry_path:
                aU, bU, cU, dU, aV, bV, cV, dV = coeffs

                approach_lanes = approach_road.lane_info.right_count if approach_road.lane_info else 1

                # Get lane widths from connected roads
                approach_width = _get_road_lane_width(approach_road, default_lane_width)
                ring_width = _get_road_lane_width(entry_ring_road, default_lane_width)
                avg_width = (approach_width + ring_width) / 2

                entry_connector = ConnectingRoad(
                    path=entry_path,
                    lane_count_left=0,
                    lane_count_right=min(approach_lanes, roundabout.lane_count),
                    lane_width=avg_width,
                    predecessor_road_id=approach_road.id,
                    successor_road_id=entry_ring_road.id,
                    contact_point_start="end",
                    contact_point_end=contact_end
                )
                entry_connector.lane_width_start = approach_width
                entry_connector.lane_width_end = ring_width

                # Store ParamPoly3D coefficients
                entry_connector.aU = aU
                entry_connector.bU = bU
                entry_connector.cU = cU
                entry_connector.dU = dU
                entry_connector.aV = aV
                entry_connector.bV = bV
                entry_connector.cV = cV
                entry_connector.dV = dV
                entry_connector.stored_start_heading = approach_heading
                entry_connector.stored_end_heading = ring_heading

                entry_connector.ensure_lanes_initialized()
                connecting_roads.append(entry_connector)

                # Lane connections for entry
                for lane_idx in range(1, entry_connector.lane_count_right + 1):
                    lc = LaneConnection(
                        from_road_id=approach_road.id,
                        from_lane_id=-lane_idx,
                        to_road_id=outgoing_ring_road.id,
                        to_lane_id=-lane_idx,
                        connecting_road_id=entry_connector.id,
                        turn_type="right"
                    )
                    lane_connections.append(lc)

                if verbose:
                    logger.debug("    Entry from %s: %d points", approach_road.name[:20], len(entry_path))

    # 3. Create EXIT connectors for outgoing approach roads
    # Exit roads are pre-determined - they START at this junction (no distance check needed)
    for approach_road_id in junction.exit_roads:
        approach_road = approach_roads.get(approach_road_id)
        if not approach_road:
            continue

        approach_polyline = polylines_dict.get(approach_road.centerline_id)
        if not approach_polyline or len(approach_polyline.points) < 2:
            continue

        approach_points = approach_polyline.points

        if incoming_ring_road and incoming_end:
            approach_start = approach_points[0]

            # Exit connector: incoming ring end → approach road start
            exit_ring_pos = incoming_end
            exit_ring_road = incoming_ring_road
            contact_start = "end"

            # Calculate headings from actual polyline directions
            ring_heading = _calculate_endpoint_heading(incoming_ring_polyline.points, at_start=False)
            approach_heading = _calculate_endpoint_heading(approach_points, at_start=True)

            # Generate smooth exit path
            exit_path, coeffs = generate_simple_connection_path(
                from_pos=exit_ring_pos,
                from_heading=ring_heading,
                to_pos=approach_start,
                to_heading=approach_heading,
                num_points=10,
                tangent_scale=0.6
            )

            if exit_path:
                aU, bU, cU, dU, aV, bV, cV, dV = coeffs

                # Exit traffic uses RIGHT lanes of the approach road (negative lane IDs)
                approach_lanes = approach_road.lane_info.right_count if approach_road.lane_info else 1

                # Get lane widths from connected roads
                ring_width = _get_road_lane_width(exit_ring_road, default_lane_width)
                approach_width = _get_road_lane_width(approach_road, default_lane_width)
                avg_width = (ring_width + approach_width) / 2

                exit_connector = ConnectingRoad(
                    path=exit_path,
                    lane_count_left=0,
                    lane_count_right=min(approach_lanes, roundabout.lane_count),
                    lane_width=avg_width,
                    predecessor_road_id=exit_ring_road.id,
                    successor_road_id=approach_road.id,
                    contact_point_start=contact_start,
                    contact_point_end="start"
                )
                exit_connector.lane_width_start = ring_width
                exit_connector.lane_width_end = approach_width

                # Store ParamPoly3D coefficients
                exit_connector.aU = aU
                exit_connector.bU = bU
                exit_connector.cU = cU
                exit_connector.dU = dU
                exit_connector.aV = aV
                exit_connector.bV = bV
                exit_connector.cV = cV
                exit_connector.dV = dV
                exit_connector.stored_start_heading = ring_heading
                exit_connector.stored_end_heading = approach_heading

                exit_connector.ensure_lanes_initialized()
                connecting_roads.append(exit_connector)

                # Lane connections for exit
                for lane_idx in range(1, exit_connector.lane_count_right + 1):
                    lc = LaneConnection(
                        from_road_id=incoming_ring_road.id,
                        from_lane_id=-lane_idx,
                        to_road_id=approach_road.id,
                        to_lane_id=-lane_idx,
                        connecting_road_id=exit_connector.id,
                        turn_type="right"
                    )
                    lane_connections.append(lc)

                if verbose:
                    logger.debug("    Exit to %s: %d points", approach_road.name[:20], len(exit_path))

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
        logger.debug("Generating connectors for roundabout %s:", roundabout.osm_way_id)

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
        logger.debug("  Total: %d connecting roads, %d lane connections",
                     total_connectors, total_lane_conns)

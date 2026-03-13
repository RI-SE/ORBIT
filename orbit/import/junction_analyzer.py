"""
Junction geometry analyzer for OSM import.

Analyzes junction geometry to automatically generate connecting roads and lane links.
"""

import math
from dataclasses import dataclass

# Type hint for circular import avoidance
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from orbit.models import Junction, LaneConnection, Polyline, Project, Road
from orbit.models.road import LaneInfo
from orbit.utils.geometry import (
    generate_connection_path_geo,
    generate_simple_connection_path,
)
from orbit.utils.logging_config import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from orbit.utils.coordinate_transform import CoordinateTransformer


@dataclass
class RoadEndpointInfo:
    """Information about a road endpoint at a junction."""
    road_id: str
    road_name: str
    position: Tuple[float, float]  # (x, y) in pixels - centerline position
    heading: float  # Radians, 0 = east, π/2 = north
    at_junction: str  # "start" or "end"
    is_incoming: bool  # Road ends at junction
    is_outgoing: bool  # Road starts at junction
    left_lane_count: int
    right_lane_count: int
    lane_width: float  # Meters
    relative_angle: float = 0.0  # Angle relative to reference direction (set later)
    position_geo: Optional[Tuple[float, float]] = None  # (lon, lat) - geographic position
    direction_geo: Optional[Tuple[float, float]] = None  # (lon, lat) - point in direction of travel

    def get_right_lane_center_position(self, scale: float, flip_heading: bool = False) -> Tuple[float, float]:
        """
        Calculate the position of the right lane center for right-hand traffic.

        For right-hand traffic, the right lanes are on the right side when traveling
        in the direction of the heading. This is 90° clockwise (perpendicular right).

        Args:
            scale: Meters per pixel conversion factor
            flip_heading: If True, flip the heading by 180° before calculating offset.
                         Use this when the road's stored direction is opposite to the
                         connection direction (e.g., TO endpoint where road ends at junction).

        Returns:
            (x, y) position of the right lane center in pixels
        """
        import math

        # Convert lane width from meters to pixels
        lane_width_px = self.lane_width / scale

        # Use flipped heading if requested (for roads stored in opposite direction)
        effective_heading = self.heading + math.pi if flip_heading else self.heading

        # For right-hand traffic, right side is -90° from heading (clockwise)
        # In standard math coordinates: right_perpendicular = heading - π/2
        right_perpendicular = effective_heading - math.pi / 2

        # Distance to right lane center depends on number of right lanes
        # If 1 lane: offset by lane_width/2 (to center of lane)
        # If 2 lanes: offset by lane_width * 1.5 (to boundary between lanes)
        # General: offset by (right_lane_count / 2.0) * lane_width
        if self.right_lane_count > 0:
            offset_distance = (self.right_lane_count / 2.0) * lane_width_px
        else:
            # No right lanes, use centerline
            offset_distance = 0.0

        # Calculate offset position
        offset_x = self.position[0] + offset_distance * math.cos(right_perpendicular)
        offset_y = self.position[1] + offset_distance * math.sin(right_perpendicular)

        return (offset_x, offset_y)

    def get_right_lane_center_position_geo(
        self,
        transformer: 'CoordinateTransformer',
        flip_heading: bool = False
    ) -> Optional[Tuple[float, float]]:
        """
        Calculate the geo position of the right lane center for right-hand traffic.

        Works in metric space then converts back to geo coordinates.

        Args:
            transformer: CoordinateTransformer for geo<->meters conversion
            flip_heading: If True, flip the heading by 180° before calculating offset.

        Returns:
            (lon, lat) position of the right lane center, or None if geo coords not available
        """
        if not self.position_geo:
            return None

        # Use flipped heading if requested
        effective_heading = self.heading + math.pi if flip_heading else self.heading

        # Convert heading from pixel space to metric space
        # Pixel space: Y increases downward, Metric space: Y increases upward
        effective_heading_metric = -effective_heading

        # For right-hand traffic, right side is -90° from heading (clockwise)
        right_perpendicular = effective_heading_metric - math.pi / 2

        # Distance to right lane center in meters
        if self.right_lane_count > 0:
            offset_meters = (self.right_lane_count / 2.0) * self.lane_width
        else:
            offset_meters = 0.0

        # Convert geo position to meters, apply offset, convert back
        lon, lat = self.position_geo
        mx, my = transformer.latlon_to_meters(lat, lon)
        offset_mx = mx + offset_meters * math.cos(right_perpendicular)
        offset_my = my + offset_meters * math.sin(right_perpendicular)
        lat_out, lon_out = transformer.meters_to_latlon(offset_mx, offset_my)
        return (lon_out, lat_out)


@dataclass
class ConnectionPattern:
    """A suggested connection between two roads at a junction."""
    from_road_id: str
    to_road_id: str
    turn_type: str  # "straight", "left", "right", "uturn"
    turn_angle: float  # Radians
    from_endpoint: RoadEndpointInfo
    to_endpoint: RoadEndpointInfo
    priority: int = 0  # Higher = higher priority


def normalize_angle(angle: float) -> float:
    """
    Normalize angle to [-π, π] range.

    Args:
        angle: Angle in radians

    Returns:
        Normalized angle in [-π, π]
    """
    while angle > math.pi:
        angle -= 2 * math.pi
    while angle < -math.pi:
        angle += 2 * math.pi
    return angle


def calculate_heading(from_point: Tuple[float, float], to_point: Tuple[float, float]) -> float:
    """
    Calculate heading from one point to another.

    Args:
        from_point: Starting point (x, y)
        to_point: Ending point (x, y)

    Returns:
        Heading in radians (0 = east, π/2 = north)
    """
    dx = to_point[0] - from_point[0]
    dy = to_point[1] - from_point[1]
    return math.atan2(dy, dx)


def classify_turn_type(turn_angle: float) -> str:
    """
    Classify turn type based on angle change.

    Args:
        turn_angle: Change in heading in radians (normalized to [-π, π])

    Returns:
        Turn type: "straight", "right", "left", or "uturn"
    """
    # Convert to degrees for easier thresholds
    angle_deg = math.degrees(abs(turn_angle))

    if angle_deg < 30:
        return "straight"
    elif angle_deg > 150:
        return "uturn"
    elif turn_angle > 0:
        # Positive = counterclockwise = left turn (in standard coordinates)
        return "left"
    else:
        # Negative = clockwise = right turn
        return "right"


def get_road_endpoint_heading(road: Road, polyline: Polyline, at_junction: str) -> float:
    """
    Get the heading of a road at its junction endpoint.

    Args:
        road: Road object
        polyline: Centerline polyline
        at_junction: "start" or "end" - which end is at junction

    Returns:
        Heading in radians
    """
    points = polyline.points
    if len(points) < 2:
        return 0.0

    if at_junction == "end":
        # Heading toward junction (from second-to-last to last point)
        return calculate_heading(points[-2], points[-1])
    else:  # "start"
        # Heading away from junction (from first to second point)
        return calculate_heading(points[0], points[1])


def analyze_junction_geometry(junction: Junction,
                              roads_dict: Dict[str, Road],
                              polylines_dict: Dict[str, Polyline],
                              skip_distance_check: bool = False) -> Dict[str, Any]:
    """
    Analyze geometric properties of a junction.

    Args:
        junction: Junction object with connected_road_ids
        roads_dict: Dictionary of road_id -> Road object
        polylines_dict: Dictionary of polyline_id -> Polyline object
        skip_distance_check: If True, skip the distance validation check.
                           Use when roads have been offset from junction center
                           but we trust the connected_road_ids list.

    Returns:
        Dictionary with:
        - 'endpoints': List of RoadEndpointInfo objects
        - 'center': Junction center point (x, y)
        - 'radius': Approximate junction radius (largest distance from center to endpoint)
    """
    endpoints = []
    center = junction.center_point if junction.center_point else (0.0, 0.0)

    for road_id in junction.connected_road_ids:
        road = roads_dict.get(road_id)
        if not road or not road.centerline_id:
            continue

        centerline = polylines_dict.get(road.centerline_id)
        if not centerline or len(centerline.points) < 2:
            continue

        # Determine which endpoint is at junction
        start_dist = math.sqrt(
            (centerline.points[0][0] - center[0])**2 +
            (centerline.points[0][1] - center[1])**2
        )
        end_dist = math.sqrt(
            (centerline.points[-1][0] - center[0])**2 +
            (centerline.points[-1][1] - center[1])**2
        )

        if start_dist < end_dist:
            at_junction = "start"
            junction_point = centerline.points[0]
            heading = get_road_endpoint_heading(road, centerline, "start")
            closest_dist = start_dist
            # Get geo position and direction point if available
            if centerline.geo_points and len(centerline.geo_points) > 0:
                junction_point_geo = centerline.geo_points[0]
                # Direction is from first to second point (away from junction)
                if len(centerline.geo_points) >= 2:
                    direction_geo = centerline.geo_points[1]
                else:
                    direction_geo = None
            else:
                junction_point_geo = None
                direction_geo = None
        else:
            at_junction = "end"
            junction_point = centerline.points[-1]
            heading = get_road_endpoint_heading(road, centerline, "end")
            closest_dist = end_dist
            # Get geo position and direction point if available
            if centerline.geo_points and len(centerline.geo_points) > 0:
                junction_point_geo = centerline.geo_points[-1]
                # Direction is from second-to-last to last point (toward junction)
                if len(centerline.geo_points) >= 2:
                    direction_geo = centerline.geo_points[-2]
                else:
                    direction_geo = None
            else:
                junction_point_geo = None
                direction_geo = None

        # Assume roads are bidirectional (two-way) unless we have explicit oneway information
        # This allows traffic to flow in both directions through the junction
        # TODO: Check road.oneway attribute from OSM data when available
        is_incoming = True
        is_outgoing = True

        # Validate that the endpoint is actually close to the junction
        # Only check distance if skip_distance_check=False
        if not skip_distance_check:
            # After road splitting, endpoints should be AT junction nodes (distance ~0)
            # Allow some tolerance for pixel alignment (10 pixels max)
            MAX_ENDPOINT_DISTANCE = 10.0  # pixels

            if closest_dist > MAX_ENDPOINT_DISTANCE:
                # Endpoint is too far from junction - road doesn't actually connect here
                # This can happen if road splitting didn't occur or junction center is wrong
                continue  # Skip this road

        # Get lane counts from road's last section (at junction)
        if road.lane_sections:
            section = road.lane_sections[-1] if at_junction == "end" else road.lane_sections[0]
            left_count = len([lane for lane in section.lanes if lane.id > 0])
            right_count = len([lane for lane in section.lanes if lane.id < 0])
            # Get lane width from first driving lane
            lane_width = next((lane.width for lane in section.lanes if lane.id != 0), 3.5)
        else:
            # Fallback to lane_info if no sections
            if hasattr(road, 'lane_info') and road.lane_info:
                left_count = road.lane_info.left_count
                right_count = road.lane_info.right_count
                lane_width = road.lane_info.lane_width
            else:
                left_count = 0
                right_count = 1
                lane_width = 3.5

        endpoint_info = RoadEndpointInfo(
            road_id=road_id,
            road_name=road.name,
            position=junction_point,
            heading=heading,
            at_junction=at_junction,
            is_incoming=is_incoming,
            is_outgoing=is_outgoing,
            left_lane_count=left_count,
            right_lane_count=right_count,
            lane_width=lane_width,
            position_geo=junction_point_geo,
            direction_geo=direction_geo
        )
        endpoints.append(endpoint_info)

    # Calculate relative angles (all angles relative to north)
    for endpoint in endpoints:
        endpoint.relative_angle = normalize_angle(endpoint.heading)

    # Sort by angle for consistent ordering
    endpoints.sort(key=lambda e: e.relative_angle)

    # Calculate approximate junction radius
    max_radius = 0.0
    if endpoints:
        for endpoint in endpoints:
            dist = math.sqrt(
                (endpoint.position[0] - center[0])**2 +
                (endpoint.position[1] - center[1])**2
            )
            max_radius = max(max_radius, dist)

    return {
        'endpoints': endpoints,
        'center': center,
        'radius': max_radius
    }


def detect_connection_patterns(geometry_info: Dict[str, Any]) -> List[ConnectionPattern]:
    """
    Detect likely connection patterns based on junction geometry.

    Args:
        geometry_info: Output from analyze_junction_geometry()

    Returns:
        List of ConnectionPattern objects
    """
    endpoints = geometry_info['endpoints']
    patterns = []

    # For each incoming road, find possible outgoing roads
    for from_endpoint in endpoints:
        if not from_endpoint.is_incoming:
            continue

        for to_endpoint in endpoints:
            if not to_endpoint.is_outgoing:
                continue

            # Can't connect to same road
            if from_endpoint.road_id == to_endpoint.road_id:
                continue

            # Calculate turn angle accounting for road direction at junction
            # The heading direction depends on at_junction:
            # - "end": road heading points INTO junction
            # - "start": road heading points AWAY from junction

            # Calculate effective incoming heading (direction traffic enters junction)
            if from_endpoint.at_junction == "end":
                # Road ends at junction: heading already points into junction
                incoming_heading = from_endpoint.heading
            else:
                # Road starts at junction: heading points away, flip for incoming direction
                incoming_heading = from_endpoint.heading + math.pi

            # Calculate effective outgoing heading (direction traffic exits junction)
            if to_endpoint.at_junction == "end":
                # Road ends at junction: heading points in, flip for outgoing direction
                outgoing_heading = to_endpoint.heading + math.pi
            else:
                # Road starts at junction: heading already points away = outgoing direction
                outgoing_heading = to_endpoint.heading

            # Turn angle is the difference
            turn_angle = normalize_angle(outgoing_heading - incoming_heading)

            # Classify turn
            turn_type = classify_turn_type(turn_angle)

            # Calculate priority (straight connections have higher priority)
            if turn_type == "straight":
                priority = 3
            elif turn_type == "right":
                priority = 2
            elif turn_type == "left":
                priority = 1
            else:  # uturn
                priority = 0

            pattern = ConnectionPattern(
                from_road_id=from_endpoint.road_id,
                to_road_id=to_endpoint.road_id,
                turn_type=turn_type,
                turn_angle=turn_angle,
                from_endpoint=from_endpoint,
                to_endpoint=to_endpoint,
                priority=priority
            )
            patterns.append(pattern)

    return patterns


def filter_unlikely_connections(patterns: List[ConnectionPattern],
                               roads_dict: Dict[str, Road]) -> List[ConnectionPattern]:
    """
    Filter out connection patterns that should not become connecting roads.

    # Note: We do NOT filter by successor/predecessor relationships here.
    # When roads are split at a junction, they get linked via successor/predecessor,
    # but they still need connecting roads within the junction for each direction.
    # The successor/predecessor links are cleaned up by clear_cross_junction_road_links().

    Args:
        patterns: List of all possible connection patterns
        roads_dict: Dictionary of road_id -> Road object

    Returns:
        All patterns unchanged — filtering is intentionally a no-op.
    """
    return patterns


def generate_lane_links_for_connection(from_endpoint: RoadEndpointInfo,
                                      to_endpoint: RoadEndpointInfo,
                                      turn_type: str) -> List[Tuple[int, int]]:
    """
    Generate lane-to-lane links for a connection.

    Args:
        from_endpoint: Incoming road endpoint info
        to_endpoint: Outgoing road endpoint info
        turn_type: Type of turn ("straight", "left", "right", "uturn")

    Returns:
        List of (from_lane_id, to_lane_id) tuples
    """
    lane_links = []

    # Determine which lanes are in play
    # For incoming road ending at junction: use right lanes (negative IDs)
    # For outgoing road starting at junction: use right lanes (negative IDs)

    # Get driving lanes
    if from_endpoint.at_junction == "end":
        # Road ends at junction, use right lanes (they're driving toward junction)
        from_lanes = list(range(-1, -(from_endpoint.right_lane_count + 1), -1))
    else:
        # Road starts at junction, use left lanes (they're driving away from junction)
        from_lanes = list(range(1, from_endpoint.left_lane_count + 1))

    if to_endpoint.at_junction == "start":
        # Road starts from junction, use right lanes (they're driving away from junction)
        to_lanes = list(range(-1, -(to_endpoint.right_lane_count + 1), -1))
    else:
        # Road ends at junction, use left lanes (they're driving toward junction)
        to_lanes = list(range(1, to_endpoint.left_lane_count + 1))

    # Match lanes
    if turn_type == "straight":
        # 1-to-1 mapping from rightmost to rightmost
        num_lanes = min(len(from_lanes), len(to_lanes))
        for i in range(num_lanes):
            lane_links.append((from_lanes[i], to_lanes[i]))

    elif turn_type in ["right", "left"]:
        # For turns, also do 1-to-1 from rightmost
        num_lanes = min(len(from_lanes), len(to_lanes))
        for i in range(num_lanes):
            lane_links.append((from_lanes[i], to_lanes[i]))

    elif turn_type == "uturn":
        # U-turns typically single lane
        if from_lanes and to_lanes:
            lane_links.append((from_lanes[0], to_lanes[0]))

    return lane_links


def create_connecting_roads_from_patterns(
    junction: Junction,
    patterns: List[ConnectionPattern],
    endpoint_lookup: Dict[str, 'RoadEndpointInfo'],
    transformer: Optional['CoordinateTransformer'] = None,
    project: Optional[Project] = None
) -> None:
    """Create connecting roads and lane connections from pre-detected patterns."""
    if not patterns:
        return

    # Step 4: Identify straight-through pairs (A->B and B->A both straight)
    straight_pairs = {}
    for pattern in patterns:
        if pattern.turn_type == "straight":
            key = tuple(sorted([pattern.from_road_id, pattern.to_road_id]))
            if key not in straight_pairs:
                straight_pairs[key] = []
            straight_pairs[key].append(pattern)

    # Step 5: Create bidirectional CRs for straight-through pairs
    handled_patterns = set()
    for pair_patterns in straight_pairs.values():
        if len(pair_patterns) == 2:
            handled = _create_bidirectional_cr(
                junction, pair_patterns, endpoint_lookup, transformer, project
            )
            handled_patterns.update(handled)

    # Step 6: Handle remaining patterns (turns and unpaired straights)
    for pattern in patterns:
        if id(pattern) in handled_patterns:
            continue
        _create_unidirectional_cr(
            junction, pattern, endpoint_lookup, transformer, project
        )


def _generate_connection_path(from_pos, from_heading, to_pos, to_heading,
                              transformer, from_pos_geo=None, to_pos_geo=None,
                              from_direction_geo=None, to_direction_geo=None,
                              is_uturn=False):
    """Generate a connection path with geo-first or pixel-first strategy.

    Returns (path, geo_path, coeffs) or (None, None, None) on failure.
    """
    geo_path = None
    if transformer and from_pos_geo and to_pos_geo:
        geo_path, coeffs = generate_connection_path_geo(
            from_pos_geo=from_pos_geo, from_heading=from_heading,
            to_pos_geo=to_pos_geo, to_heading=to_heading,
            transformer=transformer, tangent_scale=1.0, is_uturn=is_uturn,
            from_direction_geo=from_direction_geo,
            to_direction_geo=to_direction_geo
        )
        if geo_path:
            path = [transformer.geo_to_pixel(lon, lat) for lon, lat in geo_path]
            if path:
                path[0] = from_pos
                path[-1] = to_pos
        else:
            path = None
    else:
        path, coeffs = generate_simple_connection_path(
            from_pos=from_pos, from_heading=from_heading,
            to_pos=to_pos, to_heading=to_heading,
            tangent_scale=1.0, is_uturn=is_uturn
        )
    if not path:
        return None, None, None
    return path, geo_path, coeffs


def _add_cr_to_project_and_junction(connecting_road, junction, project):
    """Add a connecting road to the project and junction."""
    if project:
        project.add_road(connecting_road)
    junction.add_connecting_road(connecting_road.id)


def _add_lane_connections(junction, connecting_road_id, from_endpoint, to_endpoint,
                          pattern):
    """Generate lane links and add LaneConnection objects to junction."""
    lane_links = generate_lane_links_for_connection(
        from_endpoint, to_endpoint, pattern.turn_type
    )
    for from_lane_id, to_lane_id in lane_links:
        lane_connection = LaneConnection(
            from_road_id=pattern.from_road_id,
            from_lane_id=from_lane_id,
            to_road_id=pattern.to_road_id,
            to_lane_id=to_lane_id,
            connecting_road_id=connecting_road_id,
            turn_type=pattern.turn_type,
            priority=pattern.priority
        )
        junction.add_lane_connection(lane_connection)


def _create_bidirectional_cr(junction, pair_patterns, endpoint_lookup,
                             transformer, project):
    """Create a single bidirectional CR for a straight-through pair. Returns handled pattern ids."""
    # Pick pattern where from_endpoint is at "end" (standard direction)
    pattern = pair_patterns[0]
    from_endpoint = endpoint_lookup.get(pattern.from_road_id)
    to_endpoint = endpoint_lookup.get(pattern.to_road_id)

    if not from_endpoint or not to_endpoint:
        return set()

    if from_endpoint.at_junction != "end":
        pattern = pair_patterns[1]
        from_endpoint = endpoint_lookup.get(pattern.from_road_id)
        to_endpoint = endpoint_lookup.get(pattern.to_road_id)
        if not from_endpoint or not to_endpoint:
            return set()

    lane_width_start = from_endpoint.lane_width
    lane_width_end = to_endpoint.lane_width
    avg_lane_width = (lane_width_start + lane_width_end) / 2

    path, geo_path, coeffs = _generate_connection_path(
        from_endpoint.position, from_endpoint.heading,
        to_endpoint.position, to_endpoint.heading,
        transformer,
        from_endpoint.position_geo, to_endpoint.position_geo,
        from_endpoint.direction_geo, to_endpoint.direction_geo
    )
    if not path:
        return set()

    aU, bU, cU, dU, aV, bV, cV, dV = coeffs
    conn_left = max(1, min(from_endpoint.left_lane_count, to_endpoint.left_lane_count))
    conn_right = max(1, min(from_endpoint.right_lane_count, to_endpoint.right_lane_count))

    connecting_road = Road(
        name=f"CR {junction.id}",
        junction_id=junction.id,
        inline_path=path, inline_geo_path=geo_path,
        cr_lane_count_left=conn_left, cr_lane_count_right=conn_right,
        lane_info=LaneInfo(left_count=conn_left, right_count=conn_right, lane_width=avg_lane_width),
        lane_width_start=lane_width_start, lane_width_end=lane_width_end,
        predecessor_id=pattern.from_road_id, successor_id=pattern.to_road_id,
        predecessor_contact=from_endpoint.at_junction, successor_contact=to_endpoint.at_junction,
        geometry_type="parampoly3",
        aU=aU, bU=bU, cU=cU, dU=dU, aV=aV, bV=bV, cV=cV, dV=dV,
        p_range=1.0, p_range_normalized=True, tangent_scale=1.0,
        stored_start_heading=from_endpoint.heading, stored_end_heading=to_endpoint.heading
    )
    _add_cr_to_project_and_junction(connecting_road, junction, project)

    # Create lane connections for BOTH directions using the same connecting road
    handled = set()
    for p in pair_patterns:
        p_from = endpoint_lookup.get(p.from_road_id)
        p_to = endpoint_lookup.get(p.to_road_id)
        if p_from and p_to:
            _add_lane_connections(junction, connecting_road.id, p_from, p_to, p)
        handled.add(id(p))
    return handled


def _create_unidirectional_cr(junction, pattern, endpoint_lookup,
                              transformer, project):
    """Create a unidirectional CR for a turn or unpaired straight."""
    from_endpoint = endpoint_lookup.get(pattern.from_road_id)
    to_endpoint = endpoint_lookup.get(pattern.to_road_id)
    if not from_endpoint or not to_endpoint:
        return

    width_from = from_endpoint.lane_width
    width_to = to_endpoint.lane_width
    avg_lane_width = (width_from + width_to) / 2

    # Determine lane direction and count
    use_left_lanes = from_endpoint.at_junction != "end"
    if use_left_lanes:
        from_lane_count = from_endpoint.left_lane_count
    else:
        from_lane_count = from_endpoint.right_lane_count
    to_lane_count = (to_endpoint.right_lane_count if to_endpoint.at_junction == "start"
                     else to_endpoint.left_lane_count)
    conn_lane_count = max(1, min(from_lane_count, to_lane_count))

    if use_left_lanes:
        conn_left, conn_right = conn_lane_count, 0
    else:
        conn_left, conn_right = 0, conn_lane_count

    is_uturn = pattern.turn_type == "uturn"

    # Resolve path direction — swap for left-lane traffic
    if use_left_lanes:
        from_pos, to_pos = to_endpoint.position, from_endpoint.position
        from_pos_geo, to_pos_geo = to_endpoint.position_geo, from_endpoint.position_geo
        from_heading, to_heading = to_endpoint.heading, from_endpoint.heading
        from_dir_geo, to_dir_geo = to_endpoint.direction_geo, from_endpoint.direction_geo
        pred_id, succ_id = pattern.to_road_id, pattern.from_road_id
        contact_start, contact_end = to_endpoint.at_junction, from_endpoint.at_junction
        lane_width_start, lane_width_end = width_to, width_from
    else:
        from_pos, to_pos = from_endpoint.position, to_endpoint.position
        from_pos_geo, to_pos_geo = from_endpoint.position_geo, to_endpoint.position_geo
        from_heading, to_heading = from_endpoint.heading, to_endpoint.heading
        from_dir_geo, to_dir_geo = from_endpoint.direction_geo, to_endpoint.direction_geo
        pred_id, succ_id = pattern.from_road_id, pattern.to_road_id
        contact_start, contact_end = from_endpoint.at_junction, to_endpoint.at_junction
        lane_width_start, lane_width_end = width_from, width_to

    path, geo_path, coeffs = _generate_connection_path(
        from_pos, from_heading, to_pos, to_heading,
        transformer, from_pos_geo, to_pos_geo,
        from_dir_geo, to_dir_geo, is_uturn
    )
    if not path:
        return

    aU, bU, cU, dU, aV, bV, cV, dV = coeffs

    # Derive stored headings from actual generated path
    path_start_heading = math.atan2(path[1][1] - path[0][1], path[1][0] - path[0][0])
    path_end_heading = math.atan2(path[-1][1] - path[-2][1], path[-1][0] - path[-2][0])

    connecting_road = Road(
        name=f"CR {junction.id}",
        junction_id=junction.id,
        inline_path=path, inline_geo_path=geo_path,
        cr_lane_count_left=conn_left, cr_lane_count_right=conn_right,
        lane_info=LaneInfo(left_count=conn_left, right_count=conn_right, lane_width=avg_lane_width),
        lane_width_start=lane_width_start, lane_width_end=lane_width_end,
        predecessor_id=pred_id, successor_id=succ_id,
        predecessor_contact=contact_start, successor_contact=contact_end,
        geometry_type="parampoly3",
        aU=aU, bU=bU, cU=cU, dU=dU, aV=aV, bV=bV, cV=cV, dV=dV,
        p_range=1.0, p_range_normalized=True, tangent_scale=1.0,
        stored_start_heading=path_start_heading, stored_end_heading=path_end_heading
    )
    _add_cr_to_project_and_junction(connecting_road, junction, project)
    _add_lane_connections(junction, connecting_road.id, from_endpoint, to_endpoint, pattern)


def _compute_max_curvature(points: List[Tuple[float, float]]) -> float:
    """Compute maximum discrete curvature across a polyline."""
    max_k = 0.0
    for i in range(1, len(points) - 1):
        x0, y0 = points[i - 1]
        x1, y1 = points[i]
        x2, y2 = points[i + 1]
        # Vectors
        dx1, dy1 = x1 - x0, y1 - y0
        dx2, dy2 = x2 - x1, y2 - y1
        cross = abs(dx1 * dy2 - dy1 * dx2)
        seg_len = math.sqrt(dx1 * dx1 + dy1 * dy1)
        if seg_len < 1e-9:
            continue
        k = cross / (seg_len ** 3)
        if k > max_k:
            max_k = k
    return max_k


def evaluate_and_fix_connecting_roads(
    junction: Junction,
    project: Project,
    transformer: Optional['CoordinateTransformer'] = None,
    min_radius_meters: float = 3.0,
) -> int:
    """Evaluate CR curvature and re-generate with adjusted tangent_scale if too sharp.

    Returns the number of CRs that were improved.
    """
    if not transformer:
        return 0

    scale_x, scale_y = transformer.get_scale_factor()
    avg_scale = (scale_x + scale_y) / 2.0
    # Max curvature threshold in pixels (1/radius_pixels)
    max_k_threshold = 1.0 / (min_radius_meters / avg_scale)

    roads_dict = {road.id: road for road in project.roads}
    fixed_count = 0
    tangent_scales_to_try = [0.6, 0.8, 1.2, 1.5]

    for cr_id in list(junction.connecting_road_ids):
        cr = roads_dict.get(cr_id)
        if not cr or not cr.inline_path or len(cr.inline_path) < 3:
            continue

        current_max_k = _compute_max_curvature(cr.inline_path)
        if current_max_k <= max_k_threshold:
            continue  # Already smooth enough

        # Try alternative tangent scales
        best_k = current_max_k
        best_path = None
        best_geo_path = None
        best_coeffs = None
        best_scale = cr.tangent_scale or 1.0

        from_heading = cr.stored_start_heading
        to_heading = cr.stored_end_heading
        if from_heading is None or to_heading is None:
            continue

        is_uturn = False  # CRs from import are not U-turns

        for ts in tangent_scales_to_try:
            # Try geo-first if available
            if cr.inline_geo_path and len(cr.inline_geo_path) >= 2:
                from_geo = cr.inline_geo_path[0]
                to_geo = cr.inline_geo_path[-1]
                try:
                    geo_path, coeffs = generate_connection_path_geo(
                        from_pos_geo=from_geo,
                        from_heading=from_heading,
                        to_pos_geo=to_geo,
                        to_heading=to_heading,
                        transformer=transformer,
                        tangent_scale=ts,
                        is_uturn=is_uturn,
                    )
                except Exception:
                    continue
                if not geo_path:
                    continue
                path = [transformer.geo_to_pixel(lon, lat) for lon, lat in geo_path]
                if path:
                    path[0] = cr.inline_path[0]
                    path[-1] = cr.inline_path[-1]
            else:
                from_pos = cr.inline_path[0]
                to_pos = cr.inline_path[-1]
                try:
                    path, coeffs = generate_simple_connection_path(
                        from_pos=from_pos,
                        from_heading=from_heading,
                        to_pos=to_pos,
                        to_heading=to_heading,
                        tangent_scale=ts,
                        is_uturn=is_uturn,
                    )
                except Exception:
                    continue
                geo_path = None

            if not path or len(path) < 3:
                continue

            k = _compute_max_curvature(path)
            if k < best_k:
                best_k = k
                best_path = path
                best_geo_path = geo_path
                best_coeffs = coeffs
                best_scale = ts

        if best_path and best_k < current_max_k:
            cr.inline_path = best_path
            cr.inline_geo_path = best_geo_path
            cr.tangent_scale = best_scale
            aU, bU, cU, dU, aV, bV, cV, dV = best_coeffs
            cr.aU, cr.bU, cr.cU, cr.dU = aU, bU, cU, dU
            cr.aV, cr.bV, cr.cV, cr.dV = aV, bV, cV, dV
            fixed_count += 1

            radius_m = (1.0 / best_k * avg_scale) if best_k > 0 else float('inf')
            logger.debug("Improved CR '%s' curvature: tangent_scale=%.1f, min_radius=%.1fm",
                          cr.id, best_scale, radius_m)

    return fixed_count


def clear_cross_junction_links(junction: Junction, roads_dict: Dict[str, Road]) -> None:
    """
    Clear predecessor/successor links between roads that connect through this junction.

    In OpenDRIVE, roads connecting through a junction should NOT have direct
    predecessor/successor links to each other. Instead, the connection is:
    Road -> Junction -> ConnectingRoad -> Road

    This function clears any stale road-to-road links that exist between roads
    in the same junction.

    Args:
        junction: Junction object whose roads should have cross-links cleared
        roads_dict: Dictionary of road_id -> Road object
    """
    connected_ids = set(junction.connected_road_ids)

    for road_id in connected_ids:
        road = roads_dict.get(road_id)
        if not road:
            continue

        # If predecessor is another road in this junction, clear it
        if road.predecessor_id and road.predecessor_id in connected_ids:
            road.predecessor_id = None

        # If successor is another road in this junction, clear it
        if road.successor_id and road.successor_id in connected_ids:
            road.successor_id = None


def generate_junction_connections(junction: Junction,
                                 roads_dict: Dict[str, Road],
                                 polylines_dict: Dict[str, Polyline],
                                 scale: float = 1.0,
                                 transformer: Optional['CoordinateTransformer'] = None,
                                 project: Optional[Project] = None) -> None:
    """
    Generate connecting roads and lane connections for a junction.

    Creates Road objects (with junction_id set) and adds them to project.roads.
    Stores connecting road IDs in junction.connecting_road_ids.

    For straight-through connections between bidirectional roads, creates a single
    bidirectional connecting road with both left and right lanes. For turns,
    creates separate unidirectional connecting roads.

    Virtual junctions (path crossings) are skipped - they represent visual crossings
    where roads don't actually connect (e.g., pedestrian path crossing over a road).

    When a transformer is provided and road endpoints have geo coordinates,
    paths are generated in geographic space first (geo-first), then pixel
    coordinates are derived.

    Args:
        junction: Junction object to populate with connections
        roads_dict: Dictionary of road_id -> Road object
        polylines_dict: Dictionary of polyline_id -> Polyline object
        scale: Meters per pixel scale factor (used for lane offset calculations)
        transformer: Optional CoordinateTransformer for geo-first path generation
        project: Project to add connecting Road objects to
    """
    # Skip virtual junctions - these are path crossings, not real connections
    if junction.junction_type == "virtual":
        return

    # Step 1: Analyze junction geometry
    geometry_info = analyze_junction_geometry(junction, roads_dict, polylines_dict)

    # Step 2: Detect connection patterns
    patterns = detect_connection_patterns(geometry_info)

    # Step 3: Filter unlikely connections
    patterns = filter_unlikely_connections(patterns, roads_dict)

    if not patterns:
        # No connections found - junction might be too simple or malformed
        return

    # Build endpoint lookup from geometry_info
    endpoint_lookup = {ep.road_id: ep for ep in geometry_info['endpoints']}

    # Steps 4-6: Create connecting roads using the shared function
    create_connecting_roads_from_patterns(junction, patterns, endpoint_lookup, transformer, project)

    # Step 7: Clear any stale road-to-road predecessor/successor links
    # In OpenDRIVE, roads connecting through a junction should link to the junction,
    # not directly to roads on the other side
    clear_cross_junction_links(junction, roads_dict)

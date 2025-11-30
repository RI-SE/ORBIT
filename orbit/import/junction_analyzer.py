"""
Junction geometry analyzer for OSM import.

Analyzes junction geometry to automatically generate connecting roads and lane links.
"""

import math
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass

from orbit.models import Junction, Road, Polyline, ConnectingRoad, LaneConnection
from orbit.utils.geometry import generate_simple_connection_path


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
        else:
            at_junction = "end"
            junction_point = centerline.points[-1]
            heading = get_road_endpoint_heading(road, centerline, "end")
            closest_dist = end_dist

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
            left_count = len([l for l in section.lanes if l.id > 0])
            right_count = len([l for l in section.lanes if l.id < 0])
            # Get lane width from first driving lane
            lane_width = next((l.width for l in section.lanes if l.id != 0), 3.5)
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
            lane_width=lane_width
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

            # Calculate turn angle
            # Outgoing heading should be roughly opposite of incoming heading for straight-through
            # We need to consider the direction change

            # Incoming road heading points INTO junction
            incoming_heading = from_endpoint.heading

            # Outgoing road heading points OUT OF junction
            # For connection, we want the heading that enters the outgoing road
            # which is opposite to the road's heading away from junction
            outgoing_heading = to_endpoint.heading + math.pi

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
    Filter out geometrically unlikely connections.

    Args:
        patterns: List of all possible connection patterns
        roads_dict: Dictionary of road_id -> Road object

    Returns:
        Filtered list of likely connections
    """
    filtered = []

    for pattern in patterns:
        # Note: We do NOT filter by successor/predecessor relationships here.
        # When roads are split at a junction, they get linked via successor/predecessor,
        # but they still need connecting roads within the junction for each direction.
        # The junction is where vehicles physically transition between road segments.
        filtered.append(pattern)

    return filtered


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


def generate_junction_connections(junction: Junction,
                                 roads_dict: Dict[str, Road],
                                 polylines_dict: Dict[str, Polyline],
                                 scale: float = 1.0) -> None:
    """
    Generate connecting roads and lane connections for a junction.

    Modifies the junction object in place by adding connecting_roads and lane_connections.

    Args:
        junction: Junction object to populate with connections
        roads_dict: Dictionary of road_id -> Road object
        polylines_dict: Dictionary of polyline_id -> Polyline object
        scale: Meters per pixel scale factor (used for lane offset calculations)
    """
    # Step 1: Analyze junction geometry
    geometry_info = analyze_junction_geometry(junction, roads_dict, polylines_dict)

    # Step 2: Detect connection patterns
    patterns = detect_connection_patterns(geometry_info)

    # Step 3: Filter unlikely connections
    patterns = filter_unlikely_connections(patterns, roads_dict)

    if not patterns:
        # No connections found - junction might be too simple or malformed
        return

    # Step 4: Generate connecting roads and lane connections
    for pattern in patterns:
        # Generate path for this connection
        from_endpoint = pattern.from_endpoint
        to_endpoint = pattern.to_endpoint

        # Calculate average lane width for connecting road
        avg_lane_width = (from_endpoint.lane_width + to_endpoint.lane_width) / 2

        # Determine lane count for connecting road (use minimum of from/to)
        # For now, connecting roads are typically single lane per direction
        conn_lane_count_right = min(
            from_endpoint.right_lane_count if from_endpoint.at_junction == "end" else from_endpoint.left_lane_count,
            to_endpoint.right_lane_count if to_endpoint.at_junction == "start" else to_endpoint.left_lane_count
        )
        conn_lane_count_left = 0  # Right-hand traffic: only right lanes in connecting roads

        # Check if this is a U-turn connection
        is_uturn = pattern.turn_type == "uturn"

        # For straight connections, use lane-offset positions and simple line geometry
        if pattern.turn_type == "straight":
            # For straight-through, calculate lane offset based on connection direction
            # The connection direction is from FROM endpoint toward TO endpoint
            conn_dx = to_endpoint.position[0] - from_endpoint.position[0]
            conn_dy = to_endpoint.position[1] - from_endpoint.position[1]
            conn_heading = math.atan2(conn_dy, conn_dx)

            # Calculate lane offset perpendicular to connection direction (right side)
            lane_width_px = from_endpoint.lane_width / scale if scale > 0 else from_endpoint.lane_width
            right_perp = conn_heading - math.pi / 2

            # Offset both positions to the right of the connection direction
            offset_x = (from_endpoint.right_lane_count / 2.0) * lane_width_px * math.cos(right_perp)
            offset_y = (from_endpoint.right_lane_count / 2.0) * lane_width_px * math.sin(right_perp)

            from_pos = (from_endpoint.position[0] + offset_x, from_endpoint.position[1] + offset_y)
            to_pos = (to_endpoint.position[0] + offset_x, to_endpoint.position[1] + offset_y)

            # For straight connections, just create a simple line path (no curves)
            path = [from_pos, to_pos]
            # Coefficients for a simple line in local frame: u(p) = p * length, v(p) = 0
            dx = to_pos[0] - from_pos[0]
            dy = to_pos[1] - from_pos[1]
            length = math.sqrt(dx * dx + dy * dy)
            coeffs = (0.0, length, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)  # aU, bU, cU, dU, aV, bV, cV, dV
        else:
            # For turns, use centerline positions (the curve geometry handles lane offset)
            from_pos = from_endpoint.position
            to_pos = to_endpoint.position
            from_heading = from_endpoint.heading
            to_heading = to_endpoint.heading

            # Generate geometric path using ParamPoly3D
            path, coeffs = generate_simple_connection_path(
                from_pos=from_pos,
                from_heading=from_heading,
                to_pos=to_pos,
                to_heading=to_heading,
                num_points=20,
                tangent_scale=1.0,
                is_uturn=is_uturn
            )

        if not path:
            continue

        # Unpack ParamPoly3D coefficients
        aU, bU, cU, dU, aV, bV, cV, dV = coeffs

        # Use simple line geometry for straight connections, Bezier curves for turns
        if pattern.turn_type == "straight":
            geometry_type = "polyline"  # Clean line geometry for straight roads
        else:
            geometry_type = "parampoly3"  # Smooth Bezier curves for turns

        # Create connecting road
        connecting_road = ConnectingRoad(
            path=path,
            lane_count_left=conn_lane_count_left,
            lane_count_right=max(1, conn_lane_count_right),  # At least 1 lane
            lane_width=avg_lane_width,
            predecessor_road_id=pattern.from_road_id,
            successor_road_id=pattern.to_road_id,
            contact_point_start="end",  # Connects to end of incoming road
            contact_point_end="start",   # Connects to start of outgoing road
            geometry_type=geometry_type,
            aU=aU, bU=bU, cU=cU, dU=dU,
            aV=aV, bV=bV, cV=cV, dV=dV,
            p_range=1.0,
            p_range_normalized=True,  # Use OpenDRIVE standard normalized pRange
            tangent_scale=1.0
        )

        # Add to junction
        junction.add_connecting_road(connecting_road)

        # Generate lane links
        lane_links = generate_lane_links_for_connection(
            from_endpoint,
            to_endpoint,
            pattern.turn_type
        )

        # Create lane connection objects
        for from_lane_id, to_lane_id in lane_links:
            lane_connection = LaneConnection(
                from_road_id=pattern.from_road_id,
                from_lane_id=from_lane_id,
                to_road_id=pattern.to_road_id,
                to_lane_id=to_lane_id,
                connecting_road_id=connecting_road.id,
                turn_type=pattern.turn_type,
                priority=pattern.priority
            )

            junction.add_lane_connection(lane_connection)

"""
Geometry utilities for ORBIT.

Provides functions for geometric calculations like offset polylines,
perpendicular vectors, polygon construction, and junction path generation.
"""

import math
from typing import List, Tuple, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from orbit.utils.coordinate_transform import CoordinateTransformer


def calculate_perpendicular(p1: Tuple[float, float], p2: Tuple[float, float]) -> Tuple[float, float]:
    """
    Calculate normalized perpendicular vector for a line segment.

    The perpendicular is rotated 90° counterclockwise from the segment direction
    in mathematical coordinates. In screen coordinates (Y-down), this means:
    - For a segment going right (positive X), perpendicular points down (positive Y)
    - Positive offset along this perpendicular = right side of direction of travel

    Args:
        p1: First point (x, y)
        p2: Second point (x, y)

    Returns:
        Normalized perpendicular vector (perp_x, perp_y)
    """
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]

    length = math.sqrt(dx * dx + dy * dy)
    if length == 0:
        return (0, 0)

    # Rotate 90° counterclockwise: (dx, dy) -> (-dy, dx)
    perp_x = -dy / length
    perp_y = dx / length

    return (perp_x, perp_y)


def offset_point(point: Tuple[float, float], perpendicular: Tuple[float, float],
                 offset: float) -> Tuple[float, float]:
    """
    Offset a point along a perpendicular direction.

    Args:
        point: Original point (x, y)
        perpendicular: Unit perpendicular vector (perp_x, perp_y)
        offset: Distance to offset (positive = perpendicular direction, negative = opposite)

    Returns:
        Offset point (x, y)
    """
    return (
        point[0] + perpendicular[0] * offset,
        point[1] + perpendicular[1] * offset
    )


def calculate_offset_polyline(points: List[Tuple[float, float]],
                               offset_distance: float,
                               closed: bool = False) -> List[Tuple[float, float]]:
    """
    Calculate an offset polyline parallel to the input polyline.

    For each segment, the offset is perpendicular to the segment direction.
    At corners, we use simple miter joins (intersection of offset segments).

    Args:
        points: List of (x, y) points defining the polyline
        offset_distance: Distance to offset. In screen coordinates (Y-down):
                        positive = right side of direction of travel,
                        negative = left side of direction of travel
        closed: Whether the polyline is closed (connects last to first)

    Returns:
        List of offset points
    """
    if len(points) < 2:
        return []

    offset_points = []

    for i in range(len(points)):
        if i == 0 and not closed:
            # First point of open polyline: use perpendicular of first segment
            perp = calculate_perpendicular(points[0], points[1])
            offset_points.append(offset_point(points[0], perp, offset_distance))

        elif i == len(points) - 1 and not closed:
            # Last point of open polyline: use perpendicular of last segment
            perp = calculate_perpendicular(points[-2], points[-1])
            offset_points.append(offset_point(points[-1], perp, offset_distance))

        else:
            # Interior point: average perpendiculars of adjacent segments
            # This creates a miter join at the corner

            if closed:
                prev_idx = (i - 1) % len(points)
                next_idx = (i + 1) % len(points)
            else:
                prev_idx = i - 1
                next_idx = i + 1

            # Perpendicular from previous segment
            perp1 = calculate_perpendicular(points[prev_idx], points[i])

            # Perpendicular from next segment
            perp2 = calculate_perpendicular(points[i], points[next_idx])

            # Average perpendicular (creates miter join)
            avg_perp_x = (perp1[0] + perp2[0]) / 2
            avg_perp_y = (perp1[1] + perp2[1]) / 2

            # Normalize
            length = math.sqrt(avg_perp_x * avg_perp_x + avg_perp_y * avg_perp_y)
            if length > 0:
                avg_perp = (avg_perp_x / length, avg_perp_y / length)
            else:
                avg_perp = perp1

            # Calculate scale factor to maintain offset distance at miter
            # The miter needs to be scaled by 1/cos(angle/2) where angle is the turn angle
            cos_half_angle = perp1[0] * avg_perp[0] + perp1[1] * avg_perp[1]
            if cos_half_angle > 0.1:  # Avoid extreme miters at sharp corners
                scale = 1.0 / cos_half_angle
                # Limit scale to prevent excessive miter lengths
                scale = min(scale, 3.0)
            else:
                scale = 1.0

            offset_points.append(offset_point(points[i], avg_perp, offset_distance * scale))

    return offset_points


def create_lane_polygon(centerline_points: List[Tuple[float, float]],
                        inner_offset: float,
                        outer_offset: float,
                        closed: bool = False) -> List[Tuple[float, float]]:
    """
    Create a polygon representing a lane between two offset distances from centerline.

    The polygon is constructed by:
    1. Creating inner boundary at inner_offset
    2. Creating outer boundary at outer_offset
    3. Connecting them into a closed polygon

    Args:
        centerline_points: Points defining the road centerline
        inner_offset: Distance to inner edge (closer to centerline, in pixels)
        outer_offset: Distance to outer edge (farther from centerline, in pixels)
        closed: Whether centerline is closed

    Returns:
        List of points forming a closed polygon (inner + reversed outer + closure)
    """
    if len(centerline_points) < 2:
        return []

    # Calculate both offset polylines
    inner_boundary = calculate_offset_polyline(centerline_points, inner_offset, closed)
    outer_boundary = calculate_offset_polyline(centerline_points, outer_offset, closed)

    if not inner_boundary or not outer_boundary:
        return []

    # Build polygon: inner boundary + reversed outer boundary
    if closed:
        # For closed polylines, connect inner to outer
        polygon = inner_boundary + list(reversed(outer_boundary))
    else:
        # For open polylines, connect end points
        polygon = inner_boundary + list(reversed(outer_boundary))

    return polygon


def create_variable_width_lane_polygon(
    centerline_points: List[Tuple[float, float]],
    inner_offset_start: float,
    outer_offset_start: float,
    inner_offset_end: float,
    outer_offset_end: float
) -> List[Tuple[float, float]]:
    """
    Create a polygon representing a lane with variable width (tapering).

    The polygon is constructed by interpolating offsets along the centerline,
    creating inner and outer boundaries that vary linearly from start to end.

    Args:
        centerline_points: Points defining the road centerline
        inner_offset_start: Distance to inner edge at start (pixels)
        outer_offset_start: Distance to outer edge at start (pixels)
        inner_offset_end: Distance to inner edge at end (pixels)
        outer_offset_end: Distance to outer edge at end (pixels)

    Returns:
        List of points forming a closed polygon
    """
    if len(centerline_points) < 2:
        return []

    n_points = len(centerline_points)
    inner_boundary = []
    outer_boundary = []

    for i, point in enumerate(centerline_points):
        # Calculate interpolation factor (0 at start, 1 at end)
        t = i / (n_points - 1) if n_points > 1 else 0

        # Interpolate offsets
        inner_offset = inner_offset_start + t * (inner_offset_end - inner_offset_start)
        outer_offset = outer_offset_start + t * (outer_offset_end - outer_offset_start)

        # Calculate perpendicular at this point
        if i == 0:
            perp = calculate_perpendicular(centerline_points[0], centerline_points[1])
        elif i == n_points - 1:
            perp = calculate_perpendicular(centerline_points[-2], centerline_points[-1])
        else:
            # Average perpendiculars of adjacent segments for smoother result
            perp1 = calculate_perpendicular(centerline_points[i - 1], centerline_points[i])
            perp2 = calculate_perpendicular(centerline_points[i], centerline_points[i + 1])
            avg_perp_x = (perp1[0] + perp2[0]) / 2
            avg_perp_y = (perp1[1] + perp2[1]) / 2
            # Normalize
            length = math.sqrt(avg_perp_x**2 + avg_perp_y**2)
            if length > 0:
                perp = (avg_perp_x / length, avg_perp_y / length)
            else:
                perp = perp1

        # Create offset points
        inner_point = offset_point(point, perp, inner_offset)
        outer_point = offset_point(point, perp, outer_offset)

        inner_boundary.append(inner_point)
        outer_boundary.append(outer_point)

    # Build polygon: inner boundary + reversed outer boundary
    polygon = inner_boundary + list(reversed(outer_boundary))

    return polygon


def create_polygon_from_boundaries(
    left_boundary: List[Tuple[float, float]],
    right_boundary: List[Tuple[float, float]]
) -> List[Tuple[float, float]]:
    """
    Create a polygon from explicit left and right boundary polylines.

    Args:
        left_boundary: Points defining left edge of lane
        right_boundary: Points defining right edge of lane

    Returns:
        List of points forming a closed polygon
    """
    if len(left_boundary) < 2 or len(right_boundary) < 2:
        return []

    # Polygon: left boundary + reversed right boundary
    return list(left_boundary) + list(reversed(right_boundary))


def create_polynomial_width_lane_polygon(
    centerline_points: List[Tuple[float, float]],
    lane_id: int,
    inner_lanes_width_func,  # Callable[[float], float] - returns cumulative inner offset at s
    lane_width_func,  # Callable[[float], float] - returns this lane's width at s
    s_values: List[float],  # s-coordinate for each centerline point
    is_left_lane: bool
) -> List[Tuple[float, float]]:
    """
    Create a polygon for a lane with polynomial (or arbitrary) width variation.

    This function calculates the offset at each centerline point based on
    the provided width functions, allowing for polynomial or other complex
    width variations along the lane.

    Args:
        centerline_points: Points defining the road centerline
        lane_id: Lane ID (for debugging)
        inner_lanes_width_func: Function(s) -> cumulative width of all inner lanes at s
        lane_width_func: Function(s) -> width of this lane at s
        s_values: S-coordinate for each centerline point (in same units as width functions)
        is_left_lane: True for left lanes (positive IDs), False for right lanes

    Returns:
        List of points forming a closed polygon
    """
    if len(centerline_points) < 2 or len(s_values) != len(centerline_points):
        return []

    n_points = len(centerline_points)
    inner_boundary = []
    outer_boundary = []

    for i, point in enumerate(centerline_points):
        s = s_values[i]

        # Get offsets at this s position
        inner_offset = inner_lanes_width_func(s)
        outer_offset = inner_offset + lane_width_func(s)

        # Apply sign based on lane side
        if is_left_lane:
            inner_offset = -inner_offset
            outer_offset = -outer_offset

        # Calculate perpendicular at this point
        if i == 0:
            perp = calculate_perpendicular(centerline_points[0], centerline_points[1])
        elif i == n_points - 1:
            perp = calculate_perpendicular(centerline_points[-2], centerline_points[-1])
        else:
            # Average perpendiculars of adjacent segments
            perp1 = calculate_perpendicular(centerline_points[i - 1], centerline_points[i])
            perp2 = calculate_perpendicular(centerline_points[i], centerline_points[i + 1])
            avg_perp_x = (perp1[0] + perp2[0]) / 2
            avg_perp_y = (perp1[1] + perp2[1]) / 2
            length = math.sqrt(avg_perp_x**2 + avg_perp_y**2)
            if length > 0:
                perp = (avg_perp_x / length, avg_perp_y / length)
            else:
                perp = perp1

        # Create offset points
        inner_point = offset_point(point, perp, inner_offset)
        outer_point = offset_point(point, perp, outer_offset)

        inner_boundary.append(inner_point)
        outer_boundary.append(outer_point)

    # Build polygon: inner boundary + reversed outer boundary
    return inner_boundary + list(reversed(outer_boundary))


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


def generate_arc_path(from_pos: Tuple[float, float],
                     from_heading: float,
                     to_pos: Tuple[float, float],
                     to_heading: float,
                     num_points: int = 15,
                     min_radius: float = 5.0) -> Optional[List[Tuple[float, float]]]:
    """
    Generate a circular arc path connecting two endpoints with given headings.

    This is a simplified arc generator suitable for junction connections.
    For very sharp turns (radius < min_radius), returns None to indicate
    the connection is not feasible with current junction size.

    Args:
        from_pos: Starting position (x, y) in pixels
        from_heading: Starting heading in radians (0 = east, π/2 = north)
        to_pos: Ending position (x, y) in pixels
        to_heading: Ending heading in radians
        num_points: Number of points to generate along the arc
        min_radius: Minimum acceptable arc radius in pixels

    Returns:
        List of (x, y) points forming the arc, or None if infeasible
    """
    # Calculate turn angle
    angle_diff = normalize_angle(to_heading - from_heading)

    # Check if nearly straight (less than 10 degrees)
    if abs(angle_diff) < math.radians(10):
        # Use straight line
        return [from_pos, to_pos]

    # Calculate distance between endpoints
    dx = to_pos[0] - from_pos[0]
    dy = to_pos[1] - from_pos[1]
    distance = math.sqrt(dx * dx + dy * dy)

    if distance < 0.1:
        # Points too close
        return [from_pos]

    # For a simple arc approximation, we'll create a path that:
    # 1. Starts at from_pos with from_heading
    # 2. Ends at to_pos with to_heading
    # 3. Uses intermediate points that smoothly transition

    # Simple approach: use linear interpolation with heading adjustment
    points = []

    for i in range(num_points):
        t = i / (num_points - 1)  # 0 to 1

        # Linear interpolation of position
        x = from_pos[0] + t * dx
        y = from_pos[1] + t * dy

        # Optionally adjust path to curve
        # For now, simple straight-line approximation
        # TODO: Implement proper arc calculation in future enhancement

        points.append((x, y))

    return points


def generate_simple_connection_path(from_pos: Tuple[float, float],
                                   from_heading: float,
                                   to_pos: Tuple[float, float],
                                   to_heading: float,
                                   num_points: int = 20,
                                   tangent_scale: float = 1.0,
                                   is_uturn: bool = False) -> Tuple[List[Tuple[float, float]], Tuple[float, ...]]:
    """
    Generate a ParamPoly3D connection path between two road endpoints.

    Uses Bezier control point calculation for smooth, tangent-continuous curves.
    Falls back to Hermite interpolation with tangent_scale if Bezier fails
    (e.g., for parallel lanes that don't intersect).

    Args:
        from_pos: Starting position (x, y)
        from_heading: Starting heading in radians (0 = east, π/2 = north)
        to_pos: Ending position (x, y)
        to_heading: Ending heading in radians
        num_points: Number of points to sample for visualization
        tangent_scale: Scale factor for tangent lengths (used as fallback)
        is_uturn: Whether this is a U-turn connection

    Returns:
        Tuple of (sampled_points, parampoly3_coefficients) where:
        - sampled_points: List of (x, y) points sampled from the curve
        - parampoly3_coefficients: Tuple of (aU, bU, cU, dU, aV, bV, cV, dV)
    """
    # Calculate tangent vectors from headings
    start_tangent = (math.cos(from_heading), math.sin(from_heading))
    end_tangent = (math.cos(to_heading), math.sin(to_heading))

    # Try Bezier control point calculation first
    control_points = calculate_bezier_control_points(
        from_pos,
        start_tangent,
        to_pos,
        end_tangent,
        is_uturn
    )

    if control_points is not None:
        # Success: use Bezier curve
        coeffs = bezier_to_parampoly3(control_points, from_heading)
        sampled_points = sample_bezier(control_points, num_points)
    else:
        # Fallback: use existing Hermite interpolation with tangent_scale
        coeffs = calculate_hermite_parampoly3(
            from_pos,
            start_tangent,
            to_pos,
            end_tangent,
            tangent_scale
        )

        # Sample the curve for visualization using global transformation
        # (Hermite coefficients are now in local u/v coordinates)
        aU, bU, cU, dU, aV, bV, cV, dV = coeffs
        sampled_points = evaluate_parampoly3_global(
            aU, bU, cU, dU,
            aV, bV, cV, dV,
            from_pos,
            from_heading,
            num_points=num_points
        )

    return (sampled_points, coeffs)


def compute_heading_in_metric_space(
    pos_geo: Tuple[float, float],
    direction_geo: Tuple[float, float],
    transformer: 'CoordinateTransformer'
) -> float:
    """
    Compute heading in metric space from two geo points.

    Args:
        pos_geo: Position (lon, lat)
        direction_geo: A point in the direction of travel (lon, lat)
        transformer: CoordinateTransformer for geo<->meters conversion

    Returns:
        Heading in radians in metric space (0 = east, π/2 = north)
    """
    # Convert both points to metric
    pos_m = transformer.latlon_to_meters(pos_geo[1], pos_geo[0])
    dir_m = transformer.latlon_to_meters(direction_geo[1], direction_geo[0])

    # Calculate heading
    dx = dir_m[0] - pos_m[0]
    dy = dir_m[1] - pos_m[1]
    return math.atan2(dy, dx)


def generate_connection_path_geo(
    from_pos_geo: Tuple[float, float],
    from_heading: float,
    to_pos_geo: Tuple[float, float],
    to_heading: float,
    transformer: 'CoordinateTransformer',
    num_points: int = 20,
    tangent_scale: float = 1.0,
    is_uturn: bool = False,
    from_direction_geo: Optional[Tuple[float, float]] = None,
    to_direction_geo: Optional[Tuple[float, float]] = None
) -> Tuple[List[Tuple[float, float]], Tuple[float, ...]]:
    """
    Generate a ParamPoly3D connection path in geographic coordinates.

    Converts geo coords to local metric space, generates the path using
    existing Hermite/Bezier logic, then converts back to geo.

    Args:
        from_pos_geo: Starting position (lon, lat)
        from_heading: Starting heading in radians (pixel space) - used as fallback
        to_pos_geo: Ending position (lon, lat)
        to_heading: Ending heading in radians (pixel space) - used as fallback
        transformer: CoordinateTransformer for geo<->meters conversion
        num_points: Number of points to sample
        tangent_scale: Scale factor for tangent lengths
        is_uturn: Whether this is a U-turn connection
        from_direction_geo: Optional geo point in direction of travel at start (lon, lat)
        to_direction_geo: Optional geo point in direction of travel at end (lon, lat)

    Returns:
        Tuple of (geo_path, parampoly3_coefficients) where:
        - geo_path: List of (lon, lat) points sampled from the curve
        - parampoly3_coefficients: Tuple of (aU, bU, cU, dU, aV, bV, cV, dV)
    """
    # Convert geo positions to local metric coordinates
    from_lon, from_lat = from_pos_geo
    to_lon, to_lat = to_pos_geo

    from_mx, from_my = transformer.latlon_to_meters(from_lat, from_lon)
    to_mx, to_my = transformer.latlon_to_meters(to_lat, to_lon)

    # Compute headings in metric space
    # from_heading: Direction CR leaves the start point (into junction from source road)
    #   Compute from direction_geo TO from_pos_geo = direction toward junction
    # to_heading: Direction CR arrives at end point (onto destination road)
    #   Compute from to_pos_geo TO to_direction_geo = direction along destination road
    if from_direction_geo:
        from_heading_metric = compute_heading_in_metric_space(
            from_direction_geo, from_pos_geo, transformer
        )
    else:
        # Fallback: create a direction point from pixel heading
        # This is approximate and may not work well with skewed transformations
        offset = 0.0001  # Small offset in degrees
        dir_lon = from_lon + offset * math.cos(from_heading)
        dir_lat = from_lat - offset * math.sin(from_heading)  # Negative because pixel Y is down
        from_heading_metric = compute_heading_in_metric_space(
            from_pos_geo, (dir_lon, dir_lat), transformer
        )

    if to_direction_geo:
        # For to_heading, we want direction AWAY from junction along destination road
        # direction_geo is on the road, so compute from pos_geo TO direction_geo
        to_heading_metric = compute_heading_in_metric_space(
            to_pos_geo, to_direction_geo, transformer
        )
    else:
        # Fallback: create a direction point from pixel heading
        offset = 0.0001
        dir_lon = to_lon + offset * math.cos(to_heading)
        dir_lat = to_lat - offset * math.sin(to_heading)
        to_heading_metric = compute_heading_in_metric_space(
            to_pos_geo, (dir_lon, dir_lat), transformer
        )

    # Generate path in metric space
    from_pos_m = (from_mx, from_my)
    to_pos_m = (to_mx, to_my)

    metric_points, coeffs = generate_simple_connection_path(
        from_pos_m,
        from_heading_metric,
        to_pos_m,
        to_heading_metric,
        num_points,
        tangent_scale,
        is_uturn
    )

    # Convert sampled points back to geo coordinates
    geo_path = []
    for mx, my in metric_points:
        lat, lon = transformer.meters_to_latlon(mx, my)
        geo_path.append((lon, lat))

    return (geo_path, coeffs)


def calculate_path_length(points: List[Tuple[float, float]]) -> float:
    """
    Calculate the total length of a polyline path.

    Args:
        points: List of (x, y) points

    Returns:
        Total path length
    """
    if len(points) < 2:
        return 0.0

    total_length = 0.0
    for i in range(len(points) - 1):
        dx = points[i+1][0] - points[i][0]
        dy = points[i+1][1] - points[i][1]
        total_length += math.sqrt(dx * dx + dy * dy)

    return total_length


def distance_between_points(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """
    Calculate Euclidean distance between two points.

    Args:
        p1: First point (x, y)
        p2: Second point (x, y)

    Returns:
        Distance
    """
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    return math.sqrt(dx * dx + dy * dy)


def find_point_at_distance_along_path(
    points: List[Tuple[float, float]],
    distance: float,
    from_start: bool = True
) -> Optional[Tuple[Tuple[float, float], Tuple[float, float], int]]:
    """
    Find point at specified distance along a polyline path.

    Walks along the polyline segments accumulating distance. When the target
    distance is reached, interpolates within that segment to find the exact point.
    Returns the point coordinates, direction vector at that point, and the segment
    index (useful for removing points that were passed).

    Args:
        points: List of (x, y) points defining the polyline
        distance: Distance to travel along the path (in same units as points)
        from_start: If True, measure from start; if False, measure from end

    Returns:
        Tuple of (point, direction_vector, segment_index) or None if:
        - point: (x, y) coordinates at the target distance
        - direction_vector: Normalized (dx, dy) tangent vector at that point
        - segment_index: Index of the segment where point was found
          (for from_start=True: segment between points[i] and points[i+1])
          (for from_start=False: counted from end, same meaning)

        Returns None if distance exceeds path length or points list is invalid.

    Notes:
        - If distance lands exactly on an existing point, that point is returned
        - segment_index tells which intermediate points were "passed" and can be removed
        - For from_start=True with result (p, dir, 2): points[0], points[1], points[2] were passed
        - For from_start=False with result (p, dir, 2): points[-1], points[-2], points[-3] were passed
    """
    if len(points) < 2:
        return None

    # If measuring from end, reverse the point list
    if not from_start:
        points = list(reversed(points))

    accumulated_distance = 0.0
    target_distance = abs(distance)  # Ensure positive

    for i in range(len(points) - 1):
        p1 = points[i]
        p2 = points[i + 1]

        # Calculate segment vector and length
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        segment_length = math.sqrt(dx * dx + dy * dy)

        if segment_length < 1e-10:
            # Zero-length segment, skip it
            continue

        # Check if target distance is reached in this segment
        if accumulated_distance + segment_length >= target_distance:
            remaining = target_distance - accumulated_distance

            # Check if we land exactly on p1 (start of segment)
            if remaining < 1e-10:
                # Normalize direction vector
                dir_x = dx / segment_length
                dir_y = dy / segment_length
                return (p1, (dir_x, dir_y), i)

            # Check if we land exactly on p2 (end of segment)
            if abs(remaining - segment_length) < 1e-10:
                # Normalize direction vector
                dir_x = dx / segment_length
                dir_y = dy / segment_length
                return (p2, (dir_x, dir_y), i + 1)

            # Interpolate within the segment
            t = remaining / segment_length  # Parameter in [0, 1]

            interpolated_point = (
                p1[0] + t * dx,
                p1[1] + t * dy
            )

            # Direction vector is the segment direction
            dir_x = dx / segment_length
            dir_y = dy / segment_length

            return (interpolated_point, (dir_x, dir_y), i)

        accumulated_distance += segment_length

    # Target distance exceeds path length
    # Return None to indicate we couldn't reach the target
    return None


def calculate_hermite_parampoly3(
    start_pos: Tuple[float, float],
    start_tangent: Tuple[float, float],
    end_pos: Tuple[float, float],
    end_tangent: Tuple[float, float],
    tangent_scale: float = 1.0
) -> Tuple[float, float, float, float, float, float, float, float]:
    """
    Calculate ParamPoly3D coefficients using Hermite interpolation.

    Creates a cubic polynomial curve that:
    - Starts at start_pos with direction start_tangent
    - Ends at end_pos with direction end_tangent
    - Provides smooth, tangent-continuous transitions

    The curve is defined in LOCAL (u, v) coordinates where:
    - Origin is at start_pos
    - u-axis points along start_tangent direction (start heading)
    - v-axis is perpendicular (90° counterclockwise from u)

    The polynomial form is:
        u(p) = aU + bU*p + cU*p² + dU*p³
        v(p) = aV + bV*p + cV*p² + dV*p³
    where p ∈ [0, 1]

    Args:
        start_pos: Starting position (x, y) in pixels
        start_tangent: Tangent vector at start (dx, dy) - should be normalized
        end_pos: Ending position (x, y) in pixels
        end_tangent: Tangent vector at end (dx, dy) - should be normalized
        tangent_scale: Scale factor for tangent lengths (controls curve tightness)

    Returns:
        Tuple of (aU, bU, cU, dU, aV, bV, cV, dV) - coefficients in LOCAL coordinates
    """
    x0, y0 = start_pos
    x1, y1 = end_pos

    # Calculate start heading from start_tangent
    start_heading = math.atan2(start_tangent[1], start_tangent[0])
    cos_h = math.cos(start_heading)
    sin_h = math.sin(start_heading)

    # Transform end position to local (u, v) coordinates
    dx_global = x1 - x0
    dy_global = y1 - y0
    end_u = dx_global * cos_h + dy_global * sin_h
    end_v = -dx_global * sin_h + dy_global * cos_h

    # Transform end tangent to local frame
    end_tangent_u = end_tangent[0] * cos_h + end_tangent[1] * sin_h
    end_tangent_v = -end_tangent[0] * sin_h + end_tangent[1] * cos_h

    # Distance for tangent scaling
    dist = math.sqrt(dx_global * dx_global + dy_global * dy_global)

    # Apply tangent scale
    scale = dist * tangent_scale / 3.0  # Divide by 3 for good curve shape

    # Start tangent in local frame is (1, 0) since u-axis is along start heading
    tu0 = 1.0 * scale
    tv0 = 0.0

    # End tangent in local frame (scaled)
    tu1 = end_tangent_u * scale
    tv1 = end_tangent_v * scale

    # Hermite polynomial coefficients for cubic curve in LOCAL coordinates
    # Start at origin (0, 0) in local frame
    # Based on Hermite basis functions:
    # H0(p) = 2p³ - 3p² + 1 (start position weight)
    # H1(p) = -2p³ + 3p² (end position weight)
    # H2(p) = p³ - 2p² + p (start tangent weight)
    # H3(p) = p³ - p² (end tangent weight)

    # u(p) = 0*H0(p) + end_u*H1(p) + tu0*H2(p) + tu1*H3(p)
    aU = 0.0  # Start at local origin
    bU = tu0  # Linear term (start tangent)
    cU = 3*end_u - 2*tu0 - tu1  # Quadratic term
    dU = -2*end_u + tu0 + tu1  # Cubic term

    # Same for v(p)
    aV = 0.0
    bV = tv0
    cV = 3*end_v - 2*tv0 - tv1
    dV = -2*end_v + tv0 + tv1

    return (aU, bU, cU, dU, aV, bV, cV, dV)


def sample_parampoly3(
    aU: float, bU: float, cU: float, dU: float,
    aV: float, bV: float, cV: float, dV: float,
    num_points: int = 20,
    p_range: float = 1.0
) -> List[Tuple[float, float]]:
    """
    Sample points along a ParamPoly3D curve for visualization.

    Args:
        aU, bU, cU, dU: Coefficients for u(p) polynomial
        aV, bV, cV, dV: Coefficients for v(p) polynomial
        num_points: Number of points to sample
        p_range: Parameter range (typically 1.0 for normalized curves)

    Returns:
        List of (x, y) points along the curve
    """
    points = []

    for i in range(num_points):
        # Normalized parameter from 0 to p_range
        p = (i / (num_points - 1)) * p_range

        # Evaluate polynomials
        u = aU + bU*p + cU*p*p + dU*p*p*p
        v = aV + bV*p + cV*p*p + dV*p*p*p

        points.append((u, v))

    return points


def evaluate_parampoly3_global(
    aU: float, bU: float, cU: float, dU: float,
    aV: float, bV: float, cV: float, dV: float,
    start_pos: Tuple[float, float],
    start_heading: float,
    num_points: int = 50
) -> List[Tuple[float, float]]:
    """
    Evaluate ParamPoly3D curve and transform to global coordinates.

    The ParamPoly3D curve is defined in local (u, v) coordinates where:
    - Origin is at start_pos
    - u-axis points along start_heading
    - v-axis is perpendicular (90° counter-clockwise from u)

    Args:
        aU, bU, cU, dU: Coefficients for u(p) polynomial
        aV, bV, cV, dV: Coefficients for v(p) polynomial
        start_pos: Starting position (x, y) in global coordinates
        start_heading: Heading angle in radians (0 = east, π/2 = north)
        num_points: Number of points to sample (default 50 for smooth curves)

    Returns:
        List of (x, y) points in global coordinates
    """
    points = []
    cos_h = math.cos(start_heading)
    sin_h = math.sin(start_heading)

    for i in range(num_points + 1):
        # Parameter from 0 to 1
        p = i / num_points

        # Evaluate polynomial in local (u, v) coordinates
        u = aU + bU*p + cU*p*p + dU*p*p*p
        v = aV + bV*p + cV*p*p + dV*p*p*p

        # Transform to global coordinates:
        # x = start_x + u*cos(heading) - v*sin(heading)
        # y = start_y + u*sin(heading) + v*cos(heading)
        x = start_pos[0] + u*cos_h - v*sin_h
        y = start_pos[1] + u*sin_h + v*cos_h
        points.append((x, y))

    return points


def line_intersection(
    p1: Tuple[float, float],
    d1: Tuple[float, float],
    p2: Tuple[float, float],
    d2: Tuple[float, float]
) -> Optional[Tuple[float, float]]:
    """
    Find intersection point of two lines defined by point + direction.

    Line 1: p1 + t * d1
    Line 2: p2 + s * d2

    Args:
        p1: Point on line 1
        d1: Direction vector of line 1
        p2: Point on line 2
        d2: Direction vector of line 2

    Returns:
        Intersection point (x, y) or None if lines are parallel
    """
    # Cross product of directions
    cross = d1[0] * d2[1] - d1[1] * d2[0]

    if abs(cross) < 1e-10:
        # Lines are parallel
        return None

    # Vector from p1 to p2
    dp = (p2[0] - p1[0], p2[1] - p1[1])

    # Parameter t where intersection occurs on line 1
    t = (dp[0] * d2[1] - dp[1] * d2[0]) / cross

    # Intersection point
    return (p1[0] + t * d1[0], p1[1] + t * d1[1])


def angle_between_vectors(
    v1: Tuple[float, float],
    v2: Tuple[float, float]
) -> float:
    """
    Calculate signed angle from v1 to v2 in radians.

    Positive angle means counterclockwise rotation from v1 to v2.

    Args:
        v1: First vector (unit or non-unit)
        v2: Second vector (unit or non-unit)

    Returns:
        Angle in radians, in range [-π, π]
    """
    # Use atan2 of cross and dot products
    cross = v1[0] * v2[1] - v1[1] * v2[0]
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    return math.atan2(cross, dot)


def calculate_bezier_control_points(
    start_pos: Tuple[float, float],
    start_tangent: Tuple[float, float],
    end_pos: Tuple[float, float],
    end_tangent: Tuple[float, float],
    is_uturn: bool = False
) -> Optional[List[Tuple[float, float]]]:
    """
    Calculate Bezier control points for a smooth junction connection.

    Uses lane extrapolation and intersection to find control points that
    naturally ensure G1 (tangent) continuity. Algorithm based on SUMO's
    NBNode::bezierControlPoints().

    Args:
        start_pos: Starting position (x, y)
        start_tangent: Unit tangent vector at start (direction of travel)
        end_pos: Ending position (x, y)
        end_tangent: Unit tangent vector at end (direction of travel)
        is_uturn: Whether this is a U-turn connection

    Returns:
        List of 3-4 control points for Bezier curve, or None if calculation fails
        (e.g., parallel lanes that don't intersect)
    """
    dx = end_pos[0] - start_pos[0]
    dy = end_pos[1] - start_pos[1]
    dist = math.sqrt(dx * dx + dy * dy)

    if dist < 1e-6:
        # Points too close
        return None

    # Calculate angle between tangents
    angle = angle_between_vectors(start_tangent, end_tangent)

    control_points = [start_pos]

    if is_uturn:
        # U-turn: use perpendicular offset from midpoint
        midpoint = ((start_pos[0] + end_pos[0]) / 2, (start_pos[1] + end_pos[1]) / 2)

        # Perpendicular to the line connecting start and end
        # Offset towards the "outside" of the turn
        perp_x = -(end_pos[1] - start_pos[1])
        perp_y = end_pos[0] - start_pos[0]
        perp_len = math.sqrt(perp_x * perp_x + perp_y * perp_y)

        if perp_len > 1e-6:
            perp_x /= perp_len
            perp_y /= perp_len

            # Offset by half the distance to create a semicircular shape
            offset = dist / 2
            center = (midpoint[0] + perp_x * offset, midpoint[1] + perp_y * offset)
            control_points.append(center)

    elif abs(angle) < math.pi / 4:
        # Small angle (<45°): S-curve with 4 control points
        # Place control points along extrapolated tangent lines

        half_dist = dist / 2
        extrapolate_len = min(25.0, half_dist)  # Limit extrapolation

        # Control point 1: along start tangent
        ctrl1 = (
            start_pos[0] + start_tangent[0] * extrapolate_len,
            start_pos[1] + start_tangent[1] * extrapolate_len
        )
        control_points.append(ctrl1)

        # Control point 2: backward from end along end tangent
        ctrl2 = (
            end_pos[0] - end_tangent[0] * extrapolate_len,
            end_pos[1] - end_tangent[1] * extrapolate_len
        )
        control_points.append(ctrl2)

    else:
        # Large angle (>45°): find intersection of tangent lines
        # This naturally creates G1 continuity

        intersect = line_intersection(start_pos, start_tangent, end_pos, end_tangent)

        if intersect is None:
            # Lines are parallel - can't compute intersection
            return None

        # Check if intersection is reasonable (not too far away)
        dist_to_intersect_start = distance_between_points(start_pos, intersect)
        dist_to_intersect_end = distance_between_points(end_pos, intersect)

        # Limit control point distance to avoid extreme curves
        max_ctrl_dist = dist * 2.0  # Allow up to 2x the direct distance

        if dist_to_intersect_start > max_ctrl_dist or dist_to_intersect_end > max_ctrl_dist:
            # Intersection too far - fall back to S-curve approach
            half_dist = dist / 2
            extrapolate_len = min(25.0, half_dist)

            ctrl1 = (
                start_pos[0] + start_tangent[0] * extrapolate_len,
                start_pos[1] + start_tangent[1] * extrapolate_len
            )
            control_points.append(ctrl1)

            ctrl2 = (
                end_pos[0] - end_tangent[0] * extrapolate_len,
                end_pos[1] - end_tangent[1] * extrapolate_len
            )
            control_points.append(ctrl2)
        else:
            # Use intersection as the control point (quadratic Bezier)
            control_points.append(intersect)

    control_points.append(end_pos)
    return control_points


def bezier_to_parampoly3(
    control_points: List[Tuple[float, float]],
    start_heading: float
) -> Tuple[float, float, float, float, float, float, float, float]:
    """
    Convert Bezier control points to paramPoly3 coefficients in local (u,v) frame.

    The local coordinate system has:
    - Origin at the first control point
    - u-axis aligned with start_heading
    - v-axis perpendicular (90° counterclockwise from u)

    For quadratic Bezier (3 control points P0, P1, P2):
        B(t) = (1-t)²P0 + 2(1-t)t·P1 + t²P2
        Coefficients: a=P0, b=2(P1-P0), c=P0-2P1+P2, d=0

    For cubic Bezier (4 control points P0, P1, P2, P3):
        B(t) = (1-t)³P0 + 3(1-t)²t·P1 + 3(1-t)t²P2 + t³P3
        Coefficients: a=P0, b=3(P1-P0), c=3(P0-2P1+P2), d=-P0+3P1-3P2+P3

    Args:
        control_points: List of 3 or 4 (x, y) control points
        start_heading: Heading angle in radians for local coordinate system

    Returns:
        Tuple of (aU, bU, cU, dU, aV, bV, cV, dV) - paramPoly3 coefficients
    """
    if len(control_points) < 3:
        raise ValueError("Need at least 3 control points")

    # Transform to local (u, v) coordinate system
    origin = control_points[0]
    cos_h = math.cos(start_heading)
    sin_h = math.sin(start_heading)

    def to_local(p: Tuple[float, float]) -> Tuple[float, float]:
        """Transform point to local (u, v) coordinates."""
        dx = p[0] - origin[0]
        dy = p[1] - origin[1]
        # Rotate by -heading to align with u-axis
        u = dx * cos_h + dy * sin_h
        v = -dx * sin_h + dy * cos_h
        return (u, v)

    # Transform all control points
    local_pts = [to_local(p) for p in control_points]

    # First point should be at origin in local frame
    # (but may have small numerical errors)

    if len(control_points) == 3:
        # Quadratic Bezier
        P0, P1, P2 = local_pts

        aU = P0[0]
        bU = 2 * (P1[0] - P0[0])
        cU = P0[0] - 2 * P1[0] + P2[0]
        dU = 0.0

        aV = P0[1]
        bV = 2 * (P1[1] - P0[1])
        cV = P0[1] - 2 * P1[1] + P2[1]
        dV = 0.0

    else:
        # Cubic Bezier (4 or more points - use first 4)
        P0, P1, P2, P3 = local_pts[:4]

        aU = P0[0]
        bU = 3 * (P1[0] - P0[0])
        cU = 3 * (P0[0] - 2 * P1[0] + P2[0])
        dU = -P0[0] + 3 * P1[0] - 3 * P2[0] + P3[0]

        aV = P0[1]
        bV = 3 * (P1[1] - P0[1])
        cV = 3 * (P0[1] - 2 * P1[1] + P2[1])
        dV = -P0[1] + 3 * P1[1] - 3 * P2[1] + P3[1]

    return (aU, bU, cU, dU, aV, bV, cV, dV)


def calculate_directional_scale(
    points: List[Tuple[float, float]],
    scale_x: float,
    scale_y: float,
    default_scale: Optional[float] = None
) -> float:
    """
    Calculate appropriate scale factor based on polyline direction.

    For roads/polylines running primarily horizontal (east-west), weight scale_x more.
    For roads/polylines running primarily vertical (north-south), weight scale_y more.
    For diagonal roads, interpolate between scale_x and scale_y.

    This accounts for non-uniform pixel scales in images where scale_x != scale_y.

    Args:
        points: List of (x, y) points defining the polyline.
        scale_x: Scale factor for horizontal direction (m/px).
        scale_y: Scale factor for vertical direction (m/px).
        default_scale: Value to return if scale cannot be calculated.
                      Defaults to average of scale_x and scale_y.

    Returns:
        Scale factor in meters per pixel appropriate for this polyline's direction.

    Example:
        scale = calculate_directional_scale(centerline.points, scale_x, scale_y)
        width_m = width_px * scale
    """
    if len(points) < 2:
        # Can't determine direction, use average or default
        if default_scale is not None:
            return default_scale
        return (scale_x + scale_y) / 2

    # Calculate total displacement in x and y
    total_dx = 0.0
    total_dy = 0.0
    for i in range(len(points) - 1):
        p1 = points[i]
        p2 = points[i + 1]
        dx = abs(p2[0] - p1[0])
        dy = abs(p2[1] - p1[1])
        total_dx += dx
        total_dy += dy

    # Calculate total distance
    total_dist = total_dx + total_dy
    if total_dist == 0:
        if default_scale is not None:
            return default_scale
        return (scale_x + scale_y) / 2

    # Calculate weights based on direction
    weight_x = total_dx / total_dist
    weight_y = total_dy / total_dist

    # Interpolate between scale_x and scale_y based on direction
    return weight_x * scale_x + weight_y * scale_y


# ============================================================================
# Arc geometry utilities (for roundabouts)
# ============================================================================


def calculate_arc_parameters(
    points: List[Tuple[float, float]],
    center: Tuple[float, float]
) -> Tuple[float, float, float]:
    """
    Calculate arc parameters for a sequence of points around a center.

    Args:
        points: Points along the arc in order
        center: Center of the circle

    Returns:
        Tuple of (curvature, start_angle, sweep_angle):
        - curvature: 1/radius, positive for CCW arc
        - start_angle: angle of first point from center (radians)
        - sweep_angle: total angle swept (radians, positive=CCW)
    """
    if len(points) < 2:
        return (0.0, 0.0, 0.0)

    cx, cy = center

    # Calculate radius from first point
    first = points[0]
    radius = math.sqrt((first[0] - cx)**2 + (first[1] - cy)**2)

    if radius < 1e-6:
        return (0.0, 0.0, 0.0)

    # Start angle
    start_angle = math.atan2(first[1] - cy, first[0] - cx)

    # End angle
    last = points[-1]
    end_angle = math.atan2(last[1] - cy, last[0] - cx)

    # Sweep angle (difference, normalized to -π to π initially)
    sweep_angle = normalize_angle(end_angle - start_angle)

    # Determine sweep direction from point order
    # Check if points go CCW (positive sweep) or CW (negative sweep)
    if len(points) >= 3:
        mid = points[len(points) // 2]
        mid_angle = math.atan2(mid[1] - cy, mid[0] - cx)

        # Check if mid angle is between start and end in the expected direction
        if sweep_angle > 0:
            # Expected CCW: mid should be between start and end
            expected_mid = normalize_angle(start_angle + sweep_angle / 2)
            if abs(normalize_angle(mid_angle - expected_mid)) > math.pi / 2:
                # Wrong direction, sweep should be negative
                sweep_angle = sweep_angle - 2 * math.pi
        else:
            # Expected CW: mid should be between start and end
            expected_mid = normalize_angle(start_angle + sweep_angle / 2)
            if abs(normalize_angle(mid_angle - expected_mid)) > math.pi / 2:
                # Wrong direction, sweep should be positive
                sweep_angle = sweep_angle + 2 * math.pi

    # Curvature is 1/radius, with sign based on sweep direction
    curvature = (1.0 / radius) if sweep_angle >= 0 else (-1.0 / radius)

    return (curvature, start_angle, sweep_angle)


def generate_arc_points(
    center: Tuple[float, float],
    radius: float,
    start_angle: float,
    sweep_angle: float,
    num_points: int = 20
) -> List[Tuple[float, float]]:
    """
    Generate evenly-spaced points along a circular arc.

    Args:
        center: Circle center (cx, cy)
        radius: Circle radius
        start_angle: Starting angle (radians, 0=east)
        sweep_angle: Angle to sweep (positive=CCW)
        num_points: Number of points to generate

    Returns:
        List of (x, y) points along the arc
    """
    if num_points < 2:
        num_points = 2

    cx, cy = center
    points = []

    for i in range(num_points):
        t = i / (num_points - 1)
        angle = start_angle + t * sweep_angle

        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)
        points.append((x, y))

    return points


def calculate_tangent_heading(
    point: Tuple[float, float],
    center: Tuple[float, float],
    clockwise: bool = False
) -> float:
    """
    Calculate tangent heading at a point on a circle.

    The tangent is perpendicular to the radius, in the direction of travel.

    Args:
        point: Point on the circle (x, y)
        center: Circle center (cx, cy)
        clockwise: If True, tangent points clockwise direction

    Returns:
        Heading in radians (0=east, π/2=north in mathematical coords)
    """
    cx, cy = center
    px, py = point

    # Radius direction
    dx = px - cx
    dy = py - cy

    # Tangent is perpendicular to radius
    # For CCW travel: rotate radius 90° CCW -> (-dy, dx)
    # For CW travel: rotate radius 90° CW -> (dy, -dx)
    if clockwise:
        tangent_x = dy
        tangent_y = -dx
    else:
        tangent_x = -dy
        tangent_y = dx

    return math.atan2(tangent_y, tangent_x)


def arc_length(radius: float, sweep_angle: float) -> float:
    """
    Calculate arc length: L = r * |theta|.

    Args:
        radius: Circle radius
        sweep_angle: Sweep angle in radians

    Returns:
        Arc length
    """
    return abs(radius * sweep_angle)


def fit_circle_to_points(
    points: List[Tuple[float, float]]
) -> Optional[Tuple[Tuple[float, float], float]]:
    """
    Fit a circle to a set of points using least squares.

    Uses algebraic circle fit (minimizes algebraic distance).

    Args:
        points: List of (x, y) points

    Returns:
        Tuple of (center, radius) or None if fitting fails
    """
    if len(points) < 3:
        return None

    n = len(points)
    sum_x = sum(p[0] for p in points)
    sum_y = sum(p[1] for p in points)
    sum_x2 = sum(p[0]**2 for p in points)
    sum_y2 = sum(p[1]**2 for p in points)
    sum_xy = sum(p[0] * p[1] for p in points)
    sum_x3 = sum(p[0]**3 for p in points)
    sum_y3 = sum(p[1]**3 for p in points)
    sum_x2y = sum(p[0]**2 * p[1] for p in points)
    sum_xy2 = sum(p[0] * p[1]**2 for p in points)

    # Solve system of equations for circle center
    A = n * sum_x2 - sum_x**2
    B = n * sum_xy - sum_x * sum_y
    C = n * sum_y2 - sum_y**2
    D = 0.5 * (n * sum_x3 + n * sum_xy2 - sum_x * sum_x2 - sum_x * sum_y2)
    E = 0.5 * (n * sum_x2y + n * sum_y3 - sum_y * sum_x2 - sum_y * sum_y2)

    denom = A * C - B * B
    if abs(denom) < 1e-10:
        return None

    cx = (D * C - B * E) / denom
    cy = (A * E - B * D) / denom

    # Calculate radius
    radii = [math.sqrt((p[0] - cx)**2 + (p[1] - cy)**2) for p in points]
    radius = sum(radii) / len(radii)

    return ((cx, cy), radius)


# ============================================================================
# Polyline splitting utilities (for road splitting)
# ============================================================================


def project_point_to_polyline(
    point: Tuple[float, float],
    polyline_points: List[Tuple[float, float]]
) -> Tuple[float, float, int]:
    """
    Project a point onto a polyline, returning s-coordinate and distance.

    Finds the closest point on the polyline to the given point.

    Args:
        point: Point to project (x, y)
        polyline_points: Points defining the polyline

    Returns:
        Tuple of (s_coordinate, perpendicular_distance, segment_index):
        - s_coordinate: Distance along polyline to the projected point
        - perpendicular_distance: Distance from point to projection (positive = right of direction)
        - segment_index: Index of segment where projection lands
    """
    if len(polyline_points) < 2:
        if len(polyline_points) == 1:
            dist = distance_between_points(point, polyline_points[0])
            return (0.0, dist, 0)
        return (0.0, 0.0, 0)

    best_s = 0.0
    best_dist = float('inf')
    best_segment = 0
    accumulated_s = 0.0

    px, py = point

    for i in range(len(polyline_points) - 1):
        p1 = polyline_points[i]
        p2 = polyline_points[i + 1]

        # Segment vector
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        seg_len_sq = dx * dx + dy * dy

        if seg_len_sq < 1e-10:
            # Zero-length segment
            dist = distance_between_points(point, p1)
            if dist < best_dist:
                best_dist = dist
                best_s = accumulated_s
                best_segment = i
            continue

        seg_len = math.sqrt(seg_len_sq)

        # Project point onto segment line
        # t = ((P - P1) · (P2 - P1)) / |P2 - P1|²
        t = ((px - p1[0]) * dx + (py - p1[1]) * dy) / seg_len_sq

        # Clamp t to [0, 1] to stay within segment
        t = max(0.0, min(1.0, t))

        # Closest point on segment
        closest_x = p1[0] + t * dx
        closest_y = p1[1] + t * dy

        dist = math.sqrt((px - closest_x) ** 2 + (py - closest_y) ** 2)

        if dist < best_dist:
            best_dist = dist
            best_s = accumulated_s + t * seg_len
            best_segment = i

            # Calculate signed distance (positive = right of direction)
            # Cross product: (P2-P1) × (P-P1) / |P2-P1|
            cross = dx * (py - p1[1]) - dy * (px - p1[0])
            best_dist = -cross / seg_len  # Negative because screen coords

        accumulated_s += seg_len

    return (best_s, best_dist, best_segment)


def find_point_on_polyline_at_s(
    polyline_points: List[Tuple[float, float]],
    target_s: float
) -> Optional[Tuple[Tuple[float, float], int, float]]:
    """
    Find the point on a polyline at a given s-coordinate (distance along).

    Args:
        polyline_points: Points defining the polyline
        target_s: Target distance along the polyline

    Returns:
        Tuple of (point, segment_index, t_within_segment) or None if s exceeds length:
        - point: (x, y) coordinates at target_s
        - segment_index: Index of the segment containing the point
        - t_within_segment: Interpolation parameter within segment [0, 1]
    """
    if len(polyline_points) < 2:
        return None

    if target_s <= 0:
        return (polyline_points[0], 0, 0.0)

    accumulated_s = 0.0

    for i in range(len(polyline_points) - 1):
        p1 = polyline_points[i]
        p2 = polyline_points[i + 1]

        seg_len = distance_between_points(p1, p2)

        if seg_len < 1e-10:
            continue

        if accumulated_s + seg_len >= target_s:
            # Target is in this segment
            remaining = target_s - accumulated_s
            t = remaining / seg_len

            point = (
                p1[0] + t * (p2[0] - p1[0]),
                p1[1] + t * (p2[1] - p1[1])
            )
            return (point, i, t)

        accumulated_s += seg_len

    # Target exceeds polyline length, return last point
    return (polyline_points[-1], len(polyline_points) - 2, 1.0)


def split_polyline_at_index(
    points: List[Tuple[float, float]],
    split_index: int,
    duplicate_point: bool = True
) -> Tuple[List[Tuple[float, float]], List[Tuple[float, float]]]:
    """
    Split a polyline at a given point index.

    Args:
        points: List of (x, y) points
        split_index: Index of the point to split at
        duplicate_point: If True, split point appears in both result lists

    Returns:
        Tuple of (first_segment, second_segment)
    """
    if split_index <= 0:
        return ([], list(points))
    if split_index >= len(points) - 1:
        return (list(points), [])

    if duplicate_point:
        first = points[:split_index + 1]
        second = points[split_index:]
    else:
        first = points[:split_index + 1]
        second = points[split_index + 1:]

    return (list(first), list(second))


def split_boundary_at_centerline_s(
    boundary_points: List[Tuple[float, float]],
    centerline_points: List[Tuple[float, float]],
    target_s: float
) -> Optional[Tuple[List[Tuple[float, float]], List[Tuple[float, float]]]]:
    """
    Split a boundary polyline at the position corresponding to a centerline s-coordinate.

    Projects each boundary point onto the centerline to find where the boundary
    crosses the target s-coordinate, then splits at that point.

    Args:
        boundary_points: Points of the boundary polyline to split
        centerline_points: Points of the centerline
        target_s: Target s-coordinate along centerline where to split

    Returns:
        Tuple of (first_segment, second_segment) with split point duplicated in both,
        or None if the boundary doesn't span the target s-coordinate.
    """
    if len(boundary_points) < 2 or len(centerline_points) < 2:
        return None

    # Project each boundary point onto centerline to get its s-coordinate
    boundary_s_coords = []
    for pt in boundary_points:
        s, _, _ = project_point_to_polyline(pt, centerline_points)
        boundary_s_coords.append(s)

    # Find where boundary crosses target_s
    split_segment = None
    for i in range(len(boundary_s_coords) - 1):
        s1 = boundary_s_coords[i]
        s2 = boundary_s_coords[i + 1]

        # Check if target_s is between s1 and s2
        if (s1 <= target_s <= s2) or (s2 <= target_s <= s1):
            split_segment = i
            break

    if split_segment is None:
        # Boundary doesn't span the target s-coordinate
        # Return all points in first segment if boundary is entirely before target_s
        # or all in second segment if entirely after
        if all(s <= target_s for s in boundary_s_coords):
            return (list(boundary_points), [boundary_points[-1]])
        elif all(s >= target_s for s in boundary_s_coords):
            return ([boundary_points[0]], list(boundary_points))
        return None

    # Interpolate to find exact split point
    s1 = boundary_s_coords[split_segment]
    s2 = boundary_s_coords[split_segment + 1]
    p1 = boundary_points[split_segment]
    p2 = boundary_points[split_segment + 1]

    # Handle edge case where s1 == s2
    if abs(s2 - s1) < 1e-10:
        t = 0.5
    else:
        t = (target_s - s1) / (s2 - s1)

    # Clamp t to [0, 1]
    t = max(0.0, min(1.0, t))

    split_point = (
        p1[0] + t * (p2[0] - p1[0]),
        p1[1] + t * (p2[1] - p1[1])
    )

    # Create the two segments with split point duplicated
    first_segment = list(boundary_points[:split_segment + 1]) + [split_point]
    second_segment = [split_point] + list(boundary_points[split_segment + 1:])

    return (first_segment, second_segment)


def merge_polylines_at_junction(
    polyline1_points: List[Tuple[float, float]],
    polyline2_points: List[Tuple[float, float]],
    tolerance: float = 1.0
) -> Optional[List[Tuple[float, float]]]:
    """
    Merge two polylines that share a junction point.

    The first polyline's end point should be at or near the second polyline's start point.
    The duplicate junction point is removed in the merged result.

    Args:
        polyline1_points: First polyline (ends at junction)
        polyline2_points: Second polyline (starts at junction)
        tolerance: Max distance between endpoints to consider them as same point (pixels)

    Returns:
        Merged points list (removes duplicate junction point), or None if not joinable
    """
    if not polyline1_points or not polyline2_points:
        return None

    end1 = polyline1_points[-1]
    start2 = polyline2_points[0]

    # Check if endpoints are close enough
    dist = math.sqrt((end1[0] - start2[0])**2 + (end1[1] - start2[1])**2)
    if dist > tolerance:
        return None

    # Merge: all of polyline1 + polyline2 without first point (remove duplicate junction)
    return list(polyline1_points) + list(polyline2_points[1:])


def sample_bezier(
    control_points: List[Tuple[float, float]],
    num_points: int = 20
) -> List[Tuple[float, float]]:
    """
    Sample points along a Bezier curve for visualization.

    Supports both quadratic (3 points) and cubic (4 points) Bezier curves.

    Args:
        control_points: List of 3 or 4 (x, y) control points
        num_points: Number of points to sample

    Returns:
        List of (x, y) points along the curve
    """
    if len(control_points) < 3:
        return list(control_points)

    points = []

    for i in range(num_points):
        t = i / (num_points - 1)

        if len(control_points) == 3:
            # Quadratic Bezier: B(t) = (1-t)²P0 + 2(1-t)t·P1 + t²P2
            P0, P1, P2 = control_points
            one_minus_t = 1 - t
            x = one_minus_t * one_minus_t * P0[0] + 2 * one_minus_t * t * P1[0] + t * t * P2[0]
            y = one_minus_t * one_minus_t * P0[1] + 2 * one_minus_t * t * P1[1] + t * t * P2[1]

        else:
            # Cubic Bezier: B(t) = (1-t)³P0 + 3(1-t)²t·P1 + 3(1-t)t²P2 + t³P3
            P0, P1, P2, P3 = control_points[:4]
            one_minus_t = 1 - t
            x = (one_minus_t ** 3 * P0[0] +
                 3 * one_minus_t ** 2 * t * P1[0] +
                 3 * one_minus_t * t ** 2 * P2[0] +
                 t ** 3 * P3[0])
            y = (one_minus_t ** 3 * P0[1] +
                 3 * one_minus_t ** 2 * t * P1[1] +
                 3 * one_minus_t * t ** 2 * P2[1] +
                 t ** 3 * P3[1])

        points.append((x, y))

    return points


def find_geo_point_at_distance_along_path(
    geo_points: List[Tuple[float, float]],
    distance_meters: float,
    from_start: bool = True
) -> Optional[Tuple[Tuple[float, float], int]]:
    """
    Find point at specified distance (in meters) along a geographic path.

    Similar to find_point_at_distance_along_path but works with geographic
    coordinates (lon, lat) and uses Haversine distance calculations.

    Args:
        geo_points: List of (lon, lat) points in geographic coordinates
        distance_meters: Distance to travel along the path in meters
        from_start: If True, measure from start; if False, measure from end

    Returns:
        Tuple of (geo_point, segment_index) or None if:
        - geo_point: (lon, lat) coordinates at the target distance
        - segment_index: Index of the segment where point was found

        Returns None if distance exceeds path length or points list is invalid.
    """
    if len(geo_points) < 2:
        return None

    # If measuring from end, reverse the point list
    if not from_start:
        geo_points = list(reversed(geo_points))

    accumulated_distance = 0.0
    target_distance = abs(distance_meters)

    for i in range(len(geo_points) - 1):
        lon1, lat1 = geo_points[i]
        lon2, lat2 = geo_points[i + 1]

        # Calculate segment length using Haversine formula
        segment_length = haversine_distance(lat1, lon1, lat2, lon2)

        if segment_length < 1e-10:
            # Zero-length segment, skip it
            continue

        # Check if target distance is reached in this segment
        if accumulated_distance + segment_length >= target_distance:
            remaining = target_distance - accumulated_distance

            # Check if we land exactly on start of segment
            if remaining < 1e-10:
                return ((lon1, lat1), i)

            # Check if we land exactly on end of segment
            if abs(remaining - segment_length) < 1e-10:
                return ((lon2, lat2), i + 1)

            # Interpolate within the segment
            t = remaining / segment_length  # Parameter in [0, 1]

            # Linear interpolation in geographic space (good approximation for short segments)
            interpolated_lon = lon1 + t * (lon2 - lon1)
            interpolated_lat = lat1 + t * (lat2 - lat1)

            return ((interpolated_lon, interpolated_lat), i)

        accumulated_distance += segment_length

    # Target distance exceeds path length
    return None


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate distance between two lat/lon points using Haversine formula.

    Args:
        lat1, lon1: First point latitude and longitude in degrees
        lat2, lon2: Second point latitude and longitude in degrees

    Returns:
        Distance in meters
    """
    # Earth's radius in meters
    R = 6371000.0

    # Convert to radians
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    # Haversine formula
    a = (math.sin(delta_lat / 2) ** 2 +
         math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def shorten_geo_points(
    geo_points: List[Tuple[float, float]],
    offset_start_meters: float,
    offset_end_meters: float
) -> List[Tuple[float, float]]:
    """
    Shorten a geo path by specified distances at start and end.

    This function removes intermediate points that are passed when walking
    the specified distance from each end, similar to how pixel paths are
    shortened at junction endpoints.

    Args:
        geo_points: List of (lon, lat) points in geographic coordinates
        offset_start_meters: Distance in meters to remove from start
        offset_end_meters: Distance in meters to remove from end

    Returns:
        New list of (lon, lat) points with shortened path
    """
    if len(geo_points) < 2:
        return list(geo_points)

    result = list(geo_points)

    # Shorten from start
    if offset_start_meters > 0:
        start_result = find_geo_point_at_distance_along_path(
            result, offset_start_meters, from_start=True
        )
        if start_result:
            new_start, segment_idx = start_result
            # Remove passed points and insert new start point
            result = [new_start] + result[segment_idx + 1:]

    # Shorten from end
    if offset_end_meters > 0 and len(result) >= 2:
        end_result = find_geo_point_at_distance_along_path(
            result, offset_end_meters, from_start=False
        )
        if end_result:
            new_end, segment_idx = end_result
            # Remove passed points from end and insert new end point
            result = result[:-(segment_idx + 1)] + [new_end]

    return result

"""
Geometry utilities for ORBIT.

Provides functions for geometric calculations like offset polylines,
perpendicular vectors, polygon construction, and junction path generation.
"""

import math
from typing import List, Tuple, Optional


def calculate_perpendicular(p1: Tuple[float, float], p2: Tuple[float, float]) -> Tuple[float, float]:
    """
    Calculate normalized perpendicular vector for a line segment.

    The perpendicular is rotated 90° counterclockwise from the segment direction.
    This means for a segment going right, the perpendicular points up.

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
        offset_distance: Distance to offset (positive = left/counterclockwise, negative = right/clockwise)
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
                                   num_points: int = 10) -> List[Tuple[float, float]]:
    """
    Generate a simple connection path between two road endpoints.

    This creates a smooth transition using a simple curved path.
    For Phase 2 MVP, uses interpolated points. Can be upgraded to
    proper arc or clothoid curves in future phases.

    Args:
        from_pos: Starting position (x, y)
        from_heading: Starting heading in radians
        to_pos: Ending position (x, y)
        to_heading: Ending heading in radians
        num_points: Number of points in the path

    Returns:
        List of (x, y) points
    """
    # For MVP: simple linear interpolation
    # Future enhancement: use Bezier curves or clothoids for smoother transitions

    points = []
    dx = to_pos[0] - from_pos[0]
    dy = to_pos[1] - from_pos[1]

    # Create control points for smoother curve
    # Use a simple approach: points along headings from start and end

    # Distance to extend along initial heading
    endpoint_dist = math.sqrt(dx*dx + dy*dy)

    # For junctions where from_pos == to_pos, use a fixed extend distance
    # Otherwise use 30% of the distance between endpoints
    MIN_EXTEND_DIST = 15.0  # Minimum 15 pixels/meters for junction connections
    if endpoint_dist < 1e-6:
        # Endpoints are at same location (junction) - extend outward along headings
        extend_dist = MIN_EXTEND_DIST
    else:
        # Normal case - extend based on endpoint separation
        extend_dist = max(MIN_EXTEND_DIST, 0.3 * endpoint_dist)

    # Control point 1: along from_heading
    cp1_x = from_pos[0] + extend_dist * math.cos(from_heading)
    cp1_y = from_pos[1] + extend_dist * math.sin(from_heading)

    # Control point 2: along to_heading (backwards)
    cp2_x = to_pos[0] - extend_dist * math.cos(to_heading)
    cp2_y = to_pos[1] - extend_dist * math.sin(to_heading)

    # Generate points along a cubic Bezier curve
    # P(t) = (1-t)³P0 + 3(1-t)²t*P1 + 3(1-t)t²*P2 + t³*P3
    for i in range(num_points):
        t = i / (num_points - 1)
        one_minus_t = 1 - t

        # Bezier curve coefficients
        b0 = one_minus_t ** 3
        b1 = 3 * (one_minus_t ** 2) * t
        b2 = 3 * one_minus_t * (t ** 2)
        b3 = t ** 3

        # Calculate point on curve
        x = (b0 * from_pos[0] +
             b1 * cp1_x +
             b2 * cp2_x +
             b3 * to_pos[0])

        y = (b0 * from_pos[1] +
             b1 * cp1_y +
             b2 * cp2_y +
             b3 * to_pos[1])

        points.append((x, y))

    return points


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

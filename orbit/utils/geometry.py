"""
Geometry utilities for ORBIT.

Provides functions for geometric calculations like offset polylines,
perpendicular vectors, and polygon construction.
"""

import math
from typing import List, Tuple


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

"""
Lane width polynomial fitting utilities.

Fits cubic polynomials to explicit lane boundary polylines for OpenDRIVE export.
"""

import math
from typing import List, Optional, Tuple

import numpy as np


def fit_lane_width_polynomial(
    centerline_points: List[Tuple[float, float]],
    left_boundary_points: List[Tuple[float, float]],
    right_boundary_points: List[Tuple[float, float]],
    lane_id: int,
    scale: float = 1.0
) -> Tuple[float, float, float, float, float]:
    """
    Fit a cubic polynomial to explicit lane boundaries.

    The width polynomial is: width(ds) = a + b*ds + c*ds² + d*ds³
    where ds is distance from start of section.

    Args:
        centerline_points: Road centerline points [(x, y), ...]
        left_boundary_points: Left boundary polyline points
        right_boundary_points: Right boundary polyline points
        lane_id: Lane ID (negative=right lane, positive=left lane)
        scale: Scale factor (m/px) for converting distances

    Returns:
        (a, b, c, d, rmse) - polynomial coefficients and fitting error in meters
    """
    if len(centerline_points) < 2:
        raise ValueError("Centerline must have at least 2 points")
    if len(left_boundary_points) < 2 or len(right_boundary_points) < 2:
        raise ValueError("Both boundaries must have at least 2 points")

    # Calculate s-coordinates (cumulative distance along centerline)
    s_coords = [0.0]
    for i in range(1, len(centerline_points)):
        dx = centerline_points[i][0] - centerline_points[i-1][0]
        dy = centerline_points[i][1] - centerline_points[i-1][1]
        s_coords.append(s_coords[-1] + math.sqrt(dx*dx + dy*dy))

    total_length = s_coords[-1]
    if total_length < 1e-6:
        raise ValueError("Centerline has zero length")

    # Sample widths at each centerline point
    s_samples = []
    width_samples = []

    for i, (px, py) in enumerate(centerline_points):
        # Calculate perpendicular direction at this point
        perp = _get_perpendicular_at_point(centerline_points, i)
        if perp is None:
            continue

        # Find distances to boundaries
        # For right lanes (negative ID): outer boundary is right
        # For left lanes (positive ID): outer boundary is left
        if lane_id < 0:
            # Right lane: measure from centerline to right boundary
            inner_dist = _ray_to_polyline_distance((px, py), perp, left_boundary_points)
            outer_dist = _ray_to_polyline_distance((px, py), (-perp[0], -perp[1]), right_boundary_points)
        else:
            # Left lane: measure from centerline to left boundary
            inner_dist = _ray_to_polyline_distance((px, py), (-perp[0], -perp[1]), right_boundary_points)
            outer_dist = _ray_to_polyline_distance((px, py), perp, left_boundary_points)

        # Width is the distance between boundaries
        if inner_dist is not None and outer_dist is not None:
            width = inner_dist + outer_dist
            if width > 0:
                s_samples.append(s_coords[i] * scale)
                width_samples.append(width * scale)

    if len(s_samples) < 4:
        raise ValueError(f"Insufficient sample points ({len(s_samples)}). Need at least 4 for cubic fit.")

    # Fit cubic polynomial using least squares
    s_arr = np.array(s_samples)
    w_arr = np.array(width_samples)

    # Build Vandermonde matrix for cubic fit: [1, s, s², s³]
    A = np.column_stack([
        np.ones_like(s_arr),
        s_arr,
        s_arr**2,
        s_arr**3
    ])

    # Solve least squares
    coeffs, residuals, rank, s = np.linalg.lstsq(A, w_arr, rcond=None)
    a, b, c, d = coeffs

    # Calculate RMSE
    fitted = a + b*s_arr + c*s_arr**2 + d*s_arr**3
    rmse = np.sqrt(np.mean((w_arr - fitted)**2))

    return float(a), float(b), float(c), float(d), float(rmse)


def fit_single_lane_width(
    centerline_points: List[Tuple[float, float]],
    boundary_points: List[Tuple[float, float]],
    lane_id: int,
    scale: float = 1.0
) -> Tuple[float, float, float, float, float]:
    """
    Fit polynomial for a single lane using only the outer boundary.

    For lanes where we only have one boundary (the outer edge), we measure
    the distance from centerline to that boundary.

    Args:
        centerline_points: Road centerline points
        boundary_points: Outer boundary polyline points
        lane_id: Lane ID (determines which side to measure)
        scale: Scale factor (m/px)

    Returns:
        (a, b, c, d, rmse) - polynomial coefficients and fitting error
    """
    if len(centerline_points) < 2:
        raise ValueError("Centerline must have at least 2 points")
    if len(boundary_points) < 2:
        raise ValueError("Boundary must have at least 2 points")

    # Calculate s-coordinates
    s_coords = [0.0]
    for i in range(1, len(centerline_points)):
        dx = centerline_points[i][0] - centerline_points[i-1][0]
        dy = centerline_points[i][1] - centerline_points[i-1][1]
        s_coords.append(s_coords[-1] + math.sqrt(dx*dx + dy*dy))

    total_length = s_coords[-1]
    if total_length < 1e-6:
        raise ValueError("Centerline has zero length")

    # Sample widths using perpendicular distance to boundary
    s_samples = []
    width_samples = []

    for i, (px, py) in enumerate(centerline_points):
        perp = _get_perpendicular_at_point(centerline_points, i)
        if perp is None:
            continue

        # Try ray casting first (more accurate for parallel boundaries)
        # perp points RIGHT of road (in screen coords with Y-down)
        # For right lane (lane_id < 0): measure to right = perp direction
        # For left lane (lane_id > 0): measure to left = -perp direction
        if lane_id < 0:
            direction = perp  # Right lane: measure to right
        else:
            direction = (-perp[0], -perp[1])  # Left lane: measure to left

        dist = _ray_to_polyline_distance((px, py), direction, boundary_points)

        # If ray casting fails, use closest point on boundary
        if dist is None or dist <= 0:
            dist = _point_to_polyline_perpendicular_distance(
                (px, py), perp, boundary_points, lane_id
            )

        if dist is not None and dist > 0:
            s_samples.append(s_coords[i] * scale)
            width_samples.append(dist * scale)

    if len(s_samples) < 2:
        raise ValueError(f"Insufficient sample points ({len(s_samples)}). "
                        f"Ensure the boundary polyline is on the correct side of the centerline.")

    # Fit polynomial - degree depends on number of points
    s_arr = np.array(s_samples)
    w_arr = np.array(width_samples)

    n_points = len(s_samples)
    if n_points >= 4:
        # Full cubic fit
        A = np.column_stack([np.ones_like(s_arr), s_arr, s_arr**2, s_arr**3])
        coeffs, _, _, _ = np.linalg.lstsq(A, w_arr, rcond=None)
        a, b, c, d = coeffs
    elif n_points == 3:
        # Quadratic fit
        A = np.column_stack([np.ones_like(s_arr), s_arr, s_arr**2])
        coeffs, _, _, _ = np.linalg.lstsq(A, w_arr, rcond=None)
        a, b, c = coeffs
        d = 0.0
    else:
        # Linear fit (2 points)
        A = np.column_stack([np.ones_like(s_arr), s_arr])
        coeffs, _, _, _ = np.linalg.lstsq(A, w_arr, rcond=None)
        a, b = coeffs
        c, d = 0.0, 0.0

    fitted = a + b*s_arr + c*s_arr**2 + d*s_arr**3
    rmse = np.sqrt(np.mean((w_arr - fitted)**2))

    return float(a), float(b), float(c), float(d), float(rmse)


def _point_to_polyline_perpendicular_distance(
    point: Tuple[float, float],
    perp: Tuple[float, float],
    polyline: List[Tuple[float, float]],
    lane_id: int
) -> Optional[float]:
    """
    Find perpendicular distance from point to polyline, checking the correct side.

    Uses closest point on polyline and verifies it's on the expected side.
    """
    px, py = point
    min_dist = float('inf')
    closest_point = None

    # Find closest point on polyline
    for i in range(len(polyline) - 1):
        p1 = polyline[i]
        p2 = polyline[i + 1]

        # Project point onto segment
        seg_x = p2[0] - p1[0]
        seg_y = p2[1] - p1[1]
        seg_len_sq = seg_x * seg_x + seg_y * seg_y

        if seg_len_sq < 1e-12:
            # Degenerate segment
            dist = math.sqrt((px - p1[0])**2 + (py - p1[1])**2)
            if dist < min_dist:
                min_dist = dist
                closest_point = p1
            continue

        # Parameter t for projection
        t = max(0, min(1, ((px - p1[0]) * seg_x + (py - p1[1]) * seg_y) / seg_len_sq))

        # Closest point on segment
        proj_x = p1[0] + t * seg_x
        proj_y = p1[1] + t * seg_y

        dist = math.sqrt((px - proj_x)**2 + (py - proj_y)**2)
        if dist < min_dist:
            min_dist = dist
            closest_point = (proj_x, proj_y)

    if closest_point is None:
        return None

    # Check if closest point is on the correct side
    # Vector from centerline point to closest boundary point
    to_boundary_x = closest_point[0] - px
    to_boundary_y = closest_point[1] - py

    # Dot product with perpendicular to determine side
    # In screen coords (Y-down), perp = (-ty, tx) points RIGHT of travel direction
    # positive dot = boundary is to the right, negative dot = boundary is to the left
    dot = perp[0] * to_boundary_x + perp[1] * to_boundary_y

    # For right lane (lane_id < 0), boundary should be on right (positive dot)
    # For left lane (lane_id > 0), boundary should be on left (negative dot)
    if (lane_id < 0 and dot < 0) or (lane_id > 0 and dot > 0):
        # Boundary is on wrong side
        return None

    return min_dist


def _get_perpendicular_at_point(
    points: List[Tuple[float, float]],
    index: int
) -> Optional[Tuple[float, float]]:
    """
    Get perpendicular unit vector at a point on the polyline.

    Returns vector pointing to the left of the direction of travel.
    """
    n = len(points)
    if n < 2:
        return None

    # Get tangent direction using adjacent points
    if index == 0:
        dx = points[1][0] - points[0][0]
        dy = points[1][1] - points[0][1]
    elif index == n - 1:
        dx = points[n-1][0] - points[n-2][0]
        dy = points[n-1][1] - points[n-2][1]
    else:
        # Average of forward and backward
        dx = points[index+1][0] - points[index-1][0]
        dy = points[index+1][1] - points[index-1][1]

    length = math.sqrt(dx*dx + dy*dy)
    if length < 1e-9:
        return None

    # Normalize and rotate 90° left
    tx = dx / length
    ty = dy / length
    return (-ty, tx)


def _ray_to_polyline_distance(
    origin: Tuple[float, float],
    direction: Tuple[float, float],
    polyline: List[Tuple[float, float]]
) -> Optional[float]:
    """
    Find distance from origin to polyline along ray direction.

    Casts a ray from origin in direction and finds intersection with polyline.

    Args:
        origin: Ray starting point (x, y)
        direction: Ray direction unit vector (dx, dy)
        polyline: Polyline to intersect [(x, y), ...]

    Returns:
        Distance to intersection, or None if no intersection
    """
    min_dist = None
    ox, oy = origin
    dx, dy = direction

    for i in range(len(polyline) - 1):
        p1 = polyline[i]
        p2 = polyline[i + 1]

        # Segment direction
        sx = p2[0] - p1[0]
        sy = p2[1] - p1[1]

        # Solve: origin + t*dir = p1 + u*seg
        # [dx -sx] [t]   [p1x - ox]
        # [dy -sy] [u] = [p1y - oy]
        denom = dx * (-sy) - dy * (-sx)
        if abs(denom) < 1e-12:
            continue  # Parallel

        bx = p1[0] - ox
        by = p1[1] - oy

        t = (bx * (-sy) - by * (-sx)) / denom
        u = (dx * by - dy * bx) / denom

        # Check if intersection is valid (t >= 0 for ray, 0 <= u <= 1 for segment)
        if t >= 0 and 0 <= u <= 1:
            if min_dist is None or t < min_dist:
                min_dist = t

    return min_dist


def evaluate_fit_quality(rmse: float) -> Tuple[str, str]:
    """
    Evaluate fitting quality based on RMSE.

    Args:
        rmse: Root mean square error in meters

    Returns:
        (quality_level, message) tuple
    """
    if rmse < 0.05:
        return "excellent", f"Excellent fit (RMSE: {rmse:.3f}m)"
    elif rmse < 0.2:
        return "good", f"Good fit (RMSE: {rmse:.2f}m)"
    elif rmse < 0.5:
        return "acceptable", f"Acceptable fit (RMSE: {rmse:.2f}m)"
    else:
        return "poor", f"Poor fit (RMSE: {rmse:.2f}m) - consider splitting into sections"

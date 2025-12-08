"""
Curve fitting for ORBIT.

Fits polylines to geometric primitives (lines, arcs, spirals) for OpenDrive export.
"""

import numpy as np
from typing import List, Tuple, Optional
from enum import Enum
from dataclasses import dataclass
from scipy.optimize import least_squares

from orbit.utils.logging_config import get_logger

logger = get_logger(__name__)


class GeometryType(Enum):
    """Types of geometry elements in OpenDrive."""
    LINE = "line"
    ARC = "arc"
    SPIRAL = "spiral"  # Clothoid (not fully implemented)
    PARAMPOLY3 = "paramPoly3"  # Parametric cubic polynomial


@dataclass
class GeometryElement:
    """
    Represents a geometry element for OpenDrive.

    Attributes:
        geom_type: Type of geometry (line, arc, spiral, paramPoly3)
        start_pos: Starting position (x, y) in meters
        heading: Starting heading in radians
        length: Length of the segment in meters
        curvature: Curvature (1/radius) for arcs, or starting curvature for spirals
        curvature_end: Ending curvature for spirals (None for lines and arcs)
        aU, bU, cU, dU: ParamPoly3 coefficients for u(p) polynomial
        aV, bV, cV, dV: ParamPoly3 coefficients for v(p) polynomial
        p_range: Parameter range for ParamPoly3 (typically 1.0)
        p_range_normalized: If True, pRange="normalized" (OpenDRIVE standard)
    """
    geom_type: GeometryType
    start_pos: Tuple[float, float]
    heading: float  # radians
    length: float  # meters
    curvature: float = 0.0  # 1/radius for arcs
    curvature_end: Optional[float] = None  # For spirals
    # ParamPoly3D coefficients (only used when geom_type is PARAMPOLY3)
    aU: float = 0.0
    bU: float = 0.0
    cU: float = 0.0
    dU: float = 0.0
    aV: float = 0.0
    bV: float = 0.0
    cV: float = 0.0
    dV: float = 0.0
    p_range: float = 1.0
    p_range_normalized: bool = True  # If True, use pRange="normalized" (OpenDRIVE standard)


class CurveFitter:
    """Fits polylines to geometric primitives."""

    def __init__(self, line_tolerance: float = 0.5, arc_tolerance: float = 1.0, preserve_geometry: bool = True):
        """
        Initialize curve fitter.

        Args:
            line_tolerance: Maximum deviation for line fitting (meters)
            arc_tolerance: Maximum deviation for arc fitting (meters)
            preserve_geometry: If True, create one line per polyline segment (preserves all points)
        """
        self.line_tolerance = line_tolerance
        self.arc_tolerance = arc_tolerance
        self.preserve_geometry = preserve_geometry

    def fit_polyline(self, points: List[Tuple[float, float]]) -> List[GeometryElement]:
        """
        Fit a polyline to a sequence of geometry elements.

        Args:
            points: List of (x, y) points in meters

        Returns:
            List of GeometryElement objects
        """
        if len(points) < 2:
            return []

        # If preserve_geometry is True, create one line per segment
        if self.preserve_geometry:
            return self._fit_preserve_points(points)

        # Otherwise use the curve fitting algorithm
        elements = []
        i = 0

        while i < len(points) - 1:
            # Try to fit as many points as possible to a line
            line_end = self._find_line_segment(points, i)

            if line_end > i + 1:
                # We have a line segment
                element = self._create_line_element(points, i, line_end)
                if element:  # Skip if zero-length
                    elements.append(element)
                i = line_end
            else:
                # Try to fit an arc
                arc_end = self._find_arc_segment(points, i)

                if arc_end > i + 2:
                    # We have an arc segment
                    element = self._create_arc_element(points, i, arc_end)
                    if element:
                        elements.append(element)
                        i = arc_end
                    else:
                        # Arc fitting failed, use line segment
                        element = self._create_line_element(points, i, i + 1)
                        if element:  # Skip if zero-length
                            elements.append(element)
                        i += 1
                else:
                    # Not enough points for arc, use line
                    element = self._create_line_element(points, i, i + 1)
                    if element:  # Skip if zero-length
                        elements.append(element)
                    i += 1

        return elements

    def _fit_preserve_points(self, points: List[Tuple[float, float]]) -> List[GeometryElement]:
        """
        Create one line element for each consecutive pair of points.
        This preserves the exact geometry of the original polyline.

        Args:
            points: List of (x, y) points in meters

        Returns:
            List of GeometryElement objects (one per polyline segment)
        """
        elements = []

        for i in range(len(points) - 1):
            p1 = np.array(points[i])
            p2 = np.array(points[i + 1])

            direction = p2 - p1
            length = np.linalg.norm(direction)

            # Skip zero-length segments
            if length < 1e-6:
                continue

            heading = np.arctan2(direction[1], direction[0])

            element = GeometryElement(
                geom_type=GeometryType.LINE,
                start_pos=(p1[0], p1[1]),
                heading=heading,
                length=length,
                curvature=0.0
            )
            elements.append(element)

        return elements

    def _find_line_segment(self, points: List[Tuple[float, float]], start: int) -> int:
        """
        Find the longest line segment starting from start index.

        Returns the end index (exclusive).
        """
        if start >= len(points) - 1:
            return start + 1

        # Start with at least 2 points
        end = start + 2

        while end <= len(points):
            segment = points[start:end]
            if not self._is_line(segment):
                return end - 1
            end += 1

        return len(points)

    def _is_line(self, points: List[Tuple[float, float]]) -> bool:
        """Check if points form a line within tolerance."""
        if len(points) < 2:
            return True

        # Fit a line using least squares
        points_array = np.array(points)
        x = points_array[:, 0]
        y = points_array[:, 1]

        # Handle vertical lines
        dx = x[-1] - x[0]
        dy = y[-1] - y[0]

        if abs(dx) < 1e-6:
            # Vertical line
            deviations = np.abs(x - x[0])
        elif abs(dy) < 1e-6:
            # Horizontal line
            deviations = np.abs(y - y[0])
        else:
            # General line: y = mx + b
            # Use distance to line formula
            line_vec = np.array([dx, dy])
            line_vec = line_vec / np.linalg.norm(line_vec)

            deviations = []
            for i in range(1, len(points) - 1):
                point_vec = points_array[i] - points_array[0]
                # Distance is the perpendicular component
                parallel = np.dot(point_vec, line_vec) * line_vec
                perpendicular = point_vec - parallel
                deviations.append(np.linalg.norm(perpendicular))

            deviations = np.array(deviations) if deviations else np.array([0])

        max_deviation = np.max(deviations) if len(deviations) > 0 else 0
        return max_deviation <= self.line_tolerance

    def _find_arc_segment(self, points: List[Tuple[float, float]], start: int) -> int:
        """
        Find the longest arc segment starting from start index.

        Returns the end index (exclusive).
        """
        if start >= len(points) - 2:
            return start + 1

        # Start with at least 3 points for an arc
        end = start + 3

        while end <= len(points):
            segment = points[start:end]
            if not self._is_arc(segment):
                return end - 1
            end += 1

        return len(points)

    def _is_arc(self, points: List[Tuple[float, float]]) -> bool:
        """Check if points form an arc within tolerance."""
        if len(points) < 3:
            return False

        # Fit a circle to the points
        circle = self._fit_circle(points)
        if circle is None:
            return False

        center, radius = circle

        # Check deviations from the circle
        deviations = []
        for point in points:
            dist = np.linalg.norm(np.array(point) - center)
            deviation = abs(dist - radius)
            deviations.append(deviation)

        max_deviation = max(deviations)
        return max_deviation <= self.arc_tolerance

    def _fit_circle(self, points: List[Tuple[float, float]]) -> Optional[Tuple[np.ndarray, float]]:
        """
        Fit a circle to points using least squares.

        Returns (center, radius) or None if fitting fails.
        """
        points_array = np.array(points)

        # Initial guess: center at mean, radius as average distance
        center_guess = np.mean(points_array, axis=0)
        radius_guess = np.mean([np.linalg.norm(p - center_guess) for p in points_array])

        def residuals(params):
            cx, cy, r = params
            center = np.array([cx, cy])
            distances = [np.linalg.norm(p - center) - r for p in points_array]
            return distances

        try:
            result = least_squares(
                residuals,
                [center_guess[0], center_guess[1], radius_guess],
                loss='soft_l1'
            )

            if result.success:
                cx, cy, r = result.x
                return np.array([cx, cy]), abs(r)
        except (ValueError, RuntimeError, np.linalg.LinAlgError) as e:
            logger.debug(f"Circle fitting failed: {e}")

        return None

    def _create_line_element(
        self,
        points: List[Tuple[float, float]],
        start: int,
        end: int
    ) -> Optional[GeometryElement]:
        """
        Create a line geometry element.

        Returns None if the resulting length would be zero or near-zero,
        as OpenDRIVE requires geometry length > 0.
        """
        p1 = np.array(points[start])
        p2 = np.array(points[min(end, len(points) - 1)])

        direction = p2 - p1
        length = np.linalg.norm(direction)

        # OpenDRIVE schema requires length > 0 (t_grZero type)
        if length < 1e-9:
            logger.debug(f"Skipping zero-length line segment at index {start}")
            return None

        heading = np.arctan2(direction[1], direction[0])

        return GeometryElement(
            geom_type=GeometryType.LINE,
            start_pos=(p1[0], p1[1]),
            heading=heading,
            length=length,
            curvature=0.0
        )

    def _create_arc_element(
        self,
        points: List[Tuple[float, float]],
        start: int,
        end: int
    ) -> Optional[GeometryElement]:
        """Create an arc geometry element."""
        segment = points[start:end + 1]
        circle = self._fit_circle(segment)

        if circle is None:
            return None

        center, radius = circle

        # Calculate start position and heading
        p_start = np.array(segment[0])
        p_end = np.array(segment[-1])

        # Heading at start (tangent to circle)
        to_center = center - p_start
        # Perpendicular to radius gives tangent
        # Need to determine direction (CW or CCW)
        tangent = np.array([-to_center[1], to_center[0]])

        # Check which direction matches the polyline
        direction_to_next = np.array(segment[1]) - p_start
        if np.dot(tangent, direction_to_next) < 0:
            tangent = -tangent

        tangent = tangent / np.linalg.norm(tangent)
        heading = np.arctan2(tangent[1], tangent[0])

        # Calculate arc length
        angle_start = np.arctan2(p_start[1] - center[1], p_start[0] - center[0])
        angle_end = np.arctan2(p_end[1] - center[1], p_end[0] - center[0])

        # Normalize angle difference
        angle_diff = angle_end - angle_start
        while angle_diff > np.pi:
            angle_diff -= 2 * np.pi
        while angle_diff < -np.pi:
            angle_diff += 2 * np.pi

        arc_length = abs(angle_diff * radius)

        # Curvature (positive for left turn, negative for right turn)
        curvature = 1.0 / radius if angle_diff > 0 else -1.0 / radius

        return GeometryElement(
            geom_type=GeometryType.ARC,
            start_pos=(p_start[0], p_start[1]),
            heading=heading,
            length=arc_length,
            curvature=curvature
        )


def simplify_polyline(points: List[Tuple[float, float]], tolerance: float = 1.0) -> List[Tuple[float, float]]:
    """
    Simplify a polyline using Douglas-Peucker algorithm.

    Args:
        points: List of (x, y) points
        tolerance: Maximum distance for point removal

    Returns:
        Simplified list of points
    """
    if len(points) < 3:
        return points

    def perpendicular_distance(point: Tuple[float, float], line_start: Tuple[float, float], line_end: Tuple[float, float]) -> float:
        """Calculate perpendicular distance from point to line."""
        p = np.array(point)
        p1 = np.array(line_start)
        p2 = np.array(line_end)

        line_vec = p2 - p1
        line_len = np.linalg.norm(line_vec)

        if line_len < 1e-6:
            return np.linalg.norm(p - p1)

        # Project point onto line
        t = max(0, min(1, np.dot(p - p1, line_vec) / (line_len ** 2)))
        projection = p1 + t * line_vec

        return np.linalg.norm(p - projection)

    def douglas_peucker(pts: List[Tuple[float, float]], tol: float) -> List[Tuple[float, float]]:
        """Recursive Douglas-Peucker algorithm."""
        if len(pts) < 3:
            return pts

        # Find point with maximum distance
        max_dist = 0
        max_index = 0

        for i in range(1, len(pts) - 1):
            dist = perpendicular_distance(pts[i], pts[0], pts[-1])
            if dist > max_dist:
                max_dist = dist
                max_index = i

        # If max distance is greater than tolerance, split
        if max_dist > tol:
            left = douglas_peucker(pts[:max_index + 1], tol)
            right = douglas_peucker(pts[max_index:], tol)
            return left[:-1] + right
        else:
            return [pts[0], pts[-1]]

    return douglas_peucker(points, tolerance)

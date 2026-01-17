"""
Curve fitting for ORBIT.

Fits polylines to geometric primitives (lines, arcs, spirals) for OpenDrive export.
Implements clothoid (Euler spiral) fitting using Fresnel integrals for G2-continuous
curves suitable for OpenDRIVE road geometry.
"""

import numpy as np
from typing import List, Tuple, Optional
from enum import Enum
from dataclasses import dataclass
from scipy.optimize import least_squares, minimize
from scipy.special import fresnel

from orbit.utils.logging_config import get_logger

logger = get_logger(__name__)


class GeometryType(Enum):
    """Types of geometry elements in OpenDrive."""
    LINE = "line"
    ARC = "arc"
    SPIRAL = "spiral"  # Clothoid/Euler spiral with Fresnel integrals
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

    def __init__(
        self,
        line_tolerance: float = 0.5,
        arc_tolerance: float = 1.0,
        spiral_tolerance: float = 0.5,
        preserve_geometry: bool = True,
        enable_spirals: bool = True
    ):
        """
        Initialize curve fitter.

        Args:
            line_tolerance: Maximum deviation for line fitting (meters)
            arc_tolerance: Maximum deviation for arc fitting (meters)
            spiral_tolerance: Maximum deviation for spiral fitting (meters)
            preserve_geometry: If True, create one line per polyline segment (preserves all points)
            enable_spirals: If True, attempt to fit clothoid spirals between arcs
        """
        self.line_tolerance = line_tolerance
        self.arc_tolerance = arc_tolerance
        self.spiral_tolerance = spiral_tolerance
        self.preserve_geometry = preserve_geometry
        self.enable_spirals = enable_spirals

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

        # Use spiral-enabled fitting if enabled
        if self.enable_spirals:
            return self.fit_polyline_with_spirals(points)

        # Otherwise use the line/arc only curve fitting algorithm
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

    # =========================================================================
    # Clothoid/Spiral Fitting
    # =========================================================================

    def _estimate_curvatures(
        self,
        points: List[Tuple[float, float]]
    ) -> Tuple[List[float], List[float]]:
        """
        Estimate curvature at each interior point of a polyline.

        Uses the circumscribed circle method: for each 3 consecutive points,
        compute the curvature of the circle passing through them.

        Args:
            points: List of (x, y) coordinates

        Returns:
            Tuple of (curvatures, s_values) where:
            - curvatures: List of signed curvature values (1/m), one per interior point
            - s_values: List of arc length positions for each curvature estimate
        """
        if len(points) < 3:
            return [], []

        curvatures = []
        s_values = []
        cumulative_s = 0.0

        for i in range(1, len(points) - 1):
            p0 = np.array(points[i - 1])
            p1 = np.array(points[i])
            p2 = np.array(points[i + 1])

            # Arc length to this point
            cumulative_s += np.linalg.norm(p1 - p0)
            s_values.append(cumulative_s)

            # Compute curvature using Menger curvature formula
            # κ = 4 * Area(triangle) / (|a| * |b| * |c|)
            # where a, b, c are the side lengths
            a = np.linalg.norm(p1 - p0)
            b = np.linalg.norm(p2 - p1)
            c = np.linalg.norm(p2 - p0)

            if a < 1e-9 or b < 1e-9 or c < 1e-9:
                curvatures.append(0.0)
                continue

            # Cross product gives signed area
            cross = (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p1[1] - p0[1]) * (p2[0] - p0[0])
            area = 0.5 * cross  # Signed area

            # Menger curvature (signed)
            denom = a * b * c
            if abs(denom) < 1e-12:
                curvatures.append(0.0)
            else:
                kappa = 4.0 * area / denom
                curvatures.append(kappa)

        return curvatures, s_values

    def _eval_clothoid(
        self,
        s: float,
        x0: float,
        y0: float,
        theta0: float,
        kappa0: float,
        kappa_rate: float
    ) -> Tuple[float, float, float]:
        """
        Evaluate clothoid (Euler spiral) at arc length s.

        A clothoid has linearly varying curvature: κ(s) = κ₀ + c·s
        where c = (κ₁ - κ₀) / L is the curvature rate.

        Uses Fresnel integrals for accurate computation.

        Args:
            s: Arc length position to evaluate
            x0, y0: Starting position
            theta0: Starting heading (radians)
            kappa0: Starting curvature (1/m)
            kappa_rate: Rate of curvature change (1/m²)

        Returns:
            Tuple of (x, y, theta) at position s
        """
        if abs(kappa_rate) < 1e-12:
            # Degenerate case: constant curvature (arc or line)
            if abs(kappa0) < 1e-12:
                # Straight line
                x = x0 + s * np.cos(theta0)
                y = y0 + s * np.sin(theta0)
                theta = theta0
            else:
                # Circular arc
                theta = theta0 + kappa0 * s
                x = x0 + (np.sin(theta) - np.sin(theta0)) / kappa0
                y = y0 - (np.cos(theta) - np.cos(theta0)) / kappa0
            return x, y, theta

        # General clothoid case using Fresnel integrals
        # θ(s) = θ₀ + κ₀·s + (c/2)·s²
        theta = theta0 + kappa0 * s + 0.5 * kappa_rate * s * s

        # For Fresnel integrals, we need to handle the general case:
        # x(s) = x₀ + ∫₀ˢ cos(θ(τ)) dτ
        # y(s) = y₀ + ∫₀ˢ sin(θ(τ)) dτ
        #
        # With θ(τ) = θ₀ + κ₀·τ + (c/2)·τ²
        # This can be expressed using Fresnel integrals after transformation

        # Use numerical integration for general case (more robust)
        # Trapezoidal rule with adaptive step size
        n_steps = max(10, int(abs(s) / 0.5) + 1)
        ds = s / n_steps

        x = x0
        y = y0
        theta_i = theta0

        for i in range(n_steps):
            s_i = i * ds
            theta_i = theta0 + kappa0 * s_i + 0.5 * kappa_rate * s_i * s_i
            x += np.cos(theta_i) * ds
            y += np.sin(theta_i) * ds

        return x, y, theta

    def _eval_clothoid_points(
        self,
        length: float,
        x0: float,
        y0: float,
        theta0: float,
        kappa0: float,
        kappa_end: float,
        n_samples: int = 20
    ) -> List[Tuple[float, float]]:
        """
        Generate sample points along a clothoid.

        Args:
            length: Total arc length
            x0, y0: Starting position
            theta0: Starting heading (radians)
            kappa0: Starting curvature
            kappa_end: Ending curvature
            n_samples: Number of sample points

        Returns:
            List of (x, y) points along the clothoid
        """
        if length < 1e-9:
            return [(x0, y0)]

        kappa_rate = (kappa_end - kappa0) / length
        points = []

        for i in range(n_samples + 1):
            s = (i / n_samples) * length
            x, y, _ = self._eval_clothoid(s, x0, y0, theta0, kappa0, kappa_rate)
            points.append((x, y))

        return points

    def _find_spiral_segment(
        self,
        points: List[Tuple[float, float]],
        start: int
    ) -> Tuple[int, float, float]:
        """
        Find the longest spiral segment starting from given index.

        Detects segments where curvature changes approximately linearly.
        Prefers longer segments over shorter ones to avoid fragmentation.

        Args:
            points: List of (x, y) coordinates
            start: Starting index

        Returns:
            Tuple of (end_index, kappa_start, kappa_end) or (start+1, 0, 0) if no spiral found
        """
        if start >= len(points) - 3:
            return start + 1, 0.0, 0.0

        # Need at least 5 points for meaningful spiral fitting (to avoid tiny segments)
        min_points = 5

        # Estimate curvatures for the remaining segment
        segment = points[start:]
        curvatures, s_values = self._estimate_curvatures(segment)

        if len(curvatures) < min_points - 2:
            return start + 1, 0.0, 0.0

        # Look for the LONGEST segment with linear curvature change
        # Start from the longest possible and work down
        best_end = start + 1
        best_kappa_start = 0.0
        best_kappa_end = 0.0
        best_score = -1.0  # Score combines length and R²

        for end_offset in range(len(curvatures) + 2, min_points - 1, -1):
            seg_curvatures = curvatures[:end_offset - 1]
            seg_s = s_values[:end_offset - 1]

            if len(seg_curvatures) < 3:
                continue

            # Fit linear regression to curvatures
            s_arr = np.array(seg_s)
            k_arr = np.array(seg_curvatures)

            # Linear regression: κ(s) = a + b*s
            s_mean = np.mean(s_arr)
            k_mean = np.mean(k_arr)

            ss_tot = np.sum((k_arr - k_mean) ** 2)
            if ss_tot < 1e-12:
                # Constant curvature - not a spiral
                continue

            ss_xy = np.sum((s_arr - s_mean) * (k_arr - k_mean))
            ss_xx = np.sum((s_arr - s_mean) ** 2)

            if ss_xx < 1e-12:
                continue

            b = ss_xy / ss_xx  # Slope (curvature rate)
            a = k_mean - b * s_mean  # Intercept

            # R² value
            k_pred = a + b * s_arr
            ss_res = np.sum((k_arr - k_pred) ** 2)
            r_squared = 1 - ss_res / ss_tot

            # Calculate start and end curvatures
            kappa_start = a  # at s=0
            kappa_end = a + b * seg_s[-1]

            # Only accept if:
            # - R² is good (linear curvature change)
            # - Curvature actually changes significantly
            # - Total curvature change is significant relative to segment length
            curvature_change = abs(kappa_end - kappa_start)
            min_curvature_change = 0.001  # 1/1000m minimum

            if r_squared > 0.80 and curvature_change > min_curvature_change:
                # Validate spiral fit against actual points
                segment_points = points[start:start + end_offset]
                if self._validate_spiral_fit(segment_points, kappa_start, kappa_end):
                    # Score: prefer longer segments with good R²
                    segment_length = seg_s[-1] if seg_s else 0
                    score = segment_length * r_squared

                    if score > best_score:
                        best_end = start + end_offset
                        best_kappa_start = kappa_start
                        best_kappa_end = kappa_end
                        best_score = score

        if best_score > 0:
            return best_end, best_kappa_start, best_kappa_end

        return start + 1, 0.0, 0.0

    def _validate_spiral_fit(
        self,
        points: List[Tuple[float, float]],
        kappa_start: float,
        kappa_end: float
    ) -> bool:
        """
        Validate that a spiral with given curvatures fits the points.

        Args:
            points: List of (x, y) coordinates
            kappa_start: Starting curvature
            kappa_end: Ending curvature

        Returns:
            True if the spiral fits within tolerance
        """
        if len(points) < 3:
            return False

        # Calculate arc length
        length = 0.0
        for i in range(1, len(points)):
            length += np.linalg.norm(
                np.array(points[i]) - np.array(points[i - 1])
            )

        if length < 1e-6:
            return False

        # Get start position and heading
        p0 = np.array(points[0])
        p1 = np.array(points[1])
        direction = p1 - p0
        theta0 = np.arctan2(direction[1], direction[0])

        # Generate spiral points
        spiral_points = self._eval_clothoid_points(
            length, p0[0], p0[1], theta0, kappa_start, kappa_end,
            n_samples=len(points) - 1
        )

        # Check deviation at each point
        max_deviation = 0.0
        for i, (px, py) in enumerate(points):
            # Find closest spiral point
            min_dist = float('inf')
            for sx, sy in spiral_points:
                dist = np.sqrt((px - sx) ** 2 + (py - sy) ** 2)
                min_dist = min(min_dist, dist)
            max_deviation = max(max_deviation, min_dist)

        return max_deviation <= self.spiral_tolerance

    def _fit_spiral(
        self,
        points: List[Tuple[float, float]],
        kappa_start: float,
        kappa_end: float
    ) -> Optional[Tuple[float, float, float, float, float, float]]:
        """
        Fit a spiral to the given points with initial curvature estimates.

        Uses optimization to refine the fit.

        Args:
            points: List of (x, y) coordinates
            kappa_start: Initial estimate of starting curvature
            kappa_end: Initial estimate of ending curvature

        Returns:
            Tuple of (x0, y0, theta0, length, kappa_start, kappa_end) or None if fitting fails
        """
        if len(points) < 3:
            return None

        # Calculate arc length
        length = 0.0
        for i in range(1, len(points)):
            length += np.linalg.norm(
                np.array(points[i]) - np.array(points[i - 1])
            )

        if length < 1e-6:
            return None

        # Start position and initial heading
        p0 = np.array(points[0])
        p1 = np.array(points[1])
        direction = p1 - p0
        theta0 = np.arctan2(direction[1], direction[0])

        # Optimize curvatures for best fit
        def objective(params):
            k0, k1 = params
            total_error = 0.0

            # Generate spiral points
            spiral_pts = self._eval_clothoid_points(
                length, p0[0], p0[1], theta0, k0, k1,
                n_samples=len(points) - 1
            )

            # Sum of squared distances
            for i, (px, py) in enumerate(points):
                if i < len(spiral_pts):
                    sx, sy = spiral_pts[i]
                    total_error += (px - sx) ** 2 + (py - sy) ** 2

            return total_error

        try:
            result = minimize(
                objective,
                [kappa_start, kappa_end],
                method='Nelder-Mead',
                options={'xatol': 1e-8, 'fatol': 1e-8, 'maxiter': 200}
            )

            if result.success or result.fun < self.spiral_tolerance ** 2 * len(points):
                return (p0[0], p0[1], theta0, length, result.x[0], result.x[1])

        except Exception as e:
            logger.debug(f"Spiral optimization failed: {e}")

        # Fall back to initial estimates if optimization fails
        return (p0[0], p0[1], theta0, length, kappa_start, kappa_end)

    def _create_spiral_element(
        self,
        points: List[Tuple[float, float]],
        start: int,
        end: int,
        kappa_start: float,
        kappa_end: float
    ) -> Optional[GeometryElement]:
        """
        Create a spiral geometry element.

        Args:
            points: List of (x, y) coordinates
            start: Starting index
            end: Ending index (exclusive)
            kappa_start: Starting curvature
            kappa_end: Ending curvature

        Returns:
            GeometryElement with spiral geometry or None if fitting fails
        """
        segment = points[start:end]
        if len(segment) < 3:
            return None

        fit_result = self._fit_spiral(segment, kappa_start, kappa_end)
        if fit_result is None:
            return None

        x0, y0, theta0, length, k0, k1 = fit_result

        # OpenDRIVE requires curvStart and curvEnd
        return GeometryElement(
            geom_type=GeometryType.SPIRAL,
            start_pos=(x0, y0),
            heading=theta0,
            length=length,
            curvature=k0,  # curvStart
            curvature_end=k1  # curvEnd
        )

    def fit_polyline_with_spirals(
        self,
        points: List[Tuple[float, float]]
    ) -> List[GeometryElement]:
        """
        Fit a polyline using lines, arcs, and spirals.

        This method attempts to find spiral segments where curvature changes
        linearly, providing G2-continuous (curvature-continuous) geometry.

        Args:
            points: List of (x, y) points in meters

        Returns:
            List of GeometryElement objects
        """
        if len(points) < 2:
            return []

        elements = []
        i = 0

        while i < len(points) - 1:
            # Try spiral first (most complex, catches curvature transitions)
            if self.enable_spirals and i < len(points) - 4:
                spiral_end, k_start, k_end = self._find_spiral_segment(points, i)

                if spiral_end > i + 4 and abs(k_end - k_start) > 1e-6:
                    # We found a valid spiral segment
                    element = self._create_spiral_element(
                        points, i, spiral_end, k_start, k_end
                    )
                    if element:
                        elements.append(element)
                        i = spiral_end - 1  # -1 because we want overlap at endpoints
                        continue

            # Try to find a long line segment first
            line_end = self._find_line_segment(points, i)
            line_length = line_end - i

            # Try to find an arc segment
            arc_end = self._find_arc_segment(points, i) if i < len(points) - 2 else i + 1
            arc_length = arc_end - i

            # Choose the longer fit (prefer line when equal - simpler is better)
            if arc_length > 2 and arc_length > line_length:
                # Arc covers more points - use it
                element = self._create_arc_element(points, i, arc_end)
                if element:
                    elements.append(element)
                    i = arc_end
                    continue
                # Arc creation failed, fall through to line

            if line_length > 1:
                element = self._create_line_element(points, i, line_end)
                if element:
                    elements.append(element)
                i = line_end
                continue

            # Fallback: single line segment
            element = self._create_line_element(points, i, i + 1)
            if element:
                elements.append(element)
            i += 1

        return elements


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

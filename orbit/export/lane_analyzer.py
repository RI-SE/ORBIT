"""
Lane boundary analysis for ORBIT.

Calculates lateral offsets, matches boundaries to lanes, and suggests lane widths.
"""

from typing import List, Tuple, Optional, Dict
import numpy as np
from dataclasses import dataclass
import math

from orbit.utils.logging_config import get_logger
from orbit.utils.geometry import calculate_directional_scale
from orbit.models import Road, Polyline, Project, LineType

logger = get_logger(__name__)


@dataclass
class BoundaryInfo:
    """Information about a lane boundary relative to centerline."""
    polyline_id: str
    polyline: Polyline
    avg_offset: float  # Average lateral offset from centerline (signed)
    std_offset: float  # Standard deviation of offset
    lane_id: Optional[int] = None  # Assigned lane ID (None if unassigned)
    measured_width: Optional[float] = None  # Width to next boundary


class LaneAnalyzer:
    """Analyzes lane boundaries relative to centerline."""

    def __init__(self, project: Project, right_hand_traffic: bool = True,
                 scale_factors: Optional[Tuple[float, float]] = None,
                 transformer=None):
        """
        Initialize lane analyzer.

        Args:
            project: The ORBIT project
            right_hand_traffic: True for right-hand traffic (default), False for left-hand
            scale_factors: Optional tuple of (scale_x, scale_y) in meters/pixel for unit conversion
            transformer: Optional CoordinateTransformer for accurate pixel->meter conversions (better for homography)
        """
        self.project = project
        self.right_hand_traffic = right_hand_traffic
        self.scale_factors = scale_factors
        self.transformer = transformer
        self.polyline_map = {p.id: p for p in project.polylines}

    def analyze_road(self, road: Road, verbose: bool = False) -> Tuple[List[BoundaryInfo], Optional[str]]:
        """
        Analyze lane boundaries for a road.

        Args:
            road: The road to analyze
            verbose: If True, print detailed debug information

        Returns:
            Tuple of (list of boundary info, warning message or None)
        """
        # Get centerline
        if not road.centerline_id or road.centerline_id not in self.polyline_map:
            return [], "No centerline found"

        centerline = self.polyline_map[road.centerline_id]

        if centerline.point_count() < 2:
            return [], "Centerline has too few points"

        # Get all lane boundaries
        boundaries = []
        for polyline_id in road.polyline_ids:
            polyline = self.polyline_map.get(polyline_id)
            if polyline and polyline.line_type == LineType.LANE_BOUNDARY:
                boundaries.append(polyline)

        if not boundaries:
            return [], "No lane boundaries found"

        if verbose:
            logger.debug(f"  Analyzing {len(boundaries)} lane boundaries for road {road.name}")
            logger.debug(f"  Centerline: {len(centerline.points)} points")

        # Calculate offsets for each boundary
        boundary_infos = []
        for boundary in boundaries:
            offsets = self._calculate_lateral_offsets(boundary, centerline, verbose=verbose)
            if offsets:
                avg_offset = np.mean(offsets)
                std_offset = np.std(offsets)

                if verbose:
                    logger.debug(f"    Boundary {boundary.id[:8]}: avg_offset={avg_offset:.2f} px, std={std_offset:.2f} px")

                boundary_info = BoundaryInfo(
                    polyline_id=boundary.id,
                    polyline=boundary,
                    avg_offset=avg_offset,
                    std_offset=std_offset
                )
                boundary_infos.append(boundary_info)

        if not boundary_infos:
            return [], "Could not calculate offsets for boundaries"

        # Sort boundaries by offset
        boundary_infos.sort(key=lambda x: x.avg_offset)

        # Assign boundaries to lanes
        self._assign_boundaries_to_lanes(boundary_infos, road)

        # Calculate widths between consecutive boundaries
        self._calculate_boundary_widths(boundary_infos)

        # Generate warning if needed
        warning = self._validate_boundary_assignment(boundary_infos, road)

        return boundary_infos, warning

    def _calculate_lateral_offsets(
        self,
        boundary: Polyline,
        centerline: Polyline,
        verbose: bool = False
    ) -> List[float]:
        """
        Calculate lateral offsets from boundary to centerline.

        Returns list of signed offsets (positive = left, negative = right for right-hand traffic).
        """
        offsets = []
        centerline_points = np.array(centerline.points)

        if verbose:
            logger.debug(f"Calculating offsets for boundary {boundary.id[:8]}...")
            logger.debug(f"    Centerline has {len(centerline_points)} points")
            logger.debug(f"    Boundary has {len(boundary.points)} points")

        for idx, boundary_point in enumerate(boundary.points):
            # Find nearest segment on centerline (using actual segment distance, not infinite line)
            min_dist = float('inf')
            signed_offset = 0.0
            best_segment = None

            for i in range(len(centerline_points) - 1):
                p1 = centerline_points[i]
                p2 = centerline_points[i + 1]

                # Calculate actual distance to segment and signed offset
                dist, offset = self._point_to_segment_distance_and_offset(boundary_point, p1, p2)

                if dist < min_dist:
                    min_dist = dist
                    signed_offset = offset
                    best_segment = (i, p1, p2)

            offsets.append(signed_offset)

            if verbose and idx < 3:  # Show first 3 points for debugging
                logger.debug(f"      Point {idx}: boundary=({boundary_point[0]:.1f}, {boundary_point[1]:.1f})")
                if best_segment:
                    seg_idx, seg_p1, seg_p2 = best_segment
                    logger.debug(f"        Nearest centerline segment {seg_idx}: ({seg_p1[0]:.1f},{seg_p1[1]:.1f}) to ({seg_p2[0]:.1f},{seg_p2[1]:.1f})")
                    logger.debug(f"        Calculated offset: {signed_offset:.2f} px (actual dist={min_dist:.2f} px)")

        return offsets

    def _point_to_segment_distance_and_offset(
        self,
        point: Tuple[float, float],
        seg_start: np.ndarray,
        seg_end: np.ndarray
    ) -> Tuple[float, float]:
        """
        Calculate distance and signed offset from point to line segment.

        Returns:
            Tuple of (distance, signed_offset)
            - distance: actual distance from point to segment (considering endpoints)
            - signed_offset: perpendicular offset (positive=left, negative=right)
        """
        px, py = point
        x1, y1 = seg_start
        x2, y2 = seg_end

        # Vector along segment
        dx = x2 - x1
        dy = y2 - y1

        # Vector from segment start to point
        dpx = px - x1
        dpy = py - y1

        # Segment length squared
        seg_length_sq = dx * dx + dy * dy
        if seg_length_sq < 1e-6:
            # Degenerate segment - just return distance to point
            dist = np.sqrt(dpx * dpx + dpy * dpy)
            return dist, 0.0

        # Project point onto line (parameter t along segment)
        # t=0 means at seg_start, t=1 means at seg_end
        t = (dpx * dx + dpy * dy) / seg_length_sq

        # Clamp t to [0, 1] to stay within segment
        t_clamped = max(0.0, min(1.0, t))

        # Find closest point on segment
        closest_x = x1 + t_clamped * dx
        closest_y = y1 + t_clamped * dy

        # Distance from point to closest point on segment
        dist_x = px - closest_x
        dist_y = py - closest_y
        distance = np.sqrt(dist_x * dist_x + dist_y * dist_y)

        # Calculate signed perpendicular offset
        # Cross product to determine side
        cross = dx * dpy - dy * dpx
        seg_length = np.sqrt(seg_length_sq)
        signed_offset = cross / seg_length

        # Flip sign for left-hand traffic
        if not self.right_hand_traffic:
            signed_offset = -signed_offset

        return distance, signed_offset

    def _point_to_segment_offset(
        self,
        point: Tuple[float, float],
        seg_start: np.ndarray,
        seg_end: np.ndarray
    ) -> float:
        """
        Calculate signed perpendicular offset from point to line segment.

        Positive = left side of segment (in direction of travel)
        Negative = right side of segment
        """
        _, offset = self._point_to_segment_distance_and_offset(point, seg_start, seg_end)
        return offset

    def _assign_boundaries_to_lanes(
        self,
        boundary_infos: List[BoundaryInfo],
        road: Road
    ) -> None:
        """
        Assign boundaries to lane IDs based on their offset.

        Modifies boundary_infos in place.
        """
        # Expected lane width
        lane_width = road.lane_info.lane_width

        # Separate left and right boundaries
        left_boundaries = [b for b in boundary_infos if b.avg_offset > 0.1]
        right_boundaries = [b for b in boundary_infos if b.avg_offset < -0.1]

        # Sort by distance from centerline
        left_boundaries.sort(key=lambda x: x.avg_offset)  # Closest to farthest
        right_boundaries.sort(key=lambda x: -x.avg_offset)  # Closest to farthest

        # Assign left lane boundaries
        # Left lanes: 1, 2, 3, ... (outermost to innermost)
        # Boundaries are numbered from innermost to outermost
        for i, boundary_info in enumerate(left_boundaries):
            # Lane 1 is closest to centerline on left
            # Expected positions: lane_width/2, 1.5*lane_width, 2.5*lane_width, ...
            lane_id = i + 1
            boundary_info.lane_id = lane_id

        # Assign right lane boundaries
        # Right lanes: -1, -2, -3, ... (outermost to innermost)
        for i, boundary_info in enumerate(right_boundaries):
            lane_id = -(i + 1)
            boundary_info.lane_id = lane_id

    def _calculate_boundary_widths(self, boundary_infos: List[BoundaryInfo]) -> None:
        """
        Calculate width between consecutive boundaries.

        Modifies boundary_infos in place.
        """
        # Process left side
        left_boundaries = [b for b in boundary_infos if b.avg_offset > 0]
        left_boundaries.sort(key=lambda x: x.avg_offset)

        for i in range(len(left_boundaries) - 1):
            width = left_boundaries[i + 1].avg_offset - left_boundaries[i].avg_offset
            left_boundaries[i].measured_width = width

        # Process right side
        right_boundaries = [b for b in boundary_infos if b.avg_offset < 0]
        right_boundaries.sort(key=lambda x: -x.avg_offset)

        for i in range(len(right_boundaries) - 1):
            width = abs(right_boundaries[i + 1].avg_offset - right_boundaries[i].avg_offset)
            right_boundaries[i].measured_width = width

        # Handle boundaries without measured widths
        # For single boundaries on each side, measure from centerline to boundary (lane width)
        # For multiple boundaries on same side, outer boundaries already have widths from previous loop
        if left_boundaries and right_boundaries:
            # For single boundary on each side (most common case)
            if len(left_boundaries) == 1 and len(right_boundaries) == 1:
                # Each boundary represents the outer edge of a single lane
                # Lane width = distance from centerline to boundary
                left_boundaries[0].measured_width = abs(left_boundaries[0].avg_offset)
                right_boundaries[0].measured_width = abs(right_boundaries[0].avg_offset)
            else:
                # Multiple boundaries on at least one side
                # Handle innermost boundaries (closest to centerline)
                innermost_left = min(left_boundaries, key=lambda x: x.avg_offset)
                innermost_right = max(right_boundaries, key=lambda x: x.avg_offset)

                # For innermost boundaries without width, measure from centerline
                if innermost_left.measured_width is None:
                    innermost_left.measured_width = abs(innermost_left.avg_offset)
                if innermost_right.measured_width is None:
                    innermost_right.measured_width = abs(innermost_right.avg_offset)

                # Handle outermost boundaries that might not have widths
                # (they don't have outer neighbors on their side)
                if len(left_boundaries) > 1:
                    outermost_left = max(left_boundaries, key=lambda x: x.avg_offset)
                    if outermost_left.measured_width is None and outermost_left != innermost_left:
                        # Measure to innermost left as fallback
                        outermost_left.measured_width = outermost_left.avg_offset - innermost_left.avg_offset

                if len(right_boundaries) > 1:
                    outermost_right = min(right_boundaries, key=lambda x: x.avg_offset)
                    if outermost_right.measured_width is None and outermost_right != innermost_right:
                        # Measure to innermost right as fallback
                        outermost_right.measured_width = abs(outermost_right.avg_offset - innermost_right.avg_offset)

    def _validate_boundary_assignment(
        self,
        boundary_infos: List[BoundaryInfo],
        road: Road
    ) -> Optional[str]:
        """
        Validate boundary assignment and return warning if issues found.
        """
        left_count = len([b for b in boundary_infos if b.avg_offset > 0])
        right_count = len([b for b in boundary_infos if b.avg_offset < 0])

        warnings = []

        # Check if boundary count matches lane count
        expected_left = road.lane_info.left_count
        expected_right = road.lane_info.right_count

        if left_count != expected_left:
            warnings.append(
                f"Expected {expected_left} left boundaries, found {left_count}"
            )

        if right_count != expected_right:
            warnings.append(
                f"Expected {expected_right} right boundaries, found {right_count}"
            )

        # Check for high offset variation
        for boundary_info in boundary_infos:
            if boundary_info.std_offset > boundary_info.avg_offset * 0.3:
                warnings.append(
                    f"Boundary {boundary_info.polyline_id[:8]} has high variation "
                    f"(may not be parallel to centerline)"
                )

        return " | ".join(warnings) if warnings else None

    def _get_directional_scale(self, centerline: Polyline) -> float:
        """
        Get appropriate scale factor based on road direction.

        Args:
            centerline: The road's centerline polyline

        Returns:
            Scale factor in meters per pixel, or 1.0 if no scale available
        """
        if not self.scale_factors:
            # No georeferencing available - return 1.0 as placeholder
            # This means widths will be in pixels, not meters
            return 1.0

        scale_x, scale_y = self.scale_factors
        return calculate_directional_scale(
            centerline.points, scale_x, scale_y,
            default_scale=(scale_x + scale_y) / 2
        )

    def suggest_lane_widths(self, road: Road, verbose: bool = False) -> Optional[Dict[str, float]]:
        """
        Suggest lane widths based on measured boundaries.

        Args:
            road: The road to analyze
            verbose: If True, print detailed calculation information

        Returns:
            Dictionary with 'average', 'min', 'max' measured widths in meters, or None if no data
        """
        boundary_infos, _ = self.analyze_road(road, verbose=verbose)

        if not boundary_infos:
            if verbose:
                logger.debug(f"LANE WIDTH MEASUREMENT: {road.name}")
                logger.debug("  No boundary infos found")
            return None

        # Collect all measured widths (currently in pixels)
        widths_px = [b.measured_width for b in boundary_infos if b.measured_width is not None]

        if not widths_px:
            if verbose:
                logger.debug(f"LANE WIDTH MEASUREMENT: {road.name}")
                logger.debug("  No widths calculated from boundaries")
            return None

        # Convert pixel widths to meters using directional scale
        centerline = self.polyline_map.get(road.centerline_id)
        if not centerline:
            if verbose:
                logger.debug(f"LANE WIDTH MEASUREMENT: {road.name}")
                logger.debug("  No centerline found")
            return None

        scale = self._get_directional_scale(centerline)

        if verbose:
            logger.debug(f"{'='*60}")
            logger.debug(f"LANE WIDTH MEASUREMENT: {road.name} (ID: {road.id[:8]}...)")
            logger.debug(f"{'='*60}")
            logger.debug(f"  Boundary analysis:")
            logger.debug(f"    Found {len(boundary_infos)} boundaries")
            logger.debug(f"    {len(widths_px)} have measured widths")

            # Show individual boundary info
            for i, info in enumerate(boundary_infos):
                side = "left" if info.avg_offset > 0 else "right"
                logger.debug(f"    Boundary {i+1} ({side}):")
                logger.debug(f"      Average offset: {info.avg_offset:.2f} px")
                if info.measured_width is not None:
                    logger.debug(f"      Measured width: {info.measured_width:.2f} px")

            logger.debug(f"  Scale calculation:")
            if self.scale_factors:
                scale_x, scale_y = self.scale_factors
                logger.debug(f"    Scale X (horizontal): {scale_x:.6f} m/px = {scale_x*100:.4f} cm/px")
                logger.debug(f"    Scale Y (vertical):   {scale_y:.6f} m/px = {scale_y*100:.4f} cm/px")
                logger.debug(f"    Directional scale:    {scale:.6f} m/px = {scale*100:.4f} cm/px")
            else:
                logger.debug(f"    No georeferencing - scale: {scale:.6f} (placeholder)")

            logger.debug(f"  Width measurements:")
            logger.debug(f"    In pixels:")
            for i, w_px in enumerate(widths_px):
                logger.debug(f"      Width {i+1}: {w_px:.2f} px")

        # Convert from pixels to meters
        # Use transformer if available for more accurate conversion (especially for homography)
        if self.transformer and hasattr(self.transformer, 'pixel_to_meters'):
            # For each boundary, calculate width using transformer
            # This accounts for perspective distortion in homography
            widths_m = []
            for info in boundary_infos:
                if info.measured_width is not None:
                    # Get a representative point on the centerline for this boundary
                    # Use middle point of centerline for approximation
                    mid_idx = len(centerline.points) // 2
                    cx, cy = centerline.points[mid_idx]

                    # Calculate perpendicular points at width distance
                    # This is still an approximation but better than scale factor
                    width_px = info.measured_width

                    # Transform centerline point and a point at distance width_px
                    mx1, my1 = self.transformer.pixel_to_meters(cx, cy)
                    mx2, my2 = self.transformer.pixel_to_meters(cx + width_px, cy)

                    # Calculate distance in meter space
                    width_m = math.sqrt((mx2 - mx1)**2 + (my2 - my1)**2)
                    widths_m.append(width_m)

            if verbose and widths_m:
                logger.debug(f"    In meters (using transformer for accurate conversion):")
                for i, w_m in enumerate(widths_m):
                    logger.debug(f"      Width {i+1}: {w_m:.3f} m (perspective-corrected)")
        else:
            # Fallback to scale factor method
            widths_m = [w * scale for w in widths_px]

            if verbose:
                logger.debug(f"    In meters (using scale factor approximation):")
                for i, w_m in enumerate(widths_m):
                    logger.debug(f"      Width {i+1}: {w_m:.3f} m = {widths_px[i]:.2f} px × {scale:.6f} m/px")
                logger.debug(f"  Summary:")
                logger.debug(f"    Average: {np.mean(widths_m):.3f} m")
                logger.debug(f"    Min:     {np.min(widths_m):.3f} m")
                logger.debug(f"    Max:     {np.max(widths_m):.3f} m")
                logger.debug(f"    Std Dev: {np.std(widths_m):.3f} m")
                logger.debug(f"{'='*60}")

        return {
            'average': float(np.mean(widths_m)),
            'min': float(np.min(widths_m)),
            'max': float(np.max(widths_m)),
            'std': float(np.std(widths_m))
        }

"""
Lane graphics items for ORBIT.

Provides visual representation of lanes on the image view.
"""

from typing import List, Optional, Tuple

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QBrush, QColor, QPen, QPolygonF
from PyQt6.QtWidgets import QGraphicsScene

from orbit.gui.constants import DEFAULT_SCALE_M_PER_PX
from orbit.models import BoundaryMode, Polyline, Road
from orbit.utils.geometry import (
    calculate_directional_scale,
    calculate_offset_polyline,
    create_lane_polygon,
    create_polygon_from_boundaries,
    create_polynomial_width_lane_polygon,
    create_variable_width_lane_polygon,
)
from orbit.utils.logging_config import get_logger

from .interactive_lane import InteractiveLanePolygon

logger = get_logger(__name__)


class LaneGraphicsItem:
    """Graphics representation of a single lane (deprecated, kept for compatibility)."""

    def __init__(self, lane_number: int, polygon_points: List[tuple],
                 scene: QGraphicsScene) -> None:
        """
        Create a lane graphics item.

        Args:
            lane_number: Lane ID (positive=right, negative=left, 0=center)
            polygon_points: List of (x, y) points forming the lane polygon
            scene: Graphics scene to add items to
        """
        self.lane_number = lane_number
        self.polygon_points = polygon_points
        self.scene = scene
        self.polygon_item = None

        self.update_graphics()

    def update_graphics(self) -> None:
        """Update the graphics items based on lane data."""
        # Remove existing polygon
        if self.polygon_item:
            self.scene.removeItem(self.polygon_item)
            self.polygon_item = None

        if not self.polygon_points or len(self.polygon_points) < 3:
            return

        # Create polygon
        polygon = QPolygonF()
        for x, y in self.polygon_points:
            polygon.append(QPointF(x, y))

        # Choose color based on lane side (OpenDRIVE convention)
        if self.lane_number < 0:
            # Right lanes (negative IDs in OpenDRIVE): light green
            color = QColor(100, 255, 100, 77)  # ~30% alpha
        elif self.lane_number > 0:
            # Left lanes (positive IDs in OpenDRIVE): light blue
            color = QColor(100, 180, 255, 77)  # ~30% alpha
        else:
            # Center lane (ID = 0)
            color = QColor(200, 200, 200, 77)

        # Create pen for lane divider
        pen = QPen(QColor(200, 200, 200, 150), 1)  # Thin light gray
        brush = QBrush(color)

        # Add polygon to scene
        self.polygon_item = self.scene.addPolygon(polygon, pen, brush)
        self.polygon_item.setZValue(0.5)  # Between image (0) and polylines (1+)

    def remove(self) -> None:
        """Remove graphics item from scene."""
        if self.polygon_item and self.polygon_item.scene() == self.scene:
            self.scene.removeItem(self.polygon_item)
            self.polygon_item = None

    def set_visible(self, visible: bool) -> None:
        """Set visibility of lane graphics."""
        if self.polygon_item:
            self.polygon_item.setVisible(visible)


class RoadLanesGraphicsItem:
    """Graphics representation of all lanes in a road."""

    DEFAULT_SCALE = DEFAULT_SCALE_M_PER_PX

    def __init__(self, road: Road, centerline: Polyline, scene: QGraphicsScene,
                 scale_factors: Optional[tuple] = None, verbose: bool = False,
                 project=None) -> None:
        """
        Create road lanes graphics.

        Args:
            road: Road object with lane configuration
            centerline: Centerline polyline
            scene: Graphics scene
            scale_factors: Tuple of (scale_x, scale_y) in m/px, or None for default
            verbose: Enable verbose debug output
            project: Project object (for looking up boundary polylines)
        """
        self.road = road
        self.centerline = centerline
        self.scene = scene
        self.scale_factors = scale_factors  # Store as tuple
        self.lane_items: List = []
        self.verbose = verbose
        self.project = project

        self.update_graphics()

    def _get_directional_scale(self) -> float:
        """
        Get the appropriate scale factor based on road direction.

        For roads running primarily horizontal (east-west), use scale_x.
        For roads running primarily vertical (north-south), use scale_y.
        For diagonal roads, interpolate between scale_x and scale_y.

        Returns:
            Scale factor in meters per pixel appropriate for this road's direction
        """
        # Use default scale if no georeferencing available
        if not self.scale_factors:
            return self.DEFAULT_SCALE

        scale_x, scale_y = self.scale_factors
        return calculate_directional_scale(
            self.centerline.points, scale_x, scale_y,
            default_scale=self.DEFAULT_SCALE
        )

    def update_graphics(self) -> None:
        """Update all lane graphics based on current road configuration."""
        # Remove existing lanes
        for lane_item in self.lane_items:
            if hasattr(lane_item, 'remove'):
                lane_item.remove()
            elif hasattr(lane_item, 'scene') and lane_item.scene() == self.scene:
                self.scene.removeItem(lane_item)
        self.lane_items.clear()

        if not self.centerline or self.centerline.point_count() < 2:
            return

        # Get centerline points
        centerline_points = self.centerline.points

        # Calculate directional scale
        scale = self._get_directional_scale()

        # Verbose output for debugging
        if self.verbose:
            logger.debug("LANE VISUALIZATION: %s (ID: %s...)", self.road.name, self.road.id[:8])

        # Use lane sections if available, otherwise fall back to old method
        if self.road.lane_sections:
            self._create_section_based_lanes(centerline_points, scale)
        else:
            self._create_legacy_lanes(centerline_points, scale)

    def _create_section_based_lanes(self, centerline_points: List[Tuple[float, float]], scale: float) -> None:
        """Create lane polygons separated by section boundaries."""
        # Calculate s-coordinates for all centerline points
        s_coords = self.road.calculate_centerline_s_coordinates(centerline_points)

        # Update last section's s_end to match actual centerline length
        if self.road.lane_sections and s_coords:
            self.road.lane_sections[-1].s_end = s_coords[-1]

        if self.verbose:
            logger.debug("  Creating section-based lane polygons:")
            logger.debug("    Sections: %d", len(self.road.lane_sections))

        # For each section, create polygons for each lane
        for section_idx, section in enumerate(self.road.lane_sections):
            # Find points belonging to this section
            section_point_indices = []
            is_last_section = (section_idx == len(self.road.lane_sections) - 1)

            for i, s in enumerate(s_coords):
                if is_last_section:
                    # For last section, include all points from s_start onwards
                    if s >= section.s_start:
                        section_point_indices.append(i)
                else:
                    # For other sections, use closed interval [s_start, s_end] to avoid gaps
                    if section.s_start <= s <= section.s_end:
                        section_point_indices.append(i)

            if len(section_point_indices) < 2:
                continue  # Need at least 2 points

            # Extract section centerline points
            section_centerline = [centerline_points[i] for i in section_point_indices]

            if self.verbose:
                logger.debug(
                    "    Section %d: %d points, %d lanes",
                    section.section_number, len(section_centerline), len(section.lanes)
                )

            # Calculate section s-coordinates for polynomial width evaluation
            section_s_values = [s_coords[i] - section.s_start for i in section_point_indices]
            section_length_px = section.s_end - section.s_start
            section_length_m = section_length_px * scale  # Convert to meters for polynomial

            sorted_lanes = sorted(section.lanes, key=lambda lane: abs(lane.id))

            for lane in sorted_lanes:
                if lane.id == 0:
                    continue
                polygon_points = self._compute_lane_polygon(
                    lane, sorted_lanes, section_centerline, section_s_values,
                    section_length_m, scale
                )
                if polygon_points and len(polygon_points) >= 3:
                    self._add_lane_scene_item(
                        lane.id, section.section_number, polygon_points
                    )

    @staticmethod
    def _is_inner_lane(lane_id: int, other_id: int) -> bool:
        """Check if other_id is an inner lane relative to lane_id (closer to center)."""
        if other_id == 0:
            return False
        if lane_id > 0:
            return other_id > 0 and other_id < lane_id
        return other_id < 0 and abs(other_id) < abs(lane_id)

    def _cumulative_inner_offset(self, lane, sorted_lanes, scale):
        """Calculate cumulative pixel offset of all lanes inner to this one."""
        total = 0.0
        for inner_lane in sorted_lanes:
            if self._is_inner_lane(lane.id, inner_lane.id):
                total += inner_lane.width / scale
        return total

    def _compute_lane_polygon(
        self, lane, sorted_lanes, section_centerline, section_s_values,
        section_length_m, scale
    ):
        """Compute polygon points for a single lane using the appropriate width mode."""
        polygon_points = None

        # Option 1: Explicit outer boundary polyline
        if lane.boundary_mode == BoundaryMode.EXPLICIT and self.project is not None:
            polygon_points = self._compute_explicit_boundary_polygon(
                lane, sorted_lanes, section_centerline, scale
            )

        # Option 2: Computed width (polynomial / variable / constant)
        if polygon_points is None:
            polygon_points = self._compute_width_based_polygon(
                lane, sorted_lanes, section_centerline, section_s_values,
                section_length_m, scale
            )
        return polygon_points

    def _compute_explicit_boundary_polygon(
        self, lane, sorted_lanes, section_centerline, scale
    ):
        """Create polygon from explicit outer boundary polyline."""
        outer_boundary_id = (lane.right_boundary_id if lane.id < 0
                             else lane.left_boundary_id)
        if not outer_boundary_id:
            return None
        outer_polyline = self.project.get_polyline(outer_boundary_id)
        if not outer_polyline or len(outer_polyline.points) < 2:
            return None

        inner_offset_px = self._cumulative_inner_offset(lane, sorted_lanes, scale)
        inner_boundary = calculate_offset_polyline(
            section_centerline,
            inner_offset_px if lane.id > 0 else -inner_offset_px,
            closed=False
        )
        if self.verbose:
            logger.debug("      Lane %d: Using explicit outer boundary", lane.id)
        return create_polygon_from_boundaries(
            outer_polyline.points if lane.id > 0 else inner_boundary,
            inner_boundary if lane.id > 0 else outer_polyline.points
        )

    def _compute_width_based_polygon(
        self, lane, sorted_lanes, section_centerline, section_s_values,
        section_length_m, scale
    ):
        """Create polygon from polynomial, variable, or constant width."""
        inner_lanes = [sl for sl in sorted_lanes if self._is_inner_lane(lane.id, sl.id)]

        uses_polynomial = (
            lane.width_b != 0.0 or lane.width_c != 0.0 or lane.width_d != 0.0 or
            any(sl.width_b != 0.0 or sl.width_c != 0.0 or sl.width_d != 0.0
                for sl in inner_lanes)
        )

        if uses_polynomial and section_length_m > 0:
            return self._compute_polynomial_polygon(
                lane, sorted_lanes, section_centerline, section_s_values,
                section_length_m, scale
            )

        has_variable_width = lane.has_variable_width or any(
            sl.has_variable_width for sl in inner_lanes
        )
        if has_variable_width:
            return self._compute_variable_width_polygon(
                lane, sorted_lanes, section_centerline, scale
            )

        return self._compute_constant_width_polygon(
            lane, sorted_lanes, section_centerline, scale
        )

    def _compute_polynomial_polygon(
        self, lane, sorted_lanes, section_centerline, section_s_values,
        section_length_m, scale
    ):
        """Create polygon using polynomial width evaluation at each point."""
        def inner_width_func(s_px):
            s_m = s_px * scale
            total = 0.0
            for inner_lane in sorted_lanes:
                if self._is_inner_lane(lane.id, inner_lane.id):
                    total += inner_lane.get_width_at_s(s_m, section_length_m) / scale
            return total

        def lane_width_func(s_px):
            s_m = s_px * scale
            return lane.get_width_at_s(s_m, section_length_m) / scale

        if self.verbose:
            logger.debug("      Lane %d: Using polynomial width", lane.id)
        return create_polynomial_width_lane_polygon(
            section_centerline, lane.id, inner_width_func,
            lane_width_func, section_s_values, is_left_lane=(lane.id > 0)
        )

    def _compute_variable_width_polygon(
        self, lane, sorted_lanes, section_centerline, scale
    ):
        """Create polygon using linear interpolation between start/end widths."""
        inner_offset_start = 0.0
        inner_offset_end = 0.0
        for inner_lane in sorted_lanes:
            if self._is_inner_lane(lane.id, inner_lane.id):
                inner_offset_start += inner_lane.width / scale
                inner_offset_end += inner_lane.get_width_at_end() / scale

        outer_offset_start = inner_offset_start + lane.width / scale
        outer_offset_end = inner_offset_end + lane.get_width_at_end() / scale

        if lane.id > 0:
            inner_offset_start = -inner_offset_start
            outer_offset_start = -outer_offset_start
            inner_offset_end = -inner_offset_end
            outer_offset_end = -outer_offset_end

        return create_variable_width_lane_polygon(
            section_centerline, inner_offset_start, outer_offset_start,
            inner_offset_end, outer_offset_end
        )

    def _compute_constant_width_polygon(
        self, lane, sorted_lanes, section_centerline, scale
    ):
        """Create polygon using constant lane width offset."""
        inner_offset = self._cumulative_inner_offset(lane, sorted_lanes, scale)
        outer_offset = inner_offset + lane.width / scale

        if lane.id > 0:
            inner_offset = -inner_offset
            outer_offset = -outer_offset

        return create_lane_polygon(
            section_centerline, inner_offset, outer_offset, closed=False
        )

    def _add_lane_scene_item(self, lane_id, section_number, polygon_points):
        """Create and add an InteractiveLanePolygon to the scene."""
        from ..image_view import ImageView
        parent_view = None
        if self.scene.views():
            for view in self.scene.views():
                if isinstance(view, ImageView):
                    parent_view = view
                    break
        if parent_view:
            lane_polygon = InteractiveLanePolygon(
                lane_id, section_number, self.road.id, polygon_points, parent_view
            )
            self.scene.addItem(lane_polygon)
            self.lane_items.append(lane_polygon)

    def _create_legacy_lanes(self, centerline_points: List[Tuple[float, float]], scale: float) -> None:
        """Create continuous lane polygons (old behavior for backward compatibility)."""
        # Get lane configuration
        left_count = self.road.lane_info.left_count
        right_count = self.road.lane_info.right_count
        lane_width_m = self.road.lane_info.lane_width

        # Convert lane width to pixels
        lane_width_px = lane_width_m / scale

        # Verbose output for debugging
        if self.verbose:
            logger.debug("  Lane config: left=%d, right=%d, total=%d",
                         left_count, right_count, left_count + right_count)
            logger.debug("  Lane width configured: %.3f m", lane_width_m)

            # Enhanced scale output
            if self.scale_factors:
                scale_x, scale_y = self.scale_factors
                logger.debug("  Scale from georeferencing: X=%.6f m/px, Y=%.6f m/px, "
                             "directional=%.6f m/px", scale_x, scale_y, scale)
            else:
                logger.debug("  Scale: %.6f m/px (default, no georef)", scale)

            total_width_px = (left_count + right_count) * lane_width_px
            logger.debug("  Lane width in image: %.2f px | Total road width: %.2f px = %.3f m",
                         lane_width_px, total_width_px, total_width_px * scale)

        # Create right-hand lanes (negative IDs in OpenDRIVE: -1, -2, -3, ...)
        # Use POSITIVE offsets to place on right side (in screen coords: positive = right)
        for lane_num in range(1, right_count + 1):
            inner_offset = (lane_num - 1) * lane_width_px
            outer_offset = lane_num * lane_width_px

            polygon_points = create_lane_polygon(
                centerline_points,
                inner_offset,
                outer_offset,
                closed=self.centerline.closed
            )

            if polygon_points:
                lane_item = LaneGraphicsItem(-lane_num, polygon_points, self.scene)
                self.lane_items.append(lane_item)

        # Create left-hand lanes (positive IDs in OpenDRIVE: 1, 2, 3, ...)
        # Use NEGATIVE offsets to place on left side (in screen coords: negative = left)
        for lane_num in range(1, left_count + 1):
            inner_offset = -(lane_num - 1) * lane_width_px
            outer_offset = -lane_num * lane_width_px

            polygon_points = create_lane_polygon(
                centerline_points,
                inner_offset,
                outer_offset,
                closed=self.centerline.closed
            )

            if polygon_points:
                lane_item = LaneGraphicsItem(lane_num, polygon_points, self.scene)
                self.lane_items.append(lane_item)

    def remove(self) -> None:
        """Remove all lane graphics from scene."""
        for lane_item in self.lane_items:
            lane_item.remove()
        self.lane_items.clear()

    def set_visible(self, visible: bool) -> None:
        """Set visibility of all lane graphics."""
        for lane_item in self.lane_items:
            lane_item.set_visible(visible)

    def update_scale(self, scale_factors: tuple) -> None:
        """
        Update scale factors and regenerate graphics.

        Args:
            scale_factors: Tuple of (scale_x, scale_y) in m/px
        """
        self.scale_factors = scale_factors
        self.update_graphics()

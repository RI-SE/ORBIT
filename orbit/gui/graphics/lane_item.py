"""
Lane graphics items for ORBIT.

Provides visual representation of lanes on the image view.
"""

from typing import List, Tuple, Optional, TYPE_CHECKING

from PyQt6.QtWidgets import QGraphicsScene
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPen, QColor, QBrush, QPolygonF

from orbit.models import Road, Polyline, BoundaryMode
from orbit.utils.geometry import (
    create_lane_polygon, create_variable_width_lane_polygon,
    create_polygon_from_boundaries, create_polynomial_width_lane_polygon,
    calculate_directional_scale
)
from .interactive_lane import InteractiveLanePolygon

if TYPE_CHECKING:
    from ..image_view import ImageView


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

    # Default scale in meters per pixel (will be updated from georeferencing later)
    DEFAULT_SCALE = 0.058  # 5.8 cm/px

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
            print(f"\n{'='*60}")
            print(f"LANE VISUALIZATION: {self.road.name} (ID: {self.road.id[:8]}...)")
            print(f"{'='*60}")

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
            print(f"  Creating section-based lane polygons:")
            print(f"    Sections: {len(self.road.lane_sections)}")

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
                print(f"    Section {section.section_number}: {len(section_centerline)} points, {len(section.lanes)} lanes")

            # Calculate section s-coordinates for polynomial width evaluation
            section_s_values = [s_coords[i] - section.s_start for i in section_point_indices]
            section_length_px = section.s_end - section.s_start
            section_length_m = section_length_px * scale  # Convert to meters for polynomial

            # Create polygons for each lane in this section
            # Sort lanes by absolute ID for correct stacking
            sorted_lanes = sorted(section.lanes, key=lambda l: abs(l.id))

            for lane in sorted_lanes:
                if lane.id == 0:
                    continue  # Skip center lane

                polygon_points = None

                # Option 1: Explicit outer boundary polyline
                # (inner boundary is computed from centerline + inner lane widths)
                if (lane.boundary_mode == BoundaryMode.EXPLICIT and
                    self.project is not None):
                    # Determine which boundary ID to use based on lane side
                    outer_boundary_id = (lane.right_boundary_id if lane.id < 0
                                         else lane.left_boundary_id)

                    if outer_boundary_id:
                        outer_polyline = self.project.get_polyline(outer_boundary_id)
                        if outer_polyline and len(outer_polyline.points) >= 2:
                            # Calculate inner boundary from centerline + inner lane widths
                            inner_offset_px = 0.0
                            for inner_lane in sorted_lanes:
                                if inner_lane.id == 0:
                                    continue
                                if (lane.id > 0 and inner_lane.id > 0 and inner_lane.id < lane.id) or \
                                   (lane.id < 0 and inner_lane.id < 0 and abs(inner_lane.id) < abs(lane.id)):
                                    inner_offset_px += inner_lane.width / scale

                            inner_boundary = calculate_offset_polyline(
                                section_centerline,
                                inner_offset_px if lane.id > 0 else -inner_offset_px,
                                closed=False
                            )

                            polygon_points = create_polygon_from_boundaries(
                                outer_polyline.points if lane.id > 0 else inner_boundary,
                                inner_boundary if lane.id > 0 else outer_polyline.points
                            )
                            if self.verbose:
                                print(f"      Lane {lane.id}: Using explicit outer boundary")

                # Option 2: Polynomial/variable width
                if polygon_points is None:
                    # Check if any lane uses polynomial width (b, c, d coefficients)
                    uses_polynomial = (
                        lane.width_b != 0.0 or lane.width_c != 0.0 or lane.width_d != 0.0 or
                        any((l.width_b != 0.0 or l.width_c != 0.0 or l.width_d != 0.0)
                            for l in sorted_lanes
                            if l.id != 0 and
                            ((lane.id > 0 and l.id > 0 and l.id < lane.id) or
                             (lane.id < 0 and l.id < 0 and abs(l.id) < abs(lane.id))))
                    )

                    # Check if any lane has simple variable width (width_end)
                    has_variable_width = lane.has_variable_width or \
                        any(l.has_variable_width for l in sorted_lanes
                            if l.id != 0 and
                            ((lane.id > 0 and l.id > 0 and l.id < lane.id) or
                             (lane.id < 0 and l.id < 0 and abs(l.id) < abs(lane.id))))

                    if uses_polynomial and section_length_m > 0:
                        # Use polynomial width evaluation at each point
                        def inner_width_func(s_px):
                            """Calculate cumulative inner lane width at s position."""
                            s_m = s_px * scale  # Convert to meters
                            total = 0.0
                            for inner_lane in sorted_lanes:
                                if inner_lane.id == 0:
                                    continue
                                if (lane.id > 0 and inner_lane.id > 0 and inner_lane.id < lane.id) or \
                                   (lane.id < 0 and inner_lane.id < 0 and abs(inner_lane.id) < abs(lane.id)):
                                    total += inner_lane.get_width_at_s(s_m, section_length_m) / scale
                            return total

                        def lane_width_func(s_px):
                            """Calculate this lane's width at s position."""
                            s_m = s_px * scale
                            return lane.get_width_at_s(s_m, section_length_m) / scale

                        polygon_points = create_polynomial_width_lane_polygon(
                            section_centerline,
                            lane.id,
                            inner_width_func,
                            lane_width_func,
                            section_s_values,
                            is_left_lane=(lane.id > 0)
                        )
                        if self.verbose:
                            print(f"      Lane {lane.id}: Using polynomial width")

                    elif has_variable_width:
                        # Use linear interpolation (start/end width)
                        inner_offset_start = 0.0
                        inner_offset_end = 0.0
                        for inner_lane in sorted_lanes:
                            if inner_lane.id == 0:
                                continue
                            if (lane.id > 0 and inner_lane.id > 0 and inner_lane.id < lane.id) or \
                               (lane.id < 0 and inner_lane.id < 0 and abs(inner_lane.id) < abs(lane.id)):
                                inner_offset_start += inner_lane.width / scale
                                inner_offset_end += inner_lane.get_width_at_end() / scale

                        lane_width_start_px = lane.width / scale
                        lane_width_end_px = lane.get_width_at_end() / scale
                        outer_offset_start = inner_offset_start + lane_width_start_px
                        outer_offset_end = inner_offset_end + lane_width_end_px

                        # Apply sign for left lanes
                        if lane.id > 0:
                            inner_offset_start = -inner_offset_start
                            outer_offset_start = -outer_offset_start
                            inner_offset_end = -inner_offset_end
                            outer_offset_end = -outer_offset_end

                        polygon_points = create_variable_width_lane_polygon(
                            section_centerline,
                            inner_offset_start,
                            outer_offset_start,
                            inner_offset_end,
                            outer_offset_end
                        )
                    else:
                        # Constant width - use simple offset
                        inner_offset = 0.0
                        for inner_lane in sorted_lanes:
                            if inner_lane.id == 0:
                                continue
                            if (lane.id > 0 and inner_lane.id > 0 and inner_lane.id < lane.id) or \
                               (lane.id < 0 and inner_lane.id < 0 and abs(inner_lane.id) < abs(lane.id)):
                                inner_offset += inner_lane.width / scale

                        outer_offset = inner_offset + lane.width / scale

                        # Apply sign for left lanes
                        if lane.id > 0:
                            inner_offset = -inner_offset
                            outer_offset = -outer_offset

                        polygon_points = create_lane_polygon(
                            section_centerline,
                            inner_offset,
                            outer_offset,
                            closed=False
                        )

                if polygon_points and len(polygon_points) >= 3:
                    # Create interactive polygon
                    # Import here to avoid circular import
                    from ..image_view import ImageView
                    parent_view: Optional['ImageView'] = None
                    # Find parent ImageView from scene
                    if self.scene.views():
                        for view in self.scene.views():
                            if isinstance(view, ImageView):
                                parent_view = view
                                break

                    if parent_view:
                        lane_polygon = InteractiveLanePolygon(
                            lane.id,
                            section.section_number,
                            self.road.id,
                            polygon_points,
                            parent_view
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
            print(f"  Lane configuration:")
            print(f"    Left lanes:  {left_count}")
            print(f"    Right lanes: {right_count}")
            print(f"    Total lanes: {left_count + right_count}")
            print(f"  Lane width:")
            print(f"    Configured: {lane_width_m:.3f} m")

            # Enhanced scale output
            if self.scale_factors:
                scale_x, scale_y = self.scale_factors
                print(f"  Scale from georeferencing:")
                print(f"    X (horizontal): {scale_x:.6f} m/px = {scale_x*100:.4f} cm/px")
                print(f"    Y (vertical):   {scale_y:.6f} m/px = {scale_y*100:.4f} cm/px")
                print(f"    Directional:    {scale:.6f} m/px = {scale*100:.4f} cm/px")
            else:
                print(f"  Scale:")
                print(f"    {scale:.6f} m/px = {scale*100:.4f} cm/px")
                print(f"    Source: default (no georef)")

            print(f"  Calculated lane width in image:")
            print(f"    {lane_width_px:.2f} pixels")
            print(f"  Total road width in image:")
            total_width_px = (left_count + right_count) * lane_width_px
            print(f"    {total_width_px:.2f} pixels = {total_width_px * scale:.3f} m")
            print(f"{'='*60}\n")

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

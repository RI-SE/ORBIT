"""
Connecting road graphics items for ORBIT.

Provides visual representation of connecting roads (junction paths) on the image view.
"""

import math
from typing import List, Tuple, Optional, TYPE_CHECKING

from PyQt6.QtWidgets import QGraphicsScene
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QPen, QColor, QBrush, QPolygonF

from orbit.utils.geometry import calculate_directional_scale
from .interactive_lane import InteractiveLanePolygon

if TYPE_CHECKING:
    from orbit.models.connecting_road import ConnectingRoad
    from ..image_view import ImageView


class ConnectingRoadGraphicsItem:
    """Graphics representation of a connecting road centerline."""

    def __init__(self, connecting_road: 'ConnectingRoad', scene: QGraphicsScene) -> None:
        """
        Create graphics for a connecting road centerline.

        Args:
            connecting_road: ConnectingRoad object
            scene: Graphics scene to add items to
        """
        self.connecting_road = connecting_road
        self.scene = scene
        self.line_items: List = []
        self.point_items: List = []
        self.arrow_items: List = []
        self.selected: bool = False
        self.selected_point_index: int = -1

        self.update_graphics()

    def update_graphics(self) -> None:
        """Update the graphics items based on connecting road data."""
        # Clear existing items
        for item in self.line_items + self.point_items + self.arrow_items:
            self.scene.removeItem(item)
        self.line_items.clear()
        self.point_items.clear()
        self.arrow_items.clear()

        if len(self.connecting_road.path) < 1:
            return

        # Create pen for connecting road (magenta)
        color = QColor(255, 0, 255)  # Magenta
        if self.selected:
            color = QColor(255, 255, 0)  # Yellow when selected

        width = 3 if self.selected else 2
        pen = QPen(color, width)
        pen.setStyle(Qt.PenStyle.SolidLine)

        # Use the stored path directly - it already contains sampled curve points
        # (20 points from Bezier/Hermite interpolation during junction analysis)
        points = self.connecting_road.path

        # Draw lines between points
        for i in range(len(points) - 1):
            x1, y1 = points[i]
            x2, y2 = points[i + 1]
            line = self.scene.addLine(x1, y1, x2, y2, pen)
            line.setZValue(1)
            self.line_items.append(line)

        # Draw directional arrows
        if len(points) >= 2:
            self._draw_direction_arrows(points, pen)

        # Only draw points for polyline geometry (not for ParamPoly3D curves)
        # ParamPoly3D curves are read-only and don't show editable points
        if self.connecting_road.geometry_type == "polyline":
            point_brush = QBrush(color)

            for i, (x, y) in enumerate(points):
                radius = 5
                if i == self.selected_point_index:
                    radius = 7
                    point_brush = QBrush(QColor(255, 128, 0))  # Orange for selected point

                point = self.scene.addEllipse(
                    x - radius, y - radius, radius * 2, radius * 2,
                    pen, point_brush
                )
                point.setZValue(2)
                self.point_items.append(point)

                # Reset brush for next point
                if i == self.selected_point_index:
                    point_brush = QBrush(QColor(255, 255, 0) if self.selected else color)

    def _draw_direction_arrows(self, points: List[Tuple[float, float]], pen: QPen) -> None:
        """Draw direction arrows to show the positive direction."""
        # Arrow parameters
        arrow_size = 15  # Length of arrow head
        arrow_angle = 25  # Angle of arrow head in degrees

        # Color for arrows
        if self.selected:
            arrow_color = QColor(255, 255, 0)  # Yellow when selected
        else:
            arrow_color = QColor(255, 0, 255)  # Magenta

        arrow_pen = QPen(arrow_color, 2)
        arrow_brush = QBrush(arrow_color)

        # Draw arrow at the end
        if len(points) >= 2:
            p1 = points[-2]
            p2 = points[-1]  # End point
            self._draw_arrow_at_point(p2, p1, arrow_size, arrow_angle, arrow_pen, arrow_brush)

            # Draw arrows at regular intervals (~200 pixels)
            total_length = 0.0
            segment_lengths = []
            for i in range(len(points) - 1):
                x1, y1 = points[i]
                x2, y2 = points[i + 1]
                seg_len = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
                segment_lengths.append(seg_len)
                total_length += seg_len

            # Place arrows every 200 pixels
            arrow_interval = 200.0
            if total_length > arrow_interval:
                num_intermediate_arrows = int(total_length / arrow_interval)
                for arrow_idx in range(1, num_intermediate_arrows + 1):
                    target_distance = arrow_idx * arrow_interval

                    # Find segment containing this distance
                    accumulated = 0.0
                    for i, seg_len in enumerate(segment_lengths):
                        if accumulated + seg_len >= target_distance:
                            # Interpolate within this segment
                            t = (target_distance - accumulated) / seg_len if seg_len > 0 else 0
                            x1, y1 = points[i]
                            x2, y2 = points[i + 1]
                            arrow_x = x1 + t * (x2 - x1)
                            arrow_y = y1 + t * (y2 - y1)
                            arrow_point = (arrow_x, arrow_y)
                            prev_point = (x1, y1)
                            self._draw_arrow_at_point(arrow_point, prev_point, arrow_size,
                                                     arrow_angle, arrow_pen, arrow_brush)
                            break
                        accumulated += seg_len

    def _draw_arrow_at_point(self, end_point: Tuple[float, float],
                            prev_point: Tuple[float, float],
                            arrow_size: float, arrow_angle: float,
                            arrow_pen: QPen, arrow_brush: QBrush) -> None:
        """Draw a single arrow at a specific point."""
        x2, y2 = end_point
        x1, y1 = prev_point

        # Calculate direction angle
        angle = math.atan2(y2 - y1, x2 - x1)

        # Calculate arrow head points
        angle1 = angle + math.radians(180 - arrow_angle)
        angle2 = angle + math.radians(180 + arrow_angle)

        arrow_p1_x = x2 + arrow_size * math.cos(angle1)
        arrow_p1_y = y2 + arrow_size * math.sin(angle1)
        arrow_p2_x = x2 + arrow_size * math.cos(angle2)
        arrow_p2_y = y2 + arrow_size * math.sin(angle2)

        # Create arrow polygon
        arrow_polygon = QPolygonF()
        arrow_polygon.append(QPointF(x2, y2))
        arrow_polygon.append(QPointF(arrow_p1_x, arrow_p1_y))
        arrow_polygon.append(QPointF(arrow_p2_x, arrow_p2_y))

        arrow_item = self.scene.addPolygon(arrow_polygon, arrow_pen, arrow_brush)
        arrow_item.setZValue(2)
        self.arrow_items.append(arrow_item)

    def get_point_at(self, pos: QPointF, tolerance: float = 10.0) -> int:
        """
        Check if a position is near a point in the connecting road path.

        Args:
            pos: Position to check
            tolerance: Distance tolerance in pixels

        Returns:
            Index of the point if found, -1 otherwise
        """
        for i, (x, y) in enumerate(self.connecting_road.path):
            dx = pos.x() - x
            dy = pos.y() - y
            dist = (dx * dx + dy * dy) ** 0.5
            if dist <= tolerance:
                return i
        return -1

    def get_segment_at(self, pos: QPointF, tolerance: float = 10.0) -> int:
        """
        Check if a position is near a line segment.

        Args:
            pos: Position to check
            tolerance: Distance tolerance in pixels

        Returns:
            Index of the segment (0-based) if found, -1 otherwise
        """
        points = self.connecting_road.path
        for i in range(len(points) - 1):
            x1, y1 = points[i]
            x2, y2 = points[i + 1]

            # Calculate distance from point to line segment
            px, py = pos.x(), pos.y()

            # Vector from p1 to p2
            dx = x2 - x1
            dy = y2 - y1
            length_sq = dx * dx + dy * dy

            if length_sq == 0:
                continue

            # Project point onto line
            t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / length_sq))
            proj_x = x1 + t * dx
            proj_y = y1 + t * dy

            # Distance from point to projection
            dist_dx = px - proj_x
            dist_dy = py - proj_y
            dist = (dist_dx * dist_dx + dist_dy * dist_dy) ** 0.5

            if dist <= tolerance:
                return i

        return -1

    def set_selected(self, selected: bool) -> None:
        """Set selection state."""
        self.selected = selected
        self.update_graphics()

    def remove(self) -> None:
        """Remove all graphics items from scene."""
        for item in self.line_items + self.point_items + self.arrow_items:
            if item.scene() == self.scene:
                self.scene.removeItem(item)
        self.line_items.clear()
        self.point_items.clear()
        self.arrow_items.clear()


class ConnectingRoadLanesGraphicsItem:
    """Graphics representation of lanes in a connecting road."""

    # Default scale in meters per pixel
    DEFAULT_SCALE = 0.058  # 5.8 cm/px

    def __init__(self, connecting_road: 'ConnectingRoad', scene: QGraphicsScene,
                 scale_factors: Optional[tuple] = None, parent_view: Optional['ImageView'] = None,
                 verbose: bool = False) -> None:
        """
        Create lane graphics for a connecting road.

        Args:
            connecting_road: ConnectingRoad object
            scene: Graphics scene
            scale_factors: Tuple of (scale_x, scale_y) in m/px, or None for default
            parent_view: Parent ImageView for signaling (optional)
            verbose: Enable verbose debug output
        """
        self.connecting_road = connecting_road
        self.scene = scene
        self.scale_factors = scale_factors
        self.parent_view = parent_view
        self.verbose = verbose
        self.lane_items: List = []

        self.update_graphics()

    def _calculate_scale(self) -> float:
        """
        Calculate the appropriate scale factor.

        Returns:
            Scale factor in meters per pixel
        """
        if not self.scale_factors:
            return self.DEFAULT_SCALE

        scale_x, scale_y = self.scale_factors
        return calculate_directional_scale(
            self.connecting_road.path, scale_x, scale_y,
            default_scale=self.DEFAULT_SCALE
        )

    def update_graphics(self) -> None:
        """Update all lane graphics based on current connecting road configuration."""
        # Remove existing lanes
        for lane_item in self.lane_items:
            if hasattr(lane_item, 'remove'):
                lane_item.remove()
            elif lane_item.scene() == self.scene:
                self.scene.removeItem(lane_item)
        self.lane_items.clear()

        if len(self.connecting_road.path) < 2:
            return

        # Calculate scale
        scale = self._calculate_scale()

        if self.verbose:
            print(f"\n{'='*60}")
            print(f"CONNECTING ROAD LANES: {self.connecting_road.id[:8]}...")
            print(f"  Scale: {scale:.6f} m/px")
            print(f"  Lane width: {self.connecting_road.lane_width}m")
            print(f"  Lanes: R{self.connecting_road.lane_count_right}, L{self.connecting_road.lane_count_left}")

        # Get lane polygons
        lane_polygons = self.connecting_road.get_lane_polygons(scale)

        # Create interactive polygon for each lane
        for lane_id, polygon_points in lane_polygons.items():
            if len(polygon_points) >= 3:
                if self.parent_view:
                    # Create interactive polygon with click/hover
                    lane_polygon = InteractiveLanePolygon(
                        lane_id,
                        section_number=1,  # Connecting roads have single section
                        road_id=self.connecting_road.id,
                        polygon_points=polygon_points,
                        parent_view=self.parent_view,
                        is_connecting_road=True  # Flag this as a connecting road lane
                    )
                    self.scene.addItem(lane_polygon)
                    self.lane_items.append(lane_polygon)

                    if self.verbose:
                        print(f"    Lane {lane_id}: {len(polygon_points)} points")
                else:
                    # Fallback: create simple polygon without interactivity
                    polygon = QPolygonF()
                    for x, y in polygon_points:
                        polygon.append(QPointF(x, y))

                    # Choose color based on lane side (darker shades for connecting roads)
                    if lane_id < 0:
                        color = QColor(50, 180, 50, 77)  # Darker green for right lanes
                    else:
                        color = QColor(50, 120, 200, 77)  # Darker blue for left lanes

                    pen = QPen(QColor(200, 200, 200, 150), 1)
                    brush = QBrush(color)

                    polygon_item = self.scene.addPolygon(polygon, pen, brush)
                    polygon_item.setZValue(0.5)
                    self.lane_items.append(polygon_item)

    def remove(self) -> None:
        """Remove all lane graphics from scene."""
        for lane_item in self.lane_items:
            if hasattr(lane_item, 'remove'):
                lane_item.remove()
            elif lane_item.scene() == self.scene:
                self.scene.removeItem(lane_item)
        self.lane_items.clear()

    def set_visible(self, visible: bool) -> None:
        """Set visibility of all lane graphics."""
        for lane_item in self.lane_items:
            if hasattr(lane_item, 'setVisible'):
                lane_item.setVisible(visible)

    def update_scale(self, scale_factors: tuple) -> None:
        """
        Update scale factors and regenerate graphics.

        Args:
            scale_factors: Tuple of (scale_x, scale_y) in m/px
        """
        self.scale_factors = scale_factors
        self.update_graphics()

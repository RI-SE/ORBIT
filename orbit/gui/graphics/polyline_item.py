"""
Polyline graphics item for ORBIT.

Provides visual representation of polylines on the image view.
"""

import math
from typing import List, Tuple

from PyQt6.QtWidgets import QGraphicsScene
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QPen, QColor, QBrush, QPolygonF

from orbit.models import Polyline, LineType, RoadMarkType


class PolylineGraphicsItem:
    """Graphics representation of a polyline."""

    def __init__(self, polyline: Polyline, scene: QGraphicsScene) -> None:
        self.polyline = polyline
        self.scene = scene
        self.line_items: List = []
        self.point_items: List = []
        self.arrow_items: List = []  # Store arrow graphics for centerline direction
        self.selected: bool = False
        self.selected_point_index: int = -1

        self.update_graphics()

    def update_graphics(self) -> None:
        """Update the graphics items based on polyline data."""
        # Clear existing items
        for item in self.line_items + self.point_items + self.arrow_items:
            self.scene.removeItem(item)
        self.line_items.clear()
        self.point_items.clear()
        self.arrow_items.clear()

        if self.polyline.point_count() < 1:
            return

        # Create pen based on line type and road mark type
        pen = self._create_pen_for_polyline()

        # Draw lines between points
        points = self.polyline.points
        for i in range(len(points) - 1):
            x1, y1 = points[i]
            x2, y2 = points[i + 1]
            line = self.scene.addLine(x1, y1, x2, y2, pen)
            line.setZValue(1)
            self.line_items.append(line)

        # Draw closing line if closed
        if self.polyline.closed and len(points) > 2:
            x1, y1 = points[-1]
            x2, y2 = points[0]
            line = self.scene.addLine(x1, y1, x2, y2, pen)
            line.setZValue(1)
            self.line_items.append(line)

        # Draw directional arrows for centerlines
        if self.polyline.line_type == LineType.CENTERLINE and len(points) >= 2:
            self._draw_direction_arrows(points, pen)

        # Draw points
        color = QColor(*self.polyline.color)
        point_brush = QBrush(color)
        if self.selected:
            point_brush.setColor(QColor(255, 255, 0))

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

    def _create_pen_for_polyline(self) -> QPen:
        """Create a pen with appropriate style for the polyline's type and mark type."""
        # Base color based on line type
        if self.polyline.line_type == LineType.CENTERLINE:
            color = QColor(255, 165, 0)  # Orange for centerline
        else:
            color = QColor(0, 255, 255)  # Cyan for lane boundaries

        # Override with selection color
        if self.selected:
            color = QColor(255, 255, 0)  # Yellow when selected

        # Base width
        width = 3 if self.selected else 2

        # Create pen
        pen = QPen(color, width)

        # Set pen style based on road mark type
        mark_type = self.polyline.road_mark_type

        if mark_type == RoadMarkType.SOLID:
            pen.setStyle(Qt.PenStyle.SolidLine)
        elif mark_type == RoadMarkType.BROKEN:
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setDashPattern([10, 10])  # 10 pixels line, 10 pixels space
        elif mark_type == RoadMarkType.SOLID_SOLID:
            pen.setStyle(Qt.PenStyle.SolidLine)
            # Note: Double lines would require drawing two parallel lines
        elif mark_type == RoadMarkType.SOLID_BROKEN:
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setDashPattern([15, 5])  # Longer dashes
        elif mark_type == RoadMarkType.BROKEN_SOLID:
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setDashPattern([5, 15])  # Shorter dashes, longer gaps
        elif mark_type == RoadMarkType.BROKEN_BROKEN:
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setDashPattern([5, 5])  # Short dashes
        elif mark_type == RoadMarkType.BOTTS_DOTS:
            pen.setStyle(Qt.PenStyle.DotLine)
        elif mark_type == RoadMarkType.GRASS:
            pen.setStyle(Qt.PenStyle.DashDotLine)
        elif mark_type == RoadMarkType.CURB:
            pen.setStyle(Qt.PenStyle.SolidLine)
            pen.setWidth(width + 1)  # Slightly thicker for curbs
        elif mark_type == RoadMarkType.EDGE:
            pen.setStyle(Qt.PenStyle.SolidLine)
        elif mark_type == RoadMarkType.NONE:
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setDashPattern([3, 7])  # Very faint
        else:  # CUSTOM or unknown
            pen.setStyle(Qt.PenStyle.DashDotDotLine)

        return pen

    def _draw_direction_arrows(self, points: List[Tuple[float, float]], pen: QPen) -> None:
        """
        Draw direction arrows on centerline to show the positive direction.

        Arrows are drawn at the end and at intervals along the centerline.
        """
        # Arrow parameters
        arrow_size = 15  # Length of arrow head
        arrow_angle = 25  # Angle of arrow head in degrees

        # Color for arrows
        if self.selected:
            arrow_color = QColor(255, 255, 0)  # Yellow when selected
        else:
            arrow_color = QColor(255, 165, 0)  # Orange for centerline

        arrow_pen = QPen(arrow_color, 2)
        arrow_brush = QBrush(arrow_color)

        # Draw arrow at the end of the centerline
        if len(points) >= 2:
            # Use last two points to determine direction
            p1 = points[-2]
            p2 = points[-1]  # End point

            self._draw_arrow_at_point(p2, p1, arrow_size, arrow_angle, arrow_pen, arrow_brush)

            # Draw arrows at regular intervals along the centerline (every ~200 pixels)
            total_length = 0.0
            segment_lengths = []
            for i in range(len(points) - 1):
                x1, y1 = points[i]
                x2, y2 = points[i + 1]
                seg_len = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
                segment_lengths.append(seg_len)
                total_length += seg_len

            # Place arrows every 200 pixels (but skip if too short)
            if total_length > 300:
                arrow_interval = 200
                current_length = 0.0
                target_length = float(arrow_interval)

                for i in range(len(points) - 1):
                    seg_len = segment_lengths[i]

                    # Check if we should place an arrow in this segment
                    while current_length + seg_len >= target_length:
                        # Calculate position along this segment
                        t = (target_length - current_length) / seg_len
                        if 0 < t < 1:  # Don't place at endpoints
                            x1, y1 = points[i]
                            x2, y2 = points[i + 1]
                            arrow_x = x1 + t * (x2 - x1)
                            arrow_y = y1 + t * (y2 - y1)

                            self._draw_arrow_at_point(
                                (arrow_x, arrow_y), points[i],
                                arrow_size * 0.7, arrow_angle,  # Slightly smaller intermediate arrows
                                arrow_pen, arrow_brush
                            )

                        target_length += arrow_interval

                    current_length += seg_len

    def _draw_arrow_at_point(
        self,
        tip_point: Tuple[float, float],
        prev_point: Tuple[float, float],
        arrow_size: float,
        arrow_angle: float,
        pen: QPen,
        brush: QBrush
    ) -> None:
        """Draw a single arrow at the specified point."""
        tx, ty = tip_point
        px, py = prev_point

        # Calculate direction angle
        dx = tx - px
        dy = ty - py
        angle = math.atan2(dy, dx)

        # Calculate arrow head points
        angle_rad = math.radians(arrow_angle)

        left_x = tx - arrow_size * math.cos(angle - angle_rad)
        left_y = ty - arrow_size * math.sin(angle - angle_rad)

        right_x = tx - arrow_size * math.cos(angle + angle_rad)
        right_y = ty - arrow_size * math.sin(angle + angle_rad)

        # Create arrow polygon (filled triangle)
        arrow_polygon = QPolygonF()
        arrow_polygon.append(QPointF(tx, ty))  # Tip
        arrow_polygon.append(QPointF(left_x, left_y))
        arrow_polygon.append(QPointF(right_x, right_y))

        # Add arrow to scene
        arrow_item = self.scene.addPolygon(arrow_polygon, pen, brush)
        arrow_item.setZValue(1.5)  # Above lines, below points
        self.arrow_items.append(arrow_item)

    def set_selected(self, selected: bool) -> None:
        """Set selection state."""
        self.selected = selected
        self.update_graphics()

    def set_selected_point(self, index: int) -> None:
        """Set selected point index."""
        self.selected_point_index = index
        self.update_graphics()

    def get_point_at(self, pos: QPointF, tolerance: float = 10.0) -> int:
        """Get the index of the point at the given position, or -1 if none."""
        for i, (x, y) in enumerate(self.polyline.points):
            dx = pos.x() - x
            dy = pos.y() - y
            dist = (dx * dx + dy * dy) ** 0.5
            if dist <= tolerance:
                return i
        return -1

    def is_near_line(self, pos: QPointF, tolerance: float = 10.0) -> bool:
        """Check if position is near any line segment."""
        points = self.polyline.points
        for i in range(len(points) - 1):
            if self._point_to_segment_distance(pos, points[i], points[i + 1]) <= tolerance:
                return True
        return False

    def get_segment_at(self, pos: QPointF, tolerance: float = 10.0) -> int:
        """Get the index of the segment at the given position, or -1 if none.

        Returns the index of the first point of the segment (0 means between points 0 and 1).
        """
        points = self.polyline.points
        for i in range(len(points) - 1):
            if self._point_to_segment_distance(pos, points[i], points[i + 1]) <= tolerance:
                return i
        return -1

    @staticmethod
    def _point_to_segment_distance(point: QPointF, seg_start: tuple, seg_end: tuple) -> float:
        """Calculate distance from point to line segment."""
        px, py = point.x(), point.y()
        x1, y1 = seg_start
        x2, y2 = seg_end

        dx = x2 - x1
        dy = y2 - y1
        if dx == 0 and dy == 0:
            return ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5

        t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
        proj_x = x1 + t * dx
        proj_y = y1 + t * dy

        return ((px - proj_x) ** 2 + (py - proj_y) ** 2) ** 0.5

    def remove(self) -> None:
        """Remove all graphics items from scene."""
        for item in self.line_items + self.point_items + self.arrow_items:
            if item.scene() == self.scene:
                self.scene.removeItem(item)
        self.line_items.clear()
        self.point_items.clear()
        self.arrow_items.clear()

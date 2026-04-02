"""
Graphics item for displaying parking spaces on the map.

Supports:
- Point-based parking spaces (rectangles with width/length/orientation)
- Polygon-based parking lots (arbitrary outlines)
- Interactive resize via corner handles
- Interactive rotation via rotation handle
"""

import math
from typing import List, Optional, Tuple

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainterPath, QPen
from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsItemGroup, QGraphicsPathItem

from orbit.models.parking import ParkingAccess, ParkingSpace

# Color mapping by access type (30% opacity = 77 alpha, consistent with lanes)
ACCESS_COLORS = {
    ParkingAccess.STANDARD: QColor(100, 100, 255, 77),      # Light blue
    ParkingAccess.DISABLED: QColor(0, 100, 255, 77),        # Blue
    ParkingAccess.HANDICAPPED: QColor(0, 100, 255, 77),     # Blue
    ParkingAccess.PRIVATE: QColor(255, 100, 100, 77),       # Light red
    ParkingAccess.RESERVED: QColor(255, 165, 0, 77),        # Orange
    ParkingAccess.CUSTOMERS: QColor(100, 255, 100, 77),     # Light green
    ParkingAccess.COMPANY: QColor(180, 100, 180, 77),       # Purple
    ParkingAccess.PERMIT: QColor(255, 200, 100, 77),        # Yellow-orange
    ParkingAccess.WOMEN: QColor(255, 150, 200, 77),         # Pink
    ParkingAccess.RESIDENTS: QColor(100, 200, 150, 77),     # Teal
}

DEFAULT_COLOR = QColor(100, 100, 255, 77)

# Handle properties
HANDLE_SIZE = 8
HANDLE_COLOR = QColor(255, 165, 0)  # Orange
ROTATE_HANDLE_COLOR = QColor(0, 200, 0)  # Green
ROTATE_HANDLE_OFFSET = 30  # Distance from edge


class ParkingGraphicsItem(QGraphicsItemGroup):
    """
    Graphics item representing a parking space on the map.

    Supports both point-based (rectangle) and polygon-based (lot outline) parking.
    When selected, shows resize handles at corners and a rotation handle.
    """

    def __init__(self, parking: ParkingSpace, scale_factor: float = 0.0, parent=None):
        super().__init__(parent)
        self.parking = parking
        self.scale_factor = scale_factor  # Meters per pixel
        self.parking_changed = None  # Callback function for changes

        # Main shape item
        self.shape_item = QGraphicsPathItem()
        self.addToGroup(self.shape_item)

        # Selection highlight
        self.selection_item = QGraphicsPathItem()
        self.selection_item.setPen(QPen(QColor(255, 200, 0, 200), 2, Qt.PenStyle.DashLine))
        self.selection_item.setVisible(False)
        self.addToGroup(self.selection_item)

        # Resize handles (for point parking only)
        self.corner_handles: List[QGraphicsEllipseItem] = []
        self.rotate_handle: Optional[QGraphicsEllipseItem] = None
        self.rotate_line: Optional[QGraphicsPathItem] = None
        # Vertex handles (for polygon parking)
        self.vertex_handles: List[QGraphicsPathItem] = []

        # Interaction state
        self.dragging_handle = -1  # -1 = not dragging, 0-3 = corner index, 4 = rotate
        self.drag_start_pos = QPointF()
        self.drag_start_width = 0.0
        self.drag_start_length = 0.0
        self.drag_start_orientation = 0.0

        # Make item selectable, movable (for point parking only), and focusable
        self.setFlag(QGraphicsItemGroup.GraphicsItemFlag.ItemIsSelectable, True)
        if not parking.is_polygon():
            self.setFlag(QGraphicsItemGroup.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItemGroup.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)

        # Set position for point parking (polygon uses scene coordinates directly)
        if not parking.is_polygon():
            self.setPos(parking.position[0], parking.position[1])

        self.update_graphics()

    def update_graphics(self):
        """Update visual representation based on parking properties."""
        color = ACCESS_COLORS.get(self.parking.access, DEFAULT_COLOR)

        if self.parking.is_polygon():
            path = self._create_polygon_path()
        else:
            path = self._create_rectangle_path()

        self.shape_item.setPath(path)
        self.shape_item.setPen(QPen(color.darker(150), 2))
        self.shape_item.setBrush(QBrush(color))

        # Update tooltip
        tooltip = self.parking.get_display_name()
        if self.parking.access != ParkingAccess.STANDARD:
            tooltip += f"\nAccess: {self.parking.access.value.replace('_', ' ').title()}"
        if self.parking.capacity:
            tooltip += f"\nCapacity: {self.parking.capacity}"
        tooltip += f"\nSize: {self.parking.width:.1f}m x {self.parking.length:.1f}m"
        tooltip += f"\nOrientation: {self.parking.orientation:.1f}°"
        self.setToolTip(tooltip)

        # Update selection highlight
        self._update_selection_highlight(path)

        # Update handles if selected
        self._update_handles()

    def _get_size_in_pixels(self) -> Tuple[float, float]:
        """Get parking dimensions in pixels."""
        if self.scale_factor > 0:
            width_px = self.parking.width / self.scale_factor
            length_px = self.parking.length / self.scale_factor
        else:
            width_px = 25
            length_px = 50
        return width_px, length_px

    def _get_rotated_corners(self) -> List[Tuple[float, float]]:
        """Get corner positions in local coordinates (rotated)."""
        width_px, length_px = self._get_size_in_pixels()
        half_w = width_px / 2
        half_l = length_px / 2

        angle_rad = math.radians(self.parking.orientation)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)

        # Corners: top-left, top-right, bottom-right, bottom-left
        corners = [
            (-half_w, -half_l),
            (half_w, -half_l),
            (half_w, half_l),
            (-half_w, half_l),
        ]

        rotated = []
        for x, y in corners:
            rx = x * cos_a - y * sin_a
            ry = x * sin_a + y * cos_a
            rotated.append((rx, ry))

        return rotated

    def _create_rectangle_path(self) -> QPainterPath:
        """Create a path for rectangle parking space (point-based)."""
        path = QPainterPath()
        rotated = self._get_rotated_corners()

        path.moveTo(rotated[0][0], rotated[0][1])
        for rx, ry in rotated[1:]:
            path.lineTo(rx, ry)
        path.closeSubpath()

        return path

    def _create_polygon_path(self) -> QPainterPath:
        """Create a path from polygon points (lot outline)."""
        path = QPainterPath()

        if not self.parking.points or len(self.parking.points) < 3:
            return self._create_rectangle_path()

        path.moveTo(self.parking.points[0][0], self.parking.points[0][1])
        for x, y in self.parking.points[1:]:
            path.lineTo(x, y)
        path.closeSubpath()

        return path

    def _update_selection_highlight(self, base_path: QPainterPath):
        """Update selection highlight to match parking shape."""
        from PyQt6.QtGui import QPainterPathStroker

        stroker = QPainterPathStroker()
        stroker.setWidth(8)
        highlight_path = stroker.createStroke(base_path)

        self.selection_item.setPath(highlight_path)
        self.selection_item.setVisible(self.isSelected())

    def _update_handles(self):
        """Update resize and rotation handles visibility and position."""
        # Remove old handles
        for handle in self.corner_handles:
            self.removeFromGroup(handle)
        self.corner_handles.clear()
        for handle in self.vertex_handles:
            self.removeFromGroup(handle)
        self.vertex_handles.clear()

        if self.rotate_handle:
            self.removeFromGroup(self.rotate_handle)
            self.rotate_handle = None
        if self.rotate_line:
            self.removeFromGroup(self.rotate_line)
            self.rotate_line = None

        # Only show handles for selected items
        if not self.isSelected():
            return

        if self.parking.is_polygon():
            self._draw_polygon_vertex_handles()
            return

        # Create corner handles for point parking
        corners = self._get_rotated_corners()
        for i, (cx, cy) in enumerate(corners):
            handle = QGraphicsEllipseItem(
                cx - HANDLE_SIZE/2, cy - HANDLE_SIZE/2,
                HANDLE_SIZE, HANDLE_SIZE
            )
            handle.setPen(QPen(HANDLE_COLOR.darker(120), 1))
            handle.setBrush(QBrush(HANDLE_COLOR))
            handle.setZValue(10)
            self.addToGroup(handle)
            self.corner_handles.append(handle)

        # Create rotation handle at top center (before rotation)
        width_px, length_px = self._get_size_in_pixels()
        angle_rad = math.radians(self.parking.orientation)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)

        # Rotate point (0, -half_l - offset) by orientation
        offset_y = -length_px / 2 - ROTATE_HANDLE_OFFSET
        rot_x = -offset_y * sin_a
        rot_y = offset_y * cos_a

        self.rotate_handle = QGraphicsEllipseItem(
            rot_x - HANDLE_SIZE/2, rot_y - HANDLE_SIZE/2,
            HANDLE_SIZE, HANDLE_SIZE
        )
        self.rotate_handle.setPen(QPen(ROTATE_HANDLE_COLOR.darker(120), 1))
        self.rotate_handle.setBrush(QBrush(ROTATE_HANDLE_COLOR))
        self.rotate_handle.setZValue(10)
        self.addToGroup(self.rotate_handle)

        # Draw line from center to rotation handle
        self.rotate_line = QGraphicsPathItem()
        line_path = QPainterPath()
        line_path.moveTo(0, 0)
        line_path.lineTo(rot_x, rot_y)
        self.rotate_line.setPath(line_path)
        self.rotate_line.setPen(QPen(ROTATE_HANDLE_COLOR, 1, Qt.PenStyle.DashLine))
        self.rotate_line.setZValue(9)
        self.addToGroup(self.rotate_line)

    def _draw_polygon_vertex_handles(self):
        """Draw draggable vertex handles at all polygon vertices."""
        point_pen = QPen(QColor(255, 255, 255), 2)
        point_brush = QBrush(HANDLE_COLOR)
        radius = 5

        for x, y in self.parking.points:
            handle = QGraphicsPathItem()
            path = QPainterPath()
            path.addEllipse(x - radius, y - radius, radius * 2, radius * 2)
            handle.setPath(path)
            handle.setPen(point_pen)
            handle.setBrush(point_brush)
            handle.setZValue(10)
            self.addToGroup(handle)
            self.vertex_handles.append(handle)

    def get_point_at(self, scene_pos: QPointF, tolerance: float = 10.0) -> int:
        """Return index of polygon vertex near scene_pos, or -1."""
        if not self.parking.is_polygon():
            return -1
        for i, (px, py) in enumerate(self.parking.points):
            if ((scene_pos.x() - px) ** 2 + (scene_pos.y() - py) ** 2) ** 0.5 <= tolerance:
                return i
        return -1

    def get_segment_at(self, scene_pos: QPointF, tolerance: float = 8.0) -> int:
        """Return index of first vertex of polygon edge near scene_pos, or -1."""
        if not self.parking.is_polygon():
            return -1
        n = len(self.parking.points)
        for i in range(n):
            x1, y1 = self.parking.points[i]
            x2, y2 = self.parking.points[(i + 1) % n]
            dx, dy = x2 - x1, y2 - y1
            length_sq = dx * dx + dy * dy
            if length_sq == 0:
                continue
            t = max(0, min(1, ((scene_pos.x() - x1) * dx + (scene_pos.y() - y1) * dy) / length_sq))
            proj_x = x1 + t * dx
            proj_y = y1 + t * dy
            if ((scene_pos.x() - proj_x) ** 2 + (scene_pos.y() - proj_y) ** 2) ** 0.5 <= tolerance:
                return i
        return -1

    def _get_handle_at(self, local_pos: QPointF) -> int:
        """
        Check if position is over a handle.

        Returns:
            -1: not over any handle
            0-3: corner handle index
            4: rotation handle
        """
        if self.parking.is_polygon():
            return -1

        tolerance = HANDLE_SIZE + 4

        # Check rotation handle first
        if self.rotate_handle:
            rect = self.rotate_handle.rect()
            center = rect.center()
            dist = math.sqrt((local_pos.x() - center.x())**2 + (local_pos.y() - center.y())**2)
            if dist <= tolerance:
                return 4

        # Check corner handles
        corners = self._get_rotated_corners()
        for i, (cx, cy) in enumerate(corners):
            dist = math.sqrt((local_pos.x() - cx)**2 + (local_pos.y() - cy)**2)
            if dist <= tolerance:
                return i

        return -1

    def itemChange(self, change, value):
        """Handle item changes (position, selection)."""
        if change == QGraphicsItemGroup.GraphicsItemChange.ItemPositionHasChanged:
            if not self.parking.is_polygon():
                pos = self.pos()
                self.parking.position = (pos.x(), pos.y())

            if self.parking_changed:
                self.parking_changed(self.parking)

        elif change == QGraphicsItemGroup.GraphicsItemChange.ItemSelectedHasChanged:
            self.selection_item.setVisible(self.isSelected())
            self._update_handles()

        return super().itemChange(change, value)

    def paint(self, painter, option, widget=None):
        """Override to customize appearance."""
        super().paint(painter, option, widget)

        # Draw parking symbol "P" in center
        if not self.parking.is_polygon():
            painter.setPen(QPen(QColor(0, 0, 150, 180), 2))
            font = painter.font()
            font.setBold(True)
            font.setPointSize(10)
            painter.setFont(font)
            painter.drawText(QPointF(-4, 4), "P")

    def hoverMoveEvent(self, event):
        """Update cursor based on hover position."""
        if self.parking.is_polygon():
            return super().hoverMoveEvent(event)

        handle = self._get_handle_at(event.pos())
        if handle == 4:
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif handle >= 0:
            # Diagonal resize cursors based on corner
            if handle in (0, 2):
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            else:
                self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif self.isSelected():
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

        super().hoverMoveEvent(event)

    def hoverEnterEvent(self, event):
        """Change cursor on hover."""
        if not self.parking.is_polygon():
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        """Restore cursor."""
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        """Handle mouse press - check for handle interaction."""
        if event.button() == Qt.MouseButton.LeftButton and not self.parking.is_polygon():
            handle = self._get_handle_at(event.pos())
            if handle >= 0 and self.isSelected():
                # Start handle drag
                self.dragging_handle = handle
                self.drag_start_pos = event.pos()
                self.drag_start_width = self.parking.width
                self.drag_start_length = self.parking.length
                self.drag_start_orientation = self.parking.orientation
                event.accept()
                return

            self.setCursor(Qt.CursorShape.ClosedHandCursor)

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle mouse move - resize or rotate if dragging handle."""
        if self.dragging_handle >= 0:
            if self.dragging_handle == 4:
                # Rotation
                self._handle_rotate(event.pos())
            else:
                # Resize
                self._handle_resize(event.pos())
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Handle mouse release."""
        if event.button() == Qt.MouseButton.LeftButton:
            if self.dragging_handle >= 0:
                self.dragging_handle = -1
                if self.parking_changed:
                    self.parking_changed(self.parking)
                event.accept()
                return

            if not self.parking.is_polygon():
                self.setCursor(Qt.CursorShape.OpenHandCursor)

        super().mouseReleaseEvent(event)

    def _handle_resize(self, pos: QPointF):
        """Handle corner drag for resizing."""
        if self.scale_factor <= 0:
            return

        # Calculate distance from center to drag position
        dx = pos.x()
        dy = pos.y()

        # Rotate back to get unrotated position
        angle_rad = math.radians(self.parking.orientation)
        cos_a = math.cos(-angle_rad)
        sin_a = math.sin(-angle_rad)
        ux = dx * cos_a - dy * sin_a
        uy = dx * sin_a + dy * cos_a

        # New half-dimensions based on corner being dragged
        # All corners resize symmetrically from center
        new_half_w = abs(ux)
        new_half_l = abs(uy)

        # Convert pixels to meters
        new_width = new_half_w * 2 * self.scale_factor
        new_length = new_half_l * 2 * self.scale_factor

        # Clamp to reasonable values
        new_width = max(1.0, min(20.0, new_width))
        new_length = max(1.0, min(30.0, new_length))

        self.parking.width = new_width
        self.parking.length = new_length

        self.update_graphics()

    def _handle_rotate(self, pos: QPointF):
        """Handle rotation handle drag."""
        # Calculate angle from center to mouse position
        angle_rad = math.atan2(pos.x(), -pos.y())
        angle_deg = math.degrees(angle_rad)

        # Normalize to 0-360
        angle_deg = angle_deg % 360
        if angle_deg < 0:
            angle_deg += 360

        self.parking.orientation = angle_deg

        self.update_graphics()

    def mouseDoubleClickEvent(self, event):
        """Handle double-click to open properties dialog."""
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def update_scale_factor(self, scale_factor: float):
        """Update the scale factor and refresh graphics."""
        self.scale_factor = scale_factor
        self.update_graphics()

    def set_selected(self, selected: bool):
        """Set selection state of the parking."""
        self.setSelected(selected)

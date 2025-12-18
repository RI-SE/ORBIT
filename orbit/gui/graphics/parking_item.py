"""
Graphics item for displaying parking spaces on the map.
"""

from PyQt6.QtWidgets import QGraphicsItemGroup, QGraphicsPathItem, QGraphicsPolygonItem
from PyQt6.QtGui import QPen, QColor, QBrush, QPainterPath, QPolygonF
from PyQt6.QtCore import Qt, QPointF
from orbit.models.parking import ParkingSpace, ParkingAccess, ParkingType
from typing import Optional
import math


# Color mapping by access type
ACCESS_COLORS = {
    ParkingAccess.STANDARD: QColor(100, 100, 255, 120),      # Light blue
    ParkingAccess.DISABLED: QColor(0, 100, 255, 120),        # Blue
    ParkingAccess.HANDICAPPED: QColor(0, 100, 255, 120),     # Blue
    ParkingAccess.PRIVATE: QColor(255, 100, 100, 120),       # Light red
    ParkingAccess.RESERVED: QColor(255, 165, 0, 120),        # Orange
    ParkingAccess.CUSTOMERS: QColor(100, 255, 100, 120),     # Light green
    ParkingAccess.COMPANY: QColor(180, 100, 180, 120),       # Purple
    ParkingAccess.PERMIT: QColor(255, 200, 100, 120),        # Yellow-orange
    ParkingAccess.WOMEN: QColor(255, 150, 200, 120),         # Pink
    ParkingAccess.RESIDENTS: QColor(100, 200, 150, 120),     # Teal
}

DEFAULT_COLOR = QColor(100, 100, 255, 120)


class ParkingGraphicsItem(QGraphicsItemGroup):
    """
    Graphics item representing a parking space on the map.

    Supports both point-based (rectangle) and polygon-based (lot outline) parking.
    Displays with color-coded access type and selection highlight.
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

        # Make item selectable, movable (for point parking only), and focusable
        self.setFlag(QGraphicsItemGroup.GraphicsItemFlag.ItemIsSelectable, True)
        # Only point parking (not polygon) should be draggable
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
            # Draw as polygon (parking lot outline)
            path = self._create_polygon_path()
        else:
            # Draw as oriented rectangle
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
        self.setToolTip(tooltip)

        # Update selection highlight
        self._update_selection_highlight(path)

    def _create_rectangle_path(self) -> QPainterPath:
        """Create a path for rectangle parking space (point-based)."""
        # Calculate size in pixels from meters
        if self.scale_factor > 0:
            width_px = self.parking.width / self.scale_factor
            length_px = self.parking.length / self.scale_factor
        else:
            # Default size when scale unknown
            width_px = 25
            length_px = 50

        path = QPainterPath()

        # Create rectangle centered at origin (position is handled by setPos)
        half_w = width_px / 2
        half_l = length_px / 2

        # Apply orientation rotation
        angle_rad = math.radians(self.parking.orientation)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)

        # Rectangle corners before rotation
        corners = [
            (-half_w, -half_l),
            (half_w, -half_l),
            (half_w, half_l),
            (-half_w, half_l),
        ]

        # Rotate corners
        rotated = []
        for x, y in corners:
            rx = x * cos_a - y * sin_a
            ry = x * sin_a + y * cos_a
            rotated.append((rx, ry))

        # Build path
        path.moveTo(rotated[0][0], rotated[0][1])
        for rx, ry in rotated[1:]:
            path.lineTo(rx, ry)
        path.closeSubpath()

        return path

    def _create_polygon_path(self) -> QPainterPath:
        """Create a path from polygon points (lot outline)."""
        path = QPainterPath()

        if not self.parking.points or len(self.parking.points) < 3:
            # Fallback to small rectangle at centroid
            return self._create_rectangle_path()

        # Draw polygon from points (already in scene coordinates)
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

    def itemChange(self, change, value):
        """Handle item changes (position, selection)."""
        if change == QGraphicsItemGroup.GraphicsItemChange.ItemPositionHasChanged:
            # Update parking position (for point parking only)
            if not self.parking.is_polygon():
                pos = self.pos()
                self.parking.position = (pos.x(), pos.y())

            # Notify about change
            if self.parking_changed:
                self.parking_changed(self.parking)

        elif change == QGraphicsItemGroup.GraphicsItemChange.ItemSelectedHasChanged:
            self.selection_item.setVisible(self.isSelected())

        return super().itemChange(change, value)

    def paint(self, painter, option, widget=None):
        """Override to customize appearance."""
        super().paint(painter, option, widget)

        # Draw parking symbol "P" if selected and not polygon
        if self.isSelected() and not self.parking.is_polygon():
            painter.setPen(QPen(QColor(0, 0, 150), 2))
            font = painter.font()
            font.setBold(True)
            font.setPointSize(12)
            painter.setFont(font)
            painter.drawText(QPointF(-5, 5), "P")

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
        """Handle mouse press."""
        if event.button() == Qt.MouseButton.LeftButton:
            if not self.parking.is_polygon():
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        """Handle mouse release."""
        if event.button() == Qt.MouseButton.LeftButton:
            if not self.parking.is_polygon():
                self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)

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

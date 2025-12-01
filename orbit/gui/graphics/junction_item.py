"""
Junction marker graphics item for ORBIT.

Provides visual representation of junctions on the image view.
"""

from typing import List, Optional

from PyQt6.QtWidgets import QGraphicsScene, QGraphicsTextItem
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPen, QColor, QBrush, QPolygonF

from orbit.models import Junction


class JunctionMarkerItem:
    """Graphics representation of a junction marker."""

    def __init__(self, junction: Junction, scene: QGraphicsScene) -> None:
        self.junction = junction
        self.scene = scene
        self.marker_items: List = []
        self.text_item: Optional[QGraphicsTextItem] = None
        self.selected: bool = False

        self.update_graphics()

    def update_graphics(self) -> None:
        """Update the graphics items based on junction data."""
        # Clear existing items
        for item in self.marker_items:
            self.scene.removeItem(item)
        self.marker_items.clear()
        if self.text_item:
            self.scene.removeItem(self.text_item)
            self.text_item = None

        if not self.junction.center_point:
            return

        x, y = self.junction.center_point

        # Draw junction marker (diamond shape)
        color = QColor(255, 0, 255)  # Magenta for junctions
        if self.selected:
            color = QColor(255, 255, 0)  # Yellow when selected

        pen = QPen(color, 3)
        brush = QBrush(QColor(255, 0, 255, 100))  # Semi-transparent
        if self.selected:
            brush = QBrush(QColor(255, 255, 0, 100))

        size = 20
        # Draw diamond (rotated square)
        polygon = QPolygonF()
        polygon.append(QPointF(x, y - size))  # Top
        polygon.append(QPointF(x + size, y))  # Right
        polygon.append(QPointF(x, y + size))  # Bottom
        polygon.append(QPointF(x - size, y))  # Left

        marker = self.scene.addPolygon(polygon, pen, brush)
        marker.setZValue(3)  # Above polylines
        self.marker_items.append(marker)

        # Add text label
        self.text_item = QGraphicsTextItem(self.junction.name)
        self.text_item.setDefaultTextColor(color)
        self.text_item.setPos(x + size + 5, y - 10)
        self.text_item.setZValue(3)
        self.scene.addItem(self.text_item)

    def set_selected(self, selected: bool) -> None:
        """Set selection state."""
        self.selected = selected
        self.update_graphics()

    def is_at_position(self, pos: QPointF, tolerance: float = 20.0) -> bool:
        """Check if position is near the junction marker."""
        if not self.junction.center_point:
            return False

        x, y = self.junction.center_point
        dx = pos.x() - x
        dy = pos.y() - y
        dist = (dx * dx + dy * dy) ** 0.5
        return dist <= tolerance

    def remove(self) -> None:
        """Remove all graphics items from scene."""
        for item in self.marker_items:
            if item.scene() == self.scene:
                self.scene.removeItem(item)
        self.marker_items.clear()
        if self.text_item and self.text_item.scene() == self.scene:
            self.scene.removeItem(self.text_item)
            self.text_item = None

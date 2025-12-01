"""
Interactive lane polygon for ORBIT.

Provides clickable, hoverable lane polygons for the image view.
"""

from typing import List, TYPE_CHECKING

from PyQt6.QtWidgets import QGraphicsPolygonItem
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QPen, QColor, QBrush, QPolygonF

if TYPE_CHECKING:
    from ..image_view import ImageView


class InteractiveLanePolygon(QGraphicsPolygonItem):
    """Interactive polygon for a lane section with hover and click support."""

    # Default alpha values (0-255)
    DEFAULT_ALPHA = 77    # ~30% opacity
    HOVER_ALPHA = 204     # ~80% opacity
    SELECTED_ALPHA = 204  # ~80% opacity (same as hover)

    def __init__(self, lane_id: int, section_number: int, road_id: str,
                 polygon_points: List[tuple], parent_view: 'ImageView',
                 is_connecting_road: bool = False) -> None:
        """
        Create an interactive lane polygon.

        Args:
            lane_id: Lane ID (positive=right, negative=left, 0=center)
            section_number: Section number this polygon belongs to
            road_id: Road ID this polygon belongs to (or connecting road ID if is_connecting_road=True)
            polygon_points: List of (x, y) points forming the lane polygon
            parent_view: Parent ImageView for signaling
            is_connecting_road: True if this is a connecting road lane, False for regular road lane
        """
        # Create polygon
        polygon = QPolygonF()
        for x, y in polygon_points:
            polygon.append(QPointF(x, y))

        super().__init__(polygon)

        # Store metadata
        self.lane_id = lane_id
        self.section_number = section_number
        self.road_id = road_id
        self.parent_view = parent_view
        self.is_selected = False
        self.is_connecting_road = is_connecting_road

        # Choose base color based on lane side (OpenDRIVE convention)
        if lane_id < 0:
            # Right lanes (negative IDs in OpenDRIVE): light green
            self.base_color = QColor(100, 255, 100)
        elif lane_id > 0:
            # Left lanes (positive IDs in OpenDRIVE): light blue
            self.base_color = QColor(100, 180, 255)
        else:
            # Center lane (ID = 0)
            self.base_color = QColor(200, 200, 200)

        # Set appearance
        self.setAcceptHoverEvents(True)
        self.setZValue(0.5)  # Between image (0) and polylines (1+)

        # Set default appearance
        self._update_appearance()

    def _update_appearance(self) -> None:
        """Update brush and pen based on current state."""
        if self.is_selected:
            # Selected: dark border and higher opacity
            pen = QPen(QColor(0, 0, 0, 255), 3)  # Black border, 3px width
            self.setPen(pen)
            self._update_brush(self.SELECTED_ALPHA)
        else:
            # Not selected: default gray border and default opacity
            pen = QPen(QColor(200, 200, 200, 150), 1)
            self.setPen(pen)
            self._update_brush(self.DEFAULT_ALPHA)

    def _update_brush(self, alpha: int) -> None:
        """Update the brush with the specified alpha value."""
        color = QColor(self.base_color)
        color.setAlpha(alpha)
        self.setBrush(QBrush(color))

    def set_selected(self, selected: bool) -> None:
        """Set selection state and update appearance."""
        self.is_selected = selected
        self._update_appearance()
        if not selected:
            # If not selected, restore default opacity
            self._update_brush(self.DEFAULT_ALPHA)

    def hoverEnterEvent(self, event) -> None:
        """Handle mouse enter - make more opaque."""
        if not self.is_selected:
            self._update_brush(self.HOVER_ALPHA)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        """Handle mouse leave - restore default transparency."""
        if not self.is_selected:
            self._update_brush(self.DEFAULT_ALPHA)
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event) -> None:
        """Handle mouse click - emit selection signal."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Emit signal to select this lane in the tree
            if self.is_connecting_road:
                # Connecting road lane - emit connecting_road_lane_clicked
                if hasattr(self.parent_view, 'connecting_road_lane_clicked'):
                    self.parent_view.connecting_road_lane_clicked.emit(
                        self.road_id,  # This is the connecting road ID
                        self.lane_id
                    )
            else:
                # Regular road lane - emit lane_segment_clicked
                if hasattr(self.parent_view, 'lane_segment_clicked'):
                    self.parent_view.lane_segment_clicked.emit(
                        self.road_id,
                        self.section_number,
                        self.lane_id
                    )
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        """Handle double-click to open lane properties dialog."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Emit signal to open lane properties dialog
            if self.is_connecting_road:
                # Connecting road lane - emit connecting_road_lane_edit_requested
                if hasattr(self.parent_view, 'connecting_road_lane_edit_requested'):
                    self.parent_view.connecting_road_lane_edit_requested.emit(
                        self.road_id,  # This is the connecting road ID
                        self.lane_id
                    )
            else:
                # Regular road lane - emit lane_edit_requested
                if hasattr(self.parent_view, 'lane_edit_requested'):
                    self.parent_view.lane_edit_requested.emit(
                        self.road_id,
                        self.section_number,
                        self.lane_id
                    )
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def set_visible(self, visible: bool) -> None:
        """Set visibility of the lane polygon."""
        self.setVisible(visible)

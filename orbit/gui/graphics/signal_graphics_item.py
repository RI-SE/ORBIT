"""
Graphics item for displaying traffic signals on the map.
"""

from PyQt6.QtWidgets import QGraphicsItemGroup, QGraphicsPixmapItem, QGraphicsPathItem
from PyQt6.QtGui import QPen, QColor, QPainter, QPixmap
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QPointF
from orbit.models.signal import Signal, SignalType
from orbit.models.sign_library_manager import SignLibraryManager
from .signal_graphics import create_signal_pixmap, create_orientation_indicator


class SignalGraphicsItem(QGraphicsItemGroup):
    """
    Graphics item representing a traffic signal on the map.

    Displays the signal icon with an orientation indicator.
    Draggable and selectable.
    """

    def __init__(self, signal: Signal, project=None, parent=None):
        super().__init__(parent)
        self.signal = signal
        self.project = project  # Need project to look up road for orientation calculation
        self.signal_changed = None  # Will be set to a callback function

        # Make item selectable, movable, and focusable
        self.setFlag(QGraphicsItemGroup.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItemGroup.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItemGroup.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)

        # Create icon
        self.icon_item = QGraphicsPixmapItem()
        pixmap = self._get_signal_pixmap()
        self.icon_item.setPixmap(pixmap)
        # Center the pixmap at the signal position
        self.icon_item.setOffset(-pixmap.width() / 2, -pixmap.height() / 2)
        self.addToGroup(self.icon_item)

        # Create orientation indicator
        self.orientation_item = QGraphicsPathItem()
        self.orientation_item.setPen(QPen(QColor(0, 0, 200, 180), 2))
        self.addToGroup(self.orientation_item)

        # Create selection highlight (circle)
        self.selection_item = QGraphicsPathItem()
        self.selection_item.setPen(QPen(QColor(255, 200, 0, 200), 2, Qt.PenStyle.DashLine))
        self.selection_item.setVisible(False)
        self.addToGroup(self.selection_item)

        # Set position and update graphics
        self.setPos(signal.position[0], signal.position[1])
        self.update_graphics()

    def _get_visual_angle(self) -> float:
        """
        Calculate visual angle for displaying the signal orientation indicator.

        Returns:
            Visual angle in degrees
        """
        # If signal is attached to a road and we have project reference, calculate from road geometry
        if self.signal.road_id and self.project:
            road = self.project.get_road(self.signal.road_id)
            if road and road.centerline_id:
                centerline = self.project.get_polyline(road.centerline_id)
                if centerline and centerline.points:
                    return self.signal.calculate_visual_angle(centerline.points)

        # No road reference - use default orientation (perpendicular to north + h_offset)
        # 90° = north, plus h_offset rotation
        import math
        return 90.0 + math.degrees(self.signal.h_offset)

    def _get_signal_pixmap(self, size: int = 32) -> QPixmap:
        """
        Get the appropriate pixmap for this signal.

        For LIBRARY_SIGN type, loads from the sign library.
        For other types, generates a placeholder.
        """
        if self.signal.type == SignalType.LIBRARY_SIGN:
            # Try to load from library
            if self.signal.library_id and self.signal.sign_id:
                manager = SignLibraryManager.instance()
                library = manager.get_library(self.signal.library_id)
                if library:
                    sign_def = library.get_sign(self.signal.sign_id)
                    if sign_def:
                        image_path = library.get_sign_image_path(sign_def)
                        if image_path and image_path.exists():
                            pixmap = QPixmap(str(image_path))
                            return pixmap.scaled(
                                size, size,
                                Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation
                            )
            # Fallback for library sign without valid library
            return create_signal_pixmap(SignalType.GIVE_WAY, size=size)

        if self.signal.type == SignalType.CUSTOM:
            # Custom sign - use generic placeholder
            return create_signal_pixmap(SignalType.GIVE_WAY, size=size)

        # Legacy type - use existing placeholder generation
        return create_signal_pixmap(self.signal.type, self.signal.value, size=size)

    def update_graphics(self):
        """Update visual representation based on signal properties."""
        # Update icon if type/value changed
        pixmap = self._get_signal_pixmap()
        self.icon_item.setPixmap(pixmap)
        self.icon_item.setOffset(-pixmap.width() / 2, -pixmap.height() / 2)

        # Calculate visual angle for orientation indicator
        visual_angle = self._get_visual_angle()

        # Update orientation indicator
        orientation_path = create_orientation_indicator(visual_angle, length=25)
        self.orientation_item.setPath(orientation_path)

        # Update selection highlight
        from PyQt6.QtGui import QPainterPath
        selection_path = QPainterPath()
        selection_path.addEllipse(-20, -20, 40, 40)
        self.selection_item.setPath(selection_path)
        self.selection_item.setVisible(self.isSelected())

    def itemChange(self, change, value):
        """Handle item changes (position, selection)."""
        if change == QGraphicsItemGroup.GraphicsItemChange.ItemPositionHasChanged:
            # Update signal position
            pos = self.pos()
            self.signal.position = (pos.x(), pos.y())
            # Notify about change
            if self.signal_changed:
                self.signal_changed(self.signal)

        elif change == QGraphicsItemGroup.GraphicsItemChange.ItemSelectedHasChanged:
            # Update selection highlight visibility
            self.selection_item.setVisible(self.isSelected())

        return super().itemChange(change, value)

    def paint(self, painter, option, widget=None):
        """Override to customize appearance."""
        # Don't draw default selection rectangle
        super().paint(painter, option, widget)

    def hoverEnterEvent(self, event):
        """Change cursor on hover."""
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        """Restore cursor."""
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        """Handle mouse press."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        """Handle mouse release."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Handle double-click to open properties dialog."""
        if event.button() == Qt.MouseButton.LeftButton:
            # This will be connected to open properties dialog
            # For now, just accept the event
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

"""
Graphics item for displaying roadside objects on the map.
"""

from PyQt6.QtWidgets import QGraphicsItemGroup, QGraphicsPathItem, QGraphicsItem
from PyQt6.QtGui import QPen, QColor, QPainter, QBrush
from PyQt6.QtCore import Qt, QPointF
from models.object import RoadObject, ObjectType
from gui.object_graphics import (
    get_object_color, create_lamppost_path, create_guardrail_path,
    create_polygon_path, create_building_path, create_tree_circle_path,
    create_cone_path, create_bush_path, draw_dimension_label, rotate_path
)
from typing import Optional


class ObjectGraphicsItem(QGraphicsItemGroup):
    """
    Graphics item representing a roadside object on the map.

    Displays the object with appropriate shape, color, and dimensions.
    Supports selection, dragging, and hover effects.
    """

    def __init__(self, obj: RoadObject, scale_factor: float = 0.0, parent=None):
        super().__init__(parent)
        self.obj = obj
        self.scale_factor = scale_factor  # Meters per pixel
        self.object_changed = None  # Callback function for changes

        # Main shape item
        self.shape_item = QGraphicsPathItem()
        self.addToGroup(self.shape_item)

        # Selection highlight
        self.selection_item = QGraphicsPathItem()
        self.selection_item.setPen(QPen(QColor(255, 200, 0, 200), 2, Qt.PenStyle.DashLine))
        self.selection_item.setVisible(False)
        self.addToGroup(self.selection_item)

        # Point handles for polyline objects (guardrails)
        self.point_items = []
        self.visible_point_indices = []  # Track which points have visible handles

        # Make item selectable, movable (only for point objects), and focusable
        self.setFlag(QGraphicsItemGroup.GraphicsItemFlag.ItemIsSelectable, True)
        # Polyline objects (guardrails) and polygon buildings should not be draggable as a whole
        # Instead, individual points are dragged
        is_polygon_building = (obj.type == ObjectType.BUILDING and obj.points and len(obj.points) >= 3)
        if obj.type.get_shape_type() != "polyline" and not is_polygon_building:
            self.setFlag(QGraphicsItemGroup.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItemGroup.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)

        # Set position and update graphics
        # Don't use setPos for polylines or polygon buildings - they're in scene coordinates
        if obj.type.get_shape_type() != "polyline" and not is_polygon_building:
            self.setPos(obj.position[0], obj.position[1])

        self.update_graphics()

    def update_graphics(self):
        """Update visual representation based on object properties."""
        shape_type = self.obj.type.get_shape_type()
        color = get_object_color(self.obj.type)

        # Clear old point handles
        for point_item in self.point_items:
            self.removeFromGroup(point_item)
        self.point_items.clear()
        self.visible_point_indices.clear()

        if shape_type == "cylinder":  # Lamppost
            path = create_lamppost_path(scale=1.0)
            # Apply orientation
            if self.obj.type.has_orientation():
                path = rotate_path(path, self.obj.orientation)

        elif shape_type == "polyline":  # Guardrail
            # Use actual points from object
            path = create_guardrail_path(self.obj.points, width_pixels=5.0)
            # Don't use setPos for polylines - they're in scene coordinates

        elif shape_type == "rectangle":  # Building
            # Check if building has polygon points (from OSM)
            if self.obj.points and len(self.obj.points) >= 3:
                # Draw building as polygon using actual OSM shape
                path = create_polygon_path(self.obj.points)
                # Don't use setPos for polygon buildings - they're in scene coordinates
            else:
                # Fallback: draw as rectangle using dimensions
                width = self.obj.dimensions.get('width', 10.0)
                length = self.obj.dimensions.get('length', 8.0)
                path = create_building_path(width, length, self.scale_factor)
                # Apply orientation
                if self.obj.type.has_orientation():
                    path = rotate_path(path, self.obj.orientation)

        elif shape_type == "circle":  # Trees, bush
            radius = self.obj.dimensions.get('radius', 1.0)
            path = create_tree_circle_path(radius, self.scale_factor)

        elif shape_type == "cone":  # Conifer
            radius = self.obj.dimensions.get('radius', 1.5)
            path = create_cone_path(radius, self.scale_factor)

        else:
            # Fallback: small circle
            path = create_tree_circle_path(1.0, self.scale_factor)

        # Set path and appearance
        self.shape_item.setPath(path)
        self.shape_item.setPen(QPen(color.darker(120), 2))
        self.shape_item.setBrush(QBrush(color))

        # Draw point handles for polyline objects (guardrails)
        if shape_type == "polyline" and self.obj.points:
            self._draw_point_handles()

        # Update selection highlight
        self._update_selection_highlight(path)

    def _draw_point_handles(self):
        """Draw visible handles at guardrail points for editing (max one every 100px)."""
        # Use bright cyan color for point handles (contrasts well with dark blue guardrail)
        point_color = QColor(0, 255, 255)  # Cyan
        point_pen = QPen(QColor(255, 255, 255), 1)  # White outline

        # Make points more visible when selected
        if self.isSelected():
            point_color = QColor(255, 165, 0)  # Orange when guardrail is selected
            point_pen = QPen(QColor(255, 255, 255), 2)  # Thicker white outline

        point_brush = QBrush(point_color)
        radius = 3  # Smaller radius (6px diameter)

        # Filter points to show handles at most every 100px
        # Always show first and last point
        last_handle_pos = None
        min_distance = 100.0

        for i, (x, y) in enumerate(self.obj.points):
            # Always show first and last point
            show_handle = (i == 0 or i == len(self.obj.points) - 1)

            # For middle points, only show if far enough from last handle
            if not show_handle and last_handle_pos is not None:
                dist = ((x - last_handle_pos[0]) ** 2 + (y - last_handle_pos[1]) ** 2) ** 0.5
                show_handle = dist >= min_distance
            elif not show_handle and last_handle_pos is None:
                # First middle point after start
                dist_from_start = ((x - self.obj.points[0][0]) ** 2 +
                                  (y - self.obj.points[0][1]) ** 2) ** 0.5
                show_handle = dist_from_start >= min_distance

            if not show_handle:
                continue

            # Track this point index as having a visible handle
            self.visible_point_indices.append(i)

            # Create point handle as ellipse
            point_item = QGraphicsPathItem()
            from PyQt6.QtGui import QPainterPath
            path = QPainterPath()
            path.addEllipse(x - radius, y - radius, radius * 2, radius * 2)
            point_item.setPath(path)
            point_item.setPen(point_pen)
            point_item.setBrush(point_brush)

            # Add to group and track
            self.addToGroup(point_item)
            self.point_items.append(point_item)

            # Update last handle position
            last_handle_pos = (x, y)

    def _update_selection_highlight(self, base_path):
        """Update selection highlight to match object shape."""
        from PyQt6.QtGui import QPainterPath, QPainterPathStroker

        # Create a slightly larger version of the shape for selection
        stroker = QPainterPathStroker()
        stroker.setWidth(10)
        highlight_path = stroker.createStroke(base_path)

        self.selection_item.setPath(highlight_path)
        self.selection_item.setVisible(self.isSelected())

    def itemChange(self, change, value):
        """Handle item changes (position, selection)."""
        if change == QGraphicsItemGroup.GraphicsItemChange.ItemPositionHasChanged:
            # Update object position (for point objects only)
            if self.obj.type.get_shape_type() != "polyline":
                pos = self.pos()
                self.obj.position = (pos.x(), pos.y())

            # Notify about change
            if self.object_changed:
                self.object_changed(self.obj)

        elif change == QGraphicsItemGroup.GraphicsItemChange.ItemSelectedHasChanged:
            # Update selection highlight visibility
            self.selection_item.setVisible(self.isSelected())

        return super().itemChange(change, value)

    def paint(self, painter, option, widget=None):
        """Override to customize appearance."""
        super().paint(painter, option, widget)

        # Draw dimension labels if selected
        if self.isSelected():
            # Calculate label position
            if self.obj.type.get_shape_type() == "polyline":
                # For guardrails, show label at midpoint
                if self.obj.points and len(self.obj.points) >= 2:
                    mid_idx = len(self.obj.points) // 2
                    label_pos = QPointF(self.obj.points[mid_idx][0], self.obj.points[mid_idx][1])
                else:
                    label_pos = QPointF(0, 0)
            else:
                # For point objects, label below shape
                label_pos = QPointF(0, 0)

            # Get bounding rect to offset label appropriately
            bounds = self.shape_item.path().boundingRect()
            offset_y = bounds.height() / 2 + 10

            draw_dimension_label(painter, self.obj, self.scale_factor, label_pos, offset_y)

    def hoverEnterEvent(self, event):
        """Change cursor on hover."""
        if self.obj.type.get_shape_type() != "polyline":
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

    def update_scale_factor(self, scale_factor: float):
        """
        Update the scale factor and refresh graphics.

        Args:
            scale_factor: New meters per pixel scale
        """
        self.scale_factor = scale_factor
        self.update_graphics()

    def get_point_at(self, scene_pos: QPointF, tolerance: float = 10.0) -> int:
        """
        Check if scene position is near any visible guardrail point handle.

        Args:
            scene_pos: Position in scene coordinates
            tolerance: Distance tolerance in pixels (default 10 to match point handle size)

        Returns:
            Index of point if found, -1 otherwise
        """
        if self.obj.type.get_shape_type() != "polyline":
            return -1

        # Only check points that have visible handles
        for i in self.visible_point_indices:
            if i < len(self.obj.points):
                px, py = self.obj.points[i]
                dist = ((scene_pos.x() - px) ** 2 + (scene_pos.y() - py) ** 2) ** 0.5
                if dist <= tolerance:
                    return i

        return -1

    def get_segment_at(self, scene_pos: QPointF, tolerance: float = 8.0) -> int:
        """
        Check if scene position is near any guardrail segment.

        Args:
            scene_pos: Position in scene coordinates
            tolerance: Distance tolerance in pixels

        Returns:
            Index of first point of segment if found, -1 otherwise
        """
        if self.obj.type.get_shape_type() != "polyline":
            return -1

        for i in range(len(self.obj.points) - 1):
            x1, y1 = self.obj.points[i]
            x2, y2 = self.obj.points[i + 1]

            # Point to line segment distance
            dx = x2 - x1
            dy = y2 - y1
            length_sq = dx * dx + dy * dy

            if length_sq == 0:
                continue

            t = max(0, min(1, ((scene_pos.x() - x1) * dx + (scene_pos.y() - y1) * dy) / length_sq))
            proj_x = x1 + t * dx
            proj_y = y1 + t * dy

            dist = ((scene_pos.x() - proj_x) ** 2 + (scene_pos.y() - proj_y) ** 2) ** 0.5

            if dist <= tolerance:
                return i

        return -1

    def set_selected(self, selected: bool):
        """
        Set selection state of the object.

        Args:
            selected: True to select, False to deselect
        """
        self.setSelected(selected)

"""
Graphics item for displaying roadside objects on the map.
"""

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QPen
from PyQt6.QtWidgets import QGraphicsItemGroup, QGraphicsPathItem

from orbit.models.object import ObjectType, RoadObject

from .object_graphics import (
    create_building_path,
    create_cone_path,
    create_guardrail_path,
    create_lamppost_path,
    create_polygon_path,
    create_tree_circle_path,
    draw_dimension_label,
    get_object_color,
    rotate_path,
)


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

        # Point handles for polyline/polygon objects
        self.point_items = []
        self.visible_point_indices = []  # Track which points have visible handles

        # Custom selection flag — avoids Qt's native selection mechanism which
        # would draw an unwanted bounding-box rectangle and get cleared by
        # scene background-click handling (breaks panning over large polygons).
        self._is_selected = False

        # Make item movable (only for point objects) and geometry-change-aware.
        # ItemIsSelectable is intentionally NOT set so Qt never draws a dashed
        # selection rect and never deselects on background clicks.
        # Polyline objects (guardrails) and polygon objects should not be draggable as a whole
        is_polygon = (obj.type.get_shape_type() == "polygon" and obj.points and len(obj.points) >= 3)
        is_polygon_building = (obj.type == ObjectType.BUILDING and obj.points and len(obj.points) >= 3)
        if obj.type.get_shape_type() != "polyline" and not is_polygon_building and not is_polygon:
            self.setFlag(QGraphicsItemGroup.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItemGroup.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)

        # Set position and update graphics
        # Don't use setPos for polylines or polygon objects - they're in scene coordinates
        if obj.type.get_shape_type() != "polyline" and not is_polygon_building and not is_polygon:
            self.setPos(obj.position[0], obj.position[1])

        self.update_graphics()

    def _is_polygon_with_points(self) -> bool:
        """Check if this object is a polygon type with actual polygon points."""
        shape = self.obj.type.get_shape_type()
        has_points = self.obj.points and len(self.obj.points) >= 3
        if shape == "polygon" and has_points:
            return True
        if shape == "rectangle" and has_points:
            # Building with OSM polygon points
            return True
        return False

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

        elif shape_type == "polygon":  # Land use areas, parking
            if self.obj.points and len(self.obj.points) >= 3:
                path = create_polygon_path(self.obj.points)
            else:
                path = create_tree_circle_path(1.0, self.scale_factor)

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

        # Draw vertex handles for polygon objects when selected
        if self._is_polygon_with_points() and self._is_selected:
            self._draw_polygon_vertex_handles()

        # Update selection highlight
        self._update_selection_highlight(path)

    def _draw_point_handles(self):
        """Draw visible handles at guardrail points for editing (max one every 100px)."""
        # Use bright cyan color for point handles (contrasts well with dark blue guardrail)
        point_color = QColor(0, 255, 255)  # Cyan
        point_pen = QPen(QColor(255, 255, 255), 1)  # White outline

        # Make points more visible when selected
        if self._is_selected:
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

    def _draw_polygon_vertex_handles(self):
        """Draw draggable vertex handles at all polygon vertices (shown when selected)."""
        point_color = QColor(255, 165, 0)  # Orange
        point_pen = QPen(QColor(255, 255, 255), 2)  # White outline
        point_brush = QBrush(point_color)
        radius = 5  # Slightly larger than polyline handles for easier grabbing

        for i, (x, y) in enumerate(self.obj.points):
            self.visible_point_indices.append(i)

            point_item = QGraphicsPathItem()
            from PyQt6.QtGui import QPainterPath
            path = QPainterPath()
            path.addEllipse(x - radius, y - radius, radius * 2, radius * 2)
            point_item.setPath(path)
            point_item.setPen(point_pen)
            point_item.setBrush(point_brush)

            self.addToGroup(point_item)
            self.point_items.append(point_item)

    def _update_selection_highlight(self, base_path):
        """Update selection highlight to match object shape."""
        from PyQt6.QtGui import QPainterPathStroker

        # Create a slightly larger version of the shape for selection
        stroker = QPainterPathStroker()
        stroker.setWidth(10)
        highlight_path = stroker.createStroke(base_path)

        self.selection_item.setPath(highlight_path)
        self.selection_item.setVisible(self._is_selected)

    def itemChange(self, change, value):
        """Handle item changes (position, selection)."""
        if change == QGraphicsItemGroup.GraphicsItemChange.ItemPositionHasChanged:
            # Update object position (for point objects only)
            if self.obj.type.get_shape_type() != "polyline":
                pos = self.pos()
                self.obj.position = (pos.x(), pos.y())
                # Clear geo_position since user manually repositioned the object.
                # Otherwise the stale geo_position would override the dragged
                # position when the project is reloaded.
                self.obj.geo_position = None

            # Notify about change
            if self.object_changed:
                self.object_changed(self.obj)

        return super().itemChange(change, value)

    def paint(self, painter, option, widget=None):
        """Override to draw dimension labels when selected."""
        super().paint(painter, option, widget)

        # Draw dimension labels if selected
        if self._is_selected:
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
        shape = self.obj.type.get_shape_type()
        if shape not in ("polyline",) and not self._is_polygon_with_points():
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        """Restore cursor."""
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        """Handle mouse press.

        For polygon objects (buildings, land areas), selection and vertex
        dragging are handled entirely by the ImageView mouse handler.
        We pass the event through so the view's ScrollHandDrag can pan.
        """
        if self._is_polygon_with_points() and event.button() == Qt.MouseButton.LeftButton:
            event.ignore()  # Let view handle panning and selection
            return
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
        Check if scene position is near any visible point handle.

        Works for both polyline (guardrail) and polygon objects.

        Args:
            scene_pos: Position in scene coordinates
            tolerance: Distance tolerance in pixels

        Returns:
            Index of point if found, -1 otherwise
        """
        shape = self.obj.type.get_shape_type()
        if shape not in ("polyline",) and not self._is_polygon_with_points():
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
        Check if scene position is near any segment (edge between consecutive vertices).

        Works for both polyline and polygon objects. For polygons, also checks the
        closing edge from the last vertex back to the first.

        Args:
            scene_pos: Position in scene coordinates
            tolerance: Distance tolerance in pixels

        Returns:
            Index of first point of segment if found, -1 otherwise
        """
        shape = self.obj.type.get_shape_type()
        if shape not in ("polyline",) and not self._is_polygon_with_points():
            return -1

        n = len(self.obj.points)
        # For polygons, include the closing edge (last→first)
        num_segments = n if self._is_polygon_with_points() else n - 1

        for i in range(num_segments):
            x1, y1 = self.obj.points[i]
            x2, y2 = self.obj.points[(i + 1) % n]

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
        self._is_selected = selected
        self.selection_item.setVisible(selected)
        if self._is_polygon_with_points():
            self.update_graphics()  # Refresh vertex handles

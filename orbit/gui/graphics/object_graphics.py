"""
Graphics rendering functions for roadside objects.

Creates visual representations of objects (buildings, trees, lampposts, etc.)
with appropriate shapes, colors, and dimension labels.
"""

from PyQt6.QtGui import QPainterPath, QColor, QFont, QPainter, QPolygonF
from PyQt6.QtCore import Qt, QPointF, QRectF
from orbit.models.object import RoadObject, ObjectType
import math
from typing import Tuple, Optional


# Color scheme (30% opacity = 77 alpha, consistent with lanes/parking)
COLORS = {
    ObjectType.BUILDING: QColor(150, 150, 150, 77),       # Gray
    ObjectType.TREE_BROADLEAF: QColor(34, 139, 34, 77),   # Forest green
    ObjectType.TREE_CONIFER: QColor(34, 139, 34, 77),     # Forest green
    ObjectType.BUSH: QColor(34, 139, 34, 77),             # Forest green
    ObjectType.GUARDRAIL: QColor(25, 25, 112, 77),        # Dark blue
    ObjectType.LAMPPOST: QColor(255, 255, 255, 77),       # White
}


def get_object_color(object_type: ObjectType) -> QColor:
    """Get the display color for an object type."""
    return COLORS.get(object_type, QColor(128, 128, 128, 77))


def create_lamppost_path(scale: float = 1.0) -> QPainterPath:
    """
    Create path for lamppost (small circle with orientation line).

    Args:
        scale: Scale factor for the lamppost size

    Returns:
        QPainterPath for the lamppost
    """
    path = QPainterPath()

    # Small circle for pole base
    radius = 3.0 * scale
    path.addEllipse(-radius, -radius, radius * 2, radius * 2)

    # Orientation line (pointing direction)
    line_length = 10.0 * scale
    path.moveTo(0, 0)
    path.lineTo(line_length, 0)

    return path


def create_guardrail_path(points: list, width_pixels: float = 5.0) -> QPainterPath:
    """
    Create path for guardrail (polyline with width).

    Args:
        points: List of (x, y) tuples in scene coordinates
        width_pixels: Visual width of the guardrail line

    Returns:
        QPainterPath for the guardrail
    """
    path = QPainterPath()

    if not points or len(points) < 2:
        return path

    # Draw main line
    path.moveTo(points[0][0], points[0][1])
    for px, py in points[1:]:
        path.lineTo(px, py)

    return path


def create_polygon_path(points: list) -> QPainterPath:
    """
    Create path for polygon (e.g., building outline from OSM).

    Args:
        points: List of (x, y) tuples in scene coordinates defining the polygon

    Returns:
        QPainterPath for the filled polygon
    """
    path = QPainterPath()

    if not points or len(points) < 3:
        return path

    # Start at first point
    path.moveTo(points[0][0], points[0][1])

    # Draw lines to all other points
    for px, py in points[1:]:
        path.lineTo(px, py)

    # Close the polygon
    path.closeSubpath()

    return path


def create_building_path(width: float, length: float, scale_factor: float) -> QPainterPath:
    """
    Create path for building (rectangle).

    Args:
        width: Building width in meters
        length: Building length in meters
        scale_factor: Meters per pixel scale

    Returns:
        QPainterPath for the building (centered at origin)
    """
    path = QPainterPath()

    # Convert meters to pixels
    w_px = width / scale_factor if scale_factor > 0 else width * 10
    l_px = length / scale_factor if scale_factor > 0 else length * 10

    # Draw rectangle centered at origin
    path.addRect(-w_px / 2, -l_px / 2, w_px, l_px)

    return path


def create_tree_circle_path(radius: float, scale_factor: float) -> QPainterPath:
    """
    Create path for tree (circle).

    Args:
        radius: Tree crown radius in meters
        scale_factor: Meters per pixel scale

    Returns:
        QPainterPath for the tree (centered at origin)
    """
    path = QPainterPath()

    # Convert meters to pixels
    r_px = radius / scale_factor if scale_factor > 0 else radius * 10

    # Draw circle centered at origin
    path.addEllipse(-r_px, -r_px, r_px * 2, r_px * 2)

    return path


def create_cone_path(radius: float, scale_factor: float) -> QPainterPath:
    """
    Create path for conifer tree (cone/triangle from top view).

    Args:
        radius: Base radius in meters
        scale_factor: Meters per pixel scale

    Returns:
        QPainterPath for the cone (centered at origin)
    """
    path = QPainterPath()

    # Convert meters to pixels
    r_px = radius / scale_factor if scale_factor > 0 else radius * 10

    # Create triangle (cone from top view)
    # Point up (north)
    path.moveTo(0, -r_px * 1.5)  # Top point
    path.lineTo(-r_px, r_px)     # Bottom left
    path.lineTo(r_px, r_px)      # Bottom right
    path.closeSubpath()

    return path


def create_bush_path(radius: float, scale_factor: float) -> QPainterPath:
    """
    Create path for bush (small circle).

    Args:
        radius: Bush radius in meters
        scale_factor: Meters per pixel scale

    Returns:
        QPainterPath for the bush (centered at origin)
    """
    # Same as tree circle, just typically smaller
    return create_tree_circle_path(radius, scale_factor)


def create_dimension_label(obj: RoadObject, scale_factor: float) -> str:
    """
    Create dimension label text for an object.

    Args:
        obj: RoadObject instance
        scale_factor: Meters per pixel scale

    Returns:
        Formatted dimension string
    """
    dims = obj.dimensions

    if obj.type == ObjectType.LAMPPOST:
        diameter = dims.get('radius', 0) * 2
        height = dims.get('height', 0)
        return f"Ø{diameter:.2f}m × {height:.1f}m"

    elif obj.type == ObjectType.GUARDRAIL:
        height = dims.get('height', 0)
        if obj.validity_length:
            # Convert pixels to meters if we have scale
            length_m = obj.validity_length * scale_factor if scale_factor > 0 else obj.validity_length
            return f"L={length_m:.1f}m H={height:.1f}m"
        return f"H={height:.1f}m"

    elif obj.type == ObjectType.BUILDING:
        width = dims.get('width', 0)
        length = dims.get('length', 0)
        height = dims.get('height', 0)
        return f"{width:.1f}m × {length:.1f}m × {height:.1f}m"

    elif obj.type in (ObjectType.TREE_BROADLEAF, ObjectType.TREE_CONIFER, ObjectType.BUSH):
        diameter = dims.get('radius', 0) * 2
        height = dims.get('height', 0)
        return f"Ø{diameter:.1f}m × {height:.1f}m"

    return ""


def draw_dimension_label(painter: QPainter, obj: RoadObject, scale_factor: float,
                         position: QPointF, offset_y: float = 0):
    """
    Draw dimension label near an object.

    Args:
        painter: QPainter to draw with
        obj: RoadObject instance
        scale_factor: Meters per pixel scale
        position: Position to draw label (scene coordinates)
        offset_y: Vertical offset from position in pixels
    """
    label_text = create_dimension_label(obj, scale_factor)
    if not label_text:
        return

    # Set font
    font = QFont("Arial", 9)
    painter.setFont(font)

    # Calculate text bounds
    fm = painter.fontMetrics()
    text_rect = fm.boundingRect(label_text)
    text_width = text_rect.width()
    text_height = text_rect.height()

    # Position label below object
    label_x = position.x() - text_width / 2
    label_y = position.y() + offset_y + text_height

    # Draw background
    padding = 2
    bg_rect = QRectF(label_x - padding, label_y - text_height - padding,
                     text_width + padding * 2, text_height + padding * 2)
    painter.fillRect(bg_rect, QColor(255, 255, 255, 200))
    painter.setPen(QColor(0, 0, 0, 150))
    painter.drawRect(bg_rect)

    # Draw text
    painter.setPen(QColor(0, 0, 0))
    painter.drawText(QPointF(label_x, label_y), label_text)


def rotate_path(path: QPainterPath, angle_degrees: float) -> QPainterPath:
    """
    Rotate a painter path around the origin.

    Args:
        path: QPainterPath to rotate
        angle_degrees: Rotation angle in degrees

    Returns:
        Rotated QPainterPath
    """
    from PyQt6.QtGui import QTransform

    transform = QTransform()
    transform.rotate(angle_degrees)

    return transform.map(path)

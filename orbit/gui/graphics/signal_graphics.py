"""
Placeholder graphics generator for traffic signals.

Creates simple placeholder icons that can be replaced with actual sign images later.
"""

from PyQt6.QtGui import QPixmap, QPainter, QColor, QPen, QFont, QPainterPath
from PyQt6.QtCore import Qt, QPointF
from orbit.models.signal import SignalType


def create_give_way_sign(size: int = 48) -> QPixmap:
    """
    Create a placeholder give way sign (inverted red triangle).

    Args:
        size: Width/height of the icon in pixels

    Returns:
        QPixmap with the sign rendered
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Draw inverted triangle (point down)
    path = QPainterPath()
    margin = 4
    top_y = margin
    bottom_y = size - margin
    left_x = margin
    right_x = size - margin
    center_x = size / 2

    path.moveTo(center_x, bottom_y)  # Bottom point
    path.lineTo(left_x, top_y)  # Top left
    path.lineTo(right_x, top_y)  # Top right
    path.closeSubpath()

    # Red border with yellow fill (Swedish standard)
    painter.setPen(QPen(QColor(220, 20, 20), 3))
    painter.setBrush(QColor(255, 215, 0))
    painter.drawPath(path)

    painter.end()
    return pixmap


def create_speed_limit_sign(speed_value: int, size: int = 48) -> QPixmap:
    """
    Create a placeholder speed limit sign (circle with number).

    Args:
        speed_value: Speed limit value to display
        size: Width/height of the icon in pixels

    Returns:
        QPixmap with the sign rendered
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Draw circle with red border and yellow fill (Swedish standard)
    margin = 4
    diameter = size - 2 * margin
    painter.setPen(QPen(QColor(220, 20, 20), 3))
    painter.setBrush(QColor(255, 215, 0))
    painter.drawEllipse(margin, margin, diameter, diameter)

    # Draw speed value
    font = QFont("Arial", int(size * 0.35), QFont.Weight.Bold)
    painter.setFont(font)
    painter.setPen(QColor(0, 0, 0))

    text = str(speed_value)
    painter.drawText(0, 0, size, size, Qt.AlignmentFlag.AlignCenter, text)

    painter.end()
    return pixmap


def create_signal_pixmap(signal_type: SignalType, value: int = None, size: int = 48) -> QPixmap:
    """
    Create a placeholder pixmap for a signal based on its type.

    Args:
        signal_type: Type of signal
        value: Speed value for speed limit signs
        size: Icon size in pixels

    Returns:
        QPixmap with the appropriate sign rendered
    """
    if signal_type == SignalType.GIVE_WAY:
        return create_give_way_sign(size)
    elif signal_type == SignalType.SPEED_LIMIT and value is not None:
        return create_speed_limit_sign(value, size)
    else:
        # Fallback: generic sign
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(100, 100, 100), 2))
        painter.setBrush(QColor(200, 200, 200))
        painter.drawRect(4, 4, size - 8, size - 8)
        painter.end()
        return pixmap


def create_orientation_indicator(angle: float, length: int = 20) -> QPainterPath:
    """
    Create a directional arrow indicator showing signal orientation.

    Args:
        angle: Orientation angle in degrees (0 = right, 90 = up)
        length: Length of the arrow in pixels

    Returns:
        QPainterPath for the arrow
    """
    import math

    path = QPainterPath()

    # Convert angle to radians
    rad = math.radians(angle)

    # Arrow line from center
    dx = length * math.cos(rad)
    dy = -length * math.sin(rad)  # Negative because Qt y-axis points down

    path.moveTo(0, 0)
    path.lineTo(dx, dy)

    # Arrowhead
    arrow_size = 6
    left_angle = rad + math.radians(150)
    right_angle = rad - math.radians(150)

    left_x = dx + arrow_size * math.cos(left_angle)
    left_y = dy - arrow_size * math.sin(left_angle)
    right_x = dx + arrow_size * math.cos(right_angle)
    right_y = dy - arrow_size * math.sin(right_angle)

    path.moveTo(dx, dy)
    path.lineTo(left_x, left_y)
    path.moveTo(dx, dy)
    path.lineTo(right_x, right_y)

    return path

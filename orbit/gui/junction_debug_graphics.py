"""
Junction debug visualization graphics items.

Provides visual debugging for junction connections:
- Road endpoint markers (incoming/outgoing indicators)
- Heading arrows
- Connection path visualization
"""

import math
from typing import Optional, Tuple

from PyQt6.QtWidgets import QGraphicsItem, QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsPathItem
from PyQt6.QtGui import QPen, QBrush, QColor, QPainterPath, QPainter, QPolygonF
from PyQt6.QtCore import Qt, QPointF, QRectF


class RoadEndpointMarker(QGraphicsEllipseItem):
    """
    Visual marker for a road endpoint at a junction.

    Shows:
    - Circle at endpoint position
    - Color indicates incoming (red) or outgoing (green)
    - Heading arrow showing direction
    """

    def __init__(self, position: Tuple[float, float], heading: float,
                 is_incoming: bool, is_outgoing: bool, road_name: str = ""):
        """
        Initialize road endpoint marker.

        Args:
            position: (x, y) position of endpoint
            heading: Direction in radians (0 = east, π/2 = north)
            is_incoming: True if road ends at junction
            is_outgoing: True if road starts at junction
            road_name: Name of the road (for tooltip)
        """
        # Create circle at position
        radius = 15.0
        super().__init__(
            position[0] - radius,
            position[1] - radius,
            radius * 2,
            radius * 2
        )

        self.position = position
        self.heading = heading
        self.is_incoming = is_incoming
        self.is_outgoing = is_outgoing
        self.road_name = road_name

        # Set colors based on direction
        if is_incoming and is_outgoing:
            # Bidirectional (both)
            color = QColor(255, 255, 0, 200)  # Yellow
        elif is_incoming:
            # Incoming (road ends here)
            color = QColor(255, 50, 50, 200)  # Red
        elif is_outgoing:
            # Outgoing (road starts here)
            color = QColor(50, 255, 50, 200)  # Green
        else:
            # Unknown
            color = QColor(128, 128, 128, 200)  # Gray

        # Set appearance
        self.setBrush(QBrush(color))
        self.setPen(QPen(Qt.GlobalColor.black, 2))

        # Set tooltip
        direction_str = []
        if is_incoming:
            direction_str.append("incoming")
        if is_outgoing:
            direction_str.append("outgoing")
        direction = ", ".join(direction_str) if direction_str else "unknown"

        heading_deg = math.degrees(heading)
        self.setToolTip(
            f"{road_name}\n"
            f"Direction: {direction}\n"
            f"Heading: {heading_deg:.1f}°\n"
            f"Position: ({position[0]:.1f}, {position[1]:.1f})"
        )

        # Make it visible above other items
        self.setZValue(1000)

        # Create heading arrow as child item
        self.arrow = HeadingArrow(position, heading, color)
        self.arrow.setParentItem(self)


class HeadingArrow(QGraphicsPathItem):
    """
    Arrow showing the heading direction of a road endpoint.
    """

    def __init__(self, position: Tuple[float, float], heading: float, color: QColor):
        """
        Initialize heading arrow.

        Args:
            position: Start position of arrow
            heading: Direction in radians
            color: Color of the arrow
        """
        super().__init__()

        self.position = position
        self.heading = heading
        self.color = color

        # Create arrow path
        self.create_arrow()

        # Set appearance
        pen = QPen(color, 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.setPen(pen)
        self.setBrush(QBrush(color))

        self.setZValue(1001)

    def create_arrow(self):
        """Create the arrow shape."""
        path = QPainterPath()

        # Arrow length
        length = 40.0
        head_length = 12.0
        head_width = 8.0

        # Start point
        x0, y0 = self.position

        # End point (along heading)
        x1 = x0 + length * math.cos(self.heading)
        y1 = y0 + length * math.sin(self.heading)

        # Arrow line
        path.moveTo(x0, y0)
        path.lineTo(x1, y1)

        # Arrow head (triangle at end)
        # Calculate perpendicular direction
        perp_heading = self.heading + math.pi / 2

        # Points for arrow head
        # Back from tip along heading
        base_x = x1 - head_length * math.cos(self.heading)
        base_y = y1 - head_length * math.sin(self.heading)

        # Two side points perpendicular to heading
        side1_x = base_x + head_width * math.cos(perp_heading)
        side1_y = base_y + head_width * math.sin(perp_heading)

        side2_x = base_x - head_width * math.cos(perp_heading)
        side2_y = base_y - head_width * math.sin(perp_heading)

        # Create triangle for arrow head
        arrow_head = QPolygonF([
            QPointF(x1, y1),
            QPointF(side1_x, side1_y),
            QPointF(side2_x, side2_y)
        ])

        path.addPolygon(arrow_head)

        self.setPath(path)


class ConnectionPathGraphics(QGraphicsPathItem):
    """
    Visual representation of a junction connection path.

    Shows the connecting road path with color based on turn type.
    """

    def __init__(self, path_points: list, turn_type: str = "unknown",
                 from_road: str = "", to_road: str = ""):
        """
        Initialize connection path graphics.

        Args:
            path_points: List of (x, y) points defining the path
            turn_type: Type of turn ("straight", "left", "right", "uturn", "unknown")
            from_road: Name of source road
            to_road: Name of destination road
        """
        super().__init__()

        self.path_points = path_points
        self.turn_type = turn_type
        self.from_road = from_road
        self.to_road = to_road

        # Set color based on turn type
        colors = {
            "straight": QColor(0, 200, 0, 180),      # Green
            "right": QColor(0, 100, 255, 180),       # Blue
            "left": QColor(255, 150, 0, 180),        # Orange
            "uturn": QColor(255, 50, 50, 180),       # Red
            "unknown": QColor(128, 128, 128, 150)    # Gray
        }
        self.color = colors.get(turn_type, colors["unknown"])

        # Create path
        self.create_path()

        # Set appearance
        pen = QPen(self.color, 4)
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.setPen(pen)

        # Set tooltip
        self.setToolTip(
            f"{from_road} → {to_road}\n"
            f"Turn type: {turn_type}\n"
            f"Path points: {len(path_points)}"
        )

        # Set z-value below endpoint markers
        self.setZValue(900)

        # Make selectable for hover effect
        self.setAcceptHoverEvents(True)

    def create_path(self):
        """Create the path from points."""
        if not self.path_points:
            return

        path = QPainterPath()

        # Move to first point
        x0, y0 = self.path_points[0]
        path.moveTo(x0, y0)

        # Line to each subsequent point
        for x, y in self.path_points[1:]:
            path.lineTo(x, y)

        self.setPath(path)

    def hoverEnterEvent(self, event):
        """Highlight on hover."""
        pen = self.pen()
        pen.setWidth(6)
        pen.setStyle(Qt.PenStyle.SolidLine)
        self.setPen(pen)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        """Remove highlight."""
        pen = self.pen()
        pen.setWidth(4)
        pen.setStyle(Qt.PenStyle.DashLine)
        self.setPen(pen)
        super().hoverLeaveEvent(event)


class JunctionDebugOverlay:
    """
    Manager for all debug graphics for a single junction.

    Aggregates all debug visualization items for easy show/hide.
    """

    def __init__(self, junction, roads_dict: dict, polylines_dict: dict):
        """
        Initialize junction debug overlay.

        Args:
            junction: Junction object to visualize
            roads_dict: Dictionary of road_id -> Road
            polylines_dict: Dictionary of polyline_id -> Polyline
        """
        self.junction = junction
        self.roads_dict = roads_dict
        self.polylines_dict = polylines_dict

        self.endpoint_markers = []
        self.connection_paths = []

    def create_graphics_items(self):
        """
        Create all graphics items for this junction.

        Returns:
            List of QGraphicsItem objects to add to scene
        """
        items = []

        # First, analyze junction geometry to get endpoint info
        try:
            import importlib
            junction_analyzer = importlib.import_module('orbit.import.junction_analyzer')
            analyze_junction_geometry = junction_analyzer.analyze_junction_geometry

            geometry_info = analyze_junction_geometry(
                self.junction,
                self.roads_dict,
                self.polylines_dict
            )

            # Create endpoint markers
            for endpoint in geometry_info['endpoints']:
                marker = RoadEndpointMarker(
                    position=endpoint.position,
                    heading=endpoint.heading,
                    is_incoming=endpoint.is_incoming,
                    is_outgoing=endpoint.is_outgoing,
                    road_name=endpoint.road_name
                )
                self.endpoint_markers.append(marker)
                items.append(marker)

        except Exception as e:
            print(f"Warning: Failed to create endpoint markers: {e}")
            import traceback
            traceback.print_exc()

        # Create connection path graphics
        for lane_conn in self.junction.lane_connections:
            # Find the connecting road
            conn_road = next(
                (cr for cr in self.junction.connecting_roads
                 if cr.id == lane_conn.connecting_road_id),
                None
            )

            if conn_road and conn_road.path:
                # Get road names
                from_road = self.roads_dict.get(lane_conn.from_road_id)
                to_road = self.roads_dict.get(lane_conn.to_road_id)

                from_name = from_road.name if from_road else "Unknown"
                to_name = to_road.name if to_road else "Unknown"

                path_graphic = ConnectionPathGraphics(
                    path_points=conn_road.path,
                    turn_type=lane_conn.turn_type,
                    from_road=from_name,
                    to_road=to_name
                )
                self.connection_paths.append(path_graphic)
                items.append(path_graphic)

        return items

    def clear(self):
        """Clear all graphics items."""
        self.endpoint_markers.clear()
        self.connection_paths.clear()

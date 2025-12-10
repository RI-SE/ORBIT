"""
Image view widget for ORBIT.

Provides interactive image display with zoom, pan, and polyline drawing/editing.
"""

from pathlib import Path
from typing import Optional, List, Dict, Tuple
import cv2
import numpy as np

from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsItem, QMenu, QMessageBox, QGraphicsPolygonItem
from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QPointF
from PyQt6.QtGui import (
    QPixmap, QImage, QPen, QColor, QBrush, QPainter,
    QWheelEvent, QMouseEvent, QKeyEvent, QFont
)

from orbit.models import Polyline, Project, Junction, LineType, RoadMarkType, Road, Signal, RoadObject, ObjectType
from orbit.utils.geometry import create_lane_polygon, calculate_directional_scale
from .graphics.signal_graphics_item import SignalGraphicsItem
from .graphics.object_graphics_item import ObjectGraphicsItem
from .utils.message_helpers import show_warning, ask_yes_no
from orbit.gui.graphics import (
    PolylineGraphicsItem,
    JunctionMarkerItem,
    InteractiveLanePolygon,
    LaneGraphicsItem,
    RoadLanesGraphicsItem,
    ConnectingRoadGraphicsItem,
    ConnectingRoadLanesGraphicsItem,
)


class ImageView(QGraphicsView):
    """Interactive image view with polyline drawing and editing."""

    # Signals
    polyline_added = pyqtSignal(object)  # Emits Polyline
    polyline_modified = pyqtSignal(str)  # Emits polyline ID
    polyline_deleted = pyqtSignal(str)  # Emits polyline ID
    polyline_edit_requested = pyqtSignal(str)  # Emits polyline ID for editing
    polyline_selected = pyqtSignal(str)  # Emits polyline ID when selected in view
    junction_added = pyqtSignal(object)  # Emits Junction
    junction_modified = pyqtSignal(str)  # Emits junction ID
    junction_deleted = pyqtSignal(str)  # Emits junction ID
    junction_edit_requested = pyqtSignal(str)  # Emits junction ID for editing
    junction_selected = pyqtSignal(str)  # Emits junction ID when selected in view
    signal_added = pyqtSignal(object)  # Emits Signal
    signal_modified = pyqtSignal(str)  # Emits signal ID
    signal_deleted = pyqtSignal(str)  # Emits signal ID
    signal_edit_requested = pyqtSignal(str)  # Emits signal ID for editing
    signal_selected = pyqtSignal(str)  # Emits signal ID when selected in view
    signal_placement_requested = pyqtSignal(float, float)  # Emits x, y coordinates for signal placement
    object_added = pyqtSignal(object)  # Emits RoadObject
    object_modified = pyqtSignal(str)  # Emits object ID
    object_deleted = pyqtSignal(str)  # Emits object ID
    object_edit_requested = pyqtSignal(str)  # Emits object ID for editing
    object_selected = pyqtSignal(str)  # Emits object ID when selected in view
    object_placement_requested = pyqtSignal(float, float, object)  # Emits x, y coordinates and ObjectType
    section_split_requested = pyqtSignal(str, str, int)  # Emits road_id, polyline_id, point_index
    road_split_requested = pyqtSignal(str, str, int)  # Emits road_id, polyline_id, point_index for splitting road
    section_modified = pyqtSignal(str)  # Emits road ID
    lane_segment_clicked = pyqtSignal(str, int, int)  # Emits road_id, section_number, lane_id
    connecting_road_lane_clicked = pyqtSignal(str, int)  # Emits connecting_road_id, lane_id
    lane_edit_requested = pyqtSignal(str, int, int)  # Emits road_id, section_number, lane_id (for double-click)
    connecting_road_lane_edit_requested = pyqtSignal(str, int)  # Emits connecting_road_id, lane_id (for double-click)
    point_picked = pyqtSignal(float, float)  # Emits x, y coordinates
    mouse_moved = pyqtSignal(float, float)  # Emits x, y mouse position in scene coordinates

    def __init__(self, parent=None, verbose: bool = False):
        super().__init__(parent)

        # Debug flag
        self.verbose = verbose

        # Setup scene
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        # Image
        self.image_path: Optional[Path] = None
        self.image_item: Optional[QGraphicsPixmapItem] = None
        self.image_np: Optional[np.ndarray] = None

        # Polylines
        self.polyline_items: Dict[str, PolylineGraphicsItem] = {}
        self.current_polyline: Optional[Polyline] = None
        self.current_polyline_item: Optional[PolylineGraphicsItem] = None

        # Junctions
        self.junction_items: Dict[str, JunctionMarkerItem] = {}
        self.selected_junction_id: Optional[str] = None

        # Signals
        self.signal_items: Dict[str, SignalGraphicsItem] = {}
        self.selected_signal_id: Optional[str] = None

        # Objects
        self.object_items: Dict[str, ObjectGraphicsItem] = {}
        self.selected_object_id: Optional[str] = None

        # Control points (for georeferencing visualization)
        self.control_point_items: List = []

        # Road lanes (visual representation of lanes)
        self.road_lanes_items: Dict[str, RoadLanesGraphicsItem] = {}
        self.selected_lane_key: Optional[Tuple[str, int, int]] = None  # (road_id, section_number, lane_id)
        self.linked_lane_polygons: List = []  # Polygons currently highlighted as connected to selection
        self.project: Optional[Project] = None  # Reference to project for road lookups

        # Section boundaries (visual representation of lane section boundaries)
        self.section_boundary_items: Dict[str, List] = {}  # road_id -> list of graphics items

        # Connecting roads (junction paths)
        self.connecting_road_centerline_items: Dict[str, ConnectingRoadGraphicsItem] = {}
        self.connecting_road_lanes_items: Dict[str, ConnectingRoadLanesGraphicsItem] = {}
        self.selected_connecting_road_id: Optional[str] = None

        # Interaction state
        self.drawing_mode = False
        self.junction_mode = False
        self.signal_mode = False
        self.object_mode = False
        self.object_type_to_place: Optional[ObjectType] = None  # Type of object to place
        self.drawing_guardrail = False  # True when dragging to create guardrail
        self.guardrail_points: List[Tuple[float, float]] = []  # Points for current guardrail
        self.pick_point_mode = False
        self.measure_mode = False
        self.selected_polyline_id: Optional[str] = None
        self.dragging_point = False
        self.drag_polyline_id: Optional[str] = None
        self.drag_point_index: int = -1
        self.dragging_junction = False
        self.drag_junction_id: Optional[str] = None
        self.dragging_guardrail_point = False
        self.drag_object_id: Optional[str] = None
        # drag_point_index is shared with polyline and connecting road dragging
        self.dragging_connecting_road_point = False
        self.drag_connecting_road_id: Optional[str] = None
        # drag_point_index is also used for connecting road point dragging

        # Measure mode state
        self.measure_points: List[QPointF] = []  # Current pair being measured
        self.measurement_items: List = []  # All graphics items for cleanup

        # Show scale mode state
        self.show_scale_mode = False
        self.scale_items: List = []  # All graphics items for cleanup

        # Uncertainty overlay
        self.uncertainty_overlay = None

        # S-offset labels
        self.soffsets_visible = False
        self.soffset_labels: Dict[str, List] = {}  # polyline_id -> list of (text_item, bg_item) tuples

        # Junction debug visualization
        self.junction_debug_visible = False
        self.junction_debug_items: Dict[str, List] = {}  # junction_id -> list of graphics items

        # View settings
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMouseTracking(True)  # Enable mouse tracking for position updates

    def load_image(self, image_path: Path):
        """Load an image file."""
        self.image_path = image_path

        # Load image with OpenCV
        self.image_np = cv2.imread(str(image_path))
        if self.image_np is None:
            return

        # Convert BGR to RGB
        self.image_np = cv2.cvtColor(self.image_np, cv2.COLOR_BGR2RGB)

        # Convert to QPixmap
        height, width, channel = self.image_np.shape
        bytes_per_line = 3 * width
        q_image = QImage(
            self.image_np.data,
            width,
            height,
            bytes_per_line,
            QImage.Format.Format_RGB888
        )
        pixmap = QPixmap.fromImage(q_image)

        # Clear scene and add image
        self.scene.clear()
        self.polyline_items.clear()
        self.image_item = self.scene.addPixmap(pixmap)
        self.image_item.setZValue(0)

        # Fit to view
        self.fit_to_window()

    def load_project(self, project: Project, scale_factors: tuple = None):
        """
        Load polylines, junctions, control points, and road lanes from a project.

        Args:
            project: Project to load
            scale_factors: Optional tuple of (scale_x, scale_y) in m/px from georeferencing
        """
        # Clear all existing graphics safely
        # Note: We don't call full clear() because we want to keep the image

        # Clear scene items (this removes everything from the scene at once)
        # We need to keep the image item
        image_item_backup = self.image_item
        for item in list(self.scene.items()):
            if item != image_item_backup:
                self.scene.removeItem(item)

        # Clear tracking dictionaries
        self.polyline_items.clear()
        self.junction_items.clear()
        self.signal_items.clear()
        self.object_items.clear()
        self.control_point_items.clear()
        self.road_lanes_items.clear()
        self.connecting_road_centerline_items.clear()
        self.connecting_road_lanes_items.clear()
        self.soffset_labels.clear()

        # Store project reference for road lookups
        self.project = project

        # Add polylines from project
        for polyline in project.polylines:
            self.add_polyline_graphics(polyline)

        # Add junctions from project
        for junction in project.junctions:
            self.add_junction_graphics(junction)

        # Add signals from project
        for signal in project.signals:
            self.add_signal_graphics(signal)

        # Add objects from project
        scale_factor = scale_factors[0] if scale_factors else 0.0
        for obj in project.objects:
            self.add_object_graphics(obj, scale_factor)

        # Add control points from project
        for cp in project.control_points:
            self.add_control_point_graphics(cp)

        # Add road lanes for all roads with centerlines
        for road in project.roads:
            if road.centerline_id:
                self.add_road_lanes_graphics(road, scale_factors)

        # Add connecting roads from all junctions
        for junction in project.junctions:
            for connecting_road in junction.connecting_roads:
                self.add_connecting_road_graphics(connecting_road, scale_factors)

    def add_polyline_graphics(self, polyline: Polyline):
        """Add a polyline to the graphics scene."""
        item = PolylineGraphicsItem(polyline, self.scene)
        self.polyline_items[polyline.id] = item
        # Update s-offset labels if visible and this is a centerline
        if self.soffsets_visible:
            self._update_soffset_labels(polyline.id)

    def add_junction_graphics(self, junction: Junction):
        """Add a junction marker to the graphics scene."""
        item = JunctionMarkerItem(junction, self.scene)
        self.junction_items[junction.id] = item

    def remove_junction_graphics(self, junction_id: str):
        """Remove a junction marker from the scene."""
        if junction_id in self.junction_items:
            self.junction_items[junction_id].remove()
            del self.junction_items[junction_id]

    def refresh_junction_graphics(self, junction_id: str):
        """Refresh junction graphics after modification, including connecting roads."""
        if junction_id in self.junction_items:
            self.junction_items[junction_id].update_graphics()

        # Also refresh/remove connecting road graphics for this junction
        junction = self.project.get_junction(junction_id) if self.project else None
        if junction:
            # Get current connecting road IDs from the junction
            current_conn_road_ids = {cr.id for cr in junction.connecting_roads}

            # Find connecting road graphics that belong to this junction but are no longer valid
            orphaned_ids = []
            for conn_road_id in list(self.connecting_road_lanes_items.keys()):
                # Check if this connecting road was part of this junction
                # by checking if it's NOT in any junction's connecting_roads
                found_in_any_junction = False
                for j in self.project.junctions:
                    if any(cr.id == conn_road_id for cr in j.connecting_roads):
                        found_in_any_junction = True
                        break
                if not found_in_any_junction:
                    orphaned_ids.append(conn_road_id)

            # Remove orphaned connecting road graphics
            for conn_road_id in orphaned_ids:
                self.remove_connecting_road_graphics(conn_road_id)

            # Update existing connecting road graphics
            for conn_road in junction.connecting_roads:
                if conn_road.id in self.connecting_road_lanes_items:
                    self.connecting_road_lanes_items[conn_road.id].update_graphics()

    def add_signal_graphics(self, signal: Signal):
        """Add a signal to the graphics scene."""
        item = SignalGraphicsItem(signal, project=self.project)
        item.signal_changed = lambda s: self.signal_modified.emit(s.id)
        self.signal_items[signal.id] = item
        self.scene.addItem(item)

    def remove_signal_graphics(self, signal_id: str):
        """Remove a signal from the scene."""
        if signal_id in self.signal_items:
            item = self.signal_items[signal_id]
            self.safe_remove_item(item)
            del self.signal_items[signal_id]

    def refresh_signal_graphics(self, signal_id: str):
        """Refresh signal graphics after modification."""
        if signal_id in self.signal_items:
            self.signal_items[signal_id].update_graphics()

    def add_object_graphics(self, obj: RoadObject, scale_factor: float = 0.0):
        """Add an object to the graphics scene."""
        item = ObjectGraphicsItem(obj, scale_factor)
        item.object_changed = lambda o: self.object_modified.emit(o.id)
        self.object_items[obj.id] = item
        self.scene.addItem(item)

    def remove_object_graphics(self, object_id: str):
        """Remove an object from the scene."""
        if object_id in self.object_items:
            item = self.object_items[object_id]
            self.safe_remove_item(item)
            del self.object_items[object_id]

    def refresh_object_graphics(self, object_id: str):
        """Refresh object graphics after modification."""
        if object_id in self.object_items:
            item = self.object_items[object_id]
            obj = item.obj

            # Update position for point objects (non-polyline)
            if obj.type.get_shape_type() != "polyline":
                item.setPos(obj.position[0], obj.position[1])

            # Update graphics (shape, color, dimensions, orientation)
            item.update_graphics()

    def update_object_scale_factors(self, scale_factor: float):
        """Update scale factors for all objects when georeferencing changes."""
        for item in self.object_items.values():
            item.update_scale_factor(scale_factor)

    def add_control_point_graphics(self, control_point):
        """Add a control point marker to the graphics scene."""
        from orbit.models import ControlPoint

        # Draw a dark blue dot at the control point location
        x, y = control_point.pixel_x, control_point.pixel_y

        # Create outer circle (larger, dark blue)
        outer_radius = 12
        outer_pen = QPen(QColor(0, 50, 150), 3)  # Dark blue border
        outer_brush = QBrush(QColor(100, 150, 255, 180))  # Semi-transparent blue
        outer_circle = self.scene.addEllipse(
            x - outer_radius, y - outer_radius,
            outer_radius * 2, outer_radius * 2,
            outer_pen, outer_brush
        )
        outer_circle.setZValue(10)  # Above everything else
        self.control_point_items.append(outer_circle)

        # Create inner circle (smaller, bright blue)
        inner_radius = 5
        inner_pen = QPen(QColor(255, 255, 255), 1)  # White border
        inner_brush = QBrush(QColor(0, 100, 255))  # Bright blue
        inner_circle = self.scene.addEllipse(
            x - inner_radius, y - inner_radius,
            inner_radius * 2, inner_radius * 2,
            inner_pen, inner_brush
        )
        inner_circle.setZValue(11)  # Above outer circle
        self.control_point_items.append(inner_circle)

        # Add label with CP name
        if control_point.name:
            from PyQt6.QtWidgets import QGraphicsTextItem
            from PyQt6.QtGui import QFont
            text_item = QGraphicsTextItem(control_point.name)
            text_item.setDefaultTextColor(QColor(0, 100, 255))  # Bright blue
            font = QFont()
            font.setBold(True)
            font.setPointSize(10)
            text_item.setFont(font)
            text_item.setPos(x + 15, y - 10)
            text_item.setZValue(11)
            self.scene.addItem(text_item)
            self.control_point_items.append(text_item)

    def add_road_lanes_graphics(self, road: Road, scale_factors: tuple = None):
        """
        Add lane visualization for a road.

        Args:
            road: Road object with centerline and lane configuration
            scale_factors: Tuple of (scale_x, scale_y) in m/px, or None for default
        """
        # Check if road has a centerline
        if not road.centerline_id:
            return

        # Get centerline polyline
        if road.centerline_id not in self.polyline_items:
            return

        centerline_item = self.polyline_items[road.centerline_id]
        centerline = centerline_item.polyline

        # Remove existing lane graphics for this road if any
        if road.id in self.road_lanes_items:
            self.road_lanes_items[road.id].remove()

        # Create new lane graphics (with verbose flag for debugging)
        lanes_item = RoadLanesGraphicsItem(road, centerline, self.scene, scale_factors, self.verbose)
        self.road_lanes_items[road.id] = lanes_item

    def update_road_lanes(self, road_id: str, scale_factors: tuple = None):
        """
        Update lane graphics for a road.

        Args:
            road_id: ID of road to update
            scale_factors: Tuple of (scale_x, scale_y) in m/px, or None for current/default
        """
        if not self.project:
            return

        road = self.project.get_road(road_id)
        if not road:
            return

        # Update or create lane graphics
        if road_id in self.road_lanes_items:
            if scale_factors is not None:
                self.road_lanes_items[road_id].update_scale(scale_factors)
            else:
                self.road_lanes_items[road_id].update_graphics()
        else:
            self.add_road_lanes_graphics(road, scale_factors)

    def add_connecting_road_graphics(self, connecting_road, scale_factors: tuple = None):
        """
        Add centerline and lane visualization for a connecting road.

        Args:
            connecting_road: ConnectingRoad object
            scale_factors: Tuple of (scale_x, scale_y) in m/px, or None for default
        """
        # Remove existing graphics if any
        if connecting_road.id in self.connecting_road_centerline_items:
            self.connecting_road_centerline_items[connecting_road.id].remove()
        if connecting_road.id in self.connecting_road_lanes_items:
            self.connecting_road_lanes_items[connecting_road.id].remove()

        # Create centerline graphics
        centerline_item = ConnectingRoadGraphicsItem(connecting_road, self.scene)
        self.connecting_road_centerline_items[connecting_road.id] = centerline_item

        # Create lane graphics
        lanes_item = ConnectingRoadLanesGraphicsItem(
            connecting_road, self.scene, scale_factors,
            parent_view=self, verbose=self.verbose
        )
        self.connecting_road_lanes_items[connecting_road.id] = lanes_item

    def remove_connecting_road_graphics(self, connecting_road_id: str):
        """Remove connecting road graphics from scene."""
        if connecting_road_id in self.connecting_road_centerline_items:
            self.connecting_road_centerline_items[connecting_road_id].remove()
            del self.connecting_road_centerline_items[connecting_road_id]

        if connecting_road_id in self.connecting_road_lanes_items:
            self.connecting_road_lanes_items[connecting_road_id].remove()
            del self.connecting_road_lanes_items[connecting_road_id]

    def update_connecting_road_graphics(self, connecting_road_id: str, scale_factors: tuple = None):
        """
        Update connecting road graphics.

        Args:
            connecting_road_id: ID of connecting road to update
            scale_factors: Tuple of (scale_x, scale_y) in m/px, or None for current/default
        """
        # Update centerline
        if connecting_road_id in self.connecting_road_centerline_items:
            self.connecting_road_centerline_items[connecting_road_id].update_graphics()

        # Update lanes
        if connecting_road_id in self.connecting_road_lanes_items:
            if scale_factors is not None:
                self.connecting_road_lanes_items[connecting_road_id].update_scale(scale_factors)
            else:
                self.connecting_road_lanes_items[connecting_road_id].update_graphics()

    def remove_road_lanes(self, road_id: str):
        """Remove lane graphics for a road."""
        if road_id in self.road_lanes_items:
            self.road_lanes_items[road_id].remove()
            del self.road_lanes_items[road_id]

    def draw_section_boundaries(self, road: Road):
        """
        Draw visual markers for lane section boundaries.

        Draws perpendicular lines at each section boundary point.

        Args:
            road: Road whose section boundaries to draw
        """
        # Remove existing boundary graphics
        self.remove_section_boundaries(road.id)

        if not road.centerline_id or not road.lane_sections:
            return

        # Get centerline polyline
        centerline = self.project.get_polyline(road.centerline_id) if self.project else None
        if not centerline:
            return

        # Calculate s-coordinates for all points
        s_coords = road.calculate_centerline_s_coordinates(centerline.points)

        boundary_items = []

        # Draw boundary at each section split (not at start/end)
        for i, section in enumerate(road.lane_sections):
            if i == 0:
                continue  # Skip first section's start (road start)

            # Find the point index closest to this section's s_start
            boundary_s = section.s_start
            point_index = self._find_closest_point_index(s_coords, boundary_s)

            if point_index >= 0 and point_index < len(centerline.points):
                # Draw perpendicular line at this point
                items = self._draw_perpendicular_marker(
                    centerline.points,
                    point_index,
                    road
                )
                boundary_items.extend(items)

        self.section_boundary_items[road.id] = boundary_items

    def _find_closest_point_index(self, s_coords: List[float], target_s: float) -> int:
        """
        Find the index of the point closest to the target s-coordinate.

        Args:
            s_coords: List of s-coordinates
            target_s: Target s-coordinate to find

        Returns:
            Index of closest point, or -1 if not found
        """
        if not s_coords:
            return -1

        min_dist = float('inf')
        closest_idx = -1

        for i, s in enumerate(s_coords):
            dist = abs(s - target_s)
            if dist < min_dist:
                min_dist = dist
                closest_idx = i

        return closest_idx

    def _draw_perpendicular_marker(
        self,
        points: List[Tuple[float, float]],
        point_index: int,
        road: Road
    ) -> List:
        """
        Draw a perpendicular line at a point on the centerline.

        Args:
            points: List of centerline points
            point_index: Index of the point where to draw
            road: Road object (for estimating width)

        Returns:
            List of graphics items created
        """
        import math

        items = []

        if point_index < 0 or point_index >= len(points):
            return items

        # Get the point
        px, py = points[point_index]

        # Calculate tangent vector (direction along centerline)
        if point_index > 0 and point_index < len(points) - 1:
            # Use average of adjacent segments
            x1, y1 = points[point_index - 1]
            x2, y2 = points[point_index + 1]
            dx = x2 - x1
            dy = y2 - y1
        elif point_index == 0 and len(points) > 1:
            # Use next segment
            x2, y2 = points[point_index + 1]
            dx = x2 - px
            dy = y2 - py
        elif point_index == len(points) - 1 and len(points) > 1:
            # Use previous segment
            x1, y1 = points[point_index - 1]
            dx = px - x1
            dy = py - y1
        else:
            return items

        # Normalize
        length = math.sqrt(dx * dx + dy * dy)
        if length < 0.01:
            return items

        dx /= length
        dy /= length

        # Perpendicular vector (rotate 90 degrees)
        perp_x = -dy
        perp_y = dx

        # Estimate road width (use total lanes * default lane width, or fixed value)
        # For simplicity, use a fixed visual length
        half_width = 50.0  # pixels

        # Calculate endpoints of perpendicular line
        start_x = px - perp_x * half_width
        start_y = py - perp_y * half_width
        end_x = px + perp_x * half_width
        end_y = py + perp_y * half_width

        # Draw the line
        pen = QPen(QColor(0, 255, 255), 2, Qt.PenStyle.DashLine)  # Cyan dashed line
        line = self.scene.addLine(start_x, start_y, end_x, end_y, pen)
        line.setZValue(3)  # Above polylines and lanes
        items.append(line)

        # Draw a marker dot at the center
        marker_brush = QBrush(QColor(0, 255, 255))
        marker_pen = QPen(QColor(0, 200, 200), 1)
        marker = self.scene.addEllipse(
            px - 4, py - 4, 8, 8,
            marker_pen, marker_brush
        )
        marker.setZValue(4)
        items.append(marker)

        return items

    def remove_section_boundaries(self, road_id: str):
        """Remove section boundary graphics for a road."""
        if road_id in self.section_boundary_items:
            for item in self.section_boundary_items[road_id]:
                if item.scene() == self.scene:
                    self.scene.removeItem(item)
            del self.section_boundary_items[road_id]

    def update_section_boundaries(self, road_id: str):
        """Update section boundary graphics for a road."""
        if not self.project:
            return

        road = self.project.get_road(road_id)
        if road:
            self.draw_section_boundaries(road)

    def set_lanes_visible(self, visible: bool):
        """Set visibility for all lane graphics."""
        for lanes_item in self.road_lanes_items.values():
            lanes_item.set_visible(visible)

    def set_soffsets_visible(self, visible: bool):
        """Set visibility for s-offset labels."""
        self.soffsets_visible = visible

        if visible:
            # Create labels for all centerline polylines
            self._update_all_soffset_labels()
        else:
            # Hide all labels
            self._clear_all_soffset_labels()

    def _calculate_soffsets(self, polyline: Polyline) -> List[float]:
        """
        Calculate s-offset for each point in a polyline.

        Args:
            polyline: Polyline to calculate s-offsets for

        Returns:
            List of s-offsets (cumulative distances from start) in pixels or meters
        """
        import math

        points = polyline.points
        if len(points) == 0:
            return []

        # Check if we should use metric distances
        use_metric = self.project and self.project.has_georeferencing()

        if use_metric:
            try:
                from orbit.export import create_transformer
                transformer = create_transformer(self.project.control_points)
                if transformer:
                    # Convert all points to meters first
                    metric_points = []
                    for x, y in points:
                        mx, my = transformer.pixel_to_meters(x, y)
                        metric_points.append((mx, my))

                    # Calculate cumulative distances in meters
                    soffsets = [0.0]  # First point is at s=0
                    cumulative = 0.0
                    for i in range(1, len(metric_points)):
                        x1, y1 = metric_points[i - 1]
                        x2, y2 = metric_points[i]
                        dist = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
                        cumulative += dist
                        soffsets.append(cumulative)
                    return soffsets
            except Exception:
                pass

        # Fall back to pixel distances
        soffsets = [0.0]  # First point is at s=0
        cumulative = 0.0
        for i in range(1, len(points)):
            x1, y1 = points[i - 1]
            x2, y2 = points[i]
            dist = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
            cumulative += dist
            soffsets.append(cumulative)
        return soffsets

    def _format_soffset(self, soffset: float) -> str:
        """
        Format s-offset value for display.

        Args:
            soffset: S-offset value in pixels or meters

        Returns:
            Formatted string like "s=12.5m" or "s=150px"
        """
        # Check if we have georeferencing
        use_metric = self.project and self.project.has_georeferencing()

        if use_metric:
            # Format in meters
            if soffset < 1.0:
                return f"s={soffset * 100:.1f}cm"
            elif soffset < 1000:
                return f"s={soffset:.2f}m"
            else:
                return f"s={soffset / 1000:.3f}km"
        else:
            # Format in pixels
            return f"s={soffset:.1f}px"

    def _create_soffset_label(self, x: float, y: float, soffset: float):
        """
        Create a s-offset label at the given position.

        Args:
            x, y: Position of the point
            soffset: S-offset value

        Returns:
            Tuple of (text_item, bg_item)
        """
        from PyQt6.QtWidgets import QGraphicsTextItem
        from PyQt6.QtGui import QFont

        # Create text item
        text = self._format_soffset(soffset)
        text_item = QGraphicsTextItem(text)
        text_item.setDefaultTextColor(QColor(255, 255, 255))
        font = QFont()
        font.setBold(True)
        font.setPointSize(10)
        text_item.setFont(font)

        # Position above-right of the point
        offset_x = 10
        offset_y = -20
        text_item.setPos(x + offset_x, y + offset_y)
        text_item.setZValue(15)

        # Create background rectangle
        text_rect = text_item.boundingRect()
        bg_rect = text_rect.adjusted(-3, -1, 3, 1)  # Add padding
        bg_pen = QPen(QColor(0, 0, 0, 0))  # Transparent border
        bg_brush = QBrush(QColor(0, 0, 0, 180))  # Semi-transparent dark background
        bg_item = self.scene.addRect(
            x + offset_x + bg_rect.x() - 3,
            y + offset_y + bg_rect.y() - 1,
            bg_rect.width(),
            bg_rect.height(),
            bg_pen, bg_brush
        )
        bg_item.setZValue(14)

        # Add items to scene
        self.scene.addItem(text_item)

        return (text_item, bg_item)

    def _update_soffset_labels(self, polyline_id: str):
        """Update s-offset labels for a specific polyline."""
        # Remove existing labels for this polyline
        if polyline_id in self.soffset_labels:
            for text_item, bg_item in self.soffset_labels[polyline_id]:
                self.safe_remove_item(text_item)
                self.safe_remove_item(bg_item)
            del self.soffset_labels[polyline_id]

        # Only create labels if visible and polyline exists
        if not self.soffsets_visible:
            return

        if polyline_id not in self.polyline_items:
            return

        polyline_item = self.polyline_items[polyline_id]
        polyline = polyline_item.polyline

        # Only show s-offsets for centerlines
        if polyline.line_type != LineType.CENTERLINE:
            return

        # Calculate s-offsets
        soffsets = self._calculate_soffsets(polyline)

        # Create labels for each point
        labels = []
        for i, (x, y) in enumerate(polyline.points):
            text_item, bg_item = self._create_soffset_label(x, y, soffsets[i])
            labels.append((text_item, bg_item))

        self.soffset_labels[polyline_id] = labels

    def _update_all_soffset_labels(self):
        """Update s-offset labels for all centerline polylines."""
        for polyline_id in self.polyline_items:
            self._update_soffset_labels(polyline_id)

    def _clear_all_soffset_labels(self):
        """Clear all s-offset labels."""
        for polyline_id in list(self.soffset_labels.keys()):
            for text_item, bg_item in self.soffset_labels[polyline_id]:
                self.safe_remove_item(text_item)
                self.safe_remove_item(bg_item)
        self.soffset_labels.clear()

    def set_junction_debug_visible(self, visible: bool):
        """
        Set visibility for junction debug graphics.

        Shows road endpoint markers and connection paths for debugging.

        Args:
            visible: True to show debug graphics, False to hide
        """
        self.junction_debug_visible = visible

        if visible:
            # Create debug graphics for all junctions
            self._update_all_junction_debug()
        else:
            # Hide all debug graphics
            self._clear_all_junction_debug()

    def _update_all_junction_debug(self):
        """Create debug graphics for all junctions."""
        if not self.project:
            return

        # Clear existing
        self._clear_all_junction_debug()

        # Build dictionaries for junction analyzer
        roads_dict = {road.id: road for road in self.project.roads}
        polylines_dict = {p.id: p for p in self.project.polylines}

        # Create debug graphics for each junction
        from .graphics.junction_debug_graphics import JunctionDebugOverlay

        for junction in self.project.junctions:
            overlay = JunctionDebugOverlay(junction, roads_dict, polylines_dict)
            items = overlay.create_graphics_items()

            # Add items to scene
            for item in items:
                self.scene.addItem(item)

            # Store for later removal
            self.junction_debug_items[junction.id] = items

    def _clear_all_junction_debug(self):
        """Clear all junction debug graphics."""
        for junction_id in list(self.junction_debug_items.keys()):
            for item in self.junction_debug_items[junction_id]:
                self.safe_remove_item(item)
        self.junction_debug_items.clear()

    def update_junction_debug(self, junction_id: str):
        """
        Update debug graphics for a specific junction.

        Args:
            junction_id: ID of junction to update
        """
        if not self.junction_debug_visible or not self.project:
            return

        # Find the junction
        junction = None
        for j in self.project.junctions:
            if j.id == junction_id:
                junction = j
                break

        if not junction:
            return

        # Clear old debug graphics for this junction
        if junction_id in self.junction_debug_items:
            for item in self.junction_debug_items[junction_id]:
                self.safe_remove_item(item)
            del self.junction_debug_items[junction_id]

        # Create new debug graphics
        roads_dict = {road.id: road for road in self.project.roads}
        polylines_dict = {p.id: p for p in self.project.polylines}

        from .graphics.junction_debug_graphics import JunctionDebugOverlay

        overlay = JunctionDebugOverlay(junction, roads_dict, polylines_dict)
        items = overlay.create_graphics_items()

        # Add items to scene
        for item in items:
            self.scene.addItem(item)

        # Store for later removal
        self.junction_debug_items[junction_id] = items

    def update_polyline(self, polyline_id: str):
        """Update polyline graphics after properties change."""
        if polyline_id in self.polyline_items:
            self.polyline_items[polyline_id].update_graphics()
            # Update s-offset labels (in case line type changed to/from centerline)
            if self.soffsets_visible:
                self._update_soffset_labels(polyline_id)

    def safe_remove_item(self, item: QGraphicsItem) -> bool:
        """
        Safely remove a graphics item from the scene.

        Checks that the item belongs to this view's scene before removal to
        prevent "item's scene is different from this scene" crashes.

        Args:
            item: Graphics item to remove

        Returns:
            True if item was removed, False if item was None or not in scene
        """
        try:
            if item and item.scene() == self.scene:
                self.scene.removeItem(item)
                return True
        except RuntimeError:
            # C++ object has been deleted already (e.g., child of a removed parent item)
            pass
        return False

    def safe_remove_items(self, items: List[QGraphicsItem]):
        """
        Safely remove multiple graphics items from the scene.

        Args:
            items: List of graphics items to remove
        """
        for item in items:
            self.safe_remove_item(item)

    def clear(self):
        """Clear the view."""
        self.scene.clear()
        self.polyline_items.clear()
        self.junction_items.clear()
        self.control_point_items.clear()
        self.road_lanes_items.clear()
        self.soffset_labels.clear()  # Clear s-offset labels
        self.project = None
        self.image_item = None
        self.image_np = None
        self.current_polyline = None
        self.current_polyline_item = None
        self.selected_polyline_id = None
        self.selected_junction_id = None
        self.selected_connecting_road_id = None

    def set_drawing_mode(self, enabled: bool):
        """Enable or disable drawing mode."""
        self.drawing_mode = enabled

        if enabled:
            # Start a new polyline
            self.current_polyline = Polyline()
            self.current_polyline_item = PolylineGraphicsItem(self.current_polyline, self.scene)
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
        else:
            # Finish current polyline
            if self.current_polyline and self.current_polyline.is_valid():
                self.polyline_items[self.current_polyline.id] = self.current_polyline_item
                self.polyline_added.emit(self.current_polyline)
            else:
                # Remove orphan graphics if polyline is invalid
                if self.current_polyline_item:
                    self.current_polyline_item.remove()

            self.current_polyline = None
            self.current_polyline_item = None
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)

    def finish_current_polyline(self):
        """Finish current polyline and start a new one (keeping drawing mode active)."""
        if self.drawing_mode and self.current_polyline and self.current_polyline.is_valid():
            # Save the current polyline
            self.polyline_items[self.current_polyline.id] = self.current_polyline_item
            self.polyline_added.emit(self.current_polyline)

            # Start a new polyline
            self.current_polyline = Polyline()
            self.current_polyline_item = PolylineGraphicsItem(self.current_polyline, self.scene)

    def set_junction_mode(self, enabled: bool):
        """Enable or disable junction placement mode."""
        self.junction_mode = enabled
        if enabled:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
        else:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)

    def set_signal_mode(self, enabled: bool):
        """Enable or disable signal placement mode."""
        self.signal_mode = enabled
        if enabled:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
        else:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)

    def set_object_mode(self, enabled: bool, object_type: Optional[ObjectType] = None):
        """Enable or disable object placement mode."""
        self.object_mode = enabled
        self.object_type_to_place = object_type
        if enabled:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
        else:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            # Clean up any partial guardrail
            if self.drawing_guardrail:
                self.drawing_guardrail = False
                self.guardrail_points.clear()

    def set_pick_point_mode(self, enabled: bool):
        """Enable or disable point picking mode for georeferencing."""
        self.pick_point_mode = enabled
        if enabled:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
        else:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)

    def set_measure_mode(self, enabled: bool):
        """Enable or disable measure mode."""
        self.measure_mode = enabled
        if enabled:
            self.measure_points.clear()
        else:
            # Clear all measurement graphics
            self._clear_measurements()

    def _clear_measurements(self):
        """Clear all measurement graphics from the scene."""
        for item in self.measurement_items:
            self.scene.removeItem(item)
        self.measurement_items.clear()
        self.measure_points.clear()

    def set_show_scale_mode(self, enabled: bool):
        """Enable or disable show scale mode."""
        self.show_scale_mode = enabled
        if not enabled:
            # Clear all scale graphics
            self._clear_scale_displays()

    def _clear_scale_displays(self):
        """Clear all scale display graphics from the scene."""
        for item in self.scale_items:
            self.scene.removeItem(item)
        self.scale_items.clear()

    def set_uncertainty_overlay(self, overlay):
        """
        Add or remove uncertainty overlay.

        Args:
            overlay: UncertaintyOverlay instance or None to remove
        """
        # Remove existing overlay
        if self.uncertainty_overlay is not None:
            if self.uncertainty_overlay.scene() == self.scene:
                self.scene.removeItem(self.uncertainty_overlay)
            self.uncertainty_overlay = None

        # Add new overlay
        if overlay is not None:
            self.uncertainty_overlay = overlay
            self.scene.addItem(overlay)
            overlay.setZValue(50)  # Above image, below polylines

    def _display_scale_at_point(self, pos: QPointF):
        """Display scale factor at a clicked point."""
        x, y = pos.x(), pos.y()

        # Draw a small dot at the click location
        radius = 3
        pen = QPen(QColor(255, 200, 0), 2)  # Orange/yellow
        brush = QBrush(QColor(255, 200, 0))

        dot = self.scene.addEllipse(
            x - radius, y - radius,
            radius * 2, radius * 2,
            pen, brush
        )
        dot.setZValue(20)
        self.scale_items.append(dot)

        # Calculate scale at this point (returns text and background color)
        scale_text, bg_color = self._calculate_scale_at_point(x, y)

        # Draw text with background
        font = QFont("Arial", 10, QFont.Weight.Bold)
        text_item = self.scene.addText(scale_text, font)
        text_item.setDefaultTextColor(QColor(255, 255, 255))
        text_item.setZValue(21)

        # Get text bounding rect
        text_rect = text_item.boundingRect()

        # Position text slightly offset from point
        offset_x = 10
        offset_y = -10
        text_x = x + offset_x
        text_y = y + offset_y - text_rect.height()

        # Create background rectangle with uncertainty-based color
        padding = 4
        bg_rect = text_rect.adjusted(-padding, -padding, padding, padding)
        bg_item = self.scene.addRect(
            text_x + bg_rect.x(),
            text_y + bg_rect.y(),
            bg_rect.width(),
            bg_rect.height(),
            QPen(Qt.PenStyle.NoPen),
            QBrush(bg_color)  # Use color-coded background
        )
        bg_item.setZValue(20)

        text_item.setPos(text_x, text_y)

        # Add to cleanup list
        self.scale_items.append(bg_item)
        self.scale_items.append(text_item)

    def _calculate_scale_at_point(self, x: float, y: float) -> Tuple[str, QColor]:
        """
        Calculate scale factor and uncertainty at a specific point.

        For homography, calculates local scale by checking distances
        in pixel space vs meter space.

        Returns:
            (display_text, background_color)
        """
        if not self.project or not self.project.has_georeferencing():
            return ("No georef", QColor(255, 255, 255, 200))

        try:
            from orbit.utils import create_transformer, TransformMethod
            from orbit.utils.uncertainty_estimator import UncertaintyEstimator

            # Get transform method from project
            method = TransformMethod.HOMOGRAPHY if self.project.transform_method == 'homography' else TransformMethod.AFFINE
            transformer = create_transformer(self.project.control_points, method, use_validation=True)

            if not transformer:
                return ("Transform error", QColor(255, 255, 255, 200))

            # Calculate scale at this point by sampling nearby points
            # Use small offset to calculate local scale
            offset = 5.0  # pixels

            # Horizontal scale (X direction)
            mx1, my1 = transformer.pixel_to_meters(x, y)
            mx2, my2 = transformer.pixel_to_meters(x + offset, y)
            dist_m_x = ((mx2 - mx1)**2 + (my2 - my1)**2)**0.5
            scale_x = dist_m_x / offset  # meters per pixel

            # Vertical scale (Y direction)
            mx3, my3 = transformer.pixel_to_meters(x, y + offset)
            dist_m_y = ((mx3 - mx1)**2 + (my3 - my1)**2)**0.5
            scale_y = dist_m_y / offset  # meters per pixel

            # NEW: Calculate uncertainty
            try:
                # Create uncertainty estimator
                if self.image_item:
                    pixmap = self.image_item.pixmap()
                    estimator = UncertaintyEstimator(transformer,
                                                     pixmap.width(),
                                                     pixmap.height(),
                                                     baseline_uncertainty=self.project.baseline_uncertainty_m)

                    # Load cached grid if available
                    if self.project.uncertainty_grid_cache:
                        import numpy as np
                        estimator._cached_grid = np.array(self.project.uncertainty_grid_cache)

                    # Get scale uncertainty
                    unc_x, unc_y = estimator.estimate_scale_uncertainty_at_point(x, y)

                    # Get position uncertainty
                    pos_unc = estimator.estimate_position_uncertainty_at_point(x, y)

                    # Format with uncertainty ranges
                    text = (f"X: {scale_x * 100:.2f} ± {unc_x:.2f} cm/px\n"
                           f"Y: {scale_y * 100:.2f} ± {unc_y:.2f} cm/px\n"
                           f"Confidence: {self._get_confidence_label(pos_unc)} ({pos_unc:.2f}m)")

                    # Get background color based on uncertainty
                    bg_color = self._get_uncertainty_color(pos_unc)

                    return (text, bg_color)
                else:
                    # Fallback if no image
                    text = f"X: {scale_x * 100:.2f} cm/px\nY: {scale_y * 100:.2f} cm/px"
                    return (text, QColor(255, 255, 255, 200))

            except Exception:
                # Fallback to existing format if uncertainty calculation fails
                text = f"X: {scale_x * 100:.2f} cm/px\nY: {scale_y * 100:.2f} cm/px"
                return (text, QColor(255, 255, 255, 200))

        except Exception as e:
            return (f"Error: {str(e)}", QColor(255, 255, 255, 200))

    def _get_confidence_label(self, uncertainty: float) -> str:
        """
        Get confidence label based on uncertainty.

        Args:
            uncertainty: Position uncertainty in meters

        Returns:
            Confidence label string
        """
        if uncertainty < 0.1:
            return "Excellent"
        elif uncertainty < 0.2:
            return "Good"
        elif uncertainty < 0.4:
            return "Warning"
        else:
            return "Poor"

    def _get_uncertainty_color(self, uncertainty: float) -> QColor:
        """
        Get background color based on uncertainty level.

        Args:
            uncertainty: Position uncertainty in meters

        Returns:
            QColor for background
        """
        alpha = 150  # Semi-transparent background

        if uncertainty < 0.1:
            return QColor(0, 255, 0, alpha)       # Green
        elif uncertainty < 0.2:
            return QColor(255, 255, 0, alpha)     # Yellow
        elif uncertainty < 0.4:
            return QColor(255, 165, 0, alpha)     # Orange
        else:
            return QColor(255, 0, 0, alpha)       # Red

    def _draw_measure_point(self, pos: QPointF):
        """Draw a white dot at the measurement point."""
        radius = 4  # 2/3 of previous 6 (diameter 8 vs 12)
        pen = QPen(QColor(255, 255, 255), 2)
        brush = QBrush(QColor(255, 255, 255))

        dot = self.scene.addEllipse(
            pos.x() - radius, pos.y() - radius,
            radius * 2, radius * 2,
            pen, brush
        )
        dot.setZValue(20)  # Above everything else
        self.measurement_items.append(dot)

    def _draw_measurement(self):
        """Draw line and distance text between two measurement points."""
        if len(self.measure_points) != 2:
            return

        p1 = self.measure_points[0]
        p2 = self.measure_points[1]

        # Draw white line between points
        pen = QPen(QColor(255, 255, 255), 2)
        line = self.scene.addLine(p1.x(), p1.y(), p2.x(), p2.y(), pen)
        line.setZValue(19)
        self.measurement_items.append(line)

        # Calculate distance
        distance_text = self._calculate_distance(p1.x(), p1.y(), p2.x(), p2.y())

        # Draw text with background at midpoint
        mid_x = (p1.x() + p2.x()) / 2
        mid_y = (p1.y() + p2.y()) / 2

        # Create text item
        from PyQt6.QtWidgets import QGraphicsTextItem
        from PyQt6.QtGui import QFont
        text_item = QGraphicsTextItem(distance_text)
        text_item.setDefaultTextColor(QColor(255, 255, 255))
        font = QFont()
        font.setBold(True)
        font.setPointSize(12)
        text_item.setFont(font)

        # Position text centered at midpoint
        text_rect = text_item.boundingRect()
        text_item.setPos(mid_x - text_rect.width() / 2, mid_y - text_rect.height() / 2)
        text_item.setZValue(21)

        # Create background rectangle
        bg_rect = text_item.boundingRect()
        bg_rect.adjust(-5, -2, 5, 2)  # Add padding
        bg_pen = QPen(QColor(0, 0, 0, 0))  # Transparent border
        bg_brush = QBrush(QColor(0, 0, 0, 180))  # Semi-transparent dark background
        bg_item = self.scene.addRect(
            mid_x + bg_rect.x() - 5,
            mid_y + bg_rect.y() - 2,
            bg_rect.width(),
            bg_rect.height(),
            bg_pen, bg_brush
        )
        bg_item.setZValue(20)

        # Add items to list for cleanup
        self.measurement_items.append(bg_item)
        self.scene.addItem(text_item)
        self.measurement_items.append(text_item)

    def _calculate_distance(self, x1: float, y1: float, x2: float, y2: float) -> str:
        """
        Calculate distance between two points in pixels and meters.

        Returns formatted string with both pixel and meter distances (two lines).
        """
        import math

        # Calculate pixel distance
        dx = x2 - x1
        dy = y2 - y1
        pixel_distance = math.sqrt(dx * dx + dy * dy)

        pixel_str = f"{pixel_distance:.1f} px"
        meter_str = None

        # Check if we have georeferencing to convert to meters
        if self.project and self.project.has_georeferencing():
            try:
                from orbit.utils import create_transformer, TransformMethod

                # Get transform method from project
                method = TransformMethod.HOMOGRAPHY if self.project.transform_method == 'homography' else TransformMethod.AFFINE
                transformer = create_transformer(self.project.control_points, method, use_validation=True)

                if transformer:
                    # Convert both points to meters
                    mx1, my1 = transformer.pixel_to_meters(x1, y1)
                    mx2, my2 = transformer.pixel_to_meters(x2, y2)

                    # Calculate metric distance
                    meter_distance = math.sqrt((mx2 - mx1) ** 2 + (my2 - my1) ** 2)

                    # Format based on distance
                    if meter_distance < 1.0:
                        meter_str = f"{meter_distance * 100:.1f} cm"
                    elif meter_distance < 1000:
                        meter_str = f"{meter_distance:.2f} m"
                    else:
                        meter_str = f"{meter_distance / 1000:.3f} km"
            except Exception:
                pass

        # Return both pixel and meter (if available) on separate lines
        if meter_str:
            return f"{pixel_str}\n{meter_str}"
        else:
            return pixel_str

    def delete_selected(self):
        """Delete the currently selected polyline or junction."""
        if self.selected_polyline_id and self.selected_polyline_id in self.polyline_items:
            item = self.polyline_items[self.selected_polyline_id]
            item.remove()
            # Remove s-offset labels for this polyline
            if self.selected_polyline_id in self.soffset_labels:
                for text_item, bg_item in self.soffset_labels[self.selected_polyline_id]:
                    if text_item.scene() == self.scene:
                        self.scene.removeItem(text_item)
                    if bg_item.scene() == self.scene:
                        self.scene.removeItem(bg_item)
                del self.soffset_labels[self.selected_polyline_id]
            del self.polyline_items[self.selected_polyline_id]
            self.polyline_deleted.emit(self.selected_polyline_id)
            self.selected_polyline_id = None
        elif self.selected_junction_id and self.selected_junction_id in self.junction_items:
            item = self.junction_items[self.selected_junction_id]
            item.remove()
            del self.junction_items[self.selected_junction_id]
            self.junction_deleted.emit(self.selected_junction_id)
            self.selected_junction_id = None

    def highlight_polyline(self, polyline_id: str):
        """Highlight a specific polyline."""
        # Clear previous selection
        if self.selected_polyline_id and self.selected_polyline_id in self.polyline_items:
            self.polyline_items[self.selected_polyline_id].set_selected(False)

        # Select the new polyline
        if polyline_id in self.polyline_items:
            self.selected_polyline_id = polyline_id
            self.polyline_items[polyline_id].set_selected(True)

            # Center view on the polyline
            polyline = self.polyline_items[polyline_id].polyline
            if polyline.points:
                # Calculate center of polyline
                xs = [p[0] for p in polyline.points]
                ys = [p[1] for p in polyline.points]
                center_x = sum(xs) / len(xs)
                center_y = sum(ys) / len(ys)
                self.centerOn(center_x, center_y)

    def highlight_junction(self, junction_id: str):
        """Highlight a specific junction."""
        # Clear previous junction selection
        for jid, item in self.junction_items.items():
            if jid == junction_id:
                item.set_selected(True)
            else:
                item.set_selected(False)

        # Center view on the junction
        if junction_id in self.junction_items:
            junction = self.junction_items[junction_id].junction
            if junction.center_point:
                x, y = junction.center_point
                self.centerOn(x, y)

    def select_signal(self, signal_id: str):
        """
        Select and highlight a signal on the map.

        Args:
            signal_id: ID of the signal to select
        """
        # Clear previous selections
        if self.selected_polyline_id and self.selected_polyline_id in self.polyline_items:
            self.polyline_items[self.selected_polyline_id].set_selected(False)
            self.selected_polyline_id = None
        if self.selected_junction_id and self.selected_junction_id in self.junction_items:
            self.junction_items[self.selected_junction_id].set_selected(False)
            self.selected_junction_id = None
        if self.selected_object_id and self.selected_object_id in self.object_items:
            self.object_items[self.selected_object_id].set_selected(False)
            self.selected_object_id = None
        if self.selected_signal_id and self.selected_signal_id in self.signal_items:
            self.signal_items[self.selected_signal_id].setSelected(False)

        # Select the new signal
        if signal_id in self.signal_items:
            self.selected_signal_id = signal_id
            self.signal_items[signal_id].setSelected(True)

            # Center view on the signal
            signal = self.signal_items[signal_id].signal
            if signal.position:
                x, y = signal.position
                self.centerOn(x, y)

    def select_object(self, object_id: str):
        """
        Select and highlight an object on the map.

        Args:
            object_id: ID of the object to select
        """
        # Clear previous selections
        if self.selected_polyline_id and self.selected_polyline_id in self.polyline_items:
            self.polyline_items[self.selected_polyline_id].set_selected(False)
            self.selected_polyline_id = None
        if self.selected_junction_id and self.selected_junction_id in self.junction_items:
            self.junction_items[self.selected_junction_id].set_selected(False)
            self.selected_junction_id = None
        if self.selected_signal_id and self.selected_signal_id in self.signal_items:
            self.signal_items[self.selected_signal_id].setSelected(False)
            self.selected_signal_id = None
        if self.selected_object_id and self.selected_object_id in self.object_items:
            self.object_items[self.selected_object_id].set_selected(False)

        # Select the new object
        if object_id in self.object_items:
            self.selected_object_id = object_id
            self.object_items[object_id].set_selected(True)

            # Center view on the object
            obj = self.object_items[object_id].obj
            if obj.position:
                x, y = obj.position
                self.centerOn(x, y)

    def _get_connecting_road_lane_id(self, junction, connecting_road_id: str, source_lane_id: int) -> int:
        """
        Determine which lane on a connecting road corresponds to a source lane.

        Maps source road lanes to connecting road lanes based on ordinal position.
        For example:
        - Source lane -1 (first right lane) -> Connecting road lane -1 (if it exists)
        - Source lane -2 (second right lane) -> Connecting road lane -2 (if it exists)
        - Source lane +1 (first left lane) -> Connecting road lane +1 (if it exists)

        Args:
            junction: Junction containing the connecting road
            connecting_road_id: ID of the connecting road
            source_lane_id: Lane ID on the source road

        Returns:
            Lane ID to use on the connecting road, or None if no valid mapping
        """
        conn_road = junction.get_connecting_road_by_id(connecting_road_id)
        if not conn_road:
            return -1  # Default to first right lane

        # Get available lanes on the connecting road
        right_lanes = list(range(-1, -(conn_road.lane_count_right + 1), -1))  # [-1, -2, ...]
        left_lanes = list(range(1, conn_road.lane_count_left + 1))  # [1, 2, ...]

        if source_lane_id < 0:
            # Source is a right lane, map to connecting road right lanes
            lane_ordinal = abs(source_lane_id) - 1  # 0-indexed ordinal
            if lane_ordinal < len(right_lanes):
                return right_lanes[lane_ordinal]
            elif right_lanes:
                return right_lanes[-1]  # Use last available right lane
            elif left_lanes:
                return left_lanes[0]  # Fall back to first left lane
            else:
                return -1  # Default
        else:
            # Source is a left lane, map to connecting road left lanes
            lane_ordinal = source_lane_id - 1  # 0-indexed ordinal
            if lane_ordinal < len(left_lanes):
                return left_lanes[lane_ordinal]
            elif left_lanes:
                return left_lanes[-1]  # Use last available left lane
            elif right_lanes:
                return right_lanes[0]  # Fall back to first right lane
            else:
                return -1  # Default

    def find_connected_lanes(self, road_id: str, section_number: int, lane_id: int) -> dict:
        """
        Find lanes connected to the specified lane via junctions and road links.

        Args:
            road_id: ID of the road containing the lane
            section_number: Section number containing the lane
            lane_id: Lane ID to find connections for

        Returns:
            Dictionary with:
            - 'road_lanes': List of (road_id, section_number, lane_id) tuples for connected road lanes
            - 'connecting_road_lanes': List of (connecting_road_id, lane_id) tuples
        """
        result = {
            'road_lanes': [],
            'connecting_road_lanes': []
        }

        if not self.project:
            return result

        road = self.project.get_road(road_id)
        if not road or not road.lane_sections:
            return result

        # Determine if this section is at the start or end of the road
        first_section = road.lane_sections[0].section_number
        last_section = road.lane_sections[-1].section_number
        is_first_section = (section_number == first_section)
        is_last_section = (section_number == last_section)

        # Check if predecessor/successor links should be skipped because they go through a junction
        # If both this road and its predecessor/successor are in the same junction, the link is stale
        skip_predecessor = False
        skip_successor = False
        for junction in self.project.junctions:
            connected_ids = set(junction.connected_road_ids)
            if road_id in connected_ids:
                # If predecessor is also in this junction, skip direct link
                if road.predecessor_id and road.predecessor_id in connected_ids:
                    skip_predecessor = True
                # If successor is also in this junction, skip direct link
                if road.successor_id and road.successor_id in connected_ids:
                    skip_successor = True

        # 1. Check direct road predecessor/successor links (not through junctions)
        # Skip if both roads are in the same junction - junction connections take precedence
        if is_first_section and road.predecessor_id and not skip_predecessor:
            pred_road = self.project.get_road(road.predecessor_id)
            if pred_road and pred_road.lane_sections:
                # Predecessor connects at its last section
                pred_section = pred_road.lane_sections[-1].section_number
                # Assume same lane exists in connected road (common case for continuous roads)
                result['road_lanes'].append((road.predecessor_id, pred_section, lane_id))

        if is_last_section and road.successor_id and not skip_successor:
            succ_road = self.project.get_road(road.successor_id)
            if succ_road and succ_road.lane_sections:
                # Successor connects at its first section
                succ_section = succ_road.lane_sections[0].section_number
                # Assume same lane exists in connected road (common case for continuous roads)
                result['road_lanes'].append((road.successor_id, succ_section, lane_id))

        # 2. Search all junctions for lane connections involving this lane
        for junction in self.project.junctions:
            for lane_conn in junction.lane_connections:
                # Check if this lane is the source (find successor via junction)
                if lane_conn.from_road_id == road_id and lane_conn.from_lane_id == lane_id:
                    # Only consider if this is the last section (connects to junction)
                    if is_last_section:
                        # Only add connecting road lane - don't show destination road beyond junction
                        if lane_conn.connecting_road_id:
                            conn_lane_id = self._get_connecting_road_lane_id(
                                junction, lane_conn.connecting_road_id, lane_id
                            )
                            if conn_lane_id is not None:
                                result['connecting_road_lanes'].append((lane_conn.connecting_road_id, conn_lane_id))

                # Check if this lane is the destination (find predecessor via junction)
                if lane_conn.to_road_id == road_id and lane_conn.to_lane_id == lane_id:
                    # Only consider if this is the first section (connects from junction)
                    if is_first_section:
                        # Only add connecting road lane - don't show source road beyond junction
                        if lane_conn.connecting_road_id:
                            conn_lane_id = self._get_connecting_road_lane_id(
                                junction, lane_conn.connecting_road_id, lane_conn.from_lane_id
                            )
                            if conn_lane_id is not None:
                                result['connecting_road_lanes'].append((lane_conn.connecting_road_id, conn_lane_id))

        return result

    def select_lane(self, road_id: str, section_number: int, lane_id: int):
        """
        Select and highlight a lane on the map.

        Also highlights connected lanes (predecessors, successors, and connecting road lanes)
        with a tinted fill to show the lane connection flow.

        Args:
            road_id: ID of the road
            section_number: Section number containing the lane
            lane_id: Lane ID within the section
        """
        # Clear previously linked polygons (check if still valid - Qt object may have been deleted)
        for polygon in self.linked_lane_polygons:
            try:
                if hasattr(polygon, 'set_linked') and polygon.scene() is not None:
                    polygon.set_linked(False)
            except RuntimeError:
                # Qt object has been deleted, skip it
                pass
        self.linked_lane_polygons.clear()

        # Deselect previous lane
        if self.selected_lane_key:
            prev_road_id, prev_section, prev_lane = self.selected_lane_key
            if prev_road_id in self.road_lanes_items:
                lanes_item = self.road_lanes_items[prev_road_id]
                for lane_polygon in lanes_item.lane_items:
                    if (isinstance(lane_polygon, InteractiveLanePolygon) and
                        lane_polygon.road_id == prev_road_id and
                        lane_polygon.section_number == prev_section and
                        lane_polygon.lane_id == prev_lane):
                        lane_polygon.set_selected(False)

        # Select new lane
        if road_id in self.road_lanes_items:
            lanes_item = self.road_lanes_items[road_id]
            for lane_polygon in lanes_item.lane_items:
                if (isinstance(lane_polygon, InteractiveLanePolygon) and
                    lane_polygon.road_id == road_id and
                    lane_polygon.section_number == section_number and
                    lane_polygon.lane_id == lane_id):
                    lane_polygon.set_selected(True)
                    self.selected_lane_key = (road_id, section_number, lane_id)
                    break

        # Find and highlight connected lanes
        connected = self.find_connected_lanes(road_id, section_number, lane_id)

        # Highlight connected road lanes
        for conn_road_id, conn_section, conn_lane_id in connected['road_lanes']:
            if conn_road_id in self.road_lanes_items:
                lanes_item = self.road_lanes_items[conn_road_id]
                for lane_polygon in lanes_item.lane_items:
                    if (isinstance(lane_polygon, InteractiveLanePolygon) and
                        lane_polygon.road_id == conn_road_id and
                        lane_polygon.section_number == conn_section and
                        lane_polygon.lane_id == conn_lane_id):
                        lane_polygon.set_linked(True)
                        self.linked_lane_polygons.append(lane_polygon)

        # Highlight connecting road lanes
        for conn_road_id, conn_lane_id in connected['connecting_road_lanes']:
            if conn_road_id in self.connecting_road_lanes_items:
                lanes_item = self.connecting_road_lanes_items[conn_road_id]
                for lane_polygon in lanes_item.lane_items:
                    if (isinstance(lane_polygon, InteractiveLanePolygon) and
                        lane_polygon.road_id == conn_road_id and
                        lane_polygon.lane_id == conn_lane_id):
                        lane_polygon.set_linked(True)
                        self.linked_lane_polygons.append(lane_polygon)

    def select_connecting_road_lane(self, connecting_road_id: str, lane_id: int):
        """
        Select and highlight a connecting road lane on the map.

        Also highlights the connected road lanes (from_road and to_road) with a tinted fill.

        Args:
            connecting_road_id: ID of the connecting road
            lane_id: Lane ID within the connecting road
        """
        # Clear previously linked polygons
        for polygon in self.linked_lane_polygons:
            try:
                if hasattr(polygon, 'set_linked') and polygon.scene() is not None:
                    polygon.set_linked(False)
            except RuntimeError:
                pass
        self.linked_lane_polygons.clear()

        # Deselect previous regular lane if any
        if self.selected_lane_key:
            prev_road_id, prev_section, prev_lane = self.selected_lane_key
            if prev_road_id in self.road_lanes_items:
                lanes_item = self.road_lanes_items[prev_road_id]
                for lane_polygon in lanes_item.lane_items:
                    if (isinstance(lane_polygon, InteractiveLanePolygon) and
                        lane_polygon.road_id == prev_road_id and
                        lane_polygon.section_number == prev_section and
                        lane_polygon.lane_id == prev_lane):
                        lane_polygon.set_selected(False)
            self.selected_lane_key = None

        # Select the connecting road lane
        if connecting_road_id in self.connecting_road_lanes_items:
            lanes_item = self.connecting_road_lanes_items[connecting_road_id]
            for lane_polygon in lanes_item.lane_items:
                if (isinstance(lane_polygon, InteractiveLanePolygon) and
                    lane_polygon.road_id == connecting_road_id and
                    lane_polygon.lane_id == lane_id):
                    lane_polygon.set_selected(True)
                    break

        # Find connected road lanes via lane connections
        if not self.project:
            return

        for junction in self.project.junctions:
            for lane_conn in junction.lane_connections:
                if lane_conn.connecting_road_id == connecting_road_id:
                    # Get the connecting road to check lane mapping
                    conn_road = junction.get_connecting_road_by_id(connecting_road_id)
                    if not conn_road:
                        continue

                    # Check if this lane connection corresponds to the selected lane
                    expected_lane = self._get_connecting_road_lane_id(
                        junction, connecting_road_id, lane_conn.from_lane_id
                    )
                    if expected_lane != lane_id:
                        continue

                    # Highlight the from_road lane (last section)
                    from_road = self.project.get_road(lane_conn.from_road_id)
                    if from_road and from_road.lane_sections:
                        from_section = from_road.lane_sections[-1].section_number
                        if lane_conn.from_road_id in self.road_lanes_items:
                            lanes_item = self.road_lanes_items[lane_conn.from_road_id]
                            for lane_polygon in lanes_item.lane_items:
                                if (isinstance(lane_polygon, InteractiveLanePolygon) and
                                    lane_polygon.road_id == lane_conn.from_road_id and
                                    lane_polygon.section_number == from_section and
                                    lane_polygon.lane_id == lane_conn.from_lane_id):
                                    lane_polygon.set_linked(True)
                                    self.linked_lane_polygons.append(lane_polygon)

                    # Highlight the to_road lane (first section)
                    to_road = self.project.get_road(lane_conn.to_road_id)
                    if to_road and to_road.lane_sections:
                        to_section = to_road.lane_sections[0].section_number
                        if lane_conn.to_road_id in self.road_lanes_items:
                            lanes_item = self.road_lanes_items[lane_conn.to_road_id]
                            for lane_polygon in lanes_item.lane_items:
                                if (isinstance(lane_polygon, InteractiveLanePolygon) and
                                    lane_polygon.road_id == lane_conn.to_road_id and
                                    lane_polygon.section_number == to_section and
                                    lane_polygon.lane_id == lane_conn.to_lane_id):
                                    lane_polygon.set_linked(True)
                                    self.linked_lane_polygons.append(lane_polygon)

    # View controls
    def zoom_in(self):
        """Zoom in by 20%."""
        self.scale(1.2, 1.2)

    def zoom_out(self):
        """Zoom out by 20%."""
        self.scale(1.0 / 1.2, 1.0 / 1.2)

    def fit_to_window(self):
        """Fit the image to the window."""
        if self.image_item:
            self.fitInView(self.image_item, Qt.AspectRatioMode.KeepAspectRatio)

    def reset_view(self):
        """Reset view to 100% scale."""
        self.resetTransform()

    def _show_signal_menu(self, view_pos, signal_id: str):
        """
        Show context menu for signal with Edit and Remove options.

        Args:
            view_pos: Position in view coordinates
            signal_id: ID of the signal
        """
        menu = QMenu()
        edit_action = menu.addAction("Edit Properties...")
        remove_action = menu.addAction("Remove Signal")

        # Show menu and get selected action
        action = menu.exec(self.mapToGlobal(view_pos))

        if action == edit_action:
            self.signal_edit_requested.emit(signal_id)
        elif action == remove_action:
            self.signal_deleted.emit(signal_id)

    def _is_click_on_object(self, item, scene_pos: QPointF, tolerance: float = 15.0) -> bool:
        """
        Check if a click is on an object, with better detection for different object types.

        Args:
            item: ObjectGraphicsItem to check
            scene_pos: Position in scene coordinates
            tolerance: Distance tolerance in pixels

        Returns:
            True if click is on the object, False otherwise
        """
        obj = item.obj

        # For polyline objects (guardrails), check if click is near any segment
        if obj.type.get_shape_type() == "polyline":
            if not obj.points or len(obj.points) < 2:
                return False

            for i in range(len(obj.points) - 1):
                x1, y1 = obj.points[i]
                x2, y2 = obj.points[i + 1]

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
                    return True

            return False

        # For point objects, check if click is within tolerance radius of the object position
        else:
            obj_x, obj_y = obj.position
            dist = ((scene_pos.x() - obj_x) ** 2 + (scene_pos.y() - obj_y) ** 2) ** 0.5

            # Use larger tolerance for point objects based on their dimensions
            radius = tolerance
            if obj.type.get_shape_type() == "circle":
                radius = max(tolerance, obj.dimensions.get('radius', 1.0) * 10)  # Assuming ~10 px per meter
            elif obj.type.get_shape_type() in ("rectangle", "cylinder"):
                # Use larger dimension as radius
                width = obj.dimensions.get('width', 1.0) * 10
                length = obj.dimensions.get('length', 1.0) * 10
                radius = max(tolerance, max(width, length) / 2)

            return dist <= radius

    def _show_object_menu(self, view_pos, object_id: str, scene_pos=None):
        """
        Show context menu for object with Edit and Remove options.
        For guardrails, also shows Delete Point option if over a point.

        Args:
            view_pos: Position in view coordinates
            object_id: ID of the object
            scene_pos: Optional scene position for checking point clicks
        """
        menu = QMenu()
        edit_action = menu.addAction("Edit Properties...")

        # Check if this is a guardrail and if we're over a point
        delete_point_action = None
        point_index = -1
        if scene_pos and object_id in self.object_items:
            item = self.object_items[object_id]
            if item.obj.type.get_shape_type() == "polyline":
                point_index = item.get_point_at(scene_pos)
                if point_index >= 0:
                    delete_point_action = menu.addAction("Delete Point")
                    menu.addSeparator()

        remove_action = menu.addAction("Remove Object")

        # Show menu and get selected action
        action = menu.exec(self.mapToGlobal(view_pos))

        if action == edit_action:
            self.object_edit_requested.emit(object_id)
        elif action == remove_action:
            self.object_deleted.emit(object_id)
        elif delete_point_action and action == delete_point_action:
            self._delete_guardrail_point(object_id, point_index)

    def _show_centerline_point_menu(self, view_pos, polyline_id: str, point_index: int):
        """
        Show context menu for centerline point with Delete, Split Section, and Split Road options.

        Args:
            view_pos: Position in view coordinates
            polyline_id: ID of the polyline
            point_index: Index of the point clicked
        """
        menu = QMenu()
        delete_action = menu.addAction("Delete Point")
        split_section_action = menu.addAction("Split Section Here")
        split_road_action = menu.addAction("Split Road Here")

        # Get the road that owns this centerline
        road = self._find_road_by_centerline(polyline_id)
        polyline = self.polyline_items[polyline_id].polyline

        if not road or not road.lane_sections:
            # No road or no sections - disable split section option
            split_section_action.setEnabled(False)

        if not road:
            # No road - disable split road option
            split_road_action.setEnabled(False)
        elif point_index == 0 or point_index >= polyline.point_count() - 1:
            # Cannot split at first or last point (would create empty road)
            split_road_action.setEnabled(False)

        # Show menu and get selected action
        action = menu.exec(self.mapToGlobal(view_pos))

        if action == delete_action:
            self._delete_point(polyline_id, point_index)
        elif action == split_section_action and road:
            # Warn if creating a small section
            s_coords = road.calculate_centerline_s_coordinates(polyline.points)
            if point_index < len(s_coords):
                s = s_coords[point_index]
                section = road.get_section_at_s(s)
                if section:
                    section_length = section.get_length_pixels()
                    distance_from_start = s - section.s_start
                    distance_from_end = section.s_end - s
                    min_distance = min(distance_from_start, distance_from_end)

                    # Warn if within 5% of section length
                    if min_distance < section_length * 0.05:
                        if not ask_yes_no(self, f"This will create a very small section ({min_distance:.1f} pixels).\n\nContinue anyway?", "Small Section Warning"):
                            return

            # Emit signal for MainWindow to handle
            self.section_split_requested.emit(road.id, polyline_id, point_index)
        elif action == split_road_action and road:
            # Emit signal for MainWindow to handle road splitting
            self.road_split_requested.emit(road.id, polyline_id, point_index)

    def _find_road_by_centerline(self, polyline_id: str) -> Optional[Road]:
        """
        Find the road that has this polyline as its centerline.

        Args:
            polyline_id: ID of the polyline to search for

        Returns:
            Road if found, None otherwise
        """
        if not self.project:
            return None

        for road in self.project.roads:
            if road.centerline_id == polyline_id:
                return road
        return None

    def _delete_point(self, polyline_id: str, point_index: int):
        """
        Delete a point from a polyline.

        Args:
            polyline_id: ID of the polyline
            point_index: Index of the point to delete
        """
        item = self.polyline_items[polyline_id]
        polyline = item.polyline

        # If this is a centerline, update section boundaries before deleting
        affected_road = None
        if polyline.line_type == LineType.CENTERLINE and self.project:
            for road in self.project.roads:
                if road.centerline_id == polyline_id:
                    affected_road = road
                    road.adjust_section_indices_after_deletion(point_index)
                    break

        item.polyline.remove_point(point_index)

        # Check if polyline has no points left - delete it
        if item.polyline.point_count() == 0:
            item.remove()
            del self.polyline_items[polyline_id]
            # Remove s-offset labels if they exist
            if polyline_id in self.soffset_labels:
                for text_item, bg_item in self.soffset_labels[polyline_id]:
                    if text_item.scene() == self.scene:
                        self.scene.removeItem(text_item)
                    if bg_item.scene() == self.scene:
                        self.scene.removeItem(bg_item)
                del self.soffset_labels[polyline_id]
            self.polyline_deleted.emit(polyline_id)
        else:
            # Update section boundaries with new point list
            if affected_road:
                affected_road.update_section_boundaries(polyline.points)
                # Refresh lane graphics
                if affected_road.id in self.road_lanes_items:
                    self.road_lanes_items[affected_road.id].update_graphics()

            item.update_graphics()
            self.polyline_modified.emit(polyline_id)
            # Update s-offset labels after point deletion
            if self.soffsets_visible:
                self._update_soffset_labels(polyline_id)

    def _delete_guardrail_point(self, object_id: str, point_index: int):
        """
        Delete a point from a guardrail.

        Args:
            object_id: ID of the guardrail object
            point_index: Index of the point to delete
        """
        if object_id not in self.object_items:
            return

        item = self.object_items[object_id]
        obj = item.obj

        # Don't delete if only 2 points left (minimum for a line)
        if len(obj.points) <= 2:
            show_warning(self, "A guardrail must have at least 2 points.", "Cannot Delete Point")
            return

        # Delete the point
        obj.points.pop(point_index)

        # Update validity length
        if obj.points and len(obj.points) >= 2:
            total_length = 0.0
            for i in range(len(obj.points) - 1):
                x1, y1 = obj.points[i]
                x2, y2 = obj.points[i + 1]
                total_length += ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
            obj.validity_length = total_length

        # Refresh graphics
        item.update_graphics()
        self.object_modified.emit(object_id)

    # Event handlers
    def wheelEvent(self, event: QWheelEvent):
        """Handle mouse wheel for zooming."""
        if event.angleDelta().y() > 0:
            self.scale(1.1, 1.1)
        else:
            self.scale(1.0 / 1.1, 1.0 / 1.1)

    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press events."""
        scene_pos = self.mapToScene(event.pos())

        if event.button() == Qt.MouseButton.LeftButton:
            if self.drawing_mode:
                # Add point to current polyline
                self.current_polyline.add_point(scene_pos.x(), scene_pos.y())
                self.current_polyline_item.update_graphics()

            elif self.junction_mode:
                # Create junction at click position
                junction = Junction()
                junction.center_point = (scene_pos.x(), scene_pos.y())
                self.junction_added.emit(junction)

            elif self.signal_mode:
                # Signal placement requires dialog - emit request to open dialog
                # The MainWindow will handle showing SignalSelectionDialog
                self.signal_placement_requested.emit(scene_pos.x(), scene_pos.y())

            elif self.object_mode:
                # Object placement - handle differently for guardrails (polyline) vs point objects
                if self.object_type_to_place and self.object_type_to_place.get_shape_type() == "polyline":
                    # Start drawing guardrail polyline
                    self.drawing_guardrail = True
                    self.guardrail_points = [(scene_pos.x(), scene_pos.y())]
                else:
                    # Point object - emit request to open dialog (MainWindow will create object)
                    self.object_placement_requested.emit(scene_pos.x(), scene_pos.y(), self.object_type_to_place)

            elif self.pick_point_mode:
                # Emit picked point coordinates
                self.point_picked.emit(scene_pos.x(), scene_pos.y())
                # Turn off pick mode after selecting
                self.pick_point_mode = False
                self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)

            else:
                # Check if Ctrl+Click on a line segment to insert a point
                if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    # First check guardrails
                    for object_id, object_item in self.object_items.items():
                        if object_item.obj.type.get_shape_type() == "polyline":
                            segment_index = object_item.get_segment_at(scene_pos)
                            if segment_index >= 0:
                                insert_index = segment_index + 1
                                obj = object_item.obj
                                # Insert point after the first point of the segment
                                obj.points.insert(insert_index, (scene_pos.x(), scene_pos.y()))
                                # Update validity length
                                if obj.points and len(obj.points) >= 2:
                                    total_length = 0.0
                                    for i in range(len(obj.points) - 1):
                                        x1, y1 = obj.points[i]
                                        x2, y2 = obj.points[i + 1]
                                        total_length += ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
                                    obj.validity_length = total_length
                                object_item.update_graphics()
                                self.object_modified.emit(object_id)
                                return

                    # Then check polylines
                    for polyline_id, item in self.polyline_items.items():
                        segment_index = item.get_segment_at(scene_pos)
                        if segment_index >= 0:
                            insert_index = segment_index + 1
                            polyline = item.polyline

                            # If this is a centerline, adjust section indices before inserting
                            affected_road = None
                            if polyline.line_type == LineType.CENTERLINE and self.project:
                                for road in self.project.roads:
                                    if road.centerline_id == polyline_id:
                                        affected_road = road
                                        road.adjust_section_indices_after_insertion(insert_index)
                                        break

                            # Insert point after the first point of the segment
                            polyline.insert_point(insert_index, scene_pos.x(), scene_pos.y())

                            # Update section boundaries with new point list
                            if affected_road:
                                affected_road.update_section_boundaries(polyline.points)
                                # Refresh lane graphics
                                if affected_road.id in self.road_lanes_items:
                                    self.road_lanes_items[affected_road.id].update_graphics()

                            item.update_graphics()
                            self.polyline_modified.emit(polyline_id)
                            # Update s-offset labels after point insertion
                            if self.soffsets_visible:
                                self._update_soffset_labels(polyline_id)
                            return

                    # Then check connecting roads for Ctrl+Click insertion
                    # Only allow insertion for polyline geometry (not ParamPoly3D)
                    for conn_road_id, item in self.connecting_road_centerline_items.items():
                        if item.connecting_road.geometry_type != "polyline":
                            continue  # Skip ParamPoly3D curves (read-only)
                        segment_index = item.get_segment_at(scene_pos)
                        if segment_index >= 0:
                            # Find the connecting road in junctions
                            connecting_road = None
                            parent_junction = None
                            for junction in self.project.junctions:
                                for cr in junction.connecting_roads:
                                    if cr.id == conn_road_id:
                                        connecting_road = cr
                                        parent_junction = junction
                                        break
                                if connecting_road:
                                    break

                            if connecting_road:
                                insert_index = segment_index + 1
                                # Insert point after the first point of the segment
                                connecting_road.path.insert(insert_index, (scene_pos.x(), scene_pos.y()))
                                item.update_graphics()
                                # Update lane graphics
                                if conn_road_id in self.connecting_road_lanes_items:
                                    self.connecting_road_lanes_items[conn_road_id].update_graphics()
                                # Emit modification signal
                                # TODO: Add connecting_road_modified signal if needed
                                return

                # Check if clicking on a junction to drag
                for junction_id, item in self.junction_items.items():
                    if item.is_at_position(scene_pos):
                        self.dragging_junction = True
                        self.drag_junction_id = junction_id
                        return

                # Check if clicking on a guardrail point to drag
                for object_id, item in self.object_items.items():
                    if item.obj.type.get_shape_type() == "polyline":
                        point_index = item.get_point_at(scene_pos)
                        if point_index >= 0:
                            self.dragging_guardrail_point = True
                            self.drag_object_id = object_id
                            self.drag_point_index = point_index
                            return

                # Check if clicking on a point to drag
                for polyline_id, item in self.polyline_items.items():
                    point_index = item.get_point_at(scene_pos)
                    if point_index >= 0:
                        self.dragging_point = True
                        self.drag_polyline_id = polyline_id
                        self.drag_point_index = point_index
                        item.set_selected_point(point_index)
                        return

                # Check if clicking on a connecting road point to drag
                # Only allow dragging for polyline geometry (not ParamPoly3D)
                for conn_road_id, item in self.connecting_road_centerline_items.items():
                    if item.connecting_road.geometry_type != "polyline":
                        continue  # Skip ParamPoly3D curves (read-only)
                    point_index = item.get_point_at(scene_pos)
                    if point_index >= 0:
                        self.dragging_connecting_road_point = True
                        self.drag_connecting_road_id = conn_road_id
                        self.drag_point_index = point_index
                        item.selected_point_index = point_index
                        item.update_graphics()
                        return

                # Check if clicking on a junction to select
                clicked_junction_id = None
                for junction_id, item in self.junction_items.items():
                    if item.is_at_position(scene_pos):
                        clicked_junction_id = junction_id
                        break

                # Check if clicking on a signal to select
                clicked_signal_id = None
                if not clicked_junction_id:
                    for signal_id, item in self.signal_items.items():
                        # Check if click is near signal position (within 20 pixels)
                        if item.signal.position:
                            sx, sy = item.signal.position
                            dist = ((scene_pos.x() - sx) ** 2 + (scene_pos.y() - sy) ** 2) ** 0.5
                            if dist < 20:
                                clicked_signal_id = signal_id
                                break

                # Check if clicking on an object to select
                clicked_object_id = None
                if not clicked_junction_id and not clicked_signal_id:
                    for object_id, item in self.object_items.items():
                        if self._is_click_on_object(item, scene_pos):
                            clicked_object_id = object_id
                            break

                # Check if clicking on a polyline to select
                clicked_polyline_id = None
                if not clicked_junction_id and not clicked_signal_id and not clicked_object_id:
                    for polyline_id, item in self.polyline_items.items():
                        if item.is_near_line(scene_pos):
                            clicked_polyline_id = polyline_id
                            break

                # Update selection
                if clicked_junction_id:
                    # Select junction
                    if self.selected_polyline_id:
                        self.polyline_items[self.selected_polyline_id].set_selected(False)
                        self.selected_polyline_id = None
                    if self.selected_signal_id and self.selected_signal_id in self.signal_items:
                        self.signal_items[self.selected_signal_id].setSelected(False)
                        self.selected_signal_id = None
                    if self.selected_object_id and self.selected_object_id in self.object_items:
                        self.object_items[self.selected_object_id].set_selected(False)
                        self.selected_object_id = None
                    if self.selected_junction_id:
                        self.junction_items[self.selected_junction_id].set_selected(False)
                    self.selected_junction_id = clicked_junction_id
                    self.junction_items[clicked_junction_id].set_selected(True)
                    # Emit signal so tree can update selection
                    self.junction_selected.emit(clicked_junction_id)
                elif clicked_signal_id:
                    # Select signal
                    if self.selected_junction_id:
                        self.junction_items[self.selected_junction_id].set_selected(False)
                        self.selected_junction_id = None
                    if self.selected_polyline_id:
                        self.polyline_items[self.selected_polyline_id].set_selected(False)
                        self.selected_polyline_id = None
                    if self.selected_object_id and self.selected_object_id in self.object_items:
                        self.object_items[self.selected_object_id].set_selected(False)
                        self.selected_object_id = None
                    if self.selected_signal_id and self.selected_signal_id in self.signal_items:
                        self.signal_items[self.selected_signal_id].setSelected(False)
                    self.selected_signal_id = clicked_signal_id
                    self.signal_items[clicked_signal_id].setSelected(True)
                    # Emit signal so tree can update selection
                    self.signal_selected.emit(clicked_signal_id)
                elif clicked_object_id:
                    # Select object
                    if self.selected_junction_id:
                        self.junction_items[self.selected_junction_id].set_selected(False)
                        self.selected_junction_id = None
                    if self.selected_signal_id and self.selected_signal_id in self.signal_items:
                        self.signal_items[self.selected_signal_id].setSelected(False)
                        self.selected_signal_id = None
                    if self.selected_polyline_id:
                        self.polyline_items[self.selected_polyline_id].set_selected(False)
                        self.selected_polyline_id = None
                    if self.selected_object_id and self.selected_object_id in self.object_items:
                        self.object_items[self.selected_object_id].set_selected(False)
                    self.selected_object_id = clicked_object_id
                    self.object_items[clicked_object_id].set_selected(True)
                    # Emit signal so tree can update selection
                    self.object_selected.emit(clicked_object_id)
                elif clicked_polyline_id:
                    # Select polyline
                    if self.selected_junction_id:
                        self.junction_items[self.selected_junction_id].set_selected(False)
                        self.selected_junction_id = None
                    if self.selected_signal_id and self.selected_signal_id in self.signal_items:
                        self.signal_items[self.selected_signal_id].setSelected(False)
                        self.selected_signal_id = None
                    if self.selected_object_id and self.selected_object_id in self.object_items:
                        self.object_items[self.selected_object_id].set_selected(False)
                        self.selected_object_id = None
                    if self.selected_polyline_id:
                        self.polyline_items[self.selected_polyline_id].set_selected(False)
                    self.selected_polyline_id = clicked_polyline_id
                    self.polyline_items[clicked_polyline_id].set_selected(True)
                    # Emit signal so tree can update selection
                    self.polyline_selected.emit(clicked_polyline_id)
                else:
                    # Deselect all
                    if self.selected_polyline_id:
                        self.polyline_items[self.selected_polyline_id].set_selected(False)
                        self.selected_polyline_id = None
                    if self.selected_junction_id:
                        self.junction_items[self.selected_junction_id].set_selected(False)
                        self.selected_junction_id = None
                    if self.selected_signal_id and self.selected_signal_id in self.signal_items:
                        self.signal_items[self.selected_signal_id].setSelected(False)
                        self.selected_signal_id = None
                    if self.selected_object_id and self.selected_object_id in self.object_items:
                        self.object_items[self.selected_object_id].set_selected(False)
                        self.selected_object_id = None

        elif event.button() == Qt.MouseButton.RightButton:
            if self.measure_mode:
                # Add point to measurement
                self.measure_points.append(scene_pos)

                # Draw white dot at click location
                self._draw_measure_point(scene_pos)

                # If we have two points, draw line and distance
                if len(self.measure_points) == 2:
                    self._draw_measurement()
                    # Reset for next measurement pair
                    self.measure_points.clear()

            elif self.show_scale_mode:
                # Display scale factor at this point
                self._display_scale_at_point(scene_pos)

            elif self.drawing_guardrail:
                # Right-click while drawing guardrail - add point
                self.guardrail_points.append((scene_pos.x(), scene_pos.y()))
                return

            elif not self.drawing_mode and not self.signal_mode and not self.object_mode:
                # Check if right-clicking on a signal
                for signal_id, item in self.signal_items.items():
                    # Check if click is within signal bounds
                    if item.contains(item.mapFromScene(scene_pos)):
                        self._show_signal_menu(event.pos(), signal_id)
                        return

                # Check if right-clicking on an object
                for object_id, item in self.object_items.items():
                    if self._is_click_on_object(item, scene_pos):
                        self._show_object_menu(event.pos(), object_id, scene_pos)
                        return

                # Right-click to show context menu or delete point
                for polyline_id, item in self.polyline_items.items():
                    point_index = item.get_point_at(scene_pos)
                    if point_index >= 0:
                        # Check if this is a centerline - if so, show context menu
                        if item.polyline.line_type == LineType.CENTERLINE:
                            self._show_centerline_point_menu(event.pos(), polyline_id, point_index)
                        else:
                            # For non-centerline polylines, just delete the point
                            self._delete_point(polyline_id, point_index)
                        return

                # Check if right-clicking on a connecting road point to delete
                # Only allow deletion for polyline geometry (not ParamPoly3D)
                for conn_road_id, item in self.connecting_road_centerline_items.items():
                    if item.connecting_road.geometry_type != "polyline":
                        continue  # Skip ParamPoly3D curves (read-only)
                    point_index = item.get_point_at(scene_pos)
                    if point_index >= 0:
                        # Delete the point from connecting road
                        connecting_road = item.connecting_road
                        if len(connecting_road.path) > 2:  # Keep at least 2 points
                            connecting_road.path.pop(point_index)
                            item.update_graphics()
                            # Update lane graphics
                            if conn_road_id in self.connecting_road_lanes_items:
                                self.connecting_road_lanes_items[conn_road_id].update_graphics()
                        return

            elif self.signal_mode:
                # In signal mode, also allow right-click context menu on existing signals
                for signal_id, item in self.signal_items.items():
                    if item.contains(item.mapFromScene(scene_pos)):
                        self._show_signal_menu(event.pos(), signal_id)
                        return

            elif self.object_mode:
                # In object mode, allow right-click context menu on existing objects
                for object_id, item in self.object_items.items():
                    if self._is_click_on_object(item, scene_pos):
                        self._show_object_menu(event.pos(), object_id, scene_pos)
                        return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle mouse move events."""
        # Always emit mouse position for status bar
        scene_pos = self.mapToScene(event.pos())
        self.mouse_moved.emit(scene_pos.x(), scene_pos.y())

        if self.drawing_guardrail and event.buttons() & Qt.MouseButton.LeftButton:
            # Dragging to create guardrail - add points continuously
            if not self.guardrail_points or \
               ((scene_pos.x() - self.guardrail_points[-1][0])**2 +
                (scene_pos.y() - self.guardrail_points[-1][1])**2) > 100:  # Min 10px spacing
                self.guardrail_points.append((scene_pos.x(), scene_pos.y()))
        elif self.dragging_guardrail_point and self.drag_object_id:
            # Dragging a guardrail point
            item = self.object_items[self.drag_object_id]
            obj = item.obj
            if self.drag_point_index >= 0 and self.drag_point_index < len(obj.points):
                # Update the point position
                obj.points[self.drag_point_index] = (scene_pos.x(), scene_pos.y())
                # Refresh graphics
                item.update_graphics()
        elif self.dragging_junction and self.drag_junction_id:
            # Update junction position directly through the junction item
            item = self.junction_items[self.drag_junction_id]
            item.junction.center_point = (scene_pos.x(), scene_pos.y())
            item.update_graphics()
        elif self.dragging_point and self.drag_polyline_id:
            item = self.polyline_items[self.drag_polyline_id]
            item.polyline.update_point(self.drag_point_index, scene_pos.x(), scene_pos.y())
            item.update_graphics()
        elif self.dragging_connecting_road_point and self.drag_connecting_road_id:
            # Dragging a connecting road point
            item = self.connecting_road_centerline_items[self.drag_connecting_road_id]
            # Find the connecting road
            connecting_road = item.connecting_road
            if self.drag_point_index >= 0 and self.drag_point_index < len(connecting_road.path):
                # Update the point position
                connecting_road.path[self.drag_point_index] = (scene_pos.x(), scene_pos.y())
                # Refresh centerline graphics
                item.update_graphics()
                # Refresh lane graphics
                if self.drag_connecting_road_id in self.connecting_road_lanes_items:
                    self.connecting_road_lanes_items[self.drag_connecting_road_id].update_graphics()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        """Handle mouse release events."""
        if self.drawing_guardrail and event.button() == Qt.MouseButton.LeftButton:
            # Finish guardrail drawing
            if len(self.guardrail_points) >= 2:
                # Create guardrail object with the points
                obj = RoadObject(
                    position=self.guardrail_points[0],
                    object_type=ObjectType.GUARDRAIL
                )
                obj.points = self.guardrail_points.copy()
                # Calculate validity length
                total_length = 0.0
                for i in range(len(obj.points) - 1):
                    x1, y1 = obj.points[i]
                    x2, y2 = obj.points[i + 1]
                    total_length += ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
                obj.validity_length = total_length
                self.object_added.emit(obj)

            # Reset guardrail drawing state
            self.drawing_guardrail = False
            self.guardrail_points.clear()
        elif self.dragging_guardrail_point:
            self.dragging_guardrail_point = False
            if self.drag_object_id:
                # Update validity length after dragging
                item = self.object_items[self.drag_object_id]
                obj = item.obj
                if obj.points and len(obj.points) >= 2:
                    total_length = 0.0
                    for i in range(len(obj.points) - 1):
                        x1, y1 = obj.points[i]
                        x2, y2 = obj.points[i + 1]
                        total_length += ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
                    obj.validity_length = total_length
                # Emit modification signal
                self.object_modified.emit(self.drag_object_id)
            self.drag_object_id = None
            self.drag_point_index = -1
        elif self.dragging_junction:
            self.dragging_junction = False
            if self.drag_junction_id:
                self.junction_modified.emit(self.drag_junction_id)
            self.drag_junction_id = None
        elif self.dragging_point:
            self.dragging_point = False
            if self.drag_polyline_id:
                item = self.polyline_items[self.drag_polyline_id]
                polyline = item.polyline

                # If this is a centerline, update section boundaries after dragging
                if polyline.line_type == LineType.CENTERLINE and self.project:
                    for road in self.project.roads:
                        if road.centerline_id == self.drag_polyline_id:
                            road.update_section_boundaries(polyline.points)
                            # Refresh lane graphics
                            if road.id in self.road_lanes_items:
                                self.road_lanes_items[road.id].update_graphics()
                            break

                item.set_selected_point(-1)
                self.polyline_modified.emit(self.drag_polyline_id)
                # Update s-offset labels after point drag
                if self.soffsets_visible:
                    self._update_soffset_labels(self.drag_polyline_id)
            self.drag_polyline_id = None
            self.drag_point_index = -1
        elif self.dragging_connecting_road_point:
            self.dragging_connecting_road_point = False
            if self.drag_connecting_road_id:
                item = self.connecting_road_centerline_items[self.drag_connecting_road_id]
                item.selected_point_index = -1
                item.update_graphics()
                # TODO: Emit connecting_road_modified signal if needed
            self.drag_connecting_road_id = None
            self.drag_point_index = -1
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """Handle double-click to finish polyline, edit polyline, or edit junction."""
        if self.drawing_mode and event.button() == Qt.MouseButton.LeftButton:
            self.finish_current_polyline()
        elif event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.pos())

            # Check if double-clicking on a junction to edit
            for junction_id, item in self.junction_items.items():
                if item.is_at_position(scene_pos):
                    self.junction_edit_requested.emit(junction_id)
                    return

            # Check if double-clicking on an object to edit
            for object_id, item in self.object_items.items():
                if self._is_click_on_object(item, scene_pos):
                    self.object_edit_requested.emit(object_id)
                    return

            # Check if double-clicking on a polyline to edit
            for polyline_id, item in self.polyline_items.items():
                if item.is_near_line(scene_pos, tolerance=15):
                    self.polyline_edit_requested.emit(polyline_id)
                    return

            super().mouseDoubleClickEvent(event)
        else:
            super().mouseDoubleClickEvent(event)

    def leaveEvent(self, event):
        """Handle mouse leaving the view."""
        # Emit negative coordinates to signal mouse left the view
        self.mouse_moved.emit(-1, -1)
        super().leaveEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        """Handle key press events."""
        if self.drawing_mode:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                # Finish polyline and start a new one
                self.finish_current_polyline()
            elif event.key() == Qt.Key.Key_Escape:
                # Cancel current polyline
                if self.current_polyline_item:
                    self.current_polyline_item.remove()
                self.current_polyline = None
                self.current_polyline_item = None
                self.drawing_mode = False
                self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        elif self.measure_mode:
            if event.key() == Qt.Key.Key_Escape:
                # Exit measure mode - will be handled by MainWindow
                # Just clear any pending measurement points
                if len(self.measure_points) == 1:
                    # Remove the first dot if user pressed Escape after first click
                    self._clear_measurements()
        else:
            if event.key() == Qt.Key.Key_Delete:
                # Delete selected polyline
                self.delete_selected()
            else:
                super().keyPressEvent(event)

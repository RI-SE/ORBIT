"""
Image view widget for ORBIT.

Provides interactive image display with zoom, pan, and polyline drawing/editing.
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QImage, QKeyEvent, QMouseEvent, QPainter, QPen, QPixmap, QWheelEvent
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QMenu,
    QMessageBox,
)

from orbit.gui.graphics import (
    ConnectingRoadGraphicsItem,
    ConnectingRoadLanesGraphicsItem,
    InteractiveLanePolygon,
    JunctionMarkerItem,
    PolylineGraphicsItem,
    RoadLanesGraphicsItem,
)
from orbit.models import Junction, LineType, ObjectType, Polyline, Project, Road, RoadObject, Signal
from orbit.utils.coordinate_transform import TransformAdjustment

from .graphics.object_graphics_item import ObjectGraphicsItem
from .graphics.parking_item import ParkingGraphicsItem
from .graphics.signal_graphics_item import SignalGraphicsItem
from .utils.message_helpers import ask_yes_no, show_warning


class ImageView(QGraphicsView):
    """Interactive image view with polyline drawing and editing."""

    # Signals
    polyline_added = pyqtSignal(object)  # Emits Polyline
    polyline_modified = pyqtSignal(str)  # Emits polyline ID
    # For undo: polyline_id, old_points, new_points, old_geo, new_geo
    polyline_modified_for_undo = pyqtSignal(
        str, list, list, object, object
    )
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
    parking_placement_requested = pyqtSignal(float, float, object, object)  # Emits x, y, ParkingType, ParkingAccess
    parking_polygon_completed = pyqtSignal(list, object, object)  # Emits points list, ParkingType, ParkingAccess
    object_polygon_completed = pyqtSignal(list, object)  # Emits points list, ObjectType
    section_split_requested = pyqtSignal(str, str, int)  # Emits road_id, polyline_id, point_index
    road_split_requested = pyqtSignal(str, str, int)  # Emits road_id, polyline_id, point_index for splitting road
    section_modified = pyqtSignal(str)  # Emits road ID
    lane_segment_clicked = pyqtSignal(str, int, int)  # Emits road_id, section_number, lane_id
    connecting_road_modified = pyqtSignal(str)  # Emits connecting road ID
    connecting_road_lane_clicked = pyqtSignal(str, int)  # Emits connecting_road_id, lane_id
    lane_edit_requested = pyqtSignal(str, int, int)  # Emits road_id, section_number, lane_id (for double-click)
    connecting_road_lane_edit_requested = pyqtSignal(str, int)  # Emits connecting_road_id, lane_id (for double-click)
    point_picked = pyqtSignal(float, float)  # Emits x, y coordinates
    mouse_moved = pyqtSignal(float, float)  # Emits x, y mouse position in scene coordinates
    adjustment_changed = pyqtSignal(object)  # Emits TransformAdjustment when user adjusts alignment
    autofit_pairs_changed = pyqtSignal(int)  # Emits pair count when autofit pairs change
    area_delete_requested = pyqtSignal(dict)  # Emits dict of item IDs found in area selection
    # dragged_road_id, target_road_id, dragged_contact, target_contact
    road_link_requested = pyqtSignal(str, str, str, str)
    road_unlink_requested = pyqtSignal(str, str)  # road_id, linked_road_id (for disconnect)

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

        # Parking spaces
        self.parking_items: Dict[str, ParkingGraphicsItem] = {}
        self.selected_parking_id: Optional[str] = None

        # Control points (for georeferencing visualization)
        self.control_point_items: List = []

        # Road lanes (visual representation of lanes)
        self.road_lanes_items: Dict[str, RoadLanesGraphicsItem] = {}
        self.selected_lane_key: Optional[Tuple[str, int, int]] = None  # (road_id, section_number, lane_id)
        self.selected_road_id: Optional[str] = None  # Road whose lanes are all highlighted
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
        self.parking_mode = False
        self.parking_polygon_mode = False  # True for polygon drawing, False for point placement
        self.parking_type_to_place = None  # ParkingType to place
        self.parking_access_to_place = None  # ParkingAccess to place
        self.parking_polygon_points: List[Tuple[float, float]] = []  # Points for current polygon
        self.parking_polygon_preview: Optional[QGraphicsPathItem] = None  # Preview item
        self.adjustment_mode = False  # Transform adjustment mode for aligning imported data
        self.current_adjustment: Optional[TransformAdjustment] = None  # Current adjustment values
        self.autofit_mode = False  # Point-pair picking for auto-fit
        self.autofit_pairs: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
        self._autofit_pending_source: Optional[Tuple[float, float]] = None
        self._autofit_graphics: List = []  # Graphics items for autofit arrows
        self.object_type_to_place: Optional[ObjectType] = None  # Type of object to place
        self.object_polygon_mode = False  # True for polygon drawing (land use objects)
        self.object_polygon_points: List[Tuple[float, float]] = []  # Points for current object polygon
        self.object_polygon_preview: Optional[QGraphicsPathItem] = None  # Preview item
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
        self._drag_start_obj_points: Optional[list] = None
        self._drag_start_obj_geo_points: Optional[list] = None
        # drag_point_index is shared with polyline and connecting road dragging
        self.dragging_connecting_road_point = False
        self.drag_connecting_road_id: Optional[str] = None
        # drag_point_index is also used for connecting road point dragging

        # Endpoint snap state (for road connection during drag)
        self._dragging_endpoint = False  # True if drag_point_index is 0 or last
        self._snap_target: Optional[tuple] = None  # (road_id, polyline_id, point_index, point_coords)
        self._snap_indicator: Optional[QGraphicsEllipseItem] = None  # Visual ring on target

        # Area selection state (Alt+drag rubber-band)
        self._area_selecting = False
        self._area_select_start: Optional[QPointF] = None
        self._area_select_rect_item: Optional[QGraphicsRectItem] = None

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

    def _set_padded_scene_rect(self, image_width: int, image_height: int):
        """Set scene rect to image bounds plus a 50% margin on each side.

        Without an explicit scene rect Qt restricts panning to the bounding
        box of scene items (i.e. the image).  The extra margin lets users pan
        and place road endpoints outside the image area.
        """
        pad_x = image_width * 0.5
        pad_y = image_height * 0.5
        self.scene.setSceneRect(-pad_x, -pad_y,
                                image_width + 2 * pad_x,
                                image_height + 2 * pad_y)

    def _expand_scene_rect_to_items(self):
        """Expand the scene rect to encompass all scene items with padding.

        Called after loading a project so that imported map data extending
        beyond the image (e.g. large-radius OSM import) is fully pannable.
        """
        items_rect = self.scene.itemsBoundingRect()
        if items_rect.isNull():
            return
        current = self.scene.sceneRect()
        united = current.united(items_rect)
        # Add 20% padding around the united rect
        pad_x = united.width() * 0.2
        pad_y = united.height() * 0.2
        united.adjust(-pad_x, -pad_y, pad_x, pad_y)
        self.scene.setSceneRect(united)

    def set_synthetic_canvas(self, width: int, height: int, color=None):
        """Create a grey canvas as a synthetic image substitute.

        Used when importing data (OpenDrive, OSM) without a real image.
        Downstream code checks image_item, so we create a real QPixmap.

        Args:
            width: Canvas width in pixels
            height: Canvas height in pixels
            color: Fill color (default: light grey)
        """
        if color is None:
            color = QColor(200, 200, 200)

        pixmap = QPixmap(width, height)
        pixmap.fill(color)

        # Clear scene and add synthetic pixmap
        self.scene.clear()
        self.polyline_items.clear()
        self.image_item = self.scene.addPixmap(pixmap)
        self.image_item.setZValue(0)
        self.image_np = None
        self.image_path = None

        self._set_padded_scene_rect(width, height)
        self.fit_to_window()

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

        self._set_padded_scene_rect(width, height)
        # Fit to view
        self.fit_to_window()

    def swap_background(self, image_rgb: np.ndarray):
        """Replace the background image without clearing scene items.

        All polyline/junction/signal items remain in the scene; only the
        background pixmap is swapped.

        Args:
            image_rgb: H×W×3 RGB numpy array for the new background.
        """
        height, width = image_rgb.shape[:2]
        bytes_per_line = 3 * width
        q_image = QImage(
            image_rgb.data,
            width,
            height,
            bytes_per_line,
            QImage.Format.Format_RGB888,
        )
        pixmap = QPixmap.fromImage(q_image)

        if self.image_item is not None:
            self.scene.removeItem(self.image_item)

        self.image_item = self.scene.addPixmap(pixmap)
        self.image_item.setZValue(0)
        self.image_np = image_rgb

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
        self.parking_items.clear()
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

        # Add parking spaces from project
        for parking in project.parking_spaces:
            self.add_parking_graphics(parking, scale_factor)

        # Add control points from project
        for cp in project.control_points:
            self.add_control_point_graphics(cp)

        # Add road lanes for all roads with centerlines
        for road in project.roads:
            if road.centerline_id:
                self.add_road_lanes_graphics(road, scale_factors)

        # Add connecting roads from all junctions
        for junction in project.junctions:
            for cr_id in junction.connecting_road_ids:
                connecting_road = project.get_road(cr_id)
                if connecting_road:
                    self.add_connecting_road_graphics(connecting_road, scale_factors)

        # Expand scene rect so items outside the image are pannable
        self._expand_scene_rect_to_items()

    def add_polyline_graphics(self, polyline: Polyline):
        """Add a polyline to the graphics scene."""
        item = PolylineGraphicsItem(polyline, self.scene)
        self.polyline_items[polyline.id] = item
        # Update s-offset labels if visible and this is a centerline
        if self.soffsets_visible:
            self._update_soffset_labels(polyline.id)

    def remove_polyline_graphics(self, polyline_id: str):
        """Remove a polyline from the graphics scene."""
        if polyline_id in self.polyline_items:
            self.polyline_items[polyline_id].remove()
            del self.polyline_items[polyline_id]

        # Remove s-offset labels if they exist
        if polyline_id in self.soffset_labels:
            for text_item, bg_item in self.soffset_labels[polyline_id]:
                if text_item.scene() == self.scene:
                    self.scene.removeItem(text_item)
                if bg_item.scene() == self.scene:
                    self.scene.removeItem(bg_item)
            del self.soffset_labels[polyline_id]

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
            # Find connecting road graphics that are no longer in any junction
            all_cr_ids_in_scene = set(self.connecting_road_centerline_items.keys()) | set(
                self.connecting_road_lanes_items.keys())
            for conn_road_id in list(all_cr_ids_in_scene):
                found_in_any_junction = False
                for j in self.project.junctions:
                    if conn_road_id in j.connecting_road_ids:
                        found_in_any_junction = True
                        break
                if not found_in_any_junction:
                    self.remove_connecting_road_graphics(conn_road_id)

            # Fully recreate connecting road graphics for this junction
            # to ensure path changes from lane alignment are reflected
            scale_factors = None
            for cr_id in junction.connecting_road_ids:
                # Preserve scale_factors from existing item if available
                if scale_factors is None and cr_id in self.connecting_road_lanes_items:
                    scale_factors = self.connecting_road_lanes_items[cr_id].scale_factors

            for cr_id in junction.connecting_road_ids:
                conn_road = self.project.get_road(cr_id)
                if conn_road:
                    self.add_connecting_road_graphics(conn_road, scale_factors)

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
            shape_type = obj.type.get_shape_type()
            if shape_type in ("circle", "rectangle"):
                item.setPos(obj.position[0], obj.position[1])
            # For polyline objects (guardrails), redraw the path
            item.update_graphics()

    def add_parking_graphics(self, parking, scale_factor: float = 0.0):
        """Add a parking space to the graphics scene."""
        item = ParkingGraphicsItem(parking, scale_factor)
        item.parking_changed = lambda p: self._on_parking_changed(p)
        self.parking_items[parking.id] = item
        self.scene.addItem(item)

    def _on_parking_changed(self, parking):
        """Handle parking space position change."""
        # Mark project as modified (MainWindow will handle this via signal)
        pass

    def remove_parking_graphics(self, parking_id: str):
        """Remove a parking space from the scene."""
        if parking_id in self.parking_items:
            item = self.parking_items[parking_id]
            self.safe_remove_item(item)
            del self.parking_items[parking_id]

    def refresh_parking_graphics(self, parking_id: str):
        """Refresh parking graphics after modification."""
        if parking_id in self.parking_items:
            item = self.parking_items[parking_id]
            parking = item.parking
            # Update position for point parking (non-polygon)
            if not parking.is_polygon():
                item.setPos(parking.position[0], parking.position[1])
            item.update_graphics()

    def _add_parking_polygon_point(self, x: float, y: float):
        """Add a point to the current parking polygon being drawn."""
        from PyQt6.QtGui import QPainterPath

        self.parking_polygon_points.append((x, y))

        # Update or create preview
        if self.parking_polygon_preview is None:
            self.parking_polygon_preview = QGraphicsPathItem()
            self.parking_polygon_preview.setPen(QPen(QColor(100, 100, 255, 200), 2, Qt.PenStyle.DashLine))
            self.parking_polygon_preview.setBrush(QBrush(QColor(100, 100, 255, 80)))
            self.scene.addItem(self.parking_polygon_preview)

        # Draw polygon preview
        path = QPainterPath()
        if self.parking_polygon_points:
            path.moveTo(self.parking_polygon_points[0][0], self.parking_polygon_points[0][1])
            for px, py in self.parking_polygon_points[1:]:
                path.lineTo(px, py)
            # Close if more than 2 points
            if len(self.parking_polygon_points) > 2:
                path.closeSubpath()

        self.parking_polygon_preview.setPath(path)

    def _finish_parking_polygon(self):
        """Finish drawing the parking polygon and create the parking space."""
        if len(self.parking_polygon_points) < 3:
            # Need at least 3 points for a polygon
            self._cancel_parking_polygon()
            return

        # Emit the polygon completion signal
        self.parking_polygon_completed.emit(
            list(self.parking_polygon_points),
            self.parking_type_to_place,
            self.parking_access_to_place
        )

        # Clean up preview
        self._clear_parking_polygon_preview()

        # Reset points but stay in polygon mode for next polygon
        self.parking_polygon_points.clear()

    def _cancel_parking_polygon(self):
        """Cancel the current parking polygon drawing."""
        self.parking_polygon_points.clear()
        self._clear_parking_polygon_preview()

    def _clear_parking_polygon_preview(self):
        """Remove the polygon preview from the scene."""
        if self.parking_polygon_preview:
            self.safe_remove_item(self.parking_polygon_preview)
            self.parking_polygon_preview = None

    def _add_object_polygon_point(self, x: float, y: float):
        """Add a point to the current object polygon being drawn."""
        from PyQt6.QtGui import QPainterPath

        from orbit.gui.graphics.object_graphics import get_object_color

        self.object_polygon_points.append((x, y))

        # Update or create preview with the object type's color
        if self.object_polygon_preview is None:
            self.object_polygon_preview = QGraphicsPathItem()
            color = get_object_color(self.object_type_to_place)
            self.object_polygon_preview.setPen(QPen(color.darker(120), 2, Qt.PenStyle.DashLine))
            fill = QColor(color)
            fill.setAlpha(80)
            self.object_polygon_preview.setBrush(QBrush(fill))
            self.scene.addItem(self.object_polygon_preview)

        # Draw polygon preview
        path = QPainterPath()
        if self.object_polygon_points:
            path.moveTo(self.object_polygon_points[0][0], self.object_polygon_points[0][1])
            for px, py in self.object_polygon_points[1:]:
                path.lineTo(px, py)
            if len(self.object_polygon_points) > 2:
                path.closeSubpath()

        self.object_polygon_preview.setPath(path)

    def _finish_object_polygon(self):
        """Finish drawing the object polygon and emit completion signal."""
        if len(self.object_polygon_points) < 3:
            self._cancel_object_polygon()
            return

        self.object_polygon_completed.emit(
            list(self.object_polygon_points),
            self.object_type_to_place
        )

        self._clear_object_polygon_preview()
        self.object_polygon_points.clear()

    def _cancel_object_polygon(self):
        """Cancel the current object polygon drawing."""
        self.object_polygon_points.clear()
        self._clear_object_polygon_preview()

    def _clear_object_polygon_preview(self):
        """Remove the object polygon preview from the scene."""
        if self.object_polygon_preview:
            self.safe_remove_item(self.object_polygon_preview)
            self.object_polygon_preview = None

    def _get_geo_transformer(self):
        """Get the cached geo transformer from the parent MainWindow, if available."""
        parent = self.parent()
        return getattr(parent, '_cached_transformer', None) if parent else None

    @staticmethod
    def _interpolate_geo_for_insert(polyline, insert_index: int,
                                    px: float, py: float) -> tuple[float, float] | None:
        """Interpolate a geo_point for a newly inserted point.

        Called AFTER the pixel point has been inserted into polyline.points
        but BEFORE the geo_point is inserted into polyline.geo_points.

        Uses the fractional pixel position along the segment to linearly
        interpolate between neighbor geo_points. Much more accurate than
        pixel_to_geo for points far from control points.

        Returns (lon, lat) or None if interpolation is not possible.
        """
        gp = polyline.geo_points  # Still has original count (one fewer than pts)
        if gp is None or len(gp) < 2:
            return None

        pts = polyline.points  # Already has the new point at insert_index

        # Neighbors in geo space (pre-insert indices):
        #   prev = gp[insert_index - 1]  (same index in both arrays)
        #   next = gp[insert_index]       (was at insert_index before pixel insertion)
        # Neighbors in pixel space (post-insert indices):
        #   prev = pts[insert_index - 1]
        #   next = pts[insert_index + 1]  (shifted by insertion)
        if insert_index < 1 or insert_index >= len(gp) + 1:
            return None

        prev_geo_idx = insert_index - 1
        next_geo_idx = insert_index  # in the pre-insert geo array
        if next_geo_idx >= len(gp):
            return None

        prev_px, prev_py = pts[insert_index - 1]
        next_px, next_py = pts[insert_index + 1]

        seg_len_sq = (next_px - prev_px) ** 2 + (next_py - prev_py) ** 2
        if seg_len_sq < 1e-6:
            return tuple(gp[prev_geo_idx])

        # Project new point onto the segment to get fraction t
        t = ((px - prev_px) * (next_px - prev_px) +
             (py - prev_py) * (next_py - prev_py)) / seg_len_sq
        t = max(0.0, min(1.0, t))

        lon = gp[prev_geo_idx][0] * (1 - t) + gp[next_geo_idx][0] * t
        lat = gp[prev_geo_idx][1] * (1 - t) + gp[next_geo_idx][1] * t
        return (lon, lat)

    @staticmethod
    def _compute_dragged_geo_point(polyline, drag_index: int,
                                   old_px: float, old_py: float,
                                   old_geo: tuple[float, float],
                                   transformer=None) -> tuple[float, float] | None:
        """Compute an updated geo_point for a dragged point using local context.

        Uses the polyline's own pixel/geo pairs to derive a local affine
        Jacobian, avoiding the global control-point transform which
        extrapolates badly for points far from control points.

        Prefers a full 2x2 Jacobian when reference points have enough
        angular diversity (curved roads). Falls back to a similarity model
        for straight roads, using the global transform only to determine
        mapping orientation (conformal vs anti-conformal).

        The pixel→geo mapping may be orientation-reversing (e.g. when the
        image y-axis is flipped relative to geographic north). The full
        Jacobian handles this automatically; the similarity fallback checks
        the global transform's Jacobian determinant sign.

        Returns (lon, lat) or None if local computation is not possible.
        """
        import math

        pts = polyline.points
        gp = polyline.geo_points
        if gp is None or len(gp) < 2:
            return None
        if len(gp) != len(pts):
            return None

        new_px, new_py = pts[drag_index]
        delta_px = new_px - old_px
        delta_py = new_py - old_py

        # Build reference pairs: all undragged points + old position of
        # the dragged point (known correct pixel→geo mapping).
        ref_pairs = []
        for i in range(len(pts)):
            if i != drag_index:
                ref_pairs.append((pts[i][0], pts[i][1], gp[i][0], gp[i][1]))
        # Add old dragged point — guarantees >=2 pairs for any polyline
        # with >=2 points
        ref_pairs.append((old_px, old_py, old_geo[0], old_geo[1]))

        if len(ref_pairs) < 2:
            return None

        # --- Step 1: Find widest-separated pair ---
        best_span_sq = 0.0
        i0, i1 = 0, len(ref_pairs) - 1
        # Check endpoints + old dragged point (usually widest for polylines)
        cands = list(set([0, len(ref_pairs) - 1] +
                         ([len(ref_pairs) - 2] if len(ref_pairs) > 2 else [])))
        for a in range(len(ref_pairs)):
            for b in cands:
                if a == b:
                    continue
                sq = (ref_pairs[b][0] - ref_pairs[a][0]) ** 2 + \
                     (ref_pairs[b][1] - ref_pairs[a][1]) ** 2
                if sq > best_span_sq:
                    best_span_sq = sq
                    i0, i1 = (a, b) if a < b else (b, a)

        if best_span_sq < 1e-6:
            return None

        dpx_a = ref_pairs[i1][0] - ref_pairs[i0][0]
        dpy_a = ref_pairs[i1][1] - ref_pairs[i0][1]
        dlon_a = ref_pairs[i1][2] - ref_pairs[i0][2]
        dlat_a = ref_pairs[i1][3] - ref_pairs[i0][3]
        span_a = math.sqrt(best_span_sq)

        geo_span = math.sqrt(dlon_a ** 2 + dlat_a ** 2)
        if geo_span < 1e-12:
            return None

        # --- Step 2: Try full 2x2 Jacobian (needs a non-collinear point) ---
        # Find the reference point farthest from the line i0→i1.
        best_perp = 0.0
        i2 = -1
        for k in range(len(ref_pairs)):
            if k == i0 or k == i1:
                continue
            dpx_k = ref_pairs[k][0] - ref_pairs[i0][0]
            dpy_k = ref_pairs[k][1] - ref_pairs[i0][1]
            perp = abs(dpx_a * dpy_k - dpy_a * dpx_k) / span_a
            if perp > best_perp:
                best_perp = perp
                i2 = k

        if i2 >= 0 and best_perp > 1.0:
            # Enough angular diversity — solve full 2x2 Jacobian.
            # J maps pixel deltas to geo deltas:
            #   J @ [dpx, dpy]^T = [dlon, dlat]^T
            # Using two direction vectors from ref point i0:
            dpx_c = ref_pairs[i2][0] - ref_pairs[i0][0]
            dpy_c = ref_pairs[i2][1] - ref_pairs[i0][1]
            dlon_c = ref_pairs[i2][2] - ref_pairs[i0][2]
            dlat_c = ref_pairs[i2][3] - ref_pairs[i0][3]

            det = dpx_a * dpy_c - dpy_a * dpx_c
            if abs(det) > 1e-6:
                J11 = (dlon_a * dpy_c - dlon_c * dpy_a) / det
                J12 = (dpx_a * dlon_c - dpx_c * dlon_a) / det
                J21 = (dlat_a * dpy_c - dlat_c * dpy_a) / det
                J22 = (dpx_a * dlat_c - dpx_c * dlat_a) / det

                delta_lon = J11 * delta_px + J12 * delta_py
                delta_lat = J21 * delta_px + J22 * delta_py
                return (old_geo[0] + delta_lon, old_geo[1] + delta_lat)

        # --- Step 3: Collinear fallback — similarity model ---
        # With collinear reference points, the perpendicular direction is
        # ambiguous. Check the global transform's Jacobian determinant to
        # distinguish conformal (orientation-preserving, det>0) from
        # anti-conformal (orientation-reversing, det<0) mapping.
        # This is a safe use of the global transform — only the sign of the
        # determinant is used, not absolute position.
        orientation_reversing = False
        if transformer:
            try:
                eps = 1.0
                lon0, lat0 = transformer.pixel_to_geo(old_px, old_py)
                lon_dx, lat_dx = transformer.pixel_to_geo(old_px + eps, old_py)
                lon_dy, lat_dy = transformer.pixel_to_geo(old_px, old_py + eps)
                det_global = ((lon_dx - lon0) * (lat_dy - lat0) -
                              (lon_dy - lon0) * (lat_dx - lat0))
                orientation_reversing = (det_global < 0)
            except Exception:
                pass

        px_span_sq = best_span_sq
        if orientation_reversing:
            # Anti-conformal: J = s * [[cos θ, sin θ], [sin θ, -cos θ]]
            a = (dpx_a * dlon_a - dpy_a * dlat_a) / px_span_sq
            b = (dpy_a * dlon_a + dpx_a * dlat_a) / px_span_sq
            delta_lon = a * delta_px + b * delta_py
            delta_lat = b * delta_px - a * delta_py
        else:
            # Conformal: J = s * [[cos θ, -sin θ], [sin θ, cos θ]]
            a = (dpx_a * dlon_a + dpy_a * dlat_a) / px_span_sq
            b = (-dpy_a * dlon_a + dpx_a * dlat_a) / px_span_sq
            delta_lon = a * delta_px - b * delta_py
            delta_lat = b * delta_px + a * delta_py

        return (old_geo[0] + delta_lon, old_geo[1] + delta_lat)

    def update_all_from_geo_coords(self, transformer):
        """
        Update all geometry items from their geo coordinates using the transformer.

        This method is called when the transformer changes (e.g., during adjustment)
        to recompute pixel positions from stored geographic coordinates.

        Args:
            transformer: CoordinateTransformer for geo→pixel conversion
        """
        if not transformer or not self.project:
            return

        # Update polylines that have geo_points
        for polyline in self.project.polylines:
            if polyline.has_geo_coords():
                polyline.update_pixel_points_from_geo(transformer)
                # Refresh graphics if it exists
                if polyline.id in self.polyline_items:
                    self.polyline_items[polyline.id].update_graphics()

        # Update signals that have geo_position
        for signal in self.project.signals:
            if signal.has_geo_coords():
                signal.update_pixel_position_from_geo(transformer)
                if signal.id in self.signal_items:
                    self.signal_items[signal.id].update_graphics()

        # Update objects that have geo coords
        for obj in self.project.objects:
            if obj.has_geo_coords():
                obj.update_pixel_coords_from_geo(transformer)
                if obj.id in self.object_items:
                    self.object_items[obj.id].update_graphics()

        # Update junctions that have geo coords
        for junction in self.project.junctions:
            if junction.has_geo_coords():
                junction.update_pixel_coords_from_geo(transformer)
                if junction.id in self.junction_items:
                    self.junction_items[junction.id].update_graphics()

            # Update connecting roads within junctions
            for cr_id in junction.connecting_road_ids:
                connecting_road = self.project.get_road(cr_id) if self.project else None
                if connecting_road and connecting_road.has_geo_coords():
                    connecting_road.update_pixel_path_from_geo(transformer)
                    # Update both centerline and lanes graphics
                    if connecting_road.id in self.connecting_road_centerline_items:
                        self.connecting_road_centerline_items[connecting_road.id].update_graphics()
                    if connecting_road.id in self.connecting_road_lanes_items:
                        self.connecting_road_lanes_items[connecting_road.id].update_graphics()

        # Update road lanes graphics (they use polyline positions)
        for road in self.project.roads:
            if road.id in self.road_lanes_items:
                self.road_lanes_items[road.id].update_graphics()

        # Update parking spaces that have geo coords
        for parking in self.project.parking_spaces:
            if parking.has_geo_coords():
                parking.update_pixel_coords_from_geo(transformer)
                if parking.id in self.parking_items:
                    self.refresh_parking_graphics(parking.id)

        # Force scene update to ensure all changes are rendered
        self.scene.update()
        self.viewport().update()

    def update_object_scale_factors(self, scale_factor: float):
        """Update scale factors for all objects when georeferencing changes."""
        for item in self.object_items.values():
            item.update_scale_factor(scale_factor)

    def add_control_point_graphics(self, control_point):
        """Add a control point marker to the graphics scene as a crosshair."""

        x, y = control_point.pixel_x, control_point.pixel_y

        # Crosshair parameters
        arm_length = 10  # Length of each arm from center
        gap = 3  # Gap radius at center (so target pixel is visible)

        # Main crosshair pen (bright blue)
        pen = QPen(QColor(0, 100, 255), 2)

        # Horizontal arms (left and right of center gap)
        left_arm = self.scene.addLine(x - arm_length, y, x - gap, y, pen)
        right_arm = self.scene.addLine(x + gap, y, x + arm_length, y, pen)

        # Vertical arms (top and bottom of center gap)
        top_arm = self.scene.addLine(x, y - arm_length, x, y - gap, pen)
        bottom_arm = self.scene.addLine(x, y + gap, x, y + arm_length, pen)

        # Tiny center dot for exact position reference
        dot_pen = QPen(QColor(0, 100, 255), 1)
        dot_brush = QBrush(QColor(0, 100, 255))
        center_dot = self.scene.addEllipse(x - 0.5, y - 0.5, 1, 1, dot_pen, dot_brush)

        # Set z-values and add to tracking list
        for item in [left_arm, right_arm, top_arm, bottom_arm, center_dot]:
            item.setZValue(10)
            self.control_point_items.append(item)

        # Add label with CP name
        if control_point.name:
            from PyQt6.QtGui import QFont
            from PyQt6.QtWidgets import QGraphicsTextItem
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
        lanes_item = RoadLanesGraphicsItem(road, centerline, self.scene, scale_factors, self.verbose, self.project)
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
            connecting_road: Road object (connecting road with inline_path)
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
        from PyQt6.QtGui import QFont
        from PyQt6.QtWidgets import QGraphicsTextItem

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
            self.current_polyline = Polyline(id=self.project.next_id('polyline') if self.project else "")
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
            self.current_polyline = Polyline(id=self.project.next_id('polyline') if self.project else "")
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
        # Enable polygon drawing for polygon-shaped objects (land use, parking types)
        self.object_polygon_mode = (
            enabled and object_type is not None
            and object_type.get_shape_type() == "polygon"
        )
        if enabled:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
        else:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            # Clean up any partial guardrail
            if self.drawing_guardrail:
                self.drawing_guardrail = False
                self.guardrail_points.clear()
            # Clean up any partial object polygon
            self._cancel_object_polygon()

    def set_parking_mode(self, enabled: bool, parking_type=None, access_type=None, polygon_mode: bool = False):
        """Enable or disable parking placement mode."""
        self.parking_mode = enabled
        self.parking_polygon_mode = polygon_mode
        self.parking_type_to_place = parking_type
        self.parking_access_to_place = access_type
        if enabled:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
        else:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            # Clean up any partial polygon
            self._cancel_parking_polygon()

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

    def set_adjustment_mode(self, enabled: bool, pivot_x: float = 0.0, pivot_y: float = 0.0):
        """
        Enable or disable transform adjustment mode.

        When enabled, arrow keys and other shortcuts adjust the georeferencing
        transformation to align imported OSM data with the aerial image.

        Args:
            enabled: Whether to enable adjustment mode
            pivot_x, pivot_y: Pivot point for rotation/scale (defaults to image center)
        """
        self.adjustment_mode = enabled
        if enabled:
            # Initialize adjustment if not already set
            if self.current_adjustment is None:
                self.current_adjustment = TransformAdjustment()
            self.current_adjustment.pivot_x = pivot_x
            self.current_adjustment.pivot_y = pivot_y
            # Change cursor to indicate adjustment mode
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            # Keep ScrollHandDrag for panning — arrow keys are intercepted
            # in keyPressEvent before reaching QGraphicsView
        else:
            # Restore normal cursor
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def reset_adjustment(self):
        """Reset all adjustment values to identity."""
        if self.current_adjustment is not None:
            self.current_adjustment.reset()
            self.adjustment_changed.emit(self.current_adjustment)

    def get_adjustment(self) -> Optional[TransformAdjustment]:
        """Get current adjustment or None if not set."""
        return self.current_adjustment

    def _handle_adjustment_key(self, event: QKeyEvent) -> bool:
        """Handle keyboard input for adjustment mode."""
        if self.current_adjustment is None:
            self.current_adjustment = TransformAdjustment()

        key = event.key()
        mods = event.modifiers()

        # Ctrl = 5× for all keys (but not AltGr which is Ctrl+Alt on Linux)
        is_altgr = bool(
            mods & Qt.KeyboardModifier.ControlModifier
        ) and bool(mods & Qt.KeyboardModifier.AltModifier)
        if (mods & Qt.KeyboardModifier.ControlModifier) and not is_altgr:
            step_mult = 5.0
        else:
            step_mult = 1.0

        # Use event.text() for character keys (layout-agnostic)
        ch = event.text()
        handled = True

        # Translation: Arrow keys (1px normal, 5px with Ctrl)
        if key == Qt.Key.Key_Left:
            self.current_adjustment.translation_x -= step_mult
        elif key == Qt.Key.Key_Right:
            self.current_adjustment.translation_x += step_mult
        elif key == Qt.Key.Key_Up:
            self.current_adjustment.translation_y -= step_mult
        elif key == Qt.Key.Key_Down:
            self.current_adjustment.translation_y += step_mult

        # Rotation: [ ]  (0.1° per step)
        elif ch == '[':
            self.current_adjustment.rotation -= 0.1 * step_mult
        elif ch == ']':
            self.current_adjustment.rotation += 0.1 * step_mult

        # Uniform scale: + -  (0.5% per step)
        elif ch in ('+', '='):
            scale_factor = 1 + 0.005 * step_mult
            self.current_adjustment.scale_x *= scale_factor
            self.current_adjustment.scale_y *= scale_factor
        elif ch == '-':
            scale_factor = 1 + 0.005 * step_mult
            self.current_adjustment.scale_x /= scale_factor
            self.current_adjustment.scale_y /= scale_factor

        # Stretch X: < >  (0.5% per step)
        elif ch == '<':
            self.current_adjustment.scale_x /= (1 + 0.005 * step_mult)
        elif ch == '>':
            self.current_adjustment.scale_x *= (1 + 0.005 * step_mult)

        # Stretch Y: , .  (0.5% per step)
        elif ch == ',':
            self.current_adjustment.scale_y /= (1 + 0.005 * step_mult)
        elif ch == '.':
            self.current_adjustment.scale_y *= (1 + 0.005 * step_mult)

        # Shear X (perspective): ; :  (0.002 per step)
        elif ch == ';':
            self.current_adjustment.shear_x -= 0.002 * step_mult
        elif ch == ':':
            self.current_adjustment.shear_x += 0.002 * step_mult

        # Shear Y: { }  (0.002 per step)
        elif ch == '{':
            self.current_adjustment.shear_y -= 0.002 * step_mult
        elif ch == '}':
            self.current_adjustment.shear_y += 0.002 * step_mult

        # Reset: Escape
        elif key == Qt.Key.Key_Escape:
            self.current_adjustment.reset()

        else:
            handled = False

        if handled:
            self.adjustment_changed.emit(self.current_adjustment)

        return handled

    # ------ Auto-fit correspondence point picking ------

    def set_autofit_mode(self, enabled: bool):
        """Enable/disable autofit point-pair picking mode."""
        self.autofit_mode = enabled
        self._autofit_pending_source = None
        if enabled:
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif self.adjustment_mode:
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def clear_autofit_pairs(self):
        """Clear all collected point pairs and their graphics."""
        self.autofit_pairs.clear()
        self._autofit_pending_source = None
        for item in self._autofit_graphics:
            if item.scene():
                self.scene.removeItem(item)
        self._autofit_graphics.clear()
        self.autofit_pairs_changed.emit(0)

    def _handle_autofit_click(self, scene_pos):
        """Handle a click in autofit mode (alternating source/target)."""
        x, y = scene_pos.x(), scene_pos.y()

        if self._autofit_pending_source is None:
            # Odd click: source (where feature IS)
            self._autofit_pending_source = (x, y)
            self._draw_autofit_dot(x, y, QColor(220, 60, 60))  # Red
        else:
            # Even click: target (where it SHOULD BE)
            sx, sy = self._autofit_pending_source
            self.autofit_pairs.append(((sx, sy), (x, y)))
            self._autofit_pending_source = None
            self._draw_autofit_dot(x, y, QColor(60, 180, 60))  # Green
            self._draw_autofit_arrow(sx, sy, x, y)
            self.autofit_pairs_changed.emit(len(self.autofit_pairs))

    def _draw_autofit_dot(self, x, y, color):
        """Draw a small dot for an autofit point."""
        r = 4
        pen = QPen(color, 2)
        brush = QBrush(color)
        dot = self.scene.addEllipse(x - r, y - r, 2 * r, 2 * r, pen, brush)
        dot.setZValue(200)
        self._autofit_graphics.append(dot)

    def _draw_autofit_arrow(self, x1, y1, x2, y2):
        """Draw an arrow from source to target."""
        pen = QPen(QColor(255, 165, 0, 200), 2)  # Orange
        line = self.scene.addLine(x1, y1, x2, y2, pen)
        line.setZValue(199)
        self._autofit_graphics.append(line)

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
        # Get project from parent main window to ensure we have the current project state
        # This is more reliable than using self.project which may not be synced
        project = None
        parent_widget = self.parent()
        while parent_widget is not None:
            if hasattr(parent_widget, 'project'):
                project = parent_widget.project
                break
            parent_widget = parent_widget.parent() if hasattr(parent_widget, 'parent') else None

        # Fallback to self.project if we can't find parent's project
        if project is None:
            project = self.project

        if not project or not project.has_georeferencing():
            return ("No georef", QColor(255, 255, 255, 200))

        try:
            from orbit.utils import create_transformer
            from orbit.utils.uncertainty_estimator import UncertaintyEstimator

            # Create transformer
            transformer = create_transformer(project.control_points, project.transform_method, use_validation=True)

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
                                                     baseline_uncertainty=project.baseline_uncertainty_m)

                    # Load cached grid if available
                    if project.uncertainty_grid_cache:
                        import numpy as np
                        estimator._cached_grid = np.array(project.uncertainty_grid_cache)

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
        from PyQt6.QtGui import QFont
        from PyQt6.QtWidgets import QGraphicsTextItem
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
                from orbit.utils import create_transformer

                # Create transformer
                transformer = create_transformer(
                    self.project.control_points,
                    self.project.transform_method,
                    use_validation=True,
                )

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
        conn_road = self.project.get_road(connecting_road_id) if self.project else None
        if not conn_road or not conn_road.is_connecting_road:
            return -1  # Default to first right lane

        # Get available lanes on the connecting road
        right_lanes = list(range(-1, -(conn_road.cr_lane_count_right + 1), -1))  # [-1, -2, ...]
        left_lanes = list(range(1, conn_road.cr_lane_count_left + 1))  # [1, 2, ...]

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

    def export_layout_mask(self, output_path: str, method: str = "pixel",
                           geotiff: bool = False,
                           line_tolerance: float = 0.05,
                           arc_tolerance: float = 0.1,
                           preserve_geometry: bool = True) -> bool:
        """Export a layout mask and metadata JSON for lane segmentation.

        Args:
            output_path: Path for the mask image (PNG/TIFF)
            method: "pixel" (from rendered scene) or "opendrive" (from export pipeline)
            geotiff: If True and georeferencing available, write a world file
            line_tolerance: Curve fitting tolerance (opendrive method only)
            arc_tolerance: Arc fitting tolerance (opendrive method only)
            preserve_geometry: Preserve original geometry during fitting

        Returns:
            True on success, False on failure
        """
        from orbit.export.layout_mask_exporter import ExportMethod, LayoutMaskExporter
        from orbit.export.reference_line_sampler import LanePolygonData

        if not self.image_item:
            return False

        image_size = (
            int(self.image_item.pixmap().width()),
            int(self.image_item.pixmap().height()),
        )

        # Collect polygon data from rendered scene (for pixel method)
        lane_polygons = []
        if method == "pixel":
            # Regular road lanes
            for road_id, lanes_item in self.road_lanes_items.items():
                road = self.project.get_road(road_id) if self.project else None
                for poly_item in lanes_item.lane_items:
                    lane_type = "driving"
                    if road:
                        lane = road.get_lane(poly_item.lane_id, poly_item.section_number)
                        if lane:
                            lane_type = lane.lane_type.value
                    lane_polygons.append(LanePolygonData(
                        road_id=poly_item.road_id,
                        section_number=poly_item.section_number,
                        lane_id=poly_item.lane_id,
                        points=list(poly_item.points),
                        is_connecting_road=False,
                        lane_type=lane_type,
                    ))

            # Connecting road lanes
            for cr_id, cr_lanes_item in self.connecting_road_lanes_items.items():
                for poly_item in cr_lanes_item.lane_items:
                    lane_polygons.append(LanePolygonData(
                        road_id=poly_item.road_id,
                        section_number=poly_item.section_number,
                        lane_id=poly_item.lane_id,
                        points=list(poly_item.points),
                        is_connecting_road=True,
                        lane_type="driving",
                    ))

        # Create transformer if georeferencing available
        transformer = None
        if self.project and len(self.project.control_points) >= 3:
            from orbit.export import create_transformer
            transformer = create_transformer(
                self.project.control_points,
                self.project.transform_method,
            )

        export_method = ExportMethod.OPENDRIVE if method == "opendrive" else ExportMethod.PIXEL

        exporter = LayoutMaskExporter(
            image_size=image_size,
            project=self.project,
            find_connected_lanes=self.find_connected_lanes,
            get_connecting_road_lane_id=self._get_connecting_road_lane_id,
            transformer=transformer,
            method=export_method,
            line_tolerance=line_tolerance,
            arc_tolerance=arc_tolerance,
            preserve_geometry=preserve_geometry,
            lane_polygons=lane_polygons,
        )

        return exporter.export(output_path, geotiff=geotiff)

    def select_road(self, road_id: str):
        """Select and highlight all lanes of a road, and pan to it.

        Args:
            road_id: ID of the road to highlight
        """
        # Clear previous linked lane highlights
        for polygon in self.linked_lane_polygons:
            try:
                if hasattr(polygon, 'set_linked') and polygon.scene() is not None:
                    polygon.set_linked(False)
            except RuntimeError:
                pass
        self.linked_lane_polygons.clear()

        # Deselect previous single-lane selection
        if self.selected_lane_key:
            prev_road_id, prev_section, prev_lane = self.selected_lane_key
            if prev_road_id in self.road_lanes_items:
                for lp in self.road_lanes_items[prev_road_id].lane_items:
                    if (isinstance(lp, InteractiveLanePolygon)
                            and lp.road_id == prev_road_id
                            and lp.section_number == prev_section
                            and lp.lane_id == prev_lane):
                        lp.set_selected(False)
            self.selected_lane_key = None

        # Deselect previous road selection
        if self.selected_road_id:
            self.deselect_road(self.selected_road_id)

        self.selected_road_id = road_id

        # Highlight all lanes of the road
        if road_id in self.road_lanes_items:
            lanes_item = self.road_lanes_items[road_id]
            for lane_polygon in lanes_item.lane_items:
                if isinstance(lane_polygon, InteractiveLanePolygon):
                    lane_polygon.set_selected(True)

        # Also check connecting roads
        if road_id in self.connecting_road_lanes_items:
            lanes_item = self.connecting_road_lanes_items[road_id]
            for lane_polygon in lanes_item.lane_items:
                if isinstance(lane_polygon, InteractiveLanePolygon):
                    lane_polygon.set_selected(True)

        # Pan to the road
        road = self.project.get_road(road_id) if self.project else None
        if road:
            points = road.get_reference_points(self.project)
            if points:
                xs = [p[0] for p in points]
                ys = [p[1] for p in points]
                self.centerOn(sum(xs) / len(xs), sum(ys) / len(ys))

    def deselect_road(self, road_id: str):
        """Deselect all lanes of a road.

        Args:
            road_id: ID of the road to deselect
        """
        if road_id in self.road_lanes_items:
            for lp in self.road_lanes_items[road_id].lane_items:
                if isinstance(lp, InteractiveLanePolygon):
                    lp.set_selected(False)
        if road_id in self.connecting_road_lanes_items:
            for lp in self.connecting_road_lanes_items[road_id].lane_items:
                if isinstance(lp, InteractiveLanePolygon):
                    lp.set_selected(False)

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

        # Deselect previous whole-road selection
        if self.selected_road_id:
            self.deselect_road(self.selected_road_id)
            self.selected_road_id = None

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
                    conn_road = self.project.get_road(connecting_road_id) if self.project else None
                    if not conn_road or not conn_road.is_connecting_road:
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

    @staticmethod
    def _segment_intersects_rect(x1: float, y1: float, x2: float, y2: float, rect: QRectF) -> bool:
        """Check if a line segment intersects or is contained within a rectangle."""
        # Quick check: either endpoint inside rect
        if rect.contains(QPointF(x1, y1)) or rect.contains(QPointF(x2, y2)):
            return True

        # Check intersection with all 4 rect edges
        segment = QLineF(x1, y1, x2, y2)
        edges = [
            QLineF(rect.topLeft(), rect.topRight()),
            QLineF(rect.topRight(), rect.bottomRight()),
            QLineF(rect.bottomRight(), rect.bottomLeft()),
            QLineF(rect.bottomLeft(), rect.topLeft()),
        ]
        for edge in edges:
            itype, _ = segment.intersects(edge)
            if itype == QLineF.IntersectionType.BoundedIntersection:
                return True
        return False

    def _find_items_in_rect(self, rect: QRectF) -> dict:
        """Find project items that intersect the selection rectangle.

        Tests roads (via their polylines), junctions, signals, objects,
        and parking spaces against the given rectangle in scene (pixel)
        coordinates.

        Returns:
            Dict with keys road_ids, junction_ids, signal_ids,
            object_ids, parking_ids — each a list of matching IDs.
        """
        result = {
            "road_ids": [],
            "junction_ids": [],
            "signal_ids": [],
            "object_ids": [],
            "parking_ids": [],
        }
        if not self.project:
            return result

        # Roads: check if any polyline point/segment is in rect
        for road in self.project.roads:
            found = False
            for pid in road.polyline_ids:
                polyline = self.project.get_polyline(pid)
                if not polyline:
                    continue
                points = polyline.points
                for px, py in points:
                    if rect.contains(QPointF(px, py)):
                        found = True
                        break
                if found:
                    break
                for i in range(len(points) - 1):
                    if self._segment_intersects_rect(
                        points[i][0], points[i][1],
                        points[i + 1][0], points[i + 1][1],
                        rect,
                    ):
                        found = True
                        break
                if found:
                    break
            if found:
                result["road_ids"].append(road.id)

        # Junctions: check center point or any connecting road path
        for junction in self.project.junctions:
            found = False
            if junction.center_point and rect.contains(
                QPointF(junction.center_point[0], junction.center_point[1])
            ):
                found = True
            if not found and self.project:
                for cr_id in junction.connecting_road_ids:
                    conn_road = self.project.get_road(cr_id)
                    if not conn_road or not conn_road.inline_path:
                        continue
                    for px, py in conn_road.inline_path:
                        if rect.contains(QPointF(px, py)):
                            found = True
                            break
                    if found:
                        break
                    for i in range(len(conn_road.inline_path) - 1):
                        if self._segment_intersects_rect(
                            conn_road.inline_path[i][0], conn_road.inline_path[i][1],
                            conn_road.inline_path[i + 1][0], conn_road.inline_path[i + 1][1],
                            rect,
                        ):
                            found = True
                            break
                    if found:
                        break
            if found:
                result["junction_ids"].append(junction.id)

        # Signals: check position
        for signal in self.project.signals:
            if signal.position and rect.contains(
                QPointF(signal.position[0], signal.position[1])
            ):
                result["signal_ids"].append(signal.id)

        # Objects: point, polyline, or polygon shapes
        for obj in self.project.objects:
            shape = obj.type.get_shape_type()
            has_polygon_points = obj.points and len(obj.points) >= 3
            if (shape in ("polyline", "polygon") or (shape == "rectangle" and has_polygon_points)) and obj.points:
                found = False
                for px, py in obj.points:
                    if rect.contains(QPointF(px, py)):
                        found = True
                        break
                if not found:
                    n = len(obj.points)
                    # For polygons, also check closing segment
                    end = n if shape != "polyline" else n - 1
                    for i in range(end):
                        j = (i + 1) % n
                        if self._segment_intersects_rect(
                            obj.points[i][0], obj.points[i][1],
                            obj.points[j][0], obj.points[j][1],
                            rect,
                        ):
                            found = True
                            break
                if found:
                    result["object_ids"].append(obj.id)
            elif obj.position and rect.contains(
                QPointF(obj.position[0], obj.position[1])
            ):
                result["object_ids"].append(obj.id)

        # Parking spaces: check position or polygon points
        for parking in self.project.parking_spaces:
            if parking.points:
                found = False
                for px, py in parking.points:
                    if rect.contains(QPointF(px, py)):
                        found = True
                        break
                if not found:
                    pts = parking.points
                    for i in range(len(pts) - 1):
                        if self._segment_intersects_rect(
                            pts[i][0], pts[i][1],
                            pts[i + 1][0], pts[i + 1][1],
                            rect,
                        ):
                            found = True
                            break
                if found:
                    result["parking_ids"].append(parking.id)
            elif parking.position and rect.contains(
                QPointF(parking.position[0], parking.position[1])
            ):
                result["parking_ids"].append(parking.id)

        return result

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

        # For polygon objects (buildings with points, land use areas), check inside or near edge
        if obj.type.get_shape_type() == "polygon" or (
            obj.type.get_shape_type() == "rectangle" and obj.points and len(obj.points) >= 3
        ):
            if obj.points and len(obj.points) >= 3:
                # Point-in-polygon test (ray casting)
                x, y = scene_pos.x(), scene_pos.y()
                inside = False
                n = len(obj.points)
                j = n - 1
                for i in range(n):
                    xi, yi = obj.points[i]
                    xj, yj = obj.points[j]
                    if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                        inside = not inside
                    j = i
                if inside:
                    return True
                # Also check near edges
                for i in range(n):
                    x1, y1 = obj.points[i]
                    x2, y2 = obj.points[(i + 1) % n]
                    dx = x2 - x1
                    dy = y2 - y1
                    length_sq = dx * dx + dy * dy
                    if length_sq == 0:
                        continue
                    t = max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / length_sq))
                    proj_x = x1 + t * dx
                    proj_y = y1 + t * dy
                    dist = ((x - proj_x) ** 2 + (y - proj_y) ** 2) ** 0.5
                    if dist <= tolerance:
                        return True
                return False

        # For point objects, check if click is within tolerance radius of the object position
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
        For polyline/polygon objects, also shows vertex manipulation options.

        Args:
            view_pos: Position in view coordinates
            object_id: ID of the object
            scene_pos: Optional scene position for checking point clicks
        """
        menu = QMenu()
        edit_action = menu.addAction("Edit Properties...")

        # Check if this is a polyline/polygon and if we're over a point or edge
        delete_point_action = None
        insert_point_action = None
        point_index = -1
        segment_index = -1
        if scene_pos and object_id in self.object_items:
            item = self.object_items[object_id]
            is_polyline = item.obj.type.get_shape_type() == "polyline"
            is_polygon = item._is_polygon_with_points()

            if is_polyline or is_polygon:
                point_index = item.get_point_at(scene_pos)
                if point_index >= 0:
                    min_pts = 3 if is_polygon else 2
                    if len(item.obj.points) > min_pts:
                        delete_point_action = menu.addAction("Delete Vertex")
                else:
                    # Check if over an edge for inserting
                    segment_index = item.get_segment_at(scene_pos)
                    if segment_index >= 0:
                        insert_point_action = menu.addAction("Insert Vertex Here")
                menu.addSeparator()

        remove_action = menu.addAction("Remove Object")

        # Show menu and get selected action
        action = menu.exec(self.mapToGlobal(view_pos))

        if action == edit_action:
            self.object_edit_requested.emit(object_id)
        elif action == remove_action:
            self.object_deleted.emit(object_id)
        elif delete_point_action and action == delete_point_action:
            self._delete_object_point(object_id, point_index)
        elif insert_point_action and action == insert_point_action:
            self._insert_object_point(object_id, segment_index, scene_pos)

    def _show_centerline_point_menu(self, view_pos, polyline_id: str, point_index: int):
        """
        Show context menu for centerline point with Delete, Split Section,
        Split Road, and Disconnect options.

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

        # Add disconnect option for connected endpoints
        disconnect_action = None
        linked_road_id = None
        if road and self.project:
            is_start = (point_index == 0)
            is_end = (point_index == polyline.point_count() - 1)
            if is_start and road.predecessor_id and not road.predecessor_junction_id:
                linked = self.project.get_road(road.predecessor_id)
                if linked:
                    linked_name = linked.name or f"Road {linked.id}"
                    menu.addSeparator()
                    disconnect_action = menu.addAction(f"Disconnect from '{linked_name}'")
                    linked_road_id = road.predecessor_id
            elif is_end and road.successor_id and not road.successor_junction_id:
                linked = self.project.get_road(road.successor_id)
                if linked:
                    linked_name = linked.name or f"Road {linked.id}"
                    menu.addSeparator()
                    disconnect_action = menu.addAction(f"Disconnect from '{linked_name}'")
                    linked_road_id = road.successor_id

        # Show menu and get selected action
        action = menu.exec(self.mapToGlobal(view_pos))

        if action == delete_action:
            self._delete_point(polyline_id, point_index)
        elif disconnect_action and action == disconnect_action and road and linked_road_id:
            self.road_unlink_requested.emit(road.id, linked_road_id)
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
                        if not ask_yes_no(
                            self,
                            f"This will create a very small "
                            f"section ({min_distance:.1f} "
                            f"pixels).\n\nContinue anyway?",
                            "Small Section Warning",
                        ):
                            return

            # Emit signal for MainWindow to handle
            self.section_split_requested.emit(road.id, polyline_id, point_index)
        elif action == split_road_action and road:
            # Emit signal for MainWindow to handle road splitting
            self.road_split_requested.emit(road.id, polyline_id, point_index)

    def _show_boundary_point_menu(self, view_pos, polyline_id: str, point_index: int):
        """
        Show context menu for boundary polyline point with Delete option.

        Args:
            view_pos: Position in view coordinates
            polyline_id: ID of the polyline
            point_index: Index of the point clicked
        """
        menu = QMenu()
        delete_action = menu.addAction("Delete Point")

        # Show menu and get selected action
        action = menu.exec(self.mapToGlobal(view_pos))

        if action == delete_action:
            self._delete_point(polyline_id, point_index)

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

    def _show_snap_indicator(self, x: float, y: float) -> None:
        """Show or update the snap indicator ring at the given position."""
        radius = 12
        if self._snap_indicator is None:
            self._snap_indicator = QGraphicsEllipseItem(
                x - radius, y - radius, radius * 2, radius * 2)
            pen = QPen(QColor(0, 255, 100), 2.5)
            pen.setCosmetic(True)
            self._snap_indicator.setPen(pen)
            self._snap_indicator.setBrush(QBrush(QColor(0, 255, 100, 50)))
            self._snap_indicator.setZValue(100)
            self.scene.addItem(self._snap_indicator)
        else:
            self._snap_indicator.setRect(
                x - radius, y - radius, radius * 2, radius * 2)

    def _remove_snap_indicator(self) -> None:
        """Remove the snap indicator ring from the scene."""
        if self._snap_indicator is not None:
            if self._snap_indicator.scene() == self.scene:
                self.scene.removeItem(self._snap_indicator)
            self._snap_indicator = None

    def _offer_road_connection(self) -> None:
        """Show a dialog to connect the dragged road to the snap target."""
        if not self._snap_target or not self.project or not self.drag_polyline_id:
            return

        target_road_id, _target_poly_id, target_point_index, _target_coords = self._snap_target
        dragged_road = self._find_road_by_centerline(self.drag_polyline_id)
        target_road = self.project.get_road(target_road_id)
        if not dragged_road or not target_road:
            return

        # Determine which end of the dragged road was moved
        polyline = self.project.get_polyline(self.drag_polyline_id)
        if not polyline:
            return
        dragged_is_start = (self.drag_point_index == 0)
        dragged_contact = "start" if dragged_is_start else "end"

        # Target contact: point_index 0 = "start", -1 = "end"
        target_contact = "start" if target_point_index == 0 else "end"

        # Check if a connection already exists on this end
        if dragged_is_start and dragged_road.predecessor_id:
            return  # Already has a predecessor
        if not dragged_is_start and dragged_road.successor_id:
            return  # Already has a successor

        # Check if the target end is already connected
        if target_contact == "start" and target_road.predecessor_id:
            return
        if target_contact == "end" and target_road.successor_id:
            return

        # Don't offer self-connection
        if dragged_road.id == target_road.id:
            return

        target_name = target_road.name or f"Road {target_road.id}"
        reply = QMessageBox.question(
            self,
            "Connect Roads",
            f"Connect to '{target_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.road_link_requested.emit(
                dragged_road.id, target_road.id, dragged_contact, target_contact)

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

        # Remove corresponding entry from per-point metadata arrays
        for arr_name in ('geo_points', 'elevations', 's_offsets', 'osm_node_ids'):
            arr = getattr(polyline, arr_name, None)
            if arr is not None and point_index < len(arr):
                arr.pop(point_index)
        # Invalidate geometry segments (no longer valid after point removal)
        polyline.geometry_segments = None

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
        """Delete a point from a guardrail (legacy, calls _delete_object_point)."""
        self._delete_object_point(object_id, point_index)

    def _delete_object_point(self, object_id: str, point_index: int):
        """Delete a vertex from a polyline or polygon object.

        Args:
            object_id: ID of the object
            point_index: Index of the point to delete
        """
        if object_id not in self.object_items:
            return

        item = self.object_items[object_id]
        obj = item.obj

        if not obj.remove_point(point_index):
            min_pts = 3 if obj.type.get_shape_type() == "polygon" else 2
            show_warning(
                self,
                f"This object must have at least {min_pts} points.",
                "Cannot Delete Vertex",
            )
            return

        # Update validity length for guardrails
        if obj.type.get_shape_type() == "polyline" and obj.points and len(obj.points) >= 2:
            total_length = 0.0
            for i in range(len(obj.points) - 1):
                x1, y1 = obj.points[i]
                x2, y2 = obj.points[i + 1]
                total_length += ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
            obj.validity_length = total_length

        item.update_graphics()
        self.object_modified.emit(object_id)

    def _insert_object_point(self, object_id: str, segment_index: int, scene_pos):
        """Insert a vertex on a polygon/polyline edge at the clicked position.

        Args:
            object_id: ID of the object
            segment_index: Index of the first point of the edge
            scene_pos: Scene position where the click occurred
        """
        if object_id not in self.object_items:
            return

        item = self.object_items[object_id]
        obj = item.obj
        insert_idx = segment_index + 1

        # Compute geo coords for the new point
        geo_point = None
        transformer = self._get_geo_transformer()
        if transformer:
            lon, lat = transformer.pixel_to_geo(scene_pos.x(), scene_pos.y())
            geo_point = (lon, lat)

        obj.insert_point(insert_idx, (scene_pos.x(), scene_pos.y()), geo_point)

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
        handled = False

        if event.button() == Qt.MouseButton.LeftButton:
            handled = self._handle_left_press(scene_pos, event)
        elif event.button() == Qt.MouseButton.RightButton:
            self._handle_right_press(scene_pos, event)

        if not handled:
            super().mousePressEvent(event)

    def _handle_left_press(self, scene_pos, event: QMouseEvent) -> bool:
        """Dispatch left-button press by current interaction mode.

        Returns True if the event was consumed by a custom action (suppresses
        QGraphicsView's built-in ScrollHandDrag to avoid fighting for control).
        """
        if self.autofit_mode:
            self._handle_autofit_click(scene_pos)
            return True

        if self.drawing_mode:
            self.current_polyline.add_point(scene_pos.x(), scene_pos.y())
            self.current_polyline_item.update_graphics()
            return True

        elif self.junction_mode:
            junction = Junction(id=self.project.next_id('junction') if self.project else "")
            junction.center_point = (scene_pos.x(), scene_pos.y())
            self.junction_added.emit(junction)
            return True

        elif self.signal_mode:
            self.signal_placement_requested.emit(scene_pos.x(), scene_pos.y())
            return True

        elif self.object_mode:
            if self.object_type_to_place and self.object_type_to_place.get_shape_type() == "polyline":
                self.drawing_guardrail = True
                self.guardrail_points = [(scene_pos.x(), scene_pos.y())]
            elif self.object_polygon_mode:
                self._add_object_polygon_point(scene_pos.x(), scene_pos.y())
            else:
                self.object_placement_requested.emit(scene_pos.x(), scene_pos.y(), self.object_type_to_place)
            return True

        elif self.parking_mode:
            if self.parking_polygon_mode:
                self._add_parking_polygon_point(scene_pos.x(), scene_pos.y())
            else:
                self.parking_placement_requested.emit(
                    scene_pos.x(), scene_pos.y(),
                    self.parking_type_to_place,
                    self.parking_access_to_place
                )
            return True

        elif self.pick_point_mode:
            self.point_picked.emit(scene_pos.x(), scene_pos.y())
            self.pick_point_mode = False
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            return True

        else:
            return self._handle_select_mode_press(scene_pos, event)

    def _handle_select_mode_press(self, scene_pos, event: QMouseEvent) -> bool:
        """Handle left-click in default select/drag mode.

        Returns True if a custom action (area select, point insert, or entity
        drag) was started — caller should suppress super().mousePressEvent.
        """
        # Alt+LMB drag starts area selection for batch delete
        if event.modifiers() & Qt.KeyboardModifier.AltModifier:
            self._area_selecting = True
            self._area_select_start = scene_pos
            self._area_select_rect_item = QGraphicsRectItem()
            self._area_select_rect_item.setPen(
                QPen(QColor(70, 130, 180), 1.5, Qt.PenStyle.DashLine)
            )
            self._area_select_rect_item.setBrush(
                QBrush(QColor(70, 130, 180, 40))
            )
            self._area_select_rect_item.setZValue(1000)
            self.scene.addItem(self._area_select_rect_item)
            return True

        # Ctrl+Click on a line segment to insert a point
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if self._handle_ctrl_click_insert(scene_pos):
                return True

        # Check if clicking on an entity to start dragging
        if self._try_start_drag(scene_pos):
            return True

        # Otherwise, handle entity selection (let super handle scroll drag)
        self._handle_click_selection(scene_pos)
        return False

    def _handle_ctrl_click_insert(self, scene_pos) -> bool:
        """Handle Ctrl+click point insertion on line segments. Returns True if handled."""
        # Check object polylines and polygons
        for object_id, object_item in self.object_items.items():
            is_polyline = object_item.obj.type.get_shape_type() == "polyline"
            is_polygon = object_item._is_polygon_with_points()
            if is_polyline or is_polygon:
                segment_index = object_item.get_segment_at(scene_pos)
                if segment_index >= 0:
                    self._insert_object_point(object_id, segment_index, scene_pos)
                    if is_polyline:
                        obj = object_item.obj
                        if obj.points and len(obj.points) >= 2:
                            total_length = 0.0
                            for i in range(len(obj.points) - 1):
                                x1, y1 = obj.points[i]
                                x2, y2 = obj.points[i + 1]
                                total_length += ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
                            obj.validity_length = total_length
                    return True

        # Check polylines
        for polyline_id, item in self.polyline_items.items():
            segment_index = item.get_segment_at(scene_pos)
            if segment_index >= 0:
                self._insert_polyline_point(polyline_id, item, segment_index, scene_pos)
                return True

        # Check connecting roads (polyline geometry only)
        for conn_road_id, item in self.connecting_road_centerline_items.items():
            if item.connecting_road.geometry_type != "polyline":
                continue
            segment_index = item.get_segment_at(scene_pos)
            if segment_index >= 0:
                connecting_road = item.connecting_road
                insert_index = segment_index + 1
                connecting_road.inline_path.insert(insert_index, (scene_pos.x(), scene_pos.y()))
                item.update_graphics()
                if conn_road_id in self.connecting_road_lanes_items:
                    self.connecting_road_lanes_items[conn_road_id].update_graphics()
                self.connecting_road_modified.emit(conn_road_id)
                return True

        return False

    def _insert_polyline_point(self, polyline_id, item, segment_index, scene_pos):
        """Insert a point into a polyline at the given segment, updating all metadata."""
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

        polyline.insert_point(insert_index, scene_pos.x(), scene_pos.y())

        # Insert corresponding entries in per-point metadata
        if polyline.geo_points is not None:
            # Prefer the actual transformer for accuracy.  Falls back to
            # linear interpolation between neighbour geo_points when no
            # transformer is available.
            transformer = self._get_geo_transformer()
            if transformer is not None:
                lon, lat = transformer.pixel_to_geo(
                    scene_pos.x(), scene_pos.y())
                new_geo = (lon, lat)
            else:
                new_geo = self._interpolate_geo_for_insert(
                    polyline, insert_index, scene_pos.x(), scene_pos.y())
            if new_geo is None:
                if insert_index > 0:
                    new_geo = tuple(polyline.geo_points[insert_index - 1])
                elif insert_index < len(polyline.geo_points):
                    new_geo = tuple(polyline.geo_points[insert_index])
                else:
                    new_geo = (0.0, 0.0)
            polyline.geo_points.insert(insert_index, new_geo)
        if polyline.elevations is not None:
            prev_e = (
                polyline.elevations[insert_index - 1]
                if insert_index > 0 else 0.0
            )
            next_e = (
                polyline.elevations[insert_index]
                if insert_index < len(polyline.elevations)
                else prev_e
            )
            polyline.elevations.insert(insert_index, (prev_e + next_e) / 2.0)
        if polyline.s_offsets is not None:
            polyline.s_offsets.insert(insert_index, 0.0)
        if polyline.osm_node_ids is not None:
            polyline.osm_node_ids.insert(insert_index, None)
        polyline.geometry_segments = None  # Invalidated

        # Update section boundaries with new point list
        if affected_road:
            affected_road.update_section_boundaries(polyline.points)
            if affected_road.id in self.road_lanes_items:
                self.road_lanes_items[affected_road.id].update_graphics()

        item.update_graphics()
        self.polyline_modified.emit(polyline_id)
        if self.soffsets_visible:
            self._update_soffset_labels(polyline_id)

    def _try_start_drag(self, scene_pos) -> bool:
        """Check if clicking on a draggable entity and start drag. Returns True if handled."""
        # Junction drag
        for junction_id, item in self.junction_items.items():
            if item.is_at_position(scene_pos):
                self.dragging_junction = True
                self.drag_junction_id = junction_id
                return True

        # Guardrail/polygon vertex drag
        for object_id, item in self.object_items.items():
            if item.obj.type.get_shape_type() == "polyline" or item._is_polygon_with_points():
                point_index = item.get_point_at(scene_pos)
                if point_index >= 0:
                    self.dragging_guardrail_point = True
                    self.drag_object_id = object_id
                    self.drag_point_index = point_index
                    self._drag_start_obj_points = list(item.obj.points)
                    self._drag_start_obj_geo_points = (
                        list(item.obj.geo_points) if item.obj.geo_points else None
                    )
                    return True

        # Polyline point drag
        for polyline_id, item in self.polyline_items.items():
            point_index = item.get_point_at(scene_pos)
            if point_index >= 0:
                self.dragging_point = True
                self.drag_polyline_id = polyline_id
                self.drag_point_index = point_index
                item.set_selected_point(point_index)
                polyline = item.polyline
                self._drag_start_points = list(polyline.points)
                self._drag_start_geo_points = list(polyline.geo_points) if polyline.geo_points else None
                is_endpoint = (point_index == 0 or
                               point_index == polyline.point_count() - 1)
                is_centerline = (polyline.line_type == LineType.CENTERLINE)
                self._dragging_endpoint = is_endpoint and is_centerline
                return True

        # Connecting road point drag (polyline geometry only)
        for conn_road_id, item in self.connecting_road_centerline_items.items():
            if item.connecting_road.geometry_type != "polyline":
                continue
            point_index = item.get_point_at(scene_pos)
            if point_index >= 0:
                self.dragging_connecting_road_point = True
                self.drag_connecting_road_id = conn_road_id
                self.drag_point_index = point_index
                item.selected_point_index = point_index
                item.update_graphics()
                return True

        return False

    def _handle_click_selection(self, scene_pos):
        """Detect which entity was clicked and update selection state."""
        # Priority: junction > signal > object > polyline
        clicked_junction_id = None
        for junction_id, item in self.junction_items.items():
            if item.is_at_position(scene_pos):
                clicked_junction_id = junction_id
                break

        clicked_signal_id = None
        if not clicked_junction_id:
            for signal_id, item in self.signal_items.items():
                if item.signal.position:
                    sx, sy = item.signal.position
                    dist = ((scene_pos.x() - sx) ** 2 + (scene_pos.y() - sy) ** 2) ** 0.5
                    if dist < 20:
                        clicked_signal_id = signal_id
                        break

        clicked_object_id = None
        if not clicked_junction_id and not clicked_signal_id:
            for object_id, item in self.object_items.items():
                if self._is_click_on_object(item, scene_pos):
                    clicked_object_id = object_id
                    break

        clicked_polyline_id = None
        if not clicked_junction_id and not clicked_signal_id and not clicked_object_id:
            for polyline_id, item in self.polyline_items.items():
                if item.is_near_line(scene_pos):
                    clicked_polyline_id = polyline_id
                    break

        # Update selection — deselect all, then select clicked entity
        self._deselect_all()
        if clicked_junction_id:
            self.selected_junction_id = clicked_junction_id
            self.junction_items[clicked_junction_id].set_selected(True)
            self.junction_selected.emit(clicked_junction_id)
        elif clicked_signal_id:
            self.selected_signal_id = clicked_signal_id
            self.signal_items[clicked_signal_id].setSelected(True)
            self.signal_selected.emit(clicked_signal_id)
        elif clicked_object_id:
            self.selected_object_id = clicked_object_id
            self.object_items[clicked_object_id].set_selected(True)
            self.object_selected.emit(clicked_object_id)
        elif clicked_polyline_id:
            self.selected_polyline_id = clicked_polyline_id
            self.polyline_items[clicked_polyline_id].set_selected(True)
            self.polyline_selected.emit(clicked_polyline_id)

    def _deselect_all(self):
        """Deselect all entity types."""
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
        self.selected_object_id = None

    def _handle_right_press(self, scene_pos, event: QMouseEvent):
        """Handle right-button press events."""
        if self.measure_mode:
            self.measure_points.append(scene_pos)
            self._draw_measure_point(scene_pos)
            if len(self.measure_points) == 2:
                self._draw_measurement()
                self.measure_points.clear()

        elif self.show_scale_mode:
            self._display_scale_at_point(scene_pos)

        elif self.drawing_guardrail:
            self.guardrail_points.append((scene_pos.x(), scene_pos.y()))

        elif self.signal_mode:
            for signal_id, item in self.signal_items.items():
                if item.contains(item.mapFromScene(scene_pos)):
                    self._show_signal_menu(event.pos(), signal_id)
                    return

        elif self.object_mode:
            for object_id, item in self.object_items.items():
                if self._is_click_on_object(item, scene_pos):
                    self._show_object_menu(event.pos(), object_id, scene_pos)
                    return

        elif not self.drawing_mode:
            self._handle_right_click_context_menu(scene_pos, event)

    def _handle_right_click_context_menu(self, scene_pos, event: QMouseEvent):
        """Handle right-click context menus for signals, objects, polylines, connecting roads."""
        for signal_id, item in self.signal_items.items():
            if item.contains(item.mapFromScene(scene_pos)):
                self._show_signal_menu(event.pos(), signal_id)
                return

        for object_id, item in self.object_items.items():
            if self._is_click_on_object(item, scene_pos):
                self._show_object_menu(event.pos(), object_id, scene_pos)
                return

        for polyline_id, item in self.polyline_items.items():
            point_index = item.get_point_at(scene_pos)
            if point_index >= 0:
                if item.polyline.line_type == LineType.CENTERLINE:
                    self._show_centerline_point_menu(event.pos(), polyline_id, point_index)
                else:
                    self._show_boundary_point_menu(event.pos(), polyline_id, point_index)
                return

        # Connecting road point deletion (polyline geometry only)
        for conn_road_id, item in self.connecting_road_centerline_items.items():
            if item.connecting_road.geometry_type != "polyline":
                continue
            point_index = item.get_point_at(scene_pos)
            if point_index >= 0:
                connecting_road = item.connecting_road
                if len(connecting_road.inline_path) > 2:
                    connecting_road.inline_path.pop(point_index)
                    item.update_graphics()
                    if conn_road_id in self.connecting_road_lanes_items:
                        self.connecting_road_lanes_items[conn_road_id].update_graphics()
                return

    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle mouse move events."""
        # Always emit mouse position for status bar
        scene_pos = self.mapToScene(event.pos())
        self.mouse_moved.emit(scene_pos.x(), scene_pos.y())

        if self._area_selecting and self._area_select_start is not None:
            # Update rubber-band rectangle
            if self._area_select_rect_item:
                rect = QRectF(self._area_select_start, scene_pos).normalized()
                self._area_select_rect_item.setRect(rect)
            return

        if self.drawing_guardrail and event.buttons() & Qt.MouseButton.LeftButton:
            # Dragging to create guardrail - add points continuously
            if not self.guardrail_points or \
               ((scene_pos.x() - self.guardrail_points[-1][0])**2 +
                (scene_pos.y() - self.guardrail_points[-1][1])**2) > 100:  # Min 10px spacing
                self.guardrail_points.append((scene_pos.x(), scene_pos.y()))
        elif self.dragging_guardrail_point and self.drag_object_id:
            # Dragging a guardrail/polygon vertex
            item = self.object_items[self.drag_object_id]
            obj = item.obj
            if self.drag_point_index >= 0 and self.drag_point_index < len(obj.points):
                obj.points[self.drag_point_index] = (scene_pos.x(), scene_pos.y())
                obj.update_centroid()
                item.update_graphics()
        elif self.dragging_junction and self.drag_junction_id:
            # Update junction position directly through the junction item
            item = self.junction_items[self.drag_junction_id]
            item.junction.center_point = (scene_pos.x(), scene_pos.y())
            item.update_graphics()
        elif self.dragging_point and self.drag_polyline_id:
            item = self.polyline_items[self.drag_polyline_id]
            drag_x, drag_y = scene_pos.x(), scene_pos.y()

            # Endpoint snap detection
            if self._dragging_endpoint and self.project:
                road = self._find_road_by_centerline(self.drag_polyline_id)
                exclude_id = road.id if road else None
                nearby = self.project.find_nearby_road_endpoints(
                    (drag_x, drag_y), exclude_road_id=exclude_id, tolerance=20.0)
                if nearby:
                    target = nearby[0]  # closest
                    self._snap_target = (target[0], target[1], target[2], target[3])
                    tx, ty = target[3]
                    drag_x, drag_y = tx, ty  # snap position
                    self._show_snap_indicator(tx, ty)
                else:
                    self._snap_target = None
                    self._remove_snap_indicator()

            item.polyline.update_point(self.drag_point_index, drag_x, drag_y)
            item.update_graphics()
        elif self.dragging_connecting_road_point and self.drag_connecting_road_id:
            # Dragging a connecting road point
            item = self.connecting_road_centerline_items[self.drag_connecting_road_id]
            # Find the connecting road
            connecting_road = item.connecting_road
            if self.drag_point_index >= 0 and self.drag_point_index < len(connecting_road.inline_path):
                # Update the point position
                connecting_road.inline_path[self.drag_point_index] = (scene_pos.x(), scene_pos.y())
                # Refresh centerline graphics
                item.update_graphics()
                # Refresh lane graphics
                if self.drag_connecting_road_id in self.connecting_road_lanes_items:
                    self.connecting_road_lanes_items[self.drag_connecting_road_id].update_graphics()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        """Handle mouse release events."""
        if self._area_selecting:
            # Finalize area selection
            self._area_selecting = False
            rect = None
            if self._area_select_rect_item and self._area_select_start is not None:
                scene_pos = self.mapToScene(event.pos())
                rect = QRectF(self._area_select_start, scene_pos).normalized()
                self.scene.removeItem(self._area_select_rect_item)
            self._area_select_rect_item = None
            self._area_select_start = None

            # Only proceed if rectangle has meaningful size (>5px both dims)
            if rect and rect.width() > 5 and rect.height() > 5:
                selected = self._find_items_in_rect(rect)
                if any(selected.values()):
                    self.area_delete_requested.emit(selected)
            return

        if self.drawing_guardrail and event.button() == Qt.MouseButton.LeftButton:
            # Finish guardrail drawing
            if len(self.guardrail_points) >= 2:
                # Create guardrail object with the points
                obj = RoadObject(
                    object_id=self.project.next_id('object') if self.project else "",
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
                item = self.object_items[self.drag_object_id]
                obj = item.obj
                # Update validity length for guardrails
                if obj.type.get_shape_type() == "polyline" and obj.points and len(obj.points) >= 2:
                    total_length = 0.0
                    for i in range(len(obj.points) - 1):
                        x1, y1 = obj.points[i]
                        x2, y2 = obj.points[i + 1]
                        total_length += ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
                    obj.validity_length = total_length
                # Update geo coords for polygon vertex drags
                if item._is_polygon_with_points():
                    transformer = self._get_geo_transformer()
                    if transformer and self.drag_point_index >= 0 and self.drag_point_index < len(obj.points):
                        px, py = obj.points[self.drag_point_index]
                        lon, lat = transformer.pixel_to_geo(px, py)
                        if obj.geo_points and self.drag_point_index < len(obj.geo_points):
                            obj.geo_points[self.drag_point_index] = (lon, lat)
                        # Update geo_position centroid
                        if obj.geo_points:
                            obj.update_centroid()
                # Emit modification signal
                self.object_modified.emit(self.drag_object_id)
            self.drag_object_id = None
            self.drag_point_index = -1
        elif self.dragging_junction:
            self.dragging_junction = False
            if self.drag_junction_id:
                # Update geo coords so the edit survives view switches
                item = self.junction_items[self.drag_junction_id]
                junction = item.junction
                transformer = self._get_geo_transformer()
                if transformer and junction.center_point:
                    cx, cy = junction.center_point
                    lon, lat = transformer.pixel_to_geo(cx, cy)
                    junction.geo_center_point = (lon, lat)
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

                # Update the dragged point's geo_point only if it actually moved
                if (polyline.geo_points is not None
                        and 0 <= self.drag_point_index < len(polyline.geo_points)
                        and hasattr(self, '_drag_start_points')
                        and self._drag_start_points is not None):
                    idx = self.drag_point_index
                    new_px, new_py = polyline.points[idx]
                    old_px, old_py = self._drag_start_points[idx]
                    moved = abs(new_px - old_px) > 0.5 or abs(new_py - old_py) > 0.5

                    if moved:
                        # Use the active transformer to compute the
                        # geo_point for the new pixel position.  Falls back
                        # to a local Jacobian approximation when no
                        # transformer is available.
                        transformer = self._get_geo_transformer()
                        new_geo = None
                        if transformer is not None:
                            lon, lat = transformer.pixel_to_geo(
                                new_px, new_py)
                            new_geo = (lon, lat)
                        else:
                            old_geo = (
                                self._drag_start_geo_points[idx]
                                if self._drag_start_geo_points else None)
                            if old_geo:
                                new_geo = self._compute_dragged_geo_point(
                                    polyline, idx, old_px, old_py,
                                    old_geo, None)
                        if new_geo is not None:
                            polyline.geo_points[idx] = new_geo
                        # If new_geo is None, keep existing geo_point unchanged
                        # Invalidate preserved geometry (no longer valid after move)
                        polyline.geometry_segments = None

                # Emit undo signal with captured state
                if hasattr(self, '_drag_start_points') and self._drag_start_points is not None:
                    self.polyline_modified_for_undo.emit(
                        self.drag_polyline_id,
                        self._drag_start_points,
                        list(polyline.points),
                        self._drag_start_geo_points,
                        list(polyline.geo_points) if polyline.geo_points else None
                    )
                    self._drag_start_points = None
                    self._drag_start_geo_points = None

                self.polyline_modified.emit(self.drag_polyline_id)
                # Update s-offset labels after point drag
                if self.soffsets_visible:
                    self._update_soffset_labels(self.drag_polyline_id)

                # Post-drag road connection suggestion
                if self._dragging_endpoint and self._snap_target and self.project:
                    self._offer_road_connection()

            self._dragging_endpoint = False
            self._snap_target = None
            self._remove_snap_indicator()
            self.drag_polyline_id = None
            self.drag_point_index = -1
        elif self.dragging_connecting_road_point:
            self.dragging_connecting_road_point = False
            if self.drag_connecting_road_id:
                item = self.connecting_road_centerline_items[self.drag_connecting_road_id]
                connecting_road = item.connecting_road
                # Update geo coords so the edit survives view switches
                transformer = self._get_geo_transformer()
                if transformer and connecting_road.inline_path:
                    connecting_road.inline_geo_path = [
                        transformer.pixel_to_geo(x, y)
                        for x, y in connecting_road.inline_path
                    ]
                item.selected_point_index = -1
                item.update_graphics()
                self.connecting_road_modified.emit(self.drag_connecting_road_id)
            self.drag_connecting_road_id = None
            self.drag_point_index = -1
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """Handle double-click to finish polyline/polygon, edit polyline, or edit junction."""
        if self.drawing_mode and event.button() == Qt.MouseButton.LeftButton:
            self.finish_current_polyline()
        elif self.parking_mode and self.parking_polygon_mode and event.button() == Qt.MouseButton.LeftButton:
            # Finish parking polygon on double-click
            self._finish_parking_polygon()
        elif self.object_mode and self.object_polygon_mode and event.button() == Qt.MouseButton.LeftButton:
            # Finish object polygon on double-click
            self._finish_object_polygon()
        elif event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.pos())

            # Check if double-clicking on a junction to edit
            for junction_id, item in self.junction_items.items():
                if item.is_at_position(scene_pos):
                    self.junction_edit_requested.emit(junction_id)
                    return

            # Check if double-clicking on a polygon/polyline edge to insert vertex
            for object_id, item in self.object_items.items():
                if item._is_polygon_with_points() or item.obj.type.get_shape_type() == "polyline":
                    # Only insert if clicking on an edge (not a vertex)
                    if item.get_point_at(scene_pos) < 0:
                        segment_index = item.get_segment_at(scene_pos)
                        if segment_index >= 0:
                            self._insert_object_point(object_id, segment_index, scene_pos)
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
        if self.adjustment_mode:
            # Handle adjustment keys first
            if self._handle_adjustment_key(event):
                return
            # Fall through to other handlers if not handled
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
        elif self.parking_mode and self.parking_polygon_mode:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._finish_parking_polygon()
            elif event.key() == Qt.Key.Key_Escape:
                self._cancel_parking_polygon()
        elif self.object_mode and self.object_polygon_mode:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._finish_object_polygon()
            elif event.key() == Qt.Key.Key_Escape:
                self._cancel_object_polygon()
        else:
            if event.key() == Qt.Key.Key_Delete:
                # Delete selected polyline
                self.delete_selected()
            else:
                super().keyPressEvent(event)

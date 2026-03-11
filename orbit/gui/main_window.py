"""
Main window for ORBIT application.

Provides the main GUI with menus, toolbar, status bar, and central view.
"""

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QAction, QKeySequence, QUndoStack
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QToolBar,
)

from orbit.models import LineType, Project
from orbit.utils.coordinate_transform import TransformAdjustment
from orbit.utils.logging_config import get_logger

from .image_view import ImageView
from .utils.message_helpers import ask_yes_no, show_error, show_info, show_warning
from .widgets.adjustment_panel import AdjustmentPanel
from .widgets.elements_tree import ElementsTreeWidget
from .widgets.road_tree import RoadTreeWidget

logger = get_logger(__name__)


class MainWindow(QMainWindow):
    """Main application window for ORBIT."""

    def __init__(self, image_path: Optional[Path] = None, verbose: bool = False,
                 xodr_schema_path: Optional[str] = None, parent=None):
        super().__init__(parent)

        # Project state
        self.project = Project()
        self.current_project_file: Optional[Path] = None
        self.modified = False
        self.undo_stack = QUndoStack(self)
        self.undo_stack.cleanChanged.connect(self._on_undo_clean_changed)
        self.verbose = verbose  # Debug flag
        self.xodr_schema_path = xodr_schema_path  # Path to OpenDRIVE XSD schema for validation

        # Cached transformer for real-time coordinate display
        self._cached_transformer = None

        # Aerial view state
        self._aerial_view_active = False
        self._original_image_np = None  # Saved original background
        self._original_transformer = None  # Saved original transformer
        self._aerial_transformer = None  # Transformer for aerial tile image
        self._aerial_zoom = 18  # Default tile zoom level

        # Session-level last used directory for file dialogs
        self._last_file_directory: str = str(Path.home())

        # Settings
        self.settings = QSettings()

        # Setup UI
        self.setup_ui()
        self.create_actions()
        self.create_menus()
        self.create_toolbar()
        self.create_dock_widgets()
        self.update_window_title()

        # Load image if provided
        if image_path:
            self.load_image(image_path)

        # Restore window geometry
        self.restore_geometry()

    def setup_ui(self):
        """Setup the main UI components."""
        self.setWindowTitle("ORBIT - OpenDrive Road Builder from Imagery Tool")
        self.setMinimumSize(1200, 800)

        # Create central image view (with verbose flag for debugging)
        self.image_view = ImageView(self, verbose=self.verbose)
        self.setCentralWidget(self.image_view)

        # Connect signals
        self.image_view.polyline_added.connect(self.on_polyline_added)
        self.image_view.polyline_modified.connect(self.on_polyline_modified)
        self.image_view.polyline_modified_for_undo.connect(self.on_polyline_modified_for_undo)
        self.image_view.polyline_deleted.connect(self.on_polyline_deleted)
        self.image_view.polyline_edit_requested.connect(self.edit_polyline_properties)
        self.image_view.polyline_selected.connect(self.on_polyline_selected_in_view)
        self.image_view.junction_added.connect(self.on_junction_added)
        self.image_view.junction_modified.connect(self.on_junction_modified)
        self.image_view.junction_deleted.connect(self.on_junction_deleted)
        self.image_view.junction_edit_requested.connect(self.edit_junction_properties)
        self.image_view.junction_selected.connect(self.on_junction_selected_in_view)
        self.image_view.signal_added.connect(self.on_signal_added)
        self.image_view.signal_modified.connect(self.on_signal_modified)
        self.image_view.signal_deleted.connect(self.on_signal_deleted)
        self.image_view.signal_edit_requested.connect(self.edit_signal_properties)
        self.image_view.signal_selected.connect(self.on_signal_selected_in_view)
        self.image_view.signal_placement_requested.connect(self.on_signal_placement_requested)
        self.image_view.object_added.connect(self.on_object_added)
        self.image_view.object_modified.connect(self.on_object_modified)
        self.image_view.object_deleted.connect(self.on_object_deleted)
        self.image_view.object_edit_requested.connect(self.edit_object_properties)
        self.image_view.object_selected.connect(self.on_object_selected_in_view)
        self.image_view.object_placement_requested.connect(self.on_object_placement_requested)
        self.image_view.parking_placement_requested.connect(self.on_parking_placement_requested)
        self.image_view.parking_polygon_completed.connect(self.on_parking_polygon_completed)
        self.image_view.object_polygon_completed.connect(self.on_object_polygon_completed)
        self.image_view.section_split_requested.connect(self.on_section_split_requested)
        self.image_view.road_split_requested.connect(self.on_road_split_requested)
        self.image_view.section_modified.connect(self.on_section_modified)
        self.image_view.lane_segment_clicked.connect(self.on_lane_segment_clicked)
        self.image_view.connecting_road_modified.connect(self.on_connecting_road_modified)
        self.image_view.connecting_road_lane_clicked.connect(self.on_connecting_road_lane_clicked_in_view)
        self.image_view.lane_edit_requested.connect(self.on_lane_edit_requested)
        self.image_view.connecting_road_lane_edit_requested.connect(self.on_connecting_road_lane_edit_requested)
        self.image_view.point_picked.connect(self.on_point_picked)
        self.image_view.area_delete_requested.connect(self.on_area_delete_requested)
        self.image_view.road_link_requested.connect(self.on_road_link_requested)
        self.image_view.road_unlink_requested.connect(self.on_road_unlink_requested)

        # Status bar with permanent widgets
        self.setup_statusbar()

    def setup_statusbar(self):
        """Setup status bar with permanent widgets for scale and mouse position."""
        status_bar = self.statusBar()

        # Temporary message area (left side)
        status_bar.showMessage("Ready")

        # Scale label (permanent, right side)
        self.scale_label = QLabel("Scale: N/A")
        self.scale_label.setMinimumWidth(280)  # Wider for "X (H) × Y (V)" format
        self.scale_label.setStyleSheet("QLabel { padding: 2px 8px; }")
        status_bar.addPermanentWidget(self.scale_label)

        # Geographic coordinates label (permanent, right side)
        self.geo_coords_label = QLabel("Geo: N/A")
        self.geo_coords_label.setMinimumWidth(250)
        self.geo_coords_label.setStyleSheet("QLabel { padding: 2px 8px; }")
        status_bar.addPermanentWidget(self.geo_coords_label)

        # Mouse position label (permanent, right side)
        self.mouse_pos_label = QLabel("Pixel: N/A")
        self.mouse_pos_label.setMinimumWidth(150)
        self.mouse_pos_label.setStyleSheet("QLabel { padding: 2px 8px; }")
        status_bar.addPermanentWidget(self.mouse_pos_label)

        # Connect mouse move signal from image view
        self.image_view.mouse_moved.connect(self.on_mouse_moved)

        # Update scale if georeferencing exists
        self.update_scale_display()

    def create_actions(self):
        """Create all actions for menus and toolbar."""
        # File actions
        self.new_action = QAction("&New Project", self)
        self.new_action.setShortcut(QKeySequence.StandardKey.New)
        self.new_action.setStatusTip("Create a new project")
        self.new_action.triggered.connect(self.new_project)

        self.open_action = QAction("&Open Project...", self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.setStatusTip("Open an existing project")
        self.open_action.triggered.connect(self.open_project)

        self.save_action = QAction("&Save Project", self)
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.setStatusTip("Save the current project")
        self.save_action.triggered.connect(self.save_project)

        self.save_as_action = QAction("Save Project &As...", self)
        self.save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.save_as_action.setStatusTip("Save the project with a new name")
        self.save_as_action.triggered.connect(self.save_project_as)

        self.load_image_action = QAction("Load &Image...", self)
        self.load_image_action.setShortcut(QKeySequence("Ctrl+I"))
        self.load_image_action.setStatusTip("Load an image file")
        self.load_image_action.triggered.connect(self.load_image_dialog)

        self.export_action = QAction("&Export to OpenDrive...", self)
        self.export_action.setShortcut(QKeySequence("Ctrl+E"))
        self.export_action.setStatusTip("Export to OpenDrive format")
        self.export_action.triggered.connect(self.export_to_opendrive)

        self.export_georef_action = QAction("Export &Georeferencing...", self)
        self.export_georef_action.setStatusTip("Export georeferencing parameters to JSON")
        self.export_georef_action.triggered.connect(self.export_georeferencing)

        self.export_layout_mask_action = QAction("Export Layout &Mask...", self)
        self.export_layout_mask_action.setStatusTip("Export lane segmentation mask and metadata")
        self.export_layout_mask_action.triggered.connect(self.export_layout_mask)

        self.export_osm_action = QAction("Export to &OSM...", self)
        self.export_osm_action.setStatusTip("Export map data to OpenStreetMap format (.osm)")
        self.export_osm_action.triggered.connect(self.export_to_osm)

        self.import_osm_action = QAction("Import &OpenStreetMap Data...", self)
        self.import_osm_action.setShortcut(QKeySequence("Ctrl+Shift+I"))
        self.import_osm_action.setStatusTip("Import road network from OpenStreetMap (API or file)")
        self.import_osm_action.triggered.connect(self.import_osm_data)

        self.import_opendrive_action = QAction("Import from &OpenDrive...", self)
        self.import_opendrive_action.setShortcut(QKeySequence("Ctrl+Shift+O"))
        self.import_opendrive_action.setStatusTip("Import road network from OpenDrive file (.xodr)")
        self.import_opendrive_action.triggered.connect(self.import_opendrive_file)

        self.exit_action = QAction("E&xit", self)
        self.exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        self.exit_action.setStatusTip("Exit the application")
        self.exit_action.triggered.connect(self.close)

        # Edit actions - using QUndoStack
        self.undo_action = self.undo_stack.createUndoAction(self, "&Undo")
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.setStatusTip("Undo last action")

        self.redo_action = self.undo_stack.createRedoAction(self, "&Redo")
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self.redo_action.setStatusTip("Redo last undone action")

        self.delete_action = QAction("&Delete Selected", self)
        self.delete_action.setShortcut(QKeySequence.StandardKey.Delete)
        self.delete_action.setStatusTip("Delete selected item")
        self.delete_action.triggered.connect(self.delete_selected)

        self.preferences_action = QAction("Pr&eferences...", self)
        self.preferences_action.setStatusTip("Configure project preferences")
        self.preferences_action.triggered.connect(self.show_preferences)

        self.junction_groups_action = QAction("&Junction Groups...", self)
        self.junction_groups_action.setStatusTip("Manage junction groups (roundabouts, complex junctions)")
        self.junction_groups_action.triggered.connect(self.show_junction_groups)

        # View actions
        self.zoom_in_action = QAction("Zoom &In", self)
        self.zoom_in_action.setShortcut(QKeySequence.StandardKey.ZoomIn)
        self.zoom_in_action.setStatusTip("Zoom in")
        self.zoom_in_action.triggered.connect(self.image_view.zoom_in)

        self.zoom_out_action = QAction("Zoom &Out", self)
        self.zoom_out_action.setShortcut(QKeySequence.StandardKey.ZoomOut)
        self.zoom_out_action.setStatusTip("Zoom out")
        self.zoom_out_action.triggered.connect(self.image_view.zoom_out)

        self.fit_action = QAction("&Fit to Window", self)
        self.fit_action.setShortcut(QKeySequence("Ctrl+0"))
        self.fit_action.setStatusTip("Fit image to window")
        self.fit_action.triggered.connect(self.image_view.fit_to_window)

        self.reset_view_action = QAction("&Reset View", self)
        self.reset_view_action.setShortcut(QKeySequence("Ctrl+R"))
        self.reset_view_action.setStatusTip("Reset view to 100%")
        self.reset_view_action.triggered.connect(self.image_view.reset_view)

        self.toggle_lanes_action = QAction("Show &Lanes", self)
        self.toggle_lanes_action.setShortcut(QKeySequence("Ctrl+L"))
        self.toggle_lanes_action.setStatusTip("Toggle lane visualization on/off")
        self.toggle_lanes_action.setCheckable(True)
        self.toggle_lanes_action.setChecked(True)  # Lanes visible by default
        self.toggle_lanes_action.triggered.connect(self.toggle_lane_visibility)

        self.toggle_soffsets_action = QAction("Show &S-Offsets", self)
        self.toggle_soffsets_action.setStatusTip("Toggle s-offset labels on road reference line points")
        self.toggle_soffsets_action.setCheckable(True)
        self.toggle_soffsets_action.setChecked(False)  # S-offsets hidden by default
        self.toggle_soffsets_action.triggered.connect(self.toggle_soffset_visibility)

        self.toggle_junction_debug_action = QAction("Show &Junction Debug", self)
        self.toggle_junction_debug_action.setStatusTip(
            "Show debug visualization for junction connections "
            "(endpoints, headings, paths)"
        )
        self.toggle_junction_debug_action.setCheckable(True)
        self.toggle_junction_debug_action.setChecked(False)  # Hidden by default
        self.toggle_junction_debug_action.triggered.connect(self.toggle_junction_debug_visibility)

        # Adjustment mode action
        self.toggle_adjustment_action = QAction("&Adjust Alignment", self)
        self.toggle_adjustment_action.setShortcut(QKeySequence("Ctrl+Shift+A"))
        self.toggle_adjustment_action.setStatusTip("Adjust georeferencing alignment with keyboard controls")
        self.toggle_adjustment_action.setCheckable(True)
        self.toggle_adjustment_action.setChecked(False)
        self.toggle_adjustment_action.triggered.connect(self.toggle_adjustment_mode)

        # Uncertainty overlay action (single toggle)
        self.toggle_uncertainty_action = QAction("Show &Uncertainty Overlay", self)
        self.toggle_uncertainty_action.setStatusTip("Show position uncertainty heat map")
        self.toggle_uncertainty_action.setCheckable(True)
        self.toggle_uncertainty_action.setChecked(False)
        self.toggle_uncertainty_action.triggered.connect(self.toggle_uncertainty_overlay)

        # Aerial map view action
        self.toggle_aerial_action = QAction("&Aerial Map View", self)
        self.toggle_aerial_action.setShortcut(QKeySequence("Ctrl+Shift+M"))
        self.toggle_aerial_action.setStatusTip(
            "Toggle between original image and aerial satellite imagery"
        )
        self.toggle_aerial_action.setCheckable(True)
        self.toggle_aerial_action.setChecked(False)
        self.toggle_aerial_action.setEnabled(False)  # Enabled when georef available
        self.toggle_aerial_action.triggered.connect(self.toggle_aerial_view)

        # Tools actions
        self.new_polyline_action = QAction("New &Polyline", self)
        self.new_polyline_action.setShortcut(QKeySequence("Ctrl+P"))
        self.new_polyline_action.setStatusTip("Start drawing a new polyline")
        self.new_polyline_action.setCheckable(True)
        self.new_polyline_action.triggered.connect(self.toggle_polyline_mode)

        self.group_to_road_action = QAction("Group to &Road", self)
        self.group_to_road_action.setShortcut(QKeySequence("Ctrl+G"))
        self.group_to_road_action.setStatusTip("Group selected polylines into a road")
        self.group_to_road_action.triggered.connect(self.group_to_road)

        self.add_junction_action = QAction("Add &Junction", self)
        self.add_junction_action.setShortcut(QKeySequence("Ctrl+J"))
        self.add_junction_action.setStatusTip("Add a junction/intersection")
        self.add_junction_action.setCheckable(True)
        self.add_junction_action.triggered.connect(self.add_junction)

        self.create_roundabout_action = QAction("Create &Roundabout...", self)
        self.create_roundabout_action.setShortcut(QKeySequence("Ctrl+Shift+R"))
        self.create_roundabout_action.setStatusTip("Create a roundabout with wizard")
        self.create_roundabout_action.triggered.connect(self.create_roundabout)

        self.merge_roads_action = QAction("&Merge Selected Roads", self)
        self.merge_roads_action.setStatusTip("Merge two consecutive roads into one (select two roads in sidebar)")
        self.merge_roads_action.triggered.connect(self.merge_selected_roads)

        self.add_signal_action = QAction("Add &Signal", self)
        self.add_signal_action.setShortcut(QKeySequence("Ctrl+T"))
        self.add_signal_action.setStatusTip("Add a traffic signal/sign")
        self.add_signal_action.setCheckable(True)
        self.add_signal_action.triggered.connect(self.add_signal)

        self.add_object_action = QAction("Add &Object", self)
        self.add_object_action.setShortcut(QKeySequence("Ctrl+Alt+O"))
        self.add_object_action.setStatusTip("Add a roadside object (lamppost, building, tree, etc.)")
        self.add_object_action.setCheckable(True)
        self.add_object_action.triggered.connect(self.add_object)

        self.add_parking_action = QAction("Add &Parking", self)
        self.add_parking_action.setShortcut(QKeySequence("Ctrl+Shift+P"))
        self.add_parking_action.setStatusTip("Add a parking space by clicking on the map")
        self.add_parking_action.setCheckable(True)
        self.add_parking_action.triggered.connect(self.add_parking)

        self.georef_action = QAction("&Control Points...", self)
        self.georef_action.setShortcut(QKeySequence("Ctrl+Shift+G"))
        self.georef_action.setStatusTip("Configure georeferencing control points")
        self.georef_action.triggered.connect(self.open_georeferencing)

        self.measure_action = QAction("&Measure Distance", self)
        self.measure_action.setShortcut(QKeySequence("Ctrl+M"))
        self.measure_action.setStatusTip("Measure distances between points")
        self.measure_action.setCheckable(True)
        self.measure_action.triggered.connect(self.toggle_measure_mode)

        self.show_scale_action = QAction("Show &Scale Factor", self)
        self.show_scale_action.setShortcut(QKeySequence("Ctrl+K"))
        self.show_scale_action.setStatusTip("Show scale factor at clicked points")
        self.show_scale_action.setCheckable(True)
        self.show_scale_action.triggered.connect(self.toggle_show_scale_mode)

        # Help actions
        self.about_action = QAction("&About ORBIT", self)
        self.about_action.setStatusTip("About this application")
        self.about_action.triggered.connect(self.show_about)

        self.shortcuts_action = QAction("&Keyboard Shortcuts", self)
        self.shortcuts_action.setStatusTip("Show keyboard shortcuts reference")
        self.shortcuts_action.triggered.connect(self.show_keyboard_shortcuts)

    def create_menus(self):
        """Create the menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")
        file_menu.addAction(self.new_action)
        file_menu.addAction(self.open_action)
        file_menu.addAction(self.save_action)
        file_menu.addAction(self.save_as_action)
        file_menu.addSeparator()
        file_menu.addAction(self.load_image_action)
        file_menu.addSeparator()
        # Import submenu
        import_menu = file_menu.addMenu("&Import")
        import_menu.addAction(self.import_osm_action)
        import_menu.addAction(self.import_opendrive_action)
        # Export submenu
        export_menu = file_menu.addMenu("&Export")
        export_menu.addAction(self.export_action)
        export_menu.addAction(self.export_osm_action)
        export_menu.addAction(self.export_georef_action)
        export_menu.addAction(self.export_layout_mask_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)

        # Edit menu
        edit_menu = menubar.addMenu("&Edit")
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.delete_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.junction_groups_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.preferences_action)

        # View menu
        view_menu = menubar.addMenu("&View")
        # Zoom submenu
        zoom_menu = view_menu.addMenu("&Zoom")
        zoom_menu.addAction(self.zoom_in_action)
        zoom_menu.addAction(self.zoom_out_action)
        zoom_menu.addAction(self.fit_action)
        zoom_menu.addAction(self.reset_view_action)
        view_menu.addSeparator()
        view_menu.addAction(self.toggle_lanes_action)
        view_menu.addAction(self.toggle_soffsets_action)
        view_menu.addAction(self.toggle_junction_debug_action)
        view_menu.addAction(self.toggle_uncertainty_action)
        view_menu.addSeparator()
        view_menu.addAction(self.toggle_aerial_action)

        # Draw menu (drawing/placement tools)
        draw_menu = menubar.addMenu("&Draw")
        draw_menu.addAction(self.new_polyline_action)
        draw_menu.addSeparator()
        draw_menu.addAction(self.add_signal_action)
        draw_menu.addAction(self.add_object_action)
        draw_menu.addAction(self.add_parking_action)

        # Roads menu (road-specific operations)
        roads_menu = menubar.addMenu("&Roads")
        roads_menu.addAction(self.group_to_road_action)
        roads_menu.addAction(self.add_junction_action)
        roads_menu.addAction(self.create_roundabout_action)
        roads_menu.addSeparator()
        roads_menu.addAction(self.merge_roads_action)

        # Georeferencing menu
        georef_menu = menubar.addMenu("&Georeferencing")
        georef_menu.addAction(self.georef_action)
        georef_menu.addAction(self.toggle_adjustment_action)
        georef_menu.addSeparator()
        georef_menu.addAction(self.measure_action)
        georef_menu.addAction(self.show_scale_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")
        help_menu.addAction(self.about_action)
        help_menu.addAction(self.shortcuts_action)

    def create_toolbar(self):
        """Create the main toolbar with clear visual groups."""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # File group (minimal - just Save)
        toolbar.addAction(self.save_action)
        toolbar.addSeparator()

        # Draw group - tools for adding elements
        toolbar.addAction(self.new_polyline_action)
        toolbar.addAction(self.add_signal_action)
        toolbar.addAction(self.add_object_action)
        toolbar.addAction(self.add_parking_action)
        toolbar.addSeparator()

        # Roads group - tools for road structure
        toolbar.addAction(self.add_junction_action)
        toolbar.addAction(self.group_to_road_action)
        toolbar.addSeparator()

        # View group - navigation tools
        toolbar.addAction(self.zoom_in_action)
        toolbar.addAction(self.zoom_out_action)
        toolbar.addAction(self.fit_action)

    def create_dock_widgets(self):
        """Create dock widgets for element and road management."""
        # Elements dock (polylines and junctions)
        self.elements_dock = QDockWidget("Elements", self)
        self.elements_dock.setObjectName("elementsDock")
        self.elements_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )

        self.elements_tree = ElementsTreeWidget(self.project)
        self.elements_dock.setWidget(self.elements_tree)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.elements_dock)

        # Connect elements tree signals
        self.elements_tree.junction_selected.connect(self.on_junction_selected_in_tree)
        self.elements_tree.junction_modified.connect(self.on_junction_modified)
        self.elements_tree.junction_deleted.connect(self.on_junction_deleted)
        self.elements_tree.signal_selected.connect(self.on_signal_selected_in_tree)
        self.elements_tree.signal_modified.connect(self.on_signal_modified)
        self.elements_tree.signal_deleted.connect(self.on_signal_deleted)
        self.elements_tree.object_selected.connect(self.on_object_selected_in_tree)
        self.elements_tree.object_modified.connect(self.on_object_modified_in_tree)
        self.elements_tree.object_deleted.connect(self.on_object_deleted_in_tree)
        self.elements_tree.parking_selected.connect(self.on_parking_selected_in_tree)
        self.elements_tree.parking_modified.connect(self.on_parking_modified)
        self.elements_tree.parking_deleted.connect(self.on_parking_deleted)
        self.elements_tree.connecting_road_selected.connect(self.on_connecting_road_selected)
        self.elements_tree.connecting_road_modified.connect(self.on_connecting_road_modified)
        self.elements_tree.connecting_road_lane_selected.connect(self.on_connecting_road_lane_selected)

        # Roads dock with tree widget
        self.roads_dock = QDockWidget("Roads", self)
        self.roads_dock.setObjectName("roadsDock")
        self.roads_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )

        self.road_tree = RoadTreeWidget(self.project, verbose=self.verbose)
        self.roads_dock.setWidget(self.road_tree)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.roads_dock)

        # Connect road tree signals
        self.road_tree.road_added.connect(self.on_road_added)
        self.road_tree.road_modified.connect(self.on_road_modified)
        self.road_tree.road_deleted.connect(self.on_road_deleted)
        self.road_tree.road_delete_requested.connect(self.on_road_delete_requested)
        self.road_tree.road_edit_requested.connect(self.on_road_edit_requested)
        self.road_tree.polyline_selected.connect(self.on_polyline_selected_in_tree)
        self.road_tree.polyline_deleted.connect(self.on_polyline_deleted_in_tree)
        self.road_tree.polyline_delete_requested.connect(self.on_polyline_delete_requested)
        self.road_tree.lane_selected.connect(self.on_lane_selected_in_tree)
        self.road_tree.roads_merge_requested.connect(self.on_roads_merge_requested)
        self.road_tree.section_delete_requested.connect(self.on_section_delete_requested)

        # Adjustment dock for transform adjustment
        self.adjustment_dock = QDockWidget("Alignment Adjustment", self)
        self.adjustment_dock.setObjectName("adjustmentDock")
        self.adjustment_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )

        self.adjustment_panel = AdjustmentPanel()
        self.adjustment_dock.setWidget(self.adjustment_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.adjustment_dock)
        self.adjustment_dock.setVisible(False)  # Hidden by default

        # Connect adjustment panel signals
        self.adjustment_panel.apply_requested.connect(self.apply_adjustment_to_control_points)
        self.adjustment_panel.reset_requested.connect(self.reset_adjustment)

        # Connect image view adjustment signal
        self.image_view.adjustment_changed.connect(self.on_adjustment_changed)

    # Project management
    def new_project(self):
        """Create a new project."""
        if self.check_unsaved_changes():
            self.project.clear()
            self.current_project_file = None
            self.modified = False
            self.undo_stack.clear()
            self._cached_transformer = None  # Invalidate transformer cache

            # Reset adjustment mode and panel
            self.image_view.reset_adjustment()
            self.image_view.set_adjustment_mode(False)
            self.adjustment_dock.setVisible(False)
            self.adjustment_panel.update_display(None)
            if hasattr(self, 'toggle_adjustment_action'):
                self.toggle_adjustment_action.setChecked(False)

            self.image_view.clear()
            self.update_elements_tree()
            self.road_tree.refresh_tree()
            self.update_window_title()
            self.update_scale_display()
            self.statusBar().showMessage("New project created")

    def _remember_directory(self, file_path: str) -> None:
        """Update last used directory from a file path selected by the user."""
        if file_path:
            self._last_file_directory = str(Path(file_path).parent)

    def open_project(self):
        """Open an existing project file."""
        if not self.check_unsaved_changes():
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Project",
            self._last_file_directory,
            "ORBIT Projects (*.orbit *.json);;All Files (*)"
        )

        if file_path:
            self._remember_directory(file_path)
            try:
                self.project = Project.load(Path(file_path))
                self.current_project_file = Path(file_path)
                self.modified = False
                self.undo_stack.clear()
                self._cached_transformer = None  # Invalidate transformer cache

                # Reset adjustment mode and panel
                self.image_view.reset_adjustment()
                self.image_view.set_adjustment_mode(False)
                self.adjustment_dock.setVisible(False)
                self.adjustment_panel.update_display(None)
                if hasattr(self, 'toggle_adjustment_action'):
                    self.toggle_adjustment_action.setChecked(False)

                # Load image if specified in project
                if self.project.image_path:
                    self.load_image(self.project.image_path)
                elif self.project.synthetic_canvas_width and self.project.synthetic_canvas_height:
                    self.image_view.set_synthetic_canvas(
                        self.project.synthetic_canvas_width,
                        self.project.synthetic_canvas_height
                    )

                # Calculate scale BEFORE loading project (so lanes use correct scale)
                scale_factors = self.get_current_scale()

                # Initialize missing geo coordinates and refresh pixel coords from geo
                # This ensures pixel coords match the current transformer state
                self._initialize_and_refresh_geo_coords()

                # Apply lane alignment to all junctions so CR visuals are
                # correct immediately (without requiring the user to open the
                # lane connection dialog first).
                self._align_all_junction_connecting_roads(scale_factors)

                # Update UI
                self.image_view.load_project(self.project, scale_factors)
                self.elements_tree.set_project(self.project)
                self.road_tree.set_project(self.project)
                self.update_window_title()
                self.update_scale_display()
                self.statusBar().showMessage(f"Opened project: {file_path}")

            except Exception as e:
                show_error(self, f"Failed to open project:\n{str(e)}", "Error")

    def save_project(self):
        """Save the current project."""
        if self.current_project_file:
            try:
                self.project.save(self.current_project_file)
                self.undo_stack.setClean()
                self.modified = False
                self.update_window_title()
                self.statusBar().showMessage(f"Project saved: {self.current_project_file}")
            except Exception as e:
                show_error(self, f"Failed to save project:\n{str(e)}", "Error")
        else:
            self.save_project_as()

    def save_project_as(self):
        """Save the project with a new name."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Project As",
            self._last_file_directory,
            "ORBIT Projects (*.orbit);;JSON Files (*.json);;All Files (*)"
        )

        if file_path:
            self._remember_directory(file_path)
            try:
                self.current_project_file = Path(file_path)
                self.project.save(self.current_project_file)
                self.undo_stack.setClean()
                self.modified = False
                self.update_window_title()
                self.statusBar().showMessage(f"Project saved: {file_path}")
            except Exception as e:
                show_error(self, f"Failed to save project:\n{str(e)}", "Error")

    def load_image_dialog(self):
        """Show dialog to load an image."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Image",
            self._last_file_directory,
            "Images (*.jpg *.jpeg *.png *.bmp *.tif *.tiff);;All Files (*)"
        )

        if file_path:
            self._remember_directory(file_path)
            self.load_image(Path(file_path))

    def load_image(self, image_path: Path):
        """Load an image into the view."""
        if image_path.exists():
            self.image_view.load_image(image_path)
            self.project.image_path = image_path

            # Clear synthetic canvas metadata (real image replaces synthetic canvas)
            self.project.synthetic_canvas_width = None
            self.project.synthetic_canvas_height = None

            # Set default map name from image filename if not already set
            if not self.project.map_name:
                self.project.map_name = image_path.stem  # Filename without extension

            self.modified = True
            self.update_window_title()
            self.statusBar().showMessage(f"Loaded image: {image_path}")
        else:
            show_warning(self, f"Image file not found: {image_path}", "Warning")

    def show_preferences(self):
        """Show project preferences dialog."""
        from .dialogs.preferences_dialog import PreferencesDialog

        dialog = PreferencesDialog(self.project, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.modified = True
            self.statusBar().showMessage("Preferences updated")

            # Clear cached transformer since method may have changed
            self._cached_transformer = None

            # Update scale display and lane graphics with new transformation
            self.update_scale_display()
            self.update_affected_road_lanes()

            # Update georef validation in project if we have control points
            if self.project.has_georeferencing():
                transformer = self._create_transformer(use_validation=True)
                if transformer:
                    # Update stored validation results
                    training_points = [cp for cp in self.project.control_points if not cp.is_validation]
                    validation_points = [cp for cp in self.project.control_points if cp.is_validation]
                    scale_x, scale_y = transformer.get_scale_factor()
                    self.project.georef_validation = {
                        'transform_method': self.project.transform_method,
                        'reprojection_error': transformer.reprojection_error if transformer.reprojection_error else {},
                        'validation_error': transformer.validation_error if transformer.validation_error else {},
                        'scale_factors': {'x': scale_x, 'y': scale_y},
                        'num_training_points': len(training_points),
                        'num_validation_points': len(validation_points)
                    }

    def show_junction_groups(self):
        """Show junction groups management dialog."""
        from .dialogs.junction_group_dialog import JunctionGroupDialog

        if JunctionGroupDialog.edit_groups(self.project, self):
            self.modified = True
            self.statusBar().showMessage("Junction groups updated")

    def export_to_opendrive(self):
        """Export project to OpenDrive format."""
        from .dialogs.export_dialog import ExportDialog

        # Check if we have any roads
        if not self.project.roads:
            show_warning(self, "Cannot export: No roads defined in the project.\n"
                "Please create at least one road first.", "No Roads")
            return

        # Show export dialog with optional schema path for validation
        dialog = ExportDialog(self.project, self, xodr_schema_path=self.xodr_schema_path)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.statusBar().showMessage("Export completed successfully")
        else:
            self.statusBar().showMessage("Export cancelled")

    def export_to_osm(self):
        """Export project to OpenStreetMap XML format (.osm)."""
        from pathlib import Path as _Path

        from orbit.export.osm_writer import export_to_osm

        # Check if any element has geo coordinates
        has_geo = any(
            project_polyline.has_geo_coords()
            for road in self.project.roads
            if road.centerline_id
            for project_polyline in [self.project.get_polyline(road.centerline_id)]
            if project_polyline is not None
        )
        if not has_geo:
            show_warning(
                self,
                "Cannot export to OSM: No roads with geographic coordinates found.\n"
                "Import from OSM or set control points first.",
                "No Geo Data",
            )
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export to OSM",
            self._last_file_directory,
            "OpenStreetMap Files (*.osm);;All Files (*)",
        )
        if not file_path:
            return

        self._remember_directory(file_path)

        try:
            # Create transformer for pixel→geo conversion (needed for connecting
            # roads that only have pixel coordinates, e.g. roundabout entries/exits)
            transformer = self._create_transformer(use_validation=True)

            success, message, _stats = export_to_osm(
                self.project, _Path(file_path), transformer=transformer
            )
            if success:
                show_info(self, message, "OSM Export")
                self.statusBar().showMessage("OSM export completed")
            else:
                show_warning(self, message, "OSM Export")
        except Exception as e:
            show_error(self, f"OSM export failed:\n{e}", "Export Error")

    def export_georeferencing(self):
        """Export georeferencing parameters to JSON file."""
        from orbit.export import export_georeferencing

        # Check if we have enough control points
        if len(self.project.control_points) < 3:
            show_warning(
                self,
                "Cannot export: At least 3 control points are required.\n"
                "Use Tools → Georeferencing to add control points.",
                "Insufficient Control Points"
            )
            return

        # Create transformer
        min_points = 4 if self.project.transform_method == 'homography' else 3
        training_points = [cp for cp in self.project.control_points if not cp.is_validation]

        if len(training_points) < min_points:
            show_warning(
                self,
                f"Cannot export: {self.project.transform_method} transformation requires "
                f"at least {min_points} training (non-validation) control points.\n"
                f"Current: {len(training_points)} training points.",
                "Insufficient Control Points"
            )
            return

        transformer = self._create_transformer(use_validation=True)
        if not transformer:
            show_error(self, "Failed to create coordinate transformer.\n"
                "Please check your control points.", "Transformation Error")
            return

        # Get image size
        if self.image_view.image_item:
            image_size = (
                int(self.image_view.image_item.pixmap().width()),
                int(self.image_view.image_item.pixmap().height())
            )
        else:
            show_warning(self, "No image loaded. Image size will be unknown.", "No Image")
            image_size = (0, 0)

        # Show save dialog
        from PyQt6.QtWidgets import QFileDialog
        default_name = ""
        if self.project.image_path:
            default_name = self.project.image_path.stem + "_georef.json"
        if default_name:
            default_path = str(Path(self._last_file_directory) / default_name)
        else:
            default_path = self._last_file_directory

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Georeferencing Parameters",
            default_path,
            "JSON files (*.json);;All files (*.*)"
        )

        if not file_path:
            self.statusBar().showMessage("Export cancelled")
            return
        self._remember_directory(file_path)

        # Export
        if export_georeferencing(self.project, Path(file_path), transformer, image_size, self.current_project_file):
            self.statusBar().showMessage(f"Georeferencing exported to {file_path}")
        else:
            show_error(self, "Failed to export georeferencing parameters.", "Export Error")

    def export_layout_mask(self):
        """Export lane segmentation mask and metadata JSON."""
        # Validate prerequisites
        if not self.image_view.image_item:
            show_warning(self, "Cannot export: No image loaded.", "No Image")
            return

        if not self.project.roads:
            show_warning(self, "Cannot export: No roads defined in the project.\n"
                "Please create at least one road first.", "No Roads")
            return

        # Check if georeferencing is available (for OpenDRIVE method and GeoTIFF)
        has_georef = len(self.project.control_points) >= 3

        # Show options dialog
        from PyQt6.QtWidgets import QCheckBox, QComboBox, QDialogButtonBox, QFormLayout, QGroupBox, QVBoxLayout
        dialog = QDialog(self)
        dialog.setWindowTitle("Export Layout Mask")
        layout = QVBoxLayout(dialog)

        form = QFormLayout()
        method_combo = QComboBox()
        method_combo.addItem("Pixel-space (from rendered scene)", "pixel")
        method_combo.addItem("OpenDRIVE-accurate (from export pipeline)", "opendrive")
        if not has_georef:
            # Disable OpenDRIVE method if no georef
            model = method_combo.model()
            item = model.item(1)
            item.setEnabled(False)
            item.setToolTip("Requires at least 3 control points")
        form.addRow("Method:", method_combo)

        geotiff_check = QCheckBox("Include world file for GIS")
        geotiff_check.setEnabled(has_georef)
        if not has_georef:
            geotiff_check.setToolTip("Requires georeferencing (control points)")
        form.addRow("GeoTIFF:", geotiff_check)

        layout.addLayout(form)

        # Curve fitting settings group (for OpenDRIVE method)
        fit_group = QGroupBox("Curve Fitting Settings")
        fit_layout = QFormLayout(fit_group)

        from PyQt6.QtWidgets import QDoubleSpinBox
        line_tol_spin = QDoubleSpinBox()
        line_tol_spin.setRange(0.001, 10.0)
        line_tol_spin.setValue(0.05)
        line_tol_spin.setDecimals(3)
        line_tol_spin.setSuffix(" m")
        fit_layout.addRow("Line tolerance:", line_tol_spin)

        arc_tol_spin = QDoubleSpinBox()
        arc_tol_spin.setRange(0.001, 10.0)
        arc_tol_spin.setValue(0.1)
        arc_tol_spin.setDecimals(3)
        arc_tol_spin.setSuffix(" m")
        fit_layout.addRow("Arc tolerance:", arc_tol_spin)

        preserve_check = QCheckBox("Preserve geometry")
        preserve_check.setChecked(True)
        fit_layout.addRow(preserve_check)

        fit_group.setVisible(False)
        layout.addWidget(fit_group)

        def on_method_changed(index):
            fit_group.setVisible(method_combo.currentData() == "opendrive")
        method_combo.currentIndexChanged.connect(on_method_changed)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            self.statusBar().showMessage("Export cancelled")
            return

        method = method_combo.currentData()
        geotiff = geotiff_check.isChecked()
        line_tol = line_tol_spin.value()
        arc_tol = arc_tol_spin.value()
        preserve = preserve_check.isChecked()

        # File save dialog
        default_name = ""
        if self.project.image_path:
            default_name = self.project.image_path.stem + "_layout_mask.png"
        if default_name:
            default_path = str(Path(self._last_file_directory) / default_name)
        else:
            default_path = self._last_file_directory

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Layout Mask",
            default_path,
            "PNG files (*.png);;TIFF files (*.tif *.tiff);;All files (*.*)"
        )

        if not file_path:
            self.statusBar().showMessage("Export cancelled")
            return
        self._remember_directory(file_path)

        # Run export
        self.statusBar().showMessage("Exporting layout mask...")
        try:
            success = self.image_view.export_layout_mask(
                output_path=file_path,
                method=method,
                geotiff=geotiff,
                line_tolerance=line_tol,
                arc_tolerance=arc_tol,
                preserve_geometry=preserve,
            )
            if success:
                self.statusBar().showMessage(f"Layout mask exported to {file_path}")
            else:
                show_error(self, "Failed to export layout mask.\n"
                    "Check that roads have lanes defined.", "Export Error")
        except Exception as e:
            logger.exception("Layout mask export failed")
            show_error(self, f"Export failed: {e}", "Export Error")

    def import_osm_data(self):
        """Import road network data from OpenStreetMap (API or file)."""
        # Import from the 'import' module using importlib (since 'import' is a Python keyword)
        import importlib

        from .dialogs.osm_import_dialog import OSMImportDialog
        osm_import_module = importlib.import_module('orbit.import')
        osm_parser_module = importlib.import_module('orbit.import.osm_parser')
        osm_to_orbit_module = importlib.import_module('orbit.import.osm_to_orbit')
        OSMImporter = osm_import_module.OSMImporter
        ImportOptions = osm_import_module.ImportOptions
        ImportMode = osm_import_module.ImportMode
        DetailLevel = osm_import_module.DetailLevel
        OSMParser = osm_parser_module.OSMParser
        calculate_bbox_from_image = osm_to_orbit_module.calculate_bbox_from_image
        calculate_bbox_from_center = osm_to_orbit_module.calculate_bbox_from_center
        from PyQt6.QtCore import QCoreApplication
        from PyQt6.QtWidgets import QProgressDialog

        from orbit.models.project import ControlPoint

        has_georef = len(self.project.control_points) >= 3
        has_image = self.image_view.image_item is not None

        # --- Branch: georef + image available ---
        if has_georef and has_image:
            image_width = int(self.image_view.image_item.pixmap().width())
            image_height = int(self.image_view.image_item.pixmap().height())

            transformer = self._create_transformer(use_validation=True)
            if not transformer:
                show_error(self, "Failed to create coordinate transformer.\n"
                    "Please check your control points.", "Transformation Error")
                return

            try:
                bbox = calculate_bbox_from_image(image_width, image_height, transformer)
            except Exception as e:
                show_error(self, f"Failed to calculate bounding box:\n{e}", "Error")
                return

            # Show dialog with georef mode (custom radius option available)
            dialog = OSMImportDialog(bbox, self, has_georef=True)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                self.statusBar().showMessage("OSM import cancelled")
                return

            # Check if custom radius was requested
            custom_radius = dialog.get_custom_radius()
            if custom_radius is not None:
                # Compute image center in geo coords
                center_lon, center_lat = transformer.pixel_to_geo(
                    image_width / 2.0, image_height / 2.0
                )
                bbox = calculate_bbox_from_center(center_lat, center_lon, custom_radius)

        # --- Branch: no georef or no image -> coordinate mode ---
        else:
            # Dummy bbox for dialog (will be replaced by user input)
            dialog = OSMImportDialog((0, 0, 0, 0), self, has_georef=False)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                self.statusBar().showMessage("OSM import cancelled")
                return

            coord_params = dialog.get_coordinate_params()
            if not coord_params:
                return
            center_lat, center_lon, radius_m, scale_px_per_m = coord_params

            bbox = calculate_bbox_from_center(center_lat, center_lon, radius_m)

            # Create synthetic canvas
            canvas_size = max(int(2 * radius_m * scale_px_per_m), 2000)
            image_width = canvas_size
            image_height = canvas_size
            self.image_view.set_synthetic_canvas(image_width, image_height)
            self.project.synthetic_canvas_width = image_width
            self.project.synthetic_canvas_height = image_height

            # Create synthetic control points at canvas corners mapped to bbox corners
            min_lat, min_lon, max_lat, max_lon = bbox
            self.project.control_points = [
                ControlPoint(pixel_x=0, pixel_y=0, longitude=min_lon, latitude=max_lat),
                ControlPoint(pixel_x=image_width, pixel_y=0, longitude=max_lon, latitude=max_lat),
                ControlPoint(pixel_x=image_width, pixel_y=image_height, longitude=max_lon, latitude=min_lat),
                ControlPoint(pixel_x=0, pixel_y=image_height, longitude=min_lon, latitude=min_lat),
            ]
            self.project.transform_method = 'affine'
            self._cached_transformer = None

            transformer = self._create_transformer(use_validation=False)
            if not transformer:
                show_error(self, "Failed to create coordinate transformer from synthetic control points.",
                    "Transformation Error")
                return

        # Get import source and options
        source_data = dialog.get_import_source()
        source_type = source_data[0]

        if source_type == 'api':
            # API import
            options_dict = source_data[1]
        else:
            # File import
            file_path = source_data[1]
            options_dict = source_data[2]

            # Validate file path
            if not file_path:
                show_warning(self, "Please select an OSM file to import.", "No File Selected")
                return

        # Build ImportOptions from dict
        import_mode = ImportMode.REPLACE if options_dict['import_mode'] == 'replace' else ImportMode.ADD
        detail_level = DetailLevel.FULL if options_dict['detail_level'] == 'full' else DetailLevel.MODERATE

        options = ImportOptions(
            import_mode=import_mode,
            detail_level=detail_level,
            default_lane_width=options_dict['default_lane_width'],
            import_junctions=options_dict['import_junctions'],
            filter_outside_image=options_dict.get('filter_outside_image', False),
            timeout=60,
            verbose=self.verbose
        )

        # Show progress dialog
        if source_type == 'api':
            progress_msg = "Importing OpenStreetMap data from API..."
            progress_title = "Importing OSM Data"
        else:
            progress_msg = f"Importing from {Path(file_path).name}..."
            progress_title = "Importing OSM File"

        progress = QProgressDialog(
            progress_msg,
            "Cancel",
            0, 0,  # Indeterminate progress
            self
        )
        progress.setWindowTitle(progress_title)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setCancelButton(None)  # No cancel button for now
        progress.show()
        QCoreApplication.processEvents()

        # Perform import
        try:
            importer = OSMImporter(self.project, transformer, image_width, image_height)

            if source_type == 'api':
                # Import from Overpass API (pass bbox for custom radius support)
                result = importer.import_osm_data(options, bbox=bbox)
            else:
                # Import from file
                with open(file_path, 'r', encoding='utf-8') as f:
                    xml_content = f.read()
                osm_data = OSMParser.parse_xml(xml_content)
                result = importer._import_from_osm_data(osm_data, options, bbox=bbox)

            progress.close()

            if result.success:
                # Show success message
                if source_type == 'file':
                    msg = f"Successfully imported from {Path(file_path).name}:\n\n"
                else:
                    msg = "Successfully imported:\n\n"

                msg += f"• {result.roads_imported} roads\n"
                if result.junctions_imported > 0:
                    msg += f"• {result.junctions_imported} junctions\n"
                if result.signals_imported > 0:
                    msg += f"• {result.signals_imported} signals\n"
                if result.objects_imported > 0:
                    msg += f"• {result.objects_imported} objects\n"

                if result.roads_skipped_duplicate > 0:
                    msg += f"\n• Skipped {result.roads_skipped_duplicate} duplicate roads"

                if result.partial_import:
                    msg += "\n\nWarning: Import timed out. Partial data was imported."

                show_info(self, msg, "Import Successful")

                # Mark OpenStreetMap as used for proper attribution
                self.project.openstreetmap_used = True

                # Mark project as modified
                self.modified = True

                # Refresh all views
                self.image_view.load_project(self.project)
                self.elements_tree.refresh_tree()
                self.road_tree.refresh_tree()

                # Invalidate transformer cache
                self._cached_transformer = None

                if source_type == 'file':
                    self.statusBar().showMessage(
                        f"Imported {result.roads_imported} roads, "
                        f"{result.signals_imported} signals, "
                        f"{result.objects_imported} objects from {Path(file_path).name}"
                    )
                else:
                    self.statusBar().showMessage(
                        f"Imported {result.roads_imported} roads, "
                        f"{result.signals_imported} signals, "
                        f"{result.objects_imported} objects"
                    )
            else:
                # Show error message
                show_error(self, f"Failed to import OSM data:\n\n{result.error_message}", "Import Failed")
                self.statusBar().showMessage("OSM import failed")

        except Exception as e:
            progress.close()
            show_error(self, f"An unexpected error occurred during import:\n\n{type(e).__name__}: {e}", "Import Error")
            self.statusBar().showMessage("OSM import error")

    def import_opendrive_file(self):
        """Import road network from OpenDrive file."""
        import importlib

        from .dialogs.import_report_dialog import show_opendrive_import_report
        from .dialogs.opendrive_import_dialog import OpenDriveImportDialog
        opendrive_import_module = importlib.import_module('orbit.import.opendrive_importer')
        OpenDriveImporter = opendrive_import_module.OpenDriveImporter
        ImportOptions = opendrive_import_module.ImportOptions
        ImportMode = opendrive_import_module.ImportMode
        opendrive_parser_module = importlib.import_module('orbit.import.opendrive_parser')
        OpenDriveParser = opendrive_parser_module.OpenDriveParser
        from PyQt6.QtCore import QCoreApplication
        from PyQt6.QtWidgets import QProgressDialog

        has_image = self.image_view.image_item is not None

        # Get image dimensions (if available)
        if has_image:
            image_width = int(self.image_view.image_item.pixmap().width())
            image_height = int(self.image_view.image_item.pixmap().height())
        else:
            image_width = 0
            image_height = 0

        # Create coordinate transformer if available
        transformer = None
        has_georeferencing = len(self.project.control_points) >= 3
        if has_georeferencing:
            transformer = self._create_transformer(use_validation=True)

        # Show import dialog
        dialog = OpenDriveImportDialog(has_georeferencing, self.verbose, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self.statusBar().showMessage("OpenDrive import cancelled")
            return

        # Get options from dialog
        file_path = dialog.get_file_path()
        import_mode = ImportMode.REPLACE if dialog.get_import_mode() == 'replace' else ImportMode.ADD
        force_synthetic = dialog.get_force_synthetic()
        scale = dialog.get_scale()
        auto_georeference = dialog.get_auto_georeference()
        verbose = dialog.get_verbose()

        # Override transformer if forcing synthetic mode
        if force_synthetic:
            transformer = None

        # If no image loaded, create a synthetic canvas from OpenDrive data bounds
        if not has_image:
            try:
                parser = OpenDriveParser()
                odr_data = parser.parse_file(file_path)

                # Collect geometry start points to compute data bounds
                xs, ys = [], []
                for road in odr_data.roads:
                    for geom in road.geometry:
                        xs.append(geom.x)
                        ys.append(geom.y)

                if not xs:
                    show_warning(self, "OpenDrive file contains no road geometry.", "Empty File")
                    return

                margin = 50  # pixels margin
                data_width = (max(xs) - min(xs)) * scale
                data_height = (max(ys) - min(ys)) * scale
                image_width = max(int(data_width + 2 * margin), 2000)
                image_height = max(int(data_height + 2 * margin), 2000)

                self.image_view.set_synthetic_canvas(image_width, image_height)
                self.project.synthetic_canvas_width = image_width
                self.project.synthetic_canvas_height = image_height
            except Exception as e:
                show_error(self, f"Failed to pre-parse OpenDrive file:\n{e}", "Parse Error")
                return

        # Build import options
        options = ImportOptions(
            import_mode=import_mode,
            scale_pixels_per_meter=scale,
            auto_create_control_points=auto_georeference,
            verbose=verbose
        )

        # Show progress dialog
        progress = QProgressDialog("Importing OpenDrive file...", "Cancel", 0, 0, self)
        progress.setWindowTitle("Import OpenDrive")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(500)
        progress.setValue(0)

        # Process events to show progress dialog
        QCoreApplication.processEvents()

        try:
            # Create importer
            importer = OpenDriveImporter(
                self.project,
                transformer,
                image_width,
                image_height
            )

            # Import from file
            result = importer.import_from_file(file_path, options)

            # Close progress dialog
            progress.close()

            # Show results
            show_opendrive_import_report(result, self)

            if result.success:
                # Align connecting road paths to lane centers before rendering
                scale_factors = self.get_current_scale()
                self._align_all_junction_connecting_roads(scale_factors)

                # Update UI
                self.image_view.load_project(self.project, scale_factors)
                self.road_tree.set_project(self.project)
                self.road_tree.refresh_tree()
                self.elements_tree.set_project(self.project)
                self.elements_tree.refresh_tree()

                self.modified = True
                self.update_window_title()

                msg = f"Imported {result.roads_imported} road(s), {result.junctions_imported} junction(s), " \
                      f"{result.signals_imported} signal(s), {result.objects_imported} object(s)"
                self.statusBar().showMessage(msg, 5000)
            else:
                self.statusBar().showMessage("OpenDrive import failed")

        except Exception as e:
            progress.close()
            show_error(self, f"An unexpected error occurred during import:\n\n{type(e).__name__}: {e}", "Import Error")
            self.statusBar().showMessage("OpenDrive import error")

            if verbose:
                import traceback
                traceback.print_exc()

    # Edit operations
    def delete_selected(self):
        """Delete the selected item."""
        self.image_view.delete_selected()

    # Tool operations
    def toggle_polyline_mode(self):
        """Toggle polyline drawing mode."""
        is_drawing = self.new_polyline_action.isChecked()
        self.image_view.set_drawing_mode(is_drawing)

        if is_drawing:
            self.statusBar().showMessage("Click to add points. Double-click or press Enter to finish.")
        else:
            self.statusBar().showMessage("Ready")

    def group_to_road(self):
        """Group selected polylines into a road."""
        from .dialogs.properties_dialog import RoadPropertiesDialog

        # Get selected polylines from image view
        selected_polyline_id = self.image_view.selected_polyline_id
        if not selected_polyline_id:
            show_warning(self, "Please select a polyline first before creating a road.", "No Polyline Selected")
            return

        # Pre-assign the selected polyline so the dialog's centerline combo is populated
        road = RoadPropertiesDialog.create_road(
            self.project, self, verbose=self.verbose,
            initial_polyline_ids=[selected_polyline_id],
        )
        if road:
            # Check if road has a centerline
            if not road.has_centerline():
                if not ask_yes_no(
                    self,
                    f"The road '{road.name}' has no road reference line assigned.\n\n"
                    "Every road must have exactly one road reference line for OpenDRIVE export.\n"
                    "You can:\n"
                    "• Edit the polyline properties to set it as a road reference line (double-click the line)\n"
                    "• Add more polylines to this road and select a road reference line in road properties\n\n"
                    "Do you want to create this road anyway?",
                    "No Road Reference Line Detected"
                ):
                    return

            self.project.add_road(road)
            self.modified = True
            self.road_tree.refresh_tree()
            self.update_window_title()
            self.statusBar().showMessage(f"Created road: {road.name}")

            # Add lane visualization if road has centerline
            if road.centerline_id:
                scale_factors = self.get_current_scale()
                self.image_view.add_road_lanes_graphics(road, scale_factors)

    def add_junction(self):
        """Add a junction by clicking on the map."""
        # Toggle junction mode
        if not hasattr(self, 'junction_mode_active'):
            self.junction_mode_active = False

        self.junction_mode_active = not self.junction_mode_active
        self.image_view.set_junction_mode(self.junction_mode_active)

        if self.junction_mode_active:
            self.add_junction_action.setChecked(True)
            self.statusBar().showMessage("Click on the map to place a junction")
        else:
            self.add_junction_action.setChecked(False)
            self.statusBar().showMessage("Ready")

    def create_roundabout(self):
        """Open the roundabout creation wizard."""
        from .dialogs import RoundaboutWizardDialog

        # Get available roads for approach selection
        available_roads = [
            (road.id, road.name)
            for road in self.project.roads
        ]

        # Get scale factor if georeferenced
        scale_factor = None
        if self.project.has_georeferencing():
            transformer = self._create_transformer(use_validation=True)
            if transformer:
                scale_factor = transformer.get_scale_factor()[0]  # scale_x

        dialog = RoundaboutWizardDialog(available_roads, self, scale_factor)

        # Connect pick-from-map: hide dialog, enter pick mode, route click back
        dialog.pick_center_requested.connect(self._start_roundabout_center_pick)
        dialog.pick_radius_requested.connect(self._start_roundabout_radius_pick)

        # Store reference so on_point_picked can route to it
        self.roundabout_dialog = dialog
        self._roundabout_pick_mode = None  # 'center' or 'radius'

        # Handle result when dialog is accepted/rejected
        dialog.finished.connect(self._on_roundabout_dialog_finished)

        dialog.show()

    def _start_roundabout_center_pick(self):
        """Enter point-pick mode for roundabout center."""
        self._roundabout_pick_mode = 'center'
        self.image_view.set_pick_point_mode(True)
        self.statusBar().showMessage("Click on the image to set the roundabout center point")

    def _start_roundabout_radius_pick(self):
        """Enter point-pick mode for roundabout radius."""
        self._roundabout_pick_mode = 'radius'
        self.image_view.set_pick_point_mode(True)
        self.statusBar().showMessage("Click on the inner edge of the roundabout road to set the centerline radius")

    def _on_roundabout_dialog_finished(self, result):
        """Handle roundabout wizard dialog result."""
        from orbit.roundabout_creator import create_roundabout_from_params

        from .dialogs import RoundaboutWizardDialog

        dialog = self.roundabout_dialog
        self.roundabout_dialog = None
        self._roundabout_pick_mode = None

        if result != RoundaboutWizardDialog.DialogCode.Accepted:
            return

        params = dialog.get_roundabout_params()
        if not params:
            return

        # Get approach roads and polylines
        approach_roads = {road.id: road for road in self.project.roads}
        polylines = {p.id: p for p in self.project.polylines}

        try:
            # Create roundabout
            roads, junctions, new_polylines = create_roundabout_from_params(
                self.project, params, approach_roads, polylines
            )

            # Update UI
            self.elements_tree.refresh_tree()
            self.road_tree.refresh_tree()
            self.image_view.load_project(self.project)
            self.modified = True

            self.statusBar().showMessage(
                f"Created roundabout with {len(roads)} road(s) and {len(junctions)} junction(s)"
            )

        except Exception as e:
            show_error(self, f"Failed to create roundabout:\n\n{e}", "Roundabout Creation Failed")

    def add_signal(self):
        """Add a traffic signal by clicking on the map."""
        # Toggle signal mode
        if not hasattr(self, 'signal_mode_active'):
            self.signal_mode_active = False

        self.signal_mode_active = not self.signal_mode_active
        self.image_view.set_signal_mode(self.signal_mode_active)

        if self.signal_mode_active:
            self.add_signal_action.setChecked(True)
            self.statusBar().showMessage("Click on the map to place a signal")
        else:
            self.add_signal_action.setChecked(False)
            self.statusBar().showMessage("Ready")

    def add_object(self):
        """Add a roadside object by selecting type and clicking on the map."""
        from .dialogs.object_selection_dialog import ObjectSelectionDialog

        # Check if object mode is already active - if so, toggle it off
        if hasattr(self, 'object_mode_active') and self.object_mode_active:
            self.object_mode_active = False
            self.image_view.set_object_mode(False)
            self.add_object_action.setChecked(False)
            self.statusBar().showMessage("Ready")
            return

        # Show object selection dialog
        dialog = ObjectSelectionDialog(self)
        if dialog.exec():
            object_type = dialog.get_selection()
            if object_type:
                # Activate object placement mode with the selected type
                self.object_mode_active = True
                self.object_type_to_place = object_type
                self.image_view.set_object_mode(True, object_type)
                self.add_object_action.setChecked(True)

                if object_type.get_shape_type() == "polyline":
                    self.statusBar().showMessage("Click and drag to draw guardrail. Release to finish.")
                elif object_type.get_shape_type() == "polygon":
                    self.statusBar().showMessage(
                        "Click to place polygon vertices. Double-click or Enter to finish. Esc to cancel."
                    )
                else:
                    self.statusBar().showMessage(f"Click on the map to place {object_type.value.replace('_', ' ')}")
        else:
            # Dialog cancelled, deactivate mode
            if hasattr(self, 'object_mode_active') and self.object_mode_active:
                self.object_mode_active = False
                self.image_view.set_object_mode(False)
                self.add_object_action.setChecked(False)
                self.statusBar().showMessage("Ready")

    def add_parking(self):
        """Add a parking space by selecting type and clicking on the map."""
        from .dialogs.parking_selection_dialog import ParkingSelectionDialog

        # Check if parking mode is already active - if so, toggle it off
        if hasattr(self, 'parking_mode_active') and self.parking_mode_active:
            self.parking_mode_active = False
            self.image_view.set_parking_mode(False)
            self.add_parking_action.setChecked(False)
            self.statusBar().showMessage("Ready")
            return

        # Show parking selection dialog
        dialog = ParkingSelectionDialog(self)
        if dialog.exec():
            parking_type, access_type, is_polygon_mode = dialog.get_selection()
            if parking_type:
                # Activate parking placement mode
                self.parking_mode_active = True
                self.parking_type_to_place = parking_type
                self.parking_access_to_place = access_type
                self.image_view.set_parking_mode(True, parking_type, access_type, is_polygon_mode)
                self.add_parking_action.setChecked(True)
                if is_polygon_mode:
                    self.statusBar().showMessage(
                        "Click to add polygon points. "
                        "Double-click or press Enter to finish. "
                        "Escape to cancel."
                    )
                else:
                    self.statusBar().showMessage("Click on the map to place parking space")
        else:
            # Dialog cancelled, deactivate mode
            if hasattr(self, 'parking_mode_active') and self.parking_mode_active:
                self.parking_mode_active = False
                self.image_view.set_parking_mode(False)
                self.add_parking_action.setChecked(False)
                self.statusBar().showMessage("Ready")

    def toggle_measure_mode(self):
        """Toggle measure mode."""
        is_measuring = self.measure_action.isChecked()
        self.image_view.set_measure_mode(is_measuring)

        if is_measuring:
            # Deactivate other tools
            if self.new_polyline_action.isChecked():
                self.new_polyline_action.setChecked(False)
                self.image_view.set_drawing_mode(False)
            if self.add_junction_action.isChecked():
                self.add_junction_action.setChecked(False)
                self.image_view.set_junction_mode(False)

            self.statusBar().showMessage("Measure mode: Right-click two points to measure distance. Left-click to pan.")
        else:
            self.statusBar().showMessage("Ready")

    def toggle_show_scale_mode(self):
        """Toggle show scale factor mode."""
        is_showing_scale = self.show_scale_action.isChecked()
        self.image_view.set_show_scale_mode(is_showing_scale)

        if is_showing_scale:
            # Deactivate other tools
            if self.new_polyline_action.isChecked():
                self.new_polyline_action.setChecked(False)
                self.image_view.set_drawing_mode(False)
            if self.measure_action.isChecked():
                self.measure_action.setChecked(False)
                self.image_view.set_measure_mode(False)
            if self.add_junction_action.isChecked():
                self.add_junction_action.setChecked(False)
                self.image_view.set_junction_mode(False)

            self.statusBar().showMessage(
                "Show scale mode: Right-click points to display "
                "local scale factor. Left-click to pan."
            )
        else:
            self.statusBar().showMessage("Ready")

    def open_georeferencing(self):
        """Open georeferencing dialog."""
        from .dialogs.georeference_dialog import GeoreferenceDialog

        dialog = GeoreferenceDialog(self.project, self, verbose=self.verbose)

        # Make dialog non-modal so user can interact with image
        dialog.setModal(False)

        # Connect point picking signal
        dialog.pick_point_requested.connect(self.start_point_picking)

        # Connect control points changed signal for real-time visualization updates
        dialog.control_points_changed.connect(self.on_control_points_changed)

        # Connect dialog finished signal
        dialog.finished.connect(lambda result: self.on_georef_dialog_closed(result))

        # Store dialog reference for point picking callback
        self.georef_dialog = dialog

        # Show non-modal dialog
        dialog.show()

    def on_georef_dialog_closed(self, result):
        """Handle georeferencing dialog closing."""
        if result == QDialog.DialogCode.Accepted:
            self.modified = True
            self.update_window_title()
            self.statusBar().showMessage(
                f"Georeferencing updated: {len(self.project.control_points)} control points"
            )
            # Invalidate cached transformer since control points changed
            self._cached_transformer = None
            # Update scale display with new georeferencing
            self.update_scale_display()
            # Refresh control point visualization
            self.refresh_control_points()
            # Update lane graphics with new scale
            self.update_affected_road_lanes()

        # Clean up reference
        self.georef_dialog = None

    def on_control_points_changed(self):
        """Handle control points being added/removed in georeferencing dialog."""
        # Invalidate cached transformer since control points changed
        self._cached_transformer = None
        # Refresh control point visualization
        self.refresh_control_points()
        # Update scale display
        self.update_scale_display()
        # Update lane graphics with new scale
        self.update_affected_road_lanes()

    def refresh_control_points(self):
        """Refresh control point visualization on the image."""
        # Clear existing control point graphics
        for item in self.image_view.control_point_items:
            self.image_view.scene.removeItem(item)
        self.image_view.control_point_items.clear()

        # Re-add all control points
        for cp in self.project.control_points:
            self.image_view.add_control_point_graphics(cp)

    def start_point_picking(self):
        """Start picking a point on the image for georeferencing."""
        self.image_view.set_pick_point_mode(True)
        self.statusBar().showMessage("Click on the image to select a control point location")

    def on_point_picked(self, x: float, y: float):
        """Handle point picked signal from image view."""
        # Disable pick point mode after picking
        self.image_view.set_pick_point_mode(False)

        # Route to active dialog
        if hasattr(self, 'roundabout_dialog') and self.roundabout_dialog:
            pick_mode = getattr(self, '_roundabout_pick_mode', 'center')
            if pick_mode == 'radius':
                self.roundabout_dialog.set_radius_from_point(x, y)
                self.statusBar().showMessage(f"Roundabout radius set from rim point ({x:.1f}, {y:.1f})")
            else:
                self.roundabout_dialog.set_center_point(x, y)
                self.statusBar().showMessage(f"Roundabout center set at ({x:.1f}, {y:.1f})")
            self._roundabout_pick_mode = None
        elif hasattr(self, 'georef_dialog') and self.georef_dialog:
            self.georef_dialog.set_picked_point(x, y)
            self.statusBar().showMessage(f"Point selected at ({x:.1f}, {y:.1f})")
        else:
            self.statusBar().showMessage("Ready")

    def _create_transformer(self, **kwargs):
        """Create a coordinate transformer with image dimensions for hybrid blending.

        Centralises transformer creation so that the HybridTransformer
        (homography inside the image, affine outside) is used consistently
        across all code paths — not just OSM import.
        """
        from orbit.utils.coordinate_transform import create_transformer

        image_width, image_height = 0, 0
        if self.image_view.image_item:
            image_width = int(self.image_view.image_item.pixmap().width())
            image_height = int(self.image_view.image_item.pixmap().height())
        return create_transformer(
            self.project.control_points,
            self.project.transform_method,
            image_width=image_width,
            image_height=image_height,
            **kwargs,
        )

    def on_mouse_moved(self, x: float, y: float):
        """Handle mouse movement in image view."""
        # Sentinel (-1, -1) is emitted on leaveEvent; show N/A.
        # Otherwise always display coordinates — transforms handle
        # negative pixel values (points above/left of image origin).
        if x == -1 and y == -1:
            self.mouse_pos_label.setText("Pixel: N/A")
            self.geo_coords_label.setText("Geo: N/A")
            return

        self.mouse_pos_label.setText(f"Pixel: ({x:.1f}, {y:.1f})")

        # Update geographic coordinates if georeferencing is available
        if self.project.has_georeferencing():
            try:
                # Use cached transformer for performance
                if self._cached_transformer is None:
                    self._cached_transformer = self._create_transformer(
                        use_validation=True,
                    )

                if self._cached_transformer:
                    lon, lat = self._cached_transformer.pixel_to_geo(x, y)
                    # Format with 6 decimal places for good precision (~0.1m)
                    self.geo_coords_label.setText(f"Geo: {lat:.6f}°, {lon:.6f}°")
                else:
                    self.geo_coords_label.setText("Geo: N/A (transform error)")
            except Exception:
                self.geo_coords_label.setText("Geo: N/A (error)")
        else:
            self.geo_coords_label.setText("Geo: N/A (no georef)")

    def update_scale_display(self):
        """Update the scale display based on georeferencing."""
        has_georef = self.project.has_georeferencing() and len(self.project.control_points) >= 2
        if hasattr(self, 'toggle_aerial_action'):
            self.toggle_aerial_action.setEnabled(has_georef and not self._aerial_view_active)

        if not has_georef:
            self.scale_label.setText("Scale: N/A (no georef)")
            return

        # Calculate average scale from control points
        try:
            if self.verbose:
                logger.debug("="*60)
                logger.debug("SCALE CALCULATION DEBUG")
                logger.debug("="*60)
                logger.debug(f"Number of control points: {len(self.project.control_points)}")
                logger.debug(f"Transform method: {self.project.transform_method}")
                logger.debug("Control Points:")
                for i, cp in enumerate(self.project.control_points):
                    logger.debug(f"  CP{i+1}: Pixel=({cp.pixel_x:.2f}, {cp.pixel_y:.2f}) -> "
                          f"Geo=(Lon={cp.longitude:.6f}, Lat={cp.latitude:.6f}) "
                          f"Type={'GVP' if cp.is_validation else 'GCP'}")

            transformer = self._create_transformer(use_validation=True)

            if transformer is None:
                self.scale_label.setText("Scale: N/A (transform failed)")
                if self.verbose:
                    logger.error("Transformer creation failed!")
                return

            # Get scale factors directly from the transformer
            avg_scale_x, avg_scale_y = transformer.get_scale_factor()

            if self.verbose:
                logger.debug("Scale factors from transformation:")
                logger.debug(f"  X (horizontal): {avg_scale_x:.6f} m/px = {avg_scale_x*100:.4f} cm/px")
                logger.debug(f"  Y (vertical):   {avg_scale_y:.6f} m/px = {avg_scale_y*100:.4f} cm/px")

                # Compute and display reprojection error
                reproj_error = transformer.compute_reprojection_error()
                if reproj_error:
                    logger.debug(
                        f"  Reprojection RMSE: "
                        f"{reproj_error['rmse_meters']:.3f} meters "
                        f"({reproj_error['rmse_pixels']:.2f} pixels)"
                    )

                # Compute and display validation error if validation points exist
                val_error = transformer.compute_validation_error()
                if val_error:
                    logger.debug(
                        f"  Validation RMSE: "
                        f"{val_error['rmse_meters']:.3f} meters "
                        f"({val_error['rmse_pixels']:.2f} pixels)"
                    )

                logger.debug("="*60)

            # Format scale nicely - show both X and Y
            def format_scale(scale):
                if scale < 0.01:
                    return f"{scale*1000:.2f} mm/px"
                elif scale < 1.0:
                    return f"{scale*100:.2f} cm/px"
                else:
                    return f"{scale:.3f} m/px"

            scale_x_str = format_scale(avg_scale_x)
            scale_y_str = format_scale(avg_scale_y)
            self.scale_label.setText(f"Scale: {scale_x_str} (H) × {scale_y_str} (V)")

        except Exception as e:
            # Show actual error for debugging
            logger.exception(f"Scale calculation error: {e}")
            self.scale_label.setText(f"Scale: Error ({str(e)[:20]})")

    # UI updates
    def update_elements_tree(self):
        """Update the elements tree widget."""
        self.elements_tree.refresh_tree()

    def update_window_title(self):
        """Update the window title based on project state."""
        title = "ORBIT"
        if self.current_project_file:
            title += f" - {self.current_project_file.name}"
        else:
            title += " - Untitled"
        if self.modified:
            title += " *"
        self.setWindowTitle(title)

    def _on_undo_clean_changed(self, clean: bool):
        """Sync modified flag with undo stack clean state."""
        self.modified = not clean
        self.update_window_title()

    def _refresh_trees(self):
        """Refresh both tree widgets."""
        self.update_elements_tree()
        self.road_tree.refresh_tree()

    # Signal handlers
    def on_polyline_added(self, polyline):
        """Handle polyline added signal."""
        from .undo_commands import AddPolylineCommand

        # If transformer is available, convert pixel coords to geo coords
        # This ensures manually drawn polylines can be adjusted like imported ones
        if self._cached_transformer and not polyline.has_geo_coords():
            geo_points = []
            for px, py in polyline.points:
                lon, lat = self._cached_transformer.pixel_to_geo(px, py)
                geo_points.append((lon, lat))
            polyline.geo_points = geo_points

        # Add to project
        self.project.add_polyline(polyline)

        # Push undo command (first redo is skipped since we just added it)
        cmd = AddPolylineCommand(self, polyline)
        self.undo_stack.push(cmd)

        # Update UI
        self._refresh_trees()

    def on_polyline_modified(self, polyline_id=None):
        """Handle polyline modified signal.

        Per-point geo_points updates (insert, delete, move) are handled at the
        individual modification sites in ImageView. This handler only calculates
        geo_points for polylines that don't have them yet (e.g., newly drawn).
        """
        if polyline_id and self._cached_transformer:
            polyline = self.project.get_polyline(polyline_id)
            if polyline and not polyline.has_geo_coords():
                # Only calculate geo_points for polylines that don't have them
                geo_points = []
                for px, py in polyline.points:
                    lon, lat = self._cached_transformer.pixel_to_geo(px, py)
                    geo_points.append((lon, lat))
                polyline.geo_points = geo_points

        self.modified = True
        self.update_elements_tree()
        self.road_tree.refresh_tree()  # Also refresh road tree to update point counts
        self.update_window_title()

        # Update lane graphics for any roads whose centerline was modified
        self.update_affected_road_lanes()

        # Regenerate connecting roads if a road centerline endpoint was modified
        if polyline_id:
            self.regenerate_affected_connecting_roads(polyline_id)

    def on_polyline_deleted(self, polyline_id):
        """Handle polyline deleted signal."""
        from .undo_commands import DeletePolylineCommand

        # Create command BEFORE deletion (captures state including road associations)
        cmd = DeletePolylineCommand(self, polyline_id)

        # Remove from project
        self.project.remove_polyline(polyline_id)

        # Push command (first redo skipped since we just deleted it)
        self.undo_stack.push(cmd)

        # Update UI
        self._refresh_trees()

    def on_polyline_modified_for_undo(self, polyline_id, old_points, new_points, old_geo, new_geo):
        """Handle polyline modification with state for undo."""
        from .undo_commands import ModifyPolylineCommand

        # Infer operation type from point counts
        old_count = len(old_points)
        new_count = len(new_points)
        if new_count > old_count:
            description = "Add Point"
        elif new_count < old_count:
            description = "Delete Point"
        else:
            description = "Move Point"

        cmd = ModifyPolylineCommand(
            self, polyline_id,
            old_points, new_points,
            old_geo, new_geo,
            description
        )
        self.undo_stack.push(cmd)

    def edit_polyline_properties(self, polyline_id: str):
        """Edit properties of a polyline."""
        from .dialogs.polyline_properties_dialog import PolylinePropertiesDialog
        from .undo_commands import ModifyPolylinePropertiesCommand

        polyline = self.project.get_polyline(polyline_id)
        if not polyline:
            return

        # Capture state before editing
        old_data = polyline.to_dict()

        if PolylinePropertiesDialog.edit_polyline(polyline, self):
            # Capture state after editing
            new_data = polyline.to_dict()

            # Push undo command
            cmd = ModifyPolylinePropertiesCommand(self, polyline_id, old_data, new_data)
            self.undo_stack.push(cmd)

            # Properties were modified, update the view
            self.image_view.update_polyline(polyline_id)
            self.statusBar().showMessage("Polyline properties updated")

            # Update lane graphics in case this polyline is/was a centerline
            self.update_affected_road_lanes()

    def on_road_added(self, road):
        """Handle road added signal."""
        from .undo_commands import AddRoadCommand

        # Push undo command
        cmd = AddRoadCommand(self, road)
        self.undo_stack.push(cmd)

        self.statusBar().showMessage(f"Added road: {road.name}")

    def on_road_modified(self, road_id):
        """Handle road modified signal."""
        self.modified = True
        self.update_window_title()
        # Update lane visualization with current scale
        scale_factors = self.get_current_scale()
        self.image_view.update_road_lanes(road_id, scale_factors)

    def on_road_delete_requested(self, road_id):
        """Handle road delete request with undo support.

        Deletes the road and all its assigned polylines.
        """
        from .undo_commands import DeleteRoadCommand

        road = self.project.get_road(road_id)
        if not road:
            return

        # Create command BEFORE deletion (captures road + polyline state)
        cmd = DeleteRoadCommand(self, road_id)

        # Remove lane graphics
        self.image_view.remove_road_lanes(road_id)

        # Remove connecting road graphics that will be orphaned
        for junction in self.project.junctions:
            for cr_id in junction.connecting_road_ids:
                cr = self.project.get_road(cr_id)
                if cr and (cr.predecessor_id == road_id or cr.successor_id == road_id):
                    self.image_view.remove_connecting_road_graphics(cr.id)

        # Remove assigned polylines and their graphics
        for polyline_id in list(road.polyline_ids):
            self.image_view.remove_polyline_graphics(polyline_id)
            self.project.remove_polyline(polyline_id)

        # Remove road from project
        self.project.remove_road(road_id)

        # Push command (first redo skipped)
        self.undo_stack.push(cmd)

        # Update UI
        self._refresh_trees()
        self.statusBar().showMessage("Road deleted")

    def on_road_deleted(self, road_id):
        """Handle road deleted signal (legacy, for non-undo deletions)."""
        self.modified = True
        self.update_window_title()
        # Remove lane visualization
        self.image_view.remove_road_lanes(road_id)

    def on_road_edit_requested(self, road_id):
        """Handle road edit request with undo support."""
        from .dialogs.properties_dialog import RoadPropertiesDialog
        from .undo_commands import ModifyRoadCommand

        road = self.project.get_road(road_id)
        if not road:
            return

        # Capture state before editing
        old_data = road.to_dict()

        result = RoadPropertiesDialog.edit_road(road, self.project, self, verbose=self.verbose)
        if result:
            # Capture state after editing
            new_data = road.to_dict()

            # Push undo command
            cmd = ModifyRoadCommand(self, road_id, old_data, new_data, "Edit Road Properties")
            self.undo_stack.push(cmd)

            # Update lane visualization with current scale
            scale_factors = self.get_current_scale()
            self.image_view.update_road_lanes(road_id, scale_factors)

            self._refresh_trees()
            self.statusBar().showMessage("Road properties updated")

    def on_road_link_requested(self, road_a_id: str, road_b_id: str,
                               a_contact: str, b_contact: str):
        """Handle road link request from snap-connect in image view."""
        from .undo_commands import LinkRoadsCommand

        road_a = self.project.get_road(road_a_id)
        road_b = self.project.get_road(road_b_id)
        if not road_a or not road_b:
            return

        cmd = LinkRoadsCommand(self, road_a_id, road_b_id, a_contact, b_contact)
        self.undo_stack.push(cmd)

        # Apply the link (first redo is skipped by the command)
        if a_contact == "end":
            road_a.successor_id = road_b.id
            road_a.successor_contact = b_contact
        else:
            road_a.predecessor_id = road_b.id
            road_a.predecessor_contact = b_contact

        if b_contact == "start":
            road_b.predecessor_id = road_a.id
            road_b.predecessor_contact = a_contact
        else:
            road_b.successor_id = road_a.id
            road_b.successor_contact = a_contact

        # Snap coordinates
        self.project.enforce_road_link_coordinates(road_a_id)

        # Refresh graphics for both roads
        for road in (road_a, road_b):
            if road.centerline_id and road.centerline_id in self.image_view.polyline_items:
                self.image_view.polyline_items[road.centerline_id].update_graphics()
            if road.id in self.image_view.road_lanes_items:
                cl = self.project.get_polyline(road.centerline_id)
                if cl:
                    road.update_section_boundaries(cl.points)
                self.image_view.road_lanes_items[road.id].update_graphics()

        self._refresh_trees()
        road_b_name = road_b.name or f"Road {road_b.id}"
        self.statusBar().showMessage(f"Connected to '{road_b_name}'")

    def on_road_unlink_requested(self, road_id: str, linked_road_id: str):
        """Handle road unlink request from context menu."""
        from .undo_commands import UnlinkRoadsCommand

        road = self.project.get_road(road_id)
        linked = self.project.get_road(linked_road_id)
        if not road or not linked:
            return

        cmd = UnlinkRoadsCommand(self, road_id, linked_road_id)
        self.undo_stack.push(cmd)

        # Apply the unlink (first redo is skipped by the command)
        if road.predecessor_id == linked_road_id:
            road.predecessor_id = None
        if road.successor_id == linked_road_id:
            road.successor_id = None
        if linked.predecessor_id == road_id:
            linked.predecessor_id = None
        if linked.successor_id == road_id:
            linked.successor_id = None

        self._refresh_trees()
        linked_name = linked.name or f"Road {linked.id}"
        self.statusBar().showMessage(f"Disconnected from '{linked_name}'")

    def toggle_lane_visibility(self):
        """Toggle visibility of lane graphics."""
        visible = self.toggle_lanes_action.isChecked()
        self.image_view.set_lanes_visible(visible)
        status = "shown" if visible else "hidden"
        self.statusBar().showMessage(f"Lane visualization {status}")

    def toggle_soffset_visibility(self):
        """Toggle visibility of s-offset labels."""
        visible = self.toggle_soffsets_action.isChecked()
        self.image_view.set_soffsets_visible(visible)
        status = "shown" if visible else "hidden"
        self.statusBar().showMessage(f"S-offset labels {status}")

    def toggle_junction_debug_visibility(self):
        """Toggle visibility of junction debug graphics."""
        visible = self.toggle_junction_debug_action.isChecked()
        self.image_view.set_junction_debug_visible(visible)
        status = "shown" if visible else "hidden"
        self.statusBar().showMessage(f"Junction debug visualization {status}")

    def toggle_adjustment_mode(self):
        """Toggle alignment adjustment mode for fine-tuning georeferencing."""
        enabled = self.toggle_adjustment_action.isChecked()

        if enabled:
            # Check if georeferencing exists
            if not self.project.control_points or len(self.project.control_points) < 3:
                show_warning(
                    self,
                    "Add at least 3 control points before adjusting alignment.",
                    "No Georeferencing"
                )
                self.toggle_adjustment_action.setChecked(False)
                return

            # Check if image is loaded
            if not self.image_view.image_item:
                show_warning(self, "Load an image first.", "No Image")
                self.toggle_adjustment_action.setChecked(False)
                return

            # Get image center as pivot point
            rect = self.image_view.image_item.boundingRect()
            pivot_x = rect.width() / 2
            pivot_y = rect.height() / 2

            # Enable adjustment mode
            self.image_view.set_adjustment_mode(True, pivot_x, pivot_y)
            self.adjustment_dock.setVisible(True)
            self.adjustment_panel.set_enabled(True)
            self.statusBar().showMessage(
                "Adjustment mode ON - Use arrow keys to move, [ ] to rotate, +/- to scale"
            )
        else:
            # Disable adjustment mode
            self.image_view.set_adjustment_mode(False)
            self.adjustment_dock.setVisible(False)
            self.statusBar().showMessage("Adjustment mode OFF")

    def on_adjustment_changed(self, adjustment: TransformAdjustment):
        """Handle adjustment changes from ImageView."""
        # Update the panel display
        self.adjustment_panel.update_display(adjustment)

        # Apply adjustment to transformer and update all geometry from geo coords
        if self._cached_transformer is not None:
            self._cached_transformer.set_adjustment(adjustment)
            # Update all graphics by recomputing pixel positions from geo coords
            self.image_view.update_all_from_geo_coords(self._cached_transformer)

    def reset_adjustment(self):
        """Reset all adjustment values."""
        self.image_view.reset_adjustment()
        if self._cached_transformer is not None:
            self._cached_transformer.clear_adjustment()
            self.refresh_imported_geometry()
        self.statusBar().showMessage("Adjustment reset")

    def apply_adjustment_to_control_points(self):
        """
        Apply current adjustment to control points.

        This "bakes" the adjustment into the control point positions,
        then recomputes the transformation with the new positions.
        """
        adjustment = self.image_view.get_adjustment()
        if adjustment is None or adjustment.is_identity():
            self.statusBar().showMessage("No adjustment to apply")
            return

        if not self.project.control_points:
            self.statusBar().showMessage("No control points to adjust")
            return

        # Confirm with user
        if not ask_yes_no(
            self,
            "This will modify the pixel positions of all control points "
            "to incorporate the current adjustment.\n\n"
            "The transformation will be recomputed with the new positions.\n\n"
            "Continue?",
            "Apply Adjustment"
        ):
            return

        # Apply adjustment to each control point
        for cp in self.project.control_points:
            new_x, new_y = adjustment.apply_to_point(cp.pixel_x, cp.pixel_y)
            cp.pixel_x = new_x
            cp.pixel_y = new_y

        # Clear the adjustment
        self.image_view.reset_adjustment()

        # Invalidate and rebuild transformer
        self._cached_transformer = None
        self._cached_transformer = self._create_transformer(use_validation=True)

        # Refresh geometry with new transformation
        self.refresh_imported_geometry()

        # Mark project as modified
        self.modified = True
        self.update_window_title()

        self.statusBar().showMessage("Adjustment applied to control points")

    def refresh_imported_geometry(self):
        """
        Refresh all imported geometry after adjustment change.

        Re-positions any geometry that was placed using geo→pixel conversion.
        This method recomputes pixel positions from stored geo coordinates
        using the current transformer.
        """
        if self._cached_transformer is not None:
            # Update all geometry from geo coordinates
            self.image_view.update_all_from_geo_coords(self._cached_transformer)

        # Refresh control points visualization (if shown)
        self.update_scale_display()

    def toggle_uncertainty_overlay(self, checked: bool):
        """Toggle uncertainty overlay on/off."""
        if checked:
            self.set_uncertainty_overlay('position')
        else:
            self.set_uncertainty_overlay(None)

    def set_uncertainty_overlay(self, mode: str):
        """
        Show/hide uncertainty overlay.

        Args:
            mode: 'position' to show position uncertainty, None to hide
        """
        if mode is None:
            # Hide overlay
            self.image_view.set_uncertainty_overlay(None)
            self.statusBar().showMessage("Uncertainty overlay hidden")
            return

        # Validate georeferencing
        if not self.project.control_points or len(self.project.control_points) < 3:
            show_warning(self, "Add at least 3 control points first to show uncertainty overlay.", "No Georeferencing")
            self.toggle_uncertainty_action.setChecked(False)
            return

        # Check if image is loaded
        if not self.image_view.image_item:
            show_warning(self, "Load an image first to show uncertainty overlay.", "No Image")
            self.toggle_uncertainty_action.setChecked(False)
            return

        try:
            from orbit.utils.uncertainty_estimator import UncertaintyEstimator

            from .graphics.uncertainty_overlay import UncertaintyOverlay

            # Create transformer
            transformer = self._create_transformer(use_validation=True)

            if not transformer:
                show_warning(self, "Failed to create coordinate transformer.", "Transform Error")
                self.toggle_uncertainty_action.setChecked(False)
                return

            # Create estimator
            pixmap = self.image_view.image_item.pixmap()
            estimator = UncertaintyEstimator(transformer,
                                             pixmap.width(),
                                             pixmap.height(),
                                             baseline_uncertainty=self.project.baseline_uncertainty_m)

            # Load cached grid if available, otherwise warn user
            if self.project.uncertainty_grid_cache:
                import numpy as np
                estimator._cached_grid = np.array(self.project.uncertainty_grid_cache)
            else:
                # No cache - overlay will use fallback heuristic
                if not ask_yes_no(
                    self,
                    "Monte Carlo uncertainty has not been computed yet.\n\n"
                    "The overlay will use a simple heuristic (less accurate).\n\n"
                    "To get accurate uncertainty estimates:\n"
                    "1. Open Georeferencing dialog\n"
                    "2. Click 'Compute Uncertainty (Monte Carlo)'\n\n"
                    "Continue with simple heuristic?",
                    "No Uncertainty Cache"
                ):
                    self.toggle_uncertainty_action.setChecked(False)
                    return

            # Show status message while generating overlay
            self.statusBar().showMessage("Generating uncertainty overlay...")
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()  # Allow UI to update

            # Create and show overlay
            overlay = UncertaintyOverlay(estimator, show_suggestions=True,
                                        suggestion_threshold=self.project.gcp_suggestion_threshold)
            self.image_view.set_uncertainty_overlay(overlay)

            # Get statistics for status bar
            stats = estimator.get_uncertainty_statistics()
            self.statusBar().showMessage(
                f"Uncertainty overlay active | Mean: {stats['mean']:.2f}m | Max: {stats['max']:.2f}m"
            )

        except Exception as e:
            show_error(self, f"Failed to create uncertainty overlay: {str(e)}", "Error")
            self.toggle_uncertainty_action.setChecked(False)

    # ── Aerial Map View ──────────────────────────────────────────────

    def toggle_aerial_view(self, checked: bool):
        """Toggle between original image and aerial satellite imagery."""
        if checked:
            self._switch_to_aerial()
        else:
            self._switch_to_original()

    def _get_project_geo_bbox(self):
        """Return (min_lon, min_lat, max_lon, max_lat) from control points."""
        cps = self.project.control_points
        if not cps:
            return None
        lons = [cp.longitude for cp in cps]
        lats = [cp.latitude for cp in cps]
        return (min(lons), min(lats), max(lons), max(lats))

    def _switch_to_aerial(self):
        """Fetch aerial tiles and switch to aerial view."""
        from orbit.utils.coordinate_transform import create_transformer_from_bounds
        from orbit.utils.reproject import reproject_project_geometry
        from orbit.utils.tile_fetcher import fetch_aerial_image

        bbox = self._get_project_geo_bbox()
        if bbox is None:
            show_warning(self, "No control points — cannot determine geographic extent.")
            self.toggle_aerial_action.setChecked(False)
            return

        # Save original state
        self._original_transformer = self._create_transformer(use_validation=True)
        if self._original_transformer is None:
            show_warning(self, "Cannot create coordinate transformer.")
            self.toggle_aerial_action.setChecked(False)
            return
        self._original_image_np = self.image_view.image_np.copy() if self.image_view.image_np is not None else None

        # Determine cache directory (alongside project file, or temp)
        cache_dir = None
        if self.current_project_file:
            cache_dir = self.current_project_file.parent / "tiles" / "esri"
        else:
            import tempfile
            cache_dir = Path(tempfile.gettempdir()) / "orbit_tiles" / "esri"

        try:
            self.statusBar().showMessage("Fetching aerial imagery...")
            QApplication.processEvents()

            result = fetch_aerial_image(
                bbox[1], bbox[0], bbox[3], bbox[2],
                zoom=self._aerial_zoom,
                cache_dir=cache_dir,
            )
        except Exception as e:
            show_error(self, f"Failed to fetch aerial imagery:\n{e}", "Error")
            self.toggle_aerial_action.setChecked(False)
            self._original_image_np = None
            self._original_transformer = None
            return

        # Build initial affine transformer from raw tile image bounds
        h, w = result.image.shape[:2]
        min_lon, min_lat, max_lon, max_lat = result.geo_bbox
        aerial_transformer_raw = create_transformer_from_bounds(
            w, h, min_lon, min_lat, max_lon, max_lat,
        )
        if aerial_transformer_raw is None:
            show_error(self, "Failed to build transformer for aerial image.", "Error")
            self.toggle_aerial_action.setChecked(False)
            self._original_image_np = None
            self._original_transformer = None
            return

        # Resize aerial image so its pixels/meter matches the original image.
        # This keeps fixed-size scene elements (dots, labels, arrows) proportional.
        import cv2 as _cv2
        orig_scale_x, orig_scale_y = self._original_transformer.get_scale_factor()
        aerial_scale_x, aerial_scale_y = aerial_transformer_raw.get_scale_factor()
        aerial_image = result.image
        if orig_scale_x > 0 and aerial_scale_x > 0:
            resize_ratio = aerial_scale_x / orig_scale_x  # > 1 → upscale; < 1 → downscale
            if abs(resize_ratio - 1.0) > 0.01:  # only resize if meaningfully different
                new_w = max(1, round(w * resize_ratio))
                new_h = max(1, round(h * resize_ratio))
                interp = _cv2.INTER_AREA if resize_ratio < 1.0 else _cv2.INTER_LINEAR
                aerial_image = _cv2.resize(aerial_image, (new_w, new_h), interpolation=interp)
                # Rebuild transformer for the resized dimensions (same geo bbox)
        self._aerial_transformer = create_transformer_from_bounds(
            aerial_image.shape[1], aerial_image.shape[0],
            min_lon, min_lat, max_lon, max_lat,
        )
        if self._aerial_transformer is None:
            show_error(self, "Failed to build transformer for aerial image.", "Error")
            self.toggle_aerial_action.setChecked(False)
            self._original_image_np = None
            self._original_transformer = None
            return

        # Re-project all geometry into the aerial pixel space
        count = reproject_project_geometry(
            self.project, self._original_transformer, self._aerial_transformer,
        )

        # Swap background and refresh display
        self.image_view.swap_background(aerial_image)
        self._cached_transformer = self._aerial_transformer
        self._aerial_view_active = True

        # Refresh all scene items from updated pixel coords
        scale_factors = self._aerial_transformer.get_scale_factor()
        self.image_view.load_project(self.project, scale_factors)
        self.image_view.fit_to_window()

        self.toggle_aerial_action.setText("&Original Image View")
        self.statusBar().showMessage(
            f"Aerial view: {result.tile_count} tiles at zoom {result.zoom}, "
            f"{count} entities re-projected"
        )

    def _switch_to_original(self):
        """Switch back to the original drone/source image."""
        from orbit.utils.reproject import reproject_project_geometry

        if self._original_image_np is None or self._original_transformer is None:
            self._aerial_view_active = False
            self.toggle_aerial_action.setText("&Aerial Map View")
            return

        # Re-project geometry back to original pixel space
        reproject_project_geometry(
            self.project, self._aerial_transformer, self._original_transformer,
        )

        # Restore background
        self.image_view.swap_background(self._original_image_np)
        self._cached_transformer = self._original_transformer
        self._aerial_view_active = False

        # Refresh scene
        scale_factors = self._original_transformer.get_scale_factor()
        self.image_view.load_project(self.project, scale_factors)
        self.image_view.fit_to_window()

        # Cleanup
        self._original_image_np = None
        self._original_transformer = None
        self._aerial_transformer = None

        self.toggle_aerial_action.setText("&Aerial Map View")
        self.toggle_aerial_action.setEnabled(True)
        self.statusBar().showMessage("Restored original image view")

    def get_current_scale(self):
        """
        Get current scale from georeferencing.

        Returns:
            Tuple of (scale_x, scale_y) in m/px, or None if no georeferencing
        """
        if not self.project.has_georeferencing():
            return None

        try:
            transformer = self._create_transformer(use_validation=True)
            if transformer:
                return transformer.get_scale_factor()
        except Exception:
            pass

        return None

    def _initialize_and_refresh_geo_coords(self):
        """
        Refresh pixel coordinates from geo coordinates for all georeferenced elements.

        This is needed when loading a project because saved pixel coords may be from
        a different transformer state (e.g., before adjustment was applied).
        Geographic coordinates are the source of truth; pixel coords are derived.

        For legacy projects with connecting roads that lack geo_path, initializes
        geo_path from pixel path for backward compatibility.

        Includes bounds validation: if the transformer produces pixel coordinates
        far outside the image (e.g., due to homography extrapolation beyond the
        control point region), the original saved coordinates are preserved.
        """
        if not self.project.has_georeferencing():
            return

        # Get or create transformer
        try:
            transformer = self._create_transformer(use_validation=True)
            if not transformer:
                return
        except Exception:
            return

        # Determine image bounds for validation (allow 3x margin)
        image_w, image_h = 3840, 2160  # defaults
        if self.image_view.image_item:
            pixmap = self.image_view.image_item.pixmap()
            image_w = pixmap.width()
            image_h = pixmap.height()
        max_extent = max(image_w, image_h) * 3

        def _points_in_bounds(points):
            """Check if all pixel points are within reasonable distance of the image."""
            for x, y in points:
                if abs(x) > max_extent or abs(y) > max_extent:
                    return False
            return True

        # Initialize geo_path for connecting roads that don't have it (legacy support)
        for junction in self.project.junctions:
            for cr_id in junction.connecting_road_ids:
                conn_road = self.project.get_road(cr_id)
                if conn_road and conn_road.inline_path and not conn_road.has_geo_coords():
                    conn_road.initialize_geo_path_from_pixels(transformer)

        # Refresh pixel coordinates from geo coordinates for ALL elements,
        # but revert if the transformer produces out-of-bounds results
        skipped = 0
        for polyline in self.project.polylines:
            if polyline.has_geo_coords():
                saved_points = list(polyline.points)
                polyline.update_pixel_points_from_geo(transformer)
                if not _points_in_bounds(polyline.points):
                    polyline.points = saved_points
                    skipped += 1

        for junction in self.project.junctions:
            if junction.has_geo_coords():
                junction.update_pixel_coords_from_geo(transformer)
            for cr_id in junction.connecting_road_ids:
                conn_road = self.project.get_road(cr_id)
                if conn_road and conn_road.has_geo_coords():
                    saved_path = list(conn_road.inline_path)
                    conn_road.update_pixel_path_from_geo(transformer)
                    if not _points_in_bounds(conn_road.inline_path):
                        conn_road.inline_path = saved_path
                        skipped += 1

        for signal in self.project.signals:
            if signal.has_geo_coords():
                signal.update_pixel_position_from_geo(transformer)

        for obj in self.project.objects:
            if obj.has_geo_coords():
                obj.update_pixel_coords_from_geo(transformer)

        if skipped > 0:
            logger.warning(
                f"Skipped pixel coordinate refresh for {skipped} elements "
                f"(geo coordinates outside control point coverage area)"
            )

        # Snap connecting road endpoints to match road endpoints exactly
        # This prevents gaps due to transformer precision issues
        self._snap_connecting_road_endpoints()

    def _snap_connecting_road_endpoints(self):
        """
        Snap connecting road pixel endpoints to match road endpoints exactly.

        When converting geo coordinates to pixel coordinates, small precision
        differences can cause gaps between connecting roads and their connected
        roads. This method ensures the first and last points of each connecting
        road path exactly match the stored pixel coordinates of the connected
        road endpoints.
        """
        for junction in self.project.junctions:
            for cr_id in junction.connecting_road_ids:
                conn_road = self.project.get_road(cr_id)
                if not conn_road or not conn_road.inline_path or len(conn_road.inline_path) < 2:
                    continue

                # Get predecessor and successor roads
                pred_road = self.project.get_road(conn_road.predecessor_id)
                succ_road = self.project.get_road(conn_road.successor_id)

                if not pred_road or not succ_road:
                    continue

                # Get centerline polylines
                pred_polyline = self.project.get_polyline(pred_road.centerline_id)
                succ_polyline = self.project.get_polyline(succ_road.centerline_id)

                if not pred_polyline or not succ_polyline:
                    continue

                # Snap start point to predecessor road endpoint
                if conn_road.predecessor_contact == 'end':
                    conn_road.inline_path[0] = pred_polyline.points[-1]
                else:  # 'start'
                    conn_road.inline_path[0] = pred_polyline.points[0]

                # Snap end point to successor road endpoint
                if conn_road.successor_contact == 'end':
                    conn_road.inline_path[-1] = succ_polyline.points[-1]
                else:  # 'start'
                    conn_road.inline_path[-1] = succ_polyline.points[0]

    def update_affected_road_lanes(self):
        """Update lane graphics for all roads with centerlines."""
        # Get current scale factors if available
        scale_factors = self.get_current_scale()

        # Check all roads and update lanes for those with centerlines
        for road in self.project.roads:
            if road.centerline_id:
                self.image_view.update_road_lanes(road.id, scale_factors)

    def _refresh_connecting_road_geo_path(self, conn_road):
        """Regenerate a connecting road's geo_path from its current pixel path.

        Called after the pixel path has been updated (e.g. road move) so that
        geo_path stays in sync. If the project has no georeferencing or the
        CR had no geo_path, this is a no-op.
        """
        if not conn_road.inline_geo_path:
            return
        if not self.project.has_georeferencing():
            return
        try:
            transformer = self._create_transformer()
            if transformer and conn_road.inline_path:
                conn_road.inline_geo_path = [
                    transformer.pixel_to_geo(x, y) for x, y in conn_road.inline_path
                ]
        except Exception:
            pass

    def _align_all_junction_connecting_roads(self, scale_factors):
        """Apply lane alignment to all junctions' connecting roads.

        Called on project load to ensure CR visuals match lane connections
        without requiring the user to open the lane connection dialog.
        """
        from orbit.utils.connecting_road_alignment import align_connecting_road_paths

        if scale_factors:
            scale = (scale_factors[0] + scale_factors[1]) / 2.0
        else:
            scale = 0.058  # Default fallback

        for junction in self.project.junctions:
            if junction.lane_connections and junction.connecting_road_ids:
                modified_ids = align_connecting_road_paths(
                    junction, self.project, scale
                )
                # Update geo_path for modified CRs so export uses
                # the aligned coordinates, not the stale originals.
                if modified_ids:
                    for cr_id in junction.connecting_road_ids:
                        cr = self.project.get_road(cr_id)
                        if cr and cr.id in modified_ids:
                            self._refresh_connecting_road_geo_path(cr)

    def regenerate_affected_connecting_roads(self, polyline_id: str):
        """
        Regenerate ParamPoly3D connecting roads when a road centerline endpoint is modified.

        Args:
            polyline_id: ID of the modified polyline
        """
        import math

        from orbit.utils.geometry import generate_simple_connection_path

        # Get the modified polyline
        polyline = self.project.get_polyline(polyline_id)
        if not polyline or polyline.line_type != LineType.CENTERLINE:
            # Only regenerate for centerline modifications
            return

        # Find which road this polyline belongs to
        affected_road = None
        for road in self.project.roads:
            if road.centerline_id == polyline_id:
                affected_road = road
                break

        if not affected_road:
            return

        # Find junctions where this road appears as predecessor or successor
        affected_junctions = []
        for junction in self.project.junctions:
            for cr_id in junction.connecting_road_ids:
                conn_road = self.project.get_road(cr_id)
                if not conn_road:
                    continue
                if (conn_road.predecessor_id == affected_road.id or
                    conn_road.successor_id == affected_road.id):
                    if conn_road.geometry_type == "parampoly3":
                        affected_junctions.append((junction, conn_road))

        # Regenerate each affected ParamPoly3D connecting road
        for junction, conn_road in affected_junctions:
            # Get predecessor and successor roads
            pred_road = self.project.get_road(conn_road.predecessor_id)
            succ_road = self.project.get_road(conn_road.successor_id)

            if not pred_road or not succ_road:
                continue

            # Get centerline polylines
            pred_polyline = self.project.get_polyline(pred_road.centerline_id)
            succ_polyline = self.project.get_polyline(succ_road.centerline_id)

            if not pred_polyline or not succ_polyline:
                continue

            # Get endpoint positions and headings
            # Predecessor endpoint (end point for "end" contact)
            if conn_road.predecessor_contact == "end":
                pred_pos = pred_polyline.points[-1]
                if len(pred_polyline.points) >= 2:
                    dx = pred_polyline.points[-1][0] - pred_polyline.points[-2][0]
                    dy = pred_polyline.points[-1][1] - pred_polyline.points[-2][1]
                    pred_heading = math.atan2(dy, dx)
                else:
                    pred_heading = 0.0
            else:  # "start"
                pred_pos = pred_polyline.points[0]
                if len(pred_polyline.points) >= 2:
                    dx = pred_polyline.points[1][0] - pred_polyline.points[0][0]
                    dy = pred_polyline.points[1][1] - pred_polyline.points[0][1]
                    pred_heading = math.atan2(dy, dx)
                    pred_heading += math.pi  # Reverse direction for "start" contact
                else:
                    pred_heading = math.pi

            # Successor endpoint (start point for "start" contact)
            if conn_road.successor_contact == "start":
                succ_pos = succ_polyline.points[0]
                if len(succ_polyline.points) >= 2:
                    dx = succ_polyline.points[1][0] - succ_polyline.points[0][0]
                    dy = succ_polyline.points[1][1] - succ_polyline.points[0][1]
                    succ_heading = math.atan2(dy, dx)
                    succ_heading += math.pi  # Reverse direction to point into road
                else:
                    succ_heading = math.pi
            else:  # "end"
                succ_pos = succ_polyline.points[-1]
                if len(succ_polyline.points) >= 2:
                    dx = succ_polyline.points[-1][0] - succ_polyline.points[-2][0]
                    dy = succ_polyline.points[-1][1] - succ_polyline.points[-2][1]
                    succ_heading = math.atan2(dy, dx)
                else:
                    succ_heading = 0.0

            # Regenerate the curve
            path, coeffs = generate_simple_connection_path(
                from_pos=pred_pos,
                from_heading=pred_heading,
                to_pos=succ_pos,
                to_heading=succ_heading,
                tangent_scale=conn_road.tangent_scale
            )

            # Update the connecting road
            conn_road.inline_path = path
            self._refresh_connecting_road_geo_path(conn_road)
            aU, bU, cU, dU, aV, bV, cV, dV = coeffs
            conn_road.aU = aU
            conn_road.bU = bU
            conn_road.cU = cU
            conn_road.dU = dU
            conn_road.aV = aV
            conn_road.bV = bV
            conn_road.cV = cV
            conn_road.dV = dV

            # Update stored headings so get_start_heading/get_end_heading
            # return accurate values (used by dialog, export, alignment)
            conn_road.stored_start_heading = pred_heading
            conn_road.stored_end_heading = succ_heading

            # Update graphics
            scale_factors = self.get_current_scale()
            self.image_view.update_connecting_road_graphics(conn_road.id, scale_factors)

        # Snap endpoints of polyline-type connecting roads
        for junction in self.project.junctions:
            for cr_id in junction.connecting_road_ids:
                conn_road = self.project.get_road(cr_id)
                if not conn_road:
                    continue
                if conn_road.geometry_type == "parampoly3":
                    continue  # Already handled above
                if (conn_road.predecessor_id != affected_road.id and
                        conn_road.successor_id != affected_road.id):
                    continue
                if not conn_road.inline_path or len(conn_road.inline_path) < 2:
                    continue

                pred_road = self.project.get_road(conn_road.predecessor_id)
                succ_road = self.project.get_road(conn_road.successor_id)
                if not pred_road or not succ_road:
                    continue

                pred_polyline = self.project.get_polyline(pred_road.centerline_id)
                succ_polyline = self.project.get_polyline(succ_road.centerline_id)
                if not pred_polyline or not succ_polyline:
                    continue

                # Snap start to predecessor endpoint
                if conn_road.predecessor_contact == "end":
                    conn_road.inline_path[0] = pred_polyline.points[-1]
                else:
                    conn_road.inline_path[0] = pred_polyline.points[0]

                # Snap end to successor endpoint
                if conn_road.successor_contact == "end":
                    conn_road.inline_path[-1] = succ_polyline.points[-1]
                else:
                    conn_road.inline_path[-1] = succ_polyline.points[0]

                self._refresh_connecting_road_geo_path(conn_road)

                # Update graphics
                scale_factors = self.get_current_scale()
                self.image_view.update_connecting_road_graphics(conn_road.id, scale_factors)

        # Apply lane alignment to affected junctions so CR endpoints shift
        # from the road centerline to the correct lane position.
        from orbit.utils.connecting_road_alignment import align_connecting_road_paths

        scale_factors = self.get_current_scale()
        if scale_factors:
            scale = (scale_factors[0] + scale_factors[1]) / 2.0
        else:
            scale = 0.058

        affected_junction_ids = set()
        for junction in self.project.junctions:
            for cr_id in junction.connecting_road_ids:
                cr = self.project.get_road(cr_id)
                if cr and (cr.predecessor_id == affected_road.id or
                        cr.successor_id == affected_road.id):
                    affected_junction_ids.add(junction.id)
                    break

        for junction in self.project.junctions:
            if junction.id in affected_junction_ids:
                if junction.lane_connections and junction.connecting_road_ids:
                    modified = align_connecting_road_paths(
                        junction, self.project, scale
                    )
                    for cr_id in junction.connecting_road_ids:
                        cr = self.project.get_road(cr_id)
                        if cr and cr.id in modified:
                            self._refresh_connecting_road_geo_path(cr)
                    for cr_id in modified:
                        self.image_view.update_connecting_road_graphics(
                            cr_id, scale_factors
                        )

    def on_polyline_selected_in_tree(self, polyline_id):
        """Handle polyline selection from tree."""
        # Clear connecting road selection
        self.clear_connecting_road_selection()
        # Highlight the polyline in the image view
        self.image_view.highlight_polyline(polyline_id)

    def on_polyline_delete_requested(self, polyline_id):
        """Handle polyline delete request from tree with undo support."""
        from .undo_commands import DeletePolylineCommand

        # Create command BEFORE deletion (captures state including road associations)
        cmd = DeletePolylineCommand(self, polyline_id)

        # Remove polyline graphics from image view
        self.image_view.remove_polyline_graphics(polyline_id)

        # Remove from project
        self.project.remove_polyline(polyline_id)

        # Push command (first redo skipped since we just deleted it)
        self.undo_stack.push(cmd)

        # Update UI
        self._refresh_trees()
        self.statusBar().showMessage("Polyline deleted")

    def on_polyline_deleted_in_tree(self, polyline_id):
        """Handle polyline deletion from tree (legacy, for non-undo deletions)."""
        # Remove polyline graphics from image view
        if polyline_id in self.image_view.polyline_items:
            self.image_view.polyline_items[polyline_id].remove()
            del self.image_view.polyline_items[polyline_id]

        # Remove s-offset labels if they exist
        if polyline_id in self.image_view.soffset_labels:
            for text_item, bg_item in self.image_view.soffset_labels[polyline_id]:
                if text_item.scene() == self.image_view.scene:
                    self.image_view.scene.removeItem(text_item)
                if bg_item.scene() == self.image_view.scene:
                    self.image_view.scene.removeItem(bg_item)
            del self.image_view.soffset_labels[polyline_id]

        self.modified = True
        self.update_window_title()
        self.statusBar().showMessage("Polyline deleted")

    def on_junction_added(self, junction):
        """Handle junction added signal."""
        from .dialogs.junction_dialog import JunctionDialog
        from .undo_commands import AddJunctionCommand

        # Open dialog to configure the junction
        result = JunctionDialog.create_junction(self.project, junction.center_point, self)
        if result:
            # Convert pixel center to geo coords if transformer available
            if self._cached_transformer and result.center_point:
                lon, lat = self._cached_transformer.pixel_to_geo(result.center_point[0], result.center_point[1])
                result.geo_center_point = (lon, lat)

            self.project.add_junction(result)
            self.image_view.add_junction_graphics(result)

            # Push undo command
            cmd = AddJunctionCommand(self, result)
            self.undo_stack.push(cmd)

            self.update_elements_tree()
            self.statusBar().showMessage(
                f"Added junction: {result.name}. "
                f"Click to add another or press Escape to finish."
            )

    def on_junction_modified(self, junction_id):
        """Handle junction modified signal (legacy, for non-undo modifications)."""
        self.modified = True
        self.image_view.refresh_junction_graphics(junction_id)
        self.update_elements_tree()
        self.update_window_title()

    def on_junction_deleted(self, junction_id):
        """Handle junction deleted signal."""
        from .undo_commands import DeleteJunctionCommand

        # Create command BEFORE deletion
        cmd = DeleteJunctionCommand(self, junction_id)

        self.project.remove_junction(junction_id)
        self.image_view.remove_junction_graphics(junction_id)

        # Push command
        self.undo_stack.push(cmd)

        self.update_elements_tree()

    def on_junction_selected_in_tree(self, junction_id: str):
        """Handle junction selection in elements tree."""
        # Clear connecting road selection
        self.clear_connecting_road_selection()
        self.image_view.highlight_junction(junction_id)

    def edit_junction_properties(self, junction_id: str):
        """Edit properties of a junction."""
        from .dialogs.junction_dialog import JunctionDialog
        from .undo_commands import ModifyJunctionCommand

        junction = self.project.get_junction(junction_id)
        if not junction:
            return

        # Capture state before editing
        old_data = junction.to_dict()

        result = JunctionDialog.edit_junction(junction, self.project, self)
        if result:
            # Capture state after editing
            new_data = junction.to_dict()

            # Push undo command
            cmd = ModifyJunctionCommand(self, junction_id, old_data, new_data)
            self.undo_stack.push(cmd)

            # Properties were modified, update the view
            self.image_view.refresh_junction_graphics(junction_id)
            self.statusBar().showMessage(f"Junction properties updated: {result.name}")

    def on_connecting_road_selected(self, connecting_road_id: str):
        """Handle connecting road selection in elements tree."""
        # Clear previous connecting road selection
        self.clear_connecting_road_selection()

        # Highlight the connecting road in the view
        if connecting_road_id in self.image_view.connecting_road_centerline_items:
            self.image_view.connecting_road_centerline_items[connecting_road_id].set_selected(True)
            self.image_view.selected_connecting_road_id = connecting_road_id

    def on_connecting_road_modified(self, connecting_road_id: str):
        """Handle connecting road modification."""
        # Refresh graphics
        scale_factors = self.get_current_scale()
        self.image_view.update_connecting_road_graphics(connecting_road_id, scale_factors)
        self.modified = True
        self.update_window_title()

    def on_connecting_road_lane_selected(self, connecting_road_id: str, lane_id: int):
        """Handle connecting road lane selection in elements tree."""
        # Highlight the lane in the view
        self.highlight_connecting_road_lane(connecting_road_id, lane_id)
        self.statusBar().showMessage(f"Selected connecting road lane {lane_id}")

    def on_connecting_road_lane_clicked_in_view(self, connecting_road_id: str, lane_id: int):
        """Handle connecting road lane click in the view - select and highlight connected lanes."""
        # Select the corresponding item in the elements tree
        self.elements_tree.select_connecting_road_lane(connecting_road_id, lane_id)
        # Highlight the connecting road lane and connected road lanes
        self.image_view.select_connecting_road_lane(connecting_road_id, lane_id)
        self.statusBar().showMessage(f"Connecting road lane {lane_id} selected")

    def highlight_connecting_road_lane(self, connecting_road_id: str, lane_id: int):
        """Highlight a specific connecting road lane in the view."""
        # Clear existing lane selections
        self.clear_lane_selections()

        # Find and highlight the specific lane polygon
        if connecting_road_id in self.image_view.connecting_road_lanes_items:
            lanes_item = self.image_view.connecting_road_lanes_items[connecting_road_id]
            for lane_polygon in lanes_item.lane_items:
                if hasattr(lane_polygon, 'lane_id') and lane_polygon.lane_id == lane_id:
                    lane_polygon.set_selected(True)
                    break

    def clear_lane_selections(self):
        """Clear all lane selections in the view."""
        # Clear regular road lanes
        for road_id, lanes_item in self.image_view.road_lanes_items.items():
            for lane_polygon in lanes_item.lane_items:
                if hasattr(lane_polygon, 'set_selected'):
                    lane_polygon.set_selected(False)

        # Clear connecting road lanes
        for conn_road_id, lanes_item in self.image_view.connecting_road_lanes_items.items():
            for lane_polygon in lanes_item.lane_items:
                if hasattr(lane_polygon, 'set_selected'):
                    lane_polygon.set_selected(False)

    def clear_connecting_road_selection(self):
        """Clear the selected connecting road highlight."""
        if self.image_view.selected_connecting_road_id:
            prev_id = self.image_view.selected_connecting_road_id
            if prev_id in self.image_view.connecting_road_centerline_items:
                self.image_view.connecting_road_centerline_items[prev_id].set_selected(False)
            self.image_view.selected_connecting_road_id = None

    def on_signal_placement_requested(self, x: float, y: float):
        """Handle signal placement request - show selection dialog."""
        from orbit.models.signal import Signal, SignalType

        from .dialogs.signal_selection_dialog import SignalSelectionDialog

        # Show dialog to select signal type with enabled libraries from project
        enabled_libs = self.project.enabled_sign_libraries if self.project else ['se']
        dialog = SignalSelectionDialog(enabled_libraries=enabled_libs, parent=self)
        if dialog.exec():
            (signal_type, library_id, sign_id, value,
             speed_unit, custom_type, custom_subtype) = dialog.get_selection()
            if signal_type:
                # Create signal at clicked position
                signal = Signal(
                    signal_id=self.project.next_id('signal'),
                    position=(x, y),
                    signal_type=signal_type,
                    value=value,
                    speed_unit=speed_unit,
                    library_id=library_id,
                    sign_id=sign_id
                )
                # Set custom type/subtype if applicable
                if signal_type == SignalType.CUSTOM:
                    signal.custom_type = custom_type
                    signal.custom_subtype = custom_subtype
                # Set dimensions from library if available
                if signal_type == SignalType.LIBRARY_SIGN and library_id and sign_id:
                    from orbit.models.sign_library_manager import SignLibraryManager
                    manager = SignLibraryManager.instance()
                    sign_def = manager.get_sign_definition(library_id, sign_id)
                    if sign_def:
                        signal.sign_width = sign_def.default_width
                        signal.sign_height = sign_def.default_height

                # Find closest road or connecting road and assign
                closest_road_id = self.project.find_closest_road_or_cr((x, y))
                if closest_road_id:
                    signal.road_id = closest_road_id
                    road = self.project.get_road(closest_road_id)
                    if road and road.centerline_id:
                        centerline_polyline = self.project.get_polyline(road.centerline_id)
                        if centerline_polyline:
                            # Calculate s-position
                            # Note: Orientation defaults to '+' (forward) and can be adjusted in properties dialog
                            signal.s_position = signal.calculate_s_position(centerline_polyline.points)
                    else:
                        cr = self.project.get_road(closest_road_id)
                        if cr and cr.is_connecting_road and cr.inline_path:
                            signal.s_position = signal.calculate_s_position(cr.inline_path)

                # Convert pixel position to geo coords if transformer available
                if self._cached_transformer:
                    lon, lat = self._cached_transformer.pixel_to_geo(x, y)
                    signal.geo_position = (lon, lat)

                # Add to project and view
                self.project.add_signal(signal)
                self.image_view.add_signal_graphics(signal)

                # Push undo command
                from .undo_commands import AddSignalCommand
                cmd = AddSignalCommand(self, signal)
                self.undo_stack.push(cmd)

                self.update_elements_tree()
                self.statusBar().showMessage(
                    f"Added signal: {signal.get_display_name()}. "
                    f"Click to add another or press Escape to finish."
                )

    def on_signal_added(self, signal):
        """Handle signal added signal (legacy, for non-undo additions)."""
        # This is emitted by signal graphics when dragged
        self.modified = True
        self.update_elements_tree()
        self.update_window_title()

    def on_signal_modified(self, signal_id):
        """Handle signal modified signal (legacy, for non-undo modifications)."""
        self.modified = True
        self.image_view.refresh_signal_graphics(signal_id)
        self.update_elements_tree()
        self.road_tree.refresh_tree()
        self.update_window_title()

    def on_signal_deleted(self, signal_id):
        """Handle signal deleted signal."""
        from .undo_commands import DeleteSignalCommand

        # Create command BEFORE deletion
        cmd = DeleteSignalCommand(self, signal_id)

        self.project.remove_signal(signal_id)
        self.image_view.remove_signal_graphics(signal_id)

        # Push command
        self.undo_stack.push(cmd)

        self.update_elements_tree()

    def on_signal_selected_in_tree(self, signal_id: str):
        """Handle signal selected in elements tree."""
        self.clear_connecting_road_selection()
        self.image_view.select_signal(signal_id)

    def on_signal_selected_in_view(self, signal_id: str):
        """Handle signal selected in view - update tree selection."""
        self.clear_connecting_road_selection()
        self.elements_tree.select_signal(signal_id)

    def on_object_selected_in_tree(self, object_id: str):
        """Handle object selected in elements tree."""
        self.clear_connecting_road_selection()
        self.image_view.select_object(object_id)

    def on_object_selected_in_view(self, object_id: str):
        """Handle object selected in view - update tree selection."""
        self.clear_connecting_road_selection()
        self.elements_tree.select_object(object_id)

    def on_polyline_selected_in_view(self, polyline_id: str):
        """Handle polyline selected in view."""
        self.clear_connecting_road_selection()
        # Polylines are not in the elements tree, just keep them highlighted in view
        pass

    def on_junction_selected_in_view(self, junction_id: str):
        """Handle junction selected in view - update tree selection."""
        self.clear_connecting_road_selection()
        self.elements_tree.select_junction(junction_id)

    def on_object_modified_in_tree(self, object_id: str):
        """Handle object modified from elements tree."""
        self.modified = True
        self.image_view.refresh_object_graphics(object_id)
        self.update_window_title()

    def on_object_deleted_in_tree(self, object_id: str):
        """Handle object deleted from elements tree."""
        self.project.remove_object(object_id)
        self.image_view.remove_object_graphics(object_id)
        self.modified = True
        self.update_elements_tree()
        self.update_window_title()

    def on_parking_selected_in_tree(self, parking_id: str):
        """Handle parking selected in elements tree."""
        # Highlight parking in view
        if parking_id in self.image_view.parking_items:
            item = self.image_view.parking_items[parking_id]
            item.setSelected(True)
            # Center view on parking
            self.image_view.centerOn(item)

    def on_parking_modified(self, parking_id: str):
        """Handle parking modified from elements tree (legacy, for non-undo modifications)."""
        self.modified = True
        self.image_view.refresh_parking_graphics(parking_id)
        self.update_window_title()

    def on_parking_deleted(self, parking_id: str):
        """Handle parking deleted from elements tree."""
        from .undo_commands import DeleteParkingCommand

        # Create command BEFORE deletion
        cmd = DeleteParkingCommand(self, parking_id)

        self.project.remove_parking(parking_id)
        self.image_view.remove_parking_graphics(parking_id)

        # Push command
        self.undo_stack.push(cmd)

        self.update_elements_tree()

    def edit_signal_properties(self, signal_id: str):
        """Edit properties of a signal."""
        from .dialogs.signal_properties_dialog import SignalPropertiesDialog
        from .undo_commands import ModifySignalCommand

        signal = self.project.get_signal(signal_id)
        if not signal:
            return

        # Capture state before editing
        old_data = signal.to_dict()

        dialog = SignalPropertiesDialog(signal, self.project, self)
        if dialog.exec():
            # Capture state after editing
            new_data = signal.to_dict()

            # Push undo command
            cmd = ModifySignalCommand(self, signal_id, old_data, new_data)
            self.undo_stack.push(cmd)

            # Properties were modified, update the view
            self.image_view.refresh_signal_graphics(signal_id)
            self.update_elements_tree()
            self.statusBar().showMessage(f"Signal properties updated: {signal.get_display_name()}")

    def on_object_placement_requested(self, x: float, y: float, object_type):
        """Handle object placement request from ImageView (for point objects)."""
        from orbit.models import RoadObject

        # Create object at clicked position
        obj = RoadObject(
            object_id=self.project.next_id('object'),
            position=(x, y),
            object_type=object_type
        )

        # Find closest road and assign
        closest_road_id = self.project.find_closest_road((x, y))
        if closest_road_id:
            obj.road_id = closest_road_id
            road = self.project.get_road(closest_road_id)
            if road and road.centerline_id:
                centerline_polyline = self.project.get_polyline(road.centerline_id)
                if centerline_polyline:
                    # Calculate s and t position
                    s, t = obj.calculate_s_t_position(centerline_polyline.points)
                    obj.s_position = s
                    obj.t_offset = t

        # Convert pixel position to geo coords if transformer available
        if self._cached_transformer:
            lon, lat = self._cached_transformer.pixel_to_geo(x, y)
            obj.geo_position = (lon, lat)

        # Get scale factor for graphics
        scale_factor = 0.0
        if hasattr(self, '_cached_transformer') and self._cached_transformer:
            scale_x, scale_y = self._cached_transformer.get_scale_factor()
            scale_factor = scale_x if scale_x else 0.0

        # Add to project and view
        self.project.add_object(obj)
        self.image_view.add_object_graphics(obj, scale_factor)

        # Push undo command
        from .undo_commands import AddObjectCommand
        cmd = AddObjectCommand(self, obj)
        self.undo_stack.push(cmd)

        self.update_elements_tree()
        self.statusBar().showMessage(
            f"Added object: {obj.get_display_name()}. "
            f"Click to add another or toggle off to finish."
        )

    def on_parking_placement_requested(self, x: float, y: float, parking_type, access_type):
        """Handle parking placement request from ImageView."""
        from orbit.models.parking import ParkingSpace

        # Create parking at clicked position
        parking = ParkingSpace(
            parking_id=self.project.next_id('parking'),
            position=(x, y),
            parking_type=parking_type,
            access=access_type
        )

        # Find closest road and assign
        closest_road_id = self.project.find_closest_road((x, y))
        if closest_road_id:
            parking.road_id = closest_road_id
            road = self.project.get_road(closest_road_id)
            if road and road.centerline_id:
                centerline = self.project.get_polyline(road.centerline_id)
                if centerline:
                    s, t = parking.calculate_s_t_position(centerline.points)
                    parking.s_position = s
                    parking.t_offset = t

        # Convert pixel position to geo coords if transformer available
        if self._cached_transformer:
            lon, lat = self._cached_transformer.pixel_to_geo(x, y)
            parking.geo_position = (lon, lat)

        # Get scale factor for graphics
        scale_factor = 0.0
        if hasattr(self, '_cached_transformer') and self._cached_transformer:
            scale_x, scale_y = self._cached_transformer.get_scale_factor()
            scale_factor = scale_x if scale_x else 0.0

        # Add to project and view
        self.project.add_parking(parking)
        self.image_view.add_parking_graphics(parking, scale_factor)

        # Push undo command
        from .undo_commands import AddParkingCommand
        cmd = AddParkingCommand(self, parking)
        self.undo_stack.push(cmd)

        self.update_elements_tree()
        self.statusBar().showMessage(
            f"Added parking: {parking.get_display_name()}. "
            f"Click to add another or toggle off to finish."
        )

    def on_parking_polygon_completed(self, points: list, parking_type, access_type):
        """Handle parking polygon completion from ImageView."""
        from orbit.models.parking import ParkingSpace

        if len(points) < 3:
            self.statusBar().showMessage("Polygon needs at least 3 points")
            return

        # Calculate centroid for position
        centroid_x = sum(p[0] for p in points) / len(points)
        centroid_y = sum(p[1] for p in points) / len(points)

        # Create parking with polygon points
        parking = ParkingSpace(
            parking_id=self.project.next_id('parking'),
            position=(centroid_x, centroid_y),
            parking_type=parking_type,
            access=access_type
        )
        parking.points = list(points)  # Store polygon points

        # Find closest road and assign
        closest_road_id = self.project.find_closest_road((centroid_x, centroid_y))
        if closest_road_id:
            parking.road_id = closest_road_id
            road = self.project.get_road(closest_road_id)
            if road and road.centerline_id:
                centerline = self.project.get_polyline(road.centerline_id)
                if centerline:
                    s, t = parking.calculate_s_t_position(centerline.points)
                    parking.s_position = s
                    parking.t_offset = t

        # Convert pixel coords to geo coords if transformer available
        if self._cached_transformer:
            lon, lat = self._cached_transformer.pixel_to_geo(centroid_x, centroid_y)
            parking.geo_position = (lon, lat)
            # Also convert polygon points
            geo_points = []
            for px, py in points:
                lon, lat = self._cached_transformer.pixel_to_geo(px, py)
                geo_points.append((lon, lat))
            parking.geo_points = geo_points

        # Get scale factor for graphics
        scale_factor = 0.0
        if hasattr(self, '_cached_transformer') and self._cached_transformer:
            scale_x, scale_y = self._cached_transformer.get_scale_factor()
            scale_factor = scale_x if scale_x else 0.0

        # Add to project and view
        self.project.add_parking(parking)
        self.image_view.add_parking_graphics(parking, scale_factor)

        # Push undo command
        from .undo_commands import AddParkingCommand
        cmd = AddParkingCommand(self, parking)
        self.undo_stack.push(cmd)

        self.update_elements_tree()
        self.statusBar().showMessage(
            f"Added parking area: {parking.get_display_name()}. "
            f"Draw another or toggle off to finish."
        )

    def on_object_added(self, obj):
        """Handle object added signal (for guardrails)."""

        # Find closest road and assign
        closest_road_id = self.project.find_closest_road(obj.position)
        if closest_road_id:
            obj.road_id = closest_road_id
            road = self.project.get_road(closest_road_id)
            if road and road.centerline_id:
                centerline_polyline = self.project.get_polyline(road.centerline_id)
                if centerline_polyline:
                    s, t = obj.calculate_s_t_position(centerline_polyline.points)
                    obj.s_position = s
                    obj.t_offset = t

        # Convert pixel coords to geo coords if transformer available
        if self._cached_transformer:
            # Convert position
            lon, lat = self._cached_transformer.pixel_to_geo(obj.position[0], obj.position[1])
            obj.geo_position = (lon, lat)
            # Convert points (for polyline objects like guardrails)
            if obj.points:
                geo_points = []
                for px, py in obj.points:
                    lon, lat = self._cached_transformer.pixel_to_geo(px, py)
                    geo_points.append((lon, lat))
                obj.geo_points = geo_points

        # Get scale factor
        scale_factor = 0.0
        if hasattr(self, '_cached_transformer') and self._cached_transformer:
            scale_x, scale_y = self._cached_transformer.get_scale_factor()
            scale_factor = scale_x if scale_x else 0.0

        # Add to project and view
        self.project.add_object(obj)
        self.image_view.add_object_graphics(obj, scale_factor)

        # Push undo command
        from .undo_commands import AddObjectCommand
        cmd = AddObjectCommand(self, obj)
        self.undo_stack.push(cmd)

        self.update_elements_tree()
        self.statusBar().showMessage("Guardrail added. Click and drag to add another or toggle off to finish.")

    def on_object_polygon_completed(self, points: list, object_type):
        """Handle object polygon completion from ImageView (for land use etc.)."""
        from orbit.models import RoadObject

        if len(points) < 3:
            self.statusBar().showMessage("Polygon needs at least 3 points")
            return

        # Calculate centroid for position
        centroid_x = sum(p[0] for p in points) / len(points)
        centroid_y = sum(p[1] for p in points) / len(points)

        # Create object with polygon points
        obj = RoadObject(
            object_id=self.project.next_id('object'),
            position=(centroid_x, centroid_y),
            object_type=object_type
        )
        obj.points = list(points)

        # Find closest road and assign
        closest_road_id = self.project.find_closest_road((centroid_x, centroid_y))
        if closest_road_id:
            obj.road_id = closest_road_id
            road = self.project.get_road(closest_road_id)
            if road and road.centerline_id:
                centerline = self.project.get_polyline(road.centerline_id)
                if centerline:
                    s, t = obj.calculate_s_t_position(centerline.points)
                    obj.s_position = s
                    obj.t_offset = t

        # Convert pixel coords to geo coords if transformer available
        if self._cached_transformer:
            lon, lat = self._cached_transformer.pixel_to_geo(centroid_x, centroid_y)
            obj.geo_position = (lon, lat)
            geo_points = []
            for px, py in points:
                lon, lat = self._cached_transformer.pixel_to_geo(px, py)
                geo_points.append((lon, lat))
            obj.geo_points = geo_points

        # Get scale factor for graphics
        scale_factor = 0.0
        if hasattr(self, '_cached_transformer') and self._cached_transformer:
            scale_x, scale_y = self._cached_transformer.get_scale_factor()
            scale_factor = scale_x if scale_x else 0.0

        # Add to project and view
        self.project.add_object(obj)
        self.image_view.add_object_graphics(obj, scale_factor)

        # Push undo command
        from .undo_commands import AddObjectCommand
        cmd = AddObjectCommand(self, obj)
        self.undo_stack.push(cmd)

        self.update_elements_tree()
        self.statusBar().showMessage(
            f"Added {obj.get_display_name()}. "
            f"Draw another or toggle off to finish."
        )

    def on_object_modified(self, object_id):
        """Handle object modified signal (legacy, for non-undo modifications)."""
        self.modified = True
        self.image_view.refresh_object_graphics(object_id)
        self.update_elements_tree()
        self.update_window_title()

    def on_object_deleted(self, object_id):
        """Handle object deleted signal."""
        from .undo_commands import DeleteObjectCommand

        # Create command BEFORE deletion
        cmd = DeleteObjectCommand(self, object_id)

        self.project.remove_object(object_id)
        self.image_view.remove_object_graphics(object_id)

        # Push command
        self.undo_stack.push(cmd)

        self.update_elements_tree()

    def edit_object_properties(self, object_id: str):
        """Edit properties of an object."""
        from .dialogs.object_properties_dialog import ObjectPropertiesDialog
        from .undo_commands import ModifyObjectCommand

        obj = self.project.get_object(object_id)
        if not obj:
            return

        # Capture state before editing
        old_data = obj.to_dict()

        dialog = ObjectPropertiesDialog(obj, self.project, self)
        if dialog.exec():
            # Capture state after editing
            new_data = obj.to_dict()

            # Push undo command
            cmd = ModifyObjectCommand(self, object_id, old_data, new_data)
            self.undo_stack.push(cmd)

            # Properties were modified, update the view
            self.image_view.refresh_object_graphics(object_id)
            self.update_elements_tree()
            self.statusBar().showMessage(f"Object properties updated: {obj.get_display_name()}")

    def on_section_split_requested(self, road_id: str, polyline_id: str, point_index: int):
        """
        Handle section split request from ImageView.

        Args:
            road_id: ID of the road whose section should be split
            polyline_id: ID of the centerline polyline
            point_index: Index of the point where to split
        """
        from .undo_commands import SplitSectionCommand

        road = self.project.get_road(road_id)
        if not road:
            return

        polyline = self.project.get_polyline(polyline_id)
        if not polyline:
            return

        # Capture state before split
        old_road_data = road.to_dict()

        # Perform the split
        success = road.split_section_at_point(point_index, polyline.points)

        if success:
            # Capture state after split
            new_road_data = road.to_dict()

            # Push undo command
            cmd = SplitSectionCommand(self, road_id, old_road_data, new_road_data)
            self.undo_stack.push(cmd)

            self.road_tree.refresh_tree()
            self.statusBar().showMessage("Lane section split successfully")
            # Refresh lane graphics to show new section polygons
            self.update_affected_road_lanes()
        else:
            show_warning(
                self,
                "Failed to split lane section. The point may be "
                "outside section boundaries.",
                "Split Failed",
            )

    def on_section_delete_requested(self, road_id: str, section_number: int, re_snap: bool):
        """
        Handle section delete request from RoadTreeWidget.

        Args:
            road_id: ID of the road whose section should be deleted
            section_number: Section number to delete
            re_snap: Whether to recalculate remaining section boundaries
        """
        from .undo_commands import DeleteSectionCommand

        road = self.project.get_road(road_id)
        if not road:
            return

        old_data = road.to_dict()

        road.delete_section(section_number)

        if re_snap and road.centerline_id:
            centerline = self.project.get_polyline(road.centerline_id)
            if centerline:
                road.update_section_boundaries(centerline.points)

        new_data = road.to_dict()
        cmd = DeleteSectionCommand(self, road_id, old_data, new_data)
        self.undo_stack.push(cmd)

        self.road_tree.refresh_tree()
        self.statusBar().showMessage(f"Section {section_number} deleted")
        self.update_affected_road_lanes()

    def on_road_split_requested(self, road_id: str, polyline_id: str, point_index: int):
        """
        Handle road split request from ImageView.

        Splits the road at the specified centerline point, creating two connected
        roads with proper predecessor/successor links. Both centerline and boundary
        polylines are split at corresponding positions.

        Args:
            road_id: ID of the road to split
            polyline_id: ID of the centerline polyline
            point_index: Index of the point where to split
        """
        from .undo_commands import SplitRoadCommand

        # Capture state before split
        road = self.project.get_road(road_id)
        polyline = self.project.get_polyline(polyline_id)
        if not road or not polyline:
            return

        original_road_data = road.to_dict()
        original_polyline_data = polyline.to_dict()

        # Remember polylines before split so we can identify new ones
        polylines_before = {p.id for p in self.project.polylines}

        result = self.project.split_road_at_point(road_id, polyline_id, point_index)

        if result:
            road1, road2 = result

            # Find new polylines created by the split
            new_polylines = [p for p in self.project.polylines if p.id not in polylines_before]

            # Capture state after split for undo
            # The original polyline was modified (shortened), and a new polyline was created
            # road1 uses the modified original polyline, road2 uses the new polyline
            poly1 = self.project.get_polyline(road1.centerline_id)
            poly2 = self.project.get_polyline(road2.centerline_id)

            if poly1 and poly2:
                cmd = SplitRoadCommand(
                    self,
                    original_road_data, road1.to_dict(), road2.to_dict(),
                    original_polyline_data, poly1.to_dict(), poly2.to_dict()
                )
                self.undo_stack.push(cmd)

            # Add graphics for new polylines
            for polyline in new_polylines:
                self.image_view.add_polyline_graphics(polyline)

            # Update graphics for modified polylines (the ones that were split)
            for pid in road1.polyline_ids:
                self.image_view.update_polyline(pid)

            # Refresh trees to show new road and updated polylines
            self.road_tree.refresh_tree()
            self.elements_tree.refresh_tree()

            # Refresh lane graphics for both roads
            self.update_affected_road_lanes()

            self.statusBar().showMessage(f"Road split into '{road1.name}' and '{road2.name}'")
        else:
            show_warning(self, "Failed to split road. Check the console for details.", "Split Failed")

    def on_roads_merge_requested(self, road1_id: str, road2_id: str):
        """
        Handle road merge request from RoadTreeWidget.

        Merges two consecutive roads into one, combining their centerlines,
        boundaries, and lane sections.

        Args:
            road1_id: ID of the first road (predecessor)
            road2_id: ID of the second road (successor)
        """
        from .undo_commands import MergeRoadsCommand

        road1 = self.project.get_road(road1_id)
        road2 = self.project.get_road(road2_id)

        if not road1 or not road2:
            return

        # Confirm with user
        reply = QMessageBox.question(
            self,
            "Merge Roads",
            f"Merge '{road1.name}' and '{road2.name}' into a single road?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Capture state before merge
        road1_data = road1.to_dict()
        road2_data = road2.to_dict()
        poly1 = self.project.get_polyline(road1.centerline_id)
        poly2 = self.project.get_polyline(road2.centerline_id)
        poly1_data = poly1.to_dict() if poly1 else None
        poly2_data = poly2.to_dict() if poly2 else None

        # Remember polylines that will be deleted
        road2_polylines = set(road2.polyline_ids)

        result = self.project.merge_consecutive_roads(road1_id, road2_id)

        if result:
            # Capture merged state for undo
            merged_road_data = result.to_dict()
            merged_poly = self.project.get_polyline(result.centerline_id)
            merged_poly_data = merged_poly.to_dict() if merged_poly else None

            if poly1_data and poly2_data and merged_poly_data:
                cmd = MergeRoadsCommand(
                    self,
                    road1_data, road2_data, merged_road_data,
                    poly1_data, poly2_data, merged_poly_data
                )
                self.undo_stack.push(cmd)

            # Remove graphics for deleted polylines (road2's polylines that are no longer in project)
            for pid in road2_polylines:
                # Check if this polyline still exists (some were merged, some deleted)
                if not self.project.get_polyline(pid):
                    # Polyline was deleted - remove its graphics
                    if pid in self.image_view.polyline_items:
                        item = self.image_view.polyline_items[pid]
                        item.remove()
                        # Remove s-offset labels if they exist
                        if pid in self.image_view.soffset_labels:
                            for text_item, bg_item in self.image_view.soffset_labels[pid]:
                                if text_item.scene() == self.image_view.scene:
                                    self.image_view.scene.removeItem(text_item)
                                if bg_item.scene() == self.image_view.scene:
                                    self.image_view.scene.removeItem(bg_item)
                            del self.image_view.soffset_labels[pid]
                        del self.image_view.polyline_items[pid]

            # Update graphics for road1's polylines (they were modified)
            for pid in result.polyline_ids:
                self.image_view.update_polyline(pid)

            # Refresh trees
            self.road_tree.refresh_tree()
            self.elements_tree.refresh_tree()

            # Refresh lane graphics
            self.update_affected_road_lanes()

            self.statusBar().showMessage(f"Merged roads into '{result.name}'")
        else:
            show_warning(
                self,
                "Failed to merge roads. Check the console for details.",
                "Merge Failed"
            )

    def merge_selected_roads(self):
        """
        Merge roads selected in the Road Tree sidebar.

        Validates that exactly two consecutive roads are selected and
        triggers the merge operation.
        """
        # Get selected items from road tree
        selected_items = self.road_tree.tree.selectedItems()

        # Filter for road items only
        selected_roads = []
        for item in selected_items:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(data, dict) and data.get("type") == "road":
                selected_roads.append(data.get("id"))

        if len(selected_roads) != 2:
            show_info(
                self,
                "Please select exactly two roads in the Road Tree sidebar to merge.\n\n"
                "The roads must be consecutive (one must end where the other begins).",
                "Select Roads to Merge"
            )
            return

        # Check if roads can be merged
        can_merge, road1_id, road2_id = self.road_tree._can_merge_roads(
            selected_roads[0], selected_roads[1]
        )

        if not can_merge:
            show_warning(
                self,
                "Cannot merge these roads.\n\n"
                "Roads must be consecutive (one road's successor must be the other road).",
                "Cannot Merge"
            )
            return

        # Trigger the existing merge handler
        self.on_roads_merge_requested(road1_id, road2_id)

    def on_section_modified(self, road_id: str):
        """Handle section modified signal."""
        self.modified = True
        self.road_tree.refresh_tree()
        self.update_window_title()

    def on_lane_segment_clicked(self, road_id: str, section_number: int, lane_id: int):
        """
        Handle lane segment click from ImageView.

        Args:
            road_id: ID of the road
            section_number: Section number containing the lane
            lane_id: Lane ID within the section
        """
        # Select the lane visually in the image view
        self.image_view.select_lane(road_id, section_number, lane_id)

        # Select the lane in the road tree
        self.road_tree.select_lane(road_id, section_number, lane_id)

    def on_lane_selected_in_tree(self, road_id: str, section_number: int, lane_id: int):
        """
        Handle lane selection from road tree.

        Args:
            road_id: ID of the road
            section_number: Section number containing the lane
            lane_id: Lane ID within the section
        """
        # Clear connecting road selection
        self.clear_connecting_road_selection()
        # Select the lane visually in the image view
        self.image_view.select_lane(road_id, section_number, lane_id)

    def on_lane_edit_requested(self, road_id: str, section_number: int, lane_id: int):
        """
        Handle lane edit request (double-click on lane in map).

        Args:
            road_id: ID of the road
            section_number: Section number containing the lane
            lane_id: Lane ID within the section
        """
        from .dialogs.lane_properties_dialog import LanePropertiesDialog

        # Find the road
        road = self.project.get_road(road_id)
        if not road:
            return

        # Find the section
        section = None
        for s in road.lane_sections:
            if s.section_number == section_number:
                section = s
                break

        if not section:
            return

        # Find the lane
        lane = section.get_lane(lane_id)
        if not lane:
            return

        # Open lane properties dialog
        if LanePropertiesDialog.edit_lane(lane, self.project, road_id, None, parent=self):
            # Properties were modified, update the view
            scale_factors = self.get_current_scale()
            self.image_view.update_road_lanes(road_id, scale_factors)
            self.modified = True
            self.road_tree.refresh_tree()
            self.update_window_title()
            self.statusBar().showMessage(f"Lane properties updated: {lane.get_display_name()}")

    def on_connecting_road_lane_edit_requested(self, connecting_road_id: str, lane_id: int):
        """
        Handle connecting road lane edit request (double-click on connecting road lane in map).

        Args:
            connecting_road_id: ID of the connecting road
            lane_id: Lane ID within the connecting road
        """
        from .dialogs.lane_properties_dialog import LanePropertiesDialog

        # Find the connecting road in project roads
        connecting_road = self.project.get_road(connecting_road_id)

        if not connecting_road or not connecting_road.is_connecting_road:
            return

        # Find the lane
        lane = connecting_road.get_cr_lane(lane_id)
        if not lane:
            return
        # Open lane properties dialog (without project/road_id since connecting roads are standalone)
        if LanePropertiesDialog.edit_lane(lane, None, None, connecting_road, parent=self):
            # Properties were modified, update the view
            scale_factors = self.get_current_scale()
            self.image_view.update_connecting_road_graphics(connecting_road_id, scale_factors)
            self.modified = True
            self.elements_tree.refresh_tree()
            self.update_window_title()
            self.statusBar().showMessage(f"Connecting road lane properties updated: {lane.get_display_name()}")

    # Utility methods
    def check_unsaved_changes(self) -> bool:
        """Check for unsaved changes and prompt user. Returns True if ok to continue."""
        if self.modified:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Do you want to save before continuing?",
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel
            )

            if reply == QMessageBox.StandardButton.Save:
                self.save_project()
                return True
            elif reply == QMessageBox.StandardButton.Discard:
                return True
            else:
                return False
        return True

    def show_about(self):
        """Show about dialog with logo."""
        from pathlib import Path

        from PyQt6.QtGui import QPixmap

        # Create custom message box with logo
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("About ORBIT")

        # Try to load logo
        logo_path = Path(__file__).parent.parent.parent / "docs" / "orbit_logo_t.png"
        if logo_path.exists():
            pixmap = QPixmap(str(logo_path))
            # Scale logo to reasonable size (200px width, maintain aspect ratio)
            pixmap = pixmap.scaledToWidth(200, Qt.TransformationMode.SmoothTransformation)
            msg_box.setIconPixmap(pixmap)

        from orbit import __version__
        msg_box.setText(
            "<h2>ORBIT</h2>"
            "<p><b>OpenDrive Road Builder from Imagery Tool</b></p>"
            f"<p>Version {__version__}</p>"
        )
        msg_box.setInformativeText(
            "A tool for annotating roads in drone/aerial/satellite imagery "
            "and exporting to ASAM OpenDrive format."
        )
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()

    def show_keyboard_shortcuts(self):
        """Show keyboard shortcuts reference dialog."""
        shortcuts_text = """
<h3>File</h3>
<table>
<tr><td><b>Ctrl+N</b></td><td>New Project</td></tr>
<tr><td><b>Ctrl+O</b></td><td>Open Project</td></tr>
<tr><td><b>Ctrl+S</b></td><td>Save</td></tr>
<tr><td><b>Ctrl+Shift+S</b></td><td>Save As</td></tr>
<tr><td><b>Ctrl+I</b></td><td>Load Image</td></tr>
<tr><td><b>Ctrl+Shift+I</b></td><td>Import OpenStreetMap</td></tr>
<tr><td><b>Ctrl+Shift+O</b></td><td>Import OpenDRIVE</td></tr>
<tr><td><b>Ctrl+E</b></td><td>Export OpenDRIVE</td></tr>
</table>

<h3>View</h3>
<table>
<tr><td><b>Ctrl++</b></td><td>Zoom In</td></tr>
<tr><td><b>Ctrl+-</b></td><td>Zoom Out</td></tr>
<tr><td><b>Ctrl+0</b></td><td>Fit to Window</td></tr>
<tr><td><b>Ctrl+R</b></td><td>Reset View</td></tr>
<tr><td><b>Ctrl+L</b></td><td>Toggle Lane Visualization</td></tr>
</table>

<h3>Draw</h3>
<table>
<tr><td><b>Ctrl+P</b></td><td>New Polyline</td></tr>
<tr><td><b>Ctrl+T</b></td><td>Add Signal</td></tr>
<tr><td><b>Ctrl+Alt+O</b></td><td>Add Object</td></tr>
<tr><td><b>Ctrl+Shift+P</b></td><td>Add Parking</td></tr>
</table>

<h3>Roads</h3>
<table>
<tr><td><b>Ctrl+G</b></td><td>Group to Road</td></tr>
<tr><td><b>Ctrl+J</b></td><td>Add Junction</td></tr>
<tr><td><b>Ctrl+Shift+R</b></td><td>Create Roundabout</td></tr>
</table>

<h3>Georeferencing</h3>
<table>
<tr><td><b>Ctrl+Shift+G</b></td><td>Control Points</td></tr>
<tr><td><b>Ctrl+Shift+A</b></td><td>Adjust Alignment</td></tr>
<tr><td><b>Ctrl+M</b></td><td>Measure Distance</td></tr>
<tr><td><b>Ctrl+K</b></td><td>Show Scale Factor</td></tr>
</table>

<h3>Editing</h3>
<table>
<tr><td><b>Delete</b></td><td>Delete Selected</td></tr>
<tr><td><b>Enter/Return</b></td><td>Finish Drawing</td></tr>
<tr><td><b>Escape</b></td><td>Cancel Operation</td></tr>
</table>
"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Keyboard Shortcuts")
        msg_box.setText("<h2>Keyboard Shortcuts</h2>")
        msg_box.setInformativeText(shortcuts_text)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()

    def restore_geometry(self):
        """Restore window geometry from settings."""
        geometry = self.settings.value("mainwindow/geometry")
        if geometry:
            self.restoreGeometry(geometry)

        state = self.settings.value("mainwindow/state")
        if state:
            self.restoreState(state)

        # Always ensure adjustment dock is hidden on startup
        # (it should only be visible when adjustment mode is active)
        self.adjustment_dock.setVisible(False)
        self.image_view.set_adjustment_mode(False)

    # ========================================================================
    # Area selection batch delete
    # ========================================================================

    def _build_batch_delete_info(self, selected: dict) -> dict:
        """Build display info for the batch delete dialog.

        Args:
            selected: Dict with road_ids, junction_ids, signal_ids,
                      object_ids, parking_ids lists.

        Returns:
            Dict mapping category keys to lists of item dicts with
            id, name, details, and cascade fields.
        """
        info: dict = {}

        # Roads
        if selected.get("road_ids"):
            items = []
            for rid in selected["road_ids"]:
                road = self.project.get_road(rid)
                if not road:
                    continue
                cascade = []
                for pid in road.polyline_ids:
                    pl = self.project.get_polyline(pid)
                    if pl:
                        cascade.append(f"Polyline: {pl.line_type.value} ({pid[:8]})")
                items.append({
                    "id": rid,
                    "name": road.name or rid[:8],
                    "details": f"{len(road.polyline_ids)} polyline(s)",
                    "cascade": cascade,
                })
            if items:
                info["road_ids"] = items

        # Junctions
        if selected.get("junction_ids"):
            items = []
            for jid in selected["junction_ids"]:
                junction = self.project.get_junction(jid)
                if not junction:
                    continue
                cascade = []
                for crid in junction.connected_road_ids:
                    road = self.project.get_road(crid)
                    if road:
                        cascade.append(f"Connected road: {road.name or crid[:8]}")
                items.append({
                    "id": jid,
                    "name": junction.name or jid[:8],
                    "details": f"{len(junction.connecting_road_ids)} connecting road(s)",
                    "cascade": cascade,
                })
            if items:
                info["junction_ids"] = items

        # Signals
        if selected.get("signal_ids"):
            items = []
            for sid in selected["signal_ids"]:
                signal = self.project.get_signal(sid)
                if not signal:
                    continue
                items.append({
                    "id": sid,
                    "name": signal.get_display_name(),
                    "details": signal.type.value if hasattr(signal.type, 'value') else str(signal.type),
                })
            if items:
                info["signal_ids"] = items

        # Objects
        if selected.get("object_ids"):
            items = []
            for oid in selected["object_ids"]:
                obj = self.project.get_object(oid)
                if not obj:
                    continue
                items.append({
                    "id": oid,
                    "name": obj.get_display_name(),
                    "details": obj.type.value if hasattr(obj.type, 'value') else str(obj.type),
                })
            if items:
                info["object_ids"] = items

        # Parking
        if selected.get("parking_ids"):
            items = []
            for pid in selected["parking_ids"]:
                parking = self.project.get_parking(pid)
                if not parking:
                    continue
                items.append({
                    "id": pid,
                    "name": parking.get_display_name(),
                    "details": parking.parking_type.value if hasattr(parking.parking_type, 'value') else "",
                })
            if items:
                info["parking_ids"] = items

        return info

    def on_area_delete_requested(self, selected: dict):
        """Handle area selection batch delete request.

        Shows a confirmation dialog and deletes checked items as a
        single undo macro.
        """
        from .dialogs.batch_delete_dialog import BatchDeleteDialog
        from .undo_commands import (
            DeleteJunctionCommand,
            DeleteObjectCommand,
            DeleteParkingCommand,
            DeleteRoadCommand,
            DeleteSignalCommand,
        )

        info = self._build_batch_delete_info(selected)
        if not info:
            return

        dialog = BatchDeleteDialog(info, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        confirmed = dialog.get_selected_ids()
        if not confirmed:
            return

        # Count total items for macro name
        total = sum(len(ids) for ids in confirmed.values())

        # Capture ALL command state BEFORE any deletions, so that
        # cross-references (e.g. junction.connected_road_ids) are intact.
        road_cmds = []
        for road_id in confirmed.get("road_ids", []):
            if self.project.get_road(road_id):
                road_cmds.append(DeleteRoadCommand(self, road_id))

        junction_cmds = []
        for junction_id in confirmed.get("junction_ids", []):
            if self.project.get_junction(junction_id):
                junction_cmds.append((junction_id, DeleteJunctionCommand(self, junction_id)))

        signal_cmds = []
        for signal_id in confirmed.get("signal_ids", []):
            if self.project.get_signal(signal_id):
                signal_cmds.append(DeleteSignalCommand(self, signal_id))

        object_cmds = []
        for object_id in confirmed.get("object_ids", []):
            if self.project.get_object(object_id):
                object_cmds.append(DeleteObjectCommand(self, object_id))

        parking_cmds = []
        for parking_id in confirmed.get("parking_ids", []):
            if self.project.get_parking(parking_id):
                parking_cmds.append(DeleteParkingCommand(self, parking_id))

        # Now perform deletions and push commands
        self.undo_stack.beginMacro(f"Batch Delete ({total} items)")

        # Delete roads first (project.remove_road cleans up junction refs)
        for cmd in road_cmds:
            road = self.project.get_road(cmd.road_id)
            if road:
                self.image_view.remove_road_lanes(cmd.road_id)
                # Remove connecting road graphics that will be orphaned
                for junction in self.project.junctions:
                    for cr_id in junction.connecting_road_ids:
                        cr = self.project.get_road(cr_id)
                        if cr and (cr.predecessor_id == cmd.road_id or cr.successor_id == cmd.road_id):
                            self.image_view.remove_connecting_road_graphics(cr.id)
                for pid in list(road.polyline_ids):
                    self.image_view.remove_polyline_graphics(pid)
                    self.project.remove_polyline(pid)
                self.project.remove_road(cmd.road_id)
            self.undo_stack.push(cmd)

        # Delete junctions
        for junction_id, cmd in junction_cmds:
            junction = self.project.get_junction(junction_id)
            if junction:
                for cr_id in junction.connecting_road_ids:
                    self.image_view.remove_connecting_road_graphics(cr_id)
                self.image_view.remove_junction_graphics(junction_id)
                self.project.remove_junction(junction_id)
            self.undo_stack.push(cmd)

        # Delete signals
        for cmd in signal_cmds:
            self.image_view.remove_signal_graphics(cmd.signal_id)
            self.project.remove_signal(cmd.signal_id)
            self.undo_stack.push(cmd)

        # Delete objects
        for cmd in object_cmds:
            self.image_view.remove_object_graphics(cmd.object_id)
            self.project.remove_object(cmd.object_id)
            self.undo_stack.push(cmd)

        # Delete parking spaces
        for cmd in parking_cmds:
            self.image_view.remove_parking_graphics(cmd.parking_id)
            self.project.remove_parking(cmd.parking_id)
            self.undo_stack.push(cmd)

        self.undo_stack.endMacro()

        self._refresh_trees()
        self.modified = True
        self.update_window_title()
        self.statusBar().showMessage(f"Deleted {total} item(s)")

    def closeEvent(self, event):
        """Handle window close event."""
        if self.check_unsaved_changes():
            # Save window geometry
            self.settings.setValue("mainwindow/geometry", self.saveGeometry())
            self.settings.setValue("mainwindow/state", self.saveState())
            event.accept()
        else:
            event.ignore()

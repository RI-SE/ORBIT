"""
Main window for ORBIT application.

Provides the main GUI with menus, toolbar, status bar, and central view.
"""

from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow, QFileDialog, QMessageBox, QDockWidget,
    QListWidget, QToolBar, QWidget, QVBoxLayout, QPushButton,
    QLabel, QDialog
)
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QAction, QKeySequence

from orbit.models import Project, LineType
from .image_view import ImageView
from .widgets.road_tree import RoadTreeWidget
from .widgets.elements_tree import ElementsTreeWidget
from .message_helpers import show_error, show_warning, show_info, ask_yes_no


class MainWindow(QMainWindow):
    """Main application window for ORBIT."""

    def __init__(self, image_path: Optional[Path] = None, verbose: bool = False, parent=None):
        super().__init__(parent)

        # Project state
        self.project = Project()
        self.current_project_file: Optional[Path] = None
        self.modified = False
        self.verbose = verbose  # Debug flag

        # Cached transformer for real-time coordinate display
        self._cached_transformer = None

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
        self.image_view.section_split_requested.connect(self.on_section_split_requested)
        self.image_view.section_modified.connect(self.on_section_modified)
        self.image_view.lane_segment_clicked.connect(self.on_lane_segment_clicked)
        self.image_view.connecting_road_lane_clicked.connect(self.on_connecting_road_lane_clicked_in_view)
        self.image_view.lane_edit_requested.connect(self.on_lane_edit_requested)
        self.image_view.connecting_road_lane_edit_requested.connect(self.on_connecting_road_lane_edit_requested)
        self.image_view.point_picked.connect(self.on_point_picked)

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

        # Edit actions
        self.undo_action = QAction("&Undo", self)
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.setStatusTip("Undo last action")
        self.undo_action.setEnabled(False)  # TODO: Implement undo/redo

        self.redo_action = QAction("&Redo", self)
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self.redo_action.setStatusTip("Redo last undone action")
        self.redo_action.setEnabled(False)  # TODO: Implement undo/redo

        self.delete_action = QAction("&Delete Selected", self)
        self.delete_action.setShortcut(QKeySequence.StandardKey.Delete)
        self.delete_action.setStatusTip("Delete selected item")
        self.delete_action.triggered.connect(self.delete_selected)

        self.preferences_action = QAction("Pr&eferences...", self)
        self.preferences_action.setStatusTip("Configure project preferences")
        self.preferences_action.triggered.connect(self.show_preferences)

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
        self.toggle_junction_debug_action.setStatusTip("Show debug visualization for junction connections (endpoints, headings, paths)")
        self.toggle_junction_debug_action.setCheckable(True)
        self.toggle_junction_debug_action.setChecked(False)  # Hidden by default
        self.toggle_junction_debug_action.triggered.connect(self.toggle_junction_debug_visibility)

        # Uncertainty overlay actions
        self.uncertainty_none_action = QAction("None", self)
        self.uncertainty_none_action.setStatusTip("Hide uncertainty overlay")
        self.uncertainty_none_action.setCheckable(True)
        self.uncertainty_none_action.setChecked(True)  # Hidden by default
        self.uncertainty_none_action.triggered.connect(lambda: self.set_uncertainty_overlay(None))

        self.uncertainty_position_action = QAction("Position Uncertainty", self)
        self.uncertainty_position_action.setStatusTip("Show position uncertainty heat map")
        self.uncertainty_position_action.setCheckable(True)
        self.uncertainty_position_action.setChecked(False)
        self.uncertainty_position_action.triggered.connect(lambda: self.set_uncertainty_overlay('position'))

        # Create action group for mutual exclusivity
        from PyQt6.QtGui import QActionGroup
        self.uncertainty_action_group = QActionGroup(self)
        self.uncertainty_action_group.addAction(self.uncertainty_none_action)
        self.uncertainty_action_group.addAction(self.uncertainty_position_action)

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

        self.add_signal_action = QAction("Add &Signal", self)
        self.add_signal_action.setShortcut(QKeySequence("Ctrl+T"))
        self.add_signal_action.setStatusTip("Add a traffic signal/sign")
        self.add_signal_action.setCheckable(True)
        self.add_signal_action.triggered.connect(self.add_signal)

        self.add_object_action = QAction("Add &Object", self)
        self.add_object_action.setShortcut(QKeySequence("Ctrl+Shift+O"))
        self.add_object_action.setStatusTip("Add a roadside object (lamppost, building, tree, etc.)")
        self.add_object_action.setCheckable(True)
        self.add_object_action.triggered.connect(self.add_object)

        self.georef_action = QAction("&Georeferencing...", self)
        self.georef_action.setStatusTip("Configure georeferencing control points")
        self.georef_action.triggered.connect(self.open_georeferencing)

        self.measure_action = QAction("&Measure Distance", self)
        self.measure_action.setShortcut(QKeySequence("Ctrl+M"))
        self.measure_action.setStatusTip("Measure distances between points")
        self.measure_action.setCheckable(True)
        self.measure_action.triggered.connect(self.toggle_measure_mode)

        self.show_scale_action = QAction("Show &Scale Factor", self)
        self.show_scale_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.show_scale_action.setStatusTip("Show scale factor at clicked points")
        self.show_scale_action.setCheckable(True)
        self.show_scale_action.triggered.connect(self.toggle_show_scale_mode)

        # Help actions
        self.about_action = QAction("&About ORBIT", self)
        self.about_action.setStatusTip("About this application")
        self.about_action.triggered.connect(self.show_about)

    def create_menus(self):
        """Create the menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")
        file_menu.addAction(self.new_action)
        file_menu.addAction(self.open_action)
        file_menu.addSeparator()
        file_menu.addAction(self.save_action)
        file_menu.addAction(self.save_as_action)
        file_menu.addSeparator()
        file_menu.addAction(self.load_image_action)
        file_menu.addSeparator()
        file_menu.addAction(self.export_action)
        file_menu.addAction(self.import_osm_action)
        file_menu.addAction(self.import_opendrive_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)

        # Edit menu
        edit_menu = menubar.addMenu("&Edit")
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.delete_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.preferences_action)

        # View menu
        view_menu = menubar.addMenu("&View")
        view_menu.addAction(self.zoom_in_action)
        view_menu.addAction(self.zoom_out_action)
        view_menu.addAction(self.fit_action)
        view_menu.addAction(self.reset_view_action)
        view_menu.addSeparator()
        view_menu.addAction(self.toggle_lanes_action)
        view_menu.addAction(self.toggle_soffsets_action)
        view_menu.addAction(self.toggle_junction_debug_action)
        view_menu.addSeparator()

        # Uncertainty overlay submenu
        uncertainty_menu = view_menu.addMenu("Uncertainty Overlay")
        uncertainty_menu.addAction(self.uncertainty_none_action)
        uncertainty_menu.addAction(self.uncertainty_position_action)

        # Tools menu
        tools_menu = menubar.addMenu("&Tools")
        tools_menu.addAction(self.new_polyline_action)
        tools_menu.addAction(self.group_to_road_action)
        tools_menu.addAction(self.add_junction_action)
        tools_menu.addAction(self.add_signal_action)
        tools_menu.addAction(self.add_object_action)
        tools_menu.addAction(self.measure_action)
        tools_menu.addAction(self.show_scale_action)
        tools_menu.addSeparator()
        tools_menu.addAction(self.georef_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")
        help_menu.addAction(self.about_action)

    def create_toolbar(self):
        """Create the main toolbar."""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        toolbar.addAction(self.new_action)
        toolbar.addAction(self.open_action)
        toolbar.addAction(self.save_action)
        toolbar.addSeparator()
        toolbar.addAction(self.load_image_action)
        toolbar.addSeparator()
        toolbar.addAction(self.new_polyline_action)
        toolbar.addAction(self.group_to_road_action)
        toolbar.addAction(self.add_junction_action)
        toolbar.addAction(self.add_signal_action)
        toolbar.addAction(self.add_object_action)
        toolbar.addAction(self.measure_action)
        toolbar.addAction(self.show_scale_action)
        toolbar.addSeparator()
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
        self.road_tree.polyline_selected.connect(self.on_polyline_selected_in_tree)
        self.road_tree.polyline_deleted.connect(self.on_polyline_deleted_in_tree)
        self.road_tree.lane_selected.connect(self.on_lane_selected_in_tree)

    # Project management
    def new_project(self):
        """Create a new project."""
        if self.check_unsaved_changes():
            self.project.clear()
            self.current_project_file = None
            self.modified = False
            self._cached_transformer = None  # Invalidate transformer cache
            self.image_view.clear()
            self.update_elements_tree()
            self.road_tree.refresh_tree()
            self.update_window_title()
            self.update_scale_display()
            self.statusBar().showMessage("New project created")

    def open_project(self):
        """Open an existing project file."""
        if not self.check_unsaved_changes():
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Project",
            str(Path.home()),
            "ORBIT Projects (*.orbit *.json);;All Files (*)"
        )

        if file_path:
            try:
                self.project = Project.load(Path(file_path))
                self.current_project_file = Path(file_path)
                self.modified = False
                self._cached_transformer = None  # Invalidate transformer cache

                # Load image if specified in project
                if self.project.image_path:
                    self.load_image(self.project.image_path)

                # Calculate scale BEFORE loading project (so lanes use correct scale)
                scale_factors = self.get_current_scale()

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
            str(Path.home()),
            "ORBIT Projects (*.orbit);;JSON Files (*.json);;All Files (*)"
        )

        if file_path:
            try:
                self.current_project_file = Path(file_path)
                self.project.save(self.current_project_file)
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
            str(Path.home()),
            "Images (*.jpg *.jpeg *.png *.bmp *.tif *.tiff);;All Files (*)"
        )

        if file_path:
            self.load_image(Path(file_path))

    def load_image(self, image_path: Path):
        """Load an image into the view."""
        if image_path.exists():
            self.image_view.load_image(image_path)
            self.project.image_path = image_path

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
        from .preferences_dialog import PreferencesDialog

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
                from orbit.export import create_transformer, TransformMethod
                method = TransformMethod.HOMOGRAPHY if self.project.transform_method == 'homography' else TransformMethod.AFFINE
                transformer = create_transformer(self.project.control_points, method, use_validation=True)
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

    def export_to_opendrive(self):
        """Export project to OpenDrive format."""
        from .export_dialog import ExportDialog

        # Check if we have any roads
        if not self.project.roads:
            show_warning(self, "Cannot export: No roads defined in the project.\n"
                "Please create at least one road first.", "No Roads")
            return

        # Show export dialog
        dialog = ExportDialog(self.project, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.statusBar().showMessage("Export completed successfully")
        else:
            self.statusBar().showMessage("Export cancelled")

    def import_osm_data(self):
        """Import road network data from OpenStreetMap (API or file)."""
        from .osm_import_dialog import OSMImportDialog
        # Import from the 'import' module using importlib (since 'import' is a Python keyword)
        import importlib
        osm_import_module = importlib.import_module('orbit.import')
        osm_parser_module = importlib.import_module('orbit.import.osm_parser')
        OSMImporter = osm_import_module.OSMImporter
        ImportOptions = osm_import_module.ImportOptions
        ImportMode = osm_import_module.ImportMode
        DetailLevel = osm_import_module.DetailLevel
        OSMParser = osm_parser_module.OSMParser
        calculate_bbox_from_image = importlib.import_module('orbit.import.osm_to_orbit').calculate_bbox_from_image
        from orbit.export import create_transformer, TransformMethod
        from PyQt6.QtWidgets import QProgressDialog
        from PyQt6.QtCore import QCoreApplication

        # Check if georeferencing is set up
        if len(self.project.control_points) < 3:
            show_warning(self, "OpenStreetMap import requires georeferencing.\n\n"
                "Please set up at least 3 control points before importing.\n"
                "Use Tools → Georeferencing to add control points.", "Georeferencing Required")
            return

        # Check if image is loaded
        if not self.image_view.image_item:
            show_warning(self, "Please load an image before importing OSM data.", "No Image Loaded")
            return

        # Create coordinate transformer
        method = TransformMethod.HOMOGRAPHY if self.project.transform_method == 'homography' else TransformMethod.AFFINE
        transformer = create_transformer(self.project.control_points, method, use_validation=True)
        if not transformer:
            show_error(self, "Failed to create coordinate transformer.\n"
                "Please check your control points.", "Transformation Error")
            return

        # Calculate bounding box (needed for dialog, even if importing from file)
        try:
            image_width = int(self.image_view.image_item.pixmap().width())
            image_height = int(self.image_view.image_item.pixmap().height())
            bbox = calculate_bbox_from_image(image_width, image_height, transformer)
        except Exception as e:
            show_error(self, f"Failed to calculate bounding box:\n{e}", "Error")
            return

        # Show import dialog
        dialog = OSMImportDialog(bbox, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self.statusBar().showMessage("OSM import cancelled")
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
                # Import from Overpass API
                result = importer.import_osm_data(options)
            else:
                # Import from file
                with open(file_path, 'r', encoding='utf-8') as f:
                    xml_content = f.read()
                osm_data = OSMParser.parse_xml(xml_content)
                result = importer._import_from_osm_data(osm_data, options)

            progress.close()

            if result.success:
                # Show success message
                if source_type == 'file':
                    msg = f"Successfully imported from {Path(file_path).name}:\n\n"
                else:
                    msg = f"Successfully imported:\n\n"

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
        from .opendrive_import_dialog import OpenDriveImportDialog
        from .import_report_dialog import show_opendrive_import_report
        import importlib
        opendrive_import_module = importlib.import_module('orbit.import.opendrive_importer')
        OpenDriveImporter = opendrive_import_module.OpenDriveImporter
        ImportOptions = opendrive_import_module.ImportOptions
        ImportMode = opendrive_import_module.ImportMode
        from orbit.export import create_transformer, TransformMethod
        from PyQt6.QtWidgets import QProgressDialog
        from PyQt6.QtCore import QCoreApplication

        # Check if image is loaded
        if not self.image_view.image_item:
            show_warning(self, "Please load an image before importing OpenDrive data.", "No Image Loaded")
            return

        # Get image dimensions
        image_width = int(self.image_view.image_item.pixmap().width())
        image_height = int(self.image_view.image_item.pixmap().height())

        # Create coordinate transformer if available
        transformer = None
        has_georeferencing = len(self.project.control_points) >= 3
        if has_georeferencing:
            method = TransformMethod.HOMOGRAPHY if self.project.transform_method == 'homography' else TransformMethod.AFFINE
            transformer = create_transformer(self.project.control_points, method, use_validation=True)

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
                # Update UI
                self.image_view.load_project(self.project)
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
        from .properties_dialog import RoadPropertiesDialog
        from orbit.models import LineType

        # Get selected polylines from image view
        selected_polyline_id = self.image_view.selected_polyline_id
        if not selected_polyline_id:
            show_warning(self, "Please select a polyline first before creating a road.", "No Polyline Selected")
            return

        # Create a new road
        road = RoadPropertiesDialog.create_road(self.project, self, verbose=self.verbose)
        if road:
            # Add the selected polyline
            road.add_polyline(selected_polyline_id)

            # Automatically detect and set centerline
            polyline = self.project.get_polyline(selected_polyline_id)
            if polyline and polyline.line_type == LineType.CENTERLINE:
                road.centerline_id = selected_polyline_id

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
        from orbit.gui.object_selection_dialog import ObjectSelectionDialog

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
                else:
                    self.statusBar().showMessage(f"Click on the map to place {object_type.value.replace('_', ' ')}")
        else:
            # Dialog cancelled, deactivate mode
            if hasattr(self, 'object_mode_active') and self.object_mode_active:
                self.object_mode_active = False
                self.image_view.set_object_mode(False)
                self.add_object_action.setChecked(False)
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

            self.statusBar().showMessage("Show scale mode: Right-click points to display local scale factor. Left-click to pan.")
        else:
            self.statusBar().showMessage("Ready")

    def open_georeferencing(self):
        """Open georeferencing dialog."""
        from .georeference_dialog import GeoreferenceDialog

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

        # If we have an active georef dialog, send the coordinates to it
        if hasattr(self, 'georef_dialog') and self.georef_dialog:
            self.georef_dialog.set_picked_point(x, y)
            self.statusBar().showMessage(f"Point selected at ({x:.1f}, {y:.1f})")
        else:
            self.statusBar().showMessage("Ready")

    def on_mouse_moved(self, x: float, y: float):
        """Handle mouse movement in image view."""
        if x >= 0 and y >= 0:
            # Update pixel coordinates
            self.mouse_pos_label.setText(f"Pixel: ({x:.1f}, {y:.1f})")

            # Update geographic coordinates if georeferencing is available
            if self.project.has_georeferencing():
                try:
                    # Use cached transformer for performance
                    if self._cached_transformer is None:
                        from orbit.export import create_transformer, TransformMethod
                        method = TransformMethod.HOMOGRAPHY if self.project.transform_method == 'homography' else TransformMethod.AFFINE
                        self._cached_transformer = create_transformer(self.project.control_points, method, use_validation=True)

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
        else:
            self.mouse_pos_label.setText("Pixel: N/A")
            self.geo_coords_label.setText("Geo: N/A")

    def update_scale_display(self):
        """Update the scale display based on georeferencing."""
        if not self.project.has_georeferencing() or len(self.project.control_points) < 2:
            self.scale_label.setText("Scale: N/A (no georef)")
            return

        # Calculate average scale from control points
        try:
            from orbit.export import create_transformer, TransformMethod

            if self.verbose:
                print("\n" + "="*60)
                print("SCALE CALCULATION DEBUG")
                print("="*60)
                print(f"Number of control points: {len(self.project.control_points)}")
                print(f"Transform method: {self.project.transform_method}")
                print("\nControl Points:")
                for i, cp in enumerate(self.project.control_points):
                    print(f"  CP{i+1}: Pixel=({cp.pixel_x:.2f}, {cp.pixel_y:.2f}) -> "
                          f"Geo=(Lon={cp.longitude:.6f}, Lat={cp.latitude:.6f}) "
                          f"Type={'GVP' if cp.is_validation else 'GCP'}")

            method = TransformMethod.HOMOGRAPHY if self.project.transform_method == 'homography' else TransformMethod.AFFINE
            transformer = create_transformer(self.project.control_points, method, use_validation=True)

            if transformer is None:
                self.scale_label.setText("Scale: N/A (transform failed)")
                if self.verbose:
                    print("ERROR: Transformer creation failed!")
                return

            # Get scale factors directly from the transformer
            avg_scale_x, avg_scale_y = transformer.get_scale_factor()

            if self.verbose:
                print(f"\nScale factors from transformation:")
                print(f"  X (horizontal): {avg_scale_x:.6f} m/px = {avg_scale_x*100:.4f} cm/px")
                print(f"  Y (vertical):   {avg_scale_y:.6f} m/px = {avg_scale_y*100:.4f} cm/px")

                # Compute and display reprojection error
                reproj_error = transformer.compute_reprojection_error()
                if reproj_error:
                    print(f"  Reprojection RMSE: {reproj_error['rmse_meters']:.3f} meters ({reproj_error['rmse_pixels']:.2f} pixels)")

                # Compute and display validation error if validation points exist
                val_error = transformer.compute_validation_error()
                if val_error:
                    print(f"  Validation RMSE: {val_error['rmse_meters']:.3f} meters ({val_error['rmse_pixels']:.2f} pixels)")

                print("="*60 + "\n")

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
            import traceback
            print(f"Scale calculation error: {e}")
            traceback.print_exc()
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

    # Signal handlers
    def on_polyline_added(self, polyline):
        """Handle polyline added signal."""
        self.project.add_polyline(polyline)
        self.modified = True
        self.update_elements_tree()
        self.road_tree.refresh_tree()
        self.update_window_title()

    def on_polyline_modified(self, polyline_id=None):
        """Handle polyline modified signal."""
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
        self.project.remove_polyline(polyline_id)
        self.modified = True
        self.update_elements_tree()
        self.road_tree.refresh_tree()
        self.update_window_title()

    def edit_polyline_properties(self, polyline_id: str):
        """Edit properties of a polyline."""
        from .polyline_properties_dialog import PolylinePropertiesDialog

        polyline = self.project.get_polyline(polyline_id)
        if not polyline:
            return

        if PolylinePropertiesDialog.edit_polyline(polyline, self):
            # Properties were modified, update the view
            self.image_view.update_polyline(polyline_id)
            self.modified = True
            self.update_window_title()
            self.statusBar().showMessage("Polyline properties updated")

            # Update lane graphics in case this polyline is/was a centerline
            self.update_affected_road_lanes()

    def on_road_added(self, road):
        """Handle road added signal."""
        self.modified = True
        self.update_window_title()
        self.statusBar().showMessage(f"Added road: {road.name}")

    def on_road_modified(self, road_id):
        """Handle road modified signal."""
        self.modified = True
        self.update_window_title()
        # Update lane visualization with current scale
        scale_factors = self.get_current_scale()
        self.image_view.update_road_lanes(road_id, scale_factors)

    def on_road_deleted(self, road_id):
        """Handle road deleted signal."""
        self.modified = True
        self.update_window_title()
        # Remove lane visualization
        self.image_view.remove_road_lanes(road_id)

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
            self.uncertainty_none_action.setChecked(True)
            return

        # Check if image is loaded
        if not self.image_view.image_item:
            show_warning(self, "Load an image first to show uncertainty overlay.", "No Image")
            self.uncertainty_none_action.setChecked(True)
            return

        try:
            from orbit.utils import create_transformer, TransformMethod
            from orbit.utils.uncertainty_estimator import UncertaintyEstimator
            from orbit.gui.uncertainty_overlay import UncertaintyOverlay

            # Create transformer
            method = TransformMethod.HOMOGRAPHY if self.project.transform_method == 'homography' else TransformMethod.AFFINE
            transformer = create_transformer(self.project.control_points, method, use_validation=True)

            if not transformer:
                show_warning(self, "Failed to create coordinate transformer.", "Transform Error")
                self.uncertainty_none_action.setChecked(True)
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
                    self.uncertainty_none_action.setChecked(True)
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
            self.uncertainty_none_action.setChecked(True)

    def get_current_scale(self):
        """
        Get current scale from georeferencing.

        Returns:
            Tuple of (scale_x, scale_y) in m/px, or None if no georeferencing
        """
        if not self.project.has_georeferencing():
            return None

        try:
            from orbit.export import create_transformer, TransformMethod
            method = TransformMethod.HOMOGRAPHY if self.project.transform_method == 'homography' else TransformMethod.AFFINE
            transformer = create_transformer(self.project.control_points, method, use_validation=True)
            if transformer:
                return transformer.get_scale_factor()
        except Exception:
            pass

        return None

    def update_affected_road_lanes(self):
        """Update lane graphics for all roads with centerlines."""
        # Get current scale factors if available
        scale_factors = self.get_current_scale()

        # Check all roads and update lanes for those with centerlines
        for road in self.project.roads:
            if road.centerline_id:
                self.image_view.update_road_lanes(road.id, scale_factors)

    def regenerate_affected_connecting_roads(self, polyline_id: str):
        """
        Regenerate ParamPoly3D connecting roads when a road centerline endpoint is modified.

        Args:
            polyline_id: ID of the modified polyline
        """
        from orbit.models import LineType
        from orbit.utils.geometry import generate_simple_connection_path
        import math

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
            for conn_road in junction.connecting_roads:
                if (conn_road.predecessor_road_id == affected_road.id or
                    conn_road.successor_road_id == affected_road.id):
                    if conn_road.geometry_type == "parampoly3":
                        affected_junctions.append((junction, conn_road))

        # Regenerate each affected ParamPoly3D connecting road
        for junction, conn_road in affected_junctions:
            # Get predecessor and successor roads
            pred_road = self.project.get_road(conn_road.predecessor_road_id)
            succ_road = self.project.get_road(conn_road.successor_road_id)

            if not pred_road or not succ_road:
                continue

            # Get centerline polylines
            pred_polyline = self.project.get_polyline(pred_road.centerline_id)
            succ_polyline = self.project.get_polyline(succ_road.centerline_id)

            if not pred_polyline or not succ_polyline:
                continue

            # Get endpoint positions and headings
            # Predecessor endpoint (end point for "end" contact)
            if conn_road.contact_point_start == "end":
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
            if conn_road.contact_point_end == "start":
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
                num_points=20,
                tangent_scale=conn_road.tangent_scale
            )

            # Update the connecting road
            conn_road.path = path
            aU, bU, cU, dU, aV, bV, cV, dV = coeffs
            conn_road.aU = aU
            conn_road.bU = bU
            conn_road.cU = cU
            conn_road.dU = dU
            conn_road.aV = aV
            conn_road.bV = bV
            conn_road.cV = cV
            conn_road.dV = dV

            # Update graphics
            scale_factors = self.get_current_scale()
            self.image_view.update_connecting_road_graphics(conn_road.id, scale_factors)

    def on_polyline_selected_in_tree(self, polyline_id):
        """Handle polyline selection from tree."""
        # Highlight the polyline in the image view
        self.image_view.highlight_polyline(polyline_id)

    def on_polyline_deleted_in_tree(self, polyline_id):
        """Handle polyline deletion from tree."""
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
        from .junction_dialog import JunctionDialog

        # Open dialog to configure the junction
        result = JunctionDialog.create_junction(self.project, junction.center_point, self)
        if result:
            self.project.add_junction(result)
            self.image_view.add_junction_graphics(result)
            self.modified = True
            self.update_elements_tree()
            self.update_window_title()
            self.statusBar().showMessage(f"Added junction: {result.name}. Click to add another or press Escape to finish.")

    def on_junction_modified(self, junction_id):
        """Handle junction modified signal."""
        self.modified = True
        self.image_view.refresh_junction_graphics(junction_id)
        self.update_elements_tree()
        self.update_window_title()

    def on_junction_deleted(self, junction_id):
        """Handle junction deleted signal."""
        self.project.remove_junction(junction_id)
        self.image_view.remove_junction_graphics(junction_id)
        self.modified = True
        self.update_elements_tree()
        self.update_window_title()

    def on_junction_selected_in_tree(self, junction_id: str):
        """Handle junction selection in elements tree."""
        self.image_view.highlight_junction(junction_id)

    def edit_junction_properties(self, junction_id: str):
        """Edit properties of a junction."""
        from .junction_dialog import JunctionDialog

        junction = self.project.get_junction(junction_id)
        if not junction:
            return

        result = JunctionDialog.edit_junction(junction, self.project, self)
        if result:
            # Properties were modified, update the view
            self.image_view.refresh_junction_graphics(junction_id)
            self.modified = True
            self.update_window_title()
            self.statusBar().showMessage(f"Junction properties updated: {result.name}")

    def on_connecting_road_selected(self, connecting_road_id: str):
        """Handle connecting road selection in elements tree."""
        # Highlight the connecting road in the view
        if connecting_road_id in self.image_view.connecting_road_centerline_items:
            self.image_view.connecting_road_centerline_items[connecting_road_id].set_selected(True)
            # Deselect previously selected item (if any)
            # TODO: Track previous selection and deselect it

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
        """Handle connecting road lane click in the view - select it in the elements tree."""
        # Select the corresponding item in the elements tree
        self.elements_tree.select_connecting_road_lane(connecting_road_id, lane_id)
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

    def on_signal_placement_requested(self, x: float, y: float):
        """Handle signal placement request - show selection dialog."""
        from orbit.gui.signal_selection_dialog import SignalSelectionDialog
        from orbit.models.signal import Signal

        # Show dialog to select signal type
        dialog = SignalSelectionDialog(self)
        if dialog.exec():
            signal_type, value, speed_unit = dialog.get_selection()
            if signal_type:
                # Create signal at clicked position
                signal = Signal(
                    position=(x, y),
                    signal_type=signal_type,
                    value=value,
                    speed_unit=speed_unit
                )

                # Find closest road and assign
                closest_road_id = self.project.find_closest_road((x, y))
                if closest_road_id:
                    signal.road_id = closest_road_id
                    road = self.project.get_road(closest_road_id)
                    if road and road.centerline_id:
                        centerline_polyline = self.project.get_polyline(road.centerline_id)
                        if centerline_polyline:
                            # Calculate s-position
                            # Note: Orientation defaults to '+' (forward) and can be adjusted in properties dialog
                            signal.s_position = signal.calculate_s_position(centerline_polyline.points)

                # Add to project and view
                self.project.add_signal(signal)
                self.image_view.add_signal_graphics(signal)
                self.modified = True
                self.update_elements_tree()
                self.update_window_title()
                self.statusBar().showMessage(f"Added signal: {signal.get_display_name()}. Click to add another or press Escape to finish.")

    def on_signal_added(self, signal):
        """Handle signal added signal."""
        # This is emitted by signal graphics when dragged
        self.modified = True
        self.update_elements_tree()
        self.update_window_title()

    def on_signal_modified(self, signal_id):
        """Handle signal modified signal."""
        self.modified = True
        self.image_view.refresh_signal_graphics(signal_id)
        self.update_elements_tree()
        self.update_window_title()

    def on_signal_deleted(self, signal_id):
        """Handle signal deleted signal."""
        self.project.remove_signal(signal_id)
        self.image_view.remove_signal_graphics(signal_id)
        self.modified = True
        self.update_elements_tree()
        self.update_window_title()

    def on_signal_selected_in_tree(self, signal_id: str):
        """Handle signal selected in elements tree."""
        self.image_view.select_signal(signal_id)

    def on_signal_selected_in_view(self, signal_id: str):
        """Handle signal selected in view - update tree selection."""
        self.elements_tree.select_signal(signal_id)

    def on_object_selected_in_tree(self, object_id: str):
        """Handle object selected in elements tree."""
        self.image_view.select_object(object_id)

    def on_object_selected_in_view(self, object_id: str):
        """Handle object selected in view - update tree selection."""
        self.elements_tree.select_object(object_id)

    def on_polyline_selected_in_view(self, polyline_id: str):
        """Handle polyline selected in view."""
        # Polylines are not in the elements tree, just keep them highlighted in view
        pass

    def on_junction_selected_in_view(self, junction_id: str):
        """Handle junction selected in view - update tree selection."""
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

    def edit_signal_properties(self, signal_id: str):
        """Edit properties of a signal."""
        from orbit.gui.signal_properties_dialog import SignalPropertiesDialog

        signal = self.project.get_signal(signal_id)
        if not signal:
            return

        dialog = SignalPropertiesDialog(signal, self.project, self)
        if dialog.exec():
            # Properties were modified, update the view
            self.image_view.refresh_signal_graphics(signal_id)
            self.modified = True
            self.update_elements_tree()
            self.update_window_title()
            self.statusBar().showMessage(f"Signal properties updated: {signal.get_display_name()}")

    def on_object_placement_requested(self, x: float, y: float, object_type):
        """Handle object placement request from ImageView (for point objects)."""
        from orbit.models import RoadObject

        # Create object at clicked position
        obj = RoadObject(
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

        # Get scale factor for graphics
        scale_factor = 0.0
        if hasattr(self, '_cached_transformer') and self._cached_transformer:
            scale_x, scale_y = self._cached_transformer.get_scale_factor()
            scale_factor = scale_x if scale_x else 0.0

        # Add to project and view
        self.project.add_object(obj)
        self.image_view.add_object_graphics(obj, scale_factor)
        self.modified = True
        self.update_elements_tree()
        self.update_window_title()
        self.statusBar().showMessage(f"Added object: {obj.get_display_name()}. Click to add another or toggle off to finish.")

    def on_object_added(self, obj):
        """Handle object added signal (for guardrails)."""
        from orbit.models import RoadObject

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

        # Get scale factor
        scale_factor = 0.0
        if hasattr(self, '_cached_transformer') and self._cached_transformer:
            scale_x, scale_y = self._cached_transformer.get_scale_factor()
            scale_factor = scale_x if scale_x else 0.0

        # Add to project and view
        self.project.add_object(obj)
        self.image_view.add_object_graphics(obj, scale_factor)
        self.modified = True
        self.update_elements_tree()
        self.update_window_title()
        self.statusBar().showMessage(f"Guardrail added. Click and drag to add another or toggle off to finish.")

    def on_object_modified(self, object_id):
        """Handle object modified signal."""
        self.modified = True
        self.image_view.refresh_object_graphics(object_id)
        self.update_elements_tree()
        self.update_window_title()

    def on_object_deleted(self, object_id):
        """Handle object deleted signal."""
        self.project.remove_object(object_id)
        self.image_view.remove_object_graphics(object_id)
        self.modified = True
        self.update_elements_tree()
        self.update_window_title()

    def edit_object_properties(self, object_id: str):
        """Edit properties of an object."""
        from orbit.gui.object_properties_dialog import ObjectPropertiesDialog

        obj = self.project.get_object(object_id)
        if not obj:
            return

        dialog = ObjectPropertiesDialog(obj, self.project, self)
        if dialog.exec():
            # Properties were modified, update the view
            self.image_view.refresh_object_graphics(object_id)
            self.modified = True
            self.update_elements_tree()
            self.update_window_title()
            self.statusBar().showMessage(f"Object properties updated: {obj.get_display_name()}")

    def on_section_split_requested(self, road_id: str, polyline_id: str, point_index: int):
        """
        Handle section split request from ImageView.

        Args:
            road_id: ID of the road whose section should be split
            polyline_id: ID of the centerline polyline
            point_index: Index of the point where to split
        """
        road = self.project.get_road(road_id)
        if not road:
            return

        polyline = self.project.get_polyline(polyline_id)
        if not polyline:
            return

        # Perform the split
        success = road.split_section_at_point(point_index, polyline.points)

        if success:
            self.modified = True
            self.road_tree.refresh_tree()
            self.update_window_title()
            self.statusBar().showMessage("Lane section split successfully")
            # Refresh lane graphics to show new section polygons
            self.update_affected_road_lanes()
        else:
            show_warning(self, "Failed to split lane section. The point may be outside section boundaries.", "Split Failed")

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
        from orbit.gui.lane_properties_dialog import LanePropertiesDialog

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
        if LanePropertiesDialog.edit_lane(lane, self.project, road_id, self):
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
        from orbit.gui.lane_properties_dialog import LanePropertiesDialog

        # Find the connecting road in junctions
        connecting_road = None
        parent_junction = None
        for junction in self.project.junctions:
            for cr in junction.connecting_roads:
                if cr.id == connecting_road_id:
                    connecting_road = cr
                    parent_junction = junction
                    break
            if connecting_road:
                break

        if not connecting_road:
            return

        # Find the lane
        lane = connecting_road.get_lane(lane_id)
        if not lane:
            return
        # Open lane properties dialog (without project/road_id since connecting roads are standalone)
        if LanePropertiesDialog.edit_lane(lane, None, None, self):
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
        from PyQt6.QtGui import QPixmap
        from pathlib import Path

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

        msg_box.setText(
            "<h2>ORBIT</h2>"
            "<p><b>OpenDrive Road Builder from Imagery Tool</b></p>"
            "<p>Version 0.2.0</p>"
        )
        msg_box.setInformativeText(
            "A tool for annotating roads in drone/aerial/satellite imagery "
            "and exporting to ASAM OpenDrive format."
        )
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

    def closeEvent(self, event):
        """Handle window close event."""
        if self.check_unsaved_changes():
            # Save window geometry
            self.settings.setValue("mainwindow/geometry", self.saveGeometry())
            self.settings.setValue("mainwindow/state", self.saveState())
            event.accept()
        else:
            event.ignore()

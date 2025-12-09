"""
Junction dialog for ORBIT.

Allows editing of junction properties and road connections.
"""

from typing import Optional, List

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QComboBox, QPushButton,
    QListWidget, QLabel, QMessageBox,
    QListWidgetItem, QGroupBox, QToolButton, QWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QDoubleSpinBox, QSpinBox,
    QScrollArea, QFrame
)
from PyQt6.QtCore import Qt

from orbit.models import Junction, JunctionConnection, Project
from orbit.models.junction import (
    JunctionBoundary, JunctionBoundarySegment,
    JunctionElevationGrid, JunctionElevationGridPoint
)
from .base_dialog import BaseDialog, InfoIconLabel
from ..utils.message_helpers import show_warning


class JunctionDialog(BaseDialog):
    """Dialog for editing junction properties."""

    def __init__(self, junction: Optional[Junction] = None, project: Optional[Project] = None, parent=None):
        super().__init__("Junction Properties", parent, min_width=500, min_height=400)

        self.junction = junction if junction else Junction()
        self.project = project
        self.setup_ui()
        self.load_properties()

    def setup_ui(self):
        """Setup the dialog UI."""
        # Basic properties group
        basic_layout = self.add_form_group("Basic Properties")

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Enter junction name")
        basic_layout.addRow("Junction Name:", self.name_edit)

        self.type_combo = QComboBox()
        self.type_combo.addItems(["default", "virtual"])
        self.type_combo.setToolTip("Junction type: 'default' for normal intersections, 'virtual' for special cases")
        basic_layout.addRow("Junction Type:", self.type_combo)

        # Center point info
        self.center_label = QLabel("Not set")
        basic_layout.addRow("Center Point:", self.center_label)

        # Connected roads section - custom layout
        from PyQt6.QtWidgets import QGroupBox
        roads_group = QGroupBox()
        roads_layout = QVBoxLayout()

        roads_title = InfoIconLabel(
            "Connected Roads",
            "Select roads that connect at this junction"
        )
        roads_layout.addWidget(roads_title)

        # Available roads list
        available_label = QLabel("Available Roads:")
        roads_layout.addWidget(available_label)

        self.available_roads_list = QListWidget()
        self.available_roads_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        roads_layout.addWidget(self.available_roads_list)

        # Buttons to add/remove roads
        button_layout = QHBoxLayout()
        self.add_road_btn = QPushButton("Add Selected →")
        self.add_road_btn.clicked.connect(self.add_selected_roads)
        button_layout.addWidget(self.add_road_btn)

        self.remove_road_btn = QPushButton("← Remove Selected")
        self.remove_road_btn.clicked.connect(self.remove_selected_roads)
        button_layout.addWidget(self.remove_road_btn)
        roads_layout.addLayout(button_layout)

        # Connected roads list
        connected_label = QLabel("Connected Roads:")
        roads_layout.addWidget(connected_label)

        self.connected_roads_list = QListWidget()
        self.connected_roads_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        roads_layout.addWidget(self.connected_roads_list)

        roads_group.setLayout(roads_layout)
        self.get_main_layout().addWidget(roads_group)

        # Junction Connections section
        connections_group = QGroupBox()
        connections_layout = QVBoxLayout()

        connections_title = InfoIconLabel(
            "Junction Connections",
            "Automatically generate connecting roads and lane links based on junction geometry"
        )
        connections_layout.addWidget(connections_title)

        # Connection summary label
        self.connections_summary_label = QLabel("No connections generated yet")
        self.connections_summary_label.setStyleSheet("font-weight: bold;")
        connections_layout.addWidget(self.connections_summary_label)

        # Auto-generate button
        self.auto_generate_btn = QPushButton("Auto-Generate Connections")
        self.auto_generate_btn.setToolTip(
            "Automatically analyze junction geometry and generate:\n"
            "• Connecting roads with smooth paths\n"
            "• Lane-to-lane connections\n"
            "• Turn type classification (straight, left, right, u-turn)"
        )
        self.auto_generate_btn.clicked.connect(self.auto_generate_connections)
        connections_layout.addWidget(self.auto_generate_btn)

        connections_group.setLayout(connections_layout)
        self.get_main_layout().addWidget(connections_group)

        # V1.8 Features (collapsible)
        self._setup_v18_section()

        # Create standard OK/Cancel buttons
        self.create_button_box()

    def _setup_v18_section(self):
        """Setup the collapsible V1.8 features section (boundary, elevation grid) with scroll area."""
        # Create collapsible toggle
        self.v18_toggle = QToolButton()
        self.v18_toggle.setStyleSheet("QToolButton { border: none; }")
        self.v18_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.v18_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.v18_toggle.setText("OpenDRIVE 1.8 Features (Boundary, Elevation Grid)")
        self.v18_toggle.setCheckable(True)
        self.v18_toggle.setChecked(False)
        self.v18_toggle.clicked.connect(self._toggle_v18)

        self.get_main_layout().addWidget(self.v18_toggle)

        # Scroll area for the V1.8 content
        self.v18_scroll = QScrollArea()
        self.v18_scroll.setWidgetResizable(True)
        self.v18_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.v18_scroll.setMaximumHeight(350)

        # Container for V1.8 content
        self.v18_widget = QWidget()
        v18_layout = QVBoxLayout(self.v18_widget)
        v18_layout.setContentsMargins(10, 5, 10, 10)

        # Boundary section
        boundary_title = InfoIconLabel(
            "Junction Boundary",
            "Defines the area enclosing the junction (counter-clockwise segments)"
        )
        v18_layout.addWidget(boundary_title)

        self.boundary_table = QTableWidget(0, 4)
        self.boundary_table.setHorizontalHeaderLabels(["Type", "Road ID", "Lane ID", "Connection ID"])
        self.boundary_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.boundary_table.setMinimumHeight(100)
        v18_layout.addWidget(self.boundary_table)

        boundary_btn_widget = QWidget()
        boundary_btn_layout = QHBoxLayout(boundary_btn_widget)
        boundary_btn_layout.setContentsMargins(0, 0, 0, 0)
        boundary_btn_layout.addStretch()
        self.add_boundary_btn = QPushButton("+ Add")
        self.add_boundary_btn.clicked.connect(self._add_boundary_row)
        boundary_btn_layout.addWidget(self.add_boundary_btn)
        self.remove_boundary_btn = QPushButton("- Remove")
        self.remove_boundary_btn.clicked.connect(self._remove_boundary_row)
        boundary_btn_layout.addWidget(self.remove_boundary_btn)
        v18_layout.addWidget(boundary_btn_widget)

        # Elevation Grid section
        elev_title = InfoIconLabel(
            "Elevation Grid",
            "Grid of elevation points across the junction surface"
        )
        v18_layout.addWidget(elev_title)

        # Grid spacing
        spacing_widget = QWidget()
        spacing_layout = QHBoxLayout(spacing_widget)
        spacing_layout.setContentsMargins(0, 0, 0, 0)
        spacing_layout.addWidget(QLabel("Grid Spacing:"))
        self.grid_spacing_spin = QDoubleSpinBox()
        self.grid_spacing_spin.setRange(0.1, 100.0)
        self.grid_spacing_spin.setValue(1.0)
        self.grid_spacing_spin.setSuffix(" m")
        self.grid_spacing_spin.setToolTip("Spacing between elevation grid points")
        spacing_layout.addWidget(self.grid_spacing_spin)
        spacing_layout.addStretch()
        v18_layout.addWidget(spacing_widget)

        self.elevation_table = QTableWidget(0, 3)
        self.elevation_table.setHorizontalHeaderLabels(["Center", "Left", "Right"])
        self.elevation_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.elevation_table.setMinimumHeight(100)
        v18_layout.addWidget(self.elevation_table)

        elev_btn_widget = QWidget()
        elev_btn_layout = QHBoxLayout(elev_btn_widget)
        elev_btn_layout.setContentsMargins(0, 0, 0, 0)
        elev_btn_layout.addStretch()
        self.add_elev_btn = QPushButton("+ Add")
        self.add_elev_btn.clicked.connect(self._add_elevation_row)
        elev_btn_layout.addWidget(self.add_elev_btn)
        self.remove_elev_btn = QPushButton("- Remove")
        self.remove_elev_btn.clicked.connect(self._remove_elevation_row)
        elev_btn_layout.addWidget(self.remove_elev_btn)
        v18_layout.addWidget(elev_btn_widget)

        # Put v18_widget in scroll area
        self.v18_scroll.setWidget(self.v18_widget)
        self.v18_scroll.setVisible(False)
        self.get_main_layout().addWidget(self.v18_scroll)

    def _toggle_v18(self, checked: bool):
        """Toggle visibility of V1.8 section."""
        self.v18_scroll.setVisible(checked)
        if checked:
            self.v18_toggle.setArrowType(Qt.ArrowType.DownArrow)
        else:
            self.v18_toggle.setArrowType(Qt.ArrowType.RightArrow)

    def _add_boundary_row(self):
        """Add a new boundary segment row."""
        row = self.boundary_table.rowCount()
        self.boundary_table.insertRow(row)
        # Default values
        type_combo = QComboBox()
        type_combo.addItems(["lane", "joint"])
        self.boundary_table.setCellWidget(row, 0, type_combo)
        self.boundary_table.setItem(row, 1, QTableWidgetItem(""))  # road_id
        self.boundary_table.setItem(row, 2, QTableWidgetItem(""))  # boundary_lane
        self.boundary_table.setItem(row, 3, QTableWidgetItem(""))  # connection_id

    def _remove_boundary_row(self):
        """Remove the selected boundary row."""
        current_row = self.boundary_table.currentRow()
        if current_row >= 0:
            self.boundary_table.removeRow(current_row)

    def _add_elevation_row(self):
        """Add a new elevation grid point row."""
        row = self.elevation_table.rowCount()
        self.elevation_table.insertRow(row)
        # Default values
        self.elevation_table.setItem(row, 0, QTableWidgetItem("0.0"))  # center
        self.elevation_table.setItem(row, 1, QTableWidgetItem("0.0"))  # left
        self.elevation_table.setItem(row, 2, QTableWidgetItem("0.0"))  # right

    def _remove_elevation_row(self):
        """Remove the selected elevation row."""
        current_row = self.elevation_table.currentRow()
        if current_row >= 0:
            self.elevation_table.removeRow(current_row)

    def _load_boundary_table(self):
        """Load boundary data into the table."""
        self.boundary_table.setRowCount(0)
        if self.junction.boundary is None:
            return
        for segment in self.junction.boundary.segments:
            row = self.boundary_table.rowCount()
            self.boundary_table.insertRow(row)
            # Type combo
            type_combo = QComboBox()
            type_combo.addItems(["lane", "joint"])
            type_combo.setCurrentText(segment.segment_type)
            self.boundary_table.setCellWidget(row, 0, type_combo)
            # Other fields
            self.boundary_table.setItem(row, 1, QTableWidgetItem(segment.road_id or ""))
            self.boundary_table.setItem(row, 2, QTableWidgetItem(str(segment.boundary_lane) if segment.boundary_lane is not None else ""))
            self.boundary_table.setItem(row, 3, QTableWidgetItem(segment.connection_id or ""))

    def _load_elevation_table(self):
        """Load elevation grid data into the table."""
        self.elevation_table.setRowCount(0)
        if self.junction.elevation_grid is None:
            return
        # Set grid spacing
        if self.junction.elevation_grid.grid_spacing:
            try:
                self.grid_spacing_spin.setValue(float(self.junction.elevation_grid.grid_spacing))
            except ValueError:
                pass
        # Load elevation points
        for point in self.junction.elevation_grid.elevations:
            row = self.elevation_table.rowCount()
            self.elevation_table.insertRow(row)
            self.elevation_table.setItem(row, 0, QTableWidgetItem(point.center or "0.0"))
            self.elevation_table.setItem(row, 1, QTableWidgetItem(point.left or "0.0"))
            self.elevation_table.setItem(row, 2, QTableWidgetItem(point.right or "0.0"))

    def _get_boundary_from_table(self) -> Optional[JunctionBoundary]:
        """Get boundary data from table."""
        if self.boundary_table.rowCount() == 0:
            return None
        segments = []
        for row in range(self.boundary_table.rowCount()):
            type_combo = self.boundary_table.cellWidget(row, 0)
            segment_type = type_combo.currentText() if type_combo else "lane"

            road_id_item = self.boundary_table.item(row, 1)
            road_id = road_id_item.text() if road_id_item and road_id_item.text() else None

            lane_item = self.boundary_table.item(row, 2)
            boundary_lane = None
            if lane_item and lane_item.text():
                try:
                    boundary_lane = int(lane_item.text())
                except ValueError:
                    pass

            conn_item = self.boundary_table.item(row, 3)
            connection_id = conn_item.text() if conn_item and conn_item.text() else None

            segments.append(JunctionBoundarySegment(
                segment_type=segment_type,
                road_id=road_id,
                boundary_lane=boundary_lane,
                connection_id=connection_id
            ))
        return JunctionBoundary(segments=segments)

    def _get_elevation_from_table(self) -> Optional[JunctionElevationGrid]:
        """Get elevation grid data from table."""
        if self.elevation_table.rowCount() == 0:
            return None
        elevations = []
        for row in range(self.elevation_table.rowCount()):
            center_item = self.elevation_table.item(row, 0)
            left_item = self.elevation_table.item(row, 1)
            right_item = self.elevation_table.item(row, 2)
            elevations.append(JunctionElevationGridPoint(
                center=center_item.text() if center_item else "0.0",
                left=left_item.text() if left_item else "0.0",
                right=right_item.text() if right_item else "0.0"
            ))
        return JunctionElevationGrid(
            grid_spacing=str(self.grid_spacing_spin.value()),
            elevations=elevations
        )

    def load_properties(self):
        """Load data from the junction object."""
        self.name_edit.setText(self.junction.name)

        # Set junction type
        index = self.type_combo.findText(self.junction.junction_type)
        if index >= 0:
            self.type_combo.setCurrentIndex(index)

        # Set center point display
        if self.junction.center_point:
            x, y = self.junction.center_point
            self.center_label.setText(f"({x:.1f}, {y:.1f}) pixels")

        # Load roads from project
        if self.project:
            for road in self.project.roads:
                road_id_short = road.id[:8]
                display_text = f"{road.name} ({road_id_short}, {road.road_type.value})"
                if road.id not in self.junction.connected_road_ids:
                    item = QListWidgetItem(display_text)
                    item.setData(Qt.ItemDataRole.UserRole, road.id)
                    self.available_roads_list.addItem(item)
                else:
                    item = QListWidgetItem(display_text)
                    item.setData(Qt.ItemDataRole.UserRole, road.id)
                    self.connected_roads_list.addItem(item)

        # Update connection summary
        self.update_connection_summary()

        # Load V1.8 data
        self._load_boundary_table()
        self._load_elevation_table()

        # Auto-expand V1.8 section if data exists
        has_v18_data = (
            self.junction.boundary is not None or
            self.junction.elevation_grid is not None
        )
        if has_v18_data:
            self.v18_toggle.setChecked(True)
            self._toggle_v18(True)

    def add_selected_roads(self):
        """Add selected roads from available to connected."""
        selected_items = self.available_roads_list.selectedItems()
        for item in selected_items:
            road_id = item.data(Qt.ItemDataRole.UserRole)
            # Remove from available
            row = self.available_roads_list.row(item)
            self.available_roads_list.takeItem(row)
            # Add to connected
            new_item = QListWidgetItem(item.text())
            new_item.setData(Qt.ItemDataRole.UserRole, road_id)
            self.connected_roads_list.addItem(new_item)

    def remove_selected_roads(self):
        """Remove selected roads from connected to available."""
        selected_items = self.connected_roads_list.selectedItems()
        for item in selected_items:
            road_id = item.data(Qt.ItemDataRole.UserRole)
            # Remove from connected
            row = self.connected_roads_list.row(item)
            self.connected_roads_list.takeItem(row)
            # Add back to available
            new_item = QListWidgetItem(item.text())
            new_item.setData(Qt.ItemDataRole.UserRole, road_id)
            self.available_roads_list.addItem(new_item)

    def save_data(self):
        """Save data back to the junction object."""
        self.junction.name = self.name_edit.text().strip() or "Unnamed Junction"
        self.junction.junction_type = self.type_combo.currentText()

        # Update connected roads
        self.junction.connected_road_ids.clear()
        for i in range(self.connected_roads_list.count()):
            item = self.connected_roads_list.item(i)
            road_id = item.data(Qt.ItemDataRole.UserRole)
            self.junction.connected_road_ids.append(road_id)

        # Clear any stale road-to-road predecessor/successor links between roads
        # that now connect through this junction (OpenDRIVE compliance)
        if self.project:
            import importlib
            junction_analyzer = importlib.import_module('orbit.import.junction_analyzer')
            roads_dict = {road.id: road for road in self.project.roads}
            junction_analyzer.clear_cross_junction_links(self.junction, roads_dict)

        # Save V1.8 data
        self.junction.boundary = self._get_boundary_from_table()
        self.junction.elevation_grid = self._get_elevation_from_table()

    def accept(self):
        """Handle dialog acceptance."""
        # Validate at least 2 roads
        if self.connected_roads_list.count() < 2:
            show_warning(self, "A junction must connect at least 2 roads.", "Insufficient Roads")
            return

        self.save_data()
        super().accept()

    def get_junction(self) -> Junction:
        """Get the junction object with updated properties."""
        return self.junction

    def set_center_point(self, x: float, y: float):
        """Set the center point of the junction."""
        self.junction.center_point = (x, y)
        self.center_label.setText(f"({x:.1f}, {y:.1f}) pixels")

    def update_connection_summary(self):
        """Update the connection summary label."""
        summary = self.junction.get_connection_summary()
        total = summary['total_connections']

        if total == 0:
            self.connections_summary_label.setText("No connections generated yet")
            self.connections_summary_label.setStyleSheet("font-weight: bold; color: gray;")
        else:
            text = f"✓ {total} connection(s): "
            parts = []
            if summary['straight'] > 0:
                parts.append(f"{summary['straight']} straight")
            if summary['left'] > 0:
                parts.append(f"{summary['left']} left")
            if summary['right'] > 0:
                parts.append(f"{summary['right']} right")
            if summary['uturn'] > 0:
                parts.append(f"{summary['uturn']} u-turn")

            text += ", ".join(parts)
            self.connections_summary_label.setText(text)
            self.connections_summary_label.setStyleSheet("font-weight: bold; color: green;")

    def auto_generate_connections(self):
        """Auto-generate junction connections based on geometry."""
        if not self.project:
            QMessageBox.warning(
                self,
                "No Project",
                "Cannot generate connections without a project context."
            )
            return

        # First save current road selections
        self.save_data()

        # Check if we have enough roads
        if len(self.junction.connected_road_ids) < 2:
            QMessageBox.warning(
                self,
                "Insufficient Roads",
                "At least 2 roads must be connected to generate junction connections.\n\n"
                "Please add roads to the junction first."
            )
            return

        # Import the junction analyzer (using importlib to avoid 'import' keyword conflict)
        try:
            import importlib
            junction_analyzer = importlib.import_module('orbit.import.junction_analyzer')
            generate_junction_connections = junction_analyzer.generate_junction_connections
        except ImportError as e:
            QMessageBox.critical(
                self,
                "Import Error",
                f"Failed to import junction analyzer: {e}"
            )
            return

        # Build dictionaries for roads and polylines
        roads_dict = {road.id: road for road in self.project.roads}
        polylines_dict = {p.id: p for p in self.project.polylines}

        # Get scale factor if georeferenced
        scale = 1.0  # Default for non-georeferenced projects
        if len(self.project.control_points) >= 3:
            try:
                from orbit.export.coordinate_transformer import CoordinateTransformer
                transformer = CoordinateTransformer(self.project.control_points)
                scale_x, scale_y = transformer.get_scale_factor()
                scale = (scale_x + scale_y) / 2.0
            except Exception:
                # Use default scale if transformer fails
                scale = 1.0

        # Clear existing connections
        self.junction.connecting_roads.clear()
        self.junction.lane_connections.clear()

        # Generate connections
        try:
            generate_junction_connections(self.junction, roads_dict, polylines_dict, scale)

            # Update summary
            self.update_connection_summary()

            # Show success message
            summary = self.junction.get_connection_summary()
            QMessageBox.information(
                self,
                "Connections Generated",
                f"Successfully generated {summary['total_connections']} connection(s):\n\n"
                f"• Straight: {summary['straight']}\n"
                f"• Left turns: {summary['left']}\n"
                f"• Right turns: {summary['right']}\n"
                f"• U-turns: {summary['uturn']}\n\n"
                f"Connecting roads: {len(self.junction.connecting_roads)}\n"
                f"Lane connections: {len(self.junction.lane_connections)}"
            )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Generation Failed",
                f"Failed to generate connections:\n\n{str(e)}"
            )
            import traceback
            traceback.print_exc()

    @classmethod
    def edit_junction(cls, junction: Junction, project: Project, parent=None) -> Optional[Junction]:
        """
        Show dialog to edit a junction's properties.

        Args:
            junction: Junction to edit
            project: Project containing the junction
            parent: Parent widget

        Returns:
            The modified junction if accepted, None if cancelled
        """
        dialog = cls(junction, project, parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.get_junction()
        return None

    @classmethod
    def create_junction(cls, project: Project, center_point: Optional[tuple] = None, parent=None) -> Optional[Junction]:
        """
        Show dialog to create a new junction.

        Args:
            project: Project to contain the new junction
            center_point: Optional initial center point (x, y)
            parent: Parent widget

        Returns:
            The new junction if accepted, None if cancelled
        """
        junction = Junction()
        if center_point:
            junction.center_point = center_point

        dialog = cls(junction, project, parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.get_junction()
        return None

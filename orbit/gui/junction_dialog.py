"""
Junction dialog for ORBIT.

Allows editing of junction properties and road connections.
"""

from typing import Optional, List

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLineEdit, QComboBox, QPushButton,
    QListWidget, QLabel, QMessageBox,
    QListWidgetItem, QGroupBox
)
from PyQt6.QtCore import Qt

from orbit.models import Junction, JunctionConnection, Project
from orbit.gui.base_dialog import BaseDialog
from orbit.gui.message_helpers import show_warning


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
        roads_group = QGroupBox("Connected Roads")
        roads_layout = QVBoxLayout()

        roads_info_label = QLabel("<i>Select roads that connect at this junction</i>")
        roads_layout.addWidget(roads_info_label)

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
        connections_group = QGroupBox("Junction Connections")
        connections_layout = QVBoxLayout()

        connections_info_label = QLabel(
            "<i>Automatically generate connecting roads and lane links based on junction geometry</i>"
        )
        connections_info_label.setWordWrap(True)
        connections_layout.addWidget(connections_info_label)

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

        # Info section
        info_label = QLabel(
            "<i>Note: At least 2 roads should be connected to a junction.</i>"
        )
        info_label.setWordWrap(True)
        self.get_main_layout().addWidget(info_label)

        # Create standard OK/Cancel buttons
        self.create_button_box()

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
                if road.id not in self.junction.connected_road_ids:
                    item = QListWidgetItem(f"{road.name} ({road.road_type.value})")
                    item.setData(Qt.ItemDataRole.UserRole, road.id)
                    self.available_roads_list.addItem(item)
                else:
                    item = QListWidgetItem(f"{road.name} ({road.road_type.value})")
                    item.setData(Qt.ItemDataRole.UserRole, road.id)
                    self.connected_roads_list.addItem(item)

        # Update connection summary
        self.update_connection_summary()

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

        # Clear existing connections
        self.junction.connecting_roads.clear()
        self.junction.lane_connections.clear()

        # Generate connections
        try:
            generate_junction_connections(self.junction, roads_dict, polylines_dict)

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

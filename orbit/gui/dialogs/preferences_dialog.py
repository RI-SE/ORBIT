"""
Preferences dialog for ORBIT.

Allows configuring project-level settings including georeferencing method,
traffic side, and country code.
"""

from PyQt6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QLabel, QLineEdit
)

from orbit.models import Project
from .base_dialog import BaseDialog


class PreferencesDialog(BaseDialog):
    """Dialog for configuring project preferences."""

    def __init__(self, project: Project, parent=None):
        super().__init__("Project Preferences", parent, min_width=500)

        self.project = project
        self.setup_ui()
        self.load_properties()

    def setup_ui(self):
        """Setup the dialog UI."""
        # Map information section
        map_layout = self.add_form_group("Map Information")

        # Map name
        self.map_name_edit = QLineEdit()
        self.map_name_edit.setPlaceholderText("e.g., City Center, Highway Junction")
        self.map_name_edit.setToolTip("Name of the map for OpenDrive export (defaults to image filename)")

        map_name_help = QLabel(
            "<small>This name will be used in the OpenDrive header. "
            "Defaults to the image filename when loaded.</small>"
        )
        map_name_help.setWordWrap(True)
        map_name_help.setStyleSheet("QLabel { color: gray; }")

        map_layout.addRow("Map Name:", self.map_name_edit)
        map_layout.addRow("", map_name_help)

        # Georeferencing section
        georef_layout = self.add_form_group("Georeferencing")

        # Transformation method
        self.transform_method_combo = QComboBox()
        self.transform_method_combo.addItem("Affine (for orthophotos, satellite imagery)", "affine")
        self.transform_method_combo.addItem("Homography (for oblique drone imagery)", "homography")

        transform_help = QLabel(
            "<small><b>Affine:</b> Best for nadir (straight down) aerial/satellite images. "
            "Requires 3+ control points.<br>"
            "<b>Homography:</b> Best for tilted camera drone images with perspective. "
            "Requires 4+ control points.</small>"
        )
        transform_help.setWordWrap(True)
        transform_help.setStyleSheet("QLabel { color: gray; }")

        georef_layout.addRow("Transformation Method:", self.transform_method_combo)
        georef_layout.addRow("", transform_help)

        # Traffic and location section
        traffic_layout = self.add_form_group("Traffic and Location")

        # Right-hand traffic
        self.traffic_combo = QComboBox()
        self.traffic_combo.addItem("Right-hand traffic", True)
        self.traffic_combo.addItem("Left-hand traffic", False)

        traffic_help = QLabel(
            "<small>Right-hand: Vehicles drive on right side (USA, Europe, etc.)<br>"
            "Left-hand: Vehicles drive on left side (UK, Japan, etc.)</small>"
        )
        traffic_help.setWordWrap(True)
        traffic_help.setStyleSheet("QLabel { color: gray; }")

        # Country code
        self.country_code_edit = QLineEdit()
        self.country_code_edit.setText("se")
        self.country_code_edit.setMaxLength(2)
        self.country_code_edit.setPlaceholderText("e.g., se, us, de")
        self.country_code_edit.setToolTip("Two-letter ISO 3166-1 country code (lowercase)")
        self.country_code_edit.setMaximumWidth(100)

        country_help = QLabel(
            "<small>ISO 3166-1 two-letter country code for OpenDrive export.</small>"
        )
        country_help.setWordWrap(True)
        country_help.setStyleSheet("QLabel { color: gray; }")

        traffic_layout.addRow("Traffic Side:", self.traffic_combo)
        traffic_layout.addRow("", traffic_help)
        traffic_layout.addRow("Country Code:", self.country_code_edit)
        traffic_layout.addRow("", country_help)

        # Junction settings section
        junction_layout = self.add_form_group("Junction Settings")

        # Junction offset distance
        self.junction_offset_spin = QDoubleSpinBox()
        self.junction_offset_spin.setRange(0.0, 50.0)  # 0-50 meters
        self.junction_offset_spin.setSingleStep(1.0)
        self.junction_offset_spin.setDecimals(1)
        self.junction_offset_spin.setSuffix(" m")
        self.junction_offset_spin.setToolTip("Distance to offset road endpoints from junction centers when importing from OSM")

        junction_offset_help = QLabel(
            "<small>When importing from OSM, road endpoints are moved away from junction centers "
            "by this distance to create space for connecting roads. Typical values: 5-15m.</small>"
        )
        junction_offset_help.setWordWrap(True)
        junction_offset_help.setStyleSheet("QLabel { color: gray; }")

        junction_layout.addRow("Junction Offset Distance:", self.junction_offset_spin)
        junction_layout.addRow("", junction_offset_help)

        # Create standard OK/Cancel buttons
        self.create_button_box()

    def load_properties(self):
        """Load current preferences from project."""
        # Map name
        self.map_name_edit.setText(self.project.map_name)

        # Transformation method
        if self.project.transform_method == 'homography':
            self.transform_method_combo.setCurrentIndex(1)
        else:
            self.transform_method_combo.setCurrentIndex(0)

        # Traffic side
        if self.project.right_hand_traffic:
            self.traffic_combo.setCurrentIndex(0)
        else:
            self.traffic_combo.setCurrentIndex(1)

        # Country code
        self.country_code_edit.setText(self.project.country_code.lower())

        # Junction offset distance
        self.junction_offset_spin.setValue(self.project.junction_offset_distance_meters)

    def accept(self):
        """Save preferences and close dialog."""
        # Save map name
        self.project.map_name = self.map_name_edit.text().strip()

        # Save transformation method
        self.project.transform_method = self.transform_method_combo.currentData()

        # Save traffic side
        self.project.right_hand_traffic = self.traffic_combo.currentData()

        # Save country code
        self.project.country_code = self.country_code_edit.text().strip().lower()

        # Save junction offset distance
        self.project.junction_offset_distance_meters = self.junction_offset_spin.value()

        super().accept()

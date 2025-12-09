"""
Dialog for editing signal properties.
"""

from PyQt6.QtWidgets import (QFormLayout,
                            QLineEdit, QDoubleSpinBox, QComboBox, QPushButton,
                            QLabel, QGroupBox, QCheckBox, QVBoxLayout)
from PyQt6.QtCore import Qt
from orbit.models.signal import Signal, SignalType, SpeedUnit
from orbit.utils.enum_formatting import format_enum_name
from .base_dialog import BaseDialog
from ..utils import get_scale_factors, format_with_metric


class SignalPropertiesDialog(BaseDialog):
    """
    Dialog for editing properties of a traffic signal.

    Allows editing:
    - Name/label
    - Position (x, y)
    - Assigned road
    - Orientation angle
    - Height above ground (z-offset)
    - Sign dimensions (width and height)
    - Validity range (s_start, s_end)
    - Speed unit (for speed limit signs)
    """

    def __init__(self, signal: Signal, project, parent=None):
        super().__init__(f"Signal Properties: {signal.get_display_name()}", parent, min_width=400)
        self.signal = signal
        self.project = project

        self.setup_ui()
        self.load_properties()

    def setup_ui(self):
        """Create the dialog UI."""
        # Basic properties
        basic_layout = self.add_form_group("Basic Properties")

        self.name_edit = QLineEdit()
        basic_layout.addRow("Name:", self.name_edit)

        # Type (read-only)
        type_label = QLabel(format_enum_name(self.signal.type))
        basic_layout.addRow("Type:", type_label)

        # Value (read-only for now, could be editable)
        if self.signal.type == SignalType.SPEED_LIMIT:
            value_label = QLabel(str(self.signal.value))
            basic_layout.addRow("Speed Value:", value_label)

            # Speed unit
            self.unit_combo = QComboBox()
            self.unit_combo.addItem("km/h", SpeedUnit.KMH)
            self.unit_combo.addItem("mph", SpeedUnit.MPH)
            basic_layout.addRow("Speed Unit:", self.unit_combo)

        # Position and orientation
        position_layout = self.add_form_group_with_info(
            "Position and Orientation",
            "Signal faces perpendicular to road by default. Use heading offset to adjust."
        )

        self.x_spin = QDoubleSpinBox()
        self.x_spin.setRange(-999999, 999999)
        self.x_spin.setDecimals(1)
        position_layout.addRow("X (pixels):", self.x_spin)

        self.y_spin = QDoubleSpinBox()
        self.y_spin.setRange(-999999, 999999)
        self.y_spin.setDecimals(1)
        position_layout.addRow("Y (pixels):", self.y_spin)

        # Orientation (OpenDRIVE)
        self.orientation_combo = QComboBox()
        self.orientation_combo.addItem("Forward (with traffic)", "forward")
        self.orientation_combo.addItem("Backward (against traffic)", "backward")
        self.orientation_combo.addItem("Both directions", "both")
        self.orientation_combo.setToolTip("Traffic direction this signal applies to")
        position_layout.addRow("Orientation:", self.orientation_combo)

        # Heading offset
        self.h_offset_spin = QDoubleSpinBox()
        self.h_offset_spin.setRange(-180.0, 180.0)
        self.h_offset_spin.setDecimals(1)
        self.h_offset_spin.setSuffix("°")
        self.h_offset_spin.setWrapping(True)
        self.h_offset_spin.setToolTip("Rotation offset from perpendicular to road (0° = perpendicular)")
        position_layout.addRow("Heading Offset:", self.h_offset_spin)

        self.z_offset_spin = QDoubleSpinBox()
        self.z_offset_spin.setRange(0.1, 100.0)
        self.z_offset_spin.setDecimals(1)
        self.z_offset_spin.setSuffix(" m")
        position_layout.addRow("Height above ground:", self.z_offset_spin)

        # Sign dimensions group
        sign_dims_label = QLabel("Sign Dimensions:")
        sign_dims_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        position_layout.addRow(sign_dims_label)

        self.sign_width_spin = QDoubleSpinBox()
        self.sign_width_spin.setRange(0.1, 10.0)
        self.sign_width_spin.setDecimals(2)
        self.sign_width_spin.setSuffix(" m")
        position_layout.addRow("Sign width:", self.sign_width_spin)

        self.sign_height_spin = QDoubleSpinBox()
        self.sign_height_spin.setRange(0.1, 10.0)
        self.sign_height_spin.setDecimals(2)
        self.sign_height_spin.setSuffix(" m")
        position_layout.addRow("Sign height:", self.sign_height_spin)

        # Road assignment
        road_layout = self.add_form_group("Road Assignment")

        self.road_combo = QComboBox()
        self.road_combo.addItem("(None)", None)
        for road in self.project.roads:
            self.road_combo.addItem(road.name or f"Road {road.id[:8]}", road.id)
        self.road_combo.currentIndexChanged.connect(self.on_road_changed)
        road_layout.addRow("Assigned Road:", self.road_combo)

        self.s_position_label = QLabel("—")
        road_layout.addRow("S-Position:", self.s_position_label)

        # Validity range (custom group with VBoxLayout)
        validity_group = QGroupBox("Validity Range")
        validity_layout = QVBoxLayout()

        self.validity_checkbox = QCheckBox("Specify validity range (s_start, s_end)")
        self.validity_checkbox.stateChanged.connect(self.on_validity_toggled)
        validity_layout.addWidget(self.validity_checkbox)

        validity_form = QFormLayout()

        self.s_start_spin = QDoubleSpinBox()
        self.s_start_spin.setRange(0, 999999)
        self.s_start_spin.setDecimals(1)
        self.s_start_spin.setEnabled(False)
        validity_form.addRow("S-Start:", self.s_start_spin)

        self.s_end_spin = QDoubleSpinBox()
        self.s_end_spin.setRange(0, 999999)
        self.s_end_spin.setDecimals(1)
        self.s_end_spin.setEnabled(False)
        validity_form.addRow("S-End:", self.s_end_spin)

        validity_layout.addLayout(validity_form)
        validity_group.setLayout(validity_layout)
        self.get_main_layout().addWidget(validity_group)

        # Buttons
        self.create_button_box()

    def load_properties(self):
        """Load signal values into the form."""
        self.name_edit.setText(self.signal.name)
        self.x_spin.setValue(self.signal.position[0])
        self.y_spin.setValue(self.signal.position[1])

        # Load orientation (forward/backward/both)
        orientation_ui = self.signal.get_orientation_ui_string()
        index = self.orientation_combo.findData(orientation_ui)
        if index >= 0:
            self.orientation_combo.setCurrentIndex(index)

        # Load h_offset in degrees
        self.h_offset_spin.setValue(self.signal.get_h_offset_degrees())

        self.z_offset_spin.setValue(self.signal.z_offset)
        self.sign_width_spin.setValue(self.signal.sign_width)
        self.sign_height_spin.setValue(self.signal.sign_height)

        # Speed unit
        if self.signal.type == SignalType.SPEED_LIMIT:
            index = self.unit_combo.findData(self.signal.speed_unit)
            if index >= 0:
                self.unit_combo.setCurrentIndex(index)

        # Road assignment
        if self.signal.road_id:
            index = self.road_combo.findData(self.signal.road_id)
            if index >= 0:
                self.road_combo.setCurrentIndex(index)
            self.update_s_position()

        # Validity range
        if self.signal.validity_range:
            self.validity_checkbox.setChecked(True)
            self.s_start_spin.setValue(self.signal.validity_range[0])
            self.s_end_spin.setValue(self.signal.validity_range[1])

    def on_road_changed(self):
        """Handle road selection change."""
        self.update_s_position()

    def update_s_position(self):
        """Update s-position display based on current road."""
        road_id = self.road_combo.currentData()
        if road_id:
            road = self.project.get_road(road_id)
            if road and road.centerline_id:
                centerline_polyline = self.project.get_polyline(road.centerline_id)
                if centerline_polyline:
                    s = self.signal.calculate_s_position(centerline_polyline.points)
                    if s is not None:
                        # Show in pixels, and also in meters if georeferenced
                        scale = get_scale_factors(self.project)
                        scale_x = scale[0] if scale else None
                        display_text = format_with_metric(s, scale_x)
                        self.s_position_label.setText(display_text)
                        return
        self.s_position_label.setText("—")

    def on_validity_toggled(self, state):
        """Handle validity range checkbox toggle."""
        enabled = state == Qt.CheckState.Checked.value
        self.s_start_spin.setEnabled(enabled)
        self.s_end_spin.setEnabled(enabled)

    def accept(self):
        """Save changes and close dialog."""
        self.signal.name = self.name_edit.text()
        self.signal.position = (self.x_spin.value(), self.y_spin.value())

        # Save orientation (forward/backward/both)
        orientation_ui = self.orientation_combo.currentData()
        self.signal.set_orientation_from_ui_string(orientation_ui)

        # Save h_offset from degrees
        self.signal.set_h_offset_from_degrees(self.h_offset_spin.value())

        self.signal.z_offset = self.z_offset_spin.value()
        self.signal.sign_width = self.sign_width_spin.value()
        self.signal.sign_height = self.sign_height_spin.value()

        # Speed unit
        if self.signal.type == SignalType.SPEED_LIMIT:
            self.signal.speed_unit = self.unit_combo.currentData()

        # Road assignment
        self.signal.road_id = self.road_combo.currentData()

        # Update s-position based on new road/position
        if self.signal.road_id:
            road = self.project.get_road(self.signal.road_id)
            if road and road.centerline_id:
                centerline_polyline = self.project.get_polyline(road.centerline_id)
                if centerline_polyline:
                    self.signal.s_position = self.signal.calculate_s_position(centerline_polyline.points)

        # Validity range
        if self.validity_checkbox.isChecked():
            self.signal.validity_range = (self.s_start_spin.value(), self.s_end_spin.value())
        else:
            self.signal.validity_range = None

        super().accept()

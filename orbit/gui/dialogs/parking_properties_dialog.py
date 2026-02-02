"""
Dialog for editing parking space properties.
"""

from PyQt6.QtWidgets import QComboBox, QDoubleSpinBox, QLabel, QLineEdit, QSpinBox

from orbit.models.parking import ParkingAccess, ParkingSpace, ParkingType

from .base_dialog import BaseDialog


class ParkingPropertiesDialog(BaseDialog):
    """
    Dialog for editing properties of a parking space.

    Allows editing:
    - Name/label
    - Position (x, y)
    - Assigned road
    - Parking type (surface, underground, etc.)
    - Access type (standard, handicapped, etc.)
    - Restrictions text
    - Dimensions (width, length)
    - Orientation angle
    - Capacity (for lots)
    """

    def __init__(self, parking: ParkingSpace, project, parent=None):
        super().__init__(f"Parking Properties: {parking.get_display_name()}", parent, min_width=450)
        self.parking = parking
        self.project = project

        self.setup_ui()
        self.load_properties()

    def setup_ui(self):
        """Create the dialog UI."""
        # Basic properties
        basic_layout = self.add_form_group("Basic Properties")

        self.name_edit = QLineEdit()
        basic_layout.addRow("Name:", self.name_edit)

        # Parking type
        self.type_combo = QComboBox()
        for ptype in ParkingType:
            display_name = ptype.value.replace('_', ' ').title()
            self.type_combo.addItem(display_name, ptype)
        basic_layout.addRow("Parking Type:", self.type_combo)

        # Access type
        self.access_combo = QComboBox()
        for access in ParkingAccess:
            display_name = access.value.replace('_', ' ').title()
            self.access_combo.addItem(display_name, access)
        basic_layout.addRow("Access Type:", self.access_combo)

        # Restrictions
        self.restrictions_edit = QLineEdit()
        self.restrictions_edit.setPlaceholderText("e.g., Max 2 hours, Permit required")
        basic_layout.addRow("Restrictions:", self.restrictions_edit)

        # Capacity (for lots)
        self.capacity_spin = QSpinBox()
        self.capacity_spin.setRange(0, 10000)
        self.capacity_spin.setSpecialValueText("Not specified")
        basic_layout.addRow("Capacity:", self.capacity_spin)

        # Position and orientation
        position_layout = self.add_form_group("Position and Orientation")

        # Only show X/Y for non-polygon parking
        if not self.parking.is_polygon():
            self.x_spin = QDoubleSpinBox()
            self.x_spin.setRange(-999999, 999999)
            self.x_spin.setDecimals(1)
            position_layout.addRow("X (pixels):", self.x_spin)

            self.y_spin = QDoubleSpinBox()
            self.y_spin.setRange(-999999, 999999)
            self.y_spin.setDecimals(1)
            position_layout.addRow("Y (pixels):", self.y_spin)
        else:
            self.x_spin = None
            self.y_spin = None
            points_label = QLabel(f"{len(self.parking.points)} polygon points")
            position_layout.addRow("Shape:", points_label)

        # Orientation
        self.orientation_spin = QDoubleSpinBox()
        self.orientation_spin.setRange(0, 359.9)
        self.orientation_spin.setDecimals(1)
        self.orientation_spin.setSuffix("°")
        self.orientation_spin.setWrapping(True)
        position_layout.addRow("Orientation:", self.orientation_spin)

        self.z_offset_spin = QDoubleSpinBox()
        self.z_offset_spin.setRange(-10.0, 100.0)
        self.z_offset_spin.setDecimals(2)
        self.z_offset_spin.setSuffix(" m")
        position_layout.addRow("Height above ground:", self.z_offset_spin)

        # Dimensions section
        dimensions_layout = self.add_form_group("Dimensions")

        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(0.1, 100.0)
        self.width_spin.setDecimals(2)
        self.width_spin.setSuffix(" m")
        dimensions_layout.addRow("Width:", self.width_spin)

        self.length_spin = QDoubleSpinBox()
        self.length_spin.setRange(0.1, 100.0)
        self.length_spin.setDecimals(2)
        self.length_spin.setSuffix(" m")
        dimensions_layout.addRow("Length:", self.length_spin)

        # Road assignment
        road_layout = self.add_form_group("Road Assignment")

        self.road_combo = QComboBox()
        self.road_combo.addItem("(None)", None)
        for road in self.project.roads:
            self.road_combo.addItem(road.name or f"Road {road.id[:8]}", road.id)
        road_layout.addRow("Assigned Road:", self.road_combo)

        # S/T position info (read-only)
        self.st_label = QLabel("Not calculated")
        road_layout.addRow("Position (s, t):", self.st_label)

    def load_properties(self):
        """Load current parking properties into the dialog."""
        self.name_edit.setText(self.parking.name)

        # Parking type
        type_index = self.type_combo.findData(self.parking.parking_type)
        if type_index >= 0:
            self.type_combo.setCurrentIndex(type_index)

        # Access type
        access_index = self.access_combo.findData(self.parking.access)
        if access_index >= 0:
            self.access_combo.setCurrentIndex(access_index)

        self.restrictions_edit.setText(self.parking.restrictions)

        # Capacity
        if self.parking.capacity is not None:
            self.capacity_spin.setValue(self.parking.capacity)
        else:
            self.capacity_spin.setValue(0)

        # Position
        if self.x_spin:
            self.x_spin.setValue(self.parking.position[0])
        if self.y_spin:
            self.y_spin.setValue(self.parking.position[1])

        self.orientation_spin.setValue(self.parking.orientation)
        self.z_offset_spin.setValue(self.parking.z_offset)

        # Dimensions
        self.width_spin.setValue(self.parking.width)
        self.length_spin.setValue(self.parking.length)

        # Road assignment
        if self.parking.road_id:
            road_index = self.road_combo.findData(self.parking.road_id)
            if road_index >= 0:
                self.road_combo.setCurrentIndex(road_index)

        self._update_st_label()

    def _update_st_label(self):
        """Update the s/t position label."""
        if self.parking.s_position is not None and self.parking.t_offset is not None:
            self.st_label.setText(f"s={self.parking.s_position:.1f}, t={self.parking.t_offset:.1f}")
        else:
            self.st_label.setText("Not calculated")

    def accept(self):
        """Save changes and close dialog."""
        self.parking.name = self.name_edit.text()
        self.parking.parking_type = self.type_combo.currentData()
        self.parking.access = self.access_combo.currentData()
        self.parking.restrictions = self.restrictions_edit.text()

        # Capacity
        capacity_value = self.capacity_spin.value()
        self.parking.capacity = capacity_value if capacity_value > 0 else None

        # Position
        if self.x_spin and self.y_spin:
            self.parking.position = (self.x_spin.value(), self.y_spin.value())

        self.parking.orientation = self.orientation_spin.value()
        self.parking.z_offset = self.z_offset_spin.value()

        # Dimensions
        self.parking.width = self.width_spin.value()
        self.parking.length = self.length_spin.value()

        # Road assignment
        self.parking.road_id = self.road_combo.currentData()

        # Recalculate s/t position if road is assigned
        if self.parking.road_id:
            road = self.project.get_road(self.parking.road_id)
            if road and road.centerline_id:
                centerline = self.project.get_polyline(road.centerline_id)
                if centerline and centerline.points:
                    s, t = self.parking.calculate_s_t_position(centerline.points)
                    self.parking.s_position = s
                    self.parking.t_offset = t

        super().accept()

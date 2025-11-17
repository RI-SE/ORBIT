"""
Dialog for editing object properties.
"""

from PyQt6.QtWidgets import (QHBoxLayout, QFormLayout,
                            QLineEdit, QDoubleSpinBox, QComboBox, QPushButton,
                            QLabel, QGroupBox, QCheckBox, QVBoxLayout)
from PyQt6.QtCore import Qt
from orbit.models.object import RoadObject, ObjectType
from orbit.gui.base_dialog import BaseDialog


class ObjectPropertiesDialog(BaseDialog):
    """
    Dialog for editing properties of a roadside object.

    Allows editing:
    - Name/label
    - Position (x, y)
    - Assigned road
    - Orientation angle (for building/lamppost)
    - Height above ground (z-offset)
    - Dimensions (varies by object type)
    - Validity length (for guardrails)
    """

    def __init__(self, obj: RoadObject, project, parent=None):
        super().__init__(f"Object Properties: {obj.get_display_name()}", parent, min_width=450)
        self.obj = obj
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
        type_label = QLabel(self.obj.type.value.replace('_', ' ').title())
        basic_layout.addRow("Type:", type_label)

        # Category (read-only)
        category_label = QLabel(self.obj.type.get_category().replace('_', ' ').title())
        basic_layout.addRow("Category:", category_label)

        # Position and orientation
        position_layout = self.add_form_group("Position and Orientation")

        # Only show X/Y for non-polyline objects
        if self.obj.type.get_shape_type() != "polyline":
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
            points_label = QLabel(f"{len(self.obj.points)} points")
            position_layout.addRow("Points:", points_label)

        # Orientation (only for building/lamppost)
        if self.obj.type.has_orientation():
            self.orientation_spin = QDoubleSpinBox()
            self.orientation_spin.setRange(0, 359.9)
            self.orientation_spin.setDecimals(1)
            self.orientation_spin.setSuffix("°")
            self.orientation_spin.setWrapping(True)
            position_layout.addRow("Orientation:", self.orientation_spin)
        else:
            self.orientation_spin = None

        self.z_offset_spin = QDoubleSpinBox()
        self.z_offset_spin.setRange(-10.0, 100.0)
        self.z_offset_spin.setDecimals(2)
        self.z_offset_spin.setSuffix(" m")
        position_layout.addRow("Height above ground:", self.z_offset_spin)

        # Dimensions section
        self._setup_dimensions_section()

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

        self.t_offset_label = QLabel("—")
        road_layout.addRow("T-Offset:", self.t_offset_label)

        # Validity length (for guardrails)
        if self.obj.type.supports_validity_length():
            validity_group = QGroupBox("Validity Length")
            validity_layout = QVBoxLayout()

            validity_info = QLabel("For guardrails, validity length is calculated from the polyline length.")
            validity_info.setWordWrap(True)
            validity_layout.addWidget(validity_info)

            self.validity_length_label = QLabel("—")
            validity_form = QFormLayout()
            validity_form.addRow("Length:", self.validity_length_label)
            validity_layout.addLayout(validity_form)

            validity_group.setLayout(validity_layout)
            self.get_main_layout().addWidget(validity_group)

        # Buttons
        self.create_button_box()

    def _setup_dimensions_section(self):
        """Set up dimensions section based on object type."""
        dims_group = QGroupBox("Dimensions")
        dims_layout = QFormLayout()

        dims = self.obj.dimensions

        if self.obj.type == ObjectType.LAMPPOST:
            self.radius_spin = QDoubleSpinBox()
            self.radius_spin.setRange(0.05, 5.0)
            self.radius_spin.setDecimals(2)
            self.radius_spin.setSuffix(" m")
            dims_layout.addRow("Radius:", self.radius_spin)

            self.height_spin = QDoubleSpinBox()
            self.height_spin.setRange(0.1, 50.0)
            self.height_spin.setDecimals(1)
            self.height_spin.setSuffix(" m")
            dims_layout.addRow("Height:", self.height_spin)

        elif self.obj.type == ObjectType.GUARDRAIL:
            self.height_spin = QDoubleSpinBox()
            self.height_spin.setRange(0.1, 10.0)
            self.height_spin.setDecimals(2)
            self.height_spin.setSuffix(" m")
            dims_layout.addRow("Height:", self.height_spin)

            self.width_spin = QDoubleSpinBox()
            self.width_spin.setRange(0.1, 2.0)
            self.width_spin.setDecimals(2)
            self.width_spin.setSuffix(" m")
            dims_layout.addRow("Width:", self.width_spin)

        elif self.obj.type == ObjectType.BUILDING:
            self.width_spin = QDoubleSpinBox()
            self.width_spin.setRange(1.0, 200.0)
            self.width_spin.setDecimals(1)
            self.width_spin.setSuffix(" m")
            dims_layout.addRow("Width:", self.width_spin)

            self.length_spin = QDoubleSpinBox()
            self.length_spin.setRange(1.0, 200.0)
            self.length_spin.setDecimals(1)
            self.length_spin.setSuffix(" m")
            dims_layout.addRow("Length:", self.length_spin)

            self.height_spin = QDoubleSpinBox()
            self.height_spin.setRange(1.0, 200.0)
            self.height_spin.setDecimals(1)
            self.height_spin.setSuffix(" m")
            dims_layout.addRow("Height:", self.height_spin)

        elif self.obj.type in (ObjectType.TREE_BROADLEAF, ObjectType.TREE_CONIFER, ObjectType.BUSH):
            self.radius_spin = QDoubleSpinBox()
            self.radius_spin.setRange(0.1, 50.0)
            self.radius_spin.setDecimals(1)
            self.radius_spin.setSuffix(" m")
            dims_layout.addRow("Radius (Ø/2):", self.radius_spin)

            self.height_spin = QDoubleSpinBox()
            self.height_spin.setRange(0.1, 100.0)
            self.height_spin.setDecimals(1)
            self.height_spin.setSuffix(" m")
            dims_layout.addRow("Height:", self.height_spin)

        dims_group.setLayout(dims_layout)
        self.get_main_layout().addWidget(dims_group)

    def load_properties(self):
        """Load object values into the form."""
        self.name_edit.setText(self.obj.name)

        # Position (only for point objects)
        if self.x_spin and self.y_spin:
            self.x_spin.setValue(self.obj.position[0])
            self.y_spin.setValue(self.obj.position[1])

        # Orientation
        if self.orientation_spin:
            self.orientation_spin.setValue(self.obj.orientation)

        # Z-offset
        self.z_offset_spin.setValue(self.obj.z_offset)

        # Dimensions
        dims = self.obj.dimensions

        if hasattr(self, 'radius_spin'):
            self.radius_spin.setValue(dims.get('radius', 1.0))

        if hasattr(self, 'width_spin'):
            self.width_spin.setValue(dims.get('width', 1.0))

        if hasattr(self, 'length_spin'):
            self.length_spin.setValue(dims.get('length', 1.0))

        if hasattr(self, 'height_spin'):
            self.height_spin.setValue(dims.get('height', 1.0))

        # Road assignment
        if self.obj.road_id:
            index = self.road_combo.findData(self.obj.road_id)
            if index >= 0:
                self.road_combo.setCurrentIndex(index)
            self.update_road_position()

        # Validity length
        if self.obj.type.supports_validity_length():
            self.update_validity_length()

    def on_road_changed(self):
        """Handle road selection change."""
        self.update_road_position()

    def update_road_position(self):
        """Update s-position and t-offset display based on current road."""
        road_id = self.road_combo.currentData()
        if road_id:
            road = self.project.get_road(road_id)
            if road and road.centerline_id:
                centerline_polyline = self.project.get_polyline(road.centerline_id)
                if centerline_polyline:
                    s, t = self.obj.calculate_s_t_position(centerline_polyline.points)
                    if s is not None:
                        # Show in pixels, and also in meters if georeferenced
                        s_display = f"{s:.1f} px"
                        t_display = f"{t:.1f} px"

                        if self.project.has_georeferencing():
                            try:
                                from orbit.export import create_transformer
                                transformer = create_transformer(self.project.control_points)
                                if transformer:
                                    scale_x, scale_y = transformer.get_scale_factor()
                                    if scale_x and scale_x > 0:
                                        s_meters = s * scale_x
                                        t_meters = t * scale_x
                                        s_display = f"{s:.1f} px ({s_meters:.2f} m)"
                                        t_display = f"{t:.1f} px ({t_meters:.2f} m)"
                            except Exception:
                                pass

                        self.s_position_label.setText(s_display)
                        self.t_offset_label.setText(t_display)
                        return

        self.s_position_label.setText("—")
        self.t_offset_label.setText("—")

    def update_validity_length(self):
        """Update validity length display for guardrails."""
        if not self.obj.type.supports_validity_length():
            return

        if self.obj.points and len(self.obj.points) >= 2:
            # Calculate total polyline length
            total_length = 0.0
            for i in range(len(self.obj.points) - 1):
                x1, y1 = self.obj.points[i]
                x2, y2 = self.obj.points[i + 1]
                total_length += ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5

            length_display = f"{total_length:.1f} px"

            if self.project.has_georeferencing():
                try:
                    from orbit.export import create_transformer
                    transformer = create_transformer(self.project.control_points)
                    if transformer:
                        scale_x, scale_y = transformer.get_scale_factor()
                        if scale_x and scale_x > 0:
                            length_meters = total_length * scale_x
                            length_display = f"{total_length:.1f} px ({length_meters:.2f} m)"
                except Exception:
                    pass

            self.validity_length_label.setText(length_display)
        else:
            self.validity_length_label.setText("—")

    def accept(self):
        """Save changes and close dialog."""
        self.obj.name = self.name_edit.text()

        # Position (only for point objects)
        if self.x_spin and self.y_spin:
            self.obj.position = (self.x_spin.value(), self.y_spin.value())

        # Orientation
        if self.orientation_spin:
            self.obj.orientation = self.orientation_spin.value()

        # Z-offset
        self.obj.z_offset = self.z_offset_spin.value()

        # Dimensions
        if hasattr(self, 'radius_spin'):
            self.obj.dimensions['radius'] = self.radius_spin.value()

        if hasattr(self, 'width_spin'):
            self.obj.dimensions['width'] = self.width_spin.value()

        if hasattr(self, 'length_spin'):
            self.obj.dimensions['length'] = self.length_spin.value()

        if hasattr(self, 'height_spin'):
            self.obj.dimensions['height'] = self.height_spin.value()

        # Road assignment
        self.obj.road_id = self.road_combo.currentData()

        # Update s-position and t-offset based on new road/position
        if self.obj.road_id:
            road = self.project.get_road(self.obj.road_id)
            if road and road.centerline_id:
                centerline_polyline = self.project.get_polyline(road.centerline_id)
                if centerline_polyline:
                    s, t = self.obj.calculate_s_t_position(centerline_polyline.points)
                    self.obj.s_position = s
                    self.obj.t_offset = t

        # Update validity length for guardrails
        if self.obj.type.supports_validity_length() and self.obj.points:
            total_length = 0.0
            for i in range(len(self.obj.points) - 1):
                x1, y1 = self.obj.points[i]
                x2, y2 = self.obj.points[i + 1]
                total_length += ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
            self.obj.validity_length = total_length

        super().accept()

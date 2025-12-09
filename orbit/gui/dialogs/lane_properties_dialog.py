"""
Lane properties dialog for ORBIT.

Allows editing of individual lane properties.
"""

from typing import Optional, TYPE_CHECKING

from PyQt6.QtWidgets import (
    QDialog, QGroupBox, QFormLayout, QSpinBox,
    QComboBox, QLabel, QDoubleSpinBox, QCheckBox, QWidget, QHBoxLayout, QToolButton,
    QTableWidget, QTableWidgetItem, QPushButton, QVBoxLayout, QHeaderView,
    QScrollArea, QFrame
)
from PyQt6.QtCore import Qt

from orbit.models import Lane, LaneType, RoadMarkType, Project, LineType
from orbit.utils import format_enum_name
from .base_dialog import BaseDialog, InfoIconLabel
from ..utils import set_combo_by_data

if TYPE_CHECKING:
    from orbit.models.connecting_road import ConnectingRoad


class LanePropertiesDialog(BaseDialog):
    """Dialog for editing lane properties."""

    def __init__(self, lane: Lane, project: Optional[Project] = None, road_id: Optional[str] = None,
                 connecting_road: Optional['ConnectingRoad'] = None, parent=None):
        super().__init__("Lane Properties", parent, min_width=600)

        self.lane = lane
        self.project = project
        self.road_id = road_id
        self.connecting_road = connecting_road  # For connecting road lanes
        self.setup_ui()
        self.load_properties()

    def setup_ui(self):
        """Setup the dialog UI."""
        # Lane identification (read-only)
        id_layout = self.add_form_group("Lane Identification")

        self.lane_id_label = QLabel()
        self.lane_id_label.setStyleSheet("QLabel { font-weight: bold; }")
        id_layout.addRow("Lane ID:", self.lane_id_label)

        self.position_label = QLabel()
        id_layout.addRow("Position:", self.position_label)

        # Lane properties
        props_layout = self.add_form_group("Lane Properties")

        # Lane type dropdown
        self.lane_type_combo = QComboBox()
        for lane_type in LaneType:
            self.lane_type_combo.addItem(format_enum_name(lane_type), lane_type)
        self.lane_type_combo.currentIndexChanged.connect(self.on_lane_type_changed)
        props_layout.addRow("Lane Type:", self.lane_type_combo)

        # Road mark type dropdown
        self.road_mark_type_combo = QComboBox()
        for mark_type in RoadMarkType:
            self.road_mark_type_combo.addItem(format_enum_name(mark_type), mark_type)
        props_layout.addRow("Road Mark Type:", self.road_mark_type_combo)

        # Road mark color dropdown
        self.road_mark_color_combo = QComboBox()
        for color in ["white", "yellow", "blue", "green", "red", "orange"]:
            self.road_mark_color_combo.addItem(color.capitalize(), color)
        self.road_mark_color_combo.setToolTip("Color of the road marking (e.g., yellow for center lines)")
        props_layout.addRow("Road Mark Color:", self.road_mark_color_combo)

        # Road mark weight dropdown
        self.road_mark_weight_combo = QComboBox()
        for weight in ["standard", "bold"]:
            self.road_mark_weight_combo.addItem(weight.capitalize(), weight)
        self.road_mark_weight_combo.setToolTip("Line weight (bold for edge lines)")
        props_layout.addRow("Road Mark Weight:", self.road_mark_weight_combo)

        # Road mark width spinbox
        self.road_mark_width_spin = QDoubleSpinBox()
        self.road_mark_width_spin.setRange(0.05, 0.50)
        self.road_mark_width_spin.setSingleStep(0.01)
        self.road_mark_width_spin.setDecimals(2)
        self.road_mark_width_spin.setValue(0.12)
        self.road_mark_width_spin.setSuffix(" m")
        self.road_mark_width_spin.setToolTip("Width of the painted road marking in meters")
        props_layout.addRow("Road Mark Width:", self.road_mark_width_spin)

        # Lane width - different UI for connecting road lanes
        self.width_spin = None
        self.width_start_spin = None
        self.width_end_spin = None
        self.width_info_label = None

        is_center_lane = self.lane.id == 0
        is_connecting_road_lane = self.connecting_road is not None

        if is_connecting_road_lane and is_center_lane:
            # Center lane in connecting road - no width (show as read-only info)
            center_info = QLabel("0.0 m (center lane has no width)")
            center_info.setStyleSheet("QLabel { color: gray; }")
            props_layout.addRow("Width:", center_info)
        elif is_connecting_road_lane:
            # Driving lane in connecting road - show start/end width
            self.width_start_spin = QDoubleSpinBox()
            self.width_start_spin.setRange(0.5, 20.0)
            self.width_start_spin.setSingleStep(0.1)
            self.width_start_spin.setDecimals(2)
            self.width_start_spin.setSuffix(" m")
            self.width_start_spin.setToolTip("Lane width at the start of the connecting road (s=0)")
            props_layout.addRow("Width at Start:", self.width_start_spin)

            self.width_end_spin = QDoubleSpinBox()
            self.width_end_spin.setRange(0.5, 20.0)
            self.width_end_spin.setSingleStep(0.1)
            self.width_end_spin.setDecimals(2)
            self.width_end_spin.setSuffix(" m")
            self.width_end_spin.setToolTip("Lane width at the end of the connecting road")
            props_layout.addRow("Width at End:", self.width_end_spin)

            # Width transition info
            self.width_info_label = QLabel()
            self.width_info_label.setWordWrap(True)
            self.width_info_label.setStyleSheet("QLabel { color: gray; font-style: italic; }")
            props_layout.addRow("", self.width_info_label)

            # Connect signals to update info
            self.width_start_spin.valueChanged.connect(self.update_width_info)
            self.width_end_spin.valueChanged.connect(self.update_width_info)
        else:
            # Regular road lane - single width value
            self.width_spin = QDoubleSpinBox()
            self.width_spin.setRange(0.0, 20.0)
            self.width_spin.setSingleStep(0.1)
            self.width_spin.setValue(3.5)
            self.width_spin.setSuffix(" m")
            self.width_spin.setToolTip("Lane width in meters (or pixels if not georeferenced)")
            props_layout.addRow("Width:", self.width_spin)

        # Access restrictions (for path lanes)
        self.access_widget = QWidget()
        access_layout = QHBoxLayout(self.access_widget)
        access_layout.setContentsMargins(0, 0, 0, 0)

        self.bicycle_access_checkbox = QCheckBox("Bicycle")
        self.bicycle_access_checkbox.setToolTip("Allow bicycle access on this lane")
        access_layout.addWidget(self.bicycle_access_checkbox)

        self.pedestrian_access_checkbox = QCheckBox("Pedestrian")
        self.pedestrian_access_checkbox.setToolTip("Allow pedestrian access on this lane")
        access_layout.addWidget(self.pedestrian_access_checkbox)

        access_layout.addStretch()

        # Access label with info icon (shown only for path lanes)
        self.access_label_widget = InfoIconLabel(
            "Access",
            "For shared paths, enable both bicycle and pedestrian access.",
            bold=False
        )
        props_layout.addRow(self.access_label_widget, self.access_widget)

        # Description label
        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet("QLabel { color: gray; font-style: italic; }")
        props_layout.addRow("", self.description_label)

        # Collapsible Advanced section (only for regular road lanes, not connecting roads)
        if not is_connecting_road_lane:
            self._setup_advanced_section()

        # Boundary polylines (if project available)
        if self.project and self.road_id:
            boundary_layout = self.add_form_group_with_info(
                "Boundary Polylines",
                "Assign polylines that define the left and right edges of this lane. "
                "Leave unassigned if boundaries should be inferred from road mark type."
            )

            # Left boundary selector
            self.left_boundary_combo = QComboBox()
            self.left_boundary_combo.addItem("(Not assigned)", None)
            self._populate_boundary_polylines(self.left_boundary_combo)
            boundary_layout.addRow("Left Boundary:", self.left_boundary_combo)

            # Right boundary selector
            self.right_boundary_combo = QComboBox()
            self.right_boundary_combo.addItem("(Not assigned)", None)
            self._populate_boundary_polylines(self.right_boundary_combo)
            boundary_layout.addRow("Right Boundary:", self.right_boundary_combo)

        # Create standard OK/Cancel buttons
        self.create_button_box()

        self.update_description()

    def _populate_boundary_polylines(self, combo: QComboBox):
        """Populate combo box with boundary polylines from the road."""
        if not self.project or not self.road_id:
            return

        road = self.project.get_road(self.road_id)
        if not road:
            return

        # Add lane boundary polylines assigned to this road
        for polyline_id in road.polyline_ids:
            polyline = self.project.get_polyline(polyline_id)
            if polyline and polyline.line_type == LineType.LANE_BOUNDARY:
                display_text = f"Polyline ({polyline.point_count()} pts)"
                combo.addItem(display_text, polyline_id)

    def _setup_advanced_section(self):
        """Setup the collapsible Advanced section with two-column layout."""
        # Create collapsible toggle
        self.advanced_toggle = QToolButton()
        self.advanced_toggle.setStyleSheet("QToolButton { border: none; }")
        self.advanced_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.advanced_toggle.setText("Advanced")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setChecked(False)
        self.advanced_toggle.clicked.connect(self._toggle_advanced)

        self.get_main_layout().addWidget(self.advanced_toggle)

        # Scroll area for the advanced content
        self.advanced_scroll = QScrollArea()
        self.advanced_scroll.setWidgetResizable(True)
        self.advanced_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.advanced_scroll.setMaximumHeight(400)

        self.advanced_widget = QWidget()
        advanced_layout = QVBoxLayout(self.advanced_widget)
        advanced_layout.setContentsMargins(10, 5, 10, 10)

        # === TWO-COLUMN ROW ===
        columns_widget = QWidget()
        columns_layout = QHBoxLayout(columns_widget)
        columns_layout.setContentsMargins(0, 0, 0, 0)
        columns_layout.setSpacing(10)

        # LEFT COLUMN: Width Polynomial + Speed Limit
        left_group = QGroupBox("Width && Speed")
        left_layout = QFormLayout(left_group)
        left_layout.setVerticalSpacing(4)

        # Width b coefficient (linear)
        self.width_b_spin = QDoubleSpinBox()
        self.width_b_spin.setRange(-1.0, 1.0)
        self.width_b_spin.setSingleStep(0.001)
        self.width_b_spin.setDecimals(4)
        self.width_b_spin.setValue(0.0)
        self.width_b_spin.setToolTip("Linear coefficient: width change per meter (m/m)")
        left_layout.addRow("b (linear):", self.width_b_spin)

        # Width c coefficient (quadratic)
        self.width_c_spin = QDoubleSpinBox()
        self.width_c_spin.setRange(-0.1, 0.1)
        self.width_c_spin.setSingleStep(0.0001)
        self.width_c_spin.setDecimals(5)
        self.width_c_spin.setValue(0.0)
        self.width_c_spin.setToolTip("Quadratic coefficient (m/m²)")
        left_layout.addRow("c (quad):", self.width_c_spin)

        # Width d coefficient (cubic)
        self.width_d_spin = QDoubleSpinBox()
        self.width_d_spin.setRange(-0.01, 0.01)
        self.width_d_spin.setSingleStep(0.00001)
        self.width_d_spin.setDecimals(6)
        self.width_d_spin.setValue(0.0)
        self.width_d_spin.setToolTip("Cubic coefficient (m/m³)")
        left_layout.addRow("d (cubic):", self.width_d_spin)

        # Speed limit value
        speed_widget = QWidget()
        speed_layout = QHBoxLayout(speed_widget)
        speed_layout.setContentsMargins(0, 0, 0, 0)

        self.speed_limit_spin = QSpinBox()
        self.speed_limit_spin.setRange(0, 300)
        self.speed_limit_spin.setValue(0)
        self.speed_limit_spin.setSpecialValueText("Inherit")
        self.speed_limit_spin.setToolTip("0 = inherit road speed limit")
        speed_layout.addWidget(self.speed_limit_spin)

        self.speed_unit_combo = QComboBox()
        self.speed_unit_combo.addItem("km/h", "km/h")
        self.speed_unit_combo.addItem("mph", "mph")
        self.speed_unit_combo.addItem("m/s", "m/s")
        speed_layout.addWidget(self.speed_unit_combo)

        left_layout.addRow("Speed:", speed_widget)

        columns_layout.addWidget(left_group)

        # RIGHT COLUMN: OpenDRIVE 1.8 Attributes + Lane Links
        right_group = QGroupBox("OpenDRIVE 1.8")
        right_layout = QFormLayout(right_group)
        right_layout.setVerticalSpacing(4)

        # Direction attribute
        self.direction_combo = QComboBox()
        self.direction_combo.addItem("(Not set)", None)
        self.direction_combo.addItem("Standard", "standard")
        self.direction_combo.addItem("Reversed", "reversed")
        self.direction_combo.addItem("Both", "both")
        self.direction_combo.setToolTip("Direction of travel in the lane (V1.8)")
        right_layout.addRow("Direction:", self.direction_combo)

        # Advisory attribute
        self.advisory_combo = QComboBox()
        self.advisory_combo.addItem("(Not set)", None)
        self.advisory_combo.addItem("None", "none")
        self.advisory_combo.addItem("Inner", "inner")
        self.advisory_combo.addItem("Outer", "outer")
        self.advisory_combo.addItem("Both", "both")
        self.advisory_combo.setToolTip("Advisory restriction for shared lanes (V1.8)")
        right_layout.addRow("Advisory:", self.advisory_combo)

        # Level checkbox
        self.level_checkbox = QCheckBox("Level")
        self.level_checkbox.setToolTip("If checked, lane stays level and doesn't follow road superelevation")
        right_layout.addRow("", self.level_checkbox)

        # Predecessor link
        self.predecessor_spin = QSpinBox()
        self.predecessor_spin.setRange(-99, 99)
        self.predecessor_spin.setValue(0)
        self.predecessor_spin.setSpecialValueText("(None)")
        self.predecessor_spin.setToolTip("Lane ID of predecessor lane (0 = none)")
        right_layout.addRow("Predecessor:", self.predecessor_spin)

        # Successor link
        self.successor_spin = QSpinBox()
        self.successor_spin.setRange(-99, 99)
        self.successor_spin.setValue(0)
        self.successor_spin.setSpecialValueText("(None)")
        self.successor_spin.setToolTip("Lane ID of successor lane (0 = none)")
        right_layout.addRow("Successor:", self.successor_spin)

        columns_layout.addWidget(right_group)

        advanced_layout.addWidget(columns_widget)

        # === FULL-WIDTH TABLES ===
        # Materials section
        self._setup_materials_section(advanced_layout)

        # Heights section
        self._setup_heights_section(advanced_layout)

        # Put advanced_widget in scroll area
        self.advanced_scroll.setWidget(self.advanced_widget)
        self.advanced_scroll.setVisible(False)
        self.get_main_layout().addWidget(self.advanced_scroll)

    def _toggle_advanced(self, checked: bool):
        """Toggle visibility of advanced section."""
        self.advanced_scroll.setVisible(checked)
        if checked:
            self.advanced_toggle.setArrowType(Qt.ArrowType.DownArrow)
        else:
            self.advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)

    def _setup_materials_section(self, parent_layout: QVBoxLayout):
        """Setup the materials table section."""
        materials_group = QGroupBox()
        materials_layout = QVBoxLayout(materials_group)

        materials_title = InfoIconLabel(
            "Materials",
            "Surface properties along the lane (friction, roughness)"
        )
        materials_layout.addWidget(materials_title)

        # Materials table
        self.materials_table = QTableWidget(0, 4)
        self.materials_table.setHorizontalHeaderLabels(["S-Offset", "Friction", "Roughness", "Surface"])
        self.materials_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.materials_table.setMinimumHeight(80)
        materials_layout.addWidget(self.materials_table)

        # Add/Remove buttons
        materials_btn_widget = QWidget()
        materials_btn_layout = QHBoxLayout(materials_btn_widget)
        materials_btn_layout.setContentsMargins(0, 0, 0, 0)
        materials_btn_layout.addStretch()

        self.add_material_btn = QPushButton("+ Add")
        self.add_material_btn.clicked.connect(self._add_material_row)
        materials_btn_layout.addWidget(self.add_material_btn)

        self.remove_material_btn = QPushButton("- Remove")
        self.remove_material_btn.clicked.connect(self._remove_material_row)
        materials_btn_layout.addWidget(self.remove_material_btn)

        materials_layout.addWidget(materials_btn_widget)
        parent_layout.addWidget(materials_group)

    def _setup_heights_section(self, parent_layout: QVBoxLayout):
        """Setup the heights table section."""
        heights_group = QGroupBox()
        heights_layout = QVBoxLayout(heights_group)

        heights_title = InfoIconLabel(
            "Heights",
            "Lane height offsets (for sidewalks, curbs)"
        )
        heights_layout.addWidget(heights_title)

        # Heights table
        self.heights_table = QTableWidget(0, 3)
        self.heights_table.setHorizontalHeaderLabels(["S-Offset", "Inner", "Outer"])
        self.heights_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.heights_table.setMinimumHeight(80)
        heights_layout.addWidget(self.heights_table)

        # Add/Remove buttons
        heights_btn_widget = QWidget()
        heights_btn_layout = QHBoxLayout(heights_btn_widget)
        heights_btn_layout.setContentsMargins(0, 0, 0, 0)
        heights_btn_layout.addStretch()

        self.add_height_btn = QPushButton("+ Add")
        self.add_height_btn.clicked.connect(self._add_height_row)
        heights_btn_layout.addWidget(self.add_height_btn)

        self.remove_height_btn = QPushButton("- Remove")
        self.remove_height_btn.clicked.connect(self._remove_height_row)
        heights_btn_layout.addWidget(self.remove_height_btn)

        heights_layout.addWidget(heights_btn_widget)
        parent_layout.addWidget(heights_group)

    def _add_material_row(self):
        """Add a new material row to the table."""
        row = self.materials_table.rowCount()
        self.materials_table.insertRow(row)

        # Default values
        self.materials_table.setItem(row, 0, QTableWidgetItem("0.0"))  # s_offset
        self.materials_table.setItem(row, 1, QTableWidgetItem("0.8"))  # friction
        self.materials_table.setItem(row, 2, QTableWidgetItem("0.01"))  # roughness
        self.materials_table.setItem(row, 3, QTableWidgetItem("asphalt"))  # surface

    def _remove_material_row(self):
        """Remove the selected material row."""
        current_row = self.materials_table.currentRow()
        if current_row >= 0:
            self.materials_table.removeRow(current_row)

    def _add_height_row(self):
        """Add a new height row to the table."""
        row = self.heights_table.rowCount()
        self.heights_table.insertRow(row)

        # Default values
        self.heights_table.setItem(row, 0, QTableWidgetItem("0.0"))  # s_offset
        self.heights_table.setItem(row, 1, QTableWidgetItem("0.0"))  # inner
        self.heights_table.setItem(row, 2, QTableWidgetItem("0.0"))  # outer

    def _remove_height_row(self):
        """Remove the selected height row."""
        current_row = self.heights_table.currentRow()
        if current_row >= 0:
            self.heights_table.removeRow(current_row)

    def _load_materials_table(self):
        """Load materials from lane into the table."""
        self.materials_table.setRowCount(0)
        for material in self.lane.materials:
            row = self.materials_table.rowCount()
            self.materials_table.insertRow(row)
            # Unpack tuple: (s_offset, friction, roughness, surface)
            s_offset, friction, roughness, surface = material[:4] if len(material) >= 4 else (material[0], material[1] if len(material) > 1 else 0.8, material[2] if len(material) > 2 else 0.01, "asphalt")
            self.materials_table.setItem(row, 0, QTableWidgetItem(str(s_offset)))
            self.materials_table.setItem(row, 1, QTableWidgetItem(str(friction)))
            self.materials_table.setItem(row, 2, QTableWidgetItem(str(roughness)))
            self.materials_table.setItem(row, 3, QTableWidgetItem(str(surface)))

    def _load_heights_table(self):
        """Load heights from lane into the table."""
        self.heights_table.setRowCount(0)
        for height in self.lane.heights:
            row = self.heights_table.rowCount()
            self.heights_table.insertRow(row)
            # Unpack tuple: (s_offset, inner, outer)
            s_offset, inner, outer = height[:3] if len(height) >= 3 else (height[0], height[1] if len(height) > 1 else 0.0, 0.0)
            self.heights_table.setItem(row, 0, QTableWidgetItem(str(s_offset)))
            self.heights_table.setItem(row, 1, QTableWidgetItem(str(inner)))
            self.heights_table.setItem(row, 2, QTableWidgetItem(str(outer)))

    def _get_materials_from_table(self) -> list:
        """Get materials list from table."""
        materials = []
        for row in range(self.materials_table.rowCount()):
            try:
                s_offset = float(self.materials_table.item(row, 0).text()) if self.materials_table.item(row, 0) else 0.0
                friction = float(self.materials_table.item(row, 1).text()) if self.materials_table.item(row, 1) else 0.8
                roughness = float(self.materials_table.item(row, 2).text()) if self.materials_table.item(row, 2) else 0.01
                surface = self.materials_table.item(row, 3).text() if self.materials_table.item(row, 3) else "asphalt"
                materials.append((s_offset, friction, roughness, surface))
            except ValueError:
                continue
        return materials

    def _get_heights_from_table(self) -> list:
        """Get heights list from table."""
        heights = []
        for row in range(self.heights_table.rowCount()):
            try:
                s_offset = float(self.heights_table.item(row, 0).text()) if self.heights_table.item(row, 0) else 0.0
                inner = float(self.heights_table.item(row, 1).text()) if self.heights_table.item(row, 1) else 0.0
                outer = float(self.heights_table.item(row, 2).text()) if self.heights_table.item(row, 2) else 0.0
                heights.append((s_offset, inner, outer))
            except ValueError:
                continue
        return heights

    def load_properties(self):
        """Load lane properties into the form."""
        # Set lane ID display
        self.lane_id_label.setText(self.lane.get_display_name())
        self.position_label.setText(self.lane.get_display_position())

        # Set lane type
        set_combo_by_data(self.lane_type_combo, self.lane.lane_type)

        # Set road mark type
        set_combo_by_data(self.road_mark_type_combo, self.lane.road_mark_type)

        # Set road mark styling
        set_combo_by_data(self.road_mark_color_combo, self.lane.road_mark_color)
        set_combo_by_data(self.road_mark_weight_combo, self.lane.road_mark_weight)
        self.road_mark_width_spin.setValue(self.lane.road_mark_width)

        # Set width based on lane type
        if self.width_spin is not None:
            # Regular road lane
            self.width_spin.setValue(self.lane.width)
        elif self.width_start_spin is not None and self.width_end_spin is not None:
            # Connecting road driving lane - load from connecting road
            if self.connecting_road.lane_width_start is not None:
                self.width_start_spin.setValue(self.connecting_road.lane_width_start)
            else:
                self.width_start_spin.setValue(self.connecting_road.lane_width)

            if self.connecting_road.lane_width_end is not None:
                self.width_end_spin.setValue(self.connecting_road.lane_width_end)
            else:
                self.width_end_spin.setValue(self.connecting_road.lane_width)

            self.update_width_info()

        # Set access restrictions
        self.bicycle_access_checkbox.setChecked('bicycle' in self.lane.access_restrictions)
        self.pedestrian_access_checkbox.setChecked('pedestrian' in self.lane.access_restrictions)

        # Update access visibility based on lane type
        self.update_access_visibility()

        # Load advanced section values (if available - not for connecting road lanes)
        if hasattr(self, 'width_b_spin'):
            self.width_b_spin.setValue(self.lane.width_b)
            self.width_c_spin.setValue(self.lane.width_c)
            self.width_d_spin.setValue(self.lane.width_d)

            # Speed limit - convert from m/s if stored
            if self.lane.speed_limit is not None:
                # Convert to display unit
                speed_val = self.lane.speed_limit
                unit = self.lane.speed_limit_unit
                if unit == "m/s":
                    # Show as m/s
                    self.speed_limit_spin.setValue(int(speed_val))
                    set_combo_by_data(self.speed_unit_combo, "m/s")
                elif unit == "km/h":
                    self.speed_limit_spin.setValue(int(speed_val))
                    set_combo_by_data(self.speed_unit_combo, "km/h")
                elif unit == "mph":
                    self.speed_limit_spin.setValue(int(speed_val))
                    set_combo_by_data(self.speed_unit_combo, "mph")
                else:
                    # Default assume m/s, convert to km/h for display
                    self.speed_limit_spin.setValue(int(speed_val * 3.6))
                    set_combo_by_data(self.speed_unit_combo, "km/h")
            else:
                self.speed_limit_spin.setValue(0)

            # Load V1.8 attributes
            set_combo_by_data(self.direction_combo, self.lane.direction)
            set_combo_by_data(self.advisory_combo, self.lane.advisory)
            self.level_checkbox.setChecked(self.lane.level)

            # Load lane links
            if self.lane.predecessor_id is not None:
                self.predecessor_spin.setValue(self.lane.predecessor_id)
            else:
                self.predecessor_spin.setValue(0)

            if self.lane.successor_id is not None:
                self.successor_spin.setValue(self.lane.successor_id)
            else:
                self.successor_spin.setValue(0)

            # Load materials and heights tables
            self._load_materials_table()
            self._load_heights_table()

            # Expand advanced section if any values are non-default
            has_non_default = (
                self.lane.width_b != 0.0 or
                self.lane.width_c != 0.0 or
                self.lane.width_d != 0.0 or
                self.lane.speed_limit is not None or
                self.lane.direction is not None or
                self.lane.advisory is not None or
                self.lane.level or
                self.lane.predecessor_id is not None or
                self.lane.successor_id is not None or
                len(self.lane.materials) > 0 or
                len(self.lane.heights) > 0
            )
            if has_non_default:
                self.advanced_toggle.setChecked(True)
                self._toggle_advanced(True)

        # Set boundary selections (if available)
        if self.project and self.road_id:
            # Left boundary
            if self.lane.left_boundary_id:
                set_combo_by_data(self.left_boundary_combo, self.lane.left_boundary_id)

            # Right boundary
            if self.lane.right_boundary_id:
                set_combo_by_data(self.right_boundary_combo, self.lane.right_boundary_id)

    def on_lane_type_changed(self):
        """Handle lane type change."""
        self.update_description()
        self.update_access_visibility()

    def update_width_info(self):
        """Update the width transition info label for connecting road lanes."""
        if self.width_info_label is None or self.width_start_spin is None or self.width_end_spin is None:
            return

        start_width = self.width_start_spin.value()
        end_width = self.width_end_spin.value()
        diff = end_width - start_width

        if abs(diff) < 0.01:
            self.width_info_label.setText("<i>Constant width along the connecting road.</i>")
        elif diff > 0:
            self.width_info_label.setText(
                f"<i>Lane width increases by {diff:.2f}m (linear transition).</i>"
            )
        else:
            self.width_info_label.setText(
                f"<i>Lane width decreases by {abs(diff):.2f}m (linear transition).</i>"
            )

    def update_access_visibility(self):
        """Show/hide access restrictions based on lane type."""
        lane_type = self.lane_type_combo.currentData()
        # Show access restrictions for path-related lane types
        is_path_lane = lane_type in (LaneType.BIKING, LaneType.SIDEWALK, LaneType.WALKING)
        self.access_widget.setVisible(is_path_lane)
        self.access_label_widget.setVisible(is_path_lane)

    def update_description(self):
        """Update the description based on lane type."""
        lane_type = self.lane_type_combo.currentData()

        descriptions = {
            LaneType.NONE: "Space on the outermost edge of the road. Used for center reference lane.",
            LaneType.DRIVING: "Normal drivable road that is not one of the other types.",
            LaneType.STOP: "Hard shoulder on motorways for emergency stops.",
            LaneType.SHOULDER: "Soft border at the edge of the road.",
            LaneType.BIKING: "Lane that is reserved for cyclists.",
            LaneType.SIDEWALK: "Pedestrian pathway (deprecated; use walking instead).",
            LaneType.BORDER: "Hard border at the edge of the road. Same height as drivable lane.",
            LaneType.RESTRICTED: "Lane on which cars should not drive. Same height as drivable lanes.",
            LaneType.PARKING: "Lane with parking spaces.",
            LaneType.BIDIRECTIONAL: "Two-way traffic lane for narrow roads.",
            LaneType.MEDIAN: "Lane between driving lanes that lead in opposite directions.",
            LaneType.CURB: "Curb at the edge of the road. Different height than adjacent lanes.",
            LaneType.ENTRY: "Acceleration lane parallel to main road merging into it.",
            LaneType.EXIT: "Deceleration lane parallel to main road leading away from it.",
            LaneType.ON_RAMP: "Ramp leading to a motorway from rural or urban roads.",
            LaneType.OFF_RAMP: "Ramp leading away from a motorway onto rural or urban roads.",
            LaneType.CONNECTING_RAMP: "Ramp that connects two motorways.",
            LaneType.SLIP_LANE: "Change roads without driving into main intersection.",
            LaneType.WALKING: "Lane on which pedestrians can walk.",
            LaneType.ROAD_WORKS: "Work zone lane.",
        }

        description = descriptions.get(lane_type, "")
        self.description_label.setText(description)

    def accept(self):
        """Save changes and accept dialog."""
        # Update lane properties
        self.lane.lane_type = self.lane_type_combo.currentData()
        self.lane.road_mark_type = self.road_mark_type_combo.currentData()

        # Update road mark styling
        self.lane.road_mark_color = self.road_mark_color_combo.currentData()
        self.lane.road_mark_weight = self.road_mark_weight_combo.currentData()
        self.lane.road_mark_width = self.road_mark_width_spin.value()

        # Update width based on lane type
        if self.width_spin is not None:
            # Regular road lane
            self.lane.width = self.width_spin.value()
        elif self.width_start_spin is not None and self.width_end_spin is not None and self.connecting_road is not None:
            # Connecting road driving lane - save to connecting road
            self.connecting_road.lane_width_start = self.width_start_spin.value()
            self.connecting_road.lane_width_end = self.width_end_spin.value()
            # Update average width for backward compatibility
            self.connecting_road.lane_width = (
                self.connecting_road.lane_width_start + self.connecting_road.lane_width_end
            ) / 2
            # Also update the individual lane's width to the average
            self.lane.width = self.connecting_road.lane_width

        # Update access restrictions (for path lanes)
        access_restrictions = []
        if self.bicycle_access_checkbox.isChecked():
            access_restrictions.append('bicycle')
        if self.pedestrian_access_checkbox.isChecked():
            access_restrictions.append('pedestrian')
        self.lane.access_restrictions = access_restrictions

        # Update advanced properties (if available - not for connecting road lanes)
        if hasattr(self, 'width_b_spin'):
            self.lane.width_b = self.width_b_spin.value()
            self.lane.width_c = self.width_c_spin.value()
            self.lane.width_d = self.width_d_spin.value()

            # Speed limit - store in the selected unit
            speed_val = self.speed_limit_spin.value()
            if speed_val > 0:
                self.lane.speed_limit = float(speed_val)
                self.lane.speed_limit_unit = self.speed_unit_combo.currentData()
            else:
                self.lane.speed_limit = None  # Inherit from road

            # Update V1.8 attributes
            self.lane.direction = self.direction_combo.currentData()
            self.lane.advisory = self.advisory_combo.currentData()
            self.lane.level = self.level_checkbox.isChecked()

            # Update lane links (0 means None)
            pred_val = self.predecessor_spin.value()
            self.lane.predecessor_id = pred_val if pred_val != 0 else None

            succ_val = self.successor_spin.value()
            self.lane.successor_id = succ_val if succ_val != 0 else None

            # Update materials and heights from tables
            self.lane.materials = self._get_materials_from_table()
            self.lane.heights = self._get_heights_from_table()

        # Update boundary selections (if available)
        if self.project and self.road_id:
            self.lane.left_boundary_id = self.left_boundary_combo.currentData()
            self.lane.right_boundary_id = self.right_boundary_combo.currentData()

        super().accept()

    @classmethod
    def edit_lane(cls, lane: Lane, project: Optional[Project] = None, road_id: Optional[str] = None,
                  connecting_road: Optional['ConnectingRoad'] = None, parent=None) -> bool:
        """
        Show dialog to edit a lane's properties.

        Args:
            lane: Lane to edit
            project: Project containing the lane (optional)
            road_id: ID of road containing the lane (optional)
            connecting_road: ConnectingRoad containing the lane (for connecting road lanes)
            parent: Parent widget

        Returns:
            True if properties were modified, False if cancelled
        """
        return cls.show_and_accept(lane, project, road_id, connecting_road, parent=parent)

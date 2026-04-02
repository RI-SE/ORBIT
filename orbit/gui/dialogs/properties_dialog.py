"""
Properties dialog for roads in ORBIT.

Allows editing of road properties including lanes, speed, type, etc.
"""

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from orbit.models import LineType, Project, Road, RoadType
from orbit.utils import format_enum_name
from orbit.utils.logging_config import get_logger

from ..utils import set_combo_by_data
from .base_dialog import InfoIconLabel

logger = get_logger(__name__)


class RoadPropertiesDialog(QDialog):
    """Dialog for editing road properties."""

    def __init__(
        self,
        road: Optional[Road] = None,
        project: Optional[Project] = None,
        parent=None,
        verbose: bool = False,
    ):
        super().__init__(parent)

        self.road = road if road else Road(id=project.next_id('road') if project else "")
        self.project = project
        self.measured_widths = None  # Will store suggested widths
        self.verbose = verbose  # Debug flag for verbose output
        self.setup_ui()
        self.load_data()
        self.calculate_suggested_widths()  # Calculate after loading data

    def setup_ui(self):
        """Setup the dialog UI."""
        road_id_short = self.road.id[:8] if len(self.road.id) > 8 else self.road.id
        self.setWindowTitle(f"Road Properties - ID: {road_id_short}")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        id_label = QLabel(f"<b>Road ID:</b> {self.road.id}")
        id_label.setWordWrap(True)
        id_label.setStyleSheet("QLabel { padding: 8px; background-color: #f0f0f0; border-radius: 3px; }")
        layout.addWidget(id_label)

        self._create_basic_properties_section(layout)
        if self.project:
            self._create_centerline_section(layout)
            self._create_road_links_section(layout)
        self._create_lane_config_section(layout)
        self._setup_profiles_section(layout)

        note_widget = InfoIconLabel(
            "Note",
            "Lane widths are in meters for georeferenced projects, "
            "or in pixels for non-georeferenced projects.",
            bold=False
        )
        layout.addWidget(note_widget)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _create_basic_properties_section(self, layout):
        """Create the basic road properties group."""
        basic_group = QGroupBox("Basic Properties")
        basic_layout = QFormLayout()

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Enter road name")
        basic_layout.addRow("Road Name:", self.name_edit)

        self.road_type_combo = QComboBox()
        for road_type in RoadType:
            self.road_type_combo.addItem(format_enum_name(road_type), road_type)
        basic_layout.addRow("Road Type:", self.road_type_combo)

        self.speed_limit_spin = QDoubleSpinBox()
        self.speed_limit_spin.setRange(0, 300)
        self.speed_limit_spin.setSuffix(" km/h")
        self.speed_limit_spin.setSpecialValueText("No limit")
        self.speed_limit_spin.setValue(0)
        basic_layout.addRow("Speed Limit:", self.speed_limit_spin)

        import importlib
        _osm_mappings = importlib.import_module('orbit.import.osm_mappings')

        self.surface_combo = QComboBox()
        self.surface_combo.addItem("—", None)
        for key in _osm_mappings.OSM_SURFACE_TO_MATERIAL:
            self.surface_combo.addItem(key.replace('_', ' ').title(), key)
        basic_layout.addRow("Surface:", self.surface_combo)

        self.smoothness_combo = QComboBox()
        self.smoothness_combo.addItem("—", None)
        for key in _osm_mappings.OSM_SMOOTHNESS_TO_ROUGHNESS:
            self.smoothness_combo.addItem(key.replace('_', ' ').title(), key)
        basic_layout.addRow("Condition:", self.smoothness_combo)

        basic_group.setLayout(basic_layout)
        layout.addWidget(basic_group)

    def _create_centerline_section(self, layout):
        """Create the road reference line selection group."""
        centerline_group = QGroupBox()
        centerline_main_layout = QVBoxLayout()

        centerline_title = InfoIconLabel(
            "Road Reference Line Selection",
            "The road reference line serves as the reference line in OpenDRIVE. "
            "Each road must have exactly one road reference line."
        )
        centerline_main_layout.addWidget(centerline_title)

        centerline_layout = QFormLayout()
        self.centerline_combo = QComboBox()
        self.centerline_combo.addItem("(No road reference line selected)", None)

        for polyline_id in self.road.polyline_ids:
            polyline = self.project.get_polyline(polyline_id)
            if polyline:
                type_tag = "ref" if polyline.line_type == LineType.CENTERLINE else "boundary"
                display_text = f"Polyline ({polyline.point_count()} pts, {type_tag})"
                self.centerline_combo.addItem(display_text, polyline_id)

        centerline_layout.addRow("Road Reference Line:", self.centerline_combo)

        self.centerline_warning_label = QLabel()
        self.centerline_warning_label.setWordWrap(True)
        centerline_layout.addRow("", self.centerline_warning_label)

        self.centerline_combo.currentIndexChanged.connect(
            lambda: self.update_centerline_warning()
        )
        self.update_centerline_warning()

        centerline_main_layout.addLayout(centerline_layout)
        centerline_group.setLayout(centerline_main_layout)
        layout.addWidget(centerline_group)

    def _create_road_links_section(self, layout):
        """Create the predecessor/successor road links group."""
        links_group = QGroupBox()
        links_main_layout = QVBoxLayout()

        links_title = InfoIconLabel(
            "Road Links (Predecessor/Successor)",
            "Each endpoint connects to either a junction OR a road — not both. "
            "Junction links take priority over road links during export. "
            "Set junction to '(Auto-detect)' to let the exporter determine this spatially."
        )
        links_main_layout.addWidget(links_title)

        _AUTO = "__auto__"

        # --- Predecessor endpoint group ---
        pred_group = QGroupBox("Predecessor")
        pred_layout = QFormLayout()

        self.predecessor_junction_combo = QComboBox()
        self.predecessor_junction_combo.addItem("(Auto-detect)", _AUTO)
        self.predecessor_junction_combo.addItem("(None — road link only)", "__none__")
        for junction in self.project.junctions:
            jid = junction.id[:8] + "..." if len(junction.id) > 8 else junction.id
            self.predecessor_junction_combo.addItem(f"{junction.name} ({jid})", junction.id)
        self.predecessor_junction_combo.setToolTip(
            "Auto-detect: exporter checks spatial proximity at export time.\n"
            "None: no junction link — road link below is used instead.\n"
            "Specific junction: always link to this junction (road link ignored)."
        )
        pred_layout.addRow("Junction:", self.predecessor_junction_combo)

        self.pred_junction_note = QLabel("⚠ Junction set — road link below is ignored in export.")
        self.pred_junction_note.setStyleSheet("QLabel { color: #b07000; font-style: italic; }")
        self.pred_junction_note.setVisible(False)
        pred_layout.addRow("", self.pred_junction_note)

        self.predecessor_combo = QComboBox()
        self.predecessor_combo.addItem("(No predecessor road)", None)
        for other_road in self.project.roads:
            if other_road.id != self.road.id:
                display_text = f"{other_road.name} (ID: {other_road.id[:8]}...)"
                self.predecessor_combo.addItem(display_text, other_road.id)
        pred_layout.addRow("Road:", self.predecessor_combo)

        self.predecessor_contact_combo = QComboBox()
        self.predecessor_contact_combo.addItem("End of predecessor", "end")
        self.predecessor_contact_combo.addItem("Start of predecessor", "start")
        pred_layout.addRow("Contact point:", self.predecessor_contact_combo)

        pred_group.setLayout(pred_layout)
        links_main_layout.addWidget(pred_group)

        # --- Successor endpoint group ---
        succ_group = QGroupBox("Successor")
        succ_layout = QFormLayout()

        self.successor_junction_combo = QComboBox()
        self.successor_junction_combo.addItem("(Auto-detect)", _AUTO)
        self.successor_junction_combo.addItem("(None — road link only)", "__none__")
        for junction in self.project.junctions:
            jid = junction.id[:8] + "..." if len(junction.id) > 8 else junction.id
            self.successor_junction_combo.addItem(f"{junction.name} ({jid})", junction.id)
        self.successor_junction_combo.setToolTip(
            "Auto-detect: exporter checks spatial proximity at export time.\n"
            "None: no junction link — road link below is used instead.\n"
            "Specific junction: always link to this junction (road link ignored)."
        )
        succ_layout.addRow("Junction:", self.successor_junction_combo)

        self.succ_junction_note = QLabel("⚠ Junction set — road link below is ignored in export.")
        self.succ_junction_note.setStyleSheet("QLabel { color: #b07000; font-style: italic; }")
        self.succ_junction_note.setVisible(False)
        succ_layout.addRow("", self.succ_junction_note)

        self.successor_combo = QComboBox()
        self.successor_combo.addItem("(No successor road)", None)
        for other_road in self.project.roads:
            if other_road.id != self.road.id:
                display_text = f"{other_road.name} (ID: {other_road.id[:8]}...)"
                self.successor_combo.addItem(display_text, other_road.id)
        succ_layout.addRow("Road:", self.successor_combo)

        self.successor_contact_combo = QComboBox()
        self.successor_contact_combo.addItem("Start of successor", "start")
        self.successor_contact_combo.addItem("End of successor", "end")
        succ_layout.addRow("Contact point:", self.successor_contact_combo)

        succ_group.setLayout(succ_layout)
        links_main_layout.addWidget(succ_group)

        links_group.setLayout(links_main_layout)
        layout.addWidget(links_group)

        # Wire up dynamic priority notes
        self.predecessor_junction_combo.currentIndexChanged.connect(self._update_pred_junction_note)
        self.successor_junction_combo.currentIndexChanged.connect(self._update_succ_junction_note)

    def _update_pred_junction_note(self):
        """Show/hide the predecessor junction priority warning."""
        data = self.predecessor_junction_combo.currentData()
        self.pred_junction_note.setVisible(data not in ("__auto__", "__none__", None))

    def _update_succ_junction_note(self):
        """Show/hide the successor junction priority warning."""
        data = self.successor_junction_combo.currentData()
        self.succ_junction_note.setVisible(data not in ("__auto__", "__none__", None))

    def _create_lane_config_section(self, layout):
        """Create the lane configuration group."""
        lane_group = QGroupBox("Lane Configuration")
        lane_layout = QFormLayout()

        lane_count_layout = QHBoxLayout()
        self.left_lanes_spin = QSpinBox()
        self.left_lanes_spin.setRange(0, 10)
        self.left_lanes_spin.setValue(1)
        self.left_lanes_spin.setPrefix("Left: ")
        lane_count_layout.addWidget(self.left_lanes_spin)
        lane_count_layout.addWidget(QLabel("    "))
        self.right_lanes_spin = QSpinBox()
        self.right_lanes_spin.setRange(0, 10)
        self.right_lanes_spin.setValue(1)
        self.right_lanes_spin.setPrefix("Right: ")
        lane_count_layout.addWidget(self.right_lanes_spin)
        lane_count_layout.addStretch()
        lane_layout.addRow("Number of Lanes:", lane_count_layout)

        self.lane_width_spin = QDoubleSpinBox()
        self.lane_width_spin.setRange(1.0, 10.0)
        self.lane_width_spin.setSingleStep(0.1)
        self.lane_width_spin.setValue(3.5)
        self.lane_width_spin.setSuffix(" m")
        self.lane_width_spin.setToolTip("Default lane width in meters")
        lane_layout.addRow("Lane Width:", self.lane_width_spin)

        self.measured_width_label = QLabel("<i>Calculating from boundaries...</i>")
        self.measured_width_label.setWordWrap(True)
        lane_layout.addRow("", self.measured_width_label)

        self.apply_measured_button = QPushButton("Apply Measured Width")
        self.apply_measured_button.setEnabled(False)
        self.apply_measured_button.clicked.connect(self.apply_measured_width)
        self.apply_measured_button.setToolTip("Apply the average width measured from lane boundaries")
        lane_layout.addRow("", self.apply_measured_button)

        self.total_lanes_label = QLabel()
        self.update_total_lanes()
        lane_layout.addRow("Total Lanes:", self.total_lanes_label)

        self.left_lanes_spin.valueChanged.connect(self.update_total_lanes)
        self.right_lanes_spin.valueChanged.connect(self.update_total_lanes)

        lane_group.setLayout(lane_layout)
        layout.addWidget(lane_group)

    def _setup_profiles_section(self, parent_layout: QVBoxLayout):
        """Setup the collapsible Profiles section with scroll area."""
        # Create collapsible toggle
        self.profiles_toggle = QToolButton()
        self.profiles_toggle.setStyleSheet("QToolButton { border: none; }")
        self.profiles_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.profiles_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.profiles_toggle.setText("Road Profiles (Elevation, Superelevation, Lane Offset)")
        self.profiles_toggle.setCheckable(True)
        self.profiles_toggle.setChecked(False)
        self.profiles_toggle.clicked.connect(self._toggle_profiles)

        parent_layout.addWidget(self.profiles_toggle)

        # Scroll area for the profiles content
        self.profiles_scroll = QScrollArea()
        self.profiles_scroll.setWidgetResizable(True)
        self.profiles_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.profiles_scroll.setMaximumHeight(450)

        # Container for profiles content
        self.profiles_widget = QWidget()
        profiles_layout = QVBoxLayout(self.profiles_widget)
        profiles_layout.setContentsMargins(10, 5, 10, 10)

        # Elevation Profile table
        elev_title = InfoIconLabel(
            "Elevation Profile",
            "Height along road: elev(s) = a + b·s + c·s² + d·s³"
        )
        profiles_layout.addWidget(elev_title)

        self.elevation_table = QTableWidget(0, 5)
        self.elevation_table.setHorizontalHeaderLabels(["s", "a", "b", "c", "d"])
        self.elevation_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.elevation_table.setMinimumHeight(80)
        profiles_layout.addWidget(self.elevation_table)

        elev_btn_widget = QWidget()
        elev_btn_layout = QHBoxLayout(elev_btn_widget)
        elev_btn_layout.setContentsMargins(0, 0, 0, 0)
        elev_btn_layout.addStretch()
        self.add_elevation_btn = QPushButton("+ Add")
        self.add_elevation_btn.clicked.connect(lambda: self._add_profile_row(self.elevation_table))
        elev_btn_layout.addWidget(self.add_elevation_btn)
        self.remove_elevation_btn = QPushButton("- Remove")
        self.remove_elevation_btn.clicked.connect(lambda: self._remove_profile_row(self.elevation_table))
        elev_btn_layout.addWidget(self.remove_elevation_btn)
        profiles_layout.addWidget(elev_btn_widget)

        # Superelevation Profile table
        super_title = InfoIconLabel(
            "Superelevation Profile (Lateral Tilt)",
            "Road banking for curves: tilt(s) = a + b·s + c·s² + d·s³"
        )
        profiles_layout.addWidget(super_title)

        self.superelevation_table = QTableWidget(0, 5)
        self.superelevation_table.setHorizontalHeaderLabels(["s", "a", "b", "c", "d"])
        self.superelevation_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.superelevation_table.setMinimumHeight(80)
        profiles_layout.addWidget(self.superelevation_table)

        super_btn_widget = QWidget()
        super_btn_layout = QHBoxLayout(super_btn_widget)
        super_btn_layout.setContentsMargins(0, 0, 0, 0)
        super_btn_layout.addStretch()
        self.add_superelevation_btn = QPushButton("+ Add")
        self.add_superelevation_btn.clicked.connect(lambda: self._add_profile_row(self.superelevation_table))
        super_btn_layout.addWidget(self.add_superelevation_btn)
        self.remove_superelevation_btn = QPushButton("- Remove")
        self.remove_superelevation_btn.clicked.connect(lambda: self._remove_profile_row(self.superelevation_table))
        super_btn_layout.addWidget(self.remove_superelevation_btn)
        profiles_layout.addWidget(super_btn_widget)

        # Lane Offset Profile table
        offset_title = InfoIconLabel(
            "Lane Offset Profile",
            "Center lane offset from reference line: offset(s) = a + b·s + c·s² + d·s³"
        )
        profiles_layout.addWidget(offset_title)

        self.lane_offset_table = QTableWidget(0, 5)
        self.lane_offset_table.setHorizontalHeaderLabels(["s", "a", "b", "c", "d"])
        self.lane_offset_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.lane_offset_table.setMinimumHeight(80)
        profiles_layout.addWidget(self.lane_offset_table)

        offset_btn_widget = QWidget()
        offset_btn_layout = QHBoxLayout(offset_btn_widget)
        offset_btn_layout.setContentsMargins(0, 0, 0, 0)
        offset_btn_layout.addStretch()
        self.add_lane_offset_btn = QPushButton("+ Add")
        self.add_lane_offset_btn.clicked.connect(lambda: self._add_profile_row(self.lane_offset_table))
        offset_btn_layout.addWidget(self.add_lane_offset_btn)
        self.remove_lane_offset_btn = QPushButton("- Remove")
        self.remove_lane_offset_btn.clicked.connect(lambda: self._remove_profile_row(self.lane_offset_table))
        offset_btn_layout.addWidget(self.remove_lane_offset_btn)
        profiles_layout.addWidget(offset_btn_widget)

        # Surface CRG table
        crg_title = InfoIconLabel(
            "Surface/CRG Links",
            "Links to OpenCRG surface files for detailed road roughness"
        )
        profiles_layout.addWidget(crg_title)

        self.surface_crg_table = QTableWidget(0, 5)
        self.surface_crg_table.setHorizontalHeaderLabels(["File", "S-Start", "S-End", "Orientation", "Mode"])
        self.surface_crg_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.surface_crg_table.setMinimumHeight(80)
        profiles_layout.addWidget(self.surface_crg_table)

        crg_btn_widget = QWidget()
        crg_btn_layout = QHBoxLayout(crg_btn_widget)
        crg_btn_layout.setContentsMargins(0, 0, 0, 0)
        crg_btn_layout.addStretch()
        self.add_crg_btn = QPushButton("+ Add")
        self.add_crg_btn.clicked.connect(self._add_crg_row)
        crg_btn_layout.addWidget(self.add_crg_btn)
        self.remove_crg_btn = QPushButton("- Remove")
        self.remove_crg_btn.clicked.connect(lambda: self._remove_profile_row(self.surface_crg_table))
        crg_btn_layout.addWidget(self.remove_crg_btn)
        profiles_layout.addWidget(crg_btn_widget)

        # Put profiles_widget in scroll area
        self.profiles_scroll.setWidget(self.profiles_widget)
        self.profiles_scroll.setVisible(False)
        parent_layout.addWidget(self.profiles_scroll)

    def _toggle_profiles(self, checked: bool):
        """Toggle visibility of profiles section."""
        self.profiles_scroll.setVisible(checked)
        if checked:
            self.profiles_toggle.setArrowType(Qt.ArrowType.DownArrow)
        else:
            self.profiles_toggle.setArrowType(Qt.ArrowType.RightArrow)

    def _add_profile_row(self, table: QTableWidget):
        """Add a new row to a profile table with default polynomial values."""
        row = table.rowCount()
        table.insertRow(row)
        # Default values: s=0, a=0, b=0, c=0, d=0
        table.setItem(row, 0, QTableWidgetItem("0.0"))
        table.setItem(row, 1, QTableWidgetItem("0.0"))
        table.setItem(row, 2, QTableWidgetItem("0.0"))
        table.setItem(row, 3, QTableWidgetItem("0.0"))
        table.setItem(row, 4, QTableWidgetItem("0.0"))

    def _add_crg_row(self):
        """Add a new row to the CRG table."""
        row = self.surface_crg_table.rowCount()
        self.surface_crg_table.insertRow(row)
        # Default values
        self.surface_crg_table.setItem(row, 0, QTableWidgetItem(""))  # file
        self.surface_crg_table.setItem(row, 1, QTableWidgetItem("0.0"))  # s_start
        self.surface_crg_table.setItem(row, 2, QTableWidgetItem(""))  # s_end (empty = road end)
        self.surface_crg_table.setItem(row, 3, QTableWidgetItem("same"))  # orientation
        self.surface_crg_table.setItem(row, 4, QTableWidgetItem("genuine"))  # mode

    def _remove_profile_row(self, table: QTableWidget):
        """Remove the selected row from a profile table."""
        current_row = table.currentRow()
        if current_row >= 0:
            table.removeRow(current_row)

    def _load_profile_table(self, table: QTableWidget, data: list):
        """Load polynomial profile data into a table."""
        table.setRowCount(0)
        for item in data:
            row = table.rowCount()
            table.insertRow(row)
            # item is a tuple of (s, a, b, c, d)
            for col, val in enumerate(item[:5]):
                table.setItem(row, col, QTableWidgetItem(str(val)))

    def _load_crg_table(self, data: list):
        """Load CRG data into the surface CRG table."""
        self.surface_crg_table.setRowCount(0)
        for crg in data:
            row = self.surface_crg_table.rowCount()
            self.surface_crg_table.insertRow(row)
            self.surface_crg_table.setItem(row, 0, QTableWidgetItem(str(crg.get('file', ''))))
            self.surface_crg_table.setItem(row, 1, QTableWidgetItem(str(crg.get('s_start', '0.0'))))
            self.surface_crg_table.setItem(row, 2, QTableWidgetItem(str(crg.get('s_end', ''))))
            self.surface_crg_table.setItem(row, 3, QTableWidgetItem(str(crg.get('orientation', 'same'))))
            self.surface_crg_table.setItem(row, 4, QTableWidgetItem(str(crg.get('mode', 'genuine'))))

    def _get_profile_from_table(self, table: QTableWidget) -> list:
        """Get polynomial profile data from a table as list of tuples."""
        data = []
        for row in range(table.rowCount()):
            try:
                values = []
                for col in range(5):
                    item = table.item(row, col)
                    values.append(float(item.text()) if item else 0.0)
                data.append(tuple(values))
            except ValueError:
                continue
        return data

    def _get_crg_from_table(self) -> list:
        """Get CRG data from the surface CRG table as list of dicts."""
        data = []
        for row in range(self.surface_crg_table.rowCount()):
            try:
                file_item = self.surface_crg_table.item(row, 0)
                file_val = file_item.text() if file_item else ""
                if not file_val:
                    continue  # Skip empty rows

                s_start_item = self.surface_crg_table.item(row, 1)
                s_end_item = self.surface_crg_table.item(row, 2)
                orientation_item = self.surface_crg_table.item(row, 3)
                mode_item = self.surface_crg_table.item(row, 4)

                crg = {
                    'file': file_val,
                    's_start': float(s_start_item.text()) if s_start_item and s_start_item.text() else 0.0,
                    'orientation': orientation_item.text() if orientation_item else 'same',
                    'mode': mode_item.text() if mode_item else 'genuine'
                }
                # Only add s_end if specified
                if s_end_item and s_end_item.text():
                    crg['s_end'] = float(s_end_item.text())

                data.append(crg)
            except ValueError:
                continue
        return data

    def load_data(self):
        """Load data from the road object."""
        self.name_edit.setText(self.road.name)

        # Set road type
        set_combo_by_data(self.road_type_combo, self.road.road_type)

        # Set speed limit
        if self.road.speed_limit is not None:
            self.speed_limit_spin.setValue(self.road.speed_limit)
        else:
            self.speed_limit_spin.setValue(0)

        # Set surface and condition combos from OSM tags or lane materials
        import importlib
        _osm_mappings = importlib.import_module('orbit.import.osm_mappings')

        surface_key = None
        roughness_val = None
        for section in self.road.lane_sections:
            for lane in section.lanes:
                if lane.materials:
                    _, _friction, roughness, sname = lane.materials[0]
                    if roughness is not None:
                        roughness_val = roughness
                    if sname:
                        # Reverse-lookup surface_name to OSM key
                        for k, (_, _, sn) in _osm_mappings.OSM_SURFACE_TO_MATERIAL.items():
                            if sn == sname:
                                surface_key = k
                                break
                    break
            if surface_key:
                break

        # OSM tags take priority over lane material reverse-lookup
        if self.road.osm_tags:
            if 'surface' in self.road.osm_tags:
                surface_key = self.road.osm_tags['surface']
            if 'smoothness' in self.road.osm_tags:
                smoothness_key = self.road.osm_tags['smoothness']
                set_combo_by_data(self.smoothness_combo, smoothness_key)
            elif roughness_val is not None:
                smoothness_name = _osm_mappings.get_roughness_smoothness(roughness_val)
                if smoothness_name:
                    set_combo_by_data(self.smoothness_combo, smoothness_name)
        elif roughness_val is not None:
            smoothness_name = _osm_mappings.get_roughness_smoothness(roughness_val)
            if smoothness_name:
                set_combo_by_data(self.smoothness_combo, smoothness_name)

        if surface_key:
            set_combo_by_data(self.surface_combo, surface_key)

        # Set centerline selection (if project available)
        if self.project and hasattr(self, 'centerline_combo'):
            # If road already has a centerline_id set, select it
            if self.road.centerline_id:
                set_combo_by_data(self.centerline_combo, self.road.centerline_id)
            else:
                # Auto-select: prefer the single CENTERLINE polyline,
                # otherwise auto-select if only one polyline is assigned.
                centerline_polylines = [
                    pid for pid in self.road.polyline_ids
                    if (p := self.project.get_polyline(pid)) and p.line_type == LineType.CENTERLINE
                ]
                if len(centerline_polylines) == 1:
                    set_combo_by_data(self.centerline_combo, centerline_polylines[0])
                elif len(self.road.polyline_ids) == 1:
                    set_combo_by_data(self.centerline_combo, self.road.polyline_ids[0])

        # Set road links (if project available)
        if self.project and hasattr(self, 'predecessor_combo'):
            # Set predecessor
            if self.road.predecessor_id:
                set_combo_by_data(self.predecessor_combo, self.road.predecessor_id)

            # Set predecessor contact point
            set_combo_by_data(self.predecessor_contact_combo, self.road.predecessor_contact)

            # Set successor
            if self.road.successor_id:
                set_combo_by_data(self.successor_combo, self.road.successor_id)

            # Set successor contact point
            set_combo_by_data(self.successor_contact_combo, self.road.successor_contact)

            # Set junction link overrides
            _AUTO = "__auto__"
            if self.road.predecessor_junction_id is not None:
                set_combo_by_data(self.predecessor_junction_combo, self.road.predecessor_junction_id)
            else:
                set_combo_by_data(self.predecessor_junction_combo, _AUTO)

            if self.road.successor_junction_id is not None:
                set_combo_by_data(self.successor_junction_combo, self.road.successor_junction_id)
            else:
                set_combo_by_data(self.successor_junction_combo, _AUTO)

            # Update priority notes after loading values
            self._update_pred_junction_note()
            self._update_succ_junction_note()

        # Set lane info
        self.left_lanes_spin.setValue(self.road.lane_info.left_count)
        self.right_lanes_spin.setValue(self.road.lane_info.right_count)
        self.lane_width_spin.setValue(self.road.lane_info.lane_width)

        # Load profile tables
        self._load_profile_table(self.elevation_table, self.road.elevation_profile)
        self._load_profile_table(self.superelevation_table, self.road.superelevation_profile)
        self._load_profile_table(self.lane_offset_table, self.road.lane_offset)
        self._load_crg_table(self.road.surface_crg)

        # Auto-expand profiles section if any profiles exist
        has_profiles = (
            len(self.road.elevation_profile) > 0 or
            len(self.road.superelevation_profile) > 0 or
            len(self.road.lane_offset) > 0 or
            len(self.road.surface_crg) > 0
        )
        if has_profiles:
            self.profiles_toggle.setChecked(True)
            self._toggle_profiles(True)

    def save_data(self):
        """Save data back to the road object."""
        self.road.name = self.name_edit.text().strip() or "Unnamed Road"
        self.road.road_type = self.road_type_combo.currentData()

        # Speed limit
        speed = self.speed_limit_spin.value()
        self.road.speed_limit = speed if speed > 0 else None

        # Surface and condition
        import importlib
        _osm_mappings = importlib.import_module('orbit.import.osm_mappings')

        if not self.road.osm_tags:
            self.road.osm_tags = {}

        surface_key = self.surface_combo.currentData()
        smoothness_key = self.smoothness_combo.currentData()

        if surface_key:
            self.road.osm_tags['surface'] = surface_key
            friction, roughness, surface_name = _osm_mappings.OSM_SURFACE_TO_MATERIAL[surface_key]
            # Override roughness if smoothness is also selected
            if smoothness_key:
                roughness = _osm_mappings.OSM_SMOOTHNESS_TO_ROUGHNESS[smoothness_key]
            for section in self.road.lane_sections:
                for lane in section.lanes:
                    lane.materials = [(0.0, friction, roughness, surface_name)]
        else:
            self.road.osm_tags.pop('surface', None)

        if smoothness_key:
            self.road.osm_tags['smoothness'] = smoothness_key
            # Update roughness on existing materials even without surface change
            if not surface_key:
                roughness = _osm_mappings.OSM_SMOOTHNESS_TO_ROUGHNESS[smoothness_key]
                for section in self.road.lane_sections:
                    for lane in section.lanes:
                        if lane.materials:
                            s, f, _r, sn = lane.materials[0]
                            lane.materials = [(s, f, roughness, sn)]
        else:
            self.road.osm_tags.pop('smoothness', None)

        # Centerline selection (if project available)
        if self.project and hasattr(self, 'centerline_combo'):
            selected_cl_id = self.centerline_combo.currentData()
            self.road.centerline_id = selected_cl_id
            # Mark the selected polyline as CENTERLINE (and others as LANE_BOUNDARY)
            if selected_cl_id:
                for pid in self.road.polyline_ids:
                    polyline = self.project.get_polyline(pid)
                    if polyline:
                        polyline.line_type = (
                            LineType.CENTERLINE if pid == selected_cl_id
                            else LineType.LANE_BOUNDARY
                        )

        # Road links (if project available)
        if self.project and hasattr(self, 'predecessor_combo'):
            self.road.predecessor_id = self.predecessor_combo.currentData()
            self.road.predecessor_contact = self.predecessor_contact_combo.currentData()
            self.road.successor_id = self.successor_combo.currentData()
            self.road.successor_contact = self.successor_contact_combo.currentData()

            # Junction link overrides
            _AUTO = "__auto__"
            pred_junc = self.predecessor_junction_combo.currentData()
            self.road.predecessor_junction_id = None if pred_junc == _AUTO else pred_junc

            succ_junc = self.successor_junction_combo.currentData()
            self.road.successor_junction_id = None if succ_junc == _AUTO else succ_junc

            # Enforce endpoint coordinate alignment with connected roads
            self.project.enforce_road_link_coordinates(self.road.id)

        # Lane info
        old_left_count = self.road.lane_info.left_count
        old_right_count = self.road.lane_info.right_count
        old_lane_width = self.road.lane_info.lane_width

        new_left_count = self.left_lanes_spin.value()
        new_right_count = self.right_lanes_spin.value()
        new_lane_width = self.lane_width_spin.value()

        self.road.lane_info.left_count = new_left_count
        self.road.lane_info.right_count = new_right_count
        self.road.lane_info.lane_width = new_lane_width

        # Regenerate lanes if counts or default width changed
        if (old_left_count != new_left_count or
            old_right_count != new_right_count or
            old_lane_width != new_lane_width):
            self.road.generate_lanes()

        # Save profile tables
        self.road.elevation_profile = self._get_profile_from_table(self.elevation_table)
        self.road.superelevation_profile = self._get_profile_from_table(self.superelevation_table)
        self.road.lane_offset = self._get_profile_from_table(self.lane_offset_table)
        self.road.surface_crg = self._get_crg_from_table()

    def update_centerline_warning(self):
        """Update the centerline warning based on combo selection."""
        if not self.project or not hasattr(self, 'centerline_warning_label'):
            return

        has_polylines = len(self.road.polyline_ids) > 0
        has_selection = self.centerline_combo.currentData() is not None

        if not has_polylines:
            self.centerline_warning_label.setText(
                "<b style='color: #ff6600;'>No polylines assigned to this road.</b>"
            )
            self.centerline_warning_label.setStyleSheet(
                "QLabel { padding: 5px; "
                "background-color: #fff3cd; border-radius: 3px; }"
            )
        elif not has_selection:
            self.centerline_warning_label.setText(
                "<b style='color: #ff6600;'>Please select a road reference line above.</b>"
            )
            self.centerline_warning_label.setStyleSheet(
                "QLabel { padding: 5px; "
                "background-color: #fff3cd; border-radius: 3px; }"
            )
        else:
            self.centerline_warning_label.setText(
                "<b style='color: #28a745;'>"
                "Road reference line selected."
                "</b>"
            )
            self.centerline_warning_label.setStyleSheet(
                "QLabel { padding: 5px; "
                "background-color: #d4edda; border-radius: 3px; }"
            )

    def update_total_lanes(self):
        """Update the total lanes display."""
        total = self.left_lanes_spin.value() + self.right_lanes_spin.value()
        self.total_lanes_label.setText(f"{total} lanes")

    def calculate_suggested_widths(self):
        """Calculate suggested lane widths from boundaries."""
        if not self.project or not self.road:
            self.measured_width_label.setText("<i>No boundaries to measure</i>")
            self.apply_measured_button.setEnabled(False)
            return

        if self.verbose:
            logger.debug("calculate_suggested_widths called for road: %s", self.road.name)

        try:
            from orbit.export.lane_analyzer import LaneAnalyzer

            # Get scale factors from georeferencing if available
            scale_factors = None
            if self.project.has_georeferencing():
                try:
                    from orbit.export import create_transformer
                    transformer = create_transformer(self.project.control_points)
                    if transformer:
                        scale_factors = transformer.get_scale_factor()
                        if self.verbose:
                            logger.debug("Scale factors retrieved: %s", scale_factors)
                except Exception as e:
                    if self.verbose:
                        logger.debug("Failed to get scale factors: %s", e)
                    pass
            else:
                if self.verbose:
                    logger.debug("No georeferencing available")

            analyzer = LaneAnalyzer(self.project, self.project.right_hand_traffic, scale_factors)
            self.measured_widths = analyzer.suggest_lane_widths(self.road, verbose=self.verbose)

            if self.measured_widths:
                avg = self.measured_widths['average']
                std = self.measured_widths['std']
                current = self.lane_width_spin.value()
                diff = avg - current

                diff_str = f"+{diff:.2f}" if diff >= 0 else f"{diff:.2f}"
                color = "#28a745" if abs(diff) < 0.3 else "#ff6600"

                # Add warning if no georeferencing
                if scale_factors is None:
                    warning = "<br><span style='color: orange;'>⚠ No georeferencing - using pixels as meters</span>"
                else:
                    warning = ""

                self.measured_width_label.setText(
                    f"<b>Measured from boundaries:</b> {avg:.2f} m (±{std:.2f} m)<br>"
                    f"<span style='color: {color};'>Difference: {diff_str} m</span>"
                    f"{warning}"
                )
                self.apply_measured_button.setEnabled(True)
            else:
                self.measured_width_label.setText(
                    "<i>No lane boundaries found to measure width</i>"
                )
                self.apply_measured_button.setEnabled(False)

        except Exception as e:
            self.measured_width_label.setText(
                f"<i>Error calculating widths: {str(e)}</i>"
            )
            self.apply_measured_button.setEnabled(False)

    def apply_measured_width(self):
        """Apply the measured lane width to the lane width spinner."""
        if self.measured_widths:
            avg = self.measured_widths['average']
            self.lane_width_spin.setValue(avg)
            self.measured_width_label.setText(
                f"<b style='color: #28a745;'>✓ Applied measured width: {avg:.2f} m</b>"
            )
            self.apply_measured_button.setEnabled(False)

    def accept(self):
        """Handle dialog acceptance."""
        self.save_data()
        super().accept()

    def get_road(self) -> Road:
        """Get the road object with updated properties."""
        return self.road

    @classmethod
    def edit_road(
        cls,
        road: Road,
        project: Optional[Project] = None,
        parent=None,
        verbose: bool = False,
    ) -> Optional[Road]:
        """
        Show dialog to edit a road's properties.

        Args:
            road: Road to edit
            project: Project containing the road (optional)
            parent: Parent widget
            verbose: Enable verbose output for debugging

        Returns:
            The modified road if accepted, None if cancelled
        """
        dialog = cls(road, project, parent, verbose=verbose)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.get_road()
        return None

    @classmethod
    def create_road(
        cls,
        project: Optional[Project] = None,
        parent=None,
        verbose: bool = False,
        initial_polyline_ids: Optional[list] = None,
    ) -> Optional[Road]:
        """
        Show dialog to create a new road.

        Args:
            project: Project to contain the new road (optional)
            parent: Parent widget
            verbose: Enable verbose output for debugging
            initial_polyline_ids: Polyline IDs to pre-assign before opening the dialog,
                so the centerline combo is populated on first open.

        Returns:
            The new road if accepted, None if cancelled
        """
        road = Road(id=project.next_id('road') if project else "")
        if initial_polyline_ids:
            for pid in initial_polyline_ids:
                road.add_polyline(pid)
        dialog = cls(road, project, parent, verbose=verbose)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.get_road()
        return None

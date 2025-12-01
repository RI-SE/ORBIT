"""
Properties dialog for roads in ORBIT.

Allows editing of road properties including lanes, speed, type, etc.
"""

from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox,
    QPushButton, QGroupBox, QLabel, QDialogButtonBox, QCheckBox
)
from PyQt6.QtCore import Qt

from orbit.models import Road, RoadType, LaneInfo, Project, LineType
from orbit.utils import format_enum_name
from ..utils import set_combo_by_data


class RoadPropertiesDialog(QDialog):
    """Dialog for editing road properties."""

    def __init__(self, road: Optional[Road] = None, project: Optional[Project] = None, parent=None, verbose: bool = False):
        super().__init__(parent)

        self.road = road if road else Road()
        self.project = project
        self.measured_widths = None  # Will store suggested widths
        self.verbose = verbose  # Debug flag for verbose output
        self.setup_ui()
        self.load_data()
        self.calculate_suggested_widths()  # Calculate after loading data

    def setup_ui(self):
        """Setup the dialog UI."""
        # Set title with road ID
        road_id_short = self.road.id[:8] if len(self.road.id) > 8 else self.road.id
        self.setWindowTitle(f"Road Properties - ID: {road_id_short}")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        # Road ID display (read-only)
        id_label = QLabel(f"<b>Road ID:</b> {self.road.id}")
        id_label.setWordWrap(True)
        id_label.setStyleSheet("QLabel { padding: 8px; background-color: #f0f0f0; border-radius: 3px; }")
        layout.addWidget(id_label)

        # Basic properties group
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

        basic_group.setLayout(basic_layout)
        layout.addWidget(basic_group)

        # Centerline selection group (only if project available)
        if self.project:
            centerline_group = QGroupBox("Road Reference Line Selection")
            centerline_layout = QFormLayout()

            self.centerline_combo = QComboBox()
            self.centerline_combo.addItem("(No road reference line selected)", None)

            # Add ONLY centerline polylines assigned to this road
            for polyline_id in self.road.polyline_ids:
                polyline = self.project.get_polyline(polyline_id)
                if polyline and polyline.line_type == LineType.CENTERLINE:
                    display_text = f"Polyline ({polyline.point_count()} pts)"
                    self.centerline_combo.addItem(display_text, polyline_id)

            centerline_layout.addRow("Road Reference Line:", self.centerline_combo)

            # Warning label for centerline count
            self.centerline_warning_label = QLabel()
            self.centerline_warning_label.setWordWrap(True)
            centerline_layout.addRow("", self.centerline_warning_label)

            # Update warning initially
            self.update_centerline_warning()

            # Info label
            centerline_info = QLabel(
                "<i>The road reference line serves as the reference line in OpenDRIVE. "
                "Each road must have exactly one road reference line.</i>"
            )
            centerline_info.setWordWrap(True)
            centerline_info.setStyleSheet("QLabel { color: gray; font-style: italic; }")
            centerline_layout.addRow("", centerline_info)

            centerline_group.setLayout(centerline_layout)
            layout.addWidget(centerline_group)

        # Road links group (only if project available)
        if self.project:
            links_group = QGroupBox("Road Links (Predecessor/Successor)")
            links_layout = QFormLayout()

            # Predecessor selection
            self.predecessor_combo = QComboBox()
            self.predecessor_combo.addItem("(No predecessor)", None)
            for other_road in self.project.roads:
                if other_road.id != self.road.id:
                    display_text = f"{other_road.name} (ID: {other_road.id[:8]}...)"
                    self.predecessor_combo.addItem(display_text, other_road.id)
            links_layout.addRow("Predecessor Road:", self.predecessor_combo)

            self.predecessor_contact_combo = QComboBox()
            self.predecessor_contact_combo.addItem("End of predecessor", "end")
            self.predecessor_contact_combo.addItem("Start of predecessor", "start")
            links_layout.addRow("Connects at:", self.predecessor_contact_combo)

            # Successor selection
            self.successor_combo = QComboBox()
            self.successor_combo.addItem("(No successor)", None)
            for other_road in self.project.roads:
                if other_road.id != self.road.id:
                    display_text = f"{other_road.name} (ID: {other_road.id[:8]}...)"
                    self.successor_combo.addItem(display_text, other_road.id)
            links_layout.addRow("Successor Road:", self.successor_combo)

            self.successor_contact_combo = QComboBox()
            self.successor_contact_combo.addItem("Start of successor", "start")
            self.successor_contact_combo.addItem("End of successor", "end")
            links_layout.addRow("Connects at:", self.successor_contact_combo)

            # Info label
            links_info = QLabel(
                "<i>These links define road connectivity for OpenDRIVE export. "
                "Set predecessor and successor to connect roads end-to-end.</i>"
            )
            links_info.setWordWrap(True)
            links_info.setStyleSheet("QLabel { color: gray; font-style: italic; }")
            links_layout.addRow("", links_info)

            links_group.setLayout(links_layout)
            layout.addWidget(links_group)

        # Lane properties group
        lane_group = QGroupBox("Lane Configuration")
        lane_layout = QFormLayout()

        # Lane counts
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

        # Lane width
        self.lane_width_spin = QDoubleSpinBox()
        self.lane_width_spin.setRange(1.0, 10.0)
        self.lane_width_spin.setSingleStep(0.1)
        self.lane_width_spin.setValue(3.5)
        self.lane_width_spin.setSuffix(" m")
        self.lane_width_spin.setToolTip("Default lane width in meters")
        lane_layout.addRow("Lane Width:", self.lane_width_spin)

        # Measured width display and suggestion
        self.measured_width_label = QLabel("<i>Calculating from boundaries...</i>")
        self.measured_width_label.setWordWrap(True)
        lane_layout.addRow("", self.measured_width_label)

        self.apply_measured_button = QPushButton("Apply Measured Width")
        self.apply_measured_button.setEnabled(False)
        self.apply_measured_button.clicked.connect(self.apply_measured_width)
        self.apply_measured_button.setToolTip("Apply the average width measured from lane boundaries")
        lane_layout.addRow("", self.apply_measured_button)

        # Total lanes display
        self.total_lanes_label = QLabel()
        self.update_total_lanes()
        lane_layout.addRow("Total Lanes:", self.total_lanes_label)

        # Connect signals to update total
        self.left_lanes_spin.valueChanged.connect(self.update_total_lanes)
        self.right_lanes_spin.valueChanged.connect(self.update_total_lanes)

        lane_group.setLayout(lane_layout)
        layout.addWidget(lane_group)

        # Info section
        info_label = QLabel(
            "<i>Note: Lane widths are in meters for georeferenced projects, "
            "or in pixels for non-georeferenced projects.</i>"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

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

        # Set centerline selection (if project available)
        if self.project and hasattr(self, 'centerline_combo'):
            # If road already has a centerline_id set, select it
            if self.road.centerline_id:
                set_combo_by_data(self.centerline_combo, self.road.centerline_id)
            else:
                # Auto-select if there's exactly one centerline polyline
                centerline_polylines = []
                for polyline_id in self.road.polyline_ids:
                    polyline = self.project.get_polyline(polyline_id)
                    if polyline and polyline.line_type == LineType.CENTERLINE:
                        centerline_polylines.append(polyline_id)

                if len(centerline_polylines) == 1:
                    # Auto-select the single centerline
                    single_centerline_id = centerline_polylines[0]
                    set_combo_by_data(self.centerline_combo, single_centerline_id)

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

        # Set lane info
        self.left_lanes_spin.setValue(self.road.lane_info.left_count)
        self.right_lanes_spin.setValue(self.road.lane_info.right_count)
        self.lane_width_spin.setValue(self.road.lane_info.lane_width)

    def save_data(self):
        """Save data back to the road object."""
        self.road.name = self.name_edit.text().strip() or "Unnamed Road"
        self.road.road_type = self.road_type_combo.currentData()

        # Speed limit
        speed = self.speed_limit_spin.value()
        self.road.speed_limit = speed if speed > 0 else None

        # Centerline selection (if project available)
        if self.project and hasattr(self, 'centerline_combo'):
            self.road.centerline_id = self.centerline_combo.currentData()

        # Road links (if project available)
        if self.project and hasattr(self, 'predecessor_combo'):
            self.road.predecessor_id = self.predecessor_combo.currentData()
            self.road.predecessor_contact = self.predecessor_contact_combo.currentData()
            self.road.successor_id = self.successor_combo.currentData()
            self.road.successor_contact = self.successor_contact_combo.currentData()

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

    def update_centerline_warning(self):
        """Update the centerline warning based on how many centerlines exist."""
        if not self.project or not hasattr(self, 'centerline_warning_label'):
            return

        # Count centerline polylines in this road
        centerline_count = 0
        for polyline_id in self.road.polyline_ids:
            polyline = self.project.get_polyline(polyline_id)
            if polyline and polyline.line_type == LineType.CENTERLINE:
                centerline_count += 1

        # Display warning based on count
        if centerline_count == 0:
            self.centerline_warning_label.setText(
                "<b style='color: #ff6600;'>⚠ Warning: No road reference lines found among road's polylines.</b><br>"
                "Mark one polyline as a road reference line (double-click the polyline)."
            )
            self.centerline_warning_label.setStyleSheet("QLabel { padding: 5px; background-color: #fff3cd; border-radius: 3px; }")
        elif centerline_count == 1:
            self.centerline_warning_label.setText(
                "<b style='color: #28a745;'>✓ Good: Exactly one road reference line found.</b>"
            )
            self.centerline_warning_label.setStyleSheet("QLabel { padding: 5px; background-color: #d4edda; border-radius: 3px; }")
        else:  # centerline_count > 1
            self.centerline_warning_label.setText(
                f"<b style='color: #dc3545;'>✗ Error: {centerline_count} road reference lines found, but only 1 is allowed.</b><br>"
                "Change extra road reference lines to lane boundaries (double-click polylines)."
            )
            self.centerline_warning_label.setStyleSheet("QLabel { padding: 5px; background-color: #f8d7da; border-radius: 3px; }")

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
            print(f"\n[DEBUG] calculate_suggested_widths called for road: {self.road.name}")
            print(f"[DEBUG] Verbose mode: {self.verbose}")

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
                            print(f"[DEBUG] Scale factors retrieved: {scale_factors}")
                except Exception as e:
                    if self.verbose:
                        print(f"[DEBUG] Failed to get scale factors: {e}")
                    pass
            else:
                if self.verbose:
                    print("[DEBUG] No georeferencing available")

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
    def edit_road(cls, road: Road, project: Optional[Project] = None, parent=None, verbose: bool = False) -> Optional[Road]:
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
    def create_road(cls, project: Optional[Project] = None, parent=None, verbose: bool = False) -> Optional[Road]:
        """
        Show dialog to create a new road.

        Args:
            project: Project to contain the new road (optional)
            parent: Parent widget
            verbose: Enable verbose output for debugging

        Returns:
            The new road if accepted, None if cancelled
        """
        dialog = cls(None, project, parent, verbose=verbose)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.get_road()
        return None

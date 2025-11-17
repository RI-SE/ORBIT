"""
Lane properties dialog for ORBIT.

Allows editing of individual lane properties.
"""

from typing import Optional

from PyQt6.QtWidgets import (
    QDialog,
    QComboBox, QLabel, QDoubleSpinBox
)

from orbit.models import Lane, LaneType, RoadMarkType, Project, LineType
from orbit.utils import format_enum_name
from orbit.gui.base_dialog import BaseDialog


class LanePropertiesDialog(BaseDialog):
    """Dialog for editing lane properties."""

    def __init__(self, lane: Lane, project: Optional[Project] = None, road_id: Optional[str] = None, parent=None):
        super().__init__("Lane Properties", parent, min_width=450)

        self.lane = lane
        self.project = project
        self.road_id = road_id
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

        # Lane width
        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(0.0, 20.0)
        self.width_spin.setSingleStep(0.1)
        self.width_spin.setValue(3.5)
        self.width_spin.setSuffix(" m")
        self.width_spin.setToolTip("Lane width in meters (or pixels if not georeferenced)")
        props_layout.addRow("Width:", self.width_spin)

        # Description label
        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet("QLabel { color: gray; font-style: italic; }")
        props_layout.addRow("", self.description_label)

        # Boundary polylines (if project available)
        if self.project and self.road_id:
            boundary_layout = self.add_form_group("Boundary Polylines")

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

            # Info label
            boundary_info = QLabel(
                "<i>Assign polylines that define the left and right edges of this lane. "
                "Leave unassigned if boundaries should be inferred from road mark type.</i>"
            )
            boundary_info.setWordWrap(True)
            boundary_info.setStyleSheet("QLabel { color: gray; font-style: italic; }")
            boundary_layout.addRow("", boundary_info)

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

    def load_properties(self):
        """Load lane properties into the form."""
        # Set lane ID display
        self.lane_id_label.setText(self.lane.get_display_name())
        self.position_label.setText(self.lane.get_display_position())

        # Set lane type
        for i in range(self.lane_type_combo.count()):
            if self.lane_type_combo.itemData(i) == self.lane.lane_type:
                self.lane_type_combo.setCurrentIndex(i)
                break

        # Set road mark type
        for i in range(self.road_mark_type_combo.count()):
            if self.road_mark_type_combo.itemData(i) == self.lane.road_mark_type:
                self.road_mark_type_combo.setCurrentIndex(i)
                break

        # Set width
        self.width_spin.setValue(self.lane.width)

        # Set boundary selections (if available)
        if self.project and self.road_id:
            # Left boundary
            if self.lane.left_boundary_id:
                for i in range(self.left_boundary_combo.count()):
                    if self.left_boundary_combo.itemData(i) == self.lane.left_boundary_id:
                        self.left_boundary_combo.setCurrentIndex(i)
                        break

            # Right boundary
            if self.lane.right_boundary_id:
                for i in range(self.right_boundary_combo.count()):
                    if self.right_boundary_combo.itemData(i) == self.lane.right_boundary_id:
                        self.right_boundary_combo.setCurrentIndex(i)
                        break

    def on_lane_type_changed(self):
        """Handle lane type change."""
        self.update_description()

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
        self.lane.width = self.width_spin.value()

        # Update boundary selections (if available)
        if self.project and self.road_id:
            self.lane.left_boundary_id = self.left_boundary_combo.currentData()
            self.lane.right_boundary_id = self.right_boundary_combo.currentData()

        super().accept()

    @classmethod
    def edit_lane(cls, lane: Lane, project: Optional[Project] = None, road_id: Optional[str] = None, parent=None) -> bool:
        """
        Show dialog to edit a lane's properties.

        Args:
            lane: Lane to edit
            project: Project containing the lane (optional)
            road_id: ID of road containing the lane (optional)
            parent: Parent widget

        Returns:
            True if properties were modified, False if cancelled
        """
        return cls.show_and_accept(lane, project, road_id, parent=parent)

"""
Add lane dialog for ORBIT.

Collects the position and properties for a lane inserted into one section.
"""

from typing import Optional

from PyQt6.QtWidgets import QComboBox, QDialog, QDoubleSpinBox, QLabel

from orbit.models import Lane, LaneSection, LaneType, Road, RoadMarkType

from .base_dialog import BaseDialog


class AddLaneDialog(BaseDialog):
    """Dialog for adding a lane to a single lane section."""

    def __init__(self, section: LaneSection, road: Road, parent=None):
        super().__init__(
            f"Add Lane to Section {section.section_number}", parent, min_width=400)
        self.section = section
        self.road = road
        self.setup_ui()

    def setup_ui(self):
        """Setup the dialog UI."""
        position_layout = self.add_form_group("Position")

        self.side_combo = QComboBox()
        if self.section.single_side != "right":
            self.side_combo.addItem("Left", 1)
        if self.section.single_side != "left":
            self.side_combo.addItem("Right", -1)
        self.side_combo.currentIndexChanged.connect(self._rebuild_positions)
        position_layout.addRow("Side:", self.side_combo)

        self.position_combo = QComboBox()
        position_layout.addRow("Insert at:", self.position_combo)
        self._rebuild_positions()

        props_layout = self.add_form_group("Lane Properties")

        self.lane_type_combo = QComboBox()
        for lane_type in LaneType:
            self.lane_type_combo.addItem(lane_type.value, lane_type)
        self.lane_type_combo.setCurrentText(LaneType.DRIVING.value)
        props_layout.addRow("Lane Type:", self.lane_type_combo)

        self.road_mark_combo = QComboBox()
        for mark_type in RoadMarkType:
            self.road_mark_combo.addItem(mark_type.value, mark_type)
        self.road_mark_combo.setCurrentText(RoadMarkType.BROKEN.value)
        props_layout.addRow("Road Mark:", self.road_mark_combo)

        width_layout = self.add_form_group_with_info(
            "Width",
            "Use different start/end widths for a taper: 0 → 3.5 m for a lane "
            "that appears (split), 3.5 → 0 m for a lane that merges."
        )
        self.width_start_spin = self._make_width_spin(3.5)
        width_layout.addRow("Width at Start:", self.width_start_spin)
        self.width_end_spin = self._make_width_spin(3.5)
        width_layout.addRow("Width at End:", self.width_end_spin)

        lanes_on_side = self._lane_ids_on_side()
        info = QLabel(f"Section has {len(lanes_on_side)} lane(s) on the selected side. "
                      "Outward lanes are renumbered; lane links and junction "
                      "connections are updated automatically.")
        info.setWordWrap(True)
        self.get_main_layout().addWidget(info)

        self.create_button_box()

    @staticmethod
    def _make_width_spin(value: float) -> QDoubleSpinBox:
        """Create a width spinbox in meters."""
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 20.0)
        spin.setSingleStep(0.1)
        spin.setDecimals(2)
        spin.setSuffix(" m")
        spin.setValue(value)
        return spin

    def _lane_ids_on_side(self):
        """Absolute lane IDs on the currently selected side."""
        sign = self.side_combo.currentData() or 1
        return sorted(abs(lane.id) for lane in self.section.lanes
                      if lane.id != 0 and (lane.id > 0) == (sign > 0))

    def _rebuild_positions(self):
        """Rebuild the insert-position combo for the selected side."""
        sign = self.side_combo.currentData() or 1
        count = len(self._lane_ids_on_side())
        self.position_combo.clear()
        for pos in range(1, count + 2):
            if pos == 1:
                label = f"Innermost (lane {sign * pos})"
            elif pos == count + 1:
                label = f"Outermost (lane {sign * pos})"
            else:
                label = f"Lane {sign * pos}"
            self.position_combo.addItem(label, sign * pos)

    def get_spec(self) -> dict:
        """Build the lane spec from current form values."""
        width_start = self.width_start_spin.value()
        width_end = self.width_end_spin.value()
        lane = Lane(
            id=0,  # Assigned by Road.insert_lane_in_section
            lane_type=self.lane_type_combo.currentData(),
            road_mark_type=self.road_mark_combo.currentData(),
            width=width_start,
            width_end=width_end if width_end != width_start else None,
        )
        return {
            'new_lane_id': self.position_combo.currentData(),
            'lane': lane,
        }

    @classmethod
    def get_lane_spec(cls, section: LaneSection, road: Road, parent=None) -> Optional[dict]:
        """Show the dialog; returns {'new_lane_id', 'lane'} or None if cancelled."""
        dialog = cls(section, road, parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.get_spec()
        return None

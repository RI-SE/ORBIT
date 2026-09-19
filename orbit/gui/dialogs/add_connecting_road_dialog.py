"""
Dialog for adding a connecting road to a junction by hand.

Picks the two roads the new path joins; the geometry, lane counts and lane
connections are then built by the same code the junction analyzer uses, so a
hand-made connecting road is indistinguishable from a generated one. Fine
tuning (lane counts, tangent scale, contacts) happens afterwards in
ConnectingRoadDialog.
"""

from typing import List, Optional, Tuple

from PyQt6.QtWidgets import QComboBox, QLabel

from orbit_core.models import Junction, Project

from ..utils import entity_label
from .base_dialog import BaseDialog

#: Turn types offered, alongside letting the geometry decide.
TURN_TYPES = [
    ("(from geometry)", None),
    ("Straight", "straight"),
    ("Left", "left"),
    ("Right", "right"),
    ("U-turn", "uturn"),
]


class AddConnectingRoadDialog(BaseDialog):
    """Dialog for choosing the two roads a new connecting road joins."""

    def __init__(self, junction: Junction, project: Project, parent=None):
        super().__init__("Add Connecting Road", parent, min_width=460)

        self.junction = junction
        self.project = project
        self.setup_ui()

    def setup_ui(self):
        """Setup the dialog UI."""
        layout = self.add_form_group_with_info(
            "Path Through the Junction",
            "Traffic runs from the first road to the second. Create one "
            "connecting road per direction; a road may appear in several."
        )

        roads = self._connected_roads()
        self.from_combo = QComboBox()
        self.to_combo = QComboBox()
        for combo in (self.from_combo, self.to_combo):
            for road in roads:
                combo.addItem(entity_label(road.id, road.name, kind="Road"), road.id)
        if self.to_combo.count() > 1:
            self.to_combo.setCurrentIndex(1)

        self.from_lane_combo = QComboBox()
        self.to_lane_combo = QComboBox()
        for combo in (self.from_lane_combo, self.to_lane_combo):
            combo.setToolTip(
                "Lane the movement joins, at the end of the road that meets "
                "this junction. Driving lanes are listed first."
            )

        layout.addRow("From road:", self.from_combo)
        layout.addRow("From lane:", self.from_lane_combo)
        layout.addRow("To road:", self.to_combo)
        layout.addRow("To lane:", self.to_lane_combo)

        self.turn_combo = QComboBox()
        for label, value in TURN_TYPES:
            self.turn_combo.addItem(label, value)
        self.turn_combo.setToolTip(
            "Left as '(from geometry)' the turn type is classified from the "
            "angle between the two roads."
        )
        layout.addRow("Turn type:", self.turn_combo)

        self.warning_label = QLabel()
        self.warning_label.setWordWrap(True)
        self.warning_label.setStyleSheet("QLabel { color: #b07000; }")
        layout.addRow("", self.warning_label)

        self.from_combo.currentIndexChanged.connect(self._on_roads_changed)
        self.to_combo.currentIndexChanged.connect(self._on_roads_changed)
        self._on_roads_changed()

        self.create_button_box()

    def _on_roads_changed(self):
        """Refill the lane combos for the chosen roads, then re-check the pair."""
        self._fill_lane_combo(self.from_lane_combo, self.from_combo.currentData())
        self._fill_lane_combo(self.to_lane_combo, self.to_combo.currentData())
        self._update_warning()

    def _fill_lane_combo(self, combo: QComboBox, road_id):
        """List a road's lanes where it meets the junction, driving ones first.

        A median or a lane closed at the junction cannot carry a movement, so
        they are listed last and never preselected.
        """
        combo.clear()
        road = self.project.get_road(road_id) if road_id else None
        section = self._junction_section(road)
        if section is None:
            combo.addItem("(no lanes)", None)
            return
        at_start = self.project._junction_touches_road_start(self.junction, road)
        usable, other = [], []
        for lane in section.get_lanes_sorted():
            if lane.id == 0:
                continue
            width = lane.width if at_start else lane.get_width_at_end()
            label = (f"lane {lane.id} — {lane.lane_type.value}, "
                     f"{width:.2f} m")
            if lane.lane_type.value == "driving" and width > 0:
                usable.append((label, lane.id))
            else:
                other.append((f"{label} (not drivable here)", lane.id))
        for label, lane_id in usable + other:
            combo.addItem(label, lane_id)
        if not usable and not other:
            combo.addItem("(no lanes)", None)

    def _junction_section(self, road):
        """The lane section at the end of a road that meets this junction."""
        if road is None or not road.lane_sections:
            return None
        at_start = self.project._junction_touches_road_start(self.junction, road)
        return road.lane_sections[0] if at_start else road.lane_sections[-1]

    def _connected_roads(self) -> List:
        """Roads the junction connects, in the junction's own order."""
        roads = []
        for road_id in self.junction.connected_road_ids:
            road = self.project.get_road(road_id)
            if road is not None:
                roads.append(road)
        return roads

    def _update_warning(self):
        """Warn about choices that will not produce a usable path."""
        from_id, to_id = self.from_combo.currentData(), self.to_combo.currentData()
        if from_id and from_id == to_id:
            self.warning_label.setText(
                "Both ends are the same road — this makes a U-turn."
            )
            return
        existing = [
            cr_id for cr_id in self.junction.connecting_road_ids
            if self._joins(cr_id, from_id, to_id)
        ]
        if existing:
            self.warning_label.setText(
                f"A connecting road already joins these two: "
                f"{', '.join(existing)}. Another one is allowed, for a second "
                f"path such as a slip lane."
            )
        else:
            self.warning_label.setText("")

    def _joins(self, cr_id: str, from_id: str, to_id: str) -> bool:
        """Whether a connecting road already links this pair, either way round."""
        cr = self.project.get_road(cr_id)
        if cr is None:
            return False
        ends = {cr.predecessor_id, cr.successor_id}
        return ends == {from_id, to_id}

    def get_selection(self) -> Tuple[str, str, Optional[str], Optional[int], Optional[int]]:
        """The chosen (from road, to road, turn type, from lane, to lane)."""
        return (
            self.from_combo.currentData(),
            self.to_combo.currentData(),
            self.turn_combo.currentData(),
            self.from_lane_combo.currentData(),
            self.to_lane_combo.currentData(),
        )

    @classmethod
    def choose(
        cls, junction: Junction, project: Project, parent=None
    ) -> Optional[Tuple[str, str, Optional[str], Optional[int], Optional[int]]]:
        """Ask which roads to join. Returns None if cancelled."""
        from PyQt6.QtWidgets import QDialog

        dialog = cls(junction, project, parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.get_selection()
        return None

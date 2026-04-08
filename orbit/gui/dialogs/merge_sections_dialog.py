"""
Dialog for resolving lane attribute conflicts when merging lane sections.
"""

from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from orbit.models.lane import BoundaryMode, Lane, LaneType
from orbit.models.lane_section import LaneSection
from orbit.models.polyline import RoadMarkType
from orbit.utils.enum_formatting import format_enum_name

# Attributes checked for conflicts (width/links/materials/heights handled separately)
CONFLICT_ATTRS: List[str] = [
    'lane_type',
    'road_mark_type',
    'road_mark_color',
    'road_mark_weight',
    'road_mark_width',
    'speed_limit',
    'speed_limit_unit',
    'access_restrictions',
    'direction',
    'advisory',
    'level',
    'turn_directions',
    'boundary_mode',
]

ATTR_LABELS: Dict[str, str] = {
    'lane_type': 'Lane type',
    'road_mark_type': 'Road mark type',
    'road_mark_color': 'Road mark color',
    'road_mark_weight': 'Road mark weight',
    'road_mark_width': 'Road mark width',
    'speed_limit': 'Speed limit',
    'speed_limit_unit': 'Speed limit unit',
    'access_restrictions': 'Access restrictions',
    'direction': 'Direction',
    'advisory': 'Advisory',
    'level': 'Level',
    'turn_directions': 'Turn directions',
    'boundary_mode': 'Boundary mode',
}


def _format_value(value: Any) -> str:
    """Format an attribute value for display."""
    if value is None:
        return "(none)"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (LaneType, RoadMarkType, BoundaryMode)):
        return format_enum_name(value)
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) if value else "(empty)"
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def detect_section_conflicts(sections: List[LaneSection]) -> Dict[int, Dict[str, list]]:
    """
    Find attributes that differ across sections for each lane.

    Returns {lane_id: {attr: [first_value, last_value]}} for conflicting attributes only.
    """
    if len(sections) < 2:
        return {}

    first = sections[0]
    last = sections[-1]
    conflicts: Dict[int, Dict[str, list]] = {}

    for lane in first.lanes:
        lane_id = lane.id
        last_lane = last.get_lane(lane_id)
        if last_lane is None:
            continue

        lane_conflicts: Dict[str, list] = {}
        for attr in CONFLICT_ATTRS:
            first_val = getattr(lane, attr, None)
            last_val = getattr(last_lane, attr, None)
            if first_val != last_val:
                lane_conflicts[attr] = [first_val, last_val]

        if lane_conflicts:
            conflicts[lane_id] = lane_conflicts

    return conflicts


class MergeSectionsDialog(QDialog):
    """
    Dialog for resolving per-attribute conflicts when merging lane sections.

    Shows one group per lane with conflicting attributes, each attribute
    offering a radio-button choice between first and last section values.
    """

    def __init__(
        self,
        first_section: LaneSection,
        last_section: LaneSection,
        conflicts: Dict[int, Dict[str, list]],
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Merge Lane Sections — Resolve Conflicts")
        self.setMinimumWidth(480)

        self._first_section = first_section
        self._last_section = last_section
        self._conflicts = conflicts

        # {lane_id: {attr: QButtonGroup}}
        self._button_groups: Dict[int, Dict[str, QButtonGroup]] = {}

        self._setup_ui()

    def _setup_ui(self):
        outer = QVBoxLayout(self)

        intro = QLabel(
            "Lane attributes differ across the sections being merged.\n"
            "Choose which value to keep for each conflicting attribute."
        )
        intro.setWordWrap(True)
        outer.addWidget(intro)

        # Scroll area for the lane groups
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)

        for lane_id in sorted(self._conflicts.keys(), reverse=True):
            lane_conflicts = self._conflicts[lane_id]
            first_lane = self._first_section.get_lane(lane_id)
            label = _lane_label(lane_id, first_lane)

            group_box = QGroupBox(label)
            group_layout = QVBoxLayout(group_box)

            # Column header
            header = QHBoxLayout()
            header.addWidget(QLabel("<b>Attribute</b>"), stretch=3)
            header.addWidget(QLabel("<b>First section</b>"), stretch=2)
            header.addWidget(QLabel("<b>Last section</b>"), stretch=2)
            group_layout.addLayout(header)

            self._button_groups[lane_id] = {}

            for attr, (first_val, last_val) in lane_conflicts.items():
                row = QHBoxLayout()

                attr_label = QLabel(ATTR_LABELS.get(attr, attr))
                attr_label.setMinimumWidth(120)
                row.addWidget(attr_label, stretch=3)

                btn_group = QButtonGroup(self)
                first_radio = QRadioButton(_format_value(first_val))
                first_radio.setChecked(True)
                last_radio = QRadioButton(_format_value(last_val))

                btn_group.addButton(first_radio, 0)
                btn_group.addButton(last_radio, 1)

                row.addWidget(first_radio, stretch=2)
                row.addWidget(last_radio, stretch=2)
                group_layout.addLayout(row)

                self._button_groups[lane_id][attr] = (btn_group, [first_val, last_val])

            content_layout.addWidget(group_box)

        # Convenience buttons
        quick_row = QHBoxLayout()
        use_first_btn = _flat_button("Use first section for all")
        use_first_btn.clicked.connect(lambda: self._select_all(0))
        use_last_btn = _flat_button("Use last section for all")
        use_last_btn.clicked.connect(lambda: self._select_all(1))
        quick_row.addWidget(use_first_btn)
        quick_row.addWidget(use_last_btn)
        quick_row.addStretch()
        content_layout.addLayout(quick_row)
        content_layout.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            Qt.Orientation.Horizontal,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _select_all(self, index: int):
        """Set all radio groups to first (0) or last (1) section."""
        for lane_groups in self._button_groups.values():
            for btn_group, _ in lane_groups.values():
                btn = btn_group.button(index)
                if btn:
                    btn.setChecked(True)

    def get_resolved_attrs(self) -> Dict[int, Dict[str, Any]]:
        """Return {lane_id: {attr: chosen_value}} for all conflicting attributes."""
        result: Dict[int, Dict[str, Any]] = {}
        for lane_id, lane_groups in self._button_groups.items():
            lane_result: Dict[str, Any] = {}
            for attr, (btn_group, values) in lane_groups.items():
                chosen_index = btn_group.checkedId()
                lane_result[attr] = values[chosen_index]
            result[lane_id] = lane_result
        return result


def _lane_label(lane_id: int, lane: Optional[Lane]) -> str:
    side = "center" if lane_id == 0 else ("left" if lane_id > 0 else "right")
    type_str = ""
    if lane and lane.lane_type:
        type_str = f" — {format_enum_name(lane.lane_type)}"
    return f"Lane {lane_id} ({side}{type_str})"


def _flat_button(text: str):
    from PyQt6.QtWidgets import QPushButton
    btn = QPushButton(text)
    btn.setFlat(True)
    btn.setStyleSheet("color: #0066cc; text-decoration: underline; border: none;")
    return btn

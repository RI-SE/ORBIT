"""
Road Lane Links dialog for ORBIT.

Allows editing of per-lane predecessor/successor IDs for direct road-to-road connections.
"""

from typing import List, Optional, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from orbit.models.lane import Lane
from orbit.models.road import Road
from orbit.utils.logging_config import get_logger

logger = get_logger(__name__)

# Column indices
COL_SECTION = 0
COL_LANE_ID = 1
COL_TYPE = 2
COL_PREDECESSOR = 3
COL_SUCCESSOR = 4


class RoadLaneLinksDialog(QDialog):
    """
    Dialog for editing per-lane predecessor/successor IDs on a regular road.

    Used for road-to-road lane continuity links (not junction connections).
    For junction connections, use the LaneConnectionDialog via the Elements tree.
    """

    def __init__(self, road: Road, parent=None):
        super().__init__(parent)
        self.road = road
        self.setWindowTitle(f"Lane Links — {road.name}")
        self.setMinimumWidth(520)

        self._lane_rows: List[Tuple[int, Lane, QSpinBox, QSpinBox]] = []  # (section_idx, lane, pred_spin, succ_spin)

        self._setup_ui()
        self._load()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        note = QLabel(
            "Set predecessor/successor lane IDs for direct road-to-road continuity.\n"
            "Use 0 (shown as '—') for no link. These are used when a road links directly\n"
            "to another road (not through a junction). For junction connections, use\n"
            "Elements tree → Edit Lane Connections."
        )
        note.setWordWrap(True)
        note.setStyleSheet("QLabel { color: #555; font-style: italic; }")
        layout.addWidget(note)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Section", "Lane ID", "Type", "Predecessor", "Successor"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(COL_TYPE, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _load(self):
        """Populate table from road lane sections."""
        rows_data = []
        for section_idx, section in enumerate(self.road.lane_sections):
            for lane in sorted(section.lanes, key=lambda ln: ln.id):
                if lane.id == 0:
                    continue  # Skip center lane
                rows_data.append((section_idx, lane))

        self.table.setRowCount(len(rows_data))
        self._lane_rows.clear()

        for row, (section_idx, lane) in enumerate(rows_data):
            section_item = QTableWidgetItem(str(section_idx + 1))
            section_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, COL_SECTION, section_item)

            lane_id_item = QTableWidgetItem(str(lane.id))
            lane_id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, COL_LANE_ID, lane_id_item)

            lane_type_str = lane.lane_type.value if hasattr(lane.lane_type, 'value') else str(lane.lane_type)
            type_item = QTableWidgetItem(lane_type_str)
            self.table.setItem(row, COL_TYPE, type_item)

            pred_spin = self._make_spin(lane.predecessor_id)
            self.table.setCellWidget(row, COL_PREDECESSOR, pred_spin)

            succ_spin = self._make_spin(lane.successor_id)
            self.table.setCellWidget(row, COL_SUCCESSOR, succ_spin)

            self._lane_rows.append((section_idx, lane, pred_spin, succ_spin))

        self.table.resizeRowsToContents()

    def _make_spin(self, value: Optional[int]) -> QSpinBox:
        """Create a spin box for lane ID entry. 0 means no link."""
        spin = QSpinBox()
        spin.setRange(-99, 99)
        spin.setSpecialValueText("0 (none)")
        spin.setValue(value if value is not None else 0)
        spin.setToolTip("Lane ID to link to (0 = no link)")
        return spin

    def accept(self):
        """Save spin box values back to lane objects."""
        for _section_idx, lane, pred_spin, succ_spin in self._lane_rows:
            pred_val = pred_spin.value()
            lane.predecessor_id = pred_val if pred_val != 0 else None

            succ_val = succ_spin.value()
            lane.successor_id = succ_val if succ_val != 0 else None

        super().accept()

    @classmethod
    def edit_lane_links(cls, road: Road, parent=None) -> bool:
        """
        Open the dialog and return True if the user accepted changes.

        Args:
            road: Road whose lanes to edit
            parent: Parent widget

        Returns:
            True if user clicked OK
        """
        if not road.lane_sections:
            logger.debug("Road %s has no lane sections", road.name)
            return False

        dialog = cls(road, parent)
        return dialog.exec() == QDialog.DialogCode.Accepted

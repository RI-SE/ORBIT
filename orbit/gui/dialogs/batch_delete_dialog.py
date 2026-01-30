"""
Batch delete confirmation dialog for area selection.

Shows a checkable tree of items selected for deletion, allowing
the user to deselect individual items before confirming.
"""

from typing import Dict, List

from PyQt6.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QDialogButtonBox, QLabel
)
from PyQt6.QtCore import Qt

from .base_dialog import BaseDialog


# Display names for item categories
_CATEGORY_LABELS = {
    "road_ids": "Roads",
    "junction_ids": "Junctions",
    "signal_ids": "Signals",
    "object_ids": "Objects",
    "parking_ids": "Parking Spaces",
}


class BatchDeleteDialog(BaseDialog):
    """Confirmation dialog for batch deletion of selected items.

    Shows a tree with checkable items grouped by category. Each category
    header is tri-state checkable. Cascade children (e.g. polylines under
    roads) are shown as indented non-checkable items for information only.

    Args:
        items_info: Dict mapping category keys to lists of item dicts.
            Each item dict has: id, name, details (str), cascade (optional list of str).
        parent: Parent widget.
    """

    def __init__(self, items_info: Dict[str, List[dict]], parent=None):
        total = sum(len(items) for items in items_info.values())
        super().__init__(f"Delete {total} Items", parent, min_width=420, min_height=300)
        self._items_info = items_info
        self._setup_ui()

    def _setup_ui(self):
        layout = self.get_main_layout()

        # Summary label
        total = sum(len(items) for items in self._items_info.values())
        label = QLabel(f"The following {total} item(s) were selected. "
                       "Uncheck items you want to keep.")
        label.setWordWrap(True)
        layout.addWidget(label)

        # Tree widget
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Item", "Details"])
        self._tree.setColumnWidth(0, 250)
        self._tree.setRootIsDecorated(True)
        layout.addWidget(self._tree)

        # Populate tree
        for category_key, items in self._items_info.items():
            if not items:
                continue

            cat_label = _CATEGORY_LABELS.get(category_key, category_key)
            cat_node = QTreeWidgetItem(self._tree)
            cat_node.setText(0, f"{cat_label} ({len(items)})")
            cat_node.setFlags(
                cat_node.flags()
                | Qt.ItemFlag.ItemIsAutoTristate
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            cat_node.setCheckState(0, Qt.CheckState.Checked)
            cat_node.setExpanded(True)
            cat_node.setData(0, Qt.ItemDataRole.UserRole, category_key)

            for item in items:
                child = QTreeWidgetItem(cat_node)
                child.setText(0, item.get("name", item["id"][:8]))
                child.setText(1, item.get("details", ""))
                child.setFlags(
                    child.flags() | Qt.ItemFlag.ItemIsUserCheckable
                )
                child.setCheckState(0, Qt.CheckState.Checked)
                child.setData(0, Qt.ItemDataRole.UserRole, item["id"])

                # Cascade children (informational, not checkable)
                for cascade_text in item.get("cascade", []):
                    info_child = QTreeWidgetItem(child)
                    info_child.setText(0, cascade_text)
                    info_child.setFlags(
                        info_child.flags() & ~Qt.ItemFlag.ItemIsUserCheckable
                    )
                    info_child.setDisabled(True)

        # Buttons
        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = self._button_box.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setText("Delete Selected")
        self._button_box.accepted.connect(self.accept)
        self._button_box.rejected.connect(self.reject)
        layout.addWidget(self._button_box)

    def get_selected_ids(self) -> Dict[str, List[str]]:
        """Return checked item IDs grouped by category key.

        Returns:
            Dict mapping category keys (e.g. "road_ids") to lists of
            checked item ID strings.
        """
        result: Dict[str, List[str]] = {}
        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            cat_node = root.child(i)
            category_key = cat_node.data(0, Qt.ItemDataRole.UserRole)
            ids = []
            for j in range(cat_node.childCount()):
                child = cat_node.child(j)
                if child.checkState(0) == Qt.CheckState.Checked:
                    item_id = child.data(0, Qt.ItemDataRole.UserRole)
                    if item_id:
                        ids.append(item_id)
            if ids:
                result[category_key] = ids
        return result

    # BaseDialog requires these but we handle setup differently
    def setup_ui(self):
        pass

    def load_properties(self):
        pass

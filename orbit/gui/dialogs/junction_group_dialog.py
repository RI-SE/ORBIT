"""
Junction Groups dialog for ORBIT.

Allows editing of junction groups (roundabouts, complex junctions).
"""

from typing import Optional, List

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QComboBox, QPushButton,
    QListWidget, QLabel, QMessageBox,
    QListWidgetItem, QGroupBox, QDialogButtonBox
)
from PyQt6.QtCore import Qt

from orbit.models import Project
from orbit.models.junction import JunctionGroup
from .base_dialog import InfoIconLabel


class JunctionGroupDialog(QDialog):
    """Dialog for managing junction groups."""

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)

        self.project = project
        self.setup_ui()
        self.load_groups()

    def setup_ui(self):
        """Setup the dialog UI."""
        self.setWindowTitle("Junction Groups")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)

        layout = QVBoxLayout(self)

        # Info label with icon
        info_widget = InfoIconLabel(
            "Junction Groups",
            "Junction groups combine multiple junctions into logical units "
            "(e.g., roundabouts, highway interchanges). This is an OpenDRIVE 1.8 feature."
        )
        layout.addWidget(info_widget)

        # Main horizontal layout: group list | group details
        main_layout = QHBoxLayout()

        # Left side: Group list
        left_group = QGroupBox("Groups")
        left_layout = QVBoxLayout()

        self.groups_list = QListWidget()
        self.groups_list.currentItemChanged.connect(self.on_group_selected)
        left_layout.addWidget(self.groups_list)

        # Group list buttons
        list_btn_layout = QHBoxLayout()
        self.add_group_btn = QPushButton("+ Add Group")
        self.add_group_btn.clicked.connect(self.add_group)
        list_btn_layout.addWidget(self.add_group_btn)

        self.remove_group_btn = QPushButton("- Remove Group")
        self.remove_group_btn.clicked.connect(self.remove_group)
        self.remove_group_btn.setEnabled(False)
        list_btn_layout.addWidget(self.remove_group_btn)

        left_layout.addLayout(list_btn_layout)
        left_group.setLayout(left_layout)
        main_layout.addWidget(left_group, 1)

        # Right side: Group details
        right_group = QGroupBox("Group Details")
        right_layout = QFormLayout()

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Enter group name")
        self.name_edit.textChanged.connect(self.on_name_changed)
        right_layout.addRow("Name:", self.name_edit)

        self.type_combo = QComboBox()
        self.type_combo.addItems(["roundabout", "complexJunction", "highwayInterchange", "unknown"])
        self.type_combo.setToolTip("Type of junction group")
        self.type_combo.currentTextChanged.connect(self.on_type_changed)
        right_layout.addRow("Type:", self.type_combo)

        # Junction selection
        junctions_label = QLabel("<b>Junctions in Group:</b>")
        right_layout.addRow(junctions_label)

        # Available junctions
        self.available_junctions_list = QListWidget()
        self.available_junctions_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.available_junctions_list.setMaximumHeight(120)
        right_layout.addRow("Available:", self.available_junctions_list)

        # Add/Remove buttons
        junction_btn_layout = QHBoxLayout()
        self.add_junction_btn = QPushButton("Add Selected ↓")
        self.add_junction_btn.clicked.connect(self.add_junctions_to_group)
        junction_btn_layout.addWidget(self.add_junction_btn)

        self.remove_junction_btn = QPushButton("↑ Remove Selected")
        self.remove_junction_btn.clicked.connect(self.remove_junctions_from_group)
        junction_btn_layout.addWidget(self.remove_junction_btn)
        right_layout.addRow("", junction_btn_layout)

        # Group junctions
        self.group_junctions_list = QListWidget()
        self.group_junctions_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.group_junctions_list.setMaximumHeight(120)
        right_layout.addRow("In Group:", self.group_junctions_list)

        right_group.setLayout(right_layout)
        main_layout.addWidget(right_group, 2)

        layout.addLayout(main_layout)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Initial state
        self.set_details_enabled(False)

    def set_details_enabled(self, enabled: bool):
        """Enable/disable the details section."""
        self.name_edit.setEnabled(enabled)
        self.type_combo.setEnabled(enabled)
        self.available_junctions_list.setEnabled(enabled)
        self.group_junctions_list.setEnabled(enabled)
        self.add_junction_btn.setEnabled(enabled)
        self.remove_junction_btn.setEnabled(enabled)
        self.remove_group_btn.setEnabled(enabled)

    def load_groups(self):
        """Load junction groups from project."""
        self.groups_list.clear()
        for group in self.project.junction_groups:
            item = QListWidgetItem(f"{group.name} ({group.group_type})")
            item.setData(Qt.ItemDataRole.UserRole, group.id)
            self.groups_list.addItem(item)

    def get_group_by_id(self, group_id: str) -> Optional[JunctionGroup]:
        """Get a junction group by ID."""
        for group in self.project.junction_groups:
            if group.id == group_id:
                return group
        return None

    def on_group_selected(self, current: QListWidgetItem, previous: QListWidgetItem):
        """Handle group selection change."""
        # Save previous group
        if previous:
            self.save_current_group(previous)

        if current is None:
            self.set_details_enabled(False)
            self.name_edit.clear()
            self.type_combo.setCurrentIndex(3)  # unknown
            self.available_junctions_list.clear()
            self.group_junctions_list.clear()
            return

        self.set_details_enabled(True)

        # Load current group
        group_id = current.data(Qt.ItemDataRole.UserRole)
        group = self.get_group_by_id(group_id)
        if not group:
            return

        self.name_edit.setText(group.name or "")
        index = self.type_combo.findText(group.group_type)
        if index >= 0:
            self.type_combo.setCurrentIndex(index)

        # Load junctions
        self.available_junctions_list.clear()
        self.group_junctions_list.clear()

        for junction in self.project.junctions:
            display_text = f"{junction.name} ({junction.id[:8]}...)"
            if junction.id in group.junction_ids:
                item = QListWidgetItem(display_text)
                item.setData(Qt.ItemDataRole.UserRole, junction.id)
                self.group_junctions_list.addItem(item)
            else:
                item = QListWidgetItem(display_text)
                item.setData(Qt.ItemDataRole.UserRole, junction.id)
                self.available_junctions_list.addItem(item)

    def save_current_group(self, item: QListWidgetItem):
        """Save the current group's data."""
        group_id = item.data(Qt.ItemDataRole.UserRole)
        group = self.get_group_by_id(group_id)
        if not group:
            return

        group.name = self.name_edit.text().strip() or "Unnamed Group"
        group.group_type = self.type_combo.currentText()

        # Update junction IDs
        group.junction_ids.clear()
        for i in range(self.group_junctions_list.count()):
            junction_item = self.group_junctions_list.item(i)
            group.junction_ids.append(junction_item.data(Qt.ItemDataRole.UserRole))

        # Update list item text
        item.setText(f"{group.name} ({group.group_type})")

    def on_name_changed(self, text: str):
        """Update list item when name changes."""
        current = self.groups_list.currentItem()
        if current:
            group_type = self.type_combo.currentText()
            current.setText(f"{text or 'Unnamed Group'} ({group_type})")

    def on_type_changed(self, text: str):
        """Update list item when type changes."""
        current = self.groups_list.currentItem()
        if current:
            name = self.name_edit.text() or "Unnamed Group"
            current.setText(f"{name} ({text})")

    def add_group(self):
        """Add a new junction group."""
        new_group = JunctionGroup(
            id=self.project.next_id('junction_group'),
            name="New Group",
            group_type="unknown",
            junction_ids=[]
        )
        self.project.junction_groups.append(new_group)

        item = QListWidgetItem(f"{new_group.name} ({new_group.group_type})")
        item.setData(Qt.ItemDataRole.UserRole, new_group.id)
        self.groups_list.addItem(item)
        self.groups_list.setCurrentItem(item)

    def remove_group(self):
        """Remove the selected junction group."""
        current = self.groups_list.currentItem()
        if not current:
            return

        group_id = current.data(Qt.ItemDataRole.UserRole)

        # Remove from project
        self.project.junction_groups = [
            g for g in self.project.junction_groups if g.id != group_id
        ]

        # Remove from list
        row = self.groups_list.row(current)
        self.groups_list.takeItem(row)

    def add_junctions_to_group(self):
        """Add selected junctions to the current group."""
        selected_items = self.available_junctions_list.selectedItems()
        for item in selected_items:
            junction_id = item.data(Qt.ItemDataRole.UserRole)
            # Remove from available
            row = self.available_junctions_list.row(item)
            self.available_junctions_list.takeItem(row)
            # Add to group
            new_item = QListWidgetItem(item.text())
            new_item.setData(Qt.ItemDataRole.UserRole, junction_id)
            self.group_junctions_list.addItem(new_item)

    def remove_junctions_from_group(self):
        """Remove selected junctions from the current group."""
        selected_items = self.group_junctions_list.selectedItems()
        for item in selected_items:
            junction_id = item.data(Qt.ItemDataRole.UserRole)
            # Remove from group
            row = self.group_junctions_list.row(item)
            self.group_junctions_list.takeItem(row)
            # Add back to available
            new_item = QListWidgetItem(item.text())
            new_item.setData(Qt.ItemDataRole.UserRole, junction_id)
            self.available_junctions_list.addItem(new_item)

    def accept(self):
        """Save all changes and accept dialog."""
        # Save current group
        current = self.groups_list.currentItem()
        if current:
            self.save_current_group(current)

        super().accept()

    @classmethod
    def edit_groups(cls, project: Project, parent=None) -> bool:
        """
        Show dialog to edit junction groups.

        Args:
            project: Project containing the junction groups
            parent: Parent widget

        Returns:
            True if accepted, False if cancelled
        """
        dialog = cls(project, parent)
        return dialog.exec() == QDialog.DialogCode.Accepted

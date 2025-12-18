"""
Dialog for selecting parking type when placing a new parking space.
"""

from typing import Optional, Tuple

from PyQt6.QtWidgets import QComboBox, QLabel
from PyQt6.QtCore import Qt
from orbit.models.parking import ParkingType, ParkingAccess
from .base_dialog import BaseDialog


class ParkingSelectionDialog(BaseDialog):
    """
    Dialog for selecting the type and access of a parking space before placement.

    Provides dropdown selection for:
    - Parking type (surface, underground, multi-storey, etc.)
    - Access type (standard, handicapped, private, etc.)
    """

    def __init__(self, parent=None):
        super().__init__("Select Parking Type", parent, min_width=350)
        self.selected_type: Optional[ParkingType] = None
        self.selected_access: Optional[ParkingAccess] = None

        self.setup_ui()
        self.load_properties()

    def setup_ui(self):
        """Create the dialog UI."""
        # Instructions
        instructions = QLabel(
            "Select the parking type and access restrictions.\n"
            "Click on the map to place the parking space."
        )
        instructions.setWordWrap(True)
        self.get_main_layout().addWidget(instructions)

        # Parking Type
        type_layout = self.add_form_group("Parking Type")

        self.type_combo = QComboBox()
        for ptype in ParkingType:
            display_name = ptype.value.replace('_', ' ').title()
            self.type_combo.addItem(display_name, ptype)
        type_layout.addRow("Type:", self.type_combo)

        # Type description
        self.type_desc = QLabel()
        self.type_desc.setStyleSheet("color: #666; font-size: 10px;")
        self.type_desc.setWordWrap(True)
        type_layout.addRow("", self.type_desc)
        self.type_combo.currentIndexChanged.connect(self._update_type_description)

        # Access Type
        access_layout = self.add_form_group("Access Restrictions")

        self.access_combo = QComboBox()
        for access in ParkingAccess:
            display_name = access.value.replace('_', ' ').title()
            self.access_combo.addItem(display_name, access)
        access_layout.addRow("Access:", self.access_combo)

        # Access description
        self.access_desc = QLabel()
        self.access_desc.setStyleSheet("color: #666; font-size: 10px;")
        self.access_desc.setWordWrap(True)
        access_layout.addRow("", self.access_desc)
        self.access_combo.currentIndexChanged.connect(self._update_access_description)

        # Standard buttons
        self.create_button_box()

        # Initial descriptions
        self._update_type_description()
        self._update_access_description()

    def load_properties(self):
        """Set default values."""
        # Default to surface parking with standard access
        type_idx = self.type_combo.findData(ParkingType.SURFACE)
        if type_idx >= 0:
            self.type_combo.setCurrentIndex(type_idx)

        access_idx = self.access_combo.findData(ParkingAccess.STANDARD)
        if access_idx >= 0:
            self.access_combo.setCurrentIndex(access_idx)

    def _update_type_description(self):
        """Update description text based on selected type."""
        ptype = self.type_combo.currentData()
        descriptions = {
            ParkingType.SURFACE: "Open-air parking lot at ground level",
            ParkingType.UNDERGROUND: "Parking garage below ground level",
            ParkingType.MULTI_STOREY: "Multi-level parking structure",
            ParkingType.ROOFTOP: "Parking on top of a building",
            ParkingType.STREET: "On-street parking spaces",
            ParkingType.CARPORTS: "Covered parking with open sides",
        }
        self.type_desc.setText(descriptions.get(ptype, ""))

    def _update_access_description(self):
        """Update description text based on selected access type."""
        access = self.access_combo.currentData()
        descriptions = {
            ParkingAccess.STANDARD: "Open to general public",
            ParkingAccess.HANDICAPPED: "Reserved for persons with disabilities",
            ParkingAccess.DISABLED: "Reserved for persons with disabilities",
            ParkingAccess.PRIVATE: "Private property, restricted access",
            ParkingAccess.RESERVED: "Reserved for specific users",
            ParkingAccess.PERMIT: "Permit holders only",
            ParkingAccess.COMPANY: "Company/employee parking",
            ParkingAccess.CUSTOMERS: "Customer parking only",
            ParkingAccess.RESIDENTS: "Resident parking only",
            ParkingAccess.WOMEN: "Women-only parking area",
        }
        self.access_desc.setText(descriptions.get(access, ""))

    def accept(self):
        """Save selections and close dialog."""
        self.selected_type = self.type_combo.currentData()
        self.selected_access = self.access_combo.currentData()
        super().accept()

    def get_selection(self) -> Tuple[Optional[ParkingType], Optional[ParkingAccess]]:
        """
        Get the selected parking type and access.

        Returns:
            Tuple of (ParkingType, ParkingAccess) or (None, None) if cancelled
        """
        return (self.selected_type, self.selected_access)

"""
Dialog for selecting land use type when placing a new land use area polygon.
"""

from typing import Optional

from PyQt6.QtWidgets import QComboBox, QLabel

from orbit.models.object import ObjectType

from .base_dialog import BaseDialog

LANDUSE_TYPES = [
    ObjectType.LANDUSE_FOREST,
    ObjectType.LANDUSE_FARMLAND,
    ObjectType.LANDUSE_MEADOW,
    ObjectType.LANDUSE_SCRUB,
    ObjectType.NATURAL_WATER,
    ObjectType.NATURAL_WETLAND,
]

LANDUSE_DESCRIPTIONS = {
    ObjectType.LANDUSE_FOREST: "Forested area with dense tree cover",
    ObjectType.LANDUSE_FARMLAND: "Agricultural field or cultivated land",
    ObjectType.LANDUSE_MEADOW: "Open grassy area or meadow",
    ObjectType.LANDUSE_SCRUB: "Scrubland with low shrubs and bushes",
    ObjectType.NATURAL_WATER: "River, lake, pond or other water body",
    ObjectType.NATURAL_WETLAND: "Wetland, marsh or swamp area",
}

LANDUSE_DISPLAY_NAMES = {
    ObjectType.LANDUSE_FOREST: "Forest",
    ObjectType.LANDUSE_FARMLAND: "Farmland",
    ObjectType.LANDUSE_MEADOW: "Meadow / Grass",
    ObjectType.LANDUSE_SCRUB: "Scrub / Heath",
    ObjectType.NATURAL_WATER: "Water",
    ObjectType.NATURAL_WETLAND: "Wetland",
}


class LandUseSelectionDialog(BaseDialog):
    """Dialog for selecting land use type before polygon drawing."""

    def __init__(self, parent=None, current_type: Optional[ObjectType] = None):
        super().__init__("Select Land Use Type", parent, min_width=360)
        self.selected_type: Optional[ObjectType] = None
        self._current_type = current_type
        self.setup_ui()
        self.load_properties()

    def setup_ui(self):
        """Create the dialog UI."""
        type_layout = self.add_form_group("Land Use Type")

        self.type_combo = QComboBox()
        for ltype in LANDUSE_TYPES:
            display_name = LANDUSE_DISPLAY_NAMES.get(ltype, ltype.value.replace('_', ' ').title())
            self.type_combo.addItem(display_name, ltype)
        type_layout.addRow("Type:", self.type_combo)

        self.desc_label = QLabel()
        self.desc_label.setStyleSheet("color: #666; font-size: 10px;")
        self.desc_label.setWordWrap(True)
        type_layout.addRow("", self.desc_label)
        self.type_combo.currentIndexChanged.connect(self._update_description)

        hint = QLabel("Click to place polygon vertices.\nDouble-click or press Enter to finish. Esc to cancel.")
        hint.setStyleSheet("color: #555; font-size: 10px; margin-top: 4px;")
        hint.setWordWrap(True)
        type_layout.addRow(hint)

        self.create_button_box()
        self._update_description()

    def load_properties(self):
        """Pre-select current type if provided."""
        if self._current_type is not None:
            idx = self.type_combo.findData(self._current_type)
            if idx >= 0:
                self.type_combo.setCurrentIndex(idx)

    def _update_description(self):
        ltype = self.type_combo.currentData()
        self.desc_label.setText(LANDUSE_DESCRIPTIONS.get(ltype, ""))

    def accept(self):
        self.selected_type = self.type_combo.currentData()
        super().accept()

    def get_selection(self) -> Optional[ObjectType]:
        """Return the selected ObjectType."""
        return self.selected_type

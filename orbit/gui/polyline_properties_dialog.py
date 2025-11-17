"""
Polyline properties dialog for ORBIT.

Allows editing of polyline line type and road mark type.
"""

from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout,
    QComboBox, QLabel, QGroupBox, QPushButton, QTextEdit, QVBoxLayout
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from models import Polyline, LineType, RoadMarkType
from gui.base_dialog import BaseDialog
from gui.message_helpers import show_info


class PolylinePropertiesDialog(BaseDialog):
    """Dialog for editing polyline properties."""

    def __init__(self, polyline: Polyline, parent=None):
        super().__init__("Polyline Properties", parent, min_width=400)

        self.polyline = polyline
        self.setup_ui()
        self.load_properties()

    def setup_ui(self):
        """Setup the dialog UI."""
        # Info section
        info_layout = self.add_form_group("Line Properties")

        # Line type dropdown
        self.line_type_combo = QComboBox()
        for line_type in LineType:
            display_name = "Road Reference Line" if line_type == LineType.CENTERLINE else "Lane Boundary"
            self.line_type_combo.addItem(display_name, line_type)
        self.line_type_combo.currentIndexChanged.connect(self.on_line_type_changed)
        info_layout.addRow("Line Type:", self.line_type_combo)

        # Road mark type dropdown
        self.road_mark_type_combo = QComboBox()
        for mark_type in RoadMarkType:
            display_name = mark_type.value.title()
            self.road_mark_type_combo.addItem(display_name, mark_type)
        info_layout.addRow("Road Mark Type:", self.road_mark_type_combo)

        # Reverse direction button (for centerlines only)
        reverse_layout = QHBoxLayout()
        self.reverse_button = QPushButton("⟲ Reverse Direction")
        self.reverse_button.setToolTip(
            "Reverse the order of points in this polyline.\n"
            "This changes the positive direction (shown by arrows).\n"
            "Point positions remain unchanged."
        )
        self.reverse_button.clicked.connect(self.reverse_direction)
        reverse_layout.addWidget(self.reverse_button)
        reverse_layout.addStretch()
        info_layout.addRow("Direction:", reverse_layout)

        # Description label
        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet("QLabel { color: gray; font-style: italic; }")
        info_layout.addRow("", self.description_label)

        # Points coordinates section
        points_group = QGroupBox("Point Coordinates (pixels)")
        points_layout = QVBoxLayout()

        # Read-only text area for coordinates
        self.points_text = QTextEdit()
        self.points_text.setReadOnly(True)
        self.points_text.setMaximumHeight(200)
        font = QFont("Courier")
        font.setPointSize(9)
        self.points_text.setFont(font)
        points_layout.addWidget(self.points_text)

        points_group.setLayout(points_layout)
        self.get_main_layout().addWidget(points_group)

        # Create standard OK/Cancel buttons
        self.create_button_box()

        self.update_description()

    def load_properties(self):
        """Load polyline properties into the form."""
        # Set line type
        for i in range(self.line_type_combo.count()):
            if self.line_type_combo.itemData(i) == self.polyline.line_type:
                self.line_type_combo.setCurrentIndex(i)
                break

        # Set road mark type
        for i in range(self.road_mark_type_combo.count()):
            if self.road_mark_type_combo.itemData(i) == self.polyline.road_mark_type:
                self.road_mark_type_combo.setCurrentIndex(i)
                break

        # Load points coordinates
        self.load_points_text()

    def load_points_text(self):
        """Load points coordinates into the text display."""
        if not self.polyline.points:
            self.points_text.setPlainText("No points")
            return

        # Check if we have s-offsets or elevations
        has_s_offsets = self.polyline.s_offsets and len(self.polyline.s_offsets) == len(self.polyline.points)
        has_elevations = self.polyline.elevations and len(self.polyline.elevations) == len(self.polyline.points)

        # Format points as a table
        lines = []

        # Header
        if has_s_offsets and has_elevations:
            lines.append("  #      X         Y      S-Offset  Elevation")
            lines.append("-" * 55)
        elif has_s_offsets:
            lines.append("  #      X         Y      S-Offset")
            lines.append("-" * 42)
        elif has_elevations:
            lines.append("  #      X         Y      Elevation")
            lines.append("-" * 42)
        else:
            lines.append("  #      X         Y")
            lines.append("-" * 30)

        # Data rows
        for i, (x, y) in enumerate(self.polyline.points):
            line = f"{i+1:3d}   {x:8.2f}  {y:8.2f}"

            if has_s_offsets:
                s = self.polyline.s_offsets[i]
                line += f"  {s:8.2f}m"

            if has_elevations:
                elev = self.polyline.elevations[i]
                line += f"  {elev:8.2f}m"

            lines.append(line)

        lines.append("-" * (55 if (has_s_offsets and has_elevations) else 42 if (has_s_offsets or has_elevations) else 30))
        lines.append(f"Total: {len(self.polyline.points)} points")

        if has_elevations:
            lines.append(f"Elevation range: {min(self.polyline.elevations):.2f}m to {max(self.polyline.elevations):.2f}m")

        self.points_text.setPlainText("\n".join(lines))

    def on_line_type_changed(self):
        """Handle line type change."""
        self.update_description()

    def update_description(self):
        """Update the description based on selections."""
        line_type = self.line_type_combo.currentData()

        if line_type == LineType.CENTERLINE:
            self.description_label.setText(
                "The road reference line serves as the reference line in OpenDRIVE. "
                "Each road must have exactly one road reference line. "
                "The direction (shown by arrows) determines which side is left/right."
            )
            # Show reverse button for centerlines
            self.reverse_button.setVisible(True)
        else:
            self.description_label.setText(
                "Lane boundaries define the visual markings (solid, broken, etc.) "
                "that delineate lanes on the road."
            )
            # Hide reverse button for lane boundaries
            self.reverse_button.setVisible(False)

    def reverse_direction(self):
        """Reverse the direction of the polyline."""
        self.polyline.reverse()

        # Update the dialog to show it was reversed
        show_info(self, "The polyline direction has been reversed.\n"
            "The arrows will now point in the opposite direction.", "Direction Reversed")

    def accept(self):
        """Save changes and accept dialog."""
        # Update polyline properties
        self.polyline.line_type = self.line_type_combo.currentData()
        self.polyline.road_mark_type = self.road_mark_type_combo.currentData()

        # Update color based on line type
        if self.polyline.line_type == LineType.CENTERLINE:
            self.polyline.color = (255, 165, 0)  # Orange for road reference line
        else:
            self.polyline.color = (0, 255, 255)  # Cyan for lane boundaries

        super().accept()

    @classmethod
    def edit_polyline(cls, polyline: Polyline, parent=None) -> bool:
        """
        Show dialog to edit a polyline's properties.

        Args:
            polyline: Polyline to edit
            parent: Parent widget

        Returns:
            True if properties were modified, False if cancelled
        """
        return cls.show_and_accept(polyline, parent=parent)

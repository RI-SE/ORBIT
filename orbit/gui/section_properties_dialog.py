"""
Section properties dialog for ORBIT.

Allows editing of lane section properties.
"""

from typing import Optional, List, Tuple
import math

from PyQt6.QtWidgets import (
    QFormLayout, QPushButton, QLabel, QComboBox, QGroupBox
)
from PyQt6.QtCore import Qt

from models import LaneSection
from export import CoordinateTransformer
from gui.base_dialog import BaseDialog


class SectionPropertiesDialog(BaseDialog):
    """Dialog for editing lane section properties."""

    def __init__(self, section: LaneSection, road_id: str, centerline_length_pixels: float,
                 centerline_points: Optional[List[Tuple[float, float]]] = None,
                 transformer: Optional[CoordinateTransformer] = None, parent=None):
        """
        Initialize the section properties dialog.

        Args:
            section: LaneSection to edit
            road_id: ID of the road this section belongs to
            centerline_length_pixels: Total length of centerline in pixels
            centerline_points: Optional list of centerline points for metric calculation
            transformer: Optional coordinate transformer for metric conversion
            parent: Parent widget
        """
        super().__init__(f"Section {section.section_number} Properties", parent, min_width=400)

        self.section = section
        self.road_id = road_id
        self.centerline_length_pixels = centerline_length_pixels
        self.centerline_points = centerline_points
        self.transformer = transformer

        # Calculate metric s-offsets if we have georeferencing
        self.metric_soffsets = None
        if self.transformer and self.centerline_points:
            self.metric_soffsets = self._calculate_metric_soffsets()

        self.setup_ui()
        self.load_properties()

    def _calculate_metric_soffsets(self) -> List[float]:
        """
        Calculate s-offsets in meters using proper metric space calculation.

        This uses the same method as ImageView._calculate_soffsets to ensure consistency.

        Returns:
            List of s-offsets in meters
        """
        if not self.centerline_points or not self.transformer:
            return []

        # Convert all points to metric coordinates
        metric_points = []
        for x, y in self.centerline_points:
            mx, my = self.transformer.pixel_to_meters(x, y)
            metric_points.append((mx, my))

        # Calculate cumulative distances in metric space
        soffsets = [0.0]
        cumulative = 0.0
        for i in range(1, len(metric_points)):
            x1, y1 = metric_points[i - 1]
            x2, y2 = metric_points[i]
            distance = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
            cumulative += distance
            soffsets.append(cumulative)

        return soffsets

    def _calculate_pixel_soffsets(self) -> List[float]:
        """
        Calculate s-offsets in pixels.

        Returns:
            List of s-offsets in pixels (cumulative distances)
        """
        if not self.centerline_points:
            return []

        soffsets = [0.0]
        cumulative = 0.0
        for i in range(1, len(self.centerline_points)):
            x1, y1 = self.centerline_points[i - 1]
            x2, y2 = self.centerline_points[i]
            distance = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
            cumulative += distance
            soffsets.append(cumulative)

        return soffsets

    def _interpolate_metric_soffset(self, pixel_s: float, pixel_soffsets: List[float]) -> float:
        """
        Interpolate to find the metric s-offset corresponding to a pixel s-coordinate.

        Args:
            pixel_s: S-coordinate in pixels
            pixel_soffsets: List of pixel s-offsets for each point

        Returns:
            Corresponding s-offset in meters
        """
        if not self.metric_soffsets or not pixel_soffsets:
            return 0.0

        # Find the segment containing pixel_s
        for i in range(len(pixel_soffsets) - 1):
            if pixel_soffsets[i] <= pixel_s <= pixel_soffsets[i + 1]:
                # Interpolate between metric_soffsets[i] and metric_soffsets[i + 1]
                if pixel_soffsets[i + 1] == pixel_soffsets[i]:
                    # Avoid division by zero
                    return self.metric_soffsets[i]

                t = (pixel_s - pixel_soffsets[i]) / (pixel_soffsets[i + 1] - pixel_soffsets[i])
                metric_s = self.metric_soffsets[i] + t * (self.metric_soffsets[i + 1] - self.metric_soffsets[i])
                return metric_s

        # If pixel_s is at or past the last point, return the last metric s-offset
        if pixel_s >= pixel_soffsets[-1]:
            return self.metric_soffsets[-1]

        # Otherwise, return the first metric s-offset
        return self.metric_soffsets[0]

    def setup_ui(self):
        """Setup the dialog UI."""
        # Section info group
        info_layout = self.add_form_group("Section Information")

        # Section number (read-only)
        section_num_label = QLabel(str(self.section.section_number))
        info_layout.addRow("Section Number:", section_num_label)

        # Calculate pixel s-offsets for interpolation
        pixel_soffsets = None
        if self.centerline_points:
            pixel_soffsets = self._calculate_pixel_soffsets()

        # S-start (read-only)
        if self.metric_soffsets and pixel_soffsets:
            s_start_m = self._interpolate_metric_soffset(self.section.s_start, pixel_soffsets)
            s_start_label = QLabel(f"{s_start_m:.2f} m")
        else:
            s_start_label = QLabel(f"{self.section.s_start:.2f} px")
        info_layout.addRow("Start Position (s):", s_start_label)

        # S-end (read-only)
        if self.metric_soffsets and pixel_soffsets:
            s_end_m = self._interpolate_metric_soffset(self.section.s_end, pixel_soffsets)
            s_end_label = QLabel(f"{s_end_m:.2f} m")
        else:
            s_end_label = QLabel(f"{self.section.s_end:.2f} px")
        info_layout.addRow("End Position (s):", s_end_label)

        # Section length (read-only)
        if self.metric_soffsets and pixel_soffsets:
            s_start_m = self._interpolate_metric_soffset(self.section.s_start, pixel_soffsets)
            s_end_m = self._interpolate_metric_soffset(self.section.s_end, pixel_soffsets)
            length_m = s_end_m - s_start_m
            length_label = QLabel(f"{length_m:.2f} m")
        else:
            length_px = self.section.get_length_pixels()
            length_label = QLabel(f"{length_px:.2f} px")
        info_layout.addRow("Section Length:", length_label)

        # Percentage of total road length
        if self.centerline_length_pixels > 0:
            length_px = self.section.get_length_pixels()
            percentage = (length_px / self.centerline_length_pixels) * 100
            percentage_label = QLabel(f"{percentage:.1f}% of total road")
            info_layout.addRow("Coverage:", percentage_label)

        # Number of lanes (read-only)
        num_lanes = len([l for l in self.section.lanes if l.id != 0])  # Exclude center lane
        lanes_label = QLabel(f"{num_lanes} lanes")
        info_layout.addRow("Lanes in Section:", lanes_label)

        # OpenDRIVE properties group
        opendrive_layout = self.add_form_group("OpenDRIVE Properties")

        # Single side property
        self.single_side_combo = QComboBox()
        self.single_side_combo.addItem("Both sides", None)
        self.single_side_combo.addItem("Left only", "left")
        self.single_side_combo.addItem("Right only", "right")

        opendrive_layout.addRow("Single Side:", self.single_side_combo)

        # Add help text
        help_label = QLabel(
            "Single Side restricts lanes to one side of the reference line. "
            "Use 'Both sides' for normal road sections with lanes on both sides."
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet("QLabel { color: gray; font-size: 9pt; }")
        opendrive_layout.addRow("", help_label)

        # Buttons
        self.create_button_box()

    def load_properties(self):
        """Load section properties into the form."""
        # Set current value for single_side_combo
        if self.section.single_side is None:
            self.single_side_combo.setCurrentIndex(0)
        elif self.section.single_side == "left":
            self.single_side_combo.setCurrentIndex(1)
        elif self.section.single_side == "right":
            self.single_side_combo.setCurrentIndex(2)

    def accept(self):
        """Handle OK button - save changes."""
        # Update single_side property
        single_side_value = self.single_side_combo.currentData()
        self.section.single_side = single_side_value

        super().accept()

    @classmethod
    def edit_section(cls, section: LaneSection, road_id: str, centerline_length_pixels: float,
                     centerline_points: Optional[List[Tuple[float, float]]] = None,
                     transformer: Optional[CoordinateTransformer] = None, parent=None) -> bool:
        """
        Show dialog to edit section properties.

        Args:
            section: LaneSection to edit
            road_id: ID of the road this section belongs to
            centerline_length_pixels: Total length of centerline in pixels
            centerline_points: Optional list of centerline points for metric calculation
            transformer: Optional coordinate transformer for metric conversion
            parent: Parent widget

        Returns:
            True if user clicked OK and made changes, False otherwise
        """
        dialog = cls(section, road_id, centerline_length_pixels, centerline_points, transformer, parent)
        result = dialog.exec()
        return result == QDialog.DialogCode.Accepted

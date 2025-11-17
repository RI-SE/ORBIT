"""
CSV Control Point Placer dialog.

Handles sequential placement of control points from CSV data on the image.
"""

from typing import List, Optional, Tuple
import math

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QPushButton, QLineEdit, QGroupBox, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal

from orbit.models import Project, ControlPoint
from .csv_import_dialog import CSVControlPoint
from .message_helpers import show_warning, ask_yes_no


class CSVControlPointPlacer(QDialog):
    """Dialog for placing control points from CSV data on the image."""

    # Signal emitted when user wants to pick a point on the image
    pick_point_requested = pyqtSignal()

    def __init__(self, csv_points: List[CSVControlPoint], project: Project, parent=None):
        super().__init__(parent)

        self.csv_points = csv_points
        self.project = project
        self.current_index = 0
        self.pending_pixel_coords: Optional[Tuple[float, float]] = None

        # Set window modality to allow clicking on main window
        # Qt.WindowModal allows interaction with main window but blocks parent dialog
        self.setWindowModality(Qt.WindowModality.NonModal)

        # Register with parent georeferencing dialog
        if parent and hasattr(parent, 'csv_placer_dialog'):
            parent.csv_placer_dialog = self

        self.setup_ui()
        self.show_current_point()

    def setup_ui(self):
        """Setup the dialog UI."""
        self.setWindowTitle("Place Control Point")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)

        layout = QVBoxLayout(self)

        # Progress label
        self.progress_label = QLabel()
        self.progress_label.setStyleSheet("font-weight: bold; font-size: 14pt;")
        layout.addWidget(self.progress_label)

        # CSV data group
        csv_group = QGroupBox("CSV Data")
        csv_layout = QFormLayout()

        self.csv_lat_label = QLabel()
        csv_layout.addRow("Latitude:", self.csv_lat_label)

        self.csv_lon_label = QLabel()
        csv_layout.addRow("Longitude:", self.csv_lon_label)

        self.csv_alt_label = QLabel()
        csv_layout.addRow("Altitude:", self.csv_alt_label)

        csv_group.setLayout(csv_layout)
        layout.addWidget(csv_group)

        # Point name group
        name_group = QGroupBox("Point Name")
        name_layout = QHBoxLayout()

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Enter point name...")
        name_layout.addWidget(self.name_edit)

        name_group.setLayout(name_layout)
        layout.addWidget(name_group)

        # Image location group
        location_group = QGroupBox("Image Location")
        location_layout = QVBoxLayout()

        pick_layout = QHBoxLayout()
        self.pick_point_btn = QPushButton("Pick Point on Image")
        self.pick_point_btn.clicked.connect(self.request_pick_point)
        pick_layout.addWidget(self.pick_point_btn)

        self.picked_coords_label = QLabel("No point selected")
        pick_layout.addWidget(self.picked_coords_label)
        pick_layout.addStretch()

        location_layout.addLayout(pick_layout)

        # Warning label (hidden by default)
        self.warning_label = QLabel()
        self.warning_label.setWordWrap(True)
        self.warning_label.setStyleSheet("color: orange; font-weight: bold;")
        self.warning_label.hide()
        location_layout.addWidget(self.warning_label)

        location_group.setLayout(location_layout)
        layout.addWidget(location_group)

        layout.addStretch()

        # Buttons
        button_layout = QHBoxLayout()

        self.add_btn = QPushButton("Add Control Point")
        self.add_btn.clicked.connect(self.add_control_point)
        self.add_btn.setEnabled(False)
        self.add_btn.setDefault(True)
        button_layout.addWidget(self.add_btn)

        self.skip_btn = QPushButton("Skip This Point")
        self.skip_btn.clicked.connect(self.skip_point)
        button_layout.addWidget(self.skip_btn)

        button_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel Import")
        self.cancel_btn.clicked.connect(self.cancel_import)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)

    def show_current_point(self):
        """Display data for the current CSV point."""
        if self.current_index >= len(self.csv_points):
            # All points processed
            self.accept()
            return

        point = self.csv_points[self.current_index]

        # Update progress
        self.progress_label.setText(
            f"Place Control Point ({self.current_index + 1} of {len(self.csv_points)})"
        )

        # Update CSV data
        self.csv_lat_label.setText(f"{point.latitude:.10f}")
        self.csv_lon_label.setText(f"{point.longitude:.10f}")

        if point.altitude is not None:
            self.csv_alt_label.setText(f"{point.altitude:.2f} m")
        else:
            self.csv_alt_label.setText("—")

        # Update name (pre-fill with CSV name, user can edit)
        self.name_edit.setText(point.point_name)
        self.name_edit.selectAll()

        # Reset state
        self.pending_pixel_coords = None
        self.picked_coords_label.setText("No point selected")
        self.add_btn.setEnabled(False)
        self.warning_label.hide()
        self.pick_point_btn.setText("Pick Point on Image")
        self.pick_point_btn.setEnabled(True)

    def request_pick_point(self):
        """Request picking a point on the image."""
        # Emit signal to parent (GeoreferenceDialog)
        if self.parent() and hasattr(self.parent(), 'pick_point_requested'):
            # Connect to the parent's pick point signal
            self.parent().pick_point_requested.emit()

        self.pick_point_btn.setText("Click on image...")
        self.pick_point_btn.setEnabled(False)

        # Minimize this dialog so user can see image
        self.showMinimized()

    def set_picked_point(self, x: float, y: float):
        """
        Set the picked point coordinates.

        Called by parent when user clicks on image.
        """
        self.pending_pixel_coords = (x, y)
        self.picked_coords_label.setText(f"({x:.1f}, {y:.1f})")
        self.pick_point_btn.setText("Pick Point on Image")
        self.pick_point_btn.setEnabled(True)
        self.add_btn.setEnabled(True)

        # Restore window
        self.showNormal()
        self.raise_()
        self.activateWindow()

        # Check if point seems reasonable
        self.check_point_bounds(x, y)

    def check_point_bounds(self, pixel_x: float, pixel_y: float):
        """
        Check if picked point is reasonable and show warning if suspicious.

        Args:
            pixel_x: Picked x coordinate
            pixel_y: Picked y coordinate
        """
        point = self.csv_points[self.current_index]

        # If we have existing control points, estimate expected location
        if len(self.project.control_points) >= 2:
            estimated = self.estimate_pixel_coords(point.latitude, point.longitude)

            if estimated:
                est_x, est_y = estimated
                distance = math.sqrt((pixel_x - est_x)**2 + (pixel_y - est_y)**2)

                # If more than 100 pixels away from estimate, warn
                if distance > 100:
                    self.warning_label.setText(
                        f"⚠ Warning: Picked location seems far from expected position.\n"
                        f"Expected near ({est_x:.0f}, {est_y:.0f}), got ({pixel_x:.0f}, {pixel_y:.0f}).\n"
                        f"Distance: {distance:.0f} pixels"
                    )
                    self.warning_label.show()
                    return

        self.warning_label.hide()

    def estimate_pixel_coords(self, latitude: float, longitude: float) -> Optional[Tuple[float, float]]:
        """
        Estimate pixel coordinates for a lat/lon using existing control points.

        Uses simple linear interpolation/extrapolation.

        Args:
            latitude: Target latitude
            longitude: Target longitude

        Returns:
            Tuple of (pixel_x, pixel_y) or None if cannot estimate
        """
        if len(self.project.control_points) < 2:
            return None

        # Use the first two control points to estimate scale and offset
        cp1 = self.project.control_points[0]
        cp2 = self.project.control_points[1]

        # Calculate scale factors (pixels per degree)
        if cp2.longitude != cp1.longitude:
            scale_x = (cp2.pixel_x - cp1.pixel_x) / (cp2.longitude - cp1.longitude)
        else:
            scale_x = 0

        if cp2.latitude != cp1.latitude:
            scale_y = (cp2.pixel_y - cp1.pixel_y) / (cp2.latitude - cp1.latitude)
        else:
            scale_y = 0

        # Estimate pixel coordinates
        pixel_x = cp1.pixel_x + (longitude - cp1.longitude) * scale_x
        pixel_y = cp1.pixel_y + (latitude - cp1.latitude) * scale_y

        return (pixel_x, pixel_y)

    def add_control_point(self):
        """Add the current control point to the project."""
        if not self.pending_pixel_coords:
            show_warning(self, "Please pick a point on the image first.", "No Point Selected")
            return

        point = self.csv_points[self.current_index]
        point_name = self.name_edit.text().strip()

        if not point_name:
            show_warning(self, "Please enter a name for the control point.", "Invalid Name")
            return

        # Check for duplicate names
        existing_names = [cp.name for cp in self.project.control_points if cp.name]
        if point_name in existing_names:
            if ask_yes_no(self, f"A control point named '{point_name}' already exists.\n\n"
                "Do you want to add a suffix to make it unique?", "Duplicate Name"):
                # Add suffix
                suffix = 2
                while f"{point_name}_{suffix}" in existing_names:
                    suffix += 1
                point_name = f"{point_name}_{suffix}"
            else:
                return

        # Create control point
        cp = ControlPoint(
            pixel_x=self.pending_pixel_coords[0],
            pixel_y=self.pending_pixel_coords[1],
            longitude=point.longitude,
            latitude=point.latitude,
            name=point_name
        )

        # Add to project
        self.project.add_control_point(cp)

        # Update CSV point status
        point.status = "placed"
        point.pixel_x = cp.pixel_x
        point.pixel_y = cp.pixel_y

        # Notify parent (GeoreferenceDialog) that control points changed
        if self.parent() and hasattr(self.parent(), 'control_points_changed'):
            self.parent().control_points_changed.emit()

        # Move to next point
        self.current_index += 1
        self.show_current_point()

    def skip_point(self):
        """Skip the current point."""
        point = self.csv_points[self.current_index]
        point.status = "skipped"

        # Move to next point
        self.current_index += 1
        self.show_current_point()

    def cancel_import(self):
        """Cancel the import process."""
        if ask_yes_no(self, "Are you sure you want to cancel the import?\n\n"
            "Already placed control points will be kept.", "Cancel Import"):
            self.reject()

    def closeEvent(self, event):
        """Handle dialog close event."""
        # Unregister from parent
        if self.parent() and hasattr(self.parent(), 'csv_placer_dialog'):
            self.parent().csv_placer_dialog = None

        super().closeEvent(event)

    def accept(self):
        """Handle dialog acceptance (all points processed)."""
        # Unregister from parent
        if self.parent() and hasattr(self.parent(), 'csv_placer_dialog'):
            self.parent().csv_placer_dialog = None

        super().accept()

    def reject(self):
        """Handle dialog rejection (cancelled)."""
        # Unregister from parent
        if self.parent() and hasattr(self.parent(), 'csv_placer_dialog'):
            self.parent().csv_placer_dialog = None

        super().reject()

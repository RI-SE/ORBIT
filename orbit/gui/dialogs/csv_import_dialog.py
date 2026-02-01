"""
CSV import dialog for control points.

Allows importing control points from CSV files with flexible column detection.
"""

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from orbit.models import Project

from ..utils.message_helpers import show_error, show_info, show_warning
from .base_dialog import BaseDialog


@dataclass
class CSVControlPoint:
    """Intermediate representation of CSV control point."""
    row_number: int
    point_name: str
    latitude: float
    longitude: float
    altitude: Optional[float] = None
    status: str = "pending"  # pending, placed, skipped, error
    pixel_x: Optional[float] = None
    pixel_y: Optional[float] = None
    error: Optional[str] = None
    selected: bool = True


# Column name aliases for flexible detection
LATITUDE_ALIASES = ['latitude', 'lat', 'y', 'northing', 'north']
LONGITUDE_ALIASES = ['longitude', 'lon', 'long', 'lng', 'x', 'easting', 'east']
NAME_ALIASES = ['point_name', 'name', 'id', 'point_id', 'marker', 'label']
ALTITUDE_ALIASES = ['altitude', 'alt', 'elevation', 'z', 'height']


def find_column_index(headers: List[str], aliases: List[str]) -> Optional[int]:
    """
    Find column index by matching aliases (case-insensitive).

    Args:
        headers: List of column headers from CSV
        aliases: List of possible column name aliases

    Returns:
        Column index or None if not found
    """
    headers_lower = [h.lower().strip() for h in headers]
    for alias in aliases:
        if alias in headers_lower:
            return headers_lower.index(alias)
    return None


def detect_columns(headers: List[str]) -> dict:
    """
    Auto-detect column indices by name matching.

    Args:
        headers: List of column headers from CSV

    Returns:
        Dictionary with 'name', 'latitude', 'longitude', 'altitude' keys
    """
    return {
        'name': find_column_index(headers, NAME_ALIASES),
        'latitude': find_column_index(headers, LATITUDE_ALIASES),
        'longitude': find_column_index(headers, LONGITUDE_ALIASES),
        'altitude': find_column_index(headers, ALTITUDE_ALIASES),
    }


def parse_csv_file(filepath: Path) -> Tuple[List[CSVControlPoint], str]:
    """
    Parse CSV file and extract control points.

    Args:
        filepath: Path to CSV file

    Returns:
        Tuple of (list of CSVControlPoint, error message or empty string)
    """
    points = []

    try:
        # Try different encodings
        encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']
        content = None

        for encoding in encodings:
            try:
                with open(filepath, 'r', encoding=encoding) as f:
                    content = f.read()
                break
            except UnicodeDecodeError:
                continue

        if content is None:
            return [], "Failed to decode CSV file with any supported encoding"

        # Parse CSV
        lines = content.strip().split('\n')
        if len(lines) < 2:
            return [], "CSV file is empty or has no data rows"

        reader = csv.reader(lines)
        headers = next(reader)

        # Detect columns
        columns = detect_columns(headers)

        if columns['latitude'] is None or columns['longitude'] is None:
            return [], (
                "Could not detect latitude and longitude columns.\n\n"
                f"Available columns: {', '.join(headers)}\n\n"
                "Expected column names like: latitude, longitude, lat, lon"
            )

        # Parse data rows
        for i, row in enumerate(reader, start=1):
            if not row or len(row) < max(columns['latitude'], columns['longitude']) + 1:
                continue  # Skip empty or incomplete rows

            try:
                # Extract data
                point_name = row[columns['name']] if columns['name'] is not None else f"Point_{i}"
                latitude = float(row[columns['latitude']])
                longitude = float(row[columns['longitude']])
                altitude = (
                    float(row[columns['altitude']])
                    if columns['altitude'] is not None
                    and row[columns['altitude']]
                    else None
                )

                # Validate ranges
                if not (-90 <= latitude <= 90):
                    points.append(CSVControlPoint(
                        row_number=i,
                        point_name=point_name,
                        latitude=0,
                        longitude=0,
                        status="error",
                        error=f"Invalid latitude: {latitude} (must be -90 to 90)",
                        selected=False
                    ))
                    continue

                if not (-180 <= longitude <= 180):
                    points.append(CSVControlPoint(
                        row_number=i,
                        point_name=point_name,
                        latitude=0,
                        longitude=0,
                        status="error",
                        error=f"Invalid longitude: {longitude} (must be -180 to 180)",
                        selected=False
                    ))
                    continue

                # Create control point
                points.append(CSVControlPoint(
                    row_number=i,
                    point_name=point_name,
                    latitude=latitude,
                    longitude=longitude,
                    altitude=altitude,
                    selected=True
                ))

            except (ValueError, IndexError) as e:
                # Invalid numeric value or missing column
                point_name = (
                    row[columns['name']]
                    if columns['name'] is not None
                    and len(row) > columns['name']
                    else f"Point_{i}"
                )
                points.append(CSVControlPoint(
                    row_number=i,
                    point_name=point_name,
                    latitude=0,
                    longitude=0,
                    status="error",
                    error=f"Parse error: {str(e)}",
                    selected=False
                ))

        if not points:
            return [], "No valid data rows found in CSV"

        return points, ""

    except Exception as e:
        return [], f"Error reading CSV file: {type(e).__name__}: {str(e)}"


class CSVImportDialog(BaseDialog):
    """Dialog for importing control points from CSV."""

    # Signal emitted when user wants to start placing points
    start_placement_requested = pyqtSignal(list)  # List of CSVControlPoint

    def __init__(self, project: Project, parent=None):
        super().__init__("Import Control Points from CSV", parent, min_width=800, min_height=600)

        self.project = project
        self.csv_points: List[CSVControlPoint] = []
        self.csv_filepath: Optional[Path] = None

        self.setup_ui()
        self.load_properties()

        # Prompt user to select CSV file on startup
        self.load_csv_file()

    def setup_ui(self):
        """Setup the dialog UI."""

        # File info section
        file_layout = QHBoxLayout()
        file_layout.addWidget(QLabel("File:"))
        self.file_label = QLabel("No file selected")
        file_layout.addWidget(self.file_label, 1)

        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self.load_csv_file)
        file_layout.addWidget(self.browse_btn)

        self.get_main_layout().addLayout(file_layout)

        # Info label
        self.info_label = QLabel("No data loaded")
        self.get_main_layout().addWidget(self.info_label)

        # Table widget
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Select", "Name", "Latitude", "Longitude", "Status"
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.get_main_layout().addWidget(self.table)

        # Selection info
        self.selection_label = QLabel("Selected: 0 points")
        self.get_main_layout().addWidget(self.selection_label)

        # Button layout
        button_layout = QHBoxLayout()

        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self.select_all)
        button_layout.addWidget(self.select_all_btn)

        self.deselect_all_btn = QPushButton("Deselect All")
        self.deselect_all_btn.clicked.connect(self.deselect_all)
        button_layout.addWidget(self.deselect_all_btn)

        button_layout.addStretch()

        self.start_placement_btn = QPushButton("Start Placement")
        self.start_placement_btn.clicked.connect(self.start_placement)
        self.start_placement_btn.setEnabled(False)
        button_layout.addWidget(self.start_placement_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        self.get_main_layout().addLayout(button_layout)

    def load_properties(self):
        """No properties to load for CSV import dialog."""
        pass

    def load_csv_file(self):
        """Load and parse CSV file."""
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Select CSV File",
            "",
            "CSV Files (*.csv);;All Files (*)"
        )

        if not filepath:
            # If no file selected and this is initial load, close dialog
            if not self.csv_points:
                self.reject()
            return

        self.csv_filepath = Path(filepath)
        self.file_label.setText(str(self.csv_filepath.name))

        # Parse CSV
        points, error = parse_csv_file(self.csv_filepath)

        if error:
            show_error(self, f"Failed to parse CSV file:\n\n{error}", "CSV Parse Error")
            self.csv_points = []
            self.update_table()
            return

        self.csv_points = points
        self.update_table()

    def update_table(self):
        """Update table with CSV points."""
        self.table.setRowCount(0)

        valid_count = 0
        selected_count = 0

        for point in self.csv_points:
            row = self.table.rowCount()
            self.table.insertRow(row)

            # Checkbox
            checkbox_widget = QWidget()
            checkbox_layout = QHBoxLayout(checkbox_widget)
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            checkbox_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            checkbox = QCheckBox()
            checkbox.setChecked(point.selected and point.status != "error")
            checkbox.setEnabled(point.status != "error")
            checkbox.stateChanged.connect(lambda state, p=point: self.on_checkbox_changed(p, state))
            checkbox_layout.addWidget(checkbox)

            self.table.setCellWidget(row, 0, checkbox_widget)

            # Name
            self.table.setItem(row, 1, QTableWidgetItem(point.point_name))

            # Latitude
            lat_text = f"{point.latitude:.10f}" if point.status != "error" else "—"
            self.table.setItem(row, 2, QTableWidgetItem(lat_text))

            # Longitude
            lon_text = f"{point.longitude:.10f}" if point.status != "error" else "—"
            self.table.setItem(row, 3, QTableWidgetItem(lon_text))

            # Status
            status_text = point.status.capitalize()
            if point.error:
                status_text = f"Error: {point.error}"
            status_item = QTableWidgetItem(status_text)

            # Color code status
            if point.status == "error":
                status_item.setForeground(Qt.GlobalColor.red)
            elif point.status == "placed":
                status_item.setForeground(Qt.GlobalColor.darkGreen)
            elif point.status == "skipped":
                status_item.setForeground(Qt.GlobalColor.gray)

            self.table.setItem(row, 4, status_item)

            if point.status != "error":
                valid_count += 1
                if point.selected:
                    selected_count += 1

        # Update info labels
        total_count = len(self.csv_points)
        error_count = sum(1 for p in self.csv_points if p.status == "error")

        self.info_label.setText(
            f"Detected: {total_count} points ({valid_count} valid, {error_count} errors)"
        )
        self.selection_label.setText(f"Selected: {selected_count} points")

        # Enable start button if we have selected points
        self.start_placement_btn.setEnabled(selected_count > 0)

    def on_checkbox_changed(self, point: CSVControlPoint, state):
        """Handle checkbox state change."""
        point.selected = (state == Qt.CheckState.Checked.value)
        self.update_selection_count()

    def update_selection_count(self):
        """Update selection count label."""
        selected_count = sum(1 for p in self.csv_points if p.selected and p.status != "error")
        self.selection_label.setText(f"Selected: {selected_count} points")
        self.start_placement_btn.setEnabled(selected_count > 0)

    def select_all(self):
        """Select all valid points."""
        for point in self.csv_points:
            if point.status != "error":
                point.selected = True
        self.update_table()

    def deselect_all(self):
        """Deselect all points."""
        for point in self.csv_points:
            point.selected = False
        self.update_table()

    def start_placement(self):
        """Start the placement workflow."""
        # Get selected points
        selected_points = [p for p in self.csv_points if p.selected and p.status != "error"]

        if not selected_points:
            show_warning(self, "Please select at least one point to place.", "No Points Selected")
            return

        # Import and show placement dialog
        from ..utils.csv_control_point_placer import CSVControlPointPlacer

        placer = CSVControlPointPlacer(
            selected_points,
            self.project,
            self.parent()  # Pass georeferencing dialog as parent
        )

        # Connect to completion signals
        placer.accepted.connect(lambda: self.on_placement_complete(placer, True))
        placer.rejected.connect(lambda: self.on_placement_complete(placer, False))

        # Hide this dialog while placing
        self.hide()

        # Show non-modally (don't use exec())
        placer.show()

    def on_placement_complete(self, placer, accepted: bool):
        """Handle completion of placement dialog."""
        # Show this dialog again
        self.show()

        # Update table to show placement status
        self.update_table()

        if accepted:
            # If all selected points are placed, close this dialog
            selected_points = [p for p in self.csv_points if p.selected and p.status != "error"]
            remaining = sum(1 for p in self.csv_points if p.selected and p.status == "pending")
            if remaining == 0:
                show_info(self, f"Successfully placed {len(selected_points)} control points.", "Import Complete")
                self.accept()

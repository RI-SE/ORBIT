"""
CSV import dialog for control points.

Allows importing control points from CSV files with flexible column detection.
"""

from pathlib import Path
from typing import List, Optional

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

from orbit_core.models import Project
from orbit_core.utils.control_point_csv import (  # noqa: F401 - re-exported for existing imports
    ALTITUDE_ALIASES,
    LATITUDE_ALIASES,
    LONGITUDE_ALIASES,
    NAME_ALIASES,
    POINT_TYPE_ALIASES,
    SIGMA_H_ALIASES,
    SIGMA_V_ALIASES,
    CSVControlPoint,
    detect_columns,
    find_column_index,
    parse_csv_file,
)

from ..utils.message_helpers import show_error, show_info, show_warning
from .base_dialog import BaseDialog


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
        start_dir = getattr(self.parent(), '_last_file_directory', '')
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Select CSV File",
            start_dir,
            "CSV Files (*.csv);;All Files (*)"
        )

        if not filepath:
            # If no file selected and this is initial load, close dialog
            if not self.csv_points:
                self.reject()
            return

        if hasattr(self.parent(), '_remember_directory'):
            self.parent()._remember_directory(filepath)
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

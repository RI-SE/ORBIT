"""
Georeferencing dialog for ORBIT.

Allows adding and managing control points for coordinate transformation.
Supports both training (GCP) and validation (GVP) points.
"""

from typing import Optional, List
from pathlib import Path
import numpy as np

from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QFormLayout,
    QPushButton, QGroupBox, QTableWidget, QTableWidgetItem,
    QLabel, QDialogButtonBox, QDoubleSpinBox, QMessageBox,
    QHeaderView, QComboBox, QTextEdit, QCheckBox, QProgressBar,
    QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QEvent
from PyQt6.QtGui import QFont

from orbit.utils.logging_config import get_logger
from orbit.models import Project, ControlPoint
from .base_dialog import BaseDialog
from ..utils.message_helpers import show_error, show_warning, show_info, ask_yes_no

logger = get_logger(__name__)


class GeoreferenceDialog(BaseDialog):
    """Dialog for managing georeferencing control points."""

    # Signal emitted when user wants to pick a point on the image
    pick_point_requested = pyqtSignal()
    # Signal emitted when control points are modified (added/removed)
    control_points_changed = pyqtSignal()

    def __init__(self, project: Project, parent=None, verbose: bool = False):
        super().__init__("Georeferencing", parent, min_width=900, min_height=700)

        self.project = project
        self.verbose = verbose  # Debug output flag
        self.pending_pixel_coords: Optional[tuple] = None
        self.csv_placer_dialog: Optional['CSVControlPointPlacer'] = None  # Track active placer dialog
        self.setup_ui()
        self.load_properties()
        self.update_validation()
        self.update_uncertainty_statistics()

        # Install event filter for auto-select on focus and paste support
        self.longitude_spin.lineEdit().installEventFilter(self)
        self.latitude_spin.lineEdit().installEventFilter(self)

        # Enable context menu (right-click) for copy/paste
        self.longitude_spin.lineEdit().setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)
        self.latitude_spin.lineEdit().setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)

    def setup_ui(self):
        """Setup the dialog UI."""

        # Info section
        info_group = QGroupBox("Information")
        info_layout = QVBoxLayout()

        # Get minimum points required based on transform method
        min_points = 4 if self.project.transform_method == 'homography' else 3
        method_name = 'Homography' if self.project.transform_method == 'homography' else 'Affine'

        info_text = QLabel(
            f"<b>Georeferencing Control Points</b><br><br>"
            f"Current method: <b>{method_name}</b> (requires {min_points}+ training points)<br>"
            f"Change method in Edit → Preferences<br><br>"
            "<b>GCP (Georef Control Point):</b> Training points used to compute transformation<br>"
            "<b>GVP (Georef Validation Point):</b> Test points used to validate accuracy<br><br>"
            "<i>Steps:</i><br>"
            "1. Click 'Pick Point on Image' to select a location<br>"
            "2. Enter the longitude and latitude for that location<br>"
            f"3. Choose 'Training (GCP)' or 'Validation (GVP)'<br>"
            "4. Click 'Add Control Point'<br>"
            f"5. Add at least {min_points} training points for transformation"
        )
        info_text.setWordWrap(True)
        info_layout.addWidget(info_text)
        info_group.setLayout(info_layout)
        self.get_main_layout().addWidget(info_group)

        # Control points table
        points_group = QGroupBox("Control Points")
        points_layout = QVBoxLayout()

        self.points_table = QTableWidget()
        self.points_table.setColumnCount(6)
        self.points_table.setHorizontalHeaderLabels([
            "Name", "Type", "Pixel X", "Pixel Y", "Longitude", "Latitude"
        ])
        self.points_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.points_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.points_table.itemChanged.connect(self.on_table_item_changed)
        points_layout.addWidget(self.points_table)

        # Button layout for table operations
        table_button_layout = QHBoxLayout()

        self.remove_point_btn = QPushButton("Remove Selected")
        self.remove_point_btn.clicked.connect(self.remove_selected_point)
        table_button_layout.addWidget(self.remove_point_btn)

        self.clear_all_btn = QPushButton("Clear All")
        self.clear_all_btn.clicked.connect(self.clear_all_points)
        table_button_layout.addWidget(self.clear_all_btn)

        self.import_csv_btn = QPushButton("Import from CSV...")
        self.import_csv_btn.clicked.connect(self.import_from_csv)
        table_button_layout.addWidget(self.import_csv_btn)

        table_button_layout.addStretch()
        points_layout.addLayout(table_button_layout)

        points_group.setLayout(points_layout)
        self.get_main_layout().addWidget(points_group)

        # Add point section
        add_group = QGroupBox("Add New Control Point")
        add_layout = QFormLayout()

        # Pick point button
        pick_layout = QHBoxLayout()
        self.pick_point_btn = QPushButton("Pick Point on Image")
        self.pick_point_btn.clicked.connect(self.request_pick_point)
        pick_layout.addWidget(self.pick_point_btn)

        self.picked_coords_label = QLabel("No point selected")
        pick_layout.addWidget(self.picked_coords_label)
        pick_layout.addStretch()
        add_layout.addRow("Image Location:", pick_layout)

        # Longitude input
        self.longitude_spin = QDoubleSpinBox()
        self.longitude_spin.setRange(-180.0, 180.0)
        self.longitude_spin.setDecimals(10)
        self.longitude_spin.setSingleStep(0.0000001)
        self.longitude_spin.setSuffix(" °")
        self.longitude_spin.setKeyboardTracking(True)
        self.longitude_spin.setToolTip("Click to select, then paste from clipboard (Ctrl+V)")
        add_layout.addRow("Longitude:", self.longitude_spin)

        # Latitude input
        self.latitude_spin = QDoubleSpinBox()
        self.latitude_spin.setRange(-90.0, 90.0)
        self.latitude_spin.setDecimals(10)
        self.latitude_spin.setSingleStep(0.0000001)
        self.latitude_spin.setSuffix(" °")
        self.latitude_spin.setKeyboardTracking(True)
        self.latitude_spin.setToolTip("Click to select, then paste from clipboard (Ctrl+V)")
        add_layout.addRow("Latitude:", self.latitude_spin)

        # Point type checkbox
        self.validation_check = QCheckBox("Use for validation only (GVP)")
        self.validation_check.setToolTip(
            "GCP (unchecked): Training point used to compute transformation\n"
            "GVP (checked): Validation point used to test accuracy"
        )
        add_layout.addRow("Point Type:", self.validation_check)

        # Add button
        self.add_point_btn = QPushButton("Add Control Point")
        self.add_point_btn.clicked.connect(self.add_control_point)
        self.add_point_btn.setEnabled(False)
        add_layout.addRow("", self.add_point_btn)

        add_group.setLayout(add_layout)
        self.get_main_layout().addWidget(add_group)

        # Status and validation section
        status_group = QGroupBox("Status and Validation")
        status_layout = QVBoxLayout()

        self.status_label = QLabel()
        status_layout.addWidget(self.status_label)

        # Validation results text
        self.validation_text = QTextEdit()
        self.validation_text.setReadOnly(True)
        self.validation_text.setMaximumHeight(150)
        font = QFont("Monospace")
        font.setStyleHint(QFont.StyleHint.TypeWriter)
        self.validation_text.setFont(font)
        status_layout.addWidget(self.validation_text)

        status_group.setLayout(status_layout)
        self.get_main_layout().addWidget(status_group)

        # Uncertainty Analysis section
        uncertainty_group = QGroupBox("Uncertainty Analysis")
        uncertainty_layout = QVBoxLayout()

        # Uncertainty statistics text
        self.uncertainty_text = QTextEdit()
        self.uncertainty_text.setReadOnly(True)
        self.uncertainty_text.setMaximumHeight(150)
        uncertainty_layout.addWidget(self.uncertainty_text)

        # Parameter configuration
        params_layout = QHBoxLayout()

        # Sigma pixels (measurement error)
        params_layout.addWidget(QLabel("Measurement error (σ pixels):"))
        self.sigma_pixels_spin = QDoubleSpinBox()
        self.sigma_pixels_spin.setRange(0.1, 5.0)
        self.sigma_pixels_spin.setSingleStep(0.1)
        self.sigma_pixels_spin.setDecimals(1)
        self.sigma_pixels_spin.setValue(self.project.mc_sigma_pixels)
        self.sigma_pixels_spin.setToolTip(
            "Standard deviation of measurement error in pixels\n"
            "Typical: 1.0-2.0 px for manual digitization\n"
            "Lower for careful work, higher for rough annotation"
        )
        self.sigma_pixels_spin.valueChanged.connect(self.on_parameter_changed)
        params_layout.addWidget(self.sigma_pixels_spin)

        params_layout.addSpacing(20)

        # Baseline uncertainty (meters)
        params_layout.addWidget(QLabel("Baseline uncertainty (m):"))
        self.baseline_uncertainty_spin = QDoubleSpinBox()
        self.baseline_uncertainty_spin.setRange(0.01, 0.5)
        self.baseline_uncertainty_spin.setSingleStep(0.01)
        self.baseline_uncertainty_spin.setDecimals(2)
        self.baseline_uncertainty_spin.setValue(self.project.baseline_uncertainty_m)
        self.baseline_uncertainty_spin.setToolTip(
            "Minimum expected position uncertainty in meters\n"
            "Accounts for measurement, digitization, and transformation errors\n"
            "Typical: 0.03-0.10m depending on image resolution and scale"
        )
        self.baseline_uncertainty_spin.valueChanged.connect(self.on_parameter_changed)
        params_layout.addWidget(self.baseline_uncertainty_spin)

        params_layout.addSpacing(20)

        # GCP suggestion threshold
        params_layout.addWidget(QLabel("GCP suggestion threshold (m):"))
        self.gcp_threshold_spin = QDoubleSpinBox()
        self.gcp_threshold_spin.setRange(0.05, 1.0)
        self.gcp_threshold_spin.setSingleStep(0.05)
        self.gcp_threshold_spin.setDecimals(2)
        self.gcp_threshold_spin.setValue(self.project.gcp_suggestion_threshold)
        self.gcp_threshold_spin.setToolTip(
            "Minimum uncertainty for GCP suggestions\n"
            "Lower value = suggest more locations\n"
            "Higher value = suggest only worst areas\n"
            "Typical: 0.15-0.30m depending on your accuracy needs"
        )
        self.gcp_threshold_spin.valueChanged.connect(self.on_parameter_changed)
        params_layout.addWidget(self.gcp_threshold_spin)

        params_layout.addStretch()
        uncertainty_layout.addLayout(params_layout)

        # Analysis buttons
        analysis_button_layout = QHBoxLayout()

        # Monte Carlo button (primary method)
        self.compute_monte_carlo_btn = QPushButton("Compute Uncertainty (Monte Carlo)")
        self.compute_monte_carlo_btn.setToolTip(
            "Run Monte Carlo analysis with measurement error (200 iterations)\n"
            "Configure parameters above before running\n"
            "Results are cached for fast queries"
        )
        self.compute_monte_carlo_btn.clicked.connect(self.run_monte_carlo_analysis)
        analysis_button_layout.addWidget(self.compute_monte_carlo_btn)

        # Bootstrap button (alternative detailed method)
        self.analyze_uncertainty_btn = QPushButton("Bootstrap Analysis")
        self.analyze_uncertainty_btn.setToolTip(
            "Alternative: Bootstrap resampling (200 iterations)\n"
            "Resamples GCPs with replacement to estimate uncertainty"
        )
        self.analyze_uncertainty_btn.clicked.connect(self.run_bootstrap_analysis)
        analysis_button_layout.addWidget(self.analyze_uncertainty_btn)

        # GCP suggestions button
        self.suggest_gcp_btn = QPushButton("Suggest GCP Locations")
        self.suggest_gcp_btn.setToolTip(
            "Analyze uncertainty and suggest where to add control points\n"
            "Identifies high-uncertainty areas that would benefit from GCPs"
        )
        self.suggest_gcp_btn.clicked.connect(self.suggest_gcp_locations)
        self.suggest_gcp_btn.setEnabled(False)  # Enable after Monte Carlo
        analysis_button_layout.addWidget(self.suggest_gcp_btn)

        analysis_button_layout.addStretch()
        uncertainty_layout.addLayout(analysis_button_layout)

        # Progress bar for analysis
        self.analysis_progress = QProgressBar()
        self.analysis_progress.hide()
        uncertainty_layout.addWidget(self.analysis_progress)

        uncertainty_group.setLayout(uncertainty_layout)
        self.get_main_layout().addWidget(uncertainty_group)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        self.get_main_layout().addWidget(button_box)

    def load_properties(self):
        """Load properties (control points) into the dialog."""
        self.load_control_points()

    def load_control_points(self):
        """Load control points from project into table."""
        # Block signals to prevent triggering validation on every row add
        self.points_table.blockSignals(True)

        self.points_table.setRowCount(0)
        for i, cp in enumerate(self.project.control_points):
            self.add_point_to_table(cp, i)

        self.points_table.blockSignals(False)
        self.update_status()

    def add_point_to_table(self, cp: ControlPoint, index: int):
        """Add a control point to the table."""
        row = self.points_table.rowCount()
        self.points_table.insertRow(row)

        name = cp.name if cp.name else f"CP{index + 1}"
        self.points_table.setItem(row, 0, QTableWidgetItem(name))

        # Type column with combo box
        type_combo = QComboBox()
        type_combo.addItem("Training (GCP)", False)
        type_combo.addItem("Validation (GVP)", True)
        type_combo.setCurrentIndex(1 if cp.is_validation else 0)
        type_combo.currentIndexChanged.connect(lambda: self.on_type_changed(row))
        self.points_table.setCellWidget(row, 1, type_combo)

        self.points_table.setItem(row, 2, QTableWidgetItem(f"{cp.pixel_x:.1f}"))
        self.points_table.setItem(row, 3, QTableWidgetItem(f"{cp.pixel_y:.1f}"))
        self.points_table.setItem(row, 4, QTableWidgetItem(f"{cp.longitude:.10f}"))
        self.points_table.setItem(row, 5, QTableWidgetItem(f"{cp.latitude:.10f}"))

    def on_type_changed(self, row: int):
        """Handle change in point type (GCP/GVP)."""
        if row < len(self.project.control_points):
            type_combo = self.points_table.cellWidget(row, 1)
            if type_combo:
                is_validation = type_combo.currentData()
                self.project.control_points[row].is_validation = is_validation
                self.update_validation()
                self.update_uncertainty_statistics()
                self.control_points_changed.emit()

    def on_table_item_changed(self, item: QTableWidgetItem):
        """Handle changes to table items (like editing name)."""
        # Currently we don't allow editing other fields, but could extend this
        pass

    def request_pick_point(self):
        """Request picking a point on the image."""
        self.pick_point_requested.emit()
        self.pick_point_btn.setText("Click on image...")
        self.pick_point_btn.setEnabled(False)

    def set_picked_point(self, x: float, y: float):
        """Set the picked point coordinates."""
        # If CSV placer dialog is active, route to it
        if self.csv_placer_dialog:
            self.csv_placer_dialog.set_picked_point(x, y)
            return

        # Otherwise, use normal workflow
        self.pending_pixel_coords = (x, y)
        self.picked_coords_label.setText(f"({x:.1f}, {y:.1f})")
        self.pick_point_btn.setText("Pick Point on Image")
        self.pick_point_btn.setEnabled(True)
        self.add_point_btn.setEnabled(True)

    def add_control_point(self):
        """Add a control point to the project."""
        if not self.pending_pixel_coords:
            show_warning(self, "Please pick a point on the image first.", "No Point Selected")
            return

        # Create control point
        cp = ControlPoint(
            pixel_x=self.pending_pixel_coords[0],
            pixel_y=self.pending_pixel_coords[1],
            longitude=self.longitude_spin.value(),
            latitude=self.latitude_spin.value(),
            name=f"CP{len(self.project.control_points) + 1}",
            is_validation=self.validation_check.isChecked()
        )

        # Add to project
        self.project.add_control_point(cp)

        # Add to table
        self.add_point_to_table(cp, len(self.project.control_points) - 1)

        # Reset form
        self.pending_pixel_coords = None
        self.picked_coords_label.setText("No point selected")
        self.add_point_btn.setEnabled(False)
        self.longitude_spin.setValue(0.0)
        self.latitude_spin.setValue(0.0)
        self.validation_check.setChecked(False)

        self.update_status()
        self.update_validation()
        self.update_uncertainty_statistics()

        # Emit signal to notify that control points changed
        self.control_points_changed.emit()

    def remove_selected_point(self):
        """Remove the selected control point."""
        current_row = self.points_table.currentRow()
        if current_row >= 0:
            # Remove from project
            self.project.remove_control_point(current_row)

            # Reload to update names and indices
            self.load_control_points()
            self.update_validation()
            self.update_uncertainty_statistics()

            # Emit signal to notify that control points changed
            self.control_points_changed.emit()

    def eventFilter(self, obj, event):
        """Event filter to auto-select text on focus and handle paste operations."""
        if event.type() == QEvent.Type.FocusIn:
            # When the line edit receives focus, select all text
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, obj.selectAll)

        elif event.type() == QEvent.Type.KeyPress:
            # Handle Ctrl+V for paste
            from PyQt6.QtGui import QKeySequence
            from PyQt6.QtWidgets import QApplication

            if event.matches(QKeySequence.StandardKey.Paste):
                # Get clipboard content
                clipboard = QApplication.clipboard()
                text = clipboard.text().strip()

                # Try to parse as a number (handle various formats)
                try:
                    # Remove common non-numeric characters
                    text = text.replace('°', '').replace(' ', '').replace(',', '.')
                    value = float(text)

                    # Determine which spinbox this is and set the value
                    if obj == self.longitude_spin.lineEdit():
                        # Clamp to valid range
                        value = max(-180.0, min(180.0, value))
                        self.longitude_spin.setValue(value)
                    elif obj == self.latitude_spin.lineEdit():
                        # Clamp to valid range
                        value = max(-90.0, min(90.0, value))
                        self.latitude_spin.setValue(value)

                    return True  # Event handled
                except (ValueError, AttributeError):
                    # If parsing fails, let the default handler try
                    pass

        return super().eventFilter(obj, event)

    def clear_all_points(self):
        """Clear all control points."""
        if ask_yes_no(self, "Are you sure you want to remove all control points?", "Clear All"):
            self.project.control_points.clear()
            self.load_control_points()
            self.update_validation()

            # Emit signal to notify that control points changed
            self.control_points_changed.emit()

    def update_status(self):
        """Update the status label."""
        # Count training vs validation points
        training_points = [cp for cp in self.project.control_points if not cp.is_validation]
        validation_points = [cp for cp in self.project.control_points if cp.is_validation]

        training_count = len(training_points)
        validation_count = len(validation_points)
        total_count = len(self.project.control_points)

        # Determine minimum required based on method
        min_required = 4 if self.project.transform_method == 'homography' else 3

        if training_count < min_required:
            self.status_label.setText(
                f"<b>Status:</b> {training_count} training (GCP), {validation_count} validation (GVP) points. "
                f"Need {min_required - training_count} more training points for {self.project.transform_method}."
            )
            self.status_label.setStyleSheet("color: orange;")
        else:
            self.status_label.setText(
                f"<b>Status:</b> {training_count} training (GCP), {validation_count} validation (GVP) points. "
                f"Georeferencing is ready!"
            )
            self.status_label.setStyleSheet("color: green;")

    def update_validation(self):
        """Compute and display validation results."""
        from orbit.utils import create_transformer, TransformMethod

        # Count training points
        training_points = [cp for cp in self.project.control_points if not cp.is_validation]
        validation_points = [cp for cp in self.project.control_points if cp.is_validation]

        # Determine minimum required
        min_required = 4 if self.project.transform_method == 'homography' else 3

        if len(training_points) < min_required:
            self.validation_text.setText("Insufficient training points for validation.")
            self.project.georef_validation = {}
            return

        # Create transformer
        method = TransformMethod.HOMOGRAPHY if self.project.transform_method == 'homography' else TransformMethod.AFFINE
        transformer = create_transformer(self.project.control_points, method, use_validation=True)

        if not transformer:
            self.validation_text.setText("Failed to create transformer.")
            self.project.georef_validation = {}
            return

        # Build validation report
        report = []
        report.append("=" * 60)
        report.append(f"GEOREFERENCING VALIDATION - {self.project.transform_method.upper()}")
        report.append("=" * 60)
        report.append("")

        # Reprojection error (GCPs)
        if transformer.reprojection_error:
            err = transformer.reprojection_error
            report.append("REPROJECTION ERROR (Training Points - GCPs):")
            report.append(f"  RMSE:       {err['rmse_pixels']:.2f} px  |  {err['rmse_meters']:.3f} m")
            report.append(f"  Mean Error: {err['mean_error_pixels']:.2f} px  |  {err['mean_error_meters']:.3f} m")
            report.append(f"  Max Error:  {err['max_error_pixels']:.2f} px  |  {err['max_error_meters']:.3f} m")
            report.append("")

            if err['per_point_errors']:
                report.append("  Per-point errors:")
                for pe in err['per_point_errors']:
                    report.append(f"    {pe['name']}: {pe['error_pixels']:.2f} px  |  {pe['error_meters']:.3f} m")
                report.append("")

        # Validation error (GVPs)
        if len(validation_points) > 0 and transformer.validation_error:
            err = transformer.validation_error
            report.append("VALIDATION ERROR (Validation Points - GVPs):")
            report.append(f"  RMSE:       {err['rmse_pixels']:.2f} px  |  {err['rmse_meters']:.3f} m")
            report.append(f"  Mean Error: {err['mean_error_pixels']:.2f} px  |  {err['mean_error_meters']:.3f} m")
            report.append(f"  Max Error:  {err['max_error_pixels']:.2f} px  |  {err['max_error_meters']:.3f} m")
            report.append("")

            if err['per_point_errors']:
                report.append("  Per-point errors:")
                for pe in err['per_point_errors']:
                    report.append(f"    {pe['name']}: {pe['error_pixels']:.2f} px  |  {pe['error_meters']:.3f} m")
                report.append("")
        elif len(validation_points) == 0:
            report.append("VALIDATION ERROR: No validation points defined.")
            report.append("  Tip: Mark some points as 'Validation (GVP)' to test accuracy.")
            report.append("")

        # Scale info
        scale_x, scale_y = transformer.get_scale_factor()
        report.append(f"SCALE FACTORS:")
        report.append(f"  X: {scale_x * 100:.2f} cm/px  |  Y: {scale_y * 100:.2f} cm/px")

        report.append("=" * 60)

        self.validation_text.setText("\n".join(report))

        # Store validation results in project
        self.project.georef_validation = {
            'transform_method': self.project.transform_method,
            'reprojection_error': transformer.reprojection_error if transformer.reprojection_error else {},
            'validation_error': transformer.validation_error if transformer.validation_error else {},
            'scale_factors': {'x': scale_x, 'y': scale_y},
            'num_training_points': len(training_points),
            'num_validation_points': len(validation_points)
        }

    def import_from_csv(self):
        """Open CSV import dialog."""
        from .csv_import_dialog import CSVImportDialog

        # Open CSV import dialog
        csv_dialog = CSVImportDialog(self.project, self)

        # Connect to completion signals
        csv_dialog.accepted.connect(lambda: self.on_csv_import_complete(csv_dialog))
        csv_dialog.rejected.connect(self.on_csv_import_cancelled)

        # Show non-modally to allow point picking
        csv_dialog.show()

    def on_csv_import_complete(self, csv_dialog):
        """Handle completion of CSV import dialog."""
        # Points were imported, reload table
        self.load_control_points()
        self.update_status()
        self.update_validation()

        # Emit signal to notify that control points changed
        self.control_points_changed.emit()

        # Clear placer dialog reference when done
        self.csv_placer_dialog = None

    def on_csv_import_cancelled(self):
        """Handle cancellation of CSV import dialog."""
        # Clear placer dialog reference when cancelled
        self.csv_placer_dialog = None

    def update_uncertainty_statistics(self):
        """Display uncertainty statistics based on current control points."""
        training_points = [cp for cp in self.project.control_points if not cp.is_validation]
        min_required = 4 if self.project.transform_method == 'homography' else 3

        if len(training_points) < min_required:
            self.uncertainty_text.setPlainText(
                f"Add at least {min_required} training points (GCPs) to see uncertainty analysis."
            )
            self.analyze_uncertainty_btn.setEnabled(False)
            self.compute_monte_carlo_btn.setEnabled(False)
            return

        # Enable analysis buttons
        self.analyze_uncertainty_btn.setEnabled(True)
        self.compute_monte_carlo_btn.setEnabled(True)

        try:
            from orbit.utils import create_transformer, TransformMethod
            from orbit.utils.uncertainty_estimator import UncertaintyEstimator

            # Get image dimensions
            parent_window = self.parent()
            if not hasattr(parent_window, 'image_view') or not parent_window.image_view.image_item:
                self.uncertainty_text.setPlainText("Load an image to see uncertainty analysis.")
                return

            pixmap = parent_window.image_view.image_item.pixmap()
            image_width = pixmap.width()
            image_height = pixmap.height()

            # Create transformer
            method = TransformMethod.HOMOGRAPHY if self.project.transform_method == 'homography' else TransformMethod.AFFINE
            transformer = create_transformer(self.project.control_points, method, use_validation=True)

            if not transformer:
                self.uncertainty_text.setPlainText("Failed to create transformation.")
                return

            # Create uncertainty estimator
            estimator = UncertaintyEstimator(transformer, image_width, image_height,
                                            baseline_uncertainty=self.project.baseline_uncertainty_m)

            # Build report
            report = []

            # Check if cache exists
            if not self.project.uncertainty_grid_cache:
                # No cache - show message only
                report.append("Status: No Monte Carlo cache")
                report.append("")
                report.append("Click 'Compute Uncertainty (Monte Carlo)' to:")
                report.append("  • Run 200 iterations with ±1.5px measurement error")
                report.append("  • Generate uncertainty estimates across the image")
                report.append("  • Cache results for fast queries")
                report.append("")
                report.append("This will take 10-30 seconds depending on image size.")
                self.uncertainty_text.setPlainText("\n".join(report))
                self.suggest_gcp_btn.setEnabled(False)  # Disable until analysis run
                return

            # Load cached grid
            estimator._cached_grid = np.array(self.project.uncertainty_grid_cache)
            self.suggest_gcp_btn.setEnabled(True)  # Enable suggestions with cache

            # Get statistics from cache
            stats = estimator.get_uncertainty_statistics()

            # Cache status
            report.append("Status: Monte Carlo cache available ✓")
            if self.project.uncertainty_last_computed:
                from datetime import datetime
                try:
                    computed = datetime.fromisoformat(self.project.uncertainty_last_computed)
                    report.append(f"Computed: {computed.strftime('%Y-%m-%d %H:%M')}")
                except (ValueError, TypeError) as e:
                    logger.debug(f"Failed to parse uncertainty timestamp: {e}")
            report.append("")

            report.append("Position Uncertainty:")
            report.append(f"  Mean: {stats['mean']:.2f} m")
            report.append(f"  Median: {stats['median']:.2f} m")
            report.append(f"  Maximum: {stats['max']:.2f} m")
            report.append(f"  90th percentile: {stats['p90']:.2f} m")
            report.append("")
            report.append("Coverage:")
            report.append(f"  {stats['coverage'][0.1]*100:.0f}% of image within 0.1m (excellent)")
            report.append(f"  {stats['coverage'][0.2]*100:.0f}% of image within 0.2m (good)")
            report.append(f"  {stats['coverage'][0.4]*100:.0f}% of image within 0.4m (acceptable)")

            # Add calibration quality if validation points exist
            validation_points = [cp for cp in self.project.control_points if cp.is_validation]
            if len(validation_points) >= 2:
                cal_quality = estimator.calibrate_from_validation_points()
                report.append("")
                report.append(f"Model calibration quality: {cal_quality:.2f} (based on {len(validation_points)} GVPs)")

            self.uncertainty_text.setPlainText("\n".join(report))

        except Exception as e:
            self.uncertainty_text.setPlainText(f"Error computing uncertainty: {str(e)}")

    def run_bootstrap_analysis(self):
        """Run detailed bootstrap uncertainty analysis in background."""
        training_points = [cp for cp in self.project.control_points if not cp.is_validation]
        min_required = 4 if self.project.transform_method == 'homography' else 3

        if len(training_points) < min_required:
            show_warning(self, f"Need at least {min_required} training points (GCPs) for bootstrap analysis.", "Not Enough Points")
            return

        try:
            from orbit.utils import create_transformer, TransformMethod
            from orbit.utils.uncertainty_estimator import UncertaintyEstimator

            # Get image dimensions
            parent_window = self.parent()
            if not hasattr(parent_window, 'image_view') or not parent_window.image_view.image_item:
                show_warning(self, "Load an image first.", "No Image")
                return

            pixmap = parent_window.image_view.image_item.pixmap()
            image_width = pixmap.width()
            image_height = pixmap.height()

            # Create transformer
            method = TransformMethod.HOMOGRAPHY if self.project.transform_method == 'homography' else TransformMethod.AFFINE
            transformer = create_transformer(self.project.control_points, method, use_validation=True)

            if not transformer:
                show_warning(self, "Failed to create transformation.", "Transform Error")
                return

            # Create estimator
            estimator = UncertaintyEstimator(transformer, image_width, image_height,
                                            baseline_uncertainty=self.project.baseline_uncertainty_m)

            # Show progress bar
            self.analysis_progress.show()
            self.analysis_progress.setValue(0)
            self.analyze_uncertainty_btn.setEnabled(False)
            self.compute_monte_carlo_btn.setEnabled(False)

            # Progress callback
            def progress_callback(percent):
                self.analysis_progress.setValue(percent)
                QApplication.processEvents()  # Allow UI to update

            # Run bootstrap analysis (200 iterations)
            detailed_grid = estimator.run_bootstrap_analysis(
                n_iterations=200,
                progress_callback=progress_callback
            )

            # Store in project
            self.project.uncertainty_bootstrap_grid = detailed_grid.tolist()

            # Update overlay if active
            if hasattr(parent_window, 'uncertainty_overlay') and parent_window.image_view.uncertainty_overlay:
                # Recreate overlay with updated data
                parent_window.set_uncertainty_overlay('position')

            # Hide progress and re-enable buttons
            self.analysis_progress.hide()
            self.analyze_uncertainty_btn.setEnabled(True)
            self.compute_monte_carlo_btn.setEnabled(True)
            self.suggest_gcp_btn.setEnabled(True)  # Enable suggestions after analysis

            # Show completion message
            stats = estimator.get_uncertainty_statistics()
            show_info(self, f"Bootstrap analysis complete (200 iterations).\n\n"
                f"Mean uncertainty: {stats['mean']:.2f}m\n"
                f"Maximum: {stats['max']:.2f}m\n"
                f"Coverage: {stats['coverage'][0.2]*100:.0f}% within 0.2m", "Analysis Complete")

        except Exception as e:
            self.analysis_progress.hide()
            self.analyze_uncertainty_btn.setEnabled(True)
            self.compute_monte_carlo_btn.setEnabled(True)
            show_error(self, f"Bootstrap analysis failed: {str(e)}", "Error")

    def run_monte_carlo_analysis(self):
        """Run Monte Carlo uncertainty analysis with measurement error."""
        training_points = [cp for cp in self.project.control_points if not cp.is_validation]
        min_required = 4 if self.project.transform_method == 'homography' else 3

        if len(training_points) < min_required:
            show_warning(self, f"Need at least {min_required} training points (GCPs) for Monte Carlo analysis.", "Not Enough Points")
            return

        try:
            from orbit.utils import create_transformer, TransformMethod
            from orbit.utils.uncertainty_estimator import UncertaintyEstimator

            # Get image dimensions
            parent_window = self.parent()
            if not hasattr(parent_window, 'image_view') or not parent_window.image_view.image_item:
                show_warning(self, "Load an image first.", "No Image")
                return

            pixmap = parent_window.image_view.image_item.pixmap()
            image_width = pixmap.width()
            image_height = pixmap.height()

            # Create transformer
            method = TransformMethod.HOMOGRAPHY if self.project.transform_method == 'homography' else TransformMethod.AFFINE
            transformer = create_transformer(self.project.control_points, method, use_validation=True)

            if not transformer:
                show_warning(self, "Failed to create transformation.", "Transform Error")
                return

            # Create estimator
            estimator = UncertaintyEstimator(transformer, image_width, image_height,
                                            baseline_uncertainty=self.project.baseline_uncertainty_m)

            # Show progress bar
            self.analysis_progress.show()
            self.analysis_progress.setValue(0)
            self.analyze_uncertainty_btn.setEnabled(False)
            self.compute_monte_carlo_btn.setEnabled(False)

            # Progress callback
            def progress_callback(percent):
                self.analysis_progress.setValue(percent)
                QApplication.processEvents()  # Allow UI to update

            # Run Monte Carlo analysis with configured parameters
            sigma_pixels = self.project.mc_sigma_pixels
            uncertainty_grid = estimator.compute_uncertainty_monte_carlo(
                n_iterations=200,
                sigma_pixels=sigma_pixels,
                resolution=(50, 50),
                progress_callback=progress_callback
            )

            # Store in project cache
            self.project.uncertainty_grid_cache = uncertainty_grid.tolist()
            self.project.uncertainty_grid_resolution = (50, 50)
            from datetime import datetime
            self.project.uncertainty_last_computed = datetime.now().isoformat()

            # Update statistics display
            self.update_uncertainty_statistics()

            # Update overlay if active
            if hasattr(parent_window, 'image_view') and parent_window.image_view.uncertainty_overlay:
                # Recreate overlay with updated data
                parent_window.set_uncertainty_overlay('position')

            # Hide progress and re-enable buttons
            self.analysis_progress.hide()
            self.analyze_uncertainty_btn.setEnabled(True)
            self.compute_monte_carlo_btn.setEnabled(True)
            self.suggest_gcp_btn.setEnabled(True)  # Enable suggestions after analysis

            # Show completion message
            stats = estimator.get_uncertainty_statistics()
            show_info(self, f"Monte Carlo analysis complete (200 iterations, σ={sigma_pixels:.1f} px).\n\n"
                f"Mean uncertainty: {stats['mean']:.2f}m\n"
                f"Maximum: {stats['max']:.2f}m\n"
                f"Coverage: {stats['coverage'][0.2]*100:.0f}% within 0.2m\n\n"
                f"Results cached for fast queries.", "Analysis Complete")

        except Exception as e:
            self.analysis_progress.hide()
            self.analyze_uncertainty_btn.setEnabled(True)
            self.compute_monte_carlo_btn.setEnabled(True)
            show_error(self, f"Monte Carlo analysis failed: {str(e)}", "Error")

    def on_parameter_changed(self):
        """Handle parameter changes - save to project and invalidate cache."""
        self.project.mc_sigma_pixels = self.sigma_pixels_spin.value()
        self.project.baseline_uncertainty_m = self.baseline_uncertainty_spin.value()
        self.project.gcp_suggestion_threshold = self.gcp_threshold_spin.value()

        # Invalidate cache if MC parameters changed
        # User will need to recompute Monte Carlo with new parameters
        if self.project.uncertainty_grid_cache:
            self.project.invalidate_uncertainty_cache()
            # Update statistics to show cache is invalidated
            self.update_uncertainty_statistics()

    def suggest_gcp_locations(self):
        """Suggest where to add new control points based on uncertainty analysis."""
        try:
            from orbit.utils import create_transformer, TransformMethod
            from orbit.utils.uncertainty_estimator import UncertaintyEstimator

            # Get image dimensions
            parent_window = self.parent()
            if not hasattr(parent_window, 'image_view') or not parent_window.image_view.image_item:
                show_warning(self, "Load an image first.", "No Image")
                return

            pixmap = parent_window.image_view.image_item.pixmap()
            image_width = pixmap.width()
            image_height = pixmap.height()

            # Create transformer
            method = TransformMethod.HOMOGRAPHY if self.project.transform_method == 'homography' else TransformMethod.AFFINE
            transformer = create_transformer(self.project.control_points, method, use_validation=True)

            if not transformer:
                show_warning(self, "Failed to create transformation.", "Transform Error")
                return

            # Create estimator
            estimator = UncertaintyEstimator(transformer, image_width, image_height,
                                            baseline_uncertainty=self.project.baseline_uncertainty_m)

            # Load cached grid if available
            if self.project.uncertainty_grid_cache:
                import numpy as np
                estimator._cached_grid = np.array(self.project.uncertainty_grid_cache)
                if self.verbose:
                    print(f"[DEBUG] Loaded cached grid shape: {estimator._cached_grid.shape}")
                    print(f"[DEBUG] Cached grid min/max: {np.min(estimator._cached_grid):.3f} / {np.max(estimator._cached_grid):.3f}m")
            else:
                show_warning(self, "Run Monte Carlo or Bootstrap analysis first to generate uncertainty estimates.", "No Uncertainty Data")
                return

            # Find suggestions using configured threshold
            threshold = self.project.gcp_suggestion_threshold

            # Debug: Check what's in the grid
            if self.verbose:
                stats = estimator.get_uncertainty_statistics()
                print(f"[DEBUG] Grid stats - Mean: {stats['mean']:.3f}m, Max: {stats['max']:.3f}m, Min: {stats.get('min', 'N/A')}")
                print(f"[DEBUG] Threshold: {threshold:.3f}m")

            suggestions = estimator.find_high_uncertainty_regions(threshold=threshold, verbose=self.verbose)

            if self.verbose:
                print(f"[DEBUG] Found {len(suggestions)} suggestions")

            if not suggestions:
                show_info(self, f"No high-uncertainty areas found above threshold ({threshold:.2f}m)!\n\n"
                    "Your current control point distribution provides good coverage.\n\n"
                    "To find more suggestions, lower the 'GCP suggestion threshold' parameter above.", "No Suggestions")
                return

            # Build message with suggestions
            stats = estimator.get_uncertainty_statistics()
            message = (
                f"Found {len(suggestions)} high-uncertainty area(s) where adding control points would help:\n"
                f"(Using threshold: {threshold:.2f}m)\n\n"
            )

            for i, (x, y) in enumerate(suggestions, 1):
                # Get uncertainty at this point
                unc = estimator.estimate_position_uncertainty_at_point(x, y)
                message += f"{i}. Pixel ({x:.0f}, {y:.0f}) - Uncertainty: {unc:.2f}m\n"

            message += (
                f"\n"
                f"Current mean uncertainty: {stats['mean']:.2f}m\n"
                f"Current max uncertainty: {stats['max']:.2f}m\n\n"
                f"Recommended action:\n"
                f"1. Enable uncertainty overlay (View → Uncertainty Overlay → Position)\n"
                f"2. Locate the suggested pixel coordinates (shown in red/orange)\n"
                f"3. Add new control points at or near these locations\n"
                f"4. Recompute uncertainty analysis to verify improvement"
            )

            show_info(self, message, "GCP Location Suggestions")

        except Exception as e:
            show_error(self, f"Failed to suggest GCP locations: {str(e)}", "Error")

    def accept(self):
        """Handle dialog acceptance."""
        # Check minimum training points
        training_points = [cp for cp in self.project.control_points if not cp.is_validation]
        min_required = 4 if self.project.transform_method == 'homography' else 3

        if len(training_points) < min_required:
            if not ask_yes_no(
                self,
                f"You have {len(training_points)} training points but {self.project.transform_method} "
                f"requires at least {min_required}.\n\n"
                "Change some validation points to training, or add more points.\n\n"
                "Do you want to close anyway?",
                "Insufficient Training Points"
            ):
                return

        super().accept()

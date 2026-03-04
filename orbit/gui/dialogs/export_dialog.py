"""
Export preview dialog for ORBIT.

Shows transformation information and export options before generating OpenDrive.
"""

from pathlib import Path
from typing import Optional

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from orbit.export import CoordinateTransformer, create_transformer, export_to_opendrive, validate_opendrive_file
from orbit.export.reference_validator import validate_references
from orbit.models import Project
from orbit.models.object import ObjectType
from orbit.utils.enum_formatting import format_enum_name
from orbit.utils.logging_config import get_logger

from ..utils.message_helpers import show_error, show_info, show_warning
from .base_dialog import BaseDialog

logger = get_logger(__name__)


class ExportDialog(BaseDialog):
    """Dialog for OpenDrive export with preview."""

    def __init__(self, project: Project, parent=None, xodr_schema_path: Optional[str] = None):
        super().__init__("Export to OpenDrive", parent, min_width=700, min_height=600)

        self.project = project
        self.transformer: Optional[CoordinateTransformer] = None
        self.output_path: Optional[Path] = None
        self.xodr_schema_path = xodr_schema_path  # Path to XSD schema for validation (optional)

        self.setup_ui()
        self.load_properties()
        self.analyze_project()

    def setup_ui(self):
        """Setup the dialog UI."""
        # Project summary
        summary_layout = self.add_form_group("Project Summary")

        self.polylines_label = QLabel()
        summary_layout.addRow("Polylines:", self.polylines_label)

        self.roads_label = QLabel()
        summary_layout.addRow("Roads:", self.roads_label)

        self.junctions_label = QLabel()
        summary_layout.addRow("Junctions:", self.junctions_label)

        self.control_points_label = QLabel()
        summary_layout.addRow("Control Points:", self.control_points_label)

        # Georeferencing status (custom group with VBoxLayout)
        georef_group = QGroupBox("Georeferencing Status")
        georef_layout = QVBoxLayout()

        self.georef_status_label = QLabel()
        self.georef_status_label.setWordWrap(True)
        georef_layout.addWidget(self.georef_status_label)

        # Transformation info text
        self.transform_info = QTextEdit()
        self.transform_info.setReadOnly(True)
        self.transform_info.setMaximumHeight(150)
        font = QFont("Courier")
        font.setPointSize(9)
        self.transform_info.setFont(font)
        georef_layout.addWidget(self.transform_info)

        georef_group.setLayout(georef_layout)
        self.get_main_layout().addWidget(georef_group)

        # Export options
        options_layout = self.add_form_group("Export Options")

        self.line_tolerance_spin = QDoubleSpinBox()
        self.line_tolerance_spin.setRange(0.01, 10.0)
        self.line_tolerance_spin.setValue(0.05)
        self.line_tolerance_spin.setSingleStep(0.01)
        self.line_tolerance_spin.setSuffix(" m")
        self.line_tolerance_spin.setToolTip("Maximum deviation for line fitting")
        options_layout.addRow("Line Tolerance:", self.line_tolerance_spin)

        self.arc_tolerance_spin = QDoubleSpinBox()
        self.arc_tolerance_spin.setRange(0.01, 10.0)
        self.arc_tolerance_spin.setValue(0.1)
        self.arc_tolerance_spin.setSingleStep(0.01)
        self.arc_tolerance_spin.setSuffix(" m")
        self.arc_tolerance_spin.setToolTip("Maximum deviation for arc fitting")
        options_layout.addRow("Arc Tolerance:", self.arc_tolerance_spin)

        # Preserve geometry checkbox
        self.preserve_geometry_checkbox = QCheckBox("Preserve all polyline points")
        self.preserve_geometry_checkbox.setChecked(True)
        self.preserve_geometry_checkbox.setToolTip(
            "If checked, creates one line segment per polyline point, preserving exact geometry.\n"
            "If unchecked, uses curve fitting to simplify the geometry (tolerances above apply)."
        )
        # Enable/disable tolerance inputs based on preserve geometry
        self.preserve_geometry_checkbox.stateChanged.connect(self.on_preserve_geometry_changed)
        options_layout.addRow("Geometry:", self.preserve_geometry_checkbox)

        # Projection type dropdown (UTM, Transverse Mercator, Preserved)
        self.projection_combo = QComboBox()
        self.projection_combo.addItem("UTM", "utm")
        self.projection_combo.addItem("Transverse Mercator", "tmerc")
        if self.project.imported_geo_reference:
            self.projection_combo.addItem("Preserved from import", "preserved")
        self.projection_combo.setToolTip(
            "UTM: Standard projection with automatically calculated zone.\n"
            "Transverse Mercator: Local projection centered on control points.\n"
            "Preserved from import: Use the geoReference from the imported OpenDRIVE file."
        )
        options_layout.addRow("Projection:", self.projection_combo)

        # Origin point selection for coordinate offset
        self.origin_combo = QComboBox()
        self.origin_combo.addItem("Mean of control points", "mean")
        for i, cp in enumerate(self.project.control_points):
            label = cp.name if cp.name else f"CP {i+1}"
            label += f" ({cp.latitude:.6f}, {cp.longitude:.6f})"
            self.origin_combo.addItem(label, i)
        self.origin_combo.setToolTip(
            "Select the origin point for the local coordinate system.\n"
            "The projected coordinates of this point become the offset,\n"
            "producing small local coordinates in the exported file."
        )
        self.origin_combo.addItem("Custom coordinates", "custom")
        options_layout.addRow("Origin Point:", self.origin_combo)

        # Custom origin lat/lon spinboxes (always visible, enabled only when "Custom" is selected)
        self.origin_lat_spin = QDoubleSpinBox()
        self.origin_lat_spin.setRange(-90.0, 90.0)
        self.origin_lat_spin.setDecimals(8)
        self.origin_lat_spin.setSingleStep(0.0001)
        self.origin_lat_spin.setToolTip("Latitude of the custom origin point (−90 to 90).")
        options_layout.addRow("Origin Latitude:", self.origin_lat_spin)

        self.origin_lon_spin = QDoubleSpinBox()
        self.origin_lon_spin.setRange(-180.0, 180.0)
        self.origin_lon_spin.setDecimals(8)
        self.origin_lon_spin.setSingleStep(0.0001)
        self.origin_lon_spin.setToolTip("Longitude of the custom origin point (−180 to 180).")
        options_layout.addRow("Origin Longitude:", self.origin_lon_spin)

        # Pre-fill custom fields from imported origin if available, and default to it
        if self.project.imported_origin_latitude is not None:
            self.origin_lat_spin.setValue(self.project.imported_origin_latitude)
            self.origin_lon_spin.setValue(self.project.imported_origin_longitude)
            # Default the combo to "Custom coordinates" (last item added)
            self.origin_combo.setCurrentIndex(self.origin_combo.count() - 1)

        self.origin_combo.currentIndexChanged.connect(self._on_origin_changed)
        self._on_origin_changed()  # set initial enabled state

        # German codes checkbox
        self.use_german_codes_checkbox = QCheckBox("Use German (DE) equivalent codes for signals")
        self.use_german_codes_checkbox.setChecked(False)
        self.use_german_codes_checkbox.setToolTip(
            "If checked, signals will use German VzKat codes (opendrive_de) when available,\n"
            "with country='DE' on the signal element.\n"
            "If unchecked (default), signals use the country-specific codes from the sign library."
        )
        options_layout.addRow("Signal Codes:", self.use_german_codes_checkbox)

        # Feature categories (only shown if project has non-road objects)
        self.feature_checkboxes: dict[ObjectType, QCheckBox] = {}
        self._setup_feature_categories()

        # Output file selection
        output_layout = QHBoxLayout()
        self.output_path_edit = QLineEdit()
        self.output_path_edit.setPlaceholderText("Select output file...")
        output_layout.addWidget(self.output_path_edit)

        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self.browse_output_file)
        output_layout.addWidget(self.browse_btn)

        options_layout.addRow("Output File:", output_layout)

        # Initialize tolerance enabled state
        self.on_preserve_geometry_changed()

        # Status message
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.get_main_layout().addWidget(self.status_label)

        # Custom button box (Export/Cancel instead of OK/Cancel)
        button_box = QDialogButtonBox()

        self.export_btn = QPushButton("Export")
        self.export_btn.clicked.connect(self.do_export)
        button_box.addButton(self.export_btn, QDialogButtonBox.ButtonRole.AcceptRole)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_box.addButton(cancel_btn, QDialogButtonBox.ButtonRole.RejectRole)

        self.get_main_layout().addWidget(button_box)

    def load_properties(self):
        """Load project data (no-op for export dialog)."""
        # Export dialog doesn't load properties from the project
        # Data is populated by analyze_project() instead
        pass

    def analyze_project(self):
        """Analyze the project and display information."""
        # Count elements
        num_polylines = len(self.project.polylines)
        num_roads = len(self.project.roads)
        num_junctions = len(self.project.junctions)
        num_control_points = len(self.project.control_points)

        self.polylines_label.setText(str(num_polylines))
        self.roads_label.setText(str(num_roads))
        self.junctions_label.setText(str(num_junctions))
        self.control_points_label.setText(str(num_control_points))

        # Check georeferencing
        if self.project.has_georeferencing():
            # Create transformer using project's method
            self.transformer = create_transformer(
                self.project.control_points,
                self.project.transform_method,
                use_validation=True,
            )

            if self.transformer:
                method = self.project.transform_method.upper()
                self.georef_status_label.setText(
                    f"<b style='color: green;'>"
                    f"✓ Georeferencing Active ({method})"
                    f"</b><br>"
                    "Project has sufficient control points "
                    "for coordinate transformation."
                )
                self.georef_status_label.setStyleSheet("color: green;")

                # Display transformation info
                info = self.transformer.get_transformation_info()
                info_text = (
                    f"Method: {info['method']}\n"
                    f"Training Points (GCP): {info['num_training_points']}\n"
                    f"Validation Points (GVP): {info['num_validation_points']}\n"
                    f"Mean Latitude: {info['reference_latitude']:.6f}°\n"
                    f"Scale X: {info['scale_x_meters_per_pixel']:.4f} m/pixel\n"
                    f"Scale Y: {info['scale_y_meters_per_pixel']:.4f} m/pixel\n"
                )

                # Add reprojection error if available
                if 'reprojection_error' in info and info['reprojection_error']:
                    err = info['reprojection_error']
                    info_text += f"\nReprojection RMSE: {err['rmse_pixels']:.2f} px ({err['rmse_meters']:.3f} m)"

                # Add validation error if available
                if 'validation_error' in info and info['validation_error']:
                    err = info['validation_error']
                    info_text += f"\nValidation RMSE: {err['rmse_pixels']:.2f} px ({err['rmse_meters']:.3f} m)"

                self.transform_info.setText(info_text)

                self.export_btn.setEnabled(True)
                self.status_label.setText(
                    "<b>Ready to export.</b> Select output file and click Export."
                )
            else:
                self.georef_status_label.setText(
                    "<b style='color: red;'>✗ Georeferencing Error</b><br>"
                    "Failed to create coordinate transformation. Check control points."
                )
                self.georef_status_label.setStyleSheet("color: red;")
                self.export_btn.setEnabled(False)
                self.status_label.setText(
                    "<b style='color: red;'>Cannot export: Georeferencing error</b>"
                )
        else:
            self.georef_status_label.setText(
                f"<b style='color: orange;'>⚠ No Georeferencing</b><br>"
                f"Need at least {3 - num_control_points} more control points.<br>"
                f"Go to Tools → Georeferencing to add control points."
            )
            self.georef_status_label.setStyleSheet("color: orange;")
            self.transform_info.setText("Georeferencing not configured.")
            self.export_btn.setEnabled(False)
            self.status_label.setText(
                "<b style='color: orange;'>Cannot export: Georeferencing required</b>"
            )

    def _setup_feature_categories(self):
        """Add checkboxes for each object type present in the project."""
        # Count objects per type
        type_counts: dict[ObjectType, int] = {}
        for obj in self.project.objects:
            type_counts[obj.type] = type_counts.get(obj.type, 0) + 1

        if not type_counts:
            return

        from PyQt6.QtWidgets import QGridLayout
        feature_group = QGroupBox("Feature Categories")
        feature_layout = QGridLayout()

        row, col = 0, 0
        for obj_type in ObjectType:
            count = type_counts.get(obj_type)
            if not count:
                continue
            label = f"{format_enum_name(obj_type)} ({count})"
            cb = QCheckBox(label)
            cb.setChecked(True)
            self.feature_checkboxes[obj_type] = cb
            feature_layout.addWidget(cb, row, col)
            col += 1
            if col >= 3:
                col = 0
                row += 1

        feature_group.setLayout(feature_layout)
        self.get_main_layout().addWidget(feature_group)

    def _get_export_object_types(self) -> set | None:
        """Get the set of checked object types, or None if all are checked."""
        if not self.feature_checkboxes:
            return None
        checked = {ot for ot, cb in self.feature_checkboxes.items() if cb.isChecked()}
        # If all are checked, return None (export everything)
        if len(checked) == len(self.feature_checkboxes):
            return None
        return checked

    def on_preserve_geometry_changed(self):
        """Handle preserve geometry checkbox change."""
        preserve = self.preserve_geometry_checkbox.isChecked()
        # Disable tolerance inputs when preserving geometry
        self.line_tolerance_spin.setEnabled(not preserve)
        self.arc_tolerance_spin.setEnabled(not preserve)

    def _on_origin_changed(self):
        """Enable/disable the custom lat/lon spinboxes based on origin selection."""
        is_custom = self.origin_combo.currentData() == "custom"
        self.origin_lat_spin.setEnabled(is_custom)
        self.origin_lon_spin.setEnabled(is_custom)

    def browse_output_file(self):
        """Browse for output file location."""
        start_dir = getattr(self.parent(), '_last_file_directory', str(Path.home()))
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export to OpenDrive",
            start_dir,
            "OpenDrive Files (*.xodr);;All Files (*)"
        )

        if file_path:
            if hasattr(self.parent(), '_remember_directory'):
                self.parent()._remember_directory(file_path)
            self.output_path = Path(file_path)
            # Ensure .xodr extension
            if self.output_path.suffix != '.xodr':
                self.output_path = self.output_path.with_suffix('.xodr')

            self.output_path_edit.setText(str(self.output_path))

    def do_export(self):
        """Perform the export."""
        if not self.output_path:
            show_warning(self, "Please select an output file location.", "No Output File")
            return

        if not self.transformer:
            show_error(self, "Georeferencing is not properly configured.", "Export Error")
            return

        # Validate that all roads have centerlines
        roads_without_centerline = []
        for road in self.project.roads:
            if not road.has_centerline():
                roads_without_centerline.append(road.name)

        if roads_without_centerline:
            road_list = "\n• ".join(roads_without_centerline)
            show_error(
                self,
                f"The following roads do not have a road reference "
                f"line assigned:\n\n• {road_list}\n\n"
                "Every road must have exactly one road reference "
                "line for OpenDRIVE export.\n\n"
                "Please edit each road's properties to select a "
                "road reference line, or\n"
                "mark one of the road's polylines as a road "
                "reference line (double-click the polyline).",
                "Invalid Road Configuration",
            )
            return

        # Show progress message
        self.status_label.setText("<b>Exporting...</b>")
        self.export_btn.setEnabled(False)

        try:
            # Perform export using country code and traffic direction from preferences
            country_code = self.project.country_code.strip().lower()
            if not country_code:
                country_code = "se"  # Default to Sweden

            # Determine projection type from dropdown
            projection_type = self.projection_combo.currentData()
            use_tmerc = (projection_type == "tmerc")

            if projection_type == "preserved":
                proj_string = self.project.imported_geo_reference
            elif use_tmerc:
                proj_string = self.transformer.get_projection_string()
            else:
                proj_string = self.transformer.get_utm_projection_string()

            # Create a fresh transformer that uses pyproj for the export
            # projection. This ensures the homography/affine matrix is
            # computed in the same coordinate system written to the file.
            export_transformer = create_transformer(
                self.project.control_points,
                self.project.transform_method,
                use_validation=True,
                export_proj_string=proj_string
            )
            if not export_transformer:
                show_error(self, "Failed to create export transformer.", "Export Error")
                self.export_btn.setEnabled(True)
                self.status_label.setText("<b>Export failed.</b>")
                return

            # Compute origin offset: project the selected origin lat/lon
            # to get the offset that will be subtracted from all coordinates.
            origin_selection = self.origin_combo.currentData()
            if origin_selection == "mean":
                origin_lat = sum(cp.latitude for cp in self.project.control_points) / len(self.project.control_points)
                origin_lon = sum(cp.longitude for cp in self.project.control_points) / len(self.project.control_points)
            elif origin_selection == "custom":
                origin_lat = self.origin_lat_spin.value()
                origin_lon = self.origin_lon_spin.value()
            else:
                cp = self.project.control_points[origin_selection]
                origin_lat = cp.latitude
                origin_lon = cp.longitude

            # Project origin through pyproj to get metric offset
            from pyproj import Proj
            proj = Proj(proj_string)
            offset_x, offset_y = proj(origin_lon, origin_lat)

            # Build geo_reference_string for the XML header.
            # For UTM, append informational lat_0/lon_0 so tools can identify
            # the origin. For TMERC, the proj string already has lat_0/lon_0.
            # For preserved, use the imported string as-is.
            if projection_type == "preserved":
                geo_reference_string = self.project.imported_geo_reference
            elif projection_type == "utm":
                geo_reference_string = (
                    f"{proj_string} +lat_0={origin_lat:.8f} +lon_0={origin_lon:.8f}"
                )
            else:
                geo_reference_string = proj_string

            success = export_to_opendrive(
                self.project,
                export_transformer,
                str(self.output_path),
                line_tolerance=self.line_tolerance_spin.value(),
                arc_tolerance=self.arc_tolerance_spin.value(),
                preserve_geometry=self.preserve_geometry_checkbox.isChecked(),
                right_hand_traffic=self.project.right_hand_traffic,
                country_code=country_code,
                use_tmerc=use_tmerc,
                use_german_codes=self.use_german_codes_checkbox.isChecked(),
                offset_x=offset_x,
                offset_y=offset_y,
                geo_reference_string=geo_reference_string,
                export_object_types=self._get_export_object_types()
            )

            if success:
                # Check for dangling references
                ref_warnings = validate_references(self.project)
                ref_msg = ""
                if ref_warnings:
                    logger.warning("Reference Validation Warnings (%d):", len(ref_warnings))
                    for w in ref_warnings:
                        logger.warning("  %s", w)
                    ref_text = "\n".join(ref_warnings[:10])
                    if len(ref_warnings) > 10:
                        ref_text += f"\n... and {len(ref_warnings) - 10} more"
                    show_warning(
                        self,
                        f"Dangling references detected:\n\n{ref_text}",
                        "Reference Warnings"
                    )
                    ref_msg = f"\n\nReference check: {len(ref_warnings)} warning(s)"
                else:
                    ref_msg = "\n\nReference check: Passed"

                # Validate against schema if path was provided
                validation_msg = ""
                if self.xodr_schema_path:
                    validation_errors = validate_opendrive_file(str(self.output_path), self.xodr_schema_path)
                    if validation_errors is None:
                        validation_msg = "\n\nSchema validation: Skipped (no schema)"
                    elif validation_errors:
                        # Log all errors
                        logger.warning("OpenDRIVE Schema Validation Errors (%d):", len(validation_errors))
                        for err in validation_errors:
                            logger.warning("  %s", err)

                        # Show validation errors in dialog but don't fail the export
                        error_text = "\n".join(validation_errors[:10])  # Show first 10 errors
                        if len(validation_errors) > 10:
                            error_text += f"\n... and {len(validation_errors) - 10} more errors"
                        show_warning(self, f"OpenDrive file exported but has schema validation errors:\n\n{error_text}",
                                   "Validation Warnings")
                        validation_msg = f"\n\nSchema validation: {len(validation_errors)} error(s)"
                    else:
                        logger.info("OpenDRIVE schema validation: Passed")
                        validation_msg = "\n\nSchema validation: Passed"
                else:
                    validation_msg = "\n\nSchema validation: Skipped (use --xodr_schema to enable)"

                show_info(self, f"OpenDrive file exported successfully to:\n{self.output_path}\n\n"
                    f"Roads: {len(self.project.roads)}\n"
                    f"Junctions: {len(self.project.junctions)}{ref_msg}{validation_msg}", "Export Successful")
                self.accept()
            else:
                show_error(self, "Failed to export OpenDrive file. Check console for errors.", "Export Failed")
                self.status_label.setText("<b style='color: red;'>Export failed</b>")
                self.export_btn.setEnabled(True)

        except Exception as e:
            show_error(self, f"An error occurred during export:\n{str(e)}", "Export Error")
            self.status_label.setText(f"<b style='color: red;'>Error: {str(e)}</b>")
            self.export_btn.setEnabled(True)

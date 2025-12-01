"""
Dialog for OpenDrive import configuration.
"""

from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QRadioButton,
    QPushButton, QGroupBox, QDoubleSpinBox, QCheckBox, QTextBrowser,
    QLineEdit, QFileDialog, QMessageBox, QVBoxLayout
)
from PyQt6.QtCore import Qt
from .base_dialog import BaseDialog
from ..utils.message_helpers import show_warning


class OpenDriveImportDialog(BaseDialog):
    """Dialog for configuring OpenDrive import options."""

    def __init__(self, has_georeferencing: bool = False, verbose: bool = False, parent=None):
        """
        Initialize OpenDrive import dialog.

        Args:
            has_georeferencing: Whether ORBIT project has control points
            verbose: Whether to enable verbose output (from --verbose flag)
            parent: Parent widget
        """
        super().__init__("Import from OpenDrive", parent, min_width=550)
        self.setModal(True)

        self.has_georeferencing = has_georeferencing
        self.verbose = verbose

        self.setup_ui()
        self.load_properties()

    def setup_ui(self):
        """Create dialog UI."""
        # File selection
        file_group = QGroupBox("OpenDrive File")
        file_layout = QVBoxLayout()

        file_selection_layout = QHBoxLayout()
        self.file_label = QLabel("XODR File:")
        self.file_path_edit = QLineEdit()
        self.file_path_edit.setPlaceholderText("Select .xodr or .xml file...")
        self.file_browse_btn = QPushButton("Browse...")
        self.file_browse_btn.clicked.connect(self._browse_file)
        file_selection_layout.addWidget(self.file_label)
        file_selection_layout.addWidget(self.file_path_edit, 1)
        file_selection_layout.addWidget(self.file_browse_btn)
        file_layout.addLayout(file_selection_layout)

        file_group.setLayout(file_layout)
        self.get_main_layout().addWidget(file_group)

        # Import mode
        mode_group = QGroupBox("Import Mode")
        mode_layout = QVBoxLayout()

        self.add_radio = QRadioButton("Add to existing annotations")
        self.add_radio.setChecked(True)
        self.add_radio.setToolTip("Import OpenDrive data alongside current annotations (duplicate detection enabled)")
        mode_layout.addWidget(self.add_radio)

        self.replace_radio = QRadioButton("Replace all existing data")
        self.replace_radio.setToolTip("Clear all current data before importing")
        mode_layout.addWidget(self.replace_radio)

        mode_group.setLayout(mode_layout)
        self.get_main_layout().addWidget(mode_group)

        # Coordinate transformation options
        coord_group = QGroupBox("Coordinate Transformation")
        coord_layout = QVBoxLayout()

        # Auto-detect (preferred)
        self.auto_detect_radio = QRadioButton("Auto-detect from file")
        self.auto_detect_radio.setChecked(True)
        self.auto_detect_radio.setToolTip(
            "Automatically detect georeferencing from OpenDrive file.\n"
            "Uses geoReference if available, otherwise creates synthetic viewport."
        )
        coord_layout.addWidget(self.auto_detect_radio)

        # Synthetic viewport
        self.synthetic_radio = QRadioButton("Force synthetic viewport (fixed scale)")
        self.synthetic_radio.setToolTip("Ignore any georeferencing and use fixed pixel scale")
        self.synthetic_radio.toggled.connect(self._on_coord_mode_changed)
        coord_layout.addWidget(self.synthetic_radio)

        # Scale setting (for synthetic mode)
        scale_layout = QHBoxLayout()
        scale_layout.addSpacing(30)
        self.scale_label = QLabel("Scale (pixels/meter):")
        self.scale_spinbox = QDoubleSpinBox()
        self.scale_spinbox.setRange(1.0, 100.0)
        self.scale_spinbox.setValue(10.0)
        self.scale_spinbox.setSingleStep(1.0)
        self.scale_spinbox.setToolTip("How many pixels represent one meter (default: 10)")
        self.scale_spinbox.setEnabled(False)
        scale_layout.addWidget(self.scale_label)
        scale_layout.addWidget(self.scale_spinbox)
        scale_layout.addStretch()
        coord_layout.addLayout(scale_layout)

        # Auto-create control points option
        self.auto_georeference_check = QCheckBox("Auto-create control points if OpenDrive has georeferencing")
        self.auto_georeference_check.setToolTip(
            "If OpenDrive file has geoReference but ORBIT doesn't have control points,\n"
            "automatically create control points at image corners."
        )
        coord_layout.addWidget(self.auto_georeference_check)

        coord_group.setLayout(coord_layout)
        self.get_main_layout().addWidget(coord_group)

        # Info text
        self.info_text = QTextBrowser()
        self.info_text.setMaximumHeight(150)
        self.info_text.setOpenExternalLinks(True)
        self.get_main_layout().addWidget(self.info_text)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.import_btn = QPushButton("Import")
        self.import_btn.setDefault(True)
        self.import_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.import_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        self.get_main_layout().addLayout(button_layout)

        # Update button state
        self.file_path_edit.textChanged.connect(self._update_button_state)

    def load_properties(self):
        """Load initial property values."""
        # Set auto_georeference_check state based on has_georeferencing
        if self.has_georeferencing:
            self.auto_georeference_check.setEnabled(False)
            self.auto_georeference_check.setChecked(False)
        else:
            self.auto_georeference_check.setChecked(True)

        # Update info text
        self._update_info_text()

        # Update button state
        self._update_button_state()

    def _browse_file(self):
        """Open file browser to select .xodr file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select OpenDrive File",
            "",
            "OpenDrive Files (*.xodr *.xml);;All Files (*)"
        )
        if file_path:
            self.file_path_edit.setText(file_path)

    def _on_coord_mode_changed(self):
        """Handle coordinate mode radio button change."""
        is_synthetic = self.synthetic_radio.isChecked()
        self.scale_spinbox.setEnabled(is_synthetic)
        self.scale_label.setEnabled(is_synthetic)

    def _update_button_state(self):
        """Update import button enabled state."""
        has_file = bool(self.file_path_edit.text().strip())
        self.import_btn.setEnabled(has_file)

    def _update_info_text(self):
        """Update info text."""
        html = """
<small>
<b>Import Process:</b>
<ul style="margin-top: 0px; margin-bottom: 0px;">
<li>Parses ASAM OpenDrive XML file (.xodr)</li>
<li>Converts geometry (line, arc, spiral, poly3, paramPoly3) to polylines</li>
<li>Imports roads with centerlines, lanes, and lane sections</li>
<li>Imports junctions with connections</li>
<li>Imports traffic signals and roadside objects</li>
<li>Imports elevation profiles if available</li>
<li>Stores OpenDrive IDs for round-trip consistency</li>
</ul>

<b>Supported Features:</b>
<ul style="margin-top: 0px; margin-bottom: 0px;">
<li><b>Geometry:</b> line, arc, spiral (clothoid) - full support; poly3, paramPoly3 - converted to polylines</li>
<li><b>Lanes:</b> Width (constant), type, road marks</li>
<li><b>Elevation:</b> Stored and displayed in polyline properties</li>
<li><b>Signals:</b> Speed limits, traffic lights, stop signs, give way, etc.</li>
<li><b>Objects:</b> Lampposts, guardrails, buildings, trees, bushes</li>
</ul>

<b>Note:</b> Lateral profiles (superelevation, crossfall) are not supported (2D only).
Polynomial lane widths are imported as constant widths.
</small>
"""
        self.info_text.setHtml(html)

    def get_file_path(self) -> str:
        """Get selected file path."""
        return self.file_path_edit.text().strip()

    def get_import_mode(self) -> str:
        """Get import mode ('add' or 'replace')."""
        return 'add' if self.add_radio.isChecked() else 'replace'

    def get_force_synthetic(self) -> bool:
        """Get whether to force synthetic viewport."""
        return self.synthetic_radio.isChecked()

    def get_scale(self) -> float:
        """Get scale in pixels per meter."""
        return self.scale_spinbox.value()

    def get_auto_georeference(self) -> bool:
        """Get whether to auto-create control points."""
        return self.auto_georeference_check.isChecked()

    def get_verbose(self) -> bool:
        """Get verbose output setting (from --verbose flag)."""
        return self.verbose

    def accept(self):
        """Handle accept (validate before closing)."""
        file_path = self.get_file_path()

        if not file_path:
            show_warning(self, "Please select an OpenDrive file to import.", "No File Selected")
            return

        # Check if file exists
        from pathlib import Path
        if not Path(file_path).exists():
            show_warning(self, f"The selected file does not exist:\n{file_path}", "File Not Found")
            return

        super().accept()

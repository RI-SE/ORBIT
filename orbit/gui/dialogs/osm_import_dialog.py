"""
Dialog for OpenStreetMap import configuration.

Supports two modes:
- Georeferenced mode (has_georef=True): bbox computed from image, optional custom radius
- Coordinate mode (has_georef=False): user specifies center lat/lon, radius, and scale
"""

from typing import Optional, Tuple

from PyQt6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QTextBrowser,
    QVBoxLayout,
)

from .base_dialog import BaseDialog


class OSMImportDialog(BaseDialog):
    """Dialog for configuring OSM import options."""

    def __init__(self, bbox: tuple[float, float, float, float],
                 parent=None, has_georef: bool = True):
        """
        Initialize OSM import dialog.

        Args:
            bbox: Bounding box (min_lat, min_lon, max_lat, max_lon).
                  Ignored when has_georef is False.
            parent: Parent widget
            has_georef: Whether georeferencing and image are available
        """
        super().__init__("Import OpenStreetMap Data", parent, min_width=500)
        self.setModal(True)

        self.bbox = bbox
        self.has_georef = has_georef

        self.setup_ui()
        self.load_properties()

    def setup_ui(self):
        """Create dialog UI."""
        # Import source selection
        source_group = QGroupBox("Import Source")
        source_layout = QVBoxLayout()

        self.api_radio = QRadioButton("Import from Overpass API (live query)")
        self.api_radio.setToolTip("Query OpenStreetMap data from Overpass API")
        self.api_radio.toggled.connect(self._on_source_changed)
        source_layout.addWidget(self.api_radio)

        self.file_radio = QRadioButton("Import from file (.osm XML)")
        self.file_radio.setToolTip("Load OpenStreetMap data from a local .osm file")
        self.file_radio.toggled.connect(self._on_source_changed)
        source_layout.addWidget(self.file_radio)

        # File selection (initially hidden)
        file_selection_layout = QHBoxLayout()
        self.file_label = QLabel("OSM File:")
        self.file_path_edit = QLineEdit()
        self.file_path_edit.setPlaceholderText("Select .osm file...")
        self.file_browse_btn = QPushButton("Browse...")
        self.file_browse_btn.clicked.connect(self._browse_file)
        file_selection_layout.addWidget(self.file_label)
        file_selection_layout.addWidget(self.file_path_edit)
        file_selection_layout.addWidget(self.file_browse_btn)
        source_layout.addLayout(file_selection_layout)

        # Store file widgets for show/hide
        self.file_widgets = [self.file_label, self.file_path_edit, self.file_browse_btn]

        source_group.setLayout(source_layout)
        self.get_main_layout().addWidget(source_group)

        if self.has_georef:
            self._setup_georef_area_ui()
        else:
            self._setup_coordinate_area_ui()

        # Import mode
        mode_group = QGroupBox("Import Mode")
        mode_layout = QVBoxLayout()

        self.add_radio = QRadioButton("Add to existing annotations")
        self.add_radio.setToolTip("Import OSM data alongside current annotations")
        mode_layout.addWidget(self.add_radio)

        self.replace_radio = QRadioButton("Replace all existing data")
        self.replace_radio.setToolTip("Clear all current data before importing")
        mode_layout.addWidget(self.replace_radio)

        mode_group.setLayout(mode_layout)
        self.get_main_layout().addWidget(mode_group)

        # Detail level
        detail_group = QGroupBox("Detail Level")
        detail_layout = QVBoxLayout()

        self.moderate_radio = QRadioButton("Moderate (roads, lanes, signals)")
        self.moderate_radio.setToolTip("Import roads with lane configuration and traffic signals")
        detail_layout.addWidget(self.moderate_radio)

        self.full_radio = QRadioButton("Full (+ furniture, buildings, vegetation)")
        self.full_radio.setToolTip("Import all features including lampposts, guardrails, trees, buildings")
        detail_layout.addWidget(self.full_radio)

        detail_group.setLayout(detail_layout)
        self.get_main_layout().addWidget(detail_group)

        # Options
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout()

        # Default lane width
        lane_width_layout = QHBoxLayout()
        lane_width_layout.addWidget(QLabel("Default Lane Width:"))
        self.lane_width_spin = QDoubleSpinBox()
        self.lane_width_spin.setRange(2.0, 5.0)
        self.lane_width_spin.setValue(3.5)
        self.lane_width_spin.setSingleStep(0.1)
        self.lane_width_spin.setSuffix(" m")
        self.lane_width_spin.setToolTip("Lane width when not specified in OSM data")
        lane_width_layout.addWidget(self.lane_width_spin)
        lane_width_layout.addStretch()
        options_layout.addLayout(lane_width_layout)

        # Import junctions
        self.import_junctions_check = QCheckBox("Import junctions (split sections at intersections)")
        self.import_junctions_check.setToolTip("Detect intersections and create Junction objects")
        self.import_junctions_check.toggled.connect(self._on_junctions_toggled)
        options_layout.addWidget(self.import_junctions_check)

        # Auto-adjust junction geometry (only visible when junctions enabled)
        self.auto_adjust_check = QCheckBox("Auto-adjust junction geometry")
        self.auto_adjust_check.setToolTip(
            "Adapt junction offset distances to avoid overlap at close junctions, "
            "and fix sharp curves on connecting roads")
        self.auto_adjust_check.setChecked(True)
        options_layout.addWidget(self.auto_adjust_check)

        # Filter roads outside image
        self.filter_outside_image_check = QCheckBox("Filter roads outside image bounds")
        self.filter_outside_image_check.setToolTip(
            "Only import roads that have at least one endpoint inside the image frame"
        )
        options_layout.addWidget(self.filter_outside_image_check)

        options_group.setLayout(options_layout)
        self.get_main_layout().addWidget(options_group)

        # Info box
        info_group = QGroupBox("Information")
        info_layout = QVBoxLayout()

        self.info_text = QTextBrowser()
        self.info_text.setMaximumHeight(100)
        self.info_text.setOpenExternalLinks(False)
        info_layout.addWidget(self.info_text)
        info_group.setLayout(info_layout)
        self.get_main_layout().addWidget(info_group)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        import_btn = QPushButton("Import")
        import_btn.setDefault(True)
        import_btn.clicked.connect(self.accept)
        button_layout.addWidget(import_btn)

        self.get_main_layout().addLayout(button_layout)

    def _setup_georef_area_ui(self):
        """Set up import area UI for georeferenced mode (image + control points)."""
        # Bounding box info
        self.bbox_group = QGroupBox("Import Area")
        bbox_layout = QVBoxLayout()

        min_lat, min_lon, max_lat, max_lon = self.bbox
        bbox_text = f"""
<b>Bounding Box:</b><br>
Latitude: {min_lat:.6f}\u00b0 to {max_lat:.6f}\u00b0<br>
Longitude: {min_lon:.6f}\u00b0 to {max_lon:.6f}\u00b0<br>
<br>
<i>Data will be queried from OpenStreetMap for this area.</i>
"""
        self.bbox_label = QLabel(bbox_text)
        self.bbox_label.setWordWrap(True)
        bbox_layout.addWidget(self.bbox_label)

        # Custom radius option
        self.custom_radius_check = QCheckBox("Use custom radius from image center")
        self.custom_radius_check.setToolTip(
            "Override the image-derived bounding box with a circular area from the image center"
        )
        self.custom_radius_check.toggled.connect(self._on_custom_radius_toggled)
        bbox_layout.addWidget(self.custom_radius_check)

        # Custom radius spin box (initially hidden)
        radius_layout = QHBoxLayout()
        self.custom_radius_label = QLabel("Radius:")
        self.custom_radius_spin = QDoubleSpinBox()
        self.custom_radius_spin.setRange(50.0, 5000.0)
        self.custom_radius_spin.setValue(500.0)
        self.custom_radius_spin.setSingleStep(50.0)
        self.custom_radius_spin.setSuffix(" m")
        self.custom_radius_spin.setToolTip("Radius around image center in meters")
        radius_layout.addWidget(self.custom_radius_label)
        radius_layout.addWidget(self.custom_radius_spin)
        radius_layout.addStretch()
        bbox_layout.addLayout(radius_layout)

        # Warning label for large radius
        self.custom_radius_warning = QLabel(
            "<i style='color: orange;'>Large radius may result in slow import</i>"
        )
        self.custom_radius_warning.setVisible(False)
        bbox_layout.addWidget(self.custom_radius_warning)
        self.custom_radius_spin.valueChanged.connect(self._on_custom_radius_value_changed)

        # Initially hide custom radius widgets
        self.custom_radius_label.setVisible(False)
        self.custom_radius_spin.setVisible(False)

        self.bbox_group.setLayout(bbox_layout)
        self.get_main_layout().addWidget(self.bbox_group)

    def _setup_coordinate_area_ui(self):
        """Set up import area UI for coordinate mode (no image)."""
        self.bbox_group = QGroupBox("Import Area (specify coordinates)")
        coord_layout = QVBoxLayout()

        # Latitude
        lat_layout = QHBoxLayout()
        lat_layout.addWidget(QLabel("Center Latitude:"))
        self.center_lat_spin = QDoubleSpinBox()
        self.center_lat_spin.setRange(-90.0, 90.0)
        self.center_lat_spin.setDecimals(6)
        self.center_lat_spin.setValue(59.347)
        self.center_lat_spin.setSingleStep(0.001)
        self.center_lat_spin.setSuffix("\u00b0")
        lat_layout.addWidget(self.center_lat_spin)
        lat_layout.addStretch()
        coord_layout.addLayout(lat_layout)

        # Longitude
        lon_layout = QHBoxLayout()
        lon_layout.addWidget(QLabel("Center Longitude:"))
        self.center_lon_spin = QDoubleSpinBox()
        self.center_lon_spin.setRange(-180.0, 180.0)
        self.center_lon_spin.setDecimals(6)
        self.center_lon_spin.setValue(18.073)
        self.center_lon_spin.setSingleStep(0.001)
        self.center_lon_spin.setSuffix("\u00b0")
        lon_layout.addWidget(self.center_lon_spin)
        lon_layout.addStretch()
        coord_layout.addLayout(lon_layout)

        # Radius
        radius_layout = QHBoxLayout()
        radius_layout.addWidget(QLabel("Radius:"))
        self.coord_radius_spin = QDoubleSpinBox()
        self.coord_radius_spin.setRange(50.0, 5000.0)
        self.coord_radius_spin.setValue(500.0)
        self.coord_radius_spin.setSingleStep(50.0)
        self.coord_radius_spin.setSuffix(" m")
        self.coord_radius_spin.setToolTip("Radius around center point in meters")
        self.coord_radius_spin.valueChanged.connect(self._on_coord_radius_value_changed)
        radius_layout.addWidget(self.coord_radius_spin)
        radius_layout.addStretch()
        coord_layout.addLayout(radius_layout)

        # Warning label for large radius
        self.coord_radius_warning = QLabel(
            "<i style='color: orange;'>Large radius may result in slow import</i>"
        )
        self.coord_radius_warning.setVisible(False)
        coord_layout.addWidget(self.coord_radius_warning)

        # Scale
        scale_layout = QHBoxLayout()
        scale_layout.addWidget(QLabel("Scale:"))
        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(1.0, 20.0)
        self.scale_spin.setValue(5.0)
        self.scale_spin.setSingleStep(0.5)
        self.scale_spin.setSuffix(" px/m")
        self.scale_spin.setToolTip("Canvas resolution: pixels per meter")
        scale_layout.addWidget(self.scale_spin)
        scale_layout.addStretch()
        coord_layout.addLayout(scale_layout)

        self.bbox_group.setLayout(coord_layout)
        self.get_main_layout().addWidget(self.bbox_group)

    def load_properties(self):
        """Load initial property values."""
        # Set initial radio button states
        self.api_radio.setChecked(True)
        self.add_radio.setChecked(True)
        self.moderate_radio.setChecked(True)
        self.import_junctions_check.setChecked(True)

        # Hide file widgets initially (API is default)
        for widget in self.file_widgets:
            widget.setVisible(False)

        # Update info text
        self._update_info_text()

    def get_import_mode(self) -> str:
        """Get selected import mode.

        Returns:
            'add' or 'replace'
        """
        return 'replace' if self.replace_radio.isChecked() else 'add'

    def get_detail_level(self) -> str:
        """Get selected detail level.

        Returns:
            'moderate' or 'full'
        """
        return 'full' if self.full_radio.isChecked() else 'moderate'

    def get_default_lane_width(self) -> float:
        """Get default lane width in meters."""
        return self.lane_width_spin.value()

    def get_import_junctions(self) -> bool:
        """Get whether to import junctions."""
        return self.import_junctions_check.isChecked()

    def get_filter_outside_image(self) -> bool:
        """Get whether to filter roads outside image bounds."""
        return self.filter_outside_image_check.isChecked()

    def get_custom_radius(self) -> Optional[float]:
        """Get custom radius in meters, or None if not enabled.

        Only applicable in georef mode.
        """
        if self.has_georef and hasattr(self, 'custom_radius_check'):
            if self.custom_radius_check.isChecked():
                return self.custom_radius_spin.value()
        return None

    def get_coordinate_params(self) -> Optional[Tuple[float, float, float, float]]:
        """Get coordinate mode parameters.

        Returns:
            Tuple of (lat, lon, radius_m, scale_px_per_m) or None if in georef mode.
        """
        if self.has_georef:
            return None
        return (
            self.center_lat_spin.value(),
            self.center_lon_spin.value(),
            self.coord_radius_spin.value(),
            self.scale_spin.value(),
        )

    def get_import_source(self) -> tuple:
        """Get import source and related data.

        Returns:
            Tuple of ('api', options) or ('file', file_path, options)
            where options is a dict with import_mode, detail_level, etc.
        """
        options = {
            'import_mode': self.get_import_mode(),
            'detail_level': self.get_detail_level(),
            'default_lane_width': self.get_default_lane_width(),
            'import_junctions': self.get_import_junctions(),
            'filter_outside_image': self.get_filter_outside_image(),
            'auto_adjust_junctions': self.auto_adjust_check.isChecked(),
        }

        if self.api_radio.isChecked():
            return ('api', options)
        else:
            file_path = self.file_path_edit.text()
            return ('file', file_path, options)

    def _on_junctions_toggled(self, checked: bool):
        """Show/hide junction sub-options based on import junctions checkbox."""
        self.auto_adjust_check.setVisible(checked)

    def _on_source_changed(self):
        """Handle import source radio button change."""
        is_api = self.api_radio.isChecked()

        # Show/hide bbox group (only for API)
        self.bbox_group.setVisible(is_api)

        # Show/hide file widgets (only for file)
        for widget in self.file_widgets:
            widget.setVisible(not is_api)

        # Update info text
        self._update_info_text()

    def _on_custom_radius_toggled(self, checked: bool):
        """Handle custom radius checkbox toggle."""
        self.custom_radius_label.setVisible(checked)
        self.custom_radius_spin.setVisible(checked)
        if not checked:
            self.custom_radius_warning.setVisible(False)
        else:
            self._on_custom_radius_value_changed(self.custom_radius_spin.value())

    def _on_custom_radius_value_changed(self, value: float):
        """Show warning when custom radius exceeds 1000m."""
        if hasattr(self, 'custom_radius_warning'):
            self.custom_radius_warning.setVisible(value > 1000)

    def _on_coord_radius_value_changed(self, value: float):
        """Show warning when coordinate radius exceeds 1000m."""
        if hasattr(self, 'coord_radius_warning'):
            self.coord_radius_warning.setVisible(value > 1000)

    def _browse_file(self):
        """Open file browser to select .osm file."""
        start_dir = getattr(self.parent(), '_last_file_directory', '')
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select OSM File", start_dir, "OSM Files (*.osm);;All Files (*)")
        if file_path:
            self.file_path_edit.setText(file_path)
            if hasattr(self.parent(), '_remember_directory'):
                self.parent()._remember_directory(file_path)

    def _update_info_text(self):
        """Update info text based on selected import source."""
        if self.api_radio.isChecked():
            html = """
<small>
<b>Import Process (API):</b>
<ul style="margin-top: 0px; margin-bottom: 0px;">
<li>Queries <a href="https://overpass-api.de">Overpass API</a> for OpenStreetMap data</li>
<li>Converts OSM features to ORBIT objects (roads, lanes, signals, objects)</li>
<li>Duplicate detection prevents re-importing existing features</li>
<li>Timeout: 60 seconds (partial data kept on timeout)</li>
</ul>
</small>
"""
        else:
            html = """
<small>
<b>Import Process (File):</b>
<ul style="margin-top: 0px; margin-bottom: 0px;">
<li>Loads OpenStreetMap data from local .osm XML file</li>
<li>Converts OSM features to ORBIT objects (roads, lanes, signals, objects)</li>
<li>Duplicate detection prevents re-importing existing features</li>
<li>All import settings (mode, detail, options) apply to file imports</li>
</ul>
</small>
"""
        self.info_text.setHtml(html)

"""
Preferences dialog for ORBIT.

Allows configuring project-level settings including georeferencing method,
traffic side, and country code.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
)

from orbit_core.models import Project, SignLibraryManager
from orbit_core.utils.provenance import DEFAULT_TEMPLATE, is_dataprov_available

from .base_dialog import BaseDialog, InfoIconLabel


class PreferencesDialog(BaseDialog):
    """Dialog for configuring project preferences."""

    def __init__(self, project: Project, parent=None):
        super().__init__("Project Preferences", parent, min_width=500)

        self.project = project
        from PyQt6.QtCore import QSettings
        self.app_settings = QSettings()
        self.setup_ui()
        self.load_properties()

    def setup_ui(self):
        """Setup the dialog UI."""
        # Map information section
        map_layout = self.add_form_group("Map Information")

        # Map name
        self.map_name_edit = QLineEdit()
        self.map_name_edit.setPlaceholderText("e.g., City Center, Highway Junction")

        map_name_label = InfoIconLabel(
            "Map Name:",
            "This name will be used in the OpenDrive header. "
            "Defaults to the image filename when loaded.",
            bold=False
        )
        map_layout.addRow(map_name_label, self.map_name_edit)

        # Georeferencing section
        georef_layout = self.add_form_group("Georeferencing")

        # Transformation method
        self.transform_method_combo = QComboBox()
        self.transform_method_combo.addItem("Affine (for orthophotos, satellite imagery)", "affine")
        self.transform_method_combo.addItem("Homography (for oblique drone imagery)", "homography")
        self.transform_method_combo.addItem("Drone-assisted (requires drone log)", "drone_assisted")

        transform_label = InfoIconLabel(
            "Transformation Method:",
            "Affine: Best for nadir (straight down) aerial/satellite images. Requires 3+ control points.\n"
            "Homography: Best for tilted camera drone images with perspective. Requires 4+ control points.\n"
            "Drone-assisted: Uses drone flight log (position, altitude, gimbal) for a physically-derived\n"
            "  homography. Requires drone log loaded in the Georeferencing dialog. Works even when\n"
            "  GCPs are nearly collinear (e.g., all along one road).",
            bold=False
        )
        georef_layout.addRow(transform_label, self.transform_method_combo)

        # Traffic and location section
        traffic_layout = self.add_form_group("Traffic and Location")

        # Right-hand traffic
        self.traffic_combo = QComboBox()
        self.traffic_combo.addItem("Right-hand traffic", True)
        self.traffic_combo.addItem("Left-hand traffic", False)

        traffic_label = InfoIconLabel(
            "Traffic Side:",
            "Right-hand: Vehicles drive on right side (USA, Europe, etc.)\n"
            "Left-hand: Vehicles drive on left side (UK, Japan, etc.)",
            bold=False
        )
        traffic_layout.addRow(traffic_label, self.traffic_combo)

        # Country code
        self.country_code_edit = QLineEdit()
        self.country_code_edit.setText("se")
        self.country_code_edit.setMaxLength(2)
        self.country_code_edit.setPlaceholderText("e.g., se, us, de")
        self.country_code_edit.setMaximumWidth(100)

        country_label = InfoIconLabel(
            "Country Code:",
            "ISO 3166-1 two-letter country code for OpenDrive export.",
            bold=False
        )
        traffic_layout.addRow(country_label, self.country_code_edit)

        # Junction settings section
        junction_layout = self.add_form_group("Junction Settings")

        # Junction offset distance
        self.junction_offset_spin = QDoubleSpinBox()
        self.junction_offset_spin.setRange(0.0, 50.0)  # 0-50 meters
        self.junction_offset_spin.setSingleStep(1.0)
        self.junction_offset_spin.setDecimals(1)
        self.junction_offset_spin.setSuffix(" m")

        junction_offset_label = InfoIconLabel(
            "Junction Offset Distance:",
            "When importing from OSM, road endpoints are moved away from junction centers "
            "by this distance to create space for connecting roads. Typical values: 5-15m.",
            bold=False
        )
        junction_layout.addRow(junction_offset_label, self.junction_offset_spin)

        # Roundabout ring offset distance
        self.roundabout_ring_offset_spin = QDoubleSpinBox()
        self.roundabout_ring_offset_spin.setRange(0.0, 20.0)  # 0-20 meters
        self.roundabout_ring_offset_spin.setSingleStep(0.5)
        self.roundabout_ring_offset_spin.setDecimals(1)
        self.roundabout_ring_offset_spin.setSuffix(" m")

        roundabout_ring_label = InfoIconLabel(
            "Roundabout Ring Offset:",
            "Ring segments are moved back by this distance to create space for connecting roads. "
            "Typical values: 2-6m.",
            bold=False
        )
        junction_layout.addRow(roundabout_ring_label, self.roundabout_ring_offset_spin)

        # Roundabout approach road offset distance
        self.roundabout_approach_offset_spin = QDoubleSpinBox()
        self.roundabout_approach_offset_spin.setRange(0.0, 30.0)  # 0-30 meters
        self.roundabout_approach_offset_spin.setSingleStep(0.5)
        self.roundabout_approach_offset_spin.setDecimals(1)
        self.roundabout_approach_offset_spin.setSuffix(" m")

        roundabout_approach_label = InfoIconLabel(
            "Roundabout Approach Offset:",
            "Approach roads are moved back by this distance. Larger values create longer "
            "entry/exit connectors. Typical values: 6-12m.",
            bold=False
        )
        junction_layout.addRow(roundabout_approach_label, self.roundabout_approach_offset_spin)

        # Sign libraries section
        sign_layout = self.add_form_group("Sign Libraries")

        self.library_list = QListWidget()
        self.library_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.library_list.setMaximumHeight(120)

        # Populate with available libraries
        manager = SignLibraryManager.instance()
        manager.discover_libraries()
        for lib_info in manager.get_all_available_libraries_info():
            item = QListWidgetItem(f"{lib_info['name']} ({lib_info['id']})")
            item.setData(Qt.ItemDataRole.UserRole, lib_info['id'])
            self.library_list.addItem(item)

        library_label = InfoIconLabel(
            "Enabled Libraries:",
            "Select which sign libraries to use when adding signals. "
            "Libraries provide country-specific road signs with proper OpenDRIVE mappings.",
            bold=False
        )
        sign_layout.addRow(library_label, self.library_list)

        # Provenance tracking section
        prov_layout = self.add_form_group("Data Provenance")

        dataprov_available = is_dataprov_available()
        hint = "" if dataprov_available else " (install dataprov to enable)"

        self.provenance_checkbox = QCheckBox(f"Create provenance sidecar files{hint}")
        self.provenance_checkbox.setEnabled(dataprov_available)
        self.provenance_checkbox.setToolTip(
            "When enabled, a .prov.json file is written alongside each saved project "
            "and each exported file, recording the tools and inputs used to create it."
        )
        prov_layout.addRow("", self.provenance_checkbox)

        self.provenance_template_edit = QLineEdit()
        self.provenance_template_edit.setPlaceholderText(DEFAULT_TEMPLATE)
        self.provenance_template_edit.setEnabled(dataprov_available)
        template_label = InfoIconLabel(
            "File name template:",
            "Template for provenance sidecar file names.\n"
            "Variables: {dir} parent directory, {stem} filename without extension, "
            "{ext} extension (with dot), {name} full filename.\n"
            f"Default: {DEFAULT_TEMPLATE}",
            bold=False,
        )
        prov_layout.addRow(template_label, self.provenance_template_edit)

        # Create standard OK/Cancel buttons
        self.create_button_box()

    def load_properties(self):
        """Load current preferences from project."""
        # Map name
        self.map_name_edit.setText(self.project.map_name)

        # Transformation method
        if self.project.transform_method == 'homography':
            self.transform_method_combo.setCurrentIndex(1)
        elif self.project.transform_method == 'drone_assisted':
            self.transform_method_combo.setCurrentIndex(2)
        else:
            self.transform_method_combo.setCurrentIndex(0)

        # Disable drone-assisted if no drone log is loaded
        model = self.transform_method_combo.model()
        drone_item = model.item(2)
        if self.project.drone_metadata is None:
            from PyQt6.QtGui import QColor
            drone_item.setEnabled(False)
            drone_item.setForeground(QColor('gray'))

        # Traffic side
        if self.project.right_hand_traffic:
            self.traffic_combo.setCurrentIndex(0)
        else:
            self.traffic_combo.setCurrentIndex(1)

        # Country code
        self.country_code_edit.setText(self.project.country_code.lower())

        # Junction offset distance
        self.junction_offset_spin.setValue(self.project.junction_offset_distance_meters)

        # Roundabout offset distances
        self.roundabout_ring_offset_spin.setValue(self.project.roundabout_ring_offset_distance_meters)
        self.roundabout_approach_offset_spin.setValue(self.project.roundabout_approach_offset_distance_meters)

        # Sign libraries - select enabled ones
        enabled_libs = set(self.project.enabled_sign_libraries)
        for i in range(self.library_list.count()):
            item = self.library_list.item(i)
            lib_id = item.data(Qt.ItemDataRole.UserRole)
            if lib_id in enabled_libs:
                item.setSelected(True)

        # Provenance settings (app-level, from QSettings)
        self.provenance_checkbox.setChecked(
            self.app_settings.value("provenance/enabled", False, type=bool)
        )
        self.provenance_template_edit.setText(
            self.app_settings.value("provenance/name_template", DEFAULT_TEMPLATE, type=str)
        )

    def accept(self):
        """Save preferences and close dialog."""
        # Save map name
        self.project.map_name = self.map_name_edit.text().strip()

        # Save transformation method
        self.project.transform_method = self.transform_method_combo.currentData()

        # Save traffic side
        self.project.right_hand_traffic = self.traffic_combo.currentData()

        # Save country code
        self.project.country_code = self.country_code_edit.text().strip().lower()

        # Save junction offset distance
        self.project.junction_offset_distance_meters = self.junction_offset_spin.value()

        # Save roundabout offset distances
        self.project.roundabout_ring_offset_distance_meters = self.roundabout_ring_offset_spin.value()
        self.project.roundabout_approach_offset_distance_meters = self.roundabout_approach_offset_spin.value()

        # Save enabled sign libraries
        enabled_libs = []
        for item in self.library_list.selectedItems():
            lib_id = item.data(Qt.ItemDataRole.UserRole)
            if lib_id:
                enabled_libs.append(lib_id)
        # Ensure at least one library is enabled (default to 'se' if none selected)
        if not enabled_libs:
            enabled_libs = ['se']
        self.project.enabled_sign_libraries = enabled_libs

        # Save provenance settings to app QSettings
        self.app_settings.setValue("provenance/enabled", self.provenance_checkbox.isChecked())
        template = self.provenance_template_edit.text().strip() or DEFAULT_TEMPLATE
        self.app_settings.setValue("provenance/name_template", template)

        super().accept()

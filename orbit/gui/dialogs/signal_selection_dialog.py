"""
Dialog for selecting signal type when placing a new signal.

Supports library-based sign selection with categories and custom OpenDRIVE codes.
"""

from typing import Optional, List, Tuple
from PyQt6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QGroupBox, QPushButton, QTreeWidget,
    QTreeWidgetItem, QComboBox, QLineEdit, QCheckBox, QLabel,
    QWidget, QSplitter, QFrame
)
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtCore import Qt

from orbit.models.signal import SignalType, SpeedUnit
from orbit.models.sign_library import SignLibrary, SignDefinition
from orbit.models.sign_library_manager import SignLibraryManager
from ..graphics.signal_graphics import create_signal_pixmap
from .base_dialog import BaseDialog


class SignalSelectionDialog(BaseDialog):
    """
    Dialog for selecting a signal to place.

    Supports:
    - Library-based signs organized by category
    - Template signs (like speed limits) with value selection
    - Custom OpenDRIVE type/subtype codes
    """

    def __init__(self, enabled_libraries: Optional[List[str]] = None, parent=None):
        """
        Initialize the dialog.

        Args:
            enabled_libraries: List of enabled library IDs. If None, uses ['se'].
            parent: Parent widget
        """
        super().__init__("Select Signal", parent, min_width=600)

        self.enabled_libraries = enabled_libraries or ['se']
        self.manager = SignLibraryManager.instance()

        # Selection result
        self.selected_type: Optional[SignalType] = None
        self.selected_library_id: Optional[str] = None
        self.selected_sign_id: Optional[str] = None
        self.selected_value: Optional[int] = None
        self.selected_unit = SpeedUnit.KMH
        self.custom_type: Optional[str] = None
        self.custom_subtype: Optional[str] = None

        self.setup_ui()
        self.load_properties()

    def setup_ui(self):
        """Create the dialog UI."""
        main_layout = self.get_main_layout()

        # Library selector
        lib_layout = QHBoxLayout()
        lib_layout.addWidget(QLabel("Library:"))
        self.library_combo = QComboBox()
        self.library_combo.currentIndexChanged.connect(self._on_library_changed)
        lib_layout.addWidget(self.library_combo, 1)
        main_layout.addLayout(lib_layout)

        # Sign tree
        tree_group = QGroupBox("Available Signs")
        tree_layout = QVBoxLayout()

        self.sign_tree = QTreeWidget()
        self.sign_tree.setHeaderHidden(True)
        from PyQt6.QtCore import QSize
        self.sign_tree.setIconSize(QSize(32, 32))
        self.sign_tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.sign_tree.itemSelectionChanged.connect(self._on_selection_changed)
        tree_layout.addWidget(self.sign_tree)

        tree_group.setLayout(tree_layout)
        main_layout.addWidget(tree_group, 1)

        # Template value selector (for speed limits, etc.)
        self.value_frame = QFrame()
        value_layout = QHBoxLayout(self.value_frame)
        value_layout.setContentsMargins(0, 0, 0, 0)
        value_layout.addWidget(QLabel("Value:"))
        self.value_combo = QComboBox()
        self.value_combo.currentIndexChanged.connect(self._on_value_changed)
        value_layout.addWidget(self.value_combo, 1)
        self.value_frame.setVisible(False)
        main_layout.addWidget(self.value_frame)

        # Custom OpenDRIVE codes section
        custom_group = QGroupBox("Custom OpenDRIVE Codes")
        custom_layout = QVBoxLayout()

        self.custom_checkbox = QCheckBox("Use custom OpenDRIVE type/subtype")
        self.custom_checkbox.stateChanged.connect(self._on_custom_toggled)
        custom_layout.addWidget(self.custom_checkbox)

        custom_fields = QHBoxLayout()
        custom_fields.addWidget(QLabel("Type:"))
        self.custom_type_edit = QLineEdit()
        self.custom_type_edit.setPlaceholderText("e.g., 274")
        self.custom_type_edit.setMaximumWidth(100)
        self.custom_type_edit.setEnabled(False)
        custom_fields.addWidget(self.custom_type_edit)

        custom_fields.addWidget(QLabel("Subtype:"))
        self.custom_subtype_edit = QLineEdit()
        self.custom_subtype_edit.setPlaceholderText("e.g., 50")
        self.custom_subtype_edit.setMaximumWidth(100)
        self.custom_subtype_edit.setEnabled(False)
        custom_fields.addWidget(self.custom_subtype_edit)
        custom_fields.addStretch()

        custom_layout.addLayout(custom_fields)
        custom_group.setLayout(custom_layout)
        main_layout.addWidget(custom_group)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        self.select_btn = QPushButton("Select")
        self.select_btn.setEnabled(False)
        self.select_btn.clicked.connect(self._do_select)
        button_layout.addWidget(self.select_btn)

        main_layout.addLayout(button_layout)

    def load_properties(self):
        """Load libraries and populate UI."""
        # Populate library combo
        self.library_combo.clear()

        # Discover and load libraries
        self.manager.discover_libraries()

        for lib_id in self.enabled_libraries:
            library = self.manager.load_library(lib_id)
            if library:
                self.library_combo.addItem(
                    f"{library.name} ({library.country_code})",
                    lib_id
                )

        # If no libraries available, show message
        if self.library_combo.count() == 0:
            self.library_combo.addItem("No libraries available", None)

        # Trigger initial load
        self._on_library_changed(0)

    def _on_library_changed(self, index: int):
        """Handle library selection change."""
        lib_id = self.library_combo.currentData()
        if not lib_id:
            self.sign_tree.clear()
            return

        library = self.manager.get_library(lib_id)
        if not library:
            self.sign_tree.clear()
            return

        self._populate_tree(library)

    def _populate_tree(self, library: SignLibrary):
        """Populate the tree with signs from a library."""
        self.sign_tree.clear()

        # Create category nodes
        category_items = {}
        for category in library.categories:
            item = QTreeWidgetItem([category.name])
            item.setData(0, Qt.ItemDataRole.UserRole, {
                'type': 'category',
                'category_id': category.id
            })
            item.setExpanded(True)
            self.sign_tree.addTopLevelItem(item)
            category_items[category.id] = item

        # Add signs to categories
        for sign in library.signs:
            category_item = category_items.get(sign.category_id)
            if not category_item:
                continue

            # Create sign item
            display_name = sign.get_display_name()
            item = QTreeWidgetItem([display_name])
            item.setData(0, Qt.ItemDataRole.UserRole, {
                'type': 'sign',
                'library_id': library.id,
                'sign_id': sign.id,
                'is_template': sign.is_template,
                'template_value': sign.template_value
            })

            # Set icon from library image or fallback
            pixmap = self._get_sign_pixmap(library, sign)
            if pixmap:
                item.setIcon(0, QIcon(pixmap))

            category_item.addChild(item)

    def _get_sign_pixmap(self, library: SignLibrary, sign: SignDefinition) -> Optional[QPixmap]:
        """Get a pixmap for a sign, from library or fallback."""
        # Try to load from library
        image_path = library.get_sign_image_path(sign)
        if image_path and image_path.exists():
            pixmap = QPixmap(str(image_path))
            return pixmap.scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)

        # Fallback: generate placeholder based on category
        # Use legacy types for fallback rendering
        if 'speed' in sign.name.lower():
            return create_signal_pixmap(SignalType.SPEED_LIMIT, sign.template_value, size=32)
        elif 'give way' in sign.name.lower() or sign.id == 'B1':
            return create_signal_pixmap(SignalType.GIVE_WAY, size=32)
        elif 'stop' in sign.name.lower() or sign.id == 'B2':
            return create_signal_pixmap(SignalType.STOP, size=32)

        # Generic fallback
        return create_signal_pixmap(SignalType.GIVE_WAY, size=32)

    def _on_selection_changed(self):
        """Handle tree selection change."""
        items = self.sign_tree.selectedItems()
        if not items:
            self.select_btn.setEnabled(False)
            self.value_frame.setVisible(False)
            return

        item = items[0]
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data or data.get('type') != 'sign':
            self.select_btn.setEnabled(False)
            self.value_frame.setVisible(False)
            return

        # Enable selection
        self.select_btn.setEnabled(not self.custom_checkbox.isChecked())

        # Check if this is a template sign that needs value selection
        is_template = data.get('is_template', False)
        template_value = data.get('template_value')

        if is_template and template_value is None:
            # This is a template base - need to show value selector
            self._show_template_values(data.get('library_id'), data.get('sign_id'))
        else:
            self.value_frame.setVisible(False)

    def _show_template_values(self, library_id: str, sign_id: str):
        """Show value selector for template signs."""
        # This shouldn't normally happen since we expand templates into individual signs
        # But keeping this for potential future use
        self.value_frame.setVisible(False)

    def _on_value_changed(self, index: int):
        """Handle template value change."""
        pass  # Reserved for future use

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle double-click to select."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data.get('type') == 'sign':
            self._do_select()

    def _on_custom_toggled(self, state: int):
        """Handle custom checkbox toggle."""
        is_custom = state == Qt.CheckState.Checked.value
        self.custom_type_edit.setEnabled(is_custom)
        self.custom_subtype_edit.setEnabled(is_custom)
        self.sign_tree.setEnabled(not is_custom)

        if is_custom:
            self.select_btn.setEnabled(True)
        else:
            # Re-enable based on selection
            self._on_selection_changed()

    def _do_select(self):
        """Perform selection and close dialog."""
        if self.custom_checkbox.isChecked():
            # Custom OpenDRIVE codes
            self.selected_type = SignalType.CUSTOM
            self.custom_type = self.custom_type_edit.text().strip() or "-1"
            self.custom_subtype = self.custom_subtype_edit.text().strip() or "-1"
            self.selected_library_id = None
            self.selected_sign_id = None
            self.accept()
            return

        # Library-based selection
        items = self.sign_tree.selectedItems()
        if not items:
            return

        item = items[0]
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data or data.get('type') != 'sign':
            return

        self.selected_type = SignalType.LIBRARY_SIGN
        self.selected_library_id = data.get('library_id')
        self.selected_sign_id = data.get('sign_id')

        # Get value from sign definition if template
        if data.get('is_template'):
            self.selected_value = data.get('template_value')

        self.accept()

    def get_selection(self) -> Tuple[
        Optional[SignalType],
        Optional[str],
        Optional[str],
        Optional[int],
        SpeedUnit,
        Optional[str],
        Optional[str]
    ]:
        """
        Get the selection result.

        Returns:
            Tuple of (signal_type, library_id, sign_id, value, speed_unit, custom_type, custom_subtype)
            Returns (None, None, None, None, KMH, None, None) if cancelled
        """
        if self.selected_type:
            return (
                self.selected_type,
                self.selected_library_id,
                self.selected_sign_id,
                self.selected_value,
                self.selected_unit,
                self.custom_type,
                self.custom_subtype
            )
        return (None, None, None, None, SpeedUnit.KMH, None, None)

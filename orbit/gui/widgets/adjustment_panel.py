"""
Adjustment panel widget for ORBIT.

Displays current transformation adjustment values and provides controls
for interactive alignment of imported OSM data with the aerial image.
"""

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from orbit.utils.coordinate_transform import TransformAdjustment


class AdjustmentPanel(QWidget):
    """
    Widget for displaying and controlling georeferencing adjustments.

    Shows current adjustment values (translation, rotation, scale) and
    provides buttons for reset and apply operations.
    """

    # Signals
    apply_requested = pyqtSignal()  # User wants to bake adjustment into control points
    reset_requested = pyqtSignal()  # User wants to reset all adjustments
    autofit_toggled = pyqtSignal(bool)  # Auto-fit mode toggled on/off
    autofit_compute_requested = pyqtSignal()  # User wants to compute fit
    autofit_clear_requested = pyqtSignal()  # User wants to clear correspondence pairs

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        """Setup the widget UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Title
        title = QLabel("Transform Adjustment")
        title_font = QFont()
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        # Current values group
        values_group = QGroupBox("Current Adjustment")
        values_layout = QGridLayout(values_group)
        values_layout.setSpacing(4)

        # Translation
        values_layout.addWidget(QLabel("Translation:"), 0, 0)
        self.translation_label = QLabel("(0.0, 0.0) px")
        self.translation_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        values_layout.addWidget(self.translation_label, 0, 1)

        # Rotation
        values_layout.addWidget(QLabel("Rotation:"), 1, 0)
        self.rotation_label = QLabel("0.00°")
        self.rotation_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        values_layout.addWidget(self.rotation_label, 1, 1)

        # Scale
        values_layout.addWidget(QLabel("Scale:"), 2, 0)
        self.scale_label = QLabel("1.0000 × 1.0000")
        self.scale_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        values_layout.addWidget(self.scale_label, 2, 1)

        # Shear
        values_layout.addWidget(QLabel("Shear:"), 3, 0)
        self.shear_label = QLabel("(0.0000, 0.0000)")
        self.shear_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        values_layout.addWidget(self.shear_label, 3, 1)

        layout.addWidget(values_group)

        # Buttons
        button_layout = QHBoxLayout()

        self.reset_btn = QPushButton("Reset")
        self.reset_btn.setToolTip("Reset all adjustments (Esc)")
        self.reset_btn.clicked.connect(self.reset_requested.emit)
        button_layout.addWidget(self.reset_btn)

        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setToolTip("Apply adjustment to control points")
        self.apply_btn.clicked.connect(self.apply_requested.emit)
        button_layout.addWidget(self.apply_btn)

        layout.addLayout(button_layout)

        # Auto-fit section
        autofit_group = QGroupBox("Auto-fit from Points")
        autofit_layout = QVBoxLayout(autofit_group)
        autofit_layout.setSpacing(4)

        autofit_desc = QLabel(
            "Pick point pairs: click where a feature IS,\n"
            "then where it SHOULD BE. Repeat ≥3 times."
        )
        autofit_desc.setWordWrap(True)
        desc_font = QFont()
        desc_font.setPointSize(desc_font.pointSize() - 1)
        autofit_desc.setFont(desc_font)
        autofit_desc.setStyleSheet("color: gray;")
        autofit_layout.addWidget(autofit_desc)

        self.autofit_btn = QPushButton("Start Picking")
        self.autofit_btn.setCheckable(True)
        self.autofit_btn.setToolTip("Toggle point-pair picking mode")
        self.autofit_btn.toggled.connect(self._on_autofit_toggled)
        autofit_layout.addWidget(self.autofit_btn)

        self.pairs_label = QLabel("Pairs: 0")
        autofit_layout.addWidget(self.pairs_label)

        autofit_btn_layout = QHBoxLayout()
        self.compute_btn = QPushButton("Compute")
        self.compute_btn.setEnabled(False)
        self.compute_btn.setToolTip("Compute best-fit adjustment from picked pairs")
        self.compute_btn.clicked.connect(self.autofit_compute_requested.emit)
        autofit_btn_layout.addWidget(self.compute_btn)

        self.clear_pairs_btn = QPushButton("Clear")
        self.clear_pairs_btn.setEnabled(False)
        self.clear_pairs_btn.setToolTip("Clear all picked point pairs")
        self.clear_pairs_btn.clicked.connect(self.autofit_clear_requested.emit)
        autofit_btn_layout.addWidget(self.clear_pairs_btn)

        autofit_layout.addLayout(autofit_btn_layout)
        layout.addWidget(autofit_group)

        # Keyboard hints
        hints_frame = QFrame()
        hints_frame.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Sunken)
        hints_layout = QVBoxLayout(hints_frame)
        hints_layout.setContentsMargins(6, 6, 6, 6)
        hints_layout.setSpacing(2)

        hints_title = QLabel("Keyboard Controls:")
        hints_title_font = QFont()
        hints_title_font.setBold(True)
        hints_title_font.setPointSize(hints_title_font.pointSize() - 1)
        hints_title.setFont(hints_title_font)
        hints_layout.addWidget(hints_title)

        hint_font = QFont()
        hint_font.setPointSize(hint_font.pointSize() - 1)

        hints = [
            ("← → ↑ ↓", "Move"),
            ("[ ]", "Rotate"),
            ("+ −", "Scale"),
            ("< >", "Stretch X"),
            (", .", "Stretch Y"),
            ("; :", "Shear X (perspective)"),
            ("{ }", "Shear Y"),
            ("Ctrl", "5× faster"),
            ("Esc", "Reset"),
        ]

        for key, action in hints:
            hint_layout = QHBoxLayout()
            hint_layout.setSpacing(8)

            key_label = QLabel(key)
            key_label.setFont(hint_font)
            key_label.setMinimumWidth(60)
            hint_layout.addWidget(key_label)

            action_label = QLabel(action)
            action_label.setFont(hint_font)
            action_label.setStyleSheet("color: gray;")
            hint_layout.addWidget(action_label)

            hint_layout.addStretch()
            hints_layout.addLayout(hint_layout)

        layout.addWidget(hints_frame)

        # Stretch to push everything up
        layout.addStretch()

    def update_display(self, adjustment: Optional[TransformAdjustment]):
        """
        Update the displayed adjustment values.

        Args:
            adjustment: Current adjustment or None
        """
        if adjustment is None:
            self.translation_label.setText("(0.0, 0.0) px")
            self.rotation_label.setText("0.00°")
            self.scale_label.setText("1.0000 × 1.0000")
            self.shear_label.setText("(0.0000, 0.0000)")
            return

        self.translation_label.setText(
            f"({adjustment.translation_x:.1f}, {adjustment.translation_y:.1f}) px"
        )
        self.rotation_label.setText(f"{adjustment.rotation:.2f}°")
        self.scale_label.setText(
            f"{adjustment.scale_x:.4f} × {adjustment.scale_y:.4f}"
        )
        self.shear_label.setText(
            f"({adjustment.shear_x:.4f}, {adjustment.shear_y:.4f})"
        )

    def set_enabled(self, enabled: bool):
        """Enable or disable the panel controls."""
        self.reset_btn.setEnabled(enabled)
        self.apply_btn.setEnabled(enabled)
        self.autofit_btn.setEnabled(enabled)
        if not enabled:
            self.autofit_btn.setChecked(False)
            self.compute_btn.setEnabled(False)
            self.clear_pairs_btn.setEnabled(False)

    def update_pair_count(self, count: int):
        """Update displayed pair count and enable/disable compute button."""
        self.pairs_label.setText(f"Pairs: {count}")
        self.compute_btn.setEnabled(count >= 3)
        self.clear_pairs_btn.setEnabled(count > 0)

    def _on_autofit_toggled(self, checked: bool):
        """Handle auto-fit button toggle."""
        self.autofit_btn.setText("Stop Picking" if checked else "Start Picking")
        self.autofit_toggled.emit(checked)

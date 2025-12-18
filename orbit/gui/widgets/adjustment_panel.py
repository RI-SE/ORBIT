"""
Adjustment panel widget for ORBIT.

Displays current transformation adjustment values and provides controls
for interactive alignment of imported OSM data with the aerial image.
"""

from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QGroupBox, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

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
            ("Shift", "Coarse (10×)"),
            ("Ctrl", "Fine (0.1×)"),
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
            return

        self.translation_label.setText(
            f"({adjustment.translation_x:.1f}, {adjustment.translation_y:.1f}) px"
        )
        self.rotation_label.setText(f"{adjustment.rotation:.2f}°")
        self.scale_label.setText(
            f"{adjustment.scale_x:.4f} × {adjustment.scale_y:.4f}"
        )

    def set_enabled(self, enabled: bool):
        """Enable or disable the panel controls."""
        self.reset_btn.setEnabled(enabled)
        self.apply_btn.setEnabled(enabled)

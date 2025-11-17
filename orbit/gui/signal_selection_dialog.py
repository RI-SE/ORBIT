"""
Dialog for selecting signal type when placing a new signal.
"""

from PyQt6.QtWidgets import (QHBoxLayout, QGroupBox,
                            QPushButton, QGridLayout, QVBoxLayout)
from PyQt6.QtGui import QIcon
from models.signal import SignalType, SpeedUnit
from gui.signal_graphics import create_signal_pixmap
from gui.base_dialog import BaseDialog


class SignalSelectionDialog(BaseDialog):
    """
    Dialog for selecting the type and value of a signal to place.

    User can choose:
    - Give Way sign
    - Speed Limit sign (with speed value: 30-120)
    """

    def __init__(self, parent=None):
        super().__init__("Select Signal Type", parent)
        self.selected_type = None
        self.selected_value = None
        self.selected_unit = SpeedUnit.KMH

        self.setup_ui()
        self.load_properties()

    def setup_ui(self):
        """Create the dialog UI."""
        # Warning Signs section
        warning_group = QGroupBox("Warning Signs")
        warning_layout = QHBoxLayout()

        self.give_way_btn = QPushButton()
        pixmap = create_signal_pixmap(SignalType.GIVE_WAY, size=64)
        self.give_way_btn.setIcon(QIcon(pixmap))
        self.give_way_btn.setIconSize(pixmap.size())
        self.give_way_btn.setText("Give Way")
        self.give_way_btn.setFixedSize(120, 100)
        self.give_way_btn.clicked.connect(self.select_give_way)
        warning_layout.addWidget(self.give_way_btn)
        warning_layout.addStretch()

        warning_group.setLayout(warning_layout)
        self.get_main_layout().addWidget(warning_group)

        # Speed Limit section
        speed_group = QGroupBox("Speed Limits")
        speed_layout = QVBoxLayout()

        # Speed values grid
        speed_values = [30, 40, 50, 60, 70, 80, 90, 100, 110, 120]
        grid = QGridLayout()

        self.speed_buttons = []
        for i, speed in enumerate(speed_values):
            btn = QPushButton()
            pixmap = create_signal_pixmap(SignalType.SPEED_LIMIT, speed, size=48)
            btn.setIcon(QIcon(pixmap))
            btn.setIconSize(pixmap.size())
            btn.setText(f"{speed}")
            btn.setFixedSize(90, 80)
            btn.clicked.connect(lambda checked, s=speed: self.select_speed_limit(s))
            self.speed_buttons.append(btn)

            row = i // 5
            col = i % 5
            grid.addWidget(btn, row, col)

        speed_layout.addLayout(grid)
        speed_group.setLayout(speed_layout)
        self.get_main_layout().addWidget(speed_group)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        self.get_main_layout().addLayout(button_layout)

    def load_properties(self):
        """No properties to load for selection dialog."""
        pass

    def select_give_way(self):
        """Handle Give Way sign selection."""
        self.selected_type = SignalType.GIVE_WAY
        self.selected_value = None
        self.accept()

    def select_speed_limit(self, speed: int):
        """Handle speed limit selection."""
        self.selected_type = SignalType.SPEED_LIMIT
        self.selected_value = speed
        self.accept()

    def get_selection(self):
        """
        Get the selected signal type and value.

        Returns:
            Tuple of (SignalType, value, SpeedUnit) or (None, None, None) if cancelled
        """
        if self.selected_type:
            return (self.selected_type, self.selected_value, self.selected_unit)
        return (None, None, None)

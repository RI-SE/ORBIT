"""Combo box utility functions for ORBIT dialogs.

Provides helper functions for common QComboBox operations to reduce
code duplication across dialog classes.
"""

from typing import Any

from PyQt6.QtWidgets import QComboBox


def set_combo_by_data(combo: QComboBox, data: Any) -> bool:
    """Set combo box selection by item data value.

    Iterates through combo box items and selects the one whose
    itemData matches the provided data value.

    Args:
        combo: The QComboBox to set the selection on.
        data: The data value to match against itemData.

    Returns:
        True if a matching item was found and selected, False otherwise.

    Example:
        # Instead of:
        for i in range(self.combo.count()):
            if self.combo.itemData(i) == some_value:
                self.combo.setCurrentIndex(i)
                break

        # Use:
        set_combo_by_data(self.combo, some_value)
    """
    for i in range(combo.count()):
        if combo.itemData(i) == data:
            combo.setCurrentIndex(i)
            return True
    return False

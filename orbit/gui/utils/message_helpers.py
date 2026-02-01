"""
Helper functions for displaying message dialogs.

This module provides consistent, reusable functions for showing error,
warning, information, and confirmation dialogs throughout the application.

All functions use QMessageBox internally with consistent styling and behavior.
"""

from typing import Optional

from PyQt6.QtWidgets import QMessageBox, QWidget


def show_error(
    parent: Optional[QWidget],
    message: str,
    title: str = "Error",
    details: Optional[str] = None
) -> None:
    """
    Show an error dialog with a critical icon.

    Args:
        parent: Parent widget (can be None)
        message: Main error message to display
        title: Dialog window title (default: "Error")
        details: Optional detailed error information (shown in expandable section)

    Example:
        show_error(self, "Failed to load file.", "Load Error",
                   details="FileNotFoundError: /path/to/file.txt")
    """
    msg = QMessageBox(parent)
    msg.setIcon(QMessageBox.Icon.Critical)
    msg.setWindowTitle(title)
    msg.setText(message)
    if details:
        msg.setDetailedText(details)
    msg.exec()


def show_warning(
    parent: Optional[QWidget],
    message: str,
    title: str = "Warning"
) -> None:
    """
    Show a warning dialog with a warning icon.

    Args:
        parent: Parent widget (can be None)
        message: Warning message to display
        title: Dialog window title (default: "Warning")

    Example:
        show_warning(self, "No control points defined.", "No Georeferencing")
    """
    QMessageBox.warning(parent, title, message)


def show_info(
    parent: Optional[QWidget],
    message: str,
    title: str = "Information"
) -> None:
    """
    Show an information dialog with an info icon.

    Args:
        parent: Parent widget (can be None)
        message: Information message to display
        title: Dialog window title (default: "Information")

    Example:
        show_info(self, "Export completed successfully!", "Export Complete")
    """
    QMessageBox.information(parent, title, message)


def ask_yes_no(
    parent: Optional[QWidget],
    question: str,
    title: str = "Confirm"
) -> bool:
    """
    Show a yes/no question dialog and return True if user clicked Yes.

    Args:
        parent: Parent widget (can be None)
        question: Question to ask the user
        title: Dialog window title (default: "Confirm")

    Returns:
        True if user clicked Yes, False if user clicked No

    Example:
        if ask_yes_no(self, "Are you sure you want to delete this?", "Confirm Delete"):
            # User clicked Yes
            perform_delete()
    """
    result = QMessageBox.question(
        parent,
        title,
        question,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No  # Default to No for safety
    )
    return result == QMessageBox.StandardButton.Yes


def ask_yes_no_cancel(
    parent: Optional[QWidget],
    question: str,
    title: str = "Confirm"
) -> Optional[bool]:
    """
    Show a yes/no/cancel question dialog.

    Args:
        parent: Parent widget (can be None)
        question: Question to ask the user
        title: Dialog window title (default: "Confirm")

    Returns:
        True if user clicked Yes
        False if user clicked No
        None if user clicked Cancel

    Example:
        result = ask_yes_no_cancel(self, "Save changes?", "Unsaved Changes")
        if result is True:
            save_changes()
        elif result is False:
            discard_changes()
        else:  # result is None
            # User cancelled, do nothing
            return
    """
    result = QMessageBox.question(
        parent,
        title,
        question,
        QMessageBox.StandardButton.Yes |
        QMessageBox.StandardButton.No |
        QMessageBox.StandardButton.Cancel,
        QMessageBox.StandardButton.Cancel  # Default to Cancel for safety
    )
    if result == QMessageBox.StandardButton.Yes:
        return True
    elif result == QMessageBox.StandardButton.No:
        return False
    else:  # Cancel
        return None


def ask_ok_cancel(
    parent: Optional[QWidget],
    message: str,
    title: str = "Confirm"
) -> bool:
    """
    Show an OK/Cancel dialog and return True if user clicked OK.

    Args:
        parent: Parent widget (can be None)
        message: Message to display
        title: Dialog window title (default: "Confirm")

    Returns:
        True if user clicked OK, False if user clicked Cancel

    Example:
        if ask_ok_cancel(self, "This will clear all data.", "Clear All"):
            clear_all_data()
    """
    result = QMessageBox.question(
        parent,
        title,
        message,
        QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
        QMessageBox.StandardButton.Cancel  # Default to Cancel for safety
    )
    return result == QMessageBox.StandardButton.Ok


def show_error_with_traceback(
    parent: Optional[QWidget],
    message: str,
    exception: Exception,
    title: str = "Error"
) -> None:
    """
    Show an error dialog with exception traceback in details section.

    Args:
        parent: Parent widget (can be None)
        message: User-friendly error message
        exception: The exception that was caught
        title: Dialog window title (default: "Error")

    Example:
        try:
            risky_operation()
        except Exception as e:
            show_error_with_traceback(self, "Operation failed.", e)
    """
    import traceback
    details = "".join(traceback.format_exception(type(exception), exception, exception.__traceback__))
    show_error(parent, message, title, details=details)

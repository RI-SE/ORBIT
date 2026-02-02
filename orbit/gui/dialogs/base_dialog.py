"""
Base dialog class for ORBIT.

Provides common functionality and structure for property editing dialogs.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class InfoIconLabel(QWidget):
    """
    A label with an info icon that shows tooltip on hover.

    Used to replace inline explanatory text with a compact icon
    that shows the help text on hover.
    """

    def __init__(self, title: str, info_text: str, bold: bool = True, parent=None):
        """
        Create a label with an info icon.

        Args:
            title: The visible label text
            info_text: Text to show in tooltip when hovering over info icon
            bold: Whether to make the title bold (default True)
            parent: Parent widget
        """
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Title label
        if bold:
            title_label = QLabel(f"<b>{title}</b>")
        else:
            title_label = QLabel(title)
        layout.addWidget(title_label)

        # Info icon button
        info_btn = QToolButton()
        info_btn.setText("ⓘ")
        info_btn.setToolTip(info_text)
        info_btn.setStyleSheet(
            "QToolButton { border: none; color: #666; font-size: 12px; }"
            "QToolButton:hover { color: #333; }"
        )
        info_btn.setCursor(Qt.CursorShape.WhatsThisCursor)
        layout.addWidget(info_btn)

        layout.addStretch()


class BaseDialog(QDialog):
    """
    Base class for property editing dialogs.

    Provides standard dialog structure with:
    - Main vertical layout
    - Helper method to add form groups (QGroupBox with QFormLayout)
    - Standard OK/Cancel buttons
    - Abstract method for loading properties

    Subclasses should:
    1. Call super().__init__(title, parent) in their __init__
    2. Store their data model
    3. Call setup_ui() to create widgets
    4. Call load_properties() to populate widgets
    5. Override load_properties() to load data into widgets
    6. Override accept() to save data back to model
    """

    def __init__(self, title: str, parent=None, min_width: int = None, min_height: int = None):
        """
        Initialize base dialog.

        Args:
            title: Window title
            parent: Parent widget
            min_width: Minimum width in pixels (optional)
            min_height: Minimum height in pixels (optional)
        """
        super().__init__(parent)
        self.setWindowTitle(title)

        if min_width:
            self.setMinimumWidth(min_width)
        if min_height:
            self.setMinimumHeight(min_height)

        # Create main layout
        self._main_layout = QVBoxLayout(self)

        # Button box will be added at the end
        self._button_box = None

    def add_form_group(self, title: str) -> QFormLayout:
        """
        Add a QGroupBox with QFormLayout and return the form layout.

        This is a convenience method for creating standard form sections.
        The group box is automatically added to the main layout before the
        button box (if it exists).

        Args:
            title: Title for the group box

        Returns:
            QFormLayout that can be used to add form rows

        Example:
            layout = self.add_form_group("Basic Properties")
            layout.addRow("Name:", self.name_edit)
            layout.addRow("Type:", self.type_combo)
        """
        group = QGroupBox(title)
        form_layout = QFormLayout()
        form_layout.setVerticalSpacing(4)  # Tighter row spacing
        group.setLayout(form_layout)

        # Insert before button box if it exists, otherwise append
        if self._button_box:
            insert_index = self._main_layout.count() - 1
            self._main_layout.insertWidget(insert_index, group)
        else:
            self._main_layout.addWidget(group)

        return form_layout

    def add_form_group_with_info(self, title: str, info_text: str) -> QFormLayout:
        """
        Add a QGroupBox with title + info icon tooltip.

        Similar to add_form_group() but includes an info icon next to the title
        that shows explanatory text on hover.

        Args:
            title: Title for the group box
            info_text: Text to show in tooltip when hovering over info icon

        Returns:
            QFormLayout that can be used to add form rows
        """
        group = QGroupBox()
        group_layout = QVBoxLayout()
        group_layout.setContentsMargins(10, 10, 10, 10)
        group_layout.setSpacing(6)

        # Title with info icon
        title_widget = InfoIconLabel(title, info_text)
        group_layout.addWidget(title_widget)

        # Form layout for content
        form_layout = QFormLayout()
        form_layout.setVerticalSpacing(4)
        group_layout.addLayout(form_layout)

        group.setLayout(group_layout)

        # Insert before button box if it exists, otherwise append
        if self._button_box:
            insert_index = self._main_layout.count() - 1
            self._main_layout.insertWidget(insert_index, group)
        else:
            self._main_layout.addWidget(group)

        return form_layout

    def create_button_box(self, buttons=None):
        """
        Create standard OK/Cancel button box.

        Should be called at the end of setup_ui() in subclasses.
        Creates a QDialogButtonBox with OK and Cancel buttons and
        connects them to accept() and reject().

        Args:
            buttons: Optional StandardButton flags. Defaults to Ok | Cancel
        """
        if buttons is None:
            buttons = (
                QDialogButtonBox.StandardButton.Ok |
                QDialogButtonBox.StandardButton.Cancel
            )

        self._button_box = QDialogButtonBox(buttons)
        self._button_box.accepted.connect(self.accept)
        self._button_box.rejected.connect(self.reject)
        self._main_layout.addWidget(self._button_box)

    def get_main_layout(self) -> QVBoxLayout:
        """
        Get the main layout for adding custom widgets.

        Use this when you need to add widgets that aren't form groups,
        such as lists, tables, or custom layouts.

        Returns:
            The main QVBoxLayout
        """
        return self._main_layout

    def load_properties(self):
        """
        Load data into form widgets.

        Subclasses must implement this method to populate widgets
        from their data model.

        Example:
            def load_properties(self):
                self.name_edit.setText(self.road.name)
                self.speed_spin.setValue(self.road.speed_limit)
        """
        raise NotImplementedError("Subclasses must implement load_properties()")

    def setup_ui(self):
        """
        Setup the dialog UI.

        Subclasses must implement this method to create all widgets
        and layouts. Should call create_button_box() at the end.

        Example:
            def setup_ui(self):
                # Create widgets
                self.name_edit = QLineEdit()

                # Add form groups
                layout = self.add_form_group("Basic Properties")
                layout.addRow("Name:", self.name_edit)

                # Create buttons
                self.create_button_box()
        """
        raise NotImplementedError("Subclasses must implement setup_ui()")

    @classmethod
    def show_and_accept(cls, *args, parent=None, **kwargs) -> bool:
        """
        Convenience method to show dialog and return True if accepted.

        This is a template method that subclasses can use in their static
        edit methods for a consistent pattern.

        Args:
            *args: Positional arguments for dialog constructor
            parent: Parent widget (passed as keyword argument)
            **kwargs: Additional keyword arguments for dialog constructor

        Returns:
            True if user clicked OK/Accept, False if cancelled

        Example:
            @classmethod
            def edit_lane(cls, lane, project=None, parent=None):
                '''Show dialog to edit lane properties.'''
                return cls.show_and_accept(lane, project, parent=parent)
        """
        dialog = cls(*args, parent=parent, **kwargs)
        return dialog.exec() == QDialog.DialogCode.Accepted

    # Note: accept() should be overridden in subclasses to save data
    # def accept(self):
    #     # Save data to model
    #     self.model.name = self.name_edit.text()
    #     super().accept()

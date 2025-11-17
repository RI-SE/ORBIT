"""
Dialog for selecting object type when placing a new object.
"""

from typing import Optional

from PyQt6.QtWidgets import (QHBoxLayout, QGroupBox,
                            QPushButton, QLabel, QGridLayout)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
from models.object import ObjectType
from gui.base_dialog import BaseDialog


class ObjectSelectionDialog(BaseDialog):
    """
    Dialog for selecting the type of object to place.

    User can choose from:
    - Road Furniture: Lamppost, Guardrail
    - Road Environment: Building, Broadleaf Tree, Conifer, Bush
    """

    def __init__(self, parent=None):
        super().__init__("Select Object Type", parent)
        self.selected_type = None

        self.setup_ui()
        self.load_properties()

    def setup_ui(self):
        """Create the dialog UI."""
        # Road Furniture section
        furniture_group = QGroupBox("Road Furniture")
        furniture_layout = QHBoxLayout()

        # Lamppost button
        self.lamppost_btn = QPushButton()
        pixmap = self.create_simple_icon(ObjectType.LAMPPOST, size=64)
        self.lamppost_btn.setIcon(QIcon(pixmap))
        self.lamppost_btn.setIconSize(pixmap.size())
        self.lamppost_btn.setText("Lamppost")
        self.lamppost_btn.setFixedSize(120, 100)
        self.lamppost_btn.clicked.connect(lambda: self.select_type(ObjectType.LAMPPOST))
        furniture_layout.addWidget(self.lamppost_btn)

        # Guardrail button
        self.guardrail_btn = QPushButton()
        pixmap = self.create_simple_icon(ObjectType.GUARDRAIL, size=64)
        self.guardrail_btn.setIcon(QIcon(pixmap))
        self.guardrail_btn.setIconSize(pixmap.size())
        self.guardrail_btn.setText("Guardrail")
        self.guardrail_btn.setFixedSize(120, 100)
        self.guardrail_btn.clicked.connect(lambda: self.select_type(ObjectType.GUARDRAIL))
        furniture_layout.addWidget(self.guardrail_btn)

        furniture_layout.addStretch()
        furniture_group.setLayout(furniture_layout)
        self.get_main_layout().addWidget(furniture_group)

        # Road Environment section
        environment_group = QGroupBox("Road Environment")
        environment_layout = QGridLayout()

        # Building button
        self.building_btn = QPushButton()
        pixmap = self.create_simple_icon(ObjectType.BUILDING, size=48)
        self.building_btn.setIcon(QIcon(pixmap))
        self.building_btn.setIconSize(pixmap.size())
        self.building_btn.setText("Building")
        self.building_btn.setFixedSize(110, 90)
        self.building_btn.clicked.connect(lambda: self.select_type(ObjectType.BUILDING))
        environment_layout.addWidget(self.building_btn, 0, 0)

        # Broadleaf tree button
        self.tree_broadleaf_btn = QPushButton()
        pixmap = self.create_simple_icon(ObjectType.TREE_BROADLEAF, size=48)
        self.tree_broadleaf_btn.setIcon(QIcon(pixmap))
        self.tree_broadleaf_btn.setIconSize(pixmap.size())
        self.tree_broadleaf_btn.setText("Broadleaf Tree")
        self.tree_broadleaf_btn.setFixedSize(110, 90)
        self.tree_broadleaf_btn.clicked.connect(lambda: self.select_type(ObjectType.TREE_BROADLEAF))
        environment_layout.addWidget(self.tree_broadleaf_btn, 0, 1)

        # Conifer button
        self.conifer_btn = QPushButton()
        pixmap = self.create_simple_icon(ObjectType.TREE_CONIFER, size=48)
        self.conifer_btn.setIcon(QIcon(pixmap))
        self.conifer_btn.setIconSize(pixmap.size())
        self.conifer_btn.setText("Conifer")
        self.conifer_btn.setFixedSize(110, 90)
        self.conifer_btn.clicked.connect(lambda: self.select_type(ObjectType.TREE_CONIFER))
        environment_layout.addWidget(self.conifer_btn, 0, 2)

        # Bush button
        self.bush_btn = QPushButton()
        pixmap = self.create_simple_icon(ObjectType.BUSH, size=48)
        self.bush_btn.setIcon(QIcon(pixmap))
        self.bush_btn.setIconSize(pixmap.size())
        self.bush_btn.setText("Bush")
        self.bush_btn.setFixedSize(110, 90)
        self.bush_btn.clicked.connect(lambda: self.select_type(ObjectType.BUSH))
        environment_layout.addWidget(self.bush_btn, 1, 0)

        environment_group.setLayout(environment_layout)
        self.get_main_layout().addWidget(environment_group)

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

    def create_simple_icon(self, object_type: ObjectType, size: int = 48) -> QPixmap:
        """
        Create a simple icon representing the object type.

        Args:
            object_type: Type of object
            size: Icon size in pixels

        Returns:
            QPixmap with the icon rendered
        """
        from gui.object_graphics import get_object_color

        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        color = get_object_color(object_type)
        painter.setPen(color.darker(120))
        painter.setBrush(color)

        margin = 4
        center = size / 2

        if object_type == ObjectType.LAMPPOST:
            # Small circle with line
            radius = 4
            painter.drawEllipse(int(center - radius), int(center - radius), radius * 2, radius * 2)
            painter.drawLine(int(center), int(center), int(center + 12), int(center))

        elif object_type == ObjectType.GUARDRAIL:
            # Horizontal line with hatching
            painter.drawLine(margin, int(center), size - margin, int(center))
            for x in range(margin + 5, size - margin, 10):
                painter.drawLine(x, int(center - 5), x, int(center + 5))

        elif object_type == ObjectType.BUILDING:
            # Rectangle
            painter.drawRect(margin + 5, margin + 8, size - margin * 2 - 10, size - margin * 2 - 16)

        elif object_type == ObjectType.TREE_BROADLEAF:
            # Circle (tree crown)
            radius = (size - margin * 2) // 2
            painter.drawEllipse(int(center - radius), int(center - radius), radius * 2, radius * 2)

        elif object_type == ObjectType.TREE_CONIFER:
            # Triangle (cone from top)
            from PyQt6.QtGui import QPolygonF
            from PyQt6.QtCore import QPointF
            poly = QPolygonF([
                QPointF(center, margin + 5),
                QPointF(margin + 8, size - margin - 5),
                QPointF(size - margin - 8, size - margin - 5)
            ])
            painter.drawPolygon(poly)

        elif object_type == ObjectType.BUSH:
            # Small circle
            radius = (size - margin * 4) // 2
            painter.drawEllipse(int(center - radius), int(center - radius), radius * 2, radius * 2)

        painter.end()
        return pixmap

    def select_type(self, object_type: ObjectType):
        """Handle object type selection."""
        self.selected_type = object_type
        self.accept()

    def get_selection(self) -> Optional[ObjectType]:
        """
        Get the selected object type.

        Returns:
            ObjectType or None if cancelled
        """
        return self.selected_type

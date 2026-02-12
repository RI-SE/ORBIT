"""
Wizard dialog for creating roundabouts.

Allows users to manually create roundabouts by specifying geometry
and configuration parameters.
"""

from typing import List, Optional, Tuple

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
)

from ..utils import show_warning
from .base_dialog import BaseDialog, InfoIconLabel


class RoundaboutWizardDialog(BaseDialog):
    """
    Wizard dialog for creating roundabouts.

    Allows configuration of:
    - Center point (click on map)
    - Radius
    - Number of lanes
    - Traffic direction
    - Approach road selection
    """

    # Signal emitted when user wants to pick a point on the map
    pick_center_requested = pyqtSignal()

    def __init__(self, available_roads: List[Tuple[str, str]], parent=None,
                 scale_factor: Optional[float] = None):
        """
        Initialize roundabout wizard.

        Args:
            available_roads: List of (road_id, road_name) tuples for approach selection
            parent: Parent widget
            scale_factor: Optional scale factor in meters/pixel for conversion
        """
        super().__init__("Create Roundabout", parent, min_width=450, min_height=500)
        self.setModal(True)

        self.available_roads = available_roads
        self.scale_factor = scale_factor

        # Roundabout parameters
        self.center_point: Optional[Tuple[float, float]] = None
        self.selected_road_ids: List[str] = []

        self.setup_ui()
        self.load_properties()

    def setup_ui(self):
        """Create dialog UI."""
        # Center point section
        center_group = QGroupBox("Center Point")
        center_layout = QVBoxLayout()

        # Center coordinates display
        coord_layout = QHBoxLayout()
        coord_layout.addWidget(QLabel("X:"))
        self.center_x_spin = QDoubleSpinBox()
        self.center_x_spin.setRange(0, 100000)
        self.center_x_spin.setDecimals(1)
        self.center_x_spin.setSuffix(" px")
        self.center_x_spin.valueChanged.connect(self._on_center_changed)
        coord_layout.addWidget(self.center_x_spin)

        coord_layout.addWidget(QLabel("Y:"))
        self.center_y_spin = QDoubleSpinBox()
        self.center_y_spin.setRange(0, 100000)
        self.center_y_spin.setDecimals(1)
        self.center_y_spin.setSuffix(" px")
        self.center_y_spin.valueChanged.connect(self._on_center_changed)
        coord_layout.addWidget(self.center_y_spin)

        center_layout.addLayout(coord_layout)

        # Pick from map button
        self.pick_center_btn = QPushButton("Pick from Map...")
        self.pick_center_btn.setToolTip("Click on the image to set the center point")
        self.pick_center_btn.clicked.connect(self._on_pick_center)
        center_layout.addWidget(self.pick_center_btn)

        center_group.setLayout(center_layout)
        self.get_main_layout().addWidget(center_group)

        # Geometry section
        geom_group = QGroupBox("Geometry")
        geom_layout = QVBoxLayout()

        # Radius
        radius_layout = QHBoxLayout()
        radius_layout.addWidget(QLabel("Radius:"))
        self.radius_spin = QDoubleSpinBox()
        self.radius_spin.setRange(10, 5000)
        self.radius_spin.setValue(50)
        self.radius_spin.setDecimals(1)
        self.radius_spin.setSuffix(" px")
        self.radius_spin.setToolTip("Radius of the roundabout ring")
        self.radius_spin.valueChanged.connect(self._update_meters_display)
        radius_layout.addWidget(self.radius_spin)

        # Meters display
        self.radius_meters_label = QLabel("")
        radius_layout.addWidget(self.radius_meters_label)
        radius_layout.addStretch()
        geom_layout.addLayout(radius_layout)

        # Ring points
        points_layout = QHBoxLayout()
        points_layout.addWidget(QLabel("Ring Resolution:"))
        self.ring_points_spin = QSpinBox()
        self.ring_points_spin.setRange(12, 72)
        self.ring_points_spin.setValue(24)
        self.ring_points_spin.setToolTip("Number of points in the ring polygon (higher = smoother)")
        points_layout.addWidget(self.ring_points_spin)
        points_layout.addStretch()
        geom_layout.addLayout(points_layout)

        geom_group.setLayout(geom_layout)
        self.get_main_layout().addWidget(geom_group)

        # Lane configuration section
        lane_group = QGroupBox("Lane Configuration")
        lane_layout = QVBoxLayout()

        # Number of lanes
        lanes_layout = QHBoxLayout()
        lanes_layout.addWidget(QLabel("Lanes:"))
        self.lane_count_spin = QSpinBox()
        self.lane_count_spin.setRange(1, 4)
        self.lane_count_spin.setValue(1)
        self.lane_count_spin.setToolTip("Number of lanes in the roundabout ring")
        lanes_layout.addWidget(self.lane_count_spin)
        lanes_layout.addStretch()
        lane_layout.addLayout(lanes_layout)

        # Lane width
        width_layout = QHBoxLayout()
        width_layout.addWidget(QLabel("Lane Width:"))
        self.lane_width_spin = QDoubleSpinBox()
        self.lane_width_spin.setRange(2.0, 5.0)
        self.lane_width_spin.setValue(3.5)
        self.lane_width_spin.setSingleStep(0.1)
        self.lane_width_spin.setSuffix(" m")
        self.lane_width_spin.setToolTip("Width of each lane in meters")
        width_layout.addWidget(self.lane_width_spin)
        width_layout.addStretch()
        lane_layout.addLayout(width_layout)

        lane_group.setLayout(lane_layout)
        self.get_main_layout().addWidget(lane_group)

        # Traffic direction section
        traffic_group = QGroupBox("Traffic Direction")
        traffic_layout = QVBoxLayout()

        self.ccw_radio = QRadioButton("Counter-clockwise (right-hand traffic)")
        self.ccw_radio.setToolTip("Standard for right-hand traffic countries (Sweden, USA, etc.)")
        self.ccw_radio.setChecked(True)
        traffic_layout.addWidget(self.ccw_radio)

        self.cw_radio = QRadioButton("Clockwise (left-hand traffic)")
        self.cw_radio.setToolTip("For left-hand traffic countries (UK, Japan, etc.)")
        traffic_layout.addWidget(self.cw_radio)

        traffic_group.setLayout(traffic_layout)
        self.get_main_layout().addWidget(traffic_group)

        # Approach roads section
        approach_group = QGroupBox()
        approach_layout = QVBoxLayout()

        approach_title = InfoIconLabel(
            "Approach Roads (Optional)",
            "Select roads that connect to this roundabout. "
            "Leave empty to create standalone roundabout."
        )
        approach_layout.addWidget(approach_title)

        self.road_list = QListWidget()
        self.road_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.road_list.setMaximumHeight(120)

        for road_id, road_name in self.available_roads:
            item = QListWidgetItem(road_name)
            item.setData(Qt.ItemDataRole.UserRole, road_id)
            self.road_list.addItem(item)

        approach_layout.addWidget(self.road_list)

        approach_group.setLayout(approach_layout)
        self.get_main_layout().addWidget(approach_group)

        # Create buttons
        self.create_button_box()

        # Update meters display
        self._update_meters_display()

    def load_properties(self):
        """Load default properties."""
        pass  # Defaults are set in setup_ui

    def _on_center_changed(self):
        """Handle center coordinate change."""
        self.center_point = (
            self.center_x_spin.value(),
            self.center_y_spin.value()
        )

    def _on_pick_center(self):
        """Request center point pick from map."""
        self.pick_center_requested.emit()

    def set_center_point(self, x: float, y: float):
        """
        Set the center point from external source (e.g., map click).

        Args:
            x: X coordinate in pixels
            y: Y coordinate in pixels
        """
        self.center_x_spin.setValue(x)
        self.center_y_spin.setValue(y)
        self.center_point = (x, y)

    def _update_meters_display(self):
        """Update the meters display label."""
        if self.scale_factor and self.scale_factor > 0:
            radius_m = self.radius_spin.value() * self.scale_factor
            self.radius_meters_label.setText(f"≈ {radius_m:.1f} m")
        else:
            self.radius_meters_label.setText("")

    def get_roundabout_params(self) -> dict:
        """
        Get the configured roundabout parameters.

        Returns:
            Dictionary with roundabout configuration:
            - center: (x, y) tuple in pixels
            - radius: Radius in pixels
            - ring_points: Number of points in ring
            - lane_count: Number of lanes
            - lane_width: Lane width in meters
            - clockwise: True for clockwise traffic
            - approach_road_ids: List of selected road IDs
        """
        # Get selected approach roads
        selected_roads = []
        for item in self.road_list.selectedItems():
            road_id = item.data(Qt.ItemDataRole.UserRole)
            selected_roads.append(road_id)

        return {
            'center': self.center_point,
            'radius': self.radius_spin.value(),
            'ring_points': self.ring_points_spin.value(),
            'lane_count': self.lane_count_spin.value(),
            'lane_width': self.lane_width_spin.value(),
            'clockwise': self.cw_radio.isChecked(),
            'approach_road_ids': selected_roads
        }

    def accept(self):
        """Validate and accept dialog."""
        # Validate center point
        if self.center_point is None or (
            self.center_point[0] == 0 and self.center_point[1] == 0
        ):
            show_warning(self, "Please specify the roundabout center point.", "Missing Center Point")
            return

        # Validate radius
        if self.radius_spin.value() < 10:
            show_warning(self, "Radius must be at least 10 pixels.", "Invalid Radius")
            return

        super().accept()

    @classmethod
    def create_roundabout(cls, available_roads: List[Tuple[str, str]],
                         scale_factor: Optional[float] = None,
                         parent=None) -> Optional[dict]:
        """
        Show dialog to create a roundabout.

        Args:
            available_roads: List of (road_id, road_name) tuples
            scale_factor: Optional scale factor in meters/pixel
            parent: Parent widget

        Returns:
            Roundabout parameters dict if accepted, None if cancelled
        """
        dialog = cls(available_roads, parent, scale_factor)
        if dialog.exec() == cls.DialogCode.Accepted:
            return dialog.get_roundabout_params()
        return None

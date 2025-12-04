"""
Connecting road properties dialog for ORBIT.

Allows editing of connecting road properties including tangent adjustment for ParamPoly3D curves.
"""

from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QSpinBox, QComboBox,
    QLabel, QDoubleSpinBox, QPushButton
)

from orbit.models.connecting_road import ConnectingRoad
from orbit.models import Project
from .base_dialog import BaseDialog
from orbit.utils.geometry import generate_simple_connection_path
import math


class ConnectingRoadDialog(BaseDialog):
    """Dialog for editing connecting road properties."""

    def __init__(self, connecting_road: ConnectingRoad, project: Optional[Project] = None, parent=None):
        super().__init__("Connecting Road Properties", parent, min_width=500)

        self.connecting_road = connecting_road
        self.project = project
        self.setup_ui()
        self.load_properties()

    def setup_ui(self):
        """Setup the dialog UI."""
        # Connecting road identification (read-only)
        id_layout = self.add_form_group("Connection Information")

        # Get road names with IDs
        if self.project:
            pred_road = self.project.get_road(self.connecting_road.predecessor_road_id)
            succ_road = self.project.get_road(self.connecting_road.successor_road_id)
            pred_id_short = self.connecting_road.predecessor_road_id[:8]
            succ_id_short = self.connecting_road.successor_road_id[:8]
            pred_name = f"{pred_road.name} ({pred_id_short})" if pred_road and pred_road.name else f"Road {pred_id_short}"
            succ_name = f"{succ_road.name} ({succ_id_short})" if succ_road and succ_road.name else f"Road {succ_id_short}"
        else:
            pred_name = f"Road {self.connecting_road.predecessor_road_id[:8]}"
            succ_name = f"Road {self.connecting_road.successor_road_id[:8]}"

        self.connection_label = QLabel(f"{pred_name} → {succ_name}")
        self.connection_label.setStyleSheet("QLabel { font-weight: bold; }")
        id_layout.addRow("Connection:", self.connection_label)

        self.geometry_type_label = QLabel()
        id_layout.addRow("Geometry Type:", self.geometry_type_label)

        self.lane_count_label = QLabel()
        id_layout.addRow("Lanes:", self.lane_count_label)

        # Lane configuration
        lane_layout = self.add_form_group("Lane Configuration")

        # Lane count left
        self.lane_count_left_spin = QSpinBox()
        self.lane_count_left_spin.setRange(0, 4)
        self.lane_count_left_spin.setValue(self.connecting_road.lane_count_left)
        self.lane_count_left_spin.setToolTip("Number of left lanes (positive lane IDs)")
        lane_layout.addRow("Left Lanes:", self.lane_count_left_spin)

        # Lane count right
        self.lane_count_right_spin = QSpinBox()
        self.lane_count_right_spin.setRange(0, 4)
        self.lane_count_right_spin.setValue(self.connecting_road.lane_count_right)
        self.lane_count_right_spin.setToolTip("Number of right lanes (negative lane IDs)")
        lane_layout.addRow("Right Lanes:", self.lane_count_right_spin)

        # Width at start
        self.width_start_spin = QDoubleSpinBox()
        self.width_start_spin.setRange(0.5, 20.0)
        self.width_start_spin.setSingleStep(0.1)
        self.width_start_spin.setDecimals(2)
        self.width_start_spin.setSuffix(" m")
        start_width = self.connecting_road.lane_width_start or self.connecting_road.lane_width
        self.width_start_spin.setValue(start_width)
        self.width_start_spin.setToolTip("Lane width at the start of the connecting road (s=0)")
        lane_layout.addRow("Width at Start:", self.width_start_spin)

        # Width at end
        self.width_end_spin = QDoubleSpinBox()
        self.width_end_spin.setRange(0.5, 20.0)
        self.width_end_spin.setSingleStep(0.1)
        self.width_end_spin.setDecimals(2)
        self.width_end_spin.setSuffix(" m")
        end_width = self.connecting_road.lane_width_end or self.connecting_road.lane_width
        self.width_end_spin.setValue(end_width)
        self.width_end_spin.setToolTip("Lane width at the end of the connecting road")
        lane_layout.addRow("Width at End:", self.width_end_spin)

        # Contact points
        contact_layout = self.add_form_group("Contact Points")

        self.predecessor_contact_combo = QComboBox()
        self.predecessor_contact_combo.addItem("Start", "start")
        self.predecessor_contact_combo.addItem("End", "end")
        pred_contact = self.connecting_road.contact_point_start or "end"
        pred_index = 0 if pred_contact == "start" else 1
        self.predecessor_contact_combo.setCurrentIndex(pred_index)
        self.predecessor_contact_combo.setToolTip("Contact point on predecessor road")
        contact_layout.addRow("Predecessor Contact:", self.predecessor_contact_combo)

        self.successor_contact_combo = QComboBox()
        self.successor_contact_combo.addItem("Start", "start")
        self.successor_contact_combo.addItem("End", "end")
        succ_contact = self.connecting_road.contact_point_end or "start"
        succ_index = 0 if succ_contact == "start" else 1
        self.successor_contact_combo.setCurrentIndex(succ_index)
        self.successor_contact_combo.setToolTip("Contact point on successor road")
        contact_layout.addRow("Successor Contact:", self.successor_contact_combo)

        contact_info = QLabel("<i>Which end of each road this connection attaches to</i>")
        contact_info.setWordWrap(True)
        contact_info.setStyleSheet("color: gray;")
        contact_layout.addRow("", contact_info)

        # Geometry conversion (for polyline -> parampoly3 upgrade)
        if self.connecting_road.geometry_type == "polyline":
            conversion_layout = self.add_form_group("Geometry Upgrade")

            upgrade_info = QLabel(
                "<i>This connecting road uses legacy polyline geometry. "
                "Convert to ParamPoly3D for smooth curves with adjustable tangents.</i>"
            )
            upgrade_info.setWordWrap(True)
            upgrade_info.setStyleSheet("QLabel { color: #ff6600; font-style: italic; }")
            conversion_layout.addRow("", upgrade_info)

            self.convert_button = QPushButton("Convert to ParamPoly3D")
            self.convert_button.setToolTip("Upgrade this connecting road to use smooth parametric curves")
            self.convert_button.clicked.connect(self.on_convert_to_parampoly3)
            conversion_layout.addRow("", self.convert_button)

        # ParamPoly3D properties (only shown for parampoly3 geometry)
        if self.connecting_road.geometry_type == "parampoly3":
            curve_layout = self.add_form_group("Curve Parameters")

            # Tangent scale spinner
            self.tangent_scale_spin = QDoubleSpinBox()
            self.tangent_scale_spin.setRange(0.1, 5.0)
            self.tangent_scale_spin.setSingleStep(0.1)
            self.tangent_scale_spin.setValue(self.connecting_road.tangent_scale)
            self.tangent_scale_spin.setToolTip(
                "Controls the tightness of the curve. Lower values create tighter curves, "
                "higher values create wider, smoother curves."
            )
            curve_layout.addRow("Tangent Scale:", self.tangent_scale_spin)

            # Info label
            info_label = QLabel(
                "<i>Tangent scale controls how tight or wide the curve is. "
                "Adjust this value to fine-tune the connection path.</i>"
            )
            info_label.setWordWrap(True)
            info_label.setStyleSheet("QLabel { color: gray; font-style: italic; }")
            curve_layout.addRow("", info_label)

            # Regenerate button
            self.regenerate_button = QPushButton("Preview Curve")
            self.regenerate_button.setToolTip("Regenerate the curve with the new tangent scale")
            self.regenerate_button.clicked.connect(self.on_regenerate_curve)
            curve_layout.addRow("", self.regenerate_button)

        # Create standard OK/Cancel buttons
        self.create_button_box()

    def load_properties(self):
        """Load connecting road properties into the form."""
        # Set geometry type display
        if self.connecting_road.geometry_type == "parampoly3":
            geom_display = "ParamPoly3D (Parametric Cubic Curve)"
        else:
            geom_display = "Polyline (Linear Segments)"
        self.geometry_type_label.setText(geom_display)

        # Set lane count
        left = self.connecting_road.lane_count_left
        right = self.connecting_road.lane_count_right
        self.lane_count_label.setText(f"{left} left, {right} right")

    def on_convert_to_parampoly3(self):
        """Convert polyline geometry to ParamPoly3D."""
        if self.connecting_road.geometry_type != "polyline":
            return

        if not self.project:
            return

        if len(self.connecting_road.path) < 2:
            return

        # Get start and end points from existing polyline
        start_point = self.connecting_road.path[0]
        end_point = self.connecting_road.path[-1]

        # Calculate headings from first and last segments
        if len(self.connecting_road.path) >= 2:
            dx = self.connecting_road.path[1][0] - self.connecting_road.path[0][0]
            dy = self.connecting_road.path[1][1] - self.connecting_road.path[0][1]
            start_heading = math.atan2(dy, dx)
        else:
            start_heading = 0.0

        if len(self.connecting_road.path) >= 2:
            dx = self.connecting_road.path[-1][0] - self.connecting_road.path[-2][0]
            dy = self.connecting_road.path[-1][1] - self.connecting_road.path[-2][1]
            end_heading = math.atan2(dy, dx)
        else:
            end_heading = 0.0

        # Generate ParamPoly3D curve
        path, coeffs = generate_simple_connection_path(
            from_pos=start_point,
            from_heading=start_heading,
            to_pos=end_point,
            to_heading=end_heading,
            num_points=20,
            tangent_scale=1.0
        )

        # Update connecting road
        self.connecting_road.path = path
        aU, bU, cU, dU, aV, bV, cV, dV = coeffs
        self.connecting_road.aU = aU
        self.connecting_road.bU = bU
        self.connecting_road.cU = cU
        self.connecting_road.dU = dU
        self.connecting_road.aV = aV
        self.connecting_road.bV = bV
        self.connecting_road.cV = cV
        self.connecting_road.dV = dV
        self.connecting_road.p_range = 1.0
        self.connecting_road.tangent_scale = 1.0
        self.connecting_road.geometry_type = "parampoly3"

        # Update graphics if main window is parent
        if hasattr(self.parent(), 'image_view'):
            image_view = self.parent().image_view
            if self.connecting_road.id in image_view.connecting_road_centerline_items:
                image_view.connecting_road_centerline_items[self.connecting_road.id].update_graphics()
            if self.connecting_road.id in image_view.connecting_road_lanes_items:
                image_view.connecting_road_lanes_items[self.connecting_road.id].update_graphics()

        # Close and reopen dialog to show new UI
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            "Conversion Complete",
            "Connecting road has been converted to ParamPoly3D.\n\n"
            "The dialog will now close. Reopen it to adjust tangent parameters."
        )
        self.accept()

    def on_regenerate_curve(self):
        """Regenerate the ParamPoly3D curve with new tangent scale."""
        if self.connecting_road.geometry_type != "parampoly3":
            return

        if not self.project:
            return

        # Get predecessor and successor roads
        pred_road = self.project.get_road(self.connecting_road.predecessor_road_id)
        succ_road = self.project.get_road(self.connecting_road.successor_road_id)

        if not pred_road or not succ_road:
            return

        # Get endpoint information
        # We need to reconstruct the endpoint info to regenerate the curve
        # This is a simplified version - in practice, we'd need the full endpoint calculation
        # from junction_analyzer. For now, we'll use the existing path endpoints and
        # recalculate the curve coefficients.

        if len(self.connecting_road.path) < 2:
            return

        # Get start and end points (these should remain the same)
        start_point = self.connecting_road.path[0]
        end_point = self.connecting_road.path[-1]

        # Calculate headings from path
        # For start heading, use first segment
        if len(self.connecting_road.path) >= 2:
            dx = self.connecting_road.path[1][0] - self.connecting_road.path[0][0]
            dy = self.connecting_road.path[1][1] - self.connecting_road.path[0][1]
            start_heading = math.atan2(dy, dx)
        else:
            start_heading = 0.0

        # For end heading, use last segment
        if len(self.connecting_road.path) >= 2:
            dx = self.connecting_road.path[-1][0] - self.connecting_road.path[-2][0]
            dy = self.connecting_road.path[-1][1] - self.connecting_road.path[-2][1]
            end_heading = math.atan2(dy, dx)
        else:
            end_heading = 0.0

        # Get new tangent scale
        new_tangent_scale = self.tangent_scale_spin.value()

        # Regenerate the curve
        path, coeffs = generate_simple_connection_path(
            from_pos=start_point,
            from_heading=start_heading,
            to_pos=end_point,
            to_heading=end_heading,
            num_points=20,
            tangent_scale=new_tangent_scale
        )

        # Update the connecting road (temporary preview)
        self.connecting_road.path = path
        aU, bU, cU, dU, aV, bV, cV, dV = coeffs
        self.connecting_road.aU = aU
        self.connecting_road.bU = bU
        self.connecting_road.cU = cU
        self.connecting_road.dU = dU
        self.connecting_road.aV = aV
        self.connecting_road.bV = bV
        self.connecting_road.cV = cV
        self.connecting_road.dV = dV
        self.connecting_road.tangent_scale = new_tangent_scale

        # Emit signal to update graphics if main window is parent
        # The graphics will be updated when the dialog is accepted
        if hasattr(self.parent(), 'image_view'):
            image_view = self.parent().image_view
            if self.connecting_road.id in image_view.connecting_road_centerline_items:
                image_view.connecting_road_centerline_items[self.connecting_road.id].update_graphics()
            if self.connecting_road.id in image_view.connecting_road_lanes_items:
                image_view.connecting_road_lanes_items[self.connecting_road.id].update_graphics()

    def accept(self):
        """Save changes and accept dialog."""
        # Save lane configuration
        old_left = self.connecting_road.lane_count_left
        old_right = self.connecting_road.lane_count_right
        new_left = self.lane_count_left_spin.value()
        new_right = self.lane_count_right_spin.value()

        self.connecting_road.lane_count_left = new_left
        self.connecting_road.lane_count_right = new_right

        # Regenerate lanes if counts changed
        if old_left != new_left or old_right != new_right:
            # Clear lanes to force reinitialization with new counts
            self.connecting_road.lanes = []
            self.connecting_road.ensure_lanes_initialized()

        # Save lane widths
        self.connecting_road.lane_width_start = self.width_start_spin.value()
        self.connecting_road.lane_width_end = self.width_end_spin.value()
        # Update average width for backward compatibility
        self.connecting_road.lane_width = (
            self.connecting_road.lane_width_start + self.connecting_road.lane_width_end
        ) / 2

        # Save contact points
        self.connecting_road.contact_point_start = self.predecessor_contact_combo.currentData()
        self.connecting_road.contact_point_end = self.successor_contact_combo.currentData()

        # The curve has already been updated by on_regenerate_curve if the user clicked preview
        # Otherwise, update tangent_scale without regenerating
        if self.connecting_road.geometry_type == "parampoly3":
            self.connecting_road.tangent_scale = self.tangent_scale_spin.value()
            # If user changed tangent_scale but didn't preview, regenerate now
            self.on_regenerate_curve()

        super().accept()

    @classmethod
    def edit_connecting_road(cls, connecting_road: ConnectingRoad, project: Optional[Project] = None, parent=None) -> bool:
        """
        Show dialog to edit a connecting road's properties.

        Args:
            connecting_road: ConnectingRoad to edit
            project: Project containing the connecting road (optional)
            parent: Parent widget

        Returns:
            True if properties were modified, False if cancelled
        """
        return cls.show_and_accept(connecting_road, project, parent=parent)

"""
Connecting road properties dialog for ORBIT.

Allows editing of connecting road properties including tangent adjustment for ParamPoly3D curves.
"""

from typing import Optional

from PyQt6.QtWidgets import (
    QDialog,
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

        # Get road names
        if self.project:
            pred_road = self.project.get_road(self.connecting_road.predecessor_road_id)
            succ_road = self.project.get_road(self.connecting_road.successor_road_id)
            pred_name = pred_road.name if pred_road and pred_road.name else f"Road {self.connecting_road.predecessor_road_id[:8]}"
            succ_name = succ_road.name if succ_road and succ_road.name else f"Road {self.connecting_road.successor_road_id[:8]}"
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

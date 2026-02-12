"""
Connecting road properties dialog for ORBIT.

Allows editing of connecting road properties including tangent adjustment for ParamPoly3D curves.
"""

import math
from typing import Optional

from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
)

from orbit.models import Project
from orbit.models.connecting_road import ConnectingRoad
from orbit.utils.geometry import generate_simple_connection_path

from .base_dialog import BaseDialog


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
            pred_name = (
                f"{pred_road.name} ({pred_id_short})"
                if pred_road and pred_road.name
                else f"Road {pred_id_short}"
            )
            succ_name = (
                f"{succ_road.name} ({succ_id_short})"
                if succ_road and succ_road.name
                else f"Road {succ_id_short}"
            )
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

        # Note about lane width editing
        width_note = QLabel(
            "<i>Edit individual lane widths via the lane items in the tree view.</i>"
        )
        width_note.setWordWrap(True)
        width_note.setStyleSheet("QLabel { color: #666; font-style: italic; }")
        lane_layout.addRow("", width_note)

        # Contact points
        contact_layout = self.add_form_group_with_info(
            "Contact Points",
            "Which end of each road this connection attaches to"
        )

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
            curve_layout = self.add_form_group_with_info(
                "Curve Parameters",
                "Tangent scale controls how tight or wide the curve is. "
                "Adjust this value to fine-tune the connection path."
            )

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

            # Regenerate button
            self.regenerate_button = QPushButton("Preview Curve")
            self.regenerate_button.setToolTip("Regenerate the curve with the new tangent scale")
            self.regenerate_button.clicked.connect(self.on_regenerate_curve)
            curve_layout.addRow("", self.regenerate_button)

            # Convert to polyline: point count + button
            self.polyline_points_spin = QSpinBox()
            self.polyline_points_spin.setRange(3, len(self.connecting_road.path) or 50)
            self.polyline_points_spin.setValue(min(10, len(self.connecting_road.path) or 10))
            self.polyline_points_spin.setToolTip(
                "Number of points in the converted polyline. "
                "Fewer points are easier to edit."
            )
            self.convert_to_polyline_btn = QPushButton("Convert to Polyline")
            self.convert_to_polyline_btn.setToolTip(
                "Convert to editable polyline. Allows manual point dragging."
            )
            self.convert_to_polyline_btn.clicked.connect(self.on_convert_to_polyline)
            convert_layout = QHBoxLayout()
            convert_layout.addWidget(self.polyline_points_spin)
            convert_layout.addWidget(self.convert_to_polyline_btn)
            curve_layout.addRow("Convert:", convert_layout)

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
        QMessageBox.information(
            self,
            "Conversion Complete",
            "Connecting road has been converted to ParamPoly3D.\n\n"
            "The dialog will now close. Reopen it to adjust tangent parameters."
        )
        self.accept()

    def _resample_path(self, path, num_points):
        """Resample a path to num_points using arc-length interpolation.

        Preserves first and last points exactly.
        """
        if len(path) <= num_points:
            return list(path)

        # Compute cumulative arc lengths
        cum_lengths = [0.0]
        for i in range(1, len(path)):
            dx = path[i][0] - path[i - 1][0]
            dy = path[i][1] - path[i - 1][1]
            cum_lengths.append(cum_lengths[-1] + math.sqrt(dx * dx + dy * dy))

        total_length = cum_lengths[-1]
        if total_length == 0:
            return [path[0]] * num_points

        # Sample at equally spaced arc-length positions
        result = [path[0]]
        seg = 0  # current segment index
        for i in range(1, num_points - 1):
            target_s = total_length * i / (num_points - 1)
            # Advance to the segment containing target_s
            while seg < len(cum_lengths) - 2 and cum_lengths[seg + 1] < target_s:
                seg += 1
            seg_len = cum_lengths[seg + 1] - cum_lengths[seg]
            if seg_len > 0:
                t = (target_s - cum_lengths[seg]) / seg_len
            else:
                t = 0.0
            x = path[seg][0] + t * (path[seg + 1][0] - path[seg][0])
            y = path[seg][1] + t * (path[seg + 1][1] - path[seg][1])
            result.append((x, y))
        result.append(path[-1])
        return result

    def on_convert_to_polyline(self):
        """Convert ParamPoly3D CR to polyline, enabling manual point editing."""
        if self.connecting_road.geometry_type != "parampoly3":
            return

        # Resample path to user-selected point count
        num_points = self.polyline_points_spin.value()
        self.connecting_road.path = self._resample_path(
            self.connecting_road.path, num_points
        )

        self.connecting_road.geometry_type = "polyline"
        # Clear ParamPoly3D coefficients
        self.connecting_road.aU = 0.0
        self.connecting_road.bU = 0.0
        self.connecting_road.cU = 0.0
        self.connecting_road.dU = 0.0
        self.connecting_road.aV = 0.0
        self.connecting_road.bV = 0.0
        self.connecting_road.cV = 0.0
        self.connecting_road.dV = 0.0

        # Update graphics if main window is parent
        if hasattr(self.parent(), 'image_view'):
            image_view = self.parent().image_view
            if self.connecting_road.id in image_view.connecting_road_centerline_items:
                image_view.connecting_road_centerline_items[self.connecting_road.id].update_graphics()
            if self.connecting_road.id in image_view.connecting_road_lanes_items:
                image_view.connecting_road_lanes_items[self.connecting_road.id].update_graphics()

        QMessageBox.information(
            self,
            "Converted",
            "Converted to polyline. You can now drag points on the connecting road.\n\n"
            "The dialog will now close. Reopen it to convert back to ParamPoly3D if needed."
        )
        self.accept()

    def on_regenerate_curve(self):
        """Regenerate the ParamPoly3D curve with new tangent scale."""
        if self.connecting_road.geometry_type != "parampoly3":
            return

        if not self.project:
            return

        if len(self.connecting_road.path) < 2:
            return

        # Get start and end points (these should remain the same)
        start_point = self.connecting_road.path[0]
        end_point = self.connecting_road.path[-1]

        # Prefer stored headings (accurate, set by regenerate_affected_connecting_roads)
        start_heading = self.connecting_road.stored_start_heading
        end_heading = self.connecting_road.stored_end_heading

        # Fallback: compute from road polyline endpoints (same logic as
        # regenerate_affected_connecting_roads in main_window.py)
        if start_heading is None or end_heading is None:
            pred_road = self.project.get_road(self.connecting_road.predecessor_road_id)
            succ_road = self.project.get_road(self.connecting_road.successor_road_id)
            if pred_road and succ_road:
                pred_polyline = self.project.get_polyline(pred_road.centerline_id)
                succ_polyline = self.project.get_polyline(succ_road.centerline_id)

                if start_heading is None and pred_polyline and len(pred_polyline.points) >= 2:
                    if self.connecting_road.contact_point_start == "end":
                        dx = pred_polyline.points[-1][0] - pred_polyline.points[-2][0]
                        dy = pred_polyline.points[-1][1] - pred_polyline.points[-2][1]
                        start_heading = math.atan2(dy, dx)
                    else:
                        dx = pred_polyline.points[1][0] - pred_polyline.points[0][0]
                        dy = pred_polyline.points[1][1] - pred_polyline.points[0][1]
                        start_heading = math.atan2(dy, dx) + math.pi

                if end_heading is None and succ_polyline and len(succ_polyline.points) >= 2:
                    if self.connecting_road.contact_point_end == "start":
                        dx = succ_polyline.points[1][0] - succ_polyline.points[0][0]
                        dy = succ_polyline.points[1][1] - succ_polyline.points[0][1]
                        end_heading = math.atan2(dy, dx) + math.pi
                    else:
                        dx = succ_polyline.points[-1][0] - succ_polyline.points[-2][0]
                        dy = succ_polyline.points[-1][1] - succ_polyline.points[-2][1]
                        end_heading = math.atan2(dy, dx)

        # Last resort: approximate from path points
        if start_heading is None:
            dx = self.connecting_road.path[1][0] - self.connecting_road.path[0][0]
            dy = self.connecting_road.path[1][1] - self.connecting_road.path[0][1]
            start_heading = math.atan2(dy, dx)
        if end_heading is None:
            dx = self.connecting_road.path[-1][0] - self.connecting_road.path[-2][0]
            dy = self.connecting_road.path[-1][1] - self.connecting_road.path[-2][1]
            end_heading = math.atan2(dy, dx)

        # Get new tangent scale
        new_tangent_scale = self.tangent_scale_spin.value()

        # Regenerate the curve
        path, coeffs = generate_simple_connection_path(
            from_pos=start_point,
            from_heading=start_heading,
            to_pos=end_point,
            to_heading=end_heading,
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
        # Get new lane counts
        old_left = self.connecting_road.lane_count_left
        old_right = self.connecting_road.lane_count_right
        new_left = self.lane_count_left_spin.value()
        new_right = self.lane_count_right_spin.value()

        # Update lane counts
        self.connecting_road.lane_count_left = new_left
        self.connecting_road.lane_count_right = new_right

        # Regenerate lanes if counts changed
        if old_left != new_left or old_right != new_right:
            # Clear lanes to force reinitialization with new counts
            self.connecting_road.lanes = []
            self.connecting_road.ensure_lanes_initialized()

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
    def edit_connecting_road(
        cls,
        connecting_road: ConnectingRoad,
        project: Optional[Project] = None,
        parent=None,
    ) -> bool:
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

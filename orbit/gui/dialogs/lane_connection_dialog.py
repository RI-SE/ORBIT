"""
Lane connection dialog for ORBIT.

Allows editing of lane-to-lane connections within a junction.
"""

from typing import List, Optional, Tuple

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QVBoxLayout,
)

from orbit.models import ConnectingRoad, Junction, LaneConnection, Project

from .base_dialog import BaseDialog, InfoIconLabel

# Valid turn types for the dropdown
TURN_TYPES = ['straight', 'left', 'right', 'uturn', 'merge', 'diverge', 'unknown']


class LaneConnectionDialog(BaseDialog):
    """Dialog for editing lane connections within a junction."""

    def __init__(self, junction: Junction, project: Project, parent=None):
        super().__init__("Lane Connections", parent, min_width=900, min_height=500)

        self.junction = junction
        self.project = project
        # Work with copies to allow cancel/rollback
        self.connections: List[LaneConnection] = [
            LaneConnection.from_dict(lc.to_dict()) for lc in junction.lane_connections
        ]
        self._original_connecting_roads = [
            ConnectingRoad.from_dict(cr.to_dict()) for cr in junction.connecting_roads
        ]
        self._original_lane_connections = [
            LaneConnection.from_dict(lc.to_dict()) for lc in junction.lane_connections
        ]
        self.setup_ui()
        self.load_properties()

    def setup_ui(self):
        """Setup the dialog UI."""
        # Junction name label
        junction_label = QLabel(f"<b>Junction:</b> {self.junction.name}")
        self.get_main_layout().addWidget(junction_label)

        # Info section with icon
        info_widget = InfoIconLabel(
            "Lane Connections",
            "Edit lane-to-lane connections through this junction. "
            "Each connection maps an incoming lane to an outgoing lane."
        )
        self.get_main_layout().addWidget(info_widget)

        # Table section
        table_group = QGroupBox("Lane Connections")
        table_layout = QVBoxLayout()

        # Create table
        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "From Road", "From Lane", "To Road", "To Lane",
            "Conn. Road", "Conn. Lane",
            "Turn Type", "Priority", "Actions"
        ])

        # Configure table
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 80)   # From Lane
        self.table.setColumnWidth(3, 80)   # To Lane
        self.table.setColumnWidth(5, 80)   # Conn. Lane
        self.table.setColumnWidth(6, 100)  # Turn Type
        self.table.setColumnWidth(7, 70)   # Priority
        self.table.setColumnWidth(8, 80)   # Actions

        table_layout.addWidget(self.table)

        # Button row under table
        button_layout = QHBoxLayout()

        self.add_btn = QPushButton("+ Add Connection")
        self.add_btn.clicked.connect(self.add_connection)
        button_layout.addWidget(self.add_btn)

        self.auto_generate_btn = QPushButton("Auto-Generate")
        self.auto_generate_btn.setToolTip(
            "Clear all connections and regenerate based on junction geometry"
        )
        self.auto_generate_btn.clicked.connect(self.auto_generate)
        button_layout.addWidget(self.auto_generate_btn)

        button_layout.addStretch()

        table_layout.addLayout(button_layout)
        table_group.setLayout(table_layout)
        self.get_main_layout().addWidget(table_group)

        # Summary label
        self.summary_label = QLabel()
        self.summary_label.setStyleSheet("font-weight: bold;")
        self.get_main_layout().addWidget(self.summary_label)

        # Create standard OK/Cancel buttons
        self.create_button_box()

    def load_properties(self):
        """Load connection data into the table."""
        self.refresh_table()
        self.update_summary()

    def refresh_table(self):
        """Refresh the table from the connections list."""
        self.table.setRowCount(len(self.connections))

        for row, conn in enumerate(self.connections):
            self._populate_row(row, conn)

    def _populate_row(self, row: int, conn: LaneConnection):
        """Populate a single row with connection data."""
        # From Road combo (col 0)
        from_road_combo = QComboBox()
        self._populate_road_combo(from_road_combo)
        self._set_combo_by_id(from_road_combo, conn.from_road_id)
        from_road_combo.currentIndexChanged.connect(lambda: self._on_from_road_changed(row))
        self.table.setCellWidget(row, 0, from_road_combo)

        # From Lane combo (col 1)
        from_lane_combo = QComboBox()
        self._populate_lane_combo(from_lane_combo, conn.from_road_id)
        self._set_combo_by_lane_id(from_lane_combo, conn.from_lane_id)
        from_lane_combo.currentIndexChanged.connect(lambda: self._on_connection_changed(row))
        self.table.setCellWidget(row, 1, from_lane_combo)

        # To Road combo (col 2)
        to_road_combo = QComboBox()
        self._populate_road_combo(to_road_combo)
        self._set_combo_by_id(to_road_combo, conn.to_road_id)
        to_road_combo.currentIndexChanged.connect(lambda: self._on_to_road_changed(row))
        self.table.setCellWidget(row, 2, to_road_combo)

        # To Lane combo (col 3)
        to_lane_combo = QComboBox()
        self._populate_lane_combo(to_lane_combo, conn.to_road_id)
        self._set_combo_by_lane_id(to_lane_combo, conn.to_lane_id)
        to_lane_combo.currentIndexChanged.connect(lambda: self._on_connection_changed(row))
        self.table.setCellWidget(row, 3, to_lane_combo)

        # Connecting Road combo (col 4)
        conn_road_combo = QComboBox()
        self._populate_connecting_road_combo(conn_road_combo)
        self._set_combo_by_id(conn_road_combo, conn.connecting_road_id or "")
        conn_road_combo.currentIndexChanged.connect(lambda: self._on_connecting_road_changed(row))
        self.table.setCellWidget(row, 4, conn_road_combo)

        # Connecting Lane combo (col 5)
        conn_lane_combo = QComboBox()
        self._populate_connecting_lane_combo(conn_lane_combo, conn.connecting_road_id)
        if conn.connecting_lane_id is not None:
            self._set_combo_by_lane_id(conn_lane_combo, conn.connecting_lane_id)
        conn_lane_combo.currentIndexChanged.connect(lambda: self._on_connection_changed(row))
        self.table.setCellWidget(row, 5, conn_lane_combo)

        # Turn Type combo (col 6)
        turn_type_combo = QComboBox()
        for turn_type in TURN_TYPES:
            turn_type_combo.addItem(turn_type.capitalize(), turn_type)
        self._set_combo_by_data(turn_type_combo, conn.turn_type)
        turn_type_combo.currentIndexChanged.connect(lambda: self._on_connection_changed(row))
        self.table.setCellWidget(row, 6, turn_type_combo)

        # Priority spinbox (col 7)
        priority_spin = QSpinBox()
        priority_spin.setRange(0, 100)
        priority_spin.setValue(conn.priority)
        priority_spin.valueChanged.connect(lambda: self._on_connection_changed(row))
        self.table.setCellWidget(row, 7, priority_spin)

        # Delete button (col 8)
        delete_btn = QPushButton("Delete")
        delete_btn.clicked.connect(lambda checked, r=row: self.delete_connection(r))
        self.table.setCellWidget(row, 8, delete_btn)

    def _populate_road_combo(self, combo: QComboBox):
        """Populate a combo box with connected roads."""
        combo.clear()
        combo.addItem("(Select road)", "")
        for road_id in self.junction.connected_road_ids:
            road = self.project.get_road(road_id)
            if road:
                road_id_short = road.id[:8]
                name = f"{road.name} ({road_id_short})" if road.name else f"Road {road_id_short}"
                combo.addItem(name, road_id)

    def _populate_lane_combo(self, combo: QComboBox, road_id: str):
        """Populate a combo box with lanes from a road."""
        combo.clear()
        if not road_id:
            combo.addItem("(Select road first)", 0)
            return

        road = self.project.get_road(road_id)
        if not road:
            combo.addItem("(Invalid road)", 0)
            return

        # Get lanes from the road's first section (or all lanes)
        lane_ids = []
        if road.lane_sections:
            # Use lanes from last section (at junction end)
            for section in road.lane_sections:
                for lane in section.lanes:
                    if lane.id != 0:  # Skip center lane
                        lane_ids.append(lane.id)
        else:
            # Fallback: generate typical lanes based on lane info
            for i in range(1, road.lane_info.left_count + 1):
                lane_ids.append(i)
            for i in range(1, road.lane_info.right_count + 1):
                lane_ids.append(-i)

        # Sort: positive (left) lanes first, then negative (right) lanes
        lane_ids = sorted(set(lane_ids), key=lambda x: (-1 if x > 0 else 1, abs(x)))

        if not lane_ids:
            combo.addItem("(No lanes)", 0)
            return

        for lane_id in lane_ids:
            if lane_id > 0:
                label = f"Lane {lane_id} (Left)"
            else:
                label = f"Lane {lane_id} (Right)"
            combo.addItem(label, lane_id)

    def _populate_connecting_road_combo(self, combo: QComboBox):
        """Populate a combo box with connecting roads in the junction."""
        combo.clear()
        combo.addItem("(None)", "")
        for cr in self.junction.connecting_roads:
            # Build readable label: [id_short] PredName → SuccName
            cr_id_short = cr.id[:8] if len(cr.id) > 8 else cr.id
            pred_name = "?"
            succ_name = "?"
            pred_road = self.project.get_road(cr.predecessor_road_id)
            if pred_road:
                pred_id_short = pred_road.id[:8]
                pred_name = pred_road.name if pred_road.name else f"Road {pred_id_short}"
            succ_road = self.project.get_road(cr.successor_road_id)
            if succ_road:
                succ_id_short = succ_road.id[:8]
                succ_name = succ_road.name if succ_road.name else f"Road {succ_id_short}"
            label = f"[{cr_id_short}] {pred_name} \u2192 {succ_name}"
            combo.addItem(label, cr.id)

    def _populate_connecting_lane_combo(self, combo: QComboBox, connecting_road_id: str | None):
        """Populate a combo box with lanes from a connecting road."""
        combo.clear()
        if not connecting_road_id:
            combo.addItem("(Select conn. road)", 0)
            return

        cr = self.junction.get_connecting_road_by_id(connecting_road_id)
        if not cr:
            combo.addItem("(Invalid road)", 0)
            return

        lane_ids = cr.get_lane_ids()
        if not lane_ids:
            combo.addItem("(No lanes)", 0)
            return

        for lane_id in lane_ids:
            if lane_id > 0:
                label = f"Lane {lane_id} (Left)"
            else:
                label = f"Lane {lane_id} (Right)"
            combo.addItem(label, lane_id)

    def _set_combo_by_id(self, combo: QComboBox, value: str):
        """Set combo selection by road ID."""
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return
        # Default to first item if not found
        if combo.count() > 0:
            combo.setCurrentIndex(0)

    def _set_combo_by_lane_id(self, combo: QComboBox, lane_id: int):
        """Set combo selection by lane ID."""
        for i in range(combo.count()):
            if combo.itemData(i) == lane_id:
                combo.setCurrentIndex(i)
                return
        # Default to first item if not found
        if combo.count() > 0:
            combo.setCurrentIndex(0)

    def _set_combo_by_data(self, combo: QComboBox, value):
        """Set combo selection by data value."""
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    def _on_from_road_changed(self, row: int):
        """Handle from road selection change - update lane combo."""
        from_road_combo = self.table.cellWidget(row, 0)
        from_lane_combo = self.table.cellWidget(row, 1)
        if from_road_combo and from_lane_combo:
            road_id = from_road_combo.currentData()
            self._populate_lane_combo(from_lane_combo, road_id)
        self._on_connection_changed(row)

    def _on_to_road_changed(self, row: int):
        """Handle to road selection change - update lane combo."""
        to_road_combo = self.table.cellWidget(row, 2)
        to_lane_combo = self.table.cellWidget(row, 3)
        if to_road_combo and to_lane_combo:
            road_id = to_road_combo.currentData()
            self._populate_lane_combo(to_lane_combo, road_id)
        self._on_connection_changed(row)

    def _on_connecting_road_changed(self, row: int):
        """Handle connecting road selection change - update connecting lane combo."""
        conn_road_combo = self.table.cellWidget(row, 4)
        conn_lane_combo = self.table.cellWidget(row, 5)
        if conn_road_combo and conn_lane_combo:
            connecting_road_id = conn_road_combo.currentData()
            self._populate_connecting_lane_combo(conn_lane_combo, connecting_road_id)

            # Auto-set "To Road" from connecting road's successor
            if connecting_road_id:
                cr = self.junction.get_connecting_road_by_id(connecting_road_id)
                if cr and cr.successor_road_id:
                    to_road_combo = self.table.cellWidget(row, 2)
                    if to_road_combo:
                        self._set_combo_by_id(to_road_combo, cr.successor_road_id)

        self._on_connection_changed(row)

    def _on_connection_changed(self, row: int):
        """Handle any connection field change."""
        if row >= len(self.connections):
            return

        conn = self.connections[row]

        # Read from road/lane (cols 0-1)
        from_road_combo = self.table.cellWidget(row, 0)
        from_lane_combo = self.table.cellWidget(row, 1)
        if from_road_combo:
            conn.from_road_id = from_road_combo.currentData() or ""
        if from_lane_combo:
            lane_data = from_lane_combo.currentData()
            conn.from_lane_id = lane_data if isinstance(lane_data, int) else -1

        # Read to road/lane (cols 2-3)
        to_road_combo = self.table.cellWidget(row, 2)
        to_lane_combo = self.table.cellWidget(row, 3)
        if to_road_combo:
            conn.to_road_id = to_road_combo.currentData() or ""
        if to_lane_combo:
            lane_data = to_lane_combo.currentData()
            conn.to_lane_id = lane_data if isinstance(lane_data, int) else -1

        # Read connecting road/lane (cols 4-5)
        conn_road_combo = self.table.cellWidget(row, 4)
        conn_lane_combo = self.table.cellWidget(row, 5)
        if conn_road_combo:
            data = conn_road_combo.currentData()
            conn.connecting_road_id = data if data else None
        if conn_lane_combo:
            lane_data = conn_lane_combo.currentData()
            conn.connecting_lane_id = lane_data if isinstance(lane_data, int) and lane_data != 0 else None

        # Read turn type (col 6)
        turn_type_combo = self.table.cellWidget(row, 6)
        if turn_type_combo:
            conn.turn_type = turn_type_combo.currentData() or "unknown"

        # Read priority (col 7)
        priority_spin = self.table.cellWidget(row, 7)
        if priority_spin:
            conn.priority = priority_spin.value()

        self.update_summary()

    def add_connection(self):
        """Add a new empty connection."""
        conn = LaneConnection(id=self.project.next_id('lane_connection'))
        # Default to first connected roads if available
        if len(self.junction.connected_road_ids) >= 2:
            conn.from_road_id = self.junction.connected_road_ids[0]
            conn.to_road_id = self.junction.connected_road_ids[1]

            # Auto-select connecting road if exactly one matches this road pair
            matching_crs = [
                cr for cr in self.junction.connecting_roads
                if cr.predecessor_road_id == conn.from_road_id
                and cr.successor_road_id == conn.to_road_id
            ]
            if len(matching_crs) == 1:
                conn.connecting_road_id = matching_crs[0].id

        self.connections.append(conn)
        self.refresh_table()
        self.update_summary()

    def delete_connection(self, row: int):
        """Delete a connection by row index."""
        if 0 <= row < len(self.connections):
            del self.connections[row]
            self.refresh_table()
            self.update_summary()

    def auto_generate(self):
        """Auto-generate connections using the junction analyzer."""
        result = QMessageBox.question(
            self,
            "Auto-Generate Connections",
            "This will clear all existing connections and regenerate them based on "
            "junction geometry.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if result != QMessageBox.StandardButton.Yes:
            return

        # Import junction analyzer
        try:
            import importlib
            junction_analyzer = importlib.import_module('orbit.import.junction_analyzer')
            generate_junction_connections = junction_analyzer.generate_junction_connections
        except ImportError as e:
            QMessageBox.critical(
                self,
                "Import Error",
                f"Failed to import junction analyzer: {e}"
            )
            return

        # Build dictionaries
        roads_dict = {road.id: road for road in self.project.roads}
        polylines_dict = {p.id: p for p in self.project.polylines}

        # Get scale factor
        scale = 1.0
        if len(self.project.control_points) >= 3:
            try:
                from orbit.export.coordinate_transformer import CoordinateTransformer
                transformer = CoordinateTransformer(self.project.control_points)
                scale_x, scale_y = transformer.get_scale_factor()
                scale = (scale_x + scale_y) / 2.0
            except Exception:
                scale = 1.0

        # Save backup before clearing (auto_generate mutates junction directly)
        backup_connecting_roads = [
            ConnectingRoad.from_dict(cr.to_dict()) for cr in self.junction.connecting_roads
        ]
        backup_lane_connections = [
            LaneConnection.from_dict(lc.to_dict()) for lc in self.junction.lane_connections
        ]

        # Clear and regenerate
        self.junction.connecting_roads.clear()
        self.junction.lane_connections.clear()

        try:
            generate_junction_connections(self.junction, roads_dict, polylines_dict, scale)
            # Copy new connections to our working list
            self.connections = [
                LaneConnection.from_dict(lc.to_dict()) for lc in self.junction.lane_connections
            ]

            if not self.connections and not self.junction.connecting_roads:
                # Generation produced nothing — restore previous state
                self.junction.connecting_roads = backup_connecting_roads
                self.junction.lane_connections = backup_lane_connections
                self.connections = [
                    LaneConnection.from_dict(lc.to_dict()) for lc in backup_lane_connections
                ]
                self.refresh_table()
                self.update_summary()
                QMessageBox.warning(
                    self,
                    "No Connections Generated",
                    "The junction analyzer could not generate any connections.\n\n"
                    "Previous connections have been restored."
                )
                return

            self.refresh_table()
            self.update_summary()

            QMessageBox.information(
                self,
                "Connections Generated",
                f"Generated {len(self.connections)} lane connection(s)."
            )
        except Exception as e:
            # Restore on failure
            self.junction.connecting_roads = backup_connecting_roads
            self.junction.lane_connections = backup_lane_connections
            self.connections = [
                LaneConnection.from_dict(lc.to_dict()) for lc in backup_lane_connections
            ]
            self.refresh_table()
            self.update_summary()
            QMessageBox.critical(
                self,
                "Generation Failed",
                f"Failed to generate connections:\n\n{str(e)}\n\n"
                "Previous connections have been restored."
            )

    def update_summary(self):
        """Update the summary label."""
        total = len(self.connections)
        if total == 0:
            self.summary_label.setText("No connections defined")
            self.summary_label.setStyleSheet("font-weight: bold; color: gray;")
            return

        # Count by turn type
        counts = {}
        valid_count = 0
        for conn in self.connections:
            is_valid, _ = conn.validate_basic()
            if is_valid:
                valid_count += 1
            counts[conn.turn_type] = counts.get(conn.turn_type, 0) + 1

        parts = []
        for turn_type in TURN_TYPES:
            if counts.get(turn_type, 0) > 0:
                parts.append(f"{counts[turn_type]} {turn_type}")

        text = f"{total} connection(s)"
        if parts:
            text += f": {', '.join(parts)}"

        if valid_count < total:
            text += f" ({total - valid_count} incomplete)"
            self.summary_label.setStyleSheet("font-weight: bold; color: orange;")
        else:
            self.summary_label.setStyleSheet("font-weight: bold; color: green;")

        self.summary_label.setText(text)

    def accept(self):
        """Save connections and close dialog."""
        # Validate all connections
        errors = []
        for i, conn in enumerate(self.connections):
            is_valid, msgs = conn.validate_basic()
            if not is_valid:
                errors.extend([f"Row {i+1}: {msg}" for msg in msgs])

        if errors:
            result = QMessageBox.warning(
                self,
                "Validation Warnings",
                "Some connections have issues:\n\n" +
                "\n".join(errors[:5]) +
                (f"\n... and {len(errors)-5} more" if len(errors) > 5 else "") +
                "\n\nSave anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if result != QMessageBox.StandardButton.Yes:
                return

        # Save connections back to junction
        self.junction.lane_connections = self.connections

        # Adjust connecting road paths for changed lane targets
        self._adjust_connecting_road_paths()

        # Clean up orphaned connecting roads (roads no longer referenced by any lane connection)
        referenced_conn_road_ids = {
            conn.connecting_road_id for conn in self.connections
            if conn.connecting_road_id
        }
        self.junction.connecting_roads = [
            cr for cr in self.junction.connecting_roads
            if cr.id in referenced_conn_road_ids
        ]

        super().accept()

    # ------------------------------------------------------------------
    # Path adjustment helpers
    # ------------------------------------------------------------------

    def _adjust_connecting_road_paths(self):
        """Adjust connecting road paths so lane polygons align with connected lanes.

        For each connecting road, computes the absolute target endpoint position
        based on the road centerline and lane offsets, then regenerates the path.
        Uses calculate_perpendicular (same as lane polygon rendering) to guarantee
        consistent direction.
        """
        scale = self._get_scale()
        if scale <= 0:
            return

        for cr in self.junction.connecting_roads:
            if len(cr.path) < 2:
                continue

            # Find primary connection for this CR (first connection sets alignment)
            cr_conns = [c for c in self.connections if c.connecting_road_id == cr.id]
            if not cr_conns:
                continue
            conn = cr_conns[0]
            cr_lane_id = conn.connecting_lane_id if conn.connecting_lane_id is not None else -1

            # Predecessor end (CR start)
            start_shift = self._compute_lane_alignment_shift(
                road_id=cr.predecessor_road_id,
                contact_point=cr.contact_point_start,
                target_lane_id=conn.from_lane_id,
                cr_lane_id=cr_lane_id,
                cr_lane_width=cr.lane_width,
                cr_endpoint=cr.path[0],
                scale=scale,
            )

            # Successor end (CR end)
            end_shift = self._compute_lane_alignment_shift(
                road_id=cr.successor_road_id,
                contact_point=cr.contact_point_end,
                target_lane_id=conn.to_lane_id,
                cr_lane_id=cr_lane_id,
                cr_lane_width=cr.lane_width,
                cr_endpoint=cr.path[-1],
                scale=scale,
            )

            if start_shift or end_shift:
                self._regenerate_connecting_road_path(cr, start_shift, end_shift)

    def _compute_lane_alignment_shift(
        self,
        road_id: str,
        contact_point: str,
        target_lane_id: int,
        cr_lane_id: int,
        cr_lane_width: float,
        cr_endpoint: Tuple[float, float],
        scale: float,
    ) -> Optional[Tuple[float, float]]:
        """Compute shift to align a CR lane with a target lane on a connected road.

        Calculates the absolute target position from the road's centerline
        polyline endpoint, then returns the delta from the CR's current endpoint.
        Uses calculate_perpendicular (identical to lane polygon rendering).
        """
        from orbit.utils.geometry import calculate_perpendicular

        road = self.project.get_road(road_id)
        if not road or not road.centerline_id:
            return None

        polyline = self.project.get_polyline(road.centerline_id)
        if not polyline or len(polyline.points) < 2:
            return None

        # Road centerline position and perpendicular at the contact point
        if contact_point == "end":
            road_cl_pos = polyline.points[-1]
            perp = calculate_perpendicular(polyline.points[-2], polyline.points[-1])
        else:
            road_cl_pos = polyline.points[0]
            perp = calculate_perpendicular(polyline.points[0], polyline.points[1])

        road_lane_width = self._get_road_lane_width(road)

        # How far from the road CL should the CR CL be?
        # road_lane_offset: where the target lane center is relative to road CL
        # cr_lane_offset:   where the CR lane center is relative to CR CL
        # CR CL must sit at (road_lane_offset - cr_lane_offset) from road CL.
        road_lane_off = self._lane_center_offset(target_lane_id, road_lane_width)
        cr_lane_off = self._lane_center_offset(cr_lane_id, cr_lane_width)
        offset_px = (road_lane_off - cr_lane_off) / scale

        target_x = road_cl_pos[0] + offset_px * perp[0]
        target_y = road_cl_pos[1] + offset_px * perp[1]

        dx = target_x - cr_endpoint[0]
        dy = target_y - cr_endpoint[1]

        # Skip trivial shifts (< 1 px)
        if abs(dx) < 1.0 and abs(dy) < 1.0:
            return None

        return (dx, dy)

    @staticmethod
    def _lane_center_offset(lane_id: int, lane_width: float) -> float:
        """Perpendicular offset of a lane center from the road centerline (meters).

        Positive = right of direction of travel, negative = left.
        Matches the offset convention in calculate_offset_polyline / calculate_perpendicular.
        """
        if lane_id < 0:
            return (abs(lane_id) - 0.5) * lane_width
        elif lane_id > 0:
            return -(lane_id - 0.5) * lane_width
        return 0.0

    def _get_road_lane_width(self, road) -> float:
        """Get average lane width for a road in meters."""
        if road.lane_sections:
            section = road.lane_sections[-1]
            widths = [lane.width for lane in section.lanes if lane.id != 0 and lane.width > 0]
            if widths:
                return sum(widths) / len(widths)
        if hasattr(road, "lane_info") and road.lane_info:
            return road.lane_info.lane_width
        return 3.5

    def _get_scale(self) -> float:
        """Get meters-per-pixel scale factor."""
        if len(self.project.control_points) >= 3:
            try:
                from orbit.export.coordinate_transformer import CoordinateTransformer
                transformer = CoordinateTransformer(self.project.control_points)
                sx, sy = transformer.get_scale_factor()
                return (sx + sy) / 2.0
            except Exception:
                pass
        return 0.058  # Default fallback (ConnectingRoadLanesGraphicsItem.DEFAULT_SCALE)

    @staticmethod
    def _regenerate_connecting_road_path(
        cr: 'ConnectingRoad',
        start_shift: Optional[Tuple[float, float]],
        end_shift: Optional[Tuple[float, float]],
    ) -> None:
        """Regenerate a connecting road's path after endpoint shifts."""
        new_start = cr.path[0]
        new_end = cr.path[-1]
        if start_shift:
            new_start = (new_start[0] + start_shift[0],
                         new_start[1] + start_shift[1])
        if end_shift:
            new_end = (new_end[0] + end_shift[0],
                       new_end[1] + end_shift[1])

        start_heading = cr.get_start_heading()
        end_heading = cr.get_end_heading()

        if cr.geometry_type == "parampoly3" and start_heading is not None and end_heading is not None:
            try:
                from orbit.utils.geometry import generate_simple_connection_path
                path, coeffs = generate_simple_connection_path(
                    from_pos=new_start,
                    from_heading=start_heading,
                    to_pos=new_end,
                    to_heading=end_heading,
                    num_points=len(cr.path),
                    tangent_scale=cr.tangent_scale,
                )
                if path and len(path) >= 2:
                    cr.path = path
                    if coeffs and len(coeffs) == 8:
                        cr.aU, cr.bU, cr.cU, cr.dU = coeffs[:4]
                        cr.aV, cr.bV, cr.cV, cr.dV = coeffs[4:]
                    cr.stored_start_heading = start_heading
                    cr.stored_end_heading = end_heading
                    return
            except Exception:
                pass

        # Fallback for polyline or failed regen: shift endpoints directly
        path = list(cr.path)
        if start_shift:
            path[0] = new_start
        if end_shift:
            path[-1] = new_end
        cr.path = path

    def reject(self):
        """Restore junction state and close dialog."""
        self.junction.connecting_roads = self._original_connecting_roads
        self.junction.lane_connections = self._original_lane_connections
        super().reject()

    @classmethod
    def edit_connections(cls, junction: Junction, project: Project, parent=None) -> bool:
        """
        Show dialog to edit junction lane connections.

        Args:
            junction: Junction to edit
            project: Project containing the junction
            parent: Parent widget

        Returns:
            True if connections were modified, False if cancelled
        """
        dialog = cls(junction, project, parent)
        return dialog.exec() == QDialog.DialogCode.Accepted

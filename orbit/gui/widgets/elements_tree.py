"""
Elements tree widget for ORBIT.

Displays hierarchical view of junctions and other project elements with management capabilities.
"""

from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTreeWidget, QTreeWidgetItem, QMenu, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QEvent
from PyQt6.QtGui import QAction, QKeyEvent

from orbit.models import Project, Junction, Signal, ParkingSpace
from orbit.utils.enum_formatting import format_snake_case
from ..utils.message_helpers import ask_yes_no


class ElementsTreeWidget(QWidget):
    """Widget for managing junctions and other project elements."""

    # Signals
    junction_selected = pyqtSignal(str)  # Emits junction ID
    junction_modified = pyqtSignal(str)  # Emits junction ID
    junction_deleted = pyqtSignal(str)  # Emits junction ID
    signal_selected = pyqtSignal(str)  # Emits signal ID
    signal_modified = pyqtSignal(str)  # Emits signal ID
    signal_deleted = pyqtSignal(str)  # Emits signal ID
    object_selected = pyqtSignal(str)  # Emits object ID
    parking_selected = pyqtSignal(str)  # Emits parking ID
    parking_modified = pyqtSignal(str)  # Emits parking ID
    parking_deleted = pyqtSignal(str)  # Emits parking ID
    object_modified = pyqtSignal(str)  # Emits object ID
    object_deleted = pyqtSignal(str)  # Emits object ID
    connecting_road_selected = pyqtSignal(str)  # Emits connecting road ID
    connecting_road_modified = pyqtSignal(str)  # Emits connecting road ID
    connecting_road_lane_selected = pyqtSignal(str, int)  # Emits (connecting road ID, lane ID)

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)

        self.project = project
        self.setup_ui()
        self.refresh_tree()

    def setup_ui(self):
        """Setup the widget UI."""
        layout = QVBoxLayout(self)

        # Tree widget
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("Elements")
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)
        self.tree.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.tree.itemSelectionChanged.connect(self.on_selection_changed)
        self.tree.installEventFilter(self)
        layout.addWidget(self.tree)

    def set_project(self, project: Project):
        """Update the project reference and refresh the tree."""
        self.project = project
        self.refresh_tree()

    def refresh_tree(self):
        """Refresh the entire tree from project data."""
        self.tree.clear()

        # Add Junctions category
        junctions_item = QTreeWidgetItem(["Junctions"])
        junctions_item.setData(0, Qt.ItemDataRole.UserRole, "category_junctions")
        self.tree.addTopLevelItem(junctions_item)

        for junction in self.project.junctions:
            junction_item = self.create_junction_item(junction)
            junctions_item.addChild(junction_item)

        junctions_item.setExpanded(True)

        # Add Signals category
        signals_item = QTreeWidgetItem(["Signals"])
        signals_item.setData(0, Qt.ItemDataRole.UserRole, "category_signals")
        self.tree.addTopLevelItem(signals_item)

        for signal in self.project.signals:
            signal_item = self.create_signal_item(signal)
            signals_item.addChild(signal_item)

        signals_item.setExpanded(True)

        # Add Objects category
        objects_item = QTreeWidgetItem(["Objects"])
        objects_item.setData(0, Qt.ItemDataRole.UserRole, "category_objects")
        self.tree.addTopLevelItem(objects_item)

        for obj in self.project.objects:
            object_item = self.create_object_item(obj)
            objects_item.addChild(object_item)

        objects_item.setExpanded(True)

        # Add Parking category
        parking_item = QTreeWidgetItem(["Parking"])
        parking_item.setData(0, Qt.ItemDataRole.UserRole, "category_parking")
        self.tree.addTopLevelItem(parking_item)

        for parking in self.project.parking_spaces:
            parking_space_item = self.create_parking_item(parking)
            parking_item.addChild(parking_space_item)

        parking_item.setExpanded(True)

    def create_junction_item(self, junction: Junction) -> QTreeWidgetItem:
        """Create a tree item for a junction with connecting roads as children."""
        road_count = len(junction.connected_road_ids)
        conn_count = len(junction.connecting_roads)
        text = f"{junction.name} ({road_count} roads, {conn_count} connections)"

        item = QTreeWidgetItem([text])
        item.setData(0, Qt.ItemDataRole.UserRole, {"type": "junction", "id": junction.id})

        # Add connecting roads as children
        for connecting_road in junction.connecting_roads:
            conn_item = self.create_connecting_road_item(connecting_road)
            item.addChild(conn_item)

        return item

    def create_connecting_road_item(self, connecting_road) -> QTreeWidgetItem:
        """Create a tree item for a connecting road with centerline and lanes as children."""
        from orbit.models.connecting_road import ConnectingRoad

        conn_road: ConnectingRoad = connecting_road

        # Get road names for display
        predecessor_name = "?"
        successor_name = "?"

        if self.project:
            pred_road = self.project.get_road(conn_road.predecessor_road_id)
            if pred_road:
                pred_id_short = pred_road.id[:8]
                predecessor_name = f"{pred_road.name} ({pred_id_short})" if pred_road.name else f"Road {pred_id_short}"

            succ_road = self.project.get_road(conn_road.successor_road_id)
            if succ_road:
                succ_id_short = succ_road.id[:8]
                successor_name = f"{succ_road.name} ({succ_id_short})" if succ_road.name else f"Road {succ_id_short}"

        # Display text showing which roads are connected
        text = f"{predecessor_name} → {successor_name}"

        item = QTreeWidgetItem([text])
        item.setData(0, Qt.ItemDataRole.UserRole, {
            "type": "connecting_road",
            "id": conn_road.id
        })

        # Add centerline as first child (similar to regular roads)
        centerline_item = self.create_connecting_road_centerline_item(conn_road)
        item.addChild(centerline_item)

        # Add lanes as children
        lane_ids = conn_road.get_lane_ids()
        for lane_id in lane_ids:
            lane_item = self.create_connecting_road_lane_item(conn_road.id, lane_id)
            item.addChild(lane_item)

        return item

    def create_connecting_road_centerline_item(self, connecting_road) -> QTreeWidgetItem:
        """Create a tree item for a connecting road's centerline path."""
        from orbit.models.connecting_road import ConnectingRoad

        conn_road: ConnectingRoad = connecting_road

        # Calculate path length
        path_length = conn_road.get_length_pixels()
        point_count = len(conn_road.path)

        # Format geometry type
        if conn_road.geometry_type == "parampoly3":
            geom_type = "ParamPoly3D"
        else:
            geom_type = "Polyline"

        text = f"Centerline ({geom_type}, {point_count} pts, {path_length:.0f} px)"

        item = QTreeWidgetItem([text])
        item.setData(0, Qt.ItemDataRole.UserRole, {
            "type": "connecting_road_centerline",
            "connecting_road_id": conn_road.id
        })

        return item

    def create_connecting_road_lane_item(self, conn_road_id: str, lane_id: int) -> QTreeWidgetItem:
        """Create a tree item for a lane in a connecting road."""
        # Format position like regular lanes: "Left 1", "Right 1", etc.
        # Note: In OpenDRIVE, positive IDs are LEFT lanes, negative are RIGHT
        if lane_id == 0:
            position = "Center"
        elif lane_id > 0:
            position = f"Left {lane_id}"
        else:
            position = f"Right {abs(lane_id)}"

        # Connecting roads typically have driving lanes
        lane_type_name = "Driving"

        # Format: "Lane -1 (Right 1) - Driving"
        text = f"Lane {lane_id} ({position}) - {lane_type_name}"

        item = QTreeWidgetItem([text])
        item.setData(0, Qt.ItemDataRole.UserRole, {
            "type": "connecting_road_lane",
            "connecting_road_id": conn_road_id,
            "lane_id": lane_id
        })

        return item

    def create_signal_item(self, signal: Signal) -> QTreeWidgetItem:
        """Create a tree item for a signal."""
        from orbit.models.signal import SignalType

        # Build display text
        display_name = signal.get_display_name()

        # Add road info if assigned
        road_info = ""
        if signal.road_id and self.project:
            road = self.project.get_road(signal.road_id)
            if road:
                road_name = road.name or f"Road {road.id[:8]}"
                road_info = f" → {road_name}"

        text = f"{display_name}{road_info}"

        item = QTreeWidgetItem([text])
        item.setData(0, Qt.ItemDataRole.UserRole, {"type": "signal", "id": signal.id})
        return item

    def create_object_item(self, obj) -> QTreeWidgetItem:
        """Create a tree item for an object."""
        from orbit.models.object import RoadObject

        # Build display text
        display_name = obj.get_display_name()

        # Add category and road info
        category = format_snake_case(obj.type.get_category())
        road_info = ""
        if obj.road_id and self.project:
            road = self.project.get_road(obj.road_id)
            if road:
                road_name = road.name or f"Road {road.id[:8]}"
                road_info = f" → {road_name}"

        text = f"{display_name} ({category}){road_info}"

        item = QTreeWidgetItem([text])
        item.setData(0, Qt.ItemDataRole.UserRole, {"type": "object", "id": obj.id})
        return item

    def create_parking_item(self, parking: ParkingSpace) -> QTreeWidgetItem:
        """Create a tree item for a parking space."""
        # Build display text
        display_name = parking.get_display_name()

        # Add access and road info
        access_type = parking.access.value.replace('_', ' ').title()
        road_info = ""
        if parking.road_id and self.project:
            road = self.project.get_road(parking.road_id)
            if road:
                road_name = road.name or f"Road {road.id[:8]}"
                road_info = f" → {road_name}"

        text = f"{display_name} ({access_type}){road_info}"

        item = QTreeWidgetItem([text])
        item.setData(0, Qt.ItemDataRole.UserRole, {"type": "parking", "id": parking.id})
        return item

    def show_context_menu(self, position):
        """Show context menu for tree items."""
        item = self.tree.itemAt(position)
        if not item:
            return

        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict):
            return

        menu = QMenu(self)

        if data["type"] == "junction":
            # Junction context menu
            edit_action = QAction("Edit Junction", self)
            edit_action.triggered.connect(lambda: self.edit_junction(data["id"]))
            menu.addAction(edit_action)

            lane_connections_action = QAction("Edit Lane Connections", self)
            lane_connections_action.triggered.connect(lambda: self.edit_lane_connections(data["id"]))
            menu.addAction(lane_connections_action)

            menu.addSeparator()

            delete_action = QAction("Delete Junction", self)
            delete_action.triggered.connect(lambda: self.delete_junction(data["id"]))
            menu.addAction(delete_action)

        elif data["type"] == "signal":
            # Signal context menu
            edit_action = QAction("Edit Signal", self)
            edit_action.triggered.connect(lambda: self.edit_signal(data["id"]))
            menu.addAction(edit_action)

            delete_action = QAction("Delete Signal", self)
            delete_action.triggered.connect(lambda: self.delete_signal(data["id"]))
            menu.addAction(delete_action)

        elif data["type"] == "object":
            # Object context menu
            edit_action = QAction("Edit Object", self)
            edit_action.triggered.connect(lambda: self.edit_object(data["id"]))
            menu.addAction(edit_action)

            delete_action = QAction("Delete Object", self)
            delete_action.triggered.connect(lambda: self.delete_object(data["id"]))
            menu.addAction(delete_action)

        elif data["type"] == "parking":
            # Parking context menu
            edit_action = QAction("Edit Parking", self)
            edit_action.triggered.connect(lambda: self.edit_parking(data["id"]))
            menu.addAction(edit_action)

            delete_action = QAction("Delete Parking", self)
            delete_action.triggered.connect(lambda: self.delete_parking(data["id"]))
            menu.addAction(delete_action)

        elif data["type"] == "connecting_road":
            # Connecting road context menu
            edit_action = QAction("Edit Connecting Road", self)
            edit_action.triggered.connect(lambda: self.edit_connecting_road(data["id"]))
            menu.addAction(edit_action)

        elif data["type"] == "connecting_road_lane":
            # Connecting road lane context menu
            edit_action = QAction("Edit Lane Properties", self)
            edit_action.triggered.connect(lambda: self.edit_connecting_road_lane(
                data["connecting_road_id"], data["lane_id"]))
            menu.addAction(edit_action)

        elif data["type"] == "connecting_road_centerline":
            # Connecting road centerline context menu - open parent road properties
            edit_action = QAction("Edit Connecting Road Properties", self)
            edit_action.triggered.connect(lambda: self.edit_connecting_road(
                data["connecting_road_id"]))
            menu.addAction(edit_action)

        menu.exec(self.tree.viewport().mapToGlobal(position))

    def edit_junction(self, junction_id: str):
        """Edit a junction's properties."""
        from ..dialogs.junction_dialog import JunctionDialog

        junction = self.project.get_junction(junction_id)
        if junction:
            dialog = JunctionDialog(junction, self.project, self)
            if dialog.exec():
                self.junction_modified.emit(junction_id)
                self.refresh_tree()

    def edit_lane_connections(self, junction_id: str):
        """Edit lane connections for a junction."""
        from ..dialogs.lane_connection_dialog import LaneConnectionDialog

        junction = self.project.get_junction(junction_id)
        if junction:
            if LaneConnectionDialog.edit_connections(junction, self.project, self):
                self.junction_modified.emit(junction_id)
                self.refresh_tree()

    def delete_junction(self, junction_id: str):
        """Delete a junction."""
        if ask_yes_no(self, "Are you sure you want to delete this junction?", "Delete Junction"):
            self.project.remove_junction(junction_id)
            self.junction_deleted.emit(junction_id)
            self.refresh_tree()

    def edit_signal(self, signal_id: str):
        """Edit a signal's properties."""
        from ..dialogs.signal_properties_dialog import SignalPropertiesDialog

        signal = self.project.get_signal(signal_id)
        if signal:
            dialog = SignalPropertiesDialog(signal, self.project, self)
            if dialog.exec():
                self.signal_modified.emit(signal_id)
                self.refresh_tree()

    def delete_signal(self, signal_id: str):
        """Delete a signal."""
        if ask_yes_no(self, "Are you sure you want to delete this signal?", "Delete Signal"):
            self.project.remove_signal(signal_id)
            self.signal_deleted.emit(signal_id)
            self.refresh_tree()

    def edit_object(self, object_id: str):
        """Edit an object's properties."""
        from ..dialogs.object_properties_dialog import ObjectPropertiesDialog

        obj = self.project.get_object(object_id)
        if obj:
            dialog = ObjectPropertiesDialog(obj, self.project, self)
            if dialog.exec():
                self.object_modified.emit(object_id)
                self.refresh_tree()

    def delete_object(self, object_id: str):
        """Delete an object."""
        if ask_yes_no(self, "Are you sure you want to delete this object?", "Delete Object"):
            self.project.remove_object(object_id)
            self.object_deleted.emit(object_id)
            self.refresh_tree()

    def edit_parking(self, parking_id: str):
        """Edit a parking space's properties."""
        from ..dialogs.parking_properties_dialog import ParkingPropertiesDialog

        parking = self.project.get_parking(parking_id)
        if parking:
            dialog = ParkingPropertiesDialog(parking, self.project, self)
            if dialog.exec():
                self.parking_modified.emit(parking_id)
                self.refresh_tree()

    def delete_parking(self, parking_id: str):
        """Delete a parking space."""
        if ask_yes_no(self, "Are you sure you want to delete this parking space?", "Delete Parking"):
            self.project.remove_parking(parking_id)
            self.parking_deleted.emit(parking_id)
            self.refresh_tree()

    def edit_connecting_road(self, connecting_road_id: str):
        """Edit a connecting road's properties."""
        from ..dialogs.connecting_road_dialog import ConnectingRoadDialog

        # Find the connecting road in junctions
        connecting_road = None
        for junction in self.project.junctions:
            for cr in junction.connecting_roads:
                if cr.id == connecting_road_id:
                    connecting_road = cr
                    break
            if connecting_road:
                break

        if connecting_road:
            dialog = ConnectingRoadDialog(connecting_road, self.project, self)
            result = dialog.exec()
            if result:
                self.connecting_road_modified.emit(connecting_road_id)
                self.refresh_tree()

    def edit_connecting_road_lane(self, connecting_road_id: str, lane_id: int):
        """Edit a connecting road lane's properties."""
        from ..dialogs.lane_properties_dialog import LanePropertiesDialog

        # Find the connecting road in junctions
        connecting_road = None
        parent_junction = None
        for junction in self.project.junctions:
            for cr in junction.connecting_roads:
                if cr.id == connecting_road_id:
                    connecting_road = cr
                    parent_junction = junction
                    break
            if connecting_road:
                break

        if not connecting_road:
            return

        # Find the lane
        lane = connecting_road.get_lane(lane_id)
        if not lane:
            return

        # Open lane properties dialog with connecting road for start/end width editing
        result = LanePropertiesDialog.edit_lane(
            lane, None, None,
            connecting_road=connecting_road,
            parent=self
        )
        if result:
            # Emit modification signal
            self.connecting_road_modified.emit(connecting_road_id)
            self.refresh_tree()

    def on_item_double_clicked(self, item, column):
        """Handle double-click on item."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(data, dict):
            if data["type"] == "junction":
                self.edit_junction(data["id"])
            elif data["type"] == "signal":
                self.edit_signal(data["id"])
            elif data["type"] == "object":
                self.edit_object(data["id"])
            elif data["type"] == "parking":
                self.edit_parking(data["id"])
            elif data["type"] == "connecting_road":
                self.edit_connecting_road(data["id"])
            elif data["type"] == "connecting_road_lane":
                self.edit_connecting_road_lane(data["connecting_road_id"], data["lane_id"])
            elif data["type"] == "connecting_road_centerline":
                self.edit_connecting_road(data["connecting_road_id"])

    def on_selection_changed(self):
        """Handle selection change."""
        selected_items = self.tree.selectedItems()
        if selected_items:
            item = selected_items[0]
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(data, dict):
                if data["type"] == "junction":
                    self.junction_selected.emit(data["id"])
                elif data["type"] == "signal":
                    self.signal_selected.emit(data["id"])
                elif data["type"] == "object":
                    self.object_selected.emit(data["id"])
                elif data["type"] == "parking":
                    self.parking_selected.emit(data["id"])
                elif data["type"] == "connecting_road":
                    self.connecting_road_selected.emit(data["id"])
                elif data["type"] == "connecting_road_lane":
                    self.connecting_road_lane_selected.emit(
                        data["connecting_road_id"],
                        data["lane_id"]
                    )

    def eventFilter(self, obj, event):
        """Handle keyboard events on the tree widget."""
        if obj == self.tree and event.type() == QEvent.Type.KeyPress:
            key_event = event
            key = key_event.key()

            # Enter/Return: Edit selected item
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                selected_items = self.tree.selectedItems()
                if selected_items:
                    self.on_item_double_clicked(selected_items[0], 0)
                return True

            # Delete: Delete selected item
            if key == Qt.Key.Key_Delete:
                selected_items = self.tree.selectedItems()
                if selected_items:
                    item = selected_items[0]
                    data = item.data(0, Qt.ItemDataRole.UserRole)
                    if isinstance(data, dict):
                        if data["type"] == "junction":
                            self.delete_junction(data["id"])
                        elif data["type"] == "signal":
                            self.delete_signal(data["id"])
                        elif data["type"] == "object":
                            self.delete_object(data["id"])
                        elif data["type"] == "parking":
                            self.delete_parking(data["id"])
                return True

        return super().eventFilter(obj, event)

    def select_junction(self, junction_id: str):
        """Programmatically select a junction in the tree."""
        # Search through junctions category
        for i in range(self.tree.topLevelItemCount()):
            category = self.tree.topLevelItem(i)
            data = category.data(0, Qt.ItemDataRole.UserRole)
            if data == "category_junctions":
                for j in range(category.childCount()):
                    item = category.child(j)
                    item_data = item.data(0, Qt.ItemDataRole.UserRole)
                    if isinstance(item_data, dict) and item_data.get("id") == junction_id:
                        self.tree.setCurrentItem(item)
                        return

    def select_signal(self, signal_id: str):
        """Programmatically select a signal in the tree."""
        # Search through signals category
        for i in range(self.tree.topLevelItemCount()):
            category = self.tree.topLevelItem(i)
            data = category.data(0, Qt.ItemDataRole.UserRole)
            if data == "category_signals":
                for j in range(category.childCount()):
                    item = category.child(j)
                    item_data = item.data(0, Qt.ItemDataRole.UserRole)
                    if isinstance(item_data, dict) and item_data.get("id") == signal_id:
                        self.tree.setCurrentItem(item)
                        return

    def select_object(self, object_id: str):
        """Programmatically select an object in the tree."""
        # Search through objects category
        for i in range(self.tree.topLevelItemCount()):
            category = self.tree.topLevelItem(i)
            data = category.data(0, Qt.ItemDataRole.UserRole)
            if data == "category_objects":
                for j in range(category.childCount()):
                    item = category.child(j)
                    item_data = item.data(0, Qt.ItemDataRole.UserRole)
                    if isinstance(item_data, dict) and item_data.get("id") == object_id:
                        self.tree.setCurrentItem(item)
                        return

    def select_connecting_road_lane(self, connecting_road_id: str, lane_id: int):
        """Programmatically select a connecting road lane in the tree."""
        # Search through junctions category for the connecting road
        for i in range(self.tree.topLevelItemCount()):
            category = self.tree.topLevelItem(i)
            data = category.data(0, Qt.ItemDataRole.UserRole)
            if data == "category_junctions":
                # Iterate through junctions
                for j in range(category.childCount()):
                    junction_item = category.child(j)
                    # Iterate through connecting roads in this junction
                    for k in range(junction_item.childCount()):
                        conn_road_item = junction_item.child(k)
                        conn_road_data = conn_road_item.data(0, Qt.ItemDataRole.UserRole)
                        if isinstance(conn_road_data, dict) and conn_road_data.get("id") == connecting_road_id:
                            # Found the connecting road, now find the lane
                            for l in range(conn_road_item.childCount()):
                                lane_item = conn_road_item.child(l)
                                lane_data = lane_item.data(0, Qt.ItemDataRole.UserRole)
                                if isinstance(lane_data, dict) and lane_data.get("lane_id") == lane_id:
                                    # Expand parent items so selection is visible
                                    category.setExpanded(True)
                                    junction_item.setExpanded(True)
                                    conn_road_item.setExpanded(True)
                                    # Select the lane item
                                    self.tree.setCurrentItem(lane_item)
                                    return

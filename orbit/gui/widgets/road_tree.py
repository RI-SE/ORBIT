"""
Road tree widget for ORBIT.

Displays hierarchical view of roads and their polylines with management capabilities.
"""

from typing import Optional, List, Tuple

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator,
    QMenu, QMessageBox, QLineEdit, QAbstractItemView
)
from PyQt6.QtCore import Qt, pyqtSignal, QEvent, QMimeData
from PyQt6.QtGui import QAction, QKeyEvent, QDrag

from orbit.models import Project, Road, Polyline, LaneType
from ..utils.message_helpers import show_info, ask_yes_no


class DraggableTreeWidget(QTreeWidget):
    """Tree widget supporting drag-drop for polyline assignment to roads."""

    # Signal emitted when a polyline is dropped on a road
    polyline_dropped_on_road = pyqtSignal(str, str)  # (polyline_id, road_id)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._dragged_polyline_id: Optional[str] = None

    def startDrag(self, supportedActions):
        """Start dragging an unassigned polyline."""
        item = self.currentItem()
        if not item:
            return

        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict) or data.get("type") != "polyline":
            return

        # Check if this is an unassigned polyline (parent should be "unassigned")
        parent = item.parent()
        if not parent:
            return

        parent_data = parent.data(0, Qt.ItemDataRole.UserRole)
        if parent_data != "unassigned":
            # Already assigned to a road - don't allow dragging
            return

        # Store the polyline ID being dragged
        self._dragged_polyline_id = data.get("id")

        # Create drag with custom mime data
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(f"polyline:{self._dragged_polyline_id}")
        drag.setMimeData(mime_data)

        # Execute drag
        drag.exec(Qt.DropAction.MoveAction)
        self._dragged_polyline_id = None

    def dragEnterEvent(self, event):
        """Accept drag if it contains polyline data."""
        if event.mimeData().hasText():
            text = event.mimeData().text()
            if text.startswith("polyline:"):
                event.acceptProposedAction()
                return
        event.ignore()

    def dragMoveEvent(self, event):
        """Show visual feedback when hovering over valid drop targets."""
        if not event.mimeData().hasText():
            event.ignore()
            return

        text = event.mimeData().text()
        if not text.startswith("polyline:"):
            event.ignore()
            return

        # Check if hovering over a road item
        item = self.itemAt(event.position().toPoint())
        if item:
            road_item = self._find_road_item(item)
            if road_item:
                event.acceptProposedAction()
                return

        event.ignore()

    def dropEvent(self, event):
        """Handle dropping a polyline on a road."""
        if not event.mimeData().hasText():
            event.ignore()
            return

        text = event.mimeData().text()
        if not text.startswith("polyline:"):
            event.ignore()
            return

        polyline_id = text.replace("polyline:", "")

        # Find the road item at drop position
        item = self.itemAt(event.position().toPoint())
        if not item:
            event.ignore()
            return

        road_item = self._find_road_item(item)
        if not road_item:
            event.ignore()
            return

        road_data = road_item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(road_data, dict) or road_data.get("type") != "road":
            event.ignore()
            return

        road_id = road_data.get("id")

        # Emit signal to handle the assignment
        self.polyline_dropped_on_road.emit(polyline_id, road_id)
        event.acceptProposedAction()

    def _find_road_item(self, item: QTreeWidgetItem) -> Optional[QTreeWidgetItem]:
        """Find the road item that contains this item (or is this item)."""
        current = item
        while current:
            data = current.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(data, dict) and data.get("type") == "road":
                return current
            current = current.parent()
        return None


class RoadTreeWidget(QWidget):
    """Widget for managing roads and their polyline associations."""

    # Signals
    road_selected = pyqtSignal(str)  # Emits road ID
    road_added = pyqtSignal(object)  # Emits Road
    road_modified = pyqtSignal(str)  # Emits road ID
    road_deleted = pyqtSignal(str)  # Emits road ID
    road_delete_requested = pyqtSignal(str)  # Emits road ID - handler should do deletion
    road_edit_requested = pyqtSignal(str)  # Emits road ID - handler should open dialog with undo
    roads_merge_requested = pyqtSignal(str, str)  # Emits (road1_id, road2_id) for merge
    polyline_selected = pyqtSignal(str)  # Emits polyline ID
    polyline_deleted = pyqtSignal(str)  # Emits polyline ID (legacy)
    polyline_delete_requested = pyqtSignal(str)  # Emits polyline ID - handler does deletion
    lane_selected = pyqtSignal(str, int, int)  # Emits road_id, section_number, lane_id

    def __init__(self, project: Project, parent=None, verbose: bool = False):
        super().__init__(parent)

        self.project = project
        self.verbose = verbose
        self._cached_scale_factor: float | None = None
        self._scale_factor_computed = False
        self.setup_ui()
        self.refresh_tree()

    def setup_ui(self):
        """Setup the widget UI."""
        layout = QVBoxLayout(self)

        # Filter input
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filter roads...")
        self.filter_input.setClearButtonEnabled(True)
        self.filter_input.textChanged.connect(self.apply_filter)
        layout.addWidget(self.filter_input)

        # Tree widget with drag-drop support
        self.tree = DraggableTreeWidget()
        self.tree.setHeaderLabel("Roads & Polylines")
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)
        self.tree.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.tree.itemSelectionChanged.connect(self.on_selection_changed)
        self.tree.installEventFilter(self)
        self.tree.polyline_dropped_on_road.connect(self.on_polyline_dropped_on_road)
        layout.addWidget(self.tree)

        # Control buttons
        button_layout = QHBoxLayout()

        self.add_road_btn = QPushButton("New Road")
        self.add_road_btn.clicked.connect(self.create_road)
        button_layout.addWidget(self.add_road_btn)

        self.assign_btn = QPushButton("Assign Selected")
        self.assign_btn.clicked.connect(self.assign_polylines_to_road)
        self.assign_btn.setToolTip("Assign selected polylines to selected road")
        button_layout.addWidget(self.assign_btn)

        layout.addLayout(button_layout)

    def apply_filter(self, text: str):
        """Filter tree items based on search text."""
        text = text.lower().strip()

        # Show all if empty filter
        if not text:
            self._set_all_visible(True)
            return

        # First hide all items
        self._set_all_visible(False)

        # Iterate all items and show matching ones
        iterator = QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item = iterator.value()
            item_text = item.text(0).lower()

            # Match against item text
            matches = text in item_text

            # Also check item data (type, id)
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(data, dict):
                item_type = data.get("type", "").lower()
                if text in item_type:
                    matches = True
                item_id = str(data.get("id", "")).lower()
                if text in item_id:
                    matches = True

            if matches:
                item.setHidden(False)
                self._ensure_parents_visible(item)

            iterator += 1

    def _ensure_parents_visible(self, item: QTreeWidgetItem):
        """Make all parent items visible and expanded."""
        parent = item.parent()
        while parent:
            parent.setHidden(False)
            parent.setExpanded(True)
            parent = parent.parent()
        # Also handle top-level items
        if item.parent() is None:
            item.setExpanded(True)

    def _set_all_visible(self, visible: bool):
        """Set visibility on all items."""
        iterator = QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            iterator.value().setHidden(not visible)
            iterator += 1

    def set_project(self, project: Project):
        """Update the project reference and refresh the tree."""
        self.project = project
        self._scale_factor_computed = False  # Invalidate cache
        self.refresh_tree()

    def _get_scale_factor(self) -> float | None:
        """
        Get average scale factor (meters per pixel) from project control points.

        Returns:
            Average scale factor in meters/pixel, or None if not available.
        """
        # Use cached value if already computed
        if self._scale_factor_computed:
            return self._cached_scale_factor

        self._scale_factor_computed = True
        self._cached_scale_factor = None

        if len(self.project.control_points) < 3:
            return None

        try:
            from orbit.export import create_transformer
            transformer = create_transformer(self.project.control_points)
            if transformer is None:
                return None
            scale_x, scale_y = transformer.get_scale_factor()
            self._cached_scale_factor = (scale_x + scale_y) / 2.0
            return self._cached_scale_factor
        except Exception:
            return None

    def refresh_tree(self):
        """Refresh the entire tree from project data."""
        self._scale_factor_computed = False  # Invalidate cache on refresh
        self.tree.clear()

        # Add roads as top-level items
        for road in self.project.roads:
            road_item = self.create_road_item(road)
            self.tree.addTopLevelItem(road_item)

        # Add unassigned polylines
        unassigned = self.get_unassigned_polylines()
        if unassigned:
            unassigned_item = QTreeWidgetItem(["Unassigned Polylines"])
            unassigned_item.setData(0, Qt.ItemDataRole.UserRole, "unassigned")
            for polyline in unassigned:
                polyline_item = self.create_polyline_item(polyline)
                unassigned_item.addChild(polyline_item)
            self.tree.addTopLevelItem(unassigned_item)
            unassigned_item.setExpanded(True)

        # Expand all roads
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item.data(0, Qt.ItemDataRole.UserRole) != "unassigned":
                item.setExpanded(True)

    def create_road_item(self, road: Road) -> QTreeWidgetItem:
        """Create a tree item for a road."""
        # Format display text with ID (shortened to 8 chars)
        road_id_short = road.id[:8] if len(road.id) > 8 else road.id
        text = f"{road.name} ({road_id_short})"

        item = QTreeWidgetItem([text])
        item.setData(0, Qt.ItemDataRole.UserRole, {"type": "road", "id": road.id})

        # Add polylines as children
        for polyline_id in road.polyline_ids:
            polyline = self.project.get_polyline(polyline_id)
            if polyline:
                polyline_item = self.create_polyline_item(polyline, road)
                item.addChild(polyline_item)

        return item

    def create_polyline_item(self, polyline: Polyline, road: Optional[Road] = None) -> QTreeWidgetItem:
        """Create a tree item for a polyline."""
        # Find polyline number in project
        polyline_number = None
        for i, p in enumerate(self.project.polylines):
            if p.id == polyline.id:
                polyline_number = i + 1
                break

        # Check if this is the centerline
        is_centerline = (road is not None and
                        road.centerline_id == polyline.id and
                        polyline.line_type.value == "centerline")

        # Determine line type display
        if is_centerline:
            line_type_str = "Centerline"
        else:
            line_type_str = "Centerline" if polyline.line_type.value == "centerline" else "Boundary"

        # Format text with number if found
        if polyline_number is not None:
            text = f"Polyline {polyline_number} ({polyline.point_count()} pts) - {line_type_str}"
        else:
            text = f"Polyline ({polyline.point_count()} pts) - {line_type_str}"

        item = QTreeWidgetItem([text])
        item.setData(0, Qt.ItemDataRole.UserRole, {"type": "polyline", "id": polyline.id})

        # If this is the centerline, add lane sections as children
        if is_centerline and road:
            for section in road.lane_sections:
                section_item = self.create_section_item(section, road.id)
                item.addChild(section_item)

        return item

    def create_section_item(self, section, road_id: str) -> QTreeWidgetItem:
        """Create a tree item for a lane section."""
        from orbit.models import LaneSection

        # Format section display name with s-offset range
        scale = self._get_scale_factor()
        if scale is not None:
            # Show in meters
            s_start_m = section.s_start * scale
            s_end_m = section.s_end * scale
            range_str = f"{s_start_m:.0f}m - {s_end_m:.0f}m"
        else:
            # Show in pixels
            range_str = f"{section.s_start:.0f} - {section.s_end:.0f} px"

        text = f"Section {section.section_number} ({range_str})"
        if section.single_side:
            text += f" [{section.single_side} only]"

        item = QTreeWidgetItem([text])
        item.setData(0, Qt.ItemDataRole.UserRole, {
            "type": "lane_section",
            "section_number": section.section_number,
            "road_id": road_id
        })

        # Add lanes as children
        for lane in section.get_lanes_sorted():  # Left to right order
            lane_item = self.create_lane_item(lane, road_id, section.section_number)
            item.addChild(lane_item)

        return item

    def create_lane_item(self, lane, road_id: str, section_number: Optional[int] = None) -> QTreeWidgetItem:
        """Create a tree item for a lane."""
        from orbit.models import Lane, LaneType

        # Format lane display name with type
        lane_type_name = lane.lane_type.value.title() if lane.lane_type != LaneType.NONE else "None"
        position = lane.get_display_position()
        text = f"Lane {lane.id} ({position}) - {lane_type_name}"

        item = QTreeWidgetItem([text])
        item.setData(0, Qt.ItemDataRole.UserRole, {
            "type": "lane",
            "lane_id": lane.id,
            "road_id": road_id,
            "section_number": section_number
        })
        return item

    def get_unassigned_polylines(self) -> List[Polyline]:
        """Get polylines that are not assigned to any road."""
        assigned_ids = set()
        for road in self.project.roads:
            assigned_ids.update(road.polyline_ids)

        return [p for p in self.project.polylines if p.id not in assigned_ids]

    def create_road(self):
        """Create a new road."""
        from ..dialogs.properties_dialog import RoadPropertiesDialog

        road = RoadPropertiesDialog.create_road(self.project, self, verbose=self.verbose)
        if road:
            self.project.add_road(road)
            self.road_added.emit(road)
            self.refresh_tree()

    def assign_polylines_to_road(self):
        """Assign selected polylines to selected road."""
        # Get selected items
        selected_items = self.tree.selectedItems()
        if not selected_items:
            show_info(self, "Please select a road and one or more polylines to assign.", "No Selection")
            return

        # Find selected road and polylines
        selected_road_id = None
        selected_polyline_ids = []

        for item in selected_items:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(data, dict):
                if data["type"] == "road":
                    selected_road_id = data["id"]
                elif data["type"] == "polyline":
                    selected_polyline_ids.append(data["id"])

        if not selected_road_id:
            show_info(self, "Please select a road to assign polylines to.", "No Road Selected")
            return

        if not selected_polyline_ids:
            show_info(self, "Please select one or more polylines to assign.", "No Polylines Selected")
            return

        # Get the road
        road = self.project.get_road(selected_road_id)
        if not road:
            return

        # Assign polylines
        for polyline_id in selected_polyline_ids:
            # Remove from other roads first
            for other_road in self.project.roads:
                if polyline_id in other_road.polyline_ids:
                    other_road.remove_polyline(polyline_id)

            # Add to selected road
            road.add_polyline(polyline_id)

        self.road_modified.emit(selected_road_id)
        self.refresh_tree()

    def on_polyline_dropped_on_road(self, polyline_id: str, road_id: str):
        """Handle drag-drop of a polyline onto a road."""
        road = self.project.get_road(road_id)
        if not road:
            return

        # Check if already assigned
        if polyline_id in road.polyline_ids:
            return

        # Remove from other roads first (shouldn't happen for unassigned, but be safe)
        for other_road in self.project.roads:
            if polyline_id in other_road.polyline_ids:
                other_road.remove_polyline(polyline_id)

        # Add to target road
        road.add_polyline(polyline_id)
        self.road_modified.emit(road_id)
        self.refresh_tree()

    def show_context_menu(self, position):
        """Show context menu for tree items."""
        # Check for multi-road selection first (for merge operation)
        selected_items = self.tree.selectedItems()
        selected_roads = []
        for sel_item in selected_items:
            sel_data = sel_item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(sel_data, dict) and sel_data.get("type") == "road":
                selected_roads.append(sel_data["id"])

        # If exactly 2 roads selected, show merge menu
        if len(selected_roads) == 2:
            menu = QMenu(self)
            merge_action = QAction("Merge Roads", self)

            # Validate merge is possible and determine order
            can_merge, road1_id, road2_id = self._can_merge_roads(
                selected_roads[0], selected_roads[1]
            )
            merge_action.setEnabled(can_merge)
            if not can_merge:
                merge_action.setText("Merge Roads (not consecutive)")

            # Capture IDs for lambda
            r1_id, r2_id = road1_id, road2_id
            merge_action.triggered.connect(
                lambda checked, r1=r1_id, r2=r2_id: self.roads_merge_requested.emit(r1, r2)
            )
            menu.addAction(merge_action)
            menu.exec(self.tree.viewport().mapToGlobal(position))
            return

        # Single item context menu
        item = self.tree.itemAt(position)
        if not item:
            return

        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict):
            return

        menu = QMenu(self)

        if data["type"] == "road":
            # Road context menu
            edit_action = QAction("Edit Road", self)
            edit_action.triggered.connect(lambda: self.edit_road(data["id"]))
            menu.addAction(edit_action)

            delete_action = QAction("Delete Road", self)
            delete_action.triggered.connect(lambda: self.delete_road(data["id"]))
            menu.addAction(delete_action)

        elif data["type"] == "polyline":
            # Polyline context menu
            edit_action = QAction("Edit Polyline", self)
            edit_action.triggered.connect(lambda: self.edit_polyline(data["id"]))
            menu.addAction(edit_action)

            # Check if polyline is assigned to a road
            polyline_id = data["id"]
            is_assigned = any(polyline_id in road.polyline_ids for road in self.project.roads)

            if is_assigned:
                unassign_action = QAction("Unassign from Road", self)
                unassign_action.triggered.connect(lambda: self.unassign_polyline(data["id"]))
                menu.addAction(unassign_action)
            else:
                delete_action = QAction("Delete Polyline", self)
                delete_action.triggered.connect(lambda: self.delete_polyline(data["id"]))
                menu.addAction(delete_action)

            highlight_action = QAction("Highlight in View", self)
            highlight_action.triggered.connect(lambda: self.polyline_selected.emit(data["id"]))
            menu.addAction(highlight_action)

        elif data["type"] == "lane_section":
            # Lane section context menu
            edit_action = QAction("Edit Section Properties", self)
            edit_action.triggered.connect(lambda: self.edit_section(
                data["section_number"],
                data["road_id"]
            ))
            menu.addAction(edit_action)

        elif data["type"] == "lane":
            # Lane context menu
            edit_action = QAction("Edit Lane Properties", self)
            edit_action.triggered.connect(lambda: self.edit_lane(data["lane_id"], data["road_id"]))
            menu.addAction(edit_action)

        menu.exec(self.tree.viewport().mapToGlobal(position))

    def edit_road(self, road_id: str):
        """Edit a road's properties."""
        # Emit signal for main_window to handle with undo support
        self.road_edit_requested.emit(road_id)

    def delete_road(self, road_id: str):
        """Delete a road."""
        if ask_yes_no(self, "Are you sure you want to delete this road?\n"
            "Assigned polylines will also be deleted.", "Delete Road"):
            # Emit request signal - main_window will handle deletion with undo support
            self.road_delete_requested.emit(road_id)

    def unassign_polyline(self, polyline_id: str):
        """Unassign a polyline from its road."""
        for road in self.project.roads:
            if polyline_id in road.polyline_ids:
                road.remove_polyline(polyline_id)
                self.road_modified.emit(road.id)
                self.refresh_tree()
                return

    def delete_polyline(self, polyline_id: str):
        """Delete a polyline from the project."""
        polyline = self.project.get_polyline(polyline_id)
        if not polyline:
            return

        if ask_yes_no(self, f"Are you sure you want to delete this polyline?\n"
            f"It has {polyline.point_count()} points and will be permanently removed.", "Delete Polyline"):
            # Emit request signal - main_window will handle deletion with undo support
            self.polyline_delete_requested.emit(polyline_id)

    def edit_polyline(self, polyline_id: str):
        """Edit a polyline's properties."""
        from ..dialogs.polyline_properties_dialog import PolylinePropertiesDialog

        polyline = self.project.get_polyline(polyline_id)
        if polyline:
            if PolylinePropertiesDialog.edit_polyline(polyline, self):
                # Polyline was modified, refresh displays
                self.refresh_tree()

    def edit_lane(self, lane_id: int, road_id: str):
        """Edit a lane's properties."""
        from ..dialogs.lane_properties_dialog import LanePropertiesDialog

        road = self.project.get_road(road_id)
        if road:
            lane = road.get_lane(lane_id)
            if lane:
                if LanePropertiesDialog.edit_lane(lane, self.project, road_id, None, parent=self):
                    # Lane was modified, refresh displays
                    self.road_modified.emit(road_id)
                    self.refresh_tree()

    def edit_section(self, section_number: int, road_id: str):
        """Edit a lane section's properties."""
        from ..dialogs.section_properties_dialog import SectionPropertiesDialog
        from orbit.export import create_transformer

        road = self.project.get_road(road_id)
        if road:
            section = road.get_section(section_number)
            if section:
                # Get centerline for length calculation
                centerline = None
                if road.centerline_id:
                    centerline = self.project.get_polyline(road.centerline_id)

                centerline_length = 0.0
                if centerline:
                    s_coords = road.calculate_centerline_s_coordinates(centerline.points)
                    if s_coords:
                        centerline_length = s_coords[-1]

                # Try to create transformer for metric conversion
                transformer = None
                if self.project.control_points:
                    transformer = create_transformer(self.project.control_points)

                # Get centerline points for metric calculation
                centerline_points = centerline.points if centerline else None

                if SectionPropertiesDialog.edit_section(section, road_id, centerline_length,
                                                       centerline_points, transformer, self):
                    # Section was modified, refresh displays
                    self.road_modified.emit(road_id)
                    self.refresh_tree()

    def on_item_double_clicked(self, item, column):
        """Handle double-click on item."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(data, dict):
            if data["type"] == "road":
                self.edit_road(data["id"])
            elif data["type"] == "polyline":
                self.edit_polyline(data["id"])
            elif data["type"] == "lane_section":
                self.edit_section(data["section_number"], data["road_id"])
            elif data["type"] == "lane":
                self.edit_lane(data["lane_id"], data["road_id"])

    def on_selection_changed(self):
        """Handle selection change."""
        selected_items = self.tree.selectedItems()
        if selected_items:
            item = selected_items[0]
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(data, dict):
                if data["type"] == "road":
                    self.road_selected.emit(data["id"])
                elif data["type"] == "polyline":
                    self.polyline_selected.emit(data["id"])
                elif data["type"] == "lane":
                    self.lane_selected.emit(data["road_id"], data["section_number"], data["lane_id"])

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
                        if data["type"] == "road":
                            self.delete_road(data["id"])
                        elif data["type"] == "polyline":
                            # Check if it's assigned to a road
                            is_assigned = any(
                                data["id"] in road.polyline_ids
                                for road in self.project.roads
                            )
                            if is_assigned:
                                self.unassign_polyline(data["id"])
                            else:
                                self.delete_polyline(data["id"])
                return True

        return super().eventFilter(obj, event)

    def select_road(self, road_id: str):
        """Programmatically select a road in the tree."""
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(data, dict) and data.get("type") == "road" and data.get("id") == road_id:
                self.tree.setCurrentItem(item)
                return

    def select_polyline(self, polyline_id: str):
        """Programmatically select a polyline in the tree."""
        # Search through all items
        iterator = QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item = iterator.value()
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(data, dict) and data.get("type") == "polyline" and data.get("id") == polyline_id:
                self.tree.setCurrentItem(item)
                return
            iterator += 1

    def select_lane(self, road_id: str, section_number: int, lane_id: int):
        """
        Programmatically select a lane in the tree.

        Args:
            road_id: ID of the road
            section_number: Section number containing the lane
            lane_id: Lane ID within the section
        """
        from PyQt6.QtWidgets import QTreeWidgetItemIterator

        # Search through all items
        iterator = QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item = iterator.value()
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(data, dict) and data.get("type") == "lane":
                if (data.get("road_id") == road_id and
                    data.get("section_number") == section_number and
                    data.get("lane_id") == lane_id):
                    # Expand parents to make it visible
                    parent = item.parent()
                    while parent:
                        parent.setExpanded(True)
                        parent = parent.parent()
                    # Select the item
                    self.tree.setCurrentItem(item)
                    self.tree.scrollToItem(item)
                    return
            iterator += 1

    def _can_merge_roads(
        self,
        road_a_id: str,
        road_b_id: str
    ) -> Tuple[bool, str, str]:
        """
        Check if two roads can be merged and determine the correct order.

        Roads can be merged if they are consecutive (one is predecessor of the other).

        Args:
            road_a_id: ID of first selected road
            road_b_id: ID of second selected road

        Returns:
            Tuple of (can_merge, road1_id, road2_id) where road1 is the predecessor
        """
        road_a = self.project.get_road(road_a_id)
        road_b = self.project.get_road(road_b_id)

        if not road_a or not road_b:
            return (False, road_a_id, road_b_id)

        # Check if A is predecessor of B (A.successor == B and B.predecessor == A)
        if road_a.successor_id == road_b.id and road_b.predecessor_id == road_a.id:
            return (True, road_a_id, road_b_id)

        # Check if B is predecessor of A (B.successor == A and A.predecessor == B)
        if road_b.successor_id == road_a.id and road_a.predecessor_id == road_b.id:
            return (True, road_b_id, road_a_id)

        return (False, road_a_id, road_b_id)

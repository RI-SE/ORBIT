"""
Undo command classes for ORBIT.

Uses Qt's QUndoStack/QUndoCommand framework for undo/redo functionality.
Each command captures state using model to_dict()/from_dict() methods.
"""

import copy
from typing import Optional, List, Tuple, TYPE_CHECKING

from PyQt6.QtGui import QUndoCommand

from orbit.models import (
    Polyline, Road, Junction, Signal, RoadObject, ParkingSpace,
    ConnectingRoad, LaneConnection
)

if TYPE_CHECKING:
    from .main_window import MainWindow


class AddPolylineCommand(QUndoCommand):
    """
    Command for adding a polyline.

    Undo: Remove the polyline from project and scene
    Redo: Re-add the polyline to project and scene
    """

    def __init__(self, main_window: 'MainWindow', polyline: Polyline):
        super().__init__(f"Add Polyline ({len(polyline.points)} pts)")
        self.main_window = main_window
        self.polyline_data = polyline.to_dict()
        self.polyline_id = polyline.id
        self._first_redo = True  # Skip first redo (already added by caller)

    def redo(self):
        """Add polyline to project and scene."""
        if self._first_redo:
            self._first_redo = False
            return

        polyline = Polyline.from_dict(self.polyline_data)
        self.main_window.project.add_polyline(polyline)
        self.main_window.image_view.add_polyline_graphics(polyline)
        self.main_window._refresh_trees()

    def undo(self):
        """Remove polyline from project and scene."""
        self.main_window.image_view.remove_polyline_graphics(self.polyline_id)
        self.main_window.project.remove_polyline(self.polyline_id)
        self.main_window._refresh_trees()


class DeletePolylineCommand(QUndoCommand):
    """
    Command for deleting a polyline.

    Undo: Restore the polyline to project and scene
    Redo: Delete the polyline from project and scene

    Also tracks road association for restoration.
    """

    def __init__(self, main_window: 'MainWindow', polyline_id: str):
        super().__init__("Delete Polyline")
        self.main_window = main_window
        self.polyline_id = polyline_id
        self._first_redo = True

        # Capture polyline state before deletion
        polyline = main_window.project.get_polyline(polyline_id)
        self.polyline_data = polyline.to_dict() if polyline else None

        # Track which roads contained this polyline (for restoration)
        self.road_associations: List[Tuple[str, bool]] = []
        for road in main_window.project.roads:
            if polyline_id in road.polyline_ids:
                was_centerline = (road.centerline_id == polyline_id)
                self.road_associations.append((road.id, was_centerline))

    def redo(self):
        """Delete polyline from project and scene."""
        if self._first_redo:
            self._first_redo = False
            # Deletion already performed by caller
            return

        # Remove graphics
        self.main_window.image_view.remove_polyline_graphics(self.polyline_id)

        # Remove from project (also removes from roads)
        self.main_window.project.remove_polyline(self.polyline_id)

        # Update lane graphics for affected roads
        for road_id, _ in self.road_associations:
            self.main_window.image_view.remove_road_lanes(road_id)

        self.main_window._refresh_trees()

    def undo(self):
        """Restore polyline to project and scene."""
        if not self.polyline_data:
            return

        # Recreate polyline
        polyline = Polyline.from_dict(self.polyline_data)
        self.main_window.project.add_polyline(polyline)
        self.main_window.image_view.add_polyline_graphics(polyline)

        # Restore road associations
        for road_id, was_centerline in self.road_associations:
            road = self.main_window.project.get_road(road_id)
            if road:
                road.add_polyline(self.polyline_id)
                if was_centerline:
                    road.centerline_id = self.polyline_id
                # Restore lane graphics
                scale_factors = self.main_window.get_current_scale()
                self.main_window.image_view.add_road_lanes_graphics(road, scale_factors)

        self.main_window._refresh_trees()


class ModifyPolylineCommand(QUndoCommand):
    """
    Command for modifying a polyline (points changed).

    Captures state before and after modification.
    Used for point add/move/delete operations.

    Key feature: Only captures final state after drag ends (not intermediate).
    """

    def __init__(self, main_window: 'MainWindow', polyline_id: str,
                 old_points: List[Tuple[float, float]],
                 new_points: List[Tuple[float, float]],
                 old_geo_points: Optional[List[Tuple[float, float]]] = None,
                 new_geo_points: Optional[List[Tuple[float, float]]] = None,
                 description: str = "Modify Polyline"):
        super().__init__(description)
        self.main_window = main_window
        self.polyline_id = polyline_id
        self.old_points = list(old_points)
        self.new_points = list(new_points)
        self.old_geo_points = list(old_geo_points) if old_geo_points else None
        self.new_geo_points = list(new_geo_points) if new_geo_points else None
        self._first_redo = True

    def redo(self):
        """Apply new points to polyline."""
        if self._first_redo:
            self._first_redo = False
            return

        polyline = self.main_window.project.get_polyline(self.polyline_id)
        if not polyline:
            return

        polyline.points = list(self.new_points)
        if self.new_geo_points is not None:
            polyline.geo_points = list(self.new_geo_points)

        self._update_graphics()

    def undo(self):
        """Restore old points to polyline."""
        polyline = self.main_window.project.get_polyline(self.polyline_id)
        if not polyline:
            return

        polyline.points = list(self.old_points)
        if self.old_geo_points is not None:
            polyline.geo_points = list(self.old_geo_points)

        self._update_graphics()

    def _update_graphics(self):
        """Update graphics after point changes."""
        polyline = self.main_window.project.get_polyline(self.polyline_id)
        if not polyline:
            return

        # Update polyline graphics
        if self.polyline_id in self.main_window.image_view.polyline_items:
            self.main_window.image_view.polyline_items[self.polyline_id].update_graphics()

        # Update s-offset labels if visible
        if self.main_window.image_view.soffsets_visible:
            self.main_window.image_view._update_soffset_labels(self.polyline_id)

        # Update lane graphics for affected roads (if this is a centerline)
        from orbit.models import LineType
        if polyline.line_type == LineType.CENTERLINE:
            for road in self.main_window.project.roads:
                if road.centerline_id == self.polyline_id:
                    road.update_section_boundaries(polyline.points)
                    if road.id in self.main_window.image_view.road_lanes_items:
                        self.main_window.image_view.road_lanes_items[road.id].update_graphics()

        self.main_window._refresh_trees()

    def id(self) -> int:
        """Return command ID for merging consecutive edits."""
        return hash(("ModifyPolyline", self.polyline_id)) & 0x7FFFFFFF

    def mergeWith(self, other: QUndoCommand) -> bool:
        """
        Merge consecutive modifications to same polyline.

        This prevents many tiny undo entries during rapid editing.
        Only merges if same polyline, keeps first old_points and last new_points.
        """
        if not isinstance(other, ModifyPolylineCommand):
            return False
        if other.polyline_id != self.polyline_id:
            return False

        # Keep our old_points, take their new_points
        self.new_points = other.new_points
        self.new_geo_points = other.new_geo_points
        return True


class LinkRoadsCommand(QUndoCommand):
    """Command for linking two roads as predecessor/successor.

    Sets bidirectional connection (A.successor = B, B.predecessor = A)
    and snaps endpoint coordinates to match. Captures state of both
    roads for full undo support.
    """

    def __init__(self, main_window: 'MainWindow',
                 road_a_id: str, road_b_id: str,
                 a_contact: str, b_contact: str):
        super().__init__("Link Roads")
        self.main_window = main_window
        self.road_a_id = road_a_id
        self.road_b_id = road_b_id
        self.a_contact = a_contact  # "start" or "end" — which end of road A
        self.b_contact = b_contact  # "start" or "end" — which end of road B
        self._first_redo = True

        # Capture old state of both roads
        road_a = main_window.project.get_road(road_a_id)
        road_b = main_window.project.get_road(road_b_id)
        self.old_a_data = road_a.to_dict() if road_a else None
        self.old_b_data = road_b.to_dict() if road_b else None

        # Capture old centerline points for coordinate snap undo
        self.old_a_cl_points = None
        self.old_b_cl_points = None
        if road_a and road_a.centerline_id:
            cl_a = main_window.project.get_polyline(road_a.centerline_id)
            if cl_a:
                self.old_a_cl_points = list(cl_a.points)
        if road_b and road_b.centerline_id:
            cl_b = main_window.project.get_polyline(road_b.centerline_id)
            if cl_b:
                self.old_b_cl_points = list(cl_b.points)

    def redo(self):
        """Set bidirectional connection and snap coordinates."""
        if self._first_redo:
            self._first_redo = False
            return

        road_a = self.main_window.project.get_road(self.road_a_id)
        road_b = self.main_window.project.get_road(self.road_b_id)
        if not road_a or not road_b:
            return

        self._apply_link(road_a, road_b)
        self.main_window.project.enforce_road_link_coordinates(self.road_a_id)
        self._refresh_graphics(road_a)
        self._refresh_graphics(road_b)
        self.main_window._refresh_trees()

    def undo(self):
        """Restore both roads to their pre-link state."""
        road_a = self.main_window.project.get_road(self.road_a_id)
        road_b = self.main_window.project.get_road(self.road_b_id)
        if not road_a or not road_b:
            return

        # Restore road A link fields from old data
        if self.old_a_data:
            old_a = Road.from_dict(self.old_a_data)
            road_a.predecessor_id = old_a.predecessor_id
            road_a.predecessor_contact = old_a.predecessor_contact
            road_a.successor_id = old_a.successor_id
            road_a.successor_contact = old_a.successor_contact

        # Restore road B link fields from old data
        if self.old_b_data:
            old_b = Road.from_dict(self.old_b_data)
            road_b.predecessor_id = old_b.predecessor_id
            road_b.predecessor_contact = old_b.predecessor_contact
            road_b.successor_id = old_b.successor_id
            road_b.successor_contact = old_b.successor_contact

        # Restore centerline points
        if self.old_a_cl_points and road_a.centerline_id:
            cl_a = self.main_window.project.get_polyline(road_a.centerline_id)
            if cl_a:
                cl_a.points = list(self.old_a_cl_points)
        if self.old_b_cl_points and road_b.centerline_id:
            cl_b = self.main_window.project.get_polyline(road_b.centerline_id)
            if cl_b:
                cl_b.points = list(self.old_b_cl_points)

        self._refresh_graphics(road_a)
        self._refresh_graphics(road_b)
        self.main_window._refresh_trees()

    def _apply_link(self, road_a: Road, road_b: Road):
        """Set the bidirectional connection fields."""
        if self.a_contact == "end":
            road_a.successor_id = road_b.id
            road_a.successor_contact = self.b_contact
        else:
            road_a.predecessor_id = road_b.id
            road_a.predecessor_contact = self.b_contact

        if self.b_contact == "start":
            road_b.predecessor_id = road_a.id
            road_b.predecessor_contact = self.a_contact
        else:
            road_b.successor_id = road_a.id
            road_b.successor_contact = self.a_contact

    def _refresh_graphics(self, road: Road):
        """Refresh polyline and lane graphics for a road."""
        if road.centerline_id and road.centerline_id in self.main_window.image_view.polyline_items:
            self.main_window.image_view.polyline_items[road.centerline_id].update_graphics()
        if road.id in self.main_window.image_view.road_lanes_items:
            cl = self.main_window.project.get_polyline(road.centerline_id)
            if cl:
                road.update_section_boundaries(cl.points)
            self.main_window.image_view.road_lanes_items[road.id].update_graphics()


class UnlinkRoadsCommand(QUndoCommand):
    """Command for unlinking two connected roads.

    Clears the predecessor/successor link between two roads.
    Captures state of both roads for full undo support.
    """

    def __init__(self, main_window: 'MainWindow',
                 road_id: str, linked_road_id: str):
        super().__init__("Disconnect Roads")
        self.main_window = main_window
        self.road_id = road_id
        self.linked_road_id = linked_road_id
        self._first_redo = True

        # Capture old state of both roads
        road = main_window.project.get_road(road_id)
        linked = main_window.project.get_road(linked_road_id)
        self.old_road_data = road.to_dict() if road else None
        self.old_linked_data = linked.to_dict() if linked else None

    def redo(self):
        """Clear the connection between the two roads."""
        if self._first_redo:
            self._first_redo = False
            return

        self._clear_link()
        self.main_window._refresh_trees()

    def undo(self):
        """Restore the connection between the two roads."""
        road = self.main_window.project.get_road(self.road_id)
        linked = self.main_window.project.get_road(self.linked_road_id)

        if road and self.old_road_data:
            old = Road.from_dict(self.old_road_data)
            road.predecessor_id = old.predecessor_id
            road.predecessor_contact = old.predecessor_contact
            road.successor_id = old.successor_id
            road.successor_contact = old.successor_contact

        if linked and self.old_linked_data:
            old = Road.from_dict(self.old_linked_data)
            linked.predecessor_id = old.predecessor_id
            linked.predecessor_contact = old.predecessor_contact
            linked.successor_id = old.successor_id
            linked.successor_contact = old.successor_contact

        self.main_window._refresh_trees()

    def _clear_link(self):
        """Clear the bidirectional link between the two roads."""
        road = self.main_window.project.get_road(self.road_id)
        linked = self.main_window.project.get_road(self.linked_road_id)

        if road:
            if road.predecessor_id == self.linked_road_id:
                road.predecessor_id = None
            if road.successor_id == self.linked_road_id:
                road.successor_id = None

        if linked:
            if linked.predecessor_id == self.road_id:
                linked.predecessor_id = None
            if linked.successor_id == self.road_id:
                linked.successor_id = None


class AddRoadCommand(QUndoCommand):
    """
    Command for adding a road.

    Undo: Remove the road and its lane graphics
    Redo: Re-add the road and lane graphics
    """

    def __init__(self, main_window: 'MainWindow', road: Road):
        super().__init__(f"Add Road '{road.name}'")
        self.main_window = main_window
        self.road_data = road.to_dict()
        self.road_id = road.id
        self._first_redo = True

    def redo(self):
        """Add road to project."""
        if self._first_redo:
            self._first_redo = False
            return

        road = Road.from_dict(self.road_data)
        self.main_window.project.add_road(road)

        # Add lane graphics if road has centerline
        if road.centerline_id:
            scale_factors = self.main_window.get_current_scale()
            self.main_window.image_view.add_road_lanes_graphics(road, scale_factors)

        self.main_window._refresh_trees()

    def undo(self):
        """Remove road from project."""
        # Remove lane graphics
        self.main_window.image_view.remove_road_lanes(self.road_id)
        # Remove from project
        self.main_window.project.remove_road(self.road_id)
        self.main_window._refresh_trees()


class DeleteRoadCommand(QUndoCommand):
    """
    Command for deleting a road.

    Undo: Restore the road, its polylines, and lane graphics
    Redo: Delete the road, its polylines, and lane graphics
    """

    def __init__(self, main_window: 'MainWindow', road_id: str):
        super().__init__("Delete Road")
        self.main_window = main_window
        self.road_id = road_id
        self._first_redo = True

        # Capture road state before deletion (deep copy to avoid
        # mutation via project.remove_polyline -> road.remove_polyline)
        road = main_window.project.get_road(road_id)
        self.road_data = copy.deepcopy(road.to_dict()) if road else None

        # Capture assigned polyline state before deletion
        self.polyline_data_list = []
        if road:
            for pid in road.polyline_ids:
                polyline = main_window.project.get_polyline(pid)
                if polyline:
                    self.polyline_data_list.append(polyline.to_dict())

        # Capture incoming references that will be cleared on deletion
        # (road_id, field_name) tuples for successor/predecessor links
        self.cleared_road_refs = []
        for r in main_window.project.roads:
            if r.id == road_id:
                continue
            if r.successor_id == road_id:
                self.cleared_road_refs.append((r.id, 'successor_id'))
            if r.predecessor_id == road_id:
                self.cleared_road_refs.append((r.id, 'predecessor_id'))

        # Capture junction items that will be removed
        # (junction_id, type, serialized_data) tuples
        self.removed_junction_items = []
        for junction in main_window.project.junctions:
            for cr in junction.connecting_roads:
                if cr.predecessor_road_id == road_id or cr.successor_road_id == road_id:
                    self.removed_junction_items.append(
                        (junction.id, 'connecting_road', copy.deepcopy(cr.to_dict())))
            for lc in junction.lane_connections:
                if lc.from_road_id == road_id or lc.to_road_id == road_id:
                    self.removed_junction_items.append(
                        (junction.id, 'lane_connection', copy.deepcopy(lc.to_dict())))

    def redo(self):
        """Delete road and its polylines from project."""
        if self._first_redo:
            self._first_redo = False
            return

        road = self.main_window.project.get_road(self.road_id)
        if road:
            # Remove polyline graphics and data
            for pid in list(road.polyline_ids):
                self.main_window.image_view.remove_polyline_graphics(pid)
                self.main_window.project.remove_polyline(pid)

        # Remove connecting road graphics that will be orphaned
        for junction in self.main_window.project.junctions:
            for cr in junction.connecting_roads:
                if cr.predecessor_road_id == self.road_id or cr.successor_road_id == self.road_id:
                    self.main_window.image_view.remove_connecting_road_graphics(cr.id)

        # Remove lane graphics
        self.main_window.image_view.remove_road_lanes(self.road_id)
        # Remove road from project
        self.main_window.project.remove_road(self.road_id)
        self.main_window._refresh_trees()

    def undo(self):
        """Restore road, its polylines, and cleared references."""
        if not self.road_data:
            return

        # Restore polylines first (road references them)
        for pdata in self.polyline_data_list:
            polyline = Polyline.from_dict(pdata)
            self.main_window.project.polylines.append(polyline)
            self.main_window.image_view.add_polyline_graphics(polyline)

        road = Road.from_dict(self.road_data)
        self.main_window.project.add_road(road)

        # Restore cleared successor/predecessor references on other roads
        for ref_road_id, field_name in self.cleared_road_refs:
            ref_road = self.main_window.project.get_road(ref_road_id)
            if ref_road:
                setattr(ref_road, field_name, self.road_id)

        # Restore removed junction connecting_roads and lane_connections
        scale_factors = self.main_window.get_current_scale()
        for junction_id, item_type, data in self.removed_junction_items:
            junction = self.main_window.project.get_junction(junction_id)
            if junction:
                if item_type == 'connecting_road':
                    cr = ConnectingRoad.from_dict(data)
                    junction.connecting_roads.append(cr)
                    self.main_window.image_view.add_connecting_road_graphics(
                        cr, scale_factors)
                elif item_type == 'lane_connection':
                    junction.lane_connections.append(LaneConnection.from_dict(data))

        # Restore lane graphics if road has centerline
        if road.centerline_id:
            self.main_window.image_view.add_road_lanes_graphics(road, scale_factors)

        self.main_window._refresh_trees()


class ModifyPolylinePropertiesCommand(QUndoCommand):
    """Command for modifying polyline properties (line type, road mark, etc.)."""

    def __init__(self, main_window: 'MainWindow', polyline_id: str,
                 old_data: dict, new_data: dict):
        super().__init__("Edit Polyline Properties")
        self.main_window = main_window
        self.polyline_id = polyline_id
        self.old_data = old_data
        self.new_data = new_data
        self._first_redo = True

    def redo(self):
        if self._first_redo:
            self._first_redo = False
            return
        self._apply_data(self.new_data)

    def undo(self):
        self._apply_data(self.old_data)

    def _apply_data(self, data: dict):
        polyline = self.main_window.project.get_polyline(self.polyline_id)
        if not polyline:
            return
        # Restore from data
        restored = Polyline.from_dict(data)
        polyline.line_type = restored.line_type
        polyline.road_mark_type = restored.road_mark_type
        polyline.name = restored.name
        # Update graphics
        self.main_window.image_view.update_polyline(self.polyline_id)
        self.main_window._refresh_trees()


class ModifyRoadCommand(QUndoCommand):
    """Command for modifying road properties."""

    def __init__(self, main_window: 'MainWindow', road_id: str,
                 old_data: dict, new_data: dict, description: str = "Edit Road"):
        super().__init__(description)
        self.main_window = main_window
        self.road_id = road_id
        self.old_data = old_data
        self.new_data = new_data
        self._first_redo = True

    def redo(self):
        if self._first_redo:
            self._first_redo = False
            return
        self._apply_data(self.new_data)

    def undo(self):
        self._apply_data(self.old_data)

    def _apply_data(self, data: dict):
        # Remove old road and its graphics
        self.main_window.image_view.remove_road_lanes(self.road_id)
        self.main_window.project.remove_road(self.road_id)
        # Recreate from data
        road = Road.from_dict(data)
        self.main_window.project.add_road(road)
        # Restore lane graphics
        if road.centerline_id:
            scale_factors = self.main_window.get_current_scale()
            self.main_window.image_view.add_road_lanes_graphics(road, scale_factors)
        self.main_window._refresh_trees()


class SplitSectionCommand(QUndoCommand):
    """Command for splitting a lane section."""

    def __init__(self, main_window: 'MainWindow', road_id: str,
                 old_road_data: dict, new_road_data: dict):
        super().__init__("Split Section")
        self.main_window = main_window
        self.road_id = road_id
        self.old_road_data = old_road_data
        self.new_road_data = new_road_data
        self._first_redo = True

    def redo(self):
        if self._first_redo:
            self._first_redo = False
            return
        self._apply_road_data(self.new_road_data)

    def undo(self):
        self._apply_road_data(self.old_road_data)

    def _apply_road_data(self, data: dict):
        # Remove old road and graphics
        self.main_window.image_view.remove_road_lanes(self.road_id)
        self.main_window.project.remove_road(self.road_id)
        # Recreate from data
        road = Road.from_dict(data)
        self.main_window.project.add_road(road)
        # Restore lane graphics
        if road.centerline_id:
            scale_factors = self.main_window.get_current_scale()
            self.main_window.image_view.add_road_lanes_graphics(road, scale_factors)
        self.main_window._refresh_trees()


class ModifySectionCommand(QUndoCommand):
    """Command for modifying section properties."""

    def __init__(self, main_window: 'MainWindow', road_id: str,
                 old_road_data: dict, new_road_data: dict):
        super().__init__("Edit Section")
        self.main_window = main_window
        self.road_id = road_id
        self.old_road_data = old_road_data
        self.new_road_data = new_road_data
        self._first_redo = True

    def redo(self):
        if self._first_redo:
            self._first_redo = False
            return
        self._apply_road_data(self.new_road_data)

    def undo(self):
        self._apply_road_data(self.old_road_data)

    def _apply_road_data(self, data: dict):
        self.main_window.image_view.remove_road_lanes(self.road_id)
        self.main_window.project.remove_road(self.road_id)
        road = Road.from_dict(data)
        self.main_window.project.add_road(road)
        if road.centerline_id:
            scale_factors = self.main_window.get_current_scale()
            self.main_window.image_view.add_road_lanes_graphics(road, scale_factors)
        self.main_window._refresh_trees()


class SplitRoadCommand(QUndoCommand):
    """Command for splitting a road into two roads."""

    def __init__(self, main_window: 'MainWindow',
                 original_road_data: dict, road1_data: dict, road2_data: dict,
                 original_polyline_data: dict, poly1_data: dict, poly2_data: dict):
        super().__init__("Split Road")
        self.main_window = main_window
        self.original_road_data = original_road_data
        self.road1_data = road1_data
        self.road2_data = road2_data
        self.original_polyline_data = original_polyline_data
        self.poly1_data = poly1_data
        self.poly2_data = poly2_data
        self.original_road_id = original_road_data['id']
        self.original_polyline_id = original_polyline_data['id']
        self.road1_id = road1_data['id']
        self.road2_id = road2_data['id']
        self.poly1_id = poly1_data['id']
        self.poly2_id = poly2_data['id']
        self._first_redo = True

    def redo(self):
        if self._first_redo:
            self._first_redo = False
            return
        # Remove original road and polyline
        self.main_window.image_view.remove_road_lanes(self.original_road_id)
        self.main_window.project.remove_road(self.original_road_id)
        self.main_window.image_view.remove_polyline_graphics(self.original_polyline_id)
        self.main_window.project.remove_polyline(self.original_polyline_id)
        # Add split polylines
        poly1 = Polyline.from_dict(self.poly1_data)
        poly2 = Polyline.from_dict(self.poly2_data)
        self.main_window.project.add_polyline(poly1)
        self.main_window.project.add_polyline(poly2)
        self.main_window.image_view.add_polyline_graphics(poly1)
        self.main_window.image_view.add_polyline_graphics(poly2)
        # Add split roads
        road1 = Road.from_dict(self.road1_data)
        road2 = Road.from_dict(self.road2_data)
        self.main_window.project.add_road(road1)
        self.main_window.project.add_road(road2)
        scale_factors = self.main_window.get_current_scale()
        if road1.centerline_id:
            self.main_window.image_view.add_road_lanes_graphics(road1, scale_factors)
        if road2.centerline_id:
            self.main_window.image_view.add_road_lanes_graphics(road2, scale_factors)
        self.main_window._refresh_trees()

    def undo(self):
        # Remove split roads and polylines
        self.main_window.image_view.remove_road_lanes(self.road1_id)
        self.main_window.image_view.remove_road_lanes(self.road2_id)
        self.main_window.project.remove_road(self.road1_id)
        self.main_window.project.remove_road(self.road2_id)
        self.main_window.image_view.remove_polyline_graphics(self.poly1_id)
        self.main_window.image_view.remove_polyline_graphics(self.poly2_id)
        self.main_window.project.remove_polyline(self.poly1_id)
        self.main_window.project.remove_polyline(self.poly2_id)
        # Restore original polyline and road
        original_poly = Polyline.from_dict(self.original_polyline_data)
        self.main_window.project.add_polyline(original_poly)
        self.main_window.image_view.add_polyline_graphics(original_poly)
        original_road = Road.from_dict(self.original_road_data)
        self.main_window.project.add_road(original_road)
        if original_road.centerline_id:
            scale_factors = self.main_window.get_current_scale()
            self.main_window.image_view.add_road_lanes_graphics(original_road, scale_factors)
        self.main_window._refresh_trees()


class MergeRoadsCommand(QUndoCommand):
    """Command for merging two roads into one."""

    def __init__(self, main_window: 'MainWindow',
                 road1_data: dict, road2_data: dict,
                 merged_road_data: dict,
                 poly1_data: dict, poly2_data: dict,
                 merged_poly_data: dict):
        super().__init__("Merge Roads")
        self.main_window = main_window
        self.road1_data = road1_data
        self.road2_data = road2_data
        self.merged_road_data = merged_road_data
        self.poly1_data = poly1_data
        self.poly2_data = poly2_data
        self.merged_poly_data = merged_poly_data
        self.road1_id = road1_data['id']
        self.road2_id = road2_data['id']
        self.merged_road_id = merged_road_data['id']
        self.poly1_id = poly1_data['id']
        self.poly2_id = poly2_data['id']
        self.merged_poly_id = merged_poly_data['id']
        self._first_redo = True

    def redo(self):
        if self._first_redo:
            self._first_redo = False
            return
        # Remove original roads and polylines
        self.main_window.image_view.remove_road_lanes(self.road1_id)
        self.main_window.image_view.remove_road_lanes(self.road2_id)
        self.main_window.project.remove_road(self.road1_id)
        self.main_window.project.remove_road(self.road2_id)
        self.main_window.image_view.remove_polyline_graphics(self.poly1_id)
        self.main_window.image_view.remove_polyline_graphics(self.poly2_id)
        self.main_window.project.remove_polyline(self.poly1_id)
        self.main_window.project.remove_polyline(self.poly2_id)
        # Add merged polyline and road
        merged_poly = Polyline.from_dict(self.merged_poly_data)
        self.main_window.project.add_polyline(merged_poly)
        self.main_window.image_view.add_polyline_graphics(merged_poly)
        merged_road = Road.from_dict(self.merged_road_data)
        self.main_window.project.add_road(merged_road)
        if merged_road.centerline_id:
            scale_factors = self.main_window.get_current_scale()
            self.main_window.image_view.add_road_lanes_graphics(merged_road, scale_factors)
        self.main_window._refresh_trees()

    def undo(self):
        # Remove merged road and polyline
        self.main_window.image_view.remove_road_lanes(self.merged_road_id)
        self.main_window.project.remove_road(self.merged_road_id)
        self.main_window.image_view.remove_polyline_graphics(self.merged_poly_id)
        self.main_window.project.remove_polyline(self.merged_poly_id)
        # Restore original polylines and roads
        poly1 = Polyline.from_dict(self.poly1_data)
        poly2 = Polyline.from_dict(self.poly2_data)
        self.main_window.project.add_polyline(poly1)
        self.main_window.project.add_polyline(poly2)
        self.main_window.image_view.add_polyline_graphics(poly1)
        self.main_window.image_view.add_polyline_graphics(poly2)
        road1 = Road.from_dict(self.road1_data)
        road2 = Road.from_dict(self.road2_data)
        self.main_window.project.add_road(road1)
        self.main_window.project.add_road(road2)
        scale_factors = self.main_window.get_current_scale()
        if road1.centerline_id:
            self.main_window.image_view.add_road_lanes_graphics(road1, scale_factors)
        if road2.centerline_id:
            self.main_window.image_view.add_road_lanes_graphics(road2, scale_factors)
        self.main_window._refresh_trees()


# ============================================================================
# Junction Commands
# ============================================================================

class AddJunctionCommand(QUndoCommand):
    """Command for adding a junction."""

    def __init__(self, main_window: 'MainWindow', junction: Junction):
        super().__init__(f"Add Junction '{junction.name}'")
        self.main_window = main_window
        self.junction_data = junction.to_dict()
        self.junction_id = junction.id
        self._first_redo = True

    def redo(self):
        if self._first_redo:
            self._first_redo = False
            return
        junction = Junction.from_dict(self.junction_data)
        self.main_window.project.add_junction(junction)
        self.main_window.image_view.add_junction_graphics(junction)
        self.main_window._refresh_trees()

    def undo(self):
        self.main_window.image_view.remove_junction_graphics(self.junction_id)
        self.main_window.project.remove_junction(self.junction_id)
        self.main_window._refresh_trees()


class DeleteJunctionCommand(QUndoCommand):
    """Command for deleting a junction."""

    def __init__(self, main_window: 'MainWindow', junction_id: str):
        super().__init__("Delete Junction")
        self.main_window = main_window
        self.junction_id = junction_id
        self._first_redo = True
        # Capture junction state before deletion
        junction = main_window.project.get_junction(junction_id)
        self.junction_data = junction.to_dict() if junction else None
        # Track connecting road IDs for graphics cleanup/restore
        self.connecting_road_ids = [
            cr.id for cr in junction.connecting_roads
        ] if junction else []
        # Capture road junction references that will be cleared on deletion
        self._road_junction_refs = []
        if junction:
            for road in main_window.project.roads:
                if road.predecessor_junction_id == junction_id:
                    self._road_junction_refs.append(
                        (road.id, 'predecessor', road.predecessor_junction_id))
                if road.successor_junction_id == junction_id:
                    self._road_junction_refs.append(
                        (road.id, 'successor', road.successor_junction_id))

    def redo(self):
        if self._first_redo:
            self._first_redo = False
            return
        # Remove connecting road graphics before junction
        for cr_id in self.connecting_road_ids:
            self.main_window.image_view.remove_connecting_road_graphics(cr_id)
        self.main_window.image_view.remove_junction_graphics(self.junction_id)
        self.main_window.project.remove_junction(self.junction_id)
        self.main_window._refresh_trees()

    def undo(self):
        if not self.junction_data:
            return
        junction = Junction.from_dict(self.junction_data)
        self.main_window.project.add_junction(junction)
        self.main_window.image_view.add_junction_graphics(junction)
        # Restore connecting road graphics
        scale_factors = self.main_window.get_current_scale()
        for cr in junction.connecting_roads:
            self.main_window.image_view.add_connecting_road_graphics(cr, scale_factors)
        # Restore road junction references cleared during deletion
        for road_id, ref_type, ref_value in self._road_junction_refs:
            road = self.main_window.project.get_road(road_id)
            if road:
                if ref_type == 'predecessor':
                    road.predecessor_junction_id = ref_value
                else:
                    road.successor_junction_id = ref_value
        self.main_window._refresh_trees()


class ModifyJunctionCommand(QUndoCommand):
    """Command for modifying junction properties."""

    def __init__(self, main_window: 'MainWindow', junction_id: str,
                 old_data: dict, new_data: dict, description: str = "Edit Junction"):
        super().__init__(description)
        self.main_window = main_window
        self.junction_id = junction_id
        self.old_data = old_data
        self.new_data = new_data
        self._first_redo = True

    def redo(self):
        if self._first_redo:
            self._first_redo = False
            return
        self._apply_data(self.new_data)

    def undo(self):
        self._apply_data(self.old_data)

    def _apply_data(self, data: dict):
        # Remove old junction and graphics (keep road refs since junction is re-added)
        self.main_window.image_view.remove_junction_graphics(self.junction_id)
        self.main_window.project.remove_junction(self.junction_id, cleanup_road_refs=False)
        # Recreate from data
        junction = Junction.from_dict(data)
        self.main_window.project.add_junction(junction)
        self.main_window.image_view.add_junction_graphics(junction)
        self.main_window._refresh_trees()


# ============================================================================
# Connecting Road Commands
# ============================================================================

class ModifyConnectingRoadCommand(QUndoCommand):
    """Command for modifying connecting road properties."""

    def __init__(self, main_window: 'MainWindow', connecting_road_id: str,
                 junction_id: str, old_data: dict, new_data: dict,
                 description: str = "Edit Connecting Road"):
        super().__init__(description)
        self.main_window = main_window
        self.connecting_road_id = connecting_road_id
        self.junction_id = junction_id
        self.old_data = old_data
        self.new_data = new_data
        self._first_redo = True

    def redo(self):
        if self._first_redo:
            self._first_redo = False
            return
        self._apply_data(self.new_data)

    def undo(self):
        self._apply_data(self.old_data)

    def _apply_data(self, data: dict):
        junction = self.main_window.project.get_junction(self.junction_id)
        if not junction:
            return
        # Find and update the connecting road
        for i, cr in enumerate(junction.connecting_roads):
            if cr.id == self.connecting_road_id:
                junction.connecting_roads[i] = ConnectingRoad.from_dict(data)
                break
        # Refresh graphics
        scale_factors = self.main_window.get_current_scale()
        self.main_window.image_view.update_connecting_road_graphics(
            self.connecting_road_id, scale_factors)
        self.main_window._refresh_trees()


# ============================================================================
# Signal Commands
# ============================================================================

class AddSignalCommand(QUndoCommand):
    """Command for adding a signal."""

    def __init__(self, main_window: 'MainWindow', signal: Signal):
        super().__init__(f"Add Signal")
        self.main_window = main_window
        self.signal_data = signal.to_dict()
        self.signal_id = signal.id
        self._first_redo = True

    def redo(self):
        if self._first_redo:
            self._first_redo = False
            return
        signal = Signal.from_dict(self.signal_data)
        self.main_window.project.add_signal(signal)
        self.main_window.image_view.add_signal_graphics(signal)
        self.main_window._refresh_trees()

    def undo(self):
        self.main_window.image_view.remove_signal_graphics(self.signal_id)
        self.main_window.project.remove_signal(self.signal_id)
        self.main_window._refresh_trees()


class DeleteSignalCommand(QUndoCommand):
    """Command for deleting a signal."""

    def __init__(self, main_window: 'MainWindow', signal_id: str):
        super().__init__("Delete Signal")
        self.main_window = main_window
        self.signal_id = signal_id
        self._first_redo = True
        signal = main_window.project.get_signal(signal_id)
        self.signal_data = signal.to_dict() if signal else None

    def redo(self):
        if self._first_redo:
            self._first_redo = False
            return
        self.main_window.image_view.remove_signal_graphics(self.signal_id)
        self.main_window.project.remove_signal(self.signal_id)
        self.main_window._refresh_trees()

    def undo(self):
        if not self.signal_data:
            return
        signal = Signal.from_dict(self.signal_data)
        self.main_window.project.add_signal(signal)
        self.main_window.image_view.add_signal_graphics(signal)
        self.main_window._refresh_trees()


class ModifySignalCommand(QUndoCommand):
    """Command for modifying signal properties."""

    def __init__(self, main_window: 'MainWindow', signal_id: str,
                 old_data: dict, new_data: dict, description: str = "Edit Signal"):
        super().__init__(description)
        self.main_window = main_window
        self.signal_id = signal_id
        self.old_data = old_data
        self.new_data = new_data
        self._first_redo = True

    def redo(self):
        if self._first_redo:
            self._first_redo = False
            return
        self._apply_data(self.new_data)

    def undo(self):
        self._apply_data(self.old_data)

    def _apply_data(self, data: dict):
        self.main_window.image_view.remove_signal_graphics(self.signal_id)
        self.main_window.project.remove_signal(self.signal_id)
        signal = Signal.from_dict(data)
        self.main_window.project.add_signal(signal)
        self.main_window.image_view.add_signal_graphics(signal)
        self.main_window._refresh_trees()


# ============================================================================
# Object Commands
# ============================================================================

class AddObjectCommand(QUndoCommand):
    """Command for adding an object."""

    def __init__(self, main_window: 'MainWindow', obj: RoadObject):
        super().__init__(f"Add Object '{obj.name}'")
        self.main_window = main_window
        self.object_data = obj.to_dict()
        self.object_id = obj.id
        self._first_redo = True

    def redo(self):
        if self._first_redo:
            self._first_redo = False
            return
        obj = RoadObject.from_dict(self.object_data)
        self.main_window.project.add_object(obj)
        scale_factor = self.main_window.get_current_scale()
        self.main_window.image_view.add_object_graphics(obj, scale_factor)
        self.main_window._refresh_trees()

    def undo(self):
        self.main_window.image_view.remove_object_graphics(self.object_id)
        self.main_window.project.remove_object(self.object_id)
        self.main_window._refresh_trees()


class DeleteObjectCommand(QUndoCommand):
    """Command for deleting an object."""

    def __init__(self, main_window: 'MainWindow', object_id: str):
        super().__init__("Delete Object")
        self.main_window = main_window
        self.object_id = object_id
        self._first_redo = True
        obj = main_window.project.get_object(object_id)
        self.object_data = obj.to_dict() if obj else None

    def redo(self):
        if self._first_redo:
            self._first_redo = False
            return
        self.main_window.image_view.remove_object_graphics(self.object_id)
        self.main_window.project.remove_object(self.object_id)
        self.main_window._refresh_trees()

    def undo(self):
        if not self.object_data:
            return
        obj = RoadObject.from_dict(self.object_data)
        self.main_window.project.add_object(obj)
        scale_factor = self.main_window.get_current_scale()
        self.main_window.image_view.add_object_graphics(obj, scale_factor)
        self.main_window._refresh_trees()


class ModifyObjectCommand(QUndoCommand):
    """Command for modifying object properties."""

    def __init__(self, main_window: 'MainWindow', object_id: str,
                 old_data: dict, new_data: dict, description: str = "Edit Object"):
        super().__init__(description)
        self.main_window = main_window
        self.object_id = object_id
        self.old_data = old_data
        self.new_data = new_data
        self._first_redo = True

    def redo(self):
        if self._first_redo:
            self._first_redo = False
            return
        self._apply_data(self.new_data)

    def undo(self):
        self._apply_data(self.old_data)

    def _apply_data(self, data: dict):
        self.main_window.image_view.remove_object_graphics(self.object_id)
        self.main_window.project.remove_object(self.object_id)
        obj = RoadObject.from_dict(data)
        self.main_window.project.add_object(obj)
        scale_factor = self.main_window.get_current_scale()
        self.main_window.image_view.add_object_graphics(obj, scale_factor)
        self.main_window._refresh_trees()


# ============================================================================
# Parking Commands
# ============================================================================

class AddParkingCommand(QUndoCommand):
    """Command for adding a parking space."""

    def __init__(self, main_window: 'MainWindow', parking: ParkingSpace):
        super().__init__("Add Parking")
        self.main_window = main_window
        self.parking_data = parking.to_dict()
        self.parking_id = parking.id
        self._first_redo = True

    def redo(self):
        if self._first_redo:
            self._first_redo = False
            return
        parking = ParkingSpace.from_dict(self.parking_data)
        self.main_window.project.add_parking(parking)
        scale_factor = self.main_window.get_current_scale()
        self.main_window.image_view.add_parking_graphics(parking, scale_factor)
        self.main_window._refresh_trees()

    def undo(self):
        self.main_window.image_view.remove_parking_graphics(self.parking_id)
        self.main_window.project.remove_parking(self.parking_id)
        self.main_window._refresh_trees()


class DeleteParkingCommand(QUndoCommand):
    """Command for deleting a parking space."""

    def __init__(self, main_window: 'MainWindow', parking_id: str):
        super().__init__("Delete Parking")
        self.main_window = main_window
        self.parking_id = parking_id
        self._first_redo = True
        parking = main_window.project.get_parking(parking_id)
        self.parking_data = parking.to_dict() if parking else None

    def redo(self):
        if self._first_redo:
            self._first_redo = False
            return
        self.main_window.image_view.remove_parking_graphics(self.parking_id)
        self.main_window.project.remove_parking(self.parking_id)
        self.main_window._refresh_trees()

    def undo(self):
        if not self.parking_data:
            return
        parking = ParkingSpace.from_dict(self.parking_data)
        self.main_window.project.add_parking(parking)
        scale_factor = self.main_window.get_current_scale()
        self.main_window.image_view.add_parking_graphics(parking, scale_factor)
        self.main_window._refresh_trees()


class ModifyParkingCommand(QUndoCommand):
    """Command for modifying parking properties."""

    def __init__(self, main_window: 'MainWindow', parking_id: str,
                 old_data: dict, new_data: dict, description: str = "Edit Parking"):
        super().__init__(description)
        self.main_window = main_window
        self.parking_id = parking_id
        self.old_data = old_data
        self.new_data = new_data
        self._first_redo = True

    def redo(self):
        if self._first_redo:
            self._first_redo = False
            return
        self._apply_data(self.new_data)

    def undo(self):
        self._apply_data(self.old_data)

    def _apply_data(self, data: dict):
        self.main_window.image_view.remove_parking_graphics(self.parking_id)
        self.main_window.project.remove_parking(self.parking_id)
        parking = ParkingSpace.from_dict(data)
        self.main_window.project.add_parking(parking)
        scale_factor = self.main_window.get_current_scale()
        self.main_window.image_view.add_parking_graphics(parking, scale_factor)
        self.main_window._refresh_trees()

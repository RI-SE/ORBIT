"""
Undo command classes for ORBIT.

Uses Qt's QUndoStack/QUndoCommand framework for undo/redo functionality.
Each command captures state using model to_dict()/from_dict() methods.
"""

from typing import Optional, List, Tuple, TYPE_CHECKING

from PyQt6.QtGui import QUndoCommand

from orbit.models import Polyline, Road

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

    Undo: Restore the road and its lane graphics
    Redo: Delete the road and lane graphics

    Note: Polylines are NOT deleted, only unassigned from the road.
    """

    def __init__(self, main_window: 'MainWindow', road_id: str):
        super().__init__("Delete Road")
        self.main_window = main_window
        self.road_id = road_id
        self._first_redo = True

        # Capture road state before deletion
        road = main_window.project.get_road(road_id)
        self.road_data = road.to_dict() if road else None

    def redo(self):
        """Delete road from project."""
        if self._first_redo:
            self._first_redo = False
            return

        # Remove lane graphics
        self.main_window.image_view.remove_road_lanes(self.road_id)
        # Remove from project
        self.main_window.project.remove_road(self.road_id)
        self.main_window._refresh_trees()

    def undo(self):
        """Restore road to project."""
        if not self.road_data:
            return

        road = Road.from_dict(self.road_data)
        self.main_window.project.add_road(road)

        # Restore lane graphics if road has centerline
        if road.centerline_id:
            scale_factors = self.main_window.get_current_scale()
            self.main_window.image_view.add_road_lanes_graphics(road, scale_factors)

        self.main_window._refresh_trees()

"""
Project controller for ORBIT.

Encapsulates business logic (project mutations, connecting road regeneration,
coordinate snapping) decoupled from the GUI. MainWindow delegates here for
operations that don't require direct widget interaction.
"""

import math
from typing import Callable, Dict, List, Optional, Set, Tuple

from orbit.gui.constants import DEFAULT_SCALE_M_PER_PX
from orbit.models import LineType, Project
from orbit.utils.logging_config import get_logger

logger = get_logger(__name__)


class ProjectController:
    """Business logic layer between MainWindow and Project."""

    def __init__(
        self,
        project: Project,
        transformer_factory: Callable[..., object],
    ):
        self.project = project
        self._transformer_factory = transformer_factory

    # -- Scale / transformer helpers ------------------------------------------

    def get_current_scale(self) -> Optional[Tuple[float, float]]:
        """Get current scale (m/px) from georeferencing, or None."""
        if not self.project.has_georeferencing():
            return None
        try:
            transformer = self._transformer_factory(use_validation=True)
            if transformer:
                return transformer.get_scale_factor()
        except Exception:
            pass
        return None

    # -- Connecting road geometry pipeline ------------------------------------

    def snap_connecting_road_endpoints(self) -> None:
        """Snap CR pixel endpoints to match their connected road endpoints.

        Skips CRs that have lane connections, since those are positioned at
        lane-boundary offsets (not on the centerline) and handled by
        align_all_junction_crs instead.
        """
        for junction in self.project.junctions:
            # Build set of CR IDs that have lane connections in this junction
            aligned_cr_ids = {
                c.connecting_road_id
                for c in (junction.lane_connections or [])
                if c.connecting_road_id
            }

            for cr_id in junction.connecting_road_ids:
                if cr_id in aligned_cr_ids:
                    continue

                conn_road = self.project.get_road(cr_id)
                if not conn_road or not conn_road.inline_path or len(conn_road.inline_path) < 2:
                    continue

                pred_road = self.project.get_road(conn_road.predecessor_id)
                succ_road = self.project.get_road(conn_road.successor_id)
                if not pred_road or not succ_road:
                    continue

                pred_pl = self.project.get_polyline(pred_road.centerline_id)
                succ_pl = self.project.get_polyline(succ_road.centerline_id)
                if not pred_pl or not succ_pl:
                    continue

                conn_road.inline_path[0] = (
                    pred_pl.points[-1] if conn_road.predecessor_contact == 'end'
                    else pred_pl.points[0]
                )
                conn_road.inline_path[-1] = (
                    succ_pl.points[-1] if conn_road.successor_contact == 'end'
                    else succ_pl.points[0]
                )

    def refresh_connecting_road_geo_path(self, conn_road) -> None:
        """Regenerate a CR's geo_path from its current pixel path."""
        if not conn_road.inline_geo_path:
            return
        if not self.project.has_georeferencing():
            return
        try:
            transformer = self._transformer_factory()
            if transformer and conn_road.inline_path:
                conn_road.inline_geo_path = [
                    transformer.pixel_to_geo(x, y) for x, y in conn_road.inline_path
                ]
        except Exception:
            pass

    def align_all_junction_crs(self, scale_factors) -> Dict[str, Set[str]]:
        """Align all junctions' CRs. Returns {junction_id: set of modified CR IDs}."""
        from orbit.utils.connecting_road_alignment import align_connecting_road_paths

        scale = self._avg_scale(scale_factors)
        result: Dict[str, Set[str]] = {}

        for junction in self.project.junctions:
            if junction.lane_connections and junction.connecting_road_ids:
                modified_ids = align_connecting_road_paths(
                    junction, self.project, scale
                )
                if modified_ids:
                    for cr_id in junction.connecting_road_ids:
                        cr = self.project.get_road(cr_id)
                        if cr and cr.id in modified_ids:
                            self.refresh_connecting_road_geo_path(cr)
                    result[junction.id] = modified_ids
        return result

    def regenerate_affected_crs(self, polyline_id: str) -> List[str]:
        """Regenerate CRs affected by a centerline change.

        Returns list of CR IDs whose graphics need updating.
        """
        polyline = self.project.get_polyline(polyline_id)
        if not polyline or polyline.line_type != LineType.CENTERLINE:
            return []

        affected_road = None
        for road in self.project.roads:
            if road.centerline_id == polyline_id:
                affected_road = road
                break
        if not affected_road:
            return []

        updated_cr_ids: List[str] = []

        # Regenerate ParamPoly3D CRs
        for junction in self.project.junctions:
            for cr_id in junction.connecting_road_ids:
                conn_road = self.project.get_road(cr_id)
                if not conn_road:
                    continue
                if (conn_road.predecessor_id == affected_road.id or
                        conn_road.successor_id == affected_road.id):
                    if conn_road.geometry_type == "parampoly3":
                        self._regenerate_parampoly3_cr(conn_road)
                        updated_cr_ids.append(conn_road.id)

        # Snap polyline-type CR endpoints
        snap_ids = self._snap_polyline_cr_endpoints(affected_road)
        updated_cr_ids.extend(snap_ids)

        # Align affected junction CRs
        align_ids = self._align_affected_junction_crs(affected_road)
        updated_cr_ids.extend(align_ids)

        return updated_cr_ids

    def _regenerate_parampoly3_cr(self, conn_road) -> None:
        """Regenerate a single ParamPoly3D CR from connected roads."""
        from orbit.utils.geometry import generate_simple_connection_path

        pred_road = self.project.get_road(conn_road.predecessor_id)
        succ_road = self.project.get_road(conn_road.successor_id)
        if not pred_road or not succ_road:
            return

        pred_pl = self.project.get_polyline(pred_road.centerline_id)
        succ_pl = self.project.get_polyline(succ_road.centerline_id)
        if not pred_pl or not succ_pl:
            return

        pred_pos, pred_heading = get_contact_pos_heading(
            pred_pl, conn_road.predecessor_contact
        )
        succ_pos, succ_heading = get_contact_pos_heading(
            succ_pl, conn_road.successor_contact
        )

        path, coeffs = generate_simple_connection_path(
            from_pos=pred_pos, from_heading=pred_heading,
            to_pos=succ_pos, to_heading=succ_heading,
            tangent_scale=conn_road.tangent_scale
        )

        conn_road.inline_path = path
        self.refresh_connecting_road_geo_path(conn_road)
        (conn_road.aU, conn_road.bU, conn_road.cU, conn_road.dU,
         conn_road.aV, conn_road.bV, conn_road.cV, conn_road.dV) = coeffs
        conn_road.stored_start_heading = pred_heading
        conn_road.stored_end_heading = succ_heading

    def _snap_polyline_cr_endpoints(self, affected_road) -> List[str]:
        """Snap polyline-type CR endpoints. Returns IDs of modified CRs."""
        modified = []
        for junction in self.project.junctions:
            for cr_id in junction.connecting_road_ids:
                conn_road = self.project.get_road(cr_id)
                if not conn_road or conn_road.geometry_type == "parampoly3":
                    continue
                if (conn_road.predecessor_id != affected_road.id and
                        conn_road.successor_id != affected_road.id):
                    continue
                if not conn_road.inline_path or len(conn_road.inline_path) < 2:
                    continue

                pred_road = self.project.get_road(conn_road.predecessor_id)
                succ_road = self.project.get_road(conn_road.successor_id)
                if not pred_road or not succ_road:
                    continue

                pred_pl = self.project.get_polyline(pred_road.centerline_id)
                succ_pl = self.project.get_polyline(succ_road.centerline_id)
                if not pred_pl or not succ_pl:
                    continue

                conn_road.inline_path[0] = (
                    pred_pl.points[-1] if conn_road.predecessor_contact == "end"
                    else pred_pl.points[0]
                )
                conn_road.inline_path[-1] = (
                    succ_pl.points[-1] if conn_road.successor_contact == "end"
                    else succ_pl.points[0]
                )
                self.refresh_connecting_road_geo_path(conn_road)
                modified.append(conn_road.id)
        return modified

    def _align_affected_junction_crs(self, affected_road) -> List[str]:
        """Align CRs in junctions affected by a road change. Returns modified CR IDs."""
        from orbit.utils.connecting_road_alignment import align_connecting_road_paths

        scale_factors = self.get_current_scale()
        scale = self._avg_scale(scale_factors)

        affected_junction_ids = set()
        for junction in self.project.junctions:
            for cr_id in junction.connecting_road_ids:
                cr = self.project.get_road(cr_id)
                if cr and (cr.predecessor_id == affected_road.id or
                           cr.successor_id == affected_road.id):
                    affected_junction_ids.add(junction.id)
                    break

        all_modified: List[str] = []
        for junction in self.project.junctions:
            if junction.id not in affected_junction_ids:
                continue
            if not junction.lane_connections or not junction.connecting_road_ids:
                continue
            modified = align_connecting_road_paths(junction, self.project, scale)
            for cr_id in junction.connecting_road_ids:
                cr = self.project.get_road(cr_id)
                if cr and cr.id in modified:
                    self.refresh_connecting_road_geo_path(cr)
            all_modified.extend(modified)
        return all_modified

    # -- Road linking ---------------------------------------------------------

    def link_roads(
        self, road_a_id: str, road_b_id: str,
        a_contact: str, b_contact: str
    ) -> bool:
        """Link two roads at the specified contact points. Returns success."""
        road_a = self.project.get_road(road_a_id)
        road_b = self.project.get_road(road_b_id)
        if not road_a or not road_b:
            return False

        if a_contact == "end":
            road_a.successor_id = road_b.id
            road_a.successor_contact = b_contact
        else:
            road_a.predecessor_id = road_b.id
            road_a.predecessor_contact = b_contact

        if b_contact == "start":
            road_b.predecessor_id = road_a.id
            road_b.predecessor_contact = a_contact
        else:
            road_b.successor_id = road_a.id
            road_b.successor_contact = a_contact

        self.project.enforce_road_link_coordinates(road_a_id)
        return True

    def unlink_roads(self, road_id: str, linked_road_id: str) -> bool:
        """Unlink two roads. Returns success."""
        road = self.project.get_road(road_id)
        linked = self.project.get_road(linked_road_id)
        if not road or not linked:
            return False

        if road.predecessor_id == linked_road_id:
            road.predecessor_id = None
        if road.successor_id == linked_road_id:
            road.successor_id = None
        if linked.predecessor_id == road_id:
            linked.predecessor_id = None
        if linked.successor_id == road_id:
            linked.successor_id = None
        return True

    # -- Batch delete info (pure query) ---------------------------------------

    def build_batch_delete_info(self, selected: dict) -> dict:
        """Build display info for batch delete dialog. Pure project query."""
        info: dict = {}
        self._add_delete_info(info, "road_ids", selected, self._road_delete_info)
        self._add_delete_info(info, "junction_ids", selected, self._junction_delete_info)
        self._add_delete_info(info, "signal_ids", selected, self._signal_delete_info)
        self._add_delete_info(info, "object_ids", selected, self._object_delete_info)
        self._add_delete_info(info, "parking_ids", selected, self._parking_delete_info)
        return info

    @staticmethod
    def _add_delete_info(info, key, selected, builder_fn):
        """Generic helper: build delete info items for a category."""
        if not selected.get(key):
            return
        items = [item for eid in selected[key] if (item := builder_fn(eid))]
        if items:
            info[key] = items

    def _road_delete_info(self, road_id):
        road = self.project.get_road(road_id)
        if not road:
            return None
        cascade = []
        for pid in road.polyline_ids:
            pl = self.project.get_polyline(pid)
            if pl:
                cascade.append(f"Polyline: {pl.line_type.value} ({pid[:8]})")
        return {
            "id": road_id,
            "name": road.name or road_id[:8],
            "details": f"{len(road.polyline_ids)} polyline(s)",
            "cascade": cascade,
        }

    def _junction_delete_info(self, jid):
        junction = self.project.get_junction(jid)
        if not junction:
            return None
        cascade = []
        for crid in junction.connected_road_ids:
            road = self.project.get_road(crid)
            if road:
                cascade.append(f"Connected road: {road.name or crid[:8]}")
        return {
            "id": jid,
            "name": junction.name or jid[:8],
            "details": f"{len(junction.connecting_road_ids)} connecting road(s)",
            "cascade": cascade,
        }

    def _signal_delete_info(self, sid):
        signal = self.project.get_signal(sid)
        if not signal:
            return None
        return {
            "id": sid,
            "name": signal.get_display_name(),
            "details": signal.type.value if hasattr(signal.type, 'value') else str(signal.type),
        }

    def _object_delete_info(self, oid):
        obj = self.project.get_object(oid)
        if not obj:
            return None
        return {
            "id": oid,
            "name": obj.get_display_name(),
            "details": obj.type.value if hasattr(obj.type, 'value') else str(obj.type),
        }

    def _parking_delete_info(self, pid):
        parking = self.project.get_parking(pid)
        if not parking:
            return None
        return {
            "id": pid,
            "name": parking.get_display_name(),
            "details": parking.parking_type.value if hasattr(parking.parking_type, 'value') else "",
        }

    # -- Helpers --------------------------------------------------------------

    @staticmethod
    def _avg_scale(scale_factors) -> float:
        if scale_factors:
            return (scale_factors[0] + scale_factors[1]) / 2.0
        return DEFAULT_SCALE_M_PER_PX


def get_contact_pos_heading(polyline, contact_point) -> Tuple[Tuple[float, float], float]:
    """Get position and heading at a polyline contact point."""
    if contact_point == "end":
        pos = polyline.points[-1]
        if len(polyline.points) >= 2:
            dx = polyline.points[-1][0] - polyline.points[-2][0]
            dy = polyline.points[-1][1] - polyline.points[-2][1]
            heading = math.atan2(dy, dx)
        else:
            heading = 0.0
    else:
        pos = polyline.points[0]
        if len(polyline.points) >= 2:
            dx = polyline.points[1][0] - polyline.points[0][0]
            dy = polyline.points[1][1] - polyline.points[0][1]
            heading = math.atan2(dy, dx) + math.pi
        else:
            heading = math.pi
    return pos, heading

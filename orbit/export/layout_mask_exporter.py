"""
Layout mask exporter for ORBIT.

Exports a semantic segmentation mask (PNG/TIFF) and JSON metadata describing
lane regions, adjacency, and connectivity. Two export methods are supported:

- PIXEL: Polygons from rendered scene (fast, no georef needed)
- OPENDRIVE: Polygons from export pipeline (curve-fitted reference line + lane widths)

Optionally writes a world file (.pgw/.tfw) for GIS compatibility.
"""

import json
import math
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

import cv2
import numpy as np

from orbit.models.project import Project
from orbit.utils.logging_config import get_logger
from orbit.export.curve_fitting import CurveFitter
from orbit.export.reference_line_sampler import compute_lane_polygons, sample_reference_line

from .reference_line_sampler import LanePolygonData

logger = get_logger(__name__)


class ExportMethod(Enum):
    """Method for generating lane polygons."""
    PIXEL = "pixel"
    OPENDRIVE = "opendrive"


class LayoutMaskExporter:
    """Exports a layout mask and metadata for lane segmentation.

    The mask is an integer-valued image where each pixel value identifies
    a lane region. Background is 0. Metadata JSON maps region IDs to lane
    properties, adjacency, and connectivity information.
    """

    def __init__(
        self,
        image_size: Tuple[int, int],
        project: Project,
        find_connected_lanes: Callable,
        get_connecting_road_lane_id: Callable,
        transformer=None,
        method: ExportMethod = ExportMethod.PIXEL,
        line_tolerance: float = 0.05,
        arc_tolerance: float = 0.1,
        preserve_geometry: bool = True,
        lane_polygons: Optional[List[LanePolygonData]] = None,
    ):
        """
        Args:
            image_size: (width, height) of the source image in pixels
            project: ORBIT project with roads, junctions, etc.
            find_connected_lanes: Callable(road_id, section_number, lane_id) -> dict
            get_connecting_road_lane_id: Callable(junction, cr_id, source_lane_id) -> int
            transformer: CoordinateTransformer (required for OPENDRIVE method and GeoTIFF)
            method: PIXEL or OPENDRIVE export method
            line_tolerance: Curve fitting line tolerance (OPENDRIVE method)
            arc_tolerance: Curve fitting arc tolerance (OPENDRIVE method)
            preserve_geometry: Preserve original geometry during curve fitting
            lane_polygons: Pre-collected polygons (PIXEL method). If None with PIXEL
                method, export will fail.
        """
        self.image_size = image_size
        self.project = project
        self.find_connected_lanes = find_connected_lanes
        self.get_connecting_road_lane_id = get_connecting_road_lane_id
        self.transformer = transformer
        self.method = method
        self.line_tolerance = line_tolerance
        self.arc_tolerance = arc_tolerance
        self.preserve_geometry = preserve_geometry
        self.lane_polygons = lane_polygons or []


    def _apply_adjacency(
        self,
        region_map: Dict[Tuple, int],
        region_info: Dict[str, dict],
    ) -> None:
        """
        Lanelet-compatible adjacency:
        1) Lateral adjacency (Δ lane_id == 1) for same-road/section or same connecting road.
        2) Adjacent must NOT be successors or predecessors.
        3) No adjacency with overlaps as lane neighbors.
        4) Geometric adjacency: if min polygon distance < threshold, add to adjacent_geometric.
        """

        # helper -------------------------
        def add_adj(a, b):
            # Exclude longitudinal neighbors
            if b in succ_map.get(a, set()) or a in succ_map.get(b, set()):
                return
            if b in pred_map.get(a, set()) or a in pred_map.get(b, set()):
                return
            # Exclude overlaps
            if regions[a].get("type") == "overlap" or regions[b].get("type") == "overlap":
                return
            adj[a].add(b)
            adj[b].add(a)

        def poly_distance(polyA, polyB):
            """Compute min distance between polygons (point-to-segment)."""
            min_d = float("inf")
            for ax, ay in polyA:
                for bx, by in polyB:
                    d = math.hypot(ax - bx, ay - by)
                    if d < min_d:
                        min_d = d
            return min_d

        # --- Preload lookups ---
        regions = region_info
        succ_map = {rid: set(info.get("successors", [])) for rid, info in regions.items() if isinstance(info, dict)}
        pred_map = {rid: set(info.get("predecessors", [])) for rid, info in regions.items() if isinstance(info, dict)}

        by_road_section = {}
        by_conn_road = {}

        for rid, info in regions.items():
            if not isinstance(info, dict):
                continue

            t = info.get("type")
            if t not in ("lane", "connecting_lane"):
                continue

            road_id = str(info.get("road_id"))
            lane_id = int(info.get("lane_id"))
            section = int(info.get("section_number", 1))

            if t == "lane":
                by_road_section.setdefault((road_id, section), {})[lane_id] = rid
            else:
                by_conn_road.setdefault(road_id, {})[lane_id] = rid

        adj = {rid: set() for rid, info in regions.items()
            if isinstance(info, dict) and info.get("type") in ("lane", "connecting_lane")}

        # Rule A -------------------------------------------------
        for (road_id, section), lane_map in by_road_section.items():
            for lid, rid in lane_map.items():
                for other in (lid - 1, lid + 1):
                    if other in lane_map:
                        add_adj(rid, lane_map[other])

        # Rule B -------------------------------------------------
        for road_id, lane_map in by_conn_road.items():
            for lid, rid in lane_map.items():
                for other in (lid - 1, lid + 1):
                    if other in lane_map:
                        add_adj(rid, lane_map[other])

        # Geometric adjacency  ------------------------------
        # threshold = 3 meters (or scaled pixels)
        threshold = 3.0
        for ridA, infoA in regions.items():
            if not isinstance(infoA, dict):
                continue
            if infoA.get("type") not in ("lane", "connecting_lane"):
                continue

            polyA = [(float(px), float(py)) for px, py in infoA.get("polygon", [])]

            for ridB, infoB in regions.items():
                if ridA == ridB:
                    continue
                if not isinstance(infoB, dict):
                    continue
                if infoB.get("type") not in ("lane", "connecting_lane"):
                    continue

                # skip if already covered by lateral adjacency
                if ridB in adj[ridA]:
                    continue

                polyB = [(float(px), float(py)) for px, py in infoB.get("polygon", [])]
                d = poly_distance(polyA, polyB)

                if d < threshold:
                    regions[ridA].setdefault("adjacent_geometric", [])
                    regions[ridB].setdefault("adjacent_geometric", [])
                    regions[ridA]["adjacent_geometric"].append(ridB)
                    regions[ridB]["adjacent_geometric"].append(ridA)

        # ----------------------------------------------------------
        # RULE: overlap members are adjacent to each other
        # ----------------------------------------------------------
        for oid, oinfo in regions.items():
            if not isinstance(oinfo, dict):
                continue
            if oinfo.get("type") != "overlap":
                continue


            members = [str(m) for m in oinfo.get("members", [])]

            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    a = members[i]
                    b = members[j]

                    if a in adj and b in adj:
                        adj[a].add(b)
                        adj[b].add(a)

            # If only ONE member exists (edge crop case), mark geometric adjacency
            if len(members) == 1:
                m = members[0]
                regions[m].setdefault("adjacent_geometric", [])

        # finalize adjacency
        for rid, info in regions.items():
            if not isinstance(info, dict):
                continue
            if info.get("type") in ("lane", "connecting_lane"):
                info["adjacent"] = sorted(adj.get(rid, []), key=lambda v: int(v) if str(v).isdigit() else v)
                # dedupe geometric adjacency
                if "adjacent_geometric" in info:
                    info["adjacent_geometric"] = sorted(
                        set(info["adjacent_geometric"]),
                        key=lambda v: int(v) if str(v).isdigit() else v
                    )
            else:
                info["adjacent"] = []
                info["adjacent_geometric"] = []

    def _mark_boundary_regions(self, region_info):
        """Mark regions touching crop border (likely external connectivity)."""

        w, h = self.image_size

        for rid, info in region_info.items():
            if not isinstance(info, dict):
                continue
            if "polygon" not in info:
                continue

            pts = info["polygon"]

            touches_border = any(
                x <= 1 or x >= (w - 2) or y <= 1 or y >= (h - 2)
                for x, y in pts
            )

            if touches_border:
                info["is_crop_boundary"] = True

    def _populate_overlap_links(self, region_info: Dict[str, dict]) -> None:
        """
        Lanelet-compatible overlap behavior:
        - Overlaps are PROXY regions, NOT lanelets.
        - Their successors / predecessors / adjacency = union(members) minus members.
        - They do not appear in any lanelet's successor or adjacency lists.
        """
        def sort_ids(ids):
            s = set(str(x) for x in ids)
            return sorted(s, key=lambda v: int(v) if v.isdigit() else v)

        for oid, oinfo in region_info.items():
            if not isinstance(oinfo, dict) or oinfo.get("type") != "overlap":
                continue

            members = [str(m) for m in (oinfo.get("members") or [])]
            oinfo["proxy"] = True

            succ_u, pred_u = set(), set()
            adj_u, adj_geom_u = set(), set()
            direct_succ_u, direct_pred_u = set(), set()
            merge_u = set()

            for mid in members:
                minfo = region_info.get(mid, {})
                # LONGITUDINAL
                for s in (minfo.get("successors") or []):
                    s = str(s)
                    if s not in members:
                        succ_u.add(s)
                for p in (minfo.get("predecessors") or []):
                    p = str(p)
                    if p not in members:
                        pred_u.add(p)
                # ADJACENCY
                for a in (minfo.get("adjacent") or []):
                    a = str(a)
                    if a not in members:
                        adj_u.add(a)
                for ag in (minfo.get("adjacent_geometric") or []):
                    ag = str(ag)
                    if ag not in members:
                        adj_geom_u.add(ag)

                # DIRECT CONNECTIONS
                for ds in (minfo.get("direct_successors") or []):
                    ds = str(ds)
                    if ds not in members:
                        direct_succ_u.add(ds)
                for dp in (minfo.get("direct_predecessors") or []):
                    dp = str(dp)
                    if dp not in members:
                        direct_pred_u.add(dp)

                # MERGES
                for m in (minfo.get("merges_with") or []):
                    m = str(m)
                    if m not in members:
                        merge_u.add(m)

            oinfo["successors"] = sort_ids(succ_u)
            oinfo["predecessors"] = sort_ids(pred_u)
            oinfo["adjacent"] = sort_ids(adj_u)
            oinfo["adjacent_geometric"] = sort_ids(adj_geom_u)
            oinfo["direct_successors"] = sort_ids(direct_succ_u)
            oinfo["direct_predecessors"] = sort_ids(direct_pred_u)
            oinfo["merges_with"] = sort_ids(merge_u)


    def export(self, output_path: str, geotiff: bool = False) -> bool:
        """Run the full export pipeline.

        Args:
            output_path: Path for the mask image (PNG or TIFF)
            geotiff: If True and transformer available, write a world file

        Returns:
            True on success, False on failure
        """
        try:
            polygons = self._collect_polygons()
            if not polygons:
                logger.warning("No lane polygons to export")
                return False

            region_map, region_info = self._build_region_map(polygons)
            mask = self._render_mask_with_overlaps(polygons, region_map, region_info)
            self._encode_junctions(mask, region_info, region_map)



            self._compute_connectivity(region_map, region_info)
            self._mark_boundary_regions(region_info)
            self._apply_adjacency(region_map, region_info)
            self._populate_overlap_links(region_info)
            self._infer_road_junction_references()
            self._compute_junction_grouping(region_map, region_info)
            self._compute_distances(region_map, region_info)




            self._save_mask(mask, output_path)
            self._save_colorized_mask(mask, output_path)

            if geotiff and self.transformer:
                self._save_world_file(output_path)

            json_path = str(Path(output_path).with_suffix('.json'))
            self._save_metadata(region_info, json_path)

            n_regions = len([k for k in region_info if k != "0"])
            logger.info("Layout mask exported: %d regions, mask shape %s", n_regions, mask.shape)
            return True

        except Exception:
            logger.exception("Failed to export layout mask")
            return False

    # ---- Polygon collection ----

    def _collect_polygons(self) -> List[LanePolygonData]:
        """Collect lane polygons according to the chosen method."""
        if self.method == ExportMethod.PIXEL:
            return self._collect_pixel_polygons()
        else:
            return self._collect_opendrive_polygons()

    def _collect_pixel_polygons(self) -> List[LanePolygonData]:
        """Return pre-collected pixel-space polygons."""
        if not self.lane_polygons:
            logger.warning("No lane polygons provided for PIXEL method")
        return self.lane_polygons

    def _collect_opendrive_polygons(self) -> List[LanePolygonData]:
        """Generate polygons via curve fitting and reference line sampling."""

        if not self.transformer:
            logger.error("OPENDRIVE method requires a coordinate transformer")
            return []

        polygons = []
        # Store reference line endpoint headings for CR heading alignment:
        # {(road_id, "start"|"end"): heading_radians}
        road_ref_headings: Dict[Tuple[str, str], float] = {}

        for road in self.project.roads:
            if not road.centerline_id:
                continue

            polyline = self.project.get_polyline(road.centerline_id)
            if not polyline or len(polyline.points) < 2:
                continue

            # Transform centerline to meters
            meter_points = []
            for px, py in polyline.points:
                mx, my = self.transformer.pixel_to_meters(px, py)
                meter_points.append((mx, my))

            # Fit geometry
            fitter = CurveFitter(
                line_tolerance=self.line_tolerance,
                arc_tolerance=self.arc_tolerance,
                preserve_geometry=self.preserve_geometry,
            )
            geometry_elements = fitter.fit_polyline(meter_points)
            if not geometry_elements:
                logger.warning("Curve fitting produced no elements for road %s", road.id)
                continue

            # Sample reference line
            ref_points = sample_reference_line(geometry_elements, step_m=0.5)
            if len(ref_points) < 2:
                continue

            # Store reference line endpoint headings for CR alignment
            road_ref_headings[(road.id, "start")] = ref_points[0][2]
            road_ref_headings[(road.id, "end")] = ref_points[-1][2]

            # Compute lane polygons in meters
            lane_polys = []

            for section in road.lane_sections:
                for lane in section.lanes:

                    # EXPLICIT mode
                    if hasattr(lane, "boundary_mode") and lane.boundary_mode.value == "explicit":
                        poly = self._build_polygon_from_explicit_boundaries(
                            lane,
                            section.section_number,
                            is_connecting=False
                        )
                        if poly:
                            lane_polys.append(poly)
                        continue

                    # OFFSET mode (fallback to old logic)
                    polys = compute_lane_polygons(ref_points, road, 1)
                    lane_polys.extend(polys)
                    break  # prevent duplicate reprocessing
                break


            # Convert to pixel coordinates
            for lp in lane_polys:
                pixel_pts = []
                for mx, my in lp.points:
                    px, py = self.transformer.meters_to_pixel(mx, my)
                    pixel_pts.append((px, py))
                lp.points = pixel_pts
                polygons.append(lp)

        # Connecting road polygons — transform to meters, offset lanes, convert back.
        # This matches the regular road pipeline so widths and angles are consistent.
        for junction in self.project.junctions:
            for cr in junction.connecting_roads:
                if len(cr.path) < 2:
                    continue
                cr_polys = self._collect_connecting_road_polygons(
                    cr, road_ref_headings,
                )
                polygons.extend(cr_polys)

        return polygons

    def _build_polygon_from_explicit_boundaries(self, lane, section_number, is_connecting=False):
        """Build polygon using explicit left/right boundary polylines."""

        if not lane.left_boundary_id or not lane.right_boundary_id:
            return None

        left_poly = self.project.get_polyline(lane.left_boundary_id)
        right_poly = self.project.get_polyline(lane.right_boundary_id)

        if not left_poly or not right_poly:
            return None

        if len(left_poly.points) < 2 or len(right_poly.points) < 2:
            return None

        # Build polygon (left forward, right reversed)
        pts = list(left_poly.points) + list(reversed(right_poly.points))

        if self.transformer:
            # Explicit boundaries are in pixel already → keep as-is
            pixel_pts = [(float(px), float(py)) for px, py in pts]
        else:
            pixel_pts = [(float(px), float(py)) for px, py in pts]

        return LanePolygonData(
            road_id=getattr(lane, "road_id", "unknown"),
            section_number=section_number,
            lane_id=lane.id,
            points=pixel_pts,
            is_connecting_road=is_connecting,
            lane_type=lane.lane_type.value if hasattr(lane.lane_type, "value") else "driving",
        )    

    def _collect_connecting_road_polygons(
        self, cr, road_ref_headings: Optional[Dict] = None,
    ) -> List[LanePolygonData]:
        """Generate lane polygons for a connecting road in meter space.

        Transforms the CR path to meters, computes headings, offsets lanes
        laterally using lane widths in meters, then converts back to pixels.

        Args:
            cr: ConnectingRoad with path and lane configuration
            road_ref_headings: {(road_id, contact_point): heading} from
                curve-fitted reference lines. Used to override CR endpoint
                headings so lane edges align with road lane edges at
                junction boundaries.
        """
        
        # Transform path to meters
        path_meters = []
        for px, py in cr.path:
            mx, my = self.transformer.pixel_to_meters(px, py)
            path_meters.append((mx, my))

        # Compute headings and s-coordinates along path
        headings = []
        s_values = [0.0]
        for i in range(len(path_meters)):
            if i < len(path_meters) - 1:
                dx = path_meters[i + 1][0] - path_meters[i][0]
                dy = path_meters[i + 1][1] - path_meters[i][1]
                headings.append(math.atan2(dy, dx))
                dist = math.sqrt(dx * dx + dy * dy)
                s_values.append(s_values[-1] + dist)
            else:
                # Last point: use same heading as previous
                headings.append(headings[-1] if headings else 0.0)

        # Override endpoint headings with road reference line headings.
        # This aligns the CR lane edge direction with the road lane edge
        # direction at the junction boundary, eliminating wedge-shaped
        # misalignment. Only headings are changed — positions stay put,
        # so no path kink is introduced.
        if road_ref_headings:
            pred_hdg = road_ref_headings.get(
                (cr.predecessor_road_id, cr.contact_point_start)
            )
            if pred_hdg is not None:
                headings[0] = pred_hdg

            succ_hdg = road_ref_headings.get(
                (cr.successor_road_id, cr.contact_point_end)
            )
            if succ_hdg is not None and len(headings) > 0:
                headings[-1] = succ_hdg

        path_length_m = s_values[-1] if len(s_values) > 1 else 0.0
        if path_length_m < 1e-6:
            return []

        # Ensure lanes are initialized
        cr.ensure_lanes_initialized()
        lane_map = {lane.id: lane for lane in cr.lanes if lane.id != 0}

        polygons = []

        # Process right lanes (-1, -2, ...)
        for lane_num in range(1, cr.lane_count_right + 1):
            lane_id = -lane_num
            lane = lane_map.get(lane_id)
            if not lane:
                continue
            inner_lanes = [lane_map.get(-i) for i in range(1, lane_num) if lane_map.get(-i)]
            poly = self._offset_cr_lane(
                cr, path_meters, headings, s_values, path_length_m,
                lane, inner_lanes, lane_id, side="right",
            )
            if poly:
                polygons.append(poly)

        # Process left lanes (1, 2, ...)
        for lane_num in range(1, cr.lane_count_left + 1):
            lane_id = lane_num
            lane = lane_map.get(lane_id)
            if not lane:
                continue
            inner_lanes = [lane_map.get(i) for i in range(1, lane_num) if lane_map.get(i)]
            poly = self._offset_cr_lane(
                cr, path_meters, headings, s_values, path_length_m,
                lane, inner_lanes, lane_id, side="left",
            )
            if poly:
                polygons.append(poly)

        return polygons

    def _offset_cr_lane(
        self, cr, path_meters, headings, s_values, path_length_m,
        lane, inner_lanes, lane_id, side,
    ):
        
        if hasattr(lane, "boundary_mode") and lane.boundary_mode.value == "explicit":
            poly = self._build_polygon_from_explicit_boundaries(
                lane,
                section_number=1,
                is_connecting=True
            )
            if poly:
                return poly

        inner_boundary = []
        outer_boundary = []

        for i, (mx, my) in enumerate(path_meters):
            hdg = headings[i]
            s_m = s_values[i]

            inner_offset = sum(il.get_width_at_s(s_m, path_length_m) for il in inner_lanes)
            outer_offset = inner_offset + lane.get_width_at_s(s_m, path_length_m)

            perp_x = -math.sin(hdg)
            perp_y = math.cos(hdg)

            if side == "right":
                in_x = mx - perp_x * inner_offset
                in_y = my - perp_y * inner_offset
                out_x = mx - perp_x * outer_offset
                out_y = my - perp_y * outer_offset
            else:
                in_x = mx + perp_x * inner_offset
                in_y = my + perp_y * inner_offset
                out_x = mx + perp_x * outer_offset
                out_y = my + perp_y * outer_offset

            inner_boundary.append((in_x, in_y))
            outer_boundary.append((out_x, out_y))

        pts_m = inner_boundary + list(reversed(outer_boundary))
        if len(pts_m) < 3:
            return None

        # convert to pixels
        pixel_pts = [
            self.transformer.meters_to_pixel(mx, my)
            for mx, my in pts_m
        ]

        lane_type = lane.lane_type.value if hasattr(lane.lane_type, 'value') else "driving"

        return LanePolygonData(
            road_id=cr.id,
            section_number=1,
            lane_id=lane_id,
            points=pixel_pts,
            is_connecting_road=True,
            lane_type=lane_type,
        )

    # ---- Region map ----

    def _build_region_map(
        self, polygons: List[LanePolygonData],
    ) -> Tuple[Dict[Tuple, int], Dict[str, dict]]:
        """Assign sequential region IDs to polygons.

        Returns:
            (region_map, region_info) where:
            - region_map: (road_id, section_number, lane_id, is_connecting) -> region_id
            - region_info: str(region_id) -> metadata dict
        """
        region_map: Dict[Tuple, int] = {}
        region_info: Dict[str, dict] = {
            "0": {"type": "non_drivable"},
        }

        next_id = 1
        for poly in polygons:
            key = (poly.road_id, poly.section_number, poly.lane_id, poly.is_connecting_road)
            if key not in region_map:
                region_map[key] = next_id
                region_info[str(next_id)] = {
                    "type": "connecting_lane" if poly.is_connecting_road else "lane",
                    "road_id": poly.road_id,
                    "lane_id": poly.lane_id,
                    "section_number": poly.section_number,
                    "lane_type": poly.lane_type,
                    "is_connecting_road": poly.is_connecting_road,
                    "adjacent": [],
                    "successors": [],
                    "predecessors": [],
                    "direct_successors": [],
                    "direct_predecessors": [],
                    "shares_upcoming_junction_with": [],
                    "merges_with": [],
                    "upcoming_junction_ids": [],
                    "previous_junction_ids": [],
                    "distance_to_next_junction_m": None,
                    "distance_to_prev_junction_m": None,
                    "has_external_successor": False,
                    "has_external_predecessor": False,
                    "external_successors": [],
                    "external_predecessors": [],                    
                    "polygon": [[float(px), float(py)] for (px, py) in poly.points]
                }
                next_id += 1

        return region_map, region_info

    # ---- Mask rendering ----

    def _render_mask_with_overlaps(self, polygons, region_map, region_info):
        h, w = self.image_size[1], self.image_size[0]
        mask = np.zeros((h, w), dtype=np.int32)

        # --------------------------------------------------
        # HELPERS
        # --------------------------------------------------
        def is_connecting(rid):
            return region_info.get(str(rid), {}).get("type") == "connecting_lane"

        def are_longitudinal(a, b):
            a = str(a); b = str(b)
            return (
                b in region_info.get(a, {}).get("successors", []) or
                b in region_info.get(a, {}).get("predecessors", []) or
                a in region_info.get(b, {}).get("successors", []) or
                a in region_info.get(b, {}).get("predecessors", [])
            )

        # --------------------------------------------------
        # PASS 1: paint base regions (WITHOUT overwrite)
        # --------------------------------------------------
        polygons_sorted = sorted(
            polygons,
            key=lambda p: (p.is_connecting_road, abs(p.lane_id))
        )

        for poly in polygons_sorted:
            key = (poly.road_id, poly.section_number, poly.lane_id, poly.is_connecting_road)
            rid = region_map.get(key)
            if rid is None:
                continue

            pts = np.round(np.asarray(poly.points)).astype(np.int32)
            if len(pts) < 3:
                continue

            tmp = np.zeros((h, w), dtype=np.uint8)
            cv2.fillPoly(tmp, [pts.reshape((-1, 1, 2))], 1)
            poly_mask = tmp.astype(bool)

            # only fill empty
            mask[(mask == 0) & poly_mask] = rid

        # --------------------------------------------------
        # PASS 2: detect overlaps
        # --------------------------------------------------
        overlap_map: Dict[Tuple[int, int], np.ndarray] = {}

        for poly in polygons_sorted:
            key = (poly.road_id, poly.section_number, poly.lane_id, poly.is_connecting_road)
            rid = region_map.get(key)
            if rid is None:
                continue

            pts = np.round(np.asarray(poly.points)).astype(np.int32)
            if len(pts) < 3:
                continue

            tmp = np.zeros((h, w), dtype=np.uint8)
            cv2.fillPoly(tmp, [pts.reshape((-1, 1, 2))], 1)
            poly_mask = tmp.astype(bool)

            overlap = poly_mask & (mask != 0) & (mask != rid)
            if not np.any(overlap):
                continue

            existing_ids = mask[overlap]
            for other_id in np.unique(existing_ids):
                pair = tuple(sorted((rid, int(other_id))))
                submask = overlap & (mask == other_id)

                if pair not in overlap_map:
                    overlap_map[pair] = submask
                else:
                    overlap_map[pair] |= submask

        # --------------------------------------------------
        # PASS 3: classify overlaps (STRICT RULES)
        # --------------------------------------------------

        next_id = max(int(k) for k in region_info) + 1

        unique_ids, counts = np.unique(mask, return_counts=True)
        region_sizes = dict(zip(unique_ids.astype(int), counts))

        for (a, b), omask in overlap_map.items():
            area = int(np.sum(omask))

            # RULE 1 — only connecting lanes allowed
            if not (is_connecting(a) and is_connecting(b)):
                winner = a if region_sizes.get(a, 0) >= region_sizes.get(b, 0) else b
                mask[omask] = winner
                continue

            # RULE 2 — NO longitudinal overlap allowed
            if are_longitudinal(a, b):
                winner = a if region_sizes.get(a, 0) >= region_sizes.get(b, 0) else b
                mask[omask] = winner
                continue


            # VALID overlap (junction crossing)
            oid = next_id
            next_id += 1

            region_info[str(oid)] = {
                "type": "overlap",
                "members": [str(a), str(b)],
                "adjacent": [],
            }

            mask[omask] = oid

        # --------------------------------------------------
        # PASS 4: GAP FILL (critical for topology)
        # --------------------------------------------------
        # small holes between connected lanes are filled
        gap_mask = (mask == 0)

        if np.any(gap_mask):
            kernel = np.ones((3, 3), np.uint8)

            dilated = cv2.dilate(mask.astype(np.uint16), kernel, iterations=1)

            fill = (gap_mask) & (dilated != 0)
            mask[fill] = dilated[fill]

        # --------------------------------------------------
        # FINAL: denoise
        # --------------------------------------------------
        mask = cv2.medianBlur(mask.astype(np.uint16), 3).astype(np.int32)

        return mask



    # ---- Junction encoding ----

    def _compute_polygon_union(self, polys):
        """
        Computes the smallest region covering all polygons (geometric union),
        implemented via rasterization + contour extraction using OpenCV.
        polys: list of [ [x,y], [x,y], ... ]
        Returns list of (x,y) tuples defining the union boundary polygon.
        """

        if not polys:
            return []

        H = self.image_size[1]
        W = self.image_size[0]

        # binary mask for union
        union_mask = np.zeros((H, W), dtype=np.uint8)

        # Draw all polygons into the same buffer
        for poly in polys:
            pts = np.array(poly, dtype=np.int32).reshape((-1, 1, 2))
            cv2.fillPoly(union_mask, [pts], 255)

        # Extract external contours
        contours, _ = cv2.findContours(union_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return []

        # Take the largest contour (typical for junctions)
        contour = max(contours, key=cv2.contourArea)

        # Convert contour back to polygon list
        pts = [(int(p[0][0]), int(p[0][1])) for p in contour]
        return pts


    def _encode_junctions(self, mask, region_info, region_map):
        """
        Revised: Junction polygons are derived ONLY from the polygons of
        connecting-lane regions (their true geometric footprint).
        Junctions remain metadata-only.
        """

        def convex_hull(points):
            pts = sorted(set(points))
            if len(pts) <= 2:
                return pts

            def cross(o, a, b):
                return (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0])

            lower = []
            for p in pts:
                while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
                    lower.pop()
                lower.append(p)

            upper = []
            for p in reversed(pts):
                while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
                    upper.pop()
                upper.append(p)

            return lower[:-1] + upper[:-1]



        next_id = max(int(k) for k in region_info) + 1

        for junction in self.project.junctions:

            jid = str(next_id)
            next_id += 1

            # ----------------------------------------------------------
            # 1. Collect polygons ONLY from connecting lanes in junction

            connecting_polys = []
            cr_ids = {cr.id for cr in junction.connecting_roads}

            for rid, info in region_info.items():
                if info.get("type") == "connecting_lane" and info.get("road_id") in cr_ids:
                    connecting_polys.append(info["polygon"])

            # 1. use real boundary if available
            boundary_pts = []
            if junction.boundary and junction.boundary.segments:
                raw = []
                for seg in junction.boundary.segments:
                    raw.extend(seg.points)
                if len(raw) >= 3:
                    boundary_pts = raw

            # 2. otherwise compute polygon union (smallest covering region)
            if not boundary_pts:
                boundary_pts = self._compute_polygon_union(connecting_polys)


            # ----------------------------------------------------------
            # 4. No mask painting (junction = meta-only)
            # ----------------------------------------------------------
            painted = False
            # if len(boundary_pts) >= 3:
            #     pts_arr = np.array(boundary_pts, dtype=np.int32).reshape((-1, 1, 2))
            #     cv2.fillPoly(mask, [pts_arr], int(jid))
            #     painted = True
            # ----------------------------------------------------------
            # 5. Build metadata entry
            # ----------------------------------------------------------
            region_info[jid] = {
                "type": "junction",
                "junction_id": junction.id,
                "junction_name": junction.name,
                "polygon": [[float(a), float(b)] for (a, b) in boundary_pts],
                "adjacent": [],
                "successors": [],
                "predecessors": [],
                "adjacent_geometric": [],
                "members": [],  # filled next
            }

            # ----------------------------------------------------------
            # 6. Members = ONLY connecting lanes
            # ----------------------------------------------------------
            members = []
            for rid, info in region_info.items():
                if not isinstance(info, dict):
                    continue
                if info.get("type") == "connecting_lane":
                    if info.get("road_id") in cr_ids:
                        members.append(rid)

            region_info[jid]["members"] = members

    

    # ---- Connectivity ----


    def _connect_within_road_sections(self, region_map, region_info, road_lookup):
        """
        Ensure continuity between lane sections of same road.
        Fixes missing links inside long roads (common XODR defect).
        """
        def link(a, b):
            if a not in region_info or b not in region_info:
                return
            if b not in region_info[a]["successors"]:
                region_info[a]["successors"].append(b)
            if a not in region_info[b]["predecessors"]:
                region_info[b]["predecessors"].append(a)

        for road in self.project.roads:
            if not road.lane_sections or len(road.lane_sections) < 2:
                continue

            sections = sorted(road.lane_sections, key=lambda s: s.section_number)

            for i in range(len(sections) - 1):
                s0 = sections[i].section_number
                s1 = sections[i + 1].section_number

                # match lanes by same lane_id
                lane_ids = set()

                for (r, lane, sec) in road_lookup.keys():
                    if r == str(road.id):
                        lane_ids.add(lane)

                for lane_id in lane_ids:
                    src = road_lookup.get((road.id, lane_id, s0), [])
                    dst = road_lookup.get((road.id, lane_id, s1), [])

                    for a in src:
                        for b in dst:
                            link(a, b)

    def _compute_connectivity(self, region_map, region_info):


        # --- Build lookups ---
        road_lookup, cr_lookup = {}, {}
        for (road, section, lane, is_conn), rid in region_map.items():
            key = (str(road), int(lane), int(section))
            if is_conn:
                cr_lookup.setdefault((str(road), int(lane)), []).append(str(rid))
            else:
                road_lookup.setdefault(key, []).append(str(rid))

        def link(a, b):
            if a not in region_info or b not in region_info:
                return
            if b not in region_info[a]["successors"]:
                region_info[a]["successors"].append(b)
            if a not in region_info[b]["predecessors"]:
                region_info[b]["predecessors"].append(a)

        # --- 1. Intra-road continuity ---
        self._connect_within_road_sections(region_map, region_info, road_lookup)

        # --- 2. Junction connectivity ---
        for junction in self.project.junctions:

            cr_successor = {str(cr.id): cr.successor_road_id for cr in junction.connecting_roads}

            for lc in junction.lane_connections:

                src_road = str(lc.from_road_id)
                src_lane = int(lc.from_lane_id)
                cr_id = str(lc.connecting_road_id)
                cr_lane = int(lc.connecting_lane_id)
                
                if (cr_id, cr_lane) not in cr_lookup:
                    continue

                to_lane = int(lc.to_lane_id)

                cr_obj = next((cr for cr in junction.connecting_roads if str(cr.id) == cr_id), None)
                if not cr_obj:
                    continue

                road_obj = self.project.get_road(src_road)
                if not road_obj or not road_obj.lane_sections:
                    continue

                sec_nums = [s.section_number for s in road_obj.lane_sections]
                sec_src = min(sec_nums) if cr_obj.contact_point_start == "start" else max(sec_nums)

                src_rids = road_lookup.get((src_road, src_lane, sec_src), [])
                cr_rids = cr_lookup.get((cr_id, cr_lane), [])

                for a in src_rids:
                    for b in cr_rids:
                        link(a, b)

                # --- CR → successor road ---
                succ_road = cr_successor.get(cr_id)
                if not succ_road:
                    continue

                road_obj = self.project.get_road(succ_road)
                if not road_obj or not road_obj.lane_sections:
                    continue

                sec_nums = [s.section_number for s in road_obj.lane_sections]
                sec_succ = min(sec_nums) if cr_obj.contact_point_end == "start" else max(sec_nums)

                # lane mapping
                mapped_lane = int(lc.to_lane_id)

                key = (str(succ_road), int(mapped_lane), sec_succ)
                target_rids = road_lookup.get(key, [])

                if not target_rids:
                    for a in cr_rids:
                        if a in region_info:
                            region_info[a]["has_external_successor"] = True
                            region_info[a].setdefault("external_successors", []).append({
                                "road_id": str(succ_road),
                                "lane_id": int(mapped_lane)
                            })
                    continue

                # ✅ always link
                for a in cr_rids:
                    for b in target_rids:
                        link(a, b)

        # --- external predecessor detection ---
        for (road, lane, section), rids in road_lookup.items():
            for rid in rids:
                info = region_info.get(rid)
                if info and info.get("type") == "lane" and not info.get("predecessors"):
                    road_obj = self.project.get_road(road)
                    if road_obj and (road_obj.predecessor_id or road_obj.predecessor_junction_id):
                        info["has_external_predecessor"] = True

        # --- cleanup ---
        for info in region_info.values():
            if isinstance(info, dict):
                info["successors"] = sorted(set(info.get("successors", [])))
                info["predecessors"] = sorted(set(info.get("predecessors", [])))



    def _infer_road_junction_references(self):
        """
        Build missing road.successor_junction_id / predecessor_junction_id 
        from project.junctions[*].connected_road_ids
        """
        for j in self.project.junctions:
            for rid in j.connected_road_ids:
                road = self.project.get_road(rid)
                if not road:
                    continue

                # If road ends near junction, assign successor_junction_id
                road.successor_junction_id = j.id

                # If road begins near junction, assign predecessor_junction_id
                road.predecessor_junction_id = j.id

    def _compute_junction_grouping(
        self,
        region_map: Dict[Tuple, int],
        region_info: Dict[str, dict],
    ) -> None:
        """
        Lanelet-compatible junction grouping.

        Fixes:
        - Always assign upcoming/previous junctions (even synthetic).
        - Identify all lanes entering/exiting the same junction.
        - Compute shares_upcoming_junction_with correctly.
        - Preserve merges_with based on direct_successors.
        """

        # Build road -> junction relations
        road_to_successor_junction = {}
        road_to_predecessor_junction = {}

        for road in self.project.roads:
            # Successor
            if road.successor_junction_id:
                road_to_successor_junction[road.id] = road.successor_junction_id
            elif road.successor_id:
                for j in self.project.junctions:
                    if road.successor_id in j.connected_road_ids:
                        road_to_successor_junction[road.id] = j.id
                        break
            # Predecessor
            if road.predecessor_junction_id:
                road_to_predecessor_junction[road.id] = road.predecessor_junction_id
            elif road.predecessor_id:
                for j in self.project.junctions:
                    if road.predecessor_id in j.connected_road_ids:
                        road_to_predecessor_junction[road.id] = j.id
                        break

        upcoming_groups = {}
        previous_groups = {}

        for key, rid in region_map.items():
            road_id, section_number, lane_id, is_conn = key
            rid_str = str(rid)

            if is_conn or rid_str not in region_info:
                continue

            road = self.project.get_road(road_id)
            if not road or not road.lane_sections:
                continue

            info = region_info[rid_str]

            # UPCOMING JUNCTIONS -------------------------------------
            if road_id in road_to_successor_junction:
                junc_id = road_to_successor_junction[road_id]
                upcoming_groups.setdefault(junc_id, []).append(rid_str)
                info.setdefault("upcoming_junction_ids", []).append(junc_id)

            # PREVIOUS JUNCTIONS --------------------------------------
            if road_id in road_to_predecessor_junction:
                junc_id = road_to_predecessor_junction[road_id]
                previous_groups.setdefault(junc_id, []).append(rid_str)
                info.setdefault("previous_junction_ids", []).append(junc_id)

        # shares_upcoming_junction_with -------------------------------
        for junc_id, members in upcoming_groups.items():
            for m in members:
                if m in region_info:
                    region_info[m]["shares_upcoming_junction_with"] = [
                        o for o in members if o != m
                    ]

        # merges_with (remains same concept) ---------------------------
        succ_groups = {}
        for rid_str, info in region_info.items():
            if not isinstance(info, dict):
                continue
            for ds in info.get("direct_successors", []):
                succ_groups.setdefault(ds, []).append(rid_str)

        for target, sources in succ_groups.items():
            if len(sources) > 1:
                for s in sources:
                    if s in region_info:
                        region_info[s]["merges_with"] = [
                            o for o in sources if o != s
                        ]



    def _compute_distances(
        self,
        region_map: Dict[Tuple, int],
        region_info: Dict[str, dict],
    ) -> None:
        """
        Compute distance_to_next_junction_m and distance_to_prev_junction_m.

        Fixes:
        - Works even when junction polygons are synthetic.
        - Always uses road centerline s-coordinates if available.
        - Safe fallback if transformer unavailable.
        """

        scale = self._estimate_scale()
        if scale is None:
            # No metric conversion available → leave distances None
            return

        for key, rid in region_map.items():
            road_id, section_number, lane_id, is_conn = key
            if is_conn:
                continue

            rid_str = str(rid)
            info = region_info.get(rid_str)
            if not info:
                continue

            road = self.project.get_road(road_id)
            if not road or not road.lane_sections:
                continue

            polyline = self.project.get_polyline(road.centerline_id) if road.centerline_id else None
            if not polyline or len(polyline.points) < 2:
                continue

            s_coords = road.calculate_centerline_s_coordinates(polyline.points)
            if not s_coords:
                continue
            total_len_px = s_coords[-1]

            section = road.get_section(section_number)
            if not section:
                continue

            # UPCOMING DISTANCE ---------------------------------------
            if info.get("upcoming_junction_ids"):
                px_dist = max(0.0, total_len_px - section.s_end)
                info["distance_to_next_junction_m"] = round(px_dist * scale, 2)
            else:
                info["distance_to_next_junction_m"] = None

            # PREVIOUS DISTANCE ----------------------------------------
            if info.get("previous_junction_ids"):
                px_dist = max(0.0, section.s_start)
                info["distance_to_prev_junction_m"] = round(px_dist * scale, 2)
            else:
                info["distance_to_prev_junction_m"] = None


    def _estimate_scale(self) -> Optional[float]:
        """Estimate meters-per-pixel scale from transformer or project.

        Returns:
            Scale factor (m/px) or None if unavailable
        """
        if self.transformer:
            # Sample two points to estimate scale
            try:
                x0, y0 = self.transformer.pixel_to_meters(0, 0)
                x1, y1 = self.transformer.pixel_to_meters(100, 0)
                dist_m = math.sqrt((x1 - x0)**2 + (y1 - y0)**2)
                return dist_m / 100.0
            except Exception:
                pass

        return None

    # ---- File I/O ----

    def _save_mask(self, mask: np.ndarray, output_path: str) -> None:
        """Save mask as PNG (uint8/uint16) or TIFF.

        Chooses bit depth based on number of regions.
        """
        max_val = int(mask.max())
        path = Path(output_path)

        if max_val <= 255:
            cv2.imwrite(str(path), mask.astype(np.uint8))
            logger.debug("Saved mask as uint8 PNG (%d regions)", max_val)
        elif max_val <= 65535:
            cv2.imwrite(str(path), mask.astype(np.uint16))
            logger.debug("Saved mask as uint16 (%d regions)", max_val)
        else:
            # Fall back to numpy for very large region counts
            npy_path = path.with_suffix('.npy')
            np.save(str(npy_path), mask)
            logger.warning("Region count %d exceeds uint16 — saved as %s", max_val, npy_path)

    def _save_colorized_mask(self, mask: np.ndarray, output_path: str) -> None:
        """Save a colorized visualization alongside the raw mask.

        Each region gets a distinct, saturated color. Background stays black.
        Saved as *_vis.png for human inspection.
        """
        path = Path(output_path)
        vis_path = path.with_stem(path.stem + "_vis")

        max_val = int(mask.max())
        if max_val == 0:
            return

        # Generate a color lookup table with distinct colors using HSV spacing
        # +1 for background at index 0
        lut = np.zeros((max_val + 1, 3), dtype=np.uint8)
        for i in range(1, max_val + 1):
            # Use golden-ratio-spaced hues for maximum visual separation
            hue = ((i * 137.508) % 360) / 2  # OpenCV hue range is 0-179
            lut[i] = [int(hue), 200, 220]  # High saturation and value

        # Map mask to color image
        flat = mask.ravel().astype(np.int32)
        hsv = lut[np.clip(flat, 0, max_val)].reshape(mask.shape[0], mask.shape[1], 3)
        bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

        # Keep background black
        bgr[mask == 0] = 0

        cv2.imwrite(str(vis_path), bgr)
        logger.debug("Colorized visualization saved: %s", vis_path)

    def _save_world_file(self, output_path: str) -> None:
        """Write a world file (.pgw/.tfw) with affine transform parameters.

        The world file contains 6 lines defining pixel-to-projected-coordinate
        mapping. No new dependencies — universally supported by GIS tools.
        """
        if not self.transformer:
            logger.warning("Cannot write world file without transformer")
            return

        path = Path(output_path)
        suffix = path.suffix.lower()

        # Extension mapping
        world_ext = {
            '.png': '.pgw',
            '.tif': '.tfw',
            '.tiff': '.tfw',
            '.jpg': '.jgw',
            '.jpeg': '.jgw',
            '.bmp': '.bpw',
        }
        ext = world_ext.get(suffix, '.wld')
        world_path = path.with_suffix(ext)

        try:
            # Compute affine parameters from transformer
            # Sample three points to derive the 2x3 affine matrix
            x0, y0 = self.transformer.pixel_to_meters(0, 0)
            x1, y1 = self.transformer.pixel_to_meters(1, 0)
            x2, y2 = self.transformer.pixel_to_meters(0, 1)

            # Affine matrix columns
            a = x1 - x0  # pixel width in x direction
            d = y1 - y0  # rotation term
            b = x2 - x0  # rotation term
            e = y2 - y0  # pixel height in y direction (usually negative)

            # Upper-left pixel center
            c = x0
            f = y0

            # Write 6-line world file
            with open(world_path, 'w') as wf:
                wf.write(f"{a:.10f}\n")
                wf.write(f"{d:.10f}\n")
                wf.write(f"{b:.10f}\n")
                wf.write(f"{e:.10f}\n")
                wf.write(f"{c:.10f}\n")
                wf.write(f"{f:.10f}\n")

            logger.info("World file written: %s", world_path)
        except Exception:
            logger.exception("Failed to write world file")

    def _save_metadata(self, region_info: Dict[str, dict], json_path: str) -> None:
        """Save region metadata as JSON."""
        # Convert sets to sorted lists for JSON serialization
        serializable = {}
        for key, value in region_info.items():
            if isinstance(value, dict):
                clean = {}
                for k, v in value.items():
                    if isinstance(v, set):
                        clean[k] = sorted(str(x) for x in v)
                    elif isinstance(v, list):
                        clean[k] = [str(x) if not isinstance(x, str) else x for x in v]
                    else:
                        clean[k] = v
                serializable[key] = clean
            else:
                serializable[key] = value

        with open(json_path, 'w') as f:
            json.dump(serializable, f, indent=2)

        logger.debug("Metadata written: %s", json_path)

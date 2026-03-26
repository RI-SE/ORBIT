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

        for junction in self.project.junctions:
            print("DEBUG: Junction", junction.id, 
                "has boundary:", junction.boundary is not None)

    def _enhance_connecting_lane_links(self, region_map, region_info):
        """
        Lanelet-compatible connecting-lane linkage:
        - Connecting lanes link ONLY to the final lane of predecessor road
        and the first lane of the successor road.
        - Symmetry is enforced.
        """
        lane_lookup = {}
        for key, rid in region_map.items():
            road, section, lane, is_conn = key
            if not is_conn:
                lane_lookup[(road, lane)] = str(rid)

        for rid_str, info in region_info.items():
            if info.get("type") != "connecting_lane":
                continue

            cr_id = info["road_id"]
            lane_id = info["lane_id"]
            cr_obj = None

            for j in self.project.junctions:
                for cr in j.connecting_roads:
                    if cr.id == cr_id:
                        cr_obj = cr
                        break
                if cr_obj:
                    break

            if not cr_obj:
                continue

            pred_road = cr_obj.predecessor_road_id
            succ_road = cr_obj.successor_road_id

            # predecessor
            if pred_road:
                tup = (pred_road, lane_id)
                if tup in lane_lookup:
                    pid = lane_lookup[tup]
                    if pid not in info["predecessors"]:
                        info["predecessors"].append(pid)
                    if rid_str not in region_info[pid]["successors"]:
                        region_info[pid]["successors"].append(rid_str)

            # successor
            if succ_road:
                tup = (succ_road, lane_id)
                if tup in lane_lookup:
                    sid = lane_lookup[tup]
                    if sid not in info["successors"]:
                        info["successors"].append(sid)
                    if rid_str not in region_info[sid]["predecessors"]:
                        region_info[sid]["predecessors"].append(rid_str)

        # dedupe & sort
        for rid_str, info in region_info.items():
            if not isinstance(info, dict):
                continue
            info["successors"] = sorted(set(info.get("successors", [])), key=lambda v: int(v) if v.isdigit() else v)
            info["predecessors"] = sorted(set(info.get("predecessors", [])), key=lambda v: int(v) if v.isdigit() else v)


    def _apply_adjacency_fixscript_like(
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

        # Rule C: Overlap members are NOT adjacency carriers.

        # Geometric adjacency (NEW) ------------------------------
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
            self._enhance_connecting_lane_links(region_map, region_info)
            # --- adjacency using fix-script-like rules  ---
            self._apply_adjacency_fixscript_like(region_map, region_info)
            # --- overlap successor/predecessor unions (same as fix script) ---
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
        from orbit.export.curve_fitting import CurveFitter
        from orbit.export.reference_line_sampler import (
            compute_lane_polygons,
            sample_reference_line,
        )

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

            # Estimate scale (meters per pixel)
            total_px = sum(
                math.sqrt((polyline.points[i+1][0] - polyline.points[i][0])**2 +
                           (polyline.points[i+1][1] - polyline.points[i][1])**2)
                for i in range(len(polyline.points) - 1)
            )
            total_m = sum(
                math.sqrt((meter_points[i+1][0] - meter_points[i][0])**2 +
                           (meter_points[i+1][1] - meter_points[i][1])**2)
                for i in range(len(meter_points) - 1)
            )
            scale_x = total_m / total_px if total_px > 0 else 0.058

            # Compute lane polygons in meters
            lane_polys = compute_lane_polygons(ref_points, road, scale_x)

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

        # Extend CR path slightly at both endpoints along the heading.
        # Curve-fitted road reference lines may not end at exactly the same
        # position as the raw CR path endpoints. The extension ensures the
        # CR polygon reaches the road polygon boundary. The mask renderer
        # gives road pixels priority, so the extended part is clipped at
        # the road boundary — producing a clean seam with no gap or overlap.
        _EXT_M = 0.5  # extension distance in meters
        if len(path_meters) >= 2:
            hdg0 = headings[0]
            ext_start = (
                path_meters[0][0] - math.cos(hdg0) * _EXT_M,
                path_meters[0][1] - math.sin(hdg0) * _EXT_M,
            )
            path_meters.insert(0, ext_start)
            headings.insert(0, hdg0)
            s_values = [0.0] + [s + _EXT_M for s in s_values]

            hdg_end = headings[-1]
            ext_end = (
                path_meters[-1][0] + math.cos(hdg_end) * _EXT_M,
                path_meters[-1][1] + math.sin(hdg_end) * _EXT_M,
            )
            path_meters.append(ext_end)
            headings.append(hdg_end)
            s_values.append(s_values[-1] + _EXT_M)

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
        """Offset a single connecting road lane in meter space and convert to pixels."""
        inner_boundary = []
        outer_boundary = []

        for i, (mx, my) in enumerate(path_meters):
            hdg = headings[i]
            s_m = s_values[i]

            # Cumulative inner offset from inner lanes
            inner_offset = sum(
                il.get_width_at_s(s_m, path_length_m)
                for il in inner_lanes
            )
            outer_offset = inner_offset + lane.get_width_at_s(s_m, path_length_m)

            # Perpendicular direction
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

        # Build polygon: inner forward + outer reversed
        meter_pts = inner_boundary + list(reversed(outer_boundary))
        if len(meter_pts) < 3:
            return None

        # Convert to pixels
        pixel_pts = []
        for mx, my in meter_pts:
            px, py = self.transformer.meters_to_pixel(mx, my)
            pixel_pts.append((px, py))

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
                    "polygon": [[float(px), float(py)] for (px, py) in poly.points]
                }
                next_id += 1

        return region_map, region_info

    # ---- Mask rendering ----

    def _render_mask_with_overlaps(
        self,
        polygons: List[LanePolygonData],
        region_map: Dict[Tuple, int],
        region_info: Dict[str, dict],
    ) -> np.ndarray:
        """Render polygons into a mask, tracking overlapping regions.

        Rendering priority rules:
        - Road polygons are painted first (they appear first in the polygon list).
        - CR polygons that overlap road pixels are clipped: road pixels are
          preserved and the CR fills only the remaining background pixels up
          to the road boundary. This produces a clean 1-pixel seam between
          CR and road regions with no gap and no overlap.
        - When two CR polygons overlap (e.g. CRs sharing a common start
          that diverge), a combo region is created for downstream consumers.
        """
        h, w = self.image_size[1], self.image_size[0]
        mask = np.zeros((h, w), dtype=np.int32)

        # Track which base IDs occupy each combo
        combo_map: Dict[frozenset, int] = {}
        id_members: Dict[int, frozenset] = {}
        next_combo_id = max(int(k) for k in region_info) + 1

        # Build set of region IDs that are regular road lanes (not CRs)
        road_lane_ids: Set[int] = set()
        for key, rid in region_map.items():
            _, _, _, is_connecting = key
            if not is_connecting:
                road_lane_ids.add(rid)

        for poly in polygons:
            key = (poly.road_id, poly.section_number, poly.lane_id, poly.is_connecting_road)
            region_id = region_map.get(key)
            if region_id is None:
                continue

            is_cr = poly.is_connecting_road

            pts = np.array(poly.points, dtype=np.int32).reshape((-1, 1, 2))
            if pts.shape[0] < 3:
                continue

            # Find pixels that would be painted
            temp = np.zeros((h, w), dtype=np.uint8)
            cv2.fillPoly(temp, [pts], 1)
            new_pixels = temp > 0

            # Check for overlaps with existing painted regions
            existing = mask[new_pixels]
            overlap_mask = existing > 0

            if np.any(overlap_mask):
                # Get unique existing IDs in overlap
                overlap_ids = np.unique(existing[overlap_mask])

                for old_id in overlap_ids:
                    old_id = int(old_id)

                    # CR overlapping a road lane at junction boundary:
                    # road pixels take priority — skip, don't overwrite.
                    # The CR will fill background pixels up to the road
                    # boundary in the "paint remaining" step below.
                    if is_cr and old_id in road_lane_ids:
                        continue

                    # CR overlapping a road-only combo: same — preserve.
                    old_members = id_members.get(old_id, frozenset([old_id]))
                    if is_cr and old_members.issubset(road_lane_ids):
                        continue

                    # All other overlaps (CR-CR, road-road): create combo region
                    new_members = old_members | frozenset([region_id])

                    if new_members in combo_map:
                        combo_id = combo_map[new_members]
                    else:
                        combo_id = next_combo_id
                        next_combo_id += 1
                        combo_map[new_members] = combo_id
                        id_members[combo_id] = new_members
                        # Create overlap metadata
                        member_strs = sorted(str(m) for m in new_members)
                        region_info[str(combo_id)] = {
                            "type": "overlap",
                            "members": member_strs,
                            "adjacent": [],
                        }
                    # Paint overlap pixels with combo ID
                    overlap_pixel_mask = new_pixels & (mask == old_id)
                    mask[overlap_pixel_mask] = combo_id

            # Paint remaining (non-overlap) pixels
            no_overlap = new_pixels & (mask == 0)
            mask[no_overlap] = region_id
            id_members[region_id] = frozenset([region_id])

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

    def _compute_adjacency(self, mask: np.ndarray) -> Dict[int, Set[int]]:
        """Compute spatial adjacency between regions using vectorized comparison.

        Checks horizontal and vertical neighbor pairs. Two regions are adjacent
        if they share at least one edge pixel boundary.
        """
        # Horizontal pairs
        left = mask[:, :-1]
        right = mask[:, 1:]
        h_diff = left != right
        if np.any(h_diff):
            h_pairs = np.column_stack([left[h_diff], right[h_diff]])
        else:
            h_pairs = np.empty((0, 2), dtype=mask.dtype)

        # Vertical pairs
        top = mask[:-1, :]
        bottom = mask[1:, :]
        v_diff = top != bottom
        if np.any(v_diff):
            v_pairs = np.column_stack([top[v_diff], bottom[v_diff]])
        else:
            v_pairs = np.empty((0, 2), dtype=mask.dtype)

        if h_pairs.shape[0] == 0 and v_pairs.shape[0] == 0:
            return {}

        all_pairs = np.vstack([h_pairs, v_pairs])
        # Filter out background (0)
        valid = (all_pairs[:, 0] != 0) & (all_pairs[:, 1] != 0)
        all_pairs = all_pairs[valid]

        if all_pairs.shape[0] == 0:
            return {}

        # Normalize pair order and deduplicate
        sorted_pairs = np.sort(all_pairs, axis=1)
        unique_pairs = np.unique(sorted_pairs, axis=0)

        adjacency: Dict[int, Set[int]] = {}
        for a, b in unique_pairs:
            a, b = int(a), int(b)
            if a == b:
                continue
            adjacency.setdefault(a, set()).add(b)
            adjacency.setdefault(b, set()).add(a)
        return adjacency

    def _apply_adjacency(
        self, region_info: Dict[str, dict], adjacency: Dict[int, Set[int]],
    ) -> None:
        """Write adjacency sets into region_info."""
        for region_id, neighbors in adjacency.items():
            key = str(region_id)
            if key in region_info:
                region_info[key]["adjacent"] = sorted(str(n) for n in neighbors)

    # ---- Connectivity ----

    def _link(info_src, info_dst, src_id_str, dst_id_str, as_successor: bool):
        if as_successor:
            if dst_id_str not in info_src["successors"]:
                info_src["successors"].append(dst_id_str)
            if src_id_str not in info_dst["predecessors"]:
                info_dst["predecessors"].append(src_id_str)
        else:
            if dst_id_str not in info_src["predecessors"]:
                info_src["predecessors"].append(dst_id_str)
            if src_id_str not in info_dst["successors"]:
                info_dst["successors"].append(src_id_str)


    def _compute_connectivity(self, region_map, region_info):
        """
        Lanelet-compatible longitudinal connectivity:
        - Pure successor/predecessor graph.
        - No lateral adjacency.
        - No contradictions.
        """

        id_to_key = {v: k for k, v in region_map.items()}
        lane_lookup = {(road, sec, lane): rid
                    for (road, sec, lane, is_conn), rid in region_map.items()}

        for region_id, key in id_to_key.items():
            road_id, section_number, lane_id, is_conn = key
            rid_str = str(region_id)

            if rid_str not in region_info:
                continue
            info = region_info[rid_str]
            if info.get("type") not in ("lane", "connecting_lane"):
                continue

            try:
                connected = self.find_connected_lanes(road_id, section_number, lane_id)
            except Exception:
                continue

            for conn_road, conn_sec, conn_lane in connected.get("road_lanes", []):
                target = lane_lookup.get((conn_road, conn_sec, conn_lane))
                if target is None:
                    continue
                tid = str(target)

                # enforce symmetry
                if tid not in info["successors"]:
                    info["successors"].append(tid)
                if rid_str not in region_info[tid]["predecessors"]:
                    region_info[tid]["predecessors"].append(rid_str)

        # dedupe + sort
        for rid_str, info in region_info.items():
            if not isinstance(info, dict):
                continue
            info["successors"] = sorted(set(info.get("successors", [])), key=lambda v: int(v) if v.isdigit() else v)
            info["predecessors"] = sorted(set(info.get("predecessors", [])), key=lambda v: int(v) if v.isdigit() else v)

        # handle junction-crossing direct edges
        self._compute_direct_connections(region_map, region_info, lane_lookup)


    
    def _compute_direct_connections(
        self,
        region_map: Dict[Tuple, int],
        region_info: Dict[str, dict],
        lane_lookup: Dict[Tuple[str, int, int], int],
    ) -> None:
        """
        Direct connections across junctions represent turn-paths.
        - Must NOT include connecting-lane IDs.
        - Must refer only to entry-lane -> exit-lane relationships.
        """
        for junction in self.project.junctions:
            for lc in junction.lane_connections:
                src_road = self.project.get_road(lc.from_road_id)
                tgt_road = self.project.get_road(lc.to_road_id)

                if not src_road or not tgt_road:
                    continue
                if not src_road.lane_sections or not tgt_road.lane_sections:
                    continue

                last_section = src_road.lane_sections[-1].section_number
                first_section = tgt_road.lane_sections[0].section_number

                src_rid = lane_lookup.get((lc.from_road_id, last_section, lc.from_lane_id))
                tgt_rid = lane_lookup.get((lc.to_road_id, first_section, lc.to_lane_id))

                if src_rid is None or tgt_rid is None:
                    continue

                src = str(src_rid)
                tgt = str(tgt_rid)

                if region_info[src].get("type") == "connecting_lane":
                    continue
                if region_info[tgt].get("type") == "connecting_lane":
                    continue

                region_info[src].setdefault("direct_successors", [])
                region_info[tgt].setdefault("direct_predecessors", [])

                if tgt not in region_info[src]["direct_successors"]:
                    region_info[src]["direct_successors"].append(tgt)
                if src not in region_info[tgt]["direct_predecessors"]:
                    region_info[tgt]["direct_predecessors"].append(src)



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

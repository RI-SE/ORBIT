"""
Main OSM importer orchestrator for ORBIT.

Coordinates the full import process: query, parse, convert, and create ORBIT objects.
"""

import importlib
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Set

from orbit.models import Junction, Project, Road
from orbit.models.polyline import Polyline
from orbit.utils import CoordinateTransformer
from orbit.utils.geometry import clip_polygon_to_bbox, clip_polyline_to_bbox
from orbit.utils.logging_config import get_logger

from .junction_analyzer import create_connecting_roads_from_patterns, evaluate_and_fix_connecting_roads
from .osm_parser import OSMData, OSMParser
from .osm_query import OverpassAPIClient, OverpassAPIError
from .osm_to_orbit import (
    calculate_bbox_from_image,
    clip_node_ids,
    compute_adaptive_offsets,
    create_landuse_from_osm,
    create_object_from_osm,
    create_parking_from_osm,
    create_road_from_osm,
    create_signal_from_osm,
    detect_junctions,
    detect_junctions_from_osm,
    detect_path_crossings_from_osm,
    detect_road_links,
    offset_road_endpoints_from_junctions,
)
from .roundabout_handler import (
    analyze_roundabout,
    create_ring_segments,
    create_roundabout_junctions,
    generate_all_roundabout_connectors,
    link_ring_segments,
)

logger = get_logger(__name__)


class ImportMode(Enum):
    """Import mode: add to existing or replace."""
    ADD = "add"
    REPLACE = "replace"


class DetailLevel(Enum):
    """Level of detail for import."""
    MODERATE = "moderate"
    FULL = "full"


@dataclass
class ImportOptions:
    """Options for OSM import."""
    import_mode: ImportMode = ImportMode.ADD
    detail_level: DetailLevel = DetailLevel.MODERATE
    default_lane_width: float = 3.5  # meters
    import_junctions: bool = True
    simplify_geometry: bool = False
    simplify_tolerance: float = 1.0  # meters (not implemented yet)
    timeout: int = 60  # seconds
    verbose: bool = False  # Print debug information
    filter_outside_image: bool = False  # Filter out roads with no endpoint inside image
    auto_adjust_junctions: bool = True  # Adaptive offsets + CR curvature fix


@dataclass
class ImportResult:
    """Result of OSM import operation."""
    success: bool = False
    error_message: Optional[str] = None
    roads_imported: int = 0
    junctions_imported: int = 0
    signals_imported: int = 0
    objects_imported: int = 0
    parking_imported: int = 0
    roads_skipped_duplicate: int = 0
    signals_skipped_duplicate: int = 0
    objects_skipped_duplicate: int = 0
    parking_skipped_duplicate: int = 0
    partial_import: bool = False  # True if API timed out but kept partial data


class OSMImporter:
    """Main OSM import orchestrator."""

    def __init__(self, project: Project, transformer: CoordinateTransformer,
                 image_width: int, image_height: int):
        """
        Initialize OSM importer.

        Args:
            project: ORBIT project to import into
            transformer: Coordinate transformer with control points
            image_width: Width of image in pixels
            image_height: Height of image in pixels
        """
        self.project = project
        self.transformer = transformer
        self.image_width = image_width
        self.image_height = image_height

        # Track imported OSM IDs for duplicate detection
        self.imported_way_ids: Set[int] = set()
        self.imported_node_ids: Set[int] = set()

        # Track roundabout way IDs (processed separately from regular roads)
        self.roundabout_way_ids: Set[int] = set()

        # Track mapping from Road ID to OSM way ID for junction detection
        self.road_to_osm_way: Dict[str, int] = {}

        # Track mapping from Signal ID to OSM node ID for road attachment
        self.signal_to_osm_node: Dict[str, int] = {}

        # Clip bbox in (min_lon, min_lat, max_lon, max_lat) format.
        # Set by import_osm_data / _import_from_osm_data from the query bbox.
        # Falls back to image bounds if not set.
        self._clip_geo_bbox: Optional[tuple] = None

    def _ensure_clip_bbox(self, import_bbox: Optional[tuple] = None) -> None:
        """Set the geo clip bbox for geometry clipping.

        When the transformer handles extrapolation safely (HybridTransformer),
        uses only the query bbox — no image-bounds intersection needed.
        Otherwise falls back to intersecting with image geo bounds (with 100%
        buffer) to prevent homography extrapolation artifacts.

        Args:
            import_bbox: (min_lat, min_lon, max_lat, max_lon) from Overpass query.
                         If None, only image bounds are used.
        """
        from orbit.utils.coordinate_transform import HybridTransformer

        # HybridTransformer blends to affine outside image — no clip needed
        uses_hybrid = isinstance(self.transformer, HybridTransformer)

        # Step 1: Compute image geo bbox with generous buffer (skip for hybrid)
        image_geo_bbox = None
        if not uses_hybrid:
            corners = [
                (0, 0), (self.image_width, 0),
                (self.image_width, self.image_height), (0, self.image_height),
            ]
            try:
                lons, lats = [], []
                for px, py in corners:
                    lon, lat = self.transformer.pixel_to_geo(px, py)
                    lons.append(lon)
                    lats.append(lat)
                min_lon, max_lon = min(lons), max(lons)
                min_lat, max_lat = min(lats), max(lats)
                lon_buf = (max_lon - min_lon)
                lat_buf = (max_lat - min_lat)
                image_geo_bbox = (min_lon - lon_buf, min_lat - lat_buf,
                                  max_lon + lon_buf, max_lat + lat_buf)
            except Exception:
                pass

        # Step 2: Convert import bbox if provided
        query_geo_bbox = None
        if import_bbox is not None:
            min_lat, min_lon, max_lat, max_lon = import_bbox
            query_geo_bbox = (min_lon, min_lat, max_lon, max_lat)

        # Step 3: Combine — intersect only when image bbox clipping is active
        if image_geo_bbox and query_geo_bbox:
            self._clip_geo_bbox = (
                max(image_geo_bbox[0], query_geo_bbox[0]),
                max(image_geo_bbox[1], query_geo_bbox[1]),
                min(image_geo_bbox[2], query_geo_bbox[2]),
                min(image_geo_bbox[3], query_geo_bbox[3]),
            )
        elif image_geo_bbox:
            self._clip_geo_bbox = image_geo_bbox
        elif query_geo_bbox:
            self._clip_geo_bbox = query_geo_bbox
        else:
            self._clip_geo_bbox = None

    def _clip_resolved_coords(self, coords: List) -> List:
        """Clip (lat, lon) resolved_coords to the clip bbox.

        Args:
            coords: List of (lat, lon) tuples from OSM way

        Returns:
            Clipped list of (lat, lon) tuples
        """
        if not self._clip_geo_bbox or len(coords) < 2:
            return coords

        min_lon, min_lat, max_lon, max_lat = self._clip_geo_bbox
        lonlat_coords = [(lon, lat) for lat, lon in coords]
        clipped = clip_polyline_to_bbox(lonlat_coords, (min_lon, min_lat, max_lon, max_lat))
        return [(lat, lon) for lon, lat in clipped]

    def _clip_resolved_coords_polygon(self, coords: List) -> List:
        """Clip (lat, lon) resolved_coords polygon to the clip bbox.

        Args:
            coords: List of (lat, lon) tuples from OSM way (polygon)

        Returns:
            Clipped list of (lat, lon) tuples
        """
        if not self._clip_geo_bbox or len(coords) < 3:
            return coords

        min_lon, min_lat, max_lon, max_lat = self._clip_geo_bbox
        lonlat_coords = [(lon, lat) for lat, lon in coords]
        clipped = clip_polygon_to_bbox(lonlat_coords, (min_lon, min_lat, max_lon, max_lat))
        return [(lat, lon) for lon, lat in clipped]

    def import_osm_data(self, options: ImportOptions = None,
                        bbox: Optional[tuple] = None) -> ImportResult:
        """
        Import OSM data into project.

        Args:
            options: Import options
            bbox: Optional pre-computed bounding box (min_lat, min_lon, max_lat, max_lon).
                  If None, calculated from image bounds.

        Returns:
            ImportResult with statistics and status
        """
        if options is None:
            options = ImportOptions()

        result = ImportResult()

        # Step 1: Calculate bounding box (use provided bbox or derive from image)
        if bbox is None:
            try:
                bbox = calculate_bbox_from_image(
                    self.image_width,
                    self.image_height,
                    self.transformer,
                    buffer_percent=5.0
                )
            except Exception as e:
                result.error_message = f"Failed to calculate bounding box: {e}"
                return result

        # Set clip boundary from the query bbox
        self._ensure_clip_bbox(bbox)

        # Step 2: Query Overpass API
        client = OverpassAPIClient(timeout=options.timeout)
        try:
            osm_json = client.query_bbox(bbox, options.detail_level.value)
        except OverpassAPIError as e:
            result.error_message = f"Overpass API error: {e}"
            # Check if it's a timeout - we may have partial data
            if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                result.partial_import = True
                result.error_message += "\n\nPartial data may have been received before timeout."
            return result

        if not osm_json:
            result.error_message = "No data received from Overpass API"
            return result

        # Step 2a: Write JSON to file if verbose mode enabled
        if options.verbose:
            try:
                import json
                with open('overpass_tmp.json', 'w', encoding='utf-8') as f:
                    json.dump(osm_json, f, indent=2)
                num_elems = len(osm_json.get('elements', []))
                logger.debug(
                    "Wrote Overpass API response to overpass_tmp.json (%d elements)",
                    num_elems
                )
            except Exception as e:
                logger.warning("Failed to write overpass_tmp.json: %s", e)

        # Step 3: Parse OSM data
        try:
            osm_data = OSMParser.parse(osm_json)

            if options.verbose:
                logger.debug(
                    "Parsed OSM data: %d nodes, %d ways, %d relations",
                    len(osm_data.nodes), len(osm_data.ways), len(osm_data.relations)
                )
                # Count nodes by type
                highway_nodes = sum(1 for n in osm_data.nodes.values() if 'highway' in n.tags)
                logger.debug("Nodes with 'highway' tag: %d", highway_nodes)
                if highway_nodes > 0 and highway_nodes < 20:  # Show details if not too many
                    for node in osm_data.nodes.values():
                        if 'highway' in node.tags:
                            logger.debug("  Node %s: highway=%s, tags=%s", node.id, node.tags.get('highway'), node.tags)
        except Exception as e:
            result.error_message = f"Failed to parse OSM data: {e}"
            return result

        # Step 4: Handle import mode
        if options.import_mode == ImportMode.REPLACE:
            # Clear existing data
            self.project.roads.clear()
            self.project.polylines.clear()
            self.project.junctions.clear()
            self.project.signals.clear()
            self.project.objects.clear()
            self.imported_way_ids.clear()
            self.imported_node_ids.clear()

        # Step 5: Import roads
        roads, polylines_dict = self._import_roads(osm_data, options, result)

        # Step 6: Detect junction node IDs (for road splitting)
        if options.import_junctions:
            import importlib
            osm_to_orbit = importlib.import_module('orbit.import.osm_to_orbit')
            detect_junction_node_ids_from_osm = osm_to_orbit.detect_junction_node_ids_from_osm
            split_roads_at_junction_nodes = osm_to_orbit.split_roads_at_junction_nodes

            junction_node_ids = detect_junction_node_ids_from_osm(osm_data, self.road_to_osm_way)

            if options.verbose:
                logger.debug("Detected %d junction nodes for road splitting", len(junction_node_ids))

            # Step 7: Split roads at junction nodes (BEFORE linking!)
            if junction_node_ids:
                roads, polylines_dict, updated_road_to_osm_way = split_roads_at_junction_nodes(
                    roads, polylines_dict, junction_node_ids,
                    road_to_osm_way=self.road_to_osm_way,
                    verbose=options.verbose,
                    osm_data=osm_data,
                    transformer=self.transformer,
                )

                # Update project with split roads and polylines
                self.project.roads = roads
                self.project.polylines = list(polylines_dict.values())

                # Sync ID counters so subsequent add_road/add_polyline calls
                # don't collide with IDs assigned by the split function
                self.project._sync_id_counters()

                # Update road_to_osm_way mapping with split roads
                if updated_road_to_osm_way is not None:
                    self.road_to_osm_way = updated_road_to_osm_way

        # Step 7b: Import roundabouts (after road splitting, before junction import)
        self._import_roundabouts(osm_data, options, result, roads, polylines_dict)

        # Step 8: Detect and set predecessor/successor links (after splitting!)
        detect_road_links(roads, polylines_dict, tolerance=5.0)

        # Step 9: Import junctions and generate connections
        if options.import_junctions:
            self._import_junctions_from_osm(osm_data, options, result)

        # Step 8: Import signals (moderate and full)
        self._import_signals(osm_data, options, result)

        # Step 8a: Auto-attach signals to roads based on OSM node membership
        self._attach_signals_to_roads(osm_data, options)

        # Step 9: Import objects (full only)
        if options.detail_level == DetailLevel.FULL:
            self._import_objects(osm_data, options, result)

        # Step 9a: Import land use areas (full only)
        if options.detail_level == DetailLevel.FULL:
            self._import_landuse(osm_data, options, result)

        # Step 9b: Auto-attach objects to nearest roads
        if options.detail_level == DetailLevel.FULL:
            self._attach_objects_to_roads(options)

        # Step 9c: Import parking facilities (full only)
        if options.detail_level == DetailLevel.FULL:
            self._import_parking(osm_data, options, result)

        # Step 10: Clear stale cross-junction road links
        # Roads in junctions should not have predecessor/successor pointing to each other
        self.project.clear_cross_junction_road_links()

        # Assign IDs to any entities created without explicit IDs
        self.project.assign_missing_ids()

        # Link lane connections to connecting roads (must happen after ID assignment)
        self.project.link_lane_connections_to_connecting_roads()

        # Mark success if we imported anything
        result.success = (
            result.roads_imported > 0 or
            result.signals_imported > 0 or
            result.objects_imported > 0 or
            result.parking_imported > 0
        )

        return result

    def _import_from_osm_data(self, osm_data: OSMData, options: ImportOptions,
                             bbox: Optional[tuple] = None) -> ImportResult:
        """
        Import from already-parsed OSM data (e.g., from XML file).

        This bypasses the API query step and imports directly from OSMData.

        Args:
            osm_data: Parsed OSM data
            options: Import options
            bbox: Optional bounding box (min_lat, min_lon, max_lat, max_lon)
                  for clipping. Falls back to image bounds if None.

        Returns:
            ImportResult with statistics and status
        """
        result = ImportResult()

        # Set clip boundary
        self._ensure_clip_bbox(bbox)

        # Step 1: Handle import mode
        if options.import_mode == ImportMode.REPLACE:
            # Clear existing data
            self.project.roads.clear()
            self.project.polylines.clear()
            self.project.junctions.clear()
            self.project.signals.clear()
            self.project.objects.clear()
            self.imported_way_ids.clear()
            self.imported_node_ids.clear()

        # Step 2: Import roads
        roads, polylines_dict = self._import_roads(osm_data, options, result)

        # Step 3: Detect junction node IDs (for road splitting)
        if options.import_junctions:
            import importlib
            osm_to_orbit = importlib.import_module('orbit.import.osm_to_orbit')
            detect_junction_node_ids_from_osm = osm_to_orbit.detect_junction_node_ids_from_osm
            split_roads_at_junction_nodes = osm_to_orbit.split_roads_at_junction_nodes

            junction_node_ids = detect_junction_node_ids_from_osm(osm_data, self.road_to_osm_way)

            if options.verbose:
                logger.debug("Detected %d junction nodes for road splitting", len(junction_node_ids))

            # Step 4: Split roads at junction nodes (BEFORE linking!)
            if junction_node_ids:
                roads, polylines_dict, updated_road_to_osm_way = split_roads_at_junction_nodes(
                    roads, polylines_dict, junction_node_ids,
                    road_to_osm_way=self.road_to_osm_way,
                    verbose=options.verbose,
                    osm_data=osm_data,
                    transformer=self.transformer,
                )

                # Update project with split roads and polylines
                self.project.roads = roads
                self.project.polylines = list(polylines_dict.values())

                # Sync ID counters so subsequent add_road/add_polyline calls
                # don't collide with IDs assigned by the split function
                self.project._sync_id_counters()

                # Update road_to_osm_way mapping with split roads
                if updated_road_to_osm_way is not None:
                    self.road_to_osm_way = updated_road_to_osm_way

        # Step 4b: Import roundabouts (after road splitting, before junction import)
        self._import_roundabouts(osm_data, options, result, roads, polylines_dict)

        # Step 5: Detect and set predecessor/successor links (after splitting!)
        detect_road_links(roads, polylines_dict, tolerance=5.0)

        # Step 6: Import junctions and generate connections
        if options.import_junctions:
            self._import_junctions_from_osm(osm_data, options, result)

        # Step 7: Import signals (moderate and full)
        self._import_signals(osm_data, options, result)

        # Step 5a: Auto-attach signals to roads based on OSM node membership
        self._attach_signals_to_roads(osm_data, options)

        # Step 6: Import objects (full only)
        if options.detail_level == DetailLevel.FULL:
            self._import_objects(osm_data, options, result)

        # Step 6a: Import land use areas (full only)
        if options.detail_level == DetailLevel.FULL:
            self._import_landuse(osm_data, options, result)

        # Step 6b: Auto-attach objects to nearest roads
        if options.detail_level == DetailLevel.FULL:
            self._attach_objects_to_roads(options)

        # Step 6c: Import parking facilities (full only)
        if options.detail_level == DetailLevel.FULL:
            self._import_parking(osm_data, options, result)

        # Step 7: Clear stale cross-junction road links
        # Roads in junctions should not have predecessor/successor pointing to each other
        self.project.clear_cross_junction_road_links()

        # Assign IDs to any entities created without explicit IDs
        self.project.assign_missing_ids()

        # Link lane connections to connecting roads (must happen after ID assignment)
        self.project.link_lane_connections_to_connecting_roads()

        # Mark success if we imported anything
        result.success = (
            result.roads_imported > 0 or
            result.signals_imported > 0 or
            result.objects_imported > 0 or
            result.parking_imported > 0
        )

        return result

    def _import_roads(self, osm_data: OSMData, options: ImportOptions,
                     result: ImportResult) -> tuple[List[Road], dict]:
        """
        Import roads from OSM data.

        Roundabout ways (junction=roundabout) are skipped here and processed
        separately by _import_roundabouts().

        Returns:
            Tuple of (roads list, polylines_dict)
        """
        roads = []
        polylines_dict = {}

        highway_ways = OSMParser.get_highway_ways(osm_data)

        # Identify roundabout ways first (they'll be processed separately)
        roundabout_ways = OSMParser.get_roundabout_ways(osm_data)
        self.roundabout_way_ids = {way.id for way in roundabout_ways}

        if options.verbose and self.roundabout_way_ids:
            logger.debug("Found %d roundabout way(s) - will process separately", len(self.roundabout_way_ids))

        for osm_way in highway_ways:
            # Skip roundabout ways - they're processed by _import_roundabouts
            if osm_way.id in self.roundabout_way_ids:
                if options.verbose:
                    logger.debug("Skipping roundabout way %s (will process separately)", osm_way.id)
                continue

            # Clip road geometry to image geo bounds to prevent homography
            # extrapolation artifacts far from control points
            if self._clip_geo_bbox and osm_way.resolved_coords:
                original_coords = osm_way.resolved_coords
                osm_way.resolved_coords = self._clip_resolved_coords(
                    original_coords
                )
                if len(osm_way.resolved_coords) < 2:
                    continue
                # Update node IDs to match clipped coords: keep IDs for
                # original points that survived, use None for interpolated
                # boundary points inserted by clipping
                if len(osm_way.resolved_coords) != len(original_coords) and osm_way.nodes:
                    osm_way.nodes = clip_node_ids(
                        original_coords, osm_way.nodes,
                        osm_way.resolved_coords)

            road_result = create_road_from_osm(
                osm_way,
                self.transformer,
                options.default_lane_width,
                self.imported_way_ids
            )

            if road_result is None:
                # Already imported or should not import
                if osm_way.id in self.imported_way_ids:
                    result.roads_skipped_duplicate += 1
                continue

            road, centerline = road_result

            # Filter roads outside image bounds if option is enabled
            if options.filter_outside_image and len(centerline.points) >= 2:
                start_pt = centerline.points[0]
                end_pt = centerline.points[-1]

                start_inside = (0 <= start_pt[0] <= self.image_width and
                               0 <= start_pt[1] <= self.image_height)
                end_inside = (0 <= end_pt[0] <= self.image_width and
                             0 <= end_pt[1] <= self.image_height)

                if not start_inside and not end_inside:
                    # Neither endpoint is inside image bounds, skip this road
                    if options.verbose:
                        logger.debug("Skipping road '%s' - no endpoint inside image bounds", road.name)
                    continue

            # Add to project (assigns IDs to road and polyline)
            self.project.add_polyline(centerline)
            self.project.add_road(road)

            # Update road references with the assigned polyline ID
            road.centerline_id = centerline.id
            road.polyline_ids = [centerline.id]

            # Track
            roads.append(road)
            polylines_dict[centerline.id] = centerline
            self.imported_way_ids.add(osm_way.id)
            self.road_to_osm_way[road.id] = osm_way.id  # Track for junction detection
            result.roads_imported += 1

        return roads, polylines_dict

    def _import_roundabouts(
        self,
        osm_data: OSMData,
        options: ImportOptions,
        result: ImportResult,
        roads: List[Road],
        polylines_dict: Dict[str, Polyline]
    ) -> None:
        """
        Import roundabouts from OSM data.

        Roundabouts are split into ring segments at each entry/exit point,
        with junctions created at each connection.

        Args:
            osm_data: Parsed OSM data
            options: Import options
            result: Import result to update
            roads: List of already imported roads (to find approach roads)
            polylines_dict: Dict of polyline_id -> Polyline
        """
        if not self.roundabout_way_ids:
            return

        if options.verbose:
            logger.debug("Processing %d roundabout(s)...", len(self.roundabout_way_ids))

        # Build approach roads dict for finding connecting roads
        approach_roads = {road.id: road for road in roads}

        for roundabout_way_id in self.roundabout_way_ids:
            osm_way = osm_data.ways.get(roundabout_way_id)
            if not osm_way:
                continue

            if options.verbose:
                name = osm_way.tags.get('name', f'Way {roundabout_way_id}')
                logger.debug("Analyzing roundabout '%s' (way %s)", name, roundabout_way_id)

            try:
                # Step 1: Analyze roundabout geometry
                roundabout_info = analyze_roundabout(
                    osm_way, osm_data, self.transformer,
                    verbose=options.verbose
                )

                if options.verbose:
                    logger.debug("  Center: (%.1f, %.1f)", roundabout_info.center[0], roundabout_info.center[1])
                    logger.debug("  Radius: %.1f px", roundabout_info.radius)
                    logger.debug("  Connection points: %d", len(roundabout_info.connection_points))

                # Filter roundabouts outside image bounds if option is enabled
                if options.filter_outside_image:
                    cx, cy = roundabout_info.center
                    if not (0 <= cx <= self.image_width and 0 <= cy <= self.image_height):
                        if options.verbose:
                            logger.debug("  Skipping roundabout - center outside image bounds")
                        continue

                # Step 2: Create ring segments
                ring_segments = create_ring_segments(
                    roundabout_info,
                    default_lane_width=options.default_lane_width,
                    verbose=options.verbose
                )

                if options.verbose:
                    logger.debug("  Created %d ring segment(s)", len(ring_segments))

                # Add ring segments to project
                ring_roads = []
                for road, polyline in ring_segments:
                    self.project.add_polyline(polyline)
                    self.project.add_road(road)
                    # Update road references with the assigned polyline ID
                    road.centerline_id = polyline.id
                    road.polyline_ids = [polyline.id]
                    polylines_dict[polyline.id] = polyline
                    ring_roads.append(road)
                    result.roads_imported += 1

                    # Track OSM mapping
                    self.road_to_osm_way[road.id] = roundabout_way_id

                # Step 3: Create junctions at entry/exit points
                roundabout_junctions = create_roundabout_junctions(
                    roundabout_info,
                    ring_segments,
                    approach_roads,
                    polylines_dict,
                    verbose=options.verbose
                )

                if options.verbose:
                    logger.debug("  Created %d junction(s)", len(roundabout_junctions))

                for junction in roundabout_junctions:
                    self.project.add_junction(junction)
                    result.junctions_imported += 1

                # Step 4: Link ring segments with predecessor/successor
                link_ring_segments(ring_segments, roundabout_junctions)

                # Step 4.5: Offset road endpoints from roundabout junctions
                # This creates gaps for connecting roads to fill
                # Collect approach roads connected to this roundabout
                roundabout_approach_roads = []
                for junction in roundabout_junctions:
                    for road_id in junction.connected_road_ids:
                        road = approach_roads.get(road_id)
                        if road and road not in roundabout_approach_roads:
                            roundabout_approach_roads.append(road)

                # Offset ring segments with ring offset distance
                offset_road_endpoints_from_junctions(
                    roads=ring_roads,
                    polylines_dict=polylines_dict,
                    junctions=roundabout_junctions,
                    offset_distance_meters=self.project.roundabout_ring_offset_distance_meters,
                    transformer=self.transformer,
                    verbose=options.verbose
                )

                # Offset approach roads with approach offset distance (typically larger)
                offset_road_endpoints_from_junctions(
                    roads=roundabout_approach_roads,
                    polylines_dict=polylines_dict,
                    junctions=roundabout_junctions,
                    offset_distance_meters=self.project.roundabout_approach_offset_distance_meters,
                    transformer=self.transformer,
                    verbose=options.verbose
                )

                if options.verbose:
                    ring_offset = self.project.roundabout_ring_offset_distance_meters
                    approach_offset = self.project.roundabout_approach_offset_distance_meters
                    logger.debug(
                        "  Applied %sm offset to ring segments, %sm to approach roads",
                        ring_offset, approach_offset
                    )

                # Step 5: Generate connectors for entry/exit/through movements
                generate_all_roundabout_connectors(
                    roundabout=roundabout_info,
                    junctions=roundabout_junctions,
                    ring_segments=ring_segments,
                    approach_roads=approach_roads,
                    polylines_dict=polylines_dict,
                    default_lane_width=options.default_lane_width,
                    verbose=options.verbose,
                    project=self.project
                )

                if options.verbose:
                    total_connectors = sum(len(j.connecting_road_ids) for j in roundabout_junctions)
                    logger.debug("  Generated %d connecting road(s)", total_connectors)

                # Mark as imported
                self.imported_way_ids.add(roundabout_way_id)

            except Exception as e:
                logger.warning("Failed to import roundabout %s: %s", roundabout_way_id, e, exc_info=True)
                continue

        if options.verbose:
            logger.debug("Finished processing roundabouts")

    def _import_junctions_from_osm(self, osm_data: OSMData, options: ImportOptions,
                                   result: ImportResult) -> List[Junction]:
        """Import junctions using OSM node ID matching."""
        # Create polylines dict for junction filtering
        polylines_dict = {p.id: p for p in self.project.polylines}

        # Detect regular road-road junctions
        junctions = detect_junctions_from_osm(
            osm_data,
            self.road_to_osm_way,
            self.transformer,
            roads=self.project.roads,
            polylines_dict=polylines_dict
        )

        if options.verbose:
            logger.debug("Detected %d road junctions from OSM node IDs", len(junctions))

        for junction in junctions:
            self.project.add_junction(junction)
            result.junctions_imported += 1
            if options.verbose:
                logger.debug(
                    "Added junction '%s' at %s connecting %d roads",
                    junction.name, junction.center_point, len(junction.connected_road_ids)
                )

        # IMPORTANT ORDER: Analyze connections BEFORE offsetting endpoints
        # This way we detect which roads connect while they're still at the junction center

        roads_dict = {road.id: road for road in self.project.roads}

        # Step 1: Analyze junction geometry and detect connection patterns (before offsetting)
        if junctions and options.verbose:
            logger.debug("Analyzing geometry for %d junctions before offsetting...", len(junctions))

        # Import junction_analyzer to access analysis functions

        # Process OSM turn restriction relations
        if junctions:
            osm_to_orbit = importlib.import_module('orbit.import.osm_to_orbit')
            process_turn_restrictions = osm_to_orbit.process_turn_restrictions
            restrictions_count = process_turn_restrictions(
                osm_data,
                junctions,
                self.road_to_osm_way,
                verbose=options.verbose
            )
            if options.verbose:
                logger.debug("Processed %d turn restrictions from OSM relations", restrictions_count)
        junction_analyzer_module = importlib.import_module('orbit.import.junction_analyzer')
        analyze_junction_geometry = junction_analyzer_module.analyze_junction_geometry
        detect_connection_patterns = junction_analyzer_module.detect_connection_patterns
        filter_unlikely_connections = junction_analyzer_module.filter_unlikely_connections

        # Feature A: Compute adaptive offsets and merge close junctions
        per_road_offsets = None
        if options.auto_adjust_junctions and junctions:
            per_road_offsets, merged, merged_ids = compute_adaptive_offsets(
                junctions=junctions,
                roads=self.project.roads,
                polylines_dict=polylines_dict,
                base_offset=self.project.junction_offset_distance_meters,
                transformer=self.transformer,
            )
            if merged:
                # Remove merged source junctions, add merged replacements
                for mid in merged_ids:
                    self.project.remove_junction(mid)
                junctions = [j for j in junctions if j.id not in merged_ids]
                for m in merged:
                    self.project.add_junction(m)
                    junctions.append(m)
                    result.junctions_imported += 1
                logger.debug("Merged %d junction pairs into %d junctions",
                              len(merged_ids), len(merged))
                # Refresh roads_dict after potential changes
                roads_dict = {road.id: road for road in self.project.roads}

        # Store geometry info and patterns for each junction (before offsetting)
        # Skip virtual junctions (path crossings) as they don't need connecting roads
        junction_patterns = {}
        for junction in junctions:
            # Skip virtual junctions (path crossings) - no connecting roads needed
            if junction.junction_type == "virtual":
                if options.verbose:
                    logger.debug("Skipping virtual junction '%s' (path crossing)", junction.name)
                continue

            geometry_info = analyze_junction_geometry(junction, roads_dict, polylines_dict)
            patterns = detect_connection_patterns(geometry_info)
            patterns = filter_unlikely_connections(patterns, roads_dict)
            junction_patterns[junction.id] = patterns

        # Step 2: Offset road endpoints from junctions to create space for connecting roads
        if junctions:
            osm_to_orbit = importlib.import_module('orbit.import.osm_to_orbit')
            offset_fn = osm_to_orbit.offset_road_endpoints_from_junctions

            offset_fn(
                roads=self.project.roads,
                polylines_dict=polylines_dict,
                junctions=junctions,
                offset_distance_meters=self.project.junction_offset_distance_meters,
                transformer=self.transformer,
                verbose=options.verbose,
                per_road_offsets=per_road_offsets,
            )

            # Update project polylines with modified endpoints
            self.project.polylines = list(polylines_dict.values())

        # Step 3: Generate connecting roads using pre-detected patterns but with updated (offset) positions
        if junctions and options.verbose:
            logger.debug("Generating connections for %d junctions...", len(junctions))

        # Refresh dicts after offset
        roads_dict = {road.id: road for road in self.project.roads}
        polylines_dict = {p.id: p for p in self.project.polylines}

        for junction in junctions:
            # Skip virtual junctions (path crossings) - no connecting roads generated
            if junction.junction_type == "virtual":
                continue

            # Use the pre-detected patterns from before offsetting
            patterns = junction_patterns.get(junction.id, [])

            # Re-analyze geometry to get UPDATED endpoint positions (after offset)
            # Skip distance check since roads have been offset from junction center
            geometry_info_updated = analyze_junction_geometry(
                junction, roads_dict, polylines_dict,
                skip_distance_check=True,
            )

            # Create endpoint lookup by road_id for quick access
            endpoint_lookup = {ep.road_id: ep for ep in geometry_info_updated['endpoints']}

            # Generate connecting roads using patterns from BEFORE offset but positions from AFTER offset
            # This uses the shared function which includes pair detection for bidirectional roads
            # Pass transformer for geo-first path generation when geo coords are available
            create_connecting_roads_from_patterns(
                junction, patterns, endpoint_lookup, self.transformer,
                project=self.project)

            # Feature B: Evaluate and fix sharp CR curvature
            if options.auto_adjust_junctions:
                evaluate_and_fix_connecting_roads(
                    junction, self.project, self.transformer)

            if options.verbose:
                summary = junction.get_connection_summary()
                logger.debug(
                    "Generated %d connections for '%s': %d straight, %d left, %d right",
                    summary['total_connections'], junction.name,
                    summary['straight'], summary['left'], summary['right']
                )

        # Detect virtual junctions for path crossings
        path_crossings = detect_path_crossings_from_osm(
            osm_data,
            self.road_to_osm_way,
            self.transformer
        )

        if options.verbose:
            logger.debug("Detected %d path crossings (virtual junctions)", len(path_crossings))

        for crossing in path_crossings:
            self.project.add_junction(crossing)
            result.junctions_imported += 1
            if options.verbose:
                logger.debug("Added virtual junction '%s' at %s", crossing.name, crossing.center_point)

        # NOTE: Virtual junctions (path crossings) do NOT get connecting roads.
        # They are visual markers only, representing where paths cross roads without
        # actual traffic connections (e.g., pedestrian path over a road).

        # Return both regular junctions and path crossings
        all_junctions = junctions + path_crossings
        return all_junctions

    def _import_junctions(self, roads: List[Road], polylines_dict: dict,
                         options: ImportOptions, result: ImportResult) -> List[Junction]:
        """DEPRECATED: Import junctions using geometric detection (for non-OSM imports)."""
        # Use larger tolerance (5.0 pixels) to account for coordinate transformation imprecision
        junctions = detect_junctions(roads, polylines_dict, tolerance=5.0)

        if options.verbose:
            logger.debug("Detected %d junctions from %d roads", len(junctions), len(roads))

        for junction in junctions:
            self.project.add_junction(junction)
            result.junctions_imported += 1
            if options.verbose:
                logger.debug(
                    "Added junction '%s' at %s connecting %d roads",
                    junction.name, junction.center_point, len(junction.connected_road_ids)
                )

        return junctions

    def _import_signals(self, osm_data: OSMData, options: ImportOptions,
                       result: ImportResult) -> None:
        """Import traffic signals and signs."""
        # Traffic signals
        traffic_signals = OSMParser.get_traffic_signal_nodes(osm_data)

        if options.verbose:
            logger.debug("Found %d traffic signal nodes in OSM data", len(traffic_signals))

        for osm_node in traffic_signals:
            signal = create_signal_from_osm(
                osm_node,
                self.transformer,
                self.imported_node_ids
            )

            if signal is None:
                if osm_node.id in self.imported_node_ids:
                    result.signals_skipped_duplicate += 1
                    if options.verbose:
                        logger.debug("Skipped duplicate traffic signal node: %s", osm_node.id)
                elif options.verbose:
                    logger.debug("Skipped traffic signal node %s (create_signal_from_osm returned None)", osm_node.id)
                continue

            self.project.add_signal(signal)
            self.imported_node_ids.add(osm_node.id)
            self.signal_to_osm_node[signal.id] = osm_node.id  # Track for road attachment
            result.signals_imported += 1

            if options.verbose:
                logger.debug("Imported traffic signal: %s at %s", signal.name, signal.position)

        # Traffic signs
        traffic_signs = OSMParser.get_traffic_sign_nodes(osm_data)

        if options.verbose:
            logger.debug("Found %d traffic sign nodes in OSM data", len(traffic_signs))

        for osm_node in traffic_signs:
            signal = create_signal_from_osm(
                osm_node,
                self.transformer,
                self.imported_node_ids
            )

            if signal is None:
                if osm_node.id in self.imported_node_ids:
                    result.signals_skipped_duplicate += 1
                    if options.verbose:
                        logger.debug("Skipped duplicate traffic sign node: %s", osm_node.id)
                elif options.verbose:
                    logger.debug(
                        "Skipped traffic sign node %s (create_signal_from_osm returned None, tags: %s)",
                        osm_node.id, osm_node.tags
                    )
                continue

            self.project.add_signal(signal)
            self.imported_node_ids.add(osm_node.id)
            self.signal_to_osm_node[signal.id] = osm_node.id  # Track for road attachment
            result.signals_imported += 1

            if options.verbose:
                logger.debug("Imported traffic sign: %s at %s", signal.name, signal.position)

    def _attach_signals_to_roads(self, osm_data: OSMData, options: ImportOptions) -> None:
        """
        Attach signals to roads if they are located on OSM nodes that are part of road ways.

        This automatically assigns road_id and calculates s_position for signals that are
        on nodes belonging to imported roads. Users can still manually adjust assignments later.
        """
        if not self.signal_to_osm_node:
            return  # No signals with OSM node tracking

        # Build reverse index: OSM node ID -> list of road IDs that contain this node
        node_to_roads: Dict[int, List[str]] = {}

        for road_id, osm_way_id in self.road_to_osm_way.items():
            osm_way = osm_data.ways.get(osm_way_id)
            if not osm_way or not osm_way.nodes:
                continue

            # For each node in this way, add this road to the node's road list
            for node_id in osm_way.nodes:
                if node_id not in node_to_roads:
                    node_to_roads[node_id] = []
                node_to_roads[node_id].append(road_id)

        # Now attach signals to roads
        attached_count = 0
        for signal in self.project.signals:
            # Skip if signal already has a road assigned (manually set or previous import)
            if signal.road_id:
                continue

            # Check if this signal has an OSM node ID
            osm_node_id = self.signal_to_osm_node.get(signal.id)
            if not osm_node_id:
                continue

            # Check if this node is part of any road
            road_ids = node_to_roads.get(osm_node_id, [])
            if not road_ids:
                continue

            # Attach to the first road found (usually there's only one for traffic signals)
            # If multiple roads share this node (junction), we pick the first one
            road_id = road_ids[0]
            road = self.project.get_road(road_id)
            if not road or not road.centerline_id:
                continue

            # Get centerline polyline
            centerline = self.project.get_polyline(road.centerline_id)
            if not centerline or not centerline.points:
                continue

            # Assign road and calculate s-position
            signal.road_id = road_id
            signal.s_position = signal.calculate_s_position(centerline.points)

            attached_count += 1

            if options.verbose:
                orientation_str = signal.get_orientation_ui_string()
                logger.debug(
                    "Auto-attached signal '%s' to road '%s' at s=%.1f, orientation=%s",
                    signal.name, road.name, signal.s_position, orientation_str
                )

        if options.verbose and attached_count > 0:
            logger.debug("Auto-attached %d signals to roads based on OSM node membership", attached_count)

    def _attach_objects_to_roads(self, options: ImportOptions) -> None:
        """
        Attach objects to nearest roads.

        Automatically assigns road_id and calculates s_position and t_offset for objects
        by finding the nearest road to each object. Users can still manually adjust assignments later.
        """
        if not self.project.objects:
            return  # No objects to attach

        if not self.project.roads:
            return  # No roads to attach to

        attached_count = 0

        for obj in self.project.objects:
            # Skip if object already has a road assigned
            if obj.road_id:
                continue

            # Find nearest road
            min_distance = float('inf')
            nearest_road = None
            nearest_s = None
            nearest_t = None

            for road in self.project.roads:
                if not road.centerline_id:
                    continue

                centerline = self.project.get_polyline(road.centerline_id)
                if not centerline or not centerline.points:
                    continue

                # Calculate s and t position for this road
                s_pos, t_offset = obj.calculate_s_t_position(centerline.points)
                if s_pos is None:
                    continue

                # Distance is the absolute value of t_offset
                distance = abs(t_offset)

                if distance < min_distance:
                    min_distance = distance
                    nearest_road = road
                    nearest_s = s_pos
                    nearest_t = t_offset

            # Attach to nearest road if found
            if nearest_road:
                obj.road_id = nearest_road.id
                obj.s_position = nearest_s
                obj.t_offset = nearest_t
                attached_count += 1

                if options.verbose:
                    logger.debug(
                        "Auto-attached object '%s' to road '%s' at s=%.1f, t=%.1f",
                        obj.get_display_name(), nearest_road.name, nearest_s, nearest_t
                    )

        if options.verbose and attached_count > 0:
            logger.debug("Auto-attached %d objects to nearest roads", attached_count)

    def _import_objects(self, osm_data: OSMData, options: ImportOptions,
                       result: ImportResult) -> None:
        """Import road objects (full mode only)."""
        # Street lamps
        lamps = OSMParser.get_street_lamp_nodes(osm_data)
        for osm_node in lamps:
            obj = create_object_from_osm(
                osm_node,
                self.transformer,
                self.imported_node_ids
            )

            if obj is None:
                if osm_node.id in self.imported_node_ids:
                    result.objects_skipped_duplicate += 1
                continue

            self.project.add_object(obj)
            self.imported_node_ids.add(osm_node.id)
            result.objects_imported += 1

        # Trees
        trees = OSMParser.get_tree_nodes(osm_data)
        for osm_node in trees:
            obj = create_object_from_osm(
                osm_node,
                self.transformer,
                self.imported_node_ids
            )

            if obj is None:
                if osm_node.id in self.imported_node_ids:
                    result.objects_skipped_duplicate += 1
                continue

            self.project.add_object(obj)
            self.imported_node_ids.add(osm_node.id)
            result.objects_imported += 1

        # Guardrails
        guardrails = OSMParser.get_guardrail_ways(osm_data)
        for osm_way in guardrails:
            # Clip guardrail polyline to image geo bounds
            if self._clip_geo_bbox and osm_way.resolved_coords:
                osm_way.resolved_coords = self._clip_resolved_coords(
                    osm_way.resolved_coords
                )
                if len(osm_way.resolved_coords) < 2:
                    continue

            obj = create_object_from_osm(
                osm_way,
                self.transformer,
                self.imported_way_ids
            )

            if obj is None:
                if osm_way.id in self.imported_way_ids:
                    result.objects_skipped_duplicate += 1
                continue

            self.project.add_object(obj)
            self.imported_way_ids.add(osm_way.id)
            result.objects_imported += 1

        # Buildings
        buildings = OSMParser.get_building_ways(osm_data)
        for osm_way in buildings:
            # Clip building polygon to image geo bounds
            if self._clip_geo_bbox and osm_way.resolved_coords:
                osm_way.resolved_coords = self._clip_resolved_coords_polygon(
                    osm_way.resolved_coords
                )
                if len(osm_way.resolved_coords) < 3:
                    continue

            obj = create_object_from_osm(
                osm_way,
                self.transformer,
                self.imported_way_ids
            )

            if obj is None:
                if osm_way.id in self.imported_way_ids:
                    result.objects_skipped_duplicate += 1
                continue

            self.project.add_object(obj)
            self.imported_way_ids.add(osm_way.id)
            result.objects_imported += 1

    def _import_landuse(self, osm_data: OSMData, options: ImportOptions,
                        result: ImportResult) -> None:
        """Import land use / natural area polygons (full mode only)."""
        landuse_ways = OSMParser.get_landuse_ways(osm_data)

        if options.verbose:
            logger.debug("Found %d land use ways in OSM data", len(landuse_ways))

        for osm_way in landuse_ways:
            # Clip land use polygon to image geo bounds
            if self._clip_geo_bbox and osm_way.resolved_coords:
                osm_way.resolved_coords = self._clip_resolved_coords_polygon(
                    osm_way.resolved_coords
                )
                if len(osm_way.resolved_coords) < 3:
                    if options.verbose:
                        logger.debug("Skipping land use way %s - entirely outside image bounds", osm_way.id)
                    continue

            obj = create_landuse_from_osm(
                osm_way, self.transformer, self.imported_way_ids
            )
            if obj is None:
                continue

            self.project.add_object(obj)
            self.imported_way_ids.add(osm_way.id)
            result.objects_imported += 1

            if options.verbose:
                logger.debug("Imported land use '%s' (%s)", obj.name, obj.type.value)

    def _import_parking(self, osm_data: OSMData, options: ImportOptions,
                        result: ImportResult) -> None:
        """Import parking facilities (full mode only)."""
        # Parking ways (polygon facilities)
        parking_ways = OSMParser.get_parking_ways(osm_data)

        if options.verbose:
            logger.debug("Found %d parking ways in OSM data", len(parking_ways))

        for osm_way in parking_ways:
            parking = create_parking_from_osm(
                osm_way,
                self.transformer,
                self.imported_way_ids
            )

            if parking is None:
                if osm_way.id in self.imported_way_ids:
                    result.parking_skipped_duplicate += 1
                continue

            self.project.add_parking(parking)
            self.imported_way_ids.add(osm_way.id)
            result.parking_imported += 1

            if options.verbose:
                logger.debug("Imported parking '%s' (%s)", parking.name, parking.parking_type.value)

        # Parking nodes (point facilities)
        parking_nodes = OSMParser.get_parking_nodes(osm_data)

        if options.verbose:
            logger.debug("Found %d parking nodes in OSM data", len(parking_nodes))

        for osm_node in parking_nodes:
            parking = create_parking_from_osm(
                osm_node,
                self.transformer,
                self.imported_node_ids
            )

            if parking is None:
                if osm_node.id in self.imported_node_ids:
                    result.parking_skipped_duplicate += 1
                continue

            self.project.add_parking(parking)
            self.imported_node_ids.add(osm_node.id)
            result.parking_imported += 1

            if options.verbose:
                logger.debug("Imported parking '%s' (%s)", parking.name, parking.parking_type.value)

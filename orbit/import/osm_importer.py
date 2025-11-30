"""
Main OSM importer orchestrator for ORBIT.

Coordinates the full import process: query, parse, convert, and create ORBIT objects.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Set, Dict
from enum import Enum
import importlib

from orbit.utils import CoordinateTransformer
from orbit.models import Project, Road, Junction, Signal, RoadObject
from orbit.models.polyline import Polyline

from .osm_query import OverpassAPIClient, OverpassAPIError
from .osm_parser import OSMParser, OSMData
from .osm_to_orbit import (
    calculate_bbox_from_image,
    detect_road_links,
    detect_junctions,
    detect_junctions_from_osm,
    detect_path_crossings_from_osm,
    split_road_at_junctions,
    create_road_from_osm,
    create_signal_from_osm,
    create_object_from_osm,
)
from .junction_analyzer import generate_junction_connections


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


@dataclass
class ImportResult:
    """Result of OSM import operation."""
    success: bool = False
    error_message: Optional[str] = None
    roads_imported: int = 0
    junctions_imported: int = 0
    signals_imported: int = 0
    objects_imported: int = 0
    roads_skipped_duplicate: int = 0
    signals_skipped_duplicate: int = 0
    objects_skipped_duplicate: int = 0
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

        # Track mapping from Road ID to OSM way ID for junction detection
        self.road_to_osm_way: Dict[str, int] = {}

        # Track mapping from Signal ID to OSM node ID for road attachment
        self.signal_to_osm_node: Dict[str, int] = {}

    def import_osm_data(self, options: ImportOptions = None) -> ImportResult:
        """
        Import OSM data into project.

        Args:
            options: Import options

        Returns:
            ImportResult with statistics and status
        """
        if options is None:
            options = ImportOptions()

        result = ImportResult()

        # Step 1: Calculate bounding box
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
                print(f"DEBUG: Wrote Overpass API response to overpass_tmp.json ({len(osm_json.get('elements', []))} elements)")
            except Exception as e:
                print(f"WARNING: Failed to write overpass_tmp.json: {e}")

        # Step 3: Parse OSM data
        try:
            osm_data = OSMParser.parse(osm_json)

            if options.verbose:
                print(f"DEBUG: Parsed OSM data: {len(osm_data.nodes)} nodes, {len(osm_data.ways)} ways, {len(osm_data.relations)} relations")
                # Count nodes by type
                highway_nodes = sum(1 for n in osm_data.nodes.values() if 'highway' in n.tags)
                print(f"DEBUG: Nodes with 'highway' tag: {highway_nodes}")
                if highway_nodes > 0 and highway_nodes < 20:  # Show details if not too many
                    for node in osm_data.nodes.values():
                        if 'highway' in node.tags:
                            print(f"DEBUG:   Node {node.id}: highway={node.tags.get('highway')}, tags={node.tags}")
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
                print(f"DEBUG: Detected {len(junction_node_ids)} junction nodes for road splitting")

            # Step 7: Split roads at junction nodes (BEFORE linking!)
            if junction_node_ids:
                roads, polylines_dict, updated_road_to_osm_way = split_roads_at_junction_nodes(
                    roads, polylines_dict, junction_node_ids,
                    road_to_osm_way=self.road_to_osm_way,
                    verbose=options.verbose
                )

                # Update project with split roads and polylines
                self.project.roads = roads
                self.project.polylines = list(polylines_dict.values())

                # Update road_to_osm_way mapping with split roads
                if updated_road_to_osm_way is not None:
                    self.road_to_osm_way = updated_road_to_osm_way

        # Step 8: Detect and set predecessor/successor links (after splitting!)
        detect_road_links(roads, polylines_dict, tolerance=5.0)

        # Step 9: Import junctions and generate connections
        if options.import_junctions:
            junctions = self._import_junctions_from_osm(osm_data, options, result)
        else:
            junctions = []

        # Step 8: Import signals (moderate and full)
        self._import_signals(osm_data, options, result)

        # Step 8a: Auto-attach signals to roads based on OSM node membership
        self._attach_signals_to_roads(osm_data, options)

        # Step 9: Import objects (full only)
        if options.detail_level == DetailLevel.FULL:
            self._import_objects(osm_data, options, result)

        # Step 9a: Auto-attach objects to nearest roads
        if options.detail_level == DetailLevel.FULL:
            self._attach_objects_to_roads(options)

        # Mark success if we imported anything
        result.success = (
            result.roads_imported > 0 or
            result.signals_imported > 0 or
            result.objects_imported > 0
        )

        return result

    def _import_from_osm_data(self, osm_data: OSMData, options: ImportOptions) -> ImportResult:
        """
        Import from already-parsed OSM data (e.g., from XML file).

        This bypasses the API query step and imports directly from OSMData.

        Args:
            osm_data: Parsed OSM data
            options: Import options

        Returns:
            ImportResult with statistics and status
        """
        result = ImportResult()

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
                print(f"DEBUG: Detected {len(junction_node_ids)} junction nodes for road splitting")

            # Step 4: Split roads at junction nodes (BEFORE linking!)
            if junction_node_ids:
                roads, polylines_dict, updated_road_to_osm_way = split_roads_at_junction_nodes(
                    roads, polylines_dict, junction_node_ids,
                    road_to_osm_way=self.road_to_osm_way,
                    verbose=options.verbose
                )

                # Update project with split roads and polylines
                self.project.roads = roads
                self.project.polylines = list(polylines_dict.values())

                # Update road_to_osm_way mapping with split roads
                if updated_road_to_osm_way is not None:
                    self.road_to_osm_way = updated_road_to_osm_way

        # Step 5: Detect and set predecessor/successor links (after splitting!)
        detect_road_links(roads, polylines_dict, tolerance=5.0)

        # Step 6: Import junctions and generate connections
        if options.import_junctions:
            junctions = self._import_junctions_from_osm(osm_data, options, result)
        else:
            junctions = []

        # Step 5: Import signals (moderate and full)
        self._import_signals(osm_data, options, result)

        # Step 5a: Auto-attach signals to roads based on OSM node membership
        self._attach_signals_to_roads(osm_data, options)

        # Step 6: Import objects (full only)
        if options.detail_level == DetailLevel.FULL:
            self._import_objects(osm_data, options, result)

        # Step 6a: Auto-attach objects to nearest roads
        if options.detail_level == DetailLevel.FULL:
            self._attach_objects_to_roads(options)

        # Mark success if we imported anything
        result.success = (
            result.roads_imported > 0 or
            result.signals_imported > 0 or
            result.objects_imported > 0
        )

        return result

    def _import_roads(self, osm_data: OSMData, options: ImportOptions,
                     result: ImportResult) -> tuple[List[Road], dict]:
        """
        Import roads from OSM data.

        Returns:
            Tuple of (roads list, polylines_dict)
        """
        roads = []
        polylines_dict = {}

        highway_ways = OSMParser.get_highway_ways(osm_data)

        for osm_way in highway_ways:
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

            # Add to project
            self.project.add_road(road)
            self.project.add_polyline(centerline)

            # Track
            roads.append(road)
            polylines_dict[centerline.id] = centerline
            self.imported_way_ids.add(osm_way.id)
            self.road_to_osm_way[road.id] = osm_way.id  # Track for junction detection
            result.roads_imported += 1

        return roads, polylines_dict

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
            print(f"DEBUG: Detected {len(junctions)} road junctions from OSM node IDs")

        for junction in junctions:
            self.project.add_junction(junction)
            result.junctions_imported += 1
            if options.verbose:
                print(f"DEBUG: Added junction '{junction.name}' at {junction.center_point} connecting {len(junction.connected_road_ids)} roads")

        # IMPORTANT ORDER: Analyze connections BEFORE offsetting endpoints
        # This way we detect which roads connect while they're still at the junction center

        roads_dict = {road.id: road for road in self.project.roads}

        # Step 1: Analyze junction geometry and detect connection patterns (before offsetting)
        if junctions and options.verbose:
            print(f"DEBUG: Analyzing geometry for {len(junctions)} junctions before offsetting...")

        # Import junction_analyzer to access analysis functions
        import importlib
        junction_analyzer_module = importlib.import_module('orbit.import.junction_analyzer')
        analyze_junction_geometry = junction_analyzer_module.analyze_junction_geometry
        detect_connection_patterns = junction_analyzer_module.detect_connection_patterns
        filter_unlikely_connections = junction_analyzer_module.filter_unlikely_connections

        # Store geometry info and patterns for each junction (before offsetting)
        # Skip virtual junctions (path crossings) as they don't need connecting roads
        junction_patterns = {}
        for junction in junctions:
            # Skip virtual junctions (path crossings) - no connecting roads needed
            if junction.junction_type == "virtual":
                if options.verbose:
                    print(f"DEBUG: Skipping virtual junction '{junction.name}' (path crossing)")
                continue

            geometry_info = analyze_junction_geometry(junction, roads_dict, polylines_dict)
            patterns = detect_connection_patterns(geometry_info)
            patterns = filter_unlikely_connections(patterns, roads_dict)
            junction_patterns[junction.id] = patterns

        # Step 2: Offset road endpoints from junctions to create space for connecting roads
        if junctions:
            osm_to_orbit = importlib.import_module('orbit.import.osm_to_orbit')
            offset_road_endpoints_from_junctions = osm_to_orbit.offset_road_endpoints_from_junctions

            offset_road_endpoints_from_junctions(
                roads=self.project.roads,
                polylines_dict=polylines_dict,
                junctions=junctions,
                offset_distance_meters=self.project.junction_offset_distance_meters,
                transformer=self.transformer,
                verbose=options.verbose
            )

            # Update project polylines with modified endpoints
            self.project.polylines = list(polylines_dict.values())

        # Step 3: Generate connecting roads using pre-detected patterns but with updated (offset) positions
        if junctions and options.verbose:
            print(f"DEBUG: Generating connections for {len(junctions)} junctions...")

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
            geometry_info_updated = analyze_junction_geometry(junction, roads_dict, polylines_dict, skip_distance_check=True)

            # Create endpoint lookup by road_id for quick access
            endpoint_lookup = {}
            for endpoint in geometry_info_updated['endpoints']:
                endpoint_lookup[endpoint.road_id] = endpoint

            # Generate connecting roads using patterns from BEFORE offset but positions from AFTER offset
            generate_simple_connection_path = junction_analyzer_module.generate_simple_connection_path
            ConnectingRoad = importlib.import_module('orbit.models.connecting_road').ConnectingRoad
            LaneConnection = importlib.import_module('orbit.models.lane_connection').LaneConnection
            generate_lane_links_for_connection = junction_analyzer_module.generate_lane_links_for_connection

            for pattern in patterns:
                # Get UPDATED endpoints (with offset positions)
                from_endpoint_updated = endpoint_lookup.get(pattern.from_road_id)
                to_endpoint_updated = endpoint_lookup.get(pattern.to_road_id)

                if not from_endpoint_updated or not to_endpoint_updated:
                    continue

                # Calculate average lane width
                avg_lane_width = (from_endpoint_updated.lane_width + to_endpoint_updated.lane_width) / 2

                # Determine lane count - only use right lanes for right-hand traffic
                conn_lane_count_right = min(
                    from_endpoint_updated.right_lane_count if from_endpoint_updated.at_junction == "end" else from_endpoint_updated.left_lane_count,
                    to_endpoint_updated.right_lane_count if to_endpoint_updated.at_junction == "start" else to_endpoint_updated.left_lane_count
                )
                conn_lane_count_left = 0  # Right-hand traffic: only right lanes in connecting roads

                # Generate path using CENTERLINE positions with ParamPoly3D (tangent-continuous)
                path, coeffs = generate_simple_connection_path(
                    from_pos=from_endpoint_updated.position,  # Use centerline position
                    from_heading=from_endpoint_updated.heading,
                    to_pos=to_endpoint_updated.position,  # Use centerline position
                    to_heading=to_endpoint_updated.heading,
                    num_points=20,
                    tangent_scale=1.0
                )

                if not path:
                    continue

                # Unpack ParamPoly3D coefficients
                aU, bU, cU, dU, aV, bV, cV, dV = coeffs

                # Create connecting road with ParamPoly3D geometry
                connecting_road = ConnectingRoad(
                    path=path,
                    lane_count_left=conn_lane_count_left,
                    lane_count_right=max(1, conn_lane_count_right),
                    lane_width=avg_lane_width,
                    predecessor_road_id=pattern.from_road_id,
                    successor_road_id=pattern.to_road_id,
                    contact_point_start="end",
                    contact_point_end="start",
                    geometry_type="parampoly3",
                    aU=aU, bU=bU, cU=cU, dU=dU,
                    aV=aV, bV=bV, cV=cV, dV=dV,
                    p_range=1.0,
                    tangent_scale=1.0
                )

                junction.add_connecting_road(connecting_road)

                # Generate lane links
                lane_links = generate_lane_links_for_connection(
                    from_endpoint_updated,
                    to_endpoint_updated,
                    pattern.turn_type
                )

                for from_lane_id, to_lane_id in lane_links:
                    lane_connection = LaneConnection(
                        from_road_id=pattern.from_road_id,
                        from_lane_id=from_lane_id,
                        to_road_id=pattern.to_road_id,
                        to_lane_id=to_lane_id,
                        connecting_road_id=connecting_road.id,
                        turn_type=pattern.turn_type,
                        priority=pattern.priority
                    )
                    junction.add_lane_connection(lane_connection)

            if options.verbose:
                summary = junction.get_connection_summary()
                print(f"DEBUG: Generated {summary['total_connections']} connections for '{junction.name}': "
                      f"{summary['straight']} straight, {summary['left']} left, {summary['right']} right")

        # Detect virtual junctions for path crossings
        path_crossings = detect_path_crossings_from_osm(
            osm_data,
            self.road_to_osm_way,
            self.transformer
        )

        if options.verbose:
            print(f"DEBUG: Detected {len(path_crossings)} path crossings (virtual junctions)")

        for crossing in path_crossings:
            self.project.add_junction(crossing)
            result.junctions_imported += 1
            if options.verbose:
                print(f"DEBUG: Added virtual junction '{crossing.name}' at {crossing.center_point}")

        # IMPORTANT ORDER: Analyze connections BEFORE offsetting endpoints for path crossings

        # Step 1: Analyze geometry and detect connection patterns (before offsetting)
        crossing_patterns = {}
        for crossing in path_crossings:
            geometry_info = analyze_junction_geometry(crossing, roads_dict, polylines_dict)
            patterns = detect_connection_patterns(geometry_info)
            patterns = filter_unlikely_connections(patterns, roads_dict)
            crossing_patterns[crossing.id] = patterns

        # Step 2: Offset road endpoints from path crossings to create space for connecting roads
        if path_crossings:
            offset_road_endpoints_from_junctions(
                roads=self.project.roads,
                polylines_dict=polylines_dict,
                junctions=path_crossings,
                offset_distance_meters=self.project.junction_offset_distance_meters,
                transformer=self.transformer,
                verbose=options.verbose
            )

            # Update project polylines with modified endpoints
            self.project.polylines = list(polylines_dict.values())

        # Step 3: Generate connecting roads using pre-detected patterns with updated positions
        if path_crossings and options.verbose:
            print(f"DEBUG: Generating connections for {len(path_crossings)} path crossings...")

        # Refresh dictionaries after offset
        roads_dict = {road.id: road for road in self.project.roads}
        polylines_dict = {p.id: p for p in self.project.polylines}

        for crossing in path_crossings:
            # Use the pre-detected patterns from before offsetting
            patterns = crossing_patterns.get(crossing.id, [])

            # Re-analyze geometry to get UPDATED endpoint positions (after offset)
            # Skip distance check since roads have been offset from junction center
            geometry_info_updated = analyze_junction_geometry(crossing, roads_dict, polylines_dict, skip_distance_check=True)

            # Create endpoint lookup by road_id
            endpoint_lookup = {}
            for endpoint in geometry_info_updated['endpoints']:
                endpoint_lookup[endpoint.road_id] = endpoint

            # Generate connecting roads using patterns from BEFORE offset but positions from AFTER offset
            generate_simple_connection_path = junction_analyzer_module.generate_simple_connection_path
            ConnectingRoad = importlib.import_module('orbit.models.connecting_road').ConnectingRoad
            LaneConnection = importlib.import_module('orbit.models.lane_connection').LaneConnection
            generate_lane_links_for_connection = junction_analyzer_module.generate_lane_links_for_connection

            for pattern in patterns:
                # Get UPDATED endpoints (with offset positions)
                from_endpoint_updated = endpoint_lookup.get(pattern.from_road_id)
                to_endpoint_updated = endpoint_lookup.get(pattern.to_road_id)

                if not from_endpoint_updated or not to_endpoint_updated:
                    continue

                # Calculate average lane width
                avg_lane_width = (from_endpoint_updated.lane_width + to_endpoint_updated.lane_width) / 2

                # Determine lane count - only use right lanes for right-hand traffic
                conn_lane_count_right = min(
                    from_endpoint_updated.right_lane_count if from_endpoint_updated.at_junction == "end" else from_endpoint_updated.left_lane_count,
                    to_endpoint_updated.right_lane_count if to_endpoint_updated.at_junction == "start" else to_endpoint_updated.left_lane_count
                )
                conn_lane_count_left = 0  # Right-hand traffic: only right lanes in connecting roads

                # Generate path using CENTERLINE positions with ParamPoly3D (tangent-continuous)
                path, coeffs = generate_simple_connection_path(
                    from_pos=from_endpoint_updated.position,  # Use centerline position
                    from_heading=from_endpoint_updated.heading,
                    to_pos=to_endpoint_updated.position,  # Use centerline position
                    to_heading=to_endpoint_updated.heading,
                    num_points=20,
                    tangent_scale=1.0
                )

                if not path:
                    continue

                # Unpack ParamPoly3D coefficients
                aU, bU, cU, dU, aV, bV, cV, dV = coeffs

                # Create connecting road with ParamPoly3D geometry
                connecting_road = ConnectingRoad(
                    path=path,
                    lane_count_left=conn_lane_count_left,
                    lane_count_right=max(1, conn_lane_count_right),
                    lane_width=avg_lane_width,
                    predecessor_road_id=pattern.from_road_id,
                    successor_road_id=pattern.to_road_id,
                    contact_point_start="end",
                    contact_point_end="start",
                    geometry_type="parampoly3",
                    aU=aU, bU=bU, cU=cU, dU=dU,
                    aV=aV, bV=bV, cV=cV, dV=dV,
                    p_range=1.0,
                    tangent_scale=1.0
                )

                crossing.add_connecting_road(connecting_road)

                # Generate lane links
                lane_links = generate_lane_links_for_connection(
                    from_endpoint_updated,
                    to_endpoint_updated,
                    pattern.turn_type
                )

                for from_lane_id, to_lane_id in lane_links:
                    lane_connection = LaneConnection(
                        from_road_id=pattern.from_road_id,
                        from_lane_id=from_lane_id,
                        to_road_id=pattern.to_road_id,
                        to_lane_id=to_lane_id,
                        connecting_road_id=connecting_road.id,
                        turn_type=pattern.turn_type,
                        priority=pattern.priority
                    )
                    crossing.add_lane_connection(lane_connection)

            if options.verbose:
                summary = crossing.get_connection_summary()
                print(f"DEBUG: Generated {summary['total_connections']} connections for '{crossing.name}': "
                      f"{summary['straight']} straight, {summary['left']} left, {summary['right']} right")

        # Return both regular junctions and path crossings
        all_junctions = junctions + path_crossings
        return all_junctions

    def _import_junctions(self, roads: List[Road], polylines_dict: dict,
                         options: ImportOptions, result: ImportResult) -> List[Junction]:
        """DEPRECATED: Import junctions using geometric detection (for non-OSM imports)."""
        # Use larger tolerance (5.0 pixels) to account for coordinate transformation imprecision
        junctions = detect_junctions(roads, polylines_dict, tolerance=5.0)

        if options.verbose:
            print(f"DEBUG: Detected {len(junctions)} junctions from {len(roads)} roads")

        for junction in junctions:
            self.project.add_junction(junction)
            result.junctions_imported += 1
            if options.verbose:
                print(f"DEBUG: Added junction '{junction.name}' at {junction.center_point} connecting {len(junction.connected_road_ids)} roads")

        return junctions

    def _import_signals(self, osm_data: OSMData, options: ImportOptions,
                       result: ImportResult) -> None:
        """Import traffic signals and signs."""
        # Traffic signals
        traffic_signals = OSMParser.get_traffic_signal_nodes(osm_data)

        if options.verbose:
            print(f"DEBUG: Found {len(traffic_signals)} traffic signal nodes in OSM data")

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
                        print(f"DEBUG: Skipped duplicate traffic signal node: {osm_node.id}")
                elif options.verbose:
                    print(f"DEBUG: Skipped traffic signal node {osm_node.id} (create_signal_from_osm returned None)")
                continue

            self.project.add_signal(signal)
            self.imported_node_ids.add(osm_node.id)
            self.signal_to_osm_node[signal.id] = osm_node.id  # Track for road attachment
            result.signals_imported += 1

            if options.verbose:
                print(f"DEBUG: Imported traffic signal: {signal.name} at {signal.position}")

        # Traffic signs
        traffic_signs = OSMParser.get_traffic_sign_nodes(osm_data)

        if options.verbose:
            print(f"DEBUG: Found {len(traffic_signs)} traffic sign nodes in OSM data")

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
                        print(f"DEBUG: Skipped duplicate traffic sign node: {osm_node.id}")
                elif options.verbose:
                    print(f"DEBUG: Skipped traffic sign node {osm_node.id} (create_signal_from_osm returned None, tags: {osm_node.tags})")
                continue

            self.project.add_signal(signal)
            self.imported_node_ids.add(osm_node.id)
            self.signal_to_osm_node[signal.id] = osm_node.id  # Track for road attachment
            result.signals_imported += 1

            if options.verbose:
                print(f"DEBUG: Imported traffic sign: {signal.name} at {signal.position}")

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
                print(f"DEBUG: Auto-attached signal '{signal.name}' to road '{road.name}' at s={signal.s_position:.1f}, orientation={orientation_str}")

        if options.verbose and attached_count > 0:
            print(f"DEBUG: Auto-attached {attached_count} signals to roads based on OSM node membership")

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
                    print(f"DEBUG: Auto-attached object '{obj.get_display_name()}' to road '{nearest_road.name}' at s={nearest_s:.1f}, t={nearest_t:.1f}")

        if options.verbose and attached_count > 0:
            print(f"DEBUG: Auto-attached {attached_count} objects to nearest roads")

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

"""
Main OSM importer orchestrator for ORBIT.

Coordinates the full import process: query, parse, convert, and create ORBIT objects.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Set, Dict
from enum import Enum

from utils import CoordinateTransformer
from models import Project, Road, Junction, Signal, RoadObject
from models.polyline import Polyline

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

        # Step 6: Detect and set predecessor/successor links
        detect_road_links(roads, polylines_dict, tolerance=5.0)

        # Step 7: Import junctions using OSM node IDs
        if options.import_junctions:
            junctions = self._import_junctions_from_osm(osm_data, options, result)

            # Split road sections at junctions
            for road in roads:
                if road.centerline_id:
                    centerline = polylines_dict.get(road.centerline_id)
                    if centerline:
                        split_road_at_junctions(road, centerline, junctions)
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

        # Step 3: Detect and set predecessor/successor links
        detect_road_links(roads, polylines_dict, tolerance=5.0)

        # Step 4: Import junctions using OSM node IDs
        if options.import_junctions:
            junctions = self._import_junctions_from_osm(osm_data, options, result)

            # Split road sections at junctions
            for road in roads:
                if road.centerline_id:
                    centerline = polylines_dict.get(road.centerline_id)
                    if centerline:
                        split_road_at_junctions(road, centerline, junctions)
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
        # Detect regular road-road junctions
        junctions = detect_junctions_from_osm(
            osm_data,
            self.road_to_osm_way,
            self.transformer
        )

        if options.verbose:
            print(f"DEBUG: Detected {len(junctions)} road junctions from OSM node IDs")

        for junction in junctions:
            self.project.add_junction(junction)
            result.junctions_imported += 1
            if options.verbose:
                print(f"DEBUG: Added junction '{junction.name}' at {junction.center_point} connecting {len(junction.connected_road_ids)} roads")

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

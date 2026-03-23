"""
Convert OSM data to ORBIT objects.

Handles coordinate transformation, junction detection, and creation of
Road, Junction, Signal, and RoadObject instances from OSM data.
"""

import math
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from orbit.models import Junction, ParkingSpace, Road, RoadObject, Signal
from orbit.models.lane import Lane, LaneType
from orbit.models.lane_section import LaneSection
from orbit.models.object import ObjectType
from orbit.models.polyline import LineType, Polyline, RoadMarkType
from orbit.models.road import RoadType
from orbit.models.signal import SignalType
from orbit.utils import CoordinateTransformer
from orbit.utils.enum_formatting import format_enum_name
from orbit.utils.geometry import calculate_path_length, find_point_at_distance_along_path, shorten_geo_points
from orbit.utils.logging_config import get_logger

from .osm_mappings import (
    estimate_lane_count,
    get_lane_width_for_highway,
    get_object_type_from_osm,
    get_parking_access_from_osm,
    get_parking_type_from_osm,
    get_path_type_and_lane_type,
    get_path_width_from_osm,
    get_road_type_for_highway,
    get_signal_type_from_osm,
    get_smoothness_roughness,
    get_surface_material,
    is_oneway,
    is_reverse_oneway,
    parse_maxspeed,
    parse_turn_lanes,
    should_import_highway,
)
from .osm_parser import OSMData, OSMNode, OSMWay

logger = get_logger(__name__)


def clip_node_ids(
    original_coords: list,
    original_nodes: List[int],
    clipped_coords: list,
    tolerance: float = 1e-9,
) -> List[Optional[int]]:
    """Map node IDs from original coords to clipped coords.

    For each clipped coord, if it matches an original coord, use its node ID.
    Interpolated boundary points get None.
    """
    if not original_nodes or len(original_nodes) != len(original_coords):
        return []

    # Build lookup: (lat, lon) -> node_id for original coords
    # Use rounded coords as keys to handle float precision
    coord_to_node = {}
    for i, coord in enumerate(original_coords):
        key = (round(coord[0], 8), round(coord[1], 8))
        coord_to_node[key] = original_nodes[i]

    result = []
    for coord in clipped_coords:
        key = (round(coord[0], 8), round(coord[1], 8))
        result.append(coord_to_node.get(key))

    # Only return if we preserved at least some node IDs
    if any(nid is not None for nid in result):
        return result
    return []


def calculate_bbox_from_center(center_lat: float, center_lon: float,
                               radius_m: float) -> Tuple[float, float, float, float]:
    """Calculate bounding box from center point and radius in meters.

    Uses equirectangular approximation (~111,000 m per degree latitude,
    longitude adjusted by cos(lat)). Accuracy is sufficient for radii up to 5 km.

    Args:
        center_lat: Center latitude in decimal degrees
        center_lon: Center longitude in decimal degrees
        radius_m: Radius in meters

    Returns:
        Tuple of (min_lat, min_lon, max_lat, max_lon)
    """
    dlat = radius_m / 111_000
    dlon = radius_m / (111_000 * math.cos(math.radians(center_lat)))
    return (center_lat - dlat, center_lon - dlon,
            center_lat + dlat, center_lon + dlon)


def calculate_bbox_from_image(image_width: int, image_height: int,
                               transformer: CoordinateTransformer,
                               buffer_percent: float = 5.0) -> Tuple[float, float, float, float]:
    """
    Calculate bounding box for OSM query from image dimensions.

    Uses control points to define the area, with optional image corner inclusion
    for better coverage. This prevents issues with homography extrapolation
    far from control points.

    Args:
        image_width: Width of image in pixels
        image_height: Height of image in pixels
        transformer: CoordinateTransformer with control points
        buffer_percent: Extra buffer as percentage (default 5%)

    Returns:
        Tuple of (min_lat, min_lon, max_lat, max_lon)
    """
    # Get control point locations (these are known to be accurate)
    control_points = transformer.all_control_points
    control_lons = [cp.longitude for cp in control_points]
    control_lats = [cp.latitude for cp in control_points]

    # Start with control point bounds
    min_lon, max_lon = min(control_lons), max(control_lons)
    min_lat, max_lat = min(control_lats), max(control_lats)

    # Try to include image corners if they're reasonable
    # (i.e., not too far from control point area due to extrapolation)
    corners_pixel = [
        (0, 0),
        (image_width, 0),
        (image_width, image_height),
        (0, image_height)
    ]

    # Calculate control point extent in pixels
    control_pixels = [(cp.pixel_x, cp.pixel_y) for cp in control_points]
    cp_min_x = min(x for x, y in control_pixels)
    cp_max_x = max(x for x, y in control_pixels)
    cp_min_y = min(y for x, y in control_pixels)
    cp_max_y = max(y for x, y in control_pixels)
    cp_extent = max(cp_max_x - cp_min_x, cp_max_y - cp_min_y)

    # Only include corners that are within reasonable distance of control points
    # (within 2x the control point extent to avoid bad extrapolation)
    max_distance = cp_extent * 2.0
    cp_center_x = (cp_min_x + cp_max_x) / 2
    cp_center_y = (cp_min_y + cp_max_y) / 2

    for corner_x, corner_y in corners_pixel:
        distance = ((corner_x - cp_center_x)**2 + (corner_y - cp_center_y)**2)**0.5
        if distance <= max_distance:
            try:
                lon, lat = transformer.pixel_to_geo(corner_x, corner_y)
                # Expand bounds to include this corner
                min_lon = min(min_lon, lon)
                max_lon = max(max_lon, lon)
                min_lat = min(min_lat, lat)
                max_lat = max(max_lat, lat)
            except Exception:
                # Skip corners that fail to transform
                pass

    # Add buffer
    lon_buffer = (max_lon - min_lon) * (buffer_percent / 100.0)
    lat_buffer = (max_lat - min_lat) * (buffer_percent / 100.0)

    min_lon -= lon_buffer
    max_lon += lon_buffer
    min_lat -= lat_buffer
    max_lat += lat_buffer

    return (min_lat, min_lon, max_lat, max_lon)


def _extract_base_road_name(road_name: str) -> str:
    """
    Extract base road name from potentially split segment name.

    Examples:
        "Ekåsvägen [OSM 12345] (seg 1/2)" -> "Ekåsvägen"
        "Alingsåsvägen (seg 2/3)" -> "Alingsåsvägen"
        "Main Street" -> "Main Street"

    Args:
        road_name: Full road name potentially including OSM ID and segment info

    Returns:
        Base road name without OSM ID or segment info
    """
    # Remove " [OSM ...]" if present
    if " [OSM " in road_name:
        road_name = road_name.split(" [OSM ")[0]
    # Remove " (seg ...)" if present
    if " (seg " in road_name:
        road_name = road_name.split(" (seg ")[0]
    return road_name


def detect_road_links(roads: List[Road], polylines_dict: Dict[str, Polyline],
                      tolerance: float = 2.0) -> None:
    """
    Detect and set predecessor/successor links between roads.

    Links roads that connect end-to-end (within tolerance).
    Only links roads with the same base name (to prevent cross-road links at junctions).
    Modifies roads in place to set predecessor_id, successor_id, and contact points.

    Args:
        roads: List of Road objects
        polylines_dict: Dictionary of polyline_id -> Polyline
        tolerance: Distance tolerance in pixels for matching endpoints
    """
    import math

    # Build endpoint index: map from position to list of (road_id, is_start)
    endpoint_index = {}  # key: (rounded_x, rounded_y), value: list of (road_id, is_start, exact_point)

    # Also build a road lookup for quick access
    roads_by_id = {road.id: road for road in roads}

    for road in roads:
        if not road.centerline_id:
            continue

        centerline = polylines_dict.get(road.centerline_id)
        if not centerline or len(centerline.points) < 2:
            continue

        # Start point
        start_pt = centerline.points[0]
        # End point
        end_pt = centerline.points[-1]

        # Round to grid for approximate matching
        grid_size = tolerance
        start_key = (round(start_pt[0] / grid_size), round(start_pt[1] / grid_size))
        end_key = (round(end_pt[0] / grid_size), round(end_pt[1] / grid_size))

        # Store in index
        if start_key not in endpoint_index:
            endpoint_index[start_key] = []
        endpoint_index[start_key].append((road.id, True, start_pt))

        if end_key not in endpoint_index:
            endpoint_index[end_key] = []
        endpoint_index[end_key].append((road.id, False, end_pt))

    # Now find connections
    for road in roads:
        if not road.centerline_id:
            continue

        centerline = polylines_dict.get(road.centerline_id)
        if not centerline or len(centerline.points) < 2:
            continue

        start_pt = centerline.points[0]
        end_pt = centerline.points[-1]
        grid_size = tolerance
        base_name = _extract_base_road_name(road.name)

        # Find predecessor: look for roads that end at this road's start
        start_key = (round(start_pt[0] / grid_size), round(start_pt[1] / grid_size))
        if start_key in endpoint_index:
            for other_road_id, other_is_start, other_pt in endpoint_index[start_key]:
                # Skip self-connections
                if other_road_id == road.id:
                    continue

                # Check if roads have same base name (only link if from same "logical road")
                other_road = roads_by_id.get(other_road_id)
                if other_road:
                    other_base_name = _extract_base_road_name(other_road.name)
                    if base_name != other_base_name:
                        # Different base names = different roads = should be junction, not pred/succ
                        continue

                # Calculate exact distance
                dx = start_pt[0] - other_pt[0]
                dy = start_pt[1] - other_pt[1]
                dist = math.sqrt(dx * dx + dy * dy)

                if dist <= tolerance:
                    # Other road connects to this road's start
                    if not other_is_start:
                        # Other road's END connects to this road's START
                        # So other road is our predecessor
                        if not road.predecessor_id:  # Don't overwrite existing
                            road.predecessor_id = other_road_id
                            road.predecessor_contact = "end"
                    else:
                        # Other road's START connects to this road's START
                        # Less common, but possible (reversed connection)
                        if not road.predecessor_id:
                            road.predecessor_id = other_road_id
                            road.predecessor_contact = "start"

        # Find successor: look for roads that start at this road's end
        end_key = (round(end_pt[0] / grid_size), round(end_pt[1] / grid_size))
        if end_key in endpoint_index:
            for other_road_id, other_is_start, other_pt in endpoint_index[end_key]:
                # Skip self-connections
                if other_road_id == road.id:
                    continue

                # Check if roads have same base name (only link if from same "logical road")
                other_road = roads_by_id.get(other_road_id)
                if other_road:
                    other_base_name = _extract_base_road_name(other_road.name)
                    if base_name != other_base_name:
                        # Different base names = different roads = should be junction, not pred/succ
                        continue

                # Calculate exact distance
                dx = end_pt[0] - other_pt[0]
                dy = end_pt[1] - other_pt[1]
                dist = math.sqrt(dx * dx + dy * dy)

                if dist <= tolerance:
                    # Other road connects to this road's end
                    if other_is_start:
                        # Other road's START connects to this road's END
                        # So other road is our successor
                        if not road.successor_id:  # Don't overwrite existing
                            road.successor_id = other_road_id
                            road.successor_contact = "start"
                    else:
                        # Other road's END connects to this road's END
                        # Less common, but possible (reversed connection)
                        if not road.successor_id:
                            road.successor_id = other_road_id
                            road.successor_contact = "end"


def _is_way_endpoint(osm_way, node_id: int) -> bool:
    """Check if node_id is at start or end of an OSM way."""
    return osm_way.nodes[0] == node_id or osm_way.nodes[-1] == node_id


def detect_junction_node_ids_from_osm(osm_data, road_osm_way_map: Dict[str, int]) -> Set[int]:
    """Detect OSM node IDs that represent junctions (for road splitting).

    A junction node is where 2+ VEHICULAR roads share a node AND either:
    - The roads have different names, OR
    - The shared node is a mid-node of at least one road (T-junction with same name)
    """
    # Build reverse mapping: node_id -> list of (osm_way_id, road_name, is_vehicular)
    node_to_roads: Dict[int, list] = defaultdict(list)

    for road_id, osm_way_id in road_osm_way_map.items():
        osm_way = osm_data.ways.get(osm_way_id)
        if not osm_way or not osm_way.nodes:
            continue

        road_name = osm_way.tags.get('name', f'Way {osm_way_id}')
        highway = osm_way.tags.get('highway', '')
        is_vehicular = True
        if highway in ('cycleway', 'footway'):
            is_vehicular = False
        elif highway == 'path':
            if osm_way.tags.get('bicycle') == 'designated' or osm_way.tags.get('foot') == 'designated':
                is_vehicular = False

        for node_id in osm_way.nodes:
            node_to_roads[node_id].append((osm_way_id, road_name, is_vehicular))

    junction_node_ids = set()
    for node_id, road_list in node_to_roads.items():
        if len(road_list) < 2:
            continue

        vehicular_roads = [(osm_way_id, road_name) for osm_way_id, road_name, is_vehicular
                          in road_list if is_vehicular]
        if len(vehicular_roads) < 2:
            continue

        # Different OSM way IDs that share this node
        unique_way_ids = set(wid for wid, _ in vehicular_roads)
        if len(unique_way_ids) < 2:
            continue

        road_names = set(rn for _, rn in vehicular_roads)
        if len(road_names) >= 2:
            # Different names — always a junction
            junction_node_ids.add(node_id)
        else:
            # Same name — only a junction if this is a T-junction
            # (node is a mid-node of at least one way, not endpoint-to-endpoint)
            is_t_junction = False
            for osm_way_id, _ in vehicular_roads:
                osm_way = osm_data.ways.get(osm_way_id)
                if osm_way and not _is_way_endpoint(osm_way, node_id):
                    is_t_junction = True
                    break
            if is_t_junction:
                junction_node_ids.add(node_id)

    return junction_node_ids


def detect_junctions_from_osm(osm_data, road_osm_way_map: Dict[str, int],
                              transformer: CoordinateTransformer,
                              roads: List[Road] = None,
                              polylines_dict: Dict[str, Polyline] = None) -> List[Junction]:
    """
    Detect junctions based on shared OSM node IDs.

    A junction is where 2+ VEHICULAR roads with DIFFERENT names share a node.
    If fewer than 2 vehicular roads meet (e.g., path + road), no road junction is created
    (path crossings are handled by detect_path_crossings_from_osm instead).

    Args:
        osm_data: Parsed OSM data
        road_osm_way_map: Dictionary mapping Road.id -> OSM way ID
        transformer: Coordinate transformer for converting to pixels
        roads: List of Road objects (for filtering by endpoint proximity)
        polylines_dict: Dictionary mapping polyline ID -> Polyline (for endpoint filtering)

    Returns:
        List of detected Junction objects
    """
    from collections import defaultdict

    # Build reverse mapping: node_id -> list of (road_id, osm_way_id, road_name, is_vehicular)
    node_to_roads = defaultdict(list)

    for road_id, osm_way_id in road_osm_way_map.items():
        osm_way = osm_data.ways.get(osm_way_id)
        if not osm_way or not osm_way.nodes:
            continue

        # Get road name from OSM tags (use way ID as fallback)
        road_name = osm_way.tags.get('name', f'Way {osm_way_id}')

        # Determine if this is a vehicular road (not a path)
        highway = osm_way.tags.get('highway', '')
        is_vehicular = True

        # Paths are non-vehicular
        if highway in ('cycleway', 'footway'):
            is_vehicular = False
        elif highway == 'path':
            if osm_way.tags.get('bicycle') == 'designated' or osm_way.tags.get('foot') == 'designated':
                is_vehicular = False

        # Check ALL nodes in the way, not just endpoints
        # Roads can intersect at any point along their length
        for node_id in osm_way.nodes:
            node_to_roads[node_id].append((road_id, osm_way_id, road_name, is_vehicular))

    # Create junctions where 2+ vehicular roads meet
    junctions = []
    for node_id, road_list in node_to_roads.items():
        if len(road_list) < 2:
            continue

        vehicular_roads = [(road_id, osm_way_id, road_name) for road_id, osm_way_id, road_name, is_vehicular
                          in road_list if is_vehicular]
        if len(vehicular_roads) < 2:
            continue

        # Need 2+ different OSM ways
        unique_way_ids = set(wid for _, wid, _ in vehicular_roads)
        if len(unique_way_ids) < 2:
            continue

        road_names = set(road_name for _, _, road_name in vehicular_roads)
        if len(road_names) < 2:
            # Same name — only a junction if T-junction (mid-node of at least one way)
            is_t_junction = False
            for _, osm_way_id, _ in vehicular_roads:
                osm_way = osm_data.ways.get(osm_way_id)
                if osm_way and not _is_way_endpoint(osm_way, node_id):
                    is_t_junction = True
                    break
            if not is_t_junction:
                continue

        # Get node coordinates
        osm_node = osm_data.nodes.get(node_id)
        if not osm_node:
            continue

        # Convert to pixel coordinates and store geo position
        px, py = transformer.geo_to_pixel(osm_node.lon, osm_node.lat)
        geo_center_point = (osm_node.lon, osm_node.lat)  # Store as source of truth

        # Extract unique road IDs (only from vehicular roads)
        connected_road_ids = list(set(road_id for road_id, _, _ in vehicular_roads))

        # Filter to only include roads whose endpoints are actually AT this junction
        # This prevents including all segments of a split road when only one segment touches the junction
        if roads is not None and polylines_dict is not None:
            # Build roads_dict for quick lookup
            roads_dict = {road.id: road for road in roads}

            filtered_road_ids = []
            for road_id in connected_road_ids:
                road = roads_dict.get(road_id)
                if not road or not road.centerline_id:
                    continue

                centerline = polylines_dict.get(road.centerline_id)
                if not centerline or len(centerline.points) < 2:
                    continue

                # Check if start or end point is within tolerance of junction center
                start_dist = math.sqrt(
                    (centerline.points[0][0] - px)**2 +
                    (centerline.points[0][1] - py)**2
                )
                end_dist = math.sqrt(
                    (centerline.points[-1][0] - px)**2 +
                    (centerline.points[-1][1] - py)**2
                )

                # Include road if either endpoint is within 15 pixels of junction
                if start_dist < 15.0 or end_dist < 15.0:
                    filtered_road_ids.append(road_id)

            connected_road_ids = filtered_road_ids

        # Create junction with geo coords
        junction = Junction(
            name=f"Junction {len(junctions) + 1}",
            center_point=(px, py),
            geo_center_point=geo_center_point,  # Store geo coords as source of truth
            connected_road_ids=connected_road_ids
        )
        junctions.append(junction)

    return junctions


def detect_path_crossings_from_osm(osm_data, road_osm_way_map: Dict[str, int],
                                    transformer: CoordinateTransformer) -> List[Junction]:
    """
    Detect virtual junctions where paths cross roads or other paths.

    Creates junction_type="virtual" for path crossings, as per OpenDRIVE spec
    for bicycle/pedestrian crossings.

    Args:
        osm_data: Parsed OSM data
        road_osm_way_map: Dictionary mapping Road.id -> OSM way ID
        transformer: Coordinate transformer for converting to pixels

    Returns:
        List of virtual Junction objects for path crossings
    """
    from collections import defaultdict

    # Build mapping: node_id -> list of (road_id, osm_way_id, is_path, highway_type)
    node_to_ways = defaultdict(list)

    for road_id, osm_way_id in road_osm_way_map.items():
        osm_way = osm_data.ways.get(osm_way_id)
        if not osm_way or not osm_way.nodes:
            continue

        highway = osm_way.tags.get('highway', '')

        # Determine if this is a path (cycleway, footway, designated path)
        is_path = False
        if highway in ('cycleway', 'footway'):
            is_path = True
        elif highway == 'path':
            if osm_way.tags.get('bicycle') == 'designated' or osm_way.tags.get('foot') == 'designated':
                is_path = True

        # Record all nodes
        for node_id in osm_way.nodes:
            node_to_ways[node_id].append((road_id, osm_way_id, is_path, highway))

    # Create virtual junctions where paths cross roads/paths
    junctions = []
    for node_id, way_list in node_to_ways.items():
        if len(way_list) < 2:
            continue  # No crossing

        # Check if at least one path and one road/path meet here
        has_path = any(is_path for _, _, is_path, _ in way_list)
        has_road_or_path = len(way_list) >= 2

        if not (has_path and has_road_or_path):
            continue  # Not a path crossing

        # Get node coordinates
        osm_node = osm_data.nodes.get(node_id)
        if not osm_node:
            continue

        # Convert to pixel coordinates and store geo position
        px, py = transformer.geo_to_pixel(osm_node.lon, osm_node.lat)
        geo_center_point = (osm_node.lon, osm_node.lat)  # Store as source of truth

        # Extract unique road IDs
        connected_road_ids = list(set(road_id for road_id, _, _, _ in way_list))

        # Determine crossing type from OSM node tags
        crossing_type = osm_node.tags.get('highway', '')
        name_suffix = ""
        if crossing_type == 'crossing':
            name_suffix = " (Crossing)"

        # Create virtual junction for this path crossing with geo coords
        junction = Junction(
            name=f"Path Crossing {len(junctions) + 1}{name_suffix}",
            center_point=(px, py),
            geo_center_point=geo_center_point,  # Store geo coords as source of truth
            connected_road_ids=connected_road_ids,
            junction_type="virtual"  # Virtual junction for path crossings
        )
        junctions.append(junction)

    return junctions


def detect_junctions(roads: List[Road], polylines_dict: Dict[str, Polyline],
                     tolerance: float = 2.0) -> List[Junction]:
    """
    DEPRECATED: Geometric junction detection (kept for non-OSM imports).

    Detect junctions where 2+ roads meet at different angles.

    Creates junctions for:
    - Any point where 3+ roads meet (complex intersections)
    - Points where 2 roads meet at significant angles (T-junctions, crossroads)

    Filters out:
    - Way continuations where roads meet nearly parallel (< 30° difference)

    Args:
        roads: List of Road objects
        polylines_dict: Dictionary of polyline_id -> Polyline
        tolerance: Distance tolerance in pixels for matching endpoints

    Returns:
        List of detected Junction objects
    """
    import math

    def calculate_angle(pt1: Tuple[float, float], pt2: Tuple[float, float]) -> float:
        """Calculate angle in degrees from pt1 to pt2."""
        dx = pt2[0] - pt1[0]
        dy = pt2[1] - pt1[1]
        return math.degrees(math.atan2(dy, dx))

    def angle_difference(angle1: float, angle2: float) -> float:
        """Calculate smallest difference between two angles (0-180 degrees)."""
        diff = abs(angle1 - angle2) % 360
        return min(diff, 360 - diff)

    def get_road_direction(centerline: Polyline, is_start: bool) -> float:
        """Get direction angle of road at start or end point."""
        if is_start:
            # Direction from first point to second point
            if len(centerline.points) >= 2:
                return calculate_angle(centerline.points[0], centerline.points[1])
        else:
            # Direction from second-to-last to last point
            if len(centerline.points) >= 2:
                return calculate_angle(centerline.points[-2], centerline.points[-1])
        return 0.0

    # Collect all road endpoints
    # List of (road_id, is_start, point, centerline)
    all_endpoints = []

    for road in roads:
        if not road.centerline_id:
            continue

        centerline = polylines_dict.get(road.centerline_id)
        if not centerline or len(centerline.points) < 2:
            continue

        # Start point
        start_pt = centerline.points[0]
        all_endpoints.append((road.id, True, start_pt, centerline))

        # End point
        end_pt = centerline.points[-1]
        all_endpoints.append((road.id, False, end_pt, centerline))

    # Group endpoints by proximity using distance-based clustering
    # This avoids issues with grid-based rounding
    endpoint_clusters = []
    used = set()

    for i, (road_id, is_start, pt, centerline) in enumerate(all_endpoints):
        if i in used:
            continue

        # Start new cluster
        cluster = [(road_id, is_start, pt, centerline)]
        used.add(i)

        # Find all other endpoints within tolerance
        for j, (other_road_id, other_is_start, other_pt, other_centerline) in enumerate(all_endpoints):
            if j in used:
                continue

            # Calculate distance
            dx = pt[0] - other_pt[0]
            dy = pt[1] - other_pt[1]
            dist = math.sqrt(dx * dx + dy * dy)

            if dist <= tolerance:
                cluster.append((other_road_id, other_is_start, other_pt, other_centerline))
                used.add(j)

        endpoint_clusters.append(cluster)

    # Create junctions where roads meet
    junctions = []
    for road_endpoints in endpoint_clusters:
        num_roads = len(road_endpoints)

        # Skip single road endpoints (dead ends)
        if num_roads < 2:
            continue

        # For 3+ roads, always create junction (complex intersection)
        if num_roads >= 3:
            # Calculate average position
            avg_x = sum(pt[0] for _, _, pt, _ in road_endpoints) / len(road_endpoints)
            avg_y = sum(pt[1] for _, _, pt, _ in road_endpoints) / len(road_endpoints)

            # Get unique road IDs
            road_ids = list(set(road_id for road_id, _, _, _ in road_endpoints))

            junction = Junction(
                name=f"Junction {len(junctions) + 1}",
                center_point=(avg_x, avg_y),
                connected_road_ids=road_ids
            )
            junctions.append(junction)

        # For exactly 2 roads, check if they meet at significant angle
        elif num_roads == 2:
            road1_id, is_start1, pt1, centerline1 = road_endpoints[0]
            road2_id, is_start2, pt2, centerline2 = road_endpoints[1]

            # Get direction angles
            angle1 = get_road_direction(centerline1, is_start1)
            angle2 = get_road_direction(centerline2, is_start2)

            # Calculate angle difference
            ang_diff = angle_difference(angle1, angle2)

            # Create junction if roads meet at significant angle (>30°)
            # This filters out way continuations where roads are nearly parallel
            if ang_diff > 30:
                # Calculate average position
                avg_x = (pt1[0] + pt2[0]) / 2
                avg_y = (pt1[1] + pt2[1]) / 2

                junction = Junction(
                    name=f"Junction {len(junctions) + 1}",
                    center_point=(avg_x, avg_y),
                    connected_road_ids=[road1_id, road2_id]
                )
                junctions.append(junction)

    return junctions


def split_road_at_junctions(road: Road, centerline: Polyline,
                            junctions: List[Junction],
                            tolerance: float = 2.0) -> None:
    """
    Split a road's lane sections at junction points.

    Modifies the road's lane_sections in place.

    Args:
        road: Road object to modify
        centerline: Road's centerline polyline
        junctions: List of junctions to check
        tolerance: Distance tolerance in pixels
    """
    if len(centerline.points) < 2:
        return

    # Find junction points along this road's centerline
    junction_indices = []

    for junction in junctions:
        if road.id not in junction.connected_road_ids:
            continue

        center = junction.center_point
        if not center:
            continue

        # Find closest point on centerline
        min_dist = float('inf')
        closest_idx = -1

        for idx, pt in enumerate(centerline.points):
            dist = ((pt[0] - center[0])**2 + (pt[1] - center[1])**2)**0.5
            if dist < min_dist:
                min_dist = dist
                closest_idx = idx

        # If within tolerance and not at endpoints
        if min_dist < tolerance and 0 < closest_idx < len(centerline.points) - 1:
            junction_indices.append(closest_idx)

    # Sort junction indices
    junction_indices.sort()

    if not junction_indices:
        # No junctions to split at
        return

    # If road has no sections yet, create one spanning whole road
    if not road.lane_sections:
        return

    # Calculate s-coordinates (cumulative distances) for all points
    s_coords = road.calculate_centerline_s_coordinates(centerline.points)

    # Split sections at junction points
    # This is complex - for now, we'll create new sections at junction boundaries
    # Each junction point becomes a section boundary

    # Get the first section as template for lane configuration
    template_section = road.lane_sections[0]

    # Create new sections
    new_sections = []
    prev_idx = 0
    section_num = 1

    for junc_idx in junction_indices:
        # Create section from prev_idx to junc_idx
        # Use actual s-coordinates (cumulative distances), not point indices
        section = LaneSection(
            section_number=section_num,
            s_start=s_coords[prev_idx],
            s_end=s_coords[junc_idx],
            end_point_index=junc_idx
        )

        # Copy lanes from template
        for lane in template_section.lanes:
            new_lane = Lane(
                id=lane.id,
                lane_type=lane.lane_type,
                road_mark_type=lane.road_mark_type,
                width=lane.width
            )
            section.lanes.append(new_lane)

        new_sections.append(section)
        section_num += 1
        prev_idx = junc_idx

    # Last section from last junction to end
    section = LaneSection(
        section_number=section_num,
        s_start=s_coords[prev_idx],
        s_end=s_coords[-1],
        end_point_index=None  # Last section extends to end
    )
    for lane in template_section.lanes:
        new_lane = Lane(
            id=lane.id,
            lane_type=lane.lane_type,
            road_mark_type=lane.road_mark_type,
            width=lane.width
        )
        section.lanes.append(new_lane)
    new_sections.append(section)

    # Replace sections
    road.lane_sections = new_sections


def _recover_osm_node_ids(
    centerline: Polyline,
    osm_way_id: int,
    osm_data,
    transformer: 'CoordinateTransformer',
    tolerance_deg: float = 0.0001,
) -> Optional[List[Optional[int]]]:
    """Recover osm_node_ids for a polyline by matching geo_points to OSM node positions.

    Used when loading from .orbit files that lack osm_node_ids.
    Falls back to pixel matching via transformer if geo_points unavailable.
    Returns None if matching fails.
    """
    osm_way = osm_data.ways.get(osm_way_id)
    if not osm_way or not osm_way.nodes:
        return None

    # Build OSM node geo positions: (node_id, lon, lat)
    osm_geo = []
    for node_id in osm_way.nodes:
        node = osm_data.nodes.get(node_id)
        if not node:
            return None
        osm_geo.append((node_id, node.lon, node.lat))

    # Prefer geo_points matching (more accurate, no transformer needed)
    if centerline.geo_points and len(centerline.geo_points) >= 2:
        return _match_geo_subsequence(centerline.geo_points, osm_geo, tolerance_deg)

    # Fallback: pixel matching via transformer
    if not transformer:
        return None
    try:
        osm_pixels = []
        for nid, lon, lat in osm_geo:
            px, py = transformer.geo_to_pixel(lon, lat)
            osm_pixels.append((nid, px, py))
        return _match_pixel_subsequence(centerline.points, osm_pixels, tolerance_px=5.0)
    except (NotImplementedError, Exception):
        return None


def _match_geo_subsequence(
    geo_points: list,
    osm_geo: list,
    tolerance_deg: float,
) -> Optional[List[Optional[int]]]:
    """Match polyline geo_points to a contiguous subsequence of OSM node geo positions.

    Endpoints may have been shifted by junction offset shortening, so we match
    interior points strictly and allow a larger tolerance on the first/last point.
    """
    n_pts = len(geo_points)
    n_osm = len(osm_geo)
    if n_pts < 2 or n_pts > n_osm:
        return None

    # Match using interior points (skip first and last which may be offset-shortened)
    # Find the best alignment by matching geo_points[1] to each OSM node
    endpoint_tolerance = tolerance_deg * 10  # ~100m for shortened endpoints

    for start in range(n_osm - n_pts + 1):
        node_ids = []
        match = True
        for i in range(n_pts):
            nid, lon, lat = osm_geo[start + i]
            glon, glat = geo_points[i]
            # Use relaxed tolerance for endpoints (may be offset-shortened)
            tol = endpoint_tolerance if (i == 0 or i == n_pts - 1) else tolerance_deg
            if abs(glon - lon) > tol or abs(glat - lat) > tol:
                match = False
                break
            node_ids.append(nid)
        if match:
            return node_ids
    return None


def _match_pixel_subsequence(
    pts: list,
    osm_pixels: list,
    tolerance_px: float,
) -> Optional[List[Optional[int]]]:
    """Match polyline points to a contiguous subsequence of OSM node pixel positions."""
    n_pts = len(pts)
    n_osm = len(osm_pixels)
    if n_pts > n_osm:
        return None

    for start in range(n_osm - n_pts + 1):
        node_ids = []
        match = True
        for i in range(n_pts):
            nid, nx, ny = osm_pixels[start + i]
            px, py = pts[i]
            if math.sqrt((px - nx)**2 + (py - ny)**2) > tolerance_px:
                match = False
                break
            node_ids.append(nid)
        if match:
            return node_ids
    return None


def _set_road_osm_mapping(road_to_osm_way: Optional[Dict[str, int]], road_id: str, osm_way_id: Optional[int]) -> None:
    """Set road->OSM-way mapping when mapping is enabled and ID is available."""
    if road_to_osm_way is not None and osm_way_id is not None:
        road_to_osm_way[road_id] = osm_way_id


def _copy_lane_sections_for_segment(source_road: Road, segment_points: list) -> List[LaneSection]:
    """Copy first lane section layout from source road to a split segment."""
    if not source_road.lane_sections:
        return []

    template_section = source_road.lane_sections[0]
    new_section = LaneSection(
        section_number=1,
        s_start=0.0,
        s_end=len(segment_points) - 1.0,
        end_point_index=len(segment_points) - 1,
    )
    for lane in template_section.lanes:
        new_section.lanes.append(
            Lane(
                id=lane.id,
                lane_type=lane.lane_type,
                road_mark_type=lane.road_mark_type,
                width=lane.width,
            )
        )
    return [new_section]


def _create_split_segment_entities(
    source_road: Road,
    centerline: Polyline,
    start_idx: int,
    end_idx: int,
    segment_index: int,
    total_segments: int,
    osm_way_id: Optional[int],
    next_poly_id: int,
    next_road_id: int,
) -> Tuple[Road, Polyline, int, int]:
    """Create road/polyline entities for one split segment."""
    segment_points = centerline.points[start_idx:end_idx + 1]
    segment_node_ids = centerline.osm_node_ids[start_idx:end_idx + 1]
    segment_geo_points = None
    if centerline.geo_points:
        segment_geo_points = centerline.geo_points[start_idx:end_idx + 1]

    new_polyline = Polyline(
        points=segment_points,
        geo_points=segment_geo_points,
        line_type=LineType.CENTERLINE,
        road_mark_type=centerline.road_mark_type,
        osm_node_ids=segment_node_ids,
        color=centerline.color,
    )
    new_polyline.id = str(next_poly_id)
    next_poly_id += 1

    if osm_way_id:
        segment_name = f"{source_road.name} [OSM {osm_way_id}] (seg {segment_index}/{total_segments})"
    else:
        segment_name = f"{source_road.name} (seg {segment_index}/{total_segments})"

    new_road = Road(
        name=segment_name,
        road_type=source_road.road_type,
        centerline_id=new_polyline.id,
        speed_limit=source_road.speed_limit,
    )
    new_road.id = str(next_road_id)
    next_road_id += 1
    new_road.add_polyline(new_polyline.id)
    new_road.lane_info = source_road.lane_info
    new_road.lane_sections = _copy_lane_sections_for_segment(source_road, segment_points)

    return new_road, new_polyline, next_poly_id, next_road_id


def split_roads_at_junction_nodes(
    roads: List[Road],
    polylines_dict: Dict[str, Polyline],
    junction_node_ids: Set[int],
    road_to_osm_way: Dict[str, int] = None,
    verbose: bool = False,
    osm_data=None,
    transformer: 'CoordinateTransformer' = None,
) -> Tuple[List[Road], Dict[str, Polyline], Dict[str, int]]:
    """Split roads at junction nodes, creating separate road segments.

    Args:
        roads: List of roads to potentially split
        polylines_dict: Dictionary of polyline_id -> Polyline
        junction_node_ids: Set of OSM node IDs that are junctions
        road_to_osm_way: Optional mapping Road.id -> OSM way ID
        verbose: If True, print debug information
        osm_data: Optional OSM data for recovering missing osm_node_ids
        transformer: Optional transformer for geo->pixel conversion (for recovery)

    Returns:
        Tuple of (new_roads_list, new_polylines_dict, new_road_to_osm_way)
    """
    new_roads = []
    new_polylines = {}
    new_road_to_osm_way = {} if road_to_osm_way is not None else None

    # Determine next available IDs for new entities created during splitting.
    # Input roads/polylines already have project-assigned IDs; new segments
    # need unique IDs so dict keys don't collide and successor/predecessor
    # links work correctly.
    _next_poly_id = 1 + max(
        (int(p.id) for p in polylines_dict.values() if p.id and p.id.isdigit()),
        default=0
    )
    _next_road_id = 1 + max(
        (int(r.id) for r in roads if r.id and r.id.isdigit()),
        default=0
    )

    split_count = 0
    segment_count = 0

    for road in roads:
        centerline = polylines_dict.get(road.centerline_id)
        osm_way_id = road_to_osm_way.get(road.id) if road_to_osm_way else None

        if not centerline:
            new_roads.append(road)
            _set_road_osm_mapping(new_road_to_osm_way, road.id, osm_way_id)
            continue

        # Recover osm_node_ids from OSM data if missing (e.g., loaded from .orbit file)
        if not centerline.osm_node_ids and osm_way_id and osm_data and transformer:
            centerline.osm_node_ids = _recover_osm_node_ids(
                centerline, osm_way_id, osm_data, transformer)
            if centerline.osm_node_ids and verbose:
                logger.debug("  Recovered osm_node_ids for road '%s' from OSM way %d",
                             road.name, osm_way_id)

        if not centerline.osm_node_ids:
            new_roads.append(road)
            new_polylines[centerline.id] = centerline
            _set_road_osm_mapping(new_road_to_osm_way, road.id, osm_way_id)
            continue

        # Find junction points in this road (excluding endpoints)
        split_indices = []
        for i, node_id in enumerate(centerline.osm_node_ids):
            if node_id in junction_node_ids and 0 < i < len(centerline.points) - 1:
                # Junction in middle of road, need to split here
                split_indices.append(i)

        if not split_indices:
            # No splits needed - keep road as-is
            new_roads.append(road)
            new_polylines[centerline.id] = centerline
            _set_road_osm_mapping(new_road_to_osm_way, road.id, osm_way_id)
            continue

        # Road needs splitting!
        split_count += 1
        if verbose:
            logger.debug("  Splitting road '%s' at %d junction(s)", road.name, len(split_indices))

        # Create segments: [0, split1], [split1, split2], ..., [splitN, end]
        split_indices = [0] + split_indices + [len(centerline.points) - 1]

        # Track segments for this road to link them with predecessor/successor
        road_segments = []

        for seg_idx in range(len(split_indices) - 1):
            start_idx = split_indices[seg_idx]
            end_idx = split_indices[seg_idx + 1]
            new_road, new_polyline, _next_poly_id, _next_road_id = _create_split_segment_entities(
                source_road=road,
                centerline=centerline,
                start_idx=start_idx,
                end_idx=end_idx,
                segment_index=seg_idx + 1,
                total_segments=len(split_indices) - 1,
                osm_way_id=osm_way_id,
                next_poly_id=_next_poly_id,
                next_road_id=_next_road_id,
            )
            segment_node_ids = centerline.osm_node_ids[start_idx:end_idx + 1]

            road_segments.append(new_road)
            new_polylines[new_polyline.id] = new_polyline
            segment_count += 1

            # Preserve OSM way ID mapping for this segment
            _set_road_osm_mapping(new_road_to_osm_way, new_road.id, osm_way_id)

            if verbose:
                logger.debug("    Segment %d: %d points, OSM nodes %s -> %s",
                             seg_idx + 1, len(new_polyline.points),
                             segment_node_ids[0], segment_node_ids[-1])

        # Link consecutive segments with predecessor/successor relationships
        for i in range(len(road_segments) - 1):
            current_segment = road_segments[i]
            next_segment = road_segments[i + 1]

            current_segment.successor_id = next_segment.id
            next_segment.predecessor_id = current_segment.id

        # Add all segments to the output list
        new_roads.extend(road_segments)

    if verbose and split_count > 0:
        logger.debug("Split %d road(s) into %d segment(s)", split_count, segment_count)

    return new_roads, new_polylines, new_road_to_osm_way


def _build_road_junction_endpoint_map(
    junctions: List[Junction],
    roads_dict: Dict[str, Road],
    polylines_dict: Dict[str, Polyline],
    endpoint_radius_px: float = 15.0,
) -> Dict[str, List[Tuple[Junction, str]]]:
    """Build mapping road_id -> [(junction, endpoint)] where endpoint is start/end."""
    road_junctions: Dict[str, List[Tuple[Junction, str]]] = defaultdict(list)
    for junction in junctions:
        if junction.junction_type == "virtual" or not junction.center_point:
            continue

        jx, jy = junction.center_point
        for road_id in junction.connected_road_ids:
            road = roads_dict.get(road_id)
            if not road or not road.centerline_id:
                continue
            centerline = polylines_dict.get(road.centerline_id)
            if not centerline or len(centerline.points) < 2:
                continue

            points = centerline.points
            start_dist = math.sqrt((points[0][0] - jx) ** 2 + (points[0][1] - jy) ** 2)
            end_dist = math.sqrt((points[-1][0] - jx) ** 2 + (points[-1][1] - jy) ** 2)
            if start_dist < endpoint_radius_px:
                road_junctions[road_id].append((junction, "start"))
            if end_dist < endpoint_radius_px:
                road_junctions[road_id].append((junction, "end"))

    return road_junctions


def compute_adaptive_offsets(
    junctions: List['Junction'],
    roads: List[Road],
    polylines_dict: Dict[str, 'Polyline'],
    base_offset: float,
    transformer: 'CoordinateTransformer',
) -> Tuple[Dict[Tuple[str, str], float], List['Junction'], Set[str]]:
    """Compute per-road offset distances and merge very close junctions.

    Returns (per_road_offsets, merged_junctions, merged_source_ids) where:
    - per_road_offsets maps (road_id, "start"|"end") -> offset in meters
    - merged_junctions is a list of new Junction objects replacing close pairs
    - merged_source_ids is the set of junction IDs that were replaced by merges
    """
    scale_x, scale_y = transformer.get_scale_factor()
    avg_scale = (scale_x + scale_y) / 2.0

    roads_dict = {road.id: road for road in roads}

    road_junctions = _build_road_junction_endpoint_map(junctions, roads_dict, polylines_dict)

    # Detect close junction pairs sharing a road
    # Build pairwise distances between junctions connected by same road
    junction_pair_roads: Dict[Tuple[str, str], List[Tuple[str, float]]] = defaultdict(list)
    for road_id, jlist in road_junctions.items():
        if len(jlist) == 2:
            j1, end1 = jlist[0]
            j2, end2 = jlist[1]
            # Compute road length between these two junctions
            road = roads_dict[road_id]
            centerline = polylines_dict[road.centerline_id]
            road_length_px = calculate_path_length(centerline.points)
            road_length_m = road_length_px * avg_scale
            key = tuple(sorted([j1.id, j2.id]))
            junction_pair_roads[key].append((road_id, road_length_m))

    # Phase 1: Merge very close junctions (within 1x base_offset)
    merged_junctions: List[Junction] = []
    merged_junction_ids: Set[str] = set()

    for (j1_id, j2_id), road_lengths in junction_pair_roads.items():
        min_road_length = min(length for _, length in road_lengths)
        if min_road_length >= base_offset:
            continue  # Not close enough to merge

        # Find the actual junction objects
        j1 = next((j for j in junctions if j.id == j1_id), None)
        j2 = next((j for j in junctions if j.id == j2_id), None)
        if not j1 or not j2:
            continue
        if j1.id in merged_junction_ids or j2.id in merged_junction_ids:
            continue  # Already merged

        # Merge: combine connected roads, use midpoint as center
        merged_road_ids = list(set(j1.connected_road_ids + j2.connected_road_ids))
        cx = (j1.center_point[0] + j2.center_point[0]) / 2
        cy = (j1.center_point[1] + j2.center_point[1]) / 2

        geo_center = None
        if j1.geo_center_point and j2.geo_center_point:
            geo_center = (
                (j1.geo_center_point[0] + j2.geo_center_point[0]) / 2,
                (j1.geo_center_point[1] + j2.geo_center_point[1]) / 2,
            )

        merged = Junction(
            name=f"{j1.name}+{j2.name}",
            center_point=(cx, cy),
            geo_center_point=geo_center,
            connected_road_ids=merged_road_ids,
        )
        merged_junctions.append(merged)
        merged_junction_ids.add(j1.id)
        merged_junction_ids.add(j2.id)

        # Snap road endpoints that were at either original center to the new center
        for junc in (j1, j2):
            ojx, ojy = junc.center_point
            for road_id in junc.connected_road_ids:
                road = roads_dict.get(road_id)
                if not road or not road.centerline_id:
                    continue
                centerline = polylines_dict.get(road.centerline_id)
                if not centerline or len(centerline.points) < 2:
                    continue
                pts = list(centerline.points)
                sd = math.sqrt((pts[0][0] - ojx)**2 + (pts[0][1] - ojy)**2)
                ed = math.sqrt((pts[-1][0] - ojx)**2 + (pts[-1][1] - ojy)**2)
                changed = False
                if sd < 15.0:
                    pts[0] = (cx, cy)
                    changed = True
                if ed < 15.0:
                    pts[-1] = (cx, cy)
                    changed = True
                if changed:
                    centerline.points = pts

        logger.debug("Merged close junctions '%s' and '%s' (%.1fm apart)",
                      j1.name, j2.name, min_road_length)

    # Phase 2: Compute per-road offsets
    per_road_offsets: Dict[Tuple[str, str], float] = {}

    # Rebuild road_junctions considering merges
    active_junctions = [j for j in junctions if j.id not in merged_junction_ids] + merged_junctions

    road_junctions_active = _build_road_junction_endpoint_map(active_junctions, roads_dict, polylines_dict)

    for road_id, jlist in road_junctions_active.items():
        road = roads_dict.get(road_id)
        if not road or not road.centerline_id:
            continue
        centerline = polylines_dict.get(road.centerline_id)
        if not centerline or len(centerline.points) < 2:
            continue
        road_length_m = calculate_path_length(centerline.points) * avg_scale

        if len(jlist) == 2:
            # Road connects two junctions — cap each end at 40% of road length
            max_offset = road_length_m * 0.4
            # Check if these two junctions are moderately close (1x–2x base_offset)
            inter_dist = road_length_m
            if inter_dist < 2 * base_offset:
                # Reduce offset to half the inter-junction distance minus 1m margin
                reduced = (inter_dist / 2) - 1.0
                max_offset = max(1.0, min(max_offset, reduced))

            for junction, end in jlist:
                offset = min(base_offset, max_offset)
                per_road_offsets[(road_id, end)] = offset
        else:
            # Road at only one junction — use base offset, cap at 40% of road length
            for junction, end in jlist:
                offset = min(base_offset, road_length_m * 0.4)
                per_road_offsets[(road_id, end)] = offset

    return per_road_offsets, merged_junctions, merged_junction_ids


def offset_road_endpoints_from_junctions(
    roads: List[Road],
    polylines_dict: Dict[str, Polyline],
    junctions: List['Junction'],
    offset_distance_meters: float = 8.0,
    transformer: 'CoordinateTransformer' = None,
    minimum_length_meters: float = 1.0,
    verbose: bool = False,
    per_road_offsets: Optional[Dict[Tuple[str, str], float]] = None,
) -> None:
    """Offset road endpoints away from junction centers for connecting roads.

    Args:
        roads: List of roads
        polylines_dict: Dictionary of polyline_id -> Polyline
        junctions: List of junctions
        offset_distance_meters: Uniform offset in meters (default: 8.0m)
        transformer: CoordinateTransformer to convert meters to pixels (required)
        minimum_length_meters: Minimum road length to preserve (default: 1.0m)
        verbose: If True, print debug information
        per_road_offsets: Optional dict mapping (road_id, "start"|"end") -> offset in meters.
            When provided, overrides offset_distance_meters for specific road endpoints.
    """
    if transformer is None:
        raise ValueError("transformer is required to convert offset distance from meters to pixels")

    # Get scale factor (meters per pixel)
    scale_x, scale_y = transformer.get_scale_factor()
    avg_scale = (scale_x + scale_y) / 2.0

    # Convert offset and minimum length from meters to pixels
    offset_distance_pixels = offset_distance_meters / avg_scale
    minimum_length_pixels = minimum_length_meters / avg_scale

    if verbose:
        logger.debug("Offsetting junction endpoints by %sm (%.1f pixels)",
                     offset_distance_meters, offset_distance_pixels)

    modified_count = 0

    for junction in junctions:
        if not junction.center_point:
            continue
        if junction.junction_type == "virtual":
            if verbose:
                logger.debug("  Skipping virtual junction '%s' (path crossing)", junction.name)
            continue

        jx, jy = junction.center_point

        for road_id in junction.connected_road_ids:
            road = next((r for r in roads if r.id == road_id), None)
            if not road or not road.centerline_id:
                continue
            centerline = polylines_dict.get(road.centerline_id)
            if not centerline or len(centerline.points) < 2:
                continue

            points = list(centerline.points)
            modified = False
            start_offset_m = 0.0
            end_offset_m = 0.0

            # Check start point
            start_dist = math.sqrt((points[0][0] - jx)**2 + (points[0][1] - jy)**2)
            if start_dist < 15.0:
                new_points, offset_m = _apply_endpoint_offset(
                    points, road, road_id, "start", offset_distance_pixels,
                    minimum_length_pixels, avg_scale, minimum_length_meters,
                    per_road_offsets, verbose
                )
                if new_points is not None:
                    points = new_points
                    start_offset_m = offset_m
                    modified = True

            # Check end point
            end_dist = math.sqrt((points[-1][0] - jx)**2 + (points[-1][1] - jy)**2)
            if end_dist < 15.0:
                new_points, offset_m = _apply_endpoint_offset(
                    points, road, road_id, "end", offset_distance_pixels,
                    minimum_length_pixels, avg_scale, minimum_length_meters,
                    per_road_offsets, verbose
                )
                if new_points is not None:
                    points = new_points
                    end_offset_m = offset_m
                    modified = True

            if modified:
                centerline.points = points
                if centerline.geo_points and len(centerline.geo_points) >= 2:
                    centerline.geo_points = shorten_geo_points(
                        centerline.geo_points, start_offset_m, end_offset_m
                    )
                    if verbose:
                        logger.debug("    Also shortened geo_points: start=%.1fm, end=%.1fm -> %d geo points",
                                     start_offset_m, end_offset_m, len(centerline.geo_points))
                modified_count += 1

    if verbose and modified_count > 0:
        logger.debug("Offset endpoints for %d road(s) at junctions", modified_count)


def _apply_endpoint_offset(points, road, road_id, end, offset_pixels,
                           min_length_pixels, avg_scale, min_length_meters,
                           per_road_offsets, verbose):
    """Offset one endpoint of a road away from a junction.

    Returns (new_points, offset_meters) if modified, (None, 0) otherwise.
    """
    from_start = (end == "start")
    path_length = calculate_path_length(points)

    # Determine actual offset distance
    if per_road_offsets and (road_id, end) in per_road_offsets:
        actual_offset = per_road_offsets[(road_id, end)] / avg_scale
    else:
        actual_offset = offset_pixels

    max_allowed = path_length - min_length_pixels
    if max_allowed <= 0:
        if verbose:
            logger.debug("  SKIP: Road '%s' is too short (%.1fm) to offset while preserving %sm minimum",
                         road.name, path_length * avg_scale, min_length_meters)
        return None, 0.0
    if actual_offset > max_allowed:
        actual_offset = max_allowed
        if verbose:
            logger.debug("  WARNING: Road '%s' offset reduced to %.1fm to preserve %sm minimum length",
                         road.name, actual_offset * avg_scale, min_length_meters)

    if actual_offset <= 0:
        return None, 0.0

    result = find_point_at_distance_along_path(points, actual_offset, from_start=from_start)
    if not result:
        return None, 0.0

    new_point, _direction, segment_idx = result
    points_removed = segment_idx + 1

    if from_start:
        new_points = [new_point] + points[segment_idx + 1:]
    else:
        new_points = points[:-(segment_idx + 1)] + [new_point]

    if len(new_points) < 2:
        if verbose:
            logger.debug("  ERROR: Offsetting %s of road '%s' would leave < 2 points, skipping",
                         end, road.name)
        return None, 0.0

    offset_m = actual_offset * avg_scale
    if verbose:
        logger.debug("  Offset road '%s' %s: moved %.1fpx (%.1fm), removed %d point(s)",
                     road.name, end, actual_offset, offset_m, points_removed)
    return new_points, offset_m


def create_road_from_osm(osm_way: OSMWay, transformer: CoordinateTransformer,
                         default_lane_width: float = 3.5,
                         existing_osm_ids: Set[int] = None) -> Optional[Tuple[Road, Polyline]]:
    """
    Create ORBIT Road and centerline Polyline from OSM way.

    Args:
        osm_way: OSM way object
        transformer: Coordinate transformer
        default_lane_width: Default lane width in meters
        existing_osm_ids: Set of already-imported OSM IDs (for duplicate detection)

    Returns:
        Tuple of (Road, Polyline) or None if should not import
    """
    # Check if already imported
    if existing_osm_ids is not None and osm_way.id in existing_osm_ids:
        return None

    # Check if should import this highway type
    highway = osm_way.tags.get('highway', '')
    if not should_import_highway(highway):
        return None

    # Convert coordinates to pixels and store geo coords
    pixel_points = []
    geo_points = []  # Store (lon, lat) pairs as source of truth
    for lat, lon in osm_way.resolved_coords:
        px, py = transformer.geo_to_pixel(lon, lat)
        pixel_points.append((px, py))
        geo_points.append((lon, lat))  # lon, lat order

    if len(pixel_points) < 2:
        return None

    # Preserve OSM node IDs for junction splitting
    osm_node_ids = list(osm_way.nodes) if osm_way.nodes else None

    # Create centerline polyline with both pixel and geo coords
    centerline = Polyline(
        points=pixel_points,
        geo_points=geo_points,  # Store geo coords as source of truth
        line_type=LineType.CENTERLINE,
        road_mark_type=RoadMarkType.NONE,
        osm_node_ids=osm_node_ids
    )

    # Check if this is a path (cycleway, footway, or designated path)
    path_info = get_path_type_and_lane_type(osm_way.tags)
    if highway == 'path' and path_info is None:
        return None

    if path_info:
        road = _create_path_road(osm_way, centerline, pixel_points, path_info)
    else:
        road = _create_normal_road(osm_way, highway, centerline, pixel_points, default_lane_width)

    road.osm_tags = dict(osm_way.tags)
    road.osm_way_id = osm_way.id
    return (road, centerline)


def _create_path_road(osm_way: OSMWay, centerline: Polyline,
                      pixel_points: list, path_info: tuple) -> Road:
    """Create a road from an OSM bicycle/pedestrian path."""
    from orbit.models.road import LaneInfo
    road_type_prefix, lane_type = path_info
    is_shared_path = 'Shared' in road_type_prefix or 'Segregated' in road_type_prefix

    osm_name = osm_way.tags.get('name', '')
    road_name = f"{road_type_prefix} - {osm_name}" if osm_name else road_type_prefix
    path_width = get_path_width_from_osm(osm_way.tags, lane_type)

    road = Road(
        name=road_name,
        road_type=RoadType.TOWN,
        centerline_id=centerline.id,
        lane_info=LaneInfo(left_count=1, right_count=1, lane_width=path_width)
    )
    road.add_polyline(centerline.id)
    road.speed_limit = 20.0 if lane_type == LaneType.BIKING else None

    section = LaneSection(
        section_number=1, s_start=0.0,
        s_end=len(pixel_points) - 1, end_point_index=None
    )
    section.lanes.append(Lane(id=0, lane_type=LaneType.NONE,
                              road_mark_type=RoadMarkType.NONE, width=0.0))

    access_restrictions = ["bicycle", "pedestrian"] if is_shared_path else []
    for lane_id in (1, -1):
        section.lanes.append(Lane(
            id=lane_id, lane_type=lane_type,
            road_mark_type=RoadMarkType.SOLID, width=path_width,
            access_restrictions=access_restrictions
        ))
    road.lane_sections.append(section)
    return road


def _create_normal_road(osm_way: OSMWay, highway: str, centerline: Polyline,
                        pixel_points: list, default_lane_width: float) -> Road:
    """Create a road from a normal OSM highway."""
    from orbit.models.road import LaneInfo
    road_name = osm_way.tags.get('name', f"OSM Way {osm_way.id}")
    oneway = is_oneway(osm_way.tags)
    reverse_oneway = is_reverse_oneway(osm_way.tags)
    left_lanes, right_lanes = estimate_lane_count(osm_way.tags, oneway)
    lane_width = _resolve_lane_width(osm_way.tags, highway, left_lanes + right_lanes,
                                     default_lane_width)

    road = Road(
        name=road_name,
        road_type=RoadType[get_road_type_for_highway(highway).upper()],
        centerline_id=centerline.id,
        lane_info=LaneInfo(left_count=left_lanes, right_count=right_lanes, lane_width=lane_width)
    )
    road.add_polyline(centerline.id)
    _apply_speed_limit(road, osm_way.tags)

    turn_lanes_forward, turn_lanes_backward = _parse_turn_lane_tags(osm_way.tags, oneway)
    surface_material = _resolve_surface_material(osm_way.tags)

    section = _build_lane_section(
        pixel_points, lane_width, left_lanes, right_lanes,
        oneway, reverse_oneway, turn_lanes_forward, turn_lanes_backward,
        surface_material
    )
    road.lane_sections.append(section)
    return road


def _resolve_lane_width(tags: dict, highway: str, total_lanes: int,
                        default_lane_width: float) -> float:
    """Determine lane width from OSM tags, falling back to highway-type defaults."""
    lane_width = default_lane_width
    if 'width:lanes' in tags or 'width:lanes:forward' in tags:
        width_str = tags.get('width:lanes') or tags.get('width:lanes:forward', '')
        try:
            widths = [float(w.strip()) for w in width_str.split('|')]
            if widths:
                lane_width = sum(widths) / len(widths)
        except (ValueError, AttributeError):
            pass
    elif 'width' in tags:
        try:
            total_width = float(tags['width'])
            if total_lanes > 0:
                lane_width = total_width / total_lanes
        except (ValueError, ZeroDivisionError):
            pass
    if lane_width == default_lane_width:
        lane_width = get_lane_width_for_highway(highway, default_lane_width)
    return lane_width


def _apply_speed_limit(road: Road, tags: dict):
    """Set speed limit on road from OSM maxspeed tag."""
    if 'maxspeed' in tags:
        speed_value, speed_unit = parse_maxspeed(tags['maxspeed'])
        if speed_value:
            if speed_unit == 'mph':
                speed_value = int(speed_value * 1.60934)
            road.speed_limit = float(speed_value)


def _parse_turn_lane_tags(tags: dict, oneway: bool):
    """Parse forward/backward turn:lanes tags."""
    turn_lanes_forward = None
    turn_lanes_backward = None
    if 'turn:lanes:forward' in tags:
        turn_lanes_forward = parse_turn_lanes(tags['turn:lanes:forward'])
    elif 'turn:lanes' in tags and oneway:
        turn_lanes_forward = parse_turn_lanes(tags['turn:lanes'])
    if 'turn:lanes:backward' in tags:
        turn_lanes_backward = parse_turn_lanes(tags['turn:lanes:backward'])
    return turn_lanes_forward, turn_lanes_backward


def _resolve_surface_material(tags: dict):
    """Parse surface and smoothness tags into material tuple."""
    surface_material = None
    if 'surface' in tags:
        surface_material = get_surface_material(tags['surface'])
    if 'smoothness' in tags:
        smoothness_roughness = get_smoothness_roughness(tags['smoothness'])
        if smoothness_roughness is not None:
            if surface_material:
                friction, _, surface_name = surface_material
                surface_material = (friction, smoothness_roughness, surface_name)
            else:
                surface_material = (0.8, smoothness_roughness, 'unknown')
    return surface_material


def _apply_surface_to_lane(lane: Lane, surface_mat):
    """Apply surface material to a lane."""
    if surface_mat:
        friction, roughness, surface_name = surface_mat
        lane.materials = [(0.0, friction, roughness, surface_name)]


def _build_lane_section(pixel_points, lane_width, left_lanes, right_lanes,
                        oneway, reverse_oneway, turn_fwd, turn_bwd,
                        surface_material) -> LaneSection:
    """Build the lane section with all driving lanes."""
    section = LaneSection(
        section_number=1, s_start=0.0,
        s_end=len(pixel_points) - 1, end_point_index=None
    )
    section.lanes.append(Lane(id=0, lane_type=LaneType.NONE,
                              road_mark_type=RoadMarkType.NONE, width=0.0))

    if oneway:
        if reverse_oneway:
            _add_oneway_lanes(section, right_lanes, lane_width, positive_ids=True,
                              turn_lanes=turn_fwd, surface_material=surface_material)
        else:
            _add_oneway_lanes(section, right_lanes, lane_width, positive_ids=False,
                              turn_lanes=turn_fwd, surface_material=surface_material)
    else:
        _add_twoway_lanes(section, left_lanes, right_lanes, lane_width,
                          turn_fwd, turn_bwd, surface_material)
    return section


def _add_oneway_lanes(section, count, width, positive_ids, turn_lanes, surface_material):
    """Add lanes for a one-way road."""
    for i in range(1, count + 1):
        lane_id = i if positive_ids else -i
        lane = Lane(id=lane_id, lane_type=LaneType.DRIVING,
                    road_mark_type=RoadMarkType.BROKEN, width=width)
        if turn_lanes and i <= len(turn_lanes):
            lane.turn_directions = turn_lanes[i - 1]
        _apply_surface_to_lane(lane, surface_material)
        section.lanes.append(lane)


def _add_twoway_lanes(section, left_lanes, right_lanes, width,
                      turn_fwd, turn_bwd, surface_material):
    """Add lanes for a two-way road."""
    # Right lanes (negative IDs) - forward direction
    for i in range(1, right_lanes + 1):
        lane = Lane(
            id=-i, lane_type=LaneType.DRIVING,
            road_mark_type=RoadMarkType.BROKEN if i < right_lanes else RoadMarkType.SOLID,
            width=width
        )
        if turn_fwd and i <= len(turn_fwd):
            lane.turn_directions = turn_fwd[i - 1]
        _apply_surface_to_lane(lane, surface_material)
        section.lanes.append(lane)

    # Left lanes (positive IDs) - backward direction
    for i in range(1, left_lanes + 1):
        lane = Lane(
            id=i, lane_type=LaneType.DRIVING,
            road_mark_type=RoadMarkType.BROKEN if i < left_lanes else RoadMarkType.SOLID,
            width=width
        )
        if turn_bwd and i <= len(turn_bwd):
            lane.turn_directions = turn_bwd[i - 1]
        _apply_surface_to_lane(lane, surface_material)
        section.lanes.append(lane)


def _parse_turn_restriction_members(relation) -> Tuple[Optional[int], Optional[int], Optional[int], Optional[int]]:
    """Extract from/to/via refs from an OSM restriction relation."""
    from_way_id = None
    to_way_id = None
    via_node_id = None
    via_way_id = None

    for member in relation.members:
        role = member.get("role", "")
        ref = member.get("ref")
        member_type = member.get("type")
        if role == "from" and member_type == "way":
            from_way_id = ref
        elif role == "to" and member_type == "way":
            to_way_id = ref
        elif role == "via" and member_type == "node":
            via_node_id = ref
        elif role == "via" and member_type == "way":
            via_way_id = ref

    return from_way_id, to_way_id, via_node_id, via_way_id


def _find_restriction_target_junction(
    junctions: List[Junction],
    osm_way_to_roads: Dict[int, List[str]],
    from_way_id: int,
    to_way_id: int,
) -> Optional[Junction]:
    """Find a junction that contains roads for both from/to ways."""
    from_roads = osm_way_to_roads.get(from_way_id, [])
    to_roads = osm_way_to_roads.get(to_way_id, [])

    for junction in junctions:
        has_from = any(road_id in junction.connected_road_ids for road_id in from_roads)
        has_to = any(road_id in junction.connected_road_ids for road_id in to_roads)
        if has_from and has_to:
            return junction

    return None


def _restriction_action_from_type(restriction_type: str) -> str:
    """Map OSM restriction type to action."""
    if restriction_type.startswith("no_"):
        return "prohibit"
    if restriction_type.startswith("only_"):
        return "require"
    return "unknown"


def _append_turn_restriction(
    junction: Junction,
    restriction_type: str,
    from_way_id: int,
    to_way_id: int,
    via_node_id: Optional[int],
    via_way_id: Optional[int],
) -> None:
    """Append one turn restriction entry to a junction."""
    if not hasattr(junction, "turn_restrictions") or junction.turn_restrictions is None:
        junction.turn_restrictions = []

    junction.turn_restrictions.append(
        {
            "type": restriction_type,
            "from_osm_way": from_way_id,
            "to_osm_way": to_way_id,
            "via_node": via_node_id,
            "via_way": via_way_id,
            "action": _restriction_action_from_type(restriction_type),
        }
    )


def process_turn_restrictions(
    osm_data: 'OSMData',
    junctions: List[Junction],
    road_osm_way_map: Dict[str, int],
    verbose: bool = False
) -> int:
    """
    Process OSM turn restriction relations and apply them to junctions.

    Turn restrictions in OSM are relations with type=restriction that define
    forbidden or mandatory turns at junctions. This function parses these
    relations and stores the restrictions on the relevant junction.

    Args:
        osm_data: Parsed OSM data containing relations
        junctions: List of Junction objects to update
        road_osm_way_map: Mapping from ORBIT road ID to OSM way ID
        verbose: Print debug information

    Returns:
        Number of restrictions processed
    """
    osm_way_to_roads: Dict[int, List[str]] = defaultdict(list)
    for road_id, way_id in road_osm_way_map.items():
        osm_way_to_roads[way_id].append(road_id)

    restrictions_processed = 0

    for relation in osm_data.relations.values():
        if relation.tags.get("type") != "restriction":
            continue

        restriction_type = relation.tags.get("restriction", "")
        if not restriction_type:
            continue

        from_way_id, to_way_id, via_node_id, via_way_id = _parse_turn_restriction_members(relation)
        if not (from_way_id and to_way_id and (via_node_id or via_way_id)):
            continue

        target_junction = _find_restriction_target_junction(
            junctions, osm_way_to_roads, from_way_id, to_way_id
        )
        if not target_junction:
            if verbose:
                logger.debug("  Restriction %s: Could not find junction for "
                             "from_way=%s, to_way=%s", relation.id, from_way_id, to_way_id)
            continue

        _append_turn_restriction(
            junction=target_junction,
            restriction_type=restriction_type,
            from_way_id=from_way_id,
            to_way_id=to_way_id,
            via_node_id=via_node_id,
            via_way_id=via_way_id,
        )
        restrictions_processed += 1

        if verbose:
            logger.debug("  Added restriction '%s' to junction '%s'",
                         restriction_type, target_junction.name)

    return restrictions_processed


def create_signal_from_osm(osm_node: OSMNode, transformer: CoordinateTransformer,
                          existing_osm_ids: Set[int] = None) -> Optional[Signal]:
    """
    Create ORBIT Signal from OSM node.

    Args:
        osm_node: OSM node object
        transformer: Coordinate transformer
        existing_osm_ids: Set of already-imported OSM IDs

    Returns:
        Signal object or None
    """
    # Check if already imported
    if existing_osm_ids is not None and osm_node.id in existing_osm_ids:
        return None

    # Determine signal type
    signal_type = get_signal_type_from_osm(osm_node.tags)
    if not signal_type:
        return None

    # Convert coordinates and store geo position
    px, py = transformer.geo_to_pixel(osm_node.lon, osm_node.lat)
    geo_position = (osm_node.lon, osm_node.lat)  # Store as source of truth

    # Extract speed value if speed limit sign
    speed_value = None
    if signal_type == SignalType.SPEED_LIMIT:
        speed_val, speed_unit = parse_maxspeed(
            osm_node.tags.get('maxspeed', osm_node.tags.get('traffic_sign', ''))
        )
        if speed_val:
            # Convert to km/h if needed
            if speed_unit == 'mph':
                speed_val = int(speed_val * 1.60934)
            speed_value = speed_val

    # Create signal
    signal_name = osm_node.tags.get('name', f"OSM Signal {osm_node.id}")
    # Add signal type to name for display in elements list
    signal_name += f" ({signal_type.value})"

    # Extract direction from OSM tags and map to OpenDRIVE orientation
    direction = osm_node.tags.get('direction', '').lower()
    if direction not in ('forward', 'backward', 'both'):
        direction = 'forward'  # Default to forward if not specified

    signal = Signal(
        position=(px, py),
        signal_type=signal_type,
        value=speed_value,
        geo_position=geo_position,  # Store geo coords as source of truth
    )
    signal.name = signal_name

    # Map OSM direction to OpenDRIVE orientation
    # 'forward' -> '+', 'backward' -> '-', 'both' -> 'none'
    if direction == 'forward':
        signal.orientation = '+'
    elif direction == 'backward':
        signal.orientation = '-'
    elif direction == 'both':
        signal.orientation = 'none'
    else:
        signal.orientation = '+'  # Default

    # h_offset defaults to 0.0 (perpendicular to road), already set in Signal.__init__

    # Note: Signal will be automatically attached to a road if its OSM node is part of a road way
    # during the import process. Manual adjustment can be done in the signal properties dialog.

    signal.osm_tags = dict(osm_node.tags)
    return signal


def _way_points_from_resolved_coords(
    resolved_coords: List[Tuple[float, float]],
    transformer: CoordinateTransformer,
) -> Tuple[List[Tuple[float, float]], List[Tuple[float, float]]]:
    """Convert resolved (lat, lon) coords to pixel points and stored (lon, lat) geo points."""
    pixel_points: List[Tuple[float, float]] = []
    geo_points: List[Tuple[float, float]] = []
    for lat, lon in resolved_coords:
        px, py = transformer.geo_to_pixel(lon, lat)
        pixel_points.append((px, py))
        geo_points.append((lon, lat))
    return pixel_points, geo_points


def _pixel_geo_centroid(
    pixel_points: List[Tuple[float, float]],
    geo_points: List[Tuple[float, float]],
) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """Calculate centroids in pixel and geo spaces."""
    avg_x = sum(point[0] for point in pixel_points) / len(pixel_points)
    avg_y = sum(point[1] for point in pixel_points) / len(pixel_points)
    avg_lon = sum(point[0] for point in geo_points) / len(geo_points)
    avg_lat = sum(point[1] for point in geo_points) / len(geo_points)
    return (avg_x, avg_y), (avg_lon, avg_lat)


def _metric_bbox_dimensions(
    geo_points: List[Tuple[float, float]],
    pixel_points: List[Tuple[float, float]],
    transformer: CoordinateTransformer,
) -> Tuple[float, float]:
    """Calculate width/length in meters with geo-based method and pixel fallback."""
    try:
        meters_points = [transformer.latlon_to_meters(lat, lon) for lon, lat in geo_points]
        xs_m = [point[0] for point in meters_points]
        ys_m = [point[1] for point in meters_points]
        return max(xs_m) - min(xs_m), max(ys_m) - min(ys_m)
    except (TypeError, AttributeError):
        scale_x, scale_y = transformer.get_scale_factor()
        xs = [point[0] for point in pixel_points]
        ys = [point[1] for point in pixel_points]
        return (max(xs) - min(xs)) * scale_x, (max(ys) - min(ys)) * scale_y


def _set_capacity_from_tags(target, tags: Dict[str, str]) -> None:
    """Set numeric capacity on target object when present and valid."""
    if "capacity" not in tags:
        return
    try:
        target.capacity = int(tags["capacity"])
    except ValueError:
        pass


def _create_node_object(osm_node: OSMNode, object_type: ObjectType, transformer: CoordinateTransformer) -> RoadObject:
    """Create a point road object from an OSM node."""
    px, py = transformer.geo_to_pixel(osm_node.lon, osm_node.lat)
    obj = RoadObject(
        position=(px, py),
        object_type=object_type,
        geo_position=(osm_node.lon, osm_node.lat),
    )
    obj.name = osm_node.tags.get("name", f"OSM Object {osm_node.id}")
    obj.osm_tags = dict(osm_node.tags)
    return obj


def _create_guardrail_object(
    osm_way: OSMWay,
    pixel_points: List[Tuple[float, float]],
    geo_points: List[Tuple[float, float]],
) -> RoadObject:
    """Create a guardrail object from an OSM way."""
    obj = RoadObject(
        position=pixel_points[0],
        object_type=ObjectType.GUARDRAIL,
        geo_position=geo_points[0],
    )
    obj.points = pixel_points
    obj.geo_points = geo_points
    obj.name = osm_way.tags.get("name", f"OSM Guardrail {osm_way.id}")
    obj.osm_tags = dict(osm_way.tags)
    return obj


def _create_building_object(
    osm_way: OSMWay,
    pixel_points: List[Tuple[float, float]],
    geo_points: List[Tuple[float, float]],
    transformer: CoordinateTransformer,
) -> RoadObject:
    """Create a building object from an OSM way."""
    pixel_centroid, geo_centroid = _pixel_geo_centroid(pixel_points, geo_points)
    width_meters, length_meters = _metric_bbox_dimensions(geo_points, pixel_points, transformer)

    obj = RoadObject(
        position=pixel_centroid,
        object_type=ObjectType.BUILDING,
        geo_position=geo_centroid,
    )
    obj.name = osm_way.tags.get("name", f"OSM Building {osm_way.id}")
    obj.points = pixel_points
    obj.geo_points = geo_points
    obj.dimensions = {"width": width_meters, "length": length_meters, "height": 6.0}
    obj.osm_tags = dict(osm_way.tags)
    return obj


def create_object_from_osm(osm_element, transformer: CoordinateTransformer,
                          existing_osm_ids: Set[int] = None) -> Optional[RoadObject]:
    """
    Create ORBIT RoadObject from OSM node or way.

    Args:
        osm_element: OSM node or way object
        transformer: Coordinate transformer
        existing_osm_ids: Set of already-imported OSM IDs

    Returns:
        RoadObject or None
    """
    if existing_osm_ids is not None and osm_element.id in existing_osm_ids:
        return None

    object_type = get_object_type_from_osm(osm_element.tags)
    if not object_type:
        return None

    if isinstance(osm_element, OSMNode):
        return _create_node_object(osm_element, object_type, transformer)

    if isinstance(osm_element, OSMWay):
        pixel_points, geo_points = _way_points_from_resolved_coords(osm_element.resolved_coords, transformer)
        if len(pixel_points) < 2:
            return None
        if object_type == ObjectType.GUARDRAIL:
            return _create_guardrail_object(osm_element, pixel_points, geo_points)
        if object_type == ObjectType.BUILDING:
            return _create_building_object(osm_element, pixel_points, geo_points, transformer)

    return None


def create_landuse_from_osm(osm_way: OSMWay, transformer: CoordinateTransformer,
                            existing_osm_ids: Set[int] = None) -> Optional[RoadObject]:
    """Create RoadObject from OSM land use/natural area way.

    Args:
        osm_way: OSM way representing a land use area
        transformer: Coordinate transformer
        existing_osm_ids: Set of already-imported OSM IDs

    Returns:
        RoadObject or None
    """
    from .osm_mappings import get_landuse_type_from_osm

    if existing_osm_ids is not None and osm_way.id in existing_osm_ids:
        return None

    object_type = get_landuse_type_from_osm(osm_way.tags)
    if not object_type:
        return None

    pixel_points, geo_points = _way_points_from_resolved_coords(osm_way.resolved_coords, transformer)
    if len(pixel_points) < 3:
        return None

    pixel_centroid, geo_centroid = _pixel_geo_centroid(pixel_points, geo_points)

    obj = RoadObject(
        position=pixel_centroid,
        object_type=object_type,
        geo_position=geo_centroid,
    )
    obj.points = pixel_points
    obj.geo_points = geo_points
    obj.name = osm_way.tags.get(
        'name', f"OSM {format_enum_name(object_type)} {osm_way.id}"
    )
    obj.osm_tags = dict(osm_way.tags)
    return obj


def create_parking_from_osm(osm_element, transformer: CoordinateTransformer,
                            existing_osm_ids: Set[int] = None) -> Optional[ParkingSpace]:
    """
    Create ORBIT ParkingSpace from OSM node or way.

    Args:
        osm_element: OSM node or way object with amenity=parking
        transformer: Coordinate transformer
        existing_osm_ids: Set of already-imported OSM IDs

    Returns:
        ParkingSpace or None
    """
    if existing_osm_ids is not None and osm_element.id in existing_osm_ids:
        return None

    parking_type = get_parking_type_from_osm(osm_element.tags)
    if not parking_type:
        return None

    access_type = get_parking_access_from_osm(osm_element.tags)

    if isinstance(osm_element, OSMNode):
        px, py = transformer.geo_to_pixel(osm_element.lon, osm_element.lat)
        parking = ParkingSpace(
            position=(px, py),
            access=access_type,
            parking_type=parking_type,
            geo_position=(osm_element.lon, osm_element.lat),
        )
        parking.name = osm_element.tags.get("name", f"Parking {osm_element.id}")
        parking.osm_tags = dict(osm_element.tags)
        _set_capacity_from_tags(parking, osm_element.tags)
        return parking

    if isinstance(osm_element, OSMWay):
        pixel_points, geo_points = _way_points_from_resolved_coords(osm_element.resolved_coords, transformer)
        if len(pixel_points) < 3:
            return None
        pixel_centroid, geo_centroid = _pixel_geo_centroid(pixel_points, geo_points)

        parking = ParkingSpace(
            position=pixel_centroid,
            access=access_type,
            parking_type=parking_type,
            geo_position=geo_centroid,
        )
        parking.name = osm_element.tags.get("name", f"Parking {osm_element.id}")
        parking.osm_tags = dict(osm_element.tags)
        parking.points = pixel_points
        parking.geo_points = geo_points
        _set_capacity_from_tags(parking, osm_element.tags)
        parking.width, parking.length = _metric_bbox_dimensions(geo_points, pixel_points, transformer)
        return parking

    return None

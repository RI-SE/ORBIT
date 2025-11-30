"""
Convert OSM data to ORBIT objects.

Handles coordinate transformation, junction detection, and creation of
Road, Junction, Signal, and RoadObject instances from OSM data.
"""

from typing import List, Dict, Tuple, Optional, Set
from collections import defaultdict
import uuid
import math

from orbit.utils import CoordinateTransformer
from orbit.utils.geometry import find_point_at_distance_along_path, calculate_path_length
from orbit.models import ControlPoint, Road, Junction, Signal, RoadObject
from orbit.models.polyline import Polyline, LineType, RoadMarkType
from orbit.models.road import RoadType
from orbit.models.lane import Lane, LaneType
from orbit.models.lane_section import LaneSection
from orbit.models.signal import SignalType
from orbit.models.object import ObjectType

from .osm_parser import OSMData, OSMWay, OSMNode
from .osm_mappings import (
    get_road_type_for_highway,
    get_lane_width_for_highway,
    should_import_highway,
    is_oneway,
    is_reverse_oneway,
    estimate_lane_count,
    parse_maxspeed,
    get_signal_type_from_osm,
    get_object_type_from_osm,
    get_path_type_and_lane_type,
    get_path_width_from_osm,
)


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


def detect_junction_node_ids_from_osm(osm_data, road_osm_way_map: Dict[str, int]) -> Set[int]:
    """
    Detect OSM node IDs that represent junctions (for road splitting).

    A junction node is where 2+ VEHICULAR roads with DIFFERENT names share a node.

    Args:
        osm_data: Parsed OSM data
        road_osm_way_map: Dictionary mapping Road.id -> OSM way ID

    Returns:
        Set of OSM node IDs that are junctions
    """
    from collections import defaultdict

    # Build reverse mapping: node_id -> list of (osm_way_id, road_name, is_vehicular)
    node_to_roads = defaultdict(list)

    for road_id, osm_way_id in road_osm_way_map.items():
        osm_way = osm_data.ways.get(osm_way_id)
        if not osm_way or not osm_way.nodes:
            continue

        # Get road name from OSM tags
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

        # Check ALL nodes in the way
        for node_id in osm_way.nodes:
            node_to_roads[node_id].append((osm_way_id, road_name, is_vehicular))

    # Find junction nodes where 2+ DIFFERENT VEHICULAR roads meet
    junction_node_ids = set()
    for node_id, road_list in node_to_roads.items():
        if len(road_list) < 2:
            continue

        # Count vehicular roads and get unique road names
        vehicular_roads = [(osm_way_id, road_name) for osm_way_id, road_name, is_vehicular
                          in road_list if is_vehicular]

        # Only junction if at least 2 vehicular roads meet
        if len(vehicular_roads) < 2:
            continue

        # Get unique road names among vehicular roads
        road_names = set(road_name for _, road_name in vehicular_roads)

        # Only junction if 2+ different road names meet
        if len(road_names) >= 2:
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

    # Create junctions where 2+ DIFFERENT VEHICULAR roads meet
    junctions = []
    for node_id, road_list in node_to_roads.items():
        if len(road_list) < 2:
            continue  # Not a junction, only one road uses this node

        # Count vehicular roads and get unique road names
        vehicular_roads = [(road_id, osm_way_id, road_name) for road_id, osm_way_id, road_name, is_vehicular
                          in road_list if is_vehicular]

        # Only create road junction if at least 2 vehicular roads meet
        if len(vehicular_roads) < 2:
            continue  # Not enough vehicular roads - will be handled as path crossing instead

        # Get unique road names among vehicular roads
        road_names = set(road_name for _, _, road_name in vehicular_roads)

        # Only create junction if 2+ different road names meet
        if len(road_names) < 2:
            continue  # Same road, this is a continuation not a junction

        # Get node coordinates
        osm_node = osm_data.nodes.get(node_id)
        if not osm_node:
            continue

        # Convert to pixel coordinates
        px, py = transformer.geo_to_pixel(osm_node.lon, osm_node.lat)

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

        # Create junction
        junction = Junction(
            name=f"Junction {len(junctions) + 1}",
            center_point=(px, py),
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

        # Convert to pixel coordinates
        px, py = transformer.geo_to_pixel(osm_node.lon, osm_node.lat)

        # Extract unique road IDs
        connected_road_ids = list(set(road_id for road_id, _, _, _ in way_list))

        # Determine crossing type from OSM node tags
        crossing_type = osm_node.tags.get('highway', '')
        name_suffix = ""
        if crossing_type == 'crossing':
            name_suffix = " (Crossing)"

        # Create virtual junction for this path crossing
        junction = Junction(
            name=f"Path Crossing {len(junctions) + 1}{name_suffix}",
            center_point=(px, py),
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


def split_roads_at_junction_nodes(
    roads: List[Road],
    polylines_dict: Dict[str, Polyline],
    junction_node_ids: Set[int],
    road_to_osm_way: Dict[str, int] = None,
    verbose: bool = False
) -> Tuple[List[Road], Dict[str, Polyline], Dict[str, int]]:
    """
    Split roads at junction nodes, creating separate road segments.

    For each road that passes through junction nodes, split it into
    multiple roads with endpoints at the junctions. This ensures that
    roads always end at junctions (matching OpenDRIVE conventions).

    Args:
        roads: List of roads to potentially split
        polylines_dict: Dictionary of polyline_id -> Polyline
        junction_node_ids: Set of OSM node IDs that are junctions
        road_to_osm_way: Optional dictionary mapping Road.id -> OSM way ID (preserved for split roads)
        verbose: If True, print debug information

    Returns:
        Tuple of (new_roads_list, new_polylines_dict, new_road_to_osm_way)
    """
    new_roads = []
    new_polylines = {}
    new_road_to_osm_way = {} if road_to_osm_way is not None else None

    split_count = 0
    segment_count = 0

    for road in roads:
        centerline = polylines_dict.get(road.centerline_id)
        osm_way_id = road_to_osm_way.get(road.id) if road_to_osm_way else None

        if not centerline or not centerline.osm_node_ids:
            # Keep road as-is if no OSM data (e.g., manually drawn roads)
            new_roads.append(road)
            if centerline:
                new_polylines[centerline.id] = centerline
            if new_road_to_osm_way is not None and osm_way_id is not None:
                new_road_to_osm_way[road.id] = osm_way_id
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
            if new_road_to_osm_way is not None and osm_way_id is not None:
                new_road_to_osm_way[road.id] = osm_way_id
            continue

        # Road needs splitting!
        split_count += 1
        if verbose:
            print(f"  Splitting road '{road.name}' at {len(split_indices)} junction(s)")

        # Create segments: [0, split1], [split1, split2], ..., [splitN, end]
        split_indices = [0] + split_indices + [len(centerline.points) - 1]

        # Track segments for this road to link them with predecessor/successor
        road_segments = []

        for seg_idx in range(len(split_indices) - 1):
            start_idx = split_indices[seg_idx]
            end_idx = split_indices[seg_idx + 1]

            # Create new polyline for this segment
            segment_points = centerline.points[start_idx:end_idx + 1]
            segment_node_ids = centerline.osm_node_ids[start_idx:end_idx + 1]

            new_polyline = Polyline(
                points=segment_points,
                line_type=LineType.CENTERLINE,
                road_mark_type=centerline.road_mark_type,
                osm_node_ids=segment_node_ids,
                color=centerline.color
            )

            # Create new road for this segment
            # Include OSM way ID in name to distinguish segments from different OSM ways
            if osm_way_id:
                segment_name = f"{road.name} [OSM {osm_way_id}] (seg {seg_idx + 1}/{len(split_indices) - 1})"
            else:
                segment_name = f"{road.name} (seg {seg_idx + 1}/{len(split_indices) - 1})"
            new_road = Road(
                name=segment_name,
                road_type=road.road_type,
                centerline_id=new_polyline.id,
                speed_limit=road.speed_limit
            )

            # Add the centerline polyline to the road's polyline list
            new_road.add_polyline(new_polyline.id)

            # Copy lane info (LaneInfo is a dataclass, use replace or keep reference)
            new_road.lane_info = road.lane_info  # Share the lane info (it's immutable data)

            # Copy lane sections structure
            # For MVP, we create a single section covering the whole segment
            # with the same lane configuration as the original road
            if road.lane_sections:
                # Copy lane configuration from first section
                template_section = road.lane_sections[0]

                new_section = LaneSection(
                    section_number=1,
                    s_start=0.0,
                    s_end=len(segment_points) - 1.0,  # Pixel units
                    end_point_index=len(segment_points) - 1
                )

                # Copy lanes
                for lane in template_section.lanes:
                    new_lane = Lane(
                        id=lane.id,
                        lane_type=lane.lane_type,
                        road_mark_type=lane.road_mark_type,
                        width=lane.width
                    )
                    new_section.lanes.append(new_lane)

                new_road.lane_sections = [new_section]

            road_segments.append(new_road)
            new_polylines[new_polyline.id] = new_polyline
            segment_count += 1

            # Preserve OSM way ID mapping for this segment
            if new_road_to_osm_way is not None and osm_way_id is not None:
                new_road_to_osm_way[new_road.id] = osm_way_id

            if verbose:
                print(f"    Segment {seg_idx + 1}: {len(segment_points)} points, "
                      f"OSM nodes {segment_node_ids[0]} -> {segment_node_ids[-1]}")

        # Link consecutive segments with predecessor/successor relationships
        for i in range(len(road_segments) - 1):
            current_segment = road_segments[i]
            next_segment = road_segments[i + 1]

            current_segment.successor_id = next_segment.id
            next_segment.predecessor_id = current_segment.id

        # Add all segments to the output list
        new_roads.extend(road_segments)

    if verbose and split_count > 0:
        print(f"Split {split_count} road(s) into {segment_count} segment(s)")

    return new_roads, new_polylines, new_road_to_osm_way


def offset_road_endpoints_from_junctions(
    roads: List[Road],
    polylines_dict: Dict[str, Polyline],
    junctions: List['Junction'],
    offset_distance_meters: float = 8.0,
    transformer: 'CoordinateTransformer' = None,
    verbose: bool = False
) -> None:
    """
    Offset road endpoints away from junction centers to create space for connecting roads.

    This modifies road centerline polylines in-place, moving endpoints that are at
    junction centers outward along the road direction.

    Args:
        roads: List of roads
        polylines_dict: Dictionary of polyline_id -> Polyline
        junctions: List of junctions
        offset_distance_meters: Distance in METERS to offset endpoints from junction center (default: 8.0m)
        transformer: CoordinateTransformer to convert meters to pixels (required)
        verbose: If True, print debug information
    """
    if transformer is None:
        raise ValueError("transformer is required to convert offset distance from meters to pixels")

    # Get scale factor (meters per pixel)
    scale_x, scale_y = transformer.get_scale_factor()
    avg_scale = (scale_x + scale_y) / 2.0

    # Convert offset from meters to pixels
    offset_distance_pixels = offset_distance_meters / avg_scale

    if verbose:
        print(f"Offsetting junction endpoints by {offset_distance_meters}m ({offset_distance_pixels:.1f} pixels)")

    modified_count = 0

    for junction in junctions:
        if not junction.center_point:
            continue

        # Skip virtual junctions (path crossings) - they don't need space for connecting roads
        if junction.junction_type == "virtual":
            if verbose:
                print(f"  Skipping virtual junction '{junction.name}' (path crossing)")
            continue

        jx, jy = junction.center_point

        # Process each road connected to this junction
        for road_id in junction.connected_road_ids:
            # Find the road
            road = next((r for r in roads if r.id == road_id), None)
            if not road or not road.centerline_id:
                continue

            centerline = polylines_dict.get(road.centerline_id)
            if not centerline or len(centerline.points) < 2:
                continue

            points = list(centerline.points)  # Make a copy to modify
            modified = False

            # Check start point
            start_dx = points[0][0] - jx
            start_dy = points[0][1] - jy
            start_dist = math.sqrt(start_dx*start_dx + start_dy*start_dy)

            if start_dist < 15.0:  # Within tolerance - at junction
                # Use path-based offset: walk along the road to find point at offset distance
                # Calculate total path length first
                path_length = calculate_path_length(points)

                # Determine actual offset distance to use
                actual_offset = offset_distance_pixels
                if path_length < offset_distance_pixels:
                    # Road is shorter than offset distance - use max available
                    actual_offset = path_length * 0.95  # Leave small margin
                    if verbose:
                        offset_m = offset_distance_meters
                        actual_m = (actual_offset / offset_distance_pixels) * offset_distance_meters
                        print(f"  WARNING: Road '{road.name}' is shorter than offset ({path_length:.1f} px), "
                              f"using {actual_m:.1f}m instead of {offset_m:.1f}m")

                # Find point at offset distance along path
                result = find_point_at_distance_along_path(points, actual_offset, from_start=True)

                if result:
                    new_point, direction, segment_idx = result

                    # Remove passed points and insert new point
                    # segment_idx = i means we landed in segment between points[i] and points[i+1]
                    # We need to remove points[0] through points[i], which is i+1 points
                    points_removed = segment_idx + 1

                    # Build new points list: [new_point] + remaining points after segment
                    points = [new_point] + points[segment_idx + 1:]

                    # Validate we have at least 2 points
                    if len(points) < 2:
                        if verbose:
                            print(f"  ERROR: Offsetting start of road '{road.name}' would leave < 2 points, skipping")
                    else:
                        modified = True
                        if verbose:
                            print(f"  Offset road '{road.name}' start: moved {actual_offset:.1f}px "
                                  f"({(actual_offset / offset_distance_pixels) * offset_distance_meters:.1f}m), "
                                  f"removed {points_removed} point(s)")

            # Check end point
            end_dx = points[-1][0] - jx
            end_dy = points[-1][1] - jy
            end_dist = math.sqrt(end_dx*end_dx + end_dy*end_dy)

            if end_dist < 15.0:  # Within tolerance - at junction
                # Use path-based offset: walk along the road from end
                # Calculate total path length first
                path_length = calculate_path_length(points)

                # Determine actual offset distance to use
                actual_offset = offset_distance_pixels
                if path_length < offset_distance_pixels:
                    # Road is shorter than offset distance - use max available
                    actual_offset = path_length * 0.95  # Leave small margin
                    if verbose:
                        offset_m = offset_distance_meters
                        actual_m = (actual_offset / offset_distance_pixels) * offset_distance_meters
                        print(f"  WARNING: Road '{road.name}' is shorter than offset ({path_length:.1f} px), "
                              f"using {actual_m:.1f}m instead of {offset_m:.1f}m")

                # Find point at offset distance along path from end
                result = find_point_at_distance_along_path(points, actual_offset, from_start=False)

                if result:
                    new_point, direction, segment_idx = result

                    # Remove passed points from end and insert new point
                    # When walking from end with from_start=False, segment_idx tells us
                    # how many segments we passed. We need to remove segment_idx+1 points.
                    # segment_idx=0 means we landed in first segment of reversed list (last segment of original)
                    # segment_idx=1 means we landed in second segment of reversed list, etc.
                    points_removed = segment_idx + 1

                    # Build new points list: remaining points + [new_point]
                    # Remove the last (segment_idx + 1) points and append new_point
                    points = points[:-(segment_idx + 1)] + [new_point]

                    # Validate we have at least 2 points
                    if len(points) < 2:
                        if verbose:
                            print(f"  ERROR: Offsetting end of road '{road.name}' would leave < 2 points, skipping")
                    else:
                        modified = True
                        if verbose:
                            print(f"  Offset road '{road.name}' end: moved {actual_offset:.1f}px "
                                  f"({(actual_offset / offset_distance_pixels) * offset_distance_meters:.1f}m), "
                                  f"removed {points_removed} point(s)")

            if modified:
                # Update the polyline with modified points
                centerline.points = points
                modified_count += 1

    if verbose and modified_count > 0:
        print(f"Offset endpoints for {modified_count} road(s) at junctions")


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

    # Convert coordinates to pixels
    pixel_points = []
    for lat, lon in osm_way.resolved_coords:
        px, py = transformer.geo_to_pixel(lon, lat)
        pixel_points.append((px, py))

    if len(pixel_points) < 2:
        return None

    # Preserve OSM node IDs for junction splitting
    osm_node_ids = list(osm_way.nodes) if osm_way.nodes else None

    # Create centerline polyline
    centerline = Polyline(
        points=pixel_points,
        line_type=LineType.CENTERLINE,
        road_mark_type=RoadMarkType.NONE,
        osm_node_ids=osm_node_ids
    )

    # Check if this is a path (cycleway, footway, or designated path)
    path_info = get_path_type_and_lane_type(osm_way.tags)
    if highway == 'path' and path_info is None:
        # Undedicated path (no bicycle=designated or foot=designated) - skip import
        return None

    if path_info:
        # This is a bicycle or pedestrian path
        road_type_prefix, lane_type = path_info

        # Get path name
        osm_name = osm_way.tags.get('name', '')
        road_name = f"{road_type_prefix} - {osm_name}" if osm_name else road_type_prefix

        # Get path width
        path_width = get_path_width_from_osm(osm_way.tags, lane_type)

        # Create road with path type
        from orbit.models.road import LaneInfo
        road = Road(
            name=road_name,
            road_type=RoadType.TOWN,  # Paths are typically in town/urban areas
            centerline_id=centerline.id,
            lane_info=LaneInfo(
                left_count=0,
                right_count=1,  # Single lane on right side
                lane_width=path_width
            )
        )
        road.add_polyline(centerline.id)

        # Set speed limit for bicycle paths (optional)
        if lane_type == LaneType.BIKING:
            road.speed_limit = 20.0  # 20 km/h reasonable cycling speed
        else:
            road.speed_limit = None  # No speed limit for pedestrian paths

        # Create single lane section with one path lane
        section = LaneSection(
            section_number=1,
            s_start=0.0,
            s_end=len(pixel_points) - 1,
            end_point_index=None  # Last section
        )

        # Create center lane (lane 0)
        center_lane = Lane(
            id=0,
            lane_type=LaneType.NONE,
            road_mark_type=RoadMarkType.NONE,
            width=0.0
        )
        section.lanes.append(center_lane)

        # Create single path lane on right side
        path_lane = Lane(
            id=-1,  # Single lane on right side
            lane_type=lane_type,  # BIKING or SIDEWALK
            road_mark_type=RoadMarkType.SOLID,  # Paths typically have solid edges
            width=path_width
        )
        section.lanes.append(path_lane)

        road.lane_sections.append(section)

        return (road, centerline)

    # Normal road processing (not a path)
    # Determine road name
    road_name = osm_way.tags.get('name', f"OSM Way {osm_way.id}")

    # Determine lane configuration first
    oneway = is_oneway(osm_way.tags)
    reverse_oneway = is_reverse_oneway(osm_way.tags)
    left_lanes, right_lanes = estimate_lane_count(osm_way.tags, oneway)

    # Get lane width - check for explicit OSM tags first
    lane_width = default_lane_width

    # Check for explicit width tags in OSM
    if 'width:lanes' in osm_way.tags or 'width:lanes:forward' in osm_way.tags:
        # Parse per-lane widths (format: "3.5|3.5|3.5")
        width_str = osm_way.tags.get('width:lanes') or osm_way.tags.get('width:lanes:forward', '')
        try:
            widths = [float(w.strip()) for w in width_str.split('|')]
            if widths:
                lane_width = sum(widths) / len(widths)  # Use average
        except (ValueError, AttributeError):
            pass
    elif 'width' in osm_way.tags:
        # Parse total road width and divide by lane count
        try:
            total_width = float(osm_way.tags['width'])
            total_lanes = left_lanes + right_lanes
            if total_lanes > 0:
                lane_width = total_width / total_lanes
        except (ValueError, ZeroDivisionError):
            pass

    # If no explicit width found, use highway-type defaults
    if lane_width == default_lane_width:
        lane_width = get_lane_width_for_highway(highway, default_lane_width)

    # Create road with lane info
    from orbit.models.road import LaneInfo
    road = Road(
        name=road_name,
        road_type=RoadType[get_road_type_for_highway(highway).upper()],
        centerline_id=centerline.id,
        lane_info=LaneInfo(
            left_count=left_lanes,
            right_count=right_lanes,
            lane_width=lane_width
        )
    )
    road.add_polyline(centerline.id)

    # Set speed limit if available
    if 'maxspeed' in osm_way.tags:
        speed_value, speed_unit = parse_maxspeed(osm_way.tags['maxspeed'])
        if speed_value:
            # Convert mph to km/h if needed
            if speed_unit == 'mph':
                speed_value = int(speed_value * 1.60934)
            road.speed_limit = float(speed_value)

    # Create single lane section spanning entire road
    section = LaneSection(
        section_number=1,
        s_start=0.0,
        s_end=len(pixel_points) - 1,
        end_point_index=None  # Last section
    )

    # Create center lane (lane 0)
    center_lane = Lane(
        id=0,
        lane_type=LaneType.NONE,
        road_mark_type=RoadMarkType.NONE,
        width=0.0
    )
    section.lanes.append(center_lane)

    # For oneway roads, only create lanes on one side
    if oneway:
        if reverse_oneway:
            # Lanes on left side (positive IDs)
            for i in range(1, right_lanes + 1):
                lane = Lane(
                    id=i,
                    lane_type=LaneType.DRIVING,
                    road_mark_type=RoadMarkType.BROKEN,
                    width=lane_width
                )
                section.lanes.append(lane)
        else:
            # Lanes on right side (negative IDs)
            for i in range(1, right_lanes + 1):
                lane = Lane(
                    id=-i,
                    lane_type=LaneType.DRIVING,
                    road_mark_type=RoadMarkType.BROKEN,
                    width=lane_width
                )
                section.lanes.append(lane)
    else:
        # Two-way road: create lanes on both sides

        # Right lanes (negative IDs)
        for i in range(1, right_lanes + 1):
            lane = Lane(
                id=-i,
                lane_type=LaneType.DRIVING,
                road_mark_type=RoadMarkType.BROKEN if i < right_lanes else RoadMarkType.SOLID,
                width=lane_width
            )
            section.lanes.append(lane)

        # Left lanes (positive IDs)
        for i in range(1, left_lanes + 1):
            lane = Lane(
                id=i,
                lane_type=LaneType.DRIVING,
                road_mark_type=RoadMarkType.BROKEN if i < left_lanes else RoadMarkType.SOLID,
                width=lane_width
            )
            section.lanes.append(lane)

    road.lane_sections.append(section)

    return (road, centerline)


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

    # Convert coordinates
    px, py = transformer.geo_to_pixel(osm_node.lon, osm_node.lat)

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

    return signal


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
    # Check if already imported
    if existing_osm_ids is not None and osm_element.id in existing_osm_ids:
        return None

    # Determine object type
    object_type = get_object_type_from_osm(osm_element.tags)
    if not object_type:
        return None

    # Handle nodes (point objects)
    if isinstance(osm_element, OSMNode):
        px, py = transformer.geo_to_pixel(osm_element.lon, osm_element.lat)

        obj = RoadObject(
            position=(px, py),
            object_type=object_type
        )
        obj.name = osm_element.tags.get('name', f"OSM Object {osm_element.id}")
        return obj

    # Handle ways (polyline objects like guardrails or buildings)
    elif isinstance(osm_element, OSMWay):
        # Convert coordinates
        pixel_points = []
        for lat, lon in osm_element.resolved_coords:
            px, py = transformer.geo_to_pixel(lon, lat)
            pixel_points.append((px, py))

        if len(pixel_points) < 2:
            return None

        # For guardrails, use polyline
        if object_type == ObjectType.GUARDRAIL:
            # Use first point as position, store full polyline
            obj = RoadObject(
                position=pixel_points[0],
                object_type=object_type
            )
            obj.points = pixel_points
            obj.name = osm_element.tags.get('name', f"OSM Guardrail {osm_element.id}")
            return obj

        # For buildings, store polygon and use centroid as position
        elif object_type == ObjectType.BUILDING:
            # Calculate centroid
            avg_x = sum(p[0] for p in pixel_points) / len(pixel_points)
            avg_y = sum(p[1] for p in pixel_points) / len(pixel_points)

            obj = RoadObject(
                position=(avg_x, avg_y),
                object_type=object_type
            )
            obj.name = osm_element.tags.get('name', f"OSM Building {osm_element.id}")

            # Store polygon points for visualization
            obj.points = pixel_points

            # Calculate building dimensions from bounding box
            xs = [p[0] for p in pixel_points]
            ys = [p[1] for p in pixel_points]
            width_pixels = max(xs) - min(xs)
            length_pixels = max(ys) - min(ys)

            # Convert from pixels to meters using transformer scale
            scale_x, scale_y = transformer.get_scale_factor()
            width_meters = width_pixels * scale_x
            length_meters = length_pixels * scale_y

            obj.dimensions = {
                'width': width_meters,
                'length': length_meters,
                'height': 6.0  # Default height in meters
            }

            return obj

    return None

"""
Export ORBIT project to OpenStreetMap XML (.osm) format.

Generates OSM XML with roads as ways, signals/objects as nodes,
and polygon objects (buildings, parking) as closed ways.
Uses preserved osm_tags when available for faithful round-tripping.
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from orbit.models.object import RoadObject
from orbit.models.parking import ParkingSpace
from orbit.models.project import Project
from orbit.utils.logging_config import get_logger

from .osm_mappings import (
    get_osm_tags_for_object,
    get_osm_tags_for_parking,
    get_osm_tags_for_road,
    get_osm_tags_for_signal,
)

logger = get_logger(__name__)

# Threshold for node deduplication in degrees (~0.5m at mid-latitudes)
_DEDUP_THRESHOLD_DEG = 5e-6


def _find_or_create_node(
    lon: float, lat: float,
    node_index: Dict[Tuple[int, int], int],
    nodes: Dict[int, Tuple[float, float]],
    id_counter: List[int],
) -> int:
    """Find existing node within threshold or create a new one.

    Uses a grid-based spatial index for O(1) lookup.
    Returns the node ID.
    """
    # Quantize to grid cells (~0.5m)
    grid_key = (round(lon / _DEDUP_THRESHOLD_DEG), round(lat / _DEDUP_THRESHOLD_DEG))
    if grid_key in node_index:
        return node_index[grid_key]

    node_id = id_counter[0]
    id_counter[0] -= 1
    node_index[grid_key] = node_id
    nodes[node_id] = (lon, lat)
    return node_id


def _add_tags_to_element(parent: ET.Element, tags: Dict[str, str]) -> None:
    """Add OSM tag sub-elements to a parent element."""
    for key, value in sorted(tags.items()):
        ET.SubElement(parent, 'tag', k=key, v=str(value))


def _create_way_from_geo_points(
    geo_points: List[Tuple[float, float]],
    tags: Dict[str, str],
    node_index: Dict[Tuple[int, int], int],
    nodes: Dict[int, Tuple[float, float]],
    id_counter: List[int],
    close_polygon: bool = False,
) -> Optional[ET.Element]:
    """Create an OSM way element from a list of (lon, lat) points.

    Args:
        geo_points: List of (lon, lat) coordinates.
        tags: OSM tags for the way.
        node_index: Spatial index for node deduplication.
        nodes: Node ID -> (lon, lat) mapping.
        id_counter: Mutable counter [current_id] for negative IDs.
        close_polygon: If True, ensure first and last node refs match.

    Returns:
        ET.Element for the way, or None if insufficient points.
    """
    if not geo_points or len(geo_points) < 2:
        return None

    way_id = id_counter[0]
    id_counter[0] -= 1
    way_element = ET.Element('way', id=str(way_id), visible='true')

    node_refs = []
    for lon, lat in geo_points:
        nid = _find_or_create_node(lon, lat, node_index, nodes, id_counter)
        node_refs.append(nid)

    # Close polygon if requested and not already closed
    if close_polygon and len(node_refs) >= 3 and node_refs[0] != node_refs[-1]:
        node_refs.append(node_refs[0])

    for nid in node_refs:
        ET.SubElement(way_element, 'nd', ref=str(nid))

    _add_tags_to_element(way_element, tags)
    return way_element


def export_to_osm(
    project: Project, output_path: Path, transformer=None
) -> Tuple[bool, str, dict]:
    """Export ORBIT project to OSM XML.

    Args:
        project: The ORBIT project to export.
        output_path: Path where .osm file will be written.
        transformer: Optional CoordinateTransformer for pixel→geo conversion.
            Used to convert connecting roads that only have pixel coordinates.

    Returns:
        Tuple of (success, message, stats_dict).
        stats_dict has keys: roads, signals, objects, parking, skipped.
    """
    stats = {'roads': 0, 'signals': 0, 'objects': 0, 'parking': 0, 'skipped': 0}

    # Shared state for node deduplication
    node_index: Dict[Tuple[int, int], int] = {}  # grid_key -> node_id
    nodes: Dict[int, Tuple[float, float]] = {}    # node_id -> (lon, lat)
    id_counter = [-1]  # Negative IDs (OSM convention for unsaved data)
    way_elements: List[ET.Element] = []
    standalone_node_elements: List[ET.Element] = []

    # --- Roads ---
    for road in project.roads:
        centerline = None
        if road.centerline_id:
            centerline = project.get_polyline(road.centerline_id)
        if not centerline or not centerline.has_geo_coords():
            stats['skipped'] += 1
            continue

        tags = get_osm_tags_for_road(road)
        way_el = _create_way_from_geo_points(
            centerline.geo_points, tags,
            node_index, nodes, id_counter,
        )
        if way_el is not None:
            way_elements.append(way_el)
            stats['roads'] += 1
        else:
            stats['skipped'] += 1

    # --- Connecting Roads (junction paths) ---
    # Build road lookup for inheriting tags from connected roads
    road_by_id = {road.id: road for road in project.roads}
    for junction in project.junctions:
        for cr in junction.connecting_roads:
            geo_path = cr.geo_path
            # Fall back to pixel→geo conversion if geo_path is missing
            if not geo_path and cr.path and transformer:
                geo_path = [transformer.pixel_to_geo(x, y) for x, y in cr.path]
            if not geo_path or len(geo_path) < 2:
                stats['skipped'] += 1
                continue

            # Inherit highway tag from the predecessor or successor road
            tags = _get_connecting_road_tags(cr, road_by_id)
            way_el = _create_way_from_geo_points(
                geo_path, tags,
                node_index, nodes, id_counter,
            )
            if way_el is not None:
                way_elements.append(way_el)
                stats['roads'] += 1
            else:
                stats['skipped'] += 1

    # --- Signals ---
    for signal in project.signals:
        if not signal.has_geo_coords():
            stats['skipped'] += 1
            continue

        lon, lat = signal.geo_position
        nid = _find_or_create_node(lon, lat, node_index, nodes, id_counter)
        tags = get_osm_tags_for_signal(signal)

        node_el = ET.Element('node', id=str(nid), lat=str(lat), lon=str(lon), visible='true')
        _add_tags_to_element(node_el, tags)
        standalone_node_elements.append(node_el)
        stats['signals'] += 1

    # --- Objects ---
    for obj in project.objects:
        exported = _export_object(obj, node_index, nodes, id_counter,
                                  way_elements, standalone_node_elements)
        if exported:
            stats['objects'] += 1
        else:
            stats['skipped'] += 1

    # --- Parking ---
    for parking in project.parking_spaces:
        exported = _export_parking(parking, node_index, nodes, id_counter,
                                   way_elements, standalone_node_elements)
        if exported:
            stats['parking'] += 1
        else:
            stats['skipped'] += 1

    # Check we have something to export
    total = stats['roads'] + stats['signals'] + stats['objects'] + stats['parking']
    if total == 0:
        return False, "Nothing to export: no elements have geographic coordinates.", stats

    # --- Build XML tree ---
    osm_attribs = {
        'version': '0.6',
        'generator': 'ORBIT (https://github.com/RI-SE/ORBIT)',
        'license': 'http://opendatacommons.org/licenses/odbl/1-0/',
    }
    if project.openstreetmap_used:
        osm_attribs['attribution'] = 'Map data from OpenStreetMap (http://www.openstreetmap.org/copyright)'
    root = ET.Element('osm', **osm_attribs)

    # Add bounds element from node extents
    if nodes:
        lons = [coord[0] for coord in nodes.values()]
        lats = [coord[1] for coord in nodes.values()]
        ET.SubElement(root, 'bounds',
                      minlat=f"{min(lats):.7f}", minlon=f"{min(lons):.7f}",
                      maxlat=f"{max(lats):.7f}", maxlon=f"{max(lons):.7f}")

    # Write all nodes first (OSM convention: nodes before ways)
    # Track which nodes have standalone tags
    tagged_node_ids = {int(el.get('id')) for el in standalone_node_elements}

    for nid, (lon, lat) in sorted(nodes.items(), key=lambda x: x[0], reverse=True):
        if nid in tagged_node_ids:
            # Already have a tagged version — find and add it
            for el in standalone_node_elements:
                if int(el.get('id')) == nid:
                    root.append(el)
                    break
        else:
            ET.SubElement(root, 'node', id=str(nid),
                          lat=f"{lat:.7f}", lon=f"{lon:.7f}", visible='true')

    # Write ways
    for way_el in way_elements:
        root.append(way_el)

    # Write XML
    tree = ET.ElementTree(root)
    ET.indent(tree, space='  ')

    with open(output_path, 'wb') as f:
        tree.write(f, encoding='UTF-8', xml_declaration=True)

    msg = (f"Exported {stats['roads']} roads, {stats['signals']} signals, "
           f"{stats['objects']} objects, {stats['parking']} parking areas.")
    if stats['skipped']:
        msg += f" {stats['skipped']} items skipped (no geo coordinates)."

    return True, msg, stats


def _get_connecting_road_tags(cr, road_by_id: dict) -> Dict[str, str]:
    """Get OSM tags for a connecting road by inheriting from connected roads."""
    # Try predecessor first, then successor
    for road_id in (cr.predecessor_road_id, cr.successor_road_id):
        road = road_by_id.get(road_id)
        if road:
            tags = get_osm_tags_for_road(road)
            # Remove name — connecting roads typically don't have street names
            tags.pop('name', None)
            return tags
    # Fallback: generic road
    return {'highway': 'road'}


def _export_object(
    obj: RoadObject,
    node_index: Dict[Tuple[int, int], int],
    nodes: Dict[int, Tuple[float, float]],
    id_counter: List[int],
    way_elements: List[ET.Element],
    standalone_node_elements: List[ET.Element],
) -> bool:
    """Export a single RoadObject. Returns True if exported."""
    tags = get_osm_tags_for_object(obj)
    if not tags:
        return False

    shape = obj.type.get_shape_type()

    # Polygon objects (buildings) -> closed way
    if shape in ('rectangle', 'polygon') and obj.geo_points and len(obj.geo_points) >= 3:
        way_el = _create_way_from_geo_points(
            obj.geo_points, tags,
            node_index, nodes, id_counter,
            close_polygon=True,
        )
        if way_el is not None:
            way_elements.append(way_el)
            return True
        return False

    # Polyline objects (guardrails) -> open way
    if shape == 'polyline' and obj.geo_points and len(obj.geo_points) >= 2:
        way_el = _create_way_from_geo_points(
            obj.geo_points, tags,
            node_index, nodes, id_counter,
        )
        if way_el is not None:
            way_elements.append(way_el)
            return True
        return False

    # Point objects -> node
    if obj.has_geo_coords() and obj.geo_position:
        lon, lat = obj.geo_position
        nid = _find_or_create_node(lon, lat, node_index, nodes, id_counter)
        node_el = ET.Element('node', id=str(nid), lat=f"{lat:.7f}", lon=f"{lon:.7f}", visible='true')
        _add_tags_to_element(node_el, tags)
        standalone_node_elements.append(node_el)
        return True

    return False


def _export_parking(
    parking: ParkingSpace,
    node_index: Dict[Tuple[int, int], int],
    nodes: Dict[int, Tuple[float, float]],
    id_counter: List[int],
    way_elements: List[ET.Element],
    standalone_node_elements: List[ET.Element],
) -> bool:
    """Export a single ParkingSpace. Returns True if exported."""
    tags = get_osm_tags_for_parking(parking)

    # Polygon parking -> closed way
    if parking.geo_points and len(parking.geo_points) >= 3:
        way_el = _create_way_from_geo_points(
            parking.geo_points, tags,
            node_index, nodes, id_counter,
            close_polygon=True,
        )
        if way_el is not None:
            way_elements.append(way_el)
            return True
        return False

    # Point parking -> node
    if parking.has_geo_coords() and parking.geo_position:
        lon, lat = parking.geo_position
        nid = _find_or_create_node(lon, lat, node_index, nodes, id_counter)
        node_el = ET.Element('node', id=str(nid), lat=f"{lat:.7f}", lon=f"{lon:.7f}", visible='true')
        _add_tags_to_element(node_el, tags)
        standalone_node_elements.append(node_el)
        return True

    return False

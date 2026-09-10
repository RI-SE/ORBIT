"""
Parse OSM JSON and XML data into intermediate Python objects.
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class OSMNode:
    """Represents an OSM node (point feature)."""
    id: int
    lat: float
    lon: float
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class OSMWay:
    """Represents an OSM way (line feature)."""
    id: int
    nodes: List[int]  # Node IDs
    tags: Dict[str, str] = field(default_factory=dict)
    resolved_coords: List[tuple[float, float]] = field(default_factory=list)  # (lat, lon) pairs


@dataclass
class OSMRelation:
    """Represents an OSM relation (group of features)."""
    id: int
    members: List[dict]  # Each member: {'type': 'node'|'way', 'ref': id, 'role': str}
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class OSMData:
    """Container for parsed OSM data."""
    nodes: Dict[int, OSMNode] = field(default_factory=dict)
    ways: Dict[int, OSMWay] = field(default_factory=dict)
    relations: Dict[int, OSMRelation] = field(default_factory=dict)

    def get_way_coords(self, way: OSMWay) -> List[tuple[float, float]]:
        """
        Resolve way node IDs to coordinates.

        Args:
            way: OSMWay object

        Returns:
            List of (lat, lon) tuples
        """
        coords = []
        for node_id in way.nodes:
            if node_id in self.nodes:
                node = self.nodes[node_id]
                coords.append((node.lat, node.lon))
            else:
                # Missing node - this shouldn't happen with proper Overpass query
                # but handle gracefully
                pass
        return coords


class OSMParser:
    """Parse Overpass API JSON response."""

    @staticmethod
    def parse(osm_json: dict) -> OSMData:
        """
        Parse Overpass API JSON response.

        Args:
            osm_json: Parsed JSON from Overpass API

        Returns:
            OSMData object with parsed elements
        """
        data = OSMData()

        if 'elements' not in osm_json:
            return data

        # First pass: collect all nodes
        for element in osm_json['elements']:
            if element['type'] == 'node':
                node_id = element['id']
                tags = element.get('tags', {})

                # If node already exists, preserve existing tags (don't overwrite with empty tags)
                # This handles Overpass "out body; >; out skel qt;" which outputs nodes twice:
                # once with tags, once without (for way geometry)
                if node_id in data.nodes:
                    # Merge tags - keep existing tags and add new ones
                    if tags:
                        data.nodes[node_id].tags.update(tags)
                else:
                    # Create new node
                    node = OSMNode(
                        id=node_id,
                        lat=element['lat'],
                        lon=element['lon'],
                        tags=tags
                    )
                    data.nodes[node_id] = node

        # Second pass: collect ways and resolve coordinates
        for element in osm_json['elements']:
            if element['type'] == 'way':
                way = OSMWay(
                    id=element['id'],
                    nodes=element.get('nodes', []),
                    tags=element.get('tags', {})
                )
                # Resolve node coordinates
                way.resolved_coords = data.get_way_coords(way)
                data.ways[way.id] = way

        # Third pass: collect relations
        for element in osm_json['elements']:
            if element['type'] == 'relation':
                relation = OSMRelation(
                    id=element['id'],
                    members=element.get('members', []),
                    tags=element.get('tags', {})
                )
                data.relations[relation.id] = relation

        return data

    @staticmethod
    def parse_xml(xml_content: str) -> OSMData:
        """
        Parse OSM XML data (e.g., from .osm file).

        Args:
            xml_content: XML string content from OSM file

        Returns:
            OSMData object with parsed elements
        """
        data = OSMData()
        root = ET.fromstring(xml_content)

        # First pass: collect all nodes
        for node_elem in root.findall('node'):
            node_id = int(node_elem.get('id'))
            lat = float(node_elem.get('lat'))
            lon = float(node_elem.get('lon'))

            # Parse tags
            tags = {}
            for tag_elem in node_elem.findall('tag'):
                k = tag_elem.get('k')
                v = tag_elem.get('v')
                if k and v:
                    tags[k] = v

            node = OSMNode(id=node_id, lat=lat, lon=lon, tags=tags)
            data.nodes[node_id] = node

        # Second pass: collect ways
        for way_elem in root.findall('way'):
            way_id = int(way_elem.get('id'))

            # Parse node references
            nodes = []
            for nd_elem in way_elem.findall('nd'):
                ref = int(nd_elem.get('ref'))
                nodes.append(ref)

            # Parse tags
            tags = {}
            for tag_elem in way_elem.findall('tag'):
                k = tag_elem.get('k')
                v = tag_elem.get('v')
                if k and v:
                    tags[k] = v

            way = OSMWay(id=way_id, nodes=nodes, tags=tags)
            # Resolve node coordinates
            way.resolved_coords = data.get_way_coords(way)
            data.ways[way_id] = way

        # Third pass: collect relations
        for rel_elem in root.findall('relation'):
            rel_id = int(rel_elem.get('id'))

            # Parse members
            members = []
            for member_elem in rel_elem.findall('member'):
                member = {
                    'type': member_elem.get('type'),
                    'ref': int(member_elem.get('ref')),
                    'role': member_elem.get('role', '')
                }
                members.append(member)

            # Parse tags
            tags = {}
            for tag_elem in rel_elem.findall('tag'):
                k = tag_elem.get('k')
                v = tag_elem.get('v')
                if k and v:
                    tags[k] = v

            relation = OSMRelation(id=rel_id, members=members, tags=tags)
            data.relations[rel_id] = relation

        return data

    @staticmethod
    def get_highway_ways(data: OSMData) -> List[OSMWay]:
        """
        Extract ways with highway tag.

        Args:
            data: Parsed OSM data

        Returns:
            List of ways that represent roads
        """
        return [
            way for way in data.ways.values()
            if 'highway' in way.tags
        ]

    @staticmethod
    def get_traffic_signal_nodes(data: OSMData) -> List[OSMNode]:
        """
        Extract nodes representing traffic signals.

        Args:
            data: Parsed OSM data

        Returns:
            List of traffic signal nodes
        """
        signals = []
        for node in data.nodes.values():
            if node.tags.get('highway') == 'traffic_signals':
                signals.append(node)
        return signals

    @staticmethod
    def get_traffic_sign_nodes(data: OSMData) -> List[OSMNode]:
        """
        Extract nodes representing traffic signs.

        Includes:
        - Nodes with 'traffic_sign' tag (country-specific codes)
        - Nodes with 'maxspeed' tag (speed limit signs)
        - Nodes with highway=give_way, highway=stop, highway=crossing

        Args:
            data: Parsed OSM data

        Returns:
            List of traffic sign nodes
        """
        signs = []
        for node in data.nodes.values():
            # Check for traffic_sign or maxspeed tags
            if 'traffic_sign' in node.tags or 'maxspeed' in node.tags:
                signs.append(node)
            # Check for highway tag regulatory signs
            elif node.tags.get('highway') in ('give_way', 'stop', 'crossing'):
                signs.append(node)
        return signs

    @staticmethod
    def get_street_lamp_nodes(data: OSMData) -> List[OSMNode]:
        """
        Extract nodes representing street lamps.

        Args:
            data: Parsed OSM data

        Returns:
            List of street lamp nodes
        """
        lamps = []
        for node in data.nodes.values():
            if node.tags.get('highway') == 'street_lamp':
                lamps.append(node)
        return lamps

    @staticmethod
    def get_tree_nodes(data: OSMData) -> List[OSMNode]:
        """
        Extract nodes representing trees.

        Args:
            data: Parsed OSM data

        Returns:
            List of tree nodes
        """
        trees = []
        for node in data.nodes.values():
            if node.tags.get('natural') == 'tree':
                trees.append(node)
        return trees

    @staticmethod
    def get_building_ways(data: OSMData) -> List[OSMWay]:
        """
        Extract ways representing buildings.

        Args:
            data: Parsed OSM data

        Returns:
            List of building ways
        """
        return [
            way for way in data.ways.values()
            if 'building' in way.tags
        ]

    @staticmethod
    def get_guardrail_ways(data: OSMData) -> List[OSMWay]:
        """
        Extract ways representing guardrails.

        Args:
            data: Parsed OSM data

        Returns:
            List of guardrail ways
        """
        return [
            way for way in data.ways.values()
            if way.tags.get('barrier') == 'guard_rail'
        ]

    @staticmethod
    def get_roundabout_ways(data: OSMData) -> List[OSMWay]:
        """
        Extract ways tagged as roundabouts.

        Args:
            data: Parsed OSM data

        Returns:
            List of OSMWay objects with junction=roundabout tag
        """
        return [
            way for way in data.ways.values()
            if way.tags.get('junction') == 'roundabout'
        ]

    @staticmethod
    def is_closed_way(way: OSMWay) -> bool:
        """
        Check if way forms a closed loop (first node == last node).

        Args:
            way: OSMWay object

        Returns:
            True if the way is closed (first and last node are the same)
        """
        return len(way.nodes) > 2 and way.nodes[0] == way.nodes[-1]

    @staticmethod
    def get_landuse_ways(data: OSMData) -> List[OSMWay]:
        """Extract ways representing land use / natural areas."""
        landuse_tags = {'forest', 'farmland', 'meadow', 'grass'}
        natural_tags = {'wood', 'water', 'wetland', 'scrub', 'heath'}
        return [
            way for way in data.ways.values()
            if way.tags.get('landuse') in landuse_tags
            or way.tags.get('natural') in natural_tags
            or way.tags.get('waterway') == 'riverbank'
            or 'water' in way.tags
        ]

    @staticmethod
    def get_parking_ways(data: OSMData) -> List[OSMWay]:
        """
        Extract ways representing parking facilities.

        Args:
            data: Parsed OSM data

        Returns:
            List of parking ways (amenity=parking)
        """
        return [
            way for way in data.ways.values()
            if way.tags.get('amenity') == 'parking'
        ]

    @staticmethod
    def get_parking_nodes(data: OSMData) -> List[OSMNode]:
        """
        Extract nodes representing parking facilities.

        Some parking facilities are mapped as nodes rather than ways.

        Args:
            data: Parsed OSM data

        Returns:
            List of parking nodes (amenity=parking)
        """
        return [
            node for node in data.nodes.values()
            if node.tags.get('amenity') == 'parking'
        ]


def parse_osm_data(osm_json: dict) -> OSMData:
    """
    Convenience function to parse OSM JSON.

    Args:
        osm_json: Parsed JSON from Overpass API

    Returns:
        OSMData object
    """
    return OSMParser.parse(osm_json)

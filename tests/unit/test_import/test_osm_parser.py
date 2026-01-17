"""Tests for orbit.import.osm_parser module."""

import importlib
import pytest

# Import from orbit.import using importlib (import is a reserved keyword)
osm_parser = importlib.import_module('orbit.import.osm_parser')

OSMNode = osm_parser.OSMNode
OSMWay = osm_parser.OSMWay
OSMRelation = osm_parser.OSMRelation
OSMData = osm_parser.OSMData
OSMParser = osm_parser.OSMParser
parse_osm_data = osm_parser.parse_osm_data


class TestOSMNode:
    """Tests for OSMNode dataclass."""

    def test_basic_creation(self):
        """Node can be created with required fields."""
        node = OSMNode(id=123, lat=59.33, lon=18.07)
        assert node.id == 123
        assert node.lat == 59.33
        assert node.lon == 18.07

    def test_default_tags(self):
        """Tags default to empty dict."""
        node = OSMNode(id=1, lat=0, lon=0)
        assert node.tags == {}

    def test_with_tags(self):
        """Node can be created with tags."""
        node = OSMNode(id=1, lat=0, lon=0, tags={'highway': 'traffic_signals'})
        assert node.tags['highway'] == 'traffic_signals'


class TestOSMWay:
    """Tests for OSMWay dataclass."""

    def test_basic_creation(self):
        """Way can be created with required fields."""
        way = OSMWay(id=456, nodes=[1, 2, 3])
        assert way.id == 456
        assert way.nodes == [1, 2, 3]

    def test_default_tags(self):
        """Tags default to empty dict."""
        way = OSMWay(id=1, nodes=[])
        assert way.tags == {}

    def test_default_resolved_coords(self):
        """Resolved coords default to empty list."""
        way = OSMWay(id=1, nodes=[])
        assert way.resolved_coords == []

    def test_with_tags(self):
        """Way can be created with tags."""
        way = OSMWay(id=1, nodes=[1, 2], tags={'highway': 'residential'})
        assert way.tags['highway'] == 'residential'


class TestOSMRelation:
    """Tests for OSMRelation dataclass."""

    def test_basic_creation(self):
        """Relation can be created with required fields."""
        relation = OSMRelation(id=789, members=[])
        assert relation.id == 789
        assert relation.members == []

    def test_with_members(self):
        """Relation can have members."""
        members = [
            {'type': 'way', 'ref': 100, 'role': 'from'},
            {'type': 'node', 'ref': 200, 'role': 'via'},
            {'type': 'way', 'ref': 300, 'role': 'to'}
        ]
        relation = OSMRelation(id=1, members=members, tags={'type': 'restriction'})
        assert len(relation.members) == 3
        assert relation.tags['type'] == 'restriction'


class TestOSMData:
    """Tests for OSMData container."""

    def test_empty_creation(self):
        """OSMData can be created empty."""
        data = OSMData()
        assert data.nodes == {}
        assert data.ways == {}
        assert data.relations == {}

    def test_get_way_coords(self):
        """get_way_coords resolves node IDs to coordinates."""
        data = OSMData()
        data.nodes[1] = OSMNode(id=1, lat=59.0, lon=18.0)
        data.nodes[2] = OSMNode(id=2, lat=59.1, lon=18.1)
        data.nodes[3] = OSMNode(id=3, lat=59.2, lon=18.2)

        way = OSMWay(id=100, nodes=[1, 2, 3])
        coords = data.get_way_coords(way)

        assert len(coords) == 3
        assert coords[0] == (59.0, 18.0)
        assert coords[1] == (59.1, 18.1)
        assert coords[2] == (59.2, 18.2)

    def test_get_way_coords_missing_node(self):
        """get_way_coords handles missing nodes gracefully."""
        data = OSMData()
        data.nodes[1] = OSMNode(id=1, lat=59.0, lon=18.0)
        # Node 2 is missing

        way = OSMWay(id=100, nodes=[1, 2, 3])
        coords = data.get_way_coords(way)

        # Should only return coords for existing nodes
        assert len(coords) == 1
        assert coords[0] == (59.0, 18.0)


class TestOSMParserParseJSON:
    """Tests for OSMParser.parse method."""

    def test_empty_json(self):
        """Empty JSON returns empty OSMData."""
        data = OSMParser.parse({})
        assert len(data.nodes) == 0
        assert len(data.ways) == 0
        assert len(data.relations) == 0

    def test_no_elements(self):
        """JSON without 'elements' returns empty OSMData."""
        data = OSMParser.parse({'version': 0.6})
        assert len(data.nodes) == 0

    def test_parse_node(self):
        """Nodes are parsed correctly."""
        osm_json = {
            'elements': [
                {'type': 'node', 'id': 123, 'lat': 59.33, 'lon': 18.07, 'tags': {'name': 'Test'}}
            ]
        }
        data = OSMParser.parse(osm_json)

        assert 123 in data.nodes
        node = data.nodes[123]
        assert node.lat == 59.33
        assert node.lon == 18.07
        assert node.tags['name'] == 'Test'

    def test_parse_node_without_tags(self):
        """Nodes without tags are parsed correctly."""
        osm_json = {
            'elements': [
                {'type': 'node', 'id': 123, 'lat': 59.33, 'lon': 18.07}
            ]
        }
        data = OSMParser.parse(osm_json)
        assert data.nodes[123].tags == {}

    def test_parse_way(self):
        """Ways are parsed correctly."""
        osm_json = {
            'elements': [
                {'type': 'node', 'id': 1, 'lat': 59.0, 'lon': 18.0},
                {'type': 'node', 'id': 2, 'lat': 59.1, 'lon': 18.1},
                {'type': 'way', 'id': 100, 'nodes': [1, 2], 'tags': {'highway': 'residential'}}
            ]
        }
        data = OSMParser.parse(osm_json)

        assert 100 in data.ways
        way = data.ways[100]
        assert way.nodes == [1, 2]
        assert way.tags['highway'] == 'residential'
        assert len(way.resolved_coords) == 2
        assert way.resolved_coords[0] == (59.0, 18.0)

    def test_parse_relation(self):
        """Relations are parsed correctly."""
        osm_json = {
            'elements': [
                {
                    'type': 'relation', 'id': 500,
                    'members': [
                        {'type': 'way', 'ref': 100, 'role': 'from'},
                        {'type': 'node', 'ref': 200, 'role': 'via'},
                        {'type': 'way', 'ref': 300, 'role': 'to'}
                    ],
                    'tags': {'type': 'restriction', 'restriction': 'no_left_turn'}
                }
            ]
        }
        data = OSMParser.parse(osm_json)

        assert 500 in data.relations
        relation = data.relations[500]
        assert len(relation.members) == 3
        assert relation.members[0]['role'] == 'from'
        assert relation.tags['type'] == 'restriction'

    def test_duplicate_node_merges_tags(self):
        """Duplicate nodes merge their tags."""
        osm_json = {
            'elements': [
                # First occurrence with tags
                {'type': 'node', 'id': 123, 'lat': 59.33, 'lon': 18.07, 'tags': {'name': 'Test'}},
                # Second occurrence without tags (from skel output)
                {'type': 'node', 'id': 123, 'lat': 59.33, 'lon': 18.07}
            ]
        }
        data = OSMParser.parse(osm_json)

        # Tags should be preserved from first occurrence
        assert data.nodes[123].tags['name'] == 'Test'

    def test_duplicate_node_updates_tags(self):
        """Duplicate nodes update with new tags."""
        osm_json = {
            'elements': [
                # First occurrence without tags
                {'type': 'node', 'id': 123, 'lat': 59.33, 'lon': 18.07},
                # Second occurrence with tags
                {'type': 'node', 'id': 123, 'lat': 59.33, 'lon': 18.07, 'tags': {'name': 'Test'}}
            ]
        }
        data = OSMParser.parse(osm_json)

        # Tags should be added from second occurrence
        assert data.nodes[123].tags['name'] == 'Test'


class TestOSMParserParseXML:
    """Tests for OSMParser.parse_xml method."""

    def test_parse_simple_xml(self):
        """Simple XML is parsed correctly."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <osm version="0.6">
            <node id="123" lat="59.33" lon="18.07">
                <tag k="name" v="Test"/>
            </node>
        </osm>"""

        data = OSMParser.parse_xml(xml)

        assert 123 in data.nodes
        assert data.nodes[123].lat == 59.33
        assert data.nodes[123].tags['name'] == 'Test'

    def test_parse_xml_way(self):
        """XML ways are parsed correctly."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <osm version="0.6">
            <node id="1" lat="59.0" lon="18.0"/>
            <node id="2" lat="59.1" lon="18.1"/>
            <way id="100">
                <nd ref="1"/>
                <nd ref="2"/>
                <tag k="highway" v="residential"/>
            </way>
        </osm>"""

        data = OSMParser.parse_xml(xml)

        assert 100 in data.ways
        way = data.ways[100]
        assert way.nodes == [1, 2]
        assert way.tags['highway'] == 'residential'
        assert len(way.resolved_coords) == 2

    def test_parse_xml_relation(self):
        """XML relations are parsed correctly."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <osm version="0.6">
            <relation id="500">
                <member type="way" ref="100" role="from"/>
                <member type="node" ref="200" role="via"/>
                <tag k="type" v="restriction"/>
            </relation>
        </osm>"""

        data = OSMParser.parse_xml(xml)

        assert 500 in data.relations
        relation = data.relations[500]
        assert len(relation.members) == 2
        assert relation.members[0] == {'type': 'way', 'ref': 100, 'role': 'from'}
        assert relation.tags['type'] == 'restriction'


class TestOSMParserFilters:
    """Tests for OSMParser filter methods."""

    @pytest.fixture
    def sample_data(self):
        """Create sample OSM data."""
        data = OSMData()

        # Nodes
        data.nodes[1] = OSMNode(id=1, lat=59.0, lon=18.0, tags={'highway': 'traffic_signals'})
        data.nodes[2] = OSMNode(id=2, lat=59.1, lon=18.1, tags={'highway': 'stop'})
        data.nodes[3] = OSMNode(id=3, lat=59.2, lon=18.2, tags={'traffic_sign': 'SE:C31-50'})
        data.nodes[4] = OSMNode(id=4, lat=59.3, lon=18.3, tags={'maxspeed': '50'})
        data.nodes[5] = OSMNode(id=5, lat=59.4, lon=18.4, tags={'highway': 'street_lamp'})
        data.nodes[6] = OSMNode(id=6, lat=59.5, lon=18.5, tags={'natural': 'tree'})
        data.nodes[7] = OSMNode(id=7, lat=59.6, lon=18.6, tags={'highway': 'give_way'})
        data.nodes[8] = OSMNode(id=8, lat=59.7, lon=18.7, tags={'highway': 'crossing'})
        data.nodes[9] = OSMNode(id=9, lat=59.8, lon=18.8, tags={'amenity': 'parking'})

        # Ways
        data.ways[100] = OSMWay(id=100, nodes=[1, 2], tags={'highway': 'residential'})
        data.ways[101] = OSMWay(id=101, nodes=[2, 3], tags={'highway': 'primary'})
        data.ways[102] = OSMWay(id=102, nodes=[3, 4], tags={'building': 'yes'})
        data.ways[103] = OSMWay(id=103, nodes=[4, 5], tags={'barrier': 'guard_rail'})
        data.ways[104] = OSMWay(id=104, nodes=[5, 6, 5], tags={'junction': 'roundabout', 'highway': 'primary'})
        data.ways[105] = OSMWay(id=105, nodes=[6, 7], tags={'amenity': 'parking'})

        return data

    def test_get_highway_ways(self, sample_data):
        """get_highway_ways returns ways with highway tag."""
        ways = OSMParser.get_highway_ways(sample_data)

        highway_ids = [w.id for w in ways]
        assert 100 in highway_ids
        assert 101 in highway_ids
        assert 104 in highway_ids  # Roundabout also has highway tag
        assert 102 not in highway_ids  # Building
        assert 103 not in highway_ids  # Guardrail

    def test_get_traffic_signal_nodes(self, sample_data):
        """get_traffic_signal_nodes returns traffic signal nodes."""
        signals = OSMParser.get_traffic_signal_nodes(sample_data)

        signal_ids = [n.id for n in signals]
        assert 1 in signal_ids
        assert len(signal_ids) == 1

    def test_get_traffic_sign_nodes(self, sample_data):
        """get_traffic_sign_nodes returns traffic sign nodes."""
        signs = OSMParser.get_traffic_sign_nodes(sample_data)

        sign_ids = [n.id for n in signs]
        assert 2 in sign_ids  # highway=stop
        assert 3 in sign_ids  # traffic_sign tag
        assert 4 in sign_ids  # maxspeed tag
        assert 7 in sign_ids  # highway=give_way
        assert 8 in sign_ids  # highway=crossing
        assert 1 not in sign_ids  # traffic_signals are signals, not signs

    def test_get_street_lamp_nodes(self, sample_data):
        """get_street_lamp_nodes returns street lamp nodes."""
        lamps = OSMParser.get_street_lamp_nodes(sample_data)

        lamp_ids = [n.id for n in lamps]
        assert 5 in lamp_ids
        assert len(lamp_ids) == 1

    def test_get_tree_nodes(self, sample_data):
        """get_tree_nodes returns tree nodes."""
        trees = OSMParser.get_tree_nodes(sample_data)

        tree_ids = [n.id for n in trees]
        assert 6 in tree_ids
        assert len(tree_ids) == 1

    def test_get_building_ways(self, sample_data):
        """get_building_ways returns building ways."""
        buildings = OSMParser.get_building_ways(sample_data)

        building_ids = [w.id for w in buildings]
        assert 102 in building_ids
        assert len(building_ids) == 1

    def test_get_guardrail_ways(self, sample_data):
        """get_guardrail_ways returns guardrail ways."""
        guardrails = OSMParser.get_guardrail_ways(sample_data)

        guardrail_ids = [w.id for w in guardrails]
        assert 103 in guardrail_ids
        assert len(guardrail_ids) == 1

    def test_get_roundabout_ways(self, sample_data):
        """get_roundabout_ways returns roundabout ways."""
        roundabouts = OSMParser.get_roundabout_ways(sample_data)

        roundabout_ids = [w.id for w in roundabouts]
        assert 104 in roundabout_ids
        assert len(roundabout_ids) == 1

    def test_get_parking_ways(self, sample_data):
        """get_parking_ways returns parking ways."""
        parking = OSMParser.get_parking_ways(sample_data)

        parking_ids = [w.id for w in parking]
        assert 105 in parking_ids
        assert len(parking_ids) == 1

    def test_get_parking_nodes(self, sample_data):
        """get_parking_nodes returns parking nodes."""
        parking = OSMParser.get_parking_nodes(sample_data)

        parking_ids = [n.id for n in parking]
        assert 9 in parking_ids
        assert len(parking_ids) == 1


class TestIsClosedWay:
    """Tests for OSMParser.is_closed_way method."""

    def test_closed_way(self):
        """Closed way returns True."""
        way = OSMWay(id=1, nodes=[1, 2, 3, 4, 1])
        assert OSMParser.is_closed_way(way) is True

    def test_open_way(self):
        """Open way returns False."""
        way = OSMWay(id=1, nodes=[1, 2, 3, 4])
        assert OSMParser.is_closed_way(way) is False

    def test_two_node_way(self):
        """Way with only 2 nodes is not closed."""
        way = OSMWay(id=1, nodes=[1, 1])  # Same node but only 2
        assert OSMParser.is_closed_way(way) is False

    def test_single_node_way(self):
        """Way with single node is not closed."""
        way = OSMWay(id=1, nodes=[1])
        assert OSMParser.is_closed_way(way) is False

    def test_empty_way(self):
        """Empty way is not closed."""
        way = OSMWay(id=1, nodes=[])
        assert OSMParser.is_closed_way(way) is False


class TestParseOsmData:
    """Tests for parse_osm_data convenience function."""

    def test_parses_json(self):
        """Convenience function parses JSON correctly."""
        osm_json = {
            'elements': [
                {'type': 'node', 'id': 123, 'lat': 59.33, 'lon': 18.07}
            ]
        }
        data = parse_osm_data(osm_json)

        assert 123 in data.nodes
        assert isinstance(data, OSMData)

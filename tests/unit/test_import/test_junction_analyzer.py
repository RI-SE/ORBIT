"""Tests for orbit.import.junction_analyzer module."""

import math
import pytest
from typing import List, Dict
import importlib

# Import using importlib since 'import' is a reserved keyword
junction_analyzer = importlib.import_module('orbit.import.junction_analyzer')

# Import the classes and functions we need to test
RoadEndpointInfo = junction_analyzer.RoadEndpointInfo
ConnectionPattern = junction_analyzer.ConnectionPattern
normalize_angle = junction_analyzer.normalize_angle
calculate_heading = junction_analyzer.calculate_heading
classify_turn_type = junction_analyzer.classify_turn_type
get_road_endpoint_heading = junction_analyzer.get_road_endpoint_heading
analyze_junction_geometry = junction_analyzer.analyze_junction_geometry
detect_connection_patterns = junction_analyzer.detect_connection_patterns
filter_unlikely_connections = junction_analyzer.filter_unlikely_connections
generate_lane_links_for_connection = junction_analyzer.generate_lane_links_for_connection
clear_cross_junction_links = junction_analyzer.clear_cross_junction_links
generate_junction_connections = junction_analyzer.generate_junction_connections

from orbit.models import Junction, Road, Polyline, LineType


class TestNormalizeAngle:
    """Tests for normalize_angle function."""

    def test_angle_in_range(self):
        """Angle already in [-π, π] stays unchanged."""
        assert normalize_angle(0.0) == pytest.approx(0.0)
        assert normalize_angle(math.pi / 2) == pytest.approx(math.pi / 2)
        assert normalize_angle(-math.pi / 2) == pytest.approx(-math.pi / 2)
        assert normalize_angle(math.pi - 0.1) == pytest.approx(math.pi - 0.1)
        assert normalize_angle(-math.pi + 0.1) == pytest.approx(-math.pi + 0.1)

    def test_angle_above_pi(self):
        """Angle > π gets normalized to [-π, π]."""
        assert normalize_angle(2 * math.pi) == pytest.approx(0.0, abs=1e-10)
        assert normalize_angle(3 * math.pi / 2) == pytest.approx(-math.pi / 2)
        assert normalize_angle(math.pi + 0.5) == pytest.approx(-math.pi + 0.5)

    def test_angle_below_negative_pi(self):
        """Angle < -π gets normalized to [-π, π]."""
        assert normalize_angle(-2 * math.pi) == pytest.approx(0.0, abs=1e-10)
        assert normalize_angle(-3 * math.pi / 2) == pytest.approx(math.pi / 2)
        assert normalize_angle(-math.pi - 0.5) == pytest.approx(math.pi - 0.5)

    def test_large_positive_angle(self):
        """Very large positive angle gets normalized."""
        assert normalize_angle(5 * math.pi) == pytest.approx(math.pi, abs=1e-10)
        assert normalize_angle(6 * math.pi) == pytest.approx(0.0, abs=1e-10)

    def test_large_negative_angle(self):
        """Very large negative angle gets normalized."""
        assert normalize_angle(-5 * math.pi) == pytest.approx(-math.pi, abs=1e-10)
        assert normalize_angle(-6 * math.pi) == pytest.approx(0.0, abs=1e-10)


class TestCalculateHeading:
    """Tests for calculate_heading function."""

    def test_heading_east(self):
        """Heading to the east is 0."""
        heading = calculate_heading((0, 0), (100, 0))
        assert heading == pytest.approx(0.0)

    def test_heading_north(self):
        """Heading to the north (positive Y) is π/2."""
        heading = calculate_heading((0, 0), (0, 100))
        assert heading == pytest.approx(math.pi / 2)

    def test_heading_south(self):
        """Heading to the south (negative Y) is -π/2."""
        heading = calculate_heading((0, 0), (0, -100))
        assert heading == pytest.approx(-math.pi / 2)

    def test_heading_west(self):
        """Heading to the west is π (or -π)."""
        heading = calculate_heading((0, 0), (-100, 0))
        assert abs(heading) == pytest.approx(math.pi)

    def test_heading_northeast(self):
        """Heading to the northeast is π/4."""
        heading = calculate_heading((0, 0), (100, 100))
        assert heading == pytest.approx(math.pi / 4)

    def test_heading_southeast(self):
        """Heading to the southeast is -π/4."""
        heading = calculate_heading((0, 0), (100, -100))
        assert heading == pytest.approx(-math.pi / 4)

    def test_heading_from_nonorigin(self):
        """Heading calculation works from non-origin points."""
        heading = calculate_heading((50, 50), (150, 50))
        assert heading == pytest.approx(0.0)


class TestClassifyTurnType:
    """Tests for classify_turn_type function."""

    def test_straight(self):
        """Small angle changes are classified as straight."""
        assert classify_turn_type(0.0) == "straight"
        assert classify_turn_type(math.radians(15)) == "straight"
        assert classify_turn_type(math.radians(-15)) == "straight"
        assert classify_turn_type(math.radians(29)) == "straight"
        assert classify_turn_type(math.radians(-29)) == "straight"

    def test_right_turn(self):
        """Negative angle changes are right turns (clockwise)."""
        assert classify_turn_type(math.radians(-45)) == "right"
        assert classify_turn_type(math.radians(-90)) == "right"
        assert classify_turn_type(math.radians(-120)) == "right"
        assert classify_turn_type(math.radians(-149)) == "right"

    def test_left_turn(self):
        """Positive angle changes are left turns (counterclockwise)."""
        assert classify_turn_type(math.radians(45)) == "left"
        assert classify_turn_type(math.radians(90)) == "left"
        assert classify_turn_type(math.radians(120)) == "left"
        assert classify_turn_type(math.radians(149)) == "left"

    def test_uturn(self):
        """Large angle changes are U-turns."""
        assert classify_turn_type(math.radians(160)) == "uturn"
        assert classify_turn_type(math.radians(-160)) == "uturn"
        assert classify_turn_type(math.radians(180)) == "uturn"
        assert classify_turn_type(math.radians(-180)) == "uturn"

    def test_boundary_straight_to_turn(self):
        """30 degree threshold separates straight from turn."""
        assert classify_turn_type(math.radians(29.9)) == "straight"
        assert classify_turn_type(math.radians(30.1)) == "left"
        assert classify_turn_type(math.radians(-30.1)) == "right"

    def test_boundary_turn_to_uturn(self):
        """150 degree threshold separates turn from U-turn."""
        assert classify_turn_type(math.radians(149)) == "left"
        assert classify_turn_type(math.radians(151)) == "uturn"
        assert classify_turn_type(math.radians(-149)) == "right"
        assert classify_turn_type(math.radians(-151)) == "uturn"


class TestRoadEndpointInfo:
    """Tests for RoadEndpointInfo dataclass."""

    def test_basic_creation(self):
        """Create RoadEndpointInfo with required fields."""
        endpoint = RoadEndpointInfo(
            road_id="road1",
            road_name="Test Road",
            position=(100.0, 200.0),
            heading=math.pi / 2,
            at_junction="end",
            is_incoming=True,
            is_outgoing=True,
            left_lane_count=1,
            right_lane_count=1,
            lane_width=3.5
        )

        assert endpoint.road_id == "road1"
        assert endpoint.road_name == "Test Road"
        assert endpoint.position == (100.0, 200.0)
        assert endpoint.heading == pytest.approx(math.pi / 2)
        assert endpoint.at_junction == "end"
        assert endpoint.is_incoming is True
        assert endpoint.is_outgoing is True
        assert endpoint.left_lane_count == 1
        assert endpoint.right_lane_count == 1
        assert endpoint.lane_width == 3.5

    def test_default_values(self):
        """Default values are set correctly."""
        endpoint = RoadEndpointInfo(
            road_id="road1",
            road_name="Test Road",
            position=(0.0, 0.0),
            heading=0.0,
            at_junction="start",
            is_incoming=True,
            is_outgoing=True,
            left_lane_count=1,
            right_lane_count=1,
            lane_width=3.5
        )

        assert endpoint.relative_angle == 0.0
        assert endpoint.position_geo is None
        assert endpoint.direction_geo is None

    def test_get_right_lane_center_position_no_flip(self):
        """Calculate right lane center position without flip."""
        endpoint = RoadEndpointInfo(
            road_id="road1",
            road_name="Test Road",
            position=(100.0, 100.0),
            heading=0.0,  # Heading east
            at_junction="end",
            is_incoming=True,
            is_outgoing=True,
            left_lane_count=1,
            right_lane_count=1,
            lane_width=3.5
        )

        # Scale: 1 meter = 10 pixels
        scale = 0.1  # meters per pixel

        pos = endpoint.get_right_lane_center_position(scale, flip_heading=False)

        # Heading east (0), right side is south (negative Y)
        # 1 right lane, offset = 0.5 * 3.5 / 0.1 = 17.5 pixels south
        expected_x = 100.0
        expected_y = 100.0 - 17.5  # South of centerline (image coords, Y increases down)

        # Actually in standard math coords with heading 0 (east), right is -pi/2 (south)
        # cos(-pi/2) = 0, sin(-pi/2) = -1
        # So offset is (0, -17.5), resulting in (100, 82.5)
        assert pos[0] == pytest.approx(100.0, abs=0.1)
        assert pos[1] == pytest.approx(82.5, abs=0.1)

    def test_get_right_lane_center_position_with_flip(self):
        """Calculate right lane center position with heading flip."""
        endpoint = RoadEndpointInfo(
            road_id="road1",
            road_name="Test Road",
            position=(100.0, 100.0),
            heading=0.0,  # Heading east
            at_junction="end",
            is_incoming=True,
            is_outgoing=True,
            left_lane_count=1,
            right_lane_count=1,
            lane_width=3.5
        )

        scale = 0.1  # meters per pixel

        pos = endpoint.get_right_lane_center_position(scale, flip_heading=True)

        # Flipped heading is π (west), right side is now north (positive Y)
        # offset is (0, +17.5), resulting in (100, 117.5)
        assert pos[0] == pytest.approx(100.0, abs=0.1)
        assert pos[1] == pytest.approx(117.5, abs=0.1)

    def test_get_right_lane_center_no_right_lanes(self):
        """Position is centerline when no right lanes."""
        endpoint = RoadEndpointInfo(
            road_id="road1",
            road_name="Test Road",
            position=(100.0, 100.0),
            heading=0.0,
            at_junction="end",
            is_incoming=True,
            is_outgoing=True,
            left_lane_count=2,
            right_lane_count=0,  # No right lanes
            lane_width=3.5
        )

        scale = 0.1

        pos = endpoint.get_right_lane_center_position(scale)

        # With 0 right lanes, offset is 0, position is centerline
        assert pos[0] == pytest.approx(100.0)
        assert pos[1] == pytest.approx(100.0)


class TestConnectionPattern:
    """Tests for ConnectionPattern dataclass."""

    def test_basic_creation(self):
        """Create ConnectionPattern with required fields."""
        from_endpoint = RoadEndpointInfo(
            road_id="road1", road_name="Road 1", position=(0, 0),
            heading=0, at_junction="end", is_incoming=True, is_outgoing=True,
            left_lane_count=1, right_lane_count=1, lane_width=3.5
        )
        to_endpoint = RoadEndpointInfo(
            road_id="road2", road_name="Road 2", position=(100, 100),
            heading=math.pi/2, at_junction="start", is_incoming=True, is_outgoing=True,
            left_lane_count=1, right_lane_count=1, lane_width=3.5
        )

        pattern = ConnectionPattern(
            from_road_id="road1",
            to_road_id="road2",
            turn_type="left",
            turn_angle=math.pi / 2,
            from_endpoint=from_endpoint,
            to_endpoint=to_endpoint
        )

        assert pattern.from_road_id == "road1"
        assert pattern.to_road_id == "road2"
        assert pattern.turn_type == "left"
        assert pattern.turn_angle == pytest.approx(math.pi / 2)
        assert pattern.priority == 0  # Default


class TestGetRoadEndpointHeading:
    """Tests for get_road_endpoint_heading function."""

    @pytest.fixture
    def sample_road(self):
        """Create a sample road."""
        return Road(name="Test Road", centerline_id="cl1", polyline_ids=["cl1"])

    def test_heading_at_end(self, sample_road):
        """Calculate heading at end of road."""
        polyline = Polyline(line_type=LineType.CENTERLINE)
        polyline.add_point(0.0, 0.0)
        polyline.add_point(50.0, 0.0)
        polyline.add_point(100.0, 0.0)

        heading = get_road_endpoint_heading(sample_road, polyline, "end")

        # Last segment is from (50, 0) to (100, 0) - heading east
        assert heading == pytest.approx(0.0)

    def test_heading_at_start(self, sample_road):
        """Calculate heading at start of road."""
        polyline = Polyline(line_type=LineType.CENTERLINE)
        polyline.add_point(0.0, 0.0)
        polyline.add_point(50.0, 0.0)
        polyline.add_point(100.0, 0.0)

        heading = get_road_endpoint_heading(sample_road, polyline, "start")

        # First segment is from (0, 0) to (50, 0) - heading east
        assert heading == pytest.approx(0.0)

    def test_heading_at_end_diagonal(self, sample_road):
        """Calculate heading at end with diagonal segment."""
        polyline = Polyline(line_type=LineType.CENTERLINE)
        polyline.add_point(0.0, 0.0)
        polyline.add_point(50.0, 50.0)
        polyline.add_point(100.0, 100.0)

        heading = get_road_endpoint_heading(sample_road, polyline, "end")

        # Heading northeast (45 degrees)
        assert heading == pytest.approx(math.pi / 4)

    def test_heading_single_segment(self, sample_road):
        """Calculate heading with minimum points."""
        polyline = Polyline(line_type=LineType.CENTERLINE)
        polyline.add_point(0.0, 0.0)
        polyline.add_point(100.0, 0.0)

        heading_start = get_road_endpoint_heading(sample_road, polyline, "start")
        heading_end = get_road_endpoint_heading(sample_road, polyline, "end")

        assert heading_start == pytest.approx(0.0)
        assert heading_end == pytest.approx(0.0)

    def test_heading_insufficient_points(self, sample_road):
        """Returns 0 for polyline with insufficient points."""
        polyline = Polyline(line_type=LineType.CENTERLINE)
        polyline.add_point(0.0, 0.0)  # Only one point

        heading = get_road_endpoint_heading(sample_road, polyline, "end")

        assert heading == 0.0


class TestGenerateLaneLinks:
    """Tests for generate_lane_links_for_connection function."""

    @pytest.fixture
    def from_endpoint_at_end(self):
        """Endpoint at road end (right lanes are used)."""
        return RoadEndpointInfo(
            road_id="road1", road_name="Road 1", position=(0, 0),
            heading=0, at_junction="end", is_incoming=True, is_outgoing=True,
            left_lane_count=1, right_lane_count=2, lane_width=3.5
        )

    @pytest.fixture
    def to_endpoint_at_start(self):
        """Endpoint at road start (right lanes are used)."""
        return RoadEndpointInfo(
            road_id="road2", road_name="Road 2", position=(100, 0),
            heading=0, at_junction="start", is_incoming=True, is_outgoing=True,
            left_lane_count=1, right_lane_count=2, lane_width=3.5
        )

    @pytest.fixture
    def from_endpoint_at_start(self):
        """Endpoint at road start (left lanes are used)."""
        return RoadEndpointInfo(
            road_id="road1", road_name="Road 1", position=(0, 0),
            heading=0, at_junction="start", is_incoming=True, is_outgoing=True,
            left_lane_count=2, right_lane_count=1, lane_width=3.5
        )

    @pytest.fixture
    def to_endpoint_at_end(self):
        """Endpoint at road end (left lanes are used)."""
        return RoadEndpointInfo(
            road_id="road2", road_name="Road 2", position=(100, 0),
            heading=math.pi, at_junction="end", is_incoming=True, is_outgoing=True,
            left_lane_count=2, right_lane_count=1, lane_width=3.5
        )

    def test_straight_connection_right_lanes(self, from_endpoint_at_end, to_endpoint_at_start):
        """Straight connection with right lanes (end -> start)."""
        links = generate_lane_links_for_connection(
            from_endpoint_at_end, to_endpoint_at_start, "straight"
        )

        # From has 2 right lanes (-1, -2), to has 2 right lanes (-1, -2)
        # 1-to-1 mapping
        assert len(links) == 2
        assert (-1, -1) in links
        assert (-2, -2) in links

    def test_right_turn(self, from_endpoint_at_end, to_endpoint_at_start):
        """Right turn connection."""
        links = generate_lane_links_for_connection(
            from_endpoint_at_end, to_endpoint_at_start, "right"
        )

        # Same as straight - 1-to-1 mapping
        assert len(links) == 2
        assert (-1, -1) in links
        assert (-2, -2) in links

    def test_left_turn(self, from_endpoint_at_end, to_endpoint_at_start):
        """Left turn connection."""
        links = generate_lane_links_for_connection(
            from_endpoint_at_end, to_endpoint_at_start, "left"
        )

        # Same as straight - 1-to-1 mapping
        assert len(links) == 2

    def test_uturn(self, from_endpoint_at_end, to_endpoint_at_start):
        """U-turn connection only links single lane."""
        links = generate_lane_links_for_connection(
            from_endpoint_at_end, to_endpoint_at_start, "uturn"
        )

        # U-turns typically single lane
        assert len(links) == 1
        assert (-1, -1) in links

    def test_unequal_lane_counts(self):
        """Unequal lane counts uses minimum."""
        from_endpoint = RoadEndpointInfo(
            road_id="road1", road_name="Road 1", position=(0, 0),
            heading=0, at_junction="end", is_incoming=True, is_outgoing=True,
            left_lane_count=1, right_lane_count=3, lane_width=3.5
        )
        to_endpoint = RoadEndpointInfo(
            road_id="road2", road_name="Road 2", position=(100, 0),
            heading=0, at_junction="start", is_incoming=True, is_outgoing=True,
            left_lane_count=1, right_lane_count=1, lane_width=3.5
        )

        links = generate_lane_links_for_connection(from_endpoint, to_endpoint, "straight")

        # Min(3, 1) = 1 lane link
        assert len(links) == 1
        assert (-1, -1) in links

    def test_left_lane_connection(self, from_endpoint_at_start, to_endpoint_at_end):
        """Connection using left lanes (start -> end)."""
        links = generate_lane_links_for_connection(
            from_endpoint_at_start, to_endpoint_at_end, "straight"
        )

        # From start uses left lanes (1, 2), to end uses left lanes (1, 2)
        assert len(links) == 2
        assert (1, 1) in links
        assert (2, 2) in links


class TestAnalyzeJunctionGeometry:
    """Tests for analyze_junction_geometry function."""

    def test_empty_junction(self):
        """Junction with no connected roads."""
        junction = Junction(name="Empty Junction")
        junction.center_point = (500.0, 500.0)

        result = analyze_junction_geometry(junction, {}, {})

        assert result['endpoints'] == []
        assert result['center'] == (500.0, 500.0)
        assert result['radius'] == 0.0

    def test_junction_missing_roads(self):
        """Junction with connected_road_ids that don't exist in dict."""
        junction = Junction(name="Test Junction")
        junction.center_point = (500.0, 500.0)
        junction.connected_road_ids = ["nonexistent_road"]

        result = analyze_junction_geometry(junction, {}, {})

        assert result['endpoints'] == []

    def test_simple_junction(self):
        """Junction with two roads connecting."""
        # Create junction at (100, 100)
        junction = Junction(name="Test Junction")
        junction.center_point = (100.0, 100.0)

        # Create road 1 ending at junction
        poly1 = Polyline(line_type=LineType.CENTERLINE)
        poly1.add_point(0.0, 100.0)
        poly1.add_point(50.0, 100.0)
        poly1.add_point(100.0, 100.0)  # Ends at junction

        road1 = Road(name="Road 1", centerline_id=poly1.id, polyline_ids=[poly1.id])

        # Create road 2 starting at junction
        poly2 = Polyline(line_type=LineType.CENTERLINE)
        poly2.add_point(100.0, 100.0)  # Starts at junction
        poly2.add_point(150.0, 100.0)
        poly2.add_point(200.0, 100.0)

        road2 = Road(name="Road 2", centerline_id=poly2.id, polyline_ids=[poly2.id])

        junction.connected_road_ids = [road1.id, road2.id]

        roads_dict = {road1.id: road1, road2.id: road2}
        polylines_dict = {poly1.id: poly1, poly2.id: poly2}

        result = analyze_junction_geometry(junction, roads_dict, polylines_dict)

        # Should find 2 endpoints
        assert len(result['endpoints']) == 2

        # Verify center
        assert result['center'] == (100.0, 100.0)

    def test_junction_skip_distance_check(self):
        """Junction analysis with skip_distance_check enabled."""
        junction = Junction(name="Test Junction")
        junction.center_point = (100.0, 100.0)

        # Create road with endpoint far from junction center
        poly1 = Polyline(line_type=LineType.CENTERLINE)
        poly1.add_point(0.0, 0.0)
        poly1.add_point(50.0, 0.0)

        road1 = Road(name="Road 1", centerline_id=poly1.id, polyline_ids=[poly1.id])
        junction.connected_road_ids = [road1.id]

        roads_dict = {road1.id: road1}
        polylines_dict = {poly1.id: poly1}

        # Without skip_distance_check, endpoint is too far (>10 pixels)
        result = analyze_junction_geometry(junction, roads_dict, polylines_dict, skip_distance_check=False)
        assert len(result['endpoints']) == 0

        # With skip_distance_check=True, endpoint is included
        result = analyze_junction_geometry(junction, roads_dict, polylines_dict, skip_distance_check=True)
        assert len(result['endpoints']) == 1


class TestDetectConnectionPatterns:
    """Tests for detect_connection_patterns function."""

    def test_empty_geometry(self):
        """No patterns from empty geometry info."""
        geometry_info = {
            'endpoints': [],
            'center': (0, 0),
            'radius': 0
        }

        patterns = detect_connection_patterns(geometry_info)

        assert patterns == []

    def test_single_endpoint(self):
        """No patterns with only one endpoint."""
        endpoint = RoadEndpointInfo(
            road_id="road1", road_name="Road 1", position=(0, 0),
            heading=0, at_junction="end", is_incoming=True, is_outgoing=True,
            left_lane_count=1, right_lane_count=1, lane_width=3.5
        )

        geometry_info = {
            'endpoints': [endpoint],
            'center': (0, 0),
            'radius': 10
        }

        patterns = detect_connection_patterns(geometry_info)

        assert patterns == []

    def test_two_endpoints_straight(self):
        """Two opposite endpoints create straight patterns."""
        endpoint1 = RoadEndpointInfo(
            road_id="road1", road_name="Road 1", position=(-50, 0),
            heading=0,  # Pointing east toward junction
            at_junction="end", is_incoming=True, is_outgoing=True,
            left_lane_count=1, right_lane_count=1, lane_width=3.5
        )
        endpoint2 = RoadEndpointInfo(
            road_id="road2", road_name="Road 2", position=(50, 0),
            heading=0,  # Also pointing east (away from junction for "start")
            at_junction="start", is_incoming=True, is_outgoing=True,
            left_lane_count=1, right_lane_count=1, lane_width=3.5
        )

        geometry_info = {
            'endpoints': [endpoint1, endpoint2],
            'center': (0, 0),
            'radius': 50
        }

        patterns = detect_connection_patterns(geometry_info)

        # Should have 2 patterns: road1->road2 and road2->road1
        assert len(patterns) == 2

        # Check turn types (should be straight)
        turn_types = [p.turn_type for p in patterns]
        assert "straight" in turn_types


class TestFilterUnlikelyConnections:
    """Tests for filter_unlikely_connections function."""

    def test_returns_all_patterns(self):
        """Currently returns all patterns (no filtering implemented)."""
        endpoint1 = RoadEndpointInfo(
            road_id="road1", road_name="Road 1", position=(0, 0),
            heading=0, at_junction="end", is_incoming=True, is_outgoing=True,
            left_lane_count=1, right_lane_count=1, lane_width=3.5
        )
        endpoint2 = RoadEndpointInfo(
            road_id="road2", road_name="Road 2", position=(100, 0),
            heading=0, at_junction="start", is_incoming=True, is_outgoing=True,
            left_lane_count=1, right_lane_count=1, lane_width=3.5
        )

        pattern = ConnectionPattern(
            from_road_id="road1",
            to_road_id="road2",
            turn_type="straight",
            turn_angle=0.0,
            from_endpoint=endpoint1,
            to_endpoint=endpoint2,
            priority=3
        )

        filtered = filter_unlikely_connections([pattern], {})

        # Currently no filtering - returns all
        assert len(filtered) == 1
        assert filtered[0] is pattern


class TestClearCrossJunctionLinks:
    """Tests for clear_cross_junction_links function."""

    def test_clear_links_between_connected_roads(self):
        """Clear predecessor/successor links between roads in junction."""
        # Create roads with links to each other
        road1 = Road(name="Road 1", centerline_id="cl1", polyline_ids=["cl1"])
        road2 = Road(name="Road 2", centerline_id="cl2", polyline_ids=["cl2"])

        road1.successor_id = road2.id
        road2.predecessor_id = road1.id

        # Create junction with both roads
        junction = Junction(name="Test Junction")
        junction.connected_road_ids = [road1.id, road2.id]

        roads_dict = {road1.id: road1, road2.id: road2}

        clear_cross_junction_links(junction, roads_dict)

        # Links should be cleared
        assert road1.successor_id is None
        assert road2.predecessor_id is None

    def test_preserve_external_links(self):
        """Links to roads outside junction are preserved."""
        road1 = Road(name="Road 1", centerline_id="cl1", polyline_ids=["cl1"])
        road2 = Road(name="Road 2", centerline_id="cl2", polyline_ids=["cl2"])
        road3 = Road(name="Road 3", centerline_id="cl3", polyline_ids=["cl3"])

        # road1 -> road2 (both in junction)
        # road2 -> road3 (road3 outside junction)
        road1.successor_id = road2.id
        road2.predecessor_id = road1.id
        road2.successor_id = road3.id

        junction = Junction(name="Test Junction")
        junction.connected_road_ids = [road1.id, road2.id]

        roads_dict = {road1.id: road1, road2.id: road2, road3.id: road3}

        clear_cross_junction_links(junction, roads_dict)

        # Cross-junction links cleared
        assert road1.successor_id is None
        assert road2.predecessor_id is None

        # External link preserved
        assert road2.successor_id == road3.id


class TestGenerateJunctionConnections:
    """Tests for generate_junction_connections function."""

    def test_skip_virtual_junction(self):
        """Virtual junctions are skipped."""
        junction = Junction(name="Virtual Junction", junction_type="virtual")
        junction.center_point = (100.0, 100.0)
        junction.connected_road_ids = ["road1", "road2"]

        # Should not modify junction
        generate_junction_connections(junction, {}, {})

        assert len(junction.connecting_roads) == 0
        assert len(junction.lane_connections) == 0

    def test_junction_with_no_roads(self):
        """Junction with no valid roads gets no connections."""
        junction = Junction(name="Empty Junction")
        junction.center_point = (100.0, 100.0)
        junction.connected_road_ids = []

        generate_junction_connections(junction, {}, {})

        assert len(junction.connecting_roads) == 0

    def test_simple_two_road_junction(self):
        """Junction with two roads creates connections."""
        junction = Junction(name="Test Junction")
        junction.center_point = (100.0, 100.0)

        # Create road 1 ending at junction
        poly1 = Polyline(line_type=LineType.CENTERLINE)
        poly1.add_point(0.0, 100.0)
        poly1.add_point(50.0, 100.0)
        poly1.add_point(100.0, 100.0)

        road1 = Road(name="Road 1", centerline_id=poly1.id, polyline_ids=[poly1.id])

        # Create road 2 starting at junction
        poly2 = Polyline(line_type=LineType.CENTERLINE)
        poly2.add_point(100.0, 100.0)
        poly2.add_point(150.0, 100.0)
        poly2.add_point(200.0, 100.0)

        road2 = Road(name="Road 2", centerline_id=poly2.id, polyline_ids=[poly2.id])

        junction.connected_road_ids = [road1.id, road2.id]

        roads_dict = {road1.id: road1, road2.id: road2}
        polylines_dict = {poly1.id: poly1, poly2.id: poly2}

        generate_junction_connections(junction, roads_dict, polylines_dict)

        # Should create connecting roads and lane connections
        assert len(junction.connecting_roads) > 0 or len(junction.lane_connections) > 0

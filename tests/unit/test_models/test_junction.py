"""
Unit tests for Junction model and related classes.

Tests Junction, JunctionGroup, JunctionConnection, and boundary-related classes.
"""


from orbit.models.connecting_road import ConnectingRoad
from orbit.models.junction import (
    Junction,
    JunctionBoundary,
    JunctionBoundarySegment,
    JunctionConnection,
    JunctionElevationGrid,
    JunctionElevationGridPoint,
    JunctionGroup,
)
from orbit.models.lane_connection import LaneConnection

# ============================================================================
# Test JunctionBoundarySegment
# ============================================================================

class TestJunctionBoundarySegment:
    """Test JunctionBoundarySegment dataclass."""

    def test_create_lane_segment(self):
        """Test creating a lane-type boundary segment."""
        segment = JunctionBoundarySegment(
            segment_type='lane',
            road_id='road-1',
            boundary_lane=-1,
            s_start=0.0,
            s_end=100.0
        )
        assert segment.segment_type == 'lane'
        assert segment.road_id == 'road-1'
        assert segment.boundary_lane == -1
        assert segment.s_start == 0.0
        assert segment.s_end == 100.0

    def test_create_joint_segment(self):
        """Test creating a joint-type boundary segment."""
        segment = JunctionBoundarySegment(
            segment_type='joint',
            road_id='road-1',
            contact_point='start',
            joint_lane_start=-2,
            joint_lane_end=2,
            transition_length=5.0
        )
        assert segment.segment_type == 'joint'
        assert segment.contact_point == 'start'
        assert segment.joint_lane_start == -2
        assert segment.joint_lane_end == 2

    def test_to_dict_lane_segment(self):
        """Test serialization of lane segment."""
        segment = JunctionBoundarySegment(
            segment_type='lane',
            road_id='road-1',
            boundary_lane=-1,
            s_start=10.0,
            s_end=50.0
        )
        data = segment.to_dict()
        assert data['segment_type'] == 'lane'
        assert data['road_id'] == 'road-1'
        assert data['boundary_lane'] == -1
        assert data['s_start'] == 10.0
        assert data['s_end'] == 50.0

    def test_to_dict_joint_segment(self):
        """Test serialization of joint segment."""
        segment = JunctionBoundarySegment(
            segment_type='joint',
            road_id='road-2',
            contact_point='end',
            joint_lane_start=-1,
            joint_lane_end=1
        )
        data = segment.to_dict()
        assert data['segment_type'] == 'joint'
        assert data['contact_point'] == 'end'
        assert 'boundary_lane' not in data  # Not included for joint type

    def test_from_dict_lane_segment(self):
        """Test deserialization of lane segment."""
        data = {
            'segment_type': 'lane',
            'road_id': 'road-x',
            'boundary_lane': -2,
            's_start': 0.0,
            's_end': 75.0
        }
        segment = JunctionBoundarySegment.from_dict(data)
        assert segment.segment_type == 'lane'
        assert segment.boundary_lane == -2
        assert segment.s_end == 75.0

    def test_from_dict_joint_segment(self):
        """Test deserialization of joint segment."""
        data = {
            'segment_type': 'joint',
            'road_id': 'road-y',
            'contact_point': 'start',
            'joint_lane_start': -1,
            'joint_lane_end': 2,
            'transition_length': 3.0
        }
        segment = JunctionBoundarySegment.from_dict(data)
        assert segment.segment_type == 'joint'
        assert segment.transition_length == 3.0


# ============================================================================
# Test JunctionElevationGridPoint
# ============================================================================

class TestJunctionElevationGridPoint:
    """Test JunctionElevationGridPoint dataclass."""

    def test_create_with_all_values(self):
        """Test creating point with all elevation values."""
        point = JunctionElevationGridPoint(
            center="0.0 0.1 0.2",
            left="0.0 0.05",
            right="0.0 -0.05"
        )
        assert point.center == "0.0 0.1 0.2"
        assert point.left == "0.0 0.05"
        assert point.right == "0.0 -0.05"

    def test_to_dict_excludes_none(self):
        """Test that to_dict excludes None values."""
        point = JunctionElevationGridPoint(center="1.0")
        data = point.to_dict()
        assert 'center' in data
        assert 'left' not in data
        assert 'right' not in data

    def test_from_dict(self):
        """Test deserialization."""
        data = {'center': '0.5', 'left': '0.4'}
        point = JunctionElevationGridPoint.from_dict(data)
        assert point.center == '0.5'
        assert point.left == '0.4'
        assert point.right is None


# ============================================================================
# Test JunctionElevationGrid
# ============================================================================

class TestJunctionElevationGrid:
    """Test JunctionElevationGrid dataclass."""

    def test_create_empty(self):
        """Test creating empty grid."""
        grid = JunctionElevationGrid()
        assert grid.grid_spacing is None
        assert grid.elevations == []

    def test_create_with_points(self):
        """Test creating grid with elevation points."""
        points = [
            JunctionElevationGridPoint(center="0.0"),
            JunctionElevationGridPoint(center="0.5")
        ]
        grid = JunctionElevationGrid(grid_spacing="10.0", elevations=points)
        assert grid.grid_spacing == "10.0"
        assert len(grid.elevations) == 2

    def test_roundtrip_serialization(self):
        """Test to_dict/from_dict roundtrip."""
        original = JunctionElevationGrid(
            grid_spacing="5.0",
            elevations=[
                JunctionElevationGridPoint(center="1.0", left="0.9")
            ]
        )
        data = original.to_dict()
        restored = JunctionElevationGrid.from_dict(data)
        assert restored.grid_spacing == "5.0"
        assert len(restored.elevations) == 1
        assert restored.elevations[0].center == "1.0"


# ============================================================================
# Test JunctionBoundary
# ============================================================================

class TestJunctionBoundary:
    """Test JunctionBoundary dataclass."""

    def test_create_empty(self):
        """Test creating empty boundary."""
        boundary = JunctionBoundary()
        assert boundary.segments == []

    def test_create_with_segments(self):
        """Test creating boundary with segments."""
        segments = [
            JunctionBoundarySegment(segment_type='lane', road_id='r1'),
            JunctionBoundarySegment(segment_type='joint', road_id='r1')
        ]
        boundary = JunctionBoundary(segments=segments)
        assert len(boundary.segments) == 2

    def test_roundtrip_serialization(self):
        """Test to_dict/from_dict roundtrip."""
        original = JunctionBoundary(segments=[
            JunctionBoundarySegment(segment_type='lane', road_id='road-1', boundary_lane=-1)
        ])
        data = original.to_dict()
        restored = JunctionBoundary.from_dict(data)
        assert len(restored.segments) == 1
        assert restored.segments[0].road_id == 'road-1'


# ============================================================================
# Test JunctionGroup
# ============================================================================

class TestJunctionGroup:
    """Test JunctionGroup dataclass."""

    def test_create_default(self):
        """Test creating junction group with defaults."""
        group = JunctionGroup()
        assert group.id is not None
        assert group.name is None
        assert group.group_type == "unknown"
        assert group.junction_ids == []

    def test_create_roundabout_group(self):
        """Test creating roundabout group."""
        group = JunctionGroup(
            name="Main Roundabout",
            group_type="roundabout",
            junction_ids=['j1', 'j2', 'j3']
        )
        assert group.name == "Main Roundabout"
        assert group.group_type == "roundabout"
        assert len(group.junction_ids) == 3

    def test_add_junction(self):
        """Test adding junction to group."""
        group = JunctionGroup()
        group.add_junction('junction-1')
        group.add_junction('junction-2')
        assert 'junction-1' in group.junction_ids
        assert 'junction-2' in group.junction_ids

    def test_add_junction_no_duplicates(self):
        """Test that adding same junction twice doesn't duplicate."""
        group = JunctionGroup()
        group.add_junction('j1')
        group.add_junction('j1')
        assert group.junction_ids.count('j1') == 1

    def test_remove_junction(self):
        """Test removing junction from group."""
        group = JunctionGroup(junction_ids=['j1', 'j2', 'j3'])
        group.remove_junction('j2')
        assert 'j2' not in group.junction_ids
        assert len(group.junction_ids) == 2

    def test_remove_nonexistent_junction(self):
        """Test removing non-existent junction is safe."""
        group = JunctionGroup(junction_ids=['j1'])
        group.remove_junction('nonexistent')  # Should not raise
        assert len(group.junction_ids) == 1

    def test_roundtrip_serialization(self):
        """Test to_dict/from_dict roundtrip."""
        original = JunctionGroup(
            name="Test Group",
            group_type="complexJunction",
            junction_ids=['a', 'b']
        )
        data = original.to_dict()
        restored = JunctionGroup.from_dict(data)
        assert restored.name == "Test Group"
        assert restored.group_type == "complexJunction"
        assert restored.junction_ids == ['a', 'b']

    def test_repr(self):
        """Test string representation."""
        group = JunctionGroup(group_type="roundabout", junction_ids=['j1', 'j2'])
        repr_str = repr(group)
        assert "roundabout" in repr_str
        assert "junctions=2" in repr_str


# ============================================================================
# Test JunctionConnection
# ============================================================================

class TestJunctionConnection:
    """Test JunctionConnection dataclass."""

    def test_create(self):
        """Test creating junction connection."""
        conn = JunctionConnection(
            incoming_road_id='road-in',
            connecting_road_id='road-conn',
            contact_point='start'
        )
        assert conn.incoming_road_id == 'road-in'
        assert conn.connecting_road_id == 'road-conn'
        assert conn.contact_point == 'start'

    def test_default_contact_point(self):
        """Test default contact point."""
        conn = JunctionConnection(
            incoming_road_id='r1',
            connecting_road_id='r2'
        )
        assert conn.contact_point == 'start'

    def test_roundtrip_serialization(self):
        """Test to_dict/from_dict roundtrip."""
        original = JunctionConnection(
            incoming_road_id='in',
            connecting_road_id='conn',
            contact_point='end'
        )
        data = original.to_dict()
        restored = JunctionConnection.from_dict(data)
        assert restored.incoming_road_id == 'in'
        assert restored.connecting_road_id == 'conn'
        assert restored.contact_point == 'end'


# ============================================================================
# Test Junction - Basic Operations
# ============================================================================

class TestJunctionBasic:
    """Test basic Junction operations."""

    def test_create_default(self):
        """Test creating junction with defaults."""
        junction = Junction()
        assert junction.id is not None
        assert junction.name == "Unnamed Junction"
        assert junction.center_point is None
        assert junction.connected_road_ids == []
        assert junction.junction_type == "default"

    def test_create_with_values(self):
        """Test creating junction with specific values."""
        junction = Junction(
            name="Test Intersection",
            center_point=(100.0, 200.0),
            junction_type="virtual"
        )
        assert junction.name == "Test Intersection"
        assert junction.center_point == (100.0, 200.0)
        assert junction.junction_type == "virtual"

    def test_add_road(self):
        """Test adding roads to junction."""
        junction = Junction()
        junction.add_road('road-1')
        junction.add_road('road-2')
        assert 'road-1' in junction.connected_road_ids
        assert 'road-2' in junction.connected_road_ids

    def test_add_road_no_duplicates(self):
        """Test that adding same road twice doesn't duplicate."""
        junction = Junction()
        junction.add_road('road-1')
        junction.add_road('road-1')
        assert junction.connected_road_ids.count('road-1') == 1

    def test_remove_road(self):
        """Test removing road from junction."""
        junction = Junction(connected_road_ids=['r1', 'r2', 'r3'])
        junction.remove_road('r2')
        assert 'r2' not in junction.connected_road_ids
        assert len(junction.connected_road_ids) == 2

    def test_remove_road_clears_connections(self):
        """Test that removing road also removes related connections."""
        junction = Junction(connected_road_ids=['r1', 'r2'])
        junction.add_connection(JunctionConnection(
            incoming_road_id='r1',
            connecting_road_id='r2'
        ))
        junction.remove_road('r1')
        assert len(junction.connections) == 0

    def test_is_valid_with_two_roads(self):
        """Test junction is valid with 2+ roads."""
        junction = Junction(connected_road_ids=['r1', 'r2'])
        assert junction.is_valid() is True

    def test_is_valid_with_one_road(self):
        """Test junction is invalid with only 1 road."""
        junction = Junction(connected_road_ids=['r1'])
        assert junction.is_valid() is False

    def test_is_valid_empty(self):
        """Test junction is invalid when empty."""
        junction = Junction()
        assert junction.is_valid() is False


# ============================================================================
# Test Junction - Geo Coordinates
# ============================================================================

class TestJunctionGeoCoords:
    """Test Junction geographic coordinate handling."""

    def test_has_geo_coords_false(self):
        """Test has_geo_coords returns False when not set."""
        junction = Junction(center_point=(100, 200))
        assert junction.has_geo_coords() is False

    def test_has_geo_coords_true(self):
        """Test has_geo_coords returns True when set."""
        junction = Junction(geo_center_point=(12.0, 57.0))
        assert junction.has_geo_coords() is True

    def test_get_pixel_center_point_no_geo(self):
        """Test get_pixel_center_point returns stored pixel coords."""
        junction = Junction(center_point=(100, 200))
        assert junction.get_pixel_center_point() == (100, 200)

    def test_get_pixel_center_point_no_transformer(self):
        """Test get_pixel_center_point with geo but no transformer."""
        junction = Junction(
            center_point=(100, 200),
            geo_center_point=(12.0, 57.0)
        )
        # Without transformer, returns stored pixel coords
        assert junction.get_pixel_center_point() == (100, 200)


# ============================================================================
# Test Junction - Connecting Roads and Lane Connections
# ============================================================================

class TestJunctionConnections:
    """Test Junction connecting road and lane connection management."""

    def test_add_connecting_road(self):
        """Test adding connecting road."""
        junction = Junction()
        cr = ConnectingRoad(
            predecessor_road_id='r1',
            successor_road_id='r2'
        )
        junction.add_connecting_road(cr)
        assert len(junction.connecting_roads) == 1
        assert junction.connecting_roads[0] == cr

    def test_add_connecting_road_no_duplicates(self):
        """Test that same connecting road isn't added twice."""
        junction = Junction()
        cr = ConnectingRoad(predecessor_road_id='r1', successor_road_id='r2')
        junction.add_connecting_road(cr)
        junction.add_connecting_road(cr)
        assert len(junction.connecting_roads) == 1

    def test_remove_connecting_road(self):
        """Test removing connecting road."""
        cr = ConnectingRoad(predecessor_road_id='r1', successor_road_id='r2')
        junction = Junction(connecting_roads=[cr])
        junction.remove_connecting_road(cr.id)
        assert len(junction.connecting_roads) == 0

    def test_remove_connecting_road_clears_lane_connections(self):
        """Test that removing connecting road also removes lane connections."""
        cr = ConnectingRoad(predecessor_road_id='r1', successor_road_id='r2')
        lc = LaneConnection(
            from_road_id='r1',
            to_road_id='r2',
            connecting_road_id=cr.id
        )
        junction = Junction(connecting_roads=[cr], lane_connections=[lc])
        junction.remove_connecting_road(cr.id)
        assert len(junction.lane_connections) == 0

    def test_add_lane_connection(self):
        """Test adding lane connection."""
        junction = Junction()
        lc = LaneConnection(from_road_id='r1', to_road_id='r2')
        junction.add_lane_connection(lc)
        assert len(junction.lane_connections) == 1

    def test_remove_lane_connection(self):
        """Test removing lane connection by ID."""
        lc = LaneConnection(from_road_id='r1', to_road_id='r2')
        junction = Junction(lane_connections=[lc])
        junction.remove_lane_connection(lc.id)
        assert len(junction.lane_connections) == 0

    def test_get_connecting_road_by_id(self):
        """Test finding connecting road by ID."""
        cr = ConnectingRoad(predecessor_road_id='r1', successor_road_id='r2')
        junction = Junction(connecting_roads=[cr])
        found = junction.get_connecting_road_by_id(cr.id)
        assert found == cr

    def test_get_connecting_road_by_id_not_found(self):
        """Test finding non-existent connecting road."""
        junction = Junction()
        found = junction.get_connecting_road_by_id('nonexistent')
        assert found is None

    def test_get_connections_for_road_pair(self):
        """Test getting connections between specific roads."""
        lc1 = LaneConnection(from_road_id='r1', to_road_id='r2', from_lane_id=-1)
        lc2 = LaneConnection(from_road_id='r1', to_road_id='r2', from_lane_id=-2)
        lc3 = LaneConnection(from_road_id='r1', to_road_id='r3', from_lane_id=-1)
        junction = Junction(lane_connections=[lc1, lc2, lc3])

        connections = junction.get_connections_for_road_pair('r1', 'r2')
        assert len(connections) == 2
        assert lc3 not in connections

    def test_get_connections_by_turn_type(self):
        """Test getting connections by turn type."""
        lc1 = LaneConnection(from_road_id='r1', to_road_id='r2', turn_type='left')
        lc2 = LaneConnection(from_road_id='r1', to_road_id='r3', turn_type='right')
        lc3 = LaneConnection(from_road_id='r2', to_road_id='r1', turn_type='left')
        junction = Junction(lane_connections=[lc1, lc2, lc3])

        left_turns = junction.get_connections_by_turn_type('left')
        assert len(left_turns) == 2


# ============================================================================
# Test Junction - Roundabout Support
# ============================================================================

class TestJunctionRoundabout:
    """Test Junction roundabout-specific functionality."""

    def test_set_as_roundabout(self):
        """Test configuring junction as roundabout."""
        junction = Junction()
        junction.set_as_roundabout_junction(
            center=(500, 500),
            radius=50.0,
            lane_count=2,
            clockwise=True
        )
        assert junction.is_roundabout is True
        assert junction.roundabout_center == (500, 500)
        assert junction.roundabout_radius == 50.0
        assert junction.roundabout_lane_count == 2
        assert junction.roundabout_clockwise is True

    def test_add_roundabout_entry(self):
        """Test adding entry road."""
        junction = Junction(is_roundabout=True)
        junction.add_roundabout_entry('entry-road-1')
        assert 'entry-road-1' in junction.entry_roads

    def test_add_roundabout_entry_no_duplicates(self):
        """Test entry roads aren't duplicated."""
        junction = Junction(is_roundabout=True)
        junction.add_roundabout_entry('r1')
        junction.add_roundabout_entry('r1')
        assert junction.entry_roads.count('r1') == 1

    def test_add_roundabout_exit(self):
        """Test adding exit road."""
        junction = Junction(is_roundabout=True)
        junction.add_roundabout_exit('exit-road-1')
        assert 'exit-road-1' in junction.exit_roads

    def test_get_ring_road_ids(self):
        """Test getting ring road IDs."""
        junction = Junction(
            is_roundabout=True,
            connected_road_ids=['ring1', 'ring2', 'entry', 'exit'],
            entry_roads=['entry'],
            exit_roads=['exit']
        )
        ring1, ring2 = junction.get_ring_road_ids()
        assert ring1 == 'ring1'
        assert ring2 == 'ring2'

    def test_get_ring_road_ids_not_roundabout(self):
        """Test ring road IDs for non-roundabout."""
        junction = Junction(is_roundabout=False)
        ring1, ring2 = junction.get_ring_road_ids()
        assert ring1 is None
        assert ring2 is None

    def test_get_approach_road_ids(self):
        """Test getting approach road IDs."""
        junction = Junction(
            is_roundabout=True,
            entry_roads=['e1', 'e2'],
            exit_roads=['x1', 'e1']  # e1 is both entry and exit
        )
        approach = junction.get_approach_road_ids()
        assert set(approach) == {'e1', 'e2', 'x1'}


# ============================================================================
# Test Junction - Validation
# ============================================================================

class TestJunctionValidation:
    """Test Junction validation."""

    def test_validate_enhanced_valid(self):
        """Test validation of valid junction."""
        junction = Junction(connected_road_ids=['r1', 'r2'])
        is_valid, errors = junction.validate_enhanced()
        assert is_valid is True
        assert errors == []

    def test_validate_enhanced_too_few_roads(self):
        """Test validation fails with < 2 roads."""
        junction = Junction(connected_road_ids=['r1'])
        is_valid, errors = junction.validate_enhanced()
        assert is_valid is False
        assert any("at least 2" in err for err in errors)

    def test_validate_enhanced_roundabout_missing_center(self):
        """Test validation fails for roundabout without center."""
        junction = Junction(
            connected_road_ids=['r1', 'r2'],
            is_roundabout=True,
            roundabout_radius=50
        )
        is_valid, errors = junction.validate_enhanced()
        assert is_valid is False
        assert any("center point" in err for err in errors)

    def test_validate_enhanced_roundabout_invalid_radius(self):
        """Test validation fails for roundabout with invalid radius."""
        junction = Junction(
            connected_road_ids=['r1', 'r2'],
            is_roundabout=True,
            roundabout_center=(100, 100),
            roundabout_radius=0  # Invalid
        )
        is_valid, errors = junction.validate_enhanced()
        assert is_valid is False
        assert any("positive radius" in err for err in errors)


# ============================================================================
# Test Junction - Connection Summary
# ============================================================================

class TestJunctionSummary:
    """Test Junction connection summary."""

    def test_get_connection_summary(self):
        """Test getting connection summary."""
        cr = ConnectingRoad(predecessor_road_id='r1', successor_road_id='r2')
        lc1 = LaneConnection(from_road_id='r1', to_road_id='r2', turn_type='left')
        lc2 = LaneConnection(from_road_id='r1', to_road_id='r3', turn_type='right')
        lc3 = LaneConnection(from_road_id='r2', to_road_id='r3', turn_type='straight')

        junction = Junction(
            connecting_roads=[cr],
            lane_connections=[lc1, lc2, lc3]
        )
        summary = junction.get_connection_summary()

        assert summary['total_connections'] == 3
        assert summary['connecting_roads'] == 1
        assert summary['left'] == 1
        assert summary['right'] == 1
        assert summary['straight'] == 1


# ============================================================================
# Test Junction - Serialization
# ============================================================================

class TestJunctionSerialization:
    """Test Junction serialization."""

    def test_to_dict_basic(self):
        """Test basic serialization."""
        junction = Junction(
            name="Test Junction",
            center_point=(100, 200),
            connected_road_ids=['r1', 'r2']
        )
        data = junction.to_dict()
        assert data['name'] == "Test Junction"
        assert data['center_point'] == (100, 200)
        assert data['connected_road_ids'] == ['r1', 'r2']

    def test_to_dict_with_roundabout(self):
        """Test serialization with roundabout data."""
        junction = Junction(
            is_roundabout=True,
            roundabout_center=(500, 500),
            roundabout_radius=50.0
        )
        data = junction.to_dict()
        assert data['is_roundabout'] is True
        assert data['roundabout_center'] == (500, 500)
        assert data['roundabout_radius'] == 50.0

    def test_to_dict_with_geo_coords(self):
        """Test serialization includes geo coordinates."""
        junction = Junction(
            geo_center_point=(12.0, 57.0),
            geo_roundabout_center=(12.1, 57.1)
        )
        data = junction.to_dict()
        assert data['geo_center_point'] == [12.0, 57.0]
        assert data['geo_roundabout_center'] == [12.1, 57.1]

    def test_from_dict_basic(self):
        """Test basic deserialization."""
        data = {
            'id': 'test-id',
            'name': 'Test Junction',
            'center_point': [100, 200],
            'connected_road_ids': ['r1', 'r2']
        }
        junction = Junction.from_dict(data)
        assert junction.id == 'test-id'
        assert junction.name == 'Test Junction'
        assert junction.center_point == (100, 200)

    def test_from_dict_with_roundabout(self):
        """Test deserialization with roundabout data."""
        data = {
            'is_roundabout': True,
            'roundabout_center': [500, 500],
            'roundabout_radius': 50.0,
            'roundabout_lane_count': 2
        }
        junction = Junction.from_dict(data)
        assert junction.is_roundabout is True
        assert junction.roundabout_center == (500, 500)
        assert junction.roundabout_lane_count == 2

    def test_roundtrip_serialization(self):
        """Test full roundtrip serialization."""
        cr = ConnectingRoad(predecessor_road_id='r1', successor_road_id='r2')
        lc = LaneConnection(from_road_id='r1', to_road_id='r2')

        original = Junction(
            name="Complex Junction",
            center_point=(100, 200),
            geo_center_point=(12.0, 57.0),
            connected_road_ids=['r1', 'r2', 'r3'],
            connecting_roads=[cr],
            lane_connections=[lc],
            is_roundabout=True,
            roundabout_center=(500, 500),
            roundabout_radius=75.0
        )

        data = original.to_dict()
        restored = Junction.from_dict(data)

        assert restored.name == original.name
        assert restored.center_point == original.center_point
        assert restored.geo_center_point == original.geo_center_point
        assert restored.is_roundabout == original.is_roundabout
        assert len(restored.connecting_roads) == 1
        assert len(restored.lane_connections) == 1

    def test_repr(self):
        """Test string representation."""
        junction = Junction(
            name="Main Intersection",
            connected_road_ids=['r1', 'r2', 'r3']
        )
        repr_str = repr(junction)
        assert "Main Intersection" in repr_str
        assert "roads=3" in repr_str

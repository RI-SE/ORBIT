"""
Unit tests for Project model.

Tests project creation, serialization, save/load, and element management.
"""

import json
from pathlib import Path

import pytest

from orbit import __version__
from orbit.models import ControlPoint, Junction, LineType, Polyline, Project, Road, RoadMarkType


class TestProjectCreation:
    """Test project initialization and basic properties."""

    def test_empty_project_creation(self, empty_project: Project):
        """Test creating an empty project initializes correctly."""
        assert empty_project.polylines == []
        assert empty_project.roads == []
        assert empty_project.junctions == []
        assert empty_project.signals == []
        assert empty_project.objects == []
        assert empty_project.control_points == []
        assert empty_project.image_path is None
        assert empty_project.right_hand_traffic is True
        assert empty_project.transform_method == 'homography'

    def test_project_metadata_auto_generated(self, empty_project: Project):
        """Test that metadata is automatically generated."""
        assert 'version' in empty_project.metadata
        assert 'created' in empty_project.metadata
        assert 'modified' in empty_project.metadata
        assert empty_project.metadata['version'] == __version__

    def test_project_with_initial_data(self, sample_project: Project):
        """Test creating project with initial data."""
        assert len(sample_project.polylines) == 3
        assert len(sample_project.roads) == 1
        assert len(sample_project.control_points) == 3
        assert sample_project.transform_method == 'affine'


class TestPolylineManagement:
    """Test polyline addition, removal, and retrieval."""

    def test_add_polyline(self, empty_project: Project, sample_polyline: Polyline):
        """Test adding a polyline to project."""
        empty_project.add_polyline(sample_polyline)

        assert len(empty_project.polylines) == 1
        assert empty_project.polylines[0].id == sample_polyline.id

    def test_get_polyline_by_id(self, sample_project: Project):
        """Test retrieving polyline by ID."""
        polyline = sample_project.polylines[0]
        retrieved = sample_project.get_polyline(polyline.id)

        assert retrieved is not None
        assert retrieved.id == polyline.id
        assert retrieved.points == polyline.points

    def test_get_nonexistent_polyline_returns_none(self, sample_project: Project):
        """Test getting a non-existent polyline returns None."""
        result = sample_project.get_polyline("nonexistent-id")
        assert result is None

    def test_remove_polyline(self, sample_project: Project):
        """Test removing a polyline from project."""
        polyline_id = sample_project.polylines[0].id
        initial_count = len(sample_project.polylines)

        sample_project.remove_polyline(polyline_id)

        assert len(sample_project.polylines) == initial_count - 1
        assert sample_project.get_polyline(polyline_id) is None

    def test_remove_polyline_updates_roads(self, sample_project: Project):
        """Test that removing a polyline updates roads that reference it."""
        road = sample_project.roads[0]
        polyline_id = road.polyline_ids[0]
        initial_road_polyline_count = len(road.polyline_ids)

        sample_project.remove_polyline(polyline_id)

        # Road should have one less polyline
        assert len(road.polyline_ids) == initial_road_polyline_count - 1
        assert polyline_id not in road.polyline_ids


class TestRoadManagement:
    """Test road addition, removal, and retrieval."""

    def test_add_road(self, empty_project: Project, sample_road: Road):
        """Test adding a road to project."""
        empty_project.add_road(sample_road)

        assert len(empty_project.roads) == 1
        assert empty_project.roads[0].id == sample_road.id

    def test_get_road_by_id(self, sample_project: Project):
        """Test retrieving road by ID."""
        road = sample_project.roads[0]
        retrieved = sample_project.get_road(road.id)

        assert retrieved is not None
        assert retrieved.id == road.id
        assert retrieved.name == road.name

    def test_get_nonexistent_road_returns_none(self, sample_project: Project):
        """Test getting a non-existent road returns None."""
        result = sample_project.get_road("nonexistent-id")
        assert result is None

    def test_remove_road(self, sample_project: Project):
        """Test removing a road from project."""
        road_id = sample_project.roads[0].id
        initial_count = len(sample_project.roads)

        sample_project.remove_road(road_id)

        assert len(sample_project.roads) == initial_count - 1
        assert sample_project.get_road(road_id) is None


class TestJunctionManagement:
    """Test junction addition, removal, and retrieval."""

    def test_add_junction(self, empty_project: Project, sample_junction: Junction):
        """Test adding a junction to project."""
        empty_project.add_junction(sample_junction)

        assert len(empty_project.junctions) == 1
        assert empty_project.junctions[0].id == sample_junction.id

    def test_get_junction_by_id(self, empty_project: Project, sample_junction: Junction):
        """Test retrieving junction by ID."""
        empty_project.add_junction(sample_junction)
        retrieved = empty_project.get_junction(sample_junction.id)

        assert retrieved is not None
        assert retrieved.id == sample_junction.id
        assert retrieved.name == sample_junction.name

    def test_get_nonexistent_junction_returns_none(self, empty_project: Project):
        """Test getting a non-existent junction returns None."""
        result = empty_project.get_junction("nonexistent-id")
        assert result is None

    def test_remove_junction(self, empty_project: Project, sample_junction: Junction):
        """Test removing a junction from project."""
        empty_project.add_junction(sample_junction)
        junction_id = sample_junction.id

        empty_project.remove_junction(junction_id)

        assert len(empty_project.junctions) == 0
        assert empty_project.get_junction(junction_id) is None


class TestControlPoints:
    """Test control point management."""

    def test_project_with_control_points(self, sample_project: Project):
        """Test project with control points."""
        assert len(sample_project.control_points) == 3

        cp = sample_project.control_points[0]
        assert cp.pixel_x == 100.0
        assert cp.pixel_y == 100.0
        assert cp.longitude == 12.940000
        assert cp.latitude == 57.720000
        assert cp.name == "CP1"
        assert cp.is_validation is False

    def test_validation_control_point(self, validation_control_point: ControlPoint):
        """Test validation control point flag."""
        assert validation_control_point.is_validation is True
        assert validation_control_point.name == "GVP1"


class TestProjectSerialization:
    """Test project to_dict/from_dict serialization."""

    def test_empty_project_to_dict(self, empty_project: Project):
        """Test serializing empty project to dictionary."""
        data = empty_project.to_dict()

        assert 'metadata' in data
        assert 'polylines' in data
        assert 'roads' in data
        assert 'control_points' in data
        assert data['polylines'] == []
        assert data['roads'] == []
        assert data['right_hand_traffic'] is True

    def test_sample_project_to_dict(self, sample_project: Project):
        """Test serializing project with data to dictionary."""
        data = sample_project.to_dict()

        assert len(data['polylines']) == 3
        assert len(data['roads']) == 1
        assert len(data['control_points']) == 3
        assert data['transform_method'] == 'affine'
        assert data['image_path'] == str(sample_project.image_path)

    def test_to_dict_updates_modified_timestamp(self, empty_project: Project):
        """Test that to_dict() updates the modified timestamp."""
        original_modified = empty_project.metadata['modified']
        import time
        time.sleep(0.01)  # Small delay to ensure timestamp changes

        data = empty_project.to_dict()

        assert data['metadata']['modified'] != original_modified

    def test_project_from_dict(self, sample_project: Project):
        """Test creating project from dictionary."""
        data = sample_project.to_dict()
        restored = Project.from_dict(data)

        assert len(restored.polylines) == len(sample_project.polylines)
        assert len(restored.roads) == len(sample_project.roads)
        assert len(restored.control_points) == len(sample_project.control_points)
        assert restored.transform_method == sample_project.transform_method
        assert restored.right_hand_traffic == sample_project.right_hand_traffic

    def test_from_dict_with_missing_fields_uses_defaults(self):
        """Test that from_dict() uses defaults for missing fields."""
        minimal_data = {
            'metadata': {'version': '0.2.0'},
            'polylines': [],
            'roads': []
        }

        project = Project.from_dict(minimal_data)

        assert project.right_hand_traffic is True
        assert project.transform_method == 'affine'
        assert project.country_code == 'se'
        assert project.openstreetmap_used is False
        assert project.polylines == []
        assert project.roads == []


class TestProjectSaveLoad:
    """Test project save/load to .orbit files."""

    def test_save_project(self, sample_project: Project, tmp_path: Path):
        """Test saving project to file."""
        save_path = tmp_path / "test_project.orbit"

        sample_project.save(save_path)

        assert save_path.exists()
        assert save_path.suffix == '.orbit'

    def test_save_adds_orbit_extension(self, empty_project: Project, tmp_path: Path):
        """Test that save() adds .orbit extension if missing."""
        save_path = tmp_path / "test_project"

        empty_project.save(save_path)

        orbit_path = tmp_path / "test_project.orbit"
        assert orbit_path.exists()

    def test_save_preserves_json_extension(self, empty_project: Project, tmp_path: Path):
        """Test that .json extension is preserved (legacy support)."""
        save_path = tmp_path / "test_project.json"

        empty_project.save(save_path)

        assert save_path.exists()
        assert save_path.suffix == '.json'

    def test_load_project(self, sample_project: Project, tmp_path: Path):
        """Test loading project from file."""
        save_path = tmp_path / "test_project.orbit"
        sample_project.save(save_path)

        loaded = Project.load(save_path)

        assert len(loaded.polylines) == len(sample_project.polylines)
        assert len(loaded.roads) == len(sample_project.roads)
        assert len(loaded.control_points) == len(sample_project.control_points)

    def test_roundtrip_save_load(self, sample_project: Project, tmp_path: Path):
        """Test save → load → save produces identical files."""
        path1 = tmp_path / "project1.orbit"
        path2 = tmp_path / "project2.orbit"

        # Save → load → save
        sample_project.save(path1)
        loaded = Project.load(path1)
        loaded.save(path2)

        # Load both and compare
        with open(path1, 'r') as f:
            data1 = json.load(f)
        with open(path2, 'r') as f:
            data2 = json.load(f)

        # Modified timestamps will differ, so ignore them
        del data1['metadata']['modified']
        del data2['metadata']['modified']

        # ID counters are synced from existing IDs on load, so may differ
        # from the initial state where counters were not advanced
        data1.pop('id_counters', None)
        data2.pop('id_counters', None)

        assert data1 == data2

    def test_load_real_project(self, example_project_path: Path):
        """Test loading a real project file from examples."""
        if not example_project_path.exists():
            pytest.skip(f"Test data not found: {example_project_path}")

        project = Project.load(example_project_path)

        assert len(project.polylines) > 0
        assert len(project.roads) >= 0
        assert project.metadata is not None
        assert 'version' in project.metadata


class TestProjectClear:
    """Test clearing project data."""

    def test_clear_project(self, sample_project: Project):
        """Test clearing all project data."""
        sample_project.clear()

        assert len(sample_project.polylines) == 0
        assert len(sample_project.roads) == 0
        assert len(sample_project.junctions) == 0
        assert len(sample_project.signals) == 0
        assert len(sample_project.objects) == 0
        assert len(sample_project.control_points) == 0
        assert sample_project.image_path is None

    def test_clear_resets_metadata(self, sample_project: Project):
        """Test that clear() resets metadata."""
        old_created = sample_project.metadata['created']

        import time
        time.sleep(0.01)
        sample_project.clear()

        # Version should stay the same
        assert sample_project.metadata['version'] == __version__
        # Created timestamp should be updated
        assert sample_project.metadata['created'] != old_created


class TestControlPointSerialization:
    """Test ControlPoint to_dict/from_dict methods."""

    def test_control_point_to_dict(self, sample_control_points):
        """Test control point serialization."""
        cp = sample_control_points[0]
        data = cp.to_dict()

        assert data['pixel_x'] == 100.0
        assert data['pixel_y'] == 100.0
        assert data['longitude'] == 12.940000
        assert data['latitude'] == 57.720000
        assert data['name'] == "CP1"
        assert data['is_validation'] is False

    def test_control_point_to_dict_validation_point(self, validation_control_point):
        """Test validation control point serialization."""
        data = validation_control_point.to_dict()

        assert data['is_validation'] is True
        assert data['name'] == "GVP1"

    def test_control_point_from_dict(self):
        """Test control point deserialization."""
        data = {
            'pixel_x': 200.0,
            'pixel_y': 300.0,
            'longitude': 12.95,
            'latitude': 57.73,
            'name': 'Test Point',
            'is_validation': True
        }

        cp = ControlPoint.from_dict(data)

        assert cp.pixel_x == 200.0
        assert cp.pixel_y == 300.0
        assert cp.longitude == 12.95
        assert cp.latitude == 57.73
        assert cp.name == 'Test Point'
        assert cp.is_validation is True

    def test_control_point_from_dict_backwards_compat(self):
        """Test control point without is_validation field (old format)."""
        data = {
            'pixel_x': 100.0,
            'pixel_y': 100.0,
            'longitude': 12.94,
            'latitude': 57.72
        }

        cp = ControlPoint.from_dict(data)

        assert cp.is_validation is False  # Default
        assert cp.name is None

    def test_control_point_roundtrip(self, sample_control_points):
        """Test control point serialization roundtrip."""
        for original in sample_control_points:
            data = original.to_dict()
            restored = ControlPoint.from_dict(data)

            assert restored.pixel_x == original.pixel_x
            assert restored.pixel_y == original.pixel_y
            assert restored.longitude == original.longitude
            assert restored.latitude == original.latitude
            assert restored.name == original.name
            assert restored.is_validation == original.is_validation


class TestSignalManagement:
    """Test signal addition, removal, and retrieval."""

    def test_add_signal(self, empty_project):
        """Test adding a signal to project."""
        from orbit.models.signal import Signal, SignalType

        signal = Signal(
            position=(100.0, 200.0),
            signal_type=SignalType.STOP
        )
        empty_project.add_signal(signal)

        assert len(empty_project.signals) == 1
        assert empty_project.signals[0].id == signal.id

    def test_get_signal_by_id(self, empty_project):
        """Test retrieving signal by ID."""
        from orbit.models.signal import Signal, SignalType

        signal = Signal(
            position=(100.0, 200.0),
            signal_type=SignalType.GIVE_WAY
        )
        empty_project.add_signal(signal)
        retrieved = empty_project.get_signal(signal.id)

        assert retrieved is not None
        assert retrieved.id == signal.id

    def test_get_nonexistent_signal_returns_none(self, empty_project):
        """Test getting a non-existent signal returns None."""
        result = empty_project.get_signal("nonexistent-id")
        assert result is None

    def test_remove_signal(self, empty_project):
        """Test removing a signal from project."""
        from orbit.models.signal import Signal, SignalType

        signal = Signal(
            position=(100.0, 200.0),
            signal_type=SignalType.STOP
        )
        empty_project.add_signal(signal)
        signal_id = signal.id

        empty_project.remove_signal(signal_id)

        assert len(empty_project.signals) == 0
        assert empty_project.get_signal(signal_id) is None


class TestObjectManagement:
    """Test roadside object addition, removal, and retrieval."""

    def test_add_object(self, empty_project):
        """Test adding an object to project."""
        from orbit.models.object import ObjectType, RoadObject

        obj = RoadObject(
            position=(100.0, 200.0),
            object_type=ObjectType.LAMPPOST
        )
        empty_project.add_object(obj)

        assert len(empty_project.objects) == 1
        assert empty_project.objects[0].id == obj.id

    def test_get_object_by_id(self, empty_project):
        """Test retrieving object by ID."""
        from orbit.models.object import ObjectType, RoadObject

        obj = RoadObject(
            position=(100.0, 200.0),
            object_type=ObjectType.BUILDING
        )
        empty_project.add_object(obj)
        retrieved = empty_project.get_object(obj.id)

        assert retrieved is not None
        assert retrieved.id == obj.id

    def test_get_nonexistent_object_returns_none(self, empty_project):
        """Test getting a non-existent object returns None."""
        result = empty_project.get_object("nonexistent-id")
        assert result is None

    def test_remove_object(self, empty_project):
        """Test removing an object from project."""
        from orbit.models.object import ObjectType, RoadObject

        obj = RoadObject(
            position=(100.0, 200.0),
            object_type=ObjectType.TREE_BROADLEAF
        )
        empty_project.add_object(obj)
        obj_id = obj.id

        empty_project.remove_object(obj_id)

        assert len(empty_project.objects) == 0
        assert empty_project.get_object(obj_id) is None


class TestParkingManagement:
    """Test parking space addition, removal, and retrieval."""

    def test_add_parking(self, empty_project):
        """Test adding a parking space to project."""
        from orbit.models.parking import ParkingSpace

        parking = ParkingSpace(
            position=(100.0, 200.0)
        )
        empty_project.add_parking(parking)

        assert len(empty_project.parking_spaces) == 1
        assert empty_project.parking_spaces[0].id == parking.id

    def test_get_parking_by_id(self, empty_project):
        """Test retrieving parking by ID."""
        from orbit.models.parking import ParkingSpace

        parking = ParkingSpace(
            position=(100.0, 200.0)
        )
        empty_project.add_parking(parking)
        retrieved = empty_project.get_parking(parking.id)

        assert retrieved is not None
        assert retrieved.id == parking.id

    def test_get_nonexistent_parking_returns_none(self, empty_project):
        """Test getting a non-existent parking returns None."""
        result = empty_project.get_parking("nonexistent-id")
        assert result is None

    def test_remove_parking(self, empty_project):
        """Test removing a parking space from project."""
        from orbit.models.parking import ParkingSpace

        parking = ParkingSpace(
            position=(100.0, 200.0)
        )
        empty_project.add_parking(parking)
        parking_id = parking.id

        empty_project.remove_parking(parking_id)

        assert len(empty_project.parking_spaces) == 0
        assert empty_project.get_parking(parking_id) is None


class TestControlPointOperations:
    """Test control point operations."""

    def test_add_control_point(self, empty_project):
        """Test adding a control point."""
        cp = ControlPoint(
            pixel_x=100.0, pixel_y=100.0,
            longitude=12.94, latitude=57.72
        )
        empty_project.add_control_point(cp)

        assert len(empty_project.control_points) == 1
        assert empty_project.control_points[0].pixel_x == 100.0

    def test_add_control_point_invalidates_cache(self, empty_project):
        """Test that adding control point invalidates uncertainty cache."""
        empty_project.uncertainty_grid_cache = [[1.0, 2.0], [3.0, 4.0]]
        empty_project.uncertainty_last_computed = "2024-01-01T00:00:00"

        cp = ControlPoint(pixel_x=100.0, pixel_y=100.0, longitude=12.94, latitude=57.72)
        empty_project.add_control_point(cp)

        assert empty_project.uncertainty_grid_cache is None
        assert empty_project.uncertainty_last_computed is None

    def test_remove_control_point(self, sample_project):
        """Test removing a control point."""
        initial_count = len(sample_project.control_points)
        sample_project.remove_control_point(0)

        assert len(sample_project.control_points) == initial_count - 1

    def test_remove_control_point_out_of_range(self, sample_project):
        """Test removing a control point with invalid index does nothing."""
        initial_count = len(sample_project.control_points)
        sample_project.remove_control_point(100)  # Invalid index

        assert len(sample_project.control_points) == initial_count

    def test_remove_control_point_invalidates_cache(self, sample_project):
        """Test that removing control point invalidates uncertainty cache."""
        sample_project.uncertainty_grid_cache = [[1.0, 2.0], [3.0, 4.0]]

        sample_project.remove_control_point(0)

        assert sample_project.uncertainty_grid_cache is None

    def test_has_georeferencing_true(self, sample_project):
        """Test has_georeferencing returns True with 3+ control points."""
        assert sample_project.has_georeferencing() is True

    def test_has_georeferencing_false(self, empty_project):
        """Test has_georeferencing returns False with fewer than 3 control points."""
        assert empty_project.has_georeferencing() is False

        # Add 2 points - still not enough
        for i in range(2):
            empty_project.add_control_point(ControlPoint(
                pixel_x=i*100.0, pixel_y=100.0,
                longitude=12.94 + i*0.01, latitude=57.72
            ))
        assert empty_project.has_georeferencing() is False

        # Add 3rd point - now enough
        empty_project.add_control_point(ControlPoint(
            pixel_x=200.0, pixel_y=200.0,
            longitude=12.96, latitude=57.73
        ))
        assert empty_project.has_georeferencing() is True

    def test_invalidate_uncertainty_cache(self, empty_project):
        """Test invalidate_uncertainty_cache clears all cached data."""
        empty_project.uncertainty_grid_cache = [[1.0]]
        empty_project.uncertainty_bootstrap_grid = [[2.0]]
        empty_project.uncertainty_last_computed = "2024-01-01"

        empty_project.invalidate_uncertainty_cache()

        assert empty_project.uncertainty_grid_cache is None
        assert empty_project.uncertainty_bootstrap_grid is None
        assert empty_project.uncertainty_last_computed is None


class TestFindClosestRoad:
    """Test find_closest_road method."""

    def test_find_closest_road_single_road(self, sample_project):
        """Test finding closest road with single road."""
        # Centerline is at y=100, point at (500, 100) is on the line
        result = sample_project.find_closest_road((500.0, 100.0))

        assert result is not None
        assert result == sample_project.roads[0].id

    def test_find_closest_road_point_near_road(self, sample_project):
        """Test finding closest road with point near but not on road."""
        # Point at (500, 110) is 10 pixels from centerline at y=100
        result = sample_project.find_closest_road((500.0, 110.0))

        assert result is not None
        assert result == sample_project.roads[0].id

    def test_find_closest_road_empty_project(self, empty_project):
        """Test find_closest_road returns None when no roads exist."""
        result = empty_project.find_closest_road((100.0, 100.0))
        assert result is None

    def test_find_closest_road_multiple_roads(self, empty_project):
        """Test finding closest road among multiple roads."""
        # Create two roads at different positions
        poly1 = Polyline(line_type=LineType.CENTERLINE)
        for x in range(0, 500, 100):
            poly1.add_point(float(x), 100.0)

        poly2 = Polyline(line_type=LineType.CENTERLINE)
        for x in range(0, 500, 100):
            poly2.add_point(float(x), 300.0)

        empty_project.add_polyline(poly1)
        empty_project.add_polyline(poly2)

        road1 = Road(name="Road 1", centerline_id=poly1.id, polyline_ids=[poly1.id])
        road2 = Road(name="Road 2", centerline_id=poly2.id, polyline_ids=[poly2.id])

        empty_project.add_road(road1)
        empty_project.add_road(road2)

        # Point closer to road1 (y=100)
        result = empty_project.find_closest_road((200.0, 120.0))
        assert result == road1.id

        # Point closer to road2 (y=300)
        result = empty_project.find_closest_road((200.0, 280.0))
        assert result == road2.id


class TestPointToPolylineDistance:
    """Test _point_to_polyline_distance helper method."""

    def test_point_on_polyline(self, empty_project):
        """Test distance is zero when point is on polyline."""
        points = [(0.0, 0.0), (100.0, 0.0)]
        distance = empty_project._point_to_polyline_distance((50.0, 0.0), points)

        assert distance == pytest.approx(0.0, abs=0.001)

    def test_point_perpendicular_to_segment(self, empty_project):
        """Test distance for point perpendicular to segment."""
        points = [(0.0, 0.0), (100.0, 0.0)]
        distance = empty_project._point_to_polyline_distance((50.0, 10.0), points)

        assert distance == pytest.approx(10.0, abs=0.001)

    def test_point_nearest_to_vertex(self, empty_project):
        """Test distance when nearest point is a vertex."""
        points = [(0.0, 0.0), (100.0, 0.0)]
        # Point beyond end of segment
        distance = empty_project._point_to_polyline_distance((110.0, 10.0), points)

        # Distance to endpoint (100, 0)
        expected = ((110.0 - 100.0)**2 + 10.0**2)**0.5
        assert distance == pytest.approx(expected, abs=0.001)

    def test_empty_polyline(self, empty_project):
        """Test distance returns infinity for empty polyline."""
        distance = empty_project._point_to_polyline_distance((50.0, 0.0), [])
        assert distance == float('inf')

    def test_single_point_polyline(self, empty_project):
        """Test distance for polyline with single point (degenerate segment)."""
        points = [(50.0, 0.0), (50.0, 0.0)]  # Same point twice
        distance = empty_project._point_to_polyline_distance((60.0, 0.0), points)

        assert distance == pytest.approx(10.0, abs=0.001)


class TestClearCrossJunctionRoadLinks:
    """Test clear_cross_junction_road_links method."""

    def test_clear_cross_junction_links(self, empty_project):
        """Test clearing links between roads in same junction."""
        # Create roads
        poly1 = Polyline(id="p1", line_type=LineType.CENTERLINE)
        poly1.add_point(0.0, 0.0)
        poly1.add_point(100.0, 0.0)

        poly2 = Polyline(id="p2", line_type=LineType.CENTERLINE)
        poly2.add_point(100.0, 0.0)
        poly2.add_point(200.0, 0.0)

        empty_project.add_polyline(poly1)
        empty_project.add_polyline(poly2)

        road1 = Road(id="r1", name="Road 1", centerline_id=poly1.id, polyline_ids=[poly1.id])
        road2 = Road(id="r2", name="Road 2", centerline_id=poly2.id, polyline_ids=[poly2.id])

        # Set up cross-junction links (should be cleared)
        road1.successor_id = road2.id
        road2.predecessor_id = road1.id

        empty_project.add_road(road1)
        empty_project.add_road(road2)

        # Create junction connecting both roads
        junction = Junction(id="j1", name="Test Junction")
        junction.connected_road_ids = [road1.id, road2.id]
        empty_project.add_junction(junction)

        # Clear cross-junction links
        cleared = empty_project.clear_cross_junction_road_links()

        assert cleared == 2
        assert road1.successor_id is None
        assert road2.predecessor_id is None

    def test_clear_cross_junction_links_no_junctions(self, empty_project):
        """Test clearing when no junctions returns 0."""
        cleared = empty_project.clear_cross_junction_road_links()
        assert cleared == 0

    def test_clear_cross_junction_preserves_external_links(self, empty_project):
        """Test that links to roads outside junction are preserved."""
        # Create 3 roads, only 2 in junction
        poly1 = Polyline(id="p1", line_type=LineType.CENTERLINE)
        poly1.add_point(0.0, 0.0)
        poly1.add_point(100.0, 0.0)

        poly2 = Polyline(id="p2", line_type=LineType.CENTERLINE)
        poly2.add_point(100.0, 0.0)
        poly2.add_point(200.0, 0.0)

        poly3 = Polyline(id="p3", line_type=LineType.CENTERLINE)
        poly3.add_point(200.0, 0.0)
        poly3.add_point(300.0, 0.0)

        empty_project.add_polyline(poly1)
        empty_project.add_polyline(poly2)
        empty_project.add_polyline(poly3)

        road1 = Road(id="r1", name="Road 1", centerline_id=poly1.id, polyline_ids=[poly1.id])
        road2 = Road(id="r2", name="Road 2", centerline_id=poly2.id, polyline_ids=[poly2.id])
        road3 = Road(id="r3", name="Road 3", centerline_id=poly3.id, polyline_ids=[poly3.id])

        # road2 links to both road1 (in junction) and road3 (outside junction)
        road2.predecessor_id = road1.id  # Will be cleared
        road2.successor_id = road3.id    # Should be preserved

        empty_project.add_road(road1)
        empty_project.add_road(road2)
        empty_project.add_road(road3)

        # Junction only contains road1 and road2
        junction = Junction(id="j1", name="Test Junction")
        junction.connected_road_ids = [road1.id, road2.id]
        empty_project.add_junction(junction)

        empty_project.clear_cross_junction_road_links()

        # Link within junction should be cleared
        assert road2.predecessor_id is None
        # Link outside junction should be preserved
        assert road2.successor_id == road3.id


class TestProjectRepr:
    """Test Project __repr__ method."""

    def test_empty_project_repr(self, empty_project):
        """Test repr of empty project."""
        repr_str = repr(empty_project)

        assert "polylines=0" in repr_str
        assert "roads=0" in repr_str
        assert "junctions=0" in repr_str
        assert "signals=0" in repr_str
        assert "objects=0" in repr_str
        assert "control_points=0" in repr_str

    def test_sample_project_repr(self, sample_project):
        """Test repr of sample project."""
        repr_str = repr(sample_project)

        assert "polylines=3" in repr_str
        assert "roads=1" in repr_str
        assert "control_points=3" in repr_str


class TestProjectSerializationExtended:
    """Extended tests for project serialization."""

    def test_to_dict_includes_all_fields(self, sample_project):
        """Test that to_dict includes all expected fields."""
        data = sample_project.to_dict()

        expected_fields = [
            'metadata', 'image_path', 'polylines', 'roads', 'junctions',
            'junction_groups', 'signals', 'objects', 'parking_spaces',
            'control_points', 'right_hand_traffic', 'transform_method',
            'country_code', 'map_name', 'openstreetmap_used',
            'junction_offset_distance_meters',
            'roundabout_ring_offset_distance_meters',
            'roundabout_approach_offset_distance_meters',
            'georef_validation', 'uncertainty_grid_cache',
            'uncertainty_grid_resolution', 'uncertainty_bootstrap_grid',
            'uncertainty_last_computed', 'mc_sigma_pixels',
            'baseline_uncertainty_m', 'gcp_suggestion_threshold',
            'imported_geo_reference', 'enabled_sign_libraries'
        ]

        for field in expected_fields:
            assert field in data, f"Missing field: {field}"

    def test_from_dict_roundabout_offset_migration(self, tmp_path):
        """Test migration from old roundabout_offset_distance_meters field."""
        old_data = {
            'metadata': {'version': '0.3.0'},
            'polylines': [],
            'roads': [],
            'junctions': [],
            'roundabout_offset_distance_meters': 5.0  # Old field name
        }

        project = Project.from_dict(old_data)

        # Should use old value for ring offset
        assert project.roundabout_ring_offset_distance_meters == 5.0
        # New field should have default
        assert project.roundabout_approach_offset_distance_meters == 8.0


class TestBackwardCompatibility:
    """Test backward compatibility with older project versions."""

    def test_load_project_without_lane_sections(self, tmp_path: Path):
        """Test loading old project that uses Road.lanes instead of lane_sections."""
        # Simulate old format
        old_project_data = {
            'metadata': {'version': '0.1.0'},
            'polylines': [
                {
                    'id': 'poly1',
                    'points': [[0, 0], [100, 0]],
                    'color': [255, 0, 0],
                    'closed': False,
                    'line_type': 'centerline',
                    'road_mark_type': 'none'
                }
            ],
            'roads': [
                {
                    'id': 'road1',
                    'name': 'Old Road',
                    'polyline_ids': ['poly1'],
                    'centerline_id': 'poly1',
                    'road_type': 'town',
                    'lane_info': {
                        'left_count': 1,
                        'right_count': 1,
                        'lane_width': 3.5
                    },
                    'lanes': [  # Old format
                        {'id': 1, 'lane_type': 'driving', 'width': 3.5, 'road_mark_type': 'solid'},
                        {'id': 0, 'lane_type': 'none', 'width': 0.0, 'road_mark_type': 'none'},
                        {'id': -1, 'lane_type': 'driving', 'width': 3.5, 'road_mark_type': 'broken'}
                    ]
                }
            ],
            'junctions': [],
            'signals': [],
            'objects': [],
            'control_points': [],
            'right_hand_traffic': True,
            'transform_method': 'affine'
        }

        # Save old format
        old_file = tmp_path / "old_project.orbit"
        with open(old_file, 'w') as f:
            json.dump(old_project_data, f)

        # Load and verify migration
        project = Project.load(old_file)

        assert len(project.roads) == 1
        road = project.roads[0]
        assert road.name == 'Old Road'
        # Should be migrated to lane_sections
        assert hasattr(road, 'lane_sections')

    def test_load_project_missing_optional_fields(self, tmp_path: Path):
        """Test loading project with missing optional fields uses defaults."""
        minimal_data = {
            'metadata': {'version': '0.2.0'},
            'polylines': [],
            'roads': [],
            'junctions': []
        }

        file_path = tmp_path / "minimal.orbit"
        with open(file_path, 'w') as f:
            json.dump(minimal_data, f)

        project = Project.load(file_path)

        # Should use defaults for missing fields
        assert project.control_points == []
        assert project.signals == []
        assert project.objects == []
        assert project.right_hand_traffic is True
        assert project.transform_method == 'affine'
        assert project.country_code == 'se'
        assert project.openstreetmap_used is False


class TestSplitRoadAtPoint:
    """Test split_road_at_point method."""

    def test_split_road_basic(self, empty_project):
        """Test splitting a road at a centerline point."""
        # Create centerline with multiple points
        centerline = Polyline(line_type=LineType.CENTERLINE)
        for x in range(0, 500, 50):
            centerline.add_point(float(x), 100.0)  # 10 points
        empty_project.add_polyline(centerline)

        # Create road
        road = Road(
            name="Test Road",
            centerline_id=centerline.id,
            polyline_ids=[centerline.id]
        )
        empty_project.add_road(road)

        # Split at point index 5 (middle)
        result = empty_project.split_road_at_point(road.id, centerline.id, 5)

        assert result is not None
        road1, road2 = result

        # Should have 2 roads now
        assert len(empty_project.roads) == 2

        # Road1 should be predecessor of road2
        assert road1.successor_id == road2.id
        assert road2.predecessor_id == road1.id

        # Names should have segment suffix
        assert "(seg 1/2)" in road1.name
        assert "(seg 2/2)" in road2.name

    def test_split_road_with_boundaries(self, empty_project):
        """Test splitting a road with boundary polylines."""
        # Create centerline
        centerline = Polyline(line_type=LineType.CENTERLINE)
        for x in range(0, 500, 50):
            centerline.add_point(float(x), 100.0)
        empty_project.add_polyline(centerline)

        # Create boundary
        boundary = Polyline(line_type=LineType.LANE_BOUNDARY, road_mark_type=RoadMarkType.SOLID)
        for x in range(0, 500, 50):
            boundary.add_point(float(x), 90.0)
        empty_project.add_polyline(boundary)

        # Create road with both polylines
        road = Road(
            name="Test Road",
            centerline_id=centerline.id,
            polyline_ids=[centerline.id, boundary.id]
        )
        empty_project.add_road(road)

        initial_polyline_count = len(empty_project.polylines)

        # Split at point index 5
        result = empty_project.split_road_at_point(road.id, centerline.id, 5)

        assert result is not None
        # Should have created new polylines for road2
        assert len(empty_project.polylines) >= initial_polyline_count

    def test_split_road_not_found(self, empty_project):
        """Test splitting non-existent road returns None."""
        result = empty_project.split_road_at_point("nonexistent", "nonexistent", 5)
        assert result is None

    def test_split_road_invalid_polyline(self, empty_project):
        """Test splitting with wrong polyline returns None."""
        centerline = Polyline(line_type=LineType.CENTERLINE)
        for x in range(0, 500, 50):
            centerline.add_point(float(x), 100.0)
        empty_project.add_polyline(centerline)

        road = Road(
            name="Test Road",
            centerline_id=centerline.id,
            polyline_ids=[centerline.id]
        )
        empty_project.add_road(road)

        # Try to split with non-centerline polyline ID
        result = empty_project.split_road_at_point(road.id, "wrong-polyline-id", 5)
        assert result is None

    def test_split_road_invalid_point_index(self, empty_project):
        """Test splitting at invalid point index returns None."""
        centerline = Polyline(line_type=LineType.CENTERLINE)
        for x in range(0, 500, 50):
            centerline.add_point(float(x), 100.0)  # 10 points
        empty_project.add_polyline(centerline)

        road = Road(
            name="Test Road",
            centerline_id=centerline.id,
            polyline_ids=[centerline.id]
        )
        empty_project.add_road(road)

        # Index 0 is first point (invalid)
        result = empty_project.split_road_at_point(road.id, centerline.id, 0)
        assert result is None

        # Index 9 is last point (invalid)
        result = empty_project.split_road_at_point(road.id, centerline.id, 9)
        assert result is None

    def test_split_road_updates_junction_references(self, empty_project):
        """Test that splitting updates junction references correctly."""
        # Create centerline
        centerline = Polyline(line_type=LineType.CENTERLINE)
        for x in range(0, 500, 50):
            centerline.add_point(float(x), 100.0)
        empty_project.add_polyline(centerline)

        # Create road
        road = Road(
            name="Test Road",
            centerline_id=centerline.id,
            polyline_ids=[centerline.id],
            junction_id="junction1"  # Road connects to a junction
        )
        empty_project.add_road(road)

        # Create junction
        junction = Junction(id="junction1", name="Test Junction")
        junction.connected_road_ids = [road.id]
        empty_project.add_junction(junction)

        # Split the road
        result = empty_project.split_road_at_point(road.id, centerline.id, 5)

        assert result is not None
        road1, road2 = result

        # Junction should now reference road2 (the end segment)
        assert road2.id in junction.connected_road_ids

        # road2 should have the junction_id
        assert road2.junction_id == "junction1"
        assert road1.junction_id is None


class TestMergeConsecutiveRoads:
    """Test merge_consecutive_roads method."""

    def test_merge_roads_basic(self, empty_project):
        """Test merging two consecutive roads."""
        # Create centerlines
        centerline1 = Polyline(id="p1", line_type=LineType.CENTERLINE)
        for x in range(0, 250, 50):
            centerline1.add_point(float(x), 100.0)
        empty_project.add_polyline(centerline1)

        centerline2 = Polyline(id="p2", line_type=LineType.CENTERLINE)
        for x in range(200, 500, 50):  # Overlapping start point for join
            centerline2.add_point(float(x), 100.0)
        empty_project.add_polyline(centerline2)

        # Create roads linked together
        road1 = Road(
            id="r1",
            name="Road 1",
            centerline_id=centerline1.id,
            polyline_ids=[centerline1.id]
        )
        road2 = Road(
            id="r2",
            name="Road 2",
            centerline_id=centerline2.id,
            polyline_ids=[centerline2.id],
            predecessor_id=road1.id,
            predecessor_contact="end"
        )
        road1.successor_id = road2.id
        road1.successor_contact = "start"

        empty_project.add_road(road1)
        empty_project.add_road(road2)

        assert len(empty_project.roads) == 2

        # Merge the roads
        result = empty_project.merge_consecutive_roads(road1.id, road2.id)

        assert result is not None
        assert result.id == road1.id

        # Should have only 1 road now
        assert len(empty_project.roads) == 1

        # Merged road should have road2's successor
        assert result.successor_id == road2.successor_id

    def test_merge_roads_not_consecutive(self, empty_project):
        """Test merging non-consecutive roads returns None."""
        # Create two unlinked roads
        centerline1 = Polyline(line_type=LineType.CENTERLINE)
        centerline1.add_point(0.0, 0.0)
        centerline1.add_point(100.0, 0.0)
        empty_project.add_polyline(centerline1)

        centerline2 = Polyline(line_type=LineType.CENTERLINE)
        centerline2.add_point(200.0, 0.0)
        centerline2.add_point(300.0, 0.0)
        empty_project.add_polyline(centerline2)

        road1 = Road(name="Road 1", centerline_id=centerline1.id, polyline_ids=[centerline1.id])
        road2 = Road(name="Road 2", centerline_id=centerline2.id, polyline_ids=[centerline2.id])
        # Not linked

        empty_project.add_road(road1)
        empty_project.add_road(road2)

        result = empty_project.merge_consecutive_roads(road1.id, road2.id)
        assert result is None

    def test_merge_roads_not_found(self, empty_project):
        """Test merging non-existent roads returns None."""
        result = empty_project.merge_consecutive_roads("nonexistent1", "nonexistent2")
        assert result is None

    def test_merge_roads_removes_segment_suffix(self, empty_project):
        """Test that merging removes segment suffix from name."""
        centerline1 = Polyline(id="p1", line_type=LineType.CENTERLINE)
        for x in range(0, 250, 50):
            centerline1.add_point(float(x), 100.0)
        empty_project.add_polyline(centerline1)

        centerline2 = Polyline(id="p2", line_type=LineType.CENTERLINE)
        for x in range(200, 500, 50):
            centerline2.add_point(float(x), 100.0)
        empty_project.add_polyline(centerline2)

        road1 = Road(
            id="r1",
            name="Test Road (seg 1/2)",  # Has segment suffix
            centerline_id=centerline1.id,
            polyline_ids=[centerline1.id]
        )
        road2 = Road(
            id="r2",
            name="Test Road (seg 2/2)",
            centerline_id=centerline2.id,
            polyline_ids=[centerline2.id],
            predecessor_id=road1.id
        )
        road1.successor_id = road2.id

        empty_project.add_road(road1)
        empty_project.add_road(road2)

        result = empty_project.merge_consecutive_roads(road1.id, road2.id)

        assert result is not None
        # Segment suffix should be removed
        assert "(seg" not in result.name
        assert result.name == "Test Road"

    def test_merge_roads_updates_junction_references(self, empty_project):
        """Test that merging updates junction references."""
        centerline1 = Polyline(id="p1", line_type=LineType.CENTERLINE)
        for x in range(0, 250, 50):
            centerline1.add_point(float(x), 100.0)
        empty_project.add_polyline(centerline1)

        centerline2 = Polyline(id="p2", line_type=LineType.CENTERLINE)
        for x in range(200, 500, 50):
            centerline2.add_point(float(x), 100.0)
        empty_project.add_polyline(centerline2)

        road1 = Road(id="r1", name="Road 1", centerline_id=centerline1.id, polyline_ids=[centerline1.id])
        road2 = Road(
            id="r2",
            name="Road 2",
            centerline_id=centerline2.id,
            polyline_ids=[centerline2.id],
            predecessor_id=road1.id
        )
        road1.successor_id = road2.id

        empty_project.add_road(road1)
        empty_project.add_road(road2)

        # Create junction referencing road2
        junction = Junction(id="j1", name="Test Junction")
        junction.connected_road_ids = [road2.id]
        empty_project.add_junction(junction)

        result = empty_project.merge_consecutive_roads(road1.id, road2.id)

        assert result is not None
        # Junction should now reference road1 (the kept road)
        assert road1.id in junction.connected_road_ids
        assert road2.id not in junction.connected_road_ids


class TestRemapJunctionsAfterRoadSplit:
    """Test _remap_junctions_after_road_split helper method."""

    def test_remap_connected_road_ids(self, empty_project):
        """Test that connected_road_ids are remapped."""
        # Create minimal setup
        centerline = Polyline(line_type=LineType.CENTERLINE)
        centerline.add_point(0.0, 0.0)
        centerline.add_point(100.0, 0.0)
        empty_project.add_polyline(centerline)

        road1 = Road(name="Road 1", centerline_id=centerline.id, polyline_ids=[centerline.id])
        road2 = Road(name="Road 2", centerline_id=centerline.id, polyline_ids=[centerline.id])
        empty_project.add_road(road1)
        empty_project.add_road(road2)

        junction = Junction(name="Test Junction")
        junction.connected_road_ids = [road1.id]
        empty_project.add_junction(junction)

        empty_project._remap_junctions_after_road_split(
            road1.id, road2.id, None, successor_junction_id=junction.id)

        assert road2.id in junction.connected_road_ids
        assert road1.id not in junction.connected_road_ids

    def test_remap_entry_exit_roads(self, empty_project):
        """Test that entry and exit roads are remapped for roundabouts."""
        centerline = Polyline(line_type=LineType.CENTERLINE)
        centerline.add_point(0.0, 0.0)
        centerline.add_point(100.0, 0.0)
        empty_project.add_polyline(centerline)

        road1 = Road(name="Road 1", centerline_id=centerline.id, polyline_ids=[centerline.id])
        road2 = Road(name="Road 2", centerline_id=centerline.id, polyline_ids=[centerline.id])
        empty_project.add_road(road1)
        empty_project.add_road(road2)

        # Roundabout junctions use entry_roads and exit_roads
        junction = Junction(name="Roundabout")
        junction.entry_roads = [road1.id]
        junction.exit_roads = [road1.id]
        empty_project.add_junction(junction)

        empty_project._remap_junctions_after_road_split(
            road1.id, road2.id, None, successor_junction_id=junction.id)

        assert road2.id in junction.entry_roads
        assert road2.id in junction.exit_roads

    def test_remap_transfers_junction_id(self, empty_project):
        """Test that junction_id is transferred to new road."""
        centerline = Polyline(line_type=LineType.CENTERLINE)
        centerline.add_point(0.0, 0.0)
        centerline.add_point(100.0, 0.0)
        empty_project.add_polyline(centerline)

        road1 = Road(name="Road 1", centerline_id=centerline.id, polyline_ids=[centerline.id])
        road2 = Road(name="Road 2", centerline_id=centerline.id, polyline_ids=[centerline.id])
        empty_project.add_road(road1)
        empty_project.add_road(road2)

        junction = Junction(id="junc1", name="Test Junction")
        empty_project.add_junction(junction)

        empty_project._remap_junctions_after_road_split(road1.id, road2.id, "junc1")

        assert road2.junction_id == "junc1"
        assert road1.junction_id is None


class TestRemapJunctionsAfterRoadMerge:
    """Test _remap_junctions_after_road_merge helper method."""

    def test_remap_removes_deleted_road(self, empty_project):
        """Test that deleted road is removed from connected_road_ids."""
        centerline = Polyline(line_type=LineType.CENTERLINE)
        centerline.add_point(0.0, 0.0)
        centerline.add_point(100.0, 0.0)
        empty_project.add_polyline(centerline)

        road1 = Road(name="Road 1", centerline_id=centerline.id, polyline_ids=[centerline.id])
        road2 = Road(name="Road 2", centerline_id=centerline.id, polyline_ids=[centerline.id])
        empty_project.add_road(road1)
        empty_project.add_road(road2)

        junction = Junction(name="Test Junction")
        junction.connected_road_ids = [road2.id]
        empty_project.add_junction(junction)

        empty_project._remap_junctions_after_road_merge(road1.id, road2.id)

        assert road1.id in junction.connected_road_ids
        assert road2.id not in junction.connected_road_ids

    def test_remap_avoids_duplicates(self, empty_project):
        """Test that road1 is not added twice to connected_road_ids."""
        centerline = Polyline(line_type=LineType.CENTERLINE)
        centerline.add_point(0.0, 0.0)
        centerline.add_point(100.0, 0.0)
        empty_project.add_polyline(centerline)

        road1 = Road(name="Road 1", centerline_id=centerline.id, polyline_ids=[centerline.id])
        road2 = Road(name="Road 2", centerline_id=centerline.id, polyline_ids=[centerline.id])
        empty_project.add_road(road1)
        empty_project.add_road(road2)

        junction = Junction(name="Test Junction")
        # Both roads already in the list
        junction.connected_road_ids = [road1.id, road2.id]
        empty_project.add_junction(junction)

        empty_project._remap_junctions_after_road_merge(road1.id, road2.id)

        # Should have road1 only once
        assert junction.connected_road_ids.count(road1.id) == 1
        assert road2.id not in junction.connected_road_ids

    def test_remap_updates_lane_connections(self, empty_project):
        """Test that lane connections are updated."""
        from orbit.models.junction import LaneConnection

        centerline = Polyline(line_type=LineType.CENTERLINE)
        centerline.add_point(0.0, 0.0)
        centerline.add_point(100.0, 0.0)
        empty_project.add_polyline(centerline)

        road1 = Road(name="Road 1", centerline_id=centerline.id, polyline_ids=[centerline.id])
        road2 = Road(name="Road 2", centerline_id=centerline.id, polyline_ids=[centerline.id])
        empty_project.add_road(road1)
        empty_project.add_road(road2)

        junction = Junction(name="Test Junction")
        lane_conn = LaneConnection(
            from_road_id=road2.id,
            from_lane_id=-1,
            to_road_id="other_road",
            to_lane_id=-1
        )
        junction.lane_connections = [lane_conn]
        empty_project.add_junction(junction)

        empty_project._remap_junctions_after_road_merge(road1.id, road2.id)

        assert lane_conn.from_road_id == road1.id


class TestFindNearbyRoadEndpoints:
    """Test find_nearby_road_endpoints method."""

    def _make_road(self, project, start, end, road_name="Road"):
        """Helper to create a road with a 2-point centerline."""
        cl = Polyline(line_type=LineType.CENTERLINE)
        cl.add_point(start[0], start[1])
        cl.add_point(end[0], end[1])
        project.add_polyline(cl)
        road = Road(name=road_name, centerline_id=cl.id, polyline_ids=[cl.id])
        project.add_road(road)
        return road

    def test_finds_nearby_start(self, empty_project):
        """Test detection of a nearby start point."""
        road = self._make_road(empty_project, (100, 100), (300, 100))
        results = empty_project.find_nearby_road_endpoints((105, 100))
        assert len(results) == 1
        assert results[0][0] == road.id
        assert results[0][2] == 0  # start point

    def test_finds_nearby_end(self, empty_project):
        """Test detection of a nearby end point."""
        road = self._make_road(empty_project, (100, 100), (300, 100))
        results = empty_project.find_nearby_road_endpoints((295, 100))
        assert len(results) == 1
        assert results[0][0] == road.id
        assert results[0][2] == -1  # end point

    def test_excludes_specified_road(self, empty_project):
        """Test that the excluded road is not returned."""
        road = self._make_road(empty_project, (100, 100), (300, 100))
        results = empty_project.find_nearby_road_endpoints(
            (105, 100), exclude_road_id=road.id)
        assert len(results) == 0

    def test_skips_junction_roads(self, empty_project):
        """Test that roads with junction_id are skipped."""
        road = self._make_road(empty_project, (100, 100), (300, 100))
        road.junction_id = "some_junction"
        results = empty_project.find_nearby_road_endpoints((105, 100))
        assert len(results) == 0

    def test_respects_tolerance(self, empty_project):
        """Test that points outside tolerance are not returned."""
        self._make_road(empty_project, (100, 100), (300, 100))
        # 25 pixels away, default tolerance is 20
        results = empty_project.find_nearby_road_endpoints((125, 100))
        assert len(results) == 0

    def test_sorted_by_distance(self, empty_project):
        """Test that results are sorted closest-first."""
        self._make_road(empty_project, (100, 100), (300, 100), "Road A")
        self._make_road(empty_project, (110, 100), (400, 100), "Road B")
        results = empty_project.find_nearby_road_endpoints((105, 100))
        assert len(results) == 2
        assert results[0][4] <= results[1][4]  # first is closer

    def test_no_roads_returns_empty(self, empty_project):
        """Test empty project returns no results."""
        results = empty_project.find_nearby_road_endpoints((100, 100))
        assert results == []

    def test_skips_roads_without_centerline(self, empty_project):
        """Test that roads without a centerline are skipped."""
        road = Road(name="No CL", polyline_ids=[])
        empty_project.add_road(road)
        results = empty_project.find_nearby_road_endpoints((0, 0))
        assert results == []

    def test_self_connection_excluded(self, empty_project):
        """Test excluding self-road prevents self-connection suggestions."""
        road = self._make_road(empty_project, (100, 100), (120, 100))
        # Point near start, exclude self
        results = empty_project.find_nearby_road_endpoints(
            (120, 100), exclude_road_id=road.id)
        assert len(results) == 0


class TestEnforceRoadLinkCoordinates:
    """Test enforce_road_link_coordinates method."""

    def _make_road(self, project, start, end, road_name="Road"):
        """Helper to create a road with a 2-point centerline."""
        cl = Polyline(line_type=LineType.CENTERLINE)
        cl.add_point(start[0], start[1])
        cl.add_point(end[0], end[1])
        project.add_polyline(cl)
        road = Road(name=road_name, centerline_id=cl.id, polyline_ids=[cl.id])
        project.add_road(road)
        return road

    def test_snaps_start_to_predecessor_end(self, empty_project):
        """Test that road start is snapped to predecessor's end."""
        road_a = self._make_road(empty_project, (0, 0), (100, 0), "A")
        road_b = self._make_road(empty_project, (105, 5), (200, 0), "B")

        road_b.predecessor_id = road_a.id
        road_b.predecessor_contact = "end"

        changed = empty_project.enforce_road_link_coordinates(road_b.id)

        assert changed is True
        cl_b = empty_project.get_polyline(road_b.centerline_id)
        assert cl_b.points[0] == (100.0, 0.0)

    def test_snaps_end_to_successor_start(self, empty_project):
        """Test that road end is snapped to successor's start."""
        road_a = self._make_road(empty_project, (0, 0), (95, 5), "A")
        road_b = self._make_road(empty_project, (100, 0), (200, 0), "B")

        road_a.successor_id = road_b.id
        road_a.successor_contact = "start"

        changed = empty_project.enforce_road_link_coordinates(road_a.id)

        assert changed is True
        cl_a = empty_project.get_polyline(road_a.centerline_id)
        assert cl_a.points[-1] == (100.0, 0.0)

    def test_no_change_when_already_aligned(self, empty_project):
        """Test returns False when endpoints already match."""
        road_a = self._make_road(empty_project, (0, 0), (100, 0), "A")
        road_b = self._make_road(empty_project, (100, 0), (200, 0), "B")

        road_b.predecessor_id = road_a.id
        road_b.predecessor_contact = "end"

        changed = empty_project.enforce_road_link_coordinates(road_b.id)
        assert changed is False

    def test_no_change_without_links(self, empty_project):
        """Test returns False when road has no predecessor/successor."""
        road = self._make_road(empty_project, (0, 0), (100, 0))
        changed = empty_project.enforce_road_link_coordinates(road.id)
        assert changed is False

    def test_skips_junction_linked_predecessor(self, empty_project):
        """Test that junction-linked predecessors are not enforced."""
        road_a = self._make_road(empty_project, (0, 0), (100, 0), "A")
        road_b = self._make_road(empty_project, (105, 5), (200, 0), "B")

        road_b.predecessor_id = road_a.id
        road_b.predecessor_contact = "end"
        road_b.predecessor_junction_id = "some_junction"

        changed = empty_project.enforce_road_link_coordinates(road_b.id)
        assert changed is False
        cl_b = empty_project.get_polyline(road_b.centerline_id)
        assert cl_b.points[0] == (105.0, 5.0)  # unchanged

    def test_predecessor_contact_start(self, empty_project):
        """Test predecessor_contact='start' uses predecessor's first point."""
        road_a = self._make_road(empty_project, (50, 0), (100, 0), "A")
        road_b = self._make_road(empty_project, (55, 5), (200, 0), "B")

        road_b.predecessor_id = road_a.id
        road_b.predecessor_contact = "start"

        changed = empty_project.enforce_road_link_coordinates(road_b.id)

        assert changed is True
        cl_b = empty_project.get_polyline(road_b.centerline_id)
        assert cl_b.points[0] == (50.0, 0.0)

    def test_successor_contact_end(self, empty_project):
        """Test successor_contact='end' uses successor's last point."""
        road_a = self._make_road(empty_project, (0, 0), (95, 5), "A")
        road_b = self._make_road(empty_project, (100, 0), (200, 0), "B")

        road_a.successor_id = road_b.id
        road_a.successor_contact = "end"

        changed = empty_project.enforce_road_link_coordinates(road_a.id)

        assert changed is True
        cl_a = empty_project.get_polyline(road_a.centerline_id)
        assert cl_a.points[-1] == (200.0, 0.0)

    def test_nonexistent_road_returns_false(self, empty_project):
        """Test with non-existent road ID."""
        changed = empty_project.enforce_road_link_coordinates("nonexistent")
        assert changed is False

    def test_both_ends_enforced(self, empty_project):
        """Test that both predecessor and successor are enforced together."""
        road_a = self._make_road(empty_project, (0, 0), (100, 0), "A")
        road_b = self._make_road(empty_project, (105, 5), (195, 5), "B")
        road_c = self._make_road(empty_project, (200, 0), (300, 0), "C")

        road_b.predecessor_id = road_a.id
        road_b.predecessor_contact = "end"
        road_b.successor_id = road_c.id
        road_b.successor_contact = "start"

        changed = empty_project.enforce_road_link_coordinates(road_b.id)

        assert changed is True
        cl_b = empty_project.get_polyline(road_b.centerline_id)
        assert cl_b.points[0] == (100.0, 0.0)
        assert cl_b.points[-1] == (200.0, 0.0)

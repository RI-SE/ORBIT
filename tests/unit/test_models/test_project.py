"""
Unit tests for Project model.

Tests project creation, serialization, save/load, and element management.
"""

import pytest
import json
from pathlib import Path
from datetime import datetime

from orbit.models import (
    Project, ControlPoint, Polyline, LineType, RoadMarkType,
    Road, RoadType, Junction
)


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
        assert empty_project.metadata['version'] == '0.3.1'

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
        assert sample_project.metadata['version'] == '0.3.1'
        # Created timestamp should be updated
        assert sample_project.metadata['created'] != old_created


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

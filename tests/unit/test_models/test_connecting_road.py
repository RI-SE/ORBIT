"""
Unit tests for ConnectingRoad model.

Tests connecting road creation, geometry calculations, and serialization.
"""

import math

import pytest

from orbit.models import ConnectingRoad


class TestConnectingRoadCreation:
    """Test connecting road initialization and basic properties."""

    def test_default_creation(self):
        """Test creating connecting road with defaults."""
        cr = ConnectingRoad()

        assert cr.id == ""
        assert cr.path == []
        assert cr.lane_count_left == 0
        assert cr.lane_count_right == 1
        assert cr.lane_width == 3.5
        assert cr.predecessor_road_id == ""
        assert cr.successor_road_id == ""
        assert cr.contact_point_start == "end"
        assert cr.contact_point_end == "start"

    def test_creation_with_path(self):
        """Test creating connecting road with path."""
        path = [(0.0, 0.0), (50.0, 25.0), (100.0, 50.0)]
        cr = ConnectingRoad(path=path)

        assert cr.path == path
        assert len(cr.path) == 3

    def test_creation_with_lane_config(self):
        """Test creating connecting road with lane configuration."""
        cr = ConnectingRoad(
            lane_count_left=1,
            lane_count_right=2,
            lane_width=3.0
        )

        assert cr.lane_count_left == 1
        assert cr.lane_count_right == 2
        assert cr.lane_width == 3.0
        assert cr.get_total_lane_count() == 3

    def test_creation_with_road_references(self):
        """Test creating connecting road with predecessor/successor."""
        cr = ConnectingRoad(
            predecessor_road_id="road_in",
            successor_road_id="road_out",
            contact_point_start="end",
            contact_point_end="start"
        )

        assert cr.predecessor_road_id == "road_in"
        assert cr.successor_road_id == "road_out"
        assert cr.contact_point_start == "end"
        assert cr.contact_point_end == "start"


class TestConnectingRoadGeometry:
    """Test geometric calculations for connecting roads."""

    def test_length_calculation_empty_path(self):
        """Test length calculation for empty path."""
        cr = ConnectingRoad(path=[])
        assert cr.get_length_pixels() == 0.0

    def test_length_calculation_single_point(self):
        """Test length calculation for single point."""
        cr = ConnectingRoad(path=[(0.0, 0.0)])
        assert cr.get_length_pixels() == 0.0

    def test_length_calculation_straight_line(self):
        """Test length calculation for straight line."""
        cr = ConnectingRoad(path=[(0.0, 0.0), (100.0, 0.0)])
        assert cr.get_length_pixels() == pytest.approx(100.0)

    def test_length_calculation_diagonal(self):
        """Test length calculation for diagonal line."""
        # 3-4-5 triangle
        cr = ConnectingRoad(path=[(0.0, 0.0), (30.0, 40.0)])
        assert cr.get_length_pixels() == pytest.approx(50.0)

    def test_length_calculation_multi_segment(self):
        """Test length calculation for multiple segments."""
        cr = ConnectingRoad(path=[
            (0.0, 0.0),
            (10.0, 0.0),
            (10.0, 10.0),
            (0.0, 10.0)
        ])
        # Three segments: 10 + 10 + 10 = 30
        assert cr.get_length_pixels() == pytest.approx(30.0)

    def test_start_point_retrieval(self):
        """Test getting start point of path."""
        path = [(10.0, 20.0), (30.0, 40.0), (50.0, 60.0)]
        cr = ConnectingRoad(path=path)

        start = cr.get_start_point()
        assert start == (10.0, 20.0)

    def test_end_point_retrieval(self):
        """Test getting end point of path."""
        path = [(10.0, 20.0), (30.0, 40.0), (50.0, 60.0)]
        cr = ConnectingRoad(path=path)

        end = cr.get_end_point()
        assert end == (50.0, 60.0)

    def test_start_point_empty_path(self):
        """Test getting start point from empty path."""
        cr = ConnectingRoad(path=[])
        assert cr.get_start_point() is None

    def test_end_point_empty_path(self):
        """Test getting end point from empty path."""
        cr = ConnectingRoad(path=[])
        assert cr.get_end_point() is None


class TestConnectingRoadHeading:
    """Test heading calculations for connecting roads."""

    def test_start_heading_eastward(self):
        """Test start heading for eastward path."""
        cr = ConnectingRoad(path=[(0.0, 0.0), (100.0, 0.0)])
        heading = cr.get_start_heading()

        assert heading is not None
        assert heading == pytest.approx(0.0)  # 0 radians = east

    def test_start_heading_northward(self):
        """Test start heading for northward path."""
        cr = ConnectingRoad(path=[(0.0, 0.0), (0.0, 100.0)])
        heading = cr.get_start_heading()

        assert heading is not None
        assert heading == pytest.approx(math.pi / 2)  # π/2 radians = north

    def test_start_heading_westward(self):
        """Test start heading for westward path."""
        cr = ConnectingRoad(path=[(100.0, 0.0), (0.0, 0.0)])
        heading = cr.get_start_heading()

        assert heading is not None
        assert abs(heading) == pytest.approx(math.pi)  # π radians = west

    def test_start_heading_southward(self):
        """Test start heading for southward path."""
        cr = ConnectingRoad(path=[(0.0, 100.0), (0.0, 0.0)])
        heading = cr.get_start_heading()

        assert heading is not None
        assert heading == pytest.approx(-math.pi / 2)  # -π/2 radians = south

    def test_end_heading(self):
        """Test end heading calculation."""
        cr = ConnectingRoad(path=[
            (0.0, 0.0),
            (50.0, 0.0),
            (100.0, 50.0)
        ])
        heading = cr.get_end_heading()

        assert heading is not None
        # Last segment goes from (50,0) to (100,50) - northeast
        assert heading == pytest.approx(math.atan2(50, 50))

    def test_heading_insufficient_points(self):
        """Test heading calculation with insufficient points."""
        cr = ConnectingRoad(path=[(0.0, 0.0)])
        assert cr.get_start_heading() is None
        assert cr.get_end_heading() is None


class TestConnectingRoadLanes:
    """Test lane-related functions for connecting roads."""

    def test_total_lane_count_single_lane(self):
        """Test total lane count with single right lane."""
        cr = ConnectingRoad(lane_count_left=0, lane_count_right=1)
        assert cr.get_total_lane_count() == 1

    def test_total_lane_count_multi_lane(self):
        """Test total lane count with multiple lanes."""
        cr = ConnectingRoad(lane_count_left=2, lane_count_right=2)
        assert cr.get_total_lane_count() == 4

    def test_total_lane_count_left_only(self):
        """Test total lane count with only left lanes."""
        cr = ConnectingRoad(lane_count_left=3, lane_count_right=0)
        assert cr.get_total_lane_count() == 3


class TestConnectingRoadSerialization:
    """Test connecting road to_dict/from_dict serialization."""

    def test_to_dict_minimal(self):
        """Test converting minimal connecting road to dictionary."""
        cr = ConnectingRoad()
        data = cr.to_dict()

        assert 'id' in data
        assert data['path'] == []
        assert data['lane_count_left'] == 0
        assert data['lane_count_right'] == 1
        assert data['lane_width'] == 3.5
        assert data['predecessor_road_id'] == ""
        assert data['successor_road_id'] == ""
        assert data['contact_point_start'] == "end"
        assert data['contact_point_end'] == "start"

    def test_to_dict_complete(self):
        """Test converting complete connecting road to dictionary."""
        path = [(0.0, 0.0), (50.0, 25.0), (100.0, 50.0)]
        cr = ConnectingRoad(
            path=path,
            lane_count_left=1,
            lane_count_right=2,
            lane_width=3.0,
            predecessor_road_id="road_A",
            successor_road_id="road_B",
            contact_point_start="end",
            contact_point_end="start"
        )
        data = cr.to_dict()

        assert data['path'] == [[0.0, 0.0], [50.0, 25.0], [100.0, 50.0]]
        assert data['lane_count_left'] == 1
        assert data['lane_count_right'] == 2
        assert data['lane_width'] == 3.0
        assert data['predecessor_road_id'] == "road_A"
        assert data['successor_road_id'] == "road_B"

    def test_from_dict_minimal(self):
        """Test creating connecting road from minimal dictionary."""
        data = {
            'id': 'test_id',
            'path': [],
            'lane_count_left': 0,
            'lane_count_right': 1,
            'lane_width': 3.5,
            'predecessor_road_id': '',
            'successor_road_id': '',
            'contact_point_start': 'end',
            'contact_point_end': 'start'
        }

        cr = ConnectingRoad.from_dict(data)

        assert cr.id == 'test_id'
        assert cr.path == []
        assert cr.lane_count_left == 0
        assert cr.lane_count_right == 1

    def test_from_dict_complete(self):
        """Test creating connecting road from complete dictionary."""
        data = {
            'id': 'conn_123',
            'path': [[10.0, 20.0], [30.0, 40.0], [50.0, 60.0]],
            'lane_count_left': 2,
            'lane_count_right': 3,
            'lane_width': 3.2,
            'predecessor_road_id': 'road_X',
            'successor_road_id': 'road_Y',
            'contact_point_start': 'start',
            'contact_point_end': 'end'
        }

        cr = ConnectingRoad.from_dict(data)

        assert cr.id == 'conn_123'
        assert cr.path == [(10.0, 20.0), (30.0, 40.0), (50.0, 60.0)]
        assert cr.lane_count_left == 2
        assert cr.lane_count_right == 3
        assert cr.lane_width == 3.2
        assert cr.predecessor_road_id == 'road_X'
        assert cr.successor_road_id == 'road_Y'
        assert cr.contact_point_start == 'start'
        assert cr.contact_point_end == 'end'

    def test_roundtrip_serialization(self):
        """Test connecting road → dict → connecting road preserves data."""
        path = [(0.0, 0.0), (25.0, 50.0), (50.0, 100.0)]
        original = ConnectingRoad(
            path=path,
            lane_count_left=1,
            lane_count_right=2,
            lane_width=3.3,
            predecessor_road_id="road_1",
            successor_road_id="road_2"
        )

        data = original.to_dict()
        restored = ConnectingRoad.from_dict(data)

        assert restored.path == original.path
        assert restored.lane_count_left == original.lane_count_left
        assert restored.lane_count_right == original.lane_count_right
        assert restored.lane_width == pytest.approx(original.lane_width)
        assert restored.predecessor_road_id == original.predecessor_road_id
        assert restored.successor_road_id == original.successor_road_id

    def test_from_dict_with_missing_fields(self):
        """Test creating connecting road from dict with missing optional fields."""
        data = {
            'id': 'test_conn'
            # Missing other fields - should use defaults
        }

        cr = ConnectingRoad.from_dict(data)

        assert cr.id == 'test_conn'
        assert cr.path == []
        assert cr.lane_count_left == 0
        assert cr.lane_count_right == 1
        assert cr.lane_width == 3.5


class TestConnectingRoadRepr:
    """Test string representation of connecting road."""

    def test_repr_format(self):
        """Test __repr__ produces readable string."""
        cr = ConnectingRoad(
            path=[(0, 0), (100, 100)],
            predecessor_road_id="road_abc123",
            successor_road_id="road_xyz789"
        )

        repr_str = repr(cr)

        assert "ConnectingRoad" in repr_str
        assert "points=2" in repr_str
        assert "lanes=1" in repr_str
        assert "road_abc" in repr_str  # First 8 chars of ID
        assert "road_xyz" in repr_str


class TestConnectingRoadGeoCoordinates:
    """Test geographic coordinate handling."""

    def test_has_geo_coords_false_when_none(self):
        """Test has_geo_coords returns False when geo_path is None."""
        cr = ConnectingRoad(path=[(0, 0), (100, 100)])
        assert cr.has_geo_coords() is False

    def test_has_geo_coords_false_when_empty(self):
        """Test has_geo_coords returns False when geo_path is empty."""
        cr = ConnectingRoad(path=[(0, 0), (100, 100)])
        cr.geo_path = []
        assert cr.has_geo_coords() is False

    def test_has_geo_coords_true_when_set(self):
        """Test has_geo_coords returns True when geo_path is set."""
        cr = ConnectingRoad(path=[(0, 0), (100, 100)])
        cr.geo_path = [(12.94, 57.72), (12.95, 57.73)]
        assert cr.has_geo_coords() is True

    def test_get_pixel_path_without_transformer(self):
        """Test get_pixel_path returns stored path when no transformer."""
        path = [(10, 20), (30, 40)]
        cr = ConnectingRoad(path=path)
        cr.geo_path = [(12.94, 57.72), (12.95, 57.73)]
        assert cr.get_pixel_path(transformer=None) == path

    def test_get_pixel_path_with_transformer(self):
        """Test get_pixel_path uses transformer when available."""
        path = [(10, 20), (30, 40)]
        geo_path = [(12.94, 57.72), (12.95, 57.73)]
        cr = ConnectingRoad(path=path)
        cr.geo_path = geo_path

        # Create a mock transformer
        class MockTransformer:
            def geo_to_pixel(self, lon, lat):
                return (lon * 100, lat * 100)

        result = cr.get_pixel_path(MockTransformer())
        assert result == [(1294.0, 5772.0), (1295.0, 5773.0)]

    def test_update_pixel_path_from_geo(self):
        """Test updating pixel path from geo coordinates."""
        cr = ConnectingRoad(path=[(0, 0)])
        cr.geo_path = [(12.94, 57.72), (12.95, 57.73)]

        class MockTransformer:
            def geo_to_pixel(self, lon, lat):
                return (lon * 10, lat * 10)

        cr.update_pixel_path_from_geo(MockTransformer())
        assert cr.path == [(129.4, 577.2), (129.5, 577.3)]

    def test_update_pixel_path_does_nothing_without_geo(self):
        """Test that update_pixel_path_from_geo does nothing without geo_path."""
        original_path = [(10, 20), (30, 40)]
        cr = ConnectingRoad(path=original_path.copy())
        cr.geo_path = None

        class MockTransformer:
            def geo_to_pixel(self, lon, lat):
                return (0, 0)

        cr.update_pixel_path_from_geo(MockTransformer())
        assert cr.path == original_path

    def test_initialize_geo_path_from_pixels(self):
        """Test initializing geo path from pixel coordinates."""
        cr = ConnectingRoad(path=[(100, 200), (300, 400)])
        assert cr.geo_path is None

        class MockTransformer:
            def pixel_to_geo(self, x, y):
                return (x / 10, y / 10)

        cr.initialize_geo_path_from_pixels(MockTransformer())
        assert cr.geo_path == [(10.0, 20.0), (30.0, 40.0)]

    def test_initialize_geo_path_skips_if_already_set(self):
        """Test that initialize_geo_path doesn't overwrite existing geo_path."""
        cr = ConnectingRoad(path=[(100, 200)])
        cr.geo_path = [(12.94, 57.72)]

        class MockTransformer:
            def pixel_to_geo(self, x, y):
                return (0.0, 0.0)

        cr.initialize_geo_path_from_pixels(MockTransformer())
        # Should not change existing geo_path
        assert cr.geo_path == [(12.94, 57.72)]


class TestConnectingRoadStoredHeadings:
    """Test stored heading handling from junction analysis."""

    def test_stored_start_heading_preferred(self):
        """Test that stored start heading is used over calculated."""
        cr = ConnectingRoad(path=[(0, 0), (100, 0)])  # Would give heading=0
        cr.stored_start_heading = 1.5  # Different value
        assert cr.get_start_heading() == 1.5

    def test_stored_end_heading_preferred(self):
        """Test that stored end heading is used over calculated."""
        cr = ConnectingRoad(path=[(0, 0), (100, 0)])  # Would give heading=0
        cr.stored_end_heading = -0.5  # Different value
        assert cr.get_end_heading() == -0.5

    def test_fallback_to_calculated_heading(self):
        """Test fallback to calculated heading when stored is None."""
        cr = ConnectingRoad(path=[(0, 0), (100, 0)])
        assert cr.stored_start_heading is None
        assert cr.stored_end_heading is None
        assert cr.get_start_heading() == pytest.approx(0.0)
        assert cr.get_end_heading() == pytest.approx(0.0)


class TestConnectingRoadStoredHeadingUpdates:
    """Test that stored headings update correctly on path regeneration."""

    def test_stored_headings_roundtrip_serialization(self):
        """Test stored headings survive to_dict/from_dict roundtrip."""
        cr = ConnectingRoad(path=[(0, 0), (100, 0)])
        cr.stored_start_heading = 0.785
        cr.stored_end_heading = -1.571

        data = cr.to_dict()
        restored = ConnectingRoad.from_dict(data)

        assert restored.stored_start_heading == pytest.approx(0.785)
        assert restored.stored_end_heading == pytest.approx(-1.571)
        assert restored.get_start_heading() == pytest.approx(0.785)
        assert restored.get_end_heading() == pytest.approx(-1.571)

    def test_stored_heading_overrides_path_derived(self):
        """Test that stored heading takes priority over path-derived heading."""
        # Path points eastward (heading ~0), but stored heading points north
        cr = ConnectingRoad(path=[(0, 0), (100, 0), (200, 0)])
        cr.stored_start_heading = math.pi / 2  # North
        cr.stored_end_heading = -math.pi / 2   # South

        assert cr.get_start_heading() == pytest.approx(math.pi / 2)
        assert cr.get_end_heading() == pytest.approx(-math.pi / 2)

    def test_clearing_stored_heading_falls_back_to_path(self):
        """Test clearing stored heading reverts to path-based calculation."""
        cr = ConnectingRoad(path=[(0, 0), (100, 0)])
        cr.stored_start_heading = 1.0
        assert cr.get_start_heading() == pytest.approx(1.0)

        # Clear stored heading
        cr.stored_start_heading = None
        # Should fall back to path-derived (eastward = 0)
        assert cr.get_start_heading() == pytest.approx(0.0)


class TestConnectingRoadSampleCount:
    """Test that connection path generation uses sufficient sample points."""

    def test_default_sample_count_is_50(self):
        """Test generate_simple_connection_path defaults to 50 points."""
        from orbit.utils.geometry import generate_simple_connection_path

        path, coeffs = generate_simple_connection_path(
            from_pos=(0.0, 0.0),
            from_heading=0.0,
            to_pos=(100.0, 100.0),
            to_heading=math.pi / 2,
        )
        assert len(path) == 50

    def test_explicit_sample_count_respected(self):
        """Test explicit num_points overrides default."""
        from orbit.utils.geometry import generate_simple_connection_path

        path, coeffs = generate_simple_connection_path(
            from_pos=(0.0, 0.0),
            from_heading=0.0,
            to_pos=(100.0, 100.0),
            to_heading=math.pi / 2,
            num_points=30,
        )
        assert len(path) == 30


class TestConnectingRoadLaneManagement:
    """Test lane initialization and management."""

    def test_ensure_lanes_initialized(self):
        """Test that lanes are auto-initialized from lane counts."""
        cr = ConnectingRoad(lane_count_left=1, lane_count_right=2)
        assert cr.lanes == []
        cr.ensure_lanes_initialized()
        # Should have: center (0), right (-1, -2), left (1)
        assert len(cr.lanes) == 4  # center + 2 right + 1 left
        lane_ids = [lane.id for lane in cr.lanes]
        assert 0 in lane_ids
        assert -1 in lane_ids
        assert -2 in lane_ids
        assert 1 in lane_ids

    def test_get_lane_ids(self):
        """Test getting list of lane IDs."""
        cr = ConnectingRoad(lane_count_left=2, lane_count_right=3)
        lane_ids = cr.get_lane_ids()
        # Right lanes first, then left
        assert lane_ids == [-1, -2, -3, 1, 2]

    def test_get_lane_by_id(self):
        """Test getting a lane by its ID."""
        cr = ConnectingRoad(lane_count_left=1, lane_count_right=2)
        cr.ensure_lanes_initialized()

        lane = cr.get_lane(-1)
        assert lane is not None
        assert lane.id == -1

        center = cr.get_lane(0)
        assert center is not None
        assert center.id == 0

    def test_get_lane_not_found(self):
        """Test getting a non-existent lane returns None."""
        cr = ConnectingRoad(lane_count_left=0, lane_count_right=1)
        cr.ensure_lanes_initialized()
        assert cr.get_lane(5) is None

    def test_lane_initialization_uses_lane_width(self):
        """Test that lane initialization uses lane_width."""
        cr = ConnectingRoad(
            lane_count_left=0,
            lane_count_right=1,
            lane_width=4.0
        )
        cr.ensure_lanes_initialized()
        lane = cr.get_lane(-1)
        assert lane.width == 4.0

    def test_lane_initialization_with_start_end_widths(self):
        """Test lane initialization with variable widths."""
        cr = ConnectingRoad(
            lane_count_left=0,
            lane_count_right=1,
            lane_width=3.5,
            lane_width_start=3.0,
            lane_width_end=4.0
        )
        cr.ensure_lanes_initialized()
        lane = cr.get_lane(-1)
        assert lane.width == 3.0  # Uses lane_width_start
        assert lane.width_end == 4.0


class TestConnectingRoadLanePolygons:
    """Test lane polygon generation."""

    def test_get_lane_polygons_empty_path(self):
        """Test get_lane_polygons with empty path returns empty dict."""
        cr = ConnectingRoad(path=[], lane_count_right=1)
        polygons = cr.get_lane_polygons(scale=0.1)
        assert polygons == {}

    def test_get_lane_polygons_single_point(self):
        """Test get_lane_polygons with single point returns empty dict."""
        cr = ConnectingRoad(path=[(0, 0)], lane_count_right=1)
        polygons = cr.get_lane_polygons(scale=0.1)
        assert polygons == {}

    def test_get_lane_polygons_basic(self):
        """Test get_lane_polygons creates polygons for each lane."""
        path = [(0, 0), (100, 0), (200, 0)]  # Straight path
        cr = ConnectingRoad(
            path=path,
            lane_count_left=1,
            lane_count_right=2,
            lane_width=3.5
        )
        polygons = cr.get_lane_polygons(scale=0.1)  # 0.1 m/pixel

        # Should have 3 lanes
        assert len(polygons) == 3
        assert -1 in polygons
        assert -2 in polygons
        assert 1 in polygons

    def test_get_lane_polygons_with_variable_width(self):
        """Test get_lane_polygons with variable width lanes."""
        path = [(0, 0), (100, 0), (200, 0)]
        cr = ConnectingRoad(
            path=path,
            lane_count_left=0,
            lane_count_right=1,
            lane_width=3.5,
            lane_width_start=3.0,
            lane_width_end=4.0
        )
        polygons = cr.get_lane_polygons(scale=0.1)
        assert -1 in polygons
        # Polygon should have enough points
        assert len(polygons[-1]) >= 3


class TestConnectingRoadParamPoly3D:
    """Test ParamPoly3D geometry fields."""

    def test_default_geometry_type(self):
        """Test default geometry type is parampoly3."""
        cr = ConnectingRoad()
        assert cr.geometry_type == "parampoly3"

    def test_param_poly_coefficients_default(self):
        """Test default ParamPoly3D coefficients are zero."""
        cr = ConnectingRoad()
        assert cr.aU == 0.0
        assert cr.bU == 0.0
        assert cr.cU == 0.0
        assert cr.dU == 0.0
        assert cr.aV == 0.0
        assert cr.bV == 0.0
        assert cr.cV == 0.0
        assert cr.dV == 0.0

    def test_param_poly_serialization(self):
        """Test ParamPoly3D coefficients are serialized."""
        cr = ConnectingRoad(
            path=[(0, 0), (100, 100)],
            geometry_type="parampoly3",
            aU=1.0, bU=2.0, cU=3.0, dU=4.0,
            aV=5.0, bV=6.0, cV=7.0, dV=8.0,
            p_range=1.5,
            p_range_normalized=False
        )
        data = cr.to_dict()

        assert data['geometry_type'] == 'parampoly3'
        assert data['aU'] == 1.0
        assert data['bU'] == 2.0
        assert data['cU'] == 3.0
        assert data['dU'] == 4.0
        assert data['aV'] == 5.0
        assert data['bV'] == 6.0
        assert data['cV'] == 7.0
        assert data['dV'] == 8.0
        assert data['p_range'] == 1.5
        assert data['p_range_normalized'] is False

    def test_param_poly_deserialization(self):
        """Test ParamPoly3D coefficients are deserialized."""
        data = {
            'id': 'test',
            'path': [[0, 0], [100, 100]],
            'geometry_type': 'parampoly3',
            'aU': 10.0, 'bU': 20.0, 'cU': 30.0, 'dU': 40.0,
            'aV': 50.0, 'bV': 60.0, 'cV': 70.0, 'dV': 80.0,
            'p_range': 2.0,
            'p_range_normalized': False,
            'tangent_scale': 0.5
        }
        cr = ConnectingRoad.from_dict(data)

        assert cr.geometry_type == 'parampoly3'
        assert cr.aU == 10.0
        assert cr.bU == 20.0
        assert cr.cU == 30.0
        assert cr.dU == 40.0
        assert cr.aV == 50.0
        assert cr.bV == 60.0
        assert cr.cV == 70.0
        assert cr.dV == 80.0
        assert cr.p_range == 2.0
        assert cr.p_range_normalized is False
        assert cr.tangent_scale == 0.5


class TestConnectingRoadGeoPathSerialization:
    """Test geo_path serialization/deserialization."""

    def test_geo_path_serialization(self):
        """Test geo_path is serialized when set."""
        cr = ConnectingRoad(path=[(100, 200), (300, 400)])
        cr.geo_path = [(12.94, 57.72), (12.95, 57.73)]
        data = cr.to_dict()

        assert 'geo_path' in data
        assert data['geo_path'] == [[12.94, 57.72], [12.95, 57.73]]

    def test_geo_path_not_serialized_when_none(self):
        """Test geo_path is not in dict when None."""
        cr = ConnectingRoad(path=[(100, 200)])
        data = cr.to_dict()
        assert 'geo_path' not in data

    def test_geo_path_deserialization(self):
        """Test geo_path is deserialized correctly."""
        data = {
            'id': 'test',
            'path': [[100, 200], [300, 400]],
            'geo_path': [[12.94, 57.72], [12.95, 57.73]]
        }
        cr = ConnectingRoad.from_dict(data)

        assert cr.geo_path == [(12.94, 57.72), (12.95, 57.73)]

    def test_geo_path_none_when_not_in_dict(self):
        """Test geo_path is None when not in dict."""
        data = {
            'id': 'test',
            'path': [[100, 200]]
        }
        cr = ConnectingRoad.from_dict(data)
        assert cr.geo_path is None


class TestConnectingRoadStoredHeadingsSerialization:
    """Test stored headings serialization."""

    def test_stored_headings_serialization(self):
        """Test stored headings are serialized when set."""
        cr = ConnectingRoad(path=[(0, 0), (100, 100)])
        cr.stored_start_heading = 0.5
        cr.stored_end_heading = -0.3
        data = cr.to_dict()

        assert data['stored_start_heading'] == 0.5
        assert data['stored_end_heading'] == -0.3

    def test_stored_headings_not_serialized_when_none(self):
        """Test stored headings not in dict when None."""
        cr = ConnectingRoad(path=[(0, 0), (100, 100)])
        data = cr.to_dict()

        assert 'stored_start_heading' not in data
        assert 'stored_end_heading' not in data

    def test_stored_headings_deserialization(self):
        """Test stored headings are deserialized."""
        data = {
            'id': 'test',
            'path': [[0, 0], [100, 100]],
            'stored_start_heading': 1.57,
            'stored_end_heading': -1.57
        }
        cr = ConnectingRoad.from_dict(data)

        assert cr.stored_start_heading == 1.57
        assert cr.stored_end_heading == -1.57


class TestConnectingRoadLaneSerialization:
    """Test lane serialization in connecting roads."""

    def test_lanes_serialization(self):
        """Test that lanes are serialized."""
        cr = ConnectingRoad(
            path=[(0, 0), (100, 100)],
            lane_count_right=1
        )
        cr.ensure_lanes_initialized()
        data = cr.to_dict()

        assert 'lanes' in data
        assert len(data['lanes']) == 2  # center + 1 right

    def test_lanes_deserialization(self):
        """Test that lanes are deserialized."""
        data = {
            'id': 'test',
            'path': [[0, 0], [100, 100]],
            'lane_count_right': 1,
            'lanes': [
                {'id': 0, 'lane_type': 'none', 'road_mark_type': 'none', 'width': 0.0},
                {'id': -1, 'lane_type': 'driving', 'road_mark_type': 'solid', 'width': 4.0}
            ]
        }
        cr = ConnectingRoad.from_dict(data)

        assert len(cr.lanes) == 2
        assert cr.lanes[0].id == 0
        assert cr.lanes[1].id == -1
        assert cr.lanes[1].width == 4.0

    def test_old_project_without_lanes(self):
        """Test loading old project without lanes field."""
        data = {
            'id': 'old_conn',
            'path': [[0, 0], [100, 100]],
            'lane_count_right': 2
            # No 'lanes' field - old project format
        }
        cr = ConnectingRoad.from_dict(data)

        # Lanes should be empty initially
        assert cr.lanes == []

        # But should initialize on access
        cr.ensure_lanes_initialized()
        assert len(cr.lanes) == 3  # center + 2 right


class TestConnectingRoadVariableWidth:
    """Test variable width handling."""

    def test_lane_width_start_end_defaults(self):
        """Test lane_width_start/end default to None."""
        cr = ConnectingRoad()
        assert cr.lane_width_start is None
        assert cr.lane_width_end is None

    def test_lane_width_start_end_serialization(self):
        """Test lane_width_start/end are serialized."""
        cr = ConnectingRoad(
            path=[(0, 0), (100, 100)],
            lane_width=3.5,
            lane_width_start=3.0,
            lane_width_end=4.0
        )
        data = cr.to_dict()

        assert data['lane_width'] == 3.5
        assert data['lane_width_start'] == 3.0
        assert data['lane_width_end'] == 4.0

    def test_lane_width_start_end_deserialization(self):
        """Test lane_width_start/end are deserialized."""
        data = {
            'id': 'test',
            'path': [[0, 0], [100, 100]],
            'lane_width': 3.5,
            'lane_width_start': 2.5,
            'lane_width_end': 4.5
        }
        cr = ConnectingRoad.from_dict(data)

        assert cr.lane_width == 3.5
        assert cr.lane_width_start == 2.5
        assert cr.lane_width_end == 4.5


class TestConnectingRoadIdMigration:
    """Test migration of old road_id field to id."""

    def test_old_road_id_migrated_to_id_for_uuid(self):
        """Test that old road_id is migrated to id when id is a non-numeric UUID."""
        data = {
            'id': 'abc-123-uuid',
            'path': [[0, 0], [100, 100]],
            'road_id': 42
        }
        cr = ConnectingRoad.from_dict(data)
        assert cr.id == '42'

    def test_numeric_id_kept_over_road_id(self):
        """Test that numeric id is kept even when road_id is present."""
        data = {
            'id': '7',
            'path': [[0, 0], [100, 100]],
            'road_id': 42
        }
        cr = ConnectingRoad.from_dict(data)
        assert cr.id == '7'

    def test_no_road_id_field_leaves_id_unchanged(self):
        """Test that missing road_id field does not affect id."""
        data = {
            'id': 'some-uuid',
            'path': [[0, 0], [100, 100]]
        }
        cr = ConnectingRoad.from_dict(data)
        assert cr.id == 'some-uuid'

    def test_road_id_not_in_serialized_output(self):
        """Test that road_id is no longer serialized."""
        cr = ConnectingRoad(id='5', path=[(0, 0), (100, 100)])
        data = cr.to_dict()
        assert 'road_id' not in data

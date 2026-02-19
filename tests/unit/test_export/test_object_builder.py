"""Tests for orbit.export.object_builder module."""

import math
from unittest.mock import Mock

import pytest
from lxml import etree

from orbit.export.object_builder import ObjectBuilder
from orbit.models.object import ObjectType, RoadObject


class TestObjectBuilderInit:
    """Tests for ObjectBuilder initialization."""

    def test_default_init(self):
        """Default initialization."""
        builder = ObjectBuilder()
        assert builder.scale_x == 1.0
        assert builder.transformer is None
        assert builder.curve_fitter is None
        assert builder.polyline_map == {}

    def test_custom_scale(self):
        """Custom scale factor."""
        builder = ObjectBuilder(scale_x=0.5)
        assert builder.scale_x == 0.5

    def test_with_transformer(self):
        """Initialize with transformer."""
        mock_transformer = Mock()
        builder = ObjectBuilder(transformer=mock_transformer)
        assert builder.transformer is mock_transformer

    def test_with_polyline_map(self):
        """Initialize with polyline map."""
        polyline_map = {'pl1': Mock()}
        builder = ObjectBuilder(polyline_map=polyline_map)
        assert builder.polyline_map == polyline_map


class TestCalculatePixelLength:
    """Tests for _calculate_pixel_length method."""

    @pytest.fixture
    def builder(self):
        """Create object builder."""
        return ObjectBuilder()

    def test_empty_points(self, builder):
        """Empty points returns 0."""
        assert builder._calculate_pixel_length([]) == 0.0

    def test_single_point(self, builder):
        """Single point returns 0."""
        assert builder._calculate_pixel_length([(0, 0)]) == 0.0

    def test_two_points_horizontal(self, builder):
        """Horizontal segment length."""
        points = [(0, 0), (100, 0)]
        assert builder._calculate_pixel_length(points) == 100.0

    def test_two_points_vertical(self, builder):
        """Vertical segment length."""
        points = [(0, 0), (0, 100)]
        assert builder._calculate_pixel_length(points) == 100.0

    def test_two_points_diagonal(self, builder):
        """Diagonal segment length."""
        points = [(0, 0), (30, 40)]
        assert builder._calculate_pixel_length(points) == 50.0  # 3-4-5 triangle

    def test_multiple_segments(self, builder):
        """Multiple segments summed."""
        points = [(0, 0), (100, 0), (100, 100), (0, 100)]
        # 100 + 100 + 100 = 300
        assert builder._calculate_pixel_length(points) == 300.0


class TestCalculateRoadLengthMeters:
    """Tests for _get_meter_centerline method."""

    def test_no_transformer_returns_zero(self):
        """Returns 0 when no transformer."""
        builder = ObjectBuilder()
        mock_road = Mock()
        pts, length = builder._get_meter_centerline(mock_road)
        assert length == 0.0
        assert pts == []

    def test_no_curve_fitter_returns_zero(self):
        """Returns 0 when no curve fitter."""
        builder = ObjectBuilder(transformer=Mock())
        mock_road = Mock()
        pts, length = builder._get_meter_centerline(mock_road)
        assert length == 0.0
        assert pts == []

    def test_no_centerline_returns_zero(self):
        """Returns 0 when centerline not in polyline map."""
        mock_transformer = Mock()
        mock_curve_fitter = Mock()
        builder = ObjectBuilder(
            transformer=mock_transformer,
            curve_fitter=mock_curve_fitter,
            polyline_map={}
        )
        mock_road = Mock()
        mock_road.centerline_id = "cl1"

        pts, length = builder._get_meter_centerline(mock_road)
        assert length == 0.0
        assert pts == []

    def test_calculates_length_from_pixel_coords(self):
        """Calculates road length from pixel coordinates."""
        mock_transformer = Mock()
        mock_transformer.pixels_to_meters_batch.return_value = [(0, 0), (10, 0)]

        mock_geom_elem = Mock()
        mock_geom_elem.length = 10.0
        mock_curve_fitter = Mock()
        mock_curve_fitter.fit_polyline.return_value = [mock_geom_elem]

        mock_polyline = Mock()
        mock_polyline.geo_points = None
        mock_polyline.points = [(0, 0), (100, 0)]

        builder = ObjectBuilder(
            transformer=mock_transformer,
            curve_fitter=mock_curve_fitter,
            polyline_map={'cl1': mock_polyline}
        )
        mock_road = Mock()
        mock_road.centerline_id = "cl1"

        pts, length = builder._get_meter_centerline(mock_road)
        assert length == 10.0

    def test_uses_geo_points_when_available(self):
        """Uses geo_points when available (more precise)."""
        mock_transformer = Mock()
        mock_transformer.latlon_to_meters.return_value = (0, 0)

        mock_geom_elem = Mock()
        mock_geom_elem.length = 15.0
        mock_curve_fitter = Mock()
        mock_curve_fitter.fit_polyline.return_value = [mock_geom_elem]

        mock_polyline = Mock()
        mock_polyline.geo_points = [(18.0, 59.0), (18.001, 59.0)]
        mock_polyline.points = [(0, 0), (100, 0)]

        builder = ObjectBuilder(
            transformer=mock_transformer,
            curve_fitter=mock_curve_fitter,
            polyline_map={'cl1': mock_polyline}
        )
        mock_road = Mock()
        mock_road.centerline_id = "cl1"

        pts, length = builder._get_meter_centerline(mock_road)
        assert length == 15.0
        mock_transformer.latlon_to_meters.assert_called()


class TestCreateObjects:
    """Tests for create_objects method."""

    @pytest.fixture
    def builder(self):
        """Create object builder with mocks."""
        mock_transformer = Mock()
        mock_transformer.pixels_to_meters_batch.return_value = [(0, 0), (100, 0)]

        mock_geom_elem = Mock()
        mock_geom_elem.length = 100.0
        mock_curve_fitter = Mock()
        mock_curve_fitter.fit_polyline.return_value = [mock_geom_elem]

        mock_polyline = Mock()
        mock_polyline.geo_points = None
        mock_polyline.points = [(0, 100), (1000, 100)]

        return ObjectBuilder(
            scale_x=0.1,
            transformer=mock_transformer,
            curve_fitter=mock_curve_fitter,
            polyline_map={'cl1': mock_polyline}
        )

    @pytest.fixture
    def mock_road(self):
        """Create mock road."""
        road = Mock()
        road.id = "road1"
        road.centerline_id = "cl1"
        return road

    @pytest.fixture
    def centerline_points(self):
        """Centerline points."""
        return [(0, 100), (1000, 100)]

    def test_no_objects_for_road(self, builder, mock_road, centerline_points):
        """Returns None when no objects assigned to road."""
        objects = []
        result = builder.create_objects(mock_road, objects, centerline_points)
        assert result is None

    def test_objects_not_assigned_to_road(self, builder, mock_road, centerline_points):
        """Returns None when objects assigned to different road."""
        obj = RoadObject(position=(500, 100), object_type=ObjectType.LAMPPOST)
        obj.road_id = "other_road"
        objects = [obj]

        result = builder.create_objects(mock_road, objects, centerline_points)
        assert result is None

    def test_creates_objects_element(self, builder, mock_road, centerline_points):
        """Creates objects element."""
        obj = RoadObject(position=(500, 100), object_type=ObjectType.LAMPPOST)
        obj.road_id = "road1"
        objects = [obj]

        result = builder.create_objects(mock_road, objects, centerline_points)

        assert result is not None
        assert result.tag == 'objects'

    def test_multiple_objects(self, builder, mock_road, centerline_points):
        """Creates multiple object elements."""
        obj1 = RoadObject(position=(200, 100), object_type=ObjectType.LAMPPOST)
        obj1.road_id = "road1"
        obj2 = RoadObject(position=(800, 100), object_type=ObjectType.BUILDING)
        obj2.road_id = "road1"
        objects = [obj1, obj2]

        result = builder.create_objects(mock_road, objects, centerline_points)

        assert len(result) == 2


class TestCreateObject:
    """Tests for _create_object method."""

    @pytest.fixture
    def builder(self):
        """Create object builder."""
        return ObjectBuilder(scale_x=0.1)

    @pytest.fixture
    def centerline_points(self):
        """Centerline 1000 pixels long."""
        return [(0, 100), (1000, 100)]

    def test_object_basic_attributes(self, builder, centerline_points):
        """Object has correct basic attributes."""
        obj = RoadObject(position=(500, 100), object_type=ObjectType.LAMPPOST)
        obj.z_offset = 0.0
        obj.name = "Light pole 1"

        result = builder._create_object(obj, centerline_points, 1000.0, 100.0)

        assert result is not None
        assert result.tag == 'object'
        assert result.get('id') == obj.id
        assert result.get('zOffset') == '0.00'
        assert result.get('name') == 'Light pole 1'

    def test_object_s_coordinate(self, builder, centerline_points):
        """S coordinate calculated correctly."""
        obj = RoadObject(position=(500, 100), object_type=ObjectType.LAMPPOST)

        # 500px / 1000px = 0.5 ratio, 0.5 * 100m = 50m
        result = builder._create_object(obj, centerline_points, 1000.0, 100.0)

        s = float(result.get('s'))
        assert s == pytest.approx(50.0, abs=1.0)

    def test_object_t_coordinate(self, builder, centerline_points):
        """T coordinate calculated for offset objects."""
        obj = RoadObject(position=(500, 90), object_type=ObjectType.LAMPPOST)

        result = builder._create_object(obj, centerline_points, 1000.0, 100.0)

        t = float(result.get('t'))
        # 10 pixels * 0.1 m/px = 1 meter
        assert abs(t) == pytest.approx(1.0, abs=0.2)

    def test_object_with_pitch(self, builder, centerline_points):
        """Pitch angle is exported."""
        obj = RoadObject(position=(500, 100), object_type=ObjectType.LAMPPOST)
        obj.pitch = 0.1

        result = builder._create_object(obj, centerline_points, 1000.0, 100.0)

        assert result.get('pitch') == '0.100000'

    def test_object_with_roll(self, builder, centerline_points):
        """Roll angle is exported."""
        obj = RoadObject(position=(500, 100), object_type=ObjectType.LAMPPOST)
        obj.roll = 0.05

        result = builder._create_object(obj, centerline_points, 1000.0, 100.0)

        assert result.get('roll') == '0.050000'

    def test_object_no_pitch_when_zero(self, builder, centerline_points):
        """Pitch not exported when zero."""
        obj = RoadObject(position=(500, 100), object_type=ObjectType.LAMPPOST)
        obj.pitch = 0.0

        result = builder._create_object(obj, centerline_points, 1000.0, 100.0)

        assert result.get('pitch') is None


class TestSetTypeAttributes:
    """Tests for _set_type_attributes method."""

    @pytest.fixture
    def builder(self):
        """Create object builder."""
        return ObjectBuilder(scale_x=0.1)

    def test_lamppost_attributes(self, builder):
        """Lamppost type attributes."""
        elem = etree.Element('object')
        obj = RoadObject(position=(0, 0), object_type=ObjectType.LAMPPOST)
        obj.dimensions = {'height': 6.0, 'radius': 0.2}
        obj.orientation = 45.0

        builder._set_type_attributes(elem, obj)

        assert elem.get('type') == 'pole'
        assert elem.get('subtype') == 'lamppost'
        assert elem.get('height') == '6.00'
        assert elem.get('radius') == '0.20'
        # Orientation in radians
        hdg = float(elem.get('hdg'))
        assert hdg == pytest.approx(math.radians(45.0), abs=0.01)

    def test_guardrail_attributes(self, builder):
        """Guardrail type attributes."""
        elem = etree.Element('object')
        obj = RoadObject(position=(0, 0), object_type=ObjectType.GUARDRAIL)
        obj.dimensions = {'height': 0.81, 'width': 0.3}

        builder._set_type_attributes(elem, obj)

        assert elem.get('type') == 'barrier'
        assert elem.get('subtype') == 'guardrail'
        assert elem.get('height') == '0.81'
        assert elem.get('width') == '0.30'

    def test_guardrail_with_validity_length(self, builder):
        """Guardrail with validity length."""
        elem = etree.Element('object')
        obj = RoadObject(position=(0, 0), object_type=ObjectType.GUARDRAIL)
        obj.validity_length = 100.0  # 100 pixels

        builder._set_type_attributes(elem, obj)

        # 100 pixels * 0.1 scale = 10 meters
        length = float(elem.get('length'))
        assert length == pytest.approx(10.0, abs=0.1)

    def test_building_attributes(self, builder):
        """Building type attributes."""
        elem = etree.Element('object')
        obj = RoadObject(position=(0, 0), object_type=ObjectType.BUILDING)
        obj.dimensions = {'height': 10.0, 'width': 20.0, 'length': 30.0}
        obj.orientation = 90.0

        builder._set_type_attributes(elem, obj)

        assert elem.get('type') == 'building'
        assert elem.get('subtype') == ''
        assert elem.get('height') == '10.00'
        assert elem.get('width') == '20.00'
        assert elem.get('length') == '30.00'

    def test_tree_broadleaf_attributes(self, builder):
        """Broadleaf tree attributes."""
        elem = etree.Element('object')
        obj = RoadObject(position=(0, 0), object_type=ObjectType.TREE_BROADLEAF)
        obj.dimensions = {'height': 8.0, 'radius': 3.0}

        builder._set_type_attributes(elem, obj)

        assert elem.get('type') == 'vegetation'
        assert elem.get('subtype') == 'tree'
        assert elem.get('height') == '8.00'
        assert elem.get('radius') == '3.00'

    def test_tree_conifer_attributes(self, builder):
        """Conifer tree attributes."""
        elem = etree.Element('object')
        obj = RoadObject(position=(0, 0), object_type=ObjectType.TREE_CONIFER)
        obj.dimensions = {'height': 12.0, 'radius': 2.0}

        builder._set_type_attributes(elem, obj)

        assert elem.get('type') == 'vegetation'
        assert elem.get('subtype') == 'tree'

    def test_bush_attributes(self, builder):
        """Bush attributes."""
        elem = etree.Element('object')
        obj = RoadObject(position=(0, 0), object_type=ObjectType.BUSH)
        obj.dimensions = {'height': 2.0, 'radius': 1.0}

        builder._set_type_attributes(elem, obj)

        assert elem.get('type') == 'vegetation'
        assert elem.get('subtype') == 'bush'


class TestCreateObjectOutline:
    """Tests for _create_object_outline method."""

    @pytest.fixture
    def builder(self):
        """Create object builder."""
        return ObjectBuilder(scale_x=0.1)

    def test_lamppost_circular_outline(self, builder):
        """Lamppost gets circular outline."""
        obj = RoadObject(position=(0, 0), object_type=ObjectType.LAMPPOST)
        obj.dimensions = {'radius': 0.15, 'height': 5.0}

        result = builder._create_object_outline(obj)

        assert result is not None
        assert result.tag == 'outline'
        corners = result.findall('cornerLocal')
        assert len(corners) == 12  # Default num_points for lamppost

    def test_guardrail_polyline_outline_no_points(self, builder):
        """Guardrail with no points returns None."""
        obj = RoadObject(position=(0, 0), object_type=ObjectType.GUARDRAIL)
        obj.points = []

        result = builder._create_object_outline(obj)

        assert result is None

    def test_guardrail_polyline_outline_insufficient_points(self, builder):
        """Guardrail with single point returns None."""
        obj = RoadObject(position=(0, 0), object_type=ObjectType.GUARDRAIL)
        obj.points = [(0, 0)]

        result = builder._create_object_outline(obj)

        assert result is None

    def test_guardrail_polyline_outline(self, builder):
        """Guardrail gets polyline outline."""
        obj = RoadObject(position=(0, 0), object_type=ObjectType.GUARDRAIL)
        obj.points = [(0, 0), (100, 0), (200, 50)]
        obj.dimensions = {'height': 0.81}

        result = builder._create_object_outline(obj)

        assert result is not None
        corners = result.findall('cornerLocal')
        assert len(corners) == 3

    def test_building_polygon_outline(self, builder):
        """Building gets polygon outline from its points."""
        obj = RoadObject(position=(0, 0), object_type=ObjectType.BUILDING)
        obj.dimensions = {'width': 20.0, 'length': 30.0, 'height': 10.0}
        obj.points = [(0, 0), (10, 0), (10, 5), (5, 5), (5, 10), (0, 10)]

        result = builder._create_object_outline(obj)

        assert result is not None
        corners = result.findall('cornerLocal')
        assert len(corners) == 6

    def test_building_without_points_no_outline(self, builder):
        """Building without polygon points gets no outline."""
        obj = RoadObject(position=(0, 0), object_type=ObjectType.BUILDING)
        obj.dimensions = {'width': 20.0, 'length': 30.0, 'height': 10.0}

        result = builder._create_object_outline(obj)

        assert result is None

    def test_tree_broadleaf_circular_outline(self, builder):
        """Broadleaf tree gets circular outline."""
        obj = RoadObject(position=(0, 0), object_type=ObjectType.TREE_BROADLEAF)
        obj.dimensions = {'radius': 3.0, 'height': 8.0}

        result = builder._create_object_outline(obj)

        corners = result.findall('cornerLocal')
        assert len(corners) == 8  # Default for tree

    def test_tree_conifer_triangular_outline(self, builder):
        """Conifer tree gets triangular outline."""
        obj = RoadObject(position=(0, 0), object_type=ObjectType.TREE_CONIFER)
        obj.dimensions = {'radius': 2.0, 'height': 10.0}

        result = builder._create_object_outline(obj)

        corners = result.findall('cornerLocal')
        assert len(corners) == 3

    def test_bush_circular_outline(self, builder):
        """Bush gets circular outline."""
        obj = RoadObject(position=(0, 0), object_type=ObjectType.BUSH)
        obj.dimensions = {'radius': 1.0, 'height': 2.0}

        result = builder._create_object_outline(obj)

        corners = result.findall('cornerLocal')
        assert len(corners) == 8


class TestCreateCircularOutline:
    """Tests for _create_circular_outline method."""

    @pytest.fixture
    def builder(self):
        """Create object builder."""
        return ObjectBuilder()

    def test_corner_attributes(self, builder):
        """Corners have required attributes."""
        obj = RoadObject(position=(0, 0), object_type=ObjectType.LAMPPOST)
        obj.dimensions = {'radius': 0.15, 'height': 5.0}
        outline = etree.Element('outline')

        builder._create_circular_outline(outline, obj, 8)

        corner = outline.find('cornerLocal')
        assert corner.get('u') is not None
        assert corner.get('v') is not None
        assert corner.get('z') == '0.0'
        assert corner.get('height') == '5.00'

    def test_circular_approximation(self, builder):
        """Corners form circular approximation."""
        obj = RoadObject(position=(0, 0), object_type=ObjectType.LAMPPOST)
        obj.dimensions = {'radius': 1.0, 'height': 5.0}
        outline = etree.Element('outline')

        builder._create_circular_outline(outline, obj, 4)

        corners = outline.findall('cornerLocal')
        # First corner at angle 0 should be at (radius, 0)
        u0 = float(corners[0].get('u'))
        v0 = float(corners[0].get('v'))
        assert u0 == pytest.approx(1.0, abs=0.01)
        assert v0 == pytest.approx(0.0, abs=0.01)


class TestCreatePolylineOutline:
    """Tests for _create_polyline_outline method."""

    @pytest.fixture
    def builder(self):
        """Create object builder with scale."""
        return ObjectBuilder(scale_x=0.1)

    def test_coordinates_relative_to_first_point(self, builder):
        """Coordinates are relative to first point."""
        obj = RoadObject(position=(0, 0), object_type=ObjectType.GUARDRAIL)
        obj.points = [(100, 100), (200, 100)]
        obj.dimensions = {'height': 0.81}
        outline = etree.Element('outline')

        builder._create_polyline_outline(outline, obj)

        corners = outline.findall('cornerLocal')
        # First point should be at origin
        u0 = float(corners[0].get('u'))
        v0 = float(corners[0].get('v'))
        assert u0 == 0.0
        assert v0 == 0.0

        # Second point at (100, 0) pixels = (10, 0) meters
        u1 = float(corners[1].get('u'))
        v1 = float(corners[1].get('v'))
        assert u1 == pytest.approx(10.0, abs=0.1)
        assert v1 == pytest.approx(0.0, abs=0.1)


class TestCreateRectangularOutline:
    """Tests for _create_rectangular_outline method."""

    @pytest.fixture
    def builder(self):
        """Create object builder."""
        return ObjectBuilder()

    def test_four_corners_centered(self, builder):
        """Four corners centered at origin."""
        obj = RoadObject(position=(0, 0), object_type=ObjectType.BUILDING)
        obj.dimensions = {'width': 20.0, 'length': 30.0, 'height': 10.0}
        outline = etree.Element('outline')

        builder._create_rectangular_outline(outline, obj)

        corners = outline.findall('cornerLocal')
        assert len(corners) == 4

        # Check first corner
        u0 = float(corners[0].get('u'))
        v0 = float(corners[0].get('v'))
        assert u0 == pytest.approx(-10.0, abs=0.01)  # -width/2
        assert v0 == pytest.approx(-15.0, abs=0.01)  # -length/2


class TestCreateTriangularOutline:
    """Tests for _create_triangular_outline method."""

    @pytest.fixture
    def builder(self):
        """Create object builder."""
        return ObjectBuilder()

    def test_three_corners(self, builder):
        """Triangular outline has three corners."""
        obj = RoadObject(position=(0, 0), object_type=ObjectType.TREE_CONIFER)
        obj.dimensions = {'radius': 2.0, 'height': 10.0}
        outline = etree.Element('outline')

        builder._create_triangular_outline(outline, obj)

        corners = outline.findall('cornerLocal')
        assert len(corners) == 3

    def test_triangle_shape(self, builder):
        """Triangle has correct shape."""
        obj = RoadObject(position=(0, 0), object_type=ObjectType.TREE_CONIFER)
        obj.dimensions = {'radius': 2.0, 'height': 10.0}
        outline = etree.Element('outline')

        builder._create_triangular_outline(outline, obj)

        corners = outline.findall('cornerLocal')
        # First point at top (0, radius*1.5)
        u0 = float(corners[0].get('u'))
        v0 = float(corners[0].get('v'))
        assert u0 == 0.0
        assert v0 == pytest.approx(3.0, abs=0.01)  # radius * 1.5

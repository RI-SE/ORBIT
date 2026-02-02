"""Tests for orbit.export.parking_builder module."""

from unittest.mock import Mock

import pytest

from orbit.export.parking_builder import ParkingBuilder
from orbit.models.parking import ParkingAccess, ParkingSpace


class TestParkingBuilderInit:
    """Tests for ParkingBuilder initialization."""

    def test_default_init(self):
        """Default initialization."""
        builder = ParkingBuilder()
        assert builder.scale_x == 1.0
        assert builder.transformer is None
        assert builder.curve_fitter is None
        assert builder.polyline_map == {}

    def test_custom_scale(self):
        """Custom scale factor."""
        builder = ParkingBuilder(scale_x=0.5)
        assert builder.scale_x == 0.5

    def test_with_transformer(self):
        """Initialize with transformer."""
        mock_transformer = Mock()
        builder = ParkingBuilder(transformer=mock_transformer)
        assert builder.transformer is mock_transformer

    def test_with_polyline_map(self):
        """Initialize with polyline map."""
        polyline_map = {'pl1': Mock()}
        builder = ParkingBuilder(polyline_map=polyline_map)
        assert builder.polyline_map == polyline_map


class TestCalculatePixelLength:
    """Tests for _calculate_pixel_length method."""

    @pytest.fixture
    def builder(self):
        """Create parking builder."""
        return ParkingBuilder()

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
    """Tests for _calculate_road_length_meters method."""

    def test_no_transformer_returns_zero(self):
        """Returns 0 when no transformer."""
        builder = ParkingBuilder()
        mock_road = Mock()
        assert builder._calculate_road_length_meters(mock_road) == 0.0

    def test_no_curve_fitter_returns_zero(self):
        """Returns 0 when no curve fitter."""
        builder = ParkingBuilder(transformer=Mock())
        mock_road = Mock()
        assert builder._calculate_road_length_meters(mock_road) == 0.0

    def test_no_centerline_returns_zero(self):
        """Returns 0 when centerline not in polyline map."""
        mock_transformer = Mock()
        mock_curve_fitter = Mock()
        builder = ParkingBuilder(
            transformer=mock_transformer,
            curve_fitter=mock_curve_fitter,
            polyline_map={}
        )
        mock_road = Mock()
        mock_road.centerline_id = "cl1"

        assert builder._calculate_road_length_meters(mock_road) == 0.0

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

        builder = ParkingBuilder(
            transformer=mock_transformer,
            curve_fitter=mock_curve_fitter,
            polyline_map={'cl1': mock_polyline}
        )
        mock_road = Mock()
        mock_road.centerline_id = "cl1"

        length = builder._calculate_road_length_meters(mock_road)
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

        builder = ParkingBuilder(
            transformer=mock_transformer,
            curve_fitter=mock_curve_fitter,
            polyline_map={'cl1': mock_polyline}
        )
        mock_road = Mock()
        mock_road.centerline_id = "cl1"

        length = builder._calculate_road_length_meters(mock_road)
        assert length == 15.0
        mock_transformer.latlon_to_meters.assert_called()


class TestCreateParkingObjects:
    """Tests for create_parking_objects method."""

    @pytest.fixture
    def builder(self):
        """Create parking builder with mocks."""
        mock_transformer = Mock()
        mock_transformer.pixels_to_meters_batch.return_value = [(0, 0), (100, 0)]

        mock_geom_elem = Mock()
        mock_geom_elem.length = 100.0
        mock_curve_fitter = Mock()
        mock_curve_fitter.fit_polyline.return_value = [mock_geom_elem]

        mock_polyline = Mock()
        mock_polyline.geo_points = None
        mock_polyline.points = [(0, 100), (1000, 100)]

        return ParkingBuilder(
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

    def test_no_parking_for_road(self, builder, mock_road, centerline_points):
        """Returns empty list when no parking assigned to road."""
        parking_spaces = []
        result = builder.create_parking_objects(mock_road, parking_spaces, centerline_points)
        assert result == []

    def test_parking_not_assigned_to_road(self, builder, mock_road, centerline_points):
        """Returns empty list when parking assigned to different road."""
        parking = ParkingSpace(position=(500, 100))
        parking.road_id = "other_road"
        parking_spaces = [parking]

        result = builder.create_parking_objects(mock_road, parking_spaces, centerline_points)
        assert result == []

    def test_creates_parking_object(self, builder, mock_road, centerline_points):
        """Creates parking object element."""
        parking = ParkingSpace(position=(500, 100))
        parking.road_id = "road1"
        parking_spaces = [parking]

        result = builder.create_parking_objects(mock_road, parking_spaces, centerline_points)

        assert len(result) == 1
        assert result[0].tag == 'object'
        assert result[0].get('type') == 'parking'

    def test_multiple_parking_spaces(self, builder, mock_road, centerline_points):
        """Creates multiple parking objects."""
        parking1 = ParkingSpace(position=(200, 100))
        parking1.road_id = "road1"
        parking2 = ParkingSpace(position=(800, 100))
        parking2.road_id = "road1"
        parking_spaces = [parking1, parking2]

        result = builder.create_parking_objects(mock_road, parking_spaces, centerline_points)

        assert len(result) == 2


class TestCreateParkingObject:
    """Tests for _create_parking_object method."""

    @pytest.fixture
    def builder(self):
        """Create parking builder."""
        return ParkingBuilder(scale_x=0.1)

    @pytest.fixture
    def centerline_points(self):
        """Centerline 1000 pixels long."""
        return [(0, 100), (1000, 100)]

    def test_parking_object_attributes(self, builder, centerline_points):
        """Parking object has correct attributes."""
        parking = ParkingSpace(position=(500, 100))
        parking.width = 2.5
        parking.length = 5.0
        parking.z_offset = 0.0
        parking.orientation = 0.0

        result = builder._create_parking_object(parking, centerline_points, 1000.0, 100.0)

        assert result is not None
        assert result.tag == 'object'
        assert result.get('type') == 'parking'
        assert result.get('width') == '2.50'
        assert result.get('length') == '5.00'
        assert result.get('zOffset') == '0.00'

    def test_parking_s_coordinate(self, builder, centerline_points):
        """S coordinate is calculated correctly."""
        parking = ParkingSpace(position=(500, 100))  # Middle of centerline

        # 500px / 1000px = 0.5 ratio, 0.5 * 100m = 50m
        result = builder._create_parking_object(parking, centerline_points, 1000.0, 100.0)

        s = float(result.get('s'))
        assert s == pytest.approx(50.0, abs=1.0)

    def test_parking_t_coordinate(self, builder, centerline_points):
        """T coordinate is calculated for offset parking."""
        parking = ParkingSpace(position=(500, 90))  # 10 pixels above centerline

        result = builder._create_parking_object(parking, centerline_points, 1000.0, 100.0)

        t = float(result.get('t'))
        # 10 pixels * 0.1 m/px = 1 meter
        assert abs(t) == pytest.approx(1.0, abs=0.2)

    def test_parking_space_child_element(self, builder, centerline_points):
        """Parking object has parkingSpace child."""
        parking = ParkingSpace(position=(500, 100))
        parking.access = ParkingAccess.STANDARD

        result = builder._create_parking_object(parking, centerline_points, 1000.0, 100.0)

        ps_elem = result.find('parkingSpace')
        assert ps_elem is not None
        assert ps_elem.get('access') == 'standard'

    def test_parking_with_restrictions(self, builder, centerline_points):
        """Parking restrictions are exported."""
        parking = ParkingSpace(position=(500, 100))
        parking.restrictions = "Max 2 hours"

        result = builder._create_parking_object(parking, centerline_points, 1000.0, 100.0)

        ps_elem = result.find('parkingSpace')
        assert ps_elem.get('restrictions') == "Max 2 hours"

    def test_parking_orientation_radians(self, builder, centerline_points):
        """Parking orientation is converted to radians."""
        parking = ParkingSpace(position=(500, 100))
        parking.orientation = 90.0  # 90 degrees

        result = builder._create_parking_object(parking, centerline_points, 1000.0, 100.0)

        import math
        hdg = float(result.get('hdg'))
        assert hdg == pytest.approx(math.pi / 2, abs=0.01)


class TestCreateParkingOutline:
    """Tests for _create_parking_outline method."""

    @pytest.fixture
    def builder(self):
        """Create parking builder."""
        return ParkingBuilder(scale_x=0.1)

    def test_no_points_returns_none(self, builder):
        """Returns None when no points."""
        parking = ParkingSpace(position=(0, 0))
        parking.points = []

        result = builder._create_parking_outline(parking)
        assert result is None

    def test_insufficient_points_returns_none(self, builder):
        """Returns None when less than 3 points."""
        parking = ParkingSpace(position=(0, 0))
        parking.points = [(0, 0), (10, 0)]  # Only 2 points

        result = builder._create_parking_outline(parking)
        assert result is None

    def test_creates_outline_element(self, builder):
        """Creates outline with cornerLocal elements."""
        parking = ParkingSpace(position=(100, 100))
        parking.points = [(90, 90), (110, 90), (110, 110), (90, 110)]  # Rectangle

        result = builder._create_parking_outline(parking)

        assert result is not None
        assert result.tag == 'outline'
        corners = result.findall('cornerLocal')
        assert len(corners) == 4

    def test_corner_coordinates_in_local_system(self, builder):
        """Corner coordinates are relative to centroid."""
        parking = ParkingSpace(position=(100, 100))
        # Centroid at (100, 100), corners at ±10 pixels = ±1 meter
        parking.points = [(90, 90), (110, 90), (110, 110), (90, 110)]

        result = builder._create_parking_outline(parking)
        corners = result.findall('cornerLocal')

        # First corner: (90, 90) - centroid (100, 100) = (-10, -10) pixels = (-1, -1) meters
        u = float(corners[0].get('u'))
        v = float(corners[0].get('v'))
        assert u == pytest.approx(-1.0, abs=0.01)
        assert v == pytest.approx(-1.0, abs=0.01)

    def test_corner_has_z_and_height(self, builder):
        """Each corner has z and height attributes."""
        parking = ParkingSpace(position=(100, 100))
        parking.points = [(90, 90), (110, 90), (110, 110)]

        result = builder._create_parking_outline(parking)
        corner = result.find('cornerLocal')

        assert corner.get('z') == '0.0'
        assert corner.get('height') == '0.0'

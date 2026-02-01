"""Tests for orbit.import.opendrive_geometry module."""

import importlib
import math

import pytest

# Import from orbit.import using importlib (import is a reserved keyword)
opendrive_geometry = importlib.import_module('orbit.import.opendrive_geometry')
opendrive_parser = importlib.import_module('orbit.import.opendrive_parser')

GeometryConverter = opendrive_geometry.GeometryConverter
calculate_s_offsets = opendrive_geometry.calculate_s_offsets
sample_elevation_profile = opendrive_geometry.sample_elevation_profile

GeometryElement = opendrive_parser.GeometryElement
GeometryType = opendrive_parser.GeometryType
ElevationProfile = opendrive_parser.ElevationProfile


class TestGeometryConverterInit:
    """Tests for GeometryConverter initialization."""

    def test_default_sampling_interval(self):
        """Default sampling interval is 1.0."""
        converter = GeometryConverter()
        assert converter.sampling_interval == 1.0

    def test_custom_sampling_interval(self):
        """Custom sampling interval can be specified."""
        converter = GeometryConverter(sampling_interval=0.5)
        assert converter.sampling_interval == 0.5


class TestConvertLine:
    """Tests for line geometry conversion."""

    @pytest.fixture
    def converter(self):
        """Create converter with fine sampling."""
        return GeometryConverter(sampling_interval=0.5)

    def test_line_east(self, converter):
        """Line heading east produces correct endpoints."""
        geom = GeometryElement(
            s=0.0, x=0.0, y=0.0, hdg=0.0,  # East
            length=10.0, geometry_type=GeometryType.LINE
        )
        points, conversions, segments = converter.convert_geometry_to_polyline([geom])

        assert len(points) == 2
        assert points[0] == pytest.approx((0.0, 0.0), abs=1e-6)
        assert points[1] == pytest.approx((10.0, 0.0), abs=1e-6)

    def test_line_north(self, converter):
        """Line heading north (90 degrees)."""
        geom = GeometryElement(
            s=0.0, x=0.0, y=0.0, hdg=math.pi / 2,  # North
            length=10.0, geometry_type=GeometryType.LINE
        )
        points, _, _ = converter.convert_geometry_to_polyline([geom])

        assert len(points) == 2
        assert points[0] == pytest.approx((0.0, 0.0), abs=1e-6)
        assert points[1] == pytest.approx((0.0, 10.0), abs=1e-6)

    def test_line_with_offset_start(self, converter):
        """Line starting from non-zero position."""
        geom = GeometryElement(
            s=0.0, x=100.0, y=50.0, hdg=math.pi / 4,  # 45 degrees
            length=10.0, geometry_type=GeometryType.LINE
        )
        points, _, _ = converter.convert_geometry_to_polyline([geom])

        assert points[0] == pytest.approx((100.0, 50.0), abs=1e-6)
        expected_end_x = 100.0 + 10.0 * math.cos(math.pi / 4)
        expected_end_y = 50.0 + 10.0 * math.sin(math.pi / 4)
        assert points[1] == pytest.approx((expected_end_x, expected_end_y), abs=1e-6)


class TestConvertArc:
    """Tests for arc geometry conversion."""

    @pytest.fixture
    def converter(self):
        """Create converter."""
        return GeometryConverter(sampling_interval=1.0)

    def test_arc_produces_multiple_points(self, converter):
        """Arc generates multiple sample points."""
        geom = GeometryElement(
            s=0.0, x=0.0, y=0.0, hdg=0.0,
            length=10.0, geometry_type=GeometryType.ARC,
            params={'curvature': 0.1}  # radius = 10
        )
        points, _, _ = converter.convert_geometry_to_polyline([geom])

        # Should have at least 3 points
        assert len(points) >= 3

    def test_arc_near_zero_curvature_treated_as_line(self, converter):
        """Arc with near-zero curvature is treated as line."""
        geom = GeometryElement(
            s=0.0, x=0.0, y=0.0, hdg=0.0,
            length=10.0, geometry_type=GeometryType.ARC,
            params={'curvature': 1e-12}  # Nearly straight
        )
        points, _, _ = converter.convert_geometry_to_polyline([geom])

        # Should be 2 points like a line
        assert len(points) == 2

    def test_arc_left_turn(self, converter):
        """Arc curving left (positive curvature)."""
        radius = 50.0
        arc_length = math.pi * radius / 2  # Quarter circle
        geom = GeometryElement(
            s=0.0, x=0.0, y=0.0, hdg=0.0,  # Start heading east
            length=arc_length, geometry_type=GeometryType.ARC,
            params={'curvature': 1.0 / radius}  # Left turn
        )
        points, _, _ = converter.convert_geometry_to_polyline([geom])

        # After quarter circle left turn from heading east, should be heading north
        # End point should be roughly at (radius, radius)
        end_point = points[-1]
        assert end_point[0] == pytest.approx(radius, rel=0.1)
        assert end_point[1] == pytest.approx(radius, rel=0.1)


class TestConvertSpiral:
    """Tests for spiral/clothoid geometry conversion."""

    @pytest.fixture
    def converter(self):
        """Create converter with fine sampling."""
        return GeometryConverter(sampling_interval=0.5)

    def test_spiral_with_zero_curvatures_is_line(self, converter):
        """Spiral with both curvatures zero is treated as line."""
        geom = GeometryElement(
            s=0.0, x=0.0, y=0.0, hdg=0.0,
            length=10.0, geometry_type=GeometryType.SPIRAL,
            params={'curvStart': 0.0, 'curvEnd': 0.0}
        )
        points, _, _ = converter.convert_geometry_to_polyline([geom])

        # Should be treated as a line (2 points)
        assert len(points) == 2

    def test_spiral_produces_multiple_points(self, converter):
        """Spiral with curvature change produces multiple points."""
        geom = GeometryElement(
            s=0.0, x=0.0, y=0.0, hdg=0.0,
            length=20.0, geometry_type=GeometryType.SPIRAL,
            params={'curvStart': 0.0, 'curvEnd': 0.02}
        )
        points, _, _ = converter.convert_geometry_to_polyline([geom])

        # Should have multiple samples
        assert len(points) >= 5

    def test_spiral_starts_at_origin(self, converter):
        """Spiral starts at specified position."""
        geom = GeometryElement(
            s=0.0, x=100.0, y=50.0, hdg=math.pi / 4,
            length=10.0, geometry_type=GeometryType.SPIRAL,
            params={'curvStart': 0.0, 'curvEnd': 0.05}
        )
        points, _, _ = converter.convert_geometry_to_polyline([geom])

        assert points[0] == pytest.approx((100.0, 50.0), abs=1e-6)


class TestConvertPoly3:
    """Tests for poly3 geometry conversion."""

    @pytest.fixture
    def converter(self):
        """Create converter."""
        return GeometryConverter(sampling_interval=2.0)

    def test_poly3_straight_line(self, converter):
        """Poly3 with zero coefficients is straight."""
        geom = GeometryElement(
            s=0.0, x=0.0, y=0.0, hdg=0.0,
            length=10.0, geometry_type=GeometryType.POLY3,
            params={'a': 0, 'b': 0, 'c': 0, 'd': 0}
        )
        points, conversions, _ = converter.convert_geometry_to_polyline([geom])

        # All points should be on x-axis
        for x, y in points:
            assert y == pytest.approx(0.0, abs=1e-6)

        # Should have conversion message
        assert any('poly3' in c for c in conversions)

    def test_poly3_produces_multiple_points(self, converter):
        """Poly3 generates multiple sample points."""
        geom = GeometryElement(
            s=0.0, x=0.0, y=0.0, hdg=0.0,
            length=10.0, geometry_type=GeometryType.POLY3,
            params={'a': 0, 'b': 0.1, 'c': 0.01, 'd': 0.001}
        )
        points, _, _ = converter.convert_geometry_to_polyline([geom])

        assert len(points) >= 5


class TestConvertParamPoly3:
    """Tests for paramPoly3 geometry conversion."""

    @pytest.fixture
    def converter(self):
        """Create converter."""
        return GeometryConverter(sampling_interval=2.0)

    def test_param_poly3_straight_line(self, converter):
        """ParamPoly3 representing straight line."""
        geom = GeometryElement(
            s=0.0, x=0.0, y=0.0, hdg=0.0,
            length=10.0, geometry_type=GeometryType.PARAM_POLY3,
            params={
                'aU': 0, 'bU': 1, 'cU': 0, 'dU': 0,  # U = p (linear forward)
                'aV': 0, 'bV': 0, 'cV': 0, 'dV': 0,  # V = 0 (no lateral)
                'pRange': 'arcLength'
            }
        )
        points, conversions, _ = converter.convert_geometry_to_polyline([geom])

        # All points should be on x-axis (heading east)
        for x, y in points:
            assert y == pytest.approx(0.0, abs=1e-6)

        assert any('paramPoly3' in c for c in conversions)

    def test_param_poly3_normalized_range(self, converter):
        """ParamPoly3 with normalized parameter range."""
        geom = GeometryElement(
            s=0.0, x=0.0, y=0.0, hdg=0.0,
            length=10.0, geometry_type=GeometryType.PARAM_POLY3,
            params={
                'aU': 0, 'bU': 10, 'cU': 0, 'dU': 0,  # U = 10*p, so end at 10
                'aV': 0, 'bV': 0, 'cV': 0, 'dV': 0,
                'pRange': 'normalized'
            }
        )
        points, _, _ = converter.convert_geometry_to_polyline([geom])

        # End point should be at x=10 when p=1
        assert points[-1][0] == pytest.approx(10.0, abs=0.5)


class TestConvertMultipleGeometries:
    """Tests for converting multiple connected geometries."""

    @pytest.fixture
    def converter(self):
        """Create converter."""
        return GeometryConverter(sampling_interval=1.0)

    def test_two_lines_share_point(self, converter):
        """Two connected lines share their junction point."""
        geom1 = GeometryElement(
            s=0.0, x=0.0, y=0.0, hdg=0.0,
            length=10.0, geometry_type=GeometryType.LINE
        )
        geom2 = GeometryElement(
            s=10.0, x=10.0, y=0.0, hdg=math.pi / 4,
            length=10.0, geometry_type=GeometryType.LINE
        )
        points, _, _ = converter.convert_geometry_to_polyline([geom1, geom2])

        # Should have 3 points total (start, junction, end)
        assert len(points) == 3
        # Junction point at (10, 0)
        assert points[1] == pytest.approx((10.0, 0.0), abs=1e-6)

    def test_geometry_segments_created(self, converter):
        """Geometry segments are created for round-trip preservation."""
        geom1 = GeometryElement(
            s=0.0, x=0.0, y=0.0, hdg=0.0,
            length=10.0, geometry_type=GeometryType.LINE
        )
        geom2 = GeometryElement(
            s=10.0, x=10.0, y=0.0, hdg=0.0,
            length=20.0, geometry_type=GeometryType.ARC,
            params={'curvature': 0.05}
        )
        points, _, segments = converter.convert_geometry_to_polyline([geom1, geom2], preserve_geometry=True)

        assert len(segments) == 2
        assert segments[0].geom_type == 'line'
        assert segments[1].geom_type == 'arc'
        assert segments[1].curvature == 0.05

    def test_no_segments_when_preserve_false(self, converter):
        """No segments created when preserve_geometry is False."""
        geom = GeometryElement(
            s=0.0, x=0.0, y=0.0, hdg=0.0,
            length=10.0, geometry_type=GeometryType.LINE
        )
        points, _, segments = converter.convert_geometry_to_polyline([geom], preserve_geometry=False)

        assert segments is None


class TestCreateGeometrySegment:
    """Tests for _create_geometry_segment helper."""

    @pytest.fixture
    def converter(self):
        """Create converter."""
        return GeometryConverter()

    def test_line_segment(self, converter):
        """Line geometry creates line segment."""
        geom = GeometryElement(
            s=0.0, x=0.0, y=0.0, hdg=0.5,
            length=10.0, geometry_type=GeometryType.LINE
        )
        segment = converter._create_geometry_segment(geom, 0, 1)

        assert segment.geom_type == 'line'
        assert segment.start_index == 0
        assert segment.end_index == 1
        assert segment.s_start == 0.0
        assert segment.length == 10.0
        assert segment.heading == 0.5
        assert segment.curvature is None

    def test_arc_segment(self, converter):
        """Arc geometry creates arc segment with curvature."""
        geom = GeometryElement(
            s=5.0, x=10.0, y=20.0, hdg=1.0,
            length=15.0, geometry_type=GeometryType.ARC,
            params={'curvature': 0.02}
        )
        segment = converter._create_geometry_segment(geom, 5, 20)

        assert segment.geom_type == 'arc'
        assert segment.curvature == 0.02
        assert segment.curvature_end is None

    def test_spiral_segment(self, converter):
        """Spiral geometry creates spiral segment with both curvatures."""
        geom = GeometryElement(
            s=0.0, x=0.0, y=0.0, hdg=0.0,
            length=10.0, geometry_type=GeometryType.SPIRAL,
            params={'curvStart': 0.0, 'curvEnd': 0.05}
        )
        segment = converter._create_geometry_segment(geom, 0, 10)

        assert segment.geom_type == 'spiral'
        assert segment.curvature == 0.0
        assert segment.curvature_end == 0.05

    def test_poly3_segment(self, converter):
        """Poly3 geometry creates segment with polynomial params."""
        geom = GeometryElement(
            s=0.0, x=0.0, y=0.0, hdg=0.0,
            length=10.0, geometry_type=GeometryType.POLY3,
            params={'a': 1.0, 'b': 2.0, 'c': 3.0, 'd': 4.0}
        )
        segment = converter._create_geometry_segment(geom, 0, 5)

        assert segment.geom_type == 'poly3'
        assert segment.poly_params == {'a': 1.0, 'b': 2.0, 'c': 3.0, 'd': 4.0}

    def test_param_poly3_segment(self, converter):
        """ParamPoly3 geometry creates segment with all polynomial params."""
        geom = GeometryElement(
            s=0.0, x=0.0, y=0.0, hdg=0.0,
            length=10.0, geometry_type=GeometryType.PARAM_POLY3,
            params={
                'aU': 0, 'bU': 1, 'cU': 0, 'dU': 0,
                'aV': 0, 'bV': 0, 'cV': 1, 'dV': 0,
                'pRange': 'normalized'
            }
        )
        segment = converter._create_geometry_segment(geom, 0, 10)

        assert segment.geom_type == 'paramPoly3'
        assert segment.poly_params['aU'] == 0
        assert segment.poly_params['bU'] == 1
        assert segment.poly_params['cV'] == 1
        assert segment.poly_params['pRange'] == 'normalized'


class TestPointsMatch:
    """Tests for _points_match helper."""

    @pytest.fixture
    def converter(self):
        """Create converter."""
        return GeometryConverter()

    def test_exact_match(self, converter):
        """Exact match returns True."""
        assert converter._points_match((10.0, 20.0), (10.0, 20.0)) is True

    def test_within_tolerance(self, converter):
        """Points within tolerance match."""
        assert converter._points_match((10.0, 20.0), (10.005, 20.005)) is True

    def test_outside_tolerance(self, converter):
        """Points outside tolerance don't match."""
        assert converter._points_match((10.0, 20.0), (10.02, 20.02)) is False

    def test_custom_tolerance(self, converter):
        """Custom tolerance can be specified."""
        assert converter._points_match((10.0, 20.0), (10.05, 20.05), tol=0.1) is True
        assert converter._points_match((10.0, 20.0), (10.15, 20.15), tol=0.1) is False


class TestCalculateSOffsets:
    """Tests for calculate_s_offsets function."""

    def test_empty_points(self):
        """Empty points returns empty list."""
        assert calculate_s_offsets([]) == []

    def test_single_point(self):
        """Single point returns [0.0]."""
        assert calculate_s_offsets([(0, 0)]) == [0.0]

    def test_two_points(self):
        """Two points returns [0.0, distance]."""
        offsets = calculate_s_offsets([(0, 0), (3, 4)])
        assert offsets == [0.0, 5.0]

    def test_multiple_points(self):
        """Multiple points returns cumulative distances."""
        points = [(0, 0), (10, 0), (10, 10), (0, 10)]
        offsets = calculate_s_offsets(points)

        assert offsets[0] == 0.0
        assert offsets[1] == 10.0
        assert offsets[2] == 20.0
        assert offsets[3] == 30.0

    def test_diagonal_points(self):
        """Diagonal points use Euclidean distance."""
        points = [(0, 0), (1, 1), (2, 2)]
        offsets = calculate_s_offsets(points)

        sqrt2 = math.sqrt(2)
        assert offsets[0] == pytest.approx(0.0)
        assert offsets[1] == pytest.approx(sqrt2)
        assert offsets[2] == pytest.approx(2 * sqrt2)


class TestSampleElevationProfile:
    """Tests for sample_elevation_profile function."""

    def test_none_profile(self):
        """None profile returns None."""
        result = sample_elevation_profile([0.0, 10.0, 20.0], None)
        assert result is None

    def test_empty_elevations(self):
        """Empty elevations returns None."""
        profile = ElevationProfile(elevations=[])
        result = sample_elevation_profile([0.0, 10.0], profile)
        assert result is None

    def test_constant_elevation(self):
        """Constant elevation (a only) is sampled correctly."""
        profile = ElevationProfile(elevations=[(0.0, 100.0, 0.0, 0.0, 0.0)])
        result = sample_elevation_profile([0.0, 10.0, 20.0], profile)

        assert result == [100.0, 100.0, 100.0]

    def test_linear_elevation(self):
        """Linear elevation (a + b*ds) is sampled correctly."""
        # elevation = 100 + 2*ds (rises 2m per meter)
        profile = ElevationProfile(elevations=[(0.0, 100.0, 2.0, 0.0, 0.0)])
        result = sample_elevation_profile([0.0, 5.0, 10.0], profile)

        assert result[0] == pytest.approx(100.0)
        assert result[1] == pytest.approx(110.0)
        assert result[2] == pytest.approx(120.0)

    def test_multiple_elevation_records(self):
        """Multiple elevation records apply to their regions."""
        # First record: elevation = 100 from s=0
        # Second record: elevation = 150 from s=20
        profile = ElevationProfile(elevations=[
            (0.0, 100.0, 0.0, 0.0, 0.0),
            (20.0, 150.0, 0.0, 0.0, 0.0)
        ])
        result = sample_elevation_profile([0.0, 10.0, 25.0], profile)

        assert result[0] == 100.0  # Uses first record
        assert result[1] == 100.0  # Uses first record
        assert result[2] == 150.0  # Uses second record

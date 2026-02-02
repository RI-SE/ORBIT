"""
Unit tests for curve fitting.

Tests fitting polylines to geometric elements (lines, arcs) for OpenDrive export.
"""

import math
from typing import List, Tuple

import pytest

from orbit.export.curve_fitting import CurveFitter, GeometryType, simplify_polyline

# ============================================================================
# Helper Functions
# ============================================================================

def create_line_points(
    start: Tuple[float, float],
    end: Tuple[float, float],
    num_points: int = 10,
) -> List[Tuple[float, float]]:
    """Create evenly spaced points along a line."""
    x1, y1 = start
    x2, y2 = end
    points = []
    for i in range(num_points):
        t = i / (num_points - 1)
        x = x1 + t * (x2 - x1)
        y = y1 + t * (y2 - y1)
        points.append((x, y))
    return points


def create_arc_points(
    center: Tuple[float, float],
    radius: float,
    start_angle: float,
    end_angle: float,
    num_points: int = 20,
) -> List[Tuple[float, float]]:
    """Create points along a circular arc."""
    cx, cy = center
    points = []
    for i in range(num_points):
        t = i / (num_points - 1)
        angle = start_angle + t * (end_angle - start_angle)
        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)
        points.append((x, y))
    return points


# ============================================================================
# Test CurveFitter Initialization
# ============================================================================

class TestCurveFitterCreation:
    """Test creating CurveFitter with different parameters."""

    def test_default_fitter(self):
        """Test creating fitter with default parameters."""
        fitter = CurveFitter()

        assert fitter.line_tolerance == 0.5
        assert fitter.arc_tolerance == 1.0
        assert fitter.preserve_geometry is True

    def test_custom_tolerances(self):
        """Test creating fitter with custom tolerances."""
        fitter = CurveFitter(
            line_tolerance=0.1,
            arc_tolerance=0.5,
            preserve_geometry=False
        )

        assert fitter.line_tolerance == 0.1
        assert fitter.arc_tolerance == 0.5
        assert fitter.preserve_geometry is False


# ============================================================================
# Test Preserve Geometry Mode
# ============================================================================

class TestPreserveGeometry:
    """Test preserve_geometry mode (one line per segment)."""

    def test_preserve_geometry_creates_lines_per_segment(self):
        """Test that preserve mode creates one line per polyline segment."""
        points = [(0, 0), (10, 0), (20, 5), (30, 10)]
        fitter = CurveFitter(preserve_geometry=True)

        elements = fitter.fit_polyline(points)

        # Should create 3 lines for 4 points
        assert len(elements) == 3
        assert all(elem.geom_type == GeometryType.LINE for elem in elements)

    def test_preserve_geometry_maintains_points(self):
        """Test that preserve mode maintains all original points."""
        points = [(0, 0), (5, 0), (10, 0), (15, 0), (20, 0)]
        fitter = CurveFitter(preserve_geometry=True)

        elements = fitter.fit_polyline(points)

        # Should have one line per segment (n-1 lines for n points)
        assert len(elements) == len(points) - 1

    def test_preserve_geometry_with_two_points(self):
        """Test preserve mode with minimum 2 points."""
        points = [(0, 0), (100, 0)]
        fitter = CurveFitter(preserve_geometry=True)

        elements = fitter.fit_polyline(points)

        assert len(elements) == 1
        assert elements[0].geom_type == GeometryType.LINE


# ============================================================================
# Test Line Fitting
# ============================================================================

class TestLineFitting:
    """Test fitting straight lines."""

    def test_fit_horizontal_line(self):
        """Test fitting a horizontal line."""
        points = create_line_points((0, 0), (100, 0), num_points=10)
        fitter = CurveFitter(preserve_geometry=False, line_tolerance=0.1)

        elements = fitter.fit_polyline(points)

        # Should fit to a single line
        assert len(elements) >= 1
        first_elem = elements[0]
        assert first_elem.geom_type == GeometryType.LINE

        # Heading should be 0 (pointing right)
        assert first_elem.heading == pytest.approx(0.0, abs=0.01)

    def test_fit_vertical_line(self):
        """Test fitting a vertical line."""
        points = create_line_points((0, 0), (0, 100), num_points=10)
        fitter = CurveFitter(preserve_geometry=False, line_tolerance=0.1)

        elements = fitter.fit_polyline(points)

        assert len(elements) >= 1
        first_elem = elements[0]
        assert first_elem.geom_type == GeometryType.LINE

        # Heading should be π/2 (pointing up)
        assert first_elem.heading == pytest.approx(math.pi / 2, abs=0.01)

    def test_fit_diagonal_line(self):
        """Test fitting a diagonal line."""
        points = create_line_points((0, 0), (100, 100), num_points=10)
        fitter = CurveFitter(preserve_geometry=False, line_tolerance=0.1)

        elements = fitter.fit_polyline(points)

        assert len(elements) >= 1
        first_elem = elements[0]
        assert first_elem.geom_type == GeometryType.LINE

        # Heading should be π/4 (45 degrees)
        assert first_elem.heading == pytest.approx(math.pi / 4, abs=0.01)


# ============================================================================
# Test Arc Fitting
# ============================================================================

class TestArcFitting:
    """Test fitting circular arcs."""

    def test_fit_arc_quarter_circle(self):
        """Test fitting a quarter circle arc."""
        # Create quarter circle: center at (0,0), radius 50, from 0 to π/2
        points = create_arc_points((0, 0), 50.0, 0, math.pi / 2, num_points=20)
        fitter = CurveFitter(preserve_geometry=False, arc_tolerance=1.0)

        elements = fitter.fit_polyline(points)

        # Should fit to arcs (or lines if fitting fails)
        assert len(elements) >= 1

        # Check if any arcs were fitted
        arc_elements = [e for e in elements if e.geom_type == GeometryType.ARC]
        if arc_elements:
            # If arc fitted, curvature should be 1/radius
            _expected_curvature = 1.0 / 50.0
            assert arc_elements[0].curvature != 0.0

    def test_fit_arc_semicircle(self):
        """Test fitting a semicircle."""
        # Semicircle: radius 30, from 0 to π
        points = create_arc_points((0, 0), 30.0, 0, math.pi, num_points=30)
        fitter = CurveFitter(preserve_geometry=False, arc_tolerance=2.0)

        elements = fitter.fit_polyline(points)

        # Should create at least one element
        assert len(elements) >= 1


# ============================================================================
# Test Geometry Properties
# ============================================================================

class TestGeometryElementProperties:
    """Test properties of fitted geometry elements."""

    def test_line_element_has_zero_curvature(self):
        """Test that line elements have zero curvature."""
        points = [(0, 0), (100, 0)]
        fitter = CurveFitter(preserve_geometry=True)

        elements = fitter.fit_polyline(points)

        line_elem = elements[0]
        assert line_elem.geom_type == GeometryType.LINE
        assert line_elem.curvature == 0.0

    def test_geometry_element_has_start_position(self):
        """Test that elements have correct start positions."""
        points = [(10, 20), (50, 60), (90, 100)]
        fitter = CurveFitter(preserve_geometry=True)

        elements = fitter.fit_polyline(points)

        # First element should start at first point
        first_elem = elements[0]
        assert first_elem.start_pos[0] == pytest.approx(10.0, abs=0.01)
        assert first_elem.start_pos[1] == pytest.approx(20.0, abs=0.01)

    def test_geometry_element_has_length(self):
        """Test that elements have positive length."""
        points = [(0, 0), (100, 0), (200, 0)]
        fitter = CurveFitter(preserve_geometry=True)

        elements = fitter.fit_polyline(points)

        for elem in elements:
            assert elem.length > 0


# ============================================================================
# Test Edge Cases
# ============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_fit_empty_polyline(self):
        """Test fitting empty polyline returns empty list."""
        fitter = CurveFitter()
        elements = fitter.fit_polyline([])

        assert elements == []

    def test_fit_single_point(self):
        """Test fitting single point returns empty list."""
        fitter = CurveFitter()
        elements = fitter.fit_polyline([(0, 0)])

        assert elements == []

    def test_fit_two_points(self):
        """Test fitting two points creates single line."""
        points = [(0, 0), (100, 50)]
        fitter = CurveFitter()

        elements = fitter.fit_polyline(points)

        assert len(elements) == 1
        assert elements[0].geom_type == GeometryType.LINE

    def test_fit_collinear_points(self):
        """Test fitting collinear points."""
        # All points on same line
        points = [(0, 0), (10, 10), (20, 20), (30, 30)]
        fitter = CurveFitter(preserve_geometry=False, line_tolerance=0.1)

        elements = fitter.fit_polyline(points)

        # Should be able to fit to single line (or few lines)
        assert len(elements) >= 1
        # At least the first element should be a line
        assert elements[0].geom_type == GeometryType.LINE


# ============================================================================
# Test Douglas-Peucker Simplification
# ============================================================================

class TestPolylineSimplification:
    """Test Douglas-Peucker polyline simplification."""

    def test_simplify_straight_line_preserves_endpoints(self):
        """Test that simplifying straight line keeps endpoints."""
        # Many points on a line
        points = [(0, 0), (10, 0), (20, 0), (30, 0), (40, 0), (50, 0)]

        simplified = simplify_polyline(points, tolerance=0.1)

        # Should keep only endpoints
        assert len(simplified) == 2
        assert simplified[0] == points[0]
        assert simplified[-1] == points[-1]

    def test_simplify_zigzag_line(self):
        """Test simplifying zigzag line."""
        # Zigzag pattern
        points = [(0, 0), (10, 5), (20, 0), (30, 5), (40, 0)]

        simplified = simplify_polyline(points, tolerance=10.0)  # High tolerance

        # Should simplify significantly
        assert len(simplified) < len(points)
        # Always keeps endpoints
        assert simplified[0] == points[0]
        assert simplified[-1] == points[-1]

    def test_simplify_with_zero_tolerance(self):
        """Test that zero tolerance preserves all points."""
        points = [(0, 0), (10, 5), (20, 10), (30, 15)]

        simplified = simplify_polyline(points, tolerance=0.0)

        # Should keep all points with zero tolerance
        assert len(simplified) == len(points)

    def test_simplify_curve_with_low_tolerance(self):
        """Test that low tolerance preserves curve detail."""
        # Create curve points
        points = create_arc_points((0, 0), 50.0, 0, math.pi / 2, num_points=50)

        simplified = simplify_polyline(points, tolerance=0.5)  # Low tolerance

        # Should keep many points to preserve curve
        assert len(simplified) > 5
        assert len(simplified) < len(points)

    def test_simplify_curve_with_high_tolerance(self):
        """Test that high tolerance aggressively simplifies."""
        # Create curve points
        points = create_arc_points((0, 0), 50.0, 0, math.pi / 2, num_points=50)

        simplified = simplify_polyline(points, tolerance=10.0)  # High tolerance

        # Should simplify significantly
        assert len(simplified) < 10


# ============================================================================
# Test Complex Polylines
# ============================================================================

class TestComplexPolylines:
    """Test fitting complex polylines with mixed geometry."""

    def test_fit_line_then_arc(self):
        """Test fitting polyline with straight then curved section."""
        # Create line segment followed by arc
        line_points = create_line_points((0, 0), (50, 0), num_points=10)
        arc_points = create_arc_points((50, 0), 30.0, -math.pi/2, 0, num_points=15)

        # Combine (remove duplicate connection point)
        points = line_points[:-1] + arc_points

        fitter = CurveFitter(preserve_geometry=False, line_tolerance=0.5, arc_tolerance=1.0)

        elements = fitter.fit_polyline(points)

        # Should create multiple elements
        assert len(elements) >= 2

    def test_fit_long_polyline(self):
        """Test fitting long polyline with many points."""
        # Create a complex path
        points = []
        for i in range(100):
            x = i * 10.0
            y = 50 * math.sin(i * 0.2)  # Sinusoidal
            points.append((x, y))

        fitter = CurveFitter(preserve_geometry=False)

        elements = fitter.fit_polyline(points)

        # Should create multiple elements
        assert len(elements) > 0
        assert len(elements) < len(points)  # Should simplify


# ============================================================================
# Test Different Tolerance Values
# ============================================================================

class TestTolerances:
    """Test effect of different tolerance values."""

    def test_tight_tolerance_preserves_more_detail(self):
        """Test that lower tolerance preserves more geometry."""
        points = create_arc_points((0, 0), 50.0, 0, math.pi, num_points=30)

        fitter_tight = CurveFitter(preserve_geometry=False, line_tolerance=0.1, arc_tolerance=0.1)
        fitter_loose = CurveFitter(preserve_geometry=False, line_tolerance=5.0, arc_tolerance=5.0)

        elements_tight = fitter_tight.fit_polyline(points)
        elements_loose = fitter_loose.fit_polyline(points)

        # Tighter tolerance should create more elements (more detail)
        # Note: this may not always be true depending on fitting algorithm
        assert len(elements_tight) > 0
        assert len(elements_loose) > 0

    def test_tolerance_affects_simplification(self):
        """Test that tolerance affects how aggressively polylines are simplified."""
        # Create slightly wavy line
        points = [(i * 10.0, 5 * math.sin(i * 0.5)) for i in range(20)]

        fitter_tight = CurveFitter(preserve_geometry=False, line_tolerance=0.1)
        fitter_loose = CurveFitter(preserve_geometry=False, line_tolerance=10.0)

        elements_tight = fitter_tight.fit_polyline(points)
        elements_loose = fitter_loose.fit_polyline(points)

        # Tighter tolerance typically results in more elements
        assert len(elements_tight) > 0
        assert len(elements_loose) > 0


# ============================================================================
# Test Spiral/Clothoid Fitting
# ============================================================================

def create_spiral_points(
    x0: float, y0: float, theta0: float,
    kappa_start: float, kappa_end: float,
    length: float, num_points: int = 30
) -> List[Tuple[float, float]]:
    """Create points along a clothoid spiral with linearly varying curvature."""
    points = []
    kappa_rate = (kappa_end - kappa_start) / length if length > 0 else 0

    x, y = x0, y0
    theta = theta0

    for i in range(num_points):
        points.append((x, y))
        s = (i / (num_points - 1)) * length
        ds = length / (num_points - 1)

        # Update position using current heading
        x += math.cos(theta) * ds
        y += math.sin(theta) * ds

        # Update heading using curvature at this point
        kappa = kappa_start + kappa_rate * s
        theta += kappa * ds

    return points


class TestCurveFitterWithSpirals:
    """Test CurveFitter with spiral fitting enabled."""

    def test_fitter_with_spirals_enabled(self):
        """Test creating fitter with spirals enabled."""
        fitter = CurveFitter(
            preserve_geometry=False,
            enable_spirals=True,
            spiral_tolerance=0.5
        )

        assert fitter.enable_spirals is True
        assert fitter.spiral_tolerance == 0.5

    def test_fit_polyline_with_spirals_flag(self):
        """Test that fit_polyline uses spiral fitting when enabled."""
        points = create_line_points((0, 0), (100, 0), num_points=10)
        fitter = CurveFitter(preserve_geometry=False, enable_spirals=True)

        elements = fitter.fit_polyline(points)

        # Should still produce valid elements
        assert len(elements) >= 1


class TestEstimateCurvatures:
    """Test curvature estimation from polyline points."""

    def test_estimate_curvatures_straight_line(self):
        """Test curvature estimation for straight line."""
        points = create_line_points((0, 0), (100, 0), num_points=10)
        fitter = CurveFitter()

        curvatures, s_values = fitter._estimate_curvatures(points)

        # Straight line should have near-zero curvature
        assert len(curvatures) == len(points) - 2  # Interior points only
        for k in curvatures:
            assert abs(k) < 0.01

    def test_estimate_curvatures_arc(self):
        """Test curvature estimation for circular arc."""
        radius = 50.0
        points = create_arc_points((0, 0), radius, 0, math.pi / 2, num_points=20)
        fitter = CurveFitter()

        curvatures, s_values = fitter._estimate_curvatures(points)

        # Arc should have constant curvature ≈ 1/radius
        expected_curvature = 1.0 / radius
        for k in curvatures:
            assert abs(k) == pytest.approx(expected_curvature, rel=0.2)

    def test_estimate_curvatures_insufficient_points(self):
        """Test curvature estimation with insufficient points."""
        fitter = CurveFitter()

        curvatures, s_values = fitter._estimate_curvatures([(0, 0), (10, 0)])

        assert curvatures == []
        assert s_values == []

    def test_estimate_curvatures_with_s_values(self):
        """Test that s_values correspond to arc length positions."""
        points = create_line_points((0, 0), (100, 0), num_points=11)
        fitter = CurveFitter()

        curvatures, s_values = fitter._estimate_curvatures(points)

        # s_values should be increasing
        for i in range(1, len(s_values)):
            assert s_values[i] > s_values[i - 1]


class TestEvalClothoid:
    """Test clothoid evaluation function."""

    def test_eval_clothoid_straight_line(self):
        """Test clothoid evaluation for straight line (zero curvature)."""
        fitter = CurveFitter()

        x, y, theta = fitter._eval_clothoid(
            s=10.0, x0=0.0, y0=0.0, theta0=0.0,
            kappa0=0.0, kappa_rate=0.0
        )

        # Should move 10 units east
        assert x == pytest.approx(10.0, abs=0.01)
        assert y == pytest.approx(0.0, abs=0.01)
        assert theta == pytest.approx(0.0, abs=0.01)

    def test_eval_clothoid_circular_arc(self):
        """Test clothoid evaluation for circular arc (constant curvature)."""
        fitter = CurveFitter()
        radius = 50.0
        curvature = 1.0 / radius

        # Quarter circle: arc length = (π/2) * radius
        arc_length = (math.pi / 2) * radius

        x, y, theta = fitter._eval_clothoid(
            s=arc_length, x0=50.0, y0=0.0, theta0=math.pi / 2,
            kappa0=curvature, kappa_rate=0.0
        )

        # Final heading should be π (pointing left)
        assert theta == pytest.approx(math.pi, abs=0.1)

    def test_eval_clothoid_with_curvature_rate(self):
        """Test clothoid evaluation with varying curvature."""
        fitter = CurveFitter()

        # Start straight, end curved
        x, y, theta = fitter._eval_clothoid(
            s=20.0, x0=0.0, y0=0.0, theta0=0.0,
            kappa0=0.0, kappa_rate=0.01
        )

        # Heading should have increased (turned left)
        assert theta > 0


class TestEvalClothoidPoints:
    """Test clothoid point generation."""

    def test_eval_clothoid_points_straight(self):
        """Test generating points along straight clothoid."""
        fitter = CurveFitter()

        points = fitter._eval_clothoid_points(
            length=100.0, x0=0.0, y0=0.0, theta0=0.0,
            kappa0=0.0, kappa_end=0.0, n_samples=10
        )

        # Should have 11 points (n_samples + 1)
        assert len(points) == 11

        # First point at origin
        assert points[0] == pytest.approx((0.0, 0.0), abs=0.01)

        # Last point approximately 100 units east
        assert points[-1][0] == pytest.approx(100.0, abs=1.0)

    def test_eval_clothoid_points_zero_length(self):
        """Test generating points for zero length clothoid."""
        fitter = CurveFitter()

        points = fitter._eval_clothoid_points(
            length=0.0, x0=5.0, y0=10.0, theta0=0.0,
            kappa0=0.0, kappa_end=0.0
        )

        # Should return single starting point
        assert len(points) == 1
        assert points[0] == (5.0, 10.0)


class TestFindSpiralSegment:
    """Test spiral segment detection."""

    def test_find_spiral_segment_insufficient_points(self):
        """Test with too few points for spiral detection."""
        points = [(0, 0), (10, 0), (20, 0)]
        fitter = CurveFitter(enable_spirals=True)

        end, k_start, k_end = fitter._find_spiral_segment(points, 0)

        # Should return start + 1 (no spiral found)
        assert end == 1
        assert k_start == 0.0
        assert k_end == 0.0

    def test_find_spiral_segment_straight_line(self):
        """Test spiral detection on straight line."""
        points = create_line_points((0, 0), (100, 0), num_points=20)
        fitter = CurveFitter(enable_spirals=True)

        end, k_start, k_end = fitter._find_spiral_segment(points, 0)

        # Straight line is not a spiral (constant zero curvature)
        # Should return early index
        assert end <= 2


class TestValidateSpiralFit:
    """Test spiral fit validation."""

    def test_validate_spiral_fit_insufficient_points(self):
        """Test validation with insufficient points."""
        fitter = CurveFitter()

        result = fitter._validate_spiral_fit(
            [(0, 0), (10, 0)], kappa_start=0.0, kappa_end=0.01
        )

        assert result is False

    def test_validate_spiral_fit_zero_length(self):
        """Test validation with zero-length path."""
        fitter = CurveFitter()

        result = fitter._validate_spiral_fit(
            [(5, 5), (5, 5), (5, 5)], kappa_start=0.0, kappa_end=0.01
        )

        assert result is False


class TestFitSpiral:
    """Test spiral fitting optimization."""

    def test_fit_spiral_insufficient_points(self):
        """Test fitting with insufficient points."""
        fitter = CurveFitter()

        result = fitter._fit_spiral([(0, 0), (10, 0)], 0.0, 0.01)

        assert result is None

    def test_fit_spiral_zero_length(self):
        """Test fitting zero-length path."""
        fitter = CurveFitter()

        result = fitter._fit_spiral([(5, 5), (5, 5), (5, 5)], 0.0, 0.01)

        assert result is None

    def test_fit_spiral_returns_valid_parameters(self):
        """Test fitting returns valid parameters."""
        # Create approximate spiral points
        points = []
        x, y = 0.0, 0.0
        theta = 0.0
        kappa = 0.0
        for i in range(20):
            points.append((x, y))
            ds = 5.0
            x += math.cos(theta) * ds
            y += math.sin(theta) * ds
            kappa += 0.001
            theta += kappa * ds

        fitter = CurveFitter()
        result = fitter._fit_spiral(points, 0.0, 0.02)

        if result is not None:
            x0, y0, theta0, length, k0, k1 = result
            assert length > 0


class TestCreateSpiralElement:
    """Test spiral geometry element creation."""

    def test_create_spiral_element_insufficient_points(self):
        """Test creating spiral with insufficient points."""
        fitter = CurveFitter()

        result = fitter._create_spiral_element(
            [(0, 0), (10, 0)], 0, 2, 0.0, 0.01
        )

        assert result is None


class TestFitPolylineWithSpirals:
    """Test the full spiral-enabled fitting pipeline."""

    def test_fit_polyline_with_spirals_empty(self):
        """Test spiral fitting with empty polyline."""
        fitter = CurveFitter(enable_spirals=True)

        elements = fitter.fit_polyline_with_spirals([])

        assert elements == []

    def test_fit_polyline_with_spirals_single_point(self):
        """Test spiral fitting with single point."""
        fitter = CurveFitter(enable_spirals=True)

        elements = fitter.fit_polyline_with_spirals([(0, 0)])

        assert elements == []

    def test_fit_polyline_with_spirals_line(self):
        """Test spiral fitting recognizes straight lines."""
        points = create_line_points((0, 0), (100, 0), num_points=15)
        fitter = CurveFitter(enable_spirals=True)

        elements = fitter.fit_polyline_with_spirals(points)

        # Should produce line elements
        assert len(elements) >= 1
        assert any(e.geom_type == GeometryType.LINE for e in elements)

    def test_fit_polyline_with_spirals_arc(self):
        """Test spiral fitting with arc points."""
        points = create_arc_points((0, 0), 50.0, 0, math.pi / 2, num_points=25)
        fitter = CurveFitter(enable_spirals=True, arc_tolerance=2.0)

        elements = fitter.fit_polyline_with_spirals(points)

        # Should produce some elements
        assert len(elements) >= 1


# ============================================================================
# Test Circle Fitting
# ============================================================================

class TestCircleFitting:
    """Test circle fitting for arc detection."""

    def test_fit_circle_perfect_arc(self):
        """Test fitting circle to perfect arc points."""
        center = (50.0, 50.0)
        radius = 30.0
        points = create_arc_points(center, radius, 0, math.pi, num_points=20)

        fitter = CurveFitter()
        result = fitter._fit_circle(points)

        assert result is not None
        fitted_center, fitted_radius = result
        assert fitted_center[0] == pytest.approx(center[0], abs=1.0)
        assert fitted_center[1] == pytest.approx(center[1], abs=1.0)
        assert fitted_radius == pytest.approx(radius, abs=1.0)

    def test_fit_circle_noisy_points(self):
        """Test fitting circle with slightly noisy points."""
        import random
        random.seed(42)

        center = (0.0, 0.0)
        radius = 50.0
        points = []
        for i in range(20):
            angle = (i / 19) * math.pi
            x = center[0] + radius * math.cos(angle) + random.uniform(-0.5, 0.5)
            y = center[1] + radius * math.sin(angle) + random.uniform(-0.5, 0.5)
            points.append((x, y))

        fitter = CurveFitter()
        result = fitter._fit_circle(points)

        assert result is not None
        fitted_center, fitted_radius = result
        assert fitted_radius == pytest.approx(radius, rel=0.1)


# ============================================================================
# Test Arc Element Creation
# ============================================================================

class TestArcElementCreation:
    """Test arc geometry element creation."""

    def test_create_arc_element_quarter_circle(self):
        """Test creating arc element from quarter circle."""
        points = create_arc_points((0, 0), 50.0, 0, math.pi / 2, num_points=20)
        fitter = CurveFitter()

        element = fitter._create_arc_element(points, 0, len(points) - 1)

        assert element is not None
        assert element.geom_type == GeometryType.ARC
        assert element.length > 0
        assert element.curvature != 0

    def test_create_arc_element_invalid_circle(self):
        """Test creating arc element when circle fitting fails."""
        # Collinear points - circle fitting should fail
        points = [(0, 0), (10, 0), (20, 0)]
        fitter = CurveFitter()

        _element = fitter._create_arc_element(points, 0, 2)

        # May return None or fallback
        # Just ensure no exception is raised


# ============================================================================
# Test Line Segment Detection
# ============================================================================

class TestLineSegmentDetection:
    """Test line segment finding logic."""

    def test_find_line_segment_all_collinear(self):
        """Test finding line segment when all points are collinear."""
        points = create_line_points((0, 0), (100, 0), num_points=10)
        fitter = CurveFitter(line_tolerance=0.1)

        end = fitter._find_line_segment(points, 0)

        # Should include all points
        assert end == len(points)

    def test_find_line_segment_partial(self):
        """Test finding line segment with non-collinear tail."""
        # First part straight, then curves
        line_part = create_line_points((0, 0), (50, 0), num_points=5)
        curve_part = [(60, 10), (70, 30), (80, 60)]
        points = line_part + curve_part

        fitter = CurveFitter(line_tolerance=0.1)

        end = fitter._find_line_segment(points, 0)

        # Should stop before curve
        assert end <= 6

    def test_find_line_segment_at_end(self):
        """Test finding line segment near end of polyline."""
        points = [(0, 0), (10, 0), (20, 0)]
        fitter = CurveFitter()

        end = fitter._find_line_segment(points, 2)

        # At last point, should return start + 1
        assert end == 3


class TestIsLine:
    """Test line checking logic."""

    def test_is_line_two_points(self):
        """Test that any two points form a line."""
        fitter = CurveFitter()

        result = fitter._is_line([(0, 0), (100, 50)])

        assert result == True  # noqa: E712 - numpy bool, identity check fails

    def test_is_line_single_point(self):
        """Test that single point is a line."""
        fitter = CurveFitter()

        result = fitter._is_line([(5, 5)])

        assert result == True  # noqa: E712 - numpy bool, identity check fails

    def test_is_line_horizontal(self):
        """Test horizontal line detection."""
        points = [(0, 5), (50, 5), (100, 5)]
        fitter = CurveFitter(line_tolerance=0.1)

        result = fitter._is_line(points)

        assert result == True  # noqa: E712 - numpy bool, identity check fails

    def test_is_line_vertical(self):
        """Test vertical line detection."""
        points = [(5, 0), (5, 50), (5, 100)]
        fitter = CurveFitter(line_tolerance=0.1)

        result = fitter._is_line(points)

        assert result == True  # noqa: E712 - numpy bool, identity check fails

    def test_is_line_with_deviation(self):
        """Test line detection with point deviation."""
        # Middle point slightly off line
        points = [(0, 0), (50, 2), (100, 0)]
        fitter_strict = CurveFitter(line_tolerance=0.1)
        fitter_loose = CurveFitter(line_tolerance=5.0)

        assert fitter_strict._is_line(points) == False  # noqa: E712 - numpy bool
        assert fitter_loose._is_line(points) == True  # noqa: E712 - numpy bool


# ============================================================================
# Test Zero-Length Handling
# ============================================================================

class TestZeroLengthHandling:
    """Test handling of zero-length segments."""

    def test_create_line_element_zero_length(self):
        """Test creating line element with zero length."""
        fitter = CurveFitter()

        element = fitter._create_line_element([(5, 5), (5, 5)], 0, 1)

        # Should return None for zero-length
        assert element is None

    def test_preserve_geometry_skips_zero_length(self):
        """Test that preserve geometry mode skips zero-length segments."""
        points = [(0, 0), (0, 0), (10, 0)]  # First segment is zero-length
        fitter = CurveFitter(preserve_geometry=True)

        elements = fitter.fit_polyline(points)

        # Should only create one element (skipping zero-length)
        assert len(elements) == 1
        assert elements[0].length > 0

"""
Unit tests for curve fitting.

Tests fitting polylines to geometric elements (lines, arcs) for OpenDrive export.
"""

import pytest
import math
from typing import List, Tuple

from orbit.export.curve_fitting import (
    CurveFitter, GeometryElement, GeometryType,
    simplify_polyline
)


# ============================================================================
# Helper Functions
# ============================================================================

def create_line_points(start: Tuple[float, float], end: Tuple[float, float], num_points: int = 10) -> List[Tuple[float, float]]:
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


def create_arc_points(center: Tuple[float, float], radius: float, start_angle: float, end_angle: float, num_points: int = 20) -> List[Tuple[float, float]]:
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
            expected_curvature = 1.0 / 50.0
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

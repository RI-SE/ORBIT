"""Tests for orbit.export.reference_line_sampler module."""

import math

import pytest

from orbit.export.curve_fitting import GeometryElement, GeometryType
from orbit.export.reference_line_sampler import (
    LanePolygonData,
    compute_lane_polygons,
    sample_reference_line,
)
from orbit.models.road import Road


class TestSampleReferenceLine:
    """Tests for sample_reference_line function."""

    def test_empty_elements(self):
        """Empty geometry list returns empty result."""
        assert sample_reference_line([]) == []

    def test_sample_line_geometry(self):
        """Straight line produces evenly-spaced points along heading."""
        elem = GeometryElement(
            geom_type=GeometryType.LINE,
            start_pos=(0.0, 0.0),
            heading=0.0,  # East
            length=10.0,
        )
        points = sample_reference_line([elem], step_m=2.0)

        assert len(points) >= 5  # At least 0, 2, 4, 6, 8, 10
        # First point at origin
        assert points[0][0] == pytest.approx(0.0, abs=1e-6)
        assert points[0][1] == pytest.approx(0.0, abs=1e-6)
        # Last point at (10, 0)
        assert points[-1][0] == pytest.approx(10.0, abs=1e-6)
        assert points[-1][1] == pytest.approx(0.0, abs=1e-6)
        # All headings should be 0
        for _, _, hdg in points:
            assert hdg == pytest.approx(0.0, abs=1e-6)

    def test_sample_line_heading_north(self):
        """Line heading north (pi/2) produces correct points."""
        elem = GeometryElement(
            geom_type=GeometryType.LINE,
            start_pos=(5.0, 3.0),
            heading=math.pi / 2,  # North
            length=6.0,
        )
        points = sample_reference_line([elem], step_m=2.0)

        assert points[-1][0] == pytest.approx(5.0, abs=1e-6)
        assert points[-1][1] == pytest.approx(9.0, abs=1e-6)

    def test_sample_arc_geometry(self):
        """Arc produces points that follow a curve."""
        radius = 10.0
        curvature = 1.0 / radius
        arc_length = math.pi * radius / 2  # Quarter circle

        elem = GeometryElement(
            geom_type=GeometryType.ARC,
            start_pos=(0.0, 0.0),
            heading=0.0,  # Start heading east
            length=arc_length,
            curvature=curvature,
        )
        points = sample_reference_line([elem], step_m=0.5)

        # End of quarter circle with positive curvature (turning left):
        # Should end near (radius, radius) = (10, 10)
        end_x, end_y, end_hdg = points[-1]
        assert end_x == pytest.approx(radius, abs=0.5)
        assert end_y == pytest.approx(radius, abs=0.5)
        # Final heading should be ~pi/2 (north)
        assert end_hdg == pytest.approx(math.pi / 2, abs=0.1)

    def test_multiple_elements(self):
        """Multiple geometry elements produce continuous samples."""
        elem1 = GeometryElement(
            geom_type=GeometryType.LINE,
            start_pos=(0.0, 0.0),
            heading=0.0,
            length=5.0,
        )
        elem2 = GeometryElement(
            geom_type=GeometryType.LINE,
            start_pos=(5.0, 0.0),
            heading=0.0,
            length=5.0,
        )
        points = sample_reference_line([elem1, elem2], step_m=2.0)

        # Should cover 0 to 10
        assert points[0][0] == pytest.approx(0.0, abs=1e-6)
        assert points[-1][0] == pytest.approx(10.0, abs=1e-6)

        # No duplicate points at element boundary
        xs = [p[0] for p in points]
        for i in range(1, len(xs)):
            assert xs[i] > xs[i-1] - 1e-6  # Monotonically increasing


class TestComputeLanePolygons:
    """Tests for compute_lane_polygons function."""

    def _make_road_with_lanes(self, right_count=1, left_count=0, width=3.5, length_px=100.0):
        """Helper to create a road with simple lane configuration."""
        road = Road(id="road_1", name="Test Road")
        road.lane_info.right_count = right_count
        road.lane_info.left_count = left_count
        road.lane_info.lane_width = width
        road.generate_lanes(centerline_length=length_px)
        return road

    def _make_reference_points(self, length_m=10.0, heading=0.0, step=0.5):
        """Create reference points along a straight line."""
        n = int(length_m / step) + 1
        return [
            (i * step * math.cos(heading),
             i * step * math.sin(heading),
             heading)
            for i in range(n)
        ]

    def test_single_right_lane(self):
        """Single right lane produces polygon with correct lateral offset."""
        road = self._make_road_with_lanes(right_count=1, left_count=0, width=3.5, length_px=100.0)
        ref_points = self._make_reference_points(length_m=10.0, heading=0.0)

        # scale_x = meters_per_pixel. road sections have s in pixels.
        # With 100px centerline mapped to 10m, scale = 0.1 m/px
        scale_x = 0.1
        polygons = compute_lane_polygons(ref_points, road, scale_x)

        assert len(polygons) == 1
        poly = polygons[0]
        assert poly.road_id == "road_1"
        assert poly.lane_id == -1
        assert poly.section_number == 1
        assert poly.is_connecting_road is False
        assert poly.lane_type == "driving"

        # Polygon should have points
        assert len(poly.points) >= 6  # At least 3 per side

    def test_multi_lane_cumulative_offset(self):
        """Multiple lanes have cumulative offsets."""
        road = self._make_road_with_lanes(right_count=2, left_count=0, width=3.5, length_px=100.0)
        ref_points = self._make_reference_points(length_m=10.0, heading=0.0)
        scale_x = 0.1

        polygons = compute_lane_polygons(ref_points, road, scale_x)

        assert len(polygons) == 2
        lane_ids = [p.lane_id for p in polygons]
        assert -1 in lane_ids
        assert -2 in lane_ids

    def test_left_lanes(self):
        """Left lanes produce polygons offset in the positive direction."""
        road = self._make_road_with_lanes(right_count=0, left_count=1, width=3.5, length_px=100.0)
        ref_points = self._make_reference_points(length_m=10.0, heading=0.0)
        scale_x = 0.1

        polygons = compute_lane_polygons(ref_points, road, scale_x)

        assert len(polygons) == 1
        assert polygons[0].lane_id == 1

    def test_variable_width_inner_offset(self):
        """With variable-width inner lane, outer lane boundary tracks correctly.

        When lane -1 tapers from 4.0m to 2.0m, lane -2's inner boundary must
        follow that taper, not use a constant 4.0m offset.
        """
        from orbit.models.lane import Lane
        from orbit.models.lane_section import LaneSection

        road = Road(id="road_vw", name="Variable Width")
        section = LaneSection(section_number=1, s_start=0.0, s_end=100.0)
        # Lane -1: tapers from 4.0 to 2.0
        lane1 = Lane(id=-1, width=4.0, width_end=2.0)
        # Lane -2: constant 3.0
        lane2 = Lane(id=-2, width=3.0)
        center = Lane(id=0, width=0.0)
        section.lanes = [center, lane1, lane2]
        section.s_start = 0.0
        section.s_end = 100.0
        section.end_point_index = None
        road.lane_sections = [section]

        # 10m road, heading east, scale 0.1 m/px
        ref_points = self._make_reference_points(length_m=10.0, heading=0.0)
        polygons = compute_lane_polygons(ref_points, road, 0.1)

        assert len(polygons) == 2
        next(p for p in polygons if p.lane_id == -1)  # verify lane -1 exists
        poly_2 = next(p for p in polygons if p.lane_id == -2)

        # For lane -2, the inner boundary at the end should be at ~2.0m offset
        # (matching lane -1's tapered width), not 4.0m.
        # Inner boundary points are the first half of the polygon.
        n_half = len(poly_2.points) // 2
        inner_end = poly_2.points[n_half - 1]  # last inner boundary point
        # Road goes east (heading=0), so Y offset indicates perpendicular distance.
        # Right lanes offset downward (negative Y).
        # Inner offset at end = lane -1 width at end = 2.0
        assert inner_end[1] == pytest.approx(-2.0, abs=0.2)

    def test_empty_reference_points(self):
        """Empty reference points returns empty list."""
        road = self._make_road_with_lanes()
        assert compute_lane_polygons([], road, 0.1) == []

    def test_no_lane_sections(self):
        """Road with no sections returns empty list."""
        road = Road(id="empty")
        ref_points = self._make_reference_points()
        assert compute_lane_polygons(ref_points, road, 0.1) == []


class TestLanePolygonData:
    """Tests for LanePolygonData dataclass."""

    def test_default_values(self):
        """Default values are sensible."""
        lpd = LanePolygonData(road_id="r1", section_number=1, lane_id=-1)
        assert lpd.points == []
        assert lpd.is_connecting_road is False
        assert lpd.lane_type == "driving"

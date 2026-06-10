"""Tests for create_transformer_from_bounds and geometry re-projection."""

import math

import pytest

from orbit.models.polyline import Polyline
from orbit.models.project import ControlPoint, Project
from orbit.utils.coordinate_transform import create_transformer_from_bounds


def merc(lat_deg: float) -> float:
    return math.log(math.tan(math.pi / 4 + math.radians(lat_deg) / 2))


def inv_merc(m: float) -> float:
    return math.degrees(2 * math.atan(math.exp(m)) - math.pi / 2)


class TestCreateTransformerFromBounds:
    """Tests for the Web-Mercator transformer created from geographic bounds."""

    def test_corners_roundtrip(self):
        """Image corners should map to the expected geographic coordinates."""
        t = create_transformer_from_bounds(
            1000, 800,
            min_lon=11.0, min_lat=57.0,
            max_lon=12.0, max_lat=58.0,
        )
        assert t is not None

        # Top-left pixel → NW corner
        lon, lat = t.pixel_to_geo(0, 0)
        assert lon == pytest.approx(11.0, abs=1e-9)
        assert lat == pytest.approx(58.0, abs=1e-9)

        # Bottom-right pixel → SE corner
        lon, lat = t.pixel_to_geo(1000, 800)
        assert lon == pytest.approx(12.0, abs=1e-9)
        assert lat == pytest.approx(57.0, abs=1e-9)

    def test_center_point_is_mercator_midpoint(self):
        """Tile imagery is linear in Mercator y: the image center maps to the
        Mercator midpoint, which lies slightly north of the latitude midpoint
        in the northern hemisphere (H1)."""
        t = create_transformer_from_bounds(
            2000, 1000,
            min_lon=10.0, min_lat=55.0,
            max_lon=12.0, max_lat=57.0,
        )
        lon, lat = t.pixel_to_geo(1000, 500)
        assert lon == pytest.approx(11.0, abs=1e-9)
        expected_lat = inv_merc((merc(55.0) + merc(57.0)) / 2)
        assert lat == pytest.approx(expected_lat, abs=1e-9)
        # ~0.013° north of the linear-lat midpoint at this latitude/extent
        assert lat > 56.0

    def test_geo_to_pixel_roundtrip(self):
        """pixel_to_geo → geo_to_pixel should round-trip."""
        t = create_transformer_from_bounds(
            800, 600,
            min_lon=11.9, min_lat=57.6,
            max_lon=12.1, max_lat=57.8,
        )
        for px, py in [(0, 0), (400, 300), (800, 600), (200, 100)]:
            lon, lat = t.pixel_to_geo(px, py)
            px2, py2 = t.geo_to_pixel(lon, lat)
            assert px2 == pytest.approx(px, abs=1e-6)
            assert py2 == pytest.approx(py, abs=1e-6)

    def test_scale_factors_isotropic_for_square_mercator_tiles(self):
        """Slippy tiles are square in Mercator: when the pixel grid matches
        (lon span / W == merc span / H), x and y scales must be equal."""
        min_lat, max_lat = 57.0, 57.5
        merc_span = merc(max_lat) - merc(min_lat)
        lon_span = math.degrees(merc_span)  # square mercator pixels
        width, height = 1000, 1000
        t = create_transformer_from_bounds(
            width, height, 11.0, min_lat, 11.0 + lon_span, max_lat)
        scale_x, scale_y = t.get_scale_factor()
        assert scale_x == pytest.approx(scale_y, rel=1e-6)
        assert scale_x > 0

    def test_invalid_bounds_return_none(self):
        assert create_transformer_from_bounds(0, 100, 11.0, 57.0, 12.0, 58.0) is None
        assert create_transformer_from_bounds(100, 100, 12.0, 57.0, 11.0, 58.0) is None
        assert create_transformer_from_bounds(100, 100, 11.0, 58.0, 12.0, 57.0) is None
        assert create_transformer_from_bounds(100, 100, 11.0, 57.0, 12.0, 90.0) is None


class TestReprojectGeometry:
    """Tests for geometry re-projection between transformers."""

    def test_polyline_with_geo_points(self):
        """Polyline with geo_points should re-project correctly."""
        from orbit.utils.reproject import reproject_project_geometry

        # Same bounds at double resolution: positions scale exactly 2x
        t_old = create_transformer_from_bounds(
            1000, 800, 11.0, 57.0, 12.0, 58.0,
        )
        t_new = create_transformer_from_bounds(
            2000, 1600, 11.0, 57.0, 12.0, 58.0,
        )

        geo = (11.5, 57.5)
        project = Project()
        poly = Polyline(
            id="test",
            points=[t_old.geo_to_pixel(*geo)],
            geo_points=[geo],
        )
        project.polylines.append(poly)

        reproject_project_geometry(project, t_old, t_new)

        old_x, old_y = t_old.geo_to_pixel(*geo)
        assert poly.points[0][0] == pytest.approx(2 * old_x, abs=1e-6)
        assert poly.points[0][1] == pytest.approx(2 * old_y, abs=1e-6)

    def test_polyline_pixel_only(self):
        """Polyline with only pixel coords gets geo_points created."""
        from orbit.utils.reproject import reproject_project_geometry

        t_old = create_transformer_from_bounds(
            1000, 800, 11.0, 57.0, 12.0, 58.0,
        )
        t_new = create_transformer_from_bounds(
            500, 400, 11.0, 57.0, 12.0, 58.0,
        )

        project = Project()
        poly = Polyline(id="test", points=[(500, 400)])
        project.polylines.append(poly)

        reproject_project_geometry(project, t_old, t_new)

        # Should now have geo_points
        assert poly.geo_points is not None
        assert len(poly.geo_points) == 1
        # Same bounds at half resolution → exactly halved coords
        assert poly.points[0][0] == pytest.approx(250.0, abs=1e-6)
        assert poly.points[0][1] == pytest.approx(200.0, abs=1e-6)

    def test_control_points_reprojected(self):
        """Control point pixel positions should be updated."""
        from orbit.utils.reproject import reproject_project_geometry

        t_old = create_transformer_from_bounds(
            1000, 800, 11.0, 57.0, 12.0, 58.0,
        )
        t_new = create_transformer_from_bounds(
            2000, 1600, 11.0, 57.0, 12.0, 58.0,
        )

        old_px, old_py = t_old.geo_to_pixel(11.5, 57.5)
        project = Project()
        cp = ControlPoint(
            pixel_x=old_px, pixel_y=old_py,
            longitude=11.5, latitude=57.5,
            name="test",
        )
        project.control_points.append(cp)

        reproject_project_geometry(project, t_old, t_new)

        assert cp.pixel_x == pytest.approx(2 * old_px, abs=1e-6)
        assert cp.pixel_y == pytest.approx(2 * old_py, abs=1e-6)
        # Geographic coords unchanged
        assert cp.longitude == 11.5
        assert cp.latitude == 57.5

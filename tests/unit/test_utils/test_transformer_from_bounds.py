"""Tests for create_transformer_from_bounds and geometry re-projection."""

import numpy as np
import pytest

from orbit.models.project import ControlPoint, Project
from orbit.models.polyline import Polyline
from orbit.utils.coordinate_transform import create_transformer_from_bounds


class TestCreateTransformerFromBounds:
    """Tests for creating an affine transformer from geographic bounds."""

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
        assert lon == pytest.approx(11.0, abs=0.01)
        assert lat == pytest.approx(58.0, abs=0.01)

        # Bottom-right pixel → SE corner
        lon, lat = t.pixel_to_geo(1000, 800)
        assert lon == pytest.approx(12.0, abs=0.01)
        assert lat == pytest.approx(57.0, abs=0.01)

    def test_center_point(self):
        """Image center should map to geographic center."""
        t = create_transformer_from_bounds(
            2000, 1000,
            min_lon=10.0, min_lat=55.0,
            max_lon=12.0, max_lat=57.0,
        )
        lon, lat = t.pixel_to_geo(1000, 500)
        assert lon == pytest.approx(11.0, abs=0.01)
        assert lat == pytest.approx(56.0, abs=0.01)

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
            assert px2 == pytest.approx(px, abs=0.5)
            assert py2 == pytest.approx(py, abs=0.5)


class TestReprojectGeometry:
    """Tests for geometry re-projection between transformers."""

    def test_polyline_with_geo_points(self):
        """Polyline with geo_points should re-project correctly."""
        from orbit.utils.reproject import reproject_project_geometry

        # Create two transformers with different pixel spaces
        t_old = create_transformer_from_bounds(
            1000, 800, 11.0, 57.0, 12.0, 58.0,
        )
        t_new = create_transformer_from_bounds(
            2000, 1600, 11.0, 57.0, 12.0, 58.0,
        )

        project = Project()
        poly = Polyline(
            id="test",
            points=[(500, 400)],
            geo_points=[(11.5, 57.5)],
        )
        project.polylines.append(poly)

        reproject_project_geometry(project, t_old, t_new)

        # In the new image (2x size), center should be at (1000, 800)
        assert poly.points[0][0] == pytest.approx(1000.0, abs=2.0)
        assert poly.points[0][1] == pytest.approx(800.0, abs=2.0)

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
        # And pixel coords should be re-projected (halved image → halved coords)
        assert poly.points[0][0] == pytest.approx(250.0, abs=2.0)
        assert poly.points[0][1] == pytest.approx(200.0, abs=2.0)

    def test_control_points_reprojected(self):
        """Control point pixel positions should be updated."""
        from orbit.utils.reproject import reproject_project_geometry

        t_old = create_transformer_from_bounds(
            1000, 800, 11.0, 57.0, 12.0, 58.0,
        )
        t_new = create_transformer_from_bounds(
            2000, 1600, 11.0, 57.0, 12.0, 58.0,
        )

        project = Project()
        cp = ControlPoint(
            pixel_x=500, pixel_y=400,
            longitude=11.5, latitude=57.5,
            name="test",
        )
        project.control_points.append(cp)

        reproject_project_geometry(project, t_old, t_new)

        assert cp.pixel_x == pytest.approx(1000.0, abs=2.0)
        assert cp.pixel_y == pytest.approx(800.0, abs=2.0)
        # Geographic coords unchanged
        assert cp.longitude == 11.5
        assert cp.latitude == 57.5

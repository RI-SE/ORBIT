"""Integration test: edits made in aerial view must survive the round-trip
back to the original image and reach export-ready geo coordinates (M7)."""

import pytest

from orbit.models.junction import Junction
from orbit.models.polyline import LineType, Polyline
from orbit.models.project import ControlPoint, Project
from orbit.models.road import Road
from orbit.utils.coordinate_transform import (
    create_transformer,
    create_transformer_from_bounds,
)
from orbit.utils.geo_sync import refresh_stale_geo_points
from orbit.utils.reproject import reproject_project_geometry


def _make_project():
    """Project with an affine 'original image' transformer, one road polyline
    and one connecting road, all geo-synced."""
    cps = [
        ControlPoint(pixel_x=100.0, pixel_y=100.0,
                     longitude=12.940, latitude=57.720, name="A"),
        ControlPoint(pixel_x=900.0, pixel_y=100.0,
                     longitude=12.950, latitude=57.720, name="B"),
        ControlPoint(pixel_x=100.0, pixel_y=700.0,
                     longitude=12.940, latitude=57.714, name="C"),
        ControlPoint(pixel_x=900.0, pixel_y=700.0,
                     longitude=12.950, latitude=57.714, name="D"),
    ]
    project = Project(control_points=cps)
    orig_t = create_transformer(cps, "affine")

    pl = Polyline(id="pl1", line_type=LineType.CENTERLINE)
    pl.points = [(200.0, 200.0), (400.0, 300.0), (600.0, 400.0)]
    pl.geo_points = [orig_t.pixel_to_geo(x, y) for x, y in pl.points]
    project.polylines.append(pl)

    cr = Road(name="CR1", junction_id="j1",
              inline_path=[(600.0, 400.0), (650.0, 420.0), (700.0, 450.0)])
    cr.inline_geo_path = [orig_t.pixel_to_geo(x, y) for x, y in cr.inline_path]
    project.add_road(cr)

    j = Junction(center_point=(650.0, 420.0))
    j.geo_center_point = orig_t.pixel_to_geo(650.0, 420.0)
    j.add_connecting_road(cr.id)
    project.junctions.append(j)

    return project, orig_t, pl, cr


AERIAL_BOUNDS = dict(min_lon=12.938, min_lat=57.712, max_lon=12.952, max_lat=57.722)


class TestAerialEditRoundTrip:

    def test_polyline_edit_without_geo_sync_survives(self):
        """Worst case: a point dragged in aerial view whose geo sync was
        skipped — the geo_stale flag must carry the edit back (H2/M7)."""
        project, orig_t, pl, _ = _make_project()
        aerial_t = create_transformer_from_bounds(1400, 1000, **AERIAL_BOUNDS)

        reproject_project_geometry(project, orig_t, aerial_t)

        # Edit in aerial pixel space through the model mutator (sets geo_stale),
        # deliberately without the GUI's edit-time geo sync.
        ax, ay = pl.points[1]
        pl.update_point(1, ax + 25.0, ay - 10.0)
        edited_geo = aerial_t.pixel_to_geo(ax + 25.0, ay - 10.0)

        reproject_project_geometry(project, aerial_t, orig_t)

        assert pl.geo_points[1] == pytest.approx(edited_geo, abs=1e-9)
        expected_px = orig_t.geo_to_pixel(*edited_geo)
        assert pl.points[1] == pytest.approx(expected_px, abs=1e-6)

        # Export-time refresh must not move anything further
        assert refresh_stale_geo_points(project, orig_t) == 0

    def test_cr_edit_with_geo_sync_survives(self):
        """CR mid-point edit, geo synced at edit time (as the GUI does)."""
        project, orig_t, _, cr = _make_project()
        aerial_t = create_transformer_from_bounds(1400, 1000, **AERIAL_BOUNDS)

        reproject_project_geometry(project, orig_t, aerial_t)

        ax, ay = cr.inline_path[1]
        cr.inline_path[1] = (ax + 15.0, ay + 20.0)
        cr.inline_geo_path[1] = aerial_t.pixel_to_geo(ax + 15.0, ay + 20.0)
        edited_geo = cr.inline_geo_path[1]

        reproject_project_geometry(project, aerial_t, orig_t)

        assert cr.inline_geo_path[1] == pytest.approx(edited_geo, abs=1e-9)
        expected_px = orig_t.geo_to_pixel(*edited_geo)
        assert cr.inline_path[1] == pytest.approx(expected_px, abs=1e-6)

    def test_unedited_geometry_returns_exactly(self):
        """Round-trip without edits must reproduce original pixels and
        leave geo coordinates untouched."""
        project, orig_t, pl, cr = _make_project()
        original_pl_geo = list(pl.geo_points)
        original_pl_px = list(pl.points)
        original_cr_px = list(cr.inline_path)
        aerial_t = create_transformer_from_bounds(1400, 1000, **AERIAL_BOUNDS)

        reproject_project_geometry(project, orig_t, aerial_t)
        reproject_project_geometry(project, aerial_t, orig_t)

        # Geo untouched (it is the round-trip invariant)
        for got, exp in zip(pl.geo_points, original_pl_geo):
            assert got == pytest.approx(exp, abs=1e-12)
        # Pixels reproduced from geo via the same transformer
        for got, exp in zip(pl.points, original_pl_px):
            assert got == pytest.approx(exp, abs=1e-6)
        for got, exp in zip(cr.inline_path, original_cr_px):
            assert got == pytest.approx(exp, abs=1e-6)

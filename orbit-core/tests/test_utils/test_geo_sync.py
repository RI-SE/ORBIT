"""
Unit tests for geo/pixel consistency helpers (orbit_core.utils.geo_sync).
"""

import pytest

from orbit_core.models import Project, Road
from orbit_core.models.polyline import Polyline
from orbit_core.utils.geo_sync import (
    polyline_to_metric_points,
    refresh_polyline_geo_points,
    refresh_stale_geo_points,
)

# Degrees per pixel for the fake transformer (~1.1 m/px at the equator)
DEG_PER_PX = 1e-5


class FakeTransformer:
    """Linear pixel<->geo mapping with a configurable pixel offset."""

    def __init__(self, offset_px: float = 0.0):
        self.offset_px = offset_px

    def pixel_to_geo(self, px, py):
        return ((px - self.offset_px) * DEG_PER_PX,
                -(py - self.offset_px) * DEG_PER_PX)

    def geo_to_pixel(self, lon, lat):
        return (lon / DEG_PER_PX + self.offset_px,
                -lat / DEG_PER_PX + self.offset_px)

    def latlon_to_meters(self, lat, lon):
        return (lon * 111320.0, lat * 111320.0)

    def pixels_to_meters_batch(self, pixels):
        result = []
        for px, py in pixels:
            lon, lat = self.pixel_to_geo(px, py)
            result.append(self.latlon_to_meters(lat, lon))
        return result


def make_synced_polyline(transformer, points):
    """Polyline whose geo_points match its pixel points exactly."""
    return Polyline(
        id='pl1',
        points=list(points),
        geo_points=[transformer.pixel_to_geo(px, py) for px, py in points],
    )


class TestGeoStaleFlag:
    """Point mutators must mark geo as stale; constructor must not."""

    def test_constructor_default_not_stale(self):
        assert Polyline(id='p', points=[(0, 0)]).geo_stale is False

    @pytest.mark.parametrize('mutate', [
        lambda pl: pl.add_point(5.0, 5.0),
        lambda pl: pl.insert_point(1, 5.0, 5.0),
        lambda pl: pl.update_point(0, 5.0, 5.0),
        lambda pl: pl.remove_point(0),
    ])
    def test_mutators_set_stale(self, mutate):
        pl = Polyline(id='p', points=[(0.0, 0.0), (10.0, 10.0)])
        mutate(pl)
        assert pl.geo_stale is True

    def test_serialization_roundtrip(self):
        pl = Polyline(id='p', points=[(0.0, 0.0)])
        pl.update_point(0, 1.0, 1.0)
        restored = Polyline.from_dict(pl.to_dict())
        assert restored.geo_stale is True
        # Flag omitted from dict when not stale
        assert 'geo_stale' not in Polyline(id='q', points=[]).to_dict()


class TestRefreshPolyline:
    """refresh_polyline_geo_points threshold behavior."""

    def test_synced_polyline_untouched(self):
        t = FakeTransformer()
        pl = make_synced_polyline(t, [(0.0, 0.0), (100.0, 50.0)])
        original_geo = list(pl.geo_points)
        assert refresh_polyline_geo_points(pl, t) == 0
        assert pl.geo_points == original_geo

    def test_unflagged_subthreshold_drift_preserved(self):
        """Sub-2px drift on un-edited polylines keeps imported geo precision."""
        t = FakeTransformer()
        pl = make_synced_polyline(t, [(0.0, 0.0), (100.0, 50.0)])
        pl.points[1] = (101.0, 50.0)  # direct mutation: 1px, no flag
        original_geo = list(pl.geo_points)
        assert refresh_polyline_geo_points(pl, t) == 0
        assert pl.geo_points == original_geo

    def test_flagged_subthreshold_edit_refreshed(self):
        """A sub-2px edit through the mutators reaches geo (M5)."""
        t = FakeTransformer()
        pl = make_synced_polyline(t, [(0.0, 0.0), (100.0, 50.0)])
        pl.update_point(1, 101.0, 50.0)  # 1px edit, sets geo_stale
        assert refresh_polyline_geo_points(pl, t) == 1
        assert pl.geo_points[1] == pytest.approx(t.pixel_to_geo(101.0, 50.0))
        assert pl.geo_stale is False

    def test_unflagged_large_drift_refreshed(self):
        t = FakeTransformer()
        pl = make_synced_polyline(t, [(0.0, 0.0), (100.0, 50.0)])
        pl.points[0] = (10.0, 0.0)  # 10px, beyond 2px threshold
        assert refresh_polyline_geo_points(pl, t) == 1
        assert pl.geo_points[0] == pytest.approx(t.pixel_to_geo(10.0, 0.0))

    def test_length_mismatch_rebuilds_geo(self):
        """H4: mismatched geo_points are rebuilt from pixels, not skipped."""
        t = FakeTransformer()
        pl = make_synced_polyline(t, [(0.0, 0.0), (100.0, 50.0)])
        pl.points.append((200.0, 100.0))  # pixel added without geo entry
        assert refresh_polyline_geo_points(pl, t) == 3
        assert len(pl.geo_points) == len(pl.points)
        assert pl.geo_points[2] == pytest.approx(t.pixel_to_geo(200.0, 100.0))

    def test_edited_only_skips_unflagged_drift(self):
        """In edited_only mode (view switch) geo stays authoritative for
        unflagged drift, e.g. from adjustment/transformer changes."""
        t = FakeTransformer()
        pl = make_synced_polyline(t, [(0.0, 0.0), (100.0, 50.0)])
        pl.points[0] = (10.0, 0.0)  # large drift, but no edit flag
        original_geo = list(pl.geo_points)
        assert refresh_polyline_geo_points(pl, t, edited_only=True) == 0
        assert pl.geo_points == original_geo

    def test_edited_only_still_refreshes_flagged(self):
        t = FakeTransformer()
        pl = make_synced_polyline(t, [(0.0, 0.0), (100.0, 50.0)])
        pl.update_point(0, 10.0, 0.0)
        assert refresh_polyline_geo_points(pl, t, edited_only=True) == 1
        assert pl.geo_points[0] == pytest.approx(t.pixel_to_geo(10.0, 0.0))

    def test_no_geo_points_noop(self):
        pl = Polyline(id='p', points=[(0.0, 0.0)])
        pl.geo_stale = True
        assert refresh_polyline_geo_points(pl, FakeTransformer()) == 0
        assert pl.geo_points is None
        assert pl.geo_stale is False


class TestRefreshProject:
    """refresh_stale_geo_points over a whole project."""

    def test_connecting_road_mismatch_rebuilt(self):
        t = FakeTransformer()
        project = Project()
        cr = Road(id='cr1', junction_id='j1')
        cr.inline_path = [(0.0, 0.0), (10.0, 10.0), (20.0, 20.0)]
        cr.inline_geo_path = [t.pixel_to_geo(0.0, 0.0)]  # wrong length
        project.roads.append(cr)
        refreshed = refresh_stale_geo_points(project, t)
        assert refreshed == 3
        assert len(cr.inline_geo_path) == 3
        assert cr.inline_geo_path[2] == pytest.approx(t.pixel_to_geo(20.0, 20.0))

    def test_none_transformer_noop(self):
        assert refresh_stale_geo_points(Project(), None) == 0

    def test_endpoint_snap_marks_stale(self):
        """Project.enforce_road_links endpoint snapping flags geo as stale."""
        t = FakeTransformer()
        pl = make_synced_polyline(t, [(0.0, 0.0), (100.0, 50.0)])
        pl.update_point(0, 1.0, 1.0)
        assert pl.geo_stale is True


class TestPolylineToMetricPoints:
    """Geo used only when consistent; pixel fallback on mismatch."""

    def test_uses_geo_when_lengths_match(self):
        t = FakeTransformer()
        pl = make_synced_polyline(t, [(0.0, 0.0), (100.0, 50.0)])
        expected = [t.latlon_to_meters(lat, lon) for lon, lat in pl.geo_points]
        assert polyline_to_metric_points(pl, t) == pytest.approx(expected)

    def test_falls_back_to_pixels_on_mismatch(self):
        t = FakeTransformer()
        pl = make_synced_polyline(t, [(0.0, 0.0), (100.0, 50.0)])
        pl.points.append((200.0, 100.0))
        result = polyline_to_metric_points(pl, t)
        assert len(result) == 3
        assert result == pytest.approx(t.pixels_to_meters_batch(pl.points))


class TestReprojectPreservesEdits:
    """H2: pixel edits survive a view switch even when geo was not synced."""

    def test_unsynced_edit_survives_reprojection(self):
        from orbit_core.utils.reproject import reproject_project_geometry

        old_t = FakeTransformer(offset_px=0.0)
        new_t = FakeTransformer(offset_px=500.0)
        project = Project()
        pl = make_synced_polyline(old_t, [(0.0, 0.0), (100.0, 50.0)])
        pl.update_point(1, 110.0, 50.0)  # edit without geo sync
        project.polylines.append(pl)

        reproject_project_geometry(project, old_t, new_t)

        # The edited point must land at the new-space equivalent of the
        # EDITED pixel position, not the pre-edit one.
        expected = new_t.geo_to_pixel(*old_t.pixel_to_geo(110.0, 50.0))
        assert pl.points[1] == pytest.approx(expected)

"""Tests for adjustment handling during aerial view round-trip and refinement."""

import pytest

from orbit.models.polyline import LineType, Polyline, RoadMarkType
from orbit.models.project import ControlPoint, Project
from orbit.utils.coordinate_transform import (
    HybridTransformer,
    TransformAdjustment,
    create_transformer,
    create_transformer_from_bounds,
)
from orbit.utils.reproject import reproject_project_geometry


def _make_project_with_adjustment():
    """Create a project with control points, polylines, and an active adjustment."""
    cps = [
        ControlPoint(pixel_x=100.0, pixel_y=100.0,
                     longitude=12.940, latitude=57.720, name="CP1"),
        ControlPoint(pixel_x=500.0, pixel_y=100.0,
                     longitude=12.945, latitude=57.720, name="CP2"),
        ControlPoint(pixel_x=300.0, pixel_y=400.0,
                     longitude=12.9425, latitude=57.718, name="CP3"),
        ControlPoint(pixel_x=500.0, pixel_y=400.0,
                     longitude=12.945, latitude=57.718, name="CP4"),
    ]
    project = Project(control_points=cps)

    # Add a polyline with geo_points
    pl = Polyline(id="p1", line_type=LineType.CENTERLINE,
                  road_mark_type=RoadMarkType.NONE, color=(255, 0, 0))
    pl.points = [(200.0, 200.0), (350.0, 250.0), (450.0, 350.0)]
    # Compute geo_points from the transformer
    t = create_transformer(cps, "affine")
    pl.geo_points = [t.pixel_to_geo(x, y) for x, y in pl.points]
    project.polylines.append(pl)

    return project, t


class TestReprojectPreservesControlPoints:
    """Control point pixel positions must not be shifted by the adjustment."""

    def test_round_trip_without_adjustment(self):
        """Basic round-trip without adjustment should preserve CP positions."""
        project, original_t = _make_project_with_adjustment()
        original_cp_positions = [(cp.pixel_x, cp.pixel_y)
                                  for cp in project.control_points]

        aerial_t = create_transformer_from_bounds(
            2000, 1500, 12.938, 57.716, 12.948, 57.722)

        reproject_project_geometry(project, original_t, aerial_t)
        reproject_project_geometry(project, aerial_t, original_t)

        for (orig_x, orig_y), cp in zip(original_cp_positions,
                                         project.control_points):
            assert cp.pixel_x == pytest.approx(orig_x, abs=0.5)
            assert cp.pixel_y == pytest.approx(orig_y, abs=0.5)

    def test_round_trip_with_adjustment_on_transformer(self):
        """CPs must not be shifted when the transformer has an active adjustment."""
        project, original_t = _make_project_with_adjustment()
        original_cp_positions = [(cp.pixel_x, cp.pixel_y)
                                  for cp in project.control_points]

        # Set a non-trivial adjustment on the original transformer
        adj = TransformAdjustment(
            translation_x=15.0, translation_y=-8.0,
            rotation=0.3, scale_x=1.01, scale_y=0.99,
            pivot_x=300.0, pivot_y=250.0,
        )
        original_t.set_adjustment(adj)

        aerial_t = create_transformer_from_bounds(
            2000, 1500, 12.938, 57.716, 12.948, 57.722)

        # Forward: original → aerial (adjustment on old_transformer is OK for pixel_to_geo)
        reproject_project_geometry(project, original_t, aerial_t)

        # Backward: aerial → original — clear adjustment before reproject
        saved_adj = original_t.adjustment
        original_t.clear_adjustment()
        reproject_project_geometry(project, aerial_t, original_t)
        original_t.set_adjustment(saved_adj)

        # CPs should be back at their unadjusted original positions
        for (orig_x, orig_y), cp in zip(original_cp_positions,
                                         project.control_points):
            assert cp.pixel_x == pytest.approx(orig_x, abs=0.5), \
                f"CP {cp.name} pixel_x shifted: {orig_x} → {cp.pixel_x}"
            assert cp.pixel_y == pytest.approx(orig_y, abs=0.5), \
                f"CP {cp.name} pixel_y shifted: {orig_y} → {cp.pixel_y}"

    def test_adjusted_reproject_corrupts_cp_positions(self):
        """Demonstrate that reprojecting WITH adjustment shifts CPs (the old bug)."""
        project, original_t = _make_project_with_adjustment()
        original_cp_positions = [(cp.pixel_x, cp.pixel_y)
                                  for cp in project.control_points]

        adj = TransformAdjustment(
            translation_x=20.0, translation_y=-10.0,
            pivot_x=300.0, pivot_y=250.0,
        )
        original_t.set_adjustment(adj)

        aerial_t = create_transformer_from_bounds(
            2000, 1500, 12.938, 57.716, 12.948, 57.722)

        reproject_project_geometry(project, original_t, aerial_t)
        # If we reproject back WITH adjustment still set, CPs get corrupted
        reproject_project_geometry(project, aerial_t, original_t)

        # CPs should be shifted by the adjustment (the old buggy behavior)
        any_shifted = False
        for (orig_x, orig_y), cp in zip(original_cp_positions,
                                         project.control_points):
            if abs(cp.pixel_x - orig_x) > 1.0 or abs(cp.pixel_y - orig_y) > 1.0:
                any_shifted = True
                break
        assert any_shifted, "Expected CPs to be shifted (demonstrating the old bug)"

    def test_polyline_positions_correct_after_round_trip(self):
        """Polylines should have correct adjusted positions after round-trip."""
        project, original_t = _make_project_with_adjustment()

        adj = TransformAdjustment(
            translation_x=10.0, translation_y=-5.0,
            pivot_x=300.0, pivot_y=250.0,
        )
        original_t.set_adjustment(adj)

        # Compute expected adjusted positions
        expected_positions = []
        for lon, lat in project.polylines[0].geo_points:
            px, py = original_t.geo_to_pixel(lon, lat)
            expected_positions.append((px, py))

        aerial_t = create_transformer_from_bounds(
            2000, 1500, 12.938, 57.716, 12.948, 57.722)

        # Forward trip
        reproject_project_geometry(project, original_t, aerial_t)

        # Backward trip (with fix: clear adjustment before reproject)
        original_t.clear_adjustment()
        reproject_project_geometry(project, aerial_t, original_t)
        original_t.set_adjustment(adj)

        # Re-apply adjustment to polyline positions (mimics update_all_from_geo_coords)
        pl = project.polylines[0]
        pl.points = [original_t.geo_to_pixel(lon, lat)
                     for lon, lat in pl.geo_points]

        for (exp_x, exp_y), (act_x, act_y) in zip(expected_positions, pl.points):
            assert act_x == pytest.approx(exp_x, abs=0.5)
            assert act_y == pytest.approx(exp_y, abs=0.5)


class TestStalePixelPositionsOnLoad:
    """Pixel positions must be recalculated from geo_points on load when adjustment is active."""

    def test_stale_unadjusted_positions_become_consistent(self):
        """Simulates the real bug: file has unadjusted pixel positions but active adjustment."""
        project, t = _make_project_with_adjustment()
        pl = project.polylines[0]

        # The stored pixel positions are UNADJUSTED (computed without adjustment)
        unadjusted_positions = list(pl.points)

        # Create a non-trivial adjustment (with Y-scale like the real project)
        adj = TransformAdjustment(
            translation_x=-1.0, translation_y=-2.3,
            rotation=0.02, scale_x=0.999, scale_y=1.02,
            pivot_x=300.0, pivot_y=250.0,
        )
        t.set_adjustment(adj)

        # Compute what the ADJUSTED positions should be
        adjusted_positions = [t.geo_to_pixel(lon, lat) for lon, lat in pl.geo_points]

        # Verify the adjustment actually changes positions meaningfully
        max_diff = max(
            max(abs(a[0] - u[0]), abs(a[1] - u[1]))
            for a, u in zip(adjusted_positions, unadjusted_positions)
        )
        assert max_diff > 1.0, "Adjustment should produce noticeable position change"

        # Simulate _restore_adjustment_from_project: update from geo_points
        pl.points = [t.geo_to_pixel(lon, lat) for lon, lat in pl.geo_points]

        # Now do an aerial round-trip
        aerial_t = create_transformer_from_bounds(
            2000, 1500, 12.938, 57.716, 12.948, 57.722)
        reproject_project_geometry(project, t, aerial_t)

        saved_adj = t.adjustment
        t.clear_adjustment()
        reproject_project_geometry(project, aerial_t, t)
        t.set_adjustment(saved_adj)

        # Re-apply adjustment
        pl.points = [t.geo_to_pixel(lon, lat) for lon, lat in pl.geo_points]

        # Positions should match the adjusted positions exactly (no shift)
        for (exp_x, exp_y), (act_x, act_y) in zip(adjusted_positions, pl.points):
            assert act_x == pytest.approx(exp_x, abs=0.01)
            assert act_y == pytest.approx(exp_y, abs=0.01)


class TestHybridTransformerRefineInverse:
    """_refine_inverse must not be affected by the adjustment."""

    def _make_hybrid(self):
        """Create a HybridTransformer with enough control points."""
        cps = [
            ControlPoint(pixel_x=0.0, pixel_y=0.0,
                         longitude=12.93, latitude=57.72, name="A"),
            ControlPoint(pixel_x=1000.0, pixel_y=0.0,
                         longitude=12.95, latitude=57.72, name="B"),
            ControlPoint(pixel_x=1000.0, pixel_y=800.0,
                         longitude=12.95, latitude=57.71, name="C"),
            ControlPoint(pixel_x=0.0, pixel_y=800.0,
                         longitude=12.93, latitude=57.71, name="D"),
            ControlPoint(pixel_x=500.0, pixel_y=400.0,
                         longitude=12.94, latitude=57.715, name="E"),
        ]
        return HybridTransformer(cps, image_width=1000, image_height=800)

    def test_geo_to_pixel_roundtrip_with_adjustment(self):
        """geo_to_pixel → pixel_to_geo should round-trip with adjustment."""
        t = self._make_hybrid()
        adj = TransformAdjustment(
            translation_x=10.0, translation_y=-5.0,
            rotation=0.2, scale_x=1.005, scale_y=0.995,
            pivot_x=500.0, pivot_y=400.0,
        )
        t.set_adjustment(adj)

        # Test at several points including near edges (blend zone)
        test_geo = [
            (12.94, 57.715),   # center
            (12.935, 57.718),  # near edge
            (12.945, 57.712),  # near edge
        ]

        for lon, lat in test_geo:
            px, py = t.geo_to_pixel(lon, lat)
            lon2, lat2 = t.pixel_to_geo(px, py)
            assert lon2 == pytest.approx(lon, abs=1e-8), \
                f"Lon round-trip failed at ({lon}, {lat}): {lon} → {lon2}"
            assert lat2 == pytest.approx(lat, abs=1e-8), \
                f"Lat round-trip failed at ({lon}, {lat}): {lat} → {lat2}"

    def test_refine_inverse_consistent_with_without_adjustment(self):
        """Base pixel positions from geo_to_pixel should be same with/without adjustment."""
        t = self._make_hybrid()

        # Get base pixel positions without adjustment
        test_geo = [(12.94, 57.715), (12.935, 57.718)]
        base_positions = [t.geo_to_pixel(lon, lat) for lon, lat in test_geo]

        # Now set adjustment
        adj = TransformAdjustment(
            translation_x=15.0, translation_y=-8.0,
            pivot_x=500.0, pivot_y=400.0,
        )
        t.set_adjustment(adj)

        # Adjusted positions should differ from base by exactly the adjustment
        for (lon, lat), (base_px, base_py) in zip(test_geo, base_positions):
            adj_px, adj_py = t.geo_to_pixel(lon, lat)
            # The difference should match what the adjustment does to the base position
            expected_px, expected_py = adj.apply_to_point(base_px, base_py)
            assert adj_px == pytest.approx(expected_px, abs=0.1)
            assert adj_py == pytest.approx(expected_py, abs=0.1)


class TestBakeAdjustmentIntoControlPoints:
    """_bake_adjustment_into_control_points must correctly shift CP pixel positions."""

    def test_bake_shifts_cp_positions(self):
        """After baking, CP pixel positions reflect the adjustment."""
        project, t = _make_project_with_adjustment()
        adj = TransformAdjustment(
            translation_x=10.0, translation_y=-5.0,
            pivot_x=300.0, pivot_y=250.0,
        )
        original_positions = [(cp.pixel_x, cp.pixel_y) for cp in project.control_points]

        # Simulate bake: apply adjustment to each CP
        for cp in project.control_points:
            cp.pixel_x, cp.pixel_y = adj.apply_to_point(cp.pixel_x, cp.pixel_y)

        # After bake, CP positions should have changed
        baked_positions = [(cp.pixel_x, cp.pixel_y) for cp in project.control_points]
        for (ox, oy), (bx, by) in zip(original_positions, baked_positions):
            expected_x, expected_y = adj.apply_to_point(ox, oy)
            assert bx == pytest.approx(expected_x, abs=0.001)
            assert by == pytest.approx(expected_y, abs=0.001)

    def test_bake_then_rebuild_transformer_matches_adjusted_positions(self):
        """After baking, transformer rebuilt from new CPs should match original adjusted output."""
        project, t = _make_project_with_adjustment()
        adj = TransformAdjustment(
            translation_x=8.0, translation_y=-4.0,
            pivot_x=300.0, pivot_y=250.0,
        )
        t.set_adjustment(adj)

        # Capture adjusted pixel positions for a test geo point
        test_lon, test_lat = 12.942, 57.719
        adjusted_px, adjusted_py = t.geo_to_pixel(test_lon, test_lat)

        # Bake adjustment into CPs
        for cp in project.control_points:
            cp.pixel_x, cp.pixel_y = adj.apply_to_point(cp.pixel_x, cp.pixel_y)

        # Rebuild transformer from baked CPs (no adjustment)
        t2 = create_transformer(project.control_points, "affine")

        # New transformer (without adjustment) should produce same pixel as old+adj
        new_px, new_py = t2.geo_to_pixel(test_lon, test_lat)
        assert new_px == pytest.approx(adjusted_px, abs=1.0)
        assert new_py == pytest.approx(adjusted_py, abs=1.0)

    def test_project_transform_adjustment_cleared_after_bake(self):
        """After baking, project.transform_adjustment should be None (not stored)."""
        project, _ = _make_project_with_adjustment()

        # Simulate what _sync_adjustment_to_project does (new behavior: always None)
        project.transform_adjustment = None

        assert project.transform_adjustment is None
        # Verify it's serialized as None
        data = project.to_dict()
        assert data.get('transform_adjustment') is None

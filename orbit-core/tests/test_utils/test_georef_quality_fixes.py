"""Regression tests for georef quality numbers: true training residuals, and uncertainty refits
that use the same transformer kind as the project."""

import numpy as np
import pytest

from orbit_core.models.project import ControlPoint
from orbit_core.utils.coordinate_transform import (
    AffineTransformer,
    HomographyTransformer,
    HybridTransformer,
)
from orbit_core.utils.gcp_analyzer import analyze_control_points
from orbit_core.utils.uncertainty_estimator import UncertaintyEstimator

IMAGE_W, IMAGE_H = 1000, 800
DEG_PER_PX = 1e-5


def _grid_points(offset_px=None):
    """Six points on an exact affine pixel->geo mapping; offset_px shifts one clicked pixel."""
    points = []
    for i, (u, v) in enumerate([(100, 100), (900, 100), (100, 700), (900, 700), (500, 400), (300, 600)]):
        points.append(ControlPoint(pixel_x=float(u), pixel_y=float(v),
                                   longitude=12.0 + u * DEG_PER_PX, latitude=57.7 - v * DEG_PER_PX,
                                   name=f"p{i}"))
    if offset_px:
        points[4].pixel_x += offset_px
    return points


class TestTrainingResidual:
    def test_exact_points_have_zero_pixel_error(self):
        t = HomographyTransformer(_grid_points())
        assert t.reprojection_error["rmse_pixels"] == pytest.approx(0.0, abs=1e-6)

    def test_misclicked_point_shows_up_in_pixel_error(self):
        # The old pixel->geo->pixel round trip reported ~0 here regardless of the misfit
        t = HomographyTransformer(_grid_points(offset_px=5.0))
        assert t.reprojection_error["rmse_pixels"] > 0.5
        assert t.reprojection_error["rmse_meters"] > 0.0

    def test_pixel_and_meter_errors_agree_in_scale(self):
        t = HomographyTransformer(_grid_points(offset_px=5.0))
        # The misclick is along x, so the x scale (m/px) links the two residuals
        scale_x, _ = t.get_scale_factor()
        err = t.reprojection_error
        assert err["rmse_meters"] == pytest.approx(err["rmse_pixels"] * scale_x, rel=0.15)


class TestRefitKeepsTransformerKind:
    @pytest.mark.parametrize("make", [
        lambda pts: AffineTransformer(pts),
        lambda pts: HomographyTransformer(pts),
        lambda pts: HybridTransformer(pts, image_width=IMAGE_W, image_height=IMAGE_H),
    ])
    def test_refit_returns_same_kind(self, make):
        original = make(_grid_points())
        refitted = original.refit(_grid_points(offset_px=1.0))
        assert type(refitted) is type(original)

    def test_hybrid_refit_keeps_image_bounds(self):
        original = HybridTransformer(_grid_points(), image_width=IMAGE_W, image_height=IMAGE_H)
        refitted = original.refit(_grid_points())
        assert (refitted._image_width, refitted._image_height) == (IMAGE_W, IMAGE_H)


class _CountingHybrid(HybridTransformer):
    refits = 0

    def refit(self, control_points):
        type(self).refits += 1
        return super().refit(control_points)


@pytest.fixture
def counting_hybrid():
    _CountingHybrid.refits = 0
    return _CountingHybrid(_grid_points(offset_px=2.0), image_width=IMAGE_W, image_height=IMAGE_H)


def test_monte_carlo_refits_the_project_transformer(counting_hybrid):
    UncertaintyEstimator(counting_hybrid, IMAGE_W, IMAGE_H).compute_uncertainty_monte_carlo(
        n_iterations=3, resolution=(4, 4))
    assert _CountingHybrid.refits == 3


def test_bootstrap_refits_the_project_transformer(counting_hybrid):
    UncertaintyEstimator(counting_hybrid, IMAGE_W, IMAGE_H).run_bootstrap_analysis(n_iterations=3)
    assert _CountingHybrid.refits == 3


def test_leave_one_out_uses_the_project_transformer(counting_hybrid):
    result = analyze_control_points(counting_hybrid)
    assert result is not None
    assert _CountingHybrid.refits == len(counting_hybrid.training_points)


def test_failed_monte_carlo_samples_are_left_out(counting_hybrid, monkeypatch):
    calls = {"n": 0}
    real_refit = HybridTransformer.refit

    def flaky_refit(self, points):
        calls["n"] += 1
        if calls["n"] % 2 == 0:
            raise np.linalg.LinAlgError("singular")
        return real_refit(self, points)

    monkeypatch.setattr(_CountingHybrid, "refit", flaky_refit)
    grid = UncertaintyEstimator(counting_hybrid, IMAGE_W, IMAGE_H).compute_uncertainty_monte_carlo(
        n_iterations=6, resolution=(4, 4))
    assert np.all(np.isfinite(grid))

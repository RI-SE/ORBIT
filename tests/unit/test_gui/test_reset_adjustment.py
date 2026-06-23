"""Regression tests for MainWindow.reset_adjustment in drone-assisted mode.

For drone-assisted transformers the applied correction lives in
project.transform_adjustment (it cannot be baked into control points).
Resetting the live adjustment must therefore re-apply that stored correction
so the visible alignment keeps the already-applied change rather than
reverting to the uncorrected image.
"""

import os
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from orbit.gui.main_window import MainWindow
from orbit.models.project import Project
from orbit.utils.coordinate_transform import TransformAdjustment


class _FakeImageView:
    """Stand-in for ImageView exposing only what reset_adjustment touches."""

    def __init__(self, adjustment):
        self.current_adjustment = adjustment

    def reset_adjustment(self):
        # Mirrors ImageView.reset_adjustment: collapse the live delta to identity.
        if self.current_adjustment is not None:
            self.current_adjustment.reset()

    def get_adjustment(self):
        return self.current_adjustment


def _make_self(transformer, project, image_view):
    """Build a minimal object that the real MainWindow methods can run against."""
    obj = types.SimpleNamespace(
        project=project,
        image_view=image_view,
        _cached_transformer=transformer,
        _refreshed=False,
    )
    obj.refresh_imported_geometry = lambda: setattr(obj, "_refreshed", True)
    obj._remove_adjustment_ghost = lambda: None
    obj.statusBar = lambda: types.SimpleNamespace(showMessage=lambda *a, **k: None)
    # Bind the real methods under test so their actual bodies run.
    obj._apply_active_adjustment = types.MethodType(
        MainWindow._apply_active_adjustment, obj)
    obj.reset_adjustment = types.MethodType(MainWindow.reset_adjustment, obj)
    return obj


class _RecordingTransformer:
    """Transformer stub tracking the last adjustment applied to it."""

    def __init__(self):
        self.adjustment = None

    def set_adjustment(self, adj):
        self.adjustment = adj

    def clear_adjustment(self):
        self.adjustment = None


def test_reset_reapplies_stored_drone_adjustment():
    """Reset must restore the stored correction for drone-assisted mode."""
    stored = TransformAdjustment(
        translation_x=12.0, translation_y=-7.0,
        rotation=0.15, scale_x=1.02, scale_y=0.98,
        pivot_x=300.0, pivot_y=250.0,
    )
    project = Project(transform_method="drone_assisted")
    project.transform_adjustment = stored.to_dict()

    transformer = _RecordingTransformer()
    # A live UI delta that should be discarded by reset.
    image_view = _FakeImageView(TransformAdjustment(translation_x=5.0))

    self_obj = _make_self(transformer, project, image_view)
    self_obj.reset_adjustment()

    # The stored correction must be re-applied to the transformer (not cleared).
    assert transformer.adjustment is not None
    assert not transformer.adjustment.is_identity()
    assert transformer.adjustment.to_dict() == stored.to_dict()
    # The live delta is collapsed to identity.
    assert image_view.current_adjustment.is_identity()
    assert self_obj._refreshed is True


def test_reset_clears_adjustment_for_non_drone():
    """Reset leaves the transformer cleared when no stored correction applies."""
    project = Project(transform_method="affine")
    project.transform_adjustment = None

    transformer = _RecordingTransformer()
    transformer.set_adjustment(TransformAdjustment(translation_x=9.0))
    image_view = _FakeImageView(TransformAdjustment(translation_x=9.0))

    self_obj = _make_self(transformer, project, image_view)
    self_obj.reset_adjustment()

    # Nothing to restore: transformer stays cleared.
    assert transformer.adjustment is None

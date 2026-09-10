"""Regression test: live adjustment edits must compose onto the drone base.

on_adjustment_changed must apply the live delta on top of the stored drone-assisted
base (not replace it), otherwise the first keypress drops the base correction and the
geometry jumps — perceived as a shift rather than a stretch.
"""

import os
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from orbit.gui.main_window import MainWindow
from orbit_core.models.project import Project
from orbit_core.utils.coordinate_transform import TransformAdjustment

BASE = TransformAdjustment(
    translation_x=-6.5, translation_y=42.0, rotation=-2.55,
    scale_x=1.003, scale_y=0.86, pivot_x=1920.0, pivot_y=1080.0,
)


class _RecordingTransformer:
    def __init__(self):
        self.adjustment = None

    def set_adjustment(self, adj):
        self.adjustment = adj


def _make_self(method, current_adjustment):
    project = Project(transform_method=method)
    project.transform_adjustment = BASE.to_dict()
    obj = types.SimpleNamespace(
        project=project,
        image_view=types.SimpleNamespace(
            current_adjustment=current_adjustment,
            update_all_from_geo_coords=lambda t: None,
        ),
        _cached_transformer=_RecordingTransformer(),
        adjustment_panel=types.SimpleNamespace(update_display=lambda *a, **k: None),
    )
    for name in ("on_adjustment_changed", "_apply_active_adjustment",
                 "_compose_with_drone_base"):
        setattr(obj, name, types.MethodType(getattr(MainWindow, name), obj))
    return obj


def test_live_edit_composes_onto_drone_base():
    """A live stretch delta must be composed with the base, not replace it."""
    delta = TransformAdjustment(scale_y=1.005, pivot_x=1920.0, pivot_y=1080.0)
    s = _make_self("drone_assisted", delta)
    s.on_adjustment_changed(delta)

    applied = s._cached_transformer.adjustment
    import numpy as np
    expected = delta.get_adjustment_matrix() @ BASE.get_adjustment_matrix()
    # The applied adjustment must equal base composed with delta (not the bare delta).
    assert np.allclose(applied.get_adjustment_matrix(), expected, atol=1e-6)
    assert not np.allclose(applied.get_adjustment_matrix(),
                           delta.get_adjustment_matrix(), atol=1e-6)


def test_identity_edit_keeps_drone_base():
    """An identity delta must leave the stored base applied."""
    s = _make_self("drone_assisted", TransformAdjustment(pivot_x=1920.0, pivot_y=1080.0))
    s.on_adjustment_changed(s.image_view.current_adjustment)
    assert s._cached_transformer.adjustment.to_dict() == BASE.to_dict()

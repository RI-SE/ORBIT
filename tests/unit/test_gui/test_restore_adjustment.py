"""Regression test: drone-assisted adjustment must not be applied twice.

On load the stored drone-assisted adjustment is the permanent base. It must
not also be placed into image_view.current_adjustment, or _apply_active_adjustment
would later compose the base on top of itself (double transform — observed when
returning from aerial view).
"""

import os
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from orbit.gui.main_window import MainWindow
from orbit.models.project import Project
from orbit.utils.coordinate_transform import TransformAdjustment

A = TransformAdjustment(
    translation_x=-6.5, translation_y=42.0, rotation=-2.55,
    scale_x=1.003, scale_y=0.86, pivot_x=1920.0, pivot_y=1080.0,
)


class _RecordingTransformer:
    def __init__(self):
        self.adjustment = None

    def set_adjustment(self, adj):
        self.adjustment = adj

    def clear_adjustment(self):
        self.adjustment = None


class _FakeImageView:
    def __init__(self):
        self.current_adjustment = None
        self.updated_with = None

    def update_all_from_geo_coords(self, transformer):
        self.updated_with = transformer


def _make_self(method):
    project = Project(transform_method=method)
    project.transform_adjustment = A.to_dict()
    obj = types.SimpleNamespace(
        project=project,
        image_view=_FakeImageView(),
        _cached_transformer=_RecordingTransformer(),
        adjustment_panel=types.SimpleNamespace(update_display=lambda *a, **k: None),
    )
    obj._create_transformer = lambda **k: _RecordingTransformer()
    for name in ("_restore_adjustment_from_project", "_apply_active_adjustment",
                 "_compose_with_drone_base"):
        setattr(obj, name, types.MethodType(getattr(MainWindow, name), obj))
    return obj


def test_drone_restore_keeps_current_adjustment_identity():
    """Drone-assisted: restore must not push the stored adjustment into the live delta."""
    s = _make_self("drone_assisted")
    s._restore_adjustment_from_project()

    # Live delta stays empty; the base is on the transformer (single application).
    assert s.image_view.current_adjustment is None
    assert s._cached_transformer.adjustment.to_dict() == A.to_dict()

    # A subsequent _apply_active_adjustment (as on an aerial switch) must apply the
    # stored base ONCE, not compose it with a live copy of itself.
    fresh = _RecordingTransformer()
    s._apply_active_adjustment(fresh)
    assert fresh.adjustment.to_dict() == A.to_dict()


def test_non_drone_restore_loads_live_adjustment():
    """Homography/affine: the stored value is an unbaked live adjustment to restore."""
    s = _make_self("homography")
    s._restore_adjustment_from_project()
    assert s.image_view.current_adjustment is not None
    assert s.image_view.current_adjustment.to_dict() == A.to_dict()

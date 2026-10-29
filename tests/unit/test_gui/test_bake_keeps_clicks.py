"""Baking an alignment adjustment keeps the original clicks and records the adjustment."""

from types import SimpleNamespace

import numpy as np

from orbit.gui.main_window import MainWindow
from orbit_core.models.project import ControlPoint, Project
from orbit_core.utils.coordinate_transform import TransformAdjustment


def _project():
    project = Project()
    project.control_points = [ControlPoint(pixel_x=100.0, pixel_y=200.0, longitude=12.0, latitude=57.0),
                              ControlPoint(pixel_x=300.0, pixel_y=50.0, longitude=12.1, latitude=57.1)]
    return project


def test_bake_moves_pixels_but_keeps_clicks_and_history():
    project = _project()
    window = SimpleNamespace(project=project)
    first = TransformAdjustment(translation_x=5.0, translation_y=-3.0)
    second = TransformAdjustment(translation_x=1.0)

    MainWindow._bake_into_control_points(window, first)
    MainWindow._bake_into_control_points(window, second)

    cp = project.control_points[0]
    assert cp.pixel_clicked == [100.0, 200.0]
    assert (cp.pixel_x, cp.pixel_y) == (106.0, 197.0)
    assert len(project.baked_adjustments) == 2
    np.testing.assert_allclose(project.baked_adjustments[0]["matrix"], first.get_adjustment_matrix())


def test_bake_record_survives_save_and_load():
    project = _project()
    MainWindow._bake_into_control_points(SimpleNamespace(project=project), TransformAdjustment(rotation=0.5))
    restored = Project.from_dict(project.to_dict())
    assert restored.baked_adjustments == project.baked_adjustments
    assert restored.control_points[1].pixel_clicked == [300.0, 50.0]

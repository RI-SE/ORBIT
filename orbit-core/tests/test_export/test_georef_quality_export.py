"""Georef 1.2 quality keys (scenario-uncertainty `georef` profile) written by export_georeferencing."""

import json

import numpy as np
import pytest

from orbit_core.export.georef_export import export_georeferencing
from orbit_core.models.project import ControlPoint, Project
from orbit_core.utils.coordinate_transform import HomographyTransformer, TransformAdjustment

UTM = "+proj=utm +zone=33 +north +datum=WGS84 +units=m"
PIXELS = [(100, 100), (900, 120), (120, 700), (880, 690), (500, 400), (300, 600), (700, 250), (450, 150),
          (250, 300), (650, 550), (800, 400)]
DEG = 1e-5
VALIDATION = {8, 9, 10}


def _project(baked_shift=None):
    rng = np.random.default_rng(5)
    project = Project()
    for i, (u, v) in enumerate(PIXELS):
        clicked = [u + rng.normal(0, 1.0), v + rng.normal(0, 1.0)]
        project.control_points.append(ControlPoint(
            pixel_x=clicked[0], pixel_y=clicked[1], longitude=12.0 + u * DEG, latitude=57.7 - v * DEG,
            name=f"p{i}", is_validation=i in VALIDATION, altitude=70.0 + 0.3 * np.sin(i), sigma_h_m=0.002,
            sigma_v_m=0.004, point_type="Check Point", pick_zoom=4.0, pixel_clicked=list(clicked)))
    if baked_shift:
        adjustment = TransformAdjustment(translation_x=baked_shift)
        for cp in project.control_points:
            cp.pixel_x, cp.pixel_y = adjustment.apply_to_point(cp.pixel_x, cp.pixel_y)
        project.baked_adjustments.append({"matrix": adjustment.get_adjustment_matrix().tolist(),
                                          "params": adjustment.to_dict()})
    return project


def _export(tmp_path, project):
    transformer = HomographyTransformer(project.control_points, export_proj_string=UTM)
    path = tmp_path / "georef.json"
    assert export_georeferencing(project, path, transformer, (1000, 800))
    return json.loads(path.read_text())


def test_per_point_quality(tmp_path):
    data = _export(tmp_path, _project())
    cp = data["control_points"][0]
    assert cp["sigma_h_m"] == 0.002 and cp["point_type"] == "Check Point"
    assert cp["sigma_px_quantisation"] == pytest.approx(1 / (4.0 * np.sqrt(12)), abs=1e-4)
    assert len(cp["residual_m"]) == 2 and len(cp["residual_px"]) == 2
    assert "quality_error" not in data


def test_top_level_quality(tmp_path):
    data = _export(tmp_path, _project())
    assert data["quality_spec"] == "scenario-uncertainty/0.1"
    assert data["transform_source"] == "homography" and data["transform_method"] == "homography"
    assert data["leave_one_out"]["value"] > 0 and data["leave_one_out"]["n"] == len(PIXELS) - len(VALIDATION)
    assert set(data["validation"]) == {"rms", "datum", "internal"}
    assert data["terrain"]["residual"]["value"] == pytest.approx(0.3 * np.std(np.sin(range(len(PIXELS)))), rel=0.05)
    assert data["adjustment"]["method"] == "none"


def test_baked_adjustment_is_reported(tmp_path):
    data = _export(tmp_path, _project(baked_shift=40.0))
    adjustment = data["adjustment"]
    assert adjustment["method"] == "baked"
    np.testing.assert_allclose(np.array(adjustment["A"])[0, 2], 40.0)
    # 40 px at ~0.6 m/px (1e-5 deg longitude at 57.7 N) moves the ground by about 24 m
    assert adjustment["magnitude"]["value"] == pytest.approx(40 * 0.6, rel=0.1)
    assert adjustment["H_fit"] != data["transformation_matrix"]


def test_old_project_without_clicks_reports_unknown(tmp_path):
    project = _project()
    for cp in project.control_points:
        cp.pixel_clicked = None
    assert _export(tmp_path, project)["adjustment"]["method"] == "unknown"

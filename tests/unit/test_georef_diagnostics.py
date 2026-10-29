"""tools/georef_diagnostics.py: exact-fit and weak-geometry warnings, datum split."""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

_TOOL = Path(__file__).resolve().parents[2] / "tools" / "georef_diagnostics.py"
_spec = importlib.util.spec_from_file_location("georef_diagnostics", _TOOL)
diagnostics = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(diagnostics)

DEG_PER_PX = 1e-5
PIXELS = [(100, 100), (900, 120), (120, 700), (880, 690), (500, 400), (300, 600), (700, 250), (450, 150), (250, 300)]


def _georef(tmp_path, offsets=None, validation=()):
    offsets = offsets or {}
    points = []
    for i, (u, v) in enumerate(PIXELS):
        du, dv = offsets.get(i, (0.0, 0.0))
        points.append({"pixel_x": u + du, "pixel_y": v + dv, "longitude": 12.0 + u * DEG_PER_PX,
                       "latitude": 57.7 - v * DEG_PER_PX, "name": f"p{i}", "is_validation": i in validation})
    path = tmp_path / "test_georef.json"
    path.write_text(json.dumps({"control_points": points,
                                "proj_string": "+proj=utm +zone=33 +north +datum=WGS84 +units=m"}))
    return path


def test_exact_fit_is_flagged(tmp_path):
    # Pixels recomputed from geo through the fitted homography, as ORBIT's aerial-view round trip once did
    path = _georef(tmp_path, {0: (3.0, -2.0)})
    data = json.loads(path.read_text())
    points = diagnostics.load_control_points(data)
    fitted = diagnostics.HomographyTransformer(points, export_proj_string=data["proj_string"])
    for cp in data["control_points"]:
        cp["pixel_x"], cp["pixel_y"] = fitted.geo_to_pixel(cp["longitude"], cp["latitude"])
    path.write_text(json.dumps(data))
    result = diagnostics.diagnose(path)
    assert any("fits exactly" in w for w in result["warnings"])


def test_clicked_points_are_not_flagged_and_loo_exceeds_fit(tmp_path):
    rng = np.random.default_rng(0)
    offsets = {i: tuple(rng.normal(0, 1.5, 2)) for i in range(len(PIXELS))}
    result = diagnostics.diagnose(_georef(tmp_path, offsets))
    assert not any("fits exactly" in w for w in result["warnings"])
    assert result["loo_rms_m"] > result["fit_rms_m"] > 0


def test_similarity_split_separates_common_shift():
    true = np.array([[0.0, 0.0], [100.0, 0.0], [0.0, 80.0], [100.0, 80.0]])
    split = diagnostics.similarity_split(true + [0.5, -0.3], true)
    assert split["shift_m"] == pytest.approx([0.5, -0.3], abs=1e-6)
    assert split["rotation_deg"] == pytest.approx(0.0, abs=1e-6)
    assert split["internal_rms_m"] == pytest.approx(0.0, abs=1e-6)


def test_matrix_in_another_frame_is_flagged(tmp_path):
    path = _georef(tmp_path)
    data = json.loads(path.read_text())
    points = diagnostics.load_control_points(data)
    fitted = diagnostics.HomographyTransformer(points, export_proj_string=data["proj_string"])
    matrix = np.array(fitted.transform_matrix)
    # Shift the export to a local frame 400 km away, as drone-assisted exports do
    data["transformation_matrix"] = (np.array([[1, 0, -4e5], [0, 1, -6.4e6], [0, 0, 1]]) @ matrix).tolist()
    path.write_text(json.dumps(data))
    result = diagnostics.diagnose(path)
    assert any("not in the proj_string frame" in w for w in result["warnings"])

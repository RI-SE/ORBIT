"""Georef quality summary in the export's provenance sidecar."""

import json
from datetime import datetime, timezone

import pytest

from orbit_core.utils.georef_quality import provenance_summary
from orbit_core.utils.provenance import is_dataprov_available, prov_path_for, record_export


def _georef(magnitude=2.5, internal=0.6, terrain=0.45, method="baked"):
    q = {"unit": "m", "stat": "rms", "level": "image", "basis": "derived"}
    return {"leave_one_out": {"value": internal, **q},
            "adjustment": {"method": method,
                           "magnitude": None if magnitude is None else {"value": magnitude, **q, "stat": "max"}},
            "terrain": {"residual": {"value": terrain, **q, "stat": "sigma"}},
            "reprojection_error": {"rmse_meters": 0.3}, "control_points": [{"is_validation": False}] * 6}


def test_summary_and_warnings():
    summary = provenance_summary(_georef())
    props = summary["custom_properties"]
    assert props["activity:su:georef_internal_error"]["value"] == 0.6
    assert props["activity:su:adjustment_magnitude"]["value"] == 2.5
    codes = [line.split("]")[0] for line in summary["warning_lines"]]
    assert codes == ["[su:adjustment_exceeds_validation", "[su:nonplanar_terrain"]


def test_unknown_adjustment_and_computed_points():
    data = _georef(magnitude=None, method="unknown", terrain=0.1)
    data["reprojection_error"]["rmse_meters"] = 0.0002
    codes = [line.split("]")[0] for line in provenance_summary(data)["warning_lines"]]
    assert codes == ["[su:adjustment_unknown", "[su:control_points_computed"]


@pytest.mark.skipif(not is_dataprov_available(), reason="needs dataprov")
def test_export_sidecar_carries_the_summary(tmp_path):
    output = tmp_path / "x_georef.json"
    output.write_text("{}")
    assert record_export(output, None, "georeferencing parameter export", "JSON", datetime.now(timezone.utc),
                         quality=provenance_summary(_georef()))
    prov = json.loads(prov_path_for(output).read_text())
    assert prov["prefix"]["su"].startswith("https://das-rise.github.io/scenario-uncertainty")
    activity = next(iter(prov["activity"].values()))
    assert "[su:nonplanar_terrain]" in activity["dataprov:warnings"]
    assert activity["su:adjustment_magnitude"]["value"] == 2.5
    assert [g.get("prov:role") for g in prov["wasGeneratedBy"].values()] == ["dataprov:PrimaryOutput"]

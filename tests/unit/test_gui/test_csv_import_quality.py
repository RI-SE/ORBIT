"""CSV import keeps RTK altitude, standard deviations and point type."""

from pathlib import Path

import pytest

from orbit.gui.dialogs.csv_import_dialog import parse_csv_file

SURVEY_CSV = Path(__file__).resolve().parents[3] / "examples" / "SaroRound" / "SaroRound_coords_visualmarkers.csv"


@pytest.mark.skipif(not SURVEY_CSV.exists(), reason="example RTK CSV not available")
def test_survey_export_columns_are_kept():
    points, error = parse_csv_file(SURVEY_CSV)
    assert not error
    first = next(p for p in points if p.point_name == "lamppost_1a")
    assert first.altitude == pytest.approx(75.2419, abs=1e-3)
    assert first.sigma_h_m == pytest.approx(0.00199)
    assert first.sigma_v_m == pytest.approx(0.00346, abs=1e-5)
    assert first.point_type == "Check Point"


def test_missing_and_non_numeric_values_are_unknown(tmp_path):
    csv = tmp_path / "points.csv"
    csv.write_text("point_name,latitude,longitude,horiz SD\np1,57.0,12.0,/\np2,57.1,12.1,0.02\n")
    points, error = parse_csv_file(csv)
    assert not error
    assert [p.sigma_h_m for p in points] == [None, 0.02]
    assert all(p.sigma_v_m is None and p.altitude is None for p in points)

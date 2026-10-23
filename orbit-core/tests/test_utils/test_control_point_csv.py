"""Attaching survey data (altitude, SDs, point type) to existing control points by name."""

from orbit_core.utils.control_point_csv import CSVControlPoint, attach_survey_data, parse_csv_file


def _survey(name, lat=57.0, lon=12.0, altitude=70.0, **extra):
    return CSVControlPoint(row_number=1, point_name=name, latitude=lat, longitude=lon, altitude=altitude, **extra)


def _cp(name, lat=57.0, lon=12.0, **extra):
    return {"pixel_x": 1.0, "pixel_y": 2.0, "latitude": lat, "longitude": lon, "name": name, **extra}


def test_attach_by_name_and_report():
    points = [_cp(" Lamppost_1 "), _cp("sign_2", altitude=10.0), _cp("far", lat=57.001), _cp("missing")]
    survey = [_survey("lamppost_1", sigma_h_m=0.002, point_type="Check Point"), _survey("sign_2", altitude=71.0),
              _survey("far")]
    report = attach_survey_data(points, survey)
    assert points[0]["altitude"] == 70.0 and points[0]["sigma_h_m"] == 0.002
    assert points[0]["point_type"] == "Check Point"
    assert points[1]["altitude"] == 10.0  # kept: already set
    assert "altitude" not in points[2]  # 111 m apart: a different point with the same name
    assert report == {"updated": ["Lamppost_1"], "unchanged": ["sign_2"], "unmatched": ["missing"],
                      "too_far": ["far"], "duplicate": []}
    attach_survey_data(points, survey, overwrite=True)
    assert points[1]["altitude"] == 71.0


def test_duplicate_names_are_not_guessed():
    points = [_cp("p1")]
    report = attach_survey_data(points, [_survey("p1", altitude=1.0), _survey("P1", altitude=2.0)])
    assert report["duplicate"] == ["p1"] and "altitude" not in points[0]


def test_parse_rtk_export(tmp_path):
    csv = tmp_path / "rtk.csv"
    csv.write_text("point_name,latitude,longitude,altitude,horizontal SD,vertical SD,point type\n"
                   "a,57.1,12.1,72.4,0.002,0.004,Check Point\nb,57.2,12.2,/,/,/,\n")
    points, error = parse_csv_file(csv)
    assert not error and points[0].altitude == 72.4 and points[0].sigma_v_m == 0.004
    assert points[1].status == "pending" and points[1].altitude is None  # "/" = not surveyed, point kept

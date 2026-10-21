"""Optional quality fields of ControlPoint: round trip, and old files unchanged."""

from orbit_core.models.project import ControlPoint


def test_quality_fields_round_trip():
    cp = ControlPoint(pixel_x=1.5, pixel_y=2.5, longitude=12.0, latitude=57.0, name="lamppost_1a",
                      altitude=75.24, sigma_h_m=0.002, sigma_v_m=0.0035, point_type="Check Point", pick_zoom=4.0)
    assert ControlPoint.from_dict(cp.to_dict()) == cp


def test_old_points_load_as_unknown_and_save_unchanged():
    old = {"pixel_x": 1.0, "pixel_y": 2.0, "longitude": 12.0, "latitude": 57.0, "name": "p", "is_validation": False}
    cp = ControlPoint.from_dict(old)
    assert cp.altitude is None and cp.sigma_h_m is None and cp.pick_zoom is None
    assert cp.to_dict() == old

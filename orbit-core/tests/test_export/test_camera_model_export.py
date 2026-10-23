"""Optional camera model over terrain (G11) in the georef export."""

import json
import math

import numpy as np
import pyproj

from orbit_core.export.georef_export import export_georeferencing
from orbit_core.models.project import ControlPoint, Project
from orbit_core.utils.coordinate_transform import HomographyTransformer

UTM = "+proj=utm +zone=33 +north +datum=WGS84 +units=m"
IMAGE = (3840, 2160)
OFFSET = np.array([320700.0, 6375260.0])


def _oblique_project():
    """Camera 100 m up, 30° from nadir, looking north; control points on a domed site."""
    el = math.radians(30.0)
    z_axis = np.array([0.0, math.sin(el), -math.cos(el)])
    x_axis = np.array([1.0, 0.0, 0.0])
    R = np.stack([x_axis, np.cross(z_axis, x_axis), z_axis])
    C = np.array([0.0, -100.0 * math.tan(el), 100.0])
    K = np.array([[2600.0, 0, IMAGE[0] / 2], [0, 2600.0, IMAGE[1] / 2], [0, 0, 1.0]])
    to_geo = pyproj.Transformer.from_crs(UTM, "EPSG:4326", always_xy=True)
    rng = np.random.default_rng(3)
    project = Project()
    for i in range(14):
        e, n = rng.uniform(-60, 60), rng.uniform(-40, 70)
        z = 1.0 - 4e-4 * (e * e + n * n)
        p = K @ (R @ (np.array([e, n, z]) - C))
        lon, lat = to_geo.transform(e + OFFSET[0], n + OFFSET[1])
        project.control_points.append(ControlPoint(pixel_x=p[0] / p[2], pixel_y=p[1] / p[2], longitude=lon,
                                                   latitude=lat, name=f"p{i}", altitude=70.0 + z))
    return project


def _export(tmp_path, project, image_size):
    transformer = HomographyTransformer(project.control_points, export_proj_string=UTM)
    path = tmp_path / "georef.json"
    assert export_georeferencing(project, path, transformer, image_size)
    return json.loads(path.read_text())


def test_oblique_export_has_camera_model(tmp_path):
    data = _export(tmp_path, _oblique_project(), IMAGE)
    model = data["camera_model"]
    assert model["fit"]["rms_px"] < 1.0 and abs(model["fit"]["focal_px"] - 2600) < 30
    assert model["terrain"]["type"] == "quadratic"
    assert "homography_leave_one_out_m" in model["fit"] and data["transform_method"] == "homography"

    from orbit_georef import load_georef

    gt = load_georef(tmp_path / "georef.json")
    cp = data["control_points"][0]
    east, north, z = gt.pixel_to_ground_3d(cp["pixel_x"], cp["pixel_y"])
    assert math.dist(gt.geo_to_ground(cp["longitude"], cp["latitude"]), (east, north)) < 0.1
    assert abs(z - cp["altitude_m"]) < 0.3


def test_points_without_altitude_give_no_camera_model(tmp_path):
    project = _oblique_project()
    for cp in project.control_points:
        cp.altitude = None
    data = _export(tmp_path, project, IMAGE)
    assert "camera_model" not in data and "camera_model_error" not in data

"""Camera model over terrain, against a synthetic pinhole camera above a domed site."""

import math

import numpy as np
import pytest
from orbit_georef.camera_model import CameraModel, TerrainSurface, fit_camera_model, focal_from_homography

IMAGE = (3840, 2160)
FOCAL = 2600.0


def _terrain(east, north):
    """Dome: +1 m at the centre, about -1.3 m at 75 m (like GbgSaroRound), plus a 1.5 % slope."""
    return 1.0 - 4.1e-4 * (np.asarray(east) ** 2 + np.asarray(north) ** 2) + 0.015 * np.asarray(east)


def _camera():
    """Camera 100 m up, 30° from nadir, looking north at the origin."""
    el = math.radians(30.0)
    z_axis = np.array([0.0, math.sin(el), -math.cos(el)])
    x_axis = np.array([1.0, 0.0, 0.0])
    y_axis = np.cross(z_axis, x_axis)
    R = np.stack([x_axis, y_axis, z_axis])
    C = np.array([0.0, -100.0 * math.tan(el), 100.0])
    K = np.array([[FOCAL, 0, IMAGE[0] / 2], [0, FOCAL, IMAGE[1] / 2], [0, 0, 1.0]])
    return K, R, C


def _project(world):
    K, R, C = _camera()
    p = (K @ (R @ (world - C).T)).T
    return p[:, :2] / p[:, 2:3]


def _homography(pixels, ground):
    """Plain DLT pixel -> ground (E, N), as ORBIT fits it (altitude ignored)."""
    A = []
    for (x, y), (X, Y) in zip(pixels, ground):
        A.append([-x, -y, -1, 0, 0, 0, x * X, y * X, X])
        A.append([0, 0, 0, -x, -y, -1, x * Y, y * Y, Y])
    H = np.linalg.svd(np.array(A))[2][-1].reshape(3, 3)
    return H / H[2, 2]


def _scene(n=17, seed=0):
    rng = np.random.default_rng(seed)
    en = np.column_stack([rng.uniform(-60, 60, n), rng.uniform(-40, 70, n)])
    world = np.column_stack([en, _terrain(en[:, 0], en[:, 1])])
    pixels = _project(world)
    return world, pixels, _homography(pixels, en)


def test_focal_from_homography():
    world, pixels, H = _scene()
    flat = np.column_stack([world[:, :2], np.zeros(len(world))])
    H_flat = _homography(_project(flat), world[:, :2])
    assert focal_from_homography(np.linalg.inv(H_flat), (IMAGE[0] / 2, IMAGE[1] / 2)) == pytest.approx(FOCAL, rel=1e-3)


def test_camera_model_removes_terrain_error():
    world, pixels, H = _scene()
    model = fit_camera_model(world, pixels, H, IMAGE)
    assert model is not None and model.fit["rms_px"] < 1.0
    assert model.fit["camera_height_m"] == pytest.approx(100.0 - model.origin[2], abs=3.0)

    # Check points not used for the fit
    check_world, check_pixels, _ = _scene(n=30, seed=1)
    camera_error = [math.dist(model.pixel_to_ground(*px)[:2], w[:2]) for px, w in zip(check_pixels, check_world)]
    h_points = (H @ np.c_[check_pixels, np.ones(len(check_pixels))].T).T
    flat_error = np.linalg.norm(h_points[:, :2] / h_points[:, 2:3] - check_world[:, :2], axis=1)
    assert np.sqrt(np.mean(np.square(camera_error))) < 0.5 * np.sqrt(np.mean(np.square(flat_error)))
    assert model.fit["leave_one_out_m"] is not None

    # Round trip and serialisation
    east, north, z = model.pixel_to_ground(1900.0, 1000.0)
    assert model.ground_to_pixel(east, north) == pytest.approx((1900.0, 1000.0), abs=1e-3)
    again = CameraModel.from_dict(model.to_dict())
    assert again.pixel_to_ground(1900.0, 1000.0) == pytest.approx((east, north, z))
    assert CameraModel.from_dict({**model.to_dict(), "version": 99}) is None


def test_terrain_is_held_constant_beyond_the_points():
    points = np.array([[x, y, 0.01 * x] for x in (-10, 0, 10) for y in (-10, 0, 10)], dtype=float)
    terrain = TerrainSurface.fit(points)
    assert terrain.height(5.0, 0.0) == pytest.approx(0.05, abs=0.01)
    edge = terrain.height(terrain.radius, 0.0)
    assert terrain.height(10 * terrain.radius, 0.0) == pytest.approx(edge)


def test_too_few_points_gives_no_model():
    world, pixels, H = _scene(n=5)
    assert fit_camera_model(world, pixels, H, IMAGE) is None


def test_geotransformer_fits_saves_and_loads_camera_model(tmp_path):
    from orbit_georef import ControlPoint, GeoTransformer, load_georef, save_georef

    world, pixels, H = _scene()
    # A projected CRS in metres: here simply the scene coordinates offset into UTM 33N around Gothenburg
    proj = "+proj=utm +zone=33 +north +ellps=WGS84 +datum=WGS84 +units=m +no_defs"
    import pyproj
    to_geo = pyproj.Transformer.from_crs(proj, "EPSG:4326", always_xy=True)
    offset = np.array([320700.0, 6375260.0])
    points = []
    for (e, n, z), (u, v) in zip(world, pixels):
        lon, lat = to_geo.transform(e + offset[0], n + offset[1])
        points.append(ControlPoint(u, v, lon, lat, altitude=float(z)))
    shift = np.array([[1, 0, offset[0]], [0, 1, offset[1]], [0, 0, 1.0]])
    gt = GeoTransformer(shift @ H, np.linalg.inv(shift @ H), 12.0, 57.5, control_points=points, proj_string=proj)

    model = gt.fit_camera_model(IMAGE)
    assert model is not None and model.fit["rms_px"] < 0.1
    east, north, z = gt.pixel_to_ground_3d(*pixels[3])
    assert (east - offset[0], north - offset[1]) == pytest.approx(tuple(world[3, :2]), abs=0.05)

    path = tmp_path / "georef.json"
    save_georef(gt, path)
    loaded = load_georef(path)
    assert loaded.control_points[3].altitude == pytest.approx(world[3, 2])
    assert loaded.pixel_to_ground_3d(*pixels[3]) == pytest.approx((east, north, z))
    assert loaded.pixel_to_ground(*pixels[3]) == pytest.approx(gt.pixel_to_ground(*pixels[3]))  # homography unchanged


def test_georef_without_camera_model_still_loads(tmp_path):
    from orbit_georef import GeoTransformer, load_georef, save_georef

    gt = GeoTransformer(np.eye(3), np.eye(3), 12.0, 57.5)
    save_georef(gt, tmp_path / "g.json")
    loaded = load_georef(tmp_path / "g.json")
    assert loaded.camera_model is None
    with pytest.raises(ValueError, match="no camera model"):
        loaded.pixel_to_ground_3d(1.0, 1.0)

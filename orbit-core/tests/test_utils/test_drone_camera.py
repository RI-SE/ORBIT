"""Tests for DroneCameraModel and DroneAssistedTransformer."""

import math

import numpy as np
import pytest
from orbit_core.models.project import ControlPoint, DroneMetadata
from orbit_core.utils.camera_model import (
    DroneCameraModel,
    _build_projection_matrix,
    _rotation_matrix,
)
from orbit_core.utils.coordinate_transform import DroneAssistedTransformer

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def nadir_metadata():
    """Pure nadir camera (pitch=-90), facing North (yaw=0), 100 m altitude."""
    return DroneMetadata(
        latitude=57.0,
        longitude=12.0,
        alt_agl=100.0,
        gimbal_yaw=0.0,
        gimbal_pitch=-90.0,
        gimbal_roll=0.0,
        hfov_deg=90.0,  # 45° from centre → f = W/2
    )


@pytest.fixture
def tilted_metadata():
    """South-facing camera, 10° off-nadir, 120 m altitude."""
    return DroneMetadata(
        latitude=57.73975,
        longitude=12.89942,
        alt_agl=120.0,
        gimbal_yaw=180.0,   # facing South
        gimbal_pitch=-80.0,  # 10° off nadir
        gimbal_roll=0.0,
        hfov_deg=71.5,
    )


# ---------------------------------------------------------------------------
# _rotation_matrix
# ---------------------------------------------------------------------------

class TestRotationMatrix:
    def test_nadir_identity_columns(self):
        """At pure nadir / north-facing, Z-axis (forward) should point straight down [0,0,-1]."""
        R = _rotation_matrix(yaw_deg=0.0, pitch_deg=-90.0, roll_deg=0.0)
        np.testing.assert_allclose(R[2], [0.0, 0.0, -1.0], atol=1e-10)

    def test_orthonormal(self):
        """Rotation matrix must be orthonormal (R @ R.T == I)."""
        R = _rotation_matrix(yaw_deg=45.0, pitch_deg=-77.7, roll_deg=2.0)
        np.testing.assert_allclose(R @ R.T, np.eye(3), atol=1e-10)

    def test_determinant_one(self):
        """det(R) must be +1 (proper rotation, not reflection)."""
        R = _rotation_matrix(yaw_deg=-133.6, pitch_deg=-77.7, roll_deg=0.0)
        assert abs(np.linalg.det(R) - 1.0) < 1e-10


# ---------------------------------------------------------------------------
# _build_projection_matrix
# ---------------------------------------------------------------------------

class TestBuildProjectionMatrix:
    def test_nadir_centre_projects_to_image_centre(self):
        """Ground nadir [E=0, N=0] must project to image centre for pure nadir camera."""
        W, H = 4000, 3000
        cx, cy = W / 2.0, H / 2.0
        f = cx  # for hfov=90° tan(45°)=1 → f = cx
        M = _build_projection_matrix(0.0, -90.0, 0.0, 100.0, f, cx, cy)
        g = np.array([0.0, 0.0, 1.0])  # ENU ground point at nadir
        p = M @ g
        u, v = p[0] / p[2], p[1] / p[2]
        np.testing.assert_allclose([u, v], [cx, cy], atol=0.5)

    def test_invertibility(self):
        """M must be invertible."""
        M = _build_projection_matrix(226.4, -77.7, 0.0, 120.0, 2664.0, 1920.0, 1080.0)
        det = np.linalg.det(M)
        assert abs(det) > 1e-6


# ---------------------------------------------------------------------------
# DroneCameraModel
# ---------------------------------------------------------------------------

class TestDroneCameraModel:
    def test_focal_from_hfov(self, nadir_metadata):
        """Focal length resolves from hfov_deg without GCPs."""
        model = DroneCameraModel(nadir_metadata, image_width=4000, image_height=3000)
        expected_f = 2000.0  # (4000/2) / tan(45°)
        assert abs(model.focal_length_px - expected_f) < 1.0

    def test_raises_without_hfov_or_gcps(self):
        md = DroneMetadata(
            latitude=57.0, longitude=12.0, alt_agl=100.0,
            gimbal_yaw=0.0, gimbal_pitch=-90.0,
        )
        with pytest.raises(ValueError, match="focal length"):
            DroneCameraModel(md, image_width=1920, image_height=1080)

    def test_pixel_to_enu_roundtrip(self, nadir_metadata):
        """pixel_to_enu → enu_to_pixel should reconstruct original pixel within 0.5 px."""
        model = DroneCameraModel(nadir_metadata, image_width=4000, image_height=3000)
        test_pixels = [(1000, 800), (3500, 2500), (200, 200)]
        for u, v in test_pixels:
            east, north = model.pixel_to_enu(u, v)
            u2, v2 = model.enu_to_pixel(east, north)
            np.testing.assert_allclose([u2, v2], [u, v], atol=0.5,
                                       err_msg=f"Roundtrip failed for ({u},{v})")

    def test_nadir_ground_track_at_image_centre(self, nadir_metadata):
        """For pure-nadir camera, image centre must map to ENU origin (0, 0)."""
        model = DroneCameraModel(nadir_metadata, image_width=4000, image_height=3000)
        east, north = model.pixel_to_enu(2000.0, 1500.0)
        np.testing.assert_allclose([east, north], [0.0, 0.0], atol=1.0)

    def test_gcp_reprojection(self, tilted_metadata):
        """With hfov_deg given, nadir (ENU origin) projects to a finite pixel location."""
        model = DroneCameraModel(tilted_metadata, image_width=3840, image_height=2160)
        u, v = model.enu_to_pixel(0.0, 0.0)
        assert math.isfinite(u) and math.isfinite(v)

    def test_focal_solved_from_gcps(self):
        """When hfov_deg is absent, focal length should be solved from GCPs."""
        md = DroneMetadata(
            latitude=57.0, longitude=12.0, alt_agl=100.0,
            gimbal_yaw=0.0, gimbal_pitch=-90.0,
        )
        # Build a real model with known f to generate GCPs
        f_true = 2000.0
        W, H = 4000, 3000
        from orbit_core.utils.camera_model import _build_projection_matrix
        M = _build_projection_matrix(0.0, -90.0, 0.0, 100.0, f_true, W/2, H/2)
        M_inv = np.linalg.inv(M)

        R_earth = 6_371_000.0
        cos_lat = math.cos(math.radians(57.0))

        def enu_to_latlon(east, north):
            lat = md.latitude + math.degrees(north / R_earth)
            lon = md.longitude + math.degrees(east / (R_earth * cos_lat))
            return lat, lon

        gcps = []
        for (pu, pv) in [(500, 500), (3500, 500), (500, 2500), (3500, 2500)]:
            g = M_inv @ np.array([pu, pv, 1.0])
            e, n = g[0] / g[2], g[1] / g[2]
            lat, lon = enu_to_latlon(e, n)
            gcps.append(ControlPoint(name="g", pixel_x=pu, pixel_y=pv, latitude=lat, longitude=lon))

        model = DroneCameraModel(md, image_width=W, image_height=H, control_points=gcps)
        assert abs(model.focal_length_px - f_true) / f_true < 0.05  # within 5%

    def test_estimate_heading_from_gcps_returns_float(self, nadir_metadata):
        """estimate_heading_from_gcps returns (yaw_float, rmse_float) without error."""
        model = DroneCameraModel(nadir_metadata, image_width=4000, image_height=3000)
        # Need at least 2 GCPs
        cp1 = ControlPoint(name="a", pixel_x=1000.0, pixel_y=1000.0,
                           latitude=57.001, longitude=12.0)
        cp2 = ControlPoint(name="b", pixel_x=3000.0, pixel_y=2000.0,
                           latitude=57.0, longitude=12.001)
        yaw, rmse = model.estimate_heading_from_gcps([cp1, cp2])
        assert isinstance(yaw, float) and math.isfinite(yaw)
        assert isinstance(rmse, float) and rmse >= 0.0


# ---------------------------------------------------------------------------
# DroneAssistedTransformer
# ---------------------------------------------------------------------------

class TestDroneAssistedTransformer:
    def _make_transformer(self, metadata, gcps=None):
        return DroneAssistedTransformer(
            metadata=metadata,
            control_points=gcps or [],
            image_width=4000,
            image_height=3000,
        )

    def test_reference_point_is_drone_nadir(self, nadir_metadata):
        """Reference lat/lon should equal drone nadir, not CP centroid."""
        tr = self._make_transformer(nadir_metadata)
        assert tr.reference_lat == nadir_metadata.latitude
        assert tr.reference_lon == nadir_metadata.longitude

    def test_pixel_to_geo_roundtrip(self, nadir_metadata):
        """pixel_to_geo → geo_to_pixel roundtrip within 0.5 px."""
        tr = self._make_transformer(nadir_metadata)
        for u, v in [(500, 500), (2000, 1500), (3800, 2800)]:
            lon, lat = tr.pixel_to_geo(u, v)
            u2, v2 = tr.geo_to_pixel(lon, lat)
            np.testing.assert_allclose([u2, v2], [u, v], atol=0.5,
                                       err_msg=f"Roundtrip failed for ({u},{v})")

    def test_image_centre_near_drone_nadir(self, nadir_metadata):
        """For pure-nadir camera, image centre should be close to drone lat/lon."""
        tr = self._make_transformer(nadir_metadata)
        lon, lat = tr.pixel_to_geo(2000.0, 1500.0)
        assert abs(lat - nadir_metadata.latitude) < 0.001
        assert abs(lon - nadir_metadata.longitude) < 0.001

    def test_get_scale_factor_positive(self, nadir_metadata):
        """get_scale_factor should return positive x/y metres-per-pixel values."""
        tr = self._make_transformer(nadir_metadata)
        sx, sy = tr.get_scale_factor()
        assert sx > 0
        assert sy > 0

    def test_transform_matrix_shape(self, nadir_metadata):
        """transform_matrix and inverse_matrix must be 3×3."""
        tr = self._make_transformer(nadir_metadata)
        assert tr.transform_matrix.shape == (3, 3)
        assert tr.inverse_matrix.shape == (3, 3)

    def test_with_gcps_reprojection_error(self):
        """With consistent synthetic GCPs, reprojection error should be near zero."""
        md = DroneMetadata(
            latitude=57.0, longitude=12.0, alt_agl=100.0,
            gimbal_yaw=0.0, gimbal_pitch=-90.0, hfov_deg=90.0,
        )
        # Generate GCPs consistent with the camera model
        f = 2000.0
        W, H = 4000, 3000
        M = _build_projection_matrix(0.0, -90.0, 0.0, 100.0, f, W/2, H/2)
        M_inv = np.linalg.inv(M)
        R_earth = 6_371_000.0
        cos_lat = math.cos(math.radians(57.0))

        def enu_to_latlon(e, n):
            return (
                md.latitude + math.degrees(n / R_earth),
                md.longitude + math.degrees(e / (R_earth * cos_lat)),
            )

        gcps = []
        for pu, pv in [(500, 400), (3500, 400), (500, 2600), (3500, 2600), (2000, 1500)]:
            g = M_inv @ np.array([pu, pv, 1.0])
            e, n = g[0] / g[2], g[1] / g[2]
            lat, lon = enu_to_latlon(e, n)
            gcps.append(ControlPoint(name="g", pixel_x=pu, pixel_y=pv,
                                     latitude=lat, longitude=lon))

        tr = DroneAssistedTransformer(metadata=md, control_points=gcps,
                                      image_width=W, image_height=H)
        assert tr.reprojection_error is not None
        assert tr.reprojection_error['rmse_pixels'] < 1.0


# ---------------------------------------------------------------------------
# DroneMetadata.from_video_stats
# ---------------------------------------------------------------------------

class TestDroneMetadataFromVideoStats:
    def _sample_stats(self, **overrides):
        stats = {
            "drone_type": "Mavic3Pro",
            "lens_type": "standard",
            "sequences": [{
                "sequence_id": 0,
                "stats": {
                    "osd": {
                        "latitude": {"mean": 57.73975, "std": 0.0},
                        "longitude": {"mean": 12.89942, "std": 0.0},
                        "height_agl": {"mean": 119.92, "std": 0.5},
                    },
                    "gimbal": {
                        "yaw": {"mean": -133.6, "std": 0.0},
                        "pitch": {"mean": -77.7, "std": 0.0},
                        "roll": {"mean": 0.0, "std": 0.0},
                    },
                },
            }],
        }
        stats.update(overrides)
        return stats

    def test_basic_parsing(self):
        md = DroneMetadata.from_video_stats(self._sample_stats())
        assert abs(md.latitude - 57.73975) < 1e-5
        assert abs(md.longitude - 12.89942) < 1e-5
        assert abs(md.alt_agl - 119.92) < 0.01
        assert abs(md.gimbal_yaw - (-133.6)) < 0.01
        assert abs(md.gimbal_pitch - (-77.7)) < 0.01
        assert md.drone_type == "Mavic3Pro"
        assert md.lens_type == "standard"

    def test_hfov_from_camera_section(self):
        stats = self._sample_stats()
        stats["camera"] = {"hfov_deg": 71.5}
        md = DroneMetadata.from_video_stats(stats)
        assert md.hfov_deg == 71.5

    def test_no_hfov_without_camera_section(self):
        md = DroneMetadata.from_video_stats(self._sample_stats())
        assert md.hfov_deg is None

    def test_raises_on_empty_sequences(self):
        stats = self._sample_stats()
        stats["sequences"] = []
        with pytest.raises(ValueError, match="no sequences"):
            DroneMetadata.from_video_stats(stats)

    def test_roundtrip_to_from_dict(self):
        md = DroneMetadata.from_video_stats(self._sample_stats())
        md2 = DroneMetadata.from_dict(md.to_dict())
        assert md.latitude == md2.latitude
        assert md.longitude == md2.longitude
        assert md.alt_agl == md2.alt_agl
        assert md.gimbal_yaw == md2.gimbal_yaw
        assert md.drone_type == md2.drone_type

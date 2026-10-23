"""Elevation profiles from the control points' terrain (G11 step 4)."""

import math

import numpy as np
import pytest

from orbit_core.export.curve_fitting import GeometryElement, GeometryType
from orbit_core.export.opendrive_writer import OpenDriveWriter
from orbit_core.export.terrain_elevation import control_point_terrain, elevation_profile
from orbit_core.models import Project
from orbit_core.models.project import ControlPoint


class _Transformer:
    """latlon → metres: 1 m per 1e-5 degree, enough for the terrain fit."""

    _export_proj_string = None

    def latlon_to_meters(self, lat, lon):
        return ((lon - 12.0) * 1e5, (lat - 57.0) * 1e5)

    def get_scale_factor(self):
        return (0.1, 0.1)


def _terrain_height(x, y):
    return 70.0 + 0.02 * x - 1e-4 * (x * x + y * y)


def _project():
    project = Project()
    for x in (-50, 0, 50):
        for y in (-50, 0, 50):
            project.control_points.append(ControlPoint(pixel_x=0, pixel_y=0, longitude=12.0 + x * 1e-5,
                                                       latitude=57.0 + y * 1e-5, altitude=_terrain_height(x, y)))
    return project


def _evaluate(records, s):
    s0, a, b, c, d = max((r for r in records if r[0] <= s), key=lambda r: r[0])
    ds = s - s0
    return a + b * ds + c * ds ** 2 + d * ds ** 3


def test_profile_follows_the_terrain_along_a_line():
    terrain = control_point_terrain(_project(), _Transformer())
    line = GeometryElement(GeometryType.LINE, (-40.0, -10.0), math.radians(20), 80.0)
    records = elevation_profile([line], terrain)
    assert records[0][0] == 0.0 and len(records) == 8
    for s in (0.0, 13.0, 47.5, 79.0):
        x, y = -40.0 + s * math.cos(math.radians(20)), -10.0 + s * math.sin(math.radians(20))
        assert _evaluate(records, s) == pytest.approx(float(terrain.height(x, y)), abs=0.01)
    assert float(terrain.height(0.0, 0.0)) == pytest.approx(_terrain_height(0, 0), abs=0.05)


def test_writer_uses_terrain_only_when_asked():
    project = _project()
    line = GeometryElement(GeometryType.LINE, (0.0, 0.0), 0.0, 30.0)
    assert OpenDriveWriter(project, _Transformer()).terrain is None
    writer = OpenDriveWriter(project, _Transformer(), elevation_from_terrain=True)
    profile = writer._terrain_profile([line])
    assert profile[0][1] == pytest.approx(float(np.round(_terrain_height(0, 0), 1)), abs=0.1)
    too_few = Project()
    too_few.control_points = project.control_points[:2]
    assert OpenDriveWriter(too_few, _Transformer(), elevation_from_terrain=True).terrain is None

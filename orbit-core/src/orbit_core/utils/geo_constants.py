"""
Shared geodetic constants.

Single source for the spherical-Earth approximation used across the
codebase so scale computations agree with latlon_to_meters (M4 in
development.md). Stdlib-only on purpose — importable from modules that
must not pull in numpy/pyproj.
"""

import math

EARTH_RADIUS_M = 6371000.0
METERS_PER_DEGREE = EARTH_RADIUS_M * math.pi / 180.0  # ~111195 m/deg

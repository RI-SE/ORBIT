"""OpenDRIVE elevation profiles from a terrain surface fitted to the control points' RTK altitudes (G11 step 4)."""

from typing import List, Optional, Sequence, Tuple

import numpy as np

from .reference_line_sampler import _sample_element

SAMPLE_STEP_M = 10.0  # elevation record length; the terrain surface is smooth, so this resolves it
MIN_POINTS = 3

Elevation = Tuple[float, float, float, float, float]  # s, a, b, c, d


def control_point_terrain(project, transformer):
    """TerrainSurface over the control points with altitude, in the writer's metric frame; None if too few."""
    from orbit_georef import TerrainSurface

    points = [(*transformer.latlon_to_meters(cp.latitude, cp.longitude), cp.altitude)
              for cp in project.control_points if cp.altitude is not None]
    if len(points) < MIN_POINTS:
        return None
    return TerrainSurface.fit(np.array(points, dtype=float))


def elevation_profile(geometry_elements: Sequence, terrain, step: float = SAMPLE_STEP_M) -> Optional[List[Elevation]]:
    """Cubic (Hermite) elevation records along a reference line, sampled from the terrain every `step` metres."""
    total = sum(element.length for element in geometry_elements)
    if total <= 0:
        return None
    s_values = np.unique(np.r_[np.arange(0.0, total, step), total])
    heights = np.array([float(terrain.height(*_position(geometry_elements, s))) for s in s_values])
    slopes = np.gradient(heights, s_values) if len(s_values) > 1 else np.zeros(1)
    records = []
    for i in range(len(s_values) - 1):
        h = s_values[i + 1] - s_values[i]
        dz = heights[i + 1] - heights[i]
        m0, m1 = slopes[i], slopes[i + 1]
        records.append((float(s_values[i]), float(heights[i]), float(m0),
                        float((3 * dz / h - 2 * m0 - m1) / h), float((m0 + m1 - 2 * dz / h) / h ** 2)))
    return records or [(0.0, float(heights[0]), 0.0, 0.0, 0.0)]


def _position(geometry_elements: Sequence, s: float) -> Tuple[float, float]:
    """(x, y) on the reference line at distance s."""
    for element in geometry_elements:
        if s <= element.length + 1e-9:
            x, y, _ = _sample_element(element, max(0.0, s))
            return x, y
        s -= element.length
    last = geometry_elements[-1]
    x, y, _ = _sample_element(last, last.length)
    return x, y

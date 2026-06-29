"""Reference-line sampling for all OpenDRIVE planView primitives.

Geometry math ported from ORBIT's opendrive_geometry.py (the complete
implementation: line, arc, spiral/clothoid, poly3, paramPoly3), extended to
return per-sample heading so lanes can be offset perpendicular to the road.
"""

from __future__ import annotations

import math
from typing import List, Tuple

from .model import GeomSegment, Road

Sample = Tuple[float, float, float, float]  # (s_road, x, y, hdg) in local map frame


def _to_global(seg: GeomSegment, lx: float, ly: float, lhdg: float) -> Tuple[float, float, float]:
    ch, sh = math.cos(seg.hdg), math.sin(seg.hdg)
    return (
        seg.x + lx * ch - ly * sh,
        seg.y + lx * sh + ly * ch,
        seg.hdg + lhdg,
    )


def _sample_positions(length: float, interval: float) -> List[float]:
    n = max(2, int(math.ceil(length / max(interval, 1e-6))) + 1)
    return [length * i / (n - 1) for i in range(n)]


def sample_segment(seg: GeomSegment, interval: float) -> List[Sample]:
    """Sample one geometry primitive; returns [(s_local, x, y, hdg), ...]."""
    L = seg.length
    if L <= 0:
        return [(0.0, seg.x, seg.y, seg.hdg)]

    kind = seg.kind
    p = seg.params
    ss = _sample_positions(L, interval)
    out: List[Sample] = []

    if kind == "arc" and abs(float(p.get("curvature", 0.0))) >= 1e-12:
        k = float(p["curvature"])
        r = 1.0 / k
        ch, sh = math.cos(seg.hdg), math.sin(seg.hdg)
        cx, cy = seg.x - r * sh, seg.y + r * ch
        for s in ss:
            hd = seg.hdg + s * k
            out.append((s, cx + r * math.sin(hd), cy - r * math.cos(hd), hd))

    elif kind == "spiral" and (
        abs(float(p.get("curvStart", 0.0))) >= 1e-12 or abs(float(p.get("curvEnd", 0.0))) >= 1e-12
    ):
        out = _sample_spiral(seg, ss)

    elif kind == "poly3":
        a, b, c, d = (float(p.get(k_, 0.0)) for k_ in ("a", "b", "c", "d"))
        for v in ss:
            u = a + b * v + c * v ** 2 + d * v ** 3
            du = b + 2 * c * v + 3 * d * v ** 2
            gx, gy, gh = _to_global(seg, v, u, math.atan2(du, 1.0))
            out.append((v, gx, gy, gh))

    elif kind == "paramPoly3":
        out = _sample_param_poly3(seg, ss)

    else:  # line (and degenerate arc/spiral)
        ch, sh = math.cos(seg.hdg), math.sin(seg.hdg)
        for s in ss:
            out.append((s, seg.x + s * ch, seg.y + s * sh, seg.hdg))

    return out


def _sample_spiral(seg: GeomSegment, ss: List[float]) -> List[Sample]:
    """Clothoid via forward Euler integration in the local frame."""
    L = seg.length
    k0 = float(seg.params.get("curvStart", 0.0))
    k1 = float(seg.params.get("curvEnd", 0.0))
    kd = (k1 - k0) / L
    steps = max(len(ss) * 4, int(L / 0.05) + 1)
    ds = L / steps

    out: List[Sample] = []
    lx = ly = lhdg = 0.0
    ti = 0
    for i in range(steps + 1):
        s_here = i * ds
        while ti < len(ss) and ss[ti] <= s_here + 1e-9:
            gx, gy, gh = _to_global(seg, lx, ly, lhdg)
            out.append((ss[ti], gx, gy, gh))
            ti += 1
        kappa = k0 + kd * s_here
        lx += math.cos(lhdg) * ds
        ly += math.sin(lhdg) * ds
        lhdg += kappa * ds
    while ti < len(ss):
        gx, gy, gh = _to_global(seg, lx, ly, lhdg)
        out.append((ss[ti], gx, gy, gh))
        ti += 1
    return out


def _sample_param_poly3(seg: GeomSegment, ss: List[float]) -> List[Sample]:
    p = seg.params
    aU, bU, cU, dU = (float(p.get(k_, 0.0)) for k_ in ("aU", "bU", "cU", "dU"))
    aV, bV, cV, dV = (float(p.get(k_, 0.0)) for k_ in ("aV", "bV", "cV", "dV"))
    normalized = p.get("pRange", "arcLength") == "normalized"
    L = seg.length

    out: List[Sample] = []
    for s in ss:
        pv = (s / L) if normalized else s
        u = aU + bU * pv + cU * pv ** 2 + dU * pv ** 3
        v = aV + bV * pv + cV * pv ** 2 + dV * pv ** 3
        du = bU + 2 * cU * pv + 3 * dU * pv ** 2
        dv = bV + 2 * cV * pv + 3 * dV * pv ** 2
        lhdg = math.atan2(dv, du) if (du ** 2 + dv ** 2) > 1e-12 else 0.0
        gx, gy, gh = _to_global(seg, u, v, lhdg)
        out.append((s, gx, gy, gh))
    return out


def sample_reference_line(road: Road, interval: float) -> List[Sample]:
    """Sample the whole road reference line; returns [(s_road, x, y, hdg), ...]."""
    samples: List[Sample] = []
    for seg in road.geom_segments:
        seg_samples = sample_segment(seg, interval)
        for s_local, x, y, hdg in seg_samples:
            s_road = seg.s + s_local
            if samples and abs(samples[-1][1] - x) < 1e-6 and abs(samples[-1][2] - y) < 1e-6:
                continue  # drop duplicate point at segment boundary
            samples.append((s_road, x, y, hdg))
    return samples

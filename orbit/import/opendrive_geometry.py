"""
OpenDrive geometry converter for ORBIT.

Converts OpenDrive planView geometry elements (line, arc, spiral, poly3, paramPoly3)
into polyline points suitable for ORBIT.
"""

from typing import List, Tuple, Optional
import math
import numpy as np
from scipy import integrate
from .opendrive_parser import GeometryElement, GeometryType
from orbit.models import GeometrySegment


class GeometryConverter:
    """Converts OpenDrive geometry to polyline points."""

    def __init__(self, sampling_interval: float = 1.0):
        """
        Initialize geometry converter.

        Args:
            sampling_interval: Distance between sample points in meters (for curves)
        """
        self.sampling_interval = sampling_interval

    def convert_geometry_to_polyline(
        self,
        geometry: List[GeometryElement],
        preserve_geometry: bool = True
    ) -> Tuple[List[Tuple[float, float]], List[str], Optional[List[GeometrySegment]]]:
        """
        Convert list of geometry elements to polyline points.

        Args:
            geometry: List of geometry elements from OpenDrive
            preserve_geometry: If True, also return GeometrySegment metadata for round-trip

        Returns:
            Tuple of (points, conversions, geometry_segments) where:
            - points: List of (x, y) coordinates in meters
            - conversions: List of strings describing geometry conversions
            - geometry_segments: List of GeometrySegment objects (if preserve_geometry=True)
        """
        points = []
        conversions = []
        segments = [] if preserve_geometry else None

        for geom in geometry:
            start_index = len(points)
            geom_points, conversion_msg = self._convert_single_geometry(geom)

            # Add points, avoiding duplicates at boundaries
            skip_first = False
            if points and geom_points:
                # Skip first point of new geometry if it matches last point
                if self._points_match(points[-1], geom_points[0]):
                    geom_points = geom_points[1:]
                    skip_first = True
                    # Adjust start_index since we're reusing the last point
                    start_index = len(points) - 1

            points.extend(geom_points)
            end_index = len(points) - 1

            if conversion_msg:
                conversions.append(conversion_msg)

            # Create geometry segment for round-trip preservation
            if preserve_geometry and end_index > start_index:
                segment = self._create_geometry_segment(geom, start_index, end_index)
                if segment:
                    segments.append(segment)

        return points, conversions, segments

    def _create_geometry_segment(
        self,
        geom: GeometryElement,
        start_index: int,
        end_index: int
    ) -> Optional[GeometrySegment]:
        """Create a GeometrySegment from an OpenDrive geometry element."""
        geom_type_map = {
            GeometryType.LINE: "line",
            GeometryType.ARC: "arc",
            GeometryType.SPIRAL: "spiral",
            GeometryType.POLY3: "poly3",
            GeometryType.PARAM_POLY3: "paramPoly3",
        }

        geom_type = geom_type_map.get(geom.geometry_type)
        if not geom_type:
            return None

        # Build poly_params for non-line/arc types
        poly_params = None
        curvature = None
        curvature_end = None

        if geom.geometry_type == GeometryType.ARC:
            curvature = geom.params.get('curvature', 0.0)

        elif geom.geometry_type == GeometryType.SPIRAL:
            curvature = geom.params.get('curvStart', 0.0)
            curvature_end = geom.params.get('curvEnd', 0.0)

        elif geom.geometry_type == GeometryType.POLY3:
            poly_params = {
                'a': geom.params.get('a', 0.0),
                'b': geom.params.get('b', 0.0),
                'c': geom.params.get('c', 0.0),
                'd': geom.params.get('d', 0.0),
            }

        elif geom.geometry_type == GeometryType.PARAM_POLY3:
            poly_params = {
                'aU': geom.params.get('aU', 0.0),
                'bU': geom.params.get('bU', 0.0),
                'cU': geom.params.get('cU', 0.0),
                'dU': geom.params.get('dU', 0.0),
                'aV': geom.params.get('aV', 0.0),
                'bV': geom.params.get('bV', 0.0),
                'cV': geom.params.get('cV', 0.0),
                'dV': geom.params.get('dV', 0.0),
                'pRange': geom.params.get('pRange', 'normalized'),
            }

        return GeometrySegment(
            geom_type=geom_type,
            start_index=start_index,
            end_index=end_index,
            s_start=geom.s,
            length=geom.length,
            heading=geom.hdg,
            curvature=curvature,
            curvature_end=curvature_end,
            poly_params=poly_params,
        )

    def _convert_single_geometry(
        self,
        geom: GeometryElement
    ) -> Tuple[List[Tuple[float, float]], Optional[str]]:
        """
        Convert a single geometry element to points.

        Returns:
            Tuple of (points, conversion_message)
        """
        if geom.geometry_type == GeometryType.LINE:
            return self._convert_line(geom), None

        elif geom.geometry_type == GeometryType.ARC:
            return self._convert_arc(geom), None

        elif geom.geometry_type == GeometryType.SPIRAL:
            return self._convert_spiral(geom), None

        elif geom.geometry_type == GeometryType.POLY3:
            points = self._convert_poly3(geom)
            msg = f"s={geom.s:.1f}: poly3 converted to polyline ({len(points)} samples)"
            return points, msg

        elif geom.geometry_type == GeometryType.PARAM_POLY3:
            points = self._convert_param_poly3(geom)
            msg = f"s={geom.s:.1f}: paramPoly3 converted to polyline ({len(points)} samples)"
            return points, msg

        else:
            # Unknown geometry type - just return start point
            return [(geom.x, geom.y)], f"s={geom.s:.1f}: unknown geometry type"

    def _convert_line(self, geom: GeometryElement) -> List[Tuple[float, float]]:
        """Convert line geometry to two points (start and end)."""
        start_x = geom.x
        start_y = geom.y

        # Calculate end point
        end_x = start_x + geom.length * math.cos(geom.hdg)
        end_y = start_y + geom.length * math.sin(geom.hdg)

        return [(start_x, start_y), (end_x, end_y)]

    def _convert_arc(self, geom: GeometryElement) -> List[Tuple[float, float]]:
        """Convert arc geometry to polyline points."""
        curvature = geom.params.get('curvature', 0.0)

        if abs(curvature) < 1e-9:
            # Curvature near zero - treat as line
            return self._convert_line(geom)

        # Calculate radius and center
        radius = 1.0 / curvature

        # Center of arc (perpendicular to start heading)
        center_x = geom.x - radius * math.sin(geom.hdg)
        center_y = geom.y + radius * math.cos(geom.hdg)

        # Calculate number of samples based on arc length and sampling interval
        num_samples = max(3, int(geom.length / self.sampling_interval) + 1)

        points = []
        for i in range(num_samples):
            s = (i / (num_samples - 1)) * geom.length

            # Angle swept from start
            angle = s * curvature

            # Current heading
            current_hdg = geom.hdg + angle

            # Point on arc (relative to center)
            x = center_x + radius * math.sin(current_hdg)
            y = center_y - radius * math.cos(current_hdg)

            points.append((x, y))

        return points

    def _convert_spiral(self, geom: GeometryElement) -> List[Tuple[float, float]]:
        """
        Convert spiral (clothoid) geometry to polyline points.

        Uses proper clothoid equations with Fresnel integrals.
        """
        curv_start = geom.params.get('curvStart', 0.0)
        curv_end = geom.params.get('curvEnd', 0.0)

        # If both curvatures are effectively zero, treat as line
        if abs(curv_start) < 1e-9 and abs(curv_end) < 1e-9:
            return self._convert_line(geom)

        # Calculate number of samples (tighter sampling for spirals)
        num_samples = max(5, int(geom.length / (self.sampling_interval * 0.5)) + 1)

        points = []
        for i in range(num_samples):
            s = (i / (num_samples - 1)) * geom.length

            # Local coordinates along spiral
            x_local, y_local, hdg_local = self._eval_spiral(s, geom.length, curv_start, curv_end)

            # Transform to global coordinates
            cos_hdg = math.cos(geom.hdg)
            sin_hdg = math.sin(geom.hdg)

            x_global = geom.x + x_local * cos_hdg - y_local * sin_hdg
            y_global = geom.y + x_local * sin_hdg + y_local * cos_hdg

            points.append((x_global, y_global))

        return points

    def _eval_spiral(
        self,
        s: float,
        length: float,
        curv_start: float,
        curv_end: float
    ) -> Tuple[float, float, float]:
        """
        Evaluate clothoid spiral at position s.

        Args:
            s: Position along spiral (0 to length)
            length: Total length of spiral
            curv_start: Curvature at start
            curv_end: Curvature at end

        Returns:
            Tuple of (x, y, heading) in local coordinates
        """
        # Clothoid parameter
        if abs(length) < 1e-9:
            return (s, 0.0, 0.0)

        # Linear curvature change
        curv_dot = (curv_end - curv_start) / length

        # Integrate to get position and heading
        # heading(s) = curv_start * s + 0.5 * curv_dot * s²
        # x(s) = integral of cos(heading(s)) ds
        # y(s) = integral of sin(heading(s)) ds

        # Use numerical integration for accuracy
        num_steps = max(10, int(s / 0.1) + 1)
        ds = s / num_steps

        x = 0.0
        y = 0.0
        hdg = 0.0

        for i in range(num_steps):
            s_i = i * ds
            curvature_i = curv_start + curv_dot * s_i

            x += math.cos(hdg) * ds
            y += math.sin(hdg) * ds
            hdg += curvature_i * ds

        return (x, y, hdg)

    def _convert_poly3(self, geom: GeometryElement) -> List[Tuple[float, float]]:
        """
        Convert poly3 geometry to polyline points.

        Poly3 defines lateral offset u as polynomial of longitudinal distance v:
        u(v) = a + b*v + c*v² + d*v³
        """
        a = geom.params.get('a', 0.0)
        b = geom.params.get('b', 0.0)
        c = geom.params.get('c', 0.0)
        d = geom.params.get('d', 0.0)

        # Sample along length
        num_samples = max(5, int(geom.length / self.sampling_interval) + 1)

        points = []
        for i in range(num_samples):
            v = (i / (num_samples - 1)) * geom.length  # Longitudinal distance
            u = a + b * v + c * v**2 + d * v**3  # Lateral offset

            # Transform to global coordinates
            # Local: (v, u) where v is along start heading, u is perpendicular
            cos_hdg = math.cos(geom.hdg)
            sin_hdg = math.sin(geom.hdg)

            x_global = geom.x + v * cos_hdg - u * sin_hdg
            y_global = geom.y + v * sin_hdg + u * cos_hdg

            points.append((x_global, y_global))

        return points

    def _convert_param_poly3(self, geom: GeometryElement) -> List[Tuple[float, float]]:
        """
        Convert paramPoly3 geometry to polyline points.

        ParamPoly3 defines position as parametric cubic polynomials:
        U(p) = aU + bU*p + cU*p² + dU*p³  (along reference line direction)
        V(p) = aV + bV*p + cV*p² + dV*p³  (perpendicular to reference line)
        where p is normalized parameter [0, 1] or arc length [0, length]

        According to OpenDRIVE spec:
        - U is the local coordinate along the s-direction (forward/longitudinal)
        - V is the local coordinate perpendicular to s (lateral)
        """
        aU = geom.params.get('aU', 0.0)
        bU = geom.params.get('bU', 0.0)
        cU = geom.params.get('cU', 0.0)
        dU = geom.params.get('dU', 0.0)

        aV = geom.params.get('aV', 0.0)
        bV = geom.params.get('bV', 0.0)
        cV = geom.params.get('cV', 0.0)
        dV = geom.params.get('dV', 0.0)

        p_range = geom.params.get('pRange', 'arcLength')

        # Sample parameter space
        num_samples = max(5, int(geom.length / self.sampling_interval) + 1)

        points = []
        for i in range(num_samples):
            # Parameter value
            if p_range == 'normalized':
                p = i / (num_samples - 1)
            else:  # arcLength
                p = (i / (num_samples - 1)) * geom.length

            # Evaluate parametric curve
            # U = forward/longitudinal (along reference line heading)
            # V = lateral (perpendicular to reference line)
            forward = aU + bU * p + cU * p**2 + dU * p**3
            lateral = aV + bV * p + cV * p**2 + dV * p**3

            # Transform to global coordinates
            cos_hdg = math.cos(geom.hdg)
            sin_hdg = math.sin(geom.hdg)

            # Forward is along heading, lateral is perpendicular (right is positive)
            x_global = geom.x + forward * cos_hdg - lateral * sin_hdg
            y_global = geom.y + forward * sin_hdg + lateral * cos_hdg

            points.append((x_global, y_global))

        return points

    def _points_match(self, p1: Tuple[float, float], p2: Tuple[float, float], tol: float = 0.01) -> bool:
        """Check if two points match within tolerance."""
        return abs(p1[0] - p2[0]) < tol and abs(p1[1] - p2[1]) < tol


def calculate_s_offsets(points: List[Tuple[float, float]]) -> List[float]:
    """
    Calculate s-offset (cumulative distance) for each point along polyline.

    Args:
        points: List of (x, y) coordinates

    Returns:
        List of s-offsets in meters, starting from 0
    """
    if not points:
        return []

    s_offsets = [0.0]
    cumulative_dist = 0.0

    for i in range(1, len(points)):
        dx = points[i][0] - points[i-1][0]
        dy = points[i][1] - points[i-1][1]
        dist = math.sqrt(dx**2 + dy**2)
        cumulative_dist += dist
        s_offsets.append(cumulative_dist)

    return s_offsets


def sample_elevation_profile(
    s_offsets: List[float],
    elevation_profile
) -> Optional[List[float]]:
    """
    Sample elevation profile at given s-offsets.

    Args:
        s_offsets: List of s-coordinates to sample
        elevation_profile: ElevationProfile from OpenDrive parser

    Returns:
        List of elevation values in meters, or None if no profile
    """
    if elevation_profile is None or not elevation_profile.elevations:
        return None

    elevations = []
    for s in s_offsets:
        elev = elevation_profile.get_elevation_at(s)
        elevations.append(elev if elev is not None else 0.0)

    return elevations

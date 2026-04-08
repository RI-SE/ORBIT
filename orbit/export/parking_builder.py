"""
Parking XML builder for OpenDRIVE export.

Handles creation of parking space-related XML elements.
"""

import math
from typing import List, Optional

import numpy as np
from lxml import etree

from orbit.models import Road
from orbit.models.parking import ParkingSpace


def _project_point_onto_polyline(px: float, py: float, pts: List[tuple]):
    """Project (px, py) onto a polyline, returning (s, t, hdg).

    s: arc-length distance along the polyline to the closest foot point.
    t: signed lateral offset (positive = left of travel direction).
    hdg: road heading (radians) at the projection point.
    Assumes pts are in a consistent coordinate system (e.g. metric).
    """
    min_dist = float('inf')
    best_s = 0.0
    best_t = 0.0
    best_hdg = 0.0
    cumulative_s = 0.0

    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        dx, dy = x2 - x1, y2 - y1
        seg_len = math.sqrt(dx * dx + dy * dy)
        if seg_len < 1e-9:
            continue
        t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (seg_len * seg_len)))
        cx = x1 + t * dx
        cy = y1 + t * dy
        dist = math.sqrt((px - cx) ** 2 + (py - cy) ** 2)
        if dist < min_dist:
            min_dist = dist
            best_s = cumulative_s + t * seg_len
            cross = (px - x1) * dy - (py - y1) * dx
            best_t = (1.0 if cross >= 0 else -1.0) * dist
            best_hdg = math.atan2(dy, dx)
        cumulative_s += seg_len

    return best_s, best_t, best_hdg


class ParkingBuilder:
    """Builds parking XML elements for OpenDRIVE export."""

    def __init__(
        self,
        scale_x: float = 1.0,
        transformer=None,
        curve_fitter=None,
        polyline_map: dict = None
    ):
        """
        Initialize parking builder.

        Args:
            scale_x: Scale factor in meters per pixel
            transformer: CoordinateTransformer for pixel to meter conversion
            curve_fitter: CurveFitter for geometry calculation
            polyline_map: Map of polyline ID to Polyline objects
        """
        self.scale_x = scale_x
        self.transformer = transformer
        self.curve_fitter = curve_fitter
        self.polyline_map = polyline_map or {}

    def create_parking_objects(
        self,
        road: Road,
        parking_spaces: List[ParkingSpace],
        centerline_points_pixel: List[tuple]
    ) -> List[etree.Element]:
        """
        Create object elements for parking spaces assigned to a road.

        Args:
            road: Road object
            parking_spaces: All parking spaces in the project
            centerline_points_pixel: List of centerline points in pixel coordinates

        Returns:
            List of object XML elements for parking spaces
        """
        # Find all parking spaces assigned to this road
        road_parking = [p for p in parking_spaces if p.road_id == road.id]

        if not road_parking:
            return []

        # Calculate total pixel length of centerline
        pixel_length = self._calculate_pixel_length(centerline_points_pixel)

        # Get actual road length and metric centerline for accurate t-offset
        road_length_meters, centerline_meters, geometry_elements = self._get_road_metrics(road)

        parking_elements = []
        for parking in road_parking:
            obj_elem = self._create_parking_object(
                parking, centerline_points_pixel, pixel_length,
                road_length_meters, centerline_meters, geometry_elements
            )
            if obj_elem is not None:
                parking_elements.append(obj_elem)

        return parking_elements

    def _calculate_pixel_length(self, centerline_points: List[tuple]) -> float:
        """Calculate total pixel length of centerline."""
        pixel_length = 0.0
        for i in range(len(centerline_points) - 1):
            x1, y1 = centerline_points[i]
            x2, y2 = centerline_points[i + 1]
            pixel_length += ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        return pixel_length

    def _get_road_metrics(self, road: Road):
        """Get road length in meters and metric centerline points.

        Returns:
            Tuple of (road_length_meters, centerline_meters, geometry_elements).
            All are empty / 0.0 when transformer or centerline are unavailable.
        """
        if not self.transformer or not self.curve_fitter:
            return 0.0, [], []

        centerline = self.polyline_map.get(road.centerline_id)
        if not centerline:
            return 0.0, [], []

        # Use geo coords directly if available (more precise)
        if centerline.geo_points:
            all_points_meters = [
                self.transformer.latlon_to_meters(lat, lon)
                for lon, lat in centerline.geo_points
            ]
        else:
            all_points_meters = self.transformer.pixels_to_meters_batch(centerline.points)
        geometry_elements = self.curve_fitter.fit_polyline(all_points_meters)
        return sum(elem.length for elem in geometry_elements), all_points_meters, geometry_elements

    def _calculate_road_length_meters(self, road: Road) -> float:
        """Return road length in meters. Kept for backward compatibility."""
        road_length, _, _ = self._get_road_metrics(road)
        return road_length

    def _create_parking_object(
        self,
        parking: ParkingSpace,
        centerline_points_pixel: List[tuple],
        pixel_length: float,
        road_length_meters: float,
        centerline_meters: List[tuple] = None,
        geometry_elements: list = None,
    ) -> Optional[etree.Element]:
        """Create a single parking object element with parkingSpace child."""
        # Calculate s and t coordinates
        s_position_px, t_offset_px = parking.calculate_s_t_position(centerline_points_pixel)
        if s_position_px is None:
            return None

        # Map pixel s-coordinate to road geometry s-coordinate
        s_ratio = s_position_px / pixel_length if pixel_length > 0 else 0
        s_meters = s_ratio * road_length_meters

        road_hdg = 0.0
        reconstructed_anchor = None

        # Convert t-offset from pixels to meters.
        # Project anchor in metric space when transformer + metric centerline are available
        # to avoid the scale_x error on angled roads.
        if self.transformer and centerline_meters and len(centerline_meters) >= 2:
            if parking.points:
                anchor_px = sum(p[0] for p in parking.points) / len(parking.points)
                anchor_py = sum(p[1] for p in parking.points) / len(parking.points)
            else:
                anchor_px, anchor_py = parking.position
            try:
                anchor_m = self.transformer.pixel_to_meters(anchor_px, anchor_py)
                s_meters, t_meters, road_hdg = _project_point_onto_polyline(
                    anchor_m[0], anchor_m[1], centerline_meters
                )
                # Scale s to match fitted road length
                cl_len = sum(
                    math.sqrt((centerline_meters[i+1][0] - centerline_meters[i][0])**2
                              + (centerline_meters[i+1][1] - centerline_meters[i][1])**2)
                    for i in range(len(centerline_meters) - 1)
                )
                if cl_len > 0:
                    s_meters = s_meters * (road_length_meters / cl_len)

                # Compute reconstructed anchor and refine heading from fitted geometry
                if geometry_elements:
                    from orbit.export.object_builder import ObjectBuilder
                    road_x, road_y, road_hdg = ObjectBuilder._sample_geometry(
                        s_meters, geometry_elements
                    )
                    reconstructed_anchor = (
                        road_x + t_meters * (-math.sin(road_hdg)),
                        road_y + t_meters * math.cos(road_hdg),
                    )
            except (TypeError, AttributeError):
                t_meters = t_offset_px * self.scale_x if t_offset_px else 0.0
        else:
            t_meters = t_offset_px * self.scale_x if t_offset_px else 0.0

        # Create object element
        object_elem = etree.Element('object')
        object_elem.set('id', parking.id)
        object_elem.set('s', f'{s_meters:.6f}')
        object_elem.set('t', f'{t_meters:.6f}')
        object_elem.set('zOffset', f'{parking.z_offset:.2f}')
        object_elem.set('name', parking.get_display_name())

        # OpenDRIVE parking-specific attributes
        object_elem.set('type', 'parking')
        object_elem.set('width', f'{parking.width:.2f}')
        object_elem.set('length', f'{parking.length:.2f}')
        object_elem.set('height', '0.0')  # Typically 0 for surface parking

        # Heading (orientation in radians)
        hdg = np.radians(parking.orientation)
        object_elem.set('hdg', f'{hdg:.6f}')

        # Orientation relative to road direction
        object_elem.set('orientation', '+')  # Same as road direction

        # Add parkingSpace child element
        parking_space_elem = etree.SubElement(object_elem, 'parkingSpace')
        parking_space_elem.set('access', parking.access.value)
        if parking.restrictions:
            parking_space_elem.set('restrictions', parking.restrictions)

        # Add outline if we have polygon points
        if parking.points and len(parking.points) >= 3:
            outline = self._create_parking_outline(parking, road_hdg, reconstructed_anchor)
            if outline is not None:
                object_elem.append(outline)

        return object_elem

    def _create_parking_outline(
        self,
        parking: ParkingSpace,
        road_hdg: float = 0.0,
        reconstructed_anchor: tuple = None,
    ) -> Optional[etree.Element]:
        """Create outline geometry for a parking space.

        Uses cornerLocal elements with u,v coordinates in the road's local
        coordinate system (u along s-direction, v along t-direction).

        Args:
            road_hdg: Road heading in radians at the object's s position,
                used to rotate polygon corners into road-local coordinates.
            reconstructed_anchor: (x, y) in meter space where the viewer
                will place this object from (s, t). Offsets are computed
                relative to this point to compensate for projection error.
        """
        if not parking.points or len(parking.points) < 3:
            return None

        outline = etree.Element('outline')
        cos_h = math.cos(road_hdg)
        sin_h = math.sin(road_hdg)

        if self.transformer:
            pts_m = [self.transformer.pixel_to_meters(px, py) for px, py in parking.points]
            if reconstructed_anchor:
                ref_m = reconstructed_anchor
            else:
                ref_m = (
                    sum(p[0] for p in pts_m) / len(pts_m),
                    sum(p[1] for p in pts_m) / len(pts_m),
                )
            for pt_m in pts_m:
                dx = pt_m[0] - ref_m[0]
                dy = pt_m[1] - ref_m[1]
                u = dx * cos_h + dy * sin_h
                v = -dx * sin_h + dy * cos_h
                corner = etree.SubElement(outline, 'cornerLocal')
                corner.set('u', f'{u:.4f}')
                corner.set('v', f'{v:.4f}')
                corner.set('z', '0.0')
                corner.set('height', '0.0')
        else:
            ref_x = sum(p[0] for p in parking.points) / len(parking.points)
            ref_y = sum(p[1] for p in parking.points) / len(parking.points)
            for px, py in parking.points:
                dx = (px - ref_x) * self.scale_x
                dy = (py - ref_y) * self.scale_x
                u = dx * cos_h + dy * sin_h
                v = -dx * sin_h + dy * cos_h
                corner = etree.SubElement(outline, 'cornerLocal')
                corner.set('u', f'{u:.4f}')
                corner.set('v', f'{v:.4f}')
                corner.set('z', '0.0')
                corner.set('height', '0.0')

        return outline if len(outline) > 0 else None

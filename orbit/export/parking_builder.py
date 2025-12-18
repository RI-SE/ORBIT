"""
Parking XML builder for OpenDRIVE export.

Handles creation of parking space-related XML elements.
"""

from typing import List, Optional
import numpy as np
from lxml import etree

from orbit.models import Road
from orbit.models.parking import ParkingSpace, ParkingAccess


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

        # Get actual road length in meters from geometry
        road_length_meters = self._calculate_road_length_meters(road)

        parking_elements = []
        for parking in road_parking:
            obj_elem = self._create_parking_object(
                parking, centerline_points_pixel, pixel_length, road_length_meters
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

    def _calculate_road_length_meters(self, road: Road) -> float:
        """Calculate actual road length in meters from geometry."""
        if not self.transformer or not self.curve_fitter:
            return 0.0

        centerline = self.polyline_map.get(road.centerline_id)
        if not centerline:
            return 0.0

        # Use geo coords directly if available (more precise)
        if centerline.geo_points:
            all_points_meters = [
                self.transformer.latlon_to_meters(lat, lon)
                for lon, lat in centerline.geo_points
            ]
        else:
            all_points_meters = self.transformer.pixels_to_meters_batch(centerline.points)
        geometry_elements = self.curve_fitter.fit_polyline(all_points_meters)
        return sum(elem.length for elem in geometry_elements)

    def _create_parking_object(
        self,
        parking: ParkingSpace,
        centerline_points_pixel: List[tuple],
        pixel_length: float,
        road_length_meters: float
    ) -> Optional[etree.Element]:
        """Create a single parking object element with parkingSpace child."""
        # Calculate s and t coordinates
        s_position_px, t_offset_px = parking.calculate_s_t_position(centerline_points_pixel)
        if s_position_px is None:
            return None

        # Map pixel s-coordinate to road geometry s-coordinate
        s_ratio = s_position_px / pixel_length if pixel_length > 0 else 0
        s_meters = s_ratio * road_length_meters

        # Convert t-offset from pixels to meters
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
            outline = self._create_parking_outline(parking)
            if outline is not None:
                object_elem.append(outline)

        return object_elem

    def _create_parking_outline(self, parking: ParkingSpace) -> Optional[etree.Element]:
        """
        Create outline geometry for a parking space.

        Uses cornerLocal elements with u,v coordinates in object's local coordinate system.
        """
        if not parking.points or len(parking.points) < 3:
            return None

        outline = etree.Element('outline')

        # Calculate centroid to use as reference point
        ref_x = sum(p[0] for p in parking.points) / len(parking.points)
        ref_y = sum(p[1] for p in parking.points) / len(parking.points)

        for px, py in parking.points:
            # Convert to local coordinates (relative to centroid, in meters)
            u = (px - ref_x) * self.scale_x
            v = (py - ref_y) * self.scale_x

            corner = etree.SubElement(outline, 'cornerLocal')
            corner.set('u', f'{u:.4f}')
            corner.set('v', f'{v:.4f}')
            corner.set('z', '0.0')
            corner.set('height', '0.0')

        return outline if len(outline) > 0 else None

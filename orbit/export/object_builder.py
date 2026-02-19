"""
Object XML builder for OpenDRIVE export.

Handles creation of road object-related XML elements (barriers, poles, vegetation, etc.).
"""

from typing import List, Optional

import numpy as np
from lxml import etree

from orbit.models import Road
from orbit.models.object import ObjectType, RoadObject


class ObjectBuilder:
    """Builds object XML elements for OpenDRIVE export."""

    def __init__(
        self,
        scale_x: float = 1.0,
        transformer=None,
        curve_fitter=None,
        polyline_map: dict = None
    ):
        """
        Initialize object builder.

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

    def create_objects(
        self,
        road: Road,
        objects: List[RoadObject],
        centerline_points_pixel: List[tuple]
    ) -> Optional[etree.Element]:
        """
        Create objects element for a road.

        Args:
            road: Road object
            objects: All objects in the project
            centerline_points_pixel: List of centerline points in pixel coordinates

        Returns:
            objects XML element or None if no objects for this road
        """
        # Find all objects assigned to this road
        road_objects = [obj for obj in objects if obj.road_id == road.id]

        if not road_objects:
            return None

        # Calculate total pixel length of centerline
        pixel_length = self._calculate_pixel_length(centerline_points_pixel)

        # Get actual road length in meters from geometry
        road_length_meters = self._calculate_road_length_meters(road)

        objects_elem = etree.Element('objects')

        for obj in road_objects:
            obj_elem = self._create_object(
                obj, centerline_points_pixel, pixel_length, road_length_meters
            )
            if obj_elem is not None:
                objects_elem.append(obj_elem)

        return objects_elem if len(objects_elem) > 0 else None

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

    def _create_object(
        self,
        obj: RoadObject,
        centerline_points_pixel: List[tuple],
        pixel_length: float,
        road_length_meters: float
    ) -> Optional[etree.Element]:
        """Create a single object element."""
        # Calculate s and t coordinates in pixel space
        s_position_px, t_offset_px = obj.calculate_s_t_position(centerline_points_pixel)
        if s_position_px is None:
            return None

        # Map pixel s-coordinate to road geometry s-coordinate
        s_ratio = s_position_px / pixel_length if pixel_length > 0 else 0
        s_meters = s_ratio * road_length_meters

        # Convert t-offset from pixels to meters
        t_meters = t_offset_px * self.scale_x

        # Create object element
        object_elem = etree.Element('object')
        object_elem.set('id', obj.id)
        object_elem.set('s', f'{s_meters:.6f}')
        object_elem.set('t', f'{t_meters:.6f}')
        object_elem.set('zOffset', f'{obj.z_offset:.2f}')
        object_elem.set('name', obj.get_display_name())

        # OpenDRIVE orientation angles (pitch and roll)
        if obj.pitch != 0.0:
            object_elem.set('pitch', f'{obj.pitch:.6f}')
        if obj.roll != 0.0:
            object_elem.set('roll', f'{obj.roll:.6f}')

        # Set type-specific attributes
        self._set_type_attributes(object_elem, obj)

        # Add outline geometry
        outline = self._create_object_outline(obj)
        if outline is not None:
            object_elem.append(outline)

        return object_elem

    def _set_type_attributes(self, object_elem: etree.Element, obj: RoadObject) -> None:
        """Set type-specific attributes on the object element."""
        if obj.type == ObjectType.LAMPPOST:
            object_elem.set('type', 'pole')
            object_elem.set('subtype', 'lamppost')
            object_elem.set('height', f"{obj.dimensions.get('height', 5.0):.2f}")
            object_elem.set('radius', f"{obj.dimensions.get('radius', 0.15):.2f}")
            object_elem.set('hdg', f'{np.radians(obj.orientation):.6f}')

        elif obj.type == ObjectType.GUARDRAIL:
            object_elem.set('type', 'barrier')
            object_elem.set('subtype', 'guardrail')
            object_elem.set('height', f"{obj.dimensions.get('height', 0.81):.2f}")
            object_elem.set('width', f"{obj.dimensions.get('width', 0.3):.2f}")
            if obj.validity_length:
                length_meters = obj.validity_length * self.scale_x
                object_elem.set('length', f'{length_meters:.2f}')

        elif obj.type == ObjectType.BUILDING:
            object_elem.set('type', 'building')
            object_elem.set('subtype', '')
            object_elem.set('height', f"{obj.dimensions.get('height', 10.0):.2f}")
            object_elem.set('width', f"{obj.dimensions.get('width', 20.0):.2f}")
            object_elem.set('length', f"{obj.dimensions.get('length', 30.0):.2f}")
            object_elem.set('hdg', f'{np.radians(obj.orientation):.6f}')

        elif obj.type in (ObjectType.TREE_BROADLEAF, ObjectType.TREE_CONIFER):
            object_elem.set('type', 'vegetation')
            object_elem.set('subtype', 'tree')
            object_elem.set('height', f"{obj.dimensions.get('height', 8.0):.2f}")
            object_elem.set('radius', f"{obj.dimensions.get('radius', 3.0):.2f}")

        elif obj.type == ObjectType.BUSH:
            object_elem.set('type', 'vegetation')
            object_elem.set('subtype', 'bush')
            object_elem.set('height', f"{obj.dimensions.get('height', 2.0):.2f}")
            object_elem.set('radius', f"{obj.dimensions.get('radius', 1.0):.2f}")

        elif obj.type == ObjectType.LANDUSE_FOREST:
            object_elem.set('type', 'vegetation')
            object_elem.set('subtype', 'forest')
            object_elem.set('height', '0.00')

        elif obj.type == ObjectType.LANDUSE_FARMLAND:
            object_elem.set('type', 'land')
            object_elem.set('subtype', 'farmland')
            object_elem.set('height', '0.00')

        elif obj.type == ObjectType.LANDUSE_MEADOW:
            object_elem.set('type', 'vegetation')
            object_elem.set('subtype', 'meadow')
            object_elem.set('height', '0.00')

        elif obj.type == ObjectType.LANDUSE_SCRUB:
            object_elem.set('type', 'vegetation')
            object_elem.set('subtype', 'scrub')
            object_elem.set('height', '0.00')

        elif obj.type == ObjectType.NATURAL_WATER:
            object_elem.set('type', 'water')
            object_elem.set('subtype', '')
            object_elem.set('height', '0.00')

        elif obj.type == ObjectType.NATURAL_WETLAND:
            object_elem.set('type', 'water')
            object_elem.set('subtype', 'wetland')
            object_elem.set('height', '0.00')

    def _create_object_outline(self, obj: RoadObject) -> Optional[etree.Element]:
        """
        Create outline geometry for an object.

        Uses cornerLocal elements with u,v coordinates in object's local coordinate system.
        """
        outline = etree.Element('outline')

        if obj.type == ObjectType.LAMPPOST:
            self._create_circular_outline(outline, obj, 12)

        elif obj.type == ObjectType.GUARDRAIL:
            self._create_polyline_outline(outline, obj)

        elif obj.type == ObjectType.BUILDING:
            self._create_rectangular_outline(outline, obj)

        elif obj.type in (ObjectType.TREE_BROADLEAF, ObjectType.BUSH):
            self._create_circular_outline(outline, obj, 8)

        elif obj.type == ObjectType.TREE_CONIFER:
            self._create_triangular_outline(outline, obj)

        elif obj.type.get_shape_type() == "polygon":
            self._create_polygon_outline(outline, obj)

        return outline if len(outline) > 0 else None

    def _create_circular_outline(
        self,
        outline: etree.Element,
        obj: RoadObject,
        num_points: int
    ) -> None:
        """Create circular outline approximated with polygon."""
        if obj.type == ObjectType.LAMPPOST:
            radius = obj.dimensions.get('radius', 0.15)
            height = obj.dimensions.get('height', 5.0)
        elif obj.type == ObjectType.TREE_BROADLEAF:
            radius = obj.dimensions.get('radius', 3.0)
            height = obj.dimensions.get('height', 8.0)
        else:  # BUSH
            radius = obj.dimensions.get('radius', 1.0)
            height = obj.dimensions.get('height', 2.0)

        for i in range(num_points):
            angle = 2 * np.pi * i / num_points
            u = radius * np.cos(angle)
            v = radius * np.sin(angle)
            corner = etree.SubElement(outline, 'cornerLocal')
            corner.set('u', f'{u:.4f}')
            corner.set('v', f'{v:.4f}')
            corner.set('z', '0.0')
            corner.set('height', f'{height:.2f}')

    def _create_polyline_outline(self, outline: etree.Element, obj: RoadObject) -> None:
        """Create polyline outline for guardrails."""
        if not obj.points or len(obj.points) < 2:
            return

        height = obj.dimensions.get('height', 0.81)
        ref_x, ref_y = obj.points[0]

        for px, py in obj.points:
            u = (px - ref_x) * self.scale_x
            v = (py - ref_y) * self.scale_x
            corner = etree.SubElement(outline, 'cornerLocal')
            corner.set('u', f'{u:.4f}')
            corner.set('v', f'{v:.4f}')
            corner.set('z', '0.0')
            corner.set('height', f'{height:.2f}')

    def _create_rectangular_outline(self, outline: etree.Element, obj: RoadObject) -> None:
        """Create rectangular outline for buildings."""
        width = obj.dimensions.get('width', 20.0)
        length = obj.dimensions.get('length', 30.0)
        height = obj.dimensions.get('height', 10.0)

        # Four corners centered at origin
        corners_local = [
            (-width/2, -length/2),
            (width/2, -length/2),
            (width/2, length/2),
            (-width/2, length/2)
        ]

        for u, v in corners_local:
            corner = etree.SubElement(outline, 'cornerLocal')
            corner.set('u', f'{u:.4f}')
            corner.set('v', f'{v:.4f}')
            corner.set('z', '0.0')
            corner.set('height', f'{height:.2f}')

    def _create_polygon_outline(self, outline: etree.Element, obj: RoadObject) -> None:
        """Create polygon outline for land use areas and parking polygons.

        Converts polygon points to local u,v coordinates relative to the
        object's anchor position (first point). Uses geo_points → meters
        when available for accuracy, falling back to pixel * scale_x.
        """
        if not obj.points or len(obj.points) < 3:
            return

        height = obj.dimensions.get('height', 0.0)

        # Determine reference point (first point) and convert to meters
        if obj.geo_points and self.transformer and len(obj.geo_points) == len(obj.points):
            # Use geo coords for precision
            ref_lon, ref_lat = obj.geo_points[0]
            ref_m = self.transformer.latlon_to_meters(ref_lat, ref_lon)
            for lon, lat in obj.geo_points:
                pt_m = self.transformer.latlon_to_meters(lat, lon)
                u = pt_m[0] - ref_m[0]
                v = pt_m[1] - ref_m[1]
                corner = etree.SubElement(outline, 'cornerLocal')
                corner.set('u', f'{u:.4f}')
                corner.set('v', f'{v:.4f}')
                corner.set('z', '0.0')
                corner.set('height', f'{height:.2f}')
        else:
            # Fallback: pixel coordinates scaled to meters
            ref_x, ref_y = obj.points[0]
            for px, py in obj.points:
                u = (px - ref_x) * self.scale_x
                v = (py - ref_y) * self.scale_x
                corner = etree.SubElement(outline, 'cornerLocal')
                corner.set('u', f'{u:.4f}')
                corner.set('v', f'{v:.4f}')
                corner.set('z', '0.0')
                corner.set('height', f'{height:.2f}')

    def _create_triangular_outline(self, outline: etree.Element, obj: RoadObject) -> None:
        """Create triangular outline for conifers."""
        radius = obj.dimensions.get('radius', 2.0)
        height = obj.dimensions.get('height', 10.0)

        corners = [
            (0, radius * 1.5),
            (-radius, -radius),
            (radius, -radius)
        ]

        for u, v in corners:
            corner = etree.SubElement(outline, 'cornerLocal')
            corner.set('u', f'{u:.4f}')
            corner.set('v', f'{v:.4f}')
            corner.set('z', '0.0')
            corner.set('height', f'{height:.2f}')

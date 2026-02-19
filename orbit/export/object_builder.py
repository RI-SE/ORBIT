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
        centerline_points_pixel: List[tuple],
        geometry_elements=None,
        road_length: float = None,
    ) -> Optional[etree.Element]:
        """
        Create objects element for a road.

        Args:
            road: Road object
            objects: All objects in the project
            centerline_points_pixel: List of centerline points in pixel coordinates
            geometry_elements: Fitted geometry elements (for accurate heading)
            road_length: Total road length in meters from geometry
        """
        # Find all objects assigned to this road
        road_objects = [obj for obj in objects if obj.road_id == road.id]

        if not road_objects:
            return None

        # Calculate total pixel length of centerline
        pixel_length = self._calculate_pixel_length(centerline_points_pixel)

        # Get meter-space centerline and road length
        centerline_meters, road_length_meters = self._get_meter_centerline(road)
        # Prefer externally-provided road_length (from same geometry used in planView)
        if road_length is not None:
            road_length_meters = road_length

        objects_elem = etree.Element('objects')

        for obj in road_objects:
            obj_elem = self._create_object(
                obj, centerline_points_pixel, pixel_length,
                road_length_meters, centerline_meters, geometry_elements
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

    def _get_meter_centerline(self, road: Road) -> tuple:
        """Get meter-space centerline points and total road length.

        Returns:
            Tuple of (centerline_points_meters, road_length_meters).
            centerline_points_meters is a list of (x, y) in meters,
            or empty list if unavailable.
        """
        if not self.transformer or not self.curve_fitter:
            return [], 0.0

        centerline = self.polyline_map.get(road.centerline_id)
        if not centerline:
            return [], 0.0

        # Use geo coords directly if available (more precise)
        if centerline.geo_points:
            all_points_meters = [
                self.transformer.latlon_to_meters(lat, lon)
                for lon, lat in centerline.geo_points
            ]
        else:
            all_points_meters = self.transformer.pixels_to_meters_batch(centerline.points)
        geometry_elements = self.curve_fitter.fit_polyline(all_points_meters)
        road_length = sum(elem.length for elem in geometry_elements)
        return all_points_meters, road_length

    def _create_object(
        self,
        obj: RoadObject,
        centerline_points_pixel: List[tuple],
        pixel_length: float,
        road_length_meters: float,
        centerline_meters: List[tuple] = None,
        geometry_elements=None,
    ) -> Optional[etree.Element]:
        """Create a single object element."""
        is_polygon = obj.type.get_shape_type() == "polygon"

        # For polygon objects with geo data, project directly in meter space
        if is_polygon and centerline_meters and self.transformer and obj.geo_position:
            ref_lon, ref_lat = obj.geo_position
            anchor_m = self.transformer.latlon_to_meters(ref_lat, ref_lon)
            s_meters, t_meters, road_hdg = self._project_onto_meter_centerline(
                anchor_m, centerline_meters, road_length_meters
            )
            # Use fitted geometry heading if available (matches planView exactly)
            if geometry_elements:
                road_hdg = self._heading_from_geometry(s_meters, geometry_elements)
        else:
            # Standard pixel-space approach for non-polygon objects
            s_position_px, t_offset_px = obj.calculate_s_t_position(centerline_points_pixel)
            if s_position_px is None:
                return None
            s_ratio = s_position_px / pixel_length if pixel_length > 0 else 0
            s_meters = s_ratio * road_length_meters
            t_meters = t_offset_px * self.scale_x
            road_hdg = self._get_road_heading_at(centerline_points_pixel, obj)

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
        outline = self._create_object_outline(obj, road_hdg)
        if outline is not None:
            object_elem.append(outline)

        return object_elem

    def _get_road_heading_at(
        self,
        centerline_points_pixel: List[tuple],
        obj: RoadObject,
    ) -> float:
        """Get road heading (radians, from x-axis) at the object's anchor point.

        Finds the closest centerline segment and returns its heading in meter
        space via the transformer.
        """
        if len(centerline_points_pixel) < 2:
            return 0.0

        # Determine the anchor pixel position (same logic as calculate_s_t_position)
        if obj.points and obj.type.get_shape_type() == "polygon":
            px, py = obj.position  # centroid for polygon objects
        elif obj.points:
            px, py = obj.points[0]
        else:
            px, py = obj.position

        # Find closest segment
        min_dist = float('inf')
        closest_idx = 0
        for i in range(len(centerline_points_pixel) - 1):
            x1, y1 = centerline_points_pixel[i]
            x2, y2 = centerline_points_pixel[i + 1]
            dx, dy = x2 - x1, y2 - y1
            length_sq = dx * dx + dy * dy
            if length_sq == 0:
                t = 0
            else:
                t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / length_sq))
            proj_x = x1 + t * dx
            proj_y = y1 + t * dy
            dist = ((px - proj_x) ** 2 + (py - proj_y) ** 2) ** 0.5
            if dist < min_dist:
                min_dist = dist
                closest_idx = i

        # Compute heading of that segment in meter space
        x1_px, y1_px = centerline_points_pixel[closest_idx]
        x2_px, y2_px = centerline_points_pixel[closest_idx + 1]
        if self.transformer:
            try:
                x1_m, y1_m = self.transformer.pixel_to_meters(x1_px, y1_px)
                x2_m, y2_m = self.transformer.pixel_to_meters(x2_px, y2_px)
            except (TypeError, AttributeError):
                x1_m, y1_m = x1_px * self.scale_x, y1_px * self.scale_x
                x2_m, y2_m = x2_px * self.scale_x, y2_px * self.scale_x
        else:
            x1_m, y1_m = x1_px * self.scale_x, y1_px * self.scale_x
            x2_m, y2_m = x2_px * self.scale_x, y2_px * self.scale_x
        return np.arctan2(y2_m - y1_m, x2_m - x1_m)

    @staticmethod
    def _project_onto_meter_centerline(
        point_m: tuple,
        centerline_m: List[tuple],
        road_length_m: float,
    ) -> tuple:
        """Project a meter-space point onto the meter-space centerline.

        Returns:
            Tuple of (s_meters, t_meters, heading) where heading is the
            road direction at the projection point in radians.
        """
        px, py = point_m
        min_dist = float('inf')
        best_s = 0.0
        best_t = 0.0
        best_hdg = 0.0
        cumul_s = 0.0

        for i in range(len(centerline_m) - 1):
            x1, y1 = centerline_m[i]
            x2, y2 = centerline_m[i + 1]
            dx, dy = x2 - x1, y2 - y1
            seg_len = (dx * dx + dy * dy) ** 0.5
            if seg_len < 1e-12:
                cumul_s += seg_len
                continue

            t_param = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / (seg_len * seg_len)))
            proj_x = x1 + t_param * dx
            proj_y = y1 + t_param * dy
            dist = ((px - proj_x) ** 2 + (py - proj_y) ** 2) ** 0.5

            if dist < min_dist:
                min_dist = dist
                best_s = cumul_s + t_param * seg_len
                seg_hdg = np.arctan2(dy, dx)
                # t-offset: positive = left of road direction (OpenDRIVE convention)
                # In meter space (y-up), cross = direction × offset gives correct sign
                cross = dx * (py - proj_y) - dy * (px - proj_x)
                best_t = dist if cross >= 0 else -dist
                best_hdg = seg_hdg

            cumul_s += seg_len

        # Clamp s to [0, road_length]
        total_cl_len = cumul_s
        if total_cl_len > 0:
            best_s = best_s * (road_length_m / total_cl_len)
        return best_s, best_t, best_hdg

    @staticmethod
    def _heading_from_geometry(s: float, geometry_elements) -> float:
        """Get the road heading at s from fitted geometry elements.

        This matches the heading used by the planView exactly, ensuring
        cornerLocal u,v rotations are consistent with the xodr road geometry.
        """
        from orbit.export.reference_line_sampler import _sample_element

        cumul_s = 0.0
        for elem in geometry_elements:
            if cumul_s + elem.length >= s or elem is geometry_elements[-1]:
                s_local = max(0.0, min(s - cumul_s, elem.length))
                _, _, hdg = _sample_element(elem, s_local)
                return hdg
            cumul_s += elem.length
        # Fallback: heading of last element at its end
        if geometry_elements:
            _, _, hdg = _sample_element(geometry_elements[-1], geometry_elements[-1].length)
            return hdg
        return 0.0

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

    def _create_object_outline(
        self, obj: RoadObject, road_hdg: float = 0.0
    ) -> Optional[etree.Element]:
        """Create outline geometry for an object.

        Uses cornerLocal elements with u,v coordinates in object's local
        coordinate system (aligned with road s,t when hdg=0).

        Args:
            obj: The road object.
            road_hdg: Road heading in radians at the object's s position,
                used to rotate polygon outlines into road-local coordinates.
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
            self._create_polygon_outline(outline, obj, road_hdg)

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

    def _create_polygon_outline(
        self, outline: etree.Element, obj: RoadObject, road_hdg: float = 0.0
    ) -> None:
        """Create polygon outline for land use areas and parking polygons.

        Converts polygon points to cornerLocal u,v coordinates in the road's
        local coordinate system (u along s-direction, v along t-direction).
        Uses the centroid as reference point (matching calculate_s_t_position
        which uses obj.position for polygon objects).

        Args:
            outline: Parent XML element to append corners to.
            obj: Object with polygon points/geo_points.
            road_hdg: Road heading in radians at the object's s position.
        """
        if not obj.points or len(obj.points) < 3:
            return

        height = obj.dimensions.get('height', 0.0)
        cos_h = np.cos(road_hdg)
        sin_h = np.sin(road_hdg)

        if obj.geo_points and self.transformer and len(obj.geo_points) == len(obj.points):
            # Use geo centroid as reference (matches obj.geo_position from import)
            if obj.geo_position:
                ref_lon, ref_lat = obj.geo_position
            else:
                ref_lon = sum(p[0] for p in obj.geo_points) / len(obj.geo_points)
                ref_lat = sum(p[1] for p in obj.geo_points) / len(obj.geo_points)
            ref_m = self.transformer.latlon_to_meters(ref_lat, ref_lon)
            for lon, lat in obj.geo_points:
                pt_m = self.transformer.latlon_to_meters(lat, lon)
                dx = pt_m[0] - ref_m[0]
                dy = pt_m[1] - ref_m[1]
                # Rotate from global meter space into road-local (u,v)
                u = dx * cos_h + dy * sin_h
                v = -dx * sin_h + dy * cos_h
                corner = etree.SubElement(outline, 'cornerLocal')
                corner.set('u', f'{u:.4f}')
                corner.set('v', f'{v:.4f}')
                corner.set('z', '0.0')
                corner.set('height', f'{height:.2f}')
        else:
            # Fallback: pixel centroid as reference (matches obj.position)
            ref_x, ref_y = obj.position
            for px, py in obj.points:
                dx = (px - ref_x) * self.scale_x
                dy = (py - ref_y) * self.scale_x
                u = dx * cos_h + dy * sin_h
                v = -dx * sin_h + dy * cos_h
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

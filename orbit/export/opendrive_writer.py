"""
OpenDrive XML writer for ORBIT.

Generates ASAM OpenDrive format XML from annotated roads and junctions.
"""

from typing import List, Dict, Optional, Tuple
from datetime import datetime
from lxml import etree
import numpy as np

from orbit.models import Project, Road, Junction, Polyline, LineType, RoadMarkType, Signal
from orbit.models.signal import SignalType, SpeedUnit
from orbit.models.object import RoadObject, ObjectType
from orbit.utils import CoordinateTransformer
from .curve_fitting import CurveFitter, GeometryElement, GeometryType
from .lane_analyzer import LaneAnalyzer, BoundaryInfo


class OpenDriveWriter:
    """Writes project data to OpenDrive XML format."""

    def __init__(
        self,
        project: Project,
        transformer: CoordinateTransformer,
        curve_fitter: Optional[CurveFitter] = None,
        right_hand_traffic: bool = True,
        country_code: str = "se"
    ):
        """
        Initialize OpenDrive writer.

        Args:
            project: The ORBIT project
            transformer: Coordinate transformer for pixel to geo conversion
            curve_fitter: Optional curve fitter (creates default if None)
            right_hand_traffic: True for right-hand traffic (default), False for left-hand
            country_code: Two-letter ISO 3166-1 country code (default: "se")
        """
        self.project = project
        self.transformer = transformer
        self.curve_fitter = curve_fitter or CurveFitter(preserve_geometry=True)
        self.right_hand_traffic = right_hand_traffic
        self.country_code = country_code.lower()

        # Build lookup maps
        self.polyline_map = {p.id: p for p in project.polylines}
        self.road_map = {r.id: r for r in project.roads}
        self.junction_map = {j.id: j for j in project.junctions}

        # Get scale factors for lane width calculations
        scale_factors = transformer.get_scale_factor() if transformer else None

        # Store scale factors for coordinate conversions
        if scale_factors:
            self.scale_x, self.scale_y = scale_factors
        else:
            self.scale_x, self.scale_y = 1.0, 1.0  # Default if no georeferencing

        # Initialize lane analyzer with scale factors and transformer
        # Passing transformer enables accurate perspective-aware conversions for homography
        self.lane_analyzer = LaneAnalyzer(project, right_hand_traffic, scale_factors, transformer)

    def write(self, output_path: str) -> bool:
        """
        Write OpenDrive XML to file.

        Args:
            output_path: Path to output .xodr file

        Returns:
            True if successful
        """
        try:
            root = self._create_opendrive_root()

            # Write to file with pretty formatting
            tree = etree.ElementTree(root)
            tree.write(
                output_path,
                pretty_print=True,
                xml_declaration=True,
                encoding='utf-8'
            )
            return True
        except Exception as e:
            print(f"Error writing OpenDrive: {e}")
            return False

    def _create_opendrive_root(self) -> etree.Element:
        """Create the root OpenDRIVE element with all content."""
        root = etree.Element('OpenDRIVE')

        # Add header
        header = self._create_header()
        root.append(header)

        # Add roads
        for road in self.project.roads:
            if road.is_valid():
                road_elem = self._create_road(road)
                if road_elem is not None:
                    root.append(road_elem)

        # Add junctions
        for junction in self.project.junctions:
            if junction.is_valid():
                junction_elem = self._create_junction(junction)
                if junction_elem is not None:
                    root.append(junction_elem)

        return root

    def _create_header(self) -> etree.Element:
        """Create OpenDrive header element."""
        header = etree.Element('header')
        header.set('revMajor', '1')
        header.set('revMinor', '7')

        # Use map name from project, fallback to 'ORBIT Export' if empty
        map_name = self.project.map_name if self.project.map_name else 'ORBIT Export'
        header.set('name', map_name)

        header.set('version', '1.0')
        header.set('date', datetime.now().isoformat())

        # Calculate bounding box from all polylines in metric coordinates
        if self.project.has_georeferencing():
            bounds = self._calculate_bounds()
            header.set('north', f'{bounds["north"]:.4f}')
            header.set('south', f'{bounds["south"]:.4f}')
            header.set('east', f'{bounds["east"]:.4f}')
            header.set('west', f'{bounds["west"]:.4f}')
        else:
            header.set('north', '0.0')
            header.set('south', '0.0')
            header.set('east', '0.0')
            header.set('west', '0.0')

        header.set('vendor', 'ORBIT by RISE Research Institutes of Sweden')

        # Add tool information as userData
        tool_data = etree.SubElement(header, 'userData')
        tool_data.set('code', 'tool')
        tool_data.text = 'Produced by ORBIT (https://github.com/fwrise/SAVANT/tree/main/orbit)'

        # Add license information as userData
        # License userData is always included
        license_data = etree.SubElement(header, 'userData')
        license_data.set('code', 'license')
        license_data.text = 'Licensed under the Open Database License (https://opendatacommons.org/licenses/odbl/1-0/)'

        # Source attribution userData only if OpenStreetMap was used
        if self.project.openstreetmap_used:
            source_data = etree.SubElement(header, 'userData')
            source_data.set('code', 'sourceAttribution')
            source_data.text = 'Map data from OpenStreetMap (https://www.openstreetmap.org/copyright)'

        # Add georef if available
        if self.project.has_georeferencing():
            georef = etree.SubElement(header, 'geoReference')
            # Use proper metric projection string
            georef.text = self.transformer.get_projection_string()

        return header

    def _calculate_bounds(self) -> dict:
        """
        Calculate bounding box in metric coordinates from all polylines.

        Returns:
            Dictionary with 'north', 'south', 'east', 'west' in meters
        """
        all_points_meters = []

        # Collect all polyline points and convert to meters
        for polyline in self.project.polylines:
            points_meters = self.transformer.pixels_to_meters_batch(polyline.points)
            all_points_meters.extend(points_meters)

        if not all_points_meters:
            return {'north': 0.0, 'south': 0.0, 'east': 0.0, 'west': 0.0}

        # Find min/max
        xs = [p[0] for p in all_points_meters]
        ys = [p[1] for p in all_points_meters]

        return {
            'north': max(ys),
            'south': min(ys),
            'east': max(xs),
            'west': min(xs)
        }

    def _create_road(self, road: Road) -> Optional[etree.Element]:
        """Create a road element."""
        if not road.centerline_id:
            return None

        # Get centerline polyline ONLY for reference geometry
        centerline = self.polyline_map.get(road.centerline_id)
        if not centerline or centerline.point_count() < 2:
            return None

        # Transform centerline points to metric coordinates (meters)
        centerline_points_pixel = centerline.points
        all_points_meters = self.transformer.pixels_to_meters_batch(centerline_points_pixel)

        # Fit curves to metric coordinates
        geometry_elements = self.curve_fitter.fit_polyline(all_points_meters)

        if not geometry_elements:
            return None

        # Calculate total road length
        road_length = sum(elem.length for elem in geometry_elements)

        # Create road element
        road_elem = etree.Element('road')
        road_elem.set('id', road.id)
        road_elem.set('name', road.name)
        road_elem.set('length', f'{road_length:.4f}')
        road_elem.set('junction', road.junction_id if road.junction_id else '-1')

        # Add road link with predecessor/successor if available
        link = etree.SubElement(road_elem, 'link')

        # Add predecessor if specified
        if road.predecessor_id:
            predecessor = etree.SubElement(link, 'predecessor')
            predecessor.set('elementType', 'road')
            predecessor.set('elementId', road.predecessor_id)
            predecessor.set('contactPoint', road.predecessor_contact)

        # Add successor if specified
        if road.successor_id:
            successor = etree.SubElement(link, 'successor')
            successor.set('elementType', 'road')
            successor.set('elementId', road.successor_id)
            successor.set('contactPoint', road.successor_contact)

        # Add road type
        type_elem = etree.SubElement(road_elem, 'type')
        type_elem.set('s', '0.0')
        type_elem.set('type', road.road_type.value)

        if road.speed_limit:
            speed = etree.SubElement(type_elem, 'speed')
            speed.set('max', f'{road.speed_limit / 3.6:.2f}')  # Convert km/h to m/s
            speed.set('unit', 'm/s')

        # Add plan view (reference line geometry)
        plan_view = self._create_plan_view(geometry_elements)
        road_elem.append(plan_view)

        # Add elevation profile (flat for now)
        elevation = etree.SubElement(road_elem, 'elevationProfile')
        elev = etree.SubElement(elevation, 'elevation')
        elev.set('s', '0.0')
        elev.set('a', '0.0')
        elev.set('b', '0.0')
        elev.set('c', '0.0')
        elev.set('d', '0.0')

        # Add lateral profile (no superelevation)
        lateral = etree.SubElement(road_elem, 'lateralProfile')

        # Analyze lane boundaries
        boundary_infos, warning = self.lane_analyzer.analyze_road(road)

        # Add lanes (with boundary info if available)
        lanes = self._create_lanes(road, road_length, boundary_infos)
        road_elem.append(lanes)

        # Add signals for this road
        signals = self._create_signals(road, centerline_points_pixel)
        if signals is not None:
            road_elem.append(signals)

        # Add objects for this road
        objects = self._create_objects(road, centerline_points_pixel)
        if objects is not None:
            road_elem.append(objects)

        return road_elem

    def _create_plan_view(self, geometry_elements: List[GeometryElement]) -> etree.Element:
        """Create planView element with geometry."""
        plan_view = etree.Element('planView')

        s_offset = 0.0
        for geom in geometry_elements:
            geometry = etree.SubElement(plan_view, 'geometry')
            geometry.set('s', f'{s_offset:.4f}')
            geometry.set('x', f'{geom.start_pos[0]:.4f}')
            geometry.set('y', f'{geom.start_pos[1]:.4f}')
            geometry.set('hdg', f'{geom.heading:.6f}')
            geometry.set('length', f'{geom.length:.4f}')

            if geom.geom_type == GeometryType.LINE:
                line = etree.SubElement(geometry, 'line')
            elif geom.geom_type == GeometryType.ARC:
                arc = etree.SubElement(geometry, 'arc')
                arc.set('curvature', f'{geom.curvature:.8f}')
            elif geom.geom_type == GeometryType.SPIRAL:
                spiral = etree.SubElement(geometry, 'spiral')
                spiral.set('curvStart', f'{geom.curvature:.8f}')
                spiral.set('curvEnd', f'{geom.curvature_end:.8f}')

            s_offset += geom.length

        return plan_view

    def _create_lanes(
        self,
        road: Road,
        road_length: float,
        boundary_infos: List[BoundaryInfo]
    ) -> etree.Element:
        """Create lanes element with data-driven road marks from boundaries."""
        lanes = etree.Element('lanes')

        # Build map of lane_id to boundary info for quick lookup
        boundary_map = {b.lane_id: b for b in boundary_infos if b.lane_id is not None}

        # Use lane sections if available, otherwise fall back to old format
        if road.lane_sections:
            # New format: iterate through lane sections
            for section in road.lane_sections:
                lane_section = etree.SubElement(lanes, 'laneSection')

                # Convert pixel s-coordinates to meters
                s_meters = section.s_start * self.scale_x  # scale_x is in m/px
                lane_section.set('s', f'{s_meters:.6f}')

                # Add singleSide attribute if set
                if section.single_side:
                    lane_section.set('singleSide', section.single_side)

                # Build map of lane_id to Lane object for this section
                lane_map = {lane.id: lane for lane in section.lanes}

                # Left lanes (positive IDs)
                left = etree.SubElement(lane_section, 'left')
                left_lanes = [lane for lane in section.lanes if lane.id > 0]
                left_lanes.sort(key=lambda l: l.id)  # Sort ascending: 1, 2, 3...
                for lane_obj in left_lanes:
                    boundary_info = boundary_map.get(lane_obj.id)
                    lane = self._create_lane(lane_obj, road_length, boundary_info)
                    left.append(lane)

                # Center lane (reference lane, id=0)
                center = etree.SubElement(lane_section, 'center')
                center_lane_obj = lane_map.get(0)
                if center_lane_obj:
                    center_lane = self._create_center_lane(center_lane_obj)
                    center.append(center_lane)
                else:
                    # Fallback: create default center lane
                    center_lane = self._create_default_center_lane()
                    center.append(center_lane)

                # Right lanes (negative IDs)
                right = etree.SubElement(lane_section, 'right')
                right_lanes = [lane for lane in section.lanes if lane.id < 0]
                right_lanes.sort(key=lambda l: l.id, reverse=True)  # Sort descending: -1, -2, -3...
                for lane_obj in right_lanes:
                    boundary_info = boundary_map.get(lane_obj.id)
                    lane = self._create_lane(lane_obj, road_length, boundary_info)
                    right.append(lane)

        else:
            # Backward compatibility: create single lane section from road.lanes
            lane_section = etree.SubElement(lanes, 'laneSection')
            lane_section.set('s', '0.0')

            # Build map of lane_id to Lane object
            lane_map = {lane.id: lane for lane in road.lanes}

            # Left lanes (positive IDs)
            left = etree.SubElement(lane_section, 'left')
            left_lanes = [lane for lane in road.lanes if lane.id > 0]
            left_lanes.sort(key=lambda l: l.id)  # Sort ascending: 1, 2, 3...
            for lane_obj in left_lanes:
                boundary_info = boundary_map.get(lane_obj.id)
                lane = self._create_lane(lane_obj, road_length, boundary_info)
                left.append(lane)

            # Center lane (reference lane, id=0)
            center = etree.SubElement(lane_section, 'center')
            center_lane_obj = lane_map.get(0)
            if center_lane_obj:
                center_lane = self._create_center_lane(center_lane_obj)
                center.append(center_lane)
            else:
                # Fallback: create default center lane
                center_lane = self._create_default_center_lane()
                center.append(center_lane)

            # Right lanes (negative IDs)
            right = etree.SubElement(lane_section, 'right')
            right_lanes = [lane for lane in road.lanes if lane.id < 0]
            right_lanes.sort(key=lambda l: l.id, reverse=True)  # Sort descending: -1, -2, -3...
            for lane_obj in right_lanes:
                boundary_info = boundary_map.get(lane_obj.id)
                lane = self._create_lane(lane_obj, road_length, boundary_info)
                right.append(lane)

        return lanes

    def _create_center_lane(self, center_lane_obj) -> etree.Element:
        """Create center lane element from Lane object."""
        center_lane = etree.Element('lane')
        center_lane.set('id', '0')
        center_lane.set('type', center_lane_obj.lane_type.value)
        center_lane.set('level', 'false')

        # Road mark for center
        center_mark_type = self._convert_road_mark_type(center_lane_obj.road_mark_type)

        road_mark = etree.SubElement(center_lane, 'roadMark')
        road_mark.set('sOffset', '0.0')
        road_mark.set('type', center_mark_type)
        road_mark.set('weight', 'standard')
        road_mark.set('color', 'standard')
        road_mark.set('width', '0.13')

        return center_lane

    def _create_default_center_lane(self) -> etree.Element:
        """Create default center lane element."""
        center_lane = etree.Element('lane')
        center_lane.set('id', '0')
        center_lane.set('type', 'none')
        center_lane.set('level', 'false')

        road_mark = etree.SubElement(center_lane, 'roadMark')
        road_mark.set('sOffset', '0.0')
        road_mark.set('type', 'solid')
        road_mark.set('weight', 'standard')
        road_mark.set('color', 'standard')
        road_mark.set('width', '0.13')

        return center_lane

    def _create_lane(
        self,
        lane_obj,
        road_length: float,
        boundary_info: Optional[BoundaryInfo] = None
    ) -> etree.Element:
        """Create a single lane element with data-driven road mark."""
        from orbit.models import Lane

        lane = etree.Element('lane')
        lane.set('id', str(lane_obj.id))
        lane.set('type', lane_obj.lane_type.value)
        lane.set('level', 'false')

        # Lane link (simplified)
        link = etree.SubElement(lane, 'link')

        # Lane width - use the width from lane object (already in meters)
        width_elem = etree.SubElement(lane, 'width')
        width_elem.set('sOffset', '0.0')
        width_elem.set('a', f'{lane_obj.width:.2f}')
        width_elem.set('b', '0.0')
        width_elem.set('c', '0.0')
        width_elem.set('d', '0.0')

        # Road mark (priority: boundary polyline > lane object road_mark_type)
        if boundary_info and boundary_info.polyline:
            mark_type = self._convert_road_mark_type(boundary_info.polyline.road_mark_type)
        else:
            mark_type = self._convert_road_mark_type(lane_obj.road_mark_type)

        road_mark = etree.SubElement(lane, 'roadMark')
        road_mark.set('sOffset', '0.0')
        road_mark.set('type', mark_type)
        road_mark.set('weight', 'standard')
        road_mark.set('color', 'standard')
        road_mark.set('width', '0.13')

        return lane

    def _convert_road_mark_type(self, road_mark_type: RoadMarkType) -> str:
        """
        Convert ORBIT RoadMarkType enum to OpenDRIVE road mark type string.

        Maps ASAM e_roadMarkType values to valid OpenDRIVE types.
        """
        # Direct mapping for most types
        type_map = {
            RoadMarkType.NONE: 'none',
            RoadMarkType.SOLID: 'solid',
            RoadMarkType.BROKEN: 'broken',
            RoadMarkType.SOLID_SOLID: 'solid solid',
            RoadMarkType.SOLID_BROKEN: 'solid broken',
            RoadMarkType.BROKEN_SOLID: 'broken solid',
            RoadMarkType.BROKEN_BROKEN: 'broken broken',
            RoadMarkType.BOTTS_DOTS: 'botts dots',
            RoadMarkType.GRASS: 'grass',
            RoadMarkType.CURB: 'curb',
            RoadMarkType.CUSTOM: 'solid',  # Fallback to solid
            RoadMarkType.EDGE: 'solid'      # Edge typically solid
        }

        return type_map.get(road_mark_type, 'solid')

    def _create_signals(self, road: Road, centerline_points_pixel: List[tuple]) -> Optional[etree.Element]:
        """
        Create signals element for a road.

        Args:
            road: Road object
            centerline_points_pixel: List of centerline points in pixel coordinates

        Returns:
            signals XML element or None if no signals for this road
        """
        # Find all signals assigned to this road
        road_signals = [s for s in self.project.signals if s.road_id == road.id]

        if not road_signals:
            return None

        signals_elem = etree.Element('signals')

        for signal in road_signals:
            # Calculate s-coordinate along road centerline
            s_position = signal.calculate_s_position(centerline_points_pixel)
            if s_position is None:
                continue

            # Convert s-position from pixels to meters
            s_meters = s_position * self.scale_x  # scale_x is in m/px

            # Calculate t-coordinate (lateral offset from centerline)
            # For now, use a simple distance calculation
            # Positive t = left of road, negative t = right of road
            t_meters = self._calculate_t_offset(signal.position, centerline_points_pixel, s_position)

            # Create signal element
            signal_elem = etree.SubElement(signals_elem, 'signal')
            signal_elem.set('id', signal.id)
            signal_elem.set('s', f'{s_meters:.6f}')
            signal_elem.set('t', f'{t_meters:.6f}')
            signal_elem.set('name', signal.name if signal.name else signal.get_display_name())
            signal_elem.set('dynamic', 'no')

            # OpenDRIVE orientation: '+' (forward), '-' (backward), or 'none' (both)
            signal_elem.set('orientation', signal.orientation)

            # hOffset: heading offset in radians relative to perpendicular direction
            signal_elem.set('hOffset', f'{signal.h_offset:.6f}')

            # Z offset (height above ground)
            signal_elem.set('zOffset', f'{signal.z_offset:.2f}')

            # Physical dimensions of the sign
            signal_elem.set('height', f'{signal.sign_height:.2f}')
            signal_elem.set('width', f'{signal.sign_width:.2f}')

            # Country and type
            signal_elem.set('country', self.country_code)

            # Map signal type to OpenDRIVE type/subtype
            # Using German sign codes (DE:) as OpenDRIVE standard
            if signal.type == SignalType.STOP:
                signal_elem.set('type', '205')  # Stop sign
                signal_elem.set('subtype', '-1')
            elif signal.type == SignalType.GIVE_WAY:
                signal_elem.set('type', '206')  # Give way sign
                signal_elem.set('subtype', '-1')
            elif signal.type == SignalType.NO_ENTRY:
                signal_elem.set('type', '267')  # No entry
                signal_elem.set('subtype', '-1')
            elif signal.type == SignalType.PRIORITY_ROAD:
                signal_elem.set('type', '301')  # Priority road
                signal_elem.set('subtype', '-1')
            elif signal.type == SignalType.SPEED_LIMIT:
                signal_elem.set('type', '274')  # Speed limit
                # Convert speed if needed
                speed_value = signal.value
                if signal.speed_unit == SpeedUnit.MPH:
                    # Convert mph to km/h for OpenDRIVE
                    speed_value = int(signal.value * 1.60934)
                signal_elem.set('subtype', str(speed_value) if speed_value else '-1')
            elif signal.type == SignalType.END_OF_SPEED_LIMIT:
                signal_elem.set('type', '278')  # End of speed limit
                signal_elem.set('subtype', '-1')
            elif signal.type == SignalType.TRAFFIC_SIGNALS:
                signal_elem.set('type', '1000001')  # Traffic light
                signal_elem.set('subtype', '-1')
            else:
                # Generic/unknown sign
                signal_elem.set('type', '-1')
                signal_elem.set('subtype', '-1')

            # Validity range (optional)
            if signal.validity_range:
                validity = etree.SubElement(signal_elem, 'validity')
                # Convert pixel coordinates to meters
                from_s = signal.validity_range[0] * self.scale_x  # scale_x is in m/px
                to_s = signal.validity_range[1] * self.scale_x
                validity.set('fromLane', '0')  # Apply to all lanes by default
                validity.set('toLane', '0')

        return signals_elem

    def _calculate_t_offset(
        self,
        signal_position: tuple,
        centerline_points: List[tuple],
        s_position: float
    ) -> float:
        """
        Calculate lateral offset (t-coordinate) of signal from road centerline.

        Args:
            signal_position: (x, y) position of signal in pixels
            centerline_points: List of centerline points in pixels
            s_position: s-coordinate along centerline in pixels

        Returns:
            t-offset in meters (positive = left, negative = right)
        """
        # Find the point on the centerline at s_position
        cumulative_s = 0.0
        px, py = signal_position

        for i in range(len(centerline_points) - 1):
            x1, y1 = centerline_points[i]
            x2, y2 = centerline_points[i + 1]

            segment_length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
            next_s = cumulative_s + segment_length

            if next_s >= s_position:
                # This is the segment containing s_position
                # Find exact point on segment
                if segment_length == 0:
                    ref_x, ref_y = x1, y1
                else:
                    t = (s_position - cumulative_s) / segment_length
                    ref_x = x1 + t * (x2 - x1)
                    ref_y = y1 + t * (y2 - y1)

                # Calculate distance from signal to reference point
                distance_px = ((px - ref_x) ** 2 + (py - ref_y) ** 2) ** 0.5

                # Determine sign using cross product
                # If signal is on left side (in direction of travel), t is positive
                dx, dy = x2 - x1, y2 - y1
                cross = (px - x1) * dy - (py - y1) * dx

                sign = 1.0 if cross >= 0 else -1.0

                # Convert to meters
                distance_m = distance_px * self.scale_x  # scale_x is in m/px

                return sign * distance_m

            cumulative_s = next_s

        # Fallback: use distance to last point
        x, y = centerline_points[-1]
        distance_px = ((px - x) ** 2 + (py - y) ** 2) ** 0.5
        distance_m = distance_px * self.scale_x  # scale_x is in m/px
        return distance_m

    def _create_objects(self, road: Road, centerline_points_pixel: List[tuple]) -> Optional[etree.Element]:
        """
        Create objects element for a road.

        Args:
            road: Road object
            centerline_points_pixel: List of centerline points in pixel coordinates

        Returns:
            objects XML element or None if no objects for this road
        """
        # Find all objects assigned to this road
        road_objects = [obj for obj in self.project.objects if obj.road_id == road.id]

        if not road_objects:
            return None

        # Calculate total pixel length of centerline
        pixel_length = 0.0
        for i in range(len(centerline_points_pixel) - 1):
            x1, y1 = centerline_points_pixel[i]
            x2, y2 = centerline_points_pixel[i + 1]
            pixel_length += ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5

        # Get the actual road length from geometry elements
        centerline = self.polyline_map.get(road.centerline_id)
        all_points_meters = self.transformer.pixels_to_meters_batch(centerline.points)
        geometry_elements = self.curve_fitter.fit_polyline(all_points_meters)
        road_length_meters = sum(elem.length for elem in geometry_elements)

        objects_elem = etree.Element('objects')

        for obj in road_objects:
            # Calculate s and t coordinates in pixel space
            s_position_px, t_offset_px = obj.calculate_s_t_position(centerline_points_pixel)
            if s_position_px is None:
                continue

            # Map pixel s-coordinate to road geometry s-coordinate
            # This accounts for any distortion from the affine transformation
            s_ratio = s_position_px / pixel_length if pixel_length > 0 else 0
            s_meters = s_ratio * road_length_meters

            # Convert t-offset from pixels to meters
            t_meters = t_offset_px * self.scale_x

            # Create object element
            object_elem = etree.SubElement(objects_elem, 'object')
            object_elem.set('id', obj.id)
            object_elem.set('s', f'{s_meters:.6f}')
            object_elem.set('t', f'{t_meters:.6f}')
            object_elem.set('zOffset', f'{obj.z_offset:.2f}')
            object_elem.set('name', obj.get_display_name())

            # Map object types to OpenDRIVE type/subtype
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

            # Add outline geometry
            outline = self._create_object_outline(obj)
            if outline is not None:
                object_elem.append(outline)

        return objects_elem

    def _create_object_outline(self, obj: RoadObject) -> Optional[etree.Element]:
        """
        Create outline geometry for an object.

        Uses cornerLocal elements with u,v coordinates in object's local coordinate system.
        """
        outline = etree.Element('outline')

        if obj.type == ObjectType.LAMPPOST:
            # Circle approximated with 12-point polygon
            radius = obj.dimensions.get('radius', 0.15)
            num_points = 12
            for i in range(num_points):
                angle = 2 * np.pi * i / num_points
                u = radius * np.cos(angle)
                v = radius * np.sin(angle)
                corner = etree.SubElement(outline, 'cornerLocal')
                corner.set('u', f'{u:.4f}')
                corner.set('v', f'{v:.4f}')
                corner.set('z', '0.0')
                corner.set('height', f"{obj.dimensions.get('height', 5.0):.2f}")

        elif obj.type == ObjectType.GUARDRAIL:
            # Polyline outline using actual points
            if obj.points and len(obj.points) >= 2:
                # Convert points to object-local coordinates (relative to first point)
                ref_x, ref_y = obj.points[0]
                for px, py in obj.points:
                    u = (px - ref_x) * self.scale_x
                    v = (py - ref_y) * self.scale_x
                    corner = etree.SubElement(outline, 'cornerLocal')
                    corner.set('u', f'{u:.4f}')
                    corner.set('v', f'{v:.4f}')
                    corner.set('z', '0.0')
                    corner.set('height', f"{obj.dimensions.get('height', 0.81):.2f}")

        elif obj.type == ObjectType.BUILDING:
            # Rectangle in object's local coordinate system
            # Note: hdg attribute already handles rotation, so outline is NOT rotated
            width = obj.dimensions.get('width', 20.0)
            length = obj.dimensions.get('length', 30.0)
            height = obj.dimensions.get('height', 10.0)

            # Four corners (centered at origin, in object's local coords)
            # Match ORBIT rendering: width in u (X), length in v (Y)
            corners_local = [
                (-width/2, -length/2),   # Bottom-left
                (width/2, -length/2),    # Bottom-right
                (width/2, length/2),     # Top-right
                (-width/2, length/2)     # Top-left
            ]

            for u, v in corners_local:
                corner = etree.SubElement(outline, 'cornerLocal')
                corner.set('u', f'{u:.4f}')
                corner.set('v', f'{v:.4f}')
                corner.set('z', '0.0')
                corner.set('height', f'{height:.2f}')

        elif obj.type in (ObjectType.TREE_BROADLEAF, ObjectType.BUSH):
            # Circle approximated with 8-point polygon for vegetation
            radius = obj.dimensions.get('radius', 3.0 if obj.type == ObjectType.TREE_BROADLEAF else 1.0)
            height = obj.dimensions.get('height', 8.0 if obj.type == ObjectType.TREE_BROADLEAF else 2.0)
            num_points = 8
            for i in range(num_points):
                angle = 2 * np.pi * i / num_points
                u = radius * np.cos(angle)
                v = radius * np.sin(angle)
                corner = etree.SubElement(outline, 'cornerLocal')
                corner.set('u', f'{u:.4f}')
                corner.set('v', f'{v:.4f}')
                corner.set('z', '0.0')
                corner.set('height', f'{height:.2f}')

        elif obj.type == ObjectType.TREE_CONIFER:
            # Triangle/cone from top view
            radius = obj.dimensions.get('radius', 2.0)
            height = obj.dimensions.get('height', 10.0)

            # Three corners forming a triangle
            corners = [
                (0, radius * 1.5),           # Top point
                (-radius, -radius),          # Bottom left
                (radius, -radius)            # Bottom right
            ]

            for u, v in corners:
                corner = etree.SubElement(outline, 'cornerLocal')
                corner.set('u', f'{u:.4f}')
                corner.set('v', f'{v:.4f}')
                corner.set('z', '0.0')
                corner.set('height', f'{height:.2f}')

        return outline if len(outline) > 0 else None

    def _create_junction(self, junction: Junction) -> Optional[etree.Element]:
        """Create a junction element."""
        if len(junction.connected_road_ids) < 2:
            return None

        junction_elem = etree.Element('junction')
        junction_elem.set('id', junction.id)
        junction_elem.set('name', junction.name)
        junction_elem.set('type', junction.junction_type)

        # Create connections between roads
        # In a real implementation, this would need more sophisticated logic
        # For now, we create basic connections
        connection_id = 0
        for i, incoming_road_id in enumerate(junction.connected_road_ids):
            for j, connecting_road_id in enumerate(junction.connected_road_ids):
                if i != j:
                    connection = etree.SubElement(junction_elem, 'connection')
                    connection.set('id', str(connection_id))
                    connection.set('incomingRoad', incoming_road_id)
                    connection.set('connectingRoad', connecting_road_id)
                    connection.set('contactPoint', 'start')

                    # Lane links (simplified: connect all lanes)
                    incoming_road = self.road_map.get(incoming_road_id)
                    connecting_road = self.road_map.get(connecting_road_id)

                    if incoming_road and connecting_road:
                        # Connect one lane as example
                        lane_link = etree.SubElement(connection, 'laneLink')
                        lane_link.set('from', '-1')
                        lane_link.set('to', '-1')

                    connection_id += 1

        return junction_elem


def export_to_opendrive(
    project: Project,
    transformer: CoordinateTransformer,
    output_path: str,
    line_tolerance: float = 0.5,
    arc_tolerance: float = 1.0,
    preserve_geometry: bool = True,
    right_hand_traffic: bool = True,
    country_code: str = "se"
) -> bool:
    """
    Export project to OpenDrive format.

    Args:
        project: The ORBIT project
        transformer: Coordinate transformer
        output_path: Output file path (.xodr)
        line_tolerance: Tolerance for line fitting in meters
        arc_tolerance: Tolerance for arc fitting in meters
        preserve_geometry: If True, preserve all polyline points (one line per segment)
        right_hand_traffic: True for right-hand traffic (default), False for left-hand
        country_code: Two-letter ISO 3166-1 country code (default: "se")

    Returns:
        True if successful
    """
    curve_fitter = CurveFitter(line_tolerance, arc_tolerance, preserve_geometry)
    writer = OpenDriveWriter(project, transformer, curve_fitter, right_hand_traffic, country_code)
    return writer.write(output_path)

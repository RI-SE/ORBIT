"""
OpenDrive XML writer for ORBIT.

Generates ASAM OpenDrive format XML from annotated roads and junctions.
"""

from typing import List, Dict, Optional, Tuple
from datetime import datetime
from lxml import etree
import numpy as np
import math

from orbit.utils.logging_config import get_logger
from orbit.models import Project, Road, Junction, Polyline, LineType
from orbit.models.connecting_road import ConnectingRoad
from orbit.utils import CoordinateTransformer

from .curve_fitting import CurveFitter, GeometryElement, GeometryType
from .lane_analyzer import LaneAnalyzer
from .lane_builder import LaneBuilder
from .signal_builder import SignalBuilder
from .object_builder import ObjectBuilder

logger = get_logger(__name__)


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

        # Junction numeric IDs (assigned during export)
        self.junction_numeric_ids = {}

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

        # Initialize builders
        self.lane_builder = LaneBuilder(scale_x=self.scale_x)
        self.signal_builder = SignalBuilder(scale_x=self.scale_x, country_code=country_code)
        self.object_builder = ObjectBuilder(
            scale_x=self.scale_x,
            transformer=transformer,
            curve_fitter=self.curve_fitter,
            polyline_map=self.polyline_map
        )

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
            logger.error(f"Error writing OpenDrive: {e}")
            return False

    def _create_opendrive_root(self) -> etree.Element:
        """Create the root OpenDRIVE element with all content."""
        root = etree.Element('OpenDRIVE')

        # Add header
        header = self._create_header()
        root.append(header)

        # Assign numeric IDs to junctions (sequential)
        self.junction_numeric_ids = {}
        for idx, junction in enumerate(self.project.junctions):
            if junction.is_valid():
                # Use opendrive_id if set, otherwise sequential numbering
                if junction.opendrive_id and junction.opendrive_id.isdigit():
                    self.junction_numeric_ids[junction.id] = int(junction.opendrive_id)
                else:
                    self.junction_numeric_ids[junction.id] = idx + 1

        # Export order:
        # 1. Regular roads (junction="-1")
        # 2. Connecting roads for each junction (junction="<id>")
        # 3. Junction definitions

        # 1. Add regular roads (non-junction roads)
        for road in self.project.roads:
            if road.is_valid() and not road.junction_id:
                road_elem = self._create_road(road)
                if road_elem is not None:
                    root.append(road_elem)

        # 2. Add connecting roads for each junction
        for junction in self.project.junctions:
            if junction.is_valid():
                junction_numeric_id = self.junction_numeric_ids.get(junction.id)
                if junction_numeric_id is None:
                    continue

                # Skip connecting roads for virtual junctions (path crossings)
                if junction.junction_type == "virtual":
                    continue

                # Export each connecting road as a Road element
                for idx, connecting_road in enumerate(junction.connecting_roads):
                    conn_road_elem = self._create_connecting_road(
                        connecting_road,
                        junction_numeric_id
                    )
                    if conn_road_elem is not None:
                        root.append(conn_road_elem)
                    else:
                        logger.warning(f"Connecting road {idx} for junction {junction_numeric_id} returned None!")

        # 3. Add junction definitions
        for junction in self.project.junctions:
            if junction.is_valid():
                junction_numeric_id = self.junction_numeric_ids.get(junction.id)
                if junction_numeric_id is None:
                    continue

                junction_elem = self._create_junction(junction, junction_numeric_id)
                if junction_elem is not None:
                    root.append(junction_elem)

        return root

    def _find_junction_for_road_endpoint(self, road_id: str, is_predecessor: bool) -> Optional[int]:
        """
        Find if a road endpoint connects to a junction.

        Args:
            road_id: ID of the road
            is_predecessor: True to check predecessor end, False for successor end

        Returns:
            Junction numeric ID if road endpoint is at a junction, None otherwise
        """
        # Get the road and its centerline
        road = self.road_map.get(road_id)
        if not road or not road.centerline_id:
            return None

        centerline = self.polyline_map.get(road.centerline_id)
        if not centerline or len(centerline.points) < 2:
            return None

        # Get the endpoint we're checking
        check_point = centerline.points[0] if is_predecessor else centerline.points[-1]

        # Check each junction to see if THIS endpoint is at the junction
        for junction in self.project.junctions:
            if road_id not in junction.connected_road_ids:
                continue

            if not junction.center_point:
                continue

            # Calculate distance from endpoint to junction center
            dx = check_point[0] - junction.center_point[0]
            dy = check_point[1] - junction.center_point[1]
            dist = math.sqrt(dx*dx + dy*dy)

            # If within tolerance (15 pixels), this endpoint is at this junction
            # Using 15 pixels to account for offset that will be applied
            if dist < 15.0:
                junction_numeric_id = self.junction_numeric_ids.get(junction.id)
                if junction_numeric_id is not None:
                    return junction_numeric_id

        return None

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
        tool_data.text = 'Produced by ORBIT (https://github.com/fwrise/ORBIT)'

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

        # Check if this road connects to a junction
        predecessor_junction = self._find_junction_for_road_endpoint(road.id, is_predecessor=True)
        successor_junction = self._find_junction_for_road_endpoint(road.id, is_predecessor=False)

        # Add predecessor - check if junction or road
        if predecessor_junction is not None:
            # Road predecessor connects to a junction
            predecessor = etree.SubElement(link, 'predecessor')
            predecessor.set('elementType', 'junction')
            predecessor.set('elementId', str(predecessor_junction))
            # No contactPoint for junction links
        elif road.predecessor_id:
            # Road predecessor connects to another road
            predecessor = etree.SubElement(link, 'predecessor')
            predecessor.set('elementType', 'road')
            predecessor.set('elementId', road.predecessor_id)
            predecessor.set('contactPoint', road.predecessor_contact)

        # Add successor - check if junction or road
        if successor_junction is not None:
            # Road successor connects to a junction
            successor = etree.SubElement(link, 'successor')
            successor.set('elementType', 'junction')
            successor.set('elementId', str(successor_junction))
            # No contactPoint for junction links
        elif road.successor_id:
            # Road successor connects to another road
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

        # Add elevation profile (use stored profile or flat)
        elevation = etree.SubElement(road_elem, 'elevationProfile')
        if road.elevation_profile:
            # Use stored elevation polynomials for round-trip preservation
            for elev_data in road.elevation_profile:
                s, a, b, c, d = elev_data
                elev = etree.SubElement(elevation, 'elevation')
                elev.set('s', f'{s:.6g}')
                elev.set('a', f'{a:.6g}')
                elev.set('b', f'{b:.6g}')
                elev.set('c', f'{c:.6g}')
                elev.set('d', f'{d:.6g}')
        else:
            # Default flat profile
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
        lanes = self.lane_builder.create_lanes(road, road_length, boundary_infos)
        road_elem.append(lanes)

        # Add signals for this road
        signals = self.signal_builder.create_signals(road, self.project.signals, centerline_points_pixel)
        if signals is not None:
            road_elem.append(signals)

        # Add objects for this road
        objects = self.object_builder.create_objects(road, self.project.objects, centerline_points_pixel)
        if objects is not None:
            road_elem.append(objects)

        return road_elem

    def _create_connecting_road(self, connecting_road: ConnectingRoad,
                               junction_numeric_id: int) -> Optional[etree.Element]:
        """
        Create a road element for a junction connecting road.

        Args:
            connecting_road: ConnectingRoad object with path and lane configuration
            junction_numeric_id: Numeric ID of the junction this road belongs to

        Returns:
            Road XML element with junction="<junction_id>", or None if invalid
        """
        if not connecting_road.path or len(connecting_road.path) < 2:
            return None

        # Use road_id if set, otherwise generate one
        road_id = connecting_road.road_id
        if road_id is None:
            # Generate road ID: junction_id * 1000 + hash of connecting_road.id
            road_id = junction_numeric_id * 1000 + (hash(connecting_road.id) % 1000)
            connecting_road.road_id = road_id  # Store for future reference

        # Transform path points from pixels to meters
        path_meters = self.transformer.pixels_to_meters_batch(connecting_road.path)

        # Check if connecting road has ParamPoly3D geometry
        if connecting_road.geometry_type == "parampoly3":
            # Calculate ParamPoly3D coefficients in LOCAL coordinate system
            # Local u/v coordinates have origin at start point with u-axis along heading

            # Get start and end points in meters (global coordinates)
            start_point_meters = path_meters[0]
            end_point_meters = path_meters[-1]

            # Get headings - use stored pixel headings transformed to meter coordinates
            # for accurate tangent matching, with fallback to path approximation
            if connecting_road.stored_start_heading is not None:
                # Transform stored pixel heading to meter coordinates
                start_heading = self.transformer.transform_heading(
                    connecting_road.path[0][0],  # pixel x
                    connecting_road.path[0][1],  # pixel y
                    connecting_road.stored_start_heading
                )
            elif len(path_meters) >= 2:
                # Fallback: approximate from path (for legacy data)
                dx_start = path_meters[1][0] - path_meters[0][0]
                dy_start = path_meters[1][1] - path_meters[0][1]
                start_heading = math.atan2(dy_start, dx_start)
            else:
                start_heading = 0.0

            if connecting_road.stored_end_heading is not None:
                end_heading = self.transformer.transform_heading(
                    connecting_road.path[-1][0],
                    connecting_road.path[-1][1],
                    connecting_road.stored_end_heading
                )
            elif len(path_meters) >= 2:
                dx_end = path_meters[-1][0] - path_meters[-2][0]
                dy_end = path_meters[-1][1] - path_meters[-2][1]
                end_heading = math.atan2(dy_end, dx_end)
            else:
                end_heading = 0.0

            # Transform end point from global to local u/v coordinates
            # Local frame: origin at start_point, u-axis along start_heading, v-axis 90° CCW
            dx_global = end_point_meters[0] - start_point_meters[0]
            dy_global = end_point_meters[1] - start_point_meters[1]

            cos_h = math.cos(start_heading)
            sin_h = math.sin(start_heading)

            # Rotate to local frame: [u] = [cos  sin] [dx]
            #                         [v]   [-sin cos] [dy]
            end_u = dx_global * cos_h + dy_global * sin_h
            end_v = -dx_global * sin_h + dy_global * cos_h

            # Transform end tangent to local frame
            # End tangent direction in global frame
            end_tangent_x_global = math.cos(end_heading)
            end_tangent_y_global = math.sin(end_heading)

            # Rotate to local frame
            end_tangent_u = end_tangent_x_global * cos_h + end_tangent_y_global * sin_h
            end_tangent_v = -end_tangent_x_global * sin_h + end_tangent_y_global * cos_h

            # Compute Bezier curve in LOCAL space (with Hermite fallback)
            # Start: (0, 0) with tangent (1, 0) - aligned with u-axis
            # End: (end_u, end_v) with tangent (end_tangent_u, end_tangent_v)
            from orbit.utils.geometry import (
                calculate_bezier_control_points,
                bezier_to_parampoly3,
                calculate_hermite_parampoly3
            )

            # Try Bezier control point calculation first
            control_points = calculate_bezier_control_points(
                (0.0, 0.0),  # Start at local origin
                (1.0, 0.0),  # Start tangent aligned with u-axis
                (end_u, end_v),  # End point in local coordinates
                (end_tangent_u, end_tangent_v)  # End tangent in local frame
            )

            if control_points is not None:
                # Success: use Bezier curve
                # Since we're already in local coordinates, heading is 0
                aU, bU, cU, dU, aV, bV, cV, dV = bezier_to_parampoly3(control_points, 0.0)
            else:
                # Fallback: use Hermite interpolation with tangent_scale
                aU, bU, cU, dU, aV, bV, cV, dV = calculate_hermite_parampoly3(
                    (0.0, 0.0),  # Start at local origin
                    (1.0, 0.0),  # Start tangent aligned with u-axis
                    (end_u, end_v),  # End point in local coordinates
                    (end_tangent_u, end_tangent_v),  # End tangent in local frame
                    tangent_scale=connecting_road.tangent_scale
                )

            # Calculate road length from sampled path
            road_length = 0.0
            for i in range(len(path_meters) - 1):
                dx = path_meters[i+1][0] - path_meters[i][0]
                dy = path_meters[i+1][1] - path_meters[i][1]
                road_length += math.sqrt(dx*dx + dy*dy)

            # Create ParamPoly3 geometry element with LOCAL coefficients
            geometry_elements = [
                GeometryElement(
                    geom_type=GeometryType.PARAMPOLY3,
                    start_pos=start_point_meters,  # Global position
                    heading=start_heading,  # Global heading
                    length=road_length,
                    aU=aU, bU=bU, cU=cU, dU=dU,  # Local u/v coefficients
                    aV=aV, bV=bV, cV=cV, dV=dV,
                    p_range=1.0,
                    p_range_normalized=connecting_road.p_range_normalized
                )
            ]
        else:
            # Fit geometry to the path (legacy polyline mode)
            geometry_elements = self.curve_fitter.fit_polyline(path_meters)

            if not geometry_elements:
                return None

            # Calculate total road length
            road_length = sum(elem.length for elem in geometry_elements)

        # Create road element
        road_elem = etree.Element('road')
        road_elem.set('id', str(road_id))
        road_elem.set('name', '')  # Connecting roads typically have no name
        road_elem.set('length', f'{road_length:.4f}')
        road_elem.set('junction', str(junction_numeric_id))

        # Add road link with predecessor/successor
        link = etree.SubElement(road_elem, 'link')

        # Add predecessor (incoming road)
        if connecting_road.predecessor_road_id:
            predecessor = etree.SubElement(link, 'predecessor')
            predecessor.set('elementType', 'road')
            predecessor.set('elementId', connecting_road.predecessor_road_id)
            predecessor.set('contactPoint', connecting_road.contact_point_start)

        # Add successor (outgoing road)
        if connecting_road.successor_road_id:
            successor = etree.SubElement(link, 'successor')
            successor.set('elementType', 'road')
            successor.set('elementId', connecting_road.successor_road_id)
            successor.set('contactPoint', connecting_road.contact_point_end)

        # Add road type (junction internal road)
        type_elem = etree.SubElement(road_elem, 'type')
        type_elem.set('s', '0.0')
        type_elem.set('type', 'town')  # Default type for junction roads

        # Add plan view (reference line geometry)
        plan_view = self._create_plan_view(geometry_elements)
        road_elem.append(plan_view)

        # Add elevation profile (flat)
        elevation = etree.SubElement(road_elem, 'elevationProfile')
        elev = etree.SubElement(elevation, 'elevation')
        elev.set('s', '0.0')
        elev.set('a', '0.0')
        elev.set('b', '0.0')
        elev.set('c', '0.0')
        elev.set('d', '0.0')

        # Add lateral profile (no superelevation)
        lateral = etree.SubElement(road_elem, 'lateralProfile')

        # Add lanes (simplified - no boundary analysis for connecting roads)
        lanes = self._create_connecting_road_lanes(connecting_road, road_length)
        road_elem.append(lanes)

        # No signals or objects for connecting roads

        return road_elem

    def _create_connecting_road_lanes(self, connecting_road: ConnectingRoad,
                                     road_length: float) -> etree.Element:
        """
        Create simplified lanes element for a connecting road.

        Supports linear lane width transitions when lane_width_start and lane_width_end
        are set (OpenDRIVE polynomial: width(s) = a + b*s).

        Args:
            connecting_road: ConnectingRoad with lane configuration
            road_length: Total length of the road in meters

        Returns:
            Lanes XML element
        """
        lanes = etree.Element('lanes')

        # Single lane section covering the entire connecting road
        lane_section = etree.SubElement(lanes, 'laneSection')
        lane_section.set('s', '0.0')

        # Center lane (always required)
        center = etree.SubElement(lane_section, 'center')
        center_lane = etree.SubElement(center, 'lane')
        center_lane.set('id', '0')
        center_lane.set('type', 'none')
        center_lane.set('level', 'false')

        # Calculate lane width polynomial coefficients for linear transition
        # width(s) = a + b*s + c*s² + d*s³
        # For linear transition: a = start_width, b = (end_width - start_width) / length
        width_start = connecting_road.lane_width_start
        width_end = connecting_road.lane_width_end

        if width_start is not None and width_end is not None and road_length > 0:
            # Linear transition from start to end width
            width_a = width_start
            width_b = (width_end - width_start) / road_length
        else:
            # Constant width (backward compatibility)
            width_a = connecting_road.lane_width
            width_b = 0.0

        # Left lanes (positive IDs: 1, 2, 3...)
        if connecting_road.lane_count_left > 0:
            left = etree.SubElement(lane_section, 'left')
            for lane_id in range(1, connecting_road.lane_count_left + 1):
                lane = etree.SubElement(left, 'lane')
                lane.set('id', str(lane_id))
                lane.set('type', 'driving')
                lane.set('level', 'false')

                # Lane width (linear transition)
                width = etree.SubElement(lane, 'width')
                width.set('sOffset', '0.0')
                width.set('a', f'{width_a:.4f}')
                width.set('b', f'{width_b:.6f}')
                width.set('c', '0.0')
                width.set('d', '0.0')

                # Road mark (default: solid white)
                roadMark = etree.SubElement(lane, 'roadMark')
                roadMark.set('sOffset', '0.0')
                roadMark.set('type', 'solid')
                roadMark.set('weight', 'standard')
                roadMark.set('color', 'white')
                roadMark.set('width', '0.12')

        # Right lanes (negative IDs: -1, -2, -3...)
        if connecting_road.lane_count_right > 0:
            right = etree.SubElement(lane_section, 'right')
            for lane_id in range(-1, -(connecting_road.lane_count_right + 1), -1):
                lane = etree.SubElement(right, 'lane')
                lane.set('id', str(lane_id))
                lane.set('type', 'driving')
                lane.set('level', 'false')

                # Lane width (linear transition)
                width = etree.SubElement(lane, 'width')
                width.set('sOffset', '0.0')
                width.set('a', f'{width_a:.4f}')
                width.set('b', f'{width_b:.6f}')
                width.set('c', '0.0')
                width.set('d', '0.0')

                # Road mark (default: solid white)
                roadMark = etree.SubElement(lane, 'roadMark')
                roadMark.set('sOffset', '0.0')
                roadMark.set('type', 'solid')
                roadMark.set('weight', 'standard')
                roadMark.set('color', 'white')
                roadMark.set('width', '0.12')

        return lanes

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
            elif geom.geom_type == GeometryType.PARAMPOLY3:
                parampoly3 = etree.SubElement(geometry, 'paramPoly3')
                parampoly3.set('aU', f'{geom.aU:.10f}')
                parampoly3.set('bU', f'{geom.bU:.10f}')
                parampoly3.set('cU', f'{geom.cU:.10f}')
                parampoly3.set('dU', f'{geom.dU:.10f}')
                parampoly3.set('aV', f'{geom.aV:.10f}')
                parampoly3.set('bV', f'{geom.bV:.10f}')
                parampoly3.set('cV', f'{geom.cV:.10f}')
                parampoly3.set('dV', f'{geom.dV:.10f}')
                # Use "normalized" string if p_range_normalized is True (OpenDRIVE standard)
                if geom.p_range_normalized:
                    parampoly3.set('pRange', 'normalized')
                else:
                    parampoly3.set('pRange', f'{geom.p_range:.4f}')

            s_offset += geom.length

        return plan_view

    def _create_junction(self, junction: Junction, junction_numeric_id: int) -> Optional[etree.Element]:
        """
        Create a junction element.

        Args:
            junction: Junction object with connecting roads and lane connections
            junction_numeric_id: Numeric ID for this junction in OpenDRIVE

        Returns:
            Junction XML element, or None if invalid
        """
        if len(junction.connected_road_ids) < 2:
            return None

        junction_elem = etree.Element('junction')
        junction_elem.set('id', str(junction_numeric_id))
        junction_elem.set('name', junction.name)
        junction_elem.set('type', junction.junction_type)

        # Virtual junctions (path crossings) have no connections
        if junction.junction_type == "virtual":
            return junction_elem

        # Group lane connections by (from_road_id, connecting_road_id) to create connection elements
        # Each unique pair becomes one <connection> with multiple <laneLink> elements
        connection_groups = {}
        for lane_conn in junction.lane_connections:
            key = (lane_conn.from_road_id, lane_conn.connecting_road_id)
            if key not in connection_groups:
                connection_groups[key] = []
            connection_groups[key].append(lane_conn)

        # Create connection elements
        connection_id = 0
        for (from_road_id, connecting_road_uuid), lane_connections in connection_groups.items():
            # Find the connecting road to get its numeric road_id
            connecting_road = junction.get_connecting_road_by_id(connecting_road_uuid)
            if not connecting_road or connecting_road.road_id is None:
                # Skip if connecting road not found or doesn't have numeric ID
                continue

            connection = etree.SubElement(junction_elem, 'connection')
            connection.set('id', str(connection_id))
            connection.set('incomingRoad', from_road_id)
            connection.set('connectingRoad', str(connecting_road.road_id))
            connection.set('contactPoint', 'start')  # Connecting roads start at junction

            # Add priority if available (use highest priority in group)
            if lane_connections:
                max_priority = max(lc.priority for lc in lane_connections if lc.priority is not None)
                if max_priority is not None and max_priority > 0:
                    connection.set('priority', str(max_priority))

            # Add lane links for this connection
            for lane_conn in lane_connections:
                lane_link = etree.SubElement(connection, 'laneLink')
                lane_link.set('from', str(lane_conn.from_lane_id))
                lane_link.set('to', str(lane_conn.to_lane_id))

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

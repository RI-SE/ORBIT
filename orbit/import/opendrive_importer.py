"""
OpenDrive importer orchestrator for ORBIT.

Coordinates the full OpenDrive import process: parse, transform, and create ORBIT objects.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Set, Tuple
from enum import Enum
import uuid
import math

from orbit.models import Project, Road, Junction, Signal, RoadObject, Polyline, ControlPoint
from orbit.models.polyline import LineType, RoadMarkType
from orbit.models.road import RoadType, LaneInfo
from orbit.models.lane import Lane, LaneType as ORBITLaneType
from orbit.models.lane_section import LaneSection
from orbit.models.junction import JunctionConnection
from orbit.models.connecting_road import ConnectingRoad
from orbit.models.lane_connection import LaneConnection
from orbit.models.signal import SignalType, SpeedUnit
from orbit.models.object import ObjectType

from .opendrive_parser import OpenDriveParser, OpenDriveData, ODRRoad, ODRLane, ODRSignal, ODRObject
from .opendrive_geometry import GeometryConverter, calculate_s_offsets, sample_elevation_profile
from .opendrive_coordinate_transform import OpenDriveCoordinateTransform, TransformMode, batch_metric_to_pixel


class ImportMode(Enum):
    """Import mode: add to existing or replace."""
    ADD = "add"
    REPLACE = "replace"


@dataclass
class ImportOptions:
    """Options for OpenDrive import."""
    import_mode: ImportMode = ImportMode.ADD
    scale_pixels_per_meter: float = 10.0  # For synthetic mode
    auto_create_control_points: bool = False  # Auto-create georeferencing control points
    verbose: bool = False  # Print debug information


@dataclass
class ImportResult:
    """Result of OpenDrive import operation."""
    success: bool = False
    error_message: Optional[str] = None

    # Imported counts
    roads_imported: int = 0
    connecting_roads_imported: int = 0
    junctions_imported: int = 0
    signals_imported: int = 0
    objects_imported: int = 0
    polylines_imported: int = 0
    control_points_created: int = 0

    # Skipped/converted
    roads_skipped_duplicate: int = 0
    geometry_conversions: List[str] = field(default_factory=list)

    # Unsupported features skipped
    features_skipped: Dict[str, int] = field(default_factory=dict)
    elevation_profiles_imported: int = 0

    # Warnings
    warnings: List[str] = field(default_factory=list)

    # Transform info
    transform_mode: Optional[str] = None
    scale_used: Optional[float] = None


class OpenDriveImporter:
    """Main OpenDrive import orchestrator."""

    def __init__(
        self,
        project: Project,
        orbit_transformer,  # CoordinateTransformer from export module
        image_width: int,
        image_height: int
    ):
        """
        Initialize OpenDrive importer.

        Args:
            project: ORBIT project to import into
            orbit_transformer: ORBIT CoordinateTransformer (if available)
            image_width: Width of image in pixels
            image_height: Height of image in pixels
        """
        self.project = project
        self.orbit_transformer = orbit_transformer
        self.image_width = image_width
        self.image_height = image_height

        # Parsed OpenDrive data
        self.odr_data: Optional[OpenDriveData] = None

        # Coordinate transformer
        self.coord_transform: Optional[OpenDriveCoordinateTransform] = None

        # Geometry converter
        self.geom_converter = GeometryConverter(sampling_interval=1.0)

        # Mapping from OpenDrive IDs to ORBIT IDs
        self.odr_road_to_orbit: Dict[str, str] = {}  # ODR road ID -> ORBIT road ID
        self.odr_junction_to_orbit: Dict[str, str] = {}  # ODR junction ID -> ORBIT junction ID

        # Track imported OpenDrive IDs for duplicate detection
        self.imported_odr_road_ids: Set[str] = set()

        # Pending connecting roads (deferred until after junction import)
        self.pending_connecting_roads: List[Dict] = []

    def import_from_file(
        self,
        file_path: str,
        options: Optional[ImportOptions] = None
    ) -> ImportResult:
        """
        Import OpenDrive data from file.

        Args:
            file_path: Path to .xodr file
            options: Import options

        Returns:
            ImportResult with statistics and status
        """
        if options is None:
            options = ImportOptions()

        result = ImportResult()

        # Clear state from previous imports
        self.pending_connecting_roads.clear()
        self.odr_road_to_orbit.clear()
        self.odr_junction_to_orbit.clear()
        self.imported_odr_road_ids.clear()

        # Step 1: Parse OpenDrive file
        if options.verbose:
            print(f"Parsing OpenDrive file: {file_path}")

        parser = OpenDriveParser()
        try:
            self.odr_data = parser.parse_file(file_path)
        except Exception as e:
            result.error_message = f"Failed to parse OpenDrive file: {e}"
            return result

        if options.verbose:
            print(f"Parsed {len(self.odr_data.roads)} roads, {len(self.odr_data.junctions)} junctions")

        # Step 2: Setup coordinate transformation
        # Collect sample points from all roads
        sample_points = self._collect_sample_points()

        self.coord_transform = OpenDriveCoordinateTransform(
            image_width=self.image_width,
            image_height=self.image_height,
            orbit_transformer=self.orbit_transformer,
            opendrive_geo_reference=self.odr_data.geo_reference,
            scale_pixels_per_meter=options.scale_pixels_per_meter,
            header_offset_x=self.odr_data.header.offset_x,
            header_offset_y=self.odr_data.header.offset_y,
            header_offset_z=self.odr_data.header.offset_z,
            header_offset_hdg=self.odr_data.header.offset_hdg
        )

        transform_result = self.coord_transform.setup_transform(sample_points)
        result.transform_mode = transform_result.mode
        result.scale_used = transform_result.scale_pixels_per_meter

        if not transform_result.success:
            # Need user action for auto-georeference
            if transform_result.mode == TransformMode.AUTO_GEOREFERENCE:
                if options.auto_create_control_points and transform_result.suggested_control_points:
                    # Auto-create control points
                    for px, py, lon, lat in transform_result.suggested_control_points:
                        cp = ControlPoint(
                            pixel_x=px,
                            pixel_y=py,
                            longitude=lon,
                            latitude=lat,
                            name=f"Auto-generated from OpenDrive"
                        )
                        self.project.control_points.append(cp)
                        result.control_points_created += 1

                    # Retry transform setup with control points
                    # (Would need to create new transformer from control points here)
                    result.warnings.append(
                        f"Created {result.control_points_created} control points from OpenDrive georeferencing"
                    )
                else:
                    result.error_message = transform_result.error_message
                    return result

        if options.verbose:
            print(f"Transform mode: {result.transform_mode}, scale: {result.scale_used}")

        # Step 3: Handle import mode
        if options.import_mode == ImportMode.REPLACE:
            # Clear existing data
            self.project.polylines.clear()
            self.project.roads.clear()
            self.project.junctions.clear()
            self.project.signals.clear()
            self.project.objects.clear()

        # Step 4: Import roads (connecting roads are deferred)
        for odr_road in self.odr_data.roads:
            if self._should_skip_road(odr_road, options):
                result.roads_skipped_duplicate += 1
                continue

            try:
                road_result = self._import_road(odr_road, options)
                if road_result:
                    # Connecting roads are counted separately after junction import
                    if not road_result.get('is_connecting_road', False):
                        result.roads_imported += 1
                        result.polylines_imported += road_result['polylines_count']
                        result.geometry_conversions.extend(road_result['conversions'])
                        if road_result['has_elevation']:
                            result.elevation_profiles_imported += 1

            except Exception as e:
                result.warnings.append(f"Failed to import road {odr_road.id}: {e}")
                if options.verbose:
                    print(f"Error importing road {odr_road.id}: {e}")

        # Step 5: Import junctions
        for odr_junction in self.odr_data.junctions:
            try:
                if self._import_junction(odr_junction, options, result):
                    result.junctions_imported += 1
            except Exception as e:
                result.warnings.append(f"Failed to import junction {odr_junction.id}: {e}")

        # Step 5b: Assign junction center points (handles multiple junctions between same road pairs)
        try:
            self._assign_junction_center_points(result)
        except Exception as e:
            result.warnings.append(f"Failed to assign junction center points: {e}")

        # Step 5c: Process deferred connecting roads (now that junctions exist)
        for pending in self.pending_connecting_roads:
            try:
                if self._import_connecting_road(pending, options, result):
                    result.connecting_roads_imported += 1
            except Exception as e:
                odr_road = pending['odr_road']
                result.warnings.append(f"Failed to import connecting road {odr_road.id}: {e}")
                if options.verbose:
                    print(f"Error importing connecting road {odr_road.id}: {e}")

        # Step 6: Import signals and objects
        for odr_road in self.odr_data.roads:
            road_id = self.odr_road_to_orbit.get(odr_road.id)
            if not road_id:
                continue

            # Import signals
            for odr_signal in odr_road.signals:
                try:
                    if self._import_signal(odr_signal, road_id, odr_road, options):
                        result.signals_imported += 1
                except Exception as e:
                    result.warnings.append(f"Failed to import signal {odr_signal.id}: {e}")

            # Import objects
            for odr_object in odr_road.objects:
                try:
                    if self._import_object(odr_object, road_id, odr_road, options):
                        result.objects_imported += 1
                except Exception as e:
                    result.warnings.append(f"Failed to import object {odr_object.id}: {e}")

        # Step 7: Track unsupported features
        self._track_unsupported_features(result)

        # Step 8: Preserve geoReference for round-trip export
        if self.odr_data.geo_reference:
            self.project.imported_geo_reference = self.odr_data.geo_reference

        # Step 9: Clear stale cross-junction road links
        # Roads in junctions should not have predecessor/successor pointing to each other
        self.project.clear_cross_junction_road_links()

        result.success = True
        return result

    def _collect_sample_points(self) -> List[tuple]:
        """Collect sample points from all roads for transform setup."""
        sample_points = []

        for road in self.odr_data.roads:
            for geom in road.geometry:
                sample_points.append((geom.x, geom.y))

        return sample_points

    def _should_skip_road(self, odr_road: ODRRoad, options: ImportOptions) -> bool:
        """Check if road should be skipped (duplicate detection)."""
        if options.import_mode == ImportMode.REPLACE:
            return False

        # Check if already imported by OpenDrive ID
        if odr_road.id in self.imported_odr_road_ids:
            return True

        return False

    def _import_road(self, odr_road: ODRRoad, options: ImportOptions) -> Optional[Dict]:
        """
        Import a single road from OpenDrive.

        Connecting roads (roads with junction attribute != -1) are deferred for
        processing after junctions are imported.

        Returns:
            Dict with import statistics, or None if failed
        """
        if not odr_road.geometry:
            return None

        # Check if this is a connecting road (belongs to a junction)
        is_connecting_road = odr_road.junction_id and odr_road.junction_id != "-1"

        if is_connecting_road:
            # Defer connecting road for processing after junctions are imported
            self._defer_connecting_road(odr_road, options)
            return {
                'polylines_count': 0,
                'conversions': [],
                'has_elevation': False,
                'is_connecting_road': True
            }

        # Convert geometry to polyline points (metric)
        points_metric, conversions = self.geom_converter.convert_geometry_to_polyline(odr_road.geometry)

        if not points_metric or len(points_metric) < 2:
            return None

        # Calculate s-offsets along polyline
        s_offsets_metric = calculate_s_offsets(points_metric)

        # Sample elevation profile if available
        elevations = None
        has_elevation = False
        if odr_road.elevation_profile:
            elevations = sample_elevation_profile(s_offsets_metric, odr_road.elevation_profile)
            has_elevation = True

        # Transform to pixel coordinates
        points_pixel = batch_metric_to_pixel(points_metric, self.coord_transform)

        # Calculate s-offsets in pixel space (for ORBIT internal use)
        s_offsets_pixel = calculate_s_offsets(points_pixel)

        # Create centerline polyline
        centerline_id = str(uuid.uuid4())
        centerline = Polyline(
            id=centerline_id,
            points=points_pixel,
            color=(255, 0, 0),  # Red for centerline
            line_type=LineType.CENTERLINE,
            elevations=elevations,
            s_offsets=s_offsets_pixel,
            opendrive_id=odr_road.id
        )
        self.project.polylines.append(centerline)

        # Create road
        road_id = str(uuid.uuid4())
        road_name = odr_road.name if odr_road.name else f"Road {odr_road.id}"

        road = Road(
            id=road_id,
            name=road_name,
            polyline_ids=[centerline_id],
            centerline_id=centerline_id,
            road_type=self._convert_road_type(odr_road.road_type),
            opendrive_id=odr_road.id
        )

        # Set predecessor/successor links
        if odr_road.predecessor_type == "road" and odr_road.predecessor_id:
            road.predecessor_id = odr_road.predecessor_id  # Will be resolved later
            road.predecessor_contact = odr_road.predecessor_contact or "end"

        if odr_road.successor_type == "road" and odr_road.successor_id:
            road.successor_id = odr_road.successor_id  # Will be resolved later
            road.successor_contact = odr_road.successor_contact or "start"

        # Store elevation profile for round-trip preservation
        if odr_road.elevation_profile and odr_road.elevation_profile.elevations:
            road.elevation_profile = odr_road.elevation_profile.elevations

        # Import lane sections
        if odr_road.lane_sections:
            road.lane_sections = self._import_lane_sections(
                odr_road.lane_sections,
                odr_road.length,
                points_pixel
            )
        else:
            # No lane sections - generate default
            road.generate_lanes()

        self.project.roads.append(road)

        # Track mapping
        self.odr_road_to_orbit[odr_road.id] = road_id
        self.imported_odr_road_ids.add(odr_road.id)

        return {
            'polylines_count': 1,
            'conversions': conversions,
            'has_elevation': has_elevation
        }

    def _defer_connecting_road(self, odr_road: ODRRoad, options: ImportOptions) -> None:
        """
        Defer a connecting road for processing after junctions are imported.

        Stores the raw OpenDrive data including geometry parameters (paramPoly3).
        """
        from .opendrive_parser import GeometryType

        # Extract paramPoly3 coefficients if available
        param_poly3_data = None
        if odr_road.geometry and len(odr_road.geometry) == 1:
            geom = odr_road.geometry[0]
            if geom.geometry_type == GeometryType.PARAM_POLY3:
                param_poly3_data = {
                    'aU': geom.params.get('aU', 0.0),
                    'bU': geom.params.get('bU', 0.0),
                    'cU': geom.params.get('cU', 0.0),
                    'dU': geom.params.get('dU', 0.0),
                    'aV': geom.params.get('aV', 0.0),
                    'bV': geom.params.get('bV', 0.0),
                    'cV': geom.params.get('cV', 0.0),
                    'dV': geom.params.get('dV', 0.0),
                    'pRange': geom.params.get('pRange', 'arcLength'),
                    'x': geom.x,
                    'y': geom.y,
                    'hdg': geom.hdg,
                    'length': geom.length
                }

        # Convert geometry to polyline points for visualization
        points_metric, _ = self.geom_converter.convert_geometry_to_polyline(odr_road.geometry)
        points_pixel = batch_metric_to_pixel(points_metric, self.coord_transform) if points_metric else []

        # Store for later processing
        self.pending_connecting_roads.append({
            'odr_road': odr_road,
            'junction_id': odr_road.junction_id,
            'param_poly3': param_poly3_data,
            'points_pixel': points_pixel,
            'options': options
        })

    def _import_connecting_road(
        self,
        pending: Dict,
        options: ImportOptions,
        result: ImportResult
    ) -> bool:
        """
        Import a deferred connecting road and add it to its parent junction.

        Args:
            pending: Pending connecting road data from _defer_connecting_road
            options: Import options
            result: Import result for warnings

        Returns:
            True if successfully imported, False otherwise
        """
        odr_road: ODRRoad = pending['odr_road']
        junction_odr_id = pending['junction_id']
        param_poly3 = pending['param_poly3']
        points_pixel = pending['points_pixel']

        if not points_pixel or len(points_pixel) < 2:
            result.warnings.append(
                f"Connecting road {odr_road.id}: insufficient geometry points"
            )
            return False

        # Find the parent junction by OpenDrive ID
        junction_orbit_id = self.odr_junction_to_orbit.get(junction_odr_id)
        if not junction_orbit_id:
            result.warnings.append(
                f"Connecting road {odr_road.id}: junction {junction_odr_id} not found"
            )
            return False

        junction = self.project.get_junction(junction_orbit_id)
        if not junction:
            result.warnings.append(
                f"Connecting road {odr_road.id}: junction {junction_orbit_id} not in project"
            )
            return False

        # Get predecessor/successor road IDs (map ODR IDs to ORBIT IDs)
        predecessor_orbit_id = ""
        successor_orbit_id = ""
        contact_point_start = "end"
        contact_point_end = "start"

        if odr_road.predecessor_type == "road" and odr_road.predecessor_id:
            predecessor_orbit_id = self.odr_road_to_orbit.get(odr_road.predecessor_id, "")
            contact_point_start = odr_road.predecessor_contact or "end"

        if odr_road.successor_type == "road" and odr_road.successor_id:
            successor_orbit_id = self.odr_road_to_orbit.get(odr_road.successor_id, "")
            contact_point_end = odr_road.successor_contact or "start"

        # Determine lane counts from lane sections
        lane_count_left = 0
        lane_count_right = 0
        lane_width = 3.5  # Default

        if odr_road.lane_sections:
            first_section = odr_road.lane_sections[0]
            for odr_lane in first_section.left_lanes:
                if odr_lane.type in ("driving", "biking", "sidewalk", "parking"):
                    lane_count_left += 1
            for odr_lane in first_section.right_lanes:
                if odr_lane.type in ("driving", "biking", "sidewalk", "parking"):
                    lane_count_right += 1

            # Get lane width from first non-center lane
            all_lanes = first_section.left_lanes + first_section.right_lanes
            for odr_lane in all_lanes:
                if odr_lane.widths:
                    lane_width = odr_lane.widths[0].a
                    break

        # Ensure at least one lane
        if lane_count_left == 0 and lane_count_right == 0:
            lane_count_right = 1

        # Create connecting road
        connecting_road = ConnectingRoad(
            id=str(uuid.uuid4()),
            path=points_pixel,
            lane_count_left=lane_count_left,
            lane_count_right=lane_count_right,
            lane_width=lane_width,
            predecessor_road_id=predecessor_orbit_id,
            successor_road_id=successor_orbit_id,
            contact_point_start=contact_point_start,
            contact_point_end=contact_point_end
        )

        # Set paramPoly3 geometry if available
        if param_poly3:
            connecting_road.geometry_type = "parampoly3"
            connecting_road.aU = param_poly3['aU']
            connecting_road.bU = param_poly3['bU']
            connecting_road.cU = param_poly3['cU']
            connecting_road.dU = param_poly3['dU']
            connecting_road.aV = param_poly3['aV']
            connecting_road.bV = param_poly3['bV']
            connecting_road.cV = param_poly3['cV']
            connecting_road.dV = param_poly3['dV']
            connecting_road.p_range = param_poly3['length']
            connecting_road.p_range_normalized = (param_poly3['pRange'] == 'normalized')
            # Store the starting heading for export
            connecting_road.stored_start_heading = param_poly3['hdg']
        else:
            connecting_road.geometry_type = "polyline"

        # Initialize lanes from the lane count
        connecting_road.ensure_lanes_initialized()

        # Import lane properties if available
        if odr_road.lane_sections:
            self._import_connecting_road_lanes(connecting_road, odr_road.lane_sections[0])

            # Calculate lane_width_start and lane_width_end from polynomial
            # Use the first non-center lane's width polynomial
            road_length = odr_road.length  # Length in meters
            for lane in connecting_road.lanes:
                if lane.id != 0:  # Skip center lane
                    # Calculate width at start (ds=0) and end (ds=road_length)
                    width_start = lane.width  # a coefficient
                    width_end = (lane.width +
                                 lane.width_b * road_length +
                                 lane.width_c * road_length**2 +
                                 lane.width_d * road_length**3)
                    connecting_road.lane_width_start = width_start
                    connecting_road.lane_width_end = width_end
                    break

        # Add to junction
        junction.add_connecting_road(connecting_road)

        # Add predecessor/successor roads to junction's connected_road_ids
        if predecessor_orbit_id and predecessor_orbit_id not in junction.connected_road_ids:
            junction.connected_road_ids.append(predecessor_orbit_id)
        if successor_orbit_id and successor_orbit_id not in junction.connected_road_ids:
            junction.connected_road_ids.append(successor_orbit_id)

        # Create LaneConnection objects from junction connection data
        # Find the ODR junction to get lane link data
        odr_junction = None
        for j in self.odr_data.junctions:
            if j.id == junction_odr_id:
                odr_junction = j
                break

        if odr_junction:
            # Find the connection that uses this connecting road
            for odr_conn in odr_junction.connections:
                if odr_conn.connecting_road == odr_road.id:
                    # Get the incoming road ORBIT ID
                    from_road_id = self.odr_road_to_orbit.get(odr_conn.incoming_road, "")

                    # The to_road is the successor of the connecting road
                    to_road_id = successor_orbit_id

                    if from_road_id and to_road_id:
                        # Create LaneConnection for each lane link
                        for lane_link in odr_conn.lane_links:
                            # Note: lane_link.to_lane is the lane on the connecting road,
                            # not the outgoing road. We store it in connecting_lane_id.
                            # to_lane_id is the outgoing road lane (assumed same as from_lane_id).
                            lane_connection = LaneConnection(
                                from_road_id=from_road_id,
                                from_lane_id=lane_link.from_lane,
                                to_road_id=to_road_id,
                                to_lane_id=lane_link.from_lane,  # Assume same lane continues
                                connecting_road_id=connecting_road.id,
                                connecting_lane_id=lane_link.to_lane  # Lane on connecting road
                            )
                            junction.add_lane_connection(lane_connection)

                        if options.verbose:
                            print(f"    Created {len(odr_conn.lane_links)} lane connection(s)")

        if options.verbose:
            geom_type = "paramPoly3" if param_poly3 else "polyline"
            print(f"  Connecting road {odr_road.id} → Junction {junction.name} ({geom_type})")

        return True

    def _import_connecting_road_lanes(self, connecting_road: ConnectingRoad, odr_section) -> None:
        """
        Import lane properties from OpenDrive lane section into connecting road.

        Args:
            connecting_road: ConnectingRoad to update
            odr_section: OpenDrive lane section with lane data
        """
        # Ensure lanes are initialized
        connecting_road.ensure_lanes_initialized()

        # Process right lanes (negative IDs)
        for odr_lane in odr_section.right_lanes:
            lane = connecting_road.get_lane(odr_lane.id)
            if lane:
                # Lane type
                lane_type = self._convert_lane_type(odr_lane.type)
                lane.lane_type = lane_type

                # Lane width (use first width polynomial)
                if odr_lane.widths:
                    first_width = odr_lane.widths[0]
                    lane.width = first_width.a
                    lane.width_b = first_width.b
                    lane.width_c = first_width.c
                    lane.width_d = first_width.d

                # Road mark attributes
                if odr_lane.road_marks:
                    first_mark = odr_lane.road_marks[0]
                    lane.road_mark_type = self._convert_road_mark_type(first_mark.type)
                    lane.road_mark_color = first_mark.color
                    lane.road_mark_weight = first_mark.weight
                    lane.road_mark_width = first_mark.width

                # Speed limit
                if odr_lane.speed_limits:
                    first_speed = odr_lane.speed_limits[0]
                    lane.speed_limit = first_speed.max_speed
                    lane.speed_limit_unit = first_speed.unit

        # Process left lanes (positive IDs)
        for odr_lane in odr_section.left_lanes:
            lane = connecting_road.get_lane(odr_lane.id)
            if lane:
                # Lane type
                lane_type = self._convert_lane_type(odr_lane.type)
                lane.lane_type = lane_type

                # Lane width (use first width polynomial)
                if odr_lane.widths:
                    first_width = odr_lane.widths[0]
                    lane.width = first_width.a
                    lane.width_b = first_width.b
                    lane.width_c = first_width.c
                    lane.width_d = first_width.d

                # Road mark attributes
                if odr_lane.road_marks:
                    first_mark = odr_lane.road_marks[0]
                    lane.road_mark_type = self._convert_road_mark_type(first_mark.type)
                    lane.road_mark_color = first_mark.color
                    lane.road_mark_weight = first_mark.weight
                    lane.road_mark_width = first_mark.width

                # Speed limit
                if odr_lane.speed_limits:
                    first_speed = odr_lane.speed_limits[0]
                    lane.speed_limit = first_speed.max_speed
                    lane.speed_limit_unit = first_speed.unit

    def _import_lane_sections(
        self,
        odr_sections: List,
        road_length_meters: float,
        centerline_points: List[Tuple[float, float]]
    ) -> List[LaneSection]:
        """Import lane sections from OpenDrive."""
        orbit_sections = []

        # Calculate s-offsets in pixel space for each centerline point
        s_offsets_pixels = calculate_s_offsets(centerline_points) if centerline_points else [0.0]
        total_length_pixels = s_offsets_pixels[-1] if s_offsets_pixels else 1000.0

        for i, odr_section in enumerate(odr_sections):
            section_number = i + 1

            # Calculate where this section should start and end using fractional positions
            fraction_start = odr_section.s / road_length_meters if road_length_meters > 0 else 0.0
            target_s_start = fraction_start * total_length_pixels

            # Find the closest point for section start (always use actual point's s-coordinate)
            if i == 0:
                # First section starts at beginning
                s_start_pixels = 0.0
                start_point_index = 0
            else:
                # Start where previous section ended
                s_start_pixels = orbit_sections[-1].s_end
                start_point_index = orbit_sections[-1].end_point_index if orbit_sections[-1].end_point_index is not None else 0

            # Find where this section should end
            end_point_index = None
            if i < len(odr_sections) - 1:
                # Not the last section - find the point closest to the section boundary
                fraction_end = odr_sections[i + 1].s / road_length_meters
                target_s_end = fraction_end * total_length_pixels

                min_dist = float('inf')
                best_idx = 0

                for idx, s_offset in enumerate(s_offsets_pixels):
                    dist = abs(s_offset - target_s_end)
                    if dist < min_dist:
                        min_dist = dist
                        best_idx = idx

                # Ensure valid index
                if best_idx >= len(centerline_points) - 1:
                    best_idx = len(centerline_points) - 2
                if best_idx < 1:
                    best_idx = 1

                end_point_index = best_idx
                # Use the actual s-coordinate of this point (ensures sections share points)
                s_end_pixels = s_offsets_pixels[best_idx]
            else:
                # Last section extends to end
                end_point_index = None
                s_end_pixels = total_length_pixels

            # Create lane section
            section = LaneSection(
                section_number=section_number,
                s_start=s_start_pixels,
                s_end=s_end_pixels,
                single_side=odr_section.single_side,
                end_point_index=end_point_index
            )

            # Import lanes
            # Right lanes (negative IDs in OpenDrive)
            for odr_lane in odr_section.right_lanes:
                if odr_lane.id == 0:
                    continue  # Skip center lane
                orbit_lane = self._convert_lane(odr_lane, side='right')
                section.lanes.append(orbit_lane)

            # Left lanes (positive IDs in OpenDrive)
            for odr_lane in odr_section.left_lanes:
                if odr_lane.id == 0:
                    continue  # Skip center lane
                orbit_lane = self._convert_lane(odr_lane, side='left')
                section.lanes.append(orbit_lane)

            # If no lanes were created, add default
            if not section.lanes:
                section.lanes = [
                    Lane(id=-1, lane_type=ORBITLaneType.DRIVING, width=3.5),
                    Lane(id=1, lane_type=ORBITLaneType.DRIVING, width=3.5)
                ]

            orbit_sections.append(section)

        return orbit_sections

    def _convert_lane(self, odr_lane: ODRLane, side: str) -> Lane:
        """Convert OpenDrive lane to ORBIT lane."""
        # Get width polynomial coefficients (use first width entry)
        width_a = 3.5  # Default
        width_b = 0.0
        width_c = 0.0
        width_d = 0.0
        if odr_lane.widths:
            first_width = odr_lane.widths[0]
            width_a = first_width.a
            width_b = first_width.b
            width_c = first_width.c
            width_d = first_width.d

        # Convert lane type
        lane_type = self._convert_lane_type(odr_lane.type)

        # Convert road mark attributes
        road_mark_type = RoadMarkType.SOLID  # Default
        road_mark_color = "white"
        road_mark_weight = "standard"
        road_mark_width = 0.12
        if odr_lane.road_marks:
            first_mark = odr_lane.road_marks[0]
            road_mark_type = self._convert_road_mark_type(first_mark.type)
            road_mark_color = first_mark.color
            road_mark_weight = first_mark.weight
            road_mark_width = first_mark.width

        # Get lane-level speed limit (use first speed record if available)
        speed_limit = None
        speed_limit_unit = "m/s"
        if odr_lane.speed_limits:
            first_speed = odr_lane.speed_limits[0]
            speed_limit = first_speed.max_speed
            speed_limit_unit = first_speed.unit

        # Create lane with full width polynomial and road mark attributes
        lane = Lane(
            id=odr_lane.id,
            lane_type=lane_type,
            width=width_a,
            width_b=width_b,
            width_c=width_c,
            width_d=width_d,
            road_mark_type=road_mark_type,
            road_mark_color=road_mark_color,
            road_mark_weight=road_mark_weight,
            road_mark_width=road_mark_width,
            speed_limit=speed_limit,
            speed_limit_unit=speed_limit_unit
        )

        return lane

    def _find_all_shared_points(self, road_id_1: str, road_id_2: str, tolerance: float = 10.0) -> List[Tuple[float, float]]:
        """
        Find all shared points between two roads.

        Args:
            road_id_1: First road ID
            road_id_2: Second road ID
            tolerance: Distance tolerance in pixels for point matching

        Returns:
            List of (x, y) coordinates where roads intersect
        """
        # Get centerline points for both roads
        road1 = next((r for r in self.project.roads if r.id == road_id_1), None)
        road2 = next((r for r in self.project.roads if r.id == road_id_2), None)

        if not (road1 and road1.centerline_id and road2 and road2.centerline_id):
            return []

        centerline1 = next((p for p in self.project.polylines if p.id == road1.centerline_id), None)
        centerline2 = next((p for p in self.project.polylines if p.id == road2.centerline_id), None)

        if not (centerline1 and centerline1.points and centerline2 and centerline2.points):
            return []

        # Find all matching points
        shared_points = []
        for px, py in centerline1.points:
            for ox, oy in centerline2.points:
                dist = ((px - ox)**2 + (py - oy)**2)**0.5
                if dist < tolerance:
                    # Check if we already have a nearby point (avoid duplicates)
                    is_duplicate = False
                    for sx, sy in shared_points:
                        if ((px - sx)**2 + (py - sy)**2)**0.5 < tolerance:
                            is_duplicate = True
                            break
                    if not is_duplicate:
                        shared_points.append((px, py))
                    break

        return shared_points

    def _import_junction(self, odr_junction, options: ImportOptions, result: ImportResult) -> bool:
        """Import junction from OpenDrive."""
        junction_id = str(uuid.uuid4())
        junction = Junction(
            id=junction_id,
            name=odr_junction.name if odr_junction.name else f"Junction {odr_junction.id}",
            opendrive_id=odr_junction.id
        )

        # Import connections
        for odr_conn in odr_junction.connections:
            # Map OpenDrive road IDs to ORBIT road IDs
            incoming_orbit_id = self.odr_road_to_orbit.get(odr_conn.incoming_road)
            connecting_orbit_id = self.odr_road_to_orbit.get(odr_conn.connecting_road)

            if incoming_orbit_id and connecting_orbit_id:
                conn = JunctionConnection(
                    incoming_road_id=incoming_orbit_id,
                    connecting_road_id=connecting_orbit_id,
                    contact_point=odr_conn.contact_point
                )
                junction.connections.append(conn)
                junction.connected_road_ids.append(incoming_orbit_id)
                junction.connected_road_ids.append(connecting_orbit_id)

        # Remove duplicates from connected_road_ids
        junction.connected_road_ids = list(set(junction.connected_road_ids))

        # Store junction for later processing (center point assignment)
        # This will be handled in _assign_junction_center_points()
        self.project.junctions.append(junction)
        self.odr_junction_to_orbit[odr_junction.id] = junction_id

        return True

    def _assign_junction_center_points(self, result: ImportResult):
        """
        Assign center points to all junctions, handling multiple junctions between same road pairs.

        This method finds all intersection points between each pair of roads and distributes
        junctions across those points. Warns if there are more junctions than intersection points.
        """
        from collections import defaultdict

        # Build mapping: frozenset(road_id_1, road_id_2) -> list of junctions
        road_pair_to_junctions = defaultdict(list)

        for junction in self.project.junctions:
            if len(junction.connected_road_ids) >= 2:
                # Create a frozenset of the first two connected roads as the "road pair"
                # (frozenset is unordered, so (A,B) == (B,A))
                road_pair = frozenset(junction.connected_road_ids[:2])
                road_pair_to_junctions[road_pair].append(junction)

        # Process each road pair
        for road_pair, junctions in road_pair_to_junctions.items():
            if len(junctions) == 1:
                # Single junction: use first shared point
                junction = junctions[0]
                road_ids = list(road_pair)
                shared_points = self._find_all_shared_points(road_ids[0], road_ids[1], tolerance=10.0)
                if shared_points:
                    junction.center_point = shared_points[0]
            else:
                # Multiple junctions between same road pair
                road_ids = list(road_pair)
                shared_points = self._find_all_shared_points(road_ids[0], road_ids[1], tolerance=10.0)

                if len(shared_points) == 0:
                    # No intersection found - leave junctions without center points
                    result.warnings.append(
                        f"No intersection point found for {len(junctions)} junctions between same roads "
                        f"(road IDs: {road_ids[0][:8]}..., {road_ids[1][:8]}...)"
                    )
                elif len(shared_points) < len(junctions):
                    # More junctions than intersection points
                    # Assign points to first N junctions, put rest at last point
                    for i, junction in enumerate(junctions):
                        if i < len(shared_points):
                            junction.center_point = shared_points[i]
                        else:
                            # Excess junctions: place at last found intersection
                            junction.center_point = shared_points[-1]

                    result.warnings.append(
                        f"Found {len(shared_points)} intersection point(s) for {len(junctions)} junctions "
                        f"between same roads. {len(junctions) - len(shared_points)} junction(s) placed "
                        f"at same location. Manual review recommended."
                    )
                else:
                    # Enough intersection points for all junctions
                    for i, junction in enumerate(junctions):
                        junction.center_point = shared_points[i]

    def _import_signal(self, odr_signal: ODRSignal, road_id: str, odr_road: ODRRoad, options: ImportOptions) -> bool:
        """Import signal from OpenDrive."""
        # Convert signal type
        signal_type, value = self._convert_signal_type(odr_signal)

        if signal_type is None:
            return False  # Unsupported signal type

        # Calculate pixel position from s,t coordinates
        position_pixel = self._calculate_position_from_st(
            odr_signal.s,
            odr_signal.t,
            odr_road
        )

        if not position_pixel:
            return False

        # Create signal
        signal = Signal(
            position=position_pixel,
            signal_type=signal_type,
            value=value,
            road_id=road_id
        )

        signal.name = odr_signal.name
        signal.orientation = odr_signal.orientation
        signal.z_offset = odr_signal.z_offset
        signal.sign_width = odr_signal.width if odr_signal.width > 0 else signal.sign_width
        signal.sign_height = odr_signal.height if odr_signal.height > 0 else signal.sign_height
        signal.opendrive_id = odr_signal.id
        # Preserve OpenDRIVE attributes for round-trip
        signal.dynamic = odr_signal.dynamic
        signal.subtype = odr_signal.subtype
        signal.country = odr_signal.country

        self.project.signals.append(signal)
        return True

    def _import_object(self, odr_object: ODRObject, road_id: str, odr_road: ODRRoad, options: ImportOptions) -> bool:
        """Import object from OpenDrive."""
        # Convert object type
        object_type = self._convert_object_type(odr_object.type)

        if object_type is None:
            return False  # Unsupported object type

        # Calculate pixel position from s,t coordinates
        position_pixel = self._calculate_position_from_st(
            odr_object.s,
            odr_object.t,
            odr_road
        )

        if not position_pixel:
            return False

        # Create object
        obj = RoadObject(
            position=position_pixel,
            object_type=object_type,
            road_id=road_id
        )

        obj.name = odr_object.name
        obj.z_offset = odr_object.z_offset
        obj.orientation = math.degrees(odr_object.hdg)  # Convert radians to degrees

        # Set dimensions
        if odr_object.radius > 0:
            obj.dimensions['radius'] = odr_object.radius
        if odr_object.width > 0:
            obj.dimensions['width'] = odr_object.width
        if odr_object.length > 0:
            obj.dimensions['length'] = odr_object.length
        if odr_object.height > 0:
            obj.dimensions['height'] = odr_object.height

        obj.opendrive_id = odr_object.id
        # Preserve OpenDRIVE orientation angles for round-trip
        obj.pitch = odr_object.pitch
        obj.roll = odr_object.roll

        self.project.objects.append(obj)
        return True

    def _calculate_position_from_st(
        self,
        s: float,
        t: float,
        odr_road: ODRRoad
    ) -> Optional[Tuple[float, float]]:
        """
        Calculate pixel position from s,t coordinates along road.

        Args:
            s: Position along road centerline (meters)
            t: Lateral offset from centerline (meters, positive = left)
            odr_road: OpenDrive road

        Returns:
            Tuple of (pixel_x, pixel_y) or None if calculation fails
        """
        # Find geometry element containing s
        geom_element = None
        for geom in odr_road.geometry:
            if s >= geom.s and s < geom.s + geom.length:
                geom_element = geom
                break

        if not geom_element:
            # Use last geometry element if s is beyond end
            if odr_road.geometry:
                geom_element = odr_road.geometry[-1]
            else:
                return None

        # Calculate position along this geometry segment
        ds = s - geom_element.s

        # Get position and heading at ds
        # For simplicity, use linear interpolation along segment
        # TODO: Use proper geometry evaluation for arcs/spirals
        cos_hdg = math.cos(geom_element.hdg)
        sin_hdg = math.sin(geom_element.hdg)

        x_center = geom_element.x + ds * cos_hdg
        y_center = geom_element.y + ds * sin_hdg

        # Apply lateral offset (perpendicular to heading)
        x_metric = x_center - t * sin_hdg
        y_metric = y_center + t * cos_hdg

        # Transform to pixels
        return self.coord_transform.metric_to_pixel(x_metric, y_metric)

    def _convert_road_type(self, odr_road_type: str) -> RoadType:
        """Convert OpenDrive road type to ORBIT RoadType."""
        type_map = {
            'motorway': RoadType.MOTORWAY,
            'rural': RoadType.RURAL,
            'town': RoadType.TOWN,
            'lowSpeed': RoadType.LOW_SPEED,
            'pedestrian': RoadType.PEDESTRIAN,
            'bicycle': RoadType.BICYCLE
        }
        return type_map.get(odr_road_type, RoadType.UNKNOWN)

    def _convert_lane_type(self, odr_lane_type: str) -> ORBITLaneType:
        """Convert OpenDrive lane type to ORBIT LaneType."""
        type_map = {
            'driving': ORBITLaneType.DRIVING,
            'biking': ORBITLaneType.BIKING,
            'sidewalk': ORBITLaneType.SIDEWALK,
            'border': ORBITLaneType.BORDER,
            'restricted': ORBITLaneType.RESTRICTED,
            'parking': ORBITLaneType.PARKING,
            'bidirectional': ORBITLaneType.BIDIRECTIONAL,
            'median': ORBITLaneType.MEDIAN,
            'shoulder': ORBITLaneType.SHOULDER,
            'curb': ORBITLaneType.CURB
        }
        return type_map.get(odr_lane_type, ORBITLaneType.DRIVING)

    def _convert_road_mark_type(self, odr_mark_type: str) -> RoadMarkType:
        """Convert OpenDrive road mark type to ORBIT RoadMarkType."""
        type_map = {
            'solid': RoadMarkType.SOLID,
            'broken': RoadMarkType.BROKEN,
            'solid solid': RoadMarkType.SOLID_SOLID,
            'solid broken': RoadMarkType.SOLID_BROKEN,
            'broken solid': RoadMarkType.BROKEN_SOLID,
            'broken broken': RoadMarkType.BROKEN_BROKEN,
            'curb': RoadMarkType.CURB,
            'grass': RoadMarkType.GRASS
        }
        return type_map.get(odr_mark_type, RoadMarkType.SOLID)

    def _convert_signal_type(self, odr_signal: ODRSignal) -> Tuple[Optional[SignalType], Optional[int]]:
        """
        Convert OpenDrive signal to ORBIT SignalType.

        Supports both text-based types and numeric country codes.

        Returns:
            Tuple of (SignalType, value) or (None, None) if unsupported
        """
        # First check for numeric codes (common in OpenDrive)
        if odr_signal.type.isdigit():
            code = int(odr_signal.type)

            # Swedish road sign codes (country="se")
            if odr_signal.country.lower() == 'se':
                if code == 201:
                    return (SignalType.STOP, None)
                elif code == 206:
                    return (SignalType.GIVE_WAY, None)
                elif code in (274, 275, 276):  # Speed limit signs
                    value = int(odr_signal.value) if odr_signal.value else None
                    return (SignalType.SPEED_LIMIT, value)
                elif code == 376:
                    return (SignalType.END_OF_SPEED_LIMIT, None)
                elif code == 220:
                    return (SignalType.NO_ENTRY, None)
                elif code == 401:
                    return (SignalType.PRIORITY_ROAD, None)

            # German road sign codes (country="de")
            elif odr_signal.country.lower() == 'de':
                if code == 206:
                    return (SignalType.STOP, None)
                elif code == 205:
                    return (SignalType.GIVE_WAY, None)
                elif code in (274, 275, 276, 277):
                    value = int(odr_signal.value) if odr_signal.value else None
                    return (SignalType.SPEED_LIMIT, value)
                elif code == 267:
                    return (SignalType.NO_ENTRY, None)
                elif code == 306:
                    return (SignalType.PRIORITY_ROAD, None)

            # US MUTCD codes (country="us")
            elif odr_signal.country.lower() == 'us':
                if code == 1:  # R1-1 Stop sign
                    return (SignalType.STOP, None)
                elif code == 2:  # R1-2 Yield sign
                    return (SignalType.GIVE_WAY, None)
                # Speed limits vary by state, check for value
                if odr_signal.value:
                    value = int(odr_signal.value)
                    return (SignalType.SPEED_LIMIT, value)

        # Text-based type detection (fallback)
        type_lower = odr_signal.type.lower()

        # Check for speed limit
        if 'speed' in type_lower or 'maximum' in type_lower:
            value = int(odr_signal.value) if odr_signal.value else None
            return (SignalType.SPEED_LIMIT, value)

        # Check for traffic lights
        if 'signal' in type_lower or 'light' in type_lower:
            if odr_signal.dynamic == 'yes':
                return (SignalType.TRAFFIC_SIGNALS, None)

        # Check for stop sign
        if 'stop' in type_lower:
            return (SignalType.STOP, None)

        # Check for give way / yield
        if 'yield' in type_lower or 'give' in type_lower:
            return (SignalType.GIVE_WAY, None)

        # Check for no entry
        if 'entry' in type_lower and 'no' in type_lower:
            return (SignalType.NO_ENTRY, None)

        # Check for priority road
        if 'priority' in type_lower:
            return (SignalType.PRIORITY_ROAD, None)

        return (None, None)

    def _convert_object_type(self, odr_object_type: str) -> Optional[ObjectType]:
        """Convert OpenDrive object type to ORBIT ObjectType."""
        type_lower = odr_object_type.lower()

        if 'lamp' in type_lower or 'pole' in type_lower:
            return ObjectType.LAMPPOST
        elif 'guard' in type_lower or 'rail' in type_lower or 'barrier' in type_lower:
            return ObjectType.GUARDRAIL
        elif 'building' in type_lower or 'house' in type_lower:
            return ObjectType.BUILDING
        elif 'tree' in type_lower:
            if 'conifer' in type_lower or 'pine' in type_lower:
                return ObjectType.TREE_CONIFER
            else:
                return ObjectType.TREE_BROADLEAF
        elif 'bush' in type_lower or 'shrub' in type_lower:
            return ObjectType.BUSH

        return None

    def _track_unsupported_features(self, result: ImportResult):
        """Track unsupported OpenDrive features that were skipped."""
        # Check for lateral profiles (superelevation, crossfall)
        lateral_count = 0
        for road in self.odr_data.roads:
            # Note: lateralProfile not parsed yet, would need to add to parser
            pass

        # Track as skipped features
        if lateral_count > 0:
            result.features_skipped['lateralProfile'] = lateral_count

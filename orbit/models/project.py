"""
Project data model for ORBIT.

Manages the complete project state including polylines, roads, junctions,
and georeferencing data. Handles saving/loading to .orbit files.
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path
import json
from datetime import datetime

from orbit.utils.logging_config import get_logger
from .polyline import Polyline
from .road import Road
from .junction import Junction, JunctionGroup
from .signal import Signal
from .object import RoadObject
from .parking import ParkingSpace

logger = get_logger(__name__)


@dataclass
class ControlPoint:
    """
    A georeferencing control point.

    Attributes:
        pixel_x: X coordinate in image pixels
        pixel_y: Y coordinate in image pixels
        longitude: Longitude in decimal degrees
        latitude: Latitude in decimal degrees
        name: Optional name for the control point
        is_validation: If True, point is used for validation only (GVP), not training (GCP)
    """
    pixel_x: float
    pixel_y: float
    longitude: float
    latitude: float
    name: Optional[str] = None
    is_validation: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'pixel_x': self.pixel_x,
            'pixel_y': self.pixel_y,
            'longitude': self.longitude,
            'latitude': self.latitude,
            'name': self.name,
            'is_validation': bool(self.is_validation)
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ControlPoint':
        """Create from dictionary."""
        return cls(
            pixel_x=data['pixel_x'],
            pixel_y=data['pixel_y'],
            longitude=data['longitude'],
            latitude=data['latitude'],
            name=data.get('name'),
            is_validation=data.get('is_validation', False)  # Default to False for backwards compatibility
        )


@dataclass
class Project:
    """
    Main project container for ORBIT.

    Attributes:
        image_path: Path to the loaded image
        polylines: List of all polylines
        roads: List of all roads
        junctions: List of all junctions
        signals: List of all traffic signals
        objects: List of all roadside objects
        control_points: List of georeferencing control points
        right_hand_traffic: True for right-hand traffic (default), False for left-hand traffic
        transform_method: Georeferencing transformation method ('affine' or 'homography')
        country_code: Two-letter ISO 3166-1 country code for OpenDrive export
        map_name: Name of the map for OpenDrive export (defaults to image filename)
        openstreetmap_used: Flag indicating if OpenStreetMap data was imported
        georef_validation: Validation results for georeferencing (reprojection and validation errors)
        metadata: Additional project metadata
    """
    image_path: Optional[Path] = None
    polylines: List[Polyline] = field(default_factory=list)
    roads: List[Road] = field(default_factory=list)
    junctions: List[Junction] = field(default_factory=list)
    junction_groups: List[JunctionGroup] = field(default_factory=list)
    signals: List[Signal] = field(default_factory=list)
    objects: List[RoadObject] = field(default_factory=list)
    parking_spaces: List[ParkingSpace] = field(default_factory=list)
    control_points: List[ControlPoint] = field(default_factory=list)
    right_hand_traffic: bool = True  # Default to right-hand traffic
    transform_method: str = 'homography'  # Default to homography for drone images
    country_code: str = 'se'  # Default to Sweden
    map_name: str = ''  # Name for OpenDrive export (defaults to image filename when loaded)
    openstreetmap_used: bool = False  # Flag for OpenStreetMap attribution
    junction_offset_distance_meters: float = 8.0  # Distance to offset road endpoints from junction centers (meters)
    roundabout_ring_offset_distance_meters: float = 4.0  # Distance to offset ring segment endpoints from roundabout junctions (meters)
    roundabout_approach_offset_distance_meters: float = 8.0  # Distance to offset approach road endpoints from roundabout junctions (meters)
    georef_validation: Dict[str, Any] = field(default_factory=dict)
    uncertainty_grid_cache: Optional[List[List[float]]] = None  # Cached uncertainty grid
    uncertainty_grid_resolution: Tuple[int, int] = (50, 50)  # Grid resolution
    uncertainty_bootstrap_grid: Optional[List[List[float]]] = None  # Bootstrap analysis results
    uncertainty_last_computed: Optional[str] = None  # ISO timestamp of last computation
    mc_sigma_pixels: float = 1.5  # Measurement error for Monte Carlo (pixels)
    baseline_uncertainty_m: float = 0.05  # Baseline position uncertainty (meters)
    gcp_suggestion_threshold: float = 0.2  # Threshold for GCP suggestions (meters)
    imported_geo_reference: Optional[str] = None  # Preserved geoReference from OpenDRIVE import
    enabled_sign_libraries: List[str] = field(default_factory=lambda: ['se'])  # Enabled sign library IDs
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ID counters for sequential ID generation (one per entity type)
    _next_polyline_id: int = field(default=1, repr=False)
    _next_road_id: int = field(default=1, repr=False)
    _next_junction_id: int = field(default=1, repr=False)
    _next_signal_id: int = field(default=1, repr=False)
    _next_object_id: int = field(default=1, repr=False)
    _next_parking_id: int = field(default=1, repr=False)
    _next_connecting_road_id: int = field(default=1, repr=False)
    _next_lane_connection_id: int = field(default=1, repr=False)
    _next_junction_group_id: int = field(default=1, repr=False)

    # Map from entity type name to counter attribute name
    _COUNTER_MAP: Dict[str, str] = field(default_factory=dict, repr=False, init=False)

    def __post_init__(self):
        """Initialize metadata if not provided."""
        if not self.metadata:
            self.metadata = {
                'version': '0.4.0',
                'created': datetime.now().isoformat(),
                'modified': datetime.now().isoformat()
            }
        # Build counter map
        self._COUNTER_MAP = {
            'polyline': '_next_polyline_id',
            'road': '_next_road_id',
            'junction': '_next_junction_id',
            'signal': '_next_signal_id',
            'object': '_next_object_id',
            'parking': '_next_parking_id',
            'connecting_road': '_next_connecting_road_id',
            'lane_connection': '_next_lane_connection_id',
            'junction_group': '_next_junction_group_id',
        }

    def next_id(self, entity_type: str) -> str:
        """
        Get the next sequential ID for a given entity type and increment the counter.

        Args:
            entity_type: One of 'polyline', 'road', 'junction', 'signal',
                         'object', 'parking', 'connecting_road', 'lane_connection',
                         'junction_group'

        Returns:
            String representation of the next ID (e.g. "1", "2", ...)
        """
        attr = self._COUNTER_MAP.get(entity_type)
        if attr is None:
            raise ValueError(f"Unknown entity type: {entity_type}")
        current = getattr(self, attr)
        setattr(self, attr, current + 1)
        return str(current)

    def _sync_id_counters(self) -> None:
        """
        Scan all collections and set counters to max(existing numeric IDs) + 1.

        Non-numeric IDs (e.g. UUIDs from old projects) are skipped gracefully.
        Called after from_dict() / load() to ensure counters don't collide
        with existing IDs.
        """
        def _max_numeric_id(ids):
            """Return the maximum numeric ID from a list of string IDs, or 0."""
            max_id = 0
            for id_str in ids:
                try:
                    val = int(id_str)
                    if val > max_id:
                        max_id = val
                except (ValueError, TypeError):
                    pass
            return max_id

        self._next_polyline_id = _max_numeric_id(p.id for p in self.polylines) + 1
        self._next_road_id = _max_numeric_id(r.id for r in self.roads) + 1
        self._next_junction_id = _max_numeric_id(j.id for j in self.junctions) + 1
        self._next_signal_id = _max_numeric_id(s.id for s in self.signals) + 1
        self._next_object_id = _max_numeric_id(o.id for o in self.objects) + 1
        self._next_parking_id = _max_numeric_id(p.id for p in self.parking_spaces) + 1
        self._next_junction_group_id = _max_numeric_id(jg.id for jg in self.junction_groups) + 1

        # ConnectingRoad and LaneConnection are nested inside junctions
        cr_ids = []
        lc_ids = []
        for junction in self.junctions:
            for cr in junction.connecting_roads:
                cr_ids.append(cr.id)
            for lc in junction.lane_connections:
                lc_ids.append(lc.id)
        self._next_connecting_road_id = _max_numeric_id(cr_ids) + 1
        self._next_lane_connection_id = _max_numeric_id(lc_ids) + 1

    def _has_uuid_ids(self) -> bool:
        """Check if any entity has a non-numeric (UUID) ID."""
        for p in self.polylines:
            try:
                int(p.id)
            except (ValueError, TypeError):
                return True
        for r in self.roads:
            try:
                int(r.id)
            except (ValueError, TypeError):
                return True
        for j in self.junctions:
            try:
                int(j.id)
            except (ValueError, TypeError):
                return True
        return False

    def _migrate_uuid_ids(self, odr_id_lookup: Optional[Dict[str, str]] = None) -> None:
        """
        Migrate UUID-based IDs to sequential integers.

        Called from from_dict() when old project files with UUID IDs are loaded.
        Builds remap tables for each entity type, preferring opendrive_id (if numeric)
        as the new ID, then remaps all cross-reference fields.

        Args:
            odr_id_lookup: Mapping from old UUID IDs to opendrive_id values,
                          extracted from raw JSON before deserialization.
        """
        if not self._has_uuid_ids():
            return

        logger.info("Migrating UUID-based IDs to sequential integers...")

        # Build remap tables: {old_uuid: new_int_str}
        polyline_remap: Dict[str, str] = {}
        road_remap: Dict[str, str] = {}
        junction_remap: Dict[str, str] = {}
        signal_remap: Dict[str, str] = {}
        object_remap: Dict[str, str] = {}
        parking_remap: Dict[str, str] = {}
        connecting_road_remap: Dict[str, str] = {}
        lane_connection_remap: Dict[str, str] = {}
        junction_group_remap: Dict[str, str] = {}

        if odr_id_lookup is None:
            odr_id_lookup = {}

        # Helper to assign a new ID, preferring opendrive_id if numeric
        def _new_id(old_id: str, opendrive_id, used_ids: set, counter: list) -> str:
            """Assign a new numeric ID. Prefers opendrive_id if numeric and unused."""
            if opendrive_id:
                try:
                    int(opendrive_id)
                    if opendrive_id not in used_ids:
                        used_ids.add(opendrive_id)
                        return opendrive_id
                except (ValueError, TypeError):
                    pass
            # Already numeric and unused?
            try:
                int(old_id)
                if old_id not in used_ids:
                    used_ids.add(old_id)
                    return old_id
            except (ValueError, TypeError):
                pass
            # Generate sequential
            while str(counter[0]) in used_ids:
                counter[0] += 1
            new_id = str(counter[0])
            used_ids.add(new_id)
            counter[0] += 1
            return new_id

        # --- Assign new polyline IDs ---
        poly_used: set = set()
        poly_counter = [1]
        for p in self.polylines:
            odr_id = odr_id_lookup.get(p.id)
            new_id = _new_id(p.id, odr_id, poly_used, poly_counter)
            polyline_remap[p.id] = new_id
            p.id = new_id

        # --- Assign new road IDs ---
        road_used: set = set()
        road_counter = [1]
        for r in self.roads:
            odr_id = odr_id_lookup.get(r.id)
            new_id = _new_id(r.id, odr_id, road_used, road_counter)
            road_remap[r.id] = new_id
            r.id = new_id

        # --- Assign new junction IDs ---
        junction_used: set = set()
        junction_counter = [1]
        for j in self.junctions:
            odr_id = odr_id_lookup.get(j.id)
            new_id = _new_id(j.id, odr_id, junction_used, junction_counter)
            junction_remap[j.id] = new_id
            j.id = new_id

        # --- Assign new signal IDs ---
        signal_used: set = set()
        signal_counter = [1]
        for s in self.signals:
            odr_id = odr_id_lookup.get(s.id)
            new_id = _new_id(s.id, odr_id, signal_used, signal_counter)
            signal_remap[s.id] = new_id
            s.id = new_id

        # --- Assign new object IDs ---
        object_used: set = set()
        object_counter = [1]
        for o in self.objects:
            odr_id = odr_id_lookup.get(o.id)
            new_id = _new_id(o.id, odr_id, object_used, object_counter)
            object_remap[o.id] = new_id
            o.id = new_id

        # --- Assign new parking IDs ---
        parking_used: set = set()
        parking_counter = [1]
        for p in self.parking_spaces:
            odr_id = odr_id_lookup.get(p.id)
            new_id = _new_id(p.id, odr_id, parking_used, parking_counter)
            parking_remap[p.id] = new_id
            p.id = new_id

        # --- Assign new connecting road and lane connection IDs ---
        cr_used: set = set()
        cr_counter = [1]
        lc_used: set = set()
        lc_counter = [1]
        for j in self.junctions:
            for cr in j.connecting_roads:
                new_id = _new_id(cr.id, None, cr_used, cr_counter)
                connecting_road_remap[cr.id] = new_id
                cr.id = new_id
            for lc in j.lane_connections:
                new_id = _new_id(lc.id, None, lc_used, lc_counter)
                lane_connection_remap[lc.id] = new_id
                lc.id = new_id

        # --- Assign new junction group IDs ---
        jg_used: set = set()
        jg_counter = [1]
        for jg in self.junction_groups:
            new_id = _new_id(jg.id, None, jg_used, jg_counter)
            junction_group_remap[jg.id] = new_id
            jg.id = new_id

        # --- Remap all cross-references ---

        def _remap(old_id: Optional[str], remap_table: Dict[str, str]) -> Optional[str]:
            """Remap an ID using the given table, returning None if input is None."""
            if old_id is None:
                return None
            return remap_table.get(old_id, old_id)

        def _remap_list(id_list: List[str], remap_table: Dict[str, str]) -> List[str]:
            """Remap a list of IDs."""
            return [remap_table.get(old_id, old_id) for old_id in id_list]

        # Road cross-references
        for road in self.roads:
            road.centerline_id = _remap(road.centerline_id, polyline_remap)
            road.polyline_ids = _remap_list(road.polyline_ids, polyline_remap)
            road.predecessor_id = _remap(road.predecessor_id, road_remap)
            road.successor_id = _remap(road.successor_id, road_remap)
            road.junction_id = _remap(road.junction_id, junction_remap)
            road.predecessor_junction_id = _remap(road.predecessor_junction_id, junction_remap)
            road.successor_junction_id = _remap(road.successor_junction_id, junction_remap)

            # Lane boundary IDs
            for section in road.lane_sections:
                for lane in section.lanes:
                    lane.left_boundary_id = _remap(lane.left_boundary_id, polyline_remap)
                    lane.right_boundary_id = _remap(lane.right_boundary_id, polyline_remap)

        # Junction cross-references
        for junction in self.junctions:
            junction.connected_road_ids = _remap_list(junction.connected_road_ids, road_remap)
            junction.entry_roads = _remap_list(junction.entry_roads, road_remap)
            junction.exit_roads = _remap_list(junction.exit_roads, road_remap)

            for cr in junction.connecting_roads:
                cr.predecessor_road_id = _remap(cr.predecessor_road_id, road_remap) or ""
                cr.successor_road_id = _remap(cr.successor_road_id, road_remap) or ""

            for lc in junction.lane_connections:
                lc.from_road_id = _remap(lc.from_road_id, road_remap) or ""
                lc.to_road_id = _remap(lc.to_road_id, road_remap) or ""
                lc.connecting_road_id = _remap(lc.connecting_road_id, connecting_road_remap)
                lc.traffic_light_id = _remap(lc.traffic_light_id, signal_remap)

            if junction.boundary:
                for seg in junction.boundary.segments:
                    seg.road_id = _remap(seg.road_id, road_remap)

        # Signal cross-references
        for signal in self.signals:
            signal.road_id = _remap(signal.road_id, road_remap)

        # Object cross-references
        for obj in self.objects:
            obj.road_id = _remap(obj.road_id, road_remap)

        # Parking cross-references
        for parking in self.parking_spaces:
            parking.road_id = _remap(parking.road_id, road_remap)

        # JunctionGroup cross-references
        for jg in self.junction_groups:
            jg.junction_ids = _remap_list(jg.junction_ids, junction_remap)

        # Update version
        self.metadata['version'] = '0.4.0'

        logger.info(
            f"Migration complete: {len(polyline_remap)} polylines, "
            f"{len(road_remap)} roads, {len(junction_remap)} junctions, "
            f"{len(signal_remap)} signals, {len(object_remap)} objects, "
            f"{len(parking_remap)} parking spaces"
        )

    # Polyline management
    def assign_missing_ids(self) -> None:
        """Assign sequential IDs to all entities that have empty IDs.

        Includes nested entities (ConnectingRoad, LaneConnection inside junctions).
        Call this after bulk operations that may create entities without IDs.
        """
        for p in self.polylines:
            if not p.id:
                p.id = self.next_id('polyline')
        for r in self.roads:
            if not r.id:
                r.id = self.next_id('road')
        for j in self.junctions:
            if not j.id:
                j.id = self.next_id('junction')
            for cr in j.connecting_roads:
                if not cr.id:
                    cr.id = self.next_id('connecting_road')
            for lc in j.lane_connections:
                if not lc.id:
                    lc.id = self.next_id('lane_connection')
        for s in self.signals:
            if not s.id:
                s.id = self.next_id('signal')
        for o in self.objects:
            if not o.id:
                o.id = self.next_id('object')
        for p in self.parking_spaces:
            if not p.id:
                p.id = self.next_id('parking')
        for jg in self.junction_groups:
            if not jg.id:
                jg.id = self.next_id('junction_group')

    def add_polyline(self, polyline: Polyline) -> None:
        """Add a polyline to the project. Auto-assigns ID if empty."""
        if not polyline.id:
            polyline.id = self.next_id('polyline')
        self.polylines.append(polyline)

    def remove_polyline(self, polyline_id: str) -> None:
        """Remove a polyline and update any roads that reference it."""
        self.polylines = [p for p in self.polylines if p.id != polyline_id]
        # Remove from roads
        for road in self.roads:
            road.remove_polyline(polyline_id)

    def get_polyline(self, polyline_id: str) -> Optional[Polyline]:
        """Get a polyline by ID."""
        for polyline in self.polylines:
            if polyline.id == polyline_id:
                return polyline
        return None

    # Road management
    def add_road(self, road: Road) -> None:
        """Add a road to the project. Auto-assigns ID if empty."""
        if not road.id:
            road.id = self.next_id('road')
        self.roads.append(road)

    def remove_road(self, road_id: str) -> None:
        """Remove a road and clean up all references to it."""
        self.roads = [r for r in self.roads if r.id != road_id]

        # Clear successor/predecessor references on other roads
        for road in self.roads:
            if road.successor_id == road_id:
                road.successor_id = None
            if road.predecessor_id == road_id:
                road.predecessor_id = None

        # Remove from junctions (connected_road_ids, connecting_roads,
        # lane_connections, entry/exit_roads)
        for junction in self.junctions:
            junction.remove_road(road_id)

    def get_road(self, road_id: str) -> Optional[Road]:
        """Get a road by ID."""
        for road in self.roads:
            if road.id == road_id:
                return road
        return None

    def split_road_at_point(
        self,
        road_id: str,
        polyline_id: str,
        point_index: int
    ) -> Optional[Tuple[Road, Road]]:
        """
        Split a road at a centerline point, creating two connected roads.

        The original road is modified to become the first segment, and a new road
        is created for the second segment. Both centerline and boundary polylines
        are split at the corresponding positions.

        Args:
            road_id: ID of the road to split
            polyline_id: ID of the centerline polyline
            point_index: Index of the point where to split

        Returns:
            Tuple of (road1, road2) if successful, None on failure
        """
        from orbit.utils.geometry import (
            split_polyline_at_index,
            split_boundary_at_centerline_s,
            calculate_path_length
        )

        # Get road and centerline
        road = self.get_road(road_id)
        if not road:
            logger.error(f"Road {road_id} not found")
            return None

        centerline = self.get_polyline(polyline_id)
        if not centerline:
            logger.error(f"Centerline polyline {polyline_id} not found")
            return None

        if road.centerline_id != polyline_id:
            logger.error(f"Polyline {polyline_id} is not the centerline of road {road_id}")
            return None

        # Validate point_index (cannot split at first or last point)
        if point_index <= 0 or point_index >= centerline.point_count() - 1:
            logger.error(f"Invalid split point index {point_index}")
            return None

        # Store original centerline points before modification (needed for boundary projection)
        original_centerline_points = list(centerline.points)

        # Calculate s-coordinate at split point
        s_coords = road.calculate_centerline_s_coordinates(centerline.points)
        split_s = s_coords[point_index]

        # Split centerline polyline
        centerline_pts1, centerline_pts2 = split_polyline_at_index(
            centerline.points, point_index, duplicate_point=True
        )

        # Split per-point arrays (same slicing as duplicate_point=True)
        geo_pts1 = geo_pts2 = None
        if centerline.geo_points and len(centerline.geo_points) == len(centerline.points):
            geo_pts1 = list(centerline.geo_points[:point_index + 1])
            geo_pts2 = list(centerline.geo_points[point_index:])

        elev1 = elev2 = None
        if centerline.elevations and len(centerline.elevations) == len(centerline.points):
            elev1 = list(centerline.elevations[:point_index + 1])
            elev2 = list(centerline.elevations[point_index:])

        soff1 = soff2 = None
        if centerline.s_offsets and len(centerline.s_offsets) == len(centerline.points):
            soff1 = list(centerline.s_offsets[:point_index + 1])
            soff2 = list(centerline.s_offsets[point_index:])

        osm1 = osm2 = None
        if centerline.osm_node_ids and len(centerline.osm_node_ids) == len(centerline.points):
            osm1 = list(centerline.osm_node_ids[:point_index + 1])
            osm2 = list(centerline.osm_node_ids[point_index:])

        # Create new centerline polyline for road 2
        new_centerline = Polyline(
            id=self.next_id('polyline'),
            points=centerline_pts2,
            line_type=centerline.line_type,
            road_mark_type=centerline.road_mark_type
        )
        new_centerline.geo_points = geo_pts2
        new_centerline.elevations = elev2
        new_centerline.s_offsets = soff2
        new_centerline.osm_node_ids = osm2
        new_centerline.geometry_segments = None  # Invalidated by split
        self.add_polyline(new_centerline)

        # Update original centerline
        centerline.points = centerline_pts1
        centerline.geo_points = geo_pts1
        centerline.elevations = elev1
        centerline.s_offsets = soff1
        centerline.osm_node_ids = osm1
        centerline.geometry_segments = None  # Invalidated by split

        # Split boundary polylines
        new_boundary_ids = []
        for boundary_id in road.polyline_ids:
            if boundary_id == polyline_id:
                continue  # Skip centerline, already handled

            boundary = self.get_polyline(boundary_id)
            if not boundary:
                continue

            # Split boundary at corresponding s-coordinate
            result = split_boundary_at_centerline_s(
                boundary.points,
                original_centerline_points,  # Use original (unsplit) centerline for projection
                split_s
            )

            if result:
                boundary_pts1, boundary_pts2 = result

                # Create new boundary for road 2
                new_boundary = Polyline(
                    id=self.next_id('polyline'),
                    points=boundary_pts2,
                    line_type=boundary.line_type,
                    road_mark_type=boundary.road_mark_type
                )
                # Clear per-point metadata — interpolated split point has no geo coordinate
                new_boundary.geometry_segments = None
                self.add_polyline(new_boundary)
                new_boundary_ids.append(new_boundary.id)

                # Update original boundary
                boundary.points = boundary_pts1
                boundary.geo_points = None
                boundary.elevations = None
                boundary.s_offsets = None
                boundary.osm_node_ids = None
                boundary.geometry_segments = None

        # Distribute lane sections
        sections_road1, sections_road2 = road.distribute_lane_sections_for_split(
            split_s, point_index
        )

        # Generate segment names
        original_name = road.name
        # Check if name already has segment suffix
        import re
        seg_match = re.match(r'^(.*?)\s*\(seg \d+/\d+\)$', original_name)
        if seg_match:
            base_name = seg_match.group(1)
        else:
            base_name = original_name

        road1_name = f"{base_name} (seg 1/2)"
        road2_name = f"{base_name} (seg 2/2)"

        # Store original junction_id and junction links before we modify road1
        original_junction_id = road.junction_id
        original_successor_junction_id = road.successor_junction_id
        original_predecessor_junction_id = road.predecessor_junction_id

        # Create new road (road 2) with second segment
        road2 = Road(
            id=self.next_id('road'),
            name=road2_name,
            polyline_ids=[new_centerline.id] + new_boundary_ids,
            centerline_id=new_centerline.id,
            road_type=road.road_type,
            lane_info=road.lane_info,
            lane_sections=sections_road2,
            speed_limit=road.speed_limit,
            junction_id=None,  # Will be set below if needed
            predecessor_id=road.id,  # Link to first road
            predecessor_contact="end",
            successor_id=road.successor_id,  # Keep original successor
            successor_contact=road.successor_contact,
            # Road2 is the tail — gets original successor junction, no predecessor junction
            predecessor_junction_id=None,
            successor_junction_id=original_successor_junction_id
        )

        # Update road 1 (original road)
        road.name = road1_name
        road.polyline_ids = [polyline_id] + [
            bid for bid in road.polyline_ids
            if bid != polyline_id and bid not in [nb.id for nb in [self.get_polyline(nid) for nid in new_boundary_ids if self.get_polyline(nid)]]
        ]
        road.lane_sections = sections_road1
        road.successor_id = road2.id
        road.successor_contact = "start"
        # Road1 is the head — keeps original predecessor junction, loses successor junction
        road.predecessor_junction_id = original_predecessor_junction_id
        road.successor_junction_id = None

        # Add new road to project
        self.add_road(road2)

        # Handle junction remapping
        # If the original road was connected to a junction, we need to update the junction
        # to point to road2 instead (since road2 now has the "end" that was connected)
        self._remap_junctions_after_road_split(
            road.id, road2.id, original_junction_id,
            successor_junction_id=original_successor_junction_id
        )

        logger.info(f"Split road '{original_name}' into '{road1_name}' and '{road2_name}'")

        return (road, road2)

    def _remap_junctions_after_road_split(
        self,
        original_road_id: str,
        new_road_id: str,
        original_junction_id: Optional[str],
        successor_junction_id: Optional[str] = None
    ) -> None:
        """
        Update junction references after a road split.

        When a road is split, the "end" of the original road becomes the "end" of
        the new road (road2). Only junctions at the successor end need to be
        updated to reference the new road.

        Uses connecting road contact points to determine which end of the
        original road each junction is at when successor_junction_id is unknown.

        Args:
            original_road_id: ID of the original road (now road1, the first segment)
            new_road_id: ID of the new road (road2, the second segment)
            original_junction_id: The junction_id that was on the original road (if any)
            successor_junction_id: Junction at the successor end to remap (if any)
        """
        road2 = self.get_road(new_road_id)
        if not road2:
            return

        # If original road had a junction_id, transfer it to road2
        # (the junction_id field typically means the road connects to that junction at its end)
        if original_junction_id:
            road2.junction_id = original_junction_id
            # Clear from road1 (the original road object is already updated)
            road1 = self.get_road(original_road_id)
            if road1:
                road1.junction_id = None

        # Build set of junctions known to be at the successor (end) of the road
        target_junction_ids = set()
        if original_junction_id:
            target_junction_ids.add(original_junction_id)
        if successor_junction_id:
            target_junction_ids.add(successor_junction_id)

        for junction in self.junctions:
            # Skip junctions that don't reference this road at all
            references_road = (
                original_road_id in junction.connected_road_ids
                or original_road_id in junction.entry_roads
                or original_road_id in junction.exit_roads
                or any(cr.predecessor_road_id == original_road_id
                       or cr.successor_road_id == original_road_id
                       for cr in junction.connecting_roads)
            )
            if not references_road:
                continue

            # If we have explicit target junctions, only remap those
            if target_junction_ids:
                if junction.id not in target_junction_ids:
                    continue
            else:
                # No explicit targets — use connecting road contact points
                # to determine if this junction is at the END of the original
                # road (road2 takes over the end portion after split).
                junction_at_end = self._junction_at_road_end(
                    junction, original_road_id)
                if not junction_at_end:
                    continue

            remapped = False

            # Update connected_road_ids
            if original_road_id in junction.connected_road_ids:
                # Replace original road with new road in the list
                idx = junction.connected_road_ids.index(original_road_id)
                junction.connected_road_ids[idx] = new_road_id
                remapped = True

            # Update entry_roads (for roundabouts)
            if original_road_id in junction.entry_roads:
                idx = junction.entry_roads.index(original_road_id)
                junction.entry_roads[idx] = new_road_id
                remapped = True

            # Update exit_roads (for roundabouts)
            if original_road_id in junction.exit_roads:
                idx = junction.exit_roads.index(original_road_id)
                junction.exit_roads[idx] = new_road_id
                remapped = True

            # Update connecting_roads
            for conn_road in junction.connecting_roads:
                if conn_road.predecessor_road_id == original_road_id:
                    conn_road.predecessor_road_id = new_road_id
                    remapped = True
                if conn_road.successor_road_id == original_road_id:
                    conn_road.successor_road_id = new_road_id
                    remapped = True

            # Update lane_connections
            for lane_conn in junction.lane_connections:
                if lane_conn.from_road_id == original_road_id:
                    lane_conn.from_road_id = new_road_id
                    remapped = True
                if lane_conn.to_road_id == original_road_id:
                    lane_conn.to_road_id = new_road_id
                    remapped = True

            # Update boundary segments
            if junction.boundary:
                for segment in junction.boundary.segments:
                    if segment.road_id == original_road_id:
                        segment.road_id = new_road_id
                        remapped = True

            if remapped:
                logger.info(f"Remapped junction '{junction.name}' to reference new road {new_road_id}")

    @staticmethod
    def _junction_at_road_end(junction, road_id: str) -> bool:
        """Check if a junction connects to the END of a road using contact points.

        Examines connecting road contact points to determine which end of the
        road touches the junction. Returns True if the junction is at the road's
        end (successor side), False otherwise.

        If no connecting roads reference the road, returns False (conservative:
        don't remap when uncertain).
        """
        for cr in junction.connecting_roads:
            if cr.successor_road_id == road_id:
                # contact_point_end tells which end of the successor road
                # connects to this junction
                if cr.contact_point_end == 'end':
                    return True
                elif cr.contact_point_end == 'start':
                    return False
            if cr.predecessor_road_id == road_id:
                # contact_point_start tells which end of the predecessor road
                # connects to this junction
                if cr.contact_point_start == 'end':
                    return True
                elif cr.contact_point_start == 'start':
                    return False
        return False

    def merge_consecutive_roads(
        self,
        road1_id: str,
        road2_id: str
    ) -> Optional[Road]:
        """
        Merge two consecutive roads into one.

        Road1 must be the predecessor of Road2 (road1.successor_id == road2.id).
        The merged road keeps road1's ID and most properties. Road2 and its
        polylines are deleted after merging.

        Args:
            road1_id: ID of the first road (predecessor)
            road2_id: ID of the second road (successor)

        Returns:
            The merged road (road1 with updated data), or None on failure
        """
        import re
        from orbit.utils.geometry import (
            merge_polylines_at_junction,
            calculate_path_length,
            distance_between_points
        )

        # Get both roads
        road1 = self.get_road(road1_id)
        road2 = self.get_road(road2_id)

        if not road1 or not road2:
            logger.error(f"Road not found: road1={road1_id}, road2={road2_id}")
            return None

        # Validate that roads are consecutive
        if road1.successor_id != road2.id or road2.predecessor_id != road1.id:
            logger.error(
                f"Roads are not consecutive: road1.successor={road1.successor_id}, "
                f"road2.predecessor={road2.predecessor_id}"
            )
            return None

        # Get centerlines
        centerline1 = self.get_polyline(road1.centerline_id)
        centerline2 = self.get_polyline(road2.centerline_id)

        if not centerline1 or not centerline2:
            logger.error("Missing centerline polyline")
            return None

        # Store road1's original centerline point count for section index adjustment
        road1_point_count = len(centerline1.points)

        # Merge centerlines
        merged_centerline_pts = merge_polylines_at_junction(
            centerline1.points,
            centerline2.points,
            tolerance=5.0  # Allow some tolerance for junction points
        )

        if merged_centerline_pts is None:
            logger.error(
                f"Centerlines cannot be joined: end1={centerline1.points[-1]}, "
                f"start2={centerline2.points[0]}"
            )
            return None

        # Calculate road1's length before merge (needed for section adjustment)
        road1_length_before = calculate_path_length(centerline1.points)

        # Update road1's centerline
        centerline1.points = merged_centerline_pts

        # Merge boundary polylines by matching endpoints
        road1_boundaries = [
            bid for bid in road1.polyline_ids if bid != road1.centerline_id
        ]
        road2_boundaries = [
            bid for bid in road2.polyline_ids if bid != road2.centerline_id
        ]

        boundaries_to_delete = []

        for b1_id in road1_boundaries:
            b1 = self.get_polyline(b1_id)
            if not b1 or not b1.points:
                continue

            # Find matching boundary in road2 (by endpoint proximity)
            best_match_id = None
            best_match_dist = float('inf')

            for b2_id in road2_boundaries:
                b2 = self.get_polyline(b2_id)
                if not b2 or not b2.points:
                    continue

                dist = distance_between_points(b1.points[-1], b2.points[0])
                if dist < best_match_dist:
                    best_match_dist = dist
                    best_match_id = b2_id

            # Merge if match found within tolerance
            if best_match_id and best_match_dist < 10.0:
                b2 = self.get_polyline(best_match_id)
                merged_boundary_pts = merge_polylines_at_junction(
                    b1.points, b2.points, tolerance=10.0
                )
                if merged_boundary_pts:
                    b1.points = merged_boundary_pts
                    boundaries_to_delete.append(best_match_id)
                    road2_boundaries.remove(best_match_id)

        # Merge lane sections
        # First, keep all of road1's sections as-is
        # Then append road2's sections with adjusted s-coordinates

        for section in road2.lane_sections:
            # Adjust s-coordinates (add road1's length)
            section.s_start += road1_length_before
            section.s_end += road1_length_before

            # Adjust end_point_index (add road1's point count minus 1 for junction overlap)
            if section.end_point_index is not None:
                section.end_point_index += road1_point_count - 1

            road1.lane_sections.append(section)

        # Renumber all sections
        road1.renumber_sections()

        # Update road1's properties
        # Strip segment suffix from name if present
        base_name = road1.name
        seg_match = re.match(r'^(.*?)\s*\(seg \d+/\d+\)$', base_name)
        if seg_match:
            base_name = seg_match.group(1).strip()
        road1.name = base_name

        # Inherit road2's successor
        road1.successor_id = road2.successor_id
        road1.successor_contact = road2.successor_contact

        # Inherit road2's junction_id if it had one (at its end)
        if road2.junction_id:
            road1.junction_id = road2.junction_id

        # Remap junctions: any reference to road2 should now point to road1
        self._remap_junctions_after_road_merge(road1.id, road2.id)

        # Update any road that had road2 as predecessor to now have road1
        for road in self.roads:
            if road.predecessor_id == road2.id:
                road.predecessor_id = road1.id

        # Delete road2's polylines
        for b_id in boundaries_to_delete:
            self.remove_polyline(b_id)

        # Delete road2's centerline
        self.remove_polyline(road2.centerline_id)

        # Delete any remaining road2 boundaries that weren't merged
        for b_id in road2_boundaries:
            self.remove_polyline(b_id)

        # Delete road2
        self.remove_road(road2.id)

        logger.info(f"Merged roads into '{road1.name}' (id={road1.id})")

        return road1

    def _remap_junctions_after_road_merge(
        self,
        kept_road_id: str,
        deleted_road_id: str
    ) -> None:
        """
        Update junction references after merging roads.

        Any reference to deleted_road_id in junctions is replaced with kept_road_id.

        Args:
            kept_road_id: ID of the road that remains (merged result)
            deleted_road_id: ID of the road being deleted
        """
        for junction in self.junctions:
            remapped = False

            # Update connected_road_ids
            if deleted_road_id in junction.connected_road_ids:
                junction.connected_road_ids.remove(deleted_road_id)
                if kept_road_id not in junction.connected_road_ids:
                    junction.connected_road_ids.append(kept_road_id)
                remapped = True

            # Update entry_roads (for roundabouts)
            if deleted_road_id in junction.entry_roads:
                idx = junction.entry_roads.index(deleted_road_id)
                junction.entry_roads[idx] = kept_road_id
                remapped = True

            # Update exit_roads (for roundabouts)
            if deleted_road_id in junction.exit_roads:
                idx = junction.exit_roads.index(deleted_road_id)
                junction.exit_roads[idx] = kept_road_id
                remapped = True

            # Update connecting_roads
            for conn_road in junction.connecting_roads:
                if conn_road.predecessor_road_id == deleted_road_id:
                    conn_road.predecessor_road_id = kept_road_id
                    remapped = True
                if conn_road.successor_road_id == deleted_road_id:
                    conn_road.successor_road_id = kept_road_id
                    remapped = True

            # Update lane_connections
            for lane_conn in junction.lane_connections:
                if lane_conn.from_road_id == deleted_road_id:
                    lane_conn.from_road_id = kept_road_id
                    remapped = True
                if lane_conn.to_road_id == deleted_road_id:
                    lane_conn.to_road_id = kept_road_id
                    remapped = True

            # Update boundary segments
            if junction.boundary:
                for segment in junction.boundary.segments:
                    if segment.road_id == deleted_road_id:
                        segment.road_id = kept_road_id
                        remapped = True

            if remapped:
                logger.info(
                    f"Remapped junction '{junction.name}' references from "
                    f"{deleted_road_id} to {kept_road_id}"
                )

    # Junction management
    def add_junction(self, junction: Junction) -> None:
        """Add a junction to the project. Auto-assigns ID if empty."""
        if not junction.id:
            junction.id = self.next_id('junction')
        self.junctions.append(junction)

    def remove_junction(self, junction_id: str, cleanup_road_refs: bool = True) -> None:
        """Remove a junction from the project.

        Args:
            junction_id: ID of the junction to remove.
            cleanup_road_refs: If True, clear predecessor/successor junction
                references on roads that point to this junction. Set to False
                when the junction is being re-added immediately (e.g. modify).
        """
        if cleanup_road_refs:
            junction = self.get_junction(junction_id)
            if junction:
                for road in self.roads:
                    if road.predecessor_junction_id == junction_id:
                        road.predecessor_junction_id = None
                    if road.successor_junction_id == junction_id:
                        road.successor_junction_id = None

        self.junctions = [j for j in self.junctions if j.id != junction_id]

    def get_junction(self, junction_id: str) -> Optional[Junction]:
        """Get a junction by ID."""
        for junction in self.junctions:
            if junction.id == junction_id:
                return junction
        return None

    # Signal management
    def add_signal(self, signal: Signal) -> None:
        """Add a traffic signal to the project. Auto-assigns ID if empty."""
        if not signal.id:
            signal.id = self.next_id('signal')
        self.signals.append(signal)

    def remove_signal(self, signal_id: str) -> None:
        """Remove a signal from the project."""
        self.signals = [s for s in self.signals if s.id != signal_id]

    def get_signal(self, signal_id: str) -> Optional[Signal]:
        """Get a signal by ID."""
        for signal in self.signals:
            if signal.id == signal_id:
                return signal
        return None

    # Object management
    def add_object(self, obj: RoadObject) -> None:
        """Add a roadside object to the project. Auto-assigns ID if empty."""
        if not obj.id:
            obj.id = self.next_id('object')
        self.objects.append(obj)

    def remove_object(self, object_id: str) -> None:
        """Remove an object from the project."""
        self.objects = [o for o in self.objects if o.id != object_id]

    def get_object(self, object_id: str) -> Optional[RoadObject]:
        """Get an object by ID."""
        for obj in self.objects:
            if obj.id == object_id:
                return obj
        return None

    # Parking management
    def add_parking(self, parking: ParkingSpace) -> None:
        """Add a parking space to the project. Auto-assigns ID if empty."""
        if not parking.id:
            parking.id = self.next_id('parking')
        self.parking_spaces.append(parking)

    def remove_parking(self, parking_id: str) -> None:
        """Remove a parking space from the project."""
        self.parking_spaces = [p for p in self.parking_spaces if p.id != parking_id]

    def get_parking(self, parking_id: str) -> Optional[ParkingSpace]:
        """Get a parking space by ID."""
        for parking in self.parking_spaces:
            if parking.id == parking_id:
                return parking
        return None

    def find_closest_road(self, position: Tuple[float, float]) -> Optional[str]:
        """
        Find the road closest to a given position.

        Args:
            position: (x, y) pixel coordinates

        Returns:
            Road ID of the closest road, or None if no roads exist
        """
        if not self.roads:
            return None

        min_distance = float('inf')
        closest_road_id = None

        for road in self.roads:
            if not road.centerline_id:
                continue

            centerline_polyline = self.get_polyline(road.centerline_id)
            if not centerline_polyline or not centerline_polyline.points:
                continue

            # Calculate distance from position to road centerline
            distance = self._point_to_polyline_distance(position, centerline_polyline.points)

            if distance < min_distance:
                min_distance = distance
                closest_road_id = road.id

        return closest_road_id

    def _point_to_polyline_distance(self, point: Tuple[float, float],
                                    polyline_points: List[Tuple[float, float]]) -> float:
        """
        Calculate minimum distance from a point to a polyline.

        Args:
            point: (x, y) coordinates
            polyline_points: List of (x, y) points defining the polyline

        Returns:
            Minimum distance to the polyline
        """
        if not polyline_points:
            return float('inf')

        min_dist = float('inf')
        px, py = point

        for i in range(len(polyline_points) - 1):
            x1, y1 = polyline_points[i]
            x2, y2 = polyline_points[i + 1]

            # Distance from point to line segment
            dx, dy = x2 - x1, y2 - y1
            length_sq = dx * dx + dy * dy

            if length_sq == 0:
                # Segment is a point
                dist = ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
            else:
                # Project point onto segment
                t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / length_sq))
                proj_x = x1 + t * dx
                proj_y = y1 + t * dy
                dist = ((px - proj_x) ** 2 + (py - proj_y) ** 2) ** 0.5

            min_dist = min(min_dist, dist)

        return min_dist

    # Control point management
    def add_control_point(self, control_point: ControlPoint) -> None:
        """Add a georeferencing control point."""
        self.control_points.append(control_point)
        self.invalidate_uncertainty_cache()

    def remove_control_point(self, index: int) -> None:
        """Remove a control point by index."""
        if 0 <= index < len(self.control_points):
            self.control_points.pop(index)
            self.invalidate_uncertainty_cache()

    def has_georeferencing(self) -> bool:
        """Check if project has enough control points for georeferencing."""
        return len(self.control_points) >= 3

    def invalidate_uncertainty_cache(self) -> None:
        """Clear cached uncertainty data when GCPs change."""
        self.uncertainty_grid_cache = None
        self.uncertainty_bootstrap_grid = None
        self.uncertainty_last_computed = None

    # Save/Load
    def to_dict(self) -> Dict[str, Any]:
        """Convert project to dictionary for JSON serialization."""
        self.metadata['modified'] = datetime.now().isoformat()

        return {
            'metadata': self.metadata,
            'image_path': str(self.image_path) if self.image_path else None,
            'polylines': [p.to_dict() for p in self.polylines],
            'roads': [r.to_dict() for r in self.roads],
            'junctions': [j.to_dict() for j in self.junctions],
            'junction_groups': [jg.to_dict() for jg in self.junction_groups],
            'signals': [s.to_dict() for s in self.signals],
            'objects': [o.to_dict() for o in self.objects],
            'parking_spaces': [p.to_dict() for p in self.parking_spaces],
            'control_points': [cp.to_dict() for cp in self.control_points],
            'right_hand_traffic': bool(self.right_hand_traffic),
            'transform_method': self.transform_method,
            'country_code': self.country_code,
            'map_name': self.map_name,
            'openstreetmap_used': bool(self.openstreetmap_used),
            'junction_offset_distance_meters': self.junction_offset_distance_meters,
            'roundabout_ring_offset_distance_meters': self.roundabout_ring_offset_distance_meters,
            'roundabout_approach_offset_distance_meters': self.roundabout_approach_offset_distance_meters,
            'georef_validation': self.georef_validation,
            'uncertainty_grid_cache': self.uncertainty_grid_cache,
            'uncertainty_grid_resolution': self.uncertainty_grid_resolution,
            'uncertainty_bootstrap_grid': self.uncertainty_bootstrap_grid,
            'uncertainty_last_computed': self.uncertainty_last_computed,
            'mc_sigma_pixels': self.mc_sigma_pixels,
            'baseline_uncertainty_m': self.baseline_uncertainty_m,
            'gcp_suggestion_threshold': self.gcp_suggestion_threshold,
            'imported_geo_reference': self.imported_geo_reference,
            'enabled_sign_libraries': self.enabled_sign_libraries,
            'id_counters': {
                'polyline': self._next_polyline_id,
                'road': self._next_road_id,
                'junction': self._next_junction_id,
                'signal': self._next_signal_id,
                'object': self._next_object_id,
                'parking': self._next_parking_id,
                'connecting_road': self._next_connecting_road_id,
                'lane_connection': self._next_lane_connection_id,
                'junction_group': self._next_junction_group_id,
            }
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Project':
        """
        Create project from dictionary.

        Handles backward compatibility with older project versions.
        Old projects (v0.2.x) will be automatically migrated to v0.3.0 format.
        """
        # Check version and perform migration if needed
        metadata = data.get('metadata', {})
        version = metadata.get('version', '0.1.0')

        # Migration from old versions
        if version.startswith('0.1') or version.startswith('0.2') or version.startswith('0.3'):
            if not version.startswith('0.3'):
                logger.info(f"Migrating project from version {version}...")
                logger.info("Junctions will have empty connection lists.")
                logger.info("Use 'Auto-Generate Connections' in junction dialogs to populate connections.")
            # Junction.from_dict() handles backward compatibility automatically
            # by providing empty lists for new fields (connecting_roads, lane_connections)
            # Polyline.from_dict() handles osm_node_ids (optional field, defaults to None)
            # UUID→integer ID migration is handled by _migrate_uuid_ids() after construction
            metadata['version'] = '0.4.0'
            data['metadata'] = metadata

        image_path = data.get('image_path')
        if image_path:
            image_path = Path(image_path)

        # Build opendrive_id lookup from raw data before deserialization.
        # Old .orbit files may have opendrive_id fields that we want to prefer during migration.
        odr_id_lookup: Dict[str, str] = {}
        for collection_key in ('polylines', 'roads', 'junctions', 'signals', 'objects', 'parking_spaces'):
            for item_data in data.get(collection_key, []):
                item_id = item_data.get('id', '')
                odr_id = item_data.get('opendrive_id')
                if item_id and odr_id:
                    odr_id_lookup[item_id] = odr_id

        polylines = [Polyline.from_dict(p) for p in data.get('polylines', [])]
        roads = [Road.from_dict(r) for r in data.get('roads', [])]
        junctions = [Junction.from_dict(j) for j in data.get('junctions', [])]
        junction_groups = [JunctionGroup.from_dict(jg) for jg in data.get('junction_groups', [])]
        signals = [Signal.from_dict(s) for s in data.get('signals', [])]
        objects = [RoadObject.from_dict(o) for o in data.get('objects', [])]
        parking_spaces = [ParkingSpace.from_dict(p) for p in data.get('parking_spaces', [])]
        control_points = [ControlPoint.from_dict(cp) for cp in data.get('control_points', [])]

        project = cls(
            image_path=image_path,
            polylines=polylines,
            roads=roads,
            junctions=junctions,
            junction_groups=junction_groups,
            signals=signals,
            objects=objects,
            parking_spaces=parking_spaces,
            control_points=control_points,
            right_hand_traffic=data.get('right_hand_traffic', True),
            transform_method=data.get('transform_method', 'affine'),  # Default to affine for old projects
            country_code=data.get('country_code', 'se'),
            map_name=data.get('map_name', ''),  # Default to empty string for backward compatibility
            openstreetmap_used=data.get('openstreetmap_used', False),  # Default to False
            junction_offset_distance_meters=data.get('junction_offset_distance_meters', 8.0),  # Default to 8.0m
            roundabout_ring_offset_distance_meters=data.get('roundabout_ring_offset_distance_meters',
                data.get('roundabout_offset_distance_meters', 4.0)),  # Backward compat with old field name
            roundabout_approach_offset_distance_meters=data.get('roundabout_approach_offset_distance_meters', 8.0),
            georef_validation=data.get('georef_validation', {}),
            uncertainty_grid_cache=data.get('uncertainty_grid_cache'),
            uncertainty_grid_resolution=tuple(data.get('uncertainty_grid_resolution', [50, 50])),
            uncertainty_bootstrap_grid=data.get('uncertainty_bootstrap_grid'),
            uncertainty_last_computed=data.get('uncertainty_last_computed'),
            mc_sigma_pixels=data.get('mc_sigma_pixels', 1.5),
            baseline_uncertainty_m=data.get('baseline_uncertainty_m', 0.05),
            gcp_suggestion_threshold=data.get('gcp_suggestion_threshold', 0.2),
            imported_geo_reference=data.get('imported_geo_reference'),
            enabled_sign_libraries=data.get('enabled_sign_libraries', ['se']),  # Default to Swedish library
            metadata=data.get('metadata', {})
        )

        # Migrate UUID-based IDs to sequential integers if needed
        project._migrate_uuid_ids(odr_id_lookup)

        # Restore ID counters from saved data, then sync to ensure correctness
        id_counters = data.get('id_counters', {})
        if id_counters:
            project._next_polyline_id = id_counters.get('polyline', 1)
            project._next_road_id = id_counters.get('road', 1)
            project._next_junction_id = id_counters.get('junction', 1)
            project._next_signal_id = id_counters.get('signal', 1)
            project._next_object_id = id_counters.get('object', 1)
            project._next_parking_id = id_counters.get('parking', 1)
            project._next_connecting_road_id = id_counters.get('connecting_road', 1)
            project._next_lane_connection_id = id_counters.get('lane_connection', 1)
            project._next_junction_group_id = id_counters.get('junction_group', 1)
        # Always sync to ensure counters are >= max existing ID + 1
        project._sync_id_counters()

        return project

    def save(self, file_path: Path) -> None:
        """Save project to .orbit file."""
        file_path = Path(file_path)
        # Ensure .orbit extension
        if file_path.suffix not in ['.orbit', '.json']:
            file_path = file_path.with_suffix('.orbit')

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, file_path: Path) -> 'Project':
        """Load project from .orbit file."""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        project = cls.from_dict(data)
        # Clear any stale cross-junction road links (OpenDRIVE compliance)
        project.clear_cross_junction_road_links()
        return project

    def clear(self) -> None:
        """Clear all project data and reset ID counters."""
        self.polylines.clear()
        self.roads.clear()
        self.junctions.clear()
        self.junction_groups.clear()
        self.signals.clear()
        self.objects.clear()
        self.parking_spaces.clear()
        self.control_points.clear()
        self.image_path = None
        self.metadata = {
            'version': '0.4.0',
            'created': datetime.now().isoformat(),
            'modified': datetime.now().isoformat()
        }
        # Reset all ID counters
        self._next_polyline_id = 1
        self._next_road_id = 1
        self._next_junction_id = 1
        self._next_signal_id = 1
        self._next_object_id = 1
        self._next_parking_id = 1
        self._next_connecting_road_id = 1
        self._next_lane_connection_id = 1
        self._next_junction_group_id = 1

    def clear_cross_junction_road_links(self) -> int:
        """
        Clear predecessor/successor links between roads that connect through junctions.

        In OpenDRIVE, roads connecting through a junction should NOT have direct
        predecessor/successor links to each other. This method clears any such
        stale links that may exist from older project versions.

        Returns:
            Number of links that were cleared
        """
        cleared_count = 0
        roads_dict = {road.id: road for road in self.roads}

        for junction in self.junctions:
            connected_ids = set(junction.connected_road_ids)

            for road_id in connected_ids:
                road = roads_dict.get(road_id)
                if not road:
                    continue

                # If predecessor is another road in this junction, clear it
                if road.predecessor_id and road.predecessor_id in connected_ids:
                    road.predecessor_id = None
                    cleared_count += 1

                # If successor is another road in this junction, clear it
                if road.successor_id and road.successor_id in connected_ids:
                    road.successor_id = None
                    cleared_count += 1

        if cleared_count > 0:
            logger.info(f"Cleared {cleared_count} stale cross-junction road link(s)")

        return cleared_count

    def __repr__(self) -> str:
        return (f"Project(polylines={len(self.polylines)}, roads={len(self.roads)}, "
                f"junctions={len(self.junctions)}, signals={len(self.signals)}, "
                f"objects={len(self.objects)}, control_points={len(self.control_points)})")

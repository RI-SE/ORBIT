"""
Project data model for ORBIT.

Manages the complete project state including polylines, roads, junctions,
and georeferencing data. Handles saving/loading to .orbit files.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from orbit.utils.logging_config import get_logger

from .junction import Junction, JunctionGroup
from .object import RoadObject
from .parking import ParkingSpace
from .polyline import Polyline
from .road import Road
from .signal import Signal


def _get_version() -> str:
    """Get package version from importlib.metadata, with fallback."""
    try:
        from importlib.metadata import version
        return version("orbit")
    except Exception:
        return "0.5.0"

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
    # Distance to offset road endpoints from junction centers (meters)
    junction_offset_distance_meters: float = 8.0
    # Distance to offset ring segment endpoints from roundabout junctions (meters)
    roundabout_ring_offset_distance_meters: float = 4.0
    # Distance to offset approach road endpoints from roundabout junctions (meters)
    roundabout_approach_offset_distance_meters: float = 8.0
    georef_validation: Dict[str, Any] = field(default_factory=dict)
    uncertainty_grid_cache: Optional[List[List[float]]] = None  # Cached uncertainty grid
    uncertainty_grid_resolution: Tuple[int, int] = (50, 50)  # Grid resolution
    uncertainty_bootstrap_grid: Optional[List[List[float]]] = None  # Bootstrap analysis results
    uncertainty_last_computed: Optional[str] = None  # ISO timestamp of last computation
    mc_sigma_pixels: float = 1.5  # Measurement error for Monte Carlo (pixels)
    baseline_uncertainty_m: float = 0.05  # Baseline position uncertainty (meters)
    gcp_suggestion_threshold: float = 0.2  # Threshold for GCP suggestions (meters)
    imported_geo_reference: Optional[str] = None  # Preserved geoReference from OpenDRIVE import
    imported_origin_latitude: Optional[float] = None  # Back-projected origin lat from imported OpenDRIVE header offset
    imported_origin_longitude: Optional[float] = None  # Back-projected origin lon from imported OpenDRIVE header offset
    enabled_sign_libraries: List[str] = field(default_factory=lambda: ['se'])  # Enabled sign library IDs
    synthetic_canvas_width: Optional[int] = None  # Synthetic canvas width in pixels (no real image)
    synthetic_canvas_height: Optional[int] = None  # Synthetic canvas height in pixels (no real image)
    transform_adjustment: Optional[Dict[str, float]] = None  # Persisted geo-alignment adjustment
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ID counters for sequential ID generation (one per entity type)
    _next_polyline_id: int = field(default=1, repr=False)
    _next_road_id: int = field(default=1, repr=False)
    _next_junction_id: int = field(default=1, repr=False)
    _next_signal_id: int = field(default=1, repr=False)
    _next_object_id: int = field(default=1, repr=False)
    _next_parking_id: int = field(default=1, repr=False)
    _next_lane_connection_id: int = field(default=1, repr=False)
    _next_junction_group_id: int = field(default=1, repr=False)

    # Map from entity type name to counter attribute name
    _COUNTER_MAP: Dict[str, str] = field(default_factory=dict, repr=False, init=False)

    def __post_init__(self):
        """Initialize metadata if not provided."""
        if not self.metadata:
            self.metadata = {
                'version': _get_version(),
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
            'connecting_road': '_next_road_id',
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
        self._next_junction_id = _max_numeric_id(j.id for j in self.junctions) + 1
        self._next_signal_id = _max_numeric_id(s.id for s in self.signals) + 1
        self._next_object_id = _max_numeric_id(o.id for o in self.objects) + 1
        self._next_parking_id = _max_numeric_id(p.id for p in self.parking_spaces) + 1
        self._next_junction_group_id = _max_numeric_id(jg.id for jg in self.junction_groups) + 1

        # Roads include connecting roads now (unified storage)
        lc_ids = []
        for junction in self.junctions:
            for lc in junction.lane_connections:
                lc_ids.append(lc.id)
        self._next_road_id = _max_numeric_id(r.id for r in self.roads) + 1
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

        # Phase 1: Assign new IDs to all entities
        def _remap_entities(entities, odr_lookup):
            remap = {}
            used = set()
            counter = [1]
            for e in entities:
                odr_id = odr_lookup.get(e.id)
                new_id = _new_id(e.id, odr_id, used, counter)
                remap[e.id] = new_id
                e.id = new_id
            return remap

        polyline_remap = _remap_entities(self.polylines, odr_id_lookup)
        road_remap = _remap_entities(self.roads, odr_id_lookup)
        junction_remap = _remap_entities(self.junctions, odr_id_lookup)
        signal_remap = _remap_entities(self.signals, odr_id_lookup)
        object_remap = _remap_entities(self.objects, odr_id_lookup)
        parking_remap = _remap_entities(self.parking_spaces, odr_id_lookup)

        # Connecting road remap: subset of road_remap for connecting roads
        # Note: r.id is already remapped, so look up by new_id in road_remap values
        cr_new_ids = {r.id for r in self.roads if r.is_connecting_road}
        connecting_road_remap = {
            old: new for old, new in road_remap.items() if new in cr_new_ids
        }

        # Lane connections and junction groups (remap for side-effect only)
        all_lane_connections = [lc for j in self.junctions for lc in j.lane_connections]
        _remap_entities(all_lane_connections, {})
        _remap_entities(self.junction_groups, {})

        # Phase 2: Remap all cross-references
        self._remap_all_cross_references(
            polyline_remap, road_remap, junction_remap, signal_remap,
            connecting_road_remap
        )

        # Update version
        self.metadata['version'] = _get_version()

        logger.info(
            f"Migration complete: {len(polyline_remap)} polylines, "
            f"{len(road_remap)} roads, {len(junction_remap)} junctions, "
            f"{len(signal_remap)} signals, {len(object_remap)} objects, "
            f"{len(parking_remap)} parking spaces"
        )

    def _remap_all_cross_references(
        self,
        polyline_remap: Dict[str, str],
        road_remap: Dict[str, str],
        junction_remap: Dict[str, str],
        signal_remap: Dict[str, str],
        connecting_road_remap: Dict[str, str],
    ) -> None:
        """Remap all cross-reference fields after ID migration."""

        def _remap(old_id, table):
            if old_id is None:
                return None
            return table.get(old_id, old_id)

        def _remap_list(id_list, table):
            return [table.get(old_id, old_id) for old_id in id_list]

        for road in self.roads:
            road.centerline_id = _remap(road.centerline_id, polyline_remap)
            road.polyline_ids = _remap_list(road.polyline_ids, polyline_remap)
            road.predecessor_id = _remap(road.predecessor_id, road_remap)
            road.successor_id = _remap(road.successor_id, road_remap)
            road.junction_id = _remap(road.junction_id, junction_remap)
            road.predecessor_junction_id = _remap(
                road.predecessor_junction_id, junction_remap
            )
            road.successor_junction_id = _remap(
                road.successor_junction_id, junction_remap
            )
            for section in road.lane_sections:
                for lane in section.lanes:
                    lane.left_boundary_id = _remap(
                        lane.left_boundary_id, polyline_remap
                    )
                    lane.right_boundary_id = _remap(
                        lane.right_boundary_id, polyline_remap
                    )

        for junction in self.junctions:
            junction.connected_road_ids = _remap_list(
                junction.connected_road_ids, road_remap
            )
            junction.connecting_road_ids = _remap_list(
                junction.connecting_road_ids, connecting_road_remap
            )
            junction.entry_roads = _remap_list(junction.entry_roads, road_remap)
            junction.exit_roads = _remap_list(junction.exit_roads, road_remap)
            for lc in junction.lane_connections:
                lc.from_road_id = _remap(lc.from_road_id, road_remap) or ""
                lc.to_road_id = _remap(lc.to_road_id, road_remap) or ""
                lc.connecting_road_id = _remap(
                    lc.connecting_road_id, connecting_road_remap
                )
                lc.traffic_light_id = _remap(lc.traffic_light_id, signal_remap)
            if junction.boundary:
                for seg in junction.boundary.segments:
                    seg.road_id = _remap(seg.road_id, road_remap)

        for signal in self.signals:
            signal.road_id = _remap(signal.road_id, road_remap)

        for obj in self.objects:
            obj.road_id = _remap(obj.road_id, road_remap)

        for parking in self.parking_spaces:
            parking.road_id = _remap(parking.road_id, road_remap)

        for jg in self.junction_groups:
            jg.junction_ids = _remap_list(jg.junction_ids, junction_remap)

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

    def link_lane_connections_to_connecting_roads(self) -> int:
        """
        Match lane connections to their connecting roads by from/to road IDs.

        ConnectingRoads and LaneConnections are often created before IDs are
        assigned, so connecting_road_id and connecting_lane_id may be empty.
        This method links them after IDs have been assigned.

        Returns:
            Number of lane connections that were linked
        """
        linked = 0
        for junction in self.junctions:
            # Get connecting road objects for this junction
            cr_roads = [
                r for r in self.roads
                if r.is_connecting_road and r.id in junction.connecting_road_ids
            ]
            for lc in junction.lane_connections:
                if not lc.connecting_road_id:
                    for cr in cr_roads:
                        if (cr.predecessor_id == lc.from_road_id and
                                cr.successor_id == lc.to_road_id):
                            lc.connecting_road_id = cr.id
                            linked += 1
                            break

                # Always set connecting_lane_id when missing, even for
                # connections already linked (e.g. set during OSM import).
                # Right lanes (negative IDs) → CR lane -1; left → +1.
                if lc.connecting_lane_id is None:
                    lc.connecting_lane_id = (
                        -1 if lc.from_lane_id < 0 else 1
                    )

        return linked

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

        # Remove from junctions (connected_road_ids, connecting_road_ids,
        # lane_connections, entry/exit_roads)
        for junction in self.junctions:
            junction.remove_road(road_id)
            # Also clean up connecting_road_ids
            if road_id in junction.connecting_road_ids:
                junction.connecting_road_ids.remove(road_id)
            # Remove connecting roads that reference the deleted road
            crs_to_remove = [
                r.id for r in self.roads
                if r.is_connecting_road and r.id in junction.connecting_road_ids
                and (r.predecessor_id == road_id or r.successor_id == road_id)
            ]
            for cr_id in crs_to_remove:
                junction.remove_connecting_road(cr_id)

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

        original_centerline_points = list(centerline.points)
        s_coords = road.calculate_centerline_s_coordinates(centerline.points)
        split_s = s_coords[point_index]

        # Split centerline and create new polyline for road 2
        new_centerline = self._split_centerline(centerline, point_index)

        # Split boundary polylines
        new_boundary_ids = self._split_boundaries(
            road, polyline_id, original_centerline_points, split_s
        )

        # Distribute lane sections
        sections_road1, sections_road2 = road.distribute_lane_sections_for_split(
            split_s, point_index
        )

        # Generate segment names
        road1_name, road2_name = self._generate_split_names(road.name)

        # Store original junction links before modification
        original_junction_id = road.junction_id
        original_successor_junction_id = road.successor_junction_id
        original_predecessor_junction_id = road.predecessor_junction_id

        # Create road 2 (tail segment)
        road2 = Road(
            id=self.next_id('road'),
            name=road2_name,
            polyline_ids=[new_centerline.id] + new_boundary_ids,
            centerline_id=new_centerline.id,
            road_type=road.road_type,
            lane_info=road.lane_info,
            lane_sections=sections_road2,
            speed_limit=road.speed_limit,
            junction_id=None,
            predecessor_id=road.id,
            predecessor_contact="end",
            successor_id=road.successor_id,
            successor_contact=road.successor_contact,
            predecessor_junction_id=None,
            successor_junction_id=original_successor_junction_id
        )

        # Update road 1 (head segment)
        road.name = road1_name
        new_boundary_id_set = set(new_boundary_ids)
        road.polyline_ids = [polyline_id] + [
            bid for bid in road.polyline_ids
            if bid != polyline_id and bid not in new_boundary_id_set
        ]
        road.lane_sections = sections_road1
        road.successor_id = road2.id
        road.successor_contact = "start"
        road.predecessor_junction_id = original_predecessor_junction_id
        road.successor_junction_id = None

        self.add_road(road2)

        self._remap_junctions_after_road_split(
            road.id, road2.id, original_junction_id,
            successor_junction_id=original_successor_junction_id
        )

        logger.info(f"Split road '{road.name}' into '{road1_name}' and '{road2_name}'")
        return (road, road2)

    def _split_centerline(self, centerline: Polyline, point_index: int) -> Polyline:
        """Split a centerline at point_index, update original, return new polyline for road 2."""
        from orbit.utils.geometry import split_polyline_at_index

        pts1, pts2 = split_polyline_at_index(
            centerline.points, point_index, duplicate_point=True
        )
        n = len(centerline.points)

        def _split_array(arr):
            if arr and len(arr) == n:
                return list(arr[:point_index + 1]), list(arr[point_index:])
            return None, None

        geo1, geo2 = _split_array(centerline.geo_points)
        elev1, elev2 = _split_array(centerline.elevations)
        soff1, soff2 = _split_array(centerline.s_offsets)
        osm1, osm2 = _split_array(centerline.osm_node_ids)

        new_centerline = Polyline(
            id=self.next_id('polyline'), points=pts2,
            line_type=centerline.line_type, road_mark_type=centerline.road_mark_type
        )
        new_centerline.geo_points = geo2
        new_centerline.elevations = elev2
        new_centerline.s_offsets = soff2
        new_centerline.osm_node_ids = osm2
        new_centerline.geometry_segments = None
        self.add_polyline(new_centerline)

        centerline.points = pts1
        centerline.geo_points = geo1
        centerline.elevations = elev1
        centerline.s_offsets = soff1
        centerline.osm_node_ids = osm1
        centerline.geometry_segments = None
        return new_centerline

    def _split_boundaries(self, road: Road, centerline_id: str,
                          original_centerline_points: list,
                          split_s: float) -> list:
        """Split boundary polylines at the split s-coordinate. Returns new boundary IDs."""
        from orbit.utils.geometry import split_boundary_at_centerline_s

        new_boundary_ids = []
        for boundary_id in road.polyline_ids:
            if boundary_id == centerline_id:
                continue
            boundary = self.get_polyline(boundary_id)
            if not boundary:
                continue

            result = split_boundary_at_centerline_s(
                boundary.points, original_centerline_points, split_s
            )
            if result:
                boundary_pts1, boundary_pts2 = result
                new_boundary = Polyline(
                    id=self.next_id('polyline'), points=boundary_pts2,
                    line_type=boundary.line_type, road_mark_type=boundary.road_mark_type
                )
                new_boundary.geometry_segments = None
                self.add_polyline(new_boundary)
                new_boundary_ids.append(new_boundary.id)

                boundary.points = boundary_pts1
                boundary.geo_points = None
                boundary.elevations = None
                boundary.s_offsets = None
                boundary.osm_node_ids = None
                boundary.geometry_segments = None
        return new_boundary_ids

    @staticmethod
    def _generate_split_names(original_name: str) -> Tuple[str, str]:
        """Generate segment names for split roads."""
        import re
        seg_match = re.match(r'^(.*?)\s*\(seg \d+/\d+\)$', original_name)
        base_name = seg_match.group(1) if seg_match else original_name
        return f"{base_name} (seg 1/2)", f"{base_name} (seg 2/2)"

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
            cr_roads = [r for r in self.roads if r.id in junction.connecting_road_ids]
            references_road = (
                original_road_id in junction.connected_road_ids
                or original_road_id in junction.entry_roads
                or original_road_id in junction.exit_roads
                or any(cr.predecessor_id == original_road_id
                       or cr.successor_id == original_road_id
                       for cr in cr_roads)
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

            # Update connecting roads (now in self.roads)
            for conn_road in cr_roads:
                if conn_road.predecessor_id == original_road_id:
                    conn_road.predecessor_id = new_road_id
                    remapped = True
                if conn_road.successor_id == original_road_id:
                    conn_road.successor_id = new_road_id
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

    def _junction_at_road_end(self, junction, road_id: str) -> bool:
        """Check if a junction connects to the END of a road using contact points.

        Examines connecting road contact points to determine which end of the
        road touches the junction. Returns True if the junction is at the road's
        end (successor side), False otherwise.

        If no connecting roads reference the road, returns False (conservative:
        don't remap when uncertain).
        """
        cr_roads = [r for r in self.roads if r.id in junction.connecting_road_ids]
        for cr in cr_roads:
            if cr.successor_id == road_id:
                # successor_contact tells which end of the successor road
                # connects to this junction
                if cr.successor_contact == 'end':
                    return True
                elif cr.successor_contact == 'start':
                    return False
            if cr.predecessor_id == road_id:
                # predecessor_contact tells which end of the predecessor road
                # connects to this junction
                if cr.predecessor_contact == 'end':
                    return True
                elif cr.predecessor_contact == 'start':
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

        from orbit.utils.geometry import calculate_path_length, distance_between_points, merge_polylines_at_junction

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

            # Update connecting roads (now in self.roads)
            cr_roads = [r for r in self.roads if r.id in junction.connecting_road_ids]
            for conn_road in cr_roads:
                if conn_road.predecessor_id == deleted_road_id:
                    conn_road.predecessor_id = kept_road_id
                    remapped = True
                if conn_road.successor_id == deleted_road_id:
                    conn_road.successor_id = kept_road_id
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

    def find_nearby_road_endpoints(
        self,
        position: Tuple[float, float],
        exclude_road_id: Optional[str] = None,
        tolerance: float = 20.0
    ) -> List[Tuple[str, str, int, Tuple[float, float], float]]:
        """Find road centerline endpoints near a position.

        Only checks first/last points of each road's centerline polyline.
        Skips roads connected via junctions (junction_id set) and
        roads without a centerline.

        Args:
            position: (x, y) pixel coordinates to search near
            exclude_road_id: Road ID to exclude from results (e.g. the road being dragged)
            tolerance: Maximum distance in pixels to consider "nearby"

        Returns:
            List of (road_id, polyline_id, point_index, point_coords, distance)
            sorted by distance. point_index is 0 (start) or -1 (end).
        """
        px, py = position
        results = []

        for road in self.roads:
            if road.id == exclude_road_id:
                continue
            if road.junction_id:
                continue  # Skip connecting roads inside junctions
            if not road.centerline_id:
                continue

            centerline = self.get_polyline(road.centerline_id)
            if not centerline or len(centerline.points) < 2:
                continue

            # Check start point
            sx, sy = centerline.points[0]
            dist = ((px - sx) ** 2 + (py - sy) ** 2) ** 0.5
            if dist <= tolerance:
                results.append((road.id, road.centerline_id, 0, (sx, sy), dist))

            # Check end point
            ex, ey = centerline.points[-1]
            dist = ((px - ex) ** 2 + (py - ey) ** 2) ** 0.5
            if dist <= tolerance:
                results.append((road.id, road.centerline_id, -1, (ex, ey), dist))

        results.sort(key=lambda r: r[4])
        return results

    def enforce_road_link_coordinates(self, road_id: str) -> bool:
        """Snap a road's endpoints to match its connected roads' endpoints.

        Uses predecessor_contact/successor_contact to determine which
        endpoint on each connected road to align with.

        Args:
            road_id: ID of the road whose endpoints should be enforced

        Returns:
            True if any coordinates were changed, False otherwise
        """
        road = self.get_road(road_id)
        if not road or not road.centerline_id:
            return False

        centerline = self.get_polyline(road.centerline_id)
        if not centerline or len(centerline.points) < 2:
            return False

        changed = False

        # Enforce predecessor link
        if road.predecessor_id and not road.predecessor_junction_id:
            pred = self.get_road(road.predecessor_id)
            if pred and pred.centerline_id:
                pred_cl = self.get_polyline(pred.centerline_id)
                if pred_cl and len(pred_cl.points) >= 2:
                    # Which end of predecessor connects?
                    pred_point = (pred_cl.points[-1]
                                  if road.predecessor_contact == "end"
                                  else pred_cl.points[0])
                    # This road's start connects to predecessor
                    if centerline.points[0] != pred_point:
                        centerline.points[0] = pred_point
                        changed = True

        # Enforce successor link
        if road.successor_id and not road.successor_junction_id:
            succ = self.get_road(road.successor_id)
            if succ and succ.centerline_id:
                succ_cl = self.get_polyline(succ.centerline_id)
                if succ_cl and len(succ_cl.points) >= 2:
                    # Which end of successor connects?
                    succ_point = (succ_cl.points[0]
                                  if road.successor_contact == "start"
                                  else succ_cl.points[-1])
                    # This road's end connects to successor
                    if centerline.points[-1] != succ_point:
                        centerline.points[-1] = succ_point
                        changed = True

        return changed

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

    def find_closest_road_or_cr(self, position: Tuple[float, float]) -> Optional[str]:
        """
        Find the road or connecting road closest to a given position.

        Searches all roads (both regular and connecting) in a single pass.

        Args:
            position: (x, y) pixel coordinates

        Returns:
            ID of the closest road, or None if none exist
        """
        min_distance = float('inf')
        closest_id = None

        for road in self.roads:
            if road.is_connecting_road:
                # Connecting road: use inline path
                path = road.inline_path
                if not path or len(path) < 2:
                    continue
                distance = self._point_to_polyline_distance(position, path)
            else:
                # Regular road: use centerline polyline
                if not road.centerline_id:
                    continue
                polyline = self.get_polyline(road.centerline_id)
                if not polyline or not polyline.points:
                    continue
                distance = self._point_to_polyline_distance(position, polyline.points)
            if distance < min_distance:
                min_distance = distance
                closest_id = road.id

        return closest_id

    def get_connecting_road(self, cr_id: str) -> Optional[Road]:
        """
        Get a connecting road by ID.

        This is now just an alias for get_road() since connecting roads
        are stored in the unified roads list.

        Args:
            cr_id: Connecting road ID

        Returns:
            Road if found and is a connecting road, None otherwise
        """
        road = self.get_road(cr_id)
        if road and road.is_connecting_road:
            return road
        return None

    def get_connecting_roads_for_junction(self, junction_id: str) -> List[Road]:
        """
        Get all connecting roads belonging to a junction.

        Args:
            junction_id: Junction ID

        Returns:
            List of Road objects that are connecting roads for this junction
        """
        junction = self.get_junction(junction_id)
        if not junction:
            return []
        return [
            r for r in self.roads
            if r.id in junction.connecting_road_ids and r.is_connecting_road
        ]

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
            'imported_origin_latitude': self.imported_origin_latitude,
            'imported_origin_longitude': self.imported_origin_longitude,
            'enabled_sign_libraries': self.enabled_sign_libraries,
            'synthetic_canvas_width': self.synthetic_canvas_width,
            'synthetic_canvas_height': self.synthetic_canvas_height,
            'transform_adjustment': self.transform_adjustment,
            'id_counters': {
                'polyline': self._next_polyline_id,
                'road': self._next_road_id,
                'junction': self._next_junction_id,
                'signal': self._next_signal_id,
                'object': self._next_object_id,
                'parking': self._next_parking_id,
                'lane_connection': self._next_lane_connection_id,
                'junction_group': self._next_junction_group_id,
            }
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Project':
        """Create project from dictionary with automatic backward-compatibility migration."""
        _apply_version_migration(data)

        odr_id_lookup = _build_odr_id_lookup(data)
        roads, junctions_data = _deserialize_entities(data)

        project = cls(
            image_path=Path(data['image_path']) if data.get('image_path') else None,
            polylines=[Polyline.from_dict(p) for p in data.get('polylines', [])],
            roads=roads,
            junctions=[Junction.from_dict(j) for j in junctions_data],
            junction_groups=[JunctionGroup.from_dict(jg) for jg in data.get('junction_groups', [])],
            signals=[Signal.from_dict(s) for s in data.get('signals', [])],
            objects=[RoadObject.from_dict(o) for o in data.get('objects', [])],
            parking_spaces=[ParkingSpace.from_dict(p) for p in data.get('parking_spaces', [])],
            control_points=[ControlPoint.from_dict(cp) for cp in data.get('control_points', [])],
            right_hand_traffic=data.get('right_hand_traffic', True),
            transform_method=data.get('transform_method', 'affine'),
            country_code=data.get('country_code', 'se'),
            map_name=data.get('map_name', ''),
            openstreetmap_used=data.get('openstreetmap_used', False),
            junction_offset_distance_meters=data.get('junction_offset_distance_meters', 8.0),
            roundabout_ring_offset_distance_meters=data.get(
                'roundabout_ring_offset_distance_meters',
                data.get('roundabout_offset_distance_meters', 4.0)
            ),
            roundabout_approach_offset_distance_meters=data.get(
                'roundabout_approach_offset_distance_meters', 8.0
            ),
            georef_validation=data.get('georef_validation', {}),
            uncertainty_grid_cache=data.get('uncertainty_grid_cache'),
            uncertainty_grid_resolution=tuple(data.get('uncertainty_grid_resolution', [50, 50])),
            uncertainty_bootstrap_grid=data.get('uncertainty_bootstrap_grid'),
            uncertainty_last_computed=data.get('uncertainty_last_computed'),
            mc_sigma_pixels=data.get('mc_sigma_pixels', 1.5),
            baseline_uncertainty_m=data.get('baseline_uncertainty_m', 0.05),
            gcp_suggestion_threshold=data.get('gcp_suggestion_threshold', 0.2),
            imported_geo_reference=data.get('imported_geo_reference'),
            imported_origin_latitude=data.get('imported_origin_latitude'),
            imported_origin_longitude=data.get('imported_origin_longitude'),
            enabled_sign_libraries=data.get('enabled_sign_libraries', ['se']),
            synthetic_canvas_width=data.get('synthetic_canvas_width'),
            synthetic_canvas_height=data.get('synthetic_canvas_height'),
            transform_adjustment=data.get('transform_adjustment'),
            metadata=data.get('metadata', {})
        )

        project._migrate_uuid_ids(odr_id_lookup)
        _restore_id_counters(project, data)
        return project

    def save(self, file_path: Path) -> None:
        """Save project to .orbit file.

        Stores image_path as relative to the save location when possible.
        """
        file_path = Path(file_path)
        # Ensure .orbit extension
        if file_path.suffix not in ['.orbit', '.json']:
            file_path = file_path.with_suffix('.orbit')

        data = self.to_dict()
        # Convert absolute image path to relative for portability
        if self.image_path and self.image_path.is_absolute():
            try:
                data['image_path'] = str(
                    self.image_path.relative_to(file_path.parent.resolve())
                )
            except ValueError:
                pass  # Keep absolute if not relative to project dir

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, file_path: Path) -> 'Project':
        """Load project from .orbit file."""
        file_path = Path(file_path)
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        project = cls.from_dict(data)
        # Resolve relative image paths against the project file's directory
        if project.image_path and not project.image_path.is_absolute():
            project.image_path = (file_path.parent / project.image_path).resolve()
        # Clean up data integrity issues from older versions
        project.cleanup_junction_connected_road_ids()
        project.cleanup_empty_junctions()
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
            'version': _get_version(),
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
        self._next_lane_connection_id = 1
        self._next_junction_group_id = 1

    def cleanup_junction_connected_road_ids(self) -> int:
        """
        Remove invalid entries from junction connected_road_ids lists.

        Removes IDs that are connecting roads (should not be in this list)
        or that reference roads which no longer exist. Older imports incorrectly
        added connecting road IDs here, and road deletion may leave orphans.

        Returns:
            Number of stale entries removed
        """
        removed = 0
        road_ids = {r.id for r in self.roads}

        for junction in self.junctions:
            cr_ids = set(junction.connecting_road_ids)
            before = len(junction.connected_road_ids)
            junction.connected_road_ids = [
                rid for rid in junction.connected_road_ids
                if rid in road_ids and rid not in cr_ids
            ]
            removed += before - len(junction.connected_road_ids)

        if removed > 0:
            logger.info(
                f"Cleaned {removed} invalid entry/entries from junction connected_road_ids"
            )
        return removed

    def cleanup_empty_junctions(self) -> int:
        """
        Remove junctions that have no usable content.

        A non-virtual junction is considered empty if it has fewer than 2
        connected roads or has no lane connections. Such junctions produce
        empty <junction> elements in OpenDRIVE export.

        Returns:
            Number of junctions removed
        """
        to_remove = []
        for junction in self.junctions:
            if junction.junction_type == "virtual":
                continue
            if len(junction.connected_road_ids) < 2 or not junction.lane_connections:
                to_remove.append(junction.id)

        for junction_id in to_remove:
            self.remove_junction(junction_id)

        if to_remove:
            logger.info(f"Removed {len(to_remove)} empty junction(s): {to_remove}")
        return len(to_remove)

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


# ---------------------------------------------------------------------------
# Module-level helpers for Project.from_dict()
# Defined after the class so Road/Junction are available at call time.
# ---------------------------------------------------------------------------

def _apply_version_migration(data: Dict[str, Any]) -> None:
    """Update version metadata and log migration notice for old project files."""
    metadata = data.get('metadata', {})
    version = metadata.get('version', '0.1.0')
    if version.startswith('0.1') or version.startswith('0.2') or version.startswith('0.3'):
        if not version.startswith('0.3'):
            logger.info(f"Migrating project from version {version}...")
            logger.info("Junctions will have empty connection lists.")
            logger.info("Use 'Auto-Generate Connections' in junction dialogs to populate connections.")
        metadata['version'] = _get_version()
        data['metadata'] = metadata


def _build_odr_id_lookup(data: Dict[str, Any]) -> Dict[str, str]:
    """Build {item_id: opendrive_id} mapping from raw project data."""
    odr_id_lookup: Dict[str, str] = {}
    for collection_key in ('polylines', 'roads', 'junctions', 'signals', 'objects', 'parking_spaces'):
        for item_data in data.get(collection_key, []):
            item_id = item_data.get('id', '')
            odr_id = item_data.get('opendrive_id')
            if item_id and odr_id:
                odr_id_lookup[item_id] = odr_id
    return odr_id_lookup


def _deserialize_entities(data: Dict[str, Any]) -> Tuple[List[Road], List[Dict[str, Any]]]:
    """Deserialize roads (including legacy connecting roads) and return (roads, junctions_data)."""
    roads = [Road.from_dict(r) for r in data.get('roads', [])]

    junctions_data = data.get('junctions', [])
    for j_data in junctions_data:
        legacy_crs = j_data.get('connecting_roads', [])
        if legacy_crs and not j_data.get('connecting_road_ids'):
            junction_id = j_data.get('id', '')
            cr_ids = []
            for cr_data in legacy_crs:
                cr_road = Road.from_connecting_road_dict(cr_data, junction_id)
                roads.append(cr_road)
                cr_ids.append(cr_road.id)
            j_data['connecting_road_ids'] = cr_ids
            j_data.pop('connecting_roads', None)

    return roads, junctions_data


def _restore_id_counters(project: 'Project', data: Dict[str, Any]) -> None:
    """Restore ID counters from saved data and sync to ensure correctness."""
    id_counters = data.get('id_counters', {})
    if id_counters:
        project._next_polyline_id = id_counters.get('polyline', 1)
        project._next_road_id = id_counters.get('road', 1)
        project._next_junction_id = id_counters.get('junction', 1)
        project._next_signal_id = id_counters.get('signal', 1)
        project._next_object_id = id_counters.get('object', 1)
        project._next_parking_id = id_counters.get('parking', 1)
        project._next_lane_connection_id = id_counters.get('lane_connection', 1)
        project._next_junction_group_id = id_counters.get('junction_group', 1)
    project._sync_id_counters()

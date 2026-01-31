"""
Junction data model for ORBIT.

Represents an intersection or junction where multiple roads connect.
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

from .connecting_road import ConnectingRoad
from .lane_connection import LaneConnection


@dataclass
class JunctionBoundarySegment:
    """
    A segment of a junction boundary.

    Segments run counter-clockwise around the junction and form a closed boundary.
    Two types: 'lane' (follows lane edge) and 'joint' (perpendicular at road start/end).
    """
    segment_type: str  # 'lane' or 'joint'
    road_id: Optional[str] = None

    # For 'lane' type segments
    boundary_lane: Optional[int] = None  # Lane ID whose outer edge forms the segment
    s_start: Optional[float] = None
    s_end: Optional[float] = None

    # For 'joint' type segments
    contact_point: Optional[str] = None  # 'start' or 'end'
    joint_lane_start: Optional[int] = None
    joint_lane_end: Optional[int] = None
    transition_length: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = {
            'segment_type': self.segment_type,
            'road_id': self.road_id
        }
        if self.segment_type == 'lane':
            if self.boundary_lane is not None:
                data['boundary_lane'] = self.boundary_lane
            if self.s_start is not None:
                data['s_start'] = self.s_start
            if self.s_end is not None:
                data['s_end'] = self.s_end
        elif self.segment_type == 'joint':
            if self.contact_point:
                data['contact_point'] = self.contact_point
            if self.joint_lane_start is not None:
                data['joint_lane_start'] = self.joint_lane_start
            if self.joint_lane_end is not None:
                data['joint_lane_end'] = self.joint_lane_end
            if self.transition_length is not None:
                data['transition_length'] = self.transition_length
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'JunctionBoundarySegment':
        """Create from dictionary."""
        return cls(
            segment_type=data.get('segment_type', 'lane'),
            road_id=data.get('road_id'),
            boundary_lane=data.get('boundary_lane'),
            s_start=data.get('s_start'),
            s_end=data.get('s_end'),
            contact_point=data.get('contact_point'),
            joint_lane_start=data.get('joint_lane_start'),
            joint_lane_end=data.get('joint_lane_end'),
            transition_length=data.get('transition_length')
        )


@dataclass
class JunctionElevationGridPoint:
    """A point in the junction elevation grid."""
    center: Optional[str] = None  # Space-separated z-values
    left: Optional[str] = None    # Space-separated z-values (inside to outside)
    right: Optional[str] = None   # Space-separated z-values (inside to outside)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = {}
        if self.center:
            data['center'] = self.center
        if self.left:
            data['left'] = self.left
        if self.right:
            data['right'] = self.right
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'JunctionElevationGridPoint':
        """Create from dictionary."""
        return cls(
            center=data.get('center'),
            left=data.get('left'),
            right=data.get('right')
        )


@dataclass
class JunctionElevationGrid:
    """
    Elevation grid for junction surface (V1.8 feature).

    A coarse square grid with z-values at evenly spaced points.
    """
    grid_spacing: Optional[str] = None
    elevations: List[JunctionElevationGridPoint] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = {}
        if self.grid_spacing:
            data['grid_spacing'] = self.grid_spacing
        if self.elevations:
            data['elevations'] = [e.to_dict() for e in self.elevations]
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'JunctionElevationGrid':
        """Create from dictionary."""
        elevations = [
            JunctionElevationGridPoint.from_dict(e)
            for e in data.get('elevations', [])
        ]
        return cls(
            grid_spacing=data.get('grid_spacing'),
            elevations=elevations
        )


@dataclass
class JunctionBoundary:
    """
    Defines the boundary enclosing a junction area (V1.8 feature).

    The boundary encloses the area intended for traffic, including sidewalks.
    Segments form a closed counter-clockwise loop around the junction.
    """
    segments: List[JunctionBoundarySegment] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'segments': [s.to_dict() for s in self.segments]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'JunctionBoundary':
        """Create from dictionary."""
        segments = [
            JunctionBoundarySegment.from_dict(s)
            for s in data.get('segments', [])
        ]
        return cls(segments=segments)


@dataclass
class JunctionGroup:
    """
    Represents a group of junctions that form a logical unit.

    Used for roundabouts, complex junctions, and highway interchanges
    where multiple junction elements are seen as one navigational node.

    Attributes:
        id: Unique identifier for this junction group
        name: Optional human-readable name
        group_type: Type of junction group ('roundabout', 'complexJunction', 'highwayInterchange', 'unknown')
        junction_ids: List of junction IDs that belong to this group
    """
    id: str = ""
    name: Optional[str] = None
    group_type: str = "unknown"  # 'roundabout', 'complexJunction', 'highwayInterchange', 'unknown'
    junction_ids: List[str] = field(default_factory=list)

    def add_junction(self, junction_id: str) -> None:
        """Add a junction to this group."""
        if junction_id not in self.junction_ids:
            self.junction_ids.append(junction_id)

    def remove_junction(self, junction_id: str) -> None:
        """Remove a junction from this group."""
        if junction_id in self.junction_ids:
            self.junction_ids.remove(junction_id)

    def to_dict(self) -> Dict[str, Any]:
        """Convert junction group to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'name': self.name,
            'group_type': self.group_type,
            'junction_ids': self.junction_ids
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'JunctionGroup':
        """Create junction group from dictionary."""
        return cls(
            id=data.get('id', ''),
            name=data.get('name'),
            group_type=data.get('group_type', 'unknown'),
            junction_ids=data.get('junction_ids', [])
        )

    def __repr__(self) -> str:
        return f"JunctionGroup(id={self.id}, type='{self.group_type}', junctions={len(self.junction_ids)})"


@dataclass
class JunctionConnection:
    """
    Represents a connection between two roads at a junction.

    Attributes:
        incoming_road_id: ID of the incoming road
        connecting_road_id: ID of the connecting road
        contact_point: Start or end of the connecting road ('start' or 'end')
    """
    incoming_road_id: str
    connecting_road_id: str
    contact_point: str = "start"  # 'start' or 'end'

    def to_dict(self) -> Dict[str, Any]:
        """Convert connection to dictionary."""
        return {
            'incoming_road_id': self.incoming_road_id,
            'connecting_road_id': self.connecting_road_id,
            'contact_point': self.contact_point
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'JunctionConnection':
        """Create connection from dictionary."""
        return cls(
            incoming_road_id=data['incoming_road_id'],
            connecting_road_id=data['connecting_road_id'],
            contact_point=data.get('contact_point', 'start')
        )


@dataclass
class Junction:
    """
    Represents a junction/intersection in the road network.

    Coordinates can be stored as:
    - pixel coordinates (center_point, roundabout_center) - used for display
    - geographic coordinates (geo_center_point, geo_roundabout_center) - source of truth for imports

    When geo coords are set, pixel coords can be recomputed via get_pixel_center_point()
    using a transformer. This enables adjustment of georeferencing alignment.

    Attributes:
        id: Unique identifier for this junction
        name: Human-readable name for the junction
        center_point: Approximate center point (x, y) in pixels
        geo_center_point: Geographic center point (lon, lat) - source of truth for imports
        connected_road_ids: List of road IDs that connect at this junction
        connections: List of road-level connections (imported from OpenDRIVE)
        junction_type: Type of junction (e.g., 'default', 'virtual')

        # New fields for enhanced junction support (v0.3.0+):
        connecting_roads: List of ConnectingRoad objects providing junction geometry
        lane_connections: List of LaneConnection objects for lane-level mappings
        is_roundabout: Whether this junction is a roundabout
        roundabout_center: Center point for roundabout (x, y) in pixels
        geo_roundabout_center: Geographic roundabout center (lon, lat) - source of truth for imports
        roundabout_radius: Radius of roundabout in pixels
        roundabout_lane_count: Number of lanes in circular road
        roundabout_clockwise: True for left-hand traffic, False for right-hand
        entry_roads: Road IDs that enter the roundabout
        exit_roads: Road IDs that exit the roundabout
    """
    id: str = ""
    name: str = "Unnamed Junction"
    center_point: Optional[Tuple[float, float]] = None
    geo_center_point: Optional[Tuple[float, float]] = None  # (lon, lat) - source of truth for imports
    connected_road_ids: List[str] = field(default_factory=list)
    connections: List[JunctionConnection] = field(default_factory=list)  # Road-level connections from OpenDRIVE
    junction_type: str = "default"  # OpenDrive junction type

    # New fields for enhanced junction support (v0.3.0+)
    connecting_roads: List[ConnectingRoad] = field(default_factory=list)
    lane_connections: List[LaneConnection] = field(default_factory=list)
    boundary: Optional[JunctionBoundary] = None  # V1.8 junction boundary
    elevation_grid: Optional[JunctionElevationGrid] = None  # V1.8 elevation grid
    is_roundabout: bool = False
    roundabout_center: Optional[Tuple[float, float]] = None
    geo_roundabout_center: Optional[Tuple[float, float]] = None  # (lon, lat) - source of truth for imports
    roundabout_radius: Optional[float] = None
    roundabout_lane_count: int = 1
    roundabout_clockwise: bool = False
    entry_roads: List[str] = field(default_factory=list)
    exit_roads: List[str] = field(default_factory=list)
    # Turn restrictions from OSM (list of restriction dicts)
    # Each dict has: type, from_osm_way, to_osm_way, via_node/via_way, action
    turn_restrictions: List[Dict[str, Any]] = field(default_factory=list)

    def has_geo_coords(self) -> bool:
        """Check if this junction has geographic coordinates stored."""
        return self.geo_center_point is not None

    def get_pixel_center_point(self, transformer=None) -> Optional[Tuple[float, float]]:
        """
        Get center point in pixel coordinates.

        If geo_center_point is available and a transformer is provided,
        computes pixel coordinates from geo coordinates.
        Otherwise returns the stored pixel coordinates.

        Args:
            transformer: CoordinateTransformer for geo→pixel conversion

        Returns:
            (x, y) pixel coordinates or None
        """
        if self.geo_center_point and transformer:
            return transformer.geo_to_pixel(self.geo_center_point[0], self.geo_center_point[1])
        return self.center_point

    def get_pixel_roundabout_center(self, transformer=None) -> Optional[Tuple[float, float]]:
        """
        Get roundabout center in pixel coordinates.

        If geo_roundabout_center is available and a transformer is provided,
        computes pixel coordinates from geo coordinates.
        Otherwise returns the stored pixel coordinates.

        Args:
            transformer: CoordinateTransformer for geo→pixel conversion

        Returns:
            (x, y) pixel coordinates or None
        """
        if self.geo_roundabout_center and transformer:
            return transformer.geo_to_pixel(self.geo_roundabout_center[0], self.geo_roundabout_center[1])
        return self.roundabout_center

    def update_pixel_coords_from_geo(self, transformer) -> None:
        """
        Update stored pixel coords from geo coordinates using transformer.

        Call this after changing the transformer (e.g., adjustment) to
        update the cached pixel coordinates.

        Args:
            transformer: CoordinateTransformer for geo→pixel conversion
        """
        if self.geo_center_point and transformer:
            self.center_point = transformer.geo_to_pixel(self.geo_center_point[0], self.geo_center_point[1])
        if self.geo_roundabout_center and transformer:
            self.roundabout_center = transformer.geo_to_pixel(self.geo_roundabout_center[0], self.geo_roundabout_center[1])

    def add_road(self, road_id: str) -> None:
        """Add a road to this junction."""
        if road_id not in self.connected_road_ids:
            self.connected_road_ids.append(road_id)

    def remove_road(self, road_id: str) -> None:
        """Remove a road from this junction."""
        if road_id in self.connected_road_ids:
            self.connected_road_ids.remove(road_id)
            # Also remove any connections involving this road
            self.connections = [
                conn for conn in self.connections
                if conn.incoming_road_id != road_id and conn.connecting_road_id != road_id
            ]

    def add_connection(self, connection: JunctionConnection) -> None:
        """Add a connection between roads at this junction."""
        self.connections.append(connection)

    def is_valid(self) -> bool:
        """Check if the junction has at least two connected roads."""
        return len(self.connected_road_ids) >= 2

    def add_connecting_road(self, connecting_road: ConnectingRoad) -> None:
        """
        Add a connecting road to this junction.

        Args:
            connecting_road: ConnectingRoad object to add
        """
        if connecting_road not in self.connecting_roads:
            self.connecting_roads.append(connecting_road)

    def remove_connecting_road(self, connecting_road_id: str) -> None:
        """
        Remove a connecting road and its associated lane connections.

        Args:
            connecting_road_id: ID of the connecting road to remove
        """
        # Remove the connecting road
        self.connecting_roads = [
            cr for cr in self.connecting_roads if cr.id != connecting_road_id
        ]

        # Remove associated lane connections
        self.lane_connections = [
            lc for lc in self.lane_connections
            if lc.connecting_road_id != connecting_road_id
        ]

    def add_lane_connection(self, lane_connection: LaneConnection) -> None:
        """
        Add a lane-level connection.

        Args:
            lane_connection: LaneConnection object to add
        """
        if lane_connection not in self.lane_connections:
            self.lane_connections.append(lane_connection)

    def remove_lane_connection(self, lane_connection_id: str) -> None:
        """
        Remove a lane connection by ID.

        Args:
            lane_connection_id: ID of the lane connection to remove
        """
        self.lane_connections = [
            lc for lc in self.lane_connections if lc.id != lane_connection_id
        ]

    def get_connections_for_road_pair(self, from_road_id: str, to_road_id: str) -> List[LaneConnection]:
        """
        Get all lane connections between two specific roads.

        Args:
            from_road_id: ID of the incoming road
            to_road_id: ID of the outgoing road

        Returns:
            List of LaneConnection objects connecting these roads
        """
        return [
            lc for lc in self.lane_connections
            if lc.from_road_id == from_road_id and lc.to_road_id == to_road_id
        ]

    def get_connections_by_turn_type(self, turn_type: str) -> List[LaneConnection]:
        """
        Get all lane connections of a specific turn type.

        Args:
            turn_type: Turn type to filter by ('straight', 'left', 'right', etc.)

        Returns:
            List of LaneConnection objects with matching turn type
        """
        return [lc for lc in self.lane_connections if lc.turn_type == turn_type]

    def get_connecting_road_by_id(self, connecting_road_id: str) -> Optional[ConnectingRoad]:
        """
        Find a connecting road by its ID.

        Args:
            connecting_road_id: ID of the connecting road to find

        Returns:
            ConnectingRoad object or None if not found
        """
        for cr in self.connecting_roads:
            if cr.id == connecting_road_id:
                return cr
        return None

    def validate_enhanced(self) -> Tuple[bool, List[str]]:
        """
        Validate junction structure including new connection data.

        Returns:
            Tuple of (is_valid, list of error messages)
        """
        errors = []

        # Basic validation
        if not self.is_valid():
            errors.append("Junction must have at least 2 connected roads")

        # Validate lane connections
        for lc in self.lane_connections:
            is_valid, lc_errors = lc.validate_basic()
            if not is_valid:
                errors.extend([f"Lane connection {lc.id}: {err}" for err in lc_errors])

        # Check connecting road references
        for lc in self.lane_connections:
            if lc.connecting_road_id:
                if not self.get_connecting_road_by_id(lc.connecting_road_id):
                    errors.append(
                        f"Lane connection {lc.id} references non-existent "
                        f"connecting road {lc.connecting_road_id}"
                    )

        # Check road IDs in lane connections match connected roads
        all_road_ids = set(self.connected_road_ids)
        for lc in self.lane_connections:
            if lc.from_road_id and lc.from_road_id not in all_road_ids:
                errors.append(
                    f"Lane connection references unknown from_road: {lc.from_road_id}"
                )
            if lc.to_road_id and lc.to_road_id not in all_road_ids:
                errors.append(
                    f"Lane connection references unknown to_road: {lc.to_road_id}"
                )

        # Roundabout-specific validation
        if self.is_roundabout:
            if self.roundabout_center is None:
                errors.append("Roundabout must have center point")
            if self.roundabout_radius is None or self.roundabout_radius <= 0:
                errors.append("Roundabout must have positive radius")
            if self.roundabout_lane_count < 1:
                errors.append("Roundabout must have at least 1 lane")

        return (len(errors) == 0, errors)

    def get_connection_summary(self) -> Dict[str, int]:
        """
        Get summary statistics about connections.

        Returns:
            Dictionary with connection counts by type
        """
        summary = {
            'total_connections': len(self.lane_connections),
            'connecting_roads': len(self.connecting_roads),
            'straight': len(self.get_connections_by_turn_type('straight')),
            'left': len(self.get_connections_by_turn_type('left')),
            'right': len(self.get_connections_by_turn_type('right')),
            'uturn': len(self.get_connections_by_turn_type('uturn')),
            'other': len(self.get_connections_by_turn_type('unknown'))
        }
        return summary

    # =========================================================================
    # Roundabout helper methods
    # =========================================================================

    def set_as_roundabout_junction(
        self,
        center: Tuple[float, float],
        radius: float,
        lane_count: int = 1,
        clockwise: bool = False
    ) -> None:
        """
        Configure this junction as a roundabout entry/exit point.

        Args:
            center: Roundabout center point (x, y) in pixels
            radius: Roundabout radius in pixels
            lane_count: Number of lanes in the circular road (default: 1)
            clockwise: True for left-hand traffic (default: False for right-hand)
        """
        self.is_roundabout = True
        self.roundabout_center = center
        self.roundabout_radius = radius
        self.roundabout_lane_count = lane_count
        self.roundabout_clockwise = clockwise

    def add_roundabout_entry(self, road_id: str) -> None:
        """
        Add a road as an entry point to this roundabout junction.

        Args:
            road_id: ID of the road that can enter the roundabout
        """
        if road_id not in self.entry_roads:
            self.entry_roads.append(road_id)

    def add_roundabout_exit(self, road_id: str) -> None:
        """
        Add a road as an exit point from this roundabout junction.

        Args:
            road_id: ID of the road that vehicles can exit to
        """
        if road_id not in self.exit_roads:
            self.exit_roads.append(road_id)

    def get_ring_road_ids(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Get ring road IDs for roundabout junctions.

        Ring roads are connected roads that are NOT in the entry/exit lists.
        Typically there are two: incoming ring segment and outgoing ring segment.

        Returns:
            Tuple of (incoming_ring_id, outgoing_ring_id).
            Either or both may be None if not found.
        """
        if not self.is_roundabout:
            return (None, None)

        # Ring roads are connected_road_ids that are NOT in entry/exit lists
        ring_ids = [
            rid for rid in self.connected_road_ids
            if rid not in self.entry_roads and rid not in self.exit_roads
        ]

        if len(ring_ids) >= 2:
            return (ring_ids[0], ring_ids[1])
        elif len(ring_ids) == 1:
            return (ring_ids[0], None)
        return (None, None)

    def get_approach_road_ids(self) -> List[str]:
        """
        Get all approach road IDs (roads that enter or exit the roundabout).

        Returns:
            List of road IDs that are in either entry_roads or exit_roads
        """
        approach_ids = set(self.entry_roads) | set(self.exit_roads)
        return list(approach_ids)

    def to_dict(self) -> Dict[str, Any]:
        """Convert junction to dictionary for JSON serialization."""
        data = {
            'id': self.id,
            'name': self.name,
            'center_point': self.center_point,
            'connected_road_ids': self.connected_road_ids,
            'connections': [conn.to_dict() for conn in self.connections],  # Kept for backward compatibility
            'junction_type': self.junction_type,
            # New fields (v0.3.0+)
            'connecting_roads': [cr.to_dict() for cr in self.connecting_roads],
            'lane_connections': [lc.to_dict() for lc in self.lane_connections],
            'is_roundabout': bool(self.is_roundabout),
            'roundabout_lane_count': self.roundabout_lane_count,
            'roundabout_clockwise': bool(self.roundabout_clockwise),
            'entry_roads': self.entry_roads,
            'exit_roads': self.exit_roads
        }

        # Only include optional fields if set
        if self.roundabout_center is not None:
            data['roundabout_center'] = self.roundabout_center
        if self.roundabout_radius is not None:
            data['roundabout_radius'] = self.roundabout_radius
        if self.boundary is not None:
            data['boundary'] = self.boundary.to_dict()
        if self.elevation_grid is not None:
            data['elevation_grid'] = self.elevation_grid.to_dict()
        if self.turn_restrictions:
            data['turn_restrictions'] = self.turn_restrictions
        # Include geo coords if set
        if self.geo_center_point is not None:
            data['geo_center_point'] = list(self.geo_center_point)
        if self.geo_roundabout_center is not None:
            data['geo_roundabout_center'] = list(self.geo_roundabout_center)

        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Junction':
        """
        Create junction from dictionary.

        Handles both old format (v0.2.x) and new format (v0.3.0+) for backward compatibility.
        """
        # Old format connections (deprecated but kept for compatibility)
        connections = [
            JunctionConnection.from_dict(conn_data)
            for conn_data in data.get('connections', [])
        ]

        # New format connections (v0.3.0+)
        connecting_roads = [
            ConnectingRoad.from_dict(cr_data)
            for cr_data in data.get('connecting_roads', [])
        ]

        lane_connections = [
            LaneConnection.from_dict(lc_data)
            for lc_data in data.get('lane_connections', [])
        ]

        # Handle center point conversion
        center_point = data.get('center_point')
        if center_point is not None:
            center_point = tuple(center_point)

        # Handle roundabout center conversion
        roundabout_center = data.get('roundabout_center')
        if roundabout_center is not None:
            roundabout_center = tuple(roundabout_center)

        # Handle geo coords - convert lists to tuples if present
        geo_center_point_raw = data.get('geo_center_point')
        geo_center_point = tuple(geo_center_point_raw) if geo_center_point_raw else None

        geo_roundabout_center_raw = data.get('geo_roundabout_center')
        geo_roundabout_center = tuple(geo_roundabout_center_raw) if geo_roundabout_center_raw else None

        # Handle boundary (V1.8)
        boundary = None
        boundary_data = data.get('boundary')
        if boundary_data:
            boundary = JunctionBoundary.from_dict(boundary_data)

        # Handle elevation_grid (V1.8)
        elevation_grid = None
        elev_grid_data = data.get('elevation_grid')
        if elev_grid_data:
            elevation_grid = JunctionElevationGrid.from_dict(elev_grid_data)

        return cls(
            id=data.get('id', ''),
            name=data.get('name', 'Unnamed Junction'),
            center_point=center_point,
            geo_center_point=geo_center_point,
            connected_road_ids=data.get('connected_road_ids', []),
            connections=connections,
            junction_type=data.get('junction_type', 'default'),
            # New fields (v0.3.0+) with defaults for backward compatibility
            connecting_roads=connecting_roads,
            lane_connections=lane_connections,
            boundary=boundary,
            elevation_grid=elevation_grid,
            is_roundabout=data.get('is_roundabout', False),
            roundabout_center=roundabout_center,
            geo_roundabout_center=geo_roundabout_center,
            roundabout_radius=data.get('roundabout_radius'),
            roundabout_lane_count=data.get('roundabout_lane_count', 1),
            roundabout_clockwise=data.get('roundabout_clockwise', False),
            entry_roads=data.get('entry_roads', []),
            exit_roads=data.get('exit_roads', []),
            turn_restrictions=data.get('turn_restrictions', [])
        )

    def __repr__(self) -> str:
        return f"Junction(id={self.id}, name='{self.name}', roads={len(self.connected_road_ids)})"

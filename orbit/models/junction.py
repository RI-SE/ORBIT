"""
Junction data model for ORBIT.

Represents an intersection or junction where multiple roads connect.
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
import uuid

from .connecting_road import ConnectingRoad
from .lane_connection import LaneConnection


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

    Attributes:
        id: Unique identifier for this junction
        name: Human-readable name for the junction
        center_point: Approximate center point (x, y) in pixels
        connected_road_ids: List of road IDs that connect at this junction
        connections: List of specific connections between roads (DEPRECATED, use lane_connections)
        junction_type: Type of junction (e.g., 'default', 'virtual')
        opendrive_id: Optional OpenDrive junction ID (for round-trip consistency)

        # New fields for enhanced junction support (v0.3.0+):
        connecting_roads: List of ConnectingRoad objects providing junction geometry
        lane_connections: List of LaneConnection objects for lane-level mappings
        is_roundabout: Whether this junction is a roundabout
        roundabout_center: Center point for roundabout (x, y) in pixels
        roundabout_radius: Radius of roundabout in pixels
        roundabout_lane_count: Number of lanes in circular road
        roundabout_clockwise: True for left-hand traffic, False for right-hand
        entry_roads: Road IDs that enter the roundabout
        exit_roads: Road IDs that exit the roundabout
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Unnamed Junction"
    center_point: Optional[Tuple[float, float]] = None
    connected_road_ids: List[str] = field(default_factory=list)
    connections: List[JunctionConnection] = field(default_factory=list)  # DEPRECATED
    junction_type: str = "default"  # OpenDrive junction type
    opendrive_id: Optional[str] = None  # OpenDrive ID for round-trip import/export

    # New fields for enhanced junction support (v0.3.0+)
    connecting_roads: List[ConnectingRoad] = field(default_factory=list)
    lane_connections: List[LaneConnection] = field(default_factory=list)
    is_roundabout: bool = False
    roundabout_center: Optional[Tuple[float, float]] = None
    roundabout_radius: Optional[float] = None
    roundabout_lane_count: int = 1
    roundabout_clockwise: bool = False
    entry_roads: List[str] = field(default_factory=list)
    exit_roads: List[str] = field(default_factory=list)

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
                errors.extend([f"Lane connection {lc.id[:8]}...: {err}" for err in lc_errors])

        # Check connecting road references
        for lc in self.lane_connections:
            if lc.connecting_road_id:
                if not self.get_connecting_road_by_id(lc.connecting_road_id):
                    errors.append(
                        f"Lane connection {lc.id[:8]}... references non-existent "
                        f"connecting road {lc.connecting_road_id[:8]}..."
                    )

        # Check road IDs in lane connections match connected roads
        all_road_ids = set(self.connected_road_ids)
        for lc in self.lane_connections:
            if lc.from_road_id and lc.from_road_id not in all_road_ids:
                errors.append(
                    f"Lane connection references unknown from_road: {lc.from_road_id[:8]}..."
                )
            if lc.to_road_id and lc.to_road_id not in all_road_ids:
                errors.append(
                    f"Lane connection references unknown to_road: {lc.to_road_id[:8]}..."
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
            'is_roundabout': self.is_roundabout,
            'roundabout_lane_count': self.roundabout_lane_count,
            'roundabout_clockwise': self.roundabout_clockwise,
            'entry_roads': self.entry_roads,
            'exit_roads': self.exit_roads
        }

        # Only include optional fields if set
        if self.opendrive_id is not None:
            data['opendrive_id'] = self.opendrive_id
        if self.roundabout_center is not None:
            data['roundabout_center'] = self.roundabout_center
        if self.roundabout_radius is not None:
            data['roundabout_radius'] = self.roundabout_radius

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

        return cls(
            id=data.get('id', str(uuid.uuid4())),
            name=data.get('name', 'Unnamed Junction'),
            center_point=center_point,
            connected_road_ids=data.get('connected_road_ids', []),
            connections=connections,
            junction_type=data.get('junction_type', 'default'),
            opendrive_id=data.get('opendrive_id'),
            # New fields (v0.3.0+) with defaults for backward compatibility
            connecting_roads=connecting_roads,
            lane_connections=lane_connections,
            is_roundabout=data.get('is_roundabout', False),
            roundabout_center=roundabout_center,
            roundabout_radius=data.get('roundabout_radius'),
            roundabout_lane_count=data.get('roundabout_lane_count', 1),
            roundabout_clockwise=data.get('roundabout_clockwise', False),
            entry_roads=data.get('entry_roads', []),
            exit_roads=data.get('exit_roads', [])
        )

    def __repr__(self) -> str:
        return f"Junction(id={self.id[:8]}..., name='{self.name}', roads={len(self.connected_road_ids)})"

"""
Junction data model for ORBIT.

Represents an intersection or junction where multiple roads connect.
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
import uuid


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
        connections: List of specific connections between roads
        junction_type: Type of junction (e.g., 'default', 'virtual')
        opendrive_id: Optional OpenDrive junction ID (for round-trip consistency)
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Unnamed Junction"
    center_point: Optional[Tuple[float, float]] = None
    connected_road_ids: List[str] = field(default_factory=list)
    connections: List[JunctionConnection] = field(default_factory=list)
    junction_type: str = "default"  # OpenDrive junction type
    opendrive_id: Optional[str] = None  # OpenDrive ID for round-trip import/export

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

    def to_dict(self) -> Dict[str, Any]:
        """Convert junction to dictionary for JSON serialization."""
        data = {
            'id': self.id,
            'name': self.name,
            'center_point': self.center_point,
            'connected_road_ids': self.connected_road_ids,
            'connections': [conn.to_dict() for conn in self.connections],
            'junction_type': self.junction_type
        }
        # Only include optional field if set
        if self.opendrive_id is not None:
            data['opendrive_id'] = self.opendrive_id
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Junction':
        """Create junction from dictionary."""
        connections = [
            JunctionConnection.from_dict(conn_data)
            for conn_data in data.get('connections', [])
        ]

        center_point = data.get('center_point')
        if center_point is not None:
            center_point = tuple(center_point)

        return cls(
            id=data.get('id', str(uuid.uuid4())),
            name=data.get('name', 'Unnamed Junction'),
            center_point=center_point,
            connected_road_ids=data.get('connected_road_ids', []),
            connections=connections,
            junction_type=data.get('junction_type', 'default'),
            opendrive_id=data.get('opendrive_id')
        )

    def __repr__(self) -> str:
        return f"Junction(id={self.id[:8]}..., name='{self.name}', roads={len(self.connected_road_ids)})"

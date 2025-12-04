"""
Lane connection data model for ORBIT.

Represents a lane-level connection within a junction, mapping specific lanes
from an incoming road to an outgoing road.
"""

from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass, field
import uuid


@dataclass
class LaneConnection:
    """
    Lane-level connection within a junction.

    Maps specific lanes from incoming road to outgoing road through a connecting road.
    In OpenDRIVE export, this becomes a <laneLink> element within a <connection>.

    Attributes:
        id: Unique identifier for this lane connection
        from_road_id: ID of the incoming road
        from_lane_id: Lane ID on incoming road (OpenDRIVE convention: 0=center, -N=right, +N=left)
        to_road_id: ID of the outgoing road
        to_lane_id: Lane ID on outgoing road
        connecting_road_id: Optional reference to the ConnectingRoad that provides the geometry
        connecting_lane_id: Lane ID on connecting road (used for OpenDRIVE laneLink.to attribute)
        turn_type: Classification of the turn ('straight', 'left', 'right', 'uturn', 'merge', 'diverge', 'unknown')
        priority: Priority level for conflict resolution (higher = higher priority)
        traffic_light_id: Optional reference to a traffic signal controlling this connection
        stop_line_offset: Optional distance of stop line from junction center
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Source lane
    from_road_id: str = ""
    from_lane_id: int = -1

    # Destination lane
    to_road_id: str = ""
    to_lane_id: int = -1

    # Reference to geometric path
    connecting_road_id: Optional[str] = None
    connecting_lane_id: Optional[int] = None  # Lane ID on connecting road (for OpenDRIVE laneLink.to)

    # Connection properties
    turn_type: str = "unknown"  # 'straight', 'left', 'right', 'uturn', 'merge', 'diverge', 'unknown'
    priority: int = 0

    # Traffic control (for future use)
    traffic_light_id: Optional[str] = None
    stop_line_offset: Optional[float] = None

    def get_turn_type_display(self) -> str:
        """Get human-readable turn type."""
        type_names = {
            'straight': 'Straight',
            'left': 'Left Turn',
            'right': 'Right Turn',
            'uturn': 'U-Turn',
            'merge': 'Merge',
            'diverge': 'Diverge',
            'unknown': 'Unknown'
        }
        return type_names.get(self.turn_type, 'Unknown')

    def is_valid_turn_type(self) -> bool:
        """Check if turn type is valid."""
        valid_types = {'straight', 'left', 'right', 'uturn', 'merge', 'diverge', 'unknown'}
        return self.turn_type in valid_types

    def validate_basic(self) -> Tuple[bool, List[str]]:
        """
        Perform basic validation without needing road objects.

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        # Check required fields
        if not self.from_road_id:
            errors.append("From road ID is required")
        if not self.to_road_id:
            errors.append("To road ID is required")

        # Check lane IDs are not zero (center lane shouldn't be in connections)
        if self.from_lane_id == 0:
            errors.append("From lane ID cannot be 0 (center lane)")
        if self.to_lane_id == 0:
            errors.append("To lane ID cannot be 0 (center lane)")

        # Check turn type is valid
        if not self.is_valid_turn_type():
            errors.append(f"Invalid turn type: {self.turn_type}")

        # Can't connect road to itself
        if self.from_road_id == self.to_road_id:
            errors.append("Cannot connect road to itself")

        return (len(errors) == 0, errors)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation of the lane connection
        """
        data = {
            'id': self.id,
            'from_road_id': self.from_road_id,
            'from_lane_id': self.from_lane_id,
            'to_road_id': self.to_road_id,
            'to_lane_id': self.to_lane_id,
            'turn_type': self.turn_type,
            'priority': self.priority
        }

        # Optional fields
        if self.connecting_road_id is not None:
            data['connecting_road_id'] = self.connecting_road_id
        if self.connecting_lane_id is not None:
            data['connecting_lane_id'] = self.connecting_lane_id
        if self.traffic_light_id is not None:
            data['traffic_light_id'] = self.traffic_light_id
        if self.stop_line_offset is not None:
            data['stop_line_offset'] = self.stop_line_offset

        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LaneConnection':
        """
        Create lane connection from dictionary.

        Args:
            data: Dictionary containing lane connection data

        Returns:
            New LaneConnection instance
        """
        lc = cls()
        lc.id = data.get('id', str(uuid.uuid4()))
        lc.from_road_id = data.get('from_road_id', '')
        lc.from_lane_id = data.get('from_lane_id', -1)
        lc.to_road_id = data.get('to_road_id', '')
        lc.to_lane_id = data.get('to_lane_id', -1)
        lc.connecting_road_id = data.get('connecting_road_id')
        lc.connecting_lane_id = data.get('connecting_lane_id')
        lc.turn_type = data.get('turn_type', 'unknown')
        lc.priority = data.get('priority', 0)
        lc.traffic_light_id = data.get('traffic_light_id')
        lc.stop_line_offset = data.get('stop_line_offset')

        return lc

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (f"LaneConnection(from={self.from_road_id[:8]}...:{self.from_lane_id} -> "
                f"to={self.to_road_id[:8]}...:{self.to_lane_id}, type={self.turn_type})")

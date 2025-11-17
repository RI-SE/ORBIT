"""
Lane data model for ORBIT.

Represents a lane in a road with OpenDRIVE-compliant properties.
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

from .polyline import RoadMarkType


class LaneType(Enum):
    """OpenDRIVE e_laneType enumeration."""
    NONE = "none"
    DRIVING = "driving"
    STOP = "stop"
    SHOULDER = "shoulder"
    BIKING = "biking"
    SIDEWALK = "sidewalk"
    BORDER = "border"
    RESTRICTED = "restricted"
    PARKING = "parking"
    BIDIRECTIONAL = "bidirectional"
    MEDIAN = "median"
    CURB = "curb"
    ENTRY = "entry"
    EXIT = "exit"
    ON_RAMP = "onRamp"
    OFF_RAMP = "offRamp"
    CONNECTING_RAMP = "connectingRamp"
    SLIP_LANE = "slipLane"
    BUS = "bus"
    TAXI = "taxi"
    HOV = "HOV"
    RAIL = "rail"
    TRAM = "tram"
    WALKING = "walking"
    ROAD_WORKS = "roadWorks"
    SHARED = "shared"
    OBSTACLE = "obstacle"


@dataclass
class Lane:
    """
    Represents a lane in a road.

    In OpenDRIVE:
    - Lane 0 is the center/reference lane
    - Negative IDs are right lanes (in direction of travel)
    - Positive IDs are left lanes (in direction of travel)

    Attributes:
        id: OpenDRIVE lane ID (0=center, negative=right, positive=left)
        lane_type: Type of lane (driving, biking, sidewalk, etc.)
        road_mark_type: Road marking type (solid, broken, etc.)
        width: Lane width in meters (or pixels if not georeferenced)
        left_boundary_id: Optional polyline ID defining left boundary
        right_boundary_id: Optional polyline ID defining right boundary
    """
    id: int
    lane_type: LaneType = LaneType.DRIVING
    road_mark_type: RoadMarkType = RoadMarkType.SOLID
    width: float = 3.5
    left_boundary_id: Optional[str] = None
    right_boundary_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'lane_type': self.lane_type.value,
            'road_mark_type': self.road_mark_type.value,
            'width': self.width,
            'left_boundary_id': self.left_boundary_id,
            'right_boundary_id': self.right_boundary_id
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Lane':
        """Create from dictionary."""
        return cls(
            id=data['id'],
            lane_type=LaneType(data['lane_type']),
            road_mark_type=RoadMarkType(data['road_mark_type']),
            width=data['width'],
            left_boundary_id=data.get('left_boundary_id'),
            right_boundary_id=data.get('right_boundary_id')
        )

    def get_display_name(self) -> str:
        """Get human-readable lane name."""
        if self.id == 0:
            return "Lane 0 (Center)"
        elif self.id > 0:
            return f"Lane {self.id} (Left)"
        else:
            return f"Lane {self.id} (Right)"

    def get_display_position(self) -> str:
        """Get display position (Left/Center/Right with number)."""
        if self.id == 0:
            return "Center"
        elif self.id > 0:
            return f"Left {self.id}"
        else:
            return f"Right {abs(self.id)}"

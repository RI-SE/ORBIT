"""
Lane data model for ORBIT.

Represents a lane in a road with OpenDRIVE-compliant properties.
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
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
        width: Lane width constant term 'a' in meters
        width_b: Lane width linear coefficient (ds term)
        width_c: Lane width quadratic coefficient (ds² term)
        width_d: Lane width cubic coefficient (ds³ term)
        road_mark_color: Road mark color (white, yellow, etc.)
        road_mark_weight: Road mark weight (standard, bold)
        road_mark_width: Road mark width in meters
        speed_limit: Lane-level speed limit in m/s (optional)
        speed_limit_unit: Unit for speed limit (m/s, km/h, mph)
        left_boundary_id: Optional polyline ID defining left boundary
        right_boundary_id: Optional polyline ID defining right boundary
        access_restrictions: List of allowed vehicle/user types for OpenDRIVE access element
            (e.g., ["bicycle", "pedestrian"] for shared paths)

    Width polynomial: width(ds) = a + b*ds + c*ds² + d*ds³
    where ds is distance from start of lane section.
    """
    id: int
    lane_type: LaneType = LaneType.DRIVING
    road_mark_type: RoadMarkType = RoadMarkType.SOLID
    width: float = 3.5
    width_b: float = 0.0
    width_c: float = 0.0
    width_d: float = 0.0
    road_mark_color: str = "white"
    road_mark_weight: str = "standard"
    road_mark_width: float = 0.12
    speed_limit: Optional[float] = None  # Speed limit in m/s
    speed_limit_unit: str = "m/s"  # Unit: "m/s", "km/h", or "mph"
    left_boundary_id: Optional[str] = None
    right_boundary_id: Optional[str] = None
    access_restrictions: List[str] = field(default_factory=list)
    # Lane material properties: (s_offset, friction, roughness, surface)
    materials: List[tuple] = field(default_factory=list)
    # Lane height offsets: list of (s_offset, inner_height, outer_height)
    heights: List[tuple] = field(default_factory=list)
    # Lane predecessor/successor links (lane IDs)
    predecessor_id: Optional[int] = None
    successor_id: Optional[int] = None
    # OpenDRIVE 1.8 attributes
    direction: Optional[str] = None  # "standard", "reversed", "both"
    advisory: Optional[str] = None  # "none", "inner", "outer", "both"
    level: bool = False  # Keep lane level (don't apply superelevation)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = {
            'id': self.id,
            'lane_type': self.lane_type.value,
            'road_mark_type': self.road_mark_type.value,
            'width': self.width,
            'left_boundary_id': self.left_boundary_id,
            'right_boundary_id': self.right_boundary_id
        }
        # Only include polynomial coefficients if non-zero (backward compatibility)
        if self.width_b != 0.0:
            data['width_b'] = self.width_b
        if self.width_c != 0.0:
            data['width_c'] = self.width_c
        if self.width_d != 0.0:
            data['width_d'] = self.width_d
        # Only include road mark attributes if non-default (backward compatibility)
        if self.road_mark_color != "white":
            data['road_mark_color'] = self.road_mark_color
        if self.road_mark_weight != "standard":
            data['road_mark_weight'] = self.road_mark_weight
        if self.road_mark_width != 0.12:
            data['road_mark_width'] = self.road_mark_width
        # Only include speed limit if set
        if self.speed_limit is not None:
            data['speed_limit'] = self.speed_limit
            data['speed_limit_unit'] = self.speed_limit_unit
        # Only include access restrictions if set
        if self.access_restrictions:
            data['access_restrictions'] = self.access_restrictions
        # Only include material properties if set
        if self.materials:
            data['materials'] = [list(m) for m in self.materials]
        # Only include height offsets if set
        if self.heights:
            data['heights'] = [list(h) for h in self.heights]
        # Only include lane links if set
        if self.predecessor_id is not None:
            data['predecessor_id'] = self.predecessor_id
        if self.successor_id is not None:
            data['successor_id'] = self.successor_id
        # Only include V1.8 attributes if set
        if self.direction is not None:
            data['direction'] = self.direction
        if self.advisory is not None:
            data['advisory'] = self.advisory
        if self.level:
            data['level'] = self.level
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Lane':
        """Create from dictionary."""
        return cls(
            id=data['id'],
            lane_type=LaneType(data['lane_type']),
            road_mark_type=RoadMarkType(data['road_mark_type']),
            width=data['width'],
            width_b=data.get('width_b', 0.0),
            width_c=data.get('width_c', 0.0),
            width_d=data.get('width_d', 0.0),
            road_mark_color=data.get('road_mark_color', 'white'),
            road_mark_weight=data.get('road_mark_weight', 'standard'),
            road_mark_width=data.get('road_mark_width', 0.12),
            speed_limit=data.get('speed_limit'),
            speed_limit_unit=data.get('speed_limit_unit', 'm/s'),
            left_boundary_id=data.get('left_boundary_id'),
            right_boundary_id=data.get('right_boundary_id'),
            access_restrictions=data.get('access_restrictions', []),
            materials=[tuple(m) for m in data.get('materials', [])],
            heights=[tuple(h) for h in data.get('heights', [])],
            predecessor_id=data.get('predecessor_id'),
            successor_id=data.get('successor_id'),
            direction=data.get('direction'),
            advisory=data.get('advisory'),
            level=data.get('level', False)
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

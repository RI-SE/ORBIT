"""
Polyline data model for ORBIT.

Represents a polyline drawn on the image with pixel coordinates.
"""

from typing import List, Tuple, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
import uuid


class LineType(Enum):
    """Type of line in the road network."""
    CENTERLINE = "centerline"
    LANE_BOUNDARY = "lane_boundary"


class RoadMarkType(Enum):
    """ASAM OpenDRIVE e_roadMarkType enumeration."""
    NONE = "none"
    SOLID = "solid"
    BROKEN = "broken"
    SOLID_SOLID = "solid solid"
    SOLID_BROKEN = "solid broken"
    BROKEN_SOLID = "broken solid"
    BROKEN_BROKEN = "broken broken"
    BOTTS_DOTS = "botts dots"
    GRASS = "grass"
    CURB = "curb"
    CUSTOM = "custom"
    EDGE = "edge"


@dataclass
class Polyline:
    """
    Represents a polyline with multiple points in pixel coordinates.

    Attributes:
        id: Unique identifier for this polyline
        points: List of (x, y) coordinates in pixels
        color: RGB color tuple for visualization (r, g, b)
        closed: Whether the polyline forms a closed loop
        line_type: Type of line (centerline or lane_boundary)
        road_mark_type: Road marking type (for OpenDRIVE export)
        elevations: Optional elevation values in meters for each point (from OpenDrive import)
        s_offsets: Optional s-coordinate values along polyline for each point (for display)
        opendrive_id: Optional OpenDrive road/element ID (for round-trip consistency)
        osm_node_ids: Optional OSM node IDs for each point (from OSM import, enables road splitting)
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    points: List[Tuple[float, float]] = field(default_factory=list)
    color: Tuple[int, int, int] = (0, 255, 255)  # Default cyan for lane boundaries
    closed: bool = False
    line_type: LineType = LineType.LANE_BOUNDARY  # Default to lane boundary
    road_mark_type: RoadMarkType = RoadMarkType.SOLID  # Default to solid
    elevations: Optional[List[float]] = None  # Elevation in meters for each point (if available)
    s_offsets: Optional[List[float]] = None  # S-coordinate for each point (if available)
    opendrive_id: Optional[str] = None  # OpenDrive ID for round-trip import/export
    osm_node_ids: Optional[List[Optional[int]]] = None  # OSM node IDs for each point (from OSM import)

    def add_point(self, x: float, y: float) -> None:
        """Add a point to the end of the polyline."""
        self.points.append((x, y))

    def insert_point(self, index: int, x: float, y: float) -> None:
        """Insert a point at the specified index."""
        self.points.insert(index, (x, y))

    def remove_point(self, index: int) -> None:
        """Remove a point at the specified index."""
        if 0 <= index < len(self.points):
            self.points.pop(index)

    def update_point(self, index: int, x: float, y: float) -> None:
        """Update the coordinates of a point at the specified index."""
        if 0 <= index < len(self.points):
            self.points[index] = (x, y)

    def get_point(self, index: int) -> Tuple[float, float]:
        """Get the coordinates of a point at the specified index."""
        return self.points[index]

    def point_count(self) -> int:
        """Return the number of points in the polyline."""
        return len(self.points)

    def is_valid(self) -> bool:
        """Check if the polyline has at least 2 points."""
        return len(self.points) >= 2

    def reverse(self) -> None:
        """
        Reverse the direction of the polyline.

        The point positions remain the same, but their order is reversed.
        This is useful for correcting the direction of centerlines.
        """
        self.points.reverse()

    def to_dict(self) -> Dict[str, Any]:
        """Convert polyline to dictionary for JSON serialization."""
        data = {
            'id': self.id,
            'points': self.points,
            'color': self.color,
            'closed': bool(self.closed),
            'line_type': self.line_type.value,
            'road_mark_type': self.road_mark_type.value
        }
        # Only include optional fields if they are set
        if self.elevations is not None:
            data['elevations'] = self.elevations
        if self.s_offsets is not None:
            data['s_offsets'] = self.s_offsets
        if self.opendrive_id is not None:
            data['opendrive_id'] = self.opendrive_id
        if self.osm_node_ids is not None:
            data['osm_node_ids'] = self.osm_node_ids
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Polyline':
        """Create polyline from dictionary."""
        # Handle line_type
        line_type_str = data.get('line_type', 'lane_boundary')
        try:
            line_type = LineType(line_type_str)
        except ValueError:
            line_type = LineType.LANE_BOUNDARY

        # Handle road_mark_type
        road_mark_type_str = data.get('road_mark_type', 'solid')
        try:
            road_mark_type = RoadMarkType(road_mark_type_str)
        except ValueError:
            road_mark_type = RoadMarkType.SOLID

        return cls(
            id=data.get('id', str(uuid.uuid4())),
            points=[tuple(p) for p in data.get('points', [])],
            color=tuple(data.get('color', (0, 255, 255))),
            closed=data.get('closed', False),
            line_type=line_type,
            road_mark_type=road_mark_type,
            elevations=data.get('elevations'),
            s_offsets=data.get('s_offsets'),
            opendrive_id=data.get('opendrive_id'),
            osm_node_ids=data.get('osm_node_ids')
        )

    def __repr__(self) -> str:
        return f"Polyline(id={self.id[:8]}..., points={len(self.points)})"

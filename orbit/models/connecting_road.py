"""
Connecting road data model for ORBIT.

Represents a road that exists only within a junction, providing the geometric
path for vehicles traversing the junction.
"""

from typing import List, Tuple, Dict, Any, Optional
from dataclasses import dataclass, field
import uuid
import math


@dataclass
class ConnectingRoad:
    """
    Road that exists only within a junction.

    In OpenDRIVE export, this becomes a <road> element with junction="<junction_id>".
    Connecting roads define the actual paths vehicles take when moving through
    a junction, including the geometry and lane configuration.

    Attributes:
        id: Unique identifier for this connecting road
        path: List of (x, y) points in pixel coordinates defining the path
        lane_count_left: Number of lanes on left side (positive IDs: 1, 2, 3...)
        lane_count_right: Number of lanes on right side (negative IDs: -1, -2, -3...)
        lane_width: Lane width in meters
        predecessor_road_id: ID of the incoming road (road entering junction)
        successor_road_id: ID of the outgoing road (road exiting junction)
        contact_point_start: Contact point at start ('start' or 'end' of predecessor)
        contact_point_end: Contact point at end ('start' or 'end' of successor)
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    path: List[Tuple[float, float]] = field(default_factory=list)

    # Lane configuration
    lane_count_left: int = 0
    lane_count_right: int = 1
    lane_width: float = 3.5

    # Connection to adjacent roads
    predecessor_road_id: str = ""
    successor_road_id: str = ""
    contact_point_start: str = "end"   # Where predecessor connects
    contact_point_end: str = "start"   # Where successor connects

    def get_length_pixels(self) -> float:
        """
        Calculate path length in pixels.

        Returns:
            Total length of the path by summing distances between consecutive points
        """
        if len(self.path) < 2:
            return 0.0

        length = 0.0
        for i in range(len(self.path) - 1):
            dx = self.path[i+1][0] - self.path[i][0]
            dy = self.path[i+1][1] - self.path[i][1]
            length += math.sqrt(dx * dx + dy * dy)
        return length

    def get_start_point(self) -> Optional[Tuple[float, float]]:
        """Get the starting point of the path."""
        return self.path[0] if self.path else None

    def get_end_point(self) -> Optional[Tuple[float, float]]:
        """Get the ending point of the path."""
        return self.path[-1] if self.path else None

    def get_start_heading(self) -> Optional[float]:
        """
        Calculate heading at the start of the path in radians.

        Returns:
            Heading angle in radians (0 = east, π/2 = north), or None if insufficient points
        """
        if len(self.path) < 2:
            return None

        dx = self.path[1][0] - self.path[0][0]
        dy = self.path[1][1] - self.path[0][1]
        return math.atan2(dy, dx)

    def get_end_heading(self) -> Optional[float]:
        """
        Calculate heading at the end of the path in radians.

        Returns:
            Heading angle in radians (0 = east, π/2 = north), or None if insufficient points
        """
        if len(self.path) < 2:
            return None

        dx = self.path[-1][0] - self.path[-2][0]
        dy = self.path[-1][1] - self.path[-2][1]
        return math.atan2(dy, dx)

    def get_total_lane_count(self) -> int:
        """Get total number of lanes (left + right, excluding center lane 0)."""
        return self.lane_count_left + self.lane_count_right

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation of the connecting road
        """
        return {
            'id': self.id,
            'path': [[x, y] for x, y in self.path],
            'lane_count_left': self.lane_count_left,
            'lane_count_right': self.lane_count_right,
            'lane_width': self.lane_width,
            'predecessor_road_id': self.predecessor_road_id,
            'successor_road_id': self.successor_road_id,
            'contact_point_start': self.contact_point_start,
            'contact_point_end': self.contact_point_end
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConnectingRoad':
        """
        Create connecting road from dictionary.

        Args:
            data: Dictionary containing connecting road data

        Returns:
            New ConnectingRoad instance
        """
        cr = cls()
        cr.id = data.get('id', str(uuid.uuid4()))

        # Convert path from list of lists to list of tuples
        path_data = data.get('path', [])
        cr.path = [tuple(pt) for pt in path_data]

        cr.lane_count_left = data.get('lane_count_left', 0)
        cr.lane_count_right = data.get('lane_count_right', 1)
        cr.lane_width = data.get('lane_width', 3.5)
        cr.predecessor_road_id = data.get('predecessor_road_id', '')
        cr.successor_road_id = data.get('successor_road_id', '')
        cr.contact_point_start = data.get('contact_point_start', 'end')
        cr.contact_point_end = data.get('contact_point_end', 'start')

        return cr

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (f"ConnectingRoad(id={self.id[:8]}..., "
                f"points={len(self.path)}, "
                f"lanes={self.get_total_lane_count()}, "
                f"{self.predecessor_road_id[:8]}... -> {self.successor_road_id[:8]}...)")

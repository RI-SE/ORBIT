"""
Connecting road data model for ORBIT.

Represents a road that exists only within a junction, providing the geometric
path for vehicles traversing the junction.
"""

from typing import List, Tuple, Dict, Any, Optional
from dataclasses import dataclass, field
import uuid
import math

from .lane import Lane, LaneType
from .polyline import RoadMarkType


@dataclass
class ConnectingRoad:
    """
    Road that exists only within a junction.

    In OpenDRIVE export, this becomes a <road> element with junction="<junction_id>".
    Connecting roads define the actual paths vehicles take when moving through
    a junction, including the geometry and lane configuration.

    Attributes:
        id: Unique identifier for this connecting road (UUID string)
        path: List of (x, y) points in pixel coordinates defining the path (sampled from curve)
        lane_count_left: Number of lanes on left side (positive IDs: 1, 2, 3...)
        lane_count_right: Number of lanes on right side (negative IDs: -1, -2, -3...)
        lane_width: Average lane width in meters (for backward compatibility)
        lane_width_start: Lane width at start (s=0), None to use lane_width
        lane_width_end: Lane width at end (s=length), None to use lane_width
        predecessor_road_id: ID of the incoming road (road entering junction)
        successor_road_id: ID of the outgoing road (road exiting junction)
        contact_point_start: Contact point at start ('start' or 'end' of predecessor)
        contact_point_end: Contact point at end ('start' or 'end' of successor)
        road_id: Optional numeric OpenDRIVE road ID (assigned during export)
        geometry_type: Type of geometry ("parampoly3" or "polyline")
        aU, bU, cU, dU: ParamPoly3D coefficients for u(p) polynomial
        aV, bV, cV, dV: ParamPoly3D coefficients for v(p) polynomial
        p_range: Parameter range for ParamPoly3D (typically 1.0)
        p_range_normalized: If True, pRange="normalized" (standard), else pRange=p_range value
        tangent_scale: Scale factor for tangent lengths (user-adjustable)
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    path: List[Tuple[float, float]] = field(default_factory=list)

    # Lane configuration
    lane_count_left: int = 0
    lane_count_right: int = 1
    lane_width: float = 3.5  # Average width for backward compatibility
    lane_width_start: Optional[float] = None  # Width at start (s=0), None = use lane_width
    lane_width_end: Optional[float] = None  # Width at end (s=length), None = use lane_width
    lanes: List[Lane] = field(default_factory=list)  # Actual Lane objects for property editing

    # Connection to adjacent roads
    predecessor_road_id: str = ""
    successor_road_id: str = ""
    contact_point_start: str = "end"   # Where predecessor connects
    contact_point_end: str = "start"   # Where successor connects

    # OpenDRIVE export
    road_id: Optional[int] = None  # Numeric road ID for OpenDRIVE (assigned during export)

    # ParamPoly3D geometry (new in ParamPoly3D update)
    geometry_type: str = "parampoly3"  # "parampoly3" or "polyline" (legacy)
    aU: float = 0.0
    bU: float = 0.0
    cU: float = 0.0
    dU: float = 0.0
    aV: float = 0.0
    bV: float = 0.0
    cV: float = 0.0
    dV: float = 0.0
    p_range: float = 1.0
    p_range_normalized: bool = True  # If True, use pRange="normalized" (OpenDRIVE standard)
    tangent_scale: float = 1.0  # User-adjustable tangent length scale

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

    def get_lane_polygons(self, scale: float) -> Dict[int, List[Tuple[float, float]]]:
        """
        Generate lane boundary polygons for visualization.

        This method creates polygon representations for each lane in the connecting road,
        similar to how regular Road objects generate lane polygons. The polygons are
        calculated by offsetting the centerline path based on lane widths.

        Args:
            scale: Meters per pixel scale factor (from coordinate transformer)

        Returns:
            Dictionary mapping lane IDs to polygon point lists:
            - Negative IDs (-1, -2, -3, ...) for right-hand lanes
            - Positive IDs (1, 2, 3, ...) for left-hand lanes
            - Empty dict if insufficient path points
            (OpenDRIVE convention: negative=right, positive=left)

        Example:
            {
                -1: [(x1, y1), (x2, y2), ...],   # Right lane 1
                -2: [(x1, y1), (x2, y2), ...],   # Right lane 2
                1: [(x1, y1), (x2, y2), ...],    # Left lane 1
            }
        """
        from orbit.utils.geometry import create_lane_polygon

        if len(self.path) < 2:
            return {}

        # Convert lane width from meters to pixels
        lane_width_px = self.lane_width / scale

        polygons = {}

        # Create right-hand lanes (negative IDs in OpenDRIVE: -1, -2, -3, ...)
        for lane_num in range(1, self.lane_count_right + 1):
            inner_offset = (lane_num - 1) * lane_width_px
            outer_offset = lane_num * lane_width_px

            polygon_points = create_lane_polygon(
                self.path,
                inner_offset,
                outer_offset,
                closed=False  # Connecting roads are never closed
            )

            if polygon_points and len(polygon_points) >= 3:
                polygons[-lane_num] = polygon_points  # Use negative ID for right lanes

        # Create left-hand lanes (positive IDs in OpenDRIVE: 1, 2, 3, ...)
        for lane_num in range(1, self.lane_count_left + 1):
            inner_offset = -(lane_num - 1) * lane_width_px
            outer_offset = -lane_num * lane_width_px

            polygon_points = create_lane_polygon(
                self.path,
                inner_offset,
                outer_offset,
                closed=False
            )

            if polygon_points and len(polygon_points) >= 3:
                polygons[lane_num] = polygon_points  # Use positive ID for left lanes

        return polygons

    def get_lane_ids(self) -> List[int]:
        """
        Get list of all lane IDs in order (right lanes, then left lanes).

        Returns:
            List of lane IDs: [-1, -2, ...] for right, [1, 2, ...] for left
            (OpenDRIVE convention: negative=right, positive=left)
        """
        lane_ids = []

        # Right lanes (negative IDs in OpenDRIVE: -1, -2, -3, ...)
        for i in range(1, self.lane_count_right + 1):
            lane_ids.append(-i)

        # Left lanes (positive IDs in OpenDRIVE: 1, 2, 3, ...)
        for i in range(1, self.lane_count_left + 1):
            lane_ids.append(i)

        return lane_ids

    def ensure_lanes_initialized(self):
        """
        Ensure lanes list is initialized with Lane objects.

        This creates Lane objects if they don't exist (for backward compatibility
        with old projects that only stored lane counts). Always includes center
        lane (lane 0) as required by OpenDRIVE.
        """
        if not self.lanes:
            # Create Lane objects based on lane counts
            self.lanes = []

            # Center lane (lane 0) - always required by OpenDRIVE
            center_lane = Lane(
                id=0,
                lane_type=LaneType.NONE,
                road_mark_type=RoadMarkType.NONE,
                width=0.0  # Center lane has no width
            )
            self.lanes.append(center_lane)

            # Right lanes (negative IDs in OpenDRIVE: -1, -2, -3, ...)
            for i in range(1, self.lane_count_right + 1):
                lane = Lane(
                    id=-i,
                    lane_type=LaneType.DRIVING,
                    road_mark_type=RoadMarkType.SOLID,
                    width=self.lane_width
                )
                self.lanes.append(lane)

            # Left lanes (positive IDs in OpenDRIVE: 1, 2, 3, ...)
            for i in range(1, self.lane_count_left + 1):
                lane = Lane(
                    id=i,
                    lane_type=LaneType.DRIVING,
                    road_mark_type=RoadMarkType.SOLID,
                    width=self.lane_width
                )
                self.lanes.append(lane)

    def get_lane(self, lane_id: int) -> Optional[Lane]:
        """
        Get a lane by its ID.

        Args:
            lane_id: Lane ID (negative for right, positive for left)

        Returns:
            Lane object if found, None otherwise
        """
        # Ensure lanes are initialized
        self.ensure_lanes_initialized()

        # Find lane by ID
        for lane in self.lanes:
            if lane.id == lane_id:
                return lane

        return None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation of the connecting road
        """
        # Ensure lanes are initialized before serializing
        self.ensure_lanes_initialized()

        data = {
            'id': self.id,
            'path': [[x, y] for x, y in self.path],
            'lane_count_left': self.lane_count_left,
            'lane_count_right': self.lane_count_right,
            'lane_width': self.lane_width,
            'lane_width_start': self.lane_width_start,
            'lane_width_end': self.lane_width_end,
            'lanes': [lane.to_dict() for lane in self.lanes],
            'predecessor_road_id': self.predecessor_road_id,
            'successor_road_id': self.successor_road_id,
            'contact_point_start': self.contact_point_start,
            'contact_point_end': self.contact_point_end,
            'geometry_type': self.geometry_type,
            'aU': self.aU,
            'bU': self.bU,
            'cU': self.cU,
            'dU': self.dU,
            'aV': self.aV,
            'bV': self.bV,
            'cV': self.cV,
            'dV': self.dV,
            'p_range': self.p_range,
            'p_range_normalized': self.p_range_normalized,
            'tangent_scale': self.tangent_scale
        }

        # Only include road_id if it's set
        if self.road_id is not None:
            data['road_id'] = self.road_id

        return data

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
        cr.lane_width_start = data.get('lane_width_start')  # None if not present
        cr.lane_width_end = data.get('lane_width_end')  # None if not present
        cr.predecessor_road_id = data.get('predecessor_road_id', '')
        cr.successor_road_id = data.get('successor_road_id', '')
        cr.contact_point_start = data.get('contact_point_start', 'end')
        cr.contact_point_end = data.get('contact_point_end', 'start')
        cr.road_id = data.get('road_id')  # Optional, defaults to None

        # ParamPoly3D fields (backward compatible with older projects)
        cr.geometry_type = data.get('geometry_type', 'polyline')  # Old projects use polyline
        cr.aU = data.get('aU', 0.0)
        cr.bU = data.get('bU', 0.0)
        cr.cU = data.get('cU', 0.0)
        cr.dU = data.get('dU', 0.0)
        cr.aV = data.get('aV', 0.0)
        cr.bV = data.get('bV', 0.0)
        cr.cV = data.get('cV', 0.0)
        cr.dV = data.get('dV', 0.0)
        cr.p_range = data.get('p_range', 1.0)
        cr.p_range_normalized = data.get('p_range_normalized', True)  # Default to normalized for new
        cr.tangent_scale = data.get('tangent_scale', 1.0)

        # Load lanes if present (backward compatible - will auto-initialize if missing)
        if 'lanes' in data:
            cr.lanes = [Lane.from_dict(lane_data) for lane_data in data['lanes']]
        else:
            # Old projects without lanes - will be initialized on first access
            cr.lanes = []

        return cr

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (f"ConnectingRoad(id={self.id[:8]}..., "
                f"points={len(self.path)}, "
                f"lanes={self.get_total_lane_count()}, "
                f"{self.predecessor_road_id[:8]}... -> {self.successor_road_id[:8]}...)")

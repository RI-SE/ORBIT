"""
Connecting road data model for ORBIT.

Represents a road that exists only within a junction, providing the geometric
path for vehicles traversing the junction.
"""

from typing import List, Tuple, Dict, Any, Optional
from dataclasses import dataclass, field
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

    Coordinates can be stored as:
    - pixel coordinates (path field) - used for display
    - geographic coordinates (geo_path field) - source of truth for imported data

    When geo_path is set, pixel coords can be recomputed via get_pixel_path()
    using a transformer. This enables adjustment of georeferencing alignment.

    Attributes:
        id: Unique identifier for this connecting road (UUID string)
        path: List of (x, y) points in pixel coordinates defining the path (sampled from curve)
        geo_path: List of (lon, lat) points in geographic coords (source of truth for imports)
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
    id: str = ""
    path: List[Tuple[float, float]] = field(default_factory=list)
    geo_path: Optional[List[Tuple[float, float]]] = None  # (lon, lat) pairs - source of truth

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

    # Stored headings from junction analysis (for accurate export)
    # These are the exact headings at adjacent road endpoints, avoiding approximation error
    stored_start_heading: Optional[float] = None  # Heading at start in radians
    stored_end_heading: Optional[float] = None    # Heading at end in radians

    def has_geo_coords(self) -> bool:
        """Check if this connecting road has geographic coordinates stored."""
        return self.geo_path is not None and len(self.geo_path) > 0

    def get_pixel_path(self, transformer=None) -> List[Tuple[float, float]]:
        """
        Get path in pixel coordinates.

        If geo_path is available and a transformer is provided,
        computes pixel coordinates from geo coordinates.
        Otherwise returns the stored pixel coordinates.

        Args:
            transformer: CoordinateTransformer for geo→pixel conversion

        Returns:
            List of (x, y) pixel coordinates
        """
        if self.geo_path and transformer:
            return [transformer.geo_to_pixel(lon, lat) for lon, lat in self.geo_path]
        return self.path

    def update_pixel_path_from_geo(self, transformer) -> None:
        """
        Update stored pixel path from geo coordinates using transformer.

        Call this after changing the transformer (e.g., adjustment) to
        update the cached pixel coordinates.

        Args:
            transformer: CoordinateTransformer for geo→pixel conversion
        """
        if self.geo_path and transformer:
            self.path = [transformer.geo_to_pixel(lon, lat) for lon, lat in self.geo_path]

    def initialize_geo_path_from_pixels(self, transformer) -> None:
        """
        Initialize geo_path from pixel path using transformer.

        Call this when loading an older project that has pixel coordinates
        but no geo coordinates stored. This ensures the connecting road
        will correctly update during adjustment operations.

        Args:
            transformer: CoordinateTransformer for pixel→geo conversion
        """
        if self.path and transformer and not self.geo_path:
            self.geo_path = [transformer.pixel_to_geo(x, y) for x, y in self.path]

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
        Get heading at the start of the path in radians.

        Uses stored heading from junction analysis if available (preferred),
        otherwise falls back to approximation from sampled path points.

        Returns:
            Heading angle in radians (0 = east, π/2 = north), or None if insufficient points
        """
        # Use stored heading if available (from junction analysis)
        if self.stored_start_heading is not None:
            return self.stored_start_heading

        # Fallback: approximate from path points (less accurate)
        if len(self.path) < 2:
            return None

        dx = self.path[1][0] - self.path[0][0]
        dy = self.path[1][1] - self.path[0][1]
        return math.atan2(dy, dx)

    def get_end_heading(self) -> Optional[float]:
        """
        Get heading at the end of the path in radians.

        Uses stored heading from junction analysis if available (preferred),
        otherwise falls back to approximation from sampled path points.

        Returns:
            Heading angle in radians (0 = east, π/2 = north), or None if insufficient points
        """
        # Use stored heading if available (from junction analysis)
        if self.stored_end_heading is not None:
            return self.stored_end_heading

        # Fallback: approximate from path points (less accurate)
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
        calculated by offsetting the centerline path based on individual lane widths.

        Supports variable width lanes (tapering) when Lane.width_end differs from Lane.width,
        and polynomial widths when width_b/c/d coefficients are non-zero.

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
        from orbit.utils.geometry import (
            create_lane_polygon, create_variable_width_lane_polygon,
            create_polynomial_width_lane_polygon
        )

        if len(self.path) < 2:
            return {}

        # Ensure lanes are initialized
        self.ensure_lanes_initialized()

        # Calculate path length in meters for polynomial width evaluation
        path_length_px = self.get_length_pixels()
        path_length_m = path_length_px * scale

        # Build map of lane_id to Lane object
        lane_map = {lane.id: lane for lane in self.lanes if lane.id != 0}

        # Calculate s-values along path (distance from start at each point)
        s_values = [0.0]
        for i in range(1, len(self.path)):
            dx = self.path[i][0] - self.path[i-1][0]
            dy = self.path[i][1] - self.path[i-1][1]
            s_values.append(s_values[-1] + math.sqrt(dx*dx + dy*dy))

        polygons = {}

        # Check if any lane uses polynomial width
        uses_polynomial = any(
            lane.width_b != 0.0 or lane.width_c != 0.0 or lane.width_d != 0.0
            for lane in self.lanes if lane.id != 0
        )

        # Create right-hand lanes (negative IDs in OpenDRIVE: -1, -2, -3, ...)
        for lane_num in range(1, self.lane_count_right + 1):
            lane_id = -lane_num
            lane = lane_map.get(lane_id)
            if not lane:
                continue

            # Get inner lanes (closer to center)
            inner_lanes = [lane_map.get(-i) for i in range(1, lane_num) if lane_map.get(-i)]

            if uses_polynomial and path_length_m > 0:
                # Use polynomial width evaluation
                def inner_width_func(s_px):
                    s_m = s_px * scale
                    total = 0.0
                    for inner_lane in inner_lanes:
                        total += inner_lane.get_width_at_s(s_m, path_length_m) / scale
                    return total

                def lane_width_func(s_px):
                    s_m = s_px * scale
                    return lane.get_width_at_s(s_m, path_length_m) / scale

                polygon_points = create_polynomial_width_lane_polygon(
                    self.path,
                    lane_id,
                    inner_width_func,
                    lane_width_func,
                    s_values,
                    is_left_lane=False
                )
            elif lane.has_variable_width or any(l.has_variable_width for l in inner_lanes):
                # Use linear interpolation (start/end width)
                inner_offset_start = sum(l.width / scale for l in inner_lanes)
                inner_offset_end = sum(l.get_width_at_end() / scale for l in inner_lanes)
                outer_offset_start = inner_offset_start + lane.width / scale
                outer_offset_end = inner_offset_end + lane.get_width_at_end() / scale

                polygon_points = create_variable_width_lane_polygon(
                    self.path,
                    inner_offset_start,
                    outer_offset_start,
                    inner_offset_end,
                    outer_offset_end
                )
            else:
                # Constant width
                inner_offset = sum(l.width / scale for l in inner_lanes)
                outer_offset = inner_offset + lane.width / scale

                polygon_points = create_lane_polygon(
                    self.path,
                    inner_offset,
                    outer_offset,
                    closed=False
                )

            if polygon_points and len(polygon_points) >= 3:
                polygons[lane_id] = polygon_points

        # Create left-hand lanes (positive IDs in OpenDRIVE: 1, 2, 3, ...)
        for lane_num in range(1, self.lane_count_left + 1):
            lane_id = lane_num
            lane = lane_map.get(lane_id)
            if not lane:
                continue

            # Get inner lanes (closer to center)
            inner_lanes = [lane_map.get(i) for i in range(1, lane_num) if lane_map.get(i)]

            if uses_polynomial and path_length_m > 0:
                # Use polynomial width evaluation
                def inner_width_func(s_px):
                    s_m = s_px * scale
                    total = 0.0
                    for inner_lane in inner_lanes:
                        total += inner_lane.get_width_at_s(s_m, path_length_m) / scale
                    return total

                def lane_width_func(s_px):
                    s_m = s_px * scale
                    return lane.get_width_at_s(s_m, path_length_m) / scale

                polygon_points = create_polynomial_width_lane_polygon(
                    self.path,
                    lane_id,
                    inner_width_func,
                    lane_width_func,
                    s_values,
                    is_left_lane=True
                )
            elif lane.has_variable_width or any(l.has_variable_width for l in inner_lanes):
                # Use linear interpolation with negative offsets for left lanes
                inner_offset_start = -sum(l.width / scale for l in inner_lanes)
                inner_offset_end = -sum(l.get_width_at_end() / scale for l in inner_lanes)
                outer_offset_start = inner_offset_start - lane.width / scale
                outer_offset_end = inner_offset_end - lane.get_width_at_end() / scale

                polygon_points = create_variable_width_lane_polygon(
                    self.path,
                    inner_offset_start,
                    outer_offset_start,
                    inner_offset_end,
                    outer_offset_end
                )
            else:
                # Constant width with negative offsets for left lanes
                inner_offset = -sum(l.width / scale for l in inner_lanes)
                outer_offset = inner_offset - lane.width / scale

                polygon_points = create_lane_polygon(
                    self.path,
                    inner_offset,
                    outer_offset,
                    closed=False
                )

            if polygon_points and len(polygon_points) >= 3:
                polygons[lane_id] = polygon_points

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

        For old projects with road-level widths (lane_width, lane_width_start, lane_width_end),
        these are migrated to lane-level widths on each Lane object.
        """
        if not self.lanes:
            # Create Lane objects based on lane counts
            self.lanes = []

            # Determine width values from road-level settings (for backward compatibility)
            width_start = self.lane_width_start if self.lane_width_start is not None else self.lane_width
            width_end = self.lane_width_end if self.lane_width_end is not None else self.lane_width

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
                    width=width_start,
                    width_end=width_end if width_end != width_start else None
                )
                self.lanes.append(lane)

            # Left lanes (positive IDs in OpenDRIVE: 1, 2, 3, ...)
            for i in range(1, self.lane_count_left + 1):
                lane = Lane(
                    id=i,
                    lane_type=LaneType.DRIVING,
                    road_mark_type=RoadMarkType.SOLID,
                    width=width_start,
                    width_end=width_end if width_end != width_start else None
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

    def migrate_lane_widths(self):
        """
        Migrate lane widths from road-level to lane-level for backward compatibility.

        Called after loading from dict to ensure lane widths match road-level widths.
        This handles the case where an old project has lanes saved but with different
        widths than the road-level lane_width_start/lane_width_end values.
        """
        if not self.lanes:
            return

        # Determine target widths from road-level settings
        width_start = self.lane_width_start if self.lane_width_start is not None else self.lane_width
        width_end = self.lane_width_end if self.lane_width_end is not None else self.lane_width

        # Check if any lane needs migration (has different width than road-level)
        needs_migration = False
        for lane in self.lanes:
            if lane.id != 0:
                lane_width_end = lane.width_end if lane.width_end is not None else lane.width
                # Check if lane width differs from road-level (allowing small tolerance)
                if abs(lane.width - width_start) > 0.01 or abs(lane_width_end - width_end) > 0.01:
                    # Only migrate if lane still has old-style widths (constant or matching lane_width)
                    # Don't migrate if the lane has intentionally different widths
                    if abs(lane.width - self.lane_width) < 0.01 and lane.width_end is None:
                        needs_migration = True
                        break

        if needs_migration:
            for lane in self.lanes:
                if lane.id != 0:
                    lane.width = width_start
                    if abs(width_end - width_start) > 0.001:
                        lane.width_end = width_end
                    else:
                        lane.width_end = None

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
            'p_range_normalized': bool(self.p_range_normalized),
            'tangent_scale': self.tangent_scale
        }

        # Include geo_path if set
        if self.geo_path is not None:
            data['geo_path'] = [[lon, lat] for lon, lat in self.geo_path]

        # Only include road_id if it's set
        if self.road_id is not None:
            data['road_id'] = self.road_id

        # Only include stored headings if set (for accurate export)
        if self.stored_start_heading is not None:
            data['stored_start_heading'] = self.stored_start_heading
        if self.stored_end_heading is not None:
            data['stored_end_heading'] = self.stored_end_heading

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
        cr.id = data.get('id', '')

        # Convert path from list of lists to list of tuples
        path_data = data.get('path', [])
        cr.path = [tuple(pt) for pt in path_data]

        # Load geo_path if present - convert lists to tuples
        geo_path_data = data.get('geo_path')
        cr.geo_path = [tuple(pt) for pt in geo_path_data] if geo_path_data else None

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

        # Stored headings from junction analysis (None for legacy projects)
        cr.stored_start_heading = data.get('stored_start_heading')  # None if not present
        cr.stored_end_heading = data.get('stored_end_heading')  # None if not present

        # Load lanes if present (backward compatible - will auto-initialize if missing)
        if 'lanes' in data:
            cr.lanes = [Lane.from_dict(lane_data) for lane_data in data['lanes']]
        else:
            # Old projects without lanes - will be initialized on first access
            cr.lanes = []

        # Migrate lane widths from road-level to lane-level if needed
        # This handles old projects where lanes existed but used road-level widths
        cr.migrate_lane_widths()

        return cr

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (f"ConnectingRoad(id={self.id}, "
                f"points={len(self.path)}, "
                f"lanes={self.get_total_lane_count()}, "
                f"{self.predecessor_road_id} -> {self.successor_road_id})")

"""
Road data model for ORBIT.

Represents a road composed of one or more polylines with associated properties.
"""

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .lane import Lane, LaneType
from .lane_section import LaneSection
from .polyline import RoadMarkType


class RoadType(Enum):
    """Enumeration of road types for OpenDrive (e_roadType)."""
    UNKNOWN = "unknown"
    RURAL = "rural"
    MOTORWAY = "motorway"
    TOWN = "town"
    LOW_SPEED = "lowSpeed"
    PEDESTRIAN = "pedestrian"
    BICYCLE = "bicycle"
    # Additional types from OpenDRIVE 1.7.0+
    TOWN_EXPRESSWAY = "townExpressway"
    TOWN_COLLECTOR = "townCollector"
    TOWN_ARTERIAL = "townArterial"
    TOWN_PRIVATE = "townPrivate"
    TOWN_LOCAL = "townLocal"
    TOWN_PLAY_STREET = "townPlayStreet"


@dataclass
class LaneInfo:
    """
    Information about lanes for a road.

    Attributes:
        left_count: Number of lanes in the left direction
        right_count: Number of lanes in the right direction
        lane_width: Default width of lanes in meters (or pixels if not georeferenced)
        lane_widths: Optional list of specific widths for each lane
    """
    left_count: int = 1
    right_count: int = 1
    lane_width: float = 3.5  # Default lane width in meters
    lane_widths: Optional[List[float]] = None


@dataclass
class Road:
    """
    Represents a road composed of polylines with properties.

    Also used for connecting roads (junction-internal paths). When junction_id is set,
    this road is a connecting road within a junction. The is_connecting_road property
    provides a convenient check.

    Regular roads use polyline_ids/centerline_id for geometry.
    Connecting roads use inline_path/inline_geo_path (no Polyline objects).

    Attributes:
        id: Unique identifier for this road
        name: Human-readable name for the road
        polyline_ids: List of polyline IDs that make up this road
        centerline_id: ID of the polyline that serves as the road centerline
        road_type: Type of road (highway, urban, etc.)
        lane_info: Information about default lane configuration
        lane_sections: List of LaneSection objects (OpenDRIVE lane sections)
        speed_limit: Speed limit in km/h (optional)
        junction_id: ID of junction this road belongs to (set for connecting roads)
        predecessor_id: ID of road that precedes this one (optional)
        predecessor_contact: Contact point on predecessor ("start" or "end")
        successor_id: ID of road that follows this one (optional)
        successor_contact: Contact point on successor ("start" or "end")
        elevation_profile: List of (s, a, b, c, d) tuples for elevation polynomial
    """
    id: str = ""
    name: str = "Unnamed Road"
    polyline_ids: List[str] = field(default_factory=list)
    centerline_id: Optional[str] = None  # Required for export (regular roads)
    road_type: RoadType = RoadType.UNKNOWN
    lane_info: LaneInfo = field(default_factory=LaneInfo)
    lane_sections: List[LaneSection] = field(default_factory=list)
    speed_limit: Optional[float] = None  # km/h
    junction_id: Optional[str] = None
    predecessor_id: Optional[str] = None
    predecessor_contact: str = "end"  # "start" or "end"
    successor_id: Optional[str] = None
    successor_contact: str = "start"  # "start" or "end"
    predecessor_junction_id: Optional[str] = None  # Junction ID if predecessor is a junction
    successor_junction_id: Optional[str] = None  # Junction ID if successor is a junction
    # Elevation profile: list of (s, a, b, c, d) tuples for polynomial elevation(ds) = a + b*ds + c*ds² + d*ds³
    elevation_profile: List[Tuple[float, float, float, float, float]] = field(default_factory=list)
    # Superelevation (lateral profile): (s, a, b, c, d) tuples
    # for polynomial superelevation(ds) = a + b*ds + c*ds^2 + d*ds^3
    # Value represents cross slope (positive=left, negative=right)
    superelevation_profile: List[Tuple[float, float, float, float, float]] = field(default_factory=list)
    # Lane offset: (s, a, b, c, d) tuples shifting center lane
    lane_offset: List[Tuple[float, float, float, float, float]] = field(default_factory=list)
    # Surface CRG (OpenCRG) data: list of dicts with file,
    # s_start, s_end, orientation, mode, purpose, etc.
    surface_crg: List[Dict[str, Any]] = field(default_factory=list)
    # Original OSM tags for round-trip export
    osm_tags: Optional[Dict[str, str]] = None
    osm_way_id: Optional[int] = None

    # --- Connecting road fields (only used when junction_id is set) ---
    # Inline path in pixel coordinates (connecting roads don't use Polyline objects)
    inline_path: Optional[List[Tuple[float, float]]] = None
    # Inline path in geographic coordinates (lon, lat) - source of truth for imports
    inline_geo_path: Optional[List[Tuple[float, float]]] = None
    # Geometry type for export: "parampoly3" or "polyline"
    geometry_type: str = "polyline"
    # ParamPoly3D coefficients
    aU: float = 0.0
    bU: float = 0.0
    cU: float = 0.0
    dU: float = 0.0
    aV: float = 0.0
    bV: float = 0.0
    cV: float = 0.0
    dV: float = 0.0
    p_range: float = 1.0
    p_range_normalized: bool = True
    tangent_scale: float = 1.0
    # Stored headings from junction analysis (radians, for accurate export)
    stored_start_heading: Optional[float] = None
    stored_end_heading: Optional[float] = None
    # Lane width overrides for connecting roads (start/end tapering)
    lane_width_start: Optional[float] = None
    lane_width_end: Optional[float] = None
    # Connecting road lane counts (used when lane_sections not yet populated)
    cr_lane_count_left: int = 0
    cr_lane_count_right: int = 1

    @property
    def is_connecting_road(self) -> bool:
        """Whether this road is a connecting road within a junction."""
        return self.junction_id is not None

    def get_reference_points(self, project=None) -> List[Tuple[float, float]]:
        """
        Get the reference line points for this road.

        For connecting roads, returns inline_path.
        For regular roads, looks up centerline polyline points from project.

        Args:
            project: Project instance (needed for regular roads to look up polylines)

        Returns:
            List of (x, y) pixel coordinates, or empty list if unavailable
        """
        if self.inline_path is not None:
            return self.inline_path
        if project is not None and self.centerline_id:
            polyline = project.get_polyline(self.centerline_id)
            if polyline:
                return polyline.points
        return []

    def has_geo_coords(self) -> bool:
        """Check if this road has geographic coordinates for its inline path."""
        return self.inline_geo_path is not None and len(self.inline_geo_path) > 0

    def get_pixel_path(self, transformer=None) -> List[Tuple[float, float]]:
        """
        Get inline path in pixel coordinates.

        If inline_geo_path is available and a transformer is provided,
        computes pixel coordinates from geo coordinates.
        Otherwise returns the stored inline_path.

        Args:
            transformer: CoordinateTransformer for geo->pixel conversion

        Returns:
            List of (x, y) pixel coordinates, or empty list
        """
        if self.inline_geo_path and transformer:
            return [transformer.geo_to_pixel(lon, lat) for lon, lat in self.inline_geo_path]
        return self.inline_path or []

    def update_pixel_path_from_geo(self, transformer) -> None:
        """Update stored inline_path from geo coordinates using transformer."""
        if self.inline_geo_path and transformer:
            self.inline_path = [transformer.geo_to_pixel(lon, lat) for lon, lat in self.inline_geo_path]

    def initialize_geo_path_from_pixels(self, transformer) -> None:
        """Initialize inline_geo_path from inline_path using transformer."""
        if self.inline_path and transformer and not self.inline_geo_path:
            self.inline_geo_path = [transformer.pixel_to_geo(x, y) for x, y in self.inline_path]

    def get_inline_path_length(self) -> float:
        """Calculate inline path length in pixels."""
        path = self.inline_path
        if not path or len(path) < 2:
            return 0.0
        length = 0.0
        for i in range(len(path) - 1):
            dx = path[i + 1][0] - path[i][0]
            dy = path[i + 1][1] - path[i][1]
            length += math.sqrt(dx * dx + dy * dy)
        return length

    def get_start_point(self) -> Optional[Tuple[float, float]]:
        """Get the starting point of the inline path."""
        return self.inline_path[0] if self.inline_path else None

    def get_end_point(self) -> Optional[Tuple[float, float]]:
        """Get the ending point of the inline path."""
        return self.inline_path[-1] if self.inline_path else None

    def get_start_heading(self) -> Optional[float]:
        """
        Get heading at the start of the inline path in radians.

        Uses stored heading if available, otherwise approximates from path points.
        """
        if self.stored_start_heading is not None:
            return self.stored_start_heading
        if self.inline_path and len(self.inline_path) >= 2:
            dx = self.inline_path[1][0] - self.inline_path[0][0]
            dy = self.inline_path[1][1] - self.inline_path[0][1]
            return math.atan2(dy, dx)
        return None

    def get_end_heading(self) -> Optional[float]:
        """
        Get heading at the end of the inline path in radians.

        Uses stored heading if available, otherwise approximates from path points.
        """
        if self.stored_end_heading is not None:
            return self.stored_end_heading
        if self.inline_path and len(self.inline_path) >= 2:
            dx = self.inline_path[-1][0] - self.inline_path[-2][0]
            dy = self.inline_path[-1][1] - self.inline_path[-2][1]
            return math.atan2(dy, dx)
        return None

    def get_cr_total_lane_count(self) -> int:
        """Get total number of lanes for connecting road (left + right, excluding center)."""
        return self.cr_lane_count_left + self.cr_lane_count_right

    def get_cr_lane_ids(self) -> List[int]:
        """Get list of all lane IDs for connecting road (right then left)."""
        lane_ids = []
        for i in range(1, self.cr_lane_count_right + 1):
            lane_ids.append(-i)
        for i in range(1, self.cr_lane_count_left + 1):
            lane_ids.append(i)
        return lane_ids

    def ensure_cr_lanes_initialized(self) -> None:
        """
        Ensure lane_sections has at least one section with Lane objects for a connecting road.

        Creates Lane objects based on cr_lane_count_left/right if lane_sections is empty.
        Migrates lane_width_start/lane_width_end to lane-level widths.
        """
        if not self.is_connecting_road:
            return
        if self.lane_sections:
            return

        # Determine width from connecting road fields
        width_start = self.lane_width_start if self.lane_width_start is not None else self.lane_info.lane_width
        width_end = self.lane_width_end if self.lane_width_end is not None else self.lane_info.lane_width

        lanes = []
        # Center lane (lane 0)
        center = Lane(
            id=0,
            lane_type=LaneType.NONE,
            road_mark_type=RoadMarkType.NONE,
            width=0.0
        )
        lanes.append(center)

        # Right lanes (negative IDs)
        for i in range(1, self.cr_lane_count_right + 1):
            lane = Lane(
                id=-i,
                lane_type=LaneType.DRIVING,
                road_mark_type=RoadMarkType.SOLID,
                width=width_start,
                width_end=width_end if abs(width_end - width_start) > 0.001 else None
            )
            lanes.append(lane)

        # Left lanes (positive IDs)
        for i in range(1, self.cr_lane_count_left + 1):
            lane = Lane(
                id=i,
                lane_type=LaneType.DRIVING,
                road_mark_type=RoadMarkType.SOLID,
                width=width_start,
                width_end=width_end if abs(width_end - width_start) > 0.001 else None
            )
            lanes.append(lane)

        section = LaneSection(
            section_number=1,
            s_start=0.0,
            s_end=self.get_inline_path_length() or 1000.0,
            lanes=lanes
        )
        self.lane_sections.append(section)

    def get_cr_lane(self, lane_id: int) -> Optional[Lane]:
        """Get a lane by ID from connecting road lane sections."""
        self.ensure_cr_lanes_initialized()
        for section in self.lane_sections:
            for lane in section.lanes:
                if lane.id == lane_id:
                    return lane
        return None

    def get_cr_lane_polygons(self, scale: float) -> Dict[int, List[Tuple[float, float]]]:
        """
        Generate lane boundary polygons for connecting road visualization.

        Only applicable to connecting roads (roads with inline_path set).

        Args:
            scale: Meters per pixel scale factor

        Returns:
            Dictionary mapping lane IDs to polygon point lists
        """
        from orbit.utils.geometry import (
            create_lane_polygon,
            create_polynomial_width_lane_polygon,
            create_variable_width_lane_polygon,
        )

        path = self.inline_path
        if not path or len(path) < 2:
            return {}

        self.ensure_cr_lanes_initialized()
        if not self.lane_sections:
            return {}

        lanes = self.lane_sections[0].lanes
        path_length_px = self.get_inline_path_length()
        path_length_m = path_length_px * scale

        lane_map = {lane.id: lane for lane in lanes if lane.id != 0}

        s_values = [0.0]
        for i in range(1, len(path)):
            dx = path[i][0] - path[i - 1][0]
            dy = path[i][1] - path[i - 1][1]
            s_values.append(s_values[-1] + math.sqrt(dx * dx + dy * dy))

        polygons: Dict[int, List[Tuple[float, float]]] = {}

        uses_polynomial = any(
            lane.width_b != 0.0 or lane.width_c != 0.0 or lane.width_d != 0.0
            for lane in lanes if lane.id != 0
        )

        # Right-hand lanes (negative IDs)
        for lane_num in range(1, self.cr_lane_count_right + 1):
            lane_id = -lane_num
            lane = lane_map.get(lane_id)
            if not lane:
                continue
            inner_lanes = [lane_map.get(-i) for i in range(1, lane_num) if lane_map.get(-i)]

            if uses_polynomial and path_length_m > 0:
                def inner_width_func(s_px, _il=inner_lanes):
                    s_m = s_px * scale
                    return sum(il.get_width_at_s(s_m, path_length_m) / scale for il in _il)

                def lane_width_func(s_px, _l=lane):
                    s_m = s_px * scale
                    return _l.get_width_at_s(s_m, path_length_m) / scale

                polygon_points = create_polynomial_width_lane_polygon(
                    path, lane_id, inner_width_func, lane_width_func, s_values, is_left_lane=False)
            elif lane.has_variable_width or any(il.has_variable_width for il in inner_lanes):
                inner_offset_start = sum(il.width / scale for il in inner_lanes)
                inner_offset_end = sum(il.get_width_at_end() / scale for il in inner_lanes)
                polygon_points = create_variable_width_lane_polygon(
                    path, inner_offset_start, inner_offset_start + lane.width / scale,
                    inner_offset_end, inner_offset_end + lane.get_width_at_end() / scale)
            else:
                inner_offset = sum(il.width / scale for il in inner_lanes)
                polygon_points = create_lane_polygon(
                    path, inner_offset, inner_offset + lane.width / scale, closed=False)

            if polygon_points and len(polygon_points) >= 3:
                polygons[lane_id] = polygon_points

        # Left-hand lanes (positive IDs)
        for lane_num in range(1, self.cr_lane_count_left + 1):
            lane_id = lane_num
            lane = lane_map.get(lane_id)
            if not lane:
                continue
            inner_lanes = [lane_map.get(i) for i in range(1, lane_num) if lane_map.get(i)]

            if uses_polynomial and path_length_m > 0:
                def inner_width_func(s_px, _il=inner_lanes):
                    s_m = s_px * scale
                    return sum(il.get_width_at_s(s_m, path_length_m) / scale for il in _il)

                def lane_width_func(s_px, _l=lane):
                    s_m = s_px * scale
                    return _l.get_width_at_s(s_m, path_length_m) / scale

                polygon_points = create_polynomial_width_lane_polygon(
                    path, lane_id, inner_width_func, lane_width_func, s_values, is_left_lane=True)
            elif lane.has_variable_width or any(il.has_variable_width for il in inner_lanes):
                inner_offset_start = -sum(il.width / scale for il in inner_lanes)
                inner_offset_end = -sum(il.get_width_at_end() / scale for il in inner_lanes)
                polygon_points = create_variable_width_lane_polygon(
                    path, inner_offset_start, inner_offset_start - lane.width / scale,
                    inner_offset_end, inner_offset_end - lane.get_width_at_end() / scale)
            else:
                inner_offset = -sum(il.width / scale for il in inner_lanes)
                polygon_points = create_lane_polygon(
                    path, inner_offset, inner_offset - lane.width / scale, closed=False)

            if polygon_points and len(polygon_points) >= 3:
                polygons[lane_id] = polygon_points

        return polygons

    def add_polyline(self, polyline_id: str) -> None:
        """Add a polyline to this road."""
        if polyline_id not in self.polyline_ids:
            self.polyline_ids.append(polyline_id)

    def remove_polyline(self, polyline_id: str) -> None:
        """Remove a polyline from this road."""
        if polyline_id in self.polyline_ids:
            self.polyline_ids.remove(polyline_id)

    def is_valid(self) -> bool:
        """Check if the road has at least one polyline or an inline path."""
        if self.is_connecting_road:
            return self.inline_path is not None and len(self.inline_path) >= 2
        return len(self.polyline_ids) > 0

    def is_valid_for_export(self) -> bool:
        """Check if the road is valid for OpenDRIVE export."""
        if self.is_connecting_road:
            return self.inline_path is not None and len(self.inline_path) >= 2
        return (
            len(self.polyline_ids) > 0 and
            self.centerline_id is not None and
            self.centerline_id in self.polyline_ids
        )

    def has_centerline(self) -> bool:
        """Check if the road has a centerline assigned (or inline path for connecting roads)."""
        if self.is_connecting_road:
            return self.inline_path is not None and len(self.inline_path) >= 2
        return (
            self.centerline_id is not None and
            self.centerline_id in self.polyline_ids
        )

    def total_lanes(self) -> int:
        """Return total number of lanes."""
        return self.lane_info.left_count + self.lane_info.right_count

    # Lane management (now uses lane sections)
    def generate_lanes(self, centerline_length: float = 1000.0) -> None:
        """
        Auto-generate lanes in a single section based on left_count and right_count.

        Creates a single lane section containing:
        - Lane 0 (center/reference lane)
        - Lanes 1 to left_count (left side, positive IDs)
        - Lanes -1 to -right_count (right side, negative IDs)

        Args:
            centerline_length: Length of the centerline in pixels (default 1000.0)
        """
        self.lane_sections.clear()
        lanes = []

        # Always create lane 0 (center/reference lane)
        center = Lane(
            id=0,
            lane_type=LaneType.NONE,
            road_mark_type=RoadMarkType.SOLID,
            width=0.0  # Center lane has no width
        )
        lanes.append(center)

        # Generate right lanes (negative IDs)
        for i in range(1, self.lane_info.right_count + 1):
            lane = Lane(
                id=-i,
                lane_type=LaneType.DRIVING,
                road_mark_type=RoadMarkType.SOLID,
                width=self.lane_info.lane_width
            )
            lanes.append(lane)

        # Generate left lanes (positive IDs)
        for i in range(1, self.lane_info.left_count + 1):
            lane = Lane(
                id=i,
                lane_type=LaneType.DRIVING,
                road_mark_type=RoadMarkType.SOLID,
                width=self.lane_info.lane_width
            )
            lanes.append(lane)

        # Create single lane section
        section = LaneSection(
            section_number=1,
            s_start=0.0,
            s_end=centerline_length,
            lanes=lanes
        )
        self.lane_sections.append(section)

    def get_lane(self, lane_id: int, section_number: Optional[int] = None) -> Optional[Lane]:
        """
        Get a lane by ID from lane sections.

        Args:
            lane_id: The lane ID to search for
            section_number: Optional section number. If None, searches first section with matching lane.

        Returns:
            Lane object or None if not found
        """
        if section_number is not None:
            # Search in specific section
            section = self.get_section(section_number)
            if section:
                for lane in section.lanes:
                    if lane.id == lane_id:
                        return lane
        else:
            # Search all sections, return first match
            for section in self.lane_sections:
                for lane in section.lanes:
                    if lane.id == lane_id:
                        return lane
        return None

    # Lane Section management
    def calculate_centerline_s_coordinates(self, centerline_points: List[Tuple[float, float]]) -> List[float]:
        """
        Calculate cumulative distances along centerline points.

        Args:
            centerline_points: List of (x, y) tuples representing the centerline

        Returns:
            List of cumulative distances (s-coordinates) for each point
        """
        if not centerline_points:
            return []

        s_coords = [0.0]  # First point is at s=0
        for i in range(1, len(centerline_points)):
            x1, y1 = centerline_points[i - 1]
            x2, y2 = centerline_points[i]
            distance = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
            s_coords.append(s_coords[-1] + distance)

        return s_coords

    def get_section_at_s(self, s: float) -> Optional[LaneSection]:
        """
        Get the lane section that contains the given s-coordinate.

        Args:
            s: S-coordinate in pixels along the centerline

        Returns:
            LaneSection if found, None otherwise
        """
        for section in self.lane_sections:
            if section.contains_s_coordinate(s):
                return section
        return None

    def get_section_containing_point(
        self, point_index: int,
        centerline_points: List[Tuple[float, float]],
    ) -> Optional[LaneSection]:
        """
        Get the lane section that contains the given point index.

        Args:
            point_index: Index of the point in the centerline
            centerline_points: List of centerline points

        Returns:
            LaneSection if found, None otherwise
        """
        s_coords = self.calculate_centerline_s_coordinates(centerline_points)
        if point_index < 0 or point_index >= len(s_coords):
            return None

        s = s_coords[point_index]
        return self.get_section_at_s(s)

    def split_section_at_point(self, point_index: int, centerline_points: List[Tuple[float, float]]) -> bool:
        """
        Split a lane section at the given point index.

        The section containing the point will be split into two sections.
        All subsequent sections will be renumbered.

        Args:
            point_index: Index of the point in the centerline where to split
            centerline_points: List of centerline points

        Returns:
            True if split was successful, False otherwise
        """
        # Calculate s-coordinates
        s_coords = self.calculate_centerline_s_coordinates(centerline_points)
        if point_index < 0 or point_index >= len(s_coords):
            return False

        s = s_coords[point_index]

        # Find the section containing this point
        section_to_split = None
        section_index = -1
        for i, section in enumerate(self.lane_sections):
            if section.contains_s_coordinate(s):
                section_to_split = section
                section_index = i
                break

        if section_to_split is None:
            return False

        # Check if split point is too close to boundaries (warn threshold: 5%)
        _section_length = section_to_split.get_length_pixels()
        _distance_from_start = s - section_to_split.s_start
        _distance_from_end = section_to_split.s_end - s

        # Calculate new section number for the second section
        new_section_number = section_to_split.section_number + 1

        # Split the section
        try:
            first_section, second_section = section_to_split.split_at_s(s, new_section_number, point_index)
        except ValueError:
            return False

        # Remove the old section and insert the two new ones
        self.lane_sections.pop(section_index)
        self.lane_sections.insert(section_index, first_section)
        self.lane_sections.insert(section_index + 1, second_section)

        # Renumber all subsequent sections
        self.renumber_sections()

        return True

    def renumber_sections(self) -> None:
        """Renumber all lane sections sequentially starting from 1."""
        for i, section in enumerate(self.lane_sections, start=1):
            section.section_number = i

    def distribute_lane_sections_for_split(
        self,
        split_s: float,
        split_point_index: int
    ) -> Tuple[List[LaneSection], List[LaneSection]]:
        """
        Distribute lane sections between two roads when splitting at split_s.

        Sections entirely before split_s go to road 1.
        Sections entirely after split_s go to road 2 (with adjusted s-coordinates).
        Sections spanning split_s are split into two.

        Args:
            split_s: S-coordinate where the road is being split
            split_point_index: Index of the centerline point at the split

        Returns:
            Tuple of (sections_for_road1, sections_for_road2)
        """
        from copy import deepcopy

        sections_road1 = []
        sections_road2 = []

        for section in self.lane_sections:
            if section.s_end <= split_s:
                # Section entirely in road 1
                sections_road1.append(deepcopy(section))

            elif section.s_start >= split_s:
                # Section entirely in road 2 - adjust s-coordinates
                new_section = deepcopy(section)
                new_section.s_start = section.s_start - split_s
                new_section.s_end = section.s_end - split_s
                # Adjust end_point_index relative to new road
                if new_section.end_point_index is not None:
                    new_section.end_point_index = new_section.end_point_index - split_point_index
                    if new_section.end_point_index < 0:
                        new_section.end_point_index = None
                sections_road2.append(new_section)

            else:
                # Section spans split_s - need to split it
                # Create section for road 1 (from s_start to split_s)
                section1 = LaneSection(
                    section_number=section.section_number,
                    s_start=section.s_start,
                    s_end=split_s,
                    single_side=section.single_side,
                    lanes=section._duplicate_lanes(),
                    end_point_index=split_point_index
                )
                sections_road1.append(section1)

                # Create section for road 2 (from 0 to original s_end - split_s)
                section2 = LaneSection(
                    section_number=1,  # Will be renumbered later
                    s_start=0.0,
                    s_end=section.s_end - split_s,
                    single_side=section.single_side,
                    lanes=section._duplicate_lanes(),
                    end_point_index=(
                        section.end_point_index - split_point_index
                        if section.end_point_index is not None
                        else None
                    )
                )
                if section2.end_point_index is not None and section2.end_point_index < 0:
                    section2.end_point_index = None
                sections_road2.append(section2)

        # Renumber sections in each list
        for i, section in enumerate(sections_road1, start=1):
            section.section_number = i
        for i, section in enumerate(sections_road2, start=1):
            section.section_number = i

        # If no sections for a road, create a default one
        if not sections_road1:
            sections_road1 = [LaneSection(
                section_number=1,
                s_start=0.0,
                s_end=split_s,
                lanes=self.lane_sections[0]._duplicate_lanes() if self.lane_sections else []
            )]
        if not sections_road2:
            total_length = self.lane_sections[-1].s_end if self.lane_sections else split_s
            sections_road2 = [LaneSection(
                section_number=1,
                s_start=0.0,
                s_end=total_length - split_s,
                lanes=self.lane_sections[-1]._duplicate_lanes() if self.lane_sections else []
            )]

        return (sections_road1, sections_road2)

    def update_section_boundaries(self, centerline_points: List[Tuple[float, float]]) -> None:
        """
        Update section boundaries after centerline changes.

        This recalculates s_start and s_end based on stored end_point_index values,
        ensuring adjacent sections share boundary points even after point insertion/deletion.

        Args:
            centerline_points: Current centerline points
        """
        if not self.lane_sections or not centerline_points:
            return

        # Calculate s-coordinates for all points
        s_coords = self.calculate_centerline_s_coordinates(centerline_points)
        if not s_coords:
            return

        # Initialize end_point_index for sections that don't have it set
        for i, section in enumerate(self.lane_sections):
            is_last_section = (i == len(self.lane_sections) - 1)

            if section.end_point_index is None and not is_last_section:
                # Find the point index closest to current s_end
                best_idx = 0
                min_diff = abs(s_coords[0] - section.s_end)
                for idx, s in enumerate(s_coords):
                    diff = abs(s - section.s_end)
                    if diff < min_diff:
                        min_diff = diff
                        best_idx = idx
                section.end_point_index = best_idx

        # Update each section's boundaries
        for i, section in enumerate(self.lane_sections):
            # First section always starts at 0
            if i == 0:
                section.s_start = 0.0
            else:
                # Subsequent sections start where previous section ends
                section.s_start = self.lane_sections[i - 1].s_end

            # Update s_end based on end_point_index
            if section.end_point_index is not None:
                # Clamp index to valid range
                end_idx = min(section.end_point_index, len(s_coords) - 1)
                end_idx = max(0, end_idx)
                section.s_end = s_coords[end_idx]
            else:
                # Last section extends to end of road
                section.s_end = s_coords[-1]

    def adjust_section_indices_after_insertion(self, inserted_at: int) -> None:
        """
        Adjust section end_point_index values after a point is inserted.

        Args:
            inserted_at: Index where the new point was inserted
        """
        for section in self.lane_sections:
            if section.end_point_index is not None and section.end_point_index >= inserted_at:
                section.end_point_index += 1

    def adjust_section_indices_after_deletion(self, deleted_at: int) -> None:
        """
        Adjust section end_point_index values after a point is deleted.

        Args:
            deleted_at: Index of the deleted point
        """
        for section in self.lane_sections:
            if section.end_point_index is not None:
                if section.end_point_index > deleted_at:
                    section.end_point_index -= 1
                elif section.end_point_index == deleted_at:
                    # Boundary point was deleted - need to handle this
                    # For now, set to None to extend to end
                    section.end_point_index = None

    def delete_section(self, section_number: int) -> bool:
        """
        Delete a lane section by number.

        Prevents deletion if only one section remains.

        Args:
            section_number: Section number to delete

        Returns:
            True if deleted, False otherwise
        """
        if len(self.lane_sections) <= 1:
            return False  # Must have at least one section

        section_to_remove = None
        for section in self.lane_sections:
            if section.section_number == section_number:
                section_to_remove = section
                break

        if section_to_remove is None:
            return False

        self.lane_sections.remove(section_to_remove)
        self.renumber_sections()
        return True

    def get_section(self, section_number: int) -> Optional[LaneSection]:
        """Get a lane section by its number."""
        for section in self.lane_sections:
            if section.section_number == section_number:
                return section
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert road to dictionary for JSON serialization."""
        data = {
            'id': self.id,
            'name': self.name,
            'polyline_ids': self.polyline_ids,
            'centerline_id': self.centerline_id,
            'road_type': self.road_type.value,
            'lane_info': {
                'left_count': self.lane_info.left_count,
                'right_count': self.lane_info.right_count,
                'lane_width': self.lane_info.lane_width,
                'lane_widths': self.lane_info.lane_widths
            },
            'lane_sections': [section.to_dict() for section in self.lane_sections],
            'speed_limit': self.speed_limit,
            'junction_id': self.junction_id,
            'predecessor_id': self.predecessor_id,
            'predecessor_contact': self.predecessor_contact,
            'successor_id': self.successor_id,
            'successor_contact': self.successor_contact
        }
        # Only include optional fields if set (backward compatibility)
        if self.predecessor_junction_id is not None:
            data['predecessor_junction_id'] = self.predecessor_junction_id
        if self.successor_junction_id is not None:
            data['successor_junction_id'] = self.successor_junction_id
        if self.elevation_profile:
            data['elevation_profile'] = [list(elev) for elev in self.elevation_profile]
        if self.superelevation_profile:
            data['superelevation_profile'] = [list(se) for se in self.superelevation_profile]
        if self.lane_offset:
            data['lane_offset'] = [list(lo) for lo in self.lane_offset]
        if self.surface_crg:
            data['surface_crg'] = self.surface_crg
        if self.osm_tags:
            data['osm_tags'] = self.osm_tags
        if self.osm_way_id is not None:
            data['osm_way_id'] = self.osm_way_id
        # Connecting road fields (only serialized when set)
        if self.inline_path is not None:
            data['inline_path'] = [[x, y] for x, y in self.inline_path]
        if self.inline_geo_path is not None:
            data['inline_geo_path'] = [[lon, lat] for lon, lat in self.inline_geo_path]
        if self.geometry_type != "polyline":
            data['geometry_type'] = self.geometry_type
        if self.geometry_type == "parampoly3" or any(
            v != 0.0 for v in [self.aU, self.bU, self.cU, self.dU, self.aV, self.bV, self.cV, self.dV]
        ):
            data.update({
                'geometry_type': self.geometry_type,
                'aU': self.aU, 'bU': self.bU, 'cU': self.cU, 'dU': self.dU,
                'aV': self.aV, 'bV': self.bV, 'cV': self.cV, 'dV': self.dV,
                'p_range': self.p_range,
                'p_range_normalized': bool(self.p_range_normalized),
                'tangent_scale': self.tangent_scale,
            })
        if self.stored_start_heading is not None:
            data['stored_start_heading'] = self.stored_start_heading
        if self.stored_end_heading is not None:
            data['stored_end_heading'] = self.stored_end_heading
        if self.lane_width_start is not None:
            data['lane_width_start'] = self.lane_width_start
        if self.lane_width_end is not None:
            data['lane_width_end'] = self.lane_width_end
        if self.is_connecting_road:
            data['cr_lane_count_left'] = self.cr_lane_count_left
            data['cr_lane_count_right'] = self.cr_lane_count_right
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Road':
        """
        Create road from dictionary with backward compatibility.

        Handles both new format (with lane_sections) and old format (with lanes only).
        Old format is automatically migrated to lane_sections.
        """
        lane_info_data = data.get('lane_info', {})
        lane_info = LaneInfo(
            left_count=lane_info_data.get('left_count', 1),
            right_count=lane_info_data.get('right_count', 1),
            lane_width=lane_info_data.get('lane_width', 3.5),
            lane_widths=lane_info_data.get('lane_widths')
        )

        # Load lane sections if available (new format)
        lane_sections_data = data.get('lane_sections', [])
        lane_sections = [LaneSection.from_dict(section_data) for section_data in lane_sections_data]

        # Load old lanes for backward compatibility migration
        legacy_lanes_data = data.get('lanes', [])
        legacy_lanes = [Lane.from_dict(lane_data) for lane_data in legacy_lanes_data]

        # Load connecting road inline paths
        inline_path_data = data.get('inline_path')
        inline_path = [tuple(pt) for pt in inline_path_data] if inline_path_data else None
        inline_geo_path_data = data.get('inline_geo_path')
        inline_geo_path = [tuple(pt) for pt in inline_geo_path_data] if inline_geo_path_data else None

        road = cls(
            id=data.get('id', ''),
            name=data.get('name', 'Unnamed Road'),
            polyline_ids=data.get('polyline_ids', []),
            centerline_id=data.get('centerline_id'),
            road_type=RoadType(data.get('road_type', 'unknown')),
            lane_info=lane_info,
            lane_sections=lane_sections,
            speed_limit=data.get('speed_limit'),
            junction_id=data.get('junction_id'),
            predecessor_id=data.get('predecessor_id'),
            predecessor_contact=data.get('predecessor_contact', 'end'),
            successor_id=data.get('successor_id'),
            successor_contact=data.get('successor_contact', 'start'),
            predecessor_junction_id=data.get('predecessor_junction_id'),
            successor_junction_id=data.get('successor_junction_id'),
            elevation_profile=[tuple(e) for e in data.get('elevation_profile', [])],
            superelevation_profile=[tuple(e) for e in data.get('superelevation_profile', [])],
            lane_offset=[tuple(e) for e in data.get('lane_offset', [])],
            surface_crg=data.get('surface_crg', []),
            osm_tags=data.get('osm_tags'),
            osm_way_id=data.get('osm_way_id'),
            # Connecting road fields
            inline_path=inline_path,
            inline_geo_path=inline_geo_path,
            geometry_type=data.get('geometry_type', 'polyline'),
            aU=data.get('aU', 0.0),
            bU=data.get('bU', 0.0),
            cU=data.get('cU', 0.0),
            dU=data.get('dU', 0.0),
            aV=data.get('aV', 0.0),
            bV=data.get('bV', 0.0),
            cV=data.get('cV', 0.0),
            dV=data.get('dV', 0.0),
            p_range=data.get('p_range', 1.0),
            p_range_normalized=data.get('p_range_normalized', True),
            tangent_scale=data.get('tangent_scale', 1.0),
            stored_start_heading=data.get('stored_start_heading'),
            stored_end_heading=data.get('stored_end_heading'),
            lane_width_start=data.get('lane_width_start'),
            lane_width_end=data.get('lane_width_end'),
            cr_lane_count_left=data.get('cr_lane_count_left', 0),
            cr_lane_count_right=data.get('cr_lane_count_right', 1),
        )

        # Backward compatibility: migrate old format to lane_sections
        if not road.lane_sections:
            if legacy_lanes:
                # Migrate existing lanes to a single section
                section = LaneSection(
                    section_number=1,
                    s_start=0.0,
                    s_end=1000.0,  # Default length, will be updated when centerline is available
                    lanes=legacy_lanes
                )
                road.lane_sections.append(section)
            elif not road.is_connecting_road:
                # No lanes at all for regular road, generate default
                road.generate_lanes()
            # Connecting roads: lane_sections will be lazily initialized via ensure_cr_lanes_initialized()

        return road

    @classmethod
    def from_connecting_road_dict(cls, cr_data: Dict[str, Any], junction_id: str) -> 'Road':
        """
        Create a Road from a legacy ConnectingRoad dictionary.

        Used during migration from old project format where connecting roads
        were stored nested inside Junction objects.

        Args:
            cr_data: Dictionary from ConnectingRoad.to_dict() format
            junction_id: ID of the junction this connecting road belongs to

        Returns:
            Road instance with connecting road fields populated
        """
        # Convert path from list of lists to list of tuples
        path_data = cr_data.get('path', [])
        inline_path = [tuple(pt) for pt in path_data] if path_data else None

        # Load geo_path
        geo_path_data = cr_data.get('geo_path')
        inline_geo_path = [tuple(pt) for pt in geo_path_data] if geo_path_data else None

        # Load lanes into a lane section
        lane_sections = []
        lanes_data = cr_data.get('lanes', [])
        if lanes_data:
            lanes = [Lane.from_dict(ld) for ld in lanes_data]
            lane_sections = [LaneSection(
                section_number=1,
                s_start=0.0,
                s_end=1000.0,
                lanes=lanes
            )]

        cr_id = cr_data.get('id', '')
        # Migration: old projects stored ODR road ID in road_id field
        old_road_id = cr_data.get('road_id')
        if old_road_id is not None and cr_id:
            try:
                int(cr_id)
            except (ValueError, TypeError):
                cr_id = str(old_road_id)

        road = cls(
            id=cr_id,
            name=f"CR {cr_id}",
            junction_id=junction_id,
            predecessor_id=cr_data.get('predecessor_road_id', ''),
            predecessor_contact=cr_data.get('contact_point_start', 'end'),
            successor_id=cr_data.get('successor_road_id', ''),
            successor_contact=cr_data.get('contact_point_end', 'start'),
            lane_info=LaneInfo(
                left_count=cr_data.get('lane_count_left', 0),
                right_count=cr_data.get('lane_count_right', 1),
                lane_width=cr_data.get('lane_width', 3.5),
            ),
            lane_sections=lane_sections,
            inline_path=inline_path,
            inline_geo_path=inline_geo_path,
            geometry_type=cr_data.get('geometry_type', 'polyline'),
            aU=cr_data.get('aU', 0.0),
            bU=cr_data.get('bU', 0.0),
            cU=cr_data.get('cU', 0.0),
            dU=cr_data.get('dU', 0.0),
            aV=cr_data.get('aV', 0.0),
            bV=cr_data.get('bV', 0.0),
            cV=cr_data.get('cV', 0.0),
            dV=cr_data.get('dV', 0.0),
            p_range=cr_data.get('p_range', 1.0),
            p_range_normalized=cr_data.get('p_range_normalized', True),
            tangent_scale=cr_data.get('tangent_scale', 1.0),
            stored_start_heading=cr_data.get('stored_start_heading'),
            stored_end_heading=cr_data.get('stored_end_heading'),
            lane_width_start=cr_data.get('lane_width_start'),
            lane_width_end=cr_data.get('lane_width_end'),
            cr_lane_count_left=cr_data.get('lane_count_left', 0),
            cr_lane_count_right=cr_data.get('lane_count_right', 1),
        )
        return road

    def __repr__(self) -> str:
        if self.is_connecting_road:
            return f"Road(id={self.id}, junction={self.junction_id}, connecting_road=True)"
        return f"Road(id={self.id}, name='{self.name}', polylines={len(self.polyline_ids)})"

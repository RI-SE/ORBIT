"""
Road data model for ORBIT.

Represents a road composed of one or more polylines with associated properties.
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import uuid
import math

from .lane import Lane, LaneType
from .polyline import RoadMarkType
from .lane_section import LaneSection


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

    Attributes:
        id: Unique identifier for this road
        name: Human-readable name for the road
        polyline_ids: List of polyline IDs that make up this road
        centerline_id: ID of the polyline that serves as the road centerline
        road_type: Type of road (highway, urban, etc.)
        lane_info: Information about lanes (for backward compatibility)
        lane_sections: List of LaneSection objects (OpenDRIVE lane sections)
        lanes: DEPRECATED - kept for backward compatibility during migration
        speed_limit: Speed limit in km/h (optional)
        junction_id: ID of junction this road connects to (optional)
        predecessor_id: ID of road that precedes this one (optional)
        predecessor_contact: Contact point on predecessor ("start" or "end")
        successor_id: ID of road that follows this one (optional)
        successor_contact: Contact point on successor ("start" or "end")
        opendrive_id: Optional OpenDrive road ID (for round-trip consistency)
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Unnamed Road"
    polyline_ids: List[str] = field(default_factory=list)
    centerline_id: Optional[str] = None  # Required for export
    road_type: RoadType = RoadType.UNKNOWN
    lane_info: LaneInfo = field(default_factory=LaneInfo)
    lane_sections: List[LaneSection] = field(default_factory=list)
    lanes: List[Lane] = field(default_factory=list)  # Deprecated, for backward compatibility
    speed_limit: Optional[float] = None  # km/h
    junction_id: Optional[str] = None
    predecessor_id: Optional[str] = None
    predecessor_contact: str = "end"  # "start" or "end"
    successor_id: Optional[str] = None
    successor_contact: str = "start"  # "start" or "end"
    opendrive_id: Optional[str] = None  # OpenDrive ID for round-trip import/export

    def add_polyline(self, polyline_id: str) -> None:
        """Add a polyline to this road."""
        if polyline_id not in self.polyline_ids:
            self.polyline_ids.append(polyline_id)

    def remove_polyline(self, polyline_id: str) -> None:
        """Remove a polyline from this road."""
        if polyline_id in self.polyline_ids:
            self.polyline_ids.remove(polyline_id)

    def is_valid(self) -> bool:
        """Check if the road has at least one polyline."""
        return len(self.polyline_ids) > 0

    def is_valid_for_export(self) -> bool:
        """Check if the road is valid for OpenDRIVE export."""
        return (
            len(self.polyline_ids) > 0 and
            self.centerline_id is not None and
            self.centerline_id in self.polyline_ids
        )

    def has_centerline(self) -> bool:
        """Check if the road has a centerline assigned."""
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

    def add_lane(self, lane: Lane) -> None:
        """Add a lane to the road."""
        # Remove existing lane with same ID if present
        self.lanes = [l for l in self.lanes if l.id != lane.id]
        self.lanes.append(lane)
        # Sort lanes by ID for consistent ordering
        self.lanes.sort(key=lambda l: l.id)

    def remove_lane(self, lane_id: int) -> None:
        """Remove a lane by ID."""
        self.lanes = [l for l in self.lanes if l.id != lane_id]

    def get_lane(self, lane_id: int, section_number: Optional[int] = None) -> Optional[Lane]:
        """
        Get a lane by ID.

        Args:
            lane_id: The lane ID to search for
            section_number: Optional section number. If None, searches first section with matching lane.

        Returns:
            Lane object or None if not found
        """
        # If using new lane section system
        if self.lane_sections:
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

        # Fallback to deprecated lanes list
        for lane in self.lanes:
            if lane.id == lane_id:
                return lane
        return None

    def get_lanes_sorted(self) -> List[Lane]:
        """
        Get lanes sorted left to right for display.

        DEPRECATED: Use get_section(n).get_lanes_sorted() instead.
        Returns lanes in order: [2, 1, 0, -1, -2] (left to right)
        """
        return sorted(self.lanes, key=lambda l: -l.id)

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

    def get_section_containing_point(self, point_index: int, centerline_points: List[Tuple[float, float]]) -> Optional[LaneSection]:
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
        section_length = section_to_split.get_length_pixels()
        distance_from_start = s - section_to_split.s_start
        distance_from_end = section_to_split.s_end - s

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
            'lanes': [lane.to_dict() for lane in self.lanes],  # Keep for backward compatibility
            'speed_limit': self.speed_limit,
            'junction_id': self.junction_id,
            'predecessor_id': self.predecessor_id,
            'predecessor_contact': self.predecessor_contact,
            'successor_id': self.successor_id,
            'successor_contact': self.successor_contact
        }
        # Only include optional field if set
        if self.opendrive_id is not None:
            data['opendrive_id'] = self.opendrive_id
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

        # Load old lanes for backward compatibility
        lanes_data = data.get('lanes', [])
        lanes = [Lane.from_dict(lane_data) for lane_data in lanes_data]

        road = cls(
            id=data.get('id', str(uuid.uuid4())),
            name=data.get('name', 'Unnamed Road'),
            polyline_ids=data.get('polyline_ids', []),
            centerline_id=data.get('centerline_id'),
            road_type=RoadType(data.get('road_type', 'unknown')),
            lane_info=lane_info,
            lane_sections=lane_sections,
            lanes=lanes,  # Keep for backward compatibility
            speed_limit=data.get('speed_limit'),
            junction_id=data.get('junction_id'),
            predecessor_id=data.get('predecessor_id'),
            predecessor_contact=data.get('predecessor_contact', 'end'),
            successor_id=data.get('successor_id'),
            successor_contact=data.get('successor_contact', 'start'),
            opendrive_id=data.get('opendrive_id')
        )

        # Backward compatibility: migrate old format to lane_sections
        if not road.lane_sections:
            if road.lanes:
                # Migrate existing lanes to a single section
                section = LaneSection(
                    section_number=1,
                    s_start=0.0,
                    s_end=1000.0,  # Default length, will be updated when centerline is available
                    lanes=road.lanes.copy()
                )
                road.lane_sections.append(section)
            else:
                # No lanes at all, generate default
                road.generate_lanes()

        return road

    def __repr__(self) -> str:
        return f"Road(id={self.id[:8]}..., name='{self.name}', polylines={len(self.polyline_ids)})"

"""
Lane section data model for ORBIT.

Represents a lane section in OpenDRIVE format - a segment of a road with
a fixed number of lanes.
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

from .lane import Lane


@dataclass
class LaneSection:
    """
    Represents a lane section in OpenDRIVE.

    Lane sections partition roads whenever the number or function of lanes changes.
    Each section contains a fixed set of lanes and is defined by its start position
    along the road reference line.

    Attributes:
        section_number: Sequential number for display (1, 2, 3, ...)
        s_start: Starting position along centerline in pixels (from road start)
        s_end: Ending position along centerline in pixels
        single_side: Optional flag for single-side sections ("left", "right", or None)
        lanes: List of Lane objects in this section
        end_point_index: Optional point index where this section ends (None = end of road)
    """
    section_number: int
    s_start: float
    s_end: float
    single_side: Optional[str] = None  # "left", "right", or None
    lanes: List[Lane] = field(default_factory=list)
    end_point_index: Optional[int] = None  # Track which point this section ends at

    def get_length_pixels(self) -> float:
        """Get the length of this section in pixels."""
        return self.s_end - self.s_start

    def contains_s_coordinate(self, s: float) -> bool:
        """
        Check if the given s-coordinate falls within this section.

        Args:
            s: S-coordinate in pixels along the centerline

        Returns:
            True if s is in range [s_start, s_end)
        """
        return self.s_start <= s < self.s_end

    def split_at_s(self, s: float, new_section_number: int, split_point_index: Optional[int] = None) -> Tuple['LaneSection', 'LaneSection']:
        """
        Split this section at the given s-coordinate.

        Creates two new sections with duplicated lane properties.

        Args:
            s: S-coordinate where to split (must be within this section)
            new_section_number: Section number for the second (new) section
            split_point_index: Optional point index where the split occurs

        Returns:
            Tuple of (first_section, second_section)

        Raises:
            ValueError: If s is not within this section's range
        """
        if not self.contains_s_coordinate(s) and s != self.s_end:
            raise ValueError(f"Split point {s} is not within section range [{self.s_start}, {self.s_end}]")

        # Create first section (keeps original number, ends at split point)
        first_section = LaneSection(
            section_number=self.section_number,
            s_start=self.s_start,
            s_end=s,
            single_side=self.single_side,
            lanes=self._duplicate_lanes(),
            end_point_index=split_point_index  # Track where this section ends
        )

        # Create second section (gets new number, starts at split point)
        second_section = LaneSection(
            section_number=new_section_number,
            s_start=s,
            s_end=self.s_end,
            single_side=self.single_side,
            lanes=self._duplicate_lanes(),
            end_point_index=self.end_point_index  # Inherit original end point
        )

        return first_section, second_section

    def _duplicate_lanes(self) -> List[Lane]:
        """
        Create deep copies of all lanes in this section.

        Returns:
            List of new Lane objects with same properties
        """
        from copy import deepcopy
        return [deepcopy(lane) for lane in self.lanes]

    def add_lane(self, lane: Lane) -> None:
        """Add a lane to this section."""
        # Remove existing lane with same ID if present
        self.lanes = [l for l in self.lanes if l.id != lane.id]
        self.lanes.append(lane)
        # Sort lanes by ID for consistent ordering
        self.lanes.sort(key=lambda l: l.id)

    def remove_lane(self, lane_id: int) -> None:
        """Remove a lane by ID."""
        self.lanes = [l for l in self.lanes if l.id != lane_id]

    def get_lane(self, lane_id: int) -> Optional[Lane]:
        """Get a lane by ID."""
        for lane in self.lanes:
            if lane.id == lane_id:
                return lane
        return None

    def get_lanes_sorted(self) -> List[Lane]:
        """
        Get lanes sorted left to right for display.

        Returns lanes in order: [2, 1, 0, -1, -2] (left to right)
        """
        return sorted(self.lanes, key=lambda l: -l.id)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'section_number': self.section_number,
            's_start': self.s_start,
            's_end': self.s_end,
            'single_side': self.single_side,
            'lanes': [lane.to_dict() for lane in self.lanes],
            'end_point_index': self.end_point_index
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LaneSection':
        """Create from dictionary."""
        lanes_data = data.get('lanes', [])
        lanes = [Lane.from_dict(lane_data) for lane_data in lanes_data]

        return cls(
            section_number=data['section_number'],
            s_start=data['s_start'],
            s_end=data['s_end'],
            single_side=data.get('single_side'),
            lanes=lanes,
            end_point_index=data.get('end_point_index')  # Backward compatible
        )

    def __repr__(self) -> str:
        return f"LaneSection(num={self.section_number}, s=[{self.s_start:.1f}, {self.s_end:.1f}], lanes={len(self.lanes)})"

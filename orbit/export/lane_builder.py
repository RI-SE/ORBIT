"""
Lane XML builder for OpenDRIVE export.

Handles creation of lane-related XML elements.
"""

from typing import List, Optional
from lxml import etree

from orbit.models import Road, RoadMarkType
from .lane_analyzer import BoundaryInfo


def convert_road_mark_type(road_mark_type: RoadMarkType) -> str:
    """
    Convert ORBIT RoadMarkType enum to OpenDRIVE road mark type string.

    Maps ASAM e_roadMarkType values to valid OpenDRIVE types.
    """
    type_map = {
        RoadMarkType.NONE: 'none',
        RoadMarkType.SOLID: 'solid',
        RoadMarkType.BROKEN: 'broken',
        RoadMarkType.SOLID_SOLID: 'solid solid',
        RoadMarkType.SOLID_BROKEN: 'solid broken',
        RoadMarkType.BROKEN_SOLID: 'broken solid',
        RoadMarkType.BROKEN_BROKEN: 'broken broken',
        RoadMarkType.BOTTS_DOTS: 'botts dots',
        RoadMarkType.GRASS: 'grass',
        RoadMarkType.CURB: 'curb',
        RoadMarkType.CUSTOM: 'solid',  # Fallback to solid
        RoadMarkType.EDGE: 'solid'      # Edge typically solid
    }
    return type_map.get(road_mark_type, 'solid')


class LaneBuilder:
    """Builds lane XML elements for OpenDRIVE export."""

    def __init__(self, scale_x: float = 1.0):
        """
        Initialize lane builder.

        Args:
            scale_x: Scale factor in meters per pixel for s-coordinate conversion
        """
        self.scale_x = scale_x

    def create_lanes(
        self,
        road: Road,
        road_length: float,
        boundary_infos: List[BoundaryInfo]
    ) -> etree.Element:
        """
        Create lanes element with data-driven road marks from boundaries.

        Args:
            road: Road object
            road_length: Total road length in meters
            boundary_infos: List of boundary info for road mark types

        Returns:
            XML lanes element
        """
        lanes = etree.Element('lanes')

        # Build map of lane_id to boundary info for quick lookup
        boundary_map = {b.lane_id: b for b in boundary_infos if b.lane_id is not None}

        # Use lane sections if available, otherwise fall back to old format
        if road.lane_sections:
            self._create_section_based_lanes(lanes, road, boundary_map)
        else:
            self._create_legacy_lanes(lanes, road, road_length, boundary_map)

        return lanes

    def _create_section_based_lanes(
        self,
        lanes: etree.Element,
        road: Road,
        boundary_map: dict
    ) -> None:
        """Create lane elements using lane sections."""
        for section in road.lane_sections:
            lane_section = etree.SubElement(lanes, 'laneSection')

            # Convert pixel s-coordinates to meters
            s_meters = section.s_start * self.scale_x
            lane_section.set('s', f'{s_meters:.6f}')

            # Add singleSide attribute if set
            if section.single_side:
                lane_section.set('singleSide', section.single_side)

            # Build map of lane_id to Lane object for this section
            lane_map = {lane.id: lane for lane in section.lanes}

            # Left lanes (positive IDs)
            left = etree.SubElement(lane_section, 'left')
            left_lanes = [lane for lane in section.lanes if lane.id > 0]
            left_lanes.sort(key=lambda l: l.id)  # Sort ascending: 1, 2, 3...
            for lane_obj in left_lanes:
                boundary_info = boundary_map.get(lane_obj.id)
                lane = self._create_lane(lane_obj, boundary_info)
                left.append(lane)

            # Center lane (reference lane, id=0)
            center = etree.SubElement(lane_section, 'center')
            center_lane_obj = lane_map.get(0)
            if center_lane_obj:
                center_lane = self._create_center_lane(center_lane_obj)
                center.append(center_lane)
            else:
                center_lane = self._create_default_center_lane()
                center.append(center_lane)

            # Right lanes (negative IDs)
            right = etree.SubElement(lane_section, 'right')
            right_lanes = [lane for lane in section.lanes if lane.id < 0]
            right_lanes.sort(key=lambda l: l.id, reverse=True)  # Sort descending: -1, -2, -3...
            for lane_obj in right_lanes:
                boundary_info = boundary_map.get(lane_obj.id)
                lane = self._create_lane(lane_obj, boundary_info)
                right.append(lane)

    def _create_legacy_lanes(
        self,
        lanes: etree.Element,
        road: Road,
        road_length: float,
        boundary_map: dict
    ) -> None:
        """Create lane elements using legacy road.lanes format (backward compatibility)."""
        lane_section = etree.SubElement(lanes, 'laneSection')
        lane_section.set('s', '0.0')

        # Build map of lane_id to Lane object
        lane_map = {lane.id: lane for lane in road.lanes}

        # Left lanes (positive IDs)
        left = etree.SubElement(lane_section, 'left')
        left_lanes = [lane for lane in road.lanes if lane.id > 0]
        left_lanes.sort(key=lambda l: l.id)
        for lane_obj in left_lanes:
            boundary_info = boundary_map.get(lane_obj.id)
            lane = self._create_lane(lane_obj, boundary_info)
            left.append(lane)

        # Center lane (reference lane, id=0)
        center = etree.SubElement(lane_section, 'center')
        center_lane_obj = lane_map.get(0)
        if center_lane_obj:
            center_lane = self._create_center_lane(center_lane_obj)
            center.append(center_lane)
        else:
            center_lane = self._create_default_center_lane()
            center.append(center_lane)

        # Right lanes (negative IDs)
        right = etree.SubElement(lane_section, 'right')
        right_lanes = [lane for lane in road.lanes if lane.id < 0]
        right_lanes.sort(key=lambda l: l.id, reverse=True)
        for lane_obj in right_lanes:
            boundary_info = boundary_map.get(lane_obj.id)
            lane = self._create_lane(lane_obj, boundary_info)
            right.append(lane)

    def _create_center_lane(self, center_lane_obj) -> etree.Element:
        """Create center lane element from Lane object."""
        center_lane = etree.Element('lane')
        center_lane.set('id', '0')
        center_lane.set('type', center_lane_obj.lane_type.value)
        center_lane.set('level', 'false')

        mark_type = convert_road_mark_type(center_lane_obj.road_mark_type)

        road_mark = etree.SubElement(center_lane, 'roadMark')
        road_mark.set('sOffset', '0.0')
        road_mark.set('type', mark_type)
        road_mark.set('weight', 'standard')
        road_mark.set('color', 'standard')
        road_mark.set('width', '0.13')

        return center_lane

    def _create_default_center_lane(self) -> etree.Element:
        """Create default center lane element."""
        center_lane = etree.Element('lane')
        center_lane.set('id', '0')
        center_lane.set('type', 'none')
        center_lane.set('level', 'false')

        road_mark = etree.SubElement(center_lane, 'roadMark')
        road_mark.set('sOffset', '0.0')
        road_mark.set('type', 'solid')
        road_mark.set('weight', 'standard')
        road_mark.set('color', 'standard')
        road_mark.set('width', '0.13')

        return center_lane

    def _create_lane(
        self,
        lane_obj,
        boundary_info: Optional[BoundaryInfo] = None
    ) -> etree.Element:
        """Create a single lane element with data-driven road mark."""
        lane = etree.Element('lane')
        lane.set('id', str(lane_obj.id))
        lane.set('type', lane_obj.lane_type.value)
        lane.set('level', 'false')

        # Lane link (simplified)
        etree.SubElement(lane, 'link')

        # Lane width - use the width from lane object (already in meters)
        width_elem = etree.SubElement(lane, 'width')
        width_elem.set('sOffset', '0.0')
        width_elem.set('a', f'{lane_obj.width:.2f}')
        width_elem.set('b', '0.0')
        width_elem.set('c', '0.0')
        width_elem.set('d', '0.0')

        # Road mark (priority: boundary polyline > lane object road_mark_type)
        if boundary_info and boundary_info.polyline:
            mark_type = convert_road_mark_type(boundary_info.polyline.road_mark_type)
        else:
            mark_type = convert_road_mark_type(lane_obj.road_mark_type)

        road_mark = etree.SubElement(lane, 'roadMark')
        road_mark.set('sOffset', '0.0')
        road_mark.set('type', mark_type)
        road_mark.set('weight', 'standard')
        road_mark.set('color', 'standard')
        road_mark.set('width', '0.13')

        return lane

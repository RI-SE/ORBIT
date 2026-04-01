"""
Lane XML builder for OpenDRIVE export.

Handles creation of lane-related XML elements.
"""

from typing import List, Optional, Sequence

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

    def __init__(self, scale_x: float = 1.0, opendrive_version: str = "1.8"):
        """
        Initialize lane builder.

        Args:
            scale_x: Scale factor in meters per pixel for s-coordinate conversion
            opendrive_version: Target OpenDRIVE version (e.g. "1.8" or "1.4")
        """
        self.scale_x = scale_x
        self.opendrive_version = opendrive_version

    def create_lanes(
        self,
        road: Road,
        road_length: float,
        boundary_infos: List[BoundaryInfo],
        cumulative_metric_s: Optional[Sequence[float]] = None,
    ) -> etree.Element:
        """
        Create lanes element with data-driven road marks from boundaries.

        Args:
            road: Road object
            road_length: Total road length in meters (unused, kept for API compatibility)
            boundary_infos: List of boundary info for road mark types
            cumulative_metric_s: Metric arc-length at each centerline polyline point index.
                When provided, section boundaries are looked up from this list using
                end_point_index instead of being estimated with scale_x.

        Returns:
            XML lanes element
        """
        lanes = etree.Element('lanes')

        # Add lane offset if present (shifts center lane from reference line)
        if road.lane_offset:
            for lo_data in road.lane_offset:
                s, a, b, c, d = lo_data
                lane_offset = etree.SubElement(lanes, 'laneOffset')
                lane_offset.set('s', f'{s:.6g}')
                lane_offset.set('a', f'{a:.6g}')
                lane_offset.set('b', f'{b:.6g}')
                lane_offset.set('c', f'{c:.6g}')
                lane_offset.set('d', f'{d:.6g}')

        # Build map of lane_id to boundary info for quick lookup
        boundary_map = {b.lane_id: b for b in boundary_infos if b.lane_id is not None}

        self._create_section_based_lanes(lanes, road, boundary_map, cumulative_metric_s)

        return lanes

    def _create_section_based_lanes(
        self,
        lanes: etree.Element,
        road: Road,
        boundary_map: dict,
        cumulative_metric_s: Optional[Sequence[float]] = None,
    ) -> None:
        """Create lane elements using lane sections."""
        # Lane-level links are needed at road boundaries for both road-to-road
        # and road-to-junction connections.  CARLA (and other tools) use these
        # to resolve lane continuity across junctions.
        has_road_predecessor = bool(
            road.predecessor_id or road.predecessor_junction_id
        )
        has_road_successor = bool(
            road.successor_id or road.successor_junction_id
        )
        num_sections = len(road.lane_sections)

        # Track which cumulative_metric_s index the previous section ended at
        prev_end_idx = 0

        for idx, section in enumerate(road.lane_sections):
            lane_section = etree.SubElement(lanes, 'laneSection')

            # Compute s_start and section_length in meters.
            # Prefer looking up the exact metric arc-length via end_point_index when
            # cumulative_metric_s is available — this avoids the scale_x error on
            # angled roads where the x-direction scale under-/over-estimates distances.
            if cumulative_metric_s and section.end_point_index is not None:
                n = len(cumulative_metric_s) - 1
                start_idx = min(prev_end_idx, n)
                end_idx = min(section.end_point_index, n)
                s_meters = cumulative_metric_s[start_idx]
                s_end_m = cumulative_metric_s[end_idx]
                section_length_m = max(0.0, s_end_m - s_meters)
                prev_end_idx = section.end_point_index
            else:
                s_meters = section.s_start * self.scale_x
                section_length_px = section.s_end - section.s_start
                section_length_m = section_length_px * self.scale_x

            lane_section.set('s', f'{s_meters:.6f}')

            # Add singleSide attribute if set
            if section.single_side:
                lane_section.set('singleSide', section.single_side)

            # Build map of lane_id to Lane object for this section
            lane_map = {lane.id: lane for lane in section.lanes}

            # OpenDRIVE requires elements in order: left, center, right
            # Only add left/right if there are lanes

            # First section needs predecessor lane links, last needs successor
            add_pred = (idx == 0) and has_road_predecessor
            add_succ = (idx == num_sections - 1) and has_road_successor

            # Left lanes (positive IDs)
            left_lanes = [lane for lane in section.lanes if lane.id > 0]
            left_lanes.sort(key=lambda lane: lane.id)  # Sort ascending: 1, 2, 3...
            if left_lanes:
                left = etree.SubElement(lane_section, 'left')
                for lane_obj in left_lanes:
                    boundary_info = boundary_map.get(lane_obj.id)
                    lane = self._create_lane(
                        lane_obj, boundary_info, section_length_m,
                        add_pred, add_succ
                    )
                    left.append(lane)

            # Center lane (reference lane, id=0) - required
            center = etree.SubElement(lane_section, 'center')
            center_lane_obj = lane_map.get(0)
            if center_lane_obj:
                center_lane = self._create_center_lane(center_lane_obj)
                center.append(center_lane)
            else:
                center_lane = self._create_default_center_lane()
                center.append(center_lane)

            # Right lanes (negative IDs)
            right_lanes = [lane for lane in section.lanes if lane.id < 0]
            right_lanes.sort(key=lambda lane: lane.id, reverse=True)  # Sort descending: -1, -2, -3...
            if right_lanes:
                right = etree.SubElement(lane_section, 'right')
                for lane_obj in right_lanes:
                    boundary_info = boundary_map.get(lane_obj.id)
                    lane = self._create_lane(
                        lane_obj, boundary_info, section_length_m,
                        add_pred, add_succ
                    )
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
        road_mark.set('weight', center_lane_obj.road_mark_weight)
        road_mark.set('color', center_lane_obj.road_mark_color)
        road_mark.set('width', f'{center_lane_obj.road_mark_width:.6g}')
        road_mark.set('laneChange', 'none')

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
        road_mark.set('laneChange', 'none')

        return center_lane

    def _create_lane(
        self,
        lane_obj,
        boundary_info: Optional[BoundaryInfo] = None,
        section_length_m: float = 0.0,
        add_pred_link: bool = False,
        add_succ_link: bool = False
    ) -> etree.Element:
        """Create a single lane element with data-driven road mark.

        Args:
            add_pred_link: If True and no explicit predecessor_id, default to
                the lane's own ID (for road-to-road connections at first section).
            add_succ_link: If True and no explicit successor_id, default to
                the lane's own ID (for road-to-road connections at last section).
        """
        lane = etree.Element('lane')
        lane.set('id', str(lane_obj.id))
        lane.set('type', lane_obj.lane_type.value)
        lane.set('level', 'true' if lane_obj.level else 'false')

        # V1.8 direction and advisory attributes
        if self.opendrive_version == "1.8":
            if lane_obj.direction is not None:
                lane.set('direction', lane_obj.direction)
            if lane_obj.advisory is not None:
                lane.set('advisory', lane_obj.advisory)

        # Lane link with predecessor/successor
        pred_id = lane_obj.predecessor_id
        succ_id = lane_obj.successor_id

        # Default to same lane ID for road-to-road connections
        if pred_id is None and add_pred_link:
            pred_id = lane_obj.id
        if succ_id is None and add_succ_link:
            succ_id = lane_obj.id

        link = etree.SubElement(lane, 'link')
        if pred_id is not None:
            pred = etree.SubElement(link, 'predecessor')
            pred.set('id', str(pred_id))
        if succ_id is not None:
            succ = etree.SubElement(link, 'successor')
            succ.set('id', str(succ_id))

        # Lane width polynomial
        # If width_end is set, calculate width_b for linear transition
        # OpenDRIVE formula: width(ds) = a + b*ds + c*ds² + d*ds³
        width_a = lane_obj.width
        width_b = lane_obj.width_b
        width_c = lane_obj.width_c
        width_d = lane_obj.width_d

        # Override with linear transition if width_end is specified
        if lane_obj.has_variable_width and section_length_m > 0:
            width_a = lane_obj.width
            width_b = (lane_obj.width_end - lane_obj.width) / section_length_m
            # Keep c and d as 0 for linear transition (unless already set)
            if width_c == 0.0 and width_d == 0.0:
                width_c = 0.0
                width_d = 0.0

        width_elem = etree.SubElement(lane, 'width')
        width_elem.set('sOffset', '0.0')
        width_elem.set('a', f'{width_a:.6g}')
        width_elem.set('b', f'{width_b:.6g}')
        width_elem.set('c', f'{width_c:.6g}')
        width_elem.set('d', f'{width_d:.6g}')

        # Road mark (priority: boundary polyline > lane object road_mark_type)
        if boundary_info and boundary_info.polyline:
            mark_type = convert_road_mark_type(boundary_info.polyline.road_mark_type)
        else:
            mark_type = convert_road_mark_type(lane_obj.road_mark_type)

        road_mark = etree.SubElement(lane, 'roadMark')
        road_mark.set('sOffset', '0.0')
        road_mark.set('type', mark_type)
        road_mark.set('weight', lane_obj.road_mark_weight)
        road_mark.set('color', lane_obj.road_mark_color)
        road_mark.set('width', f'{lane_obj.road_mark_width:.6g}')
        road_mark.set('laneChange', 'both')

        # Lane-level speed limit (if set)
        if lane_obj.speed_limit is not None:
            speed = etree.SubElement(lane, 'speed')
            speed.set('sOffset', '0.0')
            speed.set('max', f'{lane_obj.speed_limit:.6g}')
            speed.set('unit', lane_obj.speed_limit_unit)

        # Access restrictions (for shared paths)
        if lane_obj.access_restrictions:
            access = etree.SubElement(lane, 'access')
            access.set('sOffset', '0.0')
            access.set('rule', 'allow')
            for restriction_type in lane_obj.access_restrictions:
                restriction = etree.SubElement(access, 'restriction')
                restriction.set('type', restriction_type)

        # Lane material properties
        if lane_obj.materials:
            for mat_data in lane_obj.materials:
                s_offset, friction, roughness, surface = mat_data
                material = etree.SubElement(lane, 'material')
                material.set('sOffset', f'{s_offset:.6g}')
                material.set('friction', f'{friction:.6g}')
                if roughness is not None:
                    material.set('roughness', f'{roughness:.6g}')
                if surface:
                    material.set('surface', surface)

        # Lane height offsets (for raised sidewalks, etc.)
        if lane_obj.heights:
            for h_data in lane_obj.heights:
                s_offset, inner, outer = h_data
                height = etree.SubElement(lane, 'height')
                height.set('sOffset', f'{s_offset:.6g}')
                height.set('inner', f'{inner:.6g}')
                height.set('outer', f'{outer:.6g}')

        return lane

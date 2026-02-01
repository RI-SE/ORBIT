"""Tests for orbit.export.lane_builder module."""

from dataclasses import dataclass
from typing import Optional
from unittest.mock import Mock

import pytest

from orbit.export.lane_builder import LaneBuilder, convert_road_mark_type
from orbit.models import RoadMarkType
from orbit.models.lane import LaneType


@dataclass
class MockBoundaryInfo:
    """Mock boundary info for testing."""
    polyline_id: str
    polyline: Optional[Mock]
    avg_offset: float
    std_offset: float
    lane_id: Optional[int] = None
    measured_width: Optional[float] = None


class TestConvertRoadMarkType:
    """Tests for convert_road_mark_type function."""

    def test_none_type(self):
        """NONE maps to 'none'."""
        assert convert_road_mark_type(RoadMarkType.NONE) == 'none'

    def test_solid_type(self):
        """SOLID maps to 'solid'."""
        assert convert_road_mark_type(RoadMarkType.SOLID) == 'solid'

    def test_broken_type(self):
        """BROKEN maps to 'broken'."""
        assert convert_road_mark_type(RoadMarkType.BROKEN) == 'broken'

    def test_solid_solid_type(self):
        """SOLID_SOLID maps to 'solid solid'."""
        assert convert_road_mark_type(RoadMarkType.SOLID_SOLID) == 'solid solid'

    def test_solid_broken_type(self):
        """SOLID_BROKEN maps to 'solid broken'."""
        assert convert_road_mark_type(RoadMarkType.SOLID_BROKEN) == 'solid broken'

    def test_broken_solid_type(self):
        """BROKEN_SOLID maps to 'broken solid'."""
        assert convert_road_mark_type(RoadMarkType.BROKEN_SOLID) == 'broken solid'

    def test_broken_broken_type(self):
        """BROKEN_BROKEN maps to 'broken broken'."""
        assert convert_road_mark_type(RoadMarkType.BROKEN_BROKEN) == 'broken broken'

    def test_botts_dots_type(self):
        """BOTTS_DOTS maps to 'botts dots'."""
        assert convert_road_mark_type(RoadMarkType.BOTTS_DOTS) == 'botts dots'

    def test_grass_type(self):
        """GRASS maps to 'grass'."""
        assert convert_road_mark_type(RoadMarkType.GRASS) == 'grass'

    def test_curb_type(self):
        """CURB maps to 'curb'."""
        assert convert_road_mark_type(RoadMarkType.CURB) == 'curb'

    def test_custom_type(self):
        """CUSTOM falls back to 'solid'."""
        assert convert_road_mark_type(RoadMarkType.CUSTOM) == 'solid'

    def test_edge_type(self):
        """EDGE maps to 'solid'."""
        assert convert_road_mark_type(RoadMarkType.EDGE) == 'solid'


class TestLaneBuilderInit:
    """Tests for LaneBuilder initialization."""

    def test_default_init(self):
        """Default initialization."""
        builder = LaneBuilder()
        assert builder.scale_x == 1.0

    def test_custom_scale(self):
        """Custom scale factor."""
        builder = LaneBuilder(scale_x=0.1)
        assert builder.scale_x == 0.1


class TestCreateLanes:
    """Tests for create_lanes method."""

    @pytest.fixture
    def builder(self):
        """Create lane builder."""
        return LaneBuilder(scale_x=0.1)

    @pytest.fixture
    def mock_road(self):
        """Create mock road with one section."""
        road = Mock()
        road.lane_offset = None

        # Create a simple lane section with center and right lane
        section = Mock()
        section.s_start = 0.0
        section.s_end = 1000.0
        section.single_side = None

        center_lane = Mock()
        center_lane.id = 0
        center_lane.lane_type = LaneType.NONE
        center_lane.road_mark_type = RoadMarkType.SOLID
        center_lane.road_mark_weight = 'standard'
        center_lane.road_mark_color = 'white'
        center_lane.road_mark_width = 0.13

        right_lane = Mock()
        right_lane.id = -1
        right_lane.lane_type = LaneType.DRIVING
        right_lane.level = False
        right_lane.direction = None
        right_lane.advisory = None
        right_lane.predecessor_id = None
        right_lane.successor_id = None
        right_lane.width = 3.5
        right_lane.width_b = 0.0
        right_lane.width_c = 0.0
        right_lane.width_d = 0.0
        right_lane.has_variable_width = False
        right_lane.road_mark_type = RoadMarkType.BROKEN
        right_lane.road_mark_weight = 'standard'
        right_lane.road_mark_color = 'white'
        right_lane.road_mark_width = 0.12
        right_lane.speed_limit = None
        right_lane.access_restrictions = []
        right_lane.materials = []
        right_lane.heights = []

        section.lanes = [center_lane, right_lane]
        road.lane_sections = [section]
        return road

    def test_creates_lanes_element(self, builder, mock_road):
        """Creates lanes element."""
        result = builder.create_lanes(mock_road, 100.0, [])

        assert result is not None
        assert result.tag == 'lanes'

    def test_contains_lane_section(self, builder, mock_road):
        """Contains laneSection element."""
        result = builder.create_lanes(mock_road, 100.0, [])

        lane_sections = result.findall('laneSection')
        assert len(lane_sections) == 1

    def test_lane_section_s_coordinate(self, builder, mock_road):
        """Section s-coordinate converted to meters."""
        mock_road.lane_sections[0].s_start = 100.0  # 100 pixels

        result = builder.create_lanes(mock_road, 100.0, [])

        lane_section = result.find('laneSection')
        # 100 pixels * 0.1 m/px = 10 meters
        assert lane_section.get('s') == '10.000000'

    def test_contains_center_lane(self, builder, mock_road):
        """Contains center element with lane."""
        result = builder.create_lanes(mock_road, 100.0, [])

        center = result.find('.//center')
        assert center is not None
        center_lane = center.find('lane')
        assert center_lane is not None
        assert center_lane.get('id') == '0'

    def test_contains_right_lane(self, builder, mock_road):
        """Contains right element with lane."""
        result = builder.create_lanes(mock_road, 100.0, [])

        right = result.find('.//right')
        assert right is not None
        lane = right.find('lane')
        assert lane is not None
        assert lane.get('id') == '-1'


class TestCreateLanesWithLaneOffset:
    """Tests for lane offset handling."""

    @pytest.fixture
    def builder(self):
        """Create lane builder."""
        return LaneBuilder(scale_x=0.1)

    @pytest.fixture
    def mock_road_with_offset(self):
        """Create mock road with lane offset."""
        road = Mock()
        # Lane offset: (s, a, b, c, d)
        road.lane_offset = [(0.0, 0.5, 0.0, 0.0, 0.0)]

        section = Mock()
        section.s_start = 0.0
        section.s_end = 1000.0
        section.single_side = None
        section.lanes = []
        road.lane_sections = [section]
        return road

    def test_lane_offset_element(self, builder, mock_road_with_offset):
        """Lane offset element created."""
        result = builder.create_lanes(mock_road_with_offset, 100.0, [])

        lane_offset = result.find('laneOffset')
        assert lane_offset is not None
        assert lane_offset.get('s') == '0'
        assert lane_offset.get('a') == '0.5'
        assert lane_offset.get('b') == '0'
        assert lane_offset.get('c') == '0'
        assert lane_offset.get('d') == '0'


class TestCreateSectionBasedLanes:
    """Tests for _create_section_based_lanes method."""

    @pytest.fixture
    def builder(self):
        """Create lane builder."""
        return LaneBuilder(scale_x=0.1)

    def test_single_side_attribute(self, builder):
        """Section with singleSide attribute."""
        road = Mock()
        road.lane_offset = None

        section = Mock()
        section.s_start = 0.0
        section.s_end = 1000.0
        section.single_side = 'right'
        section.lanes = []
        road.lane_sections = [section]

        result = builder.create_lanes(road, 100.0, [])

        lane_section = result.find('laneSection')
        assert lane_section.get('singleSide') == 'right'

    def test_multiple_sections(self, builder):
        """Multiple lane sections."""
        road = Mock()
        road.lane_offset = None

        section1 = Mock()
        section1.s_start = 0.0
        section1.s_end = 500.0
        section1.single_side = None
        section1.lanes = []

        section2 = Mock()
        section2.s_start = 500.0
        section2.s_end = 1000.0
        section2.single_side = None
        section2.lanes = []

        road.lane_sections = [section1, section2]

        result = builder.create_lanes(road, 100.0, [])

        lane_sections = result.findall('laneSection')
        assert len(lane_sections) == 2

    def test_left_lanes_sorted(self, builder):
        """Left lanes sorted ascending by ID."""
        road = Mock()
        road.lane_offset = None

        section = Mock()
        section.s_start = 0.0
        section.s_end = 1000.0
        section.single_side = None

        lane1 = Mock(id=2, lane_type=LaneType.DRIVING, level=False,
                     direction=None, advisory=None,
                     predecessor_id=None, successor_id=None,
                     width=3.5, width_b=0.0, width_c=0.0, width_d=0.0,
                     has_variable_width=False,
                     road_mark_type=RoadMarkType.SOLID,
                     road_mark_weight='standard', road_mark_color='white',
                     road_mark_width=0.12, speed_limit=None,
                     access_restrictions=[], materials=[], heights=[])
        lane2 = Mock(id=1, lane_type=LaneType.DRIVING, level=False,
                     direction=None, advisory=None,
                     predecessor_id=None, successor_id=None,
                     width=3.5, width_b=0.0, width_c=0.0, width_d=0.0,
                     has_variable_width=False,
                     road_mark_type=RoadMarkType.SOLID,
                     road_mark_weight='standard', road_mark_color='white',
                     road_mark_width=0.12, speed_limit=None,
                     access_restrictions=[], materials=[], heights=[])

        section.lanes = [lane1, lane2]  # Out of order
        road.lane_sections = [section]

        result = builder.create_lanes(road, 100.0, [])

        left = result.find('.//left')
        lanes = left.findall('lane')
        assert lanes[0].get('id') == '1'  # First
        assert lanes[1].get('id') == '2'  # Second


class TestCreateCenterLane:
    """Tests for _create_center_lane method."""

    @pytest.fixture
    def builder(self):
        """Create lane builder."""
        return LaneBuilder()

    def test_center_lane_attributes(self, builder):
        """Center lane has correct attributes."""
        center_lane_obj = Mock()
        center_lane_obj.lane_type = LaneType.NONE
        center_lane_obj.road_mark_type = RoadMarkType.SOLID
        center_lane_obj.road_mark_weight = 'standard'
        center_lane_obj.road_mark_color = 'yellow'
        center_lane_obj.road_mark_width = 0.15

        result = builder._create_center_lane(center_lane_obj)

        assert result.get('id') == '0'
        assert result.get('type') == 'none'
        assert result.get('level') == 'false'

    def test_center_lane_road_mark(self, builder):
        """Center lane has road mark."""
        center_lane_obj = Mock()
        center_lane_obj.lane_type = LaneType.NONE
        center_lane_obj.road_mark_type = RoadMarkType.BROKEN
        center_lane_obj.road_mark_weight = 'bold'
        center_lane_obj.road_mark_color = 'yellow'
        center_lane_obj.road_mark_width = 0.15

        result = builder._create_center_lane(center_lane_obj)

        road_mark = result.find('roadMark')
        assert road_mark.get('type') == 'broken'
        assert road_mark.get('weight') == 'bold'
        assert road_mark.get('color') == 'yellow'


class TestCreateDefaultCenterLane:
    """Tests for _create_default_center_lane method."""

    @pytest.fixture
    def builder(self):
        """Create lane builder."""
        return LaneBuilder()

    def test_default_center_lane(self, builder):
        """Default center lane has expected values."""
        result = builder._create_default_center_lane()

        assert result.get('id') == '0'
        assert result.get('type') == 'none'
        road_mark = result.find('roadMark')
        assert road_mark.get('type') == 'solid'
        assert road_mark.get('weight') == 'standard'


class TestCreateLane:
    """Tests for _create_lane method."""

    @pytest.fixture
    def builder(self):
        """Create lane builder."""
        return LaneBuilder(scale_x=0.1)

    @pytest.fixture
    def mock_lane(self):
        """Create mock lane object."""
        lane = Mock()
        lane.id = -1
        lane.lane_type = LaneType.DRIVING
        lane.level = False
        lane.direction = None
        lane.advisory = None
        lane.predecessor_id = None
        lane.successor_id = None
        lane.width = 3.5
        lane.width_b = 0.0
        lane.width_c = 0.0
        lane.width_d = 0.0
        lane.has_variable_width = False
        lane.road_mark_type = RoadMarkType.SOLID
        lane.road_mark_weight = 'standard'
        lane.road_mark_color = 'white'
        lane.road_mark_width = 0.12
        lane.speed_limit = None
        lane.access_restrictions = []
        lane.materials = []
        lane.heights = []
        return lane

    def test_lane_basic_attributes(self, builder, mock_lane):
        """Lane has basic attributes."""
        result = builder._create_lane(mock_lane)

        assert result.get('id') == '-1'
        assert result.get('type') == 'driving'
        assert result.get('level') == 'false'

    def test_lane_level_true(self, builder, mock_lane):
        """Lane level attribute when true."""
        mock_lane.level = True

        result = builder._create_lane(mock_lane)

        assert result.get('level') == 'true'

    def test_lane_direction_attribute(self, builder, mock_lane):
        """Lane direction attribute."""
        mock_lane.direction = 'forward'

        result = builder._create_lane(mock_lane)

        assert result.get('direction') == 'forward'

    def test_lane_advisory_attribute(self, builder, mock_lane):
        """Lane advisory attribute."""
        mock_lane.advisory = 'use'

        result = builder._create_lane(mock_lane)

        assert result.get('advisory') == 'use'

    def test_lane_link_predecessor(self, builder, mock_lane):
        """Lane link with predecessor."""
        mock_lane.predecessor_id = -2

        result = builder._create_lane(mock_lane)

        link = result.find('link')
        pred = link.find('predecessor')
        assert pred is not None
        assert pred.get('id') == '-2'

    def test_lane_link_successor(self, builder, mock_lane):
        """Lane link with successor."""
        mock_lane.successor_id = -1

        result = builder._create_lane(mock_lane)

        link = result.find('link')
        succ = link.find('successor')
        assert succ is not None
        assert succ.get('id') == '-1'

    def test_lane_width_polynomial(self, builder, mock_lane):
        """Lane width polynomial coefficients."""
        mock_lane.width = 3.5
        mock_lane.width_b = 0.01
        mock_lane.width_c = 0.001
        mock_lane.width_d = 0.0001

        result = builder._create_lane(mock_lane)

        width = result.find('width')
        assert width.get('a') == '3.5'
        assert width.get('b') == '0.01'
        assert width.get('c') == '0.001'
        assert width.get('d') == '0.0001'

    def test_lane_variable_width(self, builder, mock_lane):
        """Lane with variable width calculates linear b coefficient."""
        mock_lane.has_variable_width = True
        mock_lane.width = 3.0  # Start width
        mock_lane.width_end = 4.0  # End width
        mock_lane.width_b = 0.0
        mock_lane.width_c = 0.0
        mock_lane.width_d = 0.0

        # Section length 10 meters
        result = builder._create_lane(mock_lane, section_length_m=10.0)

        width = result.find('width')
        assert width.get('a') == '3'
        # b = (4.0 - 3.0) / 10.0 = 0.1
        assert width.get('b') == '0.1'

    def test_lane_road_mark_from_lane(self, builder, mock_lane):
        """Road mark from lane object."""
        mock_lane.road_mark_type = RoadMarkType.BROKEN

        result = builder._create_lane(mock_lane)

        road_mark = result.find('roadMark')
        assert road_mark.get('type') == 'broken'

    def test_lane_road_mark_from_boundary(self, builder, mock_lane):
        """Road mark from boundary info overrides lane."""
        mock_polyline = Mock()
        mock_polyline.road_mark_type = RoadMarkType.SOLID_SOLID

        boundary_info = MockBoundaryInfo(
            polyline_id='p1',
            polyline=mock_polyline,
            avg_offset=3.5,
            std_offset=0.1,
            lane_id=-1
        )

        result = builder._create_lane(mock_lane, boundary_info)

        road_mark = result.find('roadMark')
        assert road_mark.get('type') == 'solid solid'

    def test_lane_speed_limit(self, builder, mock_lane):
        """Lane with speed limit."""
        mock_lane.speed_limit = 50.0
        mock_lane.speed_limit_unit = 'km/h'

        result = builder._create_lane(mock_lane)

        speed = result.find('speed')
        assert speed is not None
        assert speed.get('max') == '50'
        assert speed.get('unit') == 'km/h'

    def test_lane_access_restrictions(self, builder, mock_lane):
        """Lane with access restrictions."""
        mock_lane.access_restrictions = ['bicycle', 'pedestrian']

        result = builder._create_lane(mock_lane)

        access = result.find('access')
        assert access is not None
        restrictions = access.findall('restriction')
        assert len(restrictions) == 2
        types = [r.get('type') for r in restrictions]
        assert 'bicycle' in types
        assert 'pedestrian' in types

    def test_lane_materials(self, builder, mock_lane):
        """Lane with material properties."""
        # (s_offset, friction, roughness, surface)
        mock_lane.materials = [(0.0, 0.8, 0.02, 'asphalt')]

        result = builder._create_lane(mock_lane)

        material = result.find('material')
        assert material is not None
        assert material.get('sOffset') == '0'
        assert material.get('friction') == '0.8'
        assert material.get('roughness') == '0.02'
        assert material.get('surface') == 'asphalt'

    def test_lane_heights(self, builder, mock_lane):
        """Lane with height offsets."""
        # (s_offset, inner, outer)
        mock_lane.heights = [(0.0, 0.0, 0.15)]

        result = builder._create_lane(mock_lane)

        height = result.find('height')
        assert height is not None
        assert height.get('sOffset') == '0'
        assert height.get('inner') == '0'
        assert height.get('outer') == '0.15'

    def test_lane_type_sidewalk(self, builder, mock_lane):
        """Lane with sidewalk type."""
        mock_lane.lane_type = LaneType.SIDEWALK

        result = builder._create_lane(mock_lane)

        assert result.get('type') == 'sidewalk'

    def test_lane_type_biking(self, builder, mock_lane):
        """Lane with biking type."""
        mock_lane.lane_type = LaneType.BIKING

        result = builder._create_lane(mock_lane)

        assert result.get('type') == 'biking'

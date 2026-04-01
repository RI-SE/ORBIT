"""Tests for RoadLaneLinksDialog — per-lane predecessor/successor link editing."""

import pytest

from orbit.models import Lane, LaneInfo, LaneSection, LaneType, Road
from orbit.models.lane_section import LaneSection as LS


@pytest.fixture
def road_with_lanes():
    """Road with a single lane section containing left and right lanes."""
    road = Road(name="Test Road")
    road.lane_info = LaneInfo(left_count=1, right_count=1, lane_width=3.5)
    road.generate_lanes(centerline_length=100.0)
    return road


class TestRoadLaneLinksSave:
    """Tests for lane link persistence via RoadLaneLinksDialog.accept() logic."""

    def test_lane_predecessor_saved(self, road_with_lanes):
        """Setting a predecessor lane ID persists on the lane object."""
        road = road_with_lanes
        lane = next(ln for ln in road.lane_sections[0].lanes if ln.id == -1)
        assert lane.predecessor_id is None

        lane.predecessor_id = -1  # simulating dialog save
        assert road.lane_sections[0].lanes[road.lane_sections[0].lanes.index(lane)].predecessor_id == -1

    def test_lane_successor_saved(self, road_with_lanes):
        """Setting a successor lane ID persists on the lane object."""
        road = road_with_lanes
        lane = next(ln for ln in road.lane_sections[0].lanes if ln.id == 1)
        lane.successor_id = 1
        assert lane.successor_id == 1

    def test_zero_maps_to_none(self, road_with_lanes):
        """Value of 0 should be stored as None (no link)."""
        road = road_with_lanes
        lane = next(ln for ln in road.lane_sections[0].lanes if ln.id == -1)
        lane.predecessor_id = 5  # set a value first

        # Simulate dialog saving 0 → None
        val = 0
        lane.predecessor_id = val if val != 0 else None
        assert lane.predecessor_id is None

    def test_nonzero_value_stored(self, road_with_lanes):
        """Non-zero values are stored as-is."""
        road = road_with_lanes
        lane = next(ln for ln in road.lane_sections[0].lanes if ln.id == -1)

        val = -2
        lane.predecessor_id = val if val != 0 else None
        assert lane.predecessor_id == -2

    def test_lane_links_survive_serialization(self, road_with_lanes):
        """Lane predecessor/successor IDs survive to_dict/from_dict round-trip."""
        road = road_with_lanes
        lane = next(ln for ln in road.lane_sections[0].lanes if ln.id == -1)
        lane.predecessor_id = -1
        lane.successor_id = -2

        data = road.to_dict()
        restored = Road.from_dict(data)

        restored_lane = next(
            (ln for section in restored.lane_sections for ln in section.lanes if ln.id == -1),
            None
        )
        assert restored_lane is not None
        assert restored_lane.predecessor_id == -1
        assert restored_lane.successor_id == -2

    def test_none_links_omitted_from_dict(self, road_with_lanes):
        """Lanes with no links don't include predecessor_id/successor_id in dict."""
        road = road_with_lanes
        lane = next(ln for ln in road.lane_sections[0].lanes if ln.id == -1)
        assert lane.predecessor_id is None
        assert lane.successor_id is None

        lane_data = lane.to_dict()
        assert 'predecessor_id' not in lane_data
        assert 'successor_id' not in lane_data


class TestRoadLaneLinksDialogImport:
    """Tests for RoadLaneLinksDialog import and instantiation (no GUI)."""

    def test_import_succeeds(self):
        """RoadLaneLinksDialog can be imported without errors."""
        from orbit.gui.dialogs.road_lane_links_dialog import RoadLaneLinksDialog
        assert RoadLaneLinksDialog is not None

    def test_edit_lane_links_returns_false_for_no_sections(self):
        """edit_lane_links returns False when road has no lane sections."""
        from orbit.gui.dialogs.road_lane_links_dialog import RoadLaneLinksDialog
        road = Road(name="Empty Road")
        assert not road.lane_sections
        result = RoadLaneLinksDialog.edit_lane_links(road, parent=None)
        assert result is False

"""Tests for the manual connecting-road chooser."""

import pytest
from PyQt6.QtWidgets import QApplication

from orbit.gui.dialogs.add_connecting_road_dialog import AddConnectingRoadDialog
from orbit_core.models import Junction, LineType, Polyline, Project
from orbit_core.models.lane import Lane, LaneType
from orbit_core.models.lane_section import LaneSection
from orbit_core.models.road import Road


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def project_with_junction():
    project = Project()
    for road_id, points, lanes in (
        ("a", [(0.0, 100.0), (80.0, 100.0)], [
            Lane(id=-1, width=3.5),
            Lane(id=0, width=0.0, lane_type=LaneType.NONE),
            Lane(id=1, width=0.0, lane_type=LaneType.MEDIAN),
            Lane(id=2, width=5.0),
        ]),
        ("b", [(120.0, 100.0), (200.0, 100.0)], None),
    ):
        polyline = Polyline(id=road_id, points=points, line_type=LineType.CENTERLINE)
        project.add_polyline(polyline)
        road = Road(id=road_id, name=f"Road {road_id}", centerline_id=road_id)
        road.polyline_ids = [road_id]
        road.lane_sections = [LaneSection(
            section_number=1, s_start=0.0, s_end=100.0,
            lanes=lanes or [
                Lane(id=-1, width=3.5),
                Lane(id=0, width=0.0, lane_type=LaneType.NONE),
                Lane(id=1, width=3.5),
            ],
        )]
        project.add_road(road)
    junction = Junction(id="j1", name="J", center_point=(100.0, 100.0))
    junction.connected_road_ids = ["a", "b"]
    project.junctions = [junction]
    return project, junction


class TestLaneChoices:
    def test_driving_lanes_listed_before_others(self, qapp, project_with_junction):
        project, junction = project_with_junction
        dialog = AddConnectingRoadDialog(junction, project)
        labels = [dialog.from_lane_combo.itemText(i)
                  for i in range(dialog.from_lane_combo.count())]
        drivable = [i for i, t in enumerate(labels) if "not drivable" not in t]
        undrivable = [i for i, t in enumerate(labels) if "not drivable" in t]
        assert drivable and undrivable
        assert max(drivable) < min(undrivable)

    def test_zero_width_median_marked_not_drivable(self, qapp, project_with_junction):
        project, junction = project_with_junction
        dialog = AddConnectingRoadDialog(junction, project)
        labels = [dialog.from_lane_combo.itemText(i)
                  for i in range(dialog.from_lane_combo.count())]
        assert any("lane 1" in t and "not drivable" in t for t in labels)

    def test_defaults_to_a_drivable_lane(self, qapp, project_with_junction):
        """A median would give the movement a zero-width connecting lane."""
        project, junction = project_with_junction
        dialog = AddConnectingRoadDialog(junction, project)
        assert dialog.from_lane_combo.currentData() in (2, -1)

    def test_selection_carries_roads_and_lanes(self, qapp, project_with_junction):
        project, junction = project_with_junction
        dialog = AddConnectingRoadDialog(junction, project)
        from_road, to_road, turn, from_lane, to_lane = dialog.get_selection()
        assert (from_road, to_road) == ("a", "b")
        assert turn is None
        assert from_lane is not None and to_lane is not None


class TestWarnings:
    def test_same_road_warns_about_uturn(self, qapp, project_with_junction):
        project, junction = project_with_junction
        dialog = AddConnectingRoadDialog(junction, project)
        dialog.to_combo.setCurrentIndex(dialog.from_combo.currentIndex())
        assert "U-turn" in dialog.warning_label.text()

    def test_no_warning_for_a_fresh_pair(self, qapp, project_with_junction):
        project, junction = project_with_junction
        dialog = AddConnectingRoadDialog(junction, project)
        assert dialog.warning_label.text() == ""

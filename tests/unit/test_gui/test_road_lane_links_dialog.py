"""RoadLaneLinksDialog: lives with the GUI, since it needs PyQt6.

Moved out of orbit-core's tests -- the headless library must not depend on the
application, or it cannot be tested standalone.
"""

import os

# Qt tests must not try to open a display.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from orbit_core.models import Road  # noqa: E402


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

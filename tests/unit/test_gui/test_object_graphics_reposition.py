"""ObjectGraphicsItem must follow its model position when re-projected.

Point objects (trees, lampposts, cones, simple buildings) are positioned via
setPos with the path centred at the origin. update_graphics rebuilds the path
but must also re-sync the scene position from obj.position; otherwise an
adjustment that re-projects geo coords moves the model but leaves the on-screen
object behind (the reported "trees don't move when shifting/stretching" bug).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from orbit.gui.graphics.object_graphics_item import ObjectGraphicsItem
from orbit.models.object import ObjectType, RoadObject

_app = QApplication.instance() or QApplication([])


def _tree(position):
    obj = RoadObject(object_id="t1", position=position,
                     object_type=ObjectType.TREE_CONIFER)
    obj.geo_position = (12.0, 57.0)
    return obj


def test_point_object_follows_model_position_on_update():
    obj = _tree((100.0, 200.0))
    item = ObjectGraphicsItem(obj)
    assert item.pos() == QPointF(100.0, 200.0)

    # Simulate an adjustment re-projecting geo->pixel to a new position.
    obj.position = (150.0, 260.0)
    item.update_graphics()

    assert item.pos() == QPointF(150.0, 260.0)
    # Programmatic move must not wipe the geo source of truth.
    assert obj.geo_position == (12.0, 57.0)


def test_programmatic_move_does_not_notify_change():
    obj = _tree((0.0, 0.0))
    item = ObjectGraphicsItem(obj)
    calls = []
    item.object_changed = calls.append

    obj.position = (40.0, 40.0)
    item.update_graphics()

    assert calls == []  # no spurious "modified" notification
    assert obj.geo_position == (12.0, 57.0)

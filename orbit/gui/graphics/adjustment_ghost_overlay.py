"""Ghost overlay showing unadjusted geometry positions during adjustment mode."""

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainterPath, QPen
from PyQt6.QtWidgets import QGraphicsPathItem

GHOST_COLOR = QColor(220, 60, 60, 160)  # Red, ~63% opacity
GHOST_PEN_WIDTH = 1.5
JUNCTION_GHOST_RADIUS = 8


class AdjustmentGhostOverlay(QGraphicsPathItem):
    """Semi-transparent overlay showing geometry at unadjusted (original) positions."""

    def __init__(self):
        super().__init__()
        self.setZValue(50)
        pen = QPen(GHOST_COLOR, GHOST_PEN_WIDTH)
        pen.setStyle(Qt.PenStyle.DotLine)
        self.setPen(pen)
        self.setBrush(QColor(0, 0, 0, 0))

    def build(self, project, transformer):
        """Build ghost geometry once from project using unadjusted positions."""
        path = QPainterPath()

        if not project or not transformer:
            self.setPath(path)
            return

        for polyline in project.polylines:
            if not polyline.has_geo_coords():
                continue
            points = [
                transformer.geo_to_pixel_unadjusted(lon, lat)
                for lon, lat in polyline.geo_points
            ]
            if len(points) >= 2:
                path.moveTo(points[0][0], points[0][1])
                for x, y in points[1:]:
                    path.lineTo(x, y)

        for junction in project.junctions:
            if not junction.has_geo_coords():
                continue
            x, y = transformer.geo_to_pixel_unadjusted(
                junction.geo_center_point[0], junction.geo_center_point[1]
            )
            r = JUNCTION_GHOST_RADIUS
            path.addEllipse(QRectF(x - r, y - r, 2 * r, 2 * r))

            for cr_id in junction.connecting_road_ids:
                cr = project.get_road(cr_id)
                if cr and cr.has_geo_coords():
                    points = [
                        transformer.geo_to_pixel_unadjusted(lon, lat)
                        for lon, lat in cr.inline_geo_path
                    ]
                    if len(points) >= 2:
                        path.moveTo(points[0][0], points[0][1])
                        for px, py in points[1:]:
                            path.lineTo(px, py)

        self.setPath(path)

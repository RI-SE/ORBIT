"""
Re-project all project geometry between two coordinate transformers.

Used when switching between background images (e.g. drone photo → aerial tiles)
to recompute pixel coordinates while preserving geographic positions.
"""

import logging
from typing import Optional

from orbit_core.models.project import Project
from orbit_core.utils.coordinate_transform import CoordinateTransformer
from orbit_core.utils.geo_sync import refresh_stale_geo_points

logger = logging.getLogger(__name__)


def reproject_project_geometry(
    project: Project,
    old_transformer: Optional[CoordinateTransformer],
    new_transformer: CoordinateTransformer,
) -> int:
    """
    Re-project all geometry in a project from one pixel space to another.

    For entities with geographic coordinates (geo_points / geo_position),
    new pixel positions are computed directly from the geographic coords
    using new_transformer.  For entities with only pixel coordinates,
    old_transformer is used first to obtain geographic coords, which are
    then projected into the new pixel space.

    Args:
        project: The project whose geometry will be updated in-place.
        old_transformer: Transformer for the *current* pixel space.
            Required for pixel-only entities. May be None if all
            entities have geo coords.
        new_transformer: Transformer for the *target* pixel space.

    Returns:
        Number of entities re-projected.
    """
    # Bring geo coords in sync with any pixel edits made in the current
    # pixel space before geo_to_pixel overwrites the pixel positions —
    # otherwise unsynced pixel edits would be silently reverted.
    # edited_only: unflagged drift may come from adjustment/transformer
    # changes where geo is the authority, so only explicit edits and
    # length mismatches are reconciled here.
    if old_transformer is not None:
        refresh_stale_geo_points(project, old_transformer, edited_only=True)

    count = 0

    # --- Polylines ---
    for polyline in project.polylines:
        if polyline.has_geo_coords():
            new_points = []
            for lon, lat in polyline.geo_points:
                px, py = new_transformer.geo_to_pixel(lon, lat)
                new_points.append((px, py))
            polyline.points = new_points
            count += 1
        elif old_transformer and polyline.points:
            geo_pts = []
            new_points = []
            for px, py in polyline.points:
                lon, lat = old_transformer.pixel_to_geo(px, py)
                geo_pts.append((lon, lat))
                npx, npy = new_transformer.geo_to_pixel(lon, lat)
                new_points.append((npx, npy))
            polyline.geo_points = geo_pts
            polyline.points = new_points
            count += 1

    # --- Junctions ---
    for junction in project.junctions:
        if junction.has_geo_coords():
            lon, lat = junction.geo_center_point
            px, py = new_transformer.geo_to_pixel(lon, lat)
            junction.center_point = (px, py)
            if junction.geo_roundabout_center:
                rlon, rlat = junction.geo_roundabout_center
                rpx, rpy = new_transformer.geo_to_pixel(rlon, rlat)
                junction.roundabout_center = (rpx, rpy)
            count += 1
        elif old_transformer and junction.center_point:
            cx, cy = junction.center_point
            lon, lat = old_transformer.pixel_to_geo(cx, cy)
            junction.geo_center_point = (lon, lat)
            px, py = new_transformer.geo_to_pixel(lon, lat)
            junction.center_point = (px, py)
            count += 1

        # Re-project connecting roads within this junction
        for cr_id in junction.connecting_road_ids:
            conn_road = project.get_road(cr_id)
            if not conn_road:
                continue
            if conn_road.has_geo_coords():
                conn_road.inline_path = [
                    new_transformer.geo_to_pixel(lon, lat)
                    for lon, lat in conn_road.inline_geo_path
                ]
                count += 1
            elif old_transformer and conn_road.inline_path:
                geo_pts = [
                    old_transformer.pixel_to_geo(x, y)
                    for x, y in conn_road.inline_path
                ]
                conn_road.inline_geo_path = geo_pts
                conn_road.inline_path = [
                    new_transformer.geo_to_pixel(lon, lat)
                    for lon, lat in geo_pts
                ]
                count += 1

    # --- Signals ---
    for signal in project.signals:
        if signal.has_geo_coords():
            lon, lat = signal.geo_position
            px, py = new_transformer.geo_to_pixel(lon, lat)
            signal.position = (px, py)
            count += 1
        elif old_transformer:
            sx, sy = signal.position
            lon, lat = old_transformer.pixel_to_geo(sx, sy)
            signal.geo_position = (lon, lat)
            px, py = new_transformer.geo_to_pixel(lon, lat)
            signal.position = (px, py)
            count += 1

    # --- Road Objects ---
    for obj in project.objects:
        if obj.has_geo_coords():
            if obj.geo_points:
                new_pts = []
                for lon, lat in obj.geo_points:
                    px, py = new_transformer.geo_to_pixel(lon, lat)
                    new_pts.append((px, py))
                obj.points = new_pts
            elif obj.geo_position:
                lon, lat = obj.geo_position
                px, py = new_transformer.geo_to_pixel(lon, lat)
                obj.position = (px, py)
            count += 1
        elif old_transformer:
            if hasattr(obj, 'points') and obj.points:
                geo_pts = []
                new_pts = []
                for px, py in obj.points:
                    lon, lat = old_transformer.pixel_to_geo(px, py)
                    geo_pts.append((lon, lat))
                    npx, npy = new_transformer.geo_to_pixel(lon, lat)
                    new_pts.append((npx, npy))
                obj.geo_points = geo_pts
                obj.points = new_pts
            else:
                ox, oy = obj.position
                lon, lat = old_transformer.pixel_to_geo(ox, oy)
                obj.geo_position = (lon, lat)
                px, py = new_transformer.geo_to_pixel(lon, lat)
                obj.position = (px, py)
            count += 1

    # --- Control Points ---
    # Re-project control point pixel positions (geographic coords stay fixed)
    for cp in project.control_points:
        px, py = new_transformer.geo_to_pixel(cp.longitude, cp.latitude)
        cp.pixel_x = px
        cp.pixel_y = py
        count += 1

    # --- Parking Spaces ---
    for parking in project.parking_spaces:
        if parking.geo_points:
            # Polygon parking — reproject all polygon vertices
            new_pts = [new_transformer.geo_to_pixel(lon, lat) for lon, lat in parking.geo_points]
            parking.points = new_pts
            parking.position = (
                sum(x for x, _ in new_pts) / len(new_pts),
                sum(y for _, y in new_pts) / len(new_pts),
            )
            count += 1
        elif parking.geo_position:
            # Point parking
            lon, lat = parking.geo_position
            px, py = new_transformer.geo_to_pixel(lon, lat)
            parking.position = (px, py)
            count += 1
        elif old_transformer:
            if parking.points and len(parking.points) >= 3:
                geo_pts = []
                new_pts = []
                for px, py in parking.points:
                    lon, lat = old_transformer.pixel_to_geo(px, py)
                    geo_pts.append((lon, lat))
                    npx, npy = new_transformer.geo_to_pixel(lon, lat)
                    new_pts.append((npx, npy))
                parking.geo_points = geo_pts
                parking.points = new_pts
                parking.position = (
                    sum(x for x, _ in new_pts) / len(new_pts),
                    sum(y for _, y in new_pts) / len(new_pts),
                )
            else:
                ox, oy = parking.position
                lon, lat = old_transformer.pixel_to_geo(ox, oy)
                parking.geo_position = (lon, lat)
                px, py = new_transformer.geo_to_pixel(lon, lat)
                parking.position = (px, py)
            count += 1

    logger.info("Re-projected %d entities to new pixel space", count)
    return count

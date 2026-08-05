"""
Geo/pixel consistency for dual-stored geometry.

Contract: geo coords are authoritative for output, pixel coords for
editing. Point-mutating edits set Polyline.geo_stale; refresh recomputes
only points whose geo no longer round-trips to the stored pixel, so
imported geo precision is preserved for untouched points.
"""

import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

# Drift below this is treated as transformer noise for un-edited polylines
# (refreshing would needlessly degrade imported geo precision).
TRANSFORM_DRIFT_THRESHOLD_PX = 2.0
# Round-trip tolerance for edited (geo_stale) polylines: catches real
# sub-2px edits while absorbing float/projection-frame noise.
EDIT_EPSILON_PX = 0.1


def _refresh_point_pairs(points, geo_points, transformer, threshold) -> int:
    """Recompute geo entries that diverge from their pixel point (mutates geo_points)."""
    refreshed = 0
    for i, (px, py) in enumerate(points):
        lon, lat = geo_points[i]
        try:
            rpx, rpy = transformer.geo_to_pixel(lon, lat)
            stale = abs(rpx - px) > threshold or abs(rpy - py) > threshold
        except Exception:
            stale = True
        if stale:
            geo_points[i] = transformer.pixel_to_geo(px, py)
            refreshed += 1
    return refreshed


def refresh_polyline_geo_points(polyline, transformer,
                                edited_only: bool = False) -> int:
    """Bring polyline.geo_points back in sync with polyline.points.

    Length mismatch rebuilds geo entirely from pixels; an edited
    (geo_stale) polyline gets a tight round-trip scan.  Unflagged drift
    is reconciled with a loose threshold only when ``edited_only`` is
    False — such drift can also come from transformer/adjustment changes
    where geo is the authority and pixels are the stale side.
    """
    if not polyline.geo_points:
        polyline.geo_stale = False
        return 0
    if len(polyline.geo_points) != len(polyline.points):
        logger.warning(
            "Polyline %s: geo_points length %d != points length %d — "
            "rebuilding geo from pixels",
            polyline.id, len(polyline.geo_points), len(polyline.points),
        )
        polyline.geo_points = [
            transformer.pixel_to_geo(px, py) for px, py in polyline.points
        ]
        polyline.geo_stale = False
        return len(polyline.points)
    if polyline.geo_stale:
        threshold = EDIT_EPSILON_PX
    elif edited_only:
        return 0
    else:
        threshold = TRANSFORM_DRIFT_THRESHOLD_PX
    refreshed = _refresh_point_pairs(
        polyline.points, polyline.geo_points, transformer, threshold)
    polyline.geo_stale = False
    return refreshed


def refresh_stale_geo_points(project, transformer,
                             edited_only: bool = False) -> int:
    """Refresh stale geo coords on all polylines and connecting-road paths.

    With ``edited_only`` (used before view-switch reprojection) only
    explicitly edited polylines and length mismatches are reconciled;
    unflagged drift keeps geo as the authority.
    """
    if transformer is None:
        return 0
    refreshed = 0
    for polyline in project.polylines:
        refreshed += refresh_polyline_geo_points(
            polyline, transformer, edited_only=edited_only)
    for road in project.roads:
        if not road.inline_geo_path or not road.inline_path:
            continue
        if len(road.inline_geo_path) != len(road.inline_path):
            logger.warning(
                "Connecting road %s: inline_geo_path length %d != inline_path "
                "length %d — rebuilding geo from pixels",
                road.id, len(road.inline_geo_path), len(road.inline_path),
            )
            road.inline_geo_path = [
                transformer.pixel_to_geo(px, py) for px, py in road.inline_path
            ]
            refreshed += len(road.inline_path)
            continue
        if not edited_only:
            refreshed += _refresh_point_pairs(
                road.inline_path, road.inline_geo_path, transformer,
                TRANSFORM_DRIFT_THRESHOLD_PX)
    if refreshed:
        logger.info("Refreshed %d stale geo point(s)", refreshed)
    return refreshed


def polyline_to_metric_points(polyline, transformer) -> List[Tuple[float, float]]:
    """Convert a polyline to metric points; geo only when consistent with pixels."""
    if polyline.geo_points and len(polyline.geo_points) == len(polyline.points):
        return [
            transformer.latlon_to_meters(lat, lon)
            for lon, lat in polyline.geo_points
        ]
    if polyline.geo_points:
        logger.warning(
            "Polyline %s: geo/pixel length mismatch — converting from pixel coords",
            polyline.id,
        )
    return transformer.pixels_to_meters_batch(polyline.points)

"""
Tile fetcher for aerial/satellite imagery.

Fetches slippy-map tiles from ESRI World Imagery, stitches them into a single
image, and returns the image alongside the exact geographic bounding box.
Uses a local file cache to avoid redundant downloads.
"""

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple
from urllib import request as urllib_request

import cv2
import numpy as np

logger = logging.getLogger(__name__)

ESRI_TILE_URL = (
    "https://clarity.maptiles.arcgis.com/arcgis/rest/services/"
    "World_Imagery/MapServer/tile/{z}/{y}/{x}"
)
TILE_SIZE = 256  # Standard slippy-map tile size in pixels
USER_AGENT = "ORBIT-MapViewer/1.0"
MAX_TILES = 400  # Safety limit to avoid accidental huge downloads


@dataclass
class TileResult:
    """Result of a tile fetch + stitch operation."""
    image: np.ndarray  # H×W×3 RGB numpy array
    geo_bbox: Tuple[float, float, float, float]  # (min_lon, min_lat, max_lon, max_lat)
    zoom: int
    tile_count: int


def deg2num(lat_deg: float, lon_deg: float, zoom: int) -> Tuple[int, int]:
    """Convert lat/lon to slippy-map tile indices."""
    lat_rad = math.radians(lat_deg)
    n = 2.0 ** zoom
    xtile = int(math.floor((lon_deg + 180.0) / 360.0 * n))
    ytile = int(math.floor(
        (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
    ))
    return xtile, ytile


def num2deg(xtile: int, ytile: int, zoom: int) -> Tuple[float, float]:
    """Convert tile indices to lat/lon of the tile's NW corner."""
    n = 2.0 ** zoom
    lon_deg = xtile / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * ytile / n)))
    lat_deg = math.degrees(lat_rad)
    return lat_deg, lon_deg


def auto_zoom(min_lat: float, min_lon: float, max_lat: float, max_lon: float,
              target_pixels: int = 2048) -> int:
    """Pick a zoom level that covers the bbox in roughly target_pixels width."""
    lon_span = max_lon - min_lon
    if lon_span <= 0:
        return 18
    # At zoom z, the world is 256 * 2^z pixels wide, spanning 360 degrees
    # pixels_per_degree = 256 * 2^z / 360
    # We want: lon_span * pixels_per_degree ≈ target_pixels
    # → 2^z ≈ target_pixels * 360 / (256 * lon_span)
    z = math.log2(target_pixels * 360.0 / (TILE_SIZE * lon_span))
    z = max(10, min(19, int(round(z))))
    return z


def _fetch_single_tile(
    tx: int, ty: int, zoom: int,
    cache_dir: Optional[Path] = None,
    timeout: int = 15
) -> Optional[np.ndarray]:
    """Fetch a single tile, using cache if available. Returns H×W×3 RGB or None."""
    # Check cache
    if cache_dir:
        cache_file = cache_dir / str(zoom) / str(tx) / f"{ty}.png"
        if cache_file.exists():
            try:
                img_bgr = cv2.imread(str(cache_file))
                if img_bgr is not None:
                    return cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            except Exception:
                pass

    # Download
    url = ESRI_TILE_URL.format(z=zoom, y=ty, x=tx)
    try:
        req = urllib_request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib_request.urlopen(req, timeout=timeout) as response:
            data = response.read()
        img_np = np.frombuffer(data, dtype=np.uint8)
        img_bgr = cv2.imdecode(img_np, cv2.IMREAD_COLOR)
        if img_bgr is None:
            return None
        arr = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

        # Cache to disk
        if cache_dir:
            cache_file = cache_dir / str(zoom) / str(tx) / f"{ty}.png"
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(cache_file), img_bgr)

        return arr
    except Exception as e:
        logger.warning("Failed to fetch tile z=%d x=%d y=%d: %s", zoom, tx, ty, e)
        return None


def fetch_aerial_image(
    min_lat: float, min_lon: float,
    max_lat: float, max_lon: float,
    zoom: Optional[int] = None,
    cache_dir: Optional[Path] = None,
    margin_factor: float = 1.1,
) -> TileResult:
    """
    Fetch aerial imagery tiles for a geographic bounding box and stitch them.

    Args:
        min_lat, min_lon, max_lat, max_lon: Geographic bounding box (WGS84).
        zoom: Tile zoom level. If None, auto-selected based on extent.
        cache_dir: Directory for tile file cache. If None, no caching.
        margin_factor: Expand bbox by this factor (1.1 = 10% margin).

    Returns:
        TileResult with the stitched RGB image and exact geographic bbox.

    Raises:
        ValueError: If bbox is invalid or too many tiles would be needed.
    """
    if min_lat >= max_lat or min_lon >= max_lon:
        raise ValueError(
            f"Invalid bounding box: ({min_lon},{min_lat}) to ({max_lon},{max_lat})"
        )

    # Expand bbox by margin
    lat_center = (min_lat + max_lat) / 2
    lon_center = (min_lon + max_lon) / 2
    lat_half = (max_lat - min_lat) / 2 * margin_factor
    lon_half = (max_lon - min_lon) / 2 * margin_factor
    min_lat = lat_center - lat_half
    max_lat = lat_center + lat_half
    min_lon = lon_center - lon_half
    max_lon = lon_center + lon_half

    if zoom is None:
        zoom = auto_zoom(min_lat, min_lon, max_lat, max_lon)

    # Calculate tile range
    tx_min, ty_min = deg2num(max_lat, min_lon, zoom)  # NW corner
    tx_max, ty_max = deg2num(min_lat, max_lon, zoom)  # SE corner

    n_tiles_x = tx_max - tx_min + 1
    n_tiles_y = ty_max - ty_min + 1
    total_tiles = n_tiles_x * n_tiles_y

    if total_tiles > MAX_TILES:
        raise ValueError(
            f"Too many tiles ({total_tiles}) at zoom {zoom}. "
            f"Reduce zoom or bbox size (max {MAX_TILES})."
        )

    logger.info(
        "Fetching %d tiles (%dx%d) at zoom %d for bbox (%.4f,%.4f)-(%.4f,%.4f)",
        total_tiles, n_tiles_x, n_tiles_y, zoom,
        min_lon, min_lat, max_lon, max_lat,
    )

    # Stitch tiles into a single image
    img_width = n_tiles_x * TILE_SIZE
    img_height = n_tiles_y * TILE_SIZE
    stitched = np.full((img_height, img_width, 3), 200, dtype=np.uint8)  # Grey fallback

    fetched_count = 0
    for ty in range(ty_min, ty_max + 1):
        for tx in range(tx_min, tx_max + 1):
            tile_arr = _fetch_single_tile(tx, ty, zoom, cache_dir)
            if tile_arr is not None:
                row = (ty - ty_min) * TILE_SIZE
                col = (tx - tx_min) * TILE_SIZE
                h, w = tile_arr.shape[:2]
                stitched[row:row + h, col:col + w] = tile_arr[:, :, :3]
                fetched_count += 1

    # Compute exact geographic bounding box of the stitched image
    # NW corner of top-left tile
    nw_lat, nw_lon = num2deg(tx_min, ty_min, zoom)
    # SE corner of bottom-right tile (= NW corner of tile+1)
    se_lat, se_lon = num2deg(tx_max + 1, ty_max + 1, zoom)

    exact_bbox = (nw_lon, se_lat, se_lon, nw_lat)  # (min_lon, min_lat, max_lon, max_lat)

    logger.info(
        "Stitched %d/%d tiles into %dx%d image. Exact bbox: %s",
        fetched_count, total_tiles, img_width, img_height, exact_bbox,
    )

    return TileResult(
        image=stitched,
        geo_bbox=exact_bbox,
        zoom=zoom,
        tile_count=fetched_count,
    )

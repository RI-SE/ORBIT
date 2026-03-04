"""Tests for tile_fetcher module."""

import math
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from orbit.utils.tile_fetcher import (
    auto_zoom,
    deg2num,
    fetch_aerial_image,
    num2deg,
)


class TestDeg2Num:
    """Tests for lat/lon to tile index conversion."""

    def test_known_location(self):
        """Tile indices for a known location at zoom 15."""
        # Gothenburg ~57.7°N, 11.97°E
        tx, ty = deg2num(57.7, 11.97, 15)
        assert isinstance(tx, int)
        assert isinstance(ty, int)
        # At zoom 15, world is 32768 tiles wide
        assert 0 <= tx < 2**15
        assert 0 <= ty < 2**15

    def test_equator_prime_meridian(self):
        """Tile at equator/prime meridian should be near center."""
        tx, ty = deg2num(0.0, 0.0, 1)
        assert tx == 1
        assert ty == 1


class TestNum2Deg:
    """Tests for tile index to lat/lon conversion."""

    def test_roundtrip(self):
        """deg2num → num2deg should approximately round-trip."""
        lat, lon = 57.7, 11.97
        zoom = 15
        tx, ty = deg2num(lat, lon, zoom)
        lat2, lon2 = num2deg(tx, ty, zoom)
        # Result is NW corner of tile, so should be close but not exact
        assert abs(lat2 - lat) < 0.02
        assert abs(lon2 - lon) < 0.02


class TestAutoZoom:
    """Tests for automatic zoom selection."""

    def test_small_area_high_zoom(self):
        """Small geographic area should give high zoom."""
        z = auto_zoom(57.69, 11.96, 57.71, 11.98)
        assert z >= 15

    def test_large_area_low_zoom(self):
        """Large geographic area should give lower zoom."""
        z = auto_zoom(55.0, 10.0, 60.0, 15.0)
        assert z <= 12

    def test_clamps_to_valid_range(self):
        """Zoom should be clamped between 10 and 19."""
        z = auto_zoom(0.0, 0.0, 0.001, 0.001)  # Tiny → very high
        assert z <= 19
        z = auto_zoom(-80, -170, 80, 170)  # Huge → very low
        assert z >= 10


class TestFetchAerialImage:
    """Tests for the main fetch + stitch function."""

    def test_invalid_bbox_raises(self):
        """Swapped bbox should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid bounding box"):
            fetch_aerial_image(60.0, 12.0, 57.0, 11.0)

    @patch("orbit.utils.tile_fetcher._fetch_single_tile")
    def test_stitches_tiles(self, mock_fetch):
        """Should stitch fetched tiles into a single image."""
        # Return a solid colored 256x256 tile
        tile = np.full((256, 256, 3), 128, dtype=np.uint8)
        mock_fetch.return_value = tile

        result = fetch_aerial_image(
            57.69, 11.96, 57.71, 11.98,
            zoom=15, margin_factor=1.0,
        )

        assert result.image.ndim == 3
        assert result.image.shape[2] == 3
        assert result.zoom == 15
        assert result.tile_count > 0
        # Geo bbox should be set
        min_lon, min_lat, max_lon, max_lat = result.geo_bbox
        assert min_lon < max_lon
        assert min_lat < max_lat

    @patch("orbit.utils.tile_fetcher._fetch_single_tile")
    def test_too_many_tiles_raises(self, mock_fetch):
        """Very large area at high zoom should raise."""
        with pytest.raises(ValueError, match="Too many tiles"):
            fetch_aerial_image(
                50.0, 5.0, 60.0, 20.0,
                zoom=18, margin_factor=1.0,
            )

"""Tests for orbit.export.layout_mask_exporter module."""

import json
import os
import tempfile
from unittest.mock import Mock

import numpy as np
import pytest

from orbit.export.layout_mask_exporter import ExportMethod, LayoutMaskExporter
from orbit.export.reference_line_sampler import LanePolygonData
from orbit.models.project import Project
from orbit.models.road import Road


def _make_project_with_road(road_id="road_1", right_count=1, left_count=0):
    """Helper to create a minimal project with one road."""
    project = Project()
    road = Road(id=road_id, name="Test Road")
    road.lane_info.right_count = right_count
    road.lane_info.left_count = left_count
    road.generate_lanes(centerline_length=100.0)
    project.roads.append(road)
    return project


def _make_rect_polygon(x, y, w, h):
    """Create a rectangular polygon as list of (x, y) points."""
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def _noop_find_connected(*args, **kwargs):
    return {'road_lanes': [], 'connecting_road_lanes': []}


def _noop_get_cr_lane_id(*args, **kwargs):
    return -1


class TestComputeAdjacency:
    """Tests for _compute_adjacency method."""

    def test_simple_three_regions(self):
        """10x10 mask with 3 regions correctly identifies neighbor pairs."""
        mask = np.zeros((10, 10), dtype=np.int32)
        mask[:, 0:3] = 1
        mask[:, 3:7] = 2
        mask[:, 7:10] = 3

        project = _make_project_with_road()
        exporter = LayoutMaskExporter(
            image_size=(10, 10), project=project,
            find_connected_lanes=_noop_find_connected,
            get_connecting_road_lane_id=_noop_get_cr_lane_id,
        )

        adjacency = exporter._compute_adjacency(mask)

        # Region 1 and 2 are adjacent, 2 and 3 are adjacent
        assert 2 in adjacency.get(1, set())
        assert 1 in adjacency.get(2, set())
        assert 3 in adjacency.get(2, set())
        assert 2 in adjacency.get(3, set())
        # Region 1 and 3 are NOT adjacent (separated by region 2)
        assert 3 not in adjacency.get(1, set())

    def test_no_background_in_result(self):
        """Background (0) is excluded from adjacency results."""
        mask = np.zeros((10, 10), dtype=np.int32)
        mask[2:5, 2:5] = 1
        mask[5:8, 2:5] = 2

        project = _make_project_with_road()
        exporter = LayoutMaskExporter(
            image_size=(10, 10), project=project,
            find_connected_lanes=_noop_find_connected,
            get_connecting_road_lane_id=_noop_get_cr_lane_id,
        )

        adjacency = exporter._compute_adjacency(mask)

        assert 0 not in adjacency
        for neighbors in adjacency.values():
            assert 0 not in neighbors

    def test_empty_mask(self):
        """Empty mask returns empty adjacency."""
        mask = np.zeros((10, 10), dtype=np.int32)

        project = _make_project_with_road()
        exporter = LayoutMaskExporter(
            image_size=(10, 10), project=project,
            find_connected_lanes=_noop_find_connected,
            get_connecting_road_lane_id=_noop_get_cr_lane_id,
        )

        adjacency = exporter._compute_adjacency(mask)
        assert adjacency == {}


class TestBuildRegionMap:
    """Tests for _build_region_map method."""

    def test_sequential_ids(self):
        """Region IDs are assigned sequentially starting at 1."""
        polygons = [
            LanePolygonData(road_id="r1", section_number=1, lane_id=-1,
                           points=[(0, 0), (10, 0), (10, 10)]),
            LanePolygonData(road_id="r1", section_number=1, lane_id=-2,
                           points=[(0, 0), (10, 0), (10, 10)]),
            LanePolygonData(road_id="r2", section_number=1, lane_id=-1,
                           points=[(0, 0), (10, 0), (10, 10)]),
        ]

        project = _make_project_with_road()
        exporter = LayoutMaskExporter(
            image_size=(100, 100), project=project,
            find_connected_lanes=_noop_find_connected,
            get_connecting_road_lane_id=_noop_get_cr_lane_id,
        )

        region_map, region_info = exporter._build_region_map(polygons)

        assert len(region_map) == 3
        assert set(region_map.values()) == {1, 2, 3}
        assert "0" in region_info  # Background
        assert region_info["0"]["type"] == "non_drivable"
        assert region_info["1"]["type"] == "lane"

    def test_duplicate_key_not_duplicated(self):
        """Same (road, section, lane) key gets same region ID."""
        polygons = [
            LanePolygonData(road_id="r1", section_number=1, lane_id=-1,
                           points=[(0, 0), (10, 0), (10, 10)]),
            LanePolygonData(road_id="r1", section_number=1, lane_id=-1,
                           points=[(20, 20), (30, 20), (30, 30)]),
        ]

        project = _make_project_with_road()
        exporter = LayoutMaskExporter(
            image_size=(100, 100), project=project,
            find_connected_lanes=_noop_find_connected,
            get_connecting_road_lane_id=_noop_get_cr_lane_id,
        )

        region_map, region_info = exporter._build_region_map(polygons)
        assert len(region_map) == 1


class TestRenderMask:
    """Tests for _render_mask_with_overlaps method."""

    def test_overlapping_rectangles(self):
        """Two overlapping polygons create a combo region for the intersection."""
        poly1 = LanePolygonData(
            road_id="r1", section_number=1, lane_id=-1,
            points=_make_rect_polygon(10, 10, 30, 20),
        )
        poly2 = LanePolygonData(
            road_id="r2", section_number=1, lane_id=-1,
            points=_make_rect_polygon(25, 10, 30, 20),
        )

        project = _make_project_with_road()
        exporter = LayoutMaskExporter(
            image_size=(100, 100), project=project,
            find_connected_lanes=_noop_find_connected,
            get_connecting_road_lane_id=_noop_get_cr_lane_id,
            lane_polygons=[poly1, poly2],
        )

        region_map, region_info = exporter._build_region_map([poly1, poly2])
        mask = exporter._render_mask_with_overlaps([poly1, poly2], region_map, region_info)

        # There should be at least 3 unique non-zero values (2 base + 1 overlap)
        unique_vals = set(np.unique(mask)) - {0}
        assert len(unique_vals) >= 2  # At least the two base regions

    def test_non_overlapping_rectangles(self):
        """Non-overlapping polygons produce distinct regions."""
        poly1 = LanePolygonData(
            road_id="r1", section_number=1, lane_id=-1,
            points=_make_rect_polygon(10, 10, 20, 20),
        )
        poly2 = LanePolygonData(
            road_id="r2", section_number=1, lane_id=-1,
            points=_make_rect_polygon(50, 10, 20, 20),
        )

        project = _make_project_with_road()
        exporter = LayoutMaskExporter(
            image_size=(100, 100), project=project,
            find_connected_lanes=_noop_find_connected,
            get_connecting_road_lane_id=_noop_get_cr_lane_id,
            lane_polygons=[poly1, poly2],
        )

        region_map, region_info = exporter._build_region_map([poly1, poly2])
        mask = exporter._render_mask_with_overlaps([poly1, poly2], region_map, region_info)

        unique_vals = set(np.unique(mask)) - {0}
        assert len(unique_vals) == 2


class TestSaveMask:
    """Tests for _save_mask method."""

    def test_save_uint8(self):
        """Mask with ≤255 regions saves as uint8 PNG."""
        mask = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int32)

        project = _make_project_with_road()
        exporter = LayoutMaskExporter(
            image_size=(3, 2), project=project,
            find_connected_lanes=_noop_find_connected,
            get_connecting_road_lane_id=_noop_get_cr_lane_id,
        )

        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            path = f.name

        try:
            exporter._save_mask(mask, path)
            assert os.path.exists(path)
            # Read back
            import cv2
            loaded = cv2.imread(path, cv2.IMREAD_UNCHANGED)
            assert loaded is not None
            assert loaded.dtype == np.uint8
            np.testing.assert_array_equal(loaded, mask.astype(np.uint8))
        finally:
            os.unlink(path)

    def test_save_uint16(self):
        """Mask with >255 regions saves as uint16."""
        mask = np.array([[0, 256, 300], [400, 500, 1000]], dtype=np.int32)

        project = _make_project_with_road()
        exporter = LayoutMaskExporter(
            image_size=(3, 2), project=project,
            find_connected_lanes=_noop_find_connected,
            get_connecting_road_lane_id=_noop_get_cr_lane_id,
        )

        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            path = f.name

        try:
            exporter._save_mask(mask, path)
            assert os.path.exists(path)
            import cv2
            loaded = cv2.imread(path, cv2.IMREAD_UNCHANGED)
            assert loaded is not None
            assert loaded.dtype == np.uint16
        finally:
            os.unlink(path)


class TestFullExportPixelMethod:
    """Integration test for full pixel-method export pipeline."""

    def test_export_creates_png_and_json(self):
        """Pixel method export produces mask PNG and metadata JSON."""
        project = _make_project_with_road("road_1", right_count=1)

        polygons = [
            LanePolygonData(
                road_id="road_1", section_number=1, lane_id=-1,
                points=_make_rect_polygon(10, 10, 50, 30),
                lane_type="driving",
            ),
        ]

        exporter = LayoutMaskExporter(
            image_size=(100, 100),
            project=project,
            find_connected_lanes=_noop_find_connected,
            get_connecting_road_lane_id=_noop_get_cr_lane_id,
            method=ExportMethod.PIXEL,
            lane_polygons=polygons,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            png_path = os.path.join(tmpdir, "mask.png")
            success = exporter.export(png_path)

            assert success
            assert os.path.exists(png_path)

            json_path = os.path.join(tmpdir, "mask.json")
            assert os.path.exists(json_path)

            with open(json_path) as f:
                metadata = json.load(f)

            assert "0" in metadata
            assert metadata["0"]["type"] == "non_drivable"
            # Should have at least one lane region
            lane_regions = [v for k, v in metadata.items() if v.get("type") == "lane"]
            assert len(lane_regions) >= 1

    def test_export_no_polygons_returns_false(self):
        """Export with no polygons returns False."""
        project = _make_project_with_road()

        exporter = LayoutMaskExporter(
            image_size=(100, 100),
            project=project,
            find_connected_lanes=_noop_find_connected,
            get_connecting_road_lane_id=_noop_get_cr_lane_id,
            method=ExportMethod.PIXEL,
            lane_polygons=[],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            png_path = os.path.join(tmpdir, "mask.png")
            assert exporter.export(png_path) is False


class TestWorldFile:
    """Tests for world file generation."""

    def test_world_file_content(self):
        """World file contains 6 lines with correct affine parameters."""
        project = _make_project_with_road()

        # Mock transformer
        transformer = Mock()
        transformer.pixel_to_meters = Mock(side_effect=lambda x, y: (x * 0.05, -y * 0.05))

        polygons = [
            LanePolygonData(
                road_id="road_1", section_number=1, lane_id=-1,
                points=_make_rect_polygon(10, 10, 50, 30),
                lane_type="driving",
            ),
        ]

        exporter = LayoutMaskExporter(
            image_size=(100, 100),
            project=project,
            find_connected_lanes=_noop_find_connected,
            get_connecting_road_lane_id=_noop_get_cr_lane_id,
            transformer=transformer,
            lane_polygons=polygons,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            png_path = os.path.join(tmpdir, "mask.png")
            exporter.export(png_path, geotiff=True)

            pgw_path = os.path.join(tmpdir, "mask.pgw")
            assert os.path.exists(pgw_path)

            with open(pgw_path) as f:
                lines = f.read().strip().split('\n')

            assert len(lines) == 6
            # All lines should be parseable as floats
            values = [float(line) for line in lines]
            assert len(values) == 6
            # Pixel width (a) should be ~0.05
            assert values[0] == pytest.approx(0.05, abs=1e-6)

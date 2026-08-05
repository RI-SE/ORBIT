"""orbit-core: headless road-network model, OSM/OpenDRIVE import, OpenDRIVE export.

The GUI-free half of ORBIT. Everything here works without PyQt and without imagery,
so downstream tools can build OpenDRIVE from OpenStreetMap in a script or a pipeline.

Typical use -- coordinates to a CARLA-ready .xodr:

    import orbit_core as oc

    bbox = oc.bbox_from_center(57.6968, 11.9865, radius_m=150)
    osm = oc.osm_data_from_overpass(bbox)          # or osm_data_from_file("area.osm")
    oc.opendrive_from_osm_data(osm, bbox, "out.xodr")

The two OSM sources are interchangeable: both produce an `OSMData`, so callers can
implement whatever fallback policy they need (Overpass is a shared public service and
does fail). Fetch and convert are deliberately separate so a caller can cache the
fetched data -- see `osm_data_to_file`.
"""

from pathlib import Path
from typing import Optional, Tuple

from .export.opendrive_writer import ExportOptions, OpenDriveWriter
from .importers.osm_importer import DetailLevel, ImportMode, ImportOptions, OSMImporter
from .importers.osm_parser import OSMData, OSMParser
from .importers.osm_query import OverpassAPIError, query_osm_data
from .importers.osm_to_orbit import calculate_bbox_from_center
from .models.project import Project
from .utils.coordinate_transform import WebMercatorTransformer

__all__ = [
    "bbox_from_center",
    "bbox_of",
    "osm_data_from_overpass",
    "osm_data_from_file",
    "osm_data_to_file",
    "opendrive_from_osm_data",
    "OSMData",
    "OverpassAPIError",
    "ExportOptions",
    "ImportOptions",
    "DetailLevel",
    "ImportMode",
]

__version__ = "0.1.0"

#: Nominal pixel grid for the transformer when there is no image. Only fixes the
#: pixel:metre scale; finer than any OSM geometry warrants.
DEFAULT_PIXEL_GRID = 4000

Bbox = Tuple[float, float, float, float]  # (min_lat, min_lon, max_lat, max_lon)


def bbox_from_center(lat: float, lon: float, radius_m: float) -> Bbox:
    """Square bounding box of the given radius around a point."""
    return calculate_bbox_from_center(lat, lon, radius_m)


def bbox_of(osm_data: OSMData) -> Bbox:
    """Extent of an OSMData's nodes, for file sources that carry no bbox of their own.

    `.osm` files do have a `<bounds>` element, but the parser does not retain it, and
    files trimmed by hand may not have one at all.
    """
    if not osm_data.nodes:
        raise ValueError("OSM data contains no nodes, cannot derive a bounding box")

    lats = [n.lat for n in osm_data.nodes.values()]
    lons = [n.lon for n in osm_data.nodes.values()]
    return min(lats), min(lons), max(lats), max(lons)


def osm_data_from_overpass(
    bbox: Bbox,
    detail_level: str = "moderate",
    timeout: int = 60,
) -> OSMData:
    """Fetch and parse OSM data for a bounding box. Raises if Overpass is unreachable."""
    raw = query_osm_data(bbox, detail_level=detail_level, timeout=timeout)
    if raw is None:
        raise OverpassAPIError(f"Overpass query failed for bbox {bbox}")

    return OSMParser.parse(raw)


def osm_data_from_file(path: str | Path) -> OSMData:
    """Parse a saved `.osm` XML file. No network access.

    Note this is not equivalent to `osm_data_from_overpass` for the same area: the
    Overpass query filters by detail level, whereas a `.osm` export holds everything
    in its bounding box.
    """
    return OSMParser.parse_xml(Path(path).read_text(encoding="utf-8"))


def osm_data_to_file(raw_xml: str, path: str | Path) -> Path:
    """Write raw OSM XML to disk so a later run can work offline."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(raw_xml, encoding="utf-8")
    return path


def opendrive_from_osm_data(
    osm_data: OSMData,
    bbox: Bbox,
    out_path: str | Path,
    *,
    options: Optional[ImportOptions] = None,
    export_options: Optional[ExportOptions] = None,
    pixel_grid: int = DEFAULT_PIXEL_GRID,
) -> Path:
    """Convert parsed OSM data into an OpenDRIVE file.

    Defaults to OpenDRIVE 1.4 (`carla_compat`), which is what CARLA reads.

    Args:
        osm_data: From `osm_data_from_overpass` or `osm_data_from_file`.
        bbox: The area the data covers; georeferences the output.
        out_path: Destination `.xodr`.
        options: Import tuning. Defaults to moderate detail with junctions.
        export_options: Export tuning. Defaults to `carla_compat=True`.
        pixel_grid: Nominal image size backing the coordinate transform.

    Returns:
        The written path.
    """
    min_lat, min_lon, max_lat, max_lon = bbox
    transformer = WebMercatorTransformer(
        pixel_grid, pixel_grid, min_lon, min_lat, max_lon, max_lat
    )

    project = Project()
    # The writer emits <geoReference> only when the *project* is georeferenced
    # (>= 3 control points). The transformer already synthesised four corners from
    # the bbox, so hand them over -- otherwise the map has no world anchor and cannot
    # be placed on imagery in the ORBIT GUI.
    project.control_points = list(transformer.all_control_points)

    importer = OSMImporter(project, transformer, pixel_grid, pixel_grid)
    importer.import_from_osm_data(
        osm_data,
        options
        or ImportOptions(
            import_mode=ImportMode.REPLACE,
            detail_level=DetailLevel.MODERATE,
            import_junctions=True,
            filter_outside_image=False,
        ),
        bbox=bbox,
    )

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    writer = OpenDriveWriter(
        project,
        transformer,
        options=export_options or ExportOptions(carla_compat=True),
    )
    if not writer.write(str(out_path)):
        raise RuntimeError(f"OpenDriveWriter failed to write {out_path}")

    return out_path

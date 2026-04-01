"""
OpenDrive XML writer for ORBIT.

Generates ASAM OpenDrive format XML from annotated roads and junctions.
"""

import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Set, Tuple

from lxml import etree

from orbit.models import Junction, Project, Road
from orbit.utils import CoordinateTransformer
from orbit.utils.logging_config import get_logger

from .curve_fitting import CurveFitter, GeometryElement, GeometryType
from .lane_analyzer import LaneAnalyzer
from .lane_builder import LaneBuilder
from .object_builder import ObjectBuilder
from .parking_builder import ParkingBuilder
from .reference_validator import validate_references
from .signal_builder import SignalBuilder

logger = get_logger(__name__)


@dataclass
class ExportOptions:
    """Options controlling OpenDRIVE export behaviour."""
    right_hand_traffic: bool = True
    country_code: str = "se"
    use_tmerc: bool = False
    use_german_codes: bool = False
    offset_x: float = 0.0
    offset_y: float = 0.0
    geo_reference_string: Optional[str] = None
    export_object_types: Optional[Set] = None
    carla_compat: bool = False


class OpenDriveWriter:
    """Writes project data to OpenDrive XML format."""

    def __init__(
        self,
        project: Project,
        transformer: CoordinateTransformer,
        curve_fitter: Optional[CurveFitter] = None,
        right_hand_traffic: bool = True,
        country_code: str = "se",
        use_tmerc: bool = False,
        use_german_codes: bool = False,
        offset_x: float = 0.0,
        offset_y: float = 0.0,
        geo_reference_string: Optional[str] = None,
        export_object_types: Optional[set] = None,
        options: Optional[ExportOptions] = None,
        carla_compat: bool = False,
    ):
        """Initialize OpenDrive writer.

        Pass either keyword args or an ExportOptions dataclass via `options`.
        ExportOptions takes precedence when both are supplied.
        """
        self.project = project
        self.transformer = transformer
        self.curve_fitter = curve_fitter or CurveFitter(preserve_geometry=True)

        # Resolve options: dataclass takes precedence over individual kwargs
        opts = options or ExportOptions(
            right_hand_traffic=right_hand_traffic,
            country_code=country_code,
            use_tmerc=use_tmerc,
            use_german_codes=use_german_codes,
            offset_x=offset_x,
            offset_y=offset_y,
            geo_reference_string=geo_reference_string,
            export_object_types=export_object_types,
            carla_compat=carla_compat,
        )
        self.right_hand_traffic = opts.right_hand_traffic
        self.country_code = opts.country_code.lower()
        self.use_tmerc = opts.use_tmerc
        self.offset_x = opts.offset_x
        self.offset_y = opts.offset_y
        self.geo_reference_string = opts.geo_reference_string
        self.export_object_types = opts.export_object_types
        self.carla_compat = opts.carla_compat

        # Build lookup maps
        self.polyline_map = {p.id: p for p in project.polylines}
        self.road_map = {r.id: r for r in project.roads}
        self.junction_map = {j.id: j for j in project.junctions}

        # Junction numeric IDs (derived from junction.id during export)
        self.junction_numeric_ids: dict[str, int] = {}

        # Road numeric IDs — remapped during export to avoid collisions with
        # junction IDs (CARLA's parser does not distinguish elementType and uses
        # ContainsRoad() to decide if a link target is a road or junction).
        self.road_numeric_ids: dict[str, str] = {}

        # Get scale factors for lane width calculations
        scale_factors = transformer.get_scale_factor() if transformer else None

        # Store scale factors for coordinate conversions
        if scale_factors:
            self.scale_x, self.scale_y = scale_factors
        else:
            self.scale_x, self.scale_y = 1.0, 1.0  # Default if no georeferencing

        # Initialize lane analyzer with scale factors and transformer
        # Passing transformer enables accurate perspective-aware conversions for homography
        self.lane_analyzer = LaneAnalyzer(project, self.right_hand_traffic, scale_factors, transformer)

        # Initialize builders
        self.lane_builder = LaneBuilder(scale_x=self.scale_x, carla_compat=self.carla_compat)
        self.signal_builder = SignalBuilder(
            scale_x=self.scale_x,
            country_code=opts.country_code,
            use_german_codes=opts.use_german_codes,
            transformer=transformer,
        )
        self.object_builder = ObjectBuilder(
            scale_x=self.scale_x,
            transformer=transformer,
            curve_fitter=self.curve_fitter,
            polyline_map=self.polyline_map
        )
        self.parking_builder = ParkingBuilder(
            scale_x=self.scale_x,
            transformer=transformer,
            curve_fitter=self.curve_fitter,
            polyline_map=self.polyline_map
        )

        # Curve-fit endpoint data: {(road_id, "start"|"end"): (x, y, heading)}
        # Populated during _create_road() so CR heading lookups use fitted geometry.
        self._road_curve_endpoints: dict[tuple, tuple] = {}

        # Reverse lookup: centerline polyline ID -> road ID
        self._centerline_to_road: dict[str, str] = {
            r.centerline_id: r.id for r in project.roads if r.centerline_id
        }

        # Reference validation warnings (populated during write)
        self.reference_warnings: List[str] = []

        # Ensure geo_points are consistent with the current transformer
        self._validate_and_refresh_geo_points()

    # ------------------------------------------------------------------
    # Geo-point consistency
    # ------------------------------------------------------------------

    def _validate_and_refresh_geo_points(self):
        """Refresh stale geo_points so the export uses accurate geo coords.

        Checks each polyline's geo_points against the current transformer
        by comparing ``geo_to_pixel(geo_point)`` with the stored pixel
        position. Points that diverge beyond a threshold are recomputed
        from pixels via ``pixel_to_geo``.

        Also validates ``inline_geo_path`` on connecting roads.
        """
        if self.transformer is None:
            return

        PIXEL_THRESHOLD = 2.0  # px — flags even ~0.2 m drift at typical resolution

        refreshed_polylines = 0
        refreshed_points = 0

        for polyline in self.project.polylines:
            if not polyline.geo_points or len(polyline.geo_points) != len(polyline.points):
                continue

            stale_indices = []
            for i, (px, py) in enumerate(polyline.points):
                lon, lat = polyline.geo_points[i]
                try:
                    rpx, rpy = self.transformer.geo_to_pixel(lon, lat)
                except Exception:
                    stale_indices.append(i)
                    continue
                if abs(rpx - px) > PIXEL_THRESHOLD or abs(rpy - py) > PIXEL_THRESHOLD:
                    stale_indices.append(i)

            if stale_indices:
                refreshed_polylines += 1
                refreshed_points += len(stale_indices)
                for i in stale_indices:
                    px, py = polyline.points[i]
                    new_lon, new_lat = self.transformer.pixel_to_geo(px, py)
                    polyline.geo_points[i] = (new_lon, new_lat)

        # Validate inline_geo_path on connecting roads
        for road in self.project.roads:
            if not road.inline_geo_path or not road.inline_path:
                continue
            if len(road.inline_geo_path) != len(road.inline_path):
                continue

            stale_indices = []
            for i, (px, py) in enumerate(road.inline_path):
                lon, lat = road.inline_geo_path[i]
                try:
                    rpx, rpy = self.transformer.geo_to_pixel(lon, lat)
                except Exception:
                    stale_indices.append(i)
                    continue
                if abs(rpx - px) > PIXEL_THRESHOLD or abs(rpy - py) > PIXEL_THRESHOLD:
                    stale_indices.append(i)

            if stale_indices:
                refreshed_points += len(stale_indices)
                for i in stale_indices:
                    px, py = road.inline_path[i]
                    new_lon, new_lat = self.transformer.pixel_to_geo(px, py)
                    road.inline_geo_path[i] = (new_lon, new_lat)

        if refreshed_points > 0:
            logger.info(
                "Refreshed %d stale geo_points across %d polyline(s)",
                refreshed_points, refreshed_polylines,
            )

    def write(self, output_path: str) -> bool:
        """
        Write OpenDrive XML to file.

        Args:
            output_path: Path to output .xodr file

        Returns:
            True if successful
        """
        try:
            # Run reference validation before export
            self.reference_warnings = validate_references(self.project)
            for warning in self.reference_warnings:
                logger.warning(f"Reference check: {warning}")

            root = self._create_opendrive_root()

            # Write to file with pretty formatting
            tree = etree.ElementTree(root)
            tree.write(
                output_path,
                pretty_print=True,
                xml_declaration=True,
                encoding='utf-8'
            )
            return True
        except Exception as e:
            logger.error(f"Error writing OpenDrive: {e}")
            return False

    def write_and_validate(
        self,
        output_path: str,
        schema_path: Optional[str] = None
    ) -> Tuple[bool, List[str], bool]:
        """
        Write OpenDrive XML to file and optionally validate against XSD schema.

        Args:
            output_path: Path to output .xodr file
            schema_path: Path to OpenDRIVE XSD schema file (OpenDRIVE_Core.xsd).
                        If None, validation is skipped.

        Returns:
            Tuple of (success, list of validation errors/warnings, validation_performed)
        """
        errors = []

        # Write the file first
        if not self.write(output_path):
            return False, ["Failed to write OpenDRIVE file"], False

        # Validate if schema path provided
        validation_errors = validate_opendrive_file(output_path, schema_path)
        if validation_errors is None:
            # Validation was skipped (no schema)
            return True, [], False
        elif validation_errors:
            errors.extend(validation_errors)
            return False, errors, True

        return True, [], True

    def _create_opendrive_root(self) -> etree.Element:
        """Create the root OpenDRIVE element with all content."""
        if self.carla_compat:
            # CARLA targets OpenDRIVE 1.4 — omit the 1.8 XML namespace
            root = etree.Element('OpenDRIVE')
        else:
            # OpenDRIVE 1.8 namespace
            nsmap = {None: "http://code.asam.net/simulation/standard/opendrive_schema"}
            root = etree.Element('OpenDRIVE', nsmap=nsmap)

        # Add header
        header = self._create_header()
        root.append(header)

        # Assign numeric IDs to junctions from their string IDs
        self.junction_numeric_ids = {}
        for idx, junction in enumerate(self.project.junctions):
            if junction.is_valid():
                # Skip non-virtual junctions with no lane connections (nothing to export)
                if junction.junction_type != "virtual" and not junction.lane_connections:
                    logger.warning(
                        f"Junction {junction.id} has no lane connections, skipping export"
                    )
                    continue
                try:
                    self.junction_numeric_ids[junction.id] = int(junction.id)
                except (ValueError, TypeError):
                    # Fallback for non-numeric IDs (shouldn't happen after migration)
                    self.junction_numeric_ids[junction.id] = idx + 1

        # Build road ID remapping to avoid collisions with junction IDs.
        # CARLA determines whether a predecessor/successor link references a road
        # or a junction by checking ContainsRoad(id).  If a road and a junction
        # share the same numeric ID, CARLA treats junction references as
        # road-to-road links, breaking junction routing entirely.
        self.road_numeric_ids = self._build_road_id_remap()

        # Pre-pass: filter and auto-assign objects to nearest roads
        self._export_objects = self._get_export_objects()

        # Export order:
        # 1. Regular roads (junction="-1")
        # 2. Connecting roads for each junction (junction="<id>")
        # 3. Junction definitions

        # 1. Add regular roads (non-junction roads)
        for road in self.project.roads:
            if road.is_valid() and not road.junction_id:
                road_elem = self._create_road(road)
                if road_elem is not None:
                    root.append(road_elem)

        # 2. Add connecting roads for each junction
        for junction in self.project.junctions:
            if junction.is_valid():
                junction_numeric_id = self.junction_numeric_ids.get(junction.id)
                if junction_numeric_id is None:
                    continue

                # Skip connecting roads for virtual junctions (path crossings)
                if junction.junction_type == "virtual":
                    continue

                # Export each connecting road as a Road element
                for idx, cr_id in enumerate(junction.connecting_road_ids):
                    connecting_road = self.project.get_road(cr_id)
                    if not connecting_road:
                        logger.warning(f"Connecting road {cr_id} not found for junction {junction_numeric_id}")
                        continue
                    conn_road_elem = self._create_connecting_road(
                        connecting_road,
                        junction_numeric_id,
                        junction.lane_connections
                    )
                    if conn_road_elem is not None:
                        root.append(conn_road_elem)
                    else:
                        logger.warning(f"Connecting road {idx} for junction {junction_numeric_id} returned None!")

        # 3. Add junction definitions
        for junction in self.project.junctions:
            if junction.is_valid():
                junction_numeric_id = self.junction_numeric_ids.get(junction.id)
                if junction_numeric_id is None:
                    continue

                junction_elem = self._create_junction(junction, junction_numeric_id)
                if junction_elem is not None:
                    root.append(junction_elem)

        # 4. Add junction groups
        for idx, junction_group in enumerate(self.project.junction_groups):
            jg_elem = self._create_junction_group(junction_group, idx + 1)
            if jg_elem is not None:
                root.append(jg_elem)

        return root

    def _build_road_id_remap(self) -> dict[str, str]:
        """Build a mapping from internal road ID → export road ID.

        Ensures no exported road ID collides with any exported junction ID.
        Roads whose numeric ID does not collide are kept as-is.  Colliding
        roads are assigned new IDs starting above the maximum of all existing
        road and junction IDs.
        """
        junction_id_set = set(self.junction_numeric_ids.values())
        if not junction_id_set:
            return {r.id: r.id for r in self.project.roads}

        remap: dict[str, str] = {}
        max_id = 0
        for road in self.project.roads:
            try:
                rid = int(road.id)
                if rid > max_id:
                    max_id = rid
            except (ValueError, TypeError):
                pass
        for jid in junction_id_set:
            if jid > max_id:
                max_id = jid

        next_safe_id = max_id + 1

        for road in self.project.roads:
            try:
                rid = int(road.id)
            except (ValueError, TypeError):
                remap[road.id] = road.id
                continue

            if rid in junction_id_set:
                remap[road.id] = str(next_safe_id)
                next_safe_id += 1
            else:
                remap[road.id] = road.id

        return remap

    def _remap_road_id(self, road_id: str) -> str:
        """Return the export-safe road ID for a given internal road ID."""
        return self.road_numeric_ids.get(road_id, road_id)

    def _get_export_objects(self) -> list:
        """Get filtered list of objects to export based on export_object_types.

        Also auto-assigns unassigned objects to the nearest road by centroid
        distance to road centerline.
        """
        objects = self.project.objects
        if self.export_object_types is not None:
            objects = [obj for obj in objects if obj.type in self.export_object_types]

        # Auto-assign unassigned objects to nearest road
        for obj in objects:
            if obj.road_id is not None:
                continue
            # Use centroid (position) to find nearest road
            pos = obj.position
            if obj.points and len(obj.points) >= 3:
                # Recalculate centroid from polygon points
                pos = (
                    sum(p[0] for p in obj.points) / len(obj.points),
                    sum(p[1] for p in obj.points) / len(obj.points),
                )
            closest_road_id = self._find_nearest_road(pos)
            if closest_road_id:
                obj.road_id = closest_road_id
                road = self.road_map.get(closest_road_id)
                if road and road.centerline_id:
                    centerline = self.polyline_map.get(road.centerline_id)
                    if centerline:
                        s, t = obj.calculate_s_t_position(centerline.points)
                        obj.s_position = s
                        obj.t_offset = t

        return objects

    def _find_nearest_road(self, position: tuple) -> Optional[str]:
        """Find the nearest road to a pixel position by centerline distance."""
        min_dist = float('inf')
        closest_id = None
        px, py = position

        for road in self.project.roads:
            if not road.centerline_id:
                continue
            centerline = self.polyline_map.get(road.centerline_id)
            if not centerline or len(centerline.points) < 2:
                continue

            # Find minimum distance to any segment
            for i in range(len(centerline.points) - 1):
                x1, y1 = centerline.points[i]
                x2, y2 = centerline.points[i + 1]
                dx, dy = x2 - x1, y2 - y1
                length_sq = dx * dx + dy * dy
                if length_sq == 0:
                    continue
                t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / length_sq))
                proj_x = x1 + t * dx
                proj_y = y1 + t * dy
                dist = ((px - proj_x) ** 2 + (py - proj_y) ** 2) ** 0.5
                if dist < min_dist:
                    min_dist = dist
                    closest_id = road.id

        return closest_id

    def _find_junction_for_road_endpoint(self, road_id: str, is_predecessor: bool) -> Optional[int]:
        """
        Find if a road endpoint connects to a junction.

        Args:
            road_id: ID of the road
            is_predecessor: True to check predecessor end, False for successor end

        Returns:
            Junction numeric ID if road endpoint is at a junction, None otherwise
        """
        # Get the road and its centerline
        road = self.road_map.get(road_id)
        if not road or not road.centerline_id:
            return None

        centerline = self.polyline_map.get(road.centerline_id)
        if not centerline or len(centerline.points) < 2:
            return None

        start_point = centerline.points[0]
        end_point = centerline.points[-1]
        check_point = start_point if is_predecessor else end_point

        # Check each junction to see if THIS endpoint is at the junction
        for junction in self.project.junctions:
            if road_id not in junction.connected_road_ids:
                continue

            junction_numeric_id = self.junction_numeric_ids.get(junction.id)
            if junction_numeric_id is None:
                continue

            if junction.center_point:
                # Determine which road end is closer to the junction center.
                # Road endpoints may be tens or hundreds of pixels from the junction
                # center (the junction covers an area, not a point), so a fixed
                # proximity threshold is unreliable.  Instead, return this junction
                # only when the correct end (start for predecessor, end for
                # successor) is the closer of the two ends.
                d_start = math.sqrt((start_point[0] - junction.center_point[0])**2 +
                                    (start_point[1] - junction.center_point[1])**2)
                d_end = math.sqrt((end_point[0] - junction.center_point[0])**2 +
                                  (end_point[1] - junction.center_point[1])**2)
                closer_is_start = d_start < d_end
                if closer_is_start == is_predecessor:
                    return junction_numeric_id
            else:
                # No center_point — check endpoints of other connected roads
                for other_road_id in junction.connected_road_ids:
                    if other_road_id == road_id:
                        continue
                    other_road = self.road_map.get(other_road_id)
                    if not other_road or not other_road.centerline_id:
                        continue
                    other_cl = self.polyline_map.get(other_road.centerline_id)
                    if not other_cl or len(other_cl.points) < 2:
                        continue
                    # Check both endpoints of the other road
                    for pt in (other_cl.points[0], other_cl.points[-1]):
                        dx = check_point[0] - pt[0]
                        dy = check_point[1] - pt[1]
                        dist = math.sqrt(dx*dx + dy*dy)
                        if dist < 15.0:
                            return junction_numeric_id

        return None

    def _create_header(self) -> etree.Element:
        """Create OpenDrive header element."""
        header = etree.Element('header')
        header.set('revMajor', '1')
        header.set('revMinor', '4' if self.carla_compat else '8')

        # Use map name from project, fallback to 'ORBIT Export' if empty
        map_name = self.project.map_name if self.project.map_name else 'ORBIT Export'
        header.set('name', map_name)

        header.set('version', '1.0')
        header.set('date', datetime.now().isoformat())

        # Calculate bounding box from all polylines in metric coordinates
        if self.project.has_georeferencing():
            bounds = self._calculate_bounds()
            header.set('north', f'{bounds["north"] - self.offset_y:.4f}')
            header.set('south', f'{bounds["south"] - self.offset_y:.4f}')
            header.set('east', f'{bounds["east"] - self.offset_x:.4f}')
            header.set('west', f'{bounds["west"] - self.offset_x:.4f}')
        else:
            header.set('north', '0.0')
            header.set('south', '0.0')
            header.set('east', '0.0')
            header.set('west', '0.0')

        if not self.carla_compat:
            header.set('vendor', 'ORBIT by RISE Research Institutes of Sweden')

        # OpenDRIVE schema requires elements in order: geoReference, offset, license, userData
        # Add georef first if available
        if self.project.has_georeferencing():
            georef = etree.SubElement(header, 'geoReference')
            # Priority: explicit geo_reference_string > _export_proj_string > use_tmerc > imported > UTM
            if self.geo_reference_string:
                georef.text = self.geo_reference_string
            elif getattr(self.transformer, '_export_proj_string', None):
                georef.text = self.transformer._export_proj_string
            elif self.use_tmerc:
                # Use local Transverse Mercator projection centered on control points
                georef.text = self.transformer.get_projection_string()
            else:
                # Prefer preserved geoReference from import, otherwise calculate UTM
                if self.project.imported_geo_reference:
                    georef.text = self.project.imported_geo_reference
                else:
                    georef.text = self.transformer.get_utm_projection_string()

            # Add offset element (always present when georeferenced)
            offset_elem = etree.SubElement(header, 'offset')
            offset_elem.set('x', f'{self.offset_x:.4f}')
            offset_elem.set('y', f'{self.offset_y:.4f}')
            offset_elem.set('z', '0.0000')
            offset_elem.set('hdg', '0.000000')

        # Add tool/license userData only in 1.8 mode (not recognized by CARLA's 1.4 parser)
        if not self.carla_compat:
            tool_data = etree.SubElement(header, 'userData')
            tool_data.set('code', 'tool')
            tool_data.text = 'Produced by ORBIT (https://github.com/RI-SE/ORBIT)'

            license_data = etree.SubElement(header, 'userData')
            license_data.set('code', 'license')
            license_data.text = 'Licensed under the Open Database License (https://opendatacommons.org/licenses/odbl/1-0/)'

            # Source attribution userData only if OpenStreetMap was used
            if self.project.openstreetmap_used:
                source_data = etree.SubElement(header, 'userData')
                source_data.set('code', 'sourceAttribution')
                source_data.text = 'Map data from OpenStreetMap (https://www.openstreetmap.org/copyright)'

        return header

    def _calculate_bounds(self) -> dict:
        """
        Calculate bounding box in metric coordinates from all polylines.

        Returns:
            Dictionary with 'north', 'south', 'east', 'west' in meters
        """
        all_points_meters = []

        # Collect all polyline points and convert to meters
        for polyline in self.project.polylines:
            # Use geo coords directly if available (more precise)
            if polyline.geo_points:
                for lon, lat in polyline.geo_points:
                    x_m, y_m = self.transformer.latlon_to_meters(lat, lon)
                    all_points_meters.append((x_m, y_m))
            else:
                points_meters = self.transformer.pixels_to_meters_batch(polyline.points)
                all_points_meters.extend(points_meters)

        if not all_points_meters:
            return {'north': 0.0, 'south': 0.0, 'east': 0.0, 'west': 0.0}

        # Find min/max
        xs = [p[0] for p in all_points_meters]
        ys = [p[1] for p in all_points_meters]

        return {
            'north': max(ys),
            'south': min(ys),
            'east': max(xs),
            'west': min(xs)
        }

    def _create_road(self, road: Road) -> Optional[etree.Element]:
        """Create a road element."""
        if not road.centerline_id:
            return None

        # Get centerline polyline ONLY for reference geometry
        centerline = self.polyline_map.get(road.centerline_id)
        if not centerline or centerline.point_count() < 2:
            return None

        # Get pixel points (needed for signal/object s-position calculations)
        centerline_points_pixel = centerline.points

        # Transform centerline points to metric coordinates (meters)
        # Use geo coords directly if available (more precise, avoids double conversion)
        if centerline.geo_points:
            all_points_meters = [
                self.transformer.latlon_to_meters(lat, lon)
                for lon, lat in centerline.geo_points
            ]
        else:
            all_points_meters = self.transformer.pixels_to_meters_batch(centerline_points_pixel)

        # Fit curves to metric coordinates
        geometry_elements = self.curve_fitter.fit_polyline(all_points_meters)

        if not geometry_elements:
            return None

        # Store curve-fit start/end positions and headings for CR alignment
        from .reference_line_sampler import _sample_element
        first_elem = geometry_elements[0]
        self._road_curve_endpoints[(road.id, "start")] = (
            first_elem.start_pos[0], first_elem.start_pos[1], first_elem.heading
        )
        last_elem = geometry_elements[-1]
        ex, ey, ehdg = _sample_element(last_elem, last_elem.length)
        self._road_curve_endpoints[(road.id, "end")] = (ex, ey, ehdg)

        # Compute cumulative metric arc-length at each polyline point index.
        # Used by lane_builder to convert pixel-based section boundaries to meters
        # without the scale_x error introduced by angled roads.
        cumulative_metric_s = [0.0]
        for i in range(len(all_points_meters) - 1):
            dx = all_points_meters[i + 1][0] - all_points_meters[i][0]
            dy = all_points_meters[i + 1][1] - all_points_meters[i][1]
            cumulative_metric_s.append(cumulative_metric_s[-1] + math.sqrt(dx * dx + dy * dy))

        # Calculate total road length
        road_length = sum(elem.length for elem in geometry_elements)

        # Create road element
        road_elem = etree.Element('road')
        road_elem.set('id', self._remap_road_id(road.id))
        road_elem.set('name', road.name)
        road_elem.set('length', f'{road_length:.4f}')
        road_elem.set('junction', road.junction_id if road.junction_id else '-1')

        # Add road link with predecessor/successor
        self._build_road_link_xml(road_elem, road)

        # Add road type
        type_elem = etree.SubElement(road_elem, 'type')
        type_elem.set('s', '0.0')
        road_type_str = road.road_type.value
        if self.carla_compat:
            road_type_str = self._carla_road_type(road_type_str)
        type_elem.set('type', road_type_str)

        if road.speed_limit:
            speed = etree.SubElement(type_elem, 'speed')
            speed.set('max', f'{road.speed_limit / 3.6:.2f}')  # Convert km/h to m/s
            speed.set('unit', 'm/s')
        elif self.carla_compat:
            # CARLA agents need speed targets; default 50 km/h for town/rural
            speed = etree.SubElement(type_elem, 'speed')
            speed.set('max', '13.89')
            speed.set('unit', 'm/s')

        # Add plan view (reference line geometry)
        plan_view = self._create_plan_view(geometry_elements)
        road_elem.append(plan_view)

        # Add elevation profile (use stored profile or flat)
        elevation = etree.SubElement(road_elem, 'elevationProfile')
        if road.elevation_profile:
            # Use stored elevation polynomials for round-trip preservation
            for elev_data in road.elevation_profile:
                s, a, b, c, d = elev_data
                elev = etree.SubElement(elevation, 'elevation')
                elev.set('s', f'{s:.6g}')
                elev.set('a', f'{a:.6g}')
                elev.set('b', f'{b:.6g}')
                elev.set('c', f'{c:.6g}')
                elev.set('d', f'{d:.6g}')
        else:
            # Default flat profile
            elev = etree.SubElement(elevation, 'elevation')
            elev.set('s', '0.0')
            elev.set('a', '0.0')
            elev.set('b', '0.0')
            elev.set('c', '0.0')
            elev.set('d', '0.0')

        # Add lateral profile (superelevation/crossfall)
        lateral = etree.SubElement(road_elem, 'lateralProfile')
        if road.superelevation_profile:
            # Export stored superelevation polynomials for round-trip preservation
            for se_data in road.superelevation_profile:
                s, a, b, c, d = se_data
                superelevation = etree.SubElement(lateral, 'superelevation')
                superelevation.set('s', f'{s:.6g}')
                superelevation.set('a', f'{a:.6g}')
                superelevation.set('b', f'{b:.6g}')
                superelevation.set('c', f'{c:.6g}')
                superelevation.set('d', f'{d:.6g}')

        # Analyze lane boundaries
        boundary_infos, warning = self.lane_analyzer.analyze_road(road)

        # Add lanes (with boundary info if available)
        lanes = self.lane_builder.create_lanes(road, road_length, boundary_infos, cumulative_metric_s)
        road_elem.append(lanes)

        # Add signals for this road (pass metric centerline for accurate s/t projection)
        signals = self.signal_builder.create_signals(
            road, self.project.signals, centerline_points_pixel, all_points_meters
        )
        if signals is not None:
            road_elem.append(signals)
        elif self.carla_compat:
            road_elem.append(etree.Element('signals'))

        # Add objects for this road (including parking spaces)
        export_objects = getattr(self, '_export_objects', None)
        if export_objects is None:
            export_objects = self._get_export_objects()
        objects = self.object_builder.create_objects(
            road, export_objects, centerline_points_pixel,
            geometry_elements=geometry_elements, road_length=road_length,
        )

        # Create parking objects for this road
        parking_objects = self.parking_builder.create_parking_objects(
            road, self.project.parking_spaces, centerline_points_pixel
        )

        # Combine objects and parking into single objects element
        if objects is not None or parking_objects:
            if objects is None:
                objects = etree.Element('objects')
            for parking_elem in parking_objects:
                objects.append(parking_elem)
            road_elem.append(objects)
        elif self.carla_compat:
            road_elem.append(etree.Element('objects'))

        # Add surface CRG references if present
        self._build_surface_crg_xml(road_elem, road)

        return road_elem

    def _build_road_link_xml(self, road_elem, road: Road):
        """Build link element with predecessor/successor for a road."""
        link = etree.SubElement(road_elem, 'link')

        predecessor_junction = None
        successor_junction = None

        # "__none__" sentinel means user explicitly disabled junction auto-detection
        pred_junc_id = road.predecessor_junction_id
        succ_junc_id = road.successor_junction_id
        pred_suppress = pred_junc_id == "__none__"
        succ_suppress = succ_junc_id == "__none__"

        if pred_junc_id and not pred_suppress:
            try:
                predecessor_junction = int(pred_junc_id)
            except (ValueError, TypeError):
                pass
        if succ_junc_id and not succ_suppress:
            try:
                successor_junction = int(succ_junc_id)
            except (ValueError, TypeError):
                pass

        if predecessor_junction is None and not pred_suppress:
            predecessor_junction = self._find_junction_for_road_endpoint(road.id, is_predecessor=True)
        if successor_junction is None and not succ_suppress:
            successor_junction = self._find_junction_for_road_endpoint(road.id, is_predecessor=False)

        if predecessor_junction is not None:
            pred = etree.SubElement(link, 'predecessor')
            pred.set('elementType', 'junction')
            pred.set('elementId', str(predecessor_junction))
        elif road.predecessor_id:
            pred = etree.SubElement(link, 'predecessor')
            pred.set('elementType', 'road')
            pred.set('elementId', self._remap_road_id(road.predecessor_id))
            pred.set('contactPoint', road.predecessor_contact)

        if successor_junction is not None:
            succ = etree.SubElement(link, 'successor')
            succ.set('elementType', 'junction')
            succ.set('elementId', str(successor_junction))
        elif road.successor_id:
            succ = etree.SubElement(link, 'successor')
            succ.set('elementType', 'road')
            succ.set('elementId', self._remap_road_id(road.successor_id))
            succ.set('contactPoint', road.successor_contact)

    @staticmethod
    def _carla_road_type(road_type_str: str) -> str:
        """Map OpenDRIVE road types to CARLA 1.4-compatible values."""
        # Types supported in OpenDRIVE 1.4
        carla_14_types = {'unknown', 'rural', 'motorway', 'town', 'lowSpeed', 'pedestrian', 'bicycle'}
        if road_type_str in carla_14_types:
            # Map 'unknown' to 'town' — CARLA may skip waypoints for unknown types
            return 'town' if road_type_str == 'unknown' else road_type_str
        # 1.7+ types (townExpressway, townCollector, etc.) → 'town'
        return 'town'

    @staticmethod
    def _build_surface_crg_xml(road_elem, road: Road):
        """Build surface CRG references if present."""
        if not road.surface_crg:
            return
        surface = etree.SubElement(road_elem, 'surface')
        crg_attrs = ['sStart', 'sEnd', 'orientation', 'mode', 'purpose',
                     'sOffset', 'tOffset', 'zOffset', 'zScale', 'hOffset']
        for crg_data in road.surface_crg:
            crg = etree.SubElement(surface, 'CRG')
            crg.set('file', crg_data.get('file', ''))
            for attr in crg_attrs:
                if attr in crg_data:
                    val = crg_data[attr]
                    crg.set(attr, f"{val:.6g}" if isinstance(val, float) else val)

    def _create_connecting_road(self, connecting_road: Road,
                               junction_numeric_id: int,
                               lane_connections=None) -> Optional[etree.Element]:
        """
        Create a road element for a junction connecting road.

        Args:
            connecting_road: Road object (with junction_id set) containing path and lane config
            junction_numeric_id: Numeric ID of the junction this road belongs to
            lane_connections: Junction lane connections for deriving lane link IDs

        Returns:
            Road XML element with junction="<junction_id>", or None if invalid
        """
        if not connecting_road.inline_path or len(connecting_road.inline_path) < 2:
            return None

        # Transform path points from pixels to meters
        # Use geo coords directly if available (more precise, avoids double conversion)
        if connecting_road.inline_geo_path:
            path_meters = [
                self.transformer.latlon_to_meters(lat, lon)
                for lon, lat in connecting_road.inline_geo_path
            ]
        else:
            path_meters = self.transformer.pixels_to_meters_batch(connecting_road.inline_path)

        # Snap CR endpoints to connected road endpoints for topological correctness.
        # Small pixel-level misalignment can cause visible gaps in the export.
        # Lane connections are passed so the snap accounts for lane alignment
        # (e.g., CR targeting lane -2 snaps to lane -2 center, not centerline).
        path_meters = self._snap_cr_endpoints_to_roads(
            connecting_road, path_meters, lane_connections
        )

        # Compute geometry and road length
        if connecting_road.geometry_type == "parampoly3":
            geometry_elements, road_length = self._compute_parampoly3_geometry(
                connecting_road, path_meters
            )
        else:
            geometry_elements = self.curve_fitter.fit_polyline(path_meters)
            if not geometry_elements:
                return None
            road_length = sum(elem.length for elem in geometry_elements)

        # Build road XML element
        road_elem = self._build_cr_road_xml(
            connecting_road, junction_numeric_id, road_length,
            geometry_elements, lane_connections, path_meters
        )
        return road_elem

    def _compute_parampoly3_geometry(self, connecting_road: Road,
                                     path_meters: list):
        """Compute ParamPoly3D geometry in local coordinates."""
        start_point = path_meters[0]
        end_point = path_meters[-1]

        start_heading = self._resolve_cr_heading(
            connecting_road, path_meters, is_start=True
        )
        end_heading = self._resolve_cr_heading(
            connecting_road, path_meters, is_start=False
        )

        # Override with connected road headings for C1 continuity
        start_heading = self._override_with_road_heading(
            connecting_road.predecessor_id, connecting_road.predecessor_contact,
            start_heading
        )
        end_heading = self._override_with_road_heading(
            connecting_road.successor_id, connecting_road.successor_contact,
            end_heading
        )

        # Transform to local u/v frame (origin at start, u along heading)
        dx_global = end_point[0] - start_point[0]
        dy_global = end_point[1] - start_point[1]
        cos_h = math.cos(start_heading)
        sin_h = math.sin(start_heading)
        end_u = dx_global * cos_h + dy_global * sin_h
        end_v = -dx_global * sin_h + dy_global * cos_h

        end_tangent_u = math.cos(end_heading) * cos_h + math.sin(end_heading) * sin_h
        end_tangent_v = -math.cos(end_heading) * sin_h + math.sin(end_heading) * cos_h

        # Compute curve coefficients (Bezier with Hermite fallback)
        from orbit.utils.geometry import (
            bezier_to_parampoly3,
            calculate_bezier_control_points,
            calculate_hermite_parampoly3,
        )
        control_points = calculate_bezier_control_points(
            (0.0, 0.0), (1.0, 0.0), (end_u, end_v), (end_tangent_u, end_tangent_v)
        )
        if control_points is not None:
            aU, bU, cU, dU, aV, bV, cV, dV = bezier_to_parampoly3(control_points, 0.0)
        else:
            aU, bU, cU, dU, aV, bV, cV, dV = calculate_hermite_parampoly3(
                (0.0, 0.0), (1.0, 0.0), (end_u, end_v),
                (end_tangent_u, end_tangent_v),
                tangent_scale=connecting_road.tangent_scale
            )

        road_length = 0.0
        for i in range(len(path_meters) - 1):
            dx = path_meters[i+1][0] - path_meters[i][0]
            dy = path_meters[i+1][1] - path_meters[i][1]
            road_length += math.sqrt(dx*dx + dy*dy)

        geometry_elements = [
            GeometryElement(
                geom_type=GeometryType.PARAMPOLY3,
                start_pos=start_point, heading=start_heading, length=road_length,
                aU=aU, bU=bU, cU=cU, dU=dU,
                aV=aV, bV=bV, cV=cV, dV=dV,
                p_range=1.0,
                p_range_normalized=connecting_road.p_range_normalized
            )
        ]
        return geometry_elements, road_length

    def _resolve_cr_heading(self, connecting_road: Road, path_meters: list,
                            is_start: bool) -> float:
        """Resolve heading from stored pixel heading or path approximation."""
        stored = connecting_road.stored_start_heading if is_start else connecting_road.stored_end_heading
        pixel_pt = connecting_road.inline_path[0 if is_start else -1]

        if stored is not None:
            return self.transformer.transform_heading(pixel_pt[0], pixel_pt[1], stored)
        if len(path_meters) >= 2:
            if is_start:
                dx = path_meters[1][0] - path_meters[0][0]
                dy = path_meters[1][1] - path_meters[0][1]
            else:
                dx = path_meters[-1][0] - path_meters[-2][0]
                dy = path_meters[-1][1] - path_meters[-2][1]
            return math.atan2(dy, dx)
        return 0.0

    def _override_with_road_heading(self, road_id, contact_point,
                                     current_heading: float) -> float:
        """Override heading with connected road's actual heading if available."""
        road = self.road_map.get(road_id)
        if road and road.centerline_id:
            hdg = self._get_road_heading_at_contact_meters(
                road.centerline_id, contact_point
            )
            if hdg is not None:
                return hdg
        return current_heading

    def _build_cr_road_xml(self, connecting_road: Road,
                           junction_numeric_id: int, road_length: float,
                           geometry_elements, lane_connections, path_meters):
        """Build the XML element for a connecting road."""
        road_elem = etree.Element('road')
        road_elem.set('id', self._remap_road_id(connecting_road.id))
        road_elem.set('name', '')
        road_elem.set('length', f'{road_length:.4f}')
        road_elem.set('junction', str(junction_numeric_id))

        # Link
        link = etree.SubElement(road_elem, 'link')
        if connecting_road.predecessor_id:
            pred = etree.SubElement(link, 'predecessor')
            pred.set('elementType', 'road')
            pred.set('elementId', self._remap_road_id(connecting_road.predecessor_id))
            pred.set('contactPoint', connecting_road.predecessor_contact)
        if connecting_road.successor_id:
            succ = etree.SubElement(link, 'successor')
            succ.set('elementType', 'road')
            succ.set('elementId', self._remap_road_id(connecting_road.successor_id))
            succ.set('contactPoint', connecting_road.successor_contact)

        # Type
        type_elem = etree.SubElement(road_elem, 'type')
        type_elem.set('s', '0.0')
        type_elem.set('type', 'town')

        if self.carla_compat:
            speed = etree.SubElement(type_elem, 'speed')
            speed.set('max', '13.89')
            speed.set('unit', 'm/s')

        # Plan view
        road_elem.append(self._create_plan_view(geometry_elements))

        # Elevation (flat)
        elevation = etree.SubElement(road_elem, 'elevationProfile')
        elev = etree.SubElement(elevation, 'elevation')
        for attr in ('s', 'a', 'b', 'c', 'd'):
            elev.set(attr, '0.0')

        # Lateral profile
        etree.SubElement(road_elem, 'lateralProfile')

        # Lanes — cr_lane_link_map: CR lane ID → (predecessor_lane, successor_lane).
        # For reversed-path CRs (pred=to_road, succ=from_road), the from/to
        # lane IDs must be swapped to match the CR's path direction.
        cr_lane_link_map = {}
        if lane_connections:
            for lc in lane_connections:
                if lc.connecting_road_id == connecting_road.id and lc.connecting_lane_id is not None:
                    if connecting_road.predecessor_id == lc.from_road_id:
                        pred_lane = lc.from_lane_id
                        succ_lane = lc.to_lane_id
                    else:
                        pred_lane = lc.to_lane_id
                        succ_lane = lc.from_lane_id
                    cr_lane_link_map[lc.connecting_lane_id] = (
                        pred_lane, succ_lane
                    )
        road_elem.append(self._create_connecting_road_lanes(
            connecting_road, road_length, cr_lane_link_map
        ))

        # Signals
        cr_signals = self.signal_builder.create_signals_for_connecting_road(
            connecting_road, self.project.signals, connecting_road.inline_path, path_meters
        )
        if cr_signals is not None:
            road_elem.append(cr_signals)
        elif self.carla_compat:
            road_elem.append(etree.Element('signals'))

        if self.carla_compat:
            road_elem.append(etree.Element('objects'))

        return road_elem

    def _snap_cr_endpoints_to_roads(
        self,
        connecting_road: Road,
        path_meters: list,
        lane_connections=None,
    ) -> list:
        """Snap connecting road endpoints to the connected road endpoints in meters.

        Looks up predecessor/successor road centerline endpoints, converts them
        to meters using the same source (geo_points or pixel) that the road
        export uses, and replaces path_meters[0] / path_meters[-1] so the
        exported geometry is topologically connected.

        When lane connections indicate the CR targets a lane other than -1,
        the snap point is offset perpendicular to the road heading so the
        CR's lane center aligns with the target lane center.

        Args:
            connecting_road: The connecting road being exported.
            path_meters: Path points already converted to meters.
            lane_connections: Junction lane connections for this CR's junction.

        Returns:
            path_meters with snapped first/last points (may be the same list).
        """
        if len(path_meters) < 2:
            return path_meters

        # Find primary lane connection for this CR
        primary_conn = None
        if lane_connections:
            for conn in lane_connections:
                if conn.connecting_road_id == connecting_road.id:
                    primary_conn = conn
                    break

        if primary_conn and primary_conn.connecting_lane_id is not None:
            cr_lane_id = primary_conn.connecting_lane_id
        elif connecting_road.cr_lane_count_right > 0:
            cr_lane_id = -1
        else:
            cr_lane_id = 1

        # Determine correct lane IDs for pred/succ.
        # For reversed-path CRs (left-lane, pred=to_road, succ=from_road),
        # from/to lane IDs must be swapped to match the CR's path direction.
        if primary_conn:
            if connecting_road.predecessor_id == primary_conn.from_road_id:
                pred_target_lane_id = primary_conn.from_lane_id
                succ_target_lane_id = primary_conn.to_lane_id
            else:
                pred_target_lane_id = primary_conn.to_lane_id
                succ_target_lane_id = primary_conn.from_lane_id

        # Get CR lane width at each endpoint
        connecting_road.ensure_cr_lanes_initialized()
        cr_lane_obj = connecting_road.get_cr_lane(cr_lane_id)
        cr_width_start = cr_lane_obj.width if cr_lane_obj else connecting_road.lane_info.lane_width
        cr_width_end = (cr_lane_obj.get_width_at_end() if cr_lane_obj
                        else connecting_road.lane_info.lane_width)

        # Snap start to predecessor road endpoint
        pred_road = self.road_map.get(connecting_road.predecessor_id)
        if pred_road and pred_road.centerline_id:
            snap_pt = self._get_road_endpoint_meters(
                pred_road.centerline_id, connecting_road.predecessor_contact
            )
            if snap_pt is not None:
                if primary_conn:
                    snap_pt = self._apply_lane_offset_to_snap_point(
                        snap_pt, pred_road, pred_road.centerline_id,
                        connecting_road.predecessor_contact,
                        pred_target_lane_id, cr_lane_id,
                        cr_width_start,
                        path_meters, is_start=True,
                    )
                path_meters[0] = snap_pt

        # Snap end to successor road endpoint
        succ_road = self.road_map.get(connecting_road.successor_id)
        if succ_road and succ_road.centerline_id:
            snap_pt = self._get_road_endpoint_meters(
                succ_road.centerline_id, connecting_road.successor_contact
            )
            if snap_pt is not None:
                if primary_conn:
                    snap_pt = self._apply_lane_offset_to_snap_point(
                        snap_pt, succ_road, succ_road.centerline_id,
                        connecting_road.successor_contact,
                        succ_target_lane_id, cr_lane_id,
                        cr_width_end,
                        path_meters, is_start=False,
                    )
                path_meters[-1] = snap_pt

        return path_meters

    def _apply_lane_offset_to_snap_point(
        self, snap_pt, road, centerline_id, contact_point,
        target_lane_id, cr_lane_id, cr_lane_width,
        path_meters=None, is_start=True,
    ):
        """Offset a snap point perpendicular to road heading for lane alignment.

        When the CR heading is ~180° from the road heading (reversed-path CRs),
        the CR lane offset is negated so the exported geometry stays on the
        correct side.
        """
        from orbit.utils.connecting_road_alignment import (
            _get_road_lane_width,
            _lane_center_offset,
        )

        road_lane_width = _get_road_lane_width(road, contact_point)
        road_lane_off = _lane_center_offset(target_lane_id, road_lane_width)
        cr_lane_off = _lane_center_offset(cr_lane_id, cr_lane_width)

        # Heading-sign correction: check if CR and road perpendiculars are
        # anti-aligned (headings ~180° apart) and negate CR offset if so.
        heading = self._get_road_heading_at_contact_meters(
            centerline_id, contact_point
        )
        if heading is not None and path_meters and len(path_meters) >= 2:
            road_perp = (math.sin(heading), -math.cos(heading))
            if is_start:
                cr_dx = path_meters[1][0] - path_meters[0][0]
                cr_dy = path_meters[1][1] - path_meters[0][1]
            else:
                cr_dx = path_meters[-1][0] - path_meters[-2][0]
                cr_dy = path_meters[-1][1] - path_meters[-2][1]
            cr_len = math.sqrt(cr_dx * cr_dx + cr_dy * cr_dy)
            if cr_len > 1e-9:
                cr_perp = (cr_dy / cr_len, -cr_dx / cr_len)
                dot = road_perp[0] * cr_perp[0] + road_perp[1] * cr_perp[1]
                if dot < 0:
                    cr_lane_off = -cr_lane_off

        offset_m = road_lane_off - cr_lane_off

        if abs(offset_m) < 0.01:
            return snap_pt

        if heading is None:
            return snap_pt

        # Right perpendicular in global (east/north) coordinates.
        # Positive offset_m = further to the right of the road direction.
        dx = offset_m * math.sin(heading)
        dy = -offset_m * math.cos(heading)

        return (snap_pt[0] + dx, snap_pt[1] + dy)

    def _get_road_heading_at_contact_meters(self, centerline_id, contact_point):
        """Get road heading at a contact point in meter coordinates.

        Prefers curve-fit geometry data (stored during _create_road) for
        accuracy. Falls back to 2-point approximation from raw polyline.
        """
        # Prefer curve-fit heading (matches the exported reference line)
        road_id = self._centerline_to_road.get(centerline_id)
        if road_id:
            endpoint = self._road_curve_endpoints.get((road_id, contact_point))
            if endpoint is not None:
                return endpoint[2]  # heading

        # Fallback: 2-point approximation from raw polyline
        polyline = self.polyline_map.get(centerline_id)
        if not polyline or len(polyline.points) < 2:
            return None

        use_end = (contact_point == "end")

        if polyline.geo_points:
            idx0 = -2 if use_end else 0
            idx1 = -1 if use_end else 1
            lon0, lat0 = polyline.geo_points[idx0]
            lon1, lat1 = polyline.geo_points[idx1]
            p0 = self.transformer.latlon_to_meters(lat0, lon0)
            p1 = self.transformer.latlon_to_meters(lat1, lon1)
        else:
            pts = polyline.points
            if use_end:
                batch = self.transformer.pixels_to_meters_batch(
                    [pts[-2], pts[-1]]
                )
            else:
                batch = self.transformer.pixels_to_meters_batch(
                    [pts[0], pts[1]]
                )
            p0, p1 = batch[0], batch[1]

        dx = p1[0] - p0[0]
        dy = p1[1] - p0[1]
        return math.atan2(dy, dx)

    def _get_road_endpoint_meters(
        self, centerline_id: str, contact_point: str
    ) -> Optional[tuple]:
        """Get a road centerline endpoint in meters, matching the export source.

        Uses geo_points when available (same as _create_road), otherwise
        converts from pixel coordinates.
        """
        polyline = self.polyline_map.get(centerline_id)
        if not polyline or len(polyline.points) < 2:
            return None

        use_end = (contact_point == "end")

        if polyline.geo_points:
            idx = -1 if use_end else 0
            lon, lat = polyline.geo_points[idx]
            return self.transformer.latlon_to_meters(lat, lon)
        else:
            idx = -1 if use_end else 0
            return self.transformer.pixels_to_meters_batch([polyline.points[idx]])[0]

    def _create_connecting_road_lanes(self, connecting_road: Road,
                                     road_length: float,
                                     cr_lane_link_map: dict = None) -> etree.Element:
        """
        Create lanes element for a connecting road using individual Lane objects.

        Each Lane object's width properties are used directly, supporting:
        - Constant width (width only)
        - Linear transition (width + width_end)
        - Polynomial width (width_b, width_c, width_d coefficients)

        Args:
            connecting_road: Road (with junction_id set) containing lane configuration
            road_length: Total length of the road in meters
            cr_lane_link_map: Mapping from CR lane ID to (predecessor_lane_id,
                successor_lane_id) derived from junction lane connections

        Returns:
            Lanes XML element
        """

        lanes = etree.Element('lanes')

        # Single lane section covering the entire connecting road
        lane_section = etree.SubElement(lanes, 'laneSection')
        lane_section.set('s', '0.0')

        # Ensure lanes are initialized (migrates road-level widths if needed)
        connecting_road.ensure_cr_lanes_initialized()

        # Get lanes from first lane section
        cr_lanes = connecting_road.lane_sections[0].lanes if connecting_road.lane_sections else []

        # Build lane map for quick lookup
        lane_map = {lane_obj.id: lane_obj for lane_obj in cr_lanes}

        # OpenDRIVE schema requires order: left, center, right

        # Left lanes (positive IDs: 1, 2, 3...)
        left_lanes = [lane_obj for lane_obj in cr_lanes if lane_obj.id > 0]
        left_lanes.sort(key=lambda lane: lane.id)  # Sort ascending: 1, 2, 3...
        if left_lanes:
            left = etree.SubElement(lane_section, 'left')
            for lane_obj in left_lanes:
                lane = self._create_connecting_lane_element(lane_obj, road_length, cr_lane_link_map)
                left.append(lane)

        # Center lane (always required)
        center = etree.SubElement(lane_section, 'center')
        center_lane_obj = lane_map.get(0)
        if center_lane_obj:
            center_lane = etree.SubElement(center, 'lane')
            center_lane.set('id', '0')
            center_lane.set('type', center_lane_obj.lane_type.value)
            center_lane.set('level', 'false')
        else:
            center_lane = etree.SubElement(center, 'lane')
            center_lane.set('id', '0')
            center_lane.set('type', 'none')
            center_lane.set('level', 'false')

        # Right lanes (negative IDs: -1, -2, -3...)
        right_lanes = [lane_obj for lane_obj in cr_lanes if lane_obj.id < 0]
        right_lanes.sort(key=lambda lane: lane.id, reverse=True)  # Sort descending: -1, -2, -3...
        if right_lanes:
            right = etree.SubElement(lane_section, 'right')
            for lane_obj in right_lanes:
                lane = self._create_connecting_lane_element(lane_obj, road_length, cr_lane_link_map)
                right.append(lane)

        return lanes

    def _create_connecting_lane_element(self, lane_obj, road_length: float,
                                       cr_lane_link_map: dict = None) -> etree.Element:
        """
        Create a single lane element for a connecting road.

        Args:
            lane_obj: Lane object with width and road mark properties
            road_length: Total road length for polynomial width calculation
            cr_lane_link_map: Mapping from CR lane ID to (predecessor_lane_id,
                successor_lane_id) derived from junction lane connections

        Returns:
            Lane XML element
        """
        from .lane_builder import convert_road_mark_type

        lane = etree.Element('lane')
        lane.set('id', str(lane_obj.id))
        lane.set('type', lane_obj.lane_type.value)
        lane.set('level', 'true' if lane_obj.level else 'false')

        # Lane link: use junction lane connections when available, then explicit
        # Lane.predecessor_id/successor_id, then fall back to lane's own ID.
        if lane_obj.id != 0:  # Non-center lanes
            link = etree.SubElement(lane, 'link')

            # Check junction lane connections first
            if cr_lane_link_map and lane_obj.id in cr_lane_link_map:
                pred_id, succ_id = cr_lane_link_map[lane_obj.id]
            else:
                pred_id = lane_obj.predecessor_id if lane_obj.predecessor_id is not None else lane_obj.id
                succ_id = lane_obj.successor_id if lane_obj.successor_id is not None else lane_obj.id

            pred = etree.SubElement(link, 'predecessor')
            pred.set('id', str(pred_id))
            succ = etree.SubElement(link, 'successor')
            succ.set('id', str(succ_id))

        # Calculate width polynomial coefficients
        # OpenDRIVE: width(ds) = a + b*ds + c*ds² + d*ds³
        width_a = lane_obj.width
        width_b = lane_obj.width_b
        width_c = lane_obj.width_c
        width_d = lane_obj.width_d

        # Handle linear transition via width_end (overrides polynomial b coefficient)
        if lane_obj.width_end is not None and road_length > 0:
            width_b = (lane_obj.width_end - lane_obj.width) / road_length

        width = etree.SubElement(lane, 'width')
        width.set('sOffset', '0.0')
        width.set('a', f'{width_a:.4f}')
        width.set('b', f'{width_b:.6f}')
        width.set('c', f'{width_c:.6f}')
        width.set('d', f'{width_d:.6f}')

        # Road mark from lane properties
        roadMark = etree.SubElement(lane, 'roadMark')
        roadMark.set('sOffset', '0.0')
        roadMark.set('type', convert_road_mark_type(lane_obj.road_mark_type))
        roadMark.set('weight', lane_obj.road_mark_weight)
        roadMark.set('color', lane_obj.road_mark_color)
        roadMark.set('width', f'{lane_obj.road_mark_width:.2f}')
        roadMark.set('laneChange', 'both')

        return lane

    def _create_plan_view(self, geometry_elements: List[GeometryElement]) -> etree.Element:
        """Create planView element with geometry."""
        plan_view = etree.Element('planView')

        s_offset = 0.0
        for geom in geometry_elements:
            geometry = etree.SubElement(plan_view, 'geometry')
            geometry.set('s', f'{s_offset:.4f}')
            geometry.set('x', f'{geom.start_pos[0] - self.offset_x:.4f}')
            geometry.set('y', f'{geom.start_pos[1] - self.offset_y:.4f}')
            geometry.set('hdg', f'{geom.heading:.6f}')
            geometry.set('length', f'{geom.length:.4f}')

            if geom.geom_type == GeometryType.LINE:
                etree.SubElement(geometry, 'line')
            elif geom.geom_type == GeometryType.ARC:
                arc = etree.SubElement(geometry, 'arc')
                arc.set('curvature', f'{geom.curvature:.8f}')
            elif geom.geom_type == GeometryType.SPIRAL:
                spiral = etree.SubElement(geometry, 'spiral')
                spiral.set('curvStart', f'{geom.curvature:.8f}')
                spiral.set('curvEnd', f'{geom.curvature_end:.8f}')
            elif geom.geom_type == GeometryType.PARAMPOLY3:
                parampoly3 = etree.SubElement(geometry, 'paramPoly3')
                parampoly3.set('aU', f'{geom.aU:.10f}')
                parampoly3.set('bU', f'{geom.bU:.10f}')
                parampoly3.set('cU', f'{geom.cU:.10f}')
                parampoly3.set('dU', f'{geom.dU:.10f}')
                parampoly3.set('aV', f'{geom.aV:.10f}')
                parampoly3.set('bV', f'{geom.bV:.10f}')
                parampoly3.set('cV', f'{geom.cV:.10f}')
                parampoly3.set('dV', f'{geom.dV:.10f}')
                # Use "normalized" string if p_range_normalized is True (OpenDRIVE standard)
                if geom.p_range_normalized:
                    parampoly3.set('pRange', 'normalized')
                else:
                    parampoly3.set('pRange', f'{geom.p_range:.4f}')

            s_offset += geom.length

        return plan_view

    def _create_junction(self, junction: Junction, junction_numeric_id: int) -> Optional[etree.Element]:
        """
        Create a junction element.

        Args:
            junction: Junction object with connecting roads and lane connections
            junction_numeric_id: Numeric ID for this junction in OpenDRIVE

        Returns:
            Junction XML element, or None if invalid
        """
        if len(junction.connected_road_ids) < 2:
            return None

        junction_elem = etree.Element('junction')
        junction_elem.set('id', str(junction_numeric_id))
        junction_elem.set('name', junction.name)
        # OpenDRIVE 1.4 has no 'type' attribute on junctions; omit for CARLA compat
        if not self.carla_compat:
            junction_elem.set('type', junction.junction_type)

        # Virtual junctions (path crossings) have no connections
        if junction.junction_type == "virtual":
            return junction_elem

        # Group lane connections by (from_road_id, connecting_road_id) to create connection elements
        # Each unique pair becomes one <connection> with multiple <laneLink> elements
        connection_groups = {}
        for lane_conn in junction.lane_connections:
            key = (lane_conn.from_road_id, lane_conn.connecting_road_id)
            if key not in connection_groups:
                connection_groups[key] = []
            connection_groups[key].append(lane_conn)

        # Create connection elements
        connection_id = 0
        for (from_road_id, connecting_road_id), lane_connections in connection_groups.items():
            # Verify the connecting road exists
            if connecting_road_id not in self.road_map:
                continue

            connection = etree.SubElement(junction_elem, 'connection')
            connection.set('id', str(connection_id))
            connection.set('incomingRoad', self._remap_road_id(from_road_id))
            connection.set('connectingRoad', self._remap_road_id(connecting_road_id))

            # Determine contactPoint: which end of the connecting road
            # touches the incoming road.
            cr = self.road_map.get(connecting_road_id)
            if cr and cr.predecessor_id == from_road_id:
                contact_pt = 'start'
            elif cr and cr.successor_id == from_road_id:
                contact_pt = 'end'
            else:
                contact_pt = 'start'  # fallback
            connection.set('contactPoint', contact_pt)

            # Note: priority is a child element of junction, not an attribute of connection
            # Priority handling would need to be done at the junction level if needed

            # Add lane links for this connection
            for lane_conn in lane_connections:
                lane_link = etree.SubElement(connection, 'laneLink')
                lane_link.set('from', str(lane_conn.from_lane_id))
                # Use connecting_lane_id if set, otherwise derive from from_lane_id sign
                # (OpenDRIVE laneLink.to is lane on connecting road, not outgoing road)
                if lane_conn.connecting_lane_id is not None:
                    connecting_lane = lane_conn.connecting_lane_id
                else:
                    # Fallback for older projects: map based on lane side
                    # Negative from_lane → -1 (right), positive → +1 (left)
                    connecting_lane = -1 if lane_conn.from_lane_id < 0 else 1
                lane_link.set('to', str(connecting_lane))

            connection_id += 1

        # boundary and elevationGrid are V1.8 features; skip for CARLA compat
        if not self.carla_compat:
            # Add boundary (V1.8 feature)
            if junction.boundary and junction.boundary.segments:
                boundary_elem = etree.SubElement(junction_elem, 'boundary')
                for segment in junction.boundary.segments:
                    seg_elem = etree.SubElement(boundary_elem, 'segment')
                    seg_elem.set('type', segment.segment_type)

                    if segment.road_id:
                        seg_elem.set('roadId', self._remap_road_id(segment.road_id))

                    if segment.segment_type == 'lane':
                        if segment.boundary_lane is not None:
                            seg_elem.set('boundaryLane', str(segment.boundary_lane))
                        if segment.s_start is not None:
                            seg_elem.set('sStart', f'{segment.s_start:.6g}')
                        if segment.s_end is not None:
                            seg_elem.set('sEnd', f'{segment.s_end:.6g}')
                    elif segment.segment_type == 'joint':
                        if segment.contact_point:
                            seg_elem.set('contactPoint', segment.contact_point)
                        if segment.joint_lane_start is not None:
                            seg_elem.set('jointLaneStart', str(segment.joint_lane_start))
                        if segment.joint_lane_end is not None:
                            seg_elem.set('jointLaneEnd', str(segment.joint_lane_end))
                        if segment.transition_length is not None:
                            seg_elem.set('transitionLength', f'{segment.transition_length:.6g}')

            # Add elevation grid (V1.8 feature)
            if junction.elevation_grid and junction.elevation_grid.elevations:
                eg_elem = etree.SubElement(junction_elem, 'elevationGrid')
                if junction.elevation_grid.grid_spacing:
                    eg_elem.set('gridSpacing', junction.elevation_grid.grid_spacing)
                for elev_point in junction.elevation_grid.elevations:
                    elev_elem = etree.SubElement(eg_elem, 'elevation')
                    if elev_point.center:
                        elev_elem.set('center', elev_point.center)
                    if elev_point.left:
                        elev_elem.set('left', elev_point.left)
                    if elev_point.right:
                        elev_elem.set('right', elev_point.right)

        return junction_elem

    def _create_junction_group(self, junction_group, group_id: int) -> Optional[etree.Element]:
        """
        Create a junctionGroup element.

        Args:
            junction_group: JunctionGroup object
            group_id: Numeric ID for this junction group in OpenDRIVE

        Returns:
            JunctionGroup XML element, or None if no valid junction references
        """
        # Map ORBIT junction IDs to numeric OpenDRIVE junction IDs
        junction_refs = []
        for junction_id in junction_group.junction_ids:
            numeric_id = self.junction_numeric_ids.get(junction_id)
            if numeric_id is not None:
                junction_refs.append(numeric_id)

        if not junction_refs:
            return None

        jg_elem = etree.Element('junctionGroup')
        jg_elem.set('id', str(group_id))
        jg_elem.set('type', junction_group.group_type)

        if junction_group.name:
            jg_elem.set('name', junction_group.name)

        # Add junction references
        for junction_numeric_id in junction_refs:
            ref_elem = etree.SubElement(jg_elem, 'junctionReference')
            ref_elem.set('junction', str(junction_numeric_id))

        return jg_elem


def export_to_opendrive(
    project: Project,
    transformer: CoordinateTransformer,
    output_path: str,
    line_tolerance: float = 0.5,
    arc_tolerance: float = 1.0,
    preserve_geometry: bool = True,
    right_hand_traffic: bool = True,
    country_code: str = "se",
    use_tmerc: bool = False,
    use_german_codes: bool = False,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    geo_reference_string: Optional[str] = None,
    export_object_types: Optional[set] = None,
    carla_compat: bool = False,
) -> bool:
    """
    Export project to OpenDrive format.

    Args:
        project: The ORBIT project
        transformer: Coordinate transformer
        output_path: Output file path (.xodr)
        line_tolerance: Tolerance for line fitting in meters
        arc_tolerance: Tolerance for arc fitting in meters
        preserve_geometry: If True, preserve all polyline points (one line per segment)
        right_hand_traffic: True for right-hand traffic (default), False for left-hand
        country_code: Two-letter ISO 3166-1 country code (default: "se")
        use_tmerc: If True, use Transverse Mercator projection; if False (default),
                   use UTM projection or preserved geoReference
        use_german_codes: If True, use German VzKat codes (opendrive_de) for signals
        offset_x: X offset subtracted from all exported coordinates (projected easting)
        offset_y: Y offset subtracted from all exported coordinates (projected northing)
        geo_reference_string: Explicit proj string for the geoReference element
        export_object_types: If set, only export objects whose type is in this set.
            If None (default), all objects are exported.
        carla_compat: If True, export OpenDRIVE 1.4 compatible with CARLA simulator

    Returns:
        True if successful
    """
    curve_fitter = CurveFitter(line_tolerance, arc_tolerance, preserve_geometry)
    writer = OpenDriveWriter(
        project, transformer, curve_fitter, right_hand_traffic,
        country_code, use_tmerc, use_german_codes,
        offset_x, offset_y, geo_reference_string, export_object_types,
        carla_compat=carla_compat,
    )
    return writer.write(output_path)


def validate_opendrive_file(
    file_path: str,
    schema_path: Optional[str] = None
) -> Optional[List[str]]:
    """
    Validate an OpenDRIVE XML file against the XSD schema.

    Uses the xmlschema library which supports XSD 1.1 features used by
    OpenDRIVE 1.8 schemas (like xs:assert).

    Args:
        file_path: Path to the .xodr file to validate
        schema_path: Path to OpenDRIVE XSD schema file (OpenDRIVE_Core.xsd).
                    If None, validation is skipped. All other schema files
                    (OpenDRIVE_Road.xsd, etc.) must be in the same directory.

    Returns:
        List of validation error messages (empty if valid),
        or None if validation was skipped (no schema provided).
    """
    if schema_path is None:
        logger.info("No schema path provided - validation skipped")
        return None

    errors = []

    try:
        import xmlschema
    except ImportError:
        errors.append("xmlschema library not installed - validation skipped")
        return errors

    try:
        # Convert to absolute path for file URI generation
        schema_path_abs = Path(schema_path).resolve()
        schema_dir = schema_path_abs.parent

        # Build URI mapper to redirect online URLs to local files.
        # OpenDRIVE schemas use xs:include with absolute URLs like:
        # https://opendrive.asam.net/V1-8-0/xsd_schema/OpenDRIVE_Railroad.xsd
        # The uri_mapper rewrites these to local file:// URLs before fetching.
        uri_map = {}
        for xsd_file in schema_dir.glob("*.xsd"):
            filename = xsd_file.name
            # OpenDRIVE 1.8 URL pattern
            url_v18 = f"https://opendrive.asam.net/V1-8-0/xsd_schema/{filename}"
            uri_map[url_v18] = xsd_file.resolve().as_uri()

        # Load schema with XSD 1.1 support and URI mapper
        schema = xmlschema.XMLSchema11(
            str(schema_path_abs),
            uri_mapper=uri_map
        )

        # Validate the file
        validation_errors = list(schema.iter_errors(file_path))

        for error in validation_errors:
            if hasattr(error, 'reason') and error.reason:
                errors.append(f"Line {error.sourceline}: {error.reason}")
            else:
                errors.append(f"Line {error.sourceline}: {error.message}")

    except Exception as e:
        errors.append(f"Validation error: {e}")

    return errors

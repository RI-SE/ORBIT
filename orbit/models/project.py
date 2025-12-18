"""
Project data model for ORBIT.

Manages the complete project state including polylines, roads, junctions,
and georeferencing data. Handles saving/loading to .orbit files.
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path
import json
from datetime import datetime

from orbit.utils.logging_config import get_logger
from .polyline import Polyline
from .road import Road
from .junction import Junction, JunctionGroup
from .signal import Signal
from .object import RoadObject
from .parking import ParkingSpace

logger = get_logger(__name__)


@dataclass
class ControlPoint:
    """
    A georeferencing control point.

    Attributes:
        pixel_x: X coordinate in image pixels
        pixel_y: Y coordinate in image pixels
        longitude: Longitude in decimal degrees
        latitude: Latitude in decimal degrees
        name: Optional name for the control point
        is_validation: If True, point is used for validation only (GVP), not training (GCP)
    """
    pixel_x: float
    pixel_y: float
    longitude: float
    latitude: float
    name: Optional[str] = None
    is_validation: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'pixel_x': self.pixel_x,
            'pixel_y': self.pixel_y,
            'longitude': self.longitude,
            'latitude': self.latitude,
            'name': self.name,
            'is_validation': bool(self.is_validation)
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ControlPoint':
        """Create from dictionary."""
        return cls(
            pixel_x=data['pixel_x'],
            pixel_y=data['pixel_y'],
            longitude=data['longitude'],
            latitude=data['latitude'],
            name=data.get('name'),
            is_validation=data.get('is_validation', False)  # Default to False for backwards compatibility
        )


@dataclass
class Project:
    """
    Main project container for ORBIT.

    Attributes:
        image_path: Path to the loaded image
        polylines: List of all polylines
        roads: List of all roads
        junctions: List of all junctions
        signals: List of all traffic signals
        objects: List of all roadside objects
        control_points: List of georeferencing control points
        right_hand_traffic: True for right-hand traffic (default), False for left-hand traffic
        transform_method: Georeferencing transformation method ('affine' or 'homography')
        country_code: Two-letter ISO 3166-1 country code for OpenDrive export
        map_name: Name of the map for OpenDrive export (defaults to image filename)
        openstreetmap_used: Flag indicating if OpenStreetMap data was imported
        georef_validation: Validation results for georeferencing (reprojection and validation errors)
        metadata: Additional project metadata
    """
    image_path: Optional[Path] = None
    polylines: List[Polyline] = field(default_factory=list)
    roads: List[Road] = field(default_factory=list)
    junctions: List[Junction] = field(default_factory=list)
    junction_groups: List[JunctionGroup] = field(default_factory=list)
    signals: List[Signal] = field(default_factory=list)
    objects: List[RoadObject] = field(default_factory=list)
    parking_spaces: List[ParkingSpace] = field(default_factory=list)
    control_points: List[ControlPoint] = field(default_factory=list)
    right_hand_traffic: bool = True  # Default to right-hand traffic
    transform_method: str = 'homography'  # Default to homography for drone images
    country_code: str = 'se'  # Default to Sweden
    map_name: str = ''  # Name for OpenDrive export (defaults to image filename when loaded)
    openstreetmap_used: bool = False  # Flag for OpenStreetMap attribution
    junction_offset_distance_meters: float = 8.0  # Distance to offset road endpoints from junction centers (meters)
    roundabout_ring_offset_distance_meters: float = 4.0  # Distance to offset ring segment endpoints from roundabout junctions (meters)
    roundabout_approach_offset_distance_meters: float = 8.0  # Distance to offset approach road endpoints from roundabout junctions (meters)
    georef_validation: Dict[str, Any] = field(default_factory=dict)
    uncertainty_grid_cache: Optional[List[List[float]]] = None  # Cached uncertainty grid
    uncertainty_grid_resolution: Tuple[int, int] = (50, 50)  # Grid resolution
    uncertainty_bootstrap_grid: Optional[List[List[float]]] = None  # Bootstrap analysis results
    uncertainty_last_computed: Optional[str] = None  # ISO timestamp of last computation
    mc_sigma_pixels: float = 1.5  # Measurement error for Monte Carlo (pixels)
    baseline_uncertainty_m: float = 0.05  # Baseline position uncertainty (meters)
    gcp_suggestion_threshold: float = 0.2  # Threshold for GCP suggestions (meters)
    imported_geo_reference: Optional[str] = None  # Preserved geoReference from OpenDRIVE import
    enabled_sign_libraries: List[str] = field(default_factory=lambda: ['se'])  # Enabled sign library IDs
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Initialize metadata if not provided."""
        if not self.metadata:
            self.metadata = {
                'version': '0.3.1',
                'created': datetime.now().isoformat(),
                'modified': datetime.now().isoformat()
            }

    # Polyline management
    def add_polyline(self, polyline: Polyline) -> None:
        """Add a polyline to the project."""
        self.polylines.append(polyline)

    def remove_polyline(self, polyline_id: str) -> None:
        """Remove a polyline and update any roads that reference it."""
        self.polylines = [p for p in self.polylines if p.id != polyline_id]
        # Remove from roads
        for road in self.roads:
            road.remove_polyline(polyline_id)

    def get_polyline(self, polyline_id: str) -> Optional[Polyline]:
        """Get a polyline by ID."""
        for polyline in self.polylines:
            if polyline.id == polyline_id:
                return polyline
        return None

    # Road management
    def add_road(self, road: Road) -> None:
        """Add a road to the project."""
        self.roads.append(road)

    def remove_road(self, road_id: str) -> None:
        """Remove a road and update junctions."""
        self.roads = [r for r in self.roads if r.id != road_id]
        # Remove from junctions
        for junction in self.junctions:
            junction.remove_road(road_id)

    def get_road(self, road_id: str) -> Optional[Road]:
        """Get a road by ID."""
        for road in self.roads:
            if road.id == road_id:
                return road
        return None

    def split_road_at_point(
        self,
        road_id: str,
        polyline_id: str,
        point_index: int
    ) -> Optional[Tuple[Road, Road]]:
        """
        Split a road at a centerline point, creating two connected roads.

        The original road is modified to become the first segment, and a new road
        is created for the second segment. Both centerline and boundary polylines
        are split at the corresponding positions.

        Args:
            road_id: ID of the road to split
            polyline_id: ID of the centerline polyline
            point_index: Index of the point where to split

        Returns:
            Tuple of (road1, road2) if successful, None on failure
        """
        from orbit.utils.geometry import (
            split_polyline_at_index,
            split_boundary_at_centerline_s,
            calculate_path_length
        )

        # Get road and centerline
        road = self.get_road(road_id)
        if not road:
            logger.error(f"Road {road_id} not found")
            return None

        centerline = self.get_polyline(polyline_id)
        if not centerline:
            logger.error(f"Centerline polyline {polyline_id} not found")
            return None

        if road.centerline_id != polyline_id:
            logger.error(f"Polyline {polyline_id} is not the centerline of road {road_id}")
            return None

        # Validate point_index (cannot split at first or last point)
        if point_index <= 0 or point_index >= centerline.point_count() - 1:
            logger.error(f"Invalid split point index {point_index}")
            return None

        # Store original centerline points before modification (needed for boundary projection)
        original_centerline_points = list(centerline.points)

        # Calculate s-coordinate at split point
        s_coords = road.calculate_centerline_s_coordinates(centerline.points)
        split_s = s_coords[point_index]

        # Split centerline polyline
        centerline_pts1, centerline_pts2 = split_polyline_at_index(
            centerline.points, point_index, duplicate_point=True
        )

        # Create new centerline polyline for road 2
        new_centerline = Polyline(
            points=centerline_pts2,
            line_type=centerline.line_type,
            road_mark_type=centerline.road_mark_type
        )
        self.add_polyline(new_centerline)

        # Update original centerline
        centerline.points = centerline_pts1

        # Split boundary polylines
        new_boundary_ids = []
        for boundary_id in road.polyline_ids:
            if boundary_id == polyline_id:
                continue  # Skip centerline, already handled

            boundary = self.get_polyline(boundary_id)
            if not boundary:
                continue

            # Split boundary at corresponding s-coordinate
            result = split_boundary_at_centerline_s(
                boundary.points,
                original_centerline_points,  # Use original (unsplit) centerline for projection
                split_s
            )

            if result:
                boundary_pts1, boundary_pts2 = result

                # Create new boundary for road 2
                new_boundary = Polyline(
                    points=boundary_pts2,
                    line_type=boundary.line_type,
                    road_mark_type=boundary.road_mark_type
                )
                self.add_polyline(new_boundary)
                new_boundary_ids.append(new_boundary.id)

                # Update original boundary
                boundary.points = boundary_pts1

        # Distribute lane sections
        sections_road1, sections_road2 = road.distribute_lane_sections_for_split(
            split_s, point_index
        )

        # Generate segment names
        original_name = road.name
        # Check if name already has segment suffix
        import re
        seg_match = re.match(r'^(.*?)\s*\(seg \d+/\d+\)$', original_name)
        if seg_match:
            base_name = seg_match.group(1)
        else:
            base_name = original_name

        road1_name = f"{base_name} (seg 1/2)"
        road2_name = f"{base_name} (seg 2/2)"

        # Store original junction_id before we clear it from road1
        original_junction_id = road.junction_id

        # Create new road (road 2) with second segment
        road2 = Road(
            name=road2_name,
            polyline_ids=[new_centerline.id] + new_boundary_ids,
            centerline_id=new_centerline.id,
            road_type=road.road_type,
            lane_info=road.lane_info,
            lane_sections=sections_road2,
            speed_limit=road.speed_limit,
            junction_id=None,  # Will be set below if needed
            predecessor_id=road.id,  # Link to first road
            predecessor_contact="end",
            successor_id=road.successor_id,  # Keep original successor
            successor_contact=road.successor_contact
        )

        # Update road 1 (original road)
        road.name = road1_name
        road.polyline_ids = [polyline_id] + [
            bid for bid in road.polyline_ids
            if bid != polyline_id and bid not in [nb.id for nb in [self.get_polyline(nid) for nid in new_boundary_ids if self.get_polyline(nid)]]
        ]
        road.lane_sections = sections_road1
        road.successor_id = road2.id
        road.successor_contact = "start"

        # Add new road to project
        self.add_road(road2)

        # Handle junction remapping
        # If the original road was connected to a junction, we need to update the junction
        # to point to road2 instead (since road2 now has the "end" that was connected)
        self._remap_junctions_after_road_split(road.id, road2.id, original_junction_id)

        logger.info(f"Split road '{original_name}' into '{road1_name}' and '{road2_name}'")

        return (road, road2)

    def _remap_junctions_after_road_split(
        self,
        original_road_id: str,
        new_road_id: str,
        original_junction_id: Optional[str]
    ) -> None:
        """
        Update junction references after a road split.

        When a road is split, the "end" of the original road becomes the "end" of
        the new road (road2). Any junctions that were connected to the original
        road's end need to be updated to reference the new road instead.

        Args:
            original_road_id: ID of the original road (now road1, the first segment)
            new_road_id: ID of the new road (road2, the second segment)
            original_junction_id: The junction_id that was on the original road (if any)
        """
        road2 = self.get_road(new_road_id)
        if not road2:
            return

        # If original road had a junction_id, transfer it to road2
        # (the junction_id field typically means the road connects to that junction at its end)
        if original_junction_id:
            road2.junction_id = original_junction_id
            # Clear from road1 (the original road object is already updated)
            road1 = self.get_road(original_road_id)
            if road1:
                road1.junction_id = None

        # Update all junctions that reference the original road
        for junction in self.junctions:
            remapped = False

            # Update connected_road_ids
            if original_road_id in junction.connected_road_ids:
                # Replace original road with new road in the list
                idx = junction.connected_road_ids.index(original_road_id)
                junction.connected_road_ids[idx] = new_road_id
                remapped = True

            # Update entry_roads (for roundabouts)
            if original_road_id in junction.entry_roads:
                idx = junction.entry_roads.index(original_road_id)
                junction.entry_roads[idx] = new_road_id
                remapped = True

            # Update exit_roads (for roundabouts)
            if original_road_id in junction.exit_roads:
                idx = junction.exit_roads.index(original_road_id)
                junction.exit_roads[idx] = new_road_id
                remapped = True

            # Update connecting_roads
            for conn_road in junction.connecting_roads:
                if conn_road.predecessor_road_id == original_road_id:
                    conn_road.predecessor_road_id = new_road_id
                    remapped = True
                if conn_road.successor_road_id == original_road_id:
                    conn_road.successor_road_id = new_road_id
                    remapped = True

            # Update lane_connections
            for lane_conn in junction.lane_connections:
                if lane_conn.from_road_id == original_road_id:
                    lane_conn.from_road_id = new_road_id
                    remapped = True
                if lane_conn.to_road_id == original_road_id:
                    lane_conn.to_road_id = new_road_id
                    remapped = True

            # Update boundary segments
            if junction.boundary:
                for segment in junction.boundary.segments:
                    if segment.road_id == original_road_id:
                        segment.road_id = new_road_id
                        remapped = True

            if remapped:
                logger.info(f"Remapped junction '{junction.name}' to reference new road {new_road_id[:8]}...")

    def merge_consecutive_roads(
        self,
        road1_id: str,
        road2_id: str
    ) -> Optional[Road]:
        """
        Merge two consecutive roads into one.

        Road1 must be the predecessor of Road2 (road1.successor_id == road2.id).
        The merged road keeps road1's ID and most properties. Road2 and its
        polylines are deleted after merging.

        Args:
            road1_id: ID of the first road (predecessor)
            road2_id: ID of the second road (successor)

        Returns:
            The merged road (road1 with updated data), or None on failure
        """
        import re
        from orbit.utils.geometry import (
            merge_polylines_at_junction,
            calculate_path_length,
            distance_between_points
        )

        # Get both roads
        road1 = self.get_road(road1_id)
        road2 = self.get_road(road2_id)

        if not road1 or not road2:
            logger.error(f"Road not found: road1={road1_id}, road2={road2_id}")
            return None

        # Validate that roads are consecutive
        if road1.successor_id != road2.id or road2.predecessor_id != road1.id:
            logger.error(
                f"Roads are not consecutive: road1.successor={road1.successor_id}, "
                f"road2.predecessor={road2.predecessor_id}"
            )
            return None

        # Get centerlines
        centerline1 = self.get_polyline(road1.centerline_id)
        centerline2 = self.get_polyline(road2.centerline_id)

        if not centerline1 or not centerline2:
            logger.error("Missing centerline polyline")
            return None

        # Store road1's original centerline point count for section index adjustment
        road1_point_count = len(centerline1.points)

        # Merge centerlines
        merged_centerline_pts = merge_polylines_at_junction(
            centerline1.points,
            centerline2.points,
            tolerance=5.0  # Allow some tolerance for junction points
        )

        if merged_centerline_pts is None:
            logger.error(
                f"Centerlines cannot be joined: end1={centerline1.points[-1]}, "
                f"start2={centerline2.points[0]}"
            )
            return None

        # Calculate road1's length before merge (needed for section adjustment)
        road1_length_before = calculate_path_length(centerline1.points)

        # Update road1's centerline
        centerline1.points = merged_centerline_pts

        # Merge boundary polylines by matching endpoints
        road1_boundaries = [
            bid for bid in road1.polyline_ids if bid != road1.centerline_id
        ]
        road2_boundaries = [
            bid for bid in road2.polyline_ids if bid != road2.centerline_id
        ]

        boundaries_to_delete = []

        for b1_id in road1_boundaries:
            b1 = self.get_polyline(b1_id)
            if not b1 or not b1.points:
                continue

            # Find matching boundary in road2 (by endpoint proximity)
            best_match_id = None
            best_match_dist = float('inf')

            for b2_id in road2_boundaries:
                b2 = self.get_polyline(b2_id)
                if not b2 or not b2.points:
                    continue

                dist = distance_between_points(b1.points[-1], b2.points[0])
                if dist < best_match_dist:
                    best_match_dist = dist
                    best_match_id = b2_id

            # Merge if match found within tolerance
            if best_match_id and best_match_dist < 10.0:
                b2 = self.get_polyline(best_match_id)
                merged_boundary_pts = merge_polylines_at_junction(
                    b1.points, b2.points, tolerance=10.0
                )
                if merged_boundary_pts:
                    b1.points = merged_boundary_pts
                    boundaries_to_delete.append(best_match_id)
                    road2_boundaries.remove(best_match_id)

        # Merge lane sections
        # First, keep all of road1's sections as-is
        # Then append road2's sections with adjusted s-coordinates

        for section in road2.lane_sections:
            # Adjust s-coordinates (add road1's length)
            section.s_start += road1_length_before
            section.s_end += road1_length_before

            # Adjust end_point_index (add road1's point count minus 1 for junction overlap)
            if section.end_point_index is not None:
                section.end_point_index += road1_point_count - 1

            road1.lane_sections.append(section)

        # Renumber all sections
        road1.renumber_sections()

        # Update road1's properties
        # Strip segment suffix from name if present
        base_name = road1.name
        seg_match = re.match(r'^(.*?)\s*\(seg \d+/\d+\)$', base_name)
        if seg_match:
            base_name = seg_match.group(1).strip()
        road1.name = base_name

        # Inherit road2's successor
        road1.successor_id = road2.successor_id
        road1.successor_contact = road2.successor_contact

        # Inherit road2's junction_id if it had one (at its end)
        if road2.junction_id:
            road1.junction_id = road2.junction_id

        # Remap junctions: any reference to road2 should now point to road1
        self._remap_junctions_after_road_merge(road1.id, road2.id)

        # Update any road that had road2 as predecessor to now have road1
        for road in self.roads:
            if road.predecessor_id == road2.id:
                road.predecessor_id = road1.id

        # Delete road2's polylines
        for b_id in boundaries_to_delete:
            self.remove_polyline(b_id)

        # Delete road2's centerline
        self.remove_polyline(road2.centerline_id)

        # Delete any remaining road2 boundaries that weren't merged
        for b_id in road2_boundaries:
            self.remove_polyline(b_id)

        # Delete road2
        self.remove_road(road2.id)

        logger.info(f"Merged roads into '{road1.name}' (id={road1.id[:8]}...)")

        return road1

    def _remap_junctions_after_road_merge(
        self,
        kept_road_id: str,
        deleted_road_id: str
    ) -> None:
        """
        Update junction references after merging roads.

        Any reference to deleted_road_id in junctions is replaced with kept_road_id.

        Args:
            kept_road_id: ID of the road that remains (merged result)
            deleted_road_id: ID of the road being deleted
        """
        for junction in self.junctions:
            remapped = False

            # Update connected_road_ids
            if deleted_road_id in junction.connected_road_ids:
                junction.connected_road_ids.remove(deleted_road_id)
                if kept_road_id not in junction.connected_road_ids:
                    junction.connected_road_ids.append(kept_road_id)
                remapped = True

            # Update entry_roads (for roundabouts)
            if deleted_road_id in junction.entry_roads:
                idx = junction.entry_roads.index(deleted_road_id)
                junction.entry_roads[idx] = kept_road_id
                remapped = True

            # Update exit_roads (for roundabouts)
            if deleted_road_id in junction.exit_roads:
                idx = junction.exit_roads.index(deleted_road_id)
                junction.exit_roads[idx] = kept_road_id
                remapped = True

            # Update connecting_roads
            for conn_road in junction.connecting_roads:
                if conn_road.predecessor_road_id == deleted_road_id:
                    conn_road.predecessor_road_id = kept_road_id
                    remapped = True
                if conn_road.successor_road_id == deleted_road_id:
                    conn_road.successor_road_id = kept_road_id
                    remapped = True

            # Update lane_connections
            for lane_conn in junction.lane_connections:
                if lane_conn.from_road_id == deleted_road_id:
                    lane_conn.from_road_id = kept_road_id
                    remapped = True
                if lane_conn.to_road_id == deleted_road_id:
                    lane_conn.to_road_id = kept_road_id
                    remapped = True

            # Update boundary segments
            if junction.boundary:
                for segment in junction.boundary.segments:
                    if segment.road_id == deleted_road_id:
                        segment.road_id = kept_road_id
                        remapped = True

            if remapped:
                logger.info(
                    f"Remapped junction '{junction.name}' references from "
                    f"{deleted_road_id[:8]}... to {kept_road_id[:8]}..."
                )

    # Junction management
    def add_junction(self, junction: Junction) -> None:
        """Add a junction to the project."""
        self.junctions.append(junction)

    def remove_junction(self, junction_id: str) -> None:
        """Remove a junction from the project."""
        self.junctions = [j for j in self.junctions if j.id != junction_id]

    def get_junction(self, junction_id: str) -> Optional[Junction]:
        """Get a junction by ID."""
        for junction in self.junctions:
            if junction.id == junction_id:
                return junction
        return None

    # Signal management
    def add_signal(self, signal: Signal) -> None:
        """Add a traffic signal to the project."""
        self.signals.append(signal)

    def remove_signal(self, signal_id: str) -> None:
        """Remove a signal from the project."""
        self.signals = [s for s in self.signals if s.id != signal_id]

    def get_signal(self, signal_id: str) -> Optional[Signal]:
        """Get a signal by ID."""
        for signal in self.signals:
            if signal.id == signal_id:
                return signal
        return None

    # Object management
    def add_object(self, obj: RoadObject) -> None:
        """Add a roadside object to the project."""
        self.objects.append(obj)

    def remove_object(self, object_id: str) -> None:
        """Remove an object from the project."""
        self.objects = [o for o in self.objects if o.id != object_id]

    def get_object(self, object_id: str) -> Optional[RoadObject]:
        """Get an object by ID."""
        for obj in self.objects:
            if obj.id == object_id:
                return obj
        return None

    # Parking management
    def add_parking(self, parking: ParkingSpace) -> None:
        """Add a parking space to the project."""
        self.parking_spaces.append(parking)

    def remove_parking(self, parking_id: str) -> None:
        """Remove a parking space from the project."""
        self.parking_spaces = [p for p in self.parking_spaces if p.id != parking_id]

    def get_parking(self, parking_id: str) -> Optional[ParkingSpace]:
        """Get a parking space by ID."""
        for parking in self.parking_spaces:
            if parking.id == parking_id:
                return parking
        return None

    def find_closest_road(self, position: Tuple[float, float]) -> Optional[str]:
        """
        Find the road closest to a given position.

        Args:
            position: (x, y) pixel coordinates

        Returns:
            Road ID of the closest road, or None if no roads exist
        """
        if not self.roads:
            return None

        min_distance = float('inf')
        closest_road_id = None

        for road in self.roads:
            if not road.centerline_id:
                continue

            centerline_polyline = self.get_polyline(road.centerline_id)
            if not centerline_polyline or not centerline_polyline.points:
                continue

            # Calculate distance from position to road centerline
            distance = self._point_to_polyline_distance(position, centerline_polyline.points)

            if distance < min_distance:
                min_distance = distance
                closest_road_id = road.id

        return closest_road_id

    def _point_to_polyline_distance(self, point: Tuple[float, float],
                                    polyline_points: List[Tuple[float, float]]) -> float:
        """
        Calculate minimum distance from a point to a polyline.

        Args:
            point: (x, y) coordinates
            polyline_points: List of (x, y) points defining the polyline

        Returns:
            Minimum distance to the polyline
        """
        if not polyline_points:
            return float('inf')

        min_dist = float('inf')
        px, py = point

        for i in range(len(polyline_points) - 1):
            x1, y1 = polyline_points[i]
            x2, y2 = polyline_points[i + 1]

            # Distance from point to line segment
            dx, dy = x2 - x1, y2 - y1
            length_sq = dx * dx + dy * dy

            if length_sq == 0:
                # Segment is a point
                dist = ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
            else:
                # Project point onto segment
                t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / length_sq))
                proj_x = x1 + t * dx
                proj_y = y1 + t * dy
                dist = ((px - proj_x) ** 2 + (py - proj_y) ** 2) ** 0.5

            min_dist = min(min_dist, dist)

        return min_dist

    # Control point management
    def add_control_point(self, control_point: ControlPoint) -> None:
        """Add a georeferencing control point."""
        self.control_points.append(control_point)
        self.invalidate_uncertainty_cache()

    def remove_control_point(self, index: int) -> None:
        """Remove a control point by index."""
        if 0 <= index < len(self.control_points):
            self.control_points.pop(index)
            self.invalidate_uncertainty_cache()

    def has_georeferencing(self) -> bool:
        """Check if project has enough control points for georeferencing."""
        return len(self.control_points) >= 3

    def invalidate_uncertainty_cache(self) -> None:
        """Clear cached uncertainty data when GCPs change."""
        self.uncertainty_grid_cache = None
        self.uncertainty_bootstrap_grid = None
        self.uncertainty_last_computed = None

    # Save/Load
    def to_dict(self) -> Dict[str, Any]:
        """Convert project to dictionary for JSON serialization."""
        self.metadata['modified'] = datetime.now().isoformat()

        return {
            'metadata': self.metadata,
            'image_path': str(self.image_path) if self.image_path else None,
            'polylines': [p.to_dict() for p in self.polylines],
            'roads': [r.to_dict() for r in self.roads],
            'junctions': [j.to_dict() for j in self.junctions],
            'junction_groups': [jg.to_dict() for jg in self.junction_groups],
            'signals': [s.to_dict() for s in self.signals],
            'objects': [o.to_dict() for o in self.objects],
            'parking_spaces': [p.to_dict() for p in self.parking_spaces],
            'control_points': [cp.to_dict() for cp in self.control_points],
            'right_hand_traffic': bool(self.right_hand_traffic),
            'transform_method': self.transform_method,
            'country_code': self.country_code,
            'map_name': self.map_name,
            'openstreetmap_used': bool(self.openstreetmap_used),
            'junction_offset_distance_meters': self.junction_offset_distance_meters,
            'roundabout_ring_offset_distance_meters': self.roundabout_ring_offset_distance_meters,
            'roundabout_approach_offset_distance_meters': self.roundabout_approach_offset_distance_meters,
            'georef_validation': self.georef_validation,
            'uncertainty_grid_cache': self.uncertainty_grid_cache,
            'uncertainty_grid_resolution': self.uncertainty_grid_resolution,
            'uncertainty_bootstrap_grid': self.uncertainty_bootstrap_grid,
            'uncertainty_last_computed': self.uncertainty_last_computed,
            'mc_sigma_pixels': self.mc_sigma_pixels,
            'baseline_uncertainty_m': self.baseline_uncertainty_m,
            'gcp_suggestion_threshold': self.gcp_suggestion_threshold,
            'imported_geo_reference': self.imported_geo_reference,
            'enabled_sign_libraries': self.enabled_sign_libraries
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Project':
        """
        Create project from dictionary.

        Handles backward compatibility with older project versions.
        Old projects (v0.2.x) will be automatically migrated to v0.3.0 format.
        """
        # Check version and perform migration if needed
        metadata = data.get('metadata', {})
        version = metadata.get('version', '0.1.0')

        # Migration from v0.2.x/v0.3.0 to v0.3.1
        if version.startswith('0.2') or version.startswith('0.1') or version == '0.3.0':
            if version != '0.3.0':
                logger.info(f"Migrating project from version {version} to 0.3.1...")
            # Junction.from_dict() handles backward compatibility automatically
            # by providing empty lists for new fields (connecting_roads, lane_connections)
            # Polyline.from_dict() handles osm_node_ids (optional field, defaults to None)
            # Update metadata version
            metadata['version'] = '0.3.1'
            data['metadata'] = metadata
            if version != '0.3.0':
                logger.info("Migration complete. Junctions will have empty connection lists.")
                logger.info("Use 'Auto-Generate Connections' in junction dialogs to populate connections.")

        image_path = data.get('image_path')
        if image_path:
            image_path = Path(image_path)

        polylines = [Polyline.from_dict(p) for p in data.get('polylines', [])]
        roads = [Road.from_dict(r) for r in data.get('roads', [])]
        junctions = [Junction.from_dict(j) for j in data.get('junctions', [])]
        junction_groups = [JunctionGroup.from_dict(jg) for jg in data.get('junction_groups', [])]
        signals = [Signal.from_dict(s) for s in data.get('signals', [])]
        objects = [RoadObject.from_dict(o) for o in data.get('objects', [])]
        parking_spaces = [ParkingSpace.from_dict(p) for p in data.get('parking_spaces', [])]
        control_points = [ControlPoint.from_dict(cp) for cp in data.get('control_points', [])]

        return cls(
            image_path=image_path,
            polylines=polylines,
            roads=roads,
            junctions=junctions,
            junction_groups=junction_groups,
            signals=signals,
            objects=objects,
            parking_spaces=parking_spaces,
            control_points=control_points,
            right_hand_traffic=data.get('right_hand_traffic', True),
            transform_method=data.get('transform_method', 'affine'),  # Default to affine for old projects
            country_code=data.get('country_code', 'se'),
            map_name=data.get('map_name', ''),  # Default to empty string for backward compatibility
            openstreetmap_used=data.get('openstreetmap_used', False),  # Default to False
            junction_offset_distance_meters=data.get('junction_offset_distance_meters', 8.0),  # Default to 8.0m
            roundabout_ring_offset_distance_meters=data.get('roundabout_ring_offset_distance_meters',
                data.get('roundabout_offset_distance_meters', 4.0)),  # Backward compat with old field name
            roundabout_approach_offset_distance_meters=data.get('roundabout_approach_offset_distance_meters', 8.0),
            georef_validation=data.get('georef_validation', {}),
            uncertainty_grid_cache=data.get('uncertainty_grid_cache'),
            uncertainty_grid_resolution=tuple(data.get('uncertainty_grid_resolution', [50, 50])),
            uncertainty_bootstrap_grid=data.get('uncertainty_bootstrap_grid'),
            uncertainty_last_computed=data.get('uncertainty_last_computed'),
            mc_sigma_pixels=data.get('mc_sigma_pixels', 1.5),
            baseline_uncertainty_m=data.get('baseline_uncertainty_m', 0.05),
            gcp_suggestion_threshold=data.get('gcp_suggestion_threshold', 0.2),
            imported_geo_reference=data.get('imported_geo_reference'),
            enabled_sign_libraries=data.get('enabled_sign_libraries', ['se']),  # Default to Swedish library
            metadata=data.get('metadata', {})
        )

    def save(self, file_path: Path) -> None:
        """Save project to .orbit file."""
        file_path = Path(file_path)
        # Ensure .orbit extension
        if file_path.suffix not in ['.orbit', '.json']:
            file_path = file_path.with_suffix('.orbit')

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, file_path: Path) -> 'Project':
        """Load project from .orbit file."""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        project = cls.from_dict(data)
        # Clear any stale cross-junction road links (OpenDRIVE compliance)
        project.clear_cross_junction_road_links()
        return project

    def clear(self) -> None:
        """Clear all project data."""
        self.polylines.clear()
        self.roads.clear()
        self.junctions.clear()
        self.signals.clear()
        self.objects.clear()
        self.parking_spaces.clear()
        self.control_points.clear()
        self.image_path = None
        self.metadata = {
            'version': '0.3.1',
            'created': datetime.now().isoformat(),
            'modified': datetime.now().isoformat()
        }

    def clear_cross_junction_road_links(self) -> int:
        """
        Clear predecessor/successor links between roads that connect through junctions.

        In OpenDRIVE, roads connecting through a junction should NOT have direct
        predecessor/successor links to each other. This method clears any such
        stale links that may exist from older project versions.

        Returns:
            Number of links that were cleared
        """
        cleared_count = 0
        roads_dict = {road.id: road for road in self.roads}

        for junction in self.junctions:
            connected_ids = set(junction.connected_road_ids)

            for road_id in connected_ids:
                road = roads_dict.get(road_id)
                if not road:
                    continue

                # If predecessor is another road in this junction, clear it
                if road.predecessor_id and road.predecessor_id in connected_ids:
                    road.predecessor_id = None
                    cleared_count += 1

                # If successor is another road in this junction, clear it
                if road.successor_id and road.successor_id in connected_ids:
                    road.successor_id = None
                    cleared_count += 1

        if cleared_count > 0:
            logger.info(f"Cleared {cleared_count} stale cross-junction road link(s)")

        return cleared_count

    def __repr__(self) -> str:
        return (f"Project(polylines={len(self.polylines)}, roads={len(self.roads)}, "
                f"junctions={len(self.junctions)}, signals={len(self.signals)}, "
                f"objects={len(self.objects)}, control_points={len(self.control_points)})")

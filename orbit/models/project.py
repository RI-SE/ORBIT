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

from .polyline import Polyline
from .road import Road
from .junction import Junction
from .signal import Signal
from .object import RoadObject


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
            'is_validation': self.is_validation
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
    signals: List[Signal] = field(default_factory=list)
    objects: List[RoadObject] = field(default_factory=list)
    control_points: List[ControlPoint] = field(default_factory=list)
    right_hand_traffic: bool = True  # Default to right-hand traffic
    transform_method: str = 'homography'  # Default to homography for drone images
    country_code: str = 'se'  # Default to Sweden
    map_name: str = ''  # Name for OpenDrive export (defaults to image filename when loaded)
    openstreetmap_used: bool = False  # Flag for OpenStreetMap attribution
    georef_validation: Dict[str, Any] = field(default_factory=dict)
    uncertainty_grid_cache: Optional[List[List[float]]] = None  # Cached uncertainty grid
    uncertainty_grid_resolution: Tuple[int, int] = (50, 50)  # Grid resolution
    uncertainty_bootstrap_grid: Optional[List[List[float]]] = None  # Bootstrap analysis results
    uncertainty_last_computed: Optional[str] = None  # ISO timestamp of last computation
    mc_sigma_pixels: float = 1.5  # Measurement error for Monte Carlo (pixels)
    baseline_uncertainty_m: float = 0.05  # Baseline position uncertainty (meters)
    gcp_suggestion_threshold: float = 0.2  # Threshold for GCP suggestions (meters)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Initialize metadata if not provided."""
        if not self.metadata:
            self.metadata = {
                'version': '0.2.0',
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
            'signals': [s.to_dict() for s in self.signals],
            'objects': [o.to_dict() for o in self.objects],
            'control_points': [cp.to_dict() for cp in self.control_points],
            'right_hand_traffic': self.right_hand_traffic,
            'transform_method': self.transform_method,
            'country_code': self.country_code,
            'map_name': self.map_name,
            'openstreetmap_used': self.openstreetmap_used,
            'georef_validation': self.georef_validation,
            'uncertainty_grid_cache': self.uncertainty_grid_cache,
            'uncertainty_grid_resolution': self.uncertainty_grid_resolution,
            'uncertainty_bootstrap_grid': self.uncertainty_bootstrap_grid,
            'uncertainty_last_computed': self.uncertainty_last_computed,
            'mc_sigma_pixels': self.mc_sigma_pixels,
            'baseline_uncertainty_m': self.baseline_uncertainty_m,
            'gcp_suggestion_threshold': self.gcp_suggestion_threshold
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Project':
        """Create project from dictionary."""
        image_path = data.get('image_path')
        if image_path:
            image_path = Path(image_path)

        polylines = [Polyline.from_dict(p) for p in data.get('polylines', [])]
        roads = [Road.from_dict(r) for r in data.get('roads', [])]
        junctions = [Junction.from_dict(j) for j in data.get('junctions', [])]
        signals = [Signal.from_dict(s) for s in data.get('signals', [])]
        objects = [RoadObject.from_dict(o) for o in data.get('objects', [])]
        control_points = [ControlPoint.from_dict(cp) for cp in data.get('control_points', [])]

        return cls(
            image_path=image_path,
            polylines=polylines,
            roads=roads,
            junctions=junctions,
            signals=signals,
            objects=objects,
            control_points=control_points,
            right_hand_traffic=data.get('right_hand_traffic', True),
            transform_method=data.get('transform_method', 'affine'),  # Default to affine for old projects
            country_code=data.get('country_code', 'se'),
            map_name=data.get('map_name', ''),  # Default to empty string for backward compatibility
            openstreetmap_used=data.get('openstreetmap_used', False),  # Default to False
            georef_validation=data.get('georef_validation', {}),
            uncertainty_grid_cache=data.get('uncertainty_grid_cache'),
            uncertainty_grid_resolution=tuple(data.get('uncertainty_grid_resolution', [50, 50])),
            uncertainty_bootstrap_grid=data.get('uncertainty_bootstrap_grid'),
            uncertainty_last_computed=data.get('uncertainty_last_computed'),
            mc_sigma_pixels=data.get('mc_sigma_pixels', 1.5),
            baseline_uncertainty_m=data.get('baseline_uncertainty_m', 0.05),
            gcp_suggestion_threshold=data.get('gcp_suggestion_threshold', 0.2),
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
        return cls.from_dict(data)

    def clear(self) -> None:
        """Clear all project data."""
        self.polylines.clear()
        self.roads.clear()
        self.junctions.clear()
        self.signals.clear()
        self.objects.clear()
        self.control_points.clear()
        self.image_path = None
        self.metadata = {
            'version': '0.2.0',
            'created': datetime.now().isoformat(),
            'modified': datetime.now().isoformat()
        }

    def __repr__(self) -> str:
        return (f"Project(polylines={len(self.polylines)}, roads={len(self.roads)}, "
                f"junctions={len(self.junctions)}, signals={len(self.signals)}, "
                f"objects={len(self.objects)}, control_points={len(self.control_points)})")

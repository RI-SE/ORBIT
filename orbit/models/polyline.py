"""
Polyline data model for ORBIT.

Represents a polyline drawn on the image with pixel coordinates.
"""

from typing import List, Tuple, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
import uuid


class LineType(Enum):
    """Type of line in the road network."""
    CENTERLINE = "centerline"
    LANE_BOUNDARY = "lane_boundary"


class RoadMarkType(Enum):
    """ASAM OpenDRIVE e_roadMarkType enumeration."""
    NONE = "none"
    SOLID = "solid"
    BROKEN = "broken"
    SOLID_SOLID = "solid solid"
    SOLID_BROKEN = "solid broken"
    BROKEN_SOLID = "broken solid"
    BROKEN_BROKEN = "broken broken"
    BOTTS_DOTS = "botts dots"
    GRASS = "grass"
    CURB = "curb"
    CUSTOM = "custom"
    EDGE = "edge"


@dataclass
class GeometrySegment:
    """
    Preserved OpenDRIVE geometry metadata for a polyline segment.

    Stores the original geometry parameters from OpenDRIVE import so they
    can be reused on export if the polyline points haven't been modified.
    This enables round-trip fidelity for arcs, spirals, and parametric curves.

    Attributes:
        geom_type: Geometry type ("line", "arc", "spiral", "poly3", "paramPoly3")
        start_index: Starting point index in the polyline
        end_index: Ending point index in the polyline
        s_start: S-coordinate at start (meters in original OpenDRIVE)
        length: Length of segment (meters)
        heading: Starting heading (radians)
        curvature: Curvature for arcs (1/radius), start curvature for spirals
        curvature_end: End curvature for spirals (None for arcs/lines)
        poly_params: Dictionary of polynomial coefficients for poly3/paramPoly3
    """
    geom_type: str  # "line", "arc", "spiral", "poly3", "paramPoly3"
    start_index: int
    end_index: int
    s_start: float = 0.0
    length: float = 0.0
    heading: float = 0.0
    curvature: Optional[float] = None
    curvature_end: Optional[float] = None
    poly_params: Optional[Dict[str, float]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = {
            'geom_type': self.geom_type,
            'start_index': self.start_index,
            'end_index': self.end_index,
            's_start': self.s_start,
            'length': self.length,
            'heading': self.heading,
        }
        if self.curvature is not None:
            data['curvature'] = self.curvature
        if self.curvature_end is not None:
            data['curvature_end'] = self.curvature_end
        if self.poly_params is not None:
            data['poly_params'] = self.poly_params
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GeometrySegment':
        """Create from dictionary."""
        return cls(
            geom_type=data['geom_type'],
            start_index=data['start_index'],
            end_index=data['end_index'],
            s_start=data.get('s_start', 0.0),
            length=data.get('length', 0.0),
            heading=data.get('heading', 0.0),
            curvature=data.get('curvature'),
            curvature_end=data.get('curvature_end'),
            poly_params=data.get('poly_params'),
        )


@dataclass
class Polyline:
    """
    Represents a polyline with multiple points.

    Coordinates can be stored as:
    - pixel coordinates (points field) - used for display and manual drawing
    - geographic coordinates (geo_points field) - source of truth for imported data

    When geo_points is set, pixel coords can be recomputed via get_pixel_points()
    using a transformer. This enables adjustment of georeferencing alignment.

    Attributes:
        id: Unique identifier for this polyline
        points: List of (x, y) coordinates in pixels (for display/manual drawing)
        geo_points: List of (lon, lat) geographic coordinates (source of truth for imports)
        color: RGB color tuple for visualization (r, g, b)
        closed: Whether the polyline forms a closed loop
        line_type: Type of line (centerline or lane_boundary)
        road_mark_type: Road marking type (for OpenDRIVE export)
        elevations: Optional elevation values in meters for each point (from OpenDrive import)
        s_offsets: Optional s-coordinate values along polyline for each point (for display)
        opendrive_id: Optional OpenDrive road/element ID (for round-trip consistency)
        osm_node_ids: Optional OSM node IDs for each point (from OSM import, enables road splitting)
        geometry_segments: Preserved OpenDRIVE geometry metadata for round-trip fidelity
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    points: List[Tuple[float, float]] = field(default_factory=list)
    geo_points: Optional[List[Tuple[float, float]]] = None  # (lon, lat) pairs - source of truth
    color: Tuple[int, int, int] = (0, 255, 255)  # Default cyan for lane boundaries
    closed: bool = False
    line_type: LineType = LineType.LANE_BOUNDARY  # Default to lane boundary
    road_mark_type: RoadMarkType = RoadMarkType.SOLID  # Default to solid
    elevations: Optional[List[float]] = None  # Elevation in meters for each point (if available)
    s_offsets: Optional[List[float]] = None  # S-coordinate for each point (if available)
    opendrive_id: Optional[str] = None  # OpenDrive ID for round-trip import/export
    osm_node_ids: Optional[List[Optional[int]]] = None  # OSM node IDs for each point (from OSM import)
    geometry_segments: Optional[List[GeometrySegment]] = None  # Preserved geometry from OpenDRIVE import

    def add_point(self, x: float, y: float) -> None:
        """Add a point to the end of the polyline."""
        self.points.append((x, y))

    def insert_point(self, index: int, x: float, y: float) -> None:
        """Insert a point at the specified index."""
        self.points.insert(index, (x, y))

    def remove_point(self, index: int) -> None:
        """Remove a point at the specified index."""
        if 0 <= index < len(self.points):
            self.points.pop(index)

    def update_point(self, index: int, x: float, y: float) -> None:
        """Update the coordinates of a point at the specified index."""
        if 0 <= index < len(self.points):
            self.points[index] = (x, y)

    def get_point(self, index: int) -> Tuple[float, float]:
        """Get the coordinates of a point at the specified index."""
        return self.points[index]

    def point_count(self) -> int:
        """Return the number of points in the polyline."""
        return len(self.points)

    def is_valid(self) -> bool:
        """Check if the polyline has at least 2 points."""
        return len(self.points) >= 2

    def reverse(self) -> None:
        """
        Reverse the direction of the polyline.

        The point positions remain the same, but their order is reversed.
        This is useful for correcting the direction of centerlines.
        """
        self.points.reverse()
        # Also reverse geo_points if present
        if self.geo_points:
            self.geo_points.reverse()

    def has_geo_coords(self) -> bool:
        """Check if this polyline has geographic coordinates stored."""
        return self.geo_points is not None and len(self.geo_points) > 0

    def get_pixel_points(self, transformer=None) -> List[Tuple[float, float]]:
        """
        Get points in pixel coordinates.

        If geo_points are available and a transformer is provided,
        computes pixel coordinates from geo coordinates.
        Otherwise returns the stored pixel coordinates.

        Args:
            transformer: CoordinateTransformer for geo→pixel conversion

        Returns:
            List of (x, y) pixel coordinates
        """
        if self.geo_points and transformer:
            return [transformer.geo_to_pixel(lon, lat) for lon, lat in self.geo_points]
        return self.points

    def update_pixel_points_from_geo(self, transformer) -> None:
        """
        Update stored pixel points from geo coordinates using transformer.

        Call this after changing the transformer (e.g., adjustment) to
        update the cached pixel coordinates.

        Args:
            transformer: CoordinateTransformer for geo→pixel conversion
        """
        if self.geo_points and transformer:
            self.points = [transformer.geo_to_pixel(lon, lat) for lon, lat in self.geo_points]

    def to_dict(self) -> Dict[str, Any]:
        """Convert polyline to dictionary for JSON serialization."""
        data = {
            'id': self.id,
            'points': self.points,
            'color': self.color,
            'closed': bool(self.closed),
            'line_type': self.line_type.value,
            'road_mark_type': self.road_mark_type.value
        }
        # Only include optional fields if they are set
        if self.geo_points is not None:
            data['geo_points'] = self.geo_points
        if self.elevations is not None:
            data['elevations'] = self.elevations
        if self.s_offsets is not None:
            data['s_offsets'] = self.s_offsets
        if self.opendrive_id is not None:
            data['opendrive_id'] = self.opendrive_id
        if self.osm_node_ids is not None:
            data['osm_node_ids'] = self.osm_node_ids
        if self.geometry_segments is not None:
            data['geometry_segments'] = [seg.to_dict() for seg in self.geometry_segments]
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Polyline':
        """Create polyline from dictionary."""
        # Handle line_type
        line_type_str = data.get('line_type', 'lane_boundary')
        try:
            line_type = LineType(line_type_str)
        except ValueError:
            line_type = LineType.LANE_BOUNDARY

        # Handle road_mark_type
        road_mark_type_str = data.get('road_mark_type', 'solid')
        try:
            road_mark_type = RoadMarkType(road_mark_type_str)
        except ValueError:
            road_mark_type = RoadMarkType.SOLID

        # Handle geo_points - convert lists to tuples
        geo_points_raw = data.get('geo_points')
        geo_points = [tuple(p) for p in geo_points_raw] if geo_points_raw else None

        # Handle geometry_segments
        geometry_segments_raw = data.get('geometry_segments')
        geometry_segments = None
        if geometry_segments_raw:
            geometry_segments = [GeometrySegment.from_dict(seg) for seg in geometry_segments_raw]

        return cls(
            id=data.get('id', str(uuid.uuid4())),
            points=[tuple(p) for p in data.get('points', [])],
            geo_points=geo_points,
            color=tuple(data.get('color', (0, 255, 255))),
            closed=data.get('closed', False),
            line_type=line_type,
            road_mark_type=road_mark_type,
            elevations=data.get('elevations'),
            s_offsets=data.get('s_offsets'),
            opendrive_id=data.get('opendrive_id'),
            osm_node_ids=data.get('osm_node_ids'),
            geometry_segments=geometry_segments
        )

    def __repr__(self) -> str:
        return f"Polyline(id={self.id[:8]}..., points={len(self.points)})"

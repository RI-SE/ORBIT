"""
Parking space model for OpenDRIVE parking areas.

Represents individual parking spaces with access rules, dimensions, and orientation.
Supports both point-based (single space) and polygon-based (lot outline) representation.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class ParkingAccess(Enum):
    """
    OpenDRIVE parking access types.

    Defines who is allowed to use a parking space.
    """
    STANDARD = "standard"           # General public parking
    WOMEN = "women"                 # Women-only parking
    HANDICAPPED = "handicapped"     # Handicapped accessible
    DISABLED = "disabled"           # Disabled accessible (alias)
    RESERVED = "reserved"           # Reserved/permit only
    COMPANY = "company"             # Company/employee parking
    PERMIT = "permit"               # Permit holders only
    PRIVATE = "private"             # Private/restricted parking
    CUSTOMERS = "customers"         # Customer parking only
    RESIDENTS = "residents"         # Resident parking only


class ParkingType(Enum):
    """
    Type of parking facility.

    Used for visual distinction and OSM import mapping.
    """
    SURFACE = "surface"             # Ground-level parking lot
    UNDERGROUND = "underground"     # Underground parking garage
    MULTI_STOREY = "multi_storey"   # Multi-level parking structure
    ROOFTOP = "rooftop"            # Parking on building roof
    STREET = "street"               # Street/on-road parking
    CARPORTS = "carports"           # Covered parking structures


class ParkingSpace:
    """
    Represents a parking space or parking area.

    Can represent:
    - Individual parking spaces (point-based with dimensions)
    - Parking lot boundaries (polygon-based with geo_points)

    Coordinates can be stored as:
    - pixel coordinates (position/points fields) - used for display
    - geographic coordinates (geo_position/geo_points fields) - source of truth for imports

    Attributes:
        id: Unique identifier
        position: (x, y) pixel coordinates on the map
        geo_position: (lon, lat) geographic coordinates (source of truth)
        access: ParkingAccess type defining who can use the space
        restrictions: Free text describing additional restrictions
        parking_type: Type of parking (surface, underground, etc.)
        road_id: ID of the road this parking is assigned to
        name: Display name for the parking space
        width: Width in meters (perpendicular to parking direction)
        length: Length in meters (along parking direction)
        orientation: Angle in degrees (0 = east, 90 = north)
        z_offset: Height above ground in meters
        s_position: Position along road centerline (s-coordinate) in pixels
        t_offset: Lateral offset from road in pixels
        capacity: Number of parking spaces (for lots)
        points: List of (x, y) pixel coordinates for polygon outline
        geo_points: List of (lon, lat) geographic coordinates for polygon outline
    """

    def __init__(
        self,
        parking_id: Optional[str] = None,
        position: Tuple[float, float] = (0.0, 0.0),
        access: ParkingAccess = ParkingAccess.STANDARD,
        parking_type: ParkingType = ParkingType.SURFACE,
        road_id: Optional[str] = None,
        geo_position: Optional[Tuple[float, float]] = None
    ):
        self.id = parking_id or ""
        self.position = position
        self.geo_position = geo_position  # (lon, lat) - source of truth

        self.access = access
        self.restrictions = ""
        self.parking_type = parking_type
        self.road_id = road_id
        self.name = ""

        # Dimensions in meters
        self.width = 2.5    # Standard parking space width
        self.length = 5.0   # Standard parking space length
        self.orientation = 0.0  # Degrees (0 = east, 90 = north)
        self.z_offset = 0.0

        # Position relative to road
        self.s_position: Optional[float] = None  # pixels along road
        self.t_offset: Optional[float] = None    # pixels from centerline

        # For parking lots (polygon outline)
        self.capacity: Optional[int] = None
        self.points: List[Tuple[float, float]] = []  # pixel polygon
        self.geo_points: Optional[List[Tuple[float, float]]] = None  # geo polygon
        # Original OSM tags for round-trip export
        self.osm_tags: Optional[Dict[str, str]] = None

    def has_geo_coords(self) -> bool:
        """Check if this parking space has geographic coordinates stored."""
        if self.geo_points and len(self.geo_points) > 0:
            return True
        return self.geo_position is not None

    def is_polygon(self) -> bool:
        """Check if this parking is defined as a polygon (lot) vs point (single space)."""
        if len(self.points) >= 3:
            return True
        if self.geo_points and len(self.geo_points) >= 3:
            return True
        return False

    def get_pixel_position(self, transformer=None) -> Tuple[float, float]:
        """
        Get position in pixel coordinates.

        If geo_position is available and a transformer is provided,
        computes pixel coordinates from geo coordinates.

        Args:
            transformer: CoordinateTransformer for geo→pixel conversion

        Returns:
            (x, y) pixel coordinates
        """
        if self.geo_position and transformer:
            return transformer.geo_to_pixel(self.geo_position[0], self.geo_position[1])
        return self.position

    def get_pixel_points(self, transformer=None) -> List[Tuple[float, float]]:
        """
        Get polygon points in pixel coordinates.

        If geo_points are available and a transformer is provided,
        computes pixel coordinates from geo coordinates.

        Args:
            transformer: CoordinateTransformer for geo→pixel conversion

        Returns:
            List of (x, y) pixel coordinates
        """
        if self.geo_points and transformer:
            return [transformer.geo_to_pixel(lon, lat) for lon, lat in self.geo_points]
        return self.points

    def update_pixel_coords_from_geo(self, transformer) -> None:
        """
        Update stored pixel coords from geo coordinates using transformer.

        Call this after changing the transformer (e.g., adjustment) to
        update the cached pixel coordinates.

        Args:
            transformer: CoordinateTransformer for geo→pixel conversion
        """
        if self.geo_position and transformer:
            self.position = transformer.geo_to_pixel(self.geo_position[0], self.geo_position[1])
        if self.geo_points and transformer:
            self.points = [transformer.geo_to_pixel(lon, lat) for lon, lat in self.geo_points]

    def update_point(self, index: int, pixel_point: Tuple[float, float],
                     geo_point: Optional[Tuple[float, float]] = None):
        """Update a polygon vertex at the given index."""
        if 0 <= index < len(self.points):
            self.points[index] = pixel_point
        if self.geo_points is not None and 0 <= index < len(self.geo_points):
            if geo_point is not None:
                self.geo_points[index] = geo_point

    def insert_point(self, index: int, pixel_point: Tuple[float, float],
                     geo_point: Optional[Tuple[float, float]] = None):
        """Insert a polygon vertex at the given index."""
        self.points.insert(index, pixel_point)
        if self.geo_points is not None:
            self.geo_points.insert(index, geo_point if geo_point else (0.0, 0.0))

    def remove_point(self, index: int) -> bool:
        """Remove a polygon vertex (enforces minimum 3 points). Returns True on success."""
        if len(self.points) <= 3:
            return False
        self.points.pop(index)
        if self.geo_points is not None and index < len(self.geo_points):
            self.geo_points.pop(index)
        return True

    def get_display_name(self) -> str:
        """Get display name for UI."""
        if self.name:
            return self.name
        type_name = self.parking_type.value.replace('_', ' ').title()
        return f"Parking ({type_name})"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize parking space to dictionary for JSON storage."""
        data = {
            'id': self.id,
            'position': list(self.position),
            'access': self.access.value,
            'restrictions': self.restrictions,
            'parking_type': self.parking_type.value,
            'road_id': self.road_id,
            'name': self.name,
            'width': self.width,
            'length': self.length,
            'orientation': self.orientation,
            'z_offset': self.z_offset,
            's_position': self.s_position,
            't_offset': self.t_offset,
        }

        # Include geo coords if set
        if self.geo_position is not None:
            data['geo_position'] = list(self.geo_position)

        # Include polygon data if set
        if self.points:
            data['points'] = [list(p) for p in self.points]
        if self.geo_points is not None:
            data['geo_points'] = [list(p) for p in self.geo_points]

        # Optional fields
        if self.capacity is not None:
            data['capacity'] = self.capacity
        if self.osm_tags:
            data['osm_tags'] = self.osm_tags

        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ParkingSpace':
        """Deserialize parking space from dictionary."""
        # Handle geo_position - convert list to tuple if present
        geo_position_raw = data.get('geo_position')
        geo_position = tuple(geo_position_raw) if geo_position_raw else None

        # Parse enums
        access = ParkingAccess(data.get('access', 'standard'))
        parking_type = ParkingType(data.get('parking_type', 'surface'))

        space = cls(
            parking_id=data['id'],
            position=tuple(data.get('position', [0.0, 0.0])),
            access=access,
            parking_type=parking_type,
            road_id=data.get('road_id'),
            geo_position=geo_position
        )

        space.restrictions = data.get('restrictions', '')
        space.name = data.get('name', '')
        space.width = data.get('width', 2.5)
        space.length = data.get('length', 5.0)
        space.orientation = data.get('orientation', 0.0)
        space.z_offset = data.get('z_offset', 0.0)
        space.s_position = data.get('s_position')
        space.t_offset = data.get('t_offset')
        space.capacity = data.get('capacity')

        # Load polygon points
        if 'points' in data and data['points']:
            space.points = [tuple(p) for p in data['points']]
        geo_points_raw = data.get('geo_points')
        space.geo_points = [tuple(p) for p in geo_points_raw] if geo_points_raw else None
        # OSM tags
        space.osm_tags = data.get('osm_tags')

        return space

    def calculate_s_t_position(
        self, centerline_points: List[Tuple[float, float]],
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Calculate s-coordinate and t-offset along road centerline.

        Args:
            centerline_points: List of (x, y) points defining road centerline

        Returns:
            Tuple of (s_position, t_offset) or (None, None) if no centerline
        """
        if not centerline_points or len(centerline_points) < 2:
            return None, None

        import math

        # Use centroid for polygon, position for point
        if self.points:
            px = sum(p[0] for p in self.points) / len(self.points)
            py = sum(p[1] for p in self.points) / len(self.points)
        else:
            px, py = self.position

        # Find closest point on centerline
        min_dist = float('inf')
        closest_s = 0.0
        cumulative_s = 0.0

        for i in range(len(centerline_points) - 1):
            x1, y1 = centerline_points[i]
            x2, y2 = centerline_points[i + 1]

            # Vector from p1 to p2
            dx = x2 - x1
            dy = y2 - y1
            segment_len = math.sqrt(dx * dx + dy * dy)

            if segment_len < 1e-6:
                continue

            # Project point onto segment
            t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / (segment_len * segment_len)))
            proj_x = x1 + t * dx
            proj_y = y1 + t * dy

            dist = math.sqrt((px - proj_x) ** 2 + (py - proj_y) ** 2)

            if dist < min_dist:
                min_dist = dist
                closest_s = cumulative_s + t * segment_len

                # Calculate signed t-offset (positive = left of road)
                cross = dx * (py - y1) - dy * (px - x1)
                t_offset = -min_dist if cross > 0 else min_dist

            cumulative_s += segment_len

        return closest_s, t_offset if min_dist < float('inf') else None

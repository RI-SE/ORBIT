"""
Object model for roadside objects (lampposts, buildings, trees, etc.).

Represents physical objects placed on the map with position, type, and properties.
"""

from enum import Enum
from typing import Dict, List, Optional, Tuple

from orbit.utils.enum_formatting import format_enum_name


class ObjectType(Enum):
    """
    Type of roadside object.

    To add a new object type:
    1. Add the enum value here (e.g., TREE_PALM = "tree_palm")
    2. Add it to the appropriate category in get_category()
    3. Add default dimensions in get_default_dimensions()
    4. Add shape type in get_shape_type()
    5. Update ObjectSelectionDialog to include the new type in the UI
    """
    LAMPPOST = "lamppost"
    GUARDRAIL = "guardrail"
    BUILDING = "building"
    TREE_BROADLEAF = "tree_broadleaf"
    TREE_CONIFER = "tree_conifer"
    BUSH = "bush"
    # Land use / natural area types (for OSM import of area polygons)
    LANDUSE_FOREST = "landuse_forest"
    LANDUSE_FARMLAND = "landuse_farmland"
    LANDUSE_MEADOW = "landuse_meadow"
    LANDUSE_SCRUB = "landuse_scrub"
    NATURAL_WATER = "natural_water"
    NATURAL_WETLAND = "natural_wetland"
    # Parking types (for OSM import of parking facilities)
    PARKING_SURFACE = "parking_surface"
    PARKING_UNDERGROUND = "parking_underground"
    PARKING_MULTI_STOREY = "parking_multi_storey"
    PARKING_ROOFTOP = "parking_rooftop"

    def get_category(self) -> str:
        """
        Get the OpenDRIVE category this object type belongs to.

        Categories:
        - "road_furniture": Lampposts, guardrails, signs, etc.
        - "road_environment": Buildings, trees, bushes, etc.

        Returns:
            Category name as string
        """
        if self in (ObjectType.LAMPPOST, ObjectType.GUARDRAIL):
            return "road_furniture"
        elif self in (ObjectType.BUILDING, ObjectType.TREE_BROADLEAF,
                     ObjectType.TREE_CONIFER, ObjectType.BUSH):
            return "road_environment"
        elif self in (ObjectType.LANDUSE_FOREST, ObjectType.LANDUSE_FARMLAND,
                     ObjectType.LANDUSE_MEADOW, ObjectType.LANDUSE_SCRUB,
                     ObjectType.NATURAL_WATER, ObjectType.NATURAL_WETLAND):
            return "land_use"
        elif self in (ObjectType.PARKING_SURFACE, ObjectType.PARKING_UNDERGROUND,
                     ObjectType.PARKING_MULTI_STOREY, ObjectType.PARKING_ROOFTOP):
            return "parking"
        return "none"

    def get_default_dimensions(self) -> Dict[str, float]:
        """
        Get default dimensions in meters for this object type.

        Returns dict with keys depending on shape:
        - Cylinder/Circle: {radius, height}
        - Rectangle: {width, length, height}
        - Cone: {radius, height}

        Returns:
            Dictionary with dimension keys and values in meters
        """
        defaults = {
            ObjectType.LAMPPOST: {"radius": 0.15, "height": 6.0},
            ObjectType.GUARDRAIL: {"height": 1.0, "width": 0.3},
            ObjectType.BUILDING: {"width": 10.0, "length": 8.0, "height": 6.0},
            ObjectType.TREE_BROADLEAF: {"radius": 2.5, "height": 8.0},
            ObjectType.TREE_CONIFER: {"radius": 1.5, "height": 12.0},
            ObjectType.BUSH: {"radius": 1.0, "height": 1.5},
            # Land use areas - polygon-based, dimensions are placeholders
            ObjectType.LANDUSE_FOREST: {"width": 100.0, "length": 100.0, "height": 0.0},
            ObjectType.LANDUSE_FARMLAND: {"width": 100.0, "length": 100.0, "height": 0.0},
            ObjectType.LANDUSE_MEADOW: {"width": 100.0, "length": 100.0, "height": 0.0},
            ObjectType.LANDUSE_SCRUB: {"width": 100.0, "length": 100.0, "height": 0.0},
            ObjectType.NATURAL_WATER: {"width": 100.0, "length": 100.0, "height": 0.0},
            ObjectType.NATURAL_WETLAND: {"width": 100.0, "length": 100.0, "height": 0.0},
            # Parking facilities - polygon-based, dimensions are lot size
            ObjectType.PARKING_SURFACE: {"width": 50.0, "length": 30.0, "height": 0.0},
            ObjectType.PARKING_UNDERGROUND: {"width": 50.0, "length": 30.0, "height": 3.0},
            ObjectType.PARKING_MULTI_STOREY: {"width": 40.0, "length": 40.0, "height": 12.0},
            ObjectType.PARKING_ROOFTOP: {"width": 30.0, "length": 20.0, "height": 0.0},
        }
        return defaults.get(self, {"radius": 1.0, "height": 1.0})

    def get_shape_type(self) -> str:
        """
        Get the geometric shape type for this object.

        Shape types:
        - "cylinder": Lamppost (circle outline, vertical cylinder)
        - "polyline": Guardrail (line with multiple points)
        - "rectangle": Building (rectangular outline)
        - "circle": Trees and bush (circular outline)
        - "cone": Conifer (cone-shaped outline from top view)

        Returns:
            Shape type as string
        """
        shape_map = {
            ObjectType.LAMPPOST: "cylinder",
            ObjectType.GUARDRAIL: "polyline",
            ObjectType.BUILDING: "rectangle",
            ObjectType.TREE_BROADLEAF: "circle",
            ObjectType.TREE_CONIFER: "cone",
            ObjectType.BUSH: "circle",
            # Land use - polygon outlines
            ObjectType.LANDUSE_FOREST: "polygon",
            ObjectType.LANDUSE_FARMLAND: "polygon",
            ObjectType.LANDUSE_MEADOW: "polygon",
            ObjectType.LANDUSE_SCRUB: "polygon",
            ObjectType.NATURAL_WATER: "polygon",
            ObjectType.NATURAL_WETLAND: "polygon",
            # Parking - polygon outlines
            ObjectType.PARKING_SURFACE: "polygon",
            ObjectType.PARKING_UNDERGROUND: "polygon",
            ObjectType.PARKING_MULTI_STOREY: "polygon",
            ObjectType.PARKING_ROOFTOP: "polygon",
        }
        return shape_map.get(self, "rectangle")

    def has_orientation(self) -> bool:
        """
        Check if this object type supports orientation (rotation angle).

        Returns:
            True if object can be rotated (building, lamppost)
        """
        return self in (ObjectType.BUILDING, ObjectType.LAMPPOST)

    def supports_validity_length(self) -> bool:
        """
        Check if this object type supports validity length (span along road).

        Returns:
            True if object can span along road (guardrail)
        """
        return self == ObjectType.GUARDRAIL


class RoadObject:
    """
    Represents a roadside object (lamppost, building, tree, etc.).

    Coordinates can be stored as:
    - pixel coordinates (position/points fields) - used for display and manual placement
    - geographic coordinates (geo_position/geo_points fields) - source of truth for imported data

    When geo coords are set, pixel coords can be recomputed via get_pixel_position()/get_pixel_points()
    using a transformer. This enables adjustment of georeferencing alignment.

    Attributes:
        id: Unique identifier
        position: (x, y) pixel coordinates on the map (for point objects)
        geo_position: (lon, lat) geographic coordinates (source of truth for point objects)
        points: List of (x, y) coordinates for polyline objects (guardrails)
        geo_points: List of (lon, lat) geographic coordinates (source of truth for polyline objects)
        type: ObjectType enum value
        name: Custom label for the object
        orientation: Angle in degrees (0 = right, 90 = up) - only for building/lamppost
        z_offset: Height above ground in meters
        dimensions: Dictionary with dimension values (radius, width, length, height)
        road_id: ID of the road this object is assigned to
        s_position: Position along road centerline (s-coordinate) in pixels
        t_offset: Lateral offset from road in pixels
        validity_length: Length along road (for guardrails) in pixels, or None
        pitch: Pitch angle in radians (OpenDRIVE attribute)
        roll: Roll angle in radians (OpenDRIVE attribute)
    """

    def __init__(
        self,
        object_id: Optional[str] = None,
        position: Tuple[float, float] = (0.0, 0.0),
        object_type: ObjectType = ObjectType.BUILDING,
        road_id: Optional[str] = None,
        geo_position: Optional[Tuple[float, float]] = None
    ):
        self.id = object_id or ""
        self.position = position
        self.geo_position = geo_position  # (lon, lat) - source of truth for point objects
        self.points: List[Tuple[float, float]] = []  # For guardrails
        self.geo_points: Optional[List[Tuple[float, float]]] = None  # (lon, lat) pairs for polyline objects
        self.type = object_type
        self.name = ""
        self.orientation = 0.0  # Degrees (only for building/lamppost)
        self.z_offset = 0.0  # Height above ground

        # Get default dimensions for this type
        self.dimensions = object_type.get_default_dimensions()

        self.road_id = road_id
        self.s_position: Optional[float] = None
        self.t_offset: Optional[float] = None
        self.validity_length: Optional[float] = None  # For guardrails
        # OpenDRIVE orientation angles for round-trip preservation
        self.pitch: float = 0.0  # Pitch angle in radians
        self.roll: float = 0.0  # Roll angle in radians
        # Original OSM tags for round-trip export
        self.osm_tags: Optional[Dict[str, str]] = None

    def has_geo_coords(self) -> bool:
        """Check if this object has geographic coordinates stored."""
        if self.type.get_shape_type() == "polyline":
            return self.geo_points is not None and len(self.geo_points) > 0
        return self.geo_position is not None

    def get_pixel_position(self, transformer=None) -> Tuple[float, float]:
        """
        Get position in pixel coordinates (for point objects).

        If geo_position is available and a transformer is provided,
        computes pixel coordinates from geo coordinates.
        Otherwise returns the stored pixel coordinates.

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
        Get points in pixel coordinates (for polyline objects like guardrails).

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

    def to_dict(self) -> dict:
        """Serialize object to dictionary for JSON storage."""
        data = {
            'id': self.id,
            'position': list(self.position),
            'points': [list(p) for p in self.points] if self.points else [],
            'type': self.type.value,
            'name': self.name,
            'orientation': self.orientation,
            'z_offset': self.z_offset,
            'dimensions': self.dimensions,
            'road_id': self.road_id,
            's_position': self.s_position,
            't_offset': self.t_offset,
            'validity_length': self.validity_length
        }
        # Include geo coords if set
        if self.geo_position is not None:
            data['geo_position'] = list(self.geo_position)
        if self.geo_points is not None:
            data['geo_points'] = [list(p) for p in self.geo_points]
        # Only include optional fields if set (backward compatibility)
        if self.pitch != 0.0:
            data['pitch'] = self.pitch
        if self.roll != 0.0:
            data['roll'] = self.roll
        if self.osm_tags:
            data['osm_tags'] = self.osm_tags
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'RoadObject':
        """Deserialize object from dictionary."""
        # Handle geo_position - convert list to tuple if present
        geo_position_raw = data.get('geo_position')
        geo_position = tuple(geo_position_raw) if geo_position_raw else None

        obj = cls(
            object_id=data['id'],
            position=tuple(data.get('position', [0.0, 0.0])),
            object_type=ObjectType(data['type']),
            road_id=data.get('road_id'),
            geo_position=geo_position
        )

        # Load points for polyline objects
        if 'points' in data and data['points']:
            obj.points = [tuple(p) for p in data['points']]

        # Load geo_points - convert lists to tuples if present
        geo_points_raw = data.get('geo_points')
        obj.geo_points = [tuple(p) for p in geo_points_raw] if geo_points_raw else None

        obj.name = data.get('name', '')
        obj.orientation = data.get('orientation', 0.0)
        obj.z_offset = data.get('z_offset', 0.0)

        # Load dimensions, using defaults for missing values
        default_dims = obj.type.get_default_dimensions()
        obj.dimensions = {**default_dims, **data.get('dimensions', {})}

        obj.s_position = data.get('s_position')
        obj.t_offset = data.get('t_offset')
        obj.validity_length = data.get('validity_length')
        # OpenDRIVE orientation angles
        obj.pitch = data.get('pitch', 0.0)
        obj.roll = data.get('roll', 0.0)
        # OSM tags
        obj.osm_tags = data.get('osm_tags')

        return obj

    def get_display_name(self) -> str:
        """Get display name for UI."""
        if self.name:
            return self.name
        return format_enum_name(self.type)

    def calculate_s_t_position(
        self, centerline_points: List[Tuple[float, float]],
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Calculate s-coordinate and t-offset along road centerline.

        For point objects, uses self.position.
        For polyline objects (guardrails), uses the first point.

        Args:
            centerline_points: List of (x, y) points defining road centerline

        Returns:
            Tuple of (s_position, t_offset) or (None, None) if no centerline
        """
        if not centerline_points or len(centerline_points) < 2:
            return None, None

        # Use first point for polyline objects, position for point objects
        if self.points:
            px, py = self.points[0]
        else:
            px, py = self.position

        # Find closest point on centerline
        min_dist = float('inf')
        closest_segment_idx = 0
        closest_t = 0.0
        closest_proj = (0.0, 0.0)

        for i in range(len(centerline_points) - 1):
            x1, y1 = centerline_points[i]
            x2, y2 = centerline_points[i + 1]

            # Project point onto segment
            dx, dy = x2 - x1, y2 - y1
            length_sq = dx * dx + dy * dy

            if length_sq == 0:
                t = 0
            else:
                t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / length_sq))

            proj_x = x1 + t * dx
            proj_y = y1 + t * dy

            dist = ((px - proj_x) ** 2 + (py - proj_y) ** 2) ** 0.5

            if dist < min_dist:
                min_dist = dist
                closest_segment_idx = i
                closest_t = t
                closest_proj = (proj_x, proj_y)

        # Calculate cumulative distance up to closest segment (s-coordinate)
        s = 0.0
        for i in range(closest_segment_idx):
            x1, y1 = centerline_points[i]
            x2, y2 = centerline_points[i + 1]
            s += ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5

        # Add distance within closest segment
        x1, y1 = centerline_points[closest_segment_idx]
        x2, y2 = centerline_points[closest_segment_idx + 1]
        segment_length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        s += closest_t * segment_length

        # Calculate t-offset (lateral distance from centerline)
        # Positive to the left, negative to the right (in direction of travel)
        proj_x, proj_y = closest_proj
        dx = x2 - x1
        dy = y2 - y1

        # Cross product to determine side
        cross = (px - proj_x) * dy - (py - proj_y) * dx
        t_offset = min_dist if cross >= 0 else -min_dist

        return s, t_offset

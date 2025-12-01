"""
Signal model for traffic signs and signals.

Represents traffic signals placed on the map with position, type, and properties.
"""

from enum import Enum, auto
from typing import Optional, Tuple
import uuid

from orbit.utils.enum_formatting import format_enum_name


class SignalType(Enum):
    """
    Type of traffic signal.

    To add a new signal type:
    1. Add the enum value here (e.g., STOP = "stop")
    2. Add it to the appropriate category in get_category()
    3. If it's a new category, add default dimensions in get_default_dimensions()
    4. Update SignalSelectionDialog to include the new type in the UI
    """
    GIVE_WAY = "give_way"
    SPEED_LIMIT = "speed_limit"
    STOP = "stop"
    NO_ENTRY = "no_entry"
    PRIORITY_ROAD = "priority_road"
    END_OF_SPEED_LIMIT = "end_of_speed_limit"
    TRAFFIC_SIGNALS = "traffic_signals"

    def get_category(self) -> str:
        """
        Get the category this signal type belongs to.

        Categories group signal types with similar characteristics and defaults.
        Current categories:
        - "regulatory": Regulatory signs (give way, stop, no entry, priority)
        - "speed_limit": Speed limit signs
        - "signals": Traffic signals (traffic lights)
        - "other": Fallback for uncategorized types

        Returns:
            Category name as string
        """
        if self in (SignalType.GIVE_WAY, SignalType.STOP, SignalType.NO_ENTRY,
                    SignalType.PRIORITY_ROAD):
            return "regulatory"
        elif self in (SignalType.SPEED_LIMIT, SignalType.END_OF_SPEED_LIMIT):
            return "speed_limit"
        elif self == SignalType.TRAFFIC_SIGNALS:
            return "signals"
        return "other"

    def get_default_dimensions(self) -> Tuple[float, float]:
        """
        Get default (width, height) dimensions in meters for this signal type.

        Based on Swedish road sign standards:
        - Regulatory signs: 0.9m × 0.9m (stop, give way, no entry, priority)
        - Speed limit signs: 0.6m × 0.6m
        - Traffic signals: 0.3m × 0.9m (standard traffic light housing)

        To add a new category's defaults, add an entry to the 'defaults' dict below.

        Returns:
            Tuple of (width, height) in meters
        """
        category = self.get_category()

        # Default dimensions by category (Swedish standards)
        # Add new categories here:
        defaults = {
            "regulatory": (0.9, 0.9),    # Regulatory signs (stop, give way, etc.)
            "speed_limit": (0.6, 0.6),   # Speed limit signs
            "signals": (0.3, 0.9),       # Traffic lights
            "other": (0.6, 0.6),         # Fallback
        }

        return defaults.get(category, (0.6, 0.6))


class SpeedUnit(Enum):
    """Unit for speed limit values."""
    KMH = "km/h"
    MPH = "mph"


class Signal:
    """
    Represents a traffic signal (sign) placed on the map.

    Attributes:
        id: Unique identifier
        position: (x, y) pixel coordinates on the map
        type: SignalType enum value
        value: Speed value for speed limits (30-120), None for other types
        speed_unit: Unit for speed value (km/h or mph)
        road_id: ID of the road this signal is assigned to
        name: Custom label for the signal
        orientation: OpenDRIVE orientation ('+' for forward, '-' for backward, 'none' for both)
        h_offset: Heading offset in radians, relative to perpendicular direction (OpenDRIVE hOffset)
        z_offset: Height of signal mounting above ground in meters (OpenDRIVE zOffset)
        sign_width: Physical width of the sign in meters (OpenDRIVE width)
        sign_height: Physical height of the sign in meters (OpenDRIVE height)
        s_position: Position along road centerline (s-coordinate) in pixels
        validity_range: (s_start, s_end) range in pixels, or None for point signal
        opendrive_id: Optional OpenDrive signal ID (for round-trip consistency)
    """

    def __init__(
        self,
        signal_id: Optional[str] = None,
        position: Tuple[float, float] = (0.0, 0.0),
        signal_type: SignalType = SignalType.GIVE_WAY,
        value: Optional[int] = None,
        speed_unit: SpeedUnit = SpeedUnit.KMH,
        road_id: Optional[str] = None
    ):
        self.id = signal_id or str(uuid.uuid4())
        self.position = position
        self.type = signal_type
        self.value = value  # Speed value if speed limit
        self.speed_unit = speed_unit
        self.road_id = road_id
        self.name = ""
        self.orientation = '+'  # OpenDRIVE orientation: '+', '-', or 'none'
        self.h_offset = 0.0  # Heading offset in radians relative to perpendicular
        self.z_offset = 2.0  # Height above ground in meters (OpenDRIVE zOffset)
        # Sign dimensions based on type category (Swedish standard)
        default_width, default_height = signal_type.get_default_dimensions()
        self.sign_width = default_width
        self.sign_height = default_height
        self.s_position = None  # Position along road
        self.validity_range = None  # (s_start, s_end) or None
        self.opendrive_id = None  # OpenDrive ID for round-trip import/export

    def to_dict(self) -> dict:
        """Serialize signal to dictionary for JSON storage."""
        data = {
            'id': self.id,
            'position': list(self.position),
            'type': self.type.value,
            'value': self.value,
            'speed_unit': self.speed_unit.value,
            'road_id': self.road_id,
            'name': self.name,
            'orientation': self.orientation,
            'h_offset': self.h_offset,
            'z_offset': self.z_offset,
            'sign_width': self.sign_width,
            'sign_height': self.sign_height,
            's_position': self.s_position,
            'validity_range': list(self.validity_range) if self.validity_range else None
        }
        # Only include optional field if set
        if self.opendrive_id is not None:
            data['opendrive_id'] = self.opendrive_id
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'Signal':
        """Deserialize signal from dictionary."""
        signal = cls(
            signal_id=data['id'],
            position=tuple(data['position']),
            signal_type=SignalType(data['type']),
            value=data.get('value'),
            speed_unit=SpeedUnit(data.get('speed_unit', 'km/h')),
            road_id=data.get('road_id')
        )
        signal.name = data.get('name', '')

        # Orientation - handle backward compatibility
        orientation_data = data.get('orientation', '+')
        if isinstance(orientation_data, str):
            # New format: OpenDRIVE orientation string
            signal.orientation = orientation_data
        else:
            # Old format: numeric degrees - convert to OpenDRIVE format
            # Old orientation was absolute angle, default to forward orientation
            signal.orientation = '+'

        # h_offset - new field with backward compatibility
        if 'h_offset' in data:
            signal.h_offset = data['h_offset']
        else:
            # Old projects didn't have h_offset
            # If we have old numeric orientation, we could try to convert it,
            # but it's safer to default to 0.0 (perpendicular to road)
            signal.h_offset = 0.0

        # Backward compatibility: old 'height' → 'z_offset', old 'width' → 'sign_width'
        if 'z_offset' in data:
            signal.z_offset = data['z_offset']
        else:
            signal.z_offset = data.get('height', 2.0)  # Old projects used 'height'

        # Get category-based defaults for this signal type
        default_width, default_height = signal.type.get_default_dimensions()

        if 'sign_width' in data:
            signal.sign_width = data['sign_width']
        else:
            # Try old 'width' field, otherwise use category defaults
            signal.sign_width = data.get('width', default_width)

        if 'sign_height' in data:
            signal.sign_height = data['sign_height']
        else:
            # New field, use category defaults
            signal.sign_height = default_height

        signal.s_position = data.get('s_position')
        signal.validity_range = tuple(data['validity_range']) if data.get('validity_range') else None
        signal.opendrive_id = data.get('opendrive_id')
        return signal

    def get_display_name(self) -> str:
        """Get display name for UI."""
        if self.name:
            return self.name
        if self.type == SignalType.SPEED_LIMIT and self.value:
            return f"Speed {self.value} {self.speed_unit.value}"
        return format_enum_name(self.type)

    def get_orientation_ui_string(self) -> str:
        """
        Convert OpenDRIVE orientation to UI-friendly string.

        Returns:
            'forward', 'backward', or 'both'
        """
        if self.orientation == '+':
            return 'forward'
        elif self.orientation == '-':
            return 'backward'
        else:
            return 'both'

    def set_orientation_from_ui_string(self, ui_string: str):
        """
        Set OpenDRIVE orientation from UI-friendly string.

        Args:
            ui_string: 'forward', 'backward', or 'both'
        """
        if ui_string == 'forward':
            self.orientation = '+'
        elif ui_string == 'backward':
            self.orientation = '-'
        else:
            self.orientation = 'none'

    def get_h_offset_degrees(self) -> float:
        """
        Get heading offset in degrees for UI display.

        Returns:
            Heading offset in degrees
        """
        import math
        return math.degrees(self.h_offset)

    def set_h_offset_from_degrees(self, degrees: float):
        """
        Set heading offset from degrees (for UI input).

        Args:
            degrees: Heading offset in degrees
        """
        import math
        self.h_offset = math.radians(degrees)

    def calculate_visual_angle(self, centerline_points: list) -> float:
        """
        Calculate visual display angle for this signal based on road geometry.

        The visual angle is: road_tangent_angle + 90° + h_offset
        - Perpendicular to road by default (h_offset = 0)
        - Adjusted by h_offset for custom rotations
        - Flipped 180° for backward-facing signals

        Args:
            centerline_points: List of (x, y) points defining road centerline

        Returns:
            Visual angle in degrees for display (0 = right, 90 = up, etc.)
        """
        if not centerline_points or len(centerline_points) < 2:
            # No road reference - use h_offset relative to north
            import math
            return 90.0 + math.degrees(self.h_offset)

        # Find closest segment
        min_dist = float('inf')
        closest_segment_idx = 0
        px, py = self.position

        for i in range(len(centerline_points) - 1):
            x1, y1 = centerline_points[i]
            x2, y2 = centerline_points[i + 1]

            # Distance from point to line segment
            dist = self._point_to_segment_distance(px, py, x1, y1, x2, y2)
            if dist < min_dist:
                min_dist = dist
                closest_segment_idx = i

        # Get tangent vector of closest segment
        x1, y1 = centerline_points[closest_segment_idx]
        x2, y2 = centerline_points[closest_segment_idx + 1]
        dx, dy = x2 - x1, y2 - y1

        # Calculate angle of tangent (road direction)
        import math
        road_angle = math.degrees(math.atan2(dy, dx))

        # Determine which side of road signal is on
        cross = (px - x1) * dy - (py - y1) * dx
        on_left_side = cross >= 0

        # Base angle: perpendicular to road
        if on_left_side:
            base_angle = road_angle + 90  # Perpendicular pointing left
        else:
            base_angle = road_angle - 90  # Perpendicular pointing right

        # Apply h_offset rotation
        visual_angle = base_angle + math.degrees(self.h_offset)

        # For backward orientation, flip 180°
        if self.orientation == '-':
            visual_angle += 180

        # Normalize to [0, 360)
        while visual_angle < 0:
            visual_angle += 360
        while visual_angle >= 360:
            visual_angle -= 360

        return visual_angle

    def calculate_s_position(self, centerline_points: list) -> Optional[float]:
        """
        Calculate s-coordinate along road centerline.

        Args:
            centerline_points: List of (x, y) points defining road centerline

        Returns:
            Distance along centerline to closest point, or None if no centerline
        """
        if not centerline_points or len(centerline_points) < 2:
            return None

        # Find closest point on centerline
        min_dist = float('inf')
        closest_segment_idx = 0
        closest_t = 0.0
        px, py = self.position

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

        # Calculate cumulative distance up to closest segment
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

        return s

    def _point_to_segment_distance(self, px: float, py: float,
                                   x1: float, y1: float,
                                   x2: float, y2: float) -> float:
        """Calculate distance from point to line segment."""
        dx, dy = x2 - x1, y2 - y1
        length_sq = dx * dx + dy * dy

        if length_sq == 0:
            return ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5

        t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / length_sq))
        proj_x = x1 + t * dx
        proj_y = y1 + t * dy

        return ((px - proj_x) ** 2 + (py - proj_y) ** 2) ** 0.5

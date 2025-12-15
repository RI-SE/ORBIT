"""
Signal model for traffic signs and signals.

Represents traffic signals placed on the map with position, type, and properties.
"""

from enum import Enum, auto
from typing import Optional, Tuple, List
import uuid

from orbit.utils.enum_formatting import format_enum_name


class SignalType(Enum):
    """
    Type of traffic signal.

    LIBRARY_SIGN and CUSTOM are the primary types for new signals.
    Legacy types (GIVE_WAY, SPEED_LIMIT, etc.) are kept for backward
    compatibility when loading old projects - they are automatically
    migrated to LIBRARY_SIGN when loaded.

    To add new signs, add them to a sign library instead of this enum.
    """
    # Primary types for new signals
    LIBRARY_SIGN = "library_sign"  # Sign from a loaded library
    CUSTOM = "custom"  # Custom OpenDRIVE type/subtype codes

    # Legacy types (kept for backward compatibility with old projects)
    GIVE_WAY = "give_way"
    SPEED_LIMIT = "speed_limit"
    STOP = "stop"
    NO_ENTRY = "no_entry"
    PRIORITY_ROAD = "priority_road"
    END_OF_SPEED_LIMIT = "end_of_speed_limit"
    TRAFFIC_SIGNALS = "traffic_signals"

    def is_legacy_type(self) -> bool:
        """Check if this is a legacy type that should be migrated."""
        return self not in (SignalType.LIBRARY_SIGN, SignalType.CUSTOM)

    def get_category(self) -> str:
        """
        Get the category this signal type belongs to.

        For LIBRARY_SIGN and CUSTOM types, returns "other" - actual category
        comes from the library definition.

        Categories group signal types with similar characteristics and defaults.
        Current categories:
        - "regulatory": Regulatory signs (give way, stop, no entry, priority)
        - "speed_limit": Speed limit signs
        - "signals": Traffic signals (traffic lights)
        - "other": Fallback for uncategorized types

        Returns:
            Category name as string
        """
        if self in (SignalType.LIBRARY_SIGN, SignalType.CUSTOM):
            return "other"
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
        type: SignalType enum value (LIBRARY_SIGN, CUSTOM, or legacy types)
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
        dynamic: OpenDRIVE dynamic flag ("yes" for traffic lights, "no" for static signs)
        subtype: OpenDRIVE subtype code (preserved for round-trip)
        country: Country code (e.g., "SE" for Sweden)
        library_id: Sign library ID (e.g., "se") for LIBRARY_SIGN type
        sign_id: Sign ID within library (e.g., "B1", "C31-50") for LIBRARY_SIGN type
        custom_type: Custom OpenDRIVE type code for CUSTOM type
        custom_subtype: Custom OpenDRIVE subtype code for CUSTOM type
        validity_lanes: List of lane IDs this signal applies to (None = all lanes)
    """

    def __init__(
        self,
        signal_id: Optional[str] = None,
        position: Tuple[float, float] = (0.0, 0.0),
        signal_type: SignalType = SignalType.LIBRARY_SIGN,
        value: Optional[int] = None,
        speed_unit: SpeedUnit = SpeedUnit.KMH,
        road_id: Optional[str] = None,
        library_id: Optional[str] = None,
        sign_id: Optional[str] = None
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
        # OpenDRIVE attributes for round-trip preservation
        self.dynamic = "no"  # "yes" for traffic lights, "no" for static signs
        self.subtype = ""  # OpenDRIVE subtype code
        self.country = ""  # Country code (e.g., "SE")
        # Library-based sign fields
        self.library_id = library_id  # Sign library ID (e.g., "se")
        self.sign_id = sign_id  # Sign ID within library (e.g., "B1", "C31-50")
        # Custom OpenDRIVE codes (for CUSTOM type)
        self.custom_type: Optional[str] = None
        self.custom_subtype: Optional[str] = None
        # Lane validity - list of lane IDs this signal applies to (None = all lanes)
        self.validity_lanes: Optional[List[int]] = None

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
        # Only include optional fields if set (backward compatibility)
        if self.opendrive_id is not None:
            data['opendrive_id'] = self.opendrive_id
        if self.dynamic != "no":
            data['dynamic'] = self.dynamic
        if self.subtype:
            data['subtype'] = self.subtype
        if self.country:
            data['country'] = self.country
        # Library-based sign fields
        if self.library_id:
            data['library_id'] = self.library_id
        if self.sign_id:
            data['sign_id'] = self.sign_id
        # Custom OpenDRIVE codes
        if self.custom_type:
            data['custom_type'] = self.custom_type
        if self.custom_subtype:
            data['custom_subtype'] = self.custom_subtype
        # Lane validity
        if self.validity_lanes is not None:
            data['validity_lanes'] = self.validity_lanes
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'Signal':
        """
        Deserialize signal from dictionary.

        Handles backward compatibility and auto-migration of legacy signal types
        to LIBRARY_SIGN type.
        """
        # Parse the signal type
        signal_type = SignalType(data['type'])
        library_id = data.get('library_id')
        sign_id = data.get('sign_id')
        value = data.get('value')

        # Auto-migrate legacy types to LIBRARY_SIGN
        if signal_type.is_legacy_type() and not library_id:
            # Import here to avoid circular import
            from .sign_library_manager import get_legacy_library_mapping
            migrated_lib_id, migrated_sign_id = get_legacy_library_mapping(
                signal_type.value, value
            )
            if migrated_lib_id and migrated_sign_id:
                library_id = migrated_lib_id
                sign_id = migrated_sign_id
                signal_type = SignalType.LIBRARY_SIGN

        signal = cls(
            signal_id=data['id'],
            position=tuple(data['position']),
            signal_type=signal_type,
            value=value,
            speed_unit=SpeedUnit(data.get('speed_unit', 'km/h')),
            road_id=data.get('road_id'),
            library_id=library_id,
            sign_id=sign_id
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
        # OpenDRIVE round-trip attributes
        signal.dynamic = data.get('dynamic', 'no')
        signal.subtype = data.get('subtype', '')
        signal.country = data.get('country', '')
        # Custom OpenDRIVE codes
        signal.custom_type = data.get('custom_type')
        signal.custom_subtype = data.get('custom_subtype')
        # Lane validity
        signal.validity_lanes = data.get('validity_lanes')
        return signal

    def get_display_name(self) -> str:
        """Get display name for UI."""
        if self.name:
            return self.name
        if self.type == SignalType.LIBRARY_SIGN and self.library_id and self.sign_id:
            # Try to get name from library
            from .sign_library_manager import SignLibraryManager
            manager = SignLibraryManager.instance()
            sign_def = manager.get_sign_definition(self.library_id, self.sign_id)
            if sign_def:
                return sign_def.get_display_name()
            return self.sign_id
        if self.type == SignalType.CUSTOM:
            if self.custom_type:
                return f"Custom ({self.custom_type})"
            return "Custom Signal"
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

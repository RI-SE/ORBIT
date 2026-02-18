"""
Mappings between OpenStreetMap tags and ORBIT/OpenDrive constructs.
"""

from typing import Optional

from orbit.models.lane import LaneType
from orbit.models.object import ObjectType
from orbit.models.parking import ParkingAccess, ParkingType
from orbit.models.signal import SignalType

# OSM highway types to OpenDrive road types
OSM_TO_OPENDRIVE_ROAD_TYPE = {
    'motorway': 'motorway',
    'motorway_link': 'motorway',
    'trunk': 'rural',
    'trunk_link': 'rural',
    'primary': 'rural',
    'primary_link': 'rural',
    'secondary': 'rural',
    'secondary_link': 'rural',
    'tertiary': 'town',
    'tertiary_link': 'town',
    'unclassified': 'rural',
    'residential': 'town',
    'living_street': 'town',
    'service': 'town',
    'road': 'rural',  # Unknown type, default to rural
}

# Default lane widths by road type (meters)
DEFAULT_LANE_WIDTHS = {
    'motorway': 3.75,
    'trunk': 3.5,
    'primary': 3.5,
    'secondary': 3.25,
    'tertiary': 3.0,
    'residential': 3.0,
    'service': 2.75,
    'living_street': 2.5,
    'default': 3.5,
}

# Speed limits by road type (km/h) - used if maxspeed tag missing
DEFAULT_SPEED_LIMITS = {
    'motorway': 110,
    'trunk': 90,
    'primary': 70,
    'secondary': 60,
    'tertiary': 50,
    'residential': 30,
    'service': 20,
    'living_street': 20,
    'default': 50,
}

# OSM traffic sign types to ORBIT SignalType
# Modular structure allows easy addition of country-specific signs

# Swedish traffic sign codes (SE:)
OSM_SIGN_SWEDEN = {
    'SE:B3': SignalType.STOP,
    'SE:B4': SignalType.GIVE_WAY,
    'SE:C2': SignalType.NO_ENTRY,
    'SE:B5': SignalType.PRIORITY_ROAD,
    'SE:C31': SignalType.SPEED_LIMIT,
    'SE:C32': SignalType.SPEED_LIMIT,
    'SE:C33': SignalType.END_OF_SPEED_LIMIT,
}

# German traffic sign codes (DE:) - for backward compatibility
OSM_SIGN_GERMANY = {
    'DE:205': SignalType.STOP,
    'DE:206': SignalType.GIVE_WAY,
    'DE:267': SignalType.NO_ENTRY,
    'DE:301': SignalType.PRIORITY_ROAD,
    'DE:274': SignalType.SPEED_LIMIT,
    'DE:274-': SignalType.SPEED_LIMIT,  # Speed limit with bracket
    'DE:278': SignalType.END_OF_SPEED_LIMIT,
}

# Add more countries here as needed:
# OSM_SIGN_UK = {...}
# OSM_SIGN_US = {...}

# Combined mapping (merge all country dictionaries)
OSM_SIGN_TO_SIGNAL_TYPE = {
    **OSM_SIGN_SWEDEN,
    **OSM_SIGN_GERMANY,
    'maxspeed': SignalType.SPEED_LIMIT,
}

# Highway tag values that represent traffic control features
# These are international (not country-specific)
OSM_HIGHWAY_SIGN_TYPES = {
    'give_way': SignalType.GIVE_WAY,
    'stop': SignalType.STOP,
    'traffic_signals': SignalType.TRAFFIC_SIGNALS,
}

# OSM maxspeed formats
# Examples: "50", "50 km/h", "30 mph", "DE:urban"
def parse_maxspeed(maxspeed_str: str) -> tuple[int | None, str]:
    """
    Parse OSM maxspeed tag.

    Args:
        maxspeed_str: Value of maxspeed tag

    Returns:
        Tuple of (speed_value, unit) or (None, 'kmh') if unparseable
    """
    if not maxspeed_str:
        return None, 'kmh'

    maxspeed_str = maxspeed_str.strip().lower()

    # Handle special values
    if maxspeed_str in ['none', 'unlimited', 'signals', 'variable']:
        return None, 'kmh'

    # Country-specific defaults
    if 'urban' in maxspeed_str:
        return 50, 'kmh'
    if 'rural' in maxspeed_str:
        return 100, 'kmh'

    # Parse numeric value
    import re
    match = re.search(r'(\d+)', maxspeed_str)
    if not match:
        return None, 'kmh'

    value = int(match.group(1))

    # Determine unit
    if 'mph' in maxspeed_str:
        unit = 'mph'
    else:
        unit = 'kmh'  # Default to km/h

    return value, unit


# OSM object types to ORBIT ObjectType
OSM_TO_OBJECT_TYPE = {
    # Highway furniture
    'highway=street_lamp': ObjectType.LAMPPOST,
    'barrier=guard_rail': ObjectType.GUARDRAIL,

    # Natural features
    'natural=tree': ObjectType.TREE_BROADLEAF,  # Default, refine if species tag exists
    'natural=tree+leaf_type=broadleaved': ObjectType.TREE_BROADLEAF,
    'natural=tree+leaf_type=needleleaved': ObjectType.TREE_CONIFER,

    # Buildings
    'building': ObjectType.BUILDING,

    # Vegetation
    'natural=scrub': ObjectType.BUSH,
    'natural=bush': ObjectType.BUSH,
}

# Default object dimensions (meters)
OBJECT_DEFAULT_DIMENSIONS = {
    ObjectType.LAMPPOST: {'radius': 0.15, 'height': 6.0},
    ObjectType.GUARDRAIL: {'height': 0.8},  # Width determined by polyline
    ObjectType.TREE_BROADLEAF: {'radius': 0.3, 'height': 10.0},
    ObjectType.TREE_CONIFER: {'radius': 0.25, 'height': 12.0},
    ObjectType.BUSH: {'radius': 0.5, 'height': 1.5},
    ObjectType.BUILDING: {'width': 10.0, 'length': 10.0, 'height': 6.0},  # Will be refined from geometry
}


def get_lane_width_for_highway(highway_type: str, user_default: float = 3.5) -> float:
    """
    Get appropriate lane width for a highway type.

    Args:
        highway_type: OSM highway tag value
        user_default: User-configured default width

    Returns:
        Lane width in meters
    """
    # Use OSM-specific defaults, fallback to user default
    return DEFAULT_LANE_WIDTHS.get(highway_type, user_default)


def get_road_type_for_highway(highway_type: str) -> str:
    """
    Get OpenDrive road type for OSM highway type.

    Args:
        highway_type: OSM highway tag value

    Returns:
        OpenDrive road type string
    """
    return OSM_TO_OPENDRIVE_ROAD_TYPE.get(highway_type, 'town')


def should_import_highway(highway_type: str) -> bool:
    """
    Check if highway type should be imported as a road.

    Now includes paths, footways, and cycleways for bicycle/pedestrian infrastructure.
    Excludes only: steps, pedestrian areas, bridleways, corridors, construction.

    Args:
        highway_type: OSM highway tag value

    Returns:
        True if should be imported
    """
    excluded_types = {
        'steps', 'pedestrian',
        'bridleway', 'corridor', 'construction', 'proposed'
    }
    return highway_type not in excluded_types


def get_signal_type_from_osm(tags: dict) -> SignalType | None:
    """
    Determine ORBIT signal type from OSM tags.

    Priority order:
    1. highway tag (give_way, stop, traffic_signals) - international standard
    2. traffic_sign tag (country-specific codes like SE:B3, DE:205)
    3. maxspeed tag (speed limit sign)

    Args:
        tags: OSM element tags dictionary

    Returns:
        SignalType or None if not recognized
    """
    # Check highway tag first (international standard)
    highway = tags.get('highway')
    if highway in OSM_HIGHWAY_SIGN_TYPES:
        return OSM_HIGHWAY_SIGN_TYPES[highway]

    # Check traffic_sign tag (country-specific codes)
    if 'traffic_sign' in tags:
        sign_value = tags['traffic_sign']
        # Handle multiple signs separated by semicolon
        for sign in sign_value.split(';'):
            sign = sign.strip()
            if sign in OSM_SIGN_TO_SIGNAL_TYPE:
                return OSM_SIGN_TO_SIGNAL_TYPE[sign]
            # Check if it's a speed limit sign (various formats)
            # Swedish: C31, C32; German: 274
            if 'maxspeed' in sign.lower() or '274' in sign or 'C31' in sign or 'C32' in sign:
                return SignalType.SPEED_LIMIT

    # Check for maxspeed node (speed limit sign)
    if 'maxspeed' in tags:
        return SignalType.SPEED_LIMIT

    return None


def get_object_type_from_osm(tags: dict) -> ObjectType | None:
    """
    Determine ORBIT object type from OSM tags.

    Args:
        tags: OSM element tags dictionary

    Returns:
        ObjectType or None if not recognized
    """
    # Check highway furniture
    if tags.get('highway') == 'street_lamp':
        return ObjectType.LAMPPOST

    # Check barriers
    if tags.get('barrier') == 'guard_rail':
        return ObjectType.GUARDRAIL

    # Check natural features
    if tags.get('natural') == 'tree':
        # Refine by leaf type if available
        leaf_type = tags.get('leaf_type', '').lower()
        if leaf_type == 'needleleaved':
            return ObjectType.TREE_CONIFER
        else:
            return ObjectType.TREE_BROADLEAF

    if tags.get('natural') in ['scrub', 'bush']:
        return ObjectType.BUSH

    # Check buildings
    if 'building' in tags:
        return ObjectType.BUILDING

    return None


def estimate_lane_count(tags: dict, is_oneway: bool) -> tuple[int, int]:
    """
    Estimate lane count from OSM tags.

    Args:
        tags: OSM way tags
        is_oneway: Whether the road is oneway

    Returns:
        Tuple of (left_lanes, right_lanes) relative to direction of way
        For oneway roads, returns (0, lanes) - all lanes on right side
    """
    # Try explicit lane tags
    if 'lanes' in tags:
        try:
            total_lanes = int(tags['lanes'])
        except ValueError:
            total_lanes = 1
    else:
        # Estimate from highway type
        highway = tags.get('highway', 'residential')
        if highway in ['motorway', 'trunk']:
            total_lanes = 4
        elif highway in ['primary', 'secondary']:
            total_lanes = 2
        else:
            total_lanes = 1

    if is_oneway:
        # All lanes on right side (in direction of way)
        return 0, total_lanes

    # Check for directional lane tags
    lanes_forward = tags.get('lanes:forward')
    lanes_backward = tags.get('lanes:backward')

    if lanes_forward and lanes_backward:
        try:
            right_lanes = int(lanes_forward)
            left_lanes = int(lanes_backward)
            return left_lanes, right_lanes
        except ValueError:
            pass

    # For single-lane two-way roads, create one lane on each side
    # (representing bi-directional traffic sharing)
    if total_lanes == 1:
        return 1, 1

    # Split evenly, with extra lane on right for odd numbers
    left_lanes = total_lanes // 2
    right_lanes = total_lanes - left_lanes

    return left_lanes, right_lanes


def is_oneway(tags: dict) -> bool:
    """
    Check if road is oneway.

    Args:
        tags: OSM way tags

    Returns:
        True if oneway
    """
    oneway = tags.get('oneway', 'no').lower()

    # Motorways and their links are typically oneway
    highway = tags.get('highway', '')
    if highway in ['motorway', 'motorway_link']:
        # Unless explicitly marked as not oneway
        if oneway == 'no':
            return False
        return True

    # Check oneway tag
    return oneway in ['yes', 'true', '1', '-1']


def is_reverse_oneway(tags: dict) -> bool:
    """
    Check if oneway road is in reverse direction.

    Args:
        tags: OSM way tags

    Returns:
        True if oneway=-1 (reverse direction)
    """
    return tags.get('oneway', 'no') == '-1'


def get_path_type_and_lane_type(tags: dict) -> tuple[str, LaneType] | None:
    """
    Determine path type and OpenDRIVE lane type from OSM tags.

    Identifies bicycle paths, pedestrian paths, and shared-use paths.
    Returns appropriate naming and lane type for OpenDRIVE export.

    Args:
        tags: OSM way tags dictionary

    Returns:
        Tuple of (road_name_prefix, LaneType) or None if not a recognized path

    Examples:
        highway=cycleway → ('Bicycle Path', LaneType.BIKING)
        highway=footway → ('Pedestrian Path', LaneType.SIDEWALK)
        highway=path + bicycle=designated + foot=designated → ('Shared Cycle/Pedestrian Path', LaneType.BIKING)
    """
    highway = tags.get('highway')

    if highway == 'cycleway':
        return ('Bicycle Path', LaneType.BIKING)

    if highway == 'footway':
        return ('Pedestrian Path', LaneType.SIDEWALK)

    if highway == 'path':
        bicycle_designated = tags.get('bicycle') == 'designated'
        foot_designated = tags.get('foot') == 'designated'

        if bicycle_designated and foot_designated:
            # Shared path - use biking type (OpenDRIVE doesn't have "shared")
            # Note segregation status in road name
            segregated = tags.get('segregated', 'no')
            if segregated == 'yes':
                return ('Segregated Cycle/Pedestrian Path', LaneType.BIKING)
            else:
                return ('Shared Cycle/Pedestrian Path', LaneType.BIKING)
        elif bicycle_designated:
            return ('Bicycle Path', LaneType.BIKING)
        elif foot_designated:
            return ('Pedestrian Path', LaneType.SIDEWALK)

    return None


def parse_turn_lanes(turn_lanes_str: str) -> list[list[str]]:
    """
    Parse OSM turn:lanes tag into list of turn directions per lane.

    The turn:lanes tag uses '|' to separate lanes and ';' to separate
    multiple directions for the same lane.

    Args:
        turn_lanes_str: Value of turn:lanes tag (e.g., "left|through;left|through|right")

    Returns:
        List of lists, where each inner list contains turn directions for that lane.
        Index 0 is the leftmost lane. Empty strings indicate no turn restriction.

    Examples:
        "left|through|right" -> [["left"], ["through"], ["right"]]
        "left|through;left|through|right" -> [["left"], ["through", "left"], ["through"], ["right"]]
        "none|through|through;right" -> [["none"], ["through"], ["through", "right"]]
    """
    if not turn_lanes_str:
        return []

    result = []
    lanes = turn_lanes_str.split('|')
    for lane_str in lanes:
        # Split by semicolon for multiple directions
        directions = [d.strip().lower() for d in lane_str.split(';') if d.strip()]
        # Normalize direction names
        normalized = []
        for d in directions:
            # Map various OSM turn values to standard names
            if d in ('left', 'sharp_left', 'slight_left'):
                normalized.append('left')
            elif d in ('right', 'sharp_right', 'slight_right'):
                normalized.append('right')
            elif d in ('through', 'straight'):
                normalized.append('through')
            elif d == 'reverse':
                normalized.append('reverse')
            elif d == 'merge_to_left':
                normalized.append('merge_left')
            elif d == 'merge_to_right':
                normalized.append('merge_right')
            elif d in ('none', ''):
                normalized.append('none')
            else:
                # Keep unknown values as-is
                normalized.append(d)
        result.append(normalized if normalized else ['none'])

    return result


# OSM surface values to OpenDrive material properties
# Maps to (friction, roughness, surface_name)
OSM_SURFACE_TO_MATERIAL = {
    'asphalt': (0.9, 0.01, 'asphalt'),
    'concrete': (0.8, 0.02, 'concrete'),
    'paved': (0.85, 0.015, 'asphalt'),  # Generic paved
    'unpaved': (0.5, 0.05, 'gravel'),
    'gravel': (0.5, 0.05, 'gravel'),
    'fine_gravel': (0.55, 0.04, 'gravel'),
    'compacted': (0.6, 0.03, 'gravel'),
    'cobblestone': (0.7, 0.04, 'cobblestone'),
    'sett': (0.7, 0.035, 'cobblestone'),
    'paving_stones': (0.75, 0.025, 'cobblestone'),
    'dirt': (0.4, 0.06, 'dirt'),
    'earth': (0.4, 0.06, 'dirt'),
    'ground': (0.4, 0.06, 'dirt'),
    'grass': (0.35, 0.08, 'grass'),
    'sand': (0.3, 0.07, 'sand'),
    'wood': (0.6, 0.02, 'wood'),
    'metal': (0.7, 0.01, 'metal'),
}


def get_surface_material(surface_tag: str) -> tuple[float, float, str] | None:
    """
    Get OpenDrive material properties from OSM surface tag.

    Args:
        surface_tag: Value of OSM surface tag

    Returns:
        Tuple of (friction, roughness, surface_name) or None if unknown
    """
    if not surface_tag:
        return None

    surface_tag = surface_tag.strip().lower()
    return OSM_SURFACE_TO_MATERIAL.get(surface_tag)


def get_path_width_from_osm(tags: dict, lane_type: LaneType) -> float:
    """
    Get path width in meters from OSM tags or defaults.

    Checks for explicit width tag first, otherwise uses sensible defaults
    based on path type.

    Args:
        tags: OSM way tags
        lane_type: LaneType (BIKING, SIDEWALK, or WALKING)

    Returns:
        Width in meters

    Default widths (per lane, paths use symmetric left+right lanes):
        - Bicycle/shared path: 1.5m per lane (3.0m total)
        - Pedestrian/walking: 1.0m per lane (2.0m total)
    """
    # Check for explicit width tag (this is total width, divide by 2 for per-lane)
    if 'width' in tags:
        try:
            width_str = tags['width']
            # Handle formats like "3", "3m", "3 m"
            width_str = width_str.replace('m', '').replace(' ', '').strip()
            total_width = float(width_str)
            return total_width / 2.0  # Return per-lane width
        except ValueError:
            pass

    # Defaults based on lane type (per-lane width)
    if lane_type == LaneType.BIKING:
        return 1.5  # Per-lane width for bicycle/shared paths
    elif lane_type in (LaneType.SIDEWALK, LaneType.WALKING):
        return 1.0  # Per-lane width for pedestrian paths

    # Fallback
    return 1.5


# OSM parking type to ORBIT ParkingType
OSM_PARKING_TYPE_MAP = {
    'surface': ParkingType.SURFACE,
    'underground': ParkingType.UNDERGROUND,
    'multi-storey': ParkingType.MULTI_STOREY,
    'rooftop': ParkingType.ROOFTOP,
    'street_side': ParkingType.STREET,
    'on_street': ParkingType.STREET,
    'carports': ParkingType.CARPORTS,
}

# OSM access tag to ORBIT ParkingAccess
OSM_PARKING_ACCESS_MAP = {
    'yes': ParkingAccess.STANDARD,
    'public': ParkingAccess.STANDARD,
    'customers': ParkingAccess.CUSTOMERS,
    'private': ParkingAccess.PRIVATE,
    'permit': ParkingAccess.PERMIT,
    'residents': ParkingAccess.RESIDENTS,
    'disabled': ParkingAccess.DISABLED,
    'no': ParkingAccess.PRIVATE,  # No access = private
}


def get_landuse_type_from_osm(tags: dict) -> Optional[ObjectType]:
    """Determine ORBIT land use ObjectType from OSM tags.

    Separate from get_object_type_from_osm() to avoid conflicts with
    node-level mappings (e.g. natural=scrub -> BUSH for nodes).

    Args:
        tags: OSM element tags dictionary

    Returns:
        ObjectType for land use areas, or None if not recognized
    """
    landuse = tags.get('landuse')
    if landuse == 'forest':
        return ObjectType.LANDUSE_FOREST
    if landuse == 'farmland':
        return ObjectType.LANDUSE_FARMLAND
    if landuse in ('meadow', 'grass'):
        return ObjectType.LANDUSE_MEADOW

    natural = tags.get('natural')
    if natural == 'wood':
        return ObjectType.LANDUSE_FOREST
    if natural == 'water':
        return ObjectType.NATURAL_WATER
    if natural == 'wetland':
        return ObjectType.NATURAL_WETLAND
    if natural in ('scrub', 'heath'):
        return ObjectType.LANDUSE_SCRUB

    if tags.get('waterway') == 'riverbank' or 'water' in tags:
        return ObjectType.NATURAL_WATER

    return None


def get_parking_type_from_osm(tags: dict) -> Optional[ParkingType]:
    """
    Determine parking type from OSM tags.

    Args:
        tags: OSM element tags dictionary

    Returns:
        ParkingType or None if not a parking facility
    """
    # Check for amenity=parking
    if tags.get('amenity') != 'parking':
        return None

    # Get parking type from 'parking' tag
    parking_type = tags.get('parking', 'surface')
    return OSM_PARKING_TYPE_MAP.get(parking_type, ParkingType.SURFACE)


def get_parking_access_from_osm(tags: dict) -> ParkingAccess:
    """
    Determine parking access type from OSM tags.

    Args:
        tags: OSM element tags dictionary

    Returns:
        ParkingAccess type
    """
    # Check for specific access tags
    access = tags.get('access', 'yes')

    # Check for fee-based parking
    if tags.get('fee') == 'yes':
        # Fee-based but public
        return ParkingAccess.STANDARD

    # Check for specific user restrictions
    if tags.get('parking:women') == 'yes' or 'women' in access.lower():
        return ParkingAccess.WOMEN

    if tags.get('disabled') == 'yes' or tags.get('wheelchair') == 'designated':
        return ParkingAccess.DISABLED

    return OSM_PARKING_ACCESS_MAP.get(access.lower(), ParkingAccess.STANDARD)

"""
Reverse mappings from ORBIT models to OSM tags for OSM XML export.

Used as fallback when original osm_tags are not available (e.g., manually created roads).
When osm_tags are preserved from import, those take priority over these mappings.
"""

from typing import Dict, List, Optional

from orbit.models.lane import Lane
from orbit.models.object import ObjectType, RoadObject
from orbit.models.parking import ParkingSpace, ParkingType
from orbit.models.road import Road, RoadType
from orbit.models.signal import Signal, SignalType

# Reverse mapping: RoadType -> OSM highway tag value
# This is the inverse of OSM_TO_OPENDRIVE_ROAD_TYPE in orbit/import/osm_mappings.py.
# Where multiple OSM types map to one RoadType, we pick the most common.
ROAD_TYPE_TO_OSM_HIGHWAY = {
    RoadType.MOTORWAY: 'motorway',
    RoadType.RURAL: 'secondary',
    RoadType.TOWN: 'residential',
    RoadType.LOW_SPEED: 'living_street',
    RoadType.PEDESTRIAN: 'pedestrian',
    RoadType.BICYCLE: 'cycleway',
    RoadType.TOWN_EXPRESSWAY: 'trunk',
    RoadType.TOWN_COLLECTOR: 'tertiary',
    RoadType.TOWN_ARTERIAL: 'primary',
    RoadType.TOWN_PRIVATE: 'service',
    RoadType.TOWN_LOCAL: 'residential',
    RoadType.TOWN_PLAY_STREET: 'living_street',
    RoadType.UNKNOWN: 'road',
}

# Reverse mapping: ObjectType -> OSM tags
OBJECT_TYPE_TO_OSM_TAGS = {
    ObjectType.LAMPPOST: {'highway': 'street_lamp'},
    ObjectType.GUARDRAIL: {'barrier': 'guard_rail'},
    ObjectType.TREE_BROADLEAF: {'natural': 'tree', 'leaf_type': 'broadleaved'},
    ObjectType.TREE_CONIFER: {'natural': 'tree', 'leaf_type': 'needleleaved'},
    ObjectType.BUSH: {'natural': 'scrub'},
    ObjectType.BUILDING: {'building': 'yes'},
    # Land use areas
    ObjectType.LANDUSE_FOREST: {'landuse': 'forest'},
    ObjectType.LANDUSE_FARMLAND: {'landuse': 'farmland'},
    ObjectType.LANDUSE_MEADOW: {'landuse': 'meadow'},
    ObjectType.LANDUSE_SCRUB: {'natural': 'scrub'},
    ObjectType.NATURAL_WATER: {'natural': 'water'},
    ObjectType.NATURAL_WETLAND: {'natural': 'wetland'},
}

# Reverse mapping: ParkingType -> OSM tags
PARKING_TYPE_TO_OSM_TAGS = {
    ParkingType.SURFACE: {'amenity': 'parking', 'parking': 'surface'},
    ParkingType.UNDERGROUND: {'amenity': 'parking', 'parking': 'underground'},
    ParkingType.MULTI_STOREY: {'amenity': 'parking', 'parking': 'multi-storey'},
    ParkingType.ROOFTOP: {'amenity': 'parking', 'parking': 'rooftop'},
    ParkingType.STREET: {'amenity': 'parking', 'parking': 'street_side'},
    ParkingType.CARPORTS: {'amenity': 'parking', 'parking': 'carports'},
}


def _apply_lane_tags(road: Road, tags: Dict[str, str]) -> None:
    """Update lane count and width tags from ORBIT model data.

    Sets lanes, lanes:forward/backward, width, and width:lanes:forward/backward.
    Right lanes (negative IDs) map to OSM forward, left lanes (positive IDs) to backward.
    """
    # Lane counts
    total = road.lane_info.left_count + road.lane_info.right_count
    if total != 2:
        tags['lanes'] = str(total)
    if road.lane_info.left_count != road.lane_info.right_count:
        tags['lanes:forward'] = str(road.lane_info.right_count)
        tags['lanes:backward'] = str(road.lane_info.left_count)

    # Lane widths from first lane section
    if not road.lane_sections:
        return

    section = road.lane_sections[0]
    right_lanes: List[Lane] = sorted(
        [l for l in section.lanes if l.id < 0], key=lambda l: abs(l.id)
    )
    left_lanes: List[Lane] = sorted(
        [l for l in section.lanes if l.id > 0], key=lambda l: l.id
    )

    all_widths: List[float] = []

    if right_lanes:
        widths = [l.width for l in right_lanes]
        all_widths.extend(widths)
        tags['width:lanes:forward'] = '|'.join(f'{w:.1f}' for w in widths)

    if left_lanes:
        widths = [l.width for l in left_lanes]
        all_widths.extend(widths)
        tags['width:lanes:backward'] = '|'.join(f'{w:.1f}' for w in widths)

    if all_widths:
        tags['width'] = f'{sum(all_widths):.1f}'


def get_osm_tags_for_road(road: Road) -> Dict[str, str]:
    """Get OSM tags for a road, preferring preserved osm_tags over fallback mapping.

    Lane count and width tags are always updated from ORBIT model data,
    even when osm_tags are preserved, since the user may have edited them.
    """
    if road.osm_tags:
        tags = dict(road.osm_tags)
    else:
        tags: Dict[str, str] = {}
        tags['highway'] = ROAD_TYPE_TO_OSM_HIGHWAY.get(road.road_type, 'road')

        if road.name and road.name != 'Unnamed Road':
            tags['name'] = road.name
        if road.speed_limit is not None:
            tags['maxspeed'] = str(int(road.speed_limit))

    _apply_lane_tags(road, tags)
    return tags


def get_osm_tags_for_object(obj: RoadObject) -> Dict[str, str]:
    """Get OSM tags for a road object, preferring preserved osm_tags."""
    if obj.osm_tags:
        return dict(obj.osm_tags)

    tags = dict(OBJECT_TYPE_TO_OSM_TAGS.get(obj.type, {}))
    if obj.name and not obj.name.startswith('OSM '):
        tags['name'] = obj.name
    return tags


def get_osm_tags_for_signal(signal: Signal) -> Dict[str, str]:
    """Get OSM tags for a signal, preferring preserved osm_tags."""
    if signal.osm_tags:
        return dict(signal.osm_tags)

    tags: Dict[str, str] = {}
    if signal.type == SignalType.TRAFFIC_SIGNALS:
        tags['highway'] = 'traffic_signals'
    elif signal.type == SignalType.STOP:
        tags['highway'] = 'stop'
    elif signal.type == SignalType.GIVE_WAY:
        tags['highway'] = 'give_way'
    elif signal.type == SignalType.SPEED_LIMIT and signal.value:
        tags['highway'] = 'speed_limit'  # Not standard OSM but preserves info
        tags['maxspeed'] = str(signal.value)
    elif signal.type == SignalType.LIBRARY_SIGN:
        # Best-effort: mark as traffic sign
        tags['highway'] = 'traffic_signals'
        if signal.sign_id:
            tags['traffic_sign'] = signal.sign_id
    else:
        tags['highway'] = 'traffic_signals'

    if signal.name and not signal.name.startswith('OSM '):
        tags['name'] = signal.name
    return tags


def get_osm_tags_for_parking(parking: ParkingSpace) -> Dict[str, str]:
    """Get OSM tags for a parking space, preferring preserved osm_tags."""
    if parking.osm_tags:
        return dict(parking.osm_tags)

    tags = dict(PARKING_TYPE_TO_OSM_TAGS.get(parking.parking_type, {'amenity': 'parking'}))
    if parking.name and not parking.name.startswith('Parking '):
        tags['name'] = parking.name
    if parking.capacity is not None:
        tags['capacity'] = str(parking.capacity)
    return tags

"""
OpenDrive XML parser for ORBIT.

Parses ASAM OpenDrive format XML files and extracts road network data.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from lxml import etree


class GeometryType(Enum):
    """OpenDrive planView geometry types."""
    LINE = "line"
    ARC = "arc"
    SPIRAL = "spiral"
    POLY3 = "poly3"
    PARAM_POLY3 = "paramPoly3"


@dataclass
class GeometryElement:
    """
    Represents a geometry element from OpenDrive planView.

    Attributes:
        s: Start position along road (meters)
        x: Start x coordinate (meters)
        y: Start y coordinate (meters)
        hdg: Start heading/orientation (radians)
        length: Length of geometry element (meters)
        geometry_type: Type of geometry (line, arc, spiral, etc.)
        params: Type-specific parameters (e.g., curvature for arc)
    """
    s: float
    x: float
    y: float
    hdg: float
    length: float
    geometry_type: GeometryType
    params: Dict[str, float] = field(default_factory=dict)


@dataclass
class ElevationProfile:
    """
    Represents elevation profile for a road.

    Attributes:
        elevations: List of (s, a, b, c, d) tuples for elevation polynomial
                   elevation(ds) = a + b*ds + c*ds² + d*ds³
    """
    elevations: List[Tuple[float, float, float, float, float]] = field(default_factory=list)

    def get_elevation_at(self, s: float) -> Optional[float]:
        """
        Calculate elevation at given s-coordinate.

        Args:
            s: S-coordinate along road (meters)

        Returns:
            Elevation in meters, or None if no elevation data
        """
        if not self.elevations:
            return None

        # Find the elevation record that applies to this s
        applicable_elev = None
        for elev_s, a, b, c, d in self.elevations:
            if s >= elev_s:
                applicable_elev = (elev_s, a, b, c, d)
            else:
                break

        if applicable_elev is None:
            return None

        elev_s, a, b, c, d = applicable_elev
        ds = s - elev_s
        return a + b * ds + c * ds**2 + d * ds**3


@dataclass
class LateralProfile:
    """
    Represents lateral profile (superelevation/crossfall) for a road.

    Attributes:
        superelevations: List of (s, a, b, c, d) tuples for superelevation polynomial
                        superelevation(ds) = a + b*ds + c*ds² + d*ds³
    """
    superelevations: List[Tuple[float, float, float, float, float]] = field(default_factory=list)


@dataclass
class LaneOffsetRecord:
    """
    Lane offset record shifting center lane from reference line.

    Attributes:
        offsets: List of (s, a, b, c, d) tuples for offset polynomial
                offset(ds) = a + b*ds + c*ds² + d*ds³
    """
    offsets: List[Tuple[float, float, float, float, float]] = field(default_factory=list)


@dataclass
class LaneWidth:
    """
    Lane width polynomial from OpenDrive.

    Attributes:
        s_offset: Start position within lane section (meters)
        a, b, c, d: Polynomial coefficients: width(ds) = a + b*ds + c*ds² + d*ds³
    """
    s_offset: float
    a: float
    b: float = 0.0
    c: float = 0.0
    d: float = 0.0

    def get_width_at(self, ds: float) -> float:
        """Get width at distance ds from s_offset."""
        return self.a + self.b * ds + self.c * ds**2 + self.d * ds**3


@dataclass
class LaneRoadMark:
    """Road marking for a lane."""
    s_offset: float
    type: str  # "solid", "broken", etc.
    weight: str = "standard"
    color: str = "white"
    width: float = 0.12  # meters


@dataclass
class LaneSpeed:
    """Speed limit for a lane."""
    s_offset: float
    max_speed: float  # Maximum speed in m/s
    unit: str = "m/s"  # Unit: "m/s", "mph", or "km/h"


@dataclass
class LaneMaterial:
    """Lane material properties."""
    s_offset: float
    friction: float = 1.0
    roughness: Optional[float] = None
    surface: str = "asphalt"


@dataclass
class LaneHeight:
    """Lane height offset for raised lanes."""
    s_offset: float
    inner: float = 0.0  # Inner height offset (closer to center)
    outer: float = 0.0  # Outer height offset (edge of lane)


@dataclass
class LaneLink:
    """Lane predecessor/successor link."""
    predecessor_id: Optional[int] = None
    successor_id: Optional[int] = None


@dataclass
class ODRLane:
    """
    OpenDrive lane from XML.

    Attributes:
        id: Lane ID (negative for right, positive for left, 0 for center)
        type: Lane type ("driving", "biking", "sidewalk", etc.)
        level: Level flag for lane height
        widths: List of width polynomials
        road_marks: List of road marking definitions
        speed_limits: List of speed limit records
        materials: List of material properties
        heights: List of height offsets
        link: Lane predecessor/successor links
        direction: V1.8 direction attribute
        advisory: V1.8 advisory attribute
    """
    id: int
    type: str
    level: bool = False
    widths: List[LaneWidth] = field(default_factory=list)
    road_marks: List[LaneRoadMark] = field(default_factory=list)
    speed_limits: List[LaneSpeed] = field(default_factory=list)
    materials: List[LaneMaterial] = field(default_factory=list)
    heights: List[LaneHeight] = field(default_factory=list)
    link: Optional[LaneLink] = None
    direction: Optional[str] = None  # V1.8: "standard", "reversed", "both"
    advisory: Optional[str] = None  # V1.8: "none", "inner", "outer", "both"

    def get_width_at_s(self, s: float) -> float:
        """
        Get lane width at s-coordinate within lane section.

        Uses constant width (polynomial at s=0) for ORBIT compatibility.
        TODO: Add support for variable width polynomials.
        """
        if not self.widths:
            return 3.5  # Default width
        # For now, use first width's a parameter (constant term)
        return self.widths[0].a


@dataclass
class ODRLaneSection:
    """
    OpenDrive lane section from XML.

    Attributes:
        s: Start position along road (meters)
        single_side: Optional attribute ("left", "right", or None)
        left_lanes: List of left lanes (sorted by ID descending)
        center_lanes: List of center lanes (usually just one with ID=0)
        right_lanes: List of right lanes (sorted by ID ascending)
    """
    s: float
    single_side: Optional[str] = None
    left_lanes: List[ODRLane] = field(default_factory=list)
    center_lanes: List[ODRLane] = field(default_factory=list)
    right_lanes: List[ODRLane] = field(default_factory=list)


@dataclass
class ODRSignal:
    """
    OpenDrive signal from XML.

    Attributes:
        id: Signal ID
        s: Position along road (meters)
        t: Lateral offset from reference line (meters)
        dynamic: "yes" for traffic lights, "no" for signs
        orientation: "+" (forward), "-" (backward), "none" (both)
        z_offset: Height above road surface (meters)
        country: Country code (e.g., "SE")
        type: Signal type code
        subtype: Signal subtype
        value: Value (e.g., speed limit)
        unit: Unit for value (e.g., "km/h")
        height: Sign height (meters)
        width: Sign width (meters)
        name: Optional name/description
    """
    id: str
    s: float
    t: float
    dynamic: str = "no"
    orientation: str = "+"
    z_offset: float = 0.0
    country: str = ""
    type: str = ""
    subtype: str = ""
    value: Optional[float] = None
    unit: str = ""
    height: float = 0.0
    width: float = 0.0
    name: str = ""
    validity_lanes: Optional[List[int]] = None  # Lane IDs this signal applies to


@dataclass
class ODRObject:
    """
    OpenDrive object from XML.

    Attributes:
        id: Object ID
        s: Position along road (meters)
        t: Lateral offset from reference line (meters)
        z_offset: Height above road surface (meters)
        type: Object type
        name: Object name
        orientation: Orientation angle (radians)
        length: Object length (meters)
        width: Object width (meters)
        height: Object height (meters)
        radius: Object radius (meters, for circular objects)
        hdg: Heading offset (radians)
        pitch: Pitch angle (radians)
        roll: Roll angle (radians)
        validity_length: Validity length along road (meters, for objects spanning distance)
        is_parking: True if this object is a parking space
        parking_access: Parking access type (if is_parking is True)
        parking_restrictions: Parking restrictions text (if is_parking is True)
    """
    id: str
    s: float
    t: float
    z_offset: float = 0.0
    type: str = ""
    name: str = ""
    orientation: float = 0.0
    length: float = 0.0
    width: float = 0.0
    height: float = 0.0
    radius: float = 0.0
    hdg: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0
    validity_length: Optional[float] = None
    # Parking-specific attributes
    is_parking: bool = False
    parking_access: str = "standard"
    parking_restrictions: str = ""


@dataclass
class ODRLaneLink:
    """Lane link within a junction connection."""
    from_lane: int  # Lane ID on incoming road
    to_lane: int    # Lane ID on connecting road


@dataclass
class ODRConnection:
    """Junction connection from OpenDrive."""
    id: str
    incoming_road: str
    connecting_road: str
    contact_point: str  # "start" or "end"
    lane_links: List[ODRLaneLink] = field(default_factory=list)


@dataclass
class ODRBoundarySegment:
    """A segment of junction boundary (V1.8 feature)."""
    segment_type: str  # 'lane' or 'joint'
    road_id: Optional[str] = None
    # For 'lane' type
    boundary_lane: Optional[int] = None
    s_start: Optional[float] = None
    s_end: Optional[float] = None
    # For 'joint' type
    contact_point: Optional[str] = None
    joint_lane_start: Optional[int] = None
    joint_lane_end: Optional[int] = None
    transition_length: Optional[float] = None


@dataclass
class ODRJunctionBoundary:
    """Junction boundary (V1.8 feature)."""
    segments: List[ODRBoundarySegment] = field(default_factory=list)


@dataclass
class ODRElevationGridPoint:
    """A point in junction elevation grid (V1.8 feature)."""
    center: Optional[str] = None
    left: Optional[str] = None
    right: Optional[str] = None


@dataclass
class ODRJunctionElevationGrid:
    """Junction elevation grid (V1.8 feature)."""
    grid_spacing: Optional[str] = None
    elevations: List[ODRElevationGridPoint] = field(default_factory=list)


@dataclass
class ODRJunction:
    """
    OpenDrive junction from XML.

    Attributes:
        id: Junction ID
        name: Junction name
        connections: List of connections between roads
        boundary: V1.8 junction boundary
        elevation_grid: V1.8 elevation grid
    """
    id: str
    name: str = ""
    connections: List[ODRConnection] = field(default_factory=list)
    boundary: Optional[ODRJunctionBoundary] = None
    elevation_grid: Optional[ODRJunctionElevationGrid] = None


@dataclass
class ODRJunctionGroup:
    """
    OpenDrive junction group from XML.

    Groups multiple junctions that form a logical unit (roundabouts, highway interchanges).

    Attributes:
        id: Junction group ID
        name: Optional name
        group_type: Type of group ('roundabout', 'complexJunction', 'highwayInterchange', 'unknown')
        junction_ids: List of junction IDs in this group
    """
    id: str
    name: str = ""
    group_type: str = "unknown"
    junction_ids: List[str] = field(default_factory=list)


@dataclass
class ODRRoad:
    """
    OpenDrive road from XML.

    Attributes:
        id: Road ID
        name: Road name
        length: Total road length (meters)
        junction_id: Junction ID if road is part of junction (-1 for regular roads)
        geometry: List of geometry elements in planView
        elevation_profile: Elevation profile (optional)
        lane_sections: List of lane sections
        signals: List of signals on this road
        objects: List of objects on this road
        predecessor_type: Type of predecessor ("road" or "junction")
        predecessor_id: ID of predecessor
        predecessor_contact: Contact point on predecessor ("start" or "end")
        successor_type: Type of successor ("road" or "junction")
        successor_id: ID of successor
        successor_contact: Contact point on successor ("start" or "end")
        road_type: Road type ("town", "motorway", etc.)
    """
    id: str
    name: str = ""
    length: float = 0.0
    junction_id: str = "-1"
    geometry: List[GeometryElement] = field(default_factory=list)
    elevation_profile: Optional[ElevationProfile] = None
    lateral_profile: Optional[LateralProfile] = None
    lane_offset: Optional[LaneOffsetRecord] = None
    lane_sections: List[ODRLaneSection] = field(default_factory=list)
    signals: List[ODRSignal] = field(default_factory=list)
    objects: List[ODRObject] = field(default_factory=list)
    surface_crg: List[Dict[str, Any]] = field(default_factory=list)  # OpenCRG surface data
    predecessor_type: Optional[str] = None
    predecessor_id: Optional[str] = None
    predecessor_contact: Optional[str] = None
    successor_type: Optional[str] = None
    successor_id: Optional[str] = None
    successor_contact: Optional[str] = None
    road_type: str = "unknown"


@dataclass
class ODRHeader:
    """OpenDrive file header information."""
    rev_major: int = 1
    rev_minor: int = 7
    name: str = ""
    version: str = ""
    date: str = ""
    north: float = 0.0
    south: float = 0.0
    east: float = 0.0
    west: float = 0.0
    vendor: str = ""
    # Coordinate offset (all geometry coordinates are relative to this)
    offset_x: float = 0.0
    offset_y: float = 0.0
    offset_z: float = 0.0
    offset_hdg: float = 0.0


@dataclass
class OpenDriveData:
    """Complete parsed OpenDrive data."""
    header: ODRHeader
    geo_reference: Optional[str] = None  # PROJ4 string
    roads: List[ODRRoad] = field(default_factory=list)
    junctions: List[ODRJunction] = field(default_factory=list)
    junction_groups: List[ODRJunctionGroup] = field(default_factory=list)


class OpenDriveParser:
    """Parser for ASAM OpenDrive XML files."""

    def __init__(self):
        """Initialize parser."""
        self.data: Optional[OpenDriveData] = None

    def parse_file(self, file_path: str) -> OpenDriveData:
        """
        Parse OpenDrive XML file.

        Args:
            file_path: Path to .xodr file

        Returns:
            Parsed OpenDrive data

        Raises:
            Exception: If parsing fails
        """
        try:
            tree = etree.parse(file_path)
            root = tree.getroot()
            self._strip_namespace(root)
            return self.parse_root(root)
        except Exception as e:
            raise Exception(f"Failed to parse OpenDrive file: {e}")

    @staticmethod
    def _strip_namespace(root: etree.Element) -> None:
        """Strip XML namespace from all elements to allow unqualified find/findall."""
        for elem in root.iter():
            if isinstance(elem.tag, str) and '}' in elem.tag:
                elem.tag = elem.tag.split('}', 1)[1]

    def parse_root(self, root: etree.Element) -> OpenDriveData:
        """Parse root OpenDRIVE element."""
        self.data = OpenDriveData(header=self._parse_header(root))

        # Parse geoReference if present
        geo_ref_elem = root.find('header/geoReference')
        if geo_ref_elem is not None and geo_ref_elem.text:
            self.data.geo_reference = geo_ref_elem.text.strip()

        # Parse roads
        for road_elem in root.findall('road'):
            road = self._parse_road(road_elem)
            if road:
                self.data.roads.append(road)

        # Parse junctions
        for junction_elem in root.findall('junction'):
            junction = self._parse_junction(junction_elem)
            if junction:
                self.data.junctions.append(junction)

        # Parse junction groups
        for jg_elem in root.findall('junctionGroup'):
            junction_group = self._parse_junction_group(jg_elem)
            if junction_group:
                self.data.junction_groups.append(junction_group)

        return self.data

    def _parse_header(self, root: etree.Element) -> ODRHeader:
        """Parse header element."""
        header_elem = root.find('header')
        if header_elem is None:
            return ODRHeader()

        header = ODRHeader()
        header.rev_major = int(header_elem.get('revMajor', '1'))
        header.rev_minor = int(header_elem.get('revMinor', '7'))
        header.name = header_elem.get('name', '')
        header.version = header_elem.get('version', '')
        header.date = header_elem.get('date', '')
        header.north = float(header_elem.get('north', '0'))
        header.south = float(header_elem.get('south', '0'))
        header.east = float(header_elem.get('east', '0'))
        header.west = float(header_elem.get('west', '0'))
        header.vendor = header_elem.get('vendor', '')

        # Parse offset element if present (SUMO files use this)
        offset_elem = header_elem.find('offset')
        if offset_elem is not None:
            header.offset_x = float(offset_elem.get('x', '0'))
            header.offset_y = float(offset_elem.get('y', '0'))
            header.offset_z = float(offset_elem.get('z', '0'))
            header.offset_hdg = float(offset_elem.get('hdg', '0'))

        return header

    def _parse_road(self, road_elem: etree.Element) -> Optional[ODRRoad]:
        """Parse road element."""
        road_id = road_elem.get('id')
        if not road_id:
            return None

        road = ODRRoad(
            id=road_id,
            name=road_elem.get('name', ''),
            length=float(road_elem.get('length', '0')),
            junction_id=road_elem.get('junction', '-1')
        )

        # Parse link (predecessor/successor)
        link_elem = road_elem.find('link')
        if link_elem is not None:
            pred_elem = link_elem.find('predecessor')
            if pred_elem is not None:
                road.predecessor_type = pred_elem.get('elementType')
                road.predecessor_id = pred_elem.get('elementId')
                road.predecessor_contact = pred_elem.get('contactPoint')

            succ_elem = link_elem.find('successor')
            if succ_elem is not None:
                road.successor_type = succ_elem.get('elementType')
                road.successor_id = succ_elem.get('elementId')
                road.successor_contact = succ_elem.get('contactPoint')

        # Parse type
        type_elem = road_elem.find('type')
        if type_elem is not None:
            road.road_type = type_elem.get('type', 'unknown')

        # Parse planView geometry
        plan_view_elem = road_elem.find('planView')
        if plan_view_elem is not None:
            road.geometry = self._parse_plan_view(plan_view_elem)

        # Parse elevationProfile
        elev_profile_elem = road_elem.find('elevationProfile')
        if elev_profile_elem is not None:
            road.elevation_profile = self._parse_elevation_profile(elev_profile_elem)

        # Parse lateralProfile (superelevation)
        lateral_profile_elem = road_elem.find('lateralProfile')
        if lateral_profile_elem is not None:
            road.lateral_profile = self._parse_lateral_profile(lateral_profile_elem)

        # Parse lanes (including laneOffset)
        lanes_elem = road_elem.find('lanes')
        if lanes_elem is not None:
            road.lane_sections = self._parse_lane_sections(lanes_elem)
            road.lane_offset = self._parse_lane_offset(lanes_elem)

        # Parse signals
        signals_elem = road_elem.find('signals')
        if signals_elem is not None:
            for signal_elem in signals_elem.findall('signal'):
                signal = self._parse_signal(signal_elem)
                if signal:
                    road.signals.append(signal)

        # Parse objects
        objects_elem = road_elem.find('objects')
        if objects_elem is not None:
            for object_elem in objects_elem.findall('object'):
                obj = self._parse_object(object_elem)
                if obj:
                    road.objects.append(obj)

        # Parse surface CRG (OpenCRG road surface data)
        surface_elem = road_elem.find('surface')
        if surface_elem is not None:
            for crg_elem in surface_elem.findall('CRG'):
                crg_data = {
                    'file': crg_elem.get('file', ''),
                    'sStart': float(crg_elem.get('sStart', '0')),
                    'sEnd': float(crg_elem.get('sEnd', '0')),
                    'orientation': crg_elem.get('orientation', 'same'),
                    'mode': crg_elem.get('mode', 'attached'),
                    'purpose': crg_elem.get('purpose'),
                    'sOffset': float(crg_elem.get('sOffset', '0')),
                    'tOffset': float(crg_elem.get('tOffset', '0')),
                    'zOffset': float(crg_elem.get('zOffset', '0')),
                    'zScale': float(crg_elem.get('zScale', '1')),
                    'hOffset': float(crg_elem.get('hOffset', '0')),
                }
                road.surface_crg.append(crg_data)

        return road

    def _parse_plan_view(self, plan_view_elem: etree.Element) -> List[GeometryElement]:
        """Parse planView geometry elements."""
        geometry_list = []

        for geom_elem in plan_view_elem.findall('geometry'):
            s = float(geom_elem.get('s', '0'))
            x = float(geom_elem.get('x', '0'))
            y = float(geom_elem.get('y', '0'))
            hdg = float(geom_elem.get('hdg', '0'))
            length = float(geom_elem.get('length', '0'))

            # Determine geometry type and parse type-specific parameters
            geom_type = None
            params = {}

            line_elem = geom_elem.find('line')
            if line_elem is not None:
                geom_type = GeometryType.LINE

            arc_elem = geom_elem.find('arc')
            if arc_elem is not None:
                geom_type = GeometryType.ARC
                params['curvature'] = float(arc_elem.get('curvature', '0'))

            spiral_elem = geom_elem.find('spiral')
            if spiral_elem is not None:
                geom_type = GeometryType.SPIRAL
                params['curvStart'] = float(spiral_elem.get('curvStart', '0'))
                params['curvEnd'] = float(spiral_elem.get('curvEnd', '0'))

            poly3_elem = geom_elem.find('poly3')
            if poly3_elem is not None:
                geom_type = GeometryType.POLY3
                params['a'] = float(poly3_elem.get('a', '0'))
                params['b'] = float(poly3_elem.get('b', '0'))
                params['c'] = float(poly3_elem.get('c', '0'))
                params['d'] = float(poly3_elem.get('d', '0'))

            param_poly3_elem = geom_elem.find('paramPoly3')
            if param_poly3_elem is not None:
                geom_type = GeometryType.PARAM_POLY3
                params['aU'] = float(param_poly3_elem.get('aU', '0'))
                params['bU'] = float(param_poly3_elem.get('bU', '0'))
                params['cU'] = float(param_poly3_elem.get('cU', '0'))
                params['dU'] = float(param_poly3_elem.get('dU', '0'))
                params['aV'] = float(param_poly3_elem.get('aV', '0'))
                params['bV'] = float(param_poly3_elem.get('bV', '0'))
                params['cV'] = float(param_poly3_elem.get('cV', '0'))
                params['dV'] = float(param_poly3_elem.get('dV', '0'))
                params['pRange'] = param_poly3_elem.get('pRange', 'arcLength')

            if geom_type:
                geometry_list.append(GeometryElement(
                    s=s, x=x, y=y, hdg=hdg, length=length,
                    geometry_type=geom_type, params=params
                ))

        return geometry_list

    def _parse_elevation_profile(self, elev_profile_elem: etree.Element) -> ElevationProfile:
        """Parse elevationProfile element."""
        profile = ElevationProfile()

        for elev_elem in elev_profile_elem.findall('elevation'):
            s = float(elev_elem.get('s', '0'))
            a = float(elev_elem.get('a', '0'))
            b = float(elev_elem.get('b', '0'))
            c = float(elev_elem.get('c', '0'))
            d = float(elev_elem.get('d', '0'))
            profile.elevations.append((s, a, b, c, d))

        return profile

    def _parse_lateral_profile(self, lateral_profile_elem: etree.Element) -> LateralProfile:
        """Parse lateralProfile element (superelevation)."""
        profile = LateralProfile()

        for se_elem in lateral_profile_elem.findall('superelevation'):
            s = float(se_elem.get('s', '0'))
            a = float(se_elem.get('a', '0'))
            b = float(se_elem.get('b', '0'))
            c = float(se_elem.get('c', '0'))
            d = float(se_elem.get('d', '0'))
            profile.superelevations.append((s, a, b, c, d))

        return profile

    def _parse_lane_offset(self, lanes_elem: etree.Element) -> LaneOffsetRecord:
        """Parse laneOffset elements from lanes."""
        record = LaneOffsetRecord()

        for lo_elem in lanes_elem.findall('laneOffset'):
            s = float(lo_elem.get('s', '0'))
            a = float(lo_elem.get('a', '0'))
            b = float(lo_elem.get('b', '0'))
            c = float(lo_elem.get('c', '0'))
            d = float(lo_elem.get('d', '0'))
            record.offsets.append((s, a, b, c, d))

        return record

    def _parse_lane_sections(self, lanes_elem: etree.Element) -> List[ODRLaneSection]:
        """Parse lane sections."""
        sections = []

        for section_elem in lanes_elem.findall('laneSection'):
            s = float(section_elem.get('s', '0'))
            single_side = section_elem.get('singleSide')

            section = ODRLaneSection(s=s, single_side=single_side)

            # Parse left lanes
            left_elem = section_elem.find('left')
            if left_elem is not None:
                for lane_elem in left_elem.findall('lane'):
                    lane = self._parse_lane(lane_elem)
                    if lane:
                        section.left_lanes.append(lane)

            # Parse center lanes
            center_elem = section_elem.find('center')
            if center_elem is not None:
                for lane_elem in center_elem.findall('lane'):
                    lane = self._parse_lane(lane_elem)
                    if lane:
                        section.center_lanes.append(lane)

            # Parse right lanes
            right_elem = section_elem.find('right')
            if right_elem is not None:
                for lane_elem in right_elem.findall('lane'):
                    lane = self._parse_lane(lane_elem)
                    if lane:
                        section.right_lanes.append(lane)

            sections.append(section)

        return sections

    def _parse_lane(self, lane_elem: etree.Element) -> Optional[ODRLane]:
        """Parse individual lane."""
        lane_id = lane_elem.get('id')
        if lane_id is None:
            return None

        lane = ODRLane(
            id=int(lane_id),
            type=lane_elem.get('type', 'driving'),
            level=lane_elem.get('level') == 'true',
            direction=lane_elem.get('direction'),  # V1.8
            advisory=lane_elem.get('advisory')  # V1.8
        )

        # Parse width elements
        for width_elem in lane_elem.findall('width'):
            s_offset = float(width_elem.get('sOffset', '0'))
            a = float(width_elem.get('a', '3.5'))
            b = float(width_elem.get('b', '0'))
            c = float(width_elem.get('c', '0'))
            d = float(width_elem.get('d', '0'))
            lane.widths.append(LaneWidth(s_offset, a, b, c, d))

        # Parse roadMark elements
        for mark_elem in lane_elem.findall('roadMark'):
            s_offset = float(mark_elem.get('sOffset', '0'))
            mark_type = mark_elem.get('type', 'solid')
            weight = mark_elem.get('weight', 'standard')
            color = mark_elem.get('color', 'white')
            width = float(mark_elem.get('width', '0.12'))
            lane.road_marks.append(LaneRoadMark(s_offset, mark_type, weight, color, width))

        # Parse speed elements (lane-level speed limits)
        for speed_elem in lane_elem.findall('speed'):
            s_offset = float(speed_elem.get('sOffset', '0'))
            max_speed = float(speed_elem.get('max', '0'))
            unit = speed_elem.get('unit', 'm/s')
            lane.speed_limits.append(LaneSpeed(s_offset, max_speed, unit))

        # Parse material elements
        for mat_elem in lane_elem.findall('material'):
            s_offset = float(mat_elem.get('sOffset', '0'))
            friction = float(mat_elem.get('friction', '1.0'))
            roughness_str = mat_elem.get('roughness')
            roughness = float(roughness_str) if roughness_str else None
            surface = mat_elem.get('surface', 'asphalt')
            lane.materials.append(LaneMaterial(s_offset, friction, roughness, surface))

        # Parse height elements (for raised lanes)
        for height_elem in lane_elem.findall('height'):
            s_offset = float(height_elem.get('sOffset', '0'))
            inner = float(height_elem.get('inner', '0'))
            outer = float(height_elem.get('outer', '0'))
            lane.heights.append(LaneHeight(s_offset, inner, outer))

        # Parse link element (predecessor/successor)
        link_elem = lane_elem.find('link')
        if link_elem is not None:
            pred_elem = link_elem.find('predecessor')
            succ_elem = link_elem.find('successor')
            pred_id = int(pred_elem.get('id')) if pred_elem is not None else None
            succ_id = int(succ_elem.get('id')) if succ_elem is not None else None
            if pred_id is not None or succ_id is not None:
                lane.link = LaneLink(predecessor_id=pred_id, successor_id=succ_id)

        return lane

    def _parse_signal(self, signal_elem: etree.Element) -> Optional[ODRSignal]:
        """Parse signal element."""
        signal_id = signal_elem.get('id')
        if not signal_id:
            return None

        # Parse validity elements (which lanes this signal applies to)
        validity_lanes = None
        validity_elems = signal_elem.findall('validity')
        if validity_elems:
            validity_lanes = []
            for validity in validity_elems:
                from_lane = int(validity.get('fromLane', '0'))
                to_lane = int(validity.get('toLane', '0'))
                # Add all lanes in range (inclusive)
                if from_lane <= to_lane:
                    validity_lanes.extend(range(from_lane, to_lane + 1))
                else:
                    validity_lanes.extend(range(to_lane, from_lane + 1))
            # Remove duplicates and sort
            validity_lanes = sorted(set(validity_lanes))

        return ODRSignal(
            id=signal_id,
            s=float(signal_elem.get('s', '0')),
            t=float(signal_elem.get('t', '0')),
            dynamic=signal_elem.get('dynamic', 'no'),
            orientation=signal_elem.get('orientation', '+'),
            z_offset=float(signal_elem.get('zOffset', '0')),
            country=signal_elem.get('country', ''),
            type=signal_elem.get('type', ''),
            subtype=signal_elem.get('subtype', ''),
            value=float(signal_elem.get('value')) if signal_elem.get('value') else None,
            unit=signal_elem.get('unit', ''),
            height=float(signal_elem.get('height', '0')),
            width=float(signal_elem.get('width', '0')),
            name=signal_elem.get('name', ''),
            validity_lanes=validity_lanes
        )

    def _parse_object(self, object_elem: etree.Element) -> Optional[ODRObject]:
        """Parse object element."""
        object_id = object_elem.get('id')
        if not object_id:
            return None

        # Check for parkingSpace child element
        parking_space_elem = object_elem.find('parkingSpace')
        is_parking = parking_space_elem is not None
        parking_access = "standard"
        parking_restrictions = ""

        if parking_space_elem is not None:
            parking_access = parking_space_elem.get('access', 'standard')
            parking_restrictions = parking_space_elem.get('restrictions', '')

        return ODRObject(
            id=object_id,
            s=float(object_elem.get('s', '0')),
            t=float(object_elem.get('t', '0')),
            z_offset=float(object_elem.get('zOffset', '0')),
            type=object_elem.get('type', ''),
            name=object_elem.get('name', ''),
            orientation=float(object_elem.get('orientation', '0')),
            length=float(object_elem.get('length', '0')),
            width=float(object_elem.get('width', '0')),
            height=float(object_elem.get('height', '0')),
            radius=float(object_elem.get('radius', '0')),
            hdg=float(object_elem.get('hdg', '0')),
            pitch=float(object_elem.get('pitch', '0')),
            roll=float(object_elem.get('roll', '0')),
            validity_length=float(object_elem.get('validLength')) if object_elem.get('validLength') else None,
            is_parking=is_parking,
            parking_access=parking_access,
            parking_restrictions=parking_restrictions
        )

    def _parse_junction(self, junction_elem: etree.Element) -> Optional[ODRJunction]:
        """Parse junction element."""
        junction_id = junction_elem.get('id')
        if not junction_id:
            return None

        junction = ODRJunction(
            id=junction_id,
            name=junction_elem.get('name', '')
        )

        # Parse connections
        for conn_elem in junction_elem.findall('connection'):
            conn_id = conn_elem.get('id')
            incoming_road = conn_elem.get('incomingRoad')
            connecting_road = conn_elem.get('connectingRoad')
            contact_point = conn_elem.get('contactPoint', 'start')

            if conn_id and incoming_road and connecting_road:
                # Parse lane links within this connection
                lane_links = []
                for link_elem in conn_elem.findall('laneLink'):
                    from_lane = link_elem.get('from')
                    to_lane = link_elem.get('to')
                    if from_lane is not None and to_lane is not None:
                        lane_links.append(ODRLaneLink(
                            from_lane=int(from_lane),
                            to_lane=int(to_lane)
                        ))

                junction.connections.append(ODRConnection(
                    id=conn_id,
                    incoming_road=incoming_road,
                    connecting_road=connecting_road,
                    contact_point=contact_point,
                    lane_links=lane_links
                ))

        # Parse boundary (V1.8 feature)
        boundary_elem = junction_elem.find('boundary')
        if boundary_elem is not None:
            boundary = ODRJunctionBoundary()
            for seg_elem in boundary_elem.findall('segment'):
                seg_type = seg_elem.get('type', 'lane')
                segment = ODRBoundarySegment(
                    segment_type=seg_type,
                    road_id=seg_elem.get('roadId')
                )

                if seg_type == 'lane':
                    boundary_lane = seg_elem.get('boundaryLane')
                    if boundary_lane is not None:
                        segment.boundary_lane = int(boundary_lane)
                    s_start = seg_elem.get('sStart')
                    if s_start is not None and s_start != 'start' and s_start != 'end':
                        segment.s_start = float(s_start)
                    s_end = seg_elem.get('sEnd')
                    if s_end is not None and s_end != 'start' and s_end != 'end':
                        segment.s_end = float(s_end)
                elif seg_type == 'joint':
                    segment.contact_point = seg_elem.get('contactPoint')
                    joint_start = seg_elem.get('jointLaneStart')
                    if joint_start is not None:
                        segment.joint_lane_start = int(joint_start)
                    joint_end = seg_elem.get('jointLaneEnd')
                    if joint_end is not None:
                        segment.joint_lane_end = int(joint_end)
                    trans_len = seg_elem.get('transitionLength')
                    if trans_len is not None:
                        segment.transition_length = float(trans_len)

                boundary.segments.append(segment)
            junction.boundary = boundary

        # Parse elevation grid (V1.8 feature)
        elev_grid_elem = junction_elem.find('elevationGrid')
        if elev_grid_elem is not None:
            elev_grid = ODRJunctionElevationGrid(
                grid_spacing=elev_grid_elem.get('gridSpacing')
            )
            for elev_elem in elev_grid_elem.findall('elevation'):
                point = ODRElevationGridPoint(
                    center=elev_elem.get('center'),
                    left=elev_elem.get('left'),
                    right=elev_elem.get('right')
                )
                elev_grid.elevations.append(point)
            junction.elevation_grid = elev_grid

        return junction

    def _parse_junction_group(self, jg_elem: etree.Element) -> Optional[ODRJunctionGroup]:
        """Parse junctionGroup element."""
        group_id = jg_elem.get('id')
        if not group_id:
            return None

        junction_group = ODRJunctionGroup(
            id=group_id,
            name=jg_elem.get('name', ''),
            group_type=jg_elem.get('type', 'unknown')
        )

        # Parse junction references
        for ref_elem in jg_elem.findall('junctionReference'):
            junction_id = ref_elem.get('junction')
            if junction_id:
                junction_group.junction_ids.append(junction_id)

        return junction_group

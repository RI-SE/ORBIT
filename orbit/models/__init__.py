"""
Data models for ORBIT.

This module contains all data structures for polylines, roads, junctions,
and project management.
"""

from .connecting_road import ConnectingRoad
from .junction import (
    Junction,
    JunctionBoundary,
    JunctionBoundarySegment,
    JunctionConnection,
    JunctionElevationGrid,
    JunctionElevationGridPoint,
    JunctionGroup,
)
from .lane import BoundaryMode, Lane, LaneType
from .lane_connection import LaneConnection
from .lane_section import LaneSection
from .object import ObjectType, RoadObject
from .parking import ParkingAccess, ParkingSpace, ParkingType
from .polyline import GeometrySegment, LineType, Polyline, RoadMarkType
from .project import ControlPoint, Project
from .road import LaneInfo, Road, RoadType
from .sign_library import SignCategory, SignDefinition, SignLibrary
from .sign_library_manager import SignLibraryManager
from .signal import Signal, SignalType, SpeedUnit
from .types import (
    BBox,
    EntityID,
    GeoCoordinate,
    JsonDict,
    OptionalPointList,
    OptionalTransformer,
    PixelCoordinate,
    Point2D,
    PointList,
    ScaleFactor,
)

__all__ = [
    'Polyline',
    'LineType',
    'RoadMarkType',
    'GeometrySegment',
    'Road',
    'RoadType',
    'LaneInfo',
    'Lane',
    'LaneType',
    'BoundaryMode',
    'LaneSection',
    'Junction',
    'JunctionConnection',
    'JunctionGroup',
    'JunctionBoundary',
    'JunctionBoundarySegment',
    'JunctionElevationGrid',
    'JunctionElevationGridPoint',
    'ConnectingRoad',
    'LaneConnection',
    'Project',
    'ControlPoint',
    'Signal',
    'SignalType',
    'SpeedUnit',
    'RoadObject',
    'ObjectType',
    'ParkingSpace',
    'ParkingAccess',
    'ParkingType',
    'SignDefinition',
    'SignCategory',
    'SignLibrary',
    'SignLibraryManager',
    # Type aliases
    'Point2D',
    'PointList',
    'PixelCoordinate',
    'GeoCoordinate',
    'JsonDict',
    'EntityID',
    'BBox',
    'ScaleFactor',
    'OptionalTransformer',
    'OptionalPointList'
]

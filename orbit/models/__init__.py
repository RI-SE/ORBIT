"""
Data models for ORBIT.

This module contains all data structures for polylines, roads, junctions,
and project management.
"""

from .polyline import Polyline, LineType, RoadMarkType
from .road import Road, RoadType, LaneInfo
from .junction import Junction, JunctionConnection
from .connecting_road import ConnectingRoad
from .lane_connection import LaneConnection
from .project import Project, ControlPoint
from .lane import Lane, LaneType
from .lane_section import LaneSection
from .signal import Signal, SignalType, SpeedUnit
from .object import RoadObject, ObjectType
from .types import (
    Point2D, PointList, PixelCoordinate, GeoCoordinate,
    JsonDict, EntityID, BBox, ScaleFactor,
    OptionalTransformer, OptionalPointList
)

__all__ = [
    'Polyline',
    'LineType',
    'RoadMarkType',
    'Road',
    'RoadType',
    'LaneInfo',
    'Lane',
    'LaneType',
    'LaneSection',
    'Junction',
    'JunctionConnection',
    'ConnectingRoad',
    'LaneConnection',
    'Project',
    'ControlPoint',
    'Signal',
    'SignalType',
    'SpeedUnit',
    'RoadObject',
    'ObjectType',
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

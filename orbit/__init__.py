"""
ORBIT - OpenDrive Road Builder from Imagery Tool

Main package for the ORBIT application. This package contains all modules for
annotating roads in aerial/satellite imagery and exporting to ASAM OpenDrive format.

Subpackages:
    models: Data models (Project, Road, Polyline, Junction, etc.)
    gui: GUI components (MainWindow, dialogs, widgets)
    export: Export functionality (OpenDriveWriter, coordinate transformation)
    import: Import functionality (OSM, OpenDrive)
    utils: Utility functions (coordinate transform, geometry)
"""

# Re-export main components for convenience
from orbit.export import CoordinateTransformer, CurveFitter, OpenDriveWriter
from orbit.gui import ImageView, MainWindow
from orbit.models import (
    ControlPoint,
    Junction,
    JunctionConnection,
    Lane,
    LaneInfo,
    LaneSection,
    LaneType,
    LineType,
    ObjectType,
    Polyline,
    Project,
    Road,
    RoadMarkType,
    RoadObject,
    RoadType,
    Signal,
    SignalType,
    SpeedUnit,
)
from orbit.utils import TransformMethod, create_transformer

try:
    from importlib.metadata import version as _get_version
    __version__ = _get_version("orbit")
except Exception:
    __version__ = "0.5.0"  # fallback if not installed

__all__ = [
    # Version
    '__version__',

    # Models
    'Project',
    'ControlPoint',
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
    'Signal',
    'SignalType',
    'SpeedUnit',
    'RoadObject',
    'ObjectType',

    # GUI
    'MainWindow',
    'ImageView',

    # Export
    'OpenDriveWriter',
    'CoordinateTransformer',
    'CurveFitter',

    # Utils
    'create_transformer',
    'TransformMethod',
]

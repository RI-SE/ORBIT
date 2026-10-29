"""
orbit-georef: Georeferencing library for pixel↔geo coordinate transformation.

This standalone library can load georeferencing parameters exported from ORBIT
and use them to transform coordinates between pixel and geographic spaces.

Example usage:
    from orbit_georef import load_georef

    georef = load_georef("georef_params.json")
    lon, lat = georef.pixel_to_geo(1234.5, 567.8)
    px, py = georef.geo_to_pixel(12.945, 57.720)
"""

from .camera_model import CameraModel, TerrainSurface
from .io import georef_from_data, load_georef, save_georef
from .models import ControlPoint
from .transformer import GeoTransformer

__version__ = "0.2.0"

__all__ = [
    "GeoTransformer",
    "ControlPoint",
    "CameraModel",
    "TerrainSurface",
    "georef_from_data",
    "load_georef",
    "save_georef",
]

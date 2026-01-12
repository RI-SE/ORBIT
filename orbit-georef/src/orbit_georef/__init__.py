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

from .transformer import GeoTransformer
from .models import ControlPoint
from .io import load_georef, save_georef

__version__ = "0.1.0"

__all__ = [
    "GeoTransformer",
    "ControlPoint",
    "load_georef",
    "save_georef",
]

from orbit_georef import GeoTransformer, ControlPoint
import random
import numpy as np

# Define control points
control_points = [
    ControlPoint(pixel_x=100, pixel_y=100, longitude=12.94, latitude=57.72),
    ControlPoint(pixel_x=200, pixel_y=100, longitude=12.95, latitude=57.72),
    ControlPoint(pixel_x=100, pixel_y=200, longitude=12.94, latitude=57.71),
    ControlPoint(pixel_x=200, pixel_y=200, longitude=12.95, latitude=57.71),
]

# Create transformer (uses homography by default)
georef = GeoTransformer.from_control_points(control_points, method="homography")

# Test pixel to geo
lon, lat = georef.pixel_to_geo(100, 100)

print(f"Pixel (100, 100) -> Geo ({lon}, {lat})")

lon, lat = georef.pixel_to_geo(100, 100, proj_string="+proj=longlat +datum=WGS84 +no_defs")

print(f"Pixel (100, 100) -> Geo ({lon}, {lat}) with explicit proj string")


for i in range(10):
    x, y = random.randint(0, 300), random.randint(0, 300)
    without_proj = georef.pixel_to_geo(x, y)
    with_proj = georef.pixel_to_geo(x, y, proj_string="+proj=longlat +datum=WGS84 +no_defs")
    diffs = np.array(without_proj) - np.array(with_proj)

    print(f"Pixel ({x}, {y}) ->  diffs: {diffs}")
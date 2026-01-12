# orbit-georef

Standalone Python library for pixel↔geo coordinate transformation using georeferencing parameters exported from ORBIT.

## Installation

```bash
pip install orbit-georef
```

Or install from source:
```bash
pip install -e .
```

## Usage

### Load from ORBIT export

```python
from orbit_georef import load_georef

# Load georeferencing parameters exported from ORBIT
georef = load_georef("georef_params.json")

# Convert pixel to geographic coordinates
lon, lat = georef.pixel_to_geo(1234.5, 567.8)

# Convert geographic to pixel coordinates
px, py = georef.geo_to_pixel(12.945, 57.720)

# Batch conversion
geo_coords = georef.pixels_to_geo_batch([(100, 200), (300, 400), (500, 600)])

# Get scale factors (meters per pixel)
scale_x, scale_y = georef.get_scale()
```

### Create from control points

```python
from orbit_georef import GeoTransformer, ControlPoint

# Define control points
control_points = [
    ControlPoint(pixel_x=100, pixel_y=100, longitude=12.94, latitude=57.72),
    ControlPoint(pixel_x=200, pixel_y=100, longitude=12.95, latitude=57.72),
    ControlPoint(pixel_x=100, pixel_y=200, longitude=12.94, latitude=57.71),
    ControlPoint(pixel_x=200, pixel_y=200, longitude=12.95, latitude=57.71),
]

# Create transformer (uses homography by default)
georef = GeoTransformer.from_control_points(control_points, method="homography")

# Or use affine transformation (requires minimum 3 points)
georef = GeoTransformer.from_control_points(control_points, method="affine")
```

## Transformation Methods

- **Affine** (6 parameters): Best for orthophotos and satellite imagery (nadir view). Requires minimum 3 control points.
- **Homography** (8 parameters): Best for oblique drone imagery with camera tilt. Requires minimum 4 control points.

## Export Format

The JSON export format includes:
- Control points with pixel and geographic coordinates
- Precomputed transformation matrices
- Reference point (center of control points)
- Scale factors (meters per pixel)
- Reprojection error metrics

## License

MIT

# orbit-georef

Standalone Python library for pixel↔geo coordinate transformation using georeferencing parameters exported from ORBIT. Supports transformation to any coordinate system that can be expressed via [PROJ strings](https://proj.org/en/stable/usage/quickstart.html).

> [!NOTE]
> This open source project is maintained by [RISE Research Institutes of Sweden](https://ri.se/). See [LICENSE](LICENSE) file for open source license information.

> [!NOTE]
> This is a beta version. Bugs and missing features should be expected. Github issues can be added for bug reports or feature requests.

## Installation

```bash
pip install orbit-georef
```

Or install from source:
```bash
pip install -e .
```

## Usage

### Load from ORBIT export and convert coordinates to desired coordinate system

```python
from orbit_georef import load_georef

# Load georeferencing parameters exported from ORBIT
georef = load_georef("georef_params.json")

# Convert pixel to geographic coordinates
lon, lat = georef.pixel_to_geo(1234.5, 567.8)

# Convert pixel coordinates to a projected coordinate system via a PROJ string (https://proj.org/en/stable/usage/quickstart.html), e.g. WGS84
x, y = georef.pixel_to_geo(1234.5, 567.8, proj_string="+proj=longlat +datum=WGS84 +no_defs")

# Convert geographic to pixel coordinates (assumes WGS84 as input)
px, py = georef.geo_to_pixel(12.945, 57.720)

# Batch conversion (as `pixel_to_geo()`, this supports also the optional `proj_string` argument)
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

This library is licensed under the [MIT License](LICENSE).

### Dependencies and Their Licenses

**Runtime dependencies:**
- **NumPy** - BSD 3-Clause License
- **pyproj** - MIT License

**Development dependencies (optional):**
- **pytest** - MIT License
- **pytest-cov** - MIT License

## Acknowledgement

<br><div align="center">
  <img src="../docs/synergies.svg" alt="Synergies logo" width="200"/>
</div>

This package is developed as part of the [SYNERGIES](https://synergies-ccam.eu/) project.

<br><div align="center">
  <img src="../docs/funded_by_eu.svg" alt="Funded by EU" width="200"/>
</div>

Funded by the European Union. Views and opinions expressed are however those of the author(s) only and do not necessarily reflect those of the European Union or European Climate, Infrastructure and Environment Executive Agency (CINEA). Neither the European Union nor the granting authority can be held responsible for them.

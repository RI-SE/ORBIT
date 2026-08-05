<div align="center">
  <img src="./docs/orbit_logo_t.png" alt="ORBIT logo" width="200"/>
</div>

# ORBIT - OpenDrive Road Builder from Imagery Tool

[![CI](https://github.com/RI-SE/ORBIT/actions/workflows/ci.yml/badge.svg)](https://github.com/RI-SE/ORBIT/actions/workflows/ci.yml)
[![License: GPL v3](https://img.shields.io/badge/License-GPL_v3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![OpenDrive](https://img.shields.io/badge/OpenDRIVE-1.8-orange)](https://www.asam.net/standards/detail/opendrive/)

A visual tool for creating or editing ASAM OpenDRIVE 1.8 road networks from aerial imagery.

![ORBIT main window](docs/screenshot_main_window.png)

> [!NOTE]
> This open source project is maintained by [RISE Research Institutes of Sweden](https://ri.se/). See [LICENSE](LICENSE) file for open source license information.


> [!NOTE]
> This is a beta version. Bugs and missing features should be expected. Github issues can be added for bug reports or feature requests.

---

## Contents

- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Documentation](#documentation)
- [Related Packages](#related-packages)
- [Project Structure](#project-structure)
- [Development](#development)
- [License](#license)

---

## Features

### Road Annotation
- **Interactive polyline drawing** on aerial/satellite/drone images
- **Centerline and lane boundary** distinction with road mark types (solid, broken, etc.)
- **Lane sections** for roads where lane configuration changes, with split and merge operations
- **Road splitting and merging** for flexible network editing
- **Data-driven road marks** from actual annotated line types
- **OpenDRIVE 1.8 lane attributes** (direction, advisory)

### Junction Support
- **Junction annotation** with drag-and-drop positioning
- **Roundabout wizard** for creating circular intersections
- **Connecting roads** with proper geometric paths through junctions
- **Lane-level connections** with explicit lane-to-lane mappings
- **Automatic connection generation** from road geometry

### Import Capabilities
- **OpenStreetMap import** via Overpass API (roads, signals, junctions, objects, land use areas)
- **OpenDRIVE import** for editing existing .xodr files (round-trip support)

### Georeferencing
- **Control point system** for pixel-to-geographic transformation
- **CSV import** for batch control points
- **Monte Carlo uncertainty analysis** with visualization
- **Validation metrics** with reprojection error

### Export
- **ASAM OpenDRIVE 1.8** XML format
- **XSD schema validation** against official ASAM schema ([download](https://publications.pages.asam.net/standards/ASAM_OpenDRIVE/ASAM_OpenDRIVE_Specification/latest/specification/))
- **Configurable geometry** — preserve all points or fit curves
- **Geographic reference** with PROJ4 projection string
- **Complete junction export** with connecting roads and lane links

---

## Installation

### Using uv (recommended)

```bash
# Install uv if needed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and install
git clone https://github.com/RI-SE/ORBIT.git
cd ORBIT
uv sync
```

### Using pip

```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
```

---

## Quick Start

```bash
# Start with an image
orbit path/to/aerial_image.jpg

# Start empty (load image via File menu)
orbit

# Enable verbose logging
orbit --verbose

# Enable XSD schema validation for exports
orbit --xodr_schema /path/to/OpenDRIVE_Core.xsd
```

> **Note**: After installation with `uv sync` or `pip install -e .`, the `orbit` command is available directly. Alternatively, use `uv run orbit` or `python run_orbit.py`.

### Basic Workflow

1. **Load image** — File → Load Image or pass path on command line
2. **Add control points** — Tools → Georeferencing (minimum 4 points (oblique imagery) or 3 (nadir imagery))
3. **Import or draw** — Either import an existing map from OpenStreetMap or OpenDRIVE, or draw roads directly in ORBIT.
4. **Edit** — Edit roads. Add signs, parking, land use areas, and objects.
5. **Export** — File → Export → Export to OpenDrive

---

## Documentation

| Guide | Description |
|-------|-------------|
| [User Guide](docs/USER_GUIDE.md) | Complete user guide with workflow, tips, and keyboard shortcuts |
| [Georeferencing Guide](docs/GEOREFERENCING.md) | Control points and uncertainty analysis |
| [OSM Import Guide](docs/OSM_IMPORT.md) | OpenStreetMap import feature |
| [Validation Guide](docs/VALIDATION.md) | Validation metrics and uncertainty estimation |
| [Developer Guide](docs/DEV_GUIDE.md) | Architecture and contribution guidelines |

---

## Related Packages

All three are MIT licensed and free of any PyQt dependency, so they can be used in
scripts, pipelines and downstream tools without taking on ORBIT's GPL-3.0 terms.

### [orbit-core](orbit-core/)

The headless half of ORBIT: road-network model, OpenStreetMap and OpenDRIVE import, and
OpenDRIVE export. Build a CARLA-ready `.xodr` from coordinates in three calls, with no
GUI and no imagery:

```python
import orbit_core as oc

bbox = oc.bbox_from_center(57.6968, 11.9865, radius_m=150)
osm = oc.osm_data_from_overpass(bbox)      # or osm_data_from_file("area.osm")
oc.opendrive_from_osm_data(osm, bbox, "out.xodr")
```

See [orbit-core/README.md](orbit-core/README.md) for details.

### [opendrive-map](opendrive-map/)

Read-only OpenDRIVE road-network and lane-geometry model — parses a `.xodr` into lane
polygons, centrelines and junctions, with point-to-lane lookup. Shared across the
toolchain (COSMO's `trajectory-explorer`, `data-metrics`). See
[opendrive-map/README.md](opendrive-map/README.md).

### [orbit-georef](orbit-georef/)

Standalone Python library for pixel↔geo coordinate transformation. Use it to work with ORBIT's georeferencing outside the GUI — for example, converting pixel coordinates to lat/lon in scripts or downstream tooling. See [orbit-georef/README.md](orbit-georef/README.md) for details.

---

## Project Structure

```
orbit/
├── gui/          # PyQt6 GUI (MainWindow, ImageView, dialogs, widgets)
└── signs/        # Traffic sign libraries (country-specific)
orbit-core/       # Headless core, MIT (separate package)
└── src/orbit_core/
    ├── models/       # Data models (Road, Polyline, Junction, ParkingSpace, Signal, ...)
    ├── importers/    # OSM and OpenDRIVE importers
    ├── export/       # OpenDRIVE XML generation (writers, builders)
    └── utils/        # Coordinate transforms, geometry utilities
opendrive-map/    # Read-only OpenDRIVE lane geometry, MIT (separate package)
orbit-georef/     # Standalone georeferencing library, MIT (separate package)
```

The GUI is a shell over `orbit-core`: all road-building logic lives in the library, and
nothing in it imports PyQt.

### Project Files

Projects save as `.orbit` JSON files containing:
- Image path and metadata
- Polylines (pixel coordinates)
- Roads with lane sections
- Junctions with connections and junction groups
- Control points for georeferencing
- Signals and roadside objects
- Parking spaces
- Land use areas (forest, farmland, water, etc.)

---

## Development

### Setup

```bash
# Install with dev dependencies
uv sync --extra dev

# Run tests
uv run python -m pytest tests/ -v
```

### Key Technologies

- **PyQt6** — GUI framework
- **NumPy/SciPy** — Geometry and transformations
- **lxml** — XML generation
- **pyproj** — Coordinate projections
- **xmlschema** — OpenDRIVE XSD validation

See [Developer Guide](docs/DEV_GUIDE.md) for architecture details.

---

## License

The main ORBIT project is licensed under the [GNU General Public License v3.0 (GPL-3.0)](LICENSE).

The separate libraries **orbit-georef** (located in `orbit-georef/`) and **opendrive-map** (located in `opendrive-map/`) are licensed under the MIT License — see [orbit-georef/LICENSE](orbit-georef/LICENSE) and [opendrive-map/LICENSE](opendrive-map/LICENSE) — allowing for more permissive use in downstream projects. Neither library depends on PyQt6, which is what places the main application under GPL-3.0.

### Dependencies and Their Licenses

**Main ORBIT project (runtime):**
- **PyQt6** - GPL v3 (commercial license available)
- **PyQt6-Qt6** - LGPL v3 (Qt framework bindings)
- **opencv-python** - Apache 2.0
- **NumPy** - BSD 3-Clause License
- **SciPy** - BSD 3-Clause License
- **lxml** - BSD 3-Clause License
- **pyproj** - MIT License
- **xmlschema** - MIT License

**Main ORBIT project (development, optional):**
- **pytest** - MIT License
- **pytest-cov** - MIT License
- **pytest-mock** - MIT License
- **ruff** - MIT License

**orbit-georef library (runtime):**
- **NumPy** - BSD 3-Clause License
- **pyproj** - MIT License

**orbit-georef library (development, optional):**
- **pytest** - MIT License
- **pytest-cov** - MIT License

**opendrive-map library (runtime):**
- **NumPy** - BSD 3-Clause License
- **Shapely** - BSD 3-Clause License
- **pyproj** - MIT License

**opendrive-map library (development, optional):**
- **pytest** - MIT License

## Acknowledgement
<br><div align="center">
  <img src="docs/synergies.svg" alt="Synergies logo" width="200"/>
</div>

This package is developed as part of the [SYNERGIES](https://synergies-ccam.eu/) project.

<br><div align="center">
  <img src="docs/funded_by_eu.svg" alt="Funded by EU" width="200"/>
</div>

Funded by the European Union. Views and opinions expressed are however those of the author(s) only and do not necessarily reflect those of the European Union or European Climate, Infrastructure and Environment Executive Agency (CINEA). Neither the European Union nor the granting authority can be held responsible for them.

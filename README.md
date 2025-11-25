# ORBIT - OpenDrive Road Builder from Imagery Tool

**Version:** 0.2.0

A PyQt6-based GUI application for annotating roads in drone/aerial/satellite imagery and exporting to ASAM OpenDrive format.

## 📋 Documentation

- **[README.md](README.md)** - This file (quick start)
- **[USAGE_GUIDE.md](docs/USAGE_GUIDE.md)** - Detailed user guide with tips and shortcuts
- **[COMPLETE_WORKFLOW.md](docs/COMPLETE_WORKFLOW.md)** - End-to-end workflow tutorial
- **[GEOREFERENCING_GUIDE.md](docs/GEOREFERENCING_GUIDE.md)** - Complete georeferencing guide with uncertainty analysis
- **[VALIDATION_AND_UNCERTAINTY.md](docs/VALIDATION_AND_UNCERTAINTY.md)** - Technical deep-dive: validation metrics, uncertainty estimation, and GCP suggestions
- **[OSM_IMPORT_GUIDE.md](docs/OSM_IMPORT_GUIDE.md)** - OpenStreetMap import feature guide

## 🎯 Overview

## Features

- **Interactive polyline drawing and editing** on aerial/satellite images
- **Centerline and lane boundary distinction** with ASAM OpenDRIVE road mark types
- **Measured lane widths** calculated from georeferenced boundary positions
- **Group polylines into roads** with properties (lanes, width, type, speed limits)
- **Junction/intersection annotation** with drag-and-drop positioning
- **OpenStreetMap import** - Automatically import road networks from OSM via Overpass API
  - Roads with lane configurations and speed limits
  - Traffic signals and speed limit signs
  - Junction detection and lane section splitting
  - Roadside objects (lampposts, guardrails, trees, buildings)
- **Save/load work-in-progress projects** (.orbit JSON files)
- **Georeferencing with control points** for pixel-to-geographic coordinate transformation
  - Manual control point placement
  - CSV import for batch control points (pre-surveyed positions)
  - Training and validation point separation
  - Monte Carlo uncertainty analysis with configurable parameters
  - Uncertainty visualization overlay
  - Reprojection error validation
- **Export to ASAM OpenDRIVE XML** format with automatic curve fitting
- **Data-driven road marks** using actual annotated line types instead of synthetic marks

## Installation

### Using uv (recommended)

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Install with dev dependencies (for testing)
uv sync --extra dev
```

### Using pip (alternative)

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install from pyproject.toml
pip install -e .

# Install with dev dependencies
pip install -e ".[dev]"
```

## Usage

### Start with an image
```bash
./start_orbit path/to/image.jpg
```

### Start without image (load later via GUI)
```bash
./start_orbit
```

## Workflow

### Manual Annotation
1. **Load Image**: Start with an image or load via File → Load Image
2. **Draw Centerline**: Click "New Line" and trace the road center
3. **Set as Centerline**: Double-click polyline, change Line Type to "Centerline"
4. **Draw Lane Boundaries**: Trace visible lane markings (solid, broken, etc.)
5. **Set Road Mark Types**: Double-click boundaries, set Road Mark Type (solid, broken, etc.)
6. **Group to Road**: Select all polylines (centerline + boundaries) and group into road
7. **Configure Road**: Set lane count, road type, speed limits
8. **Apply Measured Width**: Review calculated lane width from boundaries, apply if accurate
9. **Mark Junctions**: Define intersections and connecting roads
10. **Save Project**: File → Save Project (saves as .orbit file with pixel coordinates)
11. **Georeference**: Tools → Georeferencing to add control points with lat/lon (see [GEOREFERENCING_GUIDE.md](docs/GEOREFERENCING_GUIDE.md))
12. **Export**: File → Export to OpenDrive (generates XML with centerline geometry and real road marks)

### OSM Import (Alternative/Supplement)
1. **Load Image**: Start with an aerial/satellite image
2. **Georeference**: Tools → Georeferencing (add 3+ control points with lat/lon, see [GEOREFERENCING_GUIDE.md](docs/GEOREFERENCING_GUIDE.md))
3. **Import OSM**: File → Import OpenStreetMap Data (`Ctrl+Shift+I`)
4. **Configure**: Choose detail level (Moderate/Full), import mode, lane width
5. **Review**: Inspect imported roads, junctions, signals, and objects
6. **Refine**: Manually adjust imported data if needed
7. **Export**: File → Export to OpenDrive

See [OSM_IMPORT_GUIDE.md](docs/OSM_IMPORT_GUIDE.md) for detailed OSM import instructions.

## Project File Format

Projects are saved as JSON files with `.orbit` extension containing:
- Image path
- Polylines (pixel coordinates)
- Roads (groupings and properties)
- Junctions
- Control points (for georeferencing)
- Uncertainty analysis cache (Monte Carlo results)
- Uncertainty parameters (σ pixels, baseline uncertainty)
- Metadata

## OpenDrive Export

The export process:
1. Validates each road has exactly one centerline
2. Converts pixel coordinates to real-world coordinates using control points
3. Uses **centerline only** for road reference geometry (planView)
4. Fits curves (lines, arcs, clothoids) to centerline polyline
5. Calculates lateral offsets and lane widths from lane boundaries
6. Assigns boundaries to specific lanes based on position
7. Uses **actual Road Mark Types** from annotated boundaries (solid, broken, etc.)
8. Generates ASAM OpenDrive 1.7 XML with data-driven road marks
9. Supports configurable traffic direction (right/left-hand)

## License

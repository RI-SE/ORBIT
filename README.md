# ORBIT - OpenDrive Road Builder from Imagery Tool

**Version:** 0.3.1

A PyQt6-based GUI application for annotating roads in drone/aerial/satellite imagery and exporting to ASAM OpenDRIVE format.

## Documentation

- **[README.md](README.md)** - This file (quick start)
- **[USAGE_GUIDE.md](docs/USAGE_GUIDE.md)** - Detailed user guide with tips and shortcuts
- **[COMPLETE_WORKFLOW.md](docs/COMPLETE_WORKFLOW.md)** - End-to-end workflow tutorial
- **[GEOREFERENCING_GUIDE.md](docs/GEOREFERENCING_GUIDE.md)** - Complete georeferencing guide with uncertainty analysis
- **[VALIDATION_AND_UNCERTAINTY.md](docs/VALIDATION_AND_UNCERTAINTY.md)** - Technical deep-dive: validation metrics, uncertainty estimation, and GCP suggestions
- **[OSM_IMPORT_GUIDE.md](docs/OSM_IMPORT_GUIDE.md)** - OpenStreetMap import feature guide
- **[DEV_GUIDE.md](docs/DEV_GUIDE.md)** - Developer guide for contributors

## Features

### Road Annotation
- **Interactive polyline drawing and editing** on aerial/satellite images
- **Centerline and lane boundary distinction** with ASAM OpenDRIVE road mark types
- **Measured lane widths** calculated from georeferenced boundary positions
- **Group polylines into roads** with properties (lanes, width, type, speed limits)
- **Lane sections** - Split roads where lane configuration changes
- **Data-driven road marks** using actual annotated line types

### Junctions
- **Junction/intersection annotation** with drag-and-drop positioning
- **Connecting roads** - Geometric paths through junctions with proper OpenDRIVE export
- **Lane-level connections** - Explicit lane-to-lane mappings
- **Automatic connection generation** from road geometry analysis
- **Visual connection display** in the GUI

### Import
- **OpenStreetMap import** - Automatically import road networks from OSM via Overpass API
  - Roads with lane configurations and speed limits
  - Traffic signals and speed limit signs
  - Junction detection with connecting road generation
  - Roadside objects (lampposts, guardrails, trees, buildings)
- **OpenDRIVE import** - Load existing .xodr files for editing (round-trip support)

### Georeferencing
- **Control points** for pixel-to-geographic coordinate transformation
- **Manual control point placement** or **CSV import** for batch points
- **Training and validation point separation**
- **Monte Carlo uncertainty analysis** with configurable parameters
- **Uncertainty visualization overlay**
- **Reprojection error validation**

### Export
- **ASAM OpenDRIVE 1.7 XML** format with automatic curve fitting
- **Proper junction export** with connecting roads and lane links
- **Configurable geometry** - preserve all points or fit curves
- **Geographic reference** - PROJ4 string for coordinate system

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
uv run python start_orbit path/to/image.jpg
```

### Start without image (load later via GUI)
```bash
uv run python start_orbit
```

### Enable verbose logging
```bash
uv run python start_orbit --verbose
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
8. **Split Sections**: Right-click centerline points to split where lanes change
9. **Mark Junctions**: Define intersections and connecting roads
10. **Save Project**: File → Save Project (saves as .orbit file with pixel coordinates)
11. **Georeference**: Tools → Georeferencing to add control points with lat/lon
12. **Export**: File → Export to OpenDrive

### OSM Import
1. **Load Image**: Start with an aerial/satellite image
2. **Georeference**: Tools → Georeferencing (add 3+ control points with lat/lon)
3. **Import OSM**: File → Import OpenStreetMap Data (`Ctrl+Shift+I`)
4. **Configure**: Choose detail level (Moderate/Full), import mode, lane width
5. **Review**: Inspect imported roads, junctions, signals, and objects
6. **Refine**: Manually adjust imported data if needed
7. **Export**: File → Export to OpenDrive

See [OSM_IMPORT_GUIDE.md](docs/OSM_IMPORT_GUIDE.md) for detailed instructions.

## Project File Format

Projects are saved as JSON files with `.orbit` extension containing:
- Image path
- Polylines (pixel coordinates)
- Roads with lane sections
- Junctions with connecting roads and lane connections
- Signals and objects
- Control points (for georeferencing)
- Uncertainty analysis cache
- Metadata (version, timestamps)

## OpenDRIVE Export

The export process:
1. Validates each road has exactly one centerline
2. Converts pixel coordinates to metric coordinates using control points
3. Creates local Transverse Mercator projection centered on control points
4. Uses centerline for road reference geometry (planView)
5. Fits curves (lines, arcs) to centerline polyline
6. Exports lane sections with proper s-coordinates
7. Uses actual Road Mark Types from annotated boundaries
8. Exports junctions with:
   - Connecting roads (full road elements with geometry)
   - Lane links (lane-to-lane mappings)
   - Proper predecessor/successor references
9. Generates ASAM OpenDRIVE 1.7 XML

## Development

See [DEV_GUIDE.md](docs/DEV_GUIDE.md) for architecture overview and contribution guidelines.

### Running Tests
```bash
uv run python -m pytest tests/ -v
```

### Project Structure
```
orbit/
├── models/       # Data classes (Road, Polyline, Junction, etc.)
├── gui/          # PyQt6 GUI components
├── export/       # OpenDRIVE XML generation
├── import/       # OSM and OpenDRIVE import
└── utils/        # Coordinate transforms, geometry
```

## Recent Changes (v0.3.1)

- **Junction improvements**: Full connecting road and lane connection support
- **Export refactoring**: Extracted LaneBuilder, SignalBuilder, ObjectBuilder classes
- **Graphics refactoring**: Extracted graphics items to `gui/graphics/` module
- **Bug fixes**: Virtual junction export, lane width calculations
- **Code cleanup**: Removed deprecated code, added unit tests
- **Documentation**: Added developer guide

## License

MIT License - See LICENSE file for details.

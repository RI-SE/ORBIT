# ORBIT Developer Guide

A guide for developers who want to understand and contribute to ORBIT.

**Prerequisites**: Familiarity with Python 3.10+, basic PyQt/Qt concepts, and ASAM OpenDRIVE format.

---

## Table of Contents

1. [Introduction](#introduction)
2. [Getting Started](#getting-started)
3. [Architecture Overview](#architecture-overview)
4. [Data Models](#data-models)
5. [Coordinate Systems](#coordinate-systems)
6. [Lane Sections](#lane-sections)
7. [Junctions](#junctions)
8. [GUI Architecture](#gui-architecture)
9. [Export Pipeline](#export-pipeline)
10. [Import Pipeline](#import-pipeline)
11. [Development Workflow](#development-workflow)
12. [Code Style](#code-style)
13. [Testing](#testing)

---

## Introduction

ORBIT (OpenDrive Road Builder from Imagery Tool) is a PyQt6 desktop application for creating OpenDRIVE road networks by annotating aerial/satellite imagery. Users draw polylines on images, group them into roads, add georeferencing control points, and export to OpenDRIVE 1.7 XML.

### Core Workflow

```
Image → Draw Polylines → Group into Roads → Add Control Points → Export OpenDRIVE
```

### Why ORBIT?

Creating OpenDRIVE files typically requires expensive commercial tools or manual XML editing. ORBIT provides a visual approach: annotate what you see in imagery, and the tool handles the geometric transformations and XML generation.

---

## Getting Started

### Setup

```bash
# Clone and enter directory
cd ORBIT

# Install dependencies with uv (recommended)
uv sync --extra dev

# Or with pip
pip install -e ".[dev]"
```

### Running

```bash
# Start empty
uv run python start_orbit

# Start with image
uv run python start_orbit path/to/aerial_image.jpg

# Verbose mode (debug logging)
uv run python start_orbit --verbose
```

### Running Tests

```bash
uv run python -m pytest tests/ -v
```

### Project Structure

```
orbit/
├── models/           # Data classes (Road, Polyline, Junction, etc.)
├── gui/              # PyQt6 GUI components
│   ├── graphics/     # QGraphicsItem subclasses
│   └── widgets/      # Tree widgets
├── export/           # OpenDRIVE XML generation
│   ├── opendrive_writer.py
│   ├── lane_builder.py
│   ├── signal_builder.py
│   └── object_builder.py
├── import/           # OSM and OpenDRIVE import
│   ├── osm_importer.py
│   ├── opendrive_importer.py
│   └── junction_analyzer.py
└── utils/            # Coordinate transforms, geometry, logging
```

---

## Architecture Overview

### Data Flow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    ImageView    │────▶│     Project     │────▶│  OpenDriveWriter│
│  (user input)   │     │  (data store)   │     │    (export)     │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │                       │
        ▼                       ▼                       ▼
   Qt Signals            JSON .orbit file         OpenDRIVE XML
```

1. **User Interaction**: `ImageView` handles mouse/keyboard events, creates/modifies graphics items
2. **Data Storage**: `Project` holds all data (polylines, roads, junctions, control points)
3. **UI Updates**: Qt signals propagate changes to tree widgets and other UI components
4. **Export**: `OpenDriveWriter` transforms pixel data to metric coordinates and generates XML

### Key Principle: Pixel-First

All geometric data is stored in **pixel coordinates**. Conversion to geographic or metric coordinates happens only at export time. This keeps the data model simple and allows working with non-georeferenced imagery.

---

## Data Models

All models are Python dataclasses in `orbit/models/`. They implement `to_dict()` and `from_dict()` for JSON serialization.

### Project

Top-level container. Holds all data and manages save/load.

```python
@dataclass
class Project:
    polylines: List[Polyline]
    roads: List[Road]
    junctions: List[Junction]
    control_points: List[ControlPoint]
    signals: List[Signal]
    objects: List[RoadObject]
    image_path: Optional[str]
    metadata: dict  # version, created, modified
```

### Polyline

A sequence of points drawn on the image.

```python
@dataclass
class Polyline:
    id: str
    points: List[Tuple[float, float]]  # Pixel coordinates
    line_type: LineType  # CENTERLINE or BOUNDARY
    road_mark_type: RoadMarkType  # SOLID, BROKEN, etc.
    color: str
    closed: bool
```

**Important**: Every road needs exactly ONE polyline marked as `LineType.CENTERLINE`. This defines the road's reference line for OpenDRIVE.

### Road

Groups polylines and defines lane configuration.

```python
@dataclass
class Road:
    id: str
    name: str
    polyline_ids: List[str]
    centerline_id: str
    road_type: RoadType
    lane_sections: List[LaneSection]
    speed_limit: Optional[int]
    # Connectivity
    predecessor_id: Optional[str]
    successor_id: Optional[str]
    junction_id: Optional[str]
```

### LaneSection

A segment of road with fixed lane configuration. OpenDRIVE requires new sections where lane count changes.

```python
@dataclass
class LaneSection:
    section_number: int
    s_start: float  # Start position in pixels
    s_end: float    # End position in pixels
    end_point_index: Optional[int]  # Centerline point index
    lanes: List[Lane]
    single_side: Optional[str]  # OpenDRIVE attribute
```

### Lane

Individual lane within a section.

```python
@dataclass
class Lane:
    id: int  # 0=center, negative=right, positive=left
    lane_type: LaneType  # DRIVING, SHOULDER, SIDEWALK, etc.
    width: float  # In meters (not pixels!)
    road_mark_type: RoadMarkType
```

### Junction

Intersection where multiple roads meet.

```python
@dataclass
class Junction:
    id: str
    name: str
    center_point: Optional[Tuple[float, float]]
    connected_road_ids: List[str]
    connecting_roads: List[ConnectingRoad]
    lane_connections: List[LaneConnection]
    junction_type: str  # "default" or "virtual"
    is_roundabout: bool
```

### ControlPoint

Pixel-to-geographic coordinate mapping for georeferencing.

```python
@dataclass
class ControlPoint:
    id: str
    name: str
    pixel_x: float
    pixel_y: float
    latitude: float
    longitude: float
```

---

## Coordinate Systems

Understanding coordinate systems is crucial for working with ORBIT.

### Three Coordinate Spaces

1. **Pixel Space** (internal)
   - Origin: top-left of image
   - Units: pixels
   - Used for: all storage, drawing, editing

2. **Geographic Space** (intermediate)
   - WGS84 latitude/longitude
   - Used for: control points, OSM import

3. **Metric Space** (export)
   - Local Transverse Mercator projection
   - Origin: center of control points
   - Units: meters
   - Used for: OpenDRIVE output

### CoordinateTransformer

The `CoordinateTransformer` class handles all conversions:

```python
from orbit.utils import create_transformer

# Create from control points
transformer = create_transformer(control_points)

# Convert pixel to meters
x_m, y_m = transformer.pixel_to_meters(pixel_x, pixel_y)

# Batch conversion
points_m = transformer.pixels_to_meters_batch(pixel_points)

# Get scale factors
scale_x, scale_y = transformer.get_scale_factors()  # meters per pixel
```

### Why Pixel-First?

- Works without georeferencing (for testing/prototyping)
- Simpler data model (no projection complexity in storage)
- Editing operations don't accumulate floating-point errors
- Export can use different projections without re-annotating

---

## Lane Sections

Lane sections are how OpenDRIVE handles varying lane configurations along a road.

### The Problem

A road might have:
- 2 lanes for the first 500m
- 3 lanes (merge) for the next 200m
- 2 lanes again after

OpenDRIVE requires splitting this into 3 `<laneSection>` elements, each with its own lane definitions.

### ORBIT's Approach

Each `Road` has a list of `LaneSection` objects:

```python
road.lane_sections = [
    LaneSection(section_number=1, s_start=0, s_end=500, lanes=[...]),
    LaneSection(section_number=2, s_start=500, s_end=700, lanes=[...]),
    LaneSection(section_number=3, s_start=700, s_end=900, lanes=[...]),
]
```

### Section Boundaries

Section boundaries are tied to centerline points via `end_point_index`:

```python
# Section ends at centerline point 15
section.end_point_index = 15

# Last section extends to end of road
last_section.end_point_index = None
```

When centerline points change, call these methods:

```python
# BEFORE inserting a point
road.adjust_section_indices_after_insertion(point_index)

# BEFORE deleting a point
road.adjust_section_indices_after_deletion(point_index)

# AFTER any centerline modification
road.update_section_boundaries(centerline_points)
```

### Creating Sections

Users split sections via right-click on centerline points:

```python
# In ImageView context menu
road.split_section_at_point(point_index, centerline_points)
```

---

## Junctions

Junctions handle intersections where multiple roads meet.

### Junction Types

- **default**: Normal intersection (T-junction, crossroads)
- **virtual**: Path crossing (e.g., pedestrian path over road) - no actual traffic connection

### Components

1. **Connected Roads**: Roads that meet at the junction
2. **Connecting Roads**: Short road segments through the junction (one per valid path)
3. **Lane Connections**: Lane-to-lane mappings

```python
junction = Junction(
    connected_road_ids=["road_1", "road_2", "road_3"],
    connecting_roads=[
        ConnectingRoad(
            predecessor_road_id="road_1",
            successor_road_id="road_2",
            path=[(100, 100), (120, 110), (150, 120)],
            lane_sections=[...]
        ),
        # ... more connecting roads
    ],
    lane_connections=[
        LaneConnection(
            from_road_id="road_1",
            from_lane_id=-1,
            to_road_id="road_2",
            to_lane_id=-1,
            connecting_road_id="conn_road_1",
            turn_type="right"
        ),
        # ... more lane connections
    ]
)
```

### Automatic Generation

The `JunctionAnalyzer` (`import/junction_analyzer.py`) can automatically generate connecting roads and lane connections based on road geometry:

```python
from orbit.import.junction_analyzer import analyze_junction_geometry

geometry_info = analyze_junction_geometry(junction, roads_dict, polylines_dict)
# Returns road angles, suggested connections, etc.
```

---

## GUI Architecture

### Main Components

```
MainWindow
├── ImageView (central widget - QGraphicsView)
│   └── QGraphicsScene
│       ├── Image item
│       ├── PolylineGraphicsItem (per polyline)
│       ├── RoadLanesGraphicsItem (per road)
│       │   └── InteractiveLanePolygon (per lane segment)
│       ├── JunctionMarkerItem (per junction)
│       └── ConnectingRoadGraphicsItem (per connecting road)
├── ElementsTreeWidget (left dock)
├── RoadTreeWidget (right dock)
└── Dialogs (modal)
```

### Signal-Slot Pattern

Components communicate via Qt signals:

```python
# ImageView emits signals when data changes
class ImageView(QGraphicsView):
    polyline_added = pyqtSignal(object)
    polyline_modified = pyqtSignal(object)
    road_modified = pyqtSignal(object)

# MainWindow connects signals to handlers
self.image_view.polyline_added.connect(self.on_polyline_added)

def on_polyline_added(self, polyline):
    self.project.add_polyline(polyline)
    self.elements_tree.refresh()
    self.modified = True
```

### Graphics Items

Custom `QGraphicsItem` subclasses in `gui/graphics/`:

| Class | Purpose |
|-------|---------|
| `PolylineGraphicsItem` | Displays polyline with points |
| `InteractiveLanePolygon` | Clickable/hoverable lane polygon |
| `RoadLanesGraphicsItem` | Container for road's lane polygons |
| `JunctionMarkerItem` | Junction center marker |
| `ConnectingRoadGraphicsItem` | Junction connecting road path |

### Adding a New Dialog

1. Create `gui/my_dialog.py`:

```python
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QDialogButtonBox

class MyDialog(QDialog):
    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.data = data
        self.setup_ui()
        self.load_data()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        # Add widgets...

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def load_data(self):
        # Populate widgets from self.data
        pass

    def accept(self):
        # Save widget values to self.data
        super().accept()
```

2. Add menu action in `MainWindow`:

```python
def create_actions(self):
    self.my_action = QAction("My Feature", self)
    self.my_action.triggered.connect(self.show_my_dialog)

def show_my_dialog(self):
    dialog = MyDialog(self.some_data, self)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        self.modified = True
```

---

## Export Pipeline

### OpenDriveWriter

The main export class in `export/opendrive_writer.py`:

```python
writer = OpenDriveWriter(
    project=project,
    transformer=transformer,  # CoordinateTransformer
    preserve_geometry=True,   # Keep all polyline points
    country_code="se"
)

success = writer.write(output_path)
```

### Export Process

1. **Create header** with geoReference (PROJ4 string)
2. **For each road**:
   - Convert centerline to meters
   - Fit geometry (lines/arcs) via `CurveFitter`
   - Calculate road length
   - Export lane sections via `LaneBuilder`
   - Export signals via `SignalBuilder`
   - Export objects via `ObjectBuilder`
3. **For each junction**:
   - Export connecting roads
   - Export lane connections

### Builder Classes

Export logic is split into focused builders:

| Class | Responsibility |
|-------|----------------|
| `LaneBuilder` | `<lanes>` element with sections |
| `SignalBuilder` | `<signals>` element |
| `ObjectBuilder` | `<objects>` element |

### Geometry Fitting

`CurveFitter` converts polylines to OpenDRIVE geometry:

```python
fitter = CurveFitter(
    line_tolerance=0.1,  # Max deviation for lines (meters)
    arc_tolerance=0.5    # Max deviation for arcs (meters)
)

elements = fitter.fit_polyline(points_meters)
# Returns list of GeometryElement (LINE, ARC, or SPIRAL)
```

With `preserve_geometry=True`, each polyline segment becomes a separate line element (no fitting).

---

## Import Pipeline

### OSM Import

Imports road networks from OpenStreetMap via Overpass API:

```python
from orbit.import.osm_importer import OSMImporter

importer = OSMImporter(project, transformer)
stats = importer.import_from_bbox(
    min_lat, min_lon, max_lat, max_lon,
    detail_level="moderate"  # or "full"
)
```

**Flow**:
1. Query Overpass API for roads/signals/objects in bounding box
2. Parse OSM JSON into intermediate objects
3. Convert to ORBIT models (Road, Signal, RoadObject)
4. Detect junctions where roads meet
5. Generate connecting roads via `JunctionAnalyzer`

### OpenDRIVE Import

Round-trip import from existing OpenDRIVE files:

```python
from orbit.import.opendrive_importer import import_opendrive

project = import_opendrive(xodr_path, transformer)
```

Useful for editing existing OpenDRIVE or testing export accuracy.

---

## Development Workflow

### Adding a New Model Field

1. Add field to dataclass:
```python
@dataclass
class Road:
    # ... existing fields ...
    new_field: Optional[str] = None
```

2. Update serialization:
```python
def to_dict(self):
    data = {
        # ... existing fields ...
        'new_field': self.new_field,
    }
    return data

@classmethod
def from_dict(cls, data):
    return cls(
        # ... existing fields ...
        new_field=data.get('new_field'),  # Default for old files
    )
```

3. Add UI if needed (dialog, tree column, etc.)

### Adding Export Support for New Element

1. Create builder method or class in `export/`
2. Call from `OpenDriveWriter._create_road()` or similar
3. Test with OpenDRIVE validator

### Debugging Tips

- Use `--verbose` flag for debug logging
- Check `self.scene.items()` for graphics item issues
- Use `to_dict()` to inspect model state
- Export and view in esmini for visual validation

---

## Code Style

### Type Hints

Always use type hints:

```python
def calculate_distance(
    p1: Tuple[float, float],
    p2: Tuple[float, float]
) -> float:
    """Calculate Euclidean distance between two points."""
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    return math.sqrt(dx * dx + dy * dy)
```

### Imports

```python
# Standard library
from dataclasses import dataclass
from typing import List, Optional, Tuple

# Third-party
from PyQt6.QtWidgets import QDialog
import numpy as np

# Local
from orbit.models import Road, Polyline
from orbit.utils import create_transformer
```

### Naming

- Classes: `PascalCase`
- Functions/methods: `snake_case`
- Constants: `UPPER_CASE`
- Private: `_leading_underscore`
- Qt overrides: `camelCase` (framework convention)

### Docstrings

```python
def transform_point(self, x: float, y: float) -> Tuple[float, float]:
    """
    Transform pixel coordinates to meters.

    Args:
        x: Pixel x-coordinate
        y: Pixel y-coordinate

    Returns:
        Tuple of (x_meters, y_meters) in local projection

    Raises:
        ValueError: If transformer not initialized
    """
```

---

## Testing

### Running Tests

```bash
# All tests
uv run python -m pytest tests/ -v

# Specific module
uv run python -m pytest tests/unit/test_models/test_road.py -v

# With coverage
uv run python -m pytest tests/ --cov=orbit --cov-report=term-missing
```

### Test Structure

```
tests/
├── unit/
│   ├── test_models/      # Model class tests
│   ├── test_export/      # Export tests
│   └── test_utils/       # Utility function tests
├── integration/          # Multi-component tests
└── conftest.py          # Pytest fixtures
```

### Writing Tests

```python
import pytest
from orbit.models import Road, LaneSection, Lane, LaneType

class TestRoadSections:
    def test_split_section(self):
        """Test splitting a section at a point."""
        road = Road()
        road.lane_sections = [
            LaneSection(
                section_number=1,
                s_start=0.0,
                s_end=300.0,
                lanes=[Lane(id=0, lane_type=LaneType.NONE, width=0.0)]
            )
        ]

        points = [(0, 0), (100, 0), (200, 0), (300, 0)]
        success = road.split_section_at_point(2, points)

        assert success
        assert len(road.lane_sections) == 2
```

### Manual Testing

For GUI changes, test manually:

1. Load test image
2. Draw polylines, create roads
3. Add control points (georeferencing)
4. Export to OpenDRIVE
5. Validate with esmini or other viewer

---

## Quick Reference

### Key Files

| File | Purpose |
|------|---------|
| `start_orbit` | Entry point |
| `models/project.py` | Project container, save/load |
| `models/road.py` | Road with lane sections |
| `gui/image_view.py` | Main drawing canvas |
| `gui/main_window.py` | Application window |
| `export/opendrive_writer.py` | XML generation |
| `utils/coordinate_transform.py` | Pixel ↔ meter conversion |

### Common Operations

```python
# Get road's centerline polyline
centerline = project.get_polyline(road.centerline_id)

# Get transformer for export
transformer = create_transformer(project.control_points)

# Convert coordinates
x_m, y_m = transformer.pixel_to_meters(px, py)

# Access lane in section
lane = road.get_lane(lane_id=-1, section_number=1)

# Split section at point
road.split_section_at_point(point_index, centerline.points)
```

### OpenDRIVE Lane IDs

```
Left lanes:   +3  +2  +1
Center lane:       0
Right lanes:  -1  -2  -3
              ←  travel direction
```

For right-hand traffic, vehicles drive in negative-ID lanes.

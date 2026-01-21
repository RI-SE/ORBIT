# ORBIT User Guide

Complete guide for creating OpenDRIVE road networks from aerial imagery using ORBIT.

**Version**: 0.4.0 | **OpenDRIVE**: 1.8

---

## Contents

- [Getting Started](#getting-started)
- [Basic Workflow](#basic-workflow)
- [Drawing Polylines](#drawing-polylines)
- [Creating Roads](#creating-roads)
- [Lane Sections](#lane-sections)
- [Junctions](#junctions)
- [Georeferencing](#georeferencing)
- [Import Features](#import-features)
- [Export to OpenDRIVE](#export-to-opendrive)
- [View Controls](#view-controls)
- [Keyboard Shortcuts](#keyboard-shortcuts)
- [Troubleshooting](#troubleshooting)
- [Best Practices](#best-practices)

---

## Getting Started

### Installation

```bash
# Using uv (recommended)
uv sync

# Or using pip
pip install -e .
```

### Launch

```bash
# Start with image
orbit path/to/aerial_image.jpg

# Start empty (load image via File menu)
orbit

# Enable verbose logging
orbit --verbose

# Enable XSD schema validation for exports
orbit --xodr_schema /path/to/OpenDRIVE_Core.xsd
```

> **Note**: If `orbit` is not in your PATH, use `uv run orbit` instead.

---

## Basic Workflow

The typical workflow from aerial image to OpenDRIVE export:

```
Load Image → Draw Polylines → Create Roads → Add Junctions → Georeference → Export
```

### Quick Start Example

1. **Load image**: `orbit intersection.jpg` or File → Load Image
2. **Draw centerline**: Click "New Line", trace road center, double-click to finish
3. **Set as centerline**: Double-click polyline, change Line Type to "Centerline"
4. **Draw boundaries**: Trace lane markings with appropriate road mark types
5. **Create road**: Select polylines, press Ctrl+G to group into road
6. **Add control points**: Tools → Georeferencing (minimum 3 points)
7. **Export**: File → Export to OpenDrive

---

## Drawing Polylines

Polylines represent road centerlines and lane boundaries.

### Line Types

| Type | Color | Purpose |
|------|-------|---------|
| **Centerline** | Orange | Road reference line (exactly one per road) |
| **Lane Boundary** | Cyan | Visual lane markings (solid, broken, etc.) |

New polylines default to **Lane Boundary**. Change type via double-click.

### Drawing Operations

**Start Drawing**:
- Click "New Line" button (right sidebar)
- Or press **Ctrl+P**
- Or menu: Tools → New Polyline

**Add Points**:
- Click on image to add points
- Points connect with colored lines

**Finish Polyline**:
- **Double-click** to finish
- Or press **Enter**
- Or press **Escape** to cancel

### Editing Points

| Action | How |
|--------|-----|
| Move point | Click and drag |
| Insert point | Ctrl+Click on line segment |
| Delete point | Right-click on point |
| Delete polyline | Select + Delete key |

### Polyline Properties

Double-click a polyline to edit:

- **Line Type**: Centerline or Lane Boundary
- **Road Mark Type** (for boundaries): solid, broken, solid solid, solid broken, etc.

---

## Creating Roads

Roads group polylines and define lane configuration.

### Method 1: Quick Creation

1. Select a polyline by clicking on it
2. Press **Ctrl+G** (or Tools → Group to Road)
3. Fill in road properties
4. Click OK

### Method 2: Create Empty Road First

1. Open Roads panel (right sidebar)
2. Click "New Road"
3. Fill in properties
4. Assign polylines later via "Assign Selected"

### Road Properties

**Basic Properties**:
- **Road Name**: Descriptive name (e.g., "Main Street")
- **Road Type**: ASAM OpenDRIVE road type (motorway, town, rural, etc.)
- **Speed Limit**: In km/h (0 = no limit)

**Centerline Selection**:
- ✅ Green: Exactly one centerline (correct)
- ⚠️ Orange: No centerline (needs one)
- ❌ Red: Multiple centerlines (only one allowed)

**Lane Configuration**:
- **Left/Right Lanes**: Number of lanes in each direction
- **Lane Width**: Default width in meters (1.0-10.0m, default 3.5m)
- **Traffic Direction**: Right-hand (default) or left-hand traffic

### Roads Panel Operations

The Roads panel shows a hierarchical tree:

```
├─ Highway 101 (motorway) - 100 km/h
│  ├─ Polyline (5 points)
│  └─ Polyline (8 points)
├─ Main Street (town) - 50 km/h
│  └─ Polyline (12 points)
└─ Unassigned Polylines
   └─ Polyline (3 points)
```

- **Double-click** road → Edit properties
- **Right-click** road → Context menu (Edit, Delete)
- **Double-click** polyline → Highlight in view

---

## Lane Sections

Roads can be divided into sections where lane configuration changes.

### Creating Sections

1. Right-click on a centerline point
2. Select "Split Section Here"
3. A new section is created with the same lane configuration
4. Edit each section independently

### Editing Sections

1. In Road Tree, expand road to see sections
2. Double-click section or right-click → "Edit Section Properties"
3. Modify the `singleSide` attribute if needed (OpenDRIVE attribute)

### Section Properties

- **Section Number**: Sequential numbering (1, 2, 3...)
- **s_start / s_end**: Position along centerline
- **singleSide**: OpenDRIVE attribute (left, right, or none)

---

## Junctions

Junctions handle intersections where multiple roads meet.

### Creating a Junction

1. Press **Ctrl+J** or Tools → Add Junction
2. Click on the map where the intersection is located
3. Fill in junction properties:
   - **Junction Name**: e.g., "Main & Oak Intersection"
   - **Junction Type**: default or virtual
   - **Connected Roads**: Select and add roads
4. Click OK

### Junction Operations

- **Move junction**: Click and drag the marker
- **Edit junction**: Double-click the marker
- **Delete junction**: Select + Delete key

### Junction Types

- **default**: Normal intersection (T-junction, crossroads)
- **virtual**: Path crossing without traffic connection

### Roundabout Wizard

Create roundabouts via Tools → Create Roundabout:

- **Center Point**: Click "Pick on Map" or enter coordinates
- **Radius**: Inner and outer radius
- **Lanes**: Number of circular lanes
- **Traffic Direction**: Clockwise or counter-clockwise
- **Approach Roads**: Select connecting roads

---

## Georeferencing

Georeferencing converts pixel coordinates to real-world geographic coordinates.

### Why Georeference?

- Accurate distance measurements (lane widths in meters)
- OpenDRIVE export requires metric coordinates
- OSM import requires image-to-world mapping
- GIS integration

### Adding Control Points

1. Go to **Tools → Georeferencing**
2. Click "Pick Point on Image"
3. Click on a distinctive feature
4. Enter latitude/longitude coordinates
5. Click "Add Control Point"
6. Repeat (minimum 3 points required)

### Control Point Placement

**Good placement**:
- Spread across entire image
- Cover corners and edges
- Use distinctive features (road intersections, building corners)
- Verify coordinates from reliable sources

**Poor placement** (avoid):
- All points clustered in one area
- Points in a straight line
- Vague features

### Transformation Methods

- **Affine** (3+ points): Best for orthoimages, nadir views
- **Homography** (4+ points): Best for drone images, oblique angles

### Uncertainty Analysis

For quality assessment:
- Click "Compute Uncertainty (Monte Carlo)"
- Review mean/max uncertainty
- Enable View → Uncertainty Overlay to visualize
- Use "Suggest GCP Locations" for optimal placement

See the [Georeferencing Guide](GEOREFERENCING.md) for complete details.

---

## Import Features

### OpenStreetMap Import

Import road networks from OSM via Overpass API.

**Prerequisites**:
- Image loaded in ORBIT
- At least 3 control points set up

**Process**:
1. File → Import OpenStreetMap Data (Ctrl+Shift+I)
2. Configure options:
   - Import Mode: Add or Replace
   - Detail Level: Moderate or Full
   - Lane Width: Default when not in OSM
3. Click Import

See the [OSM Import Guide](OSM_IMPORT.md) for details.

### OpenDRIVE Import

Import existing .xodr files for round-trip editing:

1. File → Import OpenDRIVE
2. Select .xodr file
3. Review imported elements

---

## Export to OpenDRIVE

### Export Process

1. Press **Ctrl+E** or File → Export to OpenDrive
2. Review the Export Dialog:
   - Project Summary: counts of elements
   - Georeferencing Status: ✓ Active (green) required
   - Transformation Info: control points, RMS error, scale
3. Set export options:
   - **Preserve Geometry**: Keep all polyline points (default)
   - **Curve Fitting**: Enable line/arc fitting tolerances
4. Click "Browse" to select output location
5. Click "Export"

### Schema Validation

Enable XSD validation against ASAM schema:

```bash
orbit --xodr_schema /path/to/OpenDRIVE_Core.xsd
```

Download schema from [ASAM OpenDRIVE Specification](https://publications.pages.asam.net/standards/ASAM_OpenDRIVE/ASAM_OpenDRIVE_Specification/latest/specification/).

### Export Contents

The generated .xodr file includes:
- Road geometry (lines, arcs, clothoids)
- Lane sections with proper s-coordinates
- Lane widths and road marks
- Junction connections
- Signals and objects
- Geographic reference (PROJ4)

---

## View Controls

### Navigation

| Action | Method |
|--------|--------|
| Zoom in/out | Mouse wheel |
| Pan view | Click and drag (when not drawing) |
| Zoom in | Ctrl + + |
| Zoom out | Ctrl + - |
| Fit to window | Ctrl + 0 |
| Reset view | Ctrl + R |

---

## Keyboard Shortcuts

### File Operations

| Shortcut | Action |
|----------|--------|
| Ctrl+N | New Project |
| Ctrl+O | Open Project |
| Ctrl+S | Save Project |
| Ctrl+Shift+S | Save As |
| Ctrl+I | Load Image |
| Ctrl+E | Export to OpenDrive |
| Ctrl+Shift+I | Import OSM Data |
| Ctrl+Q | Quit |

### Editing

| Shortcut | Action |
|----------|--------|
| Delete | Delete selected item |
| Esc | Cancel current operation |

### Drawing & Tools

| Shortcut | Action |
|----------|--------|
| Ctrl+P | Start new polyline |
| Enter | Finish polyline |
| Esc | Cancel polyline |
| Ctrl+G | Group to road |
| Ctrl+J | Add junction |

### View

| Shortcut | Action |
|----------|--------|
| Ctrl + + | Zoom in |
| Ctrl + - | Zoom out |
| Ctrl+0 | Fit to window |
| Ctrl+R | Reset view |

---

## Troubleshooting

### Common Issues

**Image won't load**
- Check file path is correct
- Verify format is supported (JPG, PNG, BMP, TIF)
- Try absolute path

**Can't draw polylines**
- Ensure "New Line" mode is active
- Check that image is loaded

**Can't export**
- Verify at least one road exists
- Check georeferencing (minimum 3 control points)
- Ensure each road has exactly one centerline

**High RMS error**
- Add more control points
- Check coordinate accuracy
- Ensure points are well-distributed

**Roads don't align with OSM import**
- Review control point coordinates
- Add more control points for better accuracy
- Check lat/lon not swapped

---

## Best Practices

### Polyline Drawing

1. Follow road centerlines precisely
2. Use enough points to capture curves
3. Draw consistently in traffic flow direction
4. Create separate polylines for different road segments

### Road Organization

1. Use descriptive, unique names
2. Apply consistent road type classification
3. Set realistic speed limits
4. Verify exactly one centerline per road

### Georeferencing

1. Place 4 corner control points first
2. Add 2-4 edge/interior points
3. Target RMSE < 3 pixels
4. Run uncertainty analysis for quality assessment

### Project Management

1. Save frequently (Ctrl+S)
2. Use descriptive filenames with location/date
3. Keep images and projects together
4. Make backup copies of important work

---

## Related Documentation

- [Georeferencing Guide](GEOREFERENCING.md) - Detailed control point guide
- [OSM Import Guide](OSM_IMPORT.md) - OpenStreetMap import
- [Validation Guide](VALIDATION.md) - Uncertainty analysis
- [Developer Guide](DEV_GUIDE.md) - Architecture and contribution

---

**Last Updated**: 2026-01

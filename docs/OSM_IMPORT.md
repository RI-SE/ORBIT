# OpenStreetMap Import & Export Guide

## Overview

ORBIT can **import** road network data from OpenStreetMap and **export** annotated map data back to OSM XML format. Import queries the Overpass API to retrieve road geometries, lane configurations, traffic signals, and roadside objects, then converts them to ORBIT's native format. Export writes ORBIT roads, signals, and objects to a standard `.osm` file.

**Status**: ✅ Import and Export implemented (2026-02)

---

## Quick Start

### Prerequisites

Import supports two modes:

1. **Image + Georeferencing** (recommended): A loaded image with at least 4 control points.
   The bounding box is derived from the image extent.
2. **Coordinate mode** (no image): Specify a center coordinate, radius, and pixel scale.
   ORBIT creates a synthetic canvas and affine transform automatically.

### Import Process
1. **Open Import Dialog**: File → Import OpenStreetMap Data (`Ctrl+Shift+I`)
2. **Review Bounding Box**: Dialog shows calculated geographic bounds
3. **Configure Options**:
   - **Import Mode**: Add to existing or Replace all
   - **Detail Level**: Moderate (roads + signals) or Full (+ objects)
   - **Lane Width**: Default width when not specified in OSM (2.0-5.0m)
   - **Junctions**: Toggle junction detection and section splitting
   - **Custom Radius** (georef mode): Override the image-derived bbox with a radius
     in meters around the image center. Useful for importing context beyond the image.
4. **Click Import**: Progress dialog shows during import
5. **Review Results**: Success dialog displays import statistics

### Custom Radius and the Hybrid Transformer

When a custom radius extends beyond the image, ORBIT uses a **hybrid transformer**
that blends homography (inside the image) with affine (outside) to prevent
coordinate distortion. This is automatic — no configuration needed. See
[GEOREFERENCING.md](GEOREFERENCING.md#hybrid-transformer-homography--affine-blending)
for technical details.

---

## Features

### Road Network Import
- **Highway Types**: All drivable roads (motorway, trunk, primary, secondary, residential, etc.)
- **Lane Configuration**:
  - Estimates lane count from `lanes`, `lanes:forward`, `lanes:backward` tags
  - Creates proper OpenDrive lane numbering (0=center, negative=right, positive=left)
  - Handles oneway roads (lanes on correct side only)
- **Speed Limits**: Extracts from `maxspeed` tag, supports km/h and mph
- **Road Types**: Maps OSM highway types to OpenDrive road types
- **Road Names**: Uses OSM name or generates "OSM Way {id}" for unnamed roads

### Junction Detection
- Automatically detects intersections where 3+ roads meet
- Creates Junction objects with connected road IDs
- Splits lane sections at junction boundaries
- Preserves lane configuration across sections

### Traffic Signals & Signs
- **Traffic Signals**: From `highway=traffic_signals` nodes
- **Speed Limit Signs**: From `traffic_sign=maxspeed` nodes
- **Sign Values**: Parses speed values and units from various formats

### Roadside Objects (Full Mode)
- **Street Lamps**: From `highway=street_lamp` nodes
- **Guardrails**: From `barrier=guard_rail` ways (polyline objects)
- **Trees**: From `natural=tree` nodes (broadleaf/conifer)
- **Buildings**: From `building=*` ways (with dimension estimation)

### Import Options
- **Import Mode**:
  - **Add**: Imports alongside existing annotations
  - **Replace**: Clears all existing data before import
- **Detail Level**:
  - **Moderate**: Roads, lanes, traffic signals, speed limit signs
  - **Full**: Moderate + street furniture, buildings, vegetation
- **Configurable**:
  - Default lane width (2.0-5.0 meters)
  - Junction detection toggle

### Data Quality
- **Duplicate Detection**: Tracks imported OSM IDs to prevent re-importing
- **Partial Import**: Keeps successfully imported data if API times out
- **Validation**: Checks for georeferencing and loaded image before import
- **Error Handling**: Graceful handling of missing tags, API failures, network issues

---

## Technical Details

### Module Structure
```
import/
├── __init__.py              # Module exports
├── osm_mappings.py          # OSM tag → ORBIT/OpenDrive mappings (import side)
├── osm_query.py             # Overpass API client
├── osm_parser.py            # JSON parser for OSM data
├── osm_to_orbit.py          # Feature converters (OSM → ORBIT)
└── osm_importer.py          # Main import orchestrator

export/
├── osm_writer.py            # OSM XML writer (ORBIT → .osm)
└── osm_mappings.py          # ORBIT → OSM tag mappings (export side)

utils/
└── coordinate_transform.py  # AffineTransformer, HomographyTransformer,
                             # HybridTransformer, create_transformer
```

### Overpass API
- **Endpoint**: https://overpass-api.de/api/interpreter (with backup)
- **Timeout**: 60 seconds
- **Query Format**: Overpass QL with bounding box
- **Response**: JSON format (nodes, ways, relations)
- **Rate Limiting**: Automatic retry with backup endpoint on failure

### Coordinate Transformation
- Uses `CoordinateTransformer` from the utils module
- Calculates bounding box from image corners with 5% buffer (or from user-specified center + radius)
- Transforms OSM lat/lon coordinates to pixel space
- When custom radius exceeds image bounds, a `HybridTransformer` blends homography
  (inside image) with affine (outside) to prevent projective distortion artifacts
- Maintains consistency with OpenDrive and OSM export

### OSM Tag Mappings

#### Highway Types → OpenDrive Road Types
| OSM Highway | OpenDrive Type |
|-------------|----------------|
| motorway, motorway_link | motorway |
| trunk, trunk_link, primary, secondary | rural |
| tertiary, residential, living_street, service | town |
| unclassified, road | rural (default) |

#### Default Lane Widths by Road Type
| Road Type | Width (meters) |
|-----------|----------------|
| motorway | 3.75 |
| trunk, primary | 3.5 |
| secondary | 3.25 |
| tertiary, residential | 3.0 |
| service | 2.75 |
| living_street | 2.5 |

#### Default Speed Limits by Road Type
| Road Type | Speed (km/h) |
|-----------|--------------|
| motorway | 110 |
| trunk | 90 |
| primary | 70 |
| secondary | 60 |
| tertiary | 50 |
| residential | 30 |
| service, living_street | 20 |

### Lane Configuration Logic

**Two-Way Roads** (default):
- Splits total lane count between left and right
- Example: `lanes=4` → 2 left lanes, 2 right lanes
- Uses `lanes:forward` and `lanes:backward` if available

**Oneway Roads** (`oneway=yes`):
- All lanes on one side (right by default)
- `oneway=-1` creates lanes on left side (reverse direction)
- Examples:
  - `oneway=yes, lanes=3` → 0 left, 3 right
  - `oneway=-1, lanes=2` → 2 left, 0 right

**Lane IDs** (OpenDrive convention):
- Center lane: 0 (type: none, width: 0)
- Right lanes: -1, -2, -3, ... (increasing magnitude away from center)
- Left lanes: 1, 2, 3, ... (increasing magnitude away from center)

### Junction Detection Algorithm

1. **Build Endpoint Index**:
   - Extract start and end points from all road centerlines
   - Round to tolerance (2 pixels) to match nearby points
   - Store: `(rounded_point) → [(road_id, is_start, exact_point)]`

2. **Identify Junctions**:
   - Find keys with 3+ roads meeting
   - Calculate average position of meeting points
   - Create Junction object with connected road IDs

3. **Split Lane Sections**:
   - For each road, find junction points along centerline
   - Create new lane sections at junction boundaries
   - Duplicate lane configuration from first section
   - Set `end_point_index` to track section boundaries

---

## Import Statistics

After import, you'll see:
- **Roads imported**: Number of new roads created
- **Junctions imported**: Number of intersections detected
- **Signals imported**: Number of traffic signals and signs
- **Objects imported**: Number of furniture/buildings/trees (Full mode only)
- **Duplicates skipped**: Number of features already in project
- **Partial import warning**: If API timed out before completing

---

## Troubleshooting

### "Georeferencing Required" Error
**Cause**: Less than 3 control points defined

**Solution**:
1. Go to **Tools → Georeferencing**
2. Add at least 3 control points with pixel and lat/lon coordinates
3. Ensure points are not collinear (form a triangle or polygon)

### No Image Loaded
An image is no longer required. Without an image, the import dialog switches to
**coordinate mode** where you enter a center lat/lon, radius, and pixel scale.
ORBIT creates a synthetic canvas with an affine transform from those parameters.

### "Overpass API Error" or "Request timed out"
**Cause**: Network issue, API overload, or very large area

**Solutions**:
- **Check network connection**: Ensure internet access
- **Reduce area**: Use smaller image or tighter georeferencing
- **Retry**: API may be temporarily overloaded
- **Partial import**: If timeout occurred, already-imported data is kept

### No Roads Imported
**Causes**:
- Area has no roads in OpenStreetMap
- Bounding box doesn't overlap with road network
- Roads are excluded types (footways, paths, cycleways)

**Solutions**:
- Check OpenStreetMap coverage at https://www.openstreetmap.org
- Verify georeferencing accuracy (check control points)
- Adjust image alignment or control point coordinates

### Roads Don't Align with Image
**Cause**: Inaccurate georeferencing or control points

**Solution**:
1. Review control points in **Tools → Georeferencing**
2. Verify lat/lon coordinates are correct
3. Add more control points for better transformation accuracy
4. Check that image and OSM data use same projection/datum

### Duplicate Roads on Re-Import
**Expected Behavior**: Duplicate detection prevents re-importing same OSM ways

**If seeing duplicates**:
- Are they truly the same roads? Check OSM IDs in road names
- Did you use "Replace All" mode? This clears existing data first
- Report as bug if duplicate detection isn't working

---

## Known Limitations

### Current Implementation
1. **Module Name**: `import` is a Python keyword, requiring `importlib` workaround. Works correctly but not ideal. Consider renaming in future refactoring.

2. **Geometry**: All polyline points preserved (no simplification yet). Can result in many points for curved roads.

3. **Lane Boundaries**: Only centerlines imported. Boundary polylines not generated automatically.

4. **Elevation**: No z-coordinates. Roads are 2D only.

5. **Turn Restrictions**: OSM turn restriction relations not parsed yet.

6. **Lane Types**: All lanes created as "driving" type. Bicycle lanes, parking, sidewalks not separated.

7. **Surface Types**: OSM `surface` tag not imported yet.

8. **API Limits**:
   - 60-second timeout (configurable in code)
   - May fail for very large areas (>10 km²)
   - Public API has rate limiting (unknown thresholds)

### OpenStreetMap Data Quality
- **Completeness**: Varies by region. Some areas have minimal road data.
- **Accuracy**: OSM accuracy depends on contributor efforts and data sources.
- **Tag Consistency**: Tag usage varies by region and mapper preferences.
- **Lane Data**: Many roads lack `lanes` tags; defaults are applied.
- **Speed Limits**: Often missing; type-based defaults used as fallback.

---

## OSM Export

### Overview

Export writes ORBIT project data to a standard OpenStreetMap XML file (`.osm`).
This allows round-tripping data through OSM-compatible tools (JOSM, Valhalla,
SUMO, etc.) and sharing annotated maps with others.

**Menu**: File → Export → Export to OSM...

### What Gets Exported

| Feature | OSM Element | Key Tags |
|---------|-------------|----------|
| Roads | `way` | `highway`, `lanes`, `maxspeed`, `name`, `oneway` |
| Connecting roads | `way` | Inherits `highway` from connected road |
| Traffic signals | `node` | `highway=traffic_signals` |
| Stop / give-way signs | `node` | `highway=stop` / `highway=give_way` |
| Speed limit signs | `node` | `traffic_sign=maxspeed`, `maxspeed` |
| Buildings | `way` (closed) | `building=yes` |
| Guardrails | `way` (open) | `barrier=guard_rail` |
| Trees | `node` | `natural=tree` |
| Street lamps | `node` | `highway=street_lamp` |
| Forest, farmland, etc. | `way` (closed) | `landuse=forest`, `landuse=farmland`, etc. |
| Parking spaces | `way` or `node` | `amenity=parking` |

### Lane Width Tags

Road exports include per-lane width information:

- `lanes`, `lanes:forward`, `lanes:backward` — lane counts
- `width:lanes:forward` — pipe-separated widths for forward (right) lanes, e.g. `3.5|3.5`
- `width:lanes:backward` — pipe-separated widths for backward (left) lanes
- `width` — total road width

### OSM Tag Preservation

Features originally imported from OSM retain their original tags. When
exporting, these preserved tags are written back, with lane/width tags
updated from the current ORBIT model. Manually created features use
default tag mappings from `osm_mappings.py`.

### Requirements

- At least one road with geographic coordinates (georeferencing required)
- A coordinate transformer is created automatically for converting any
  pixel-only geometries (e.g. connecting roads) to geographic coordinates

### Node Deduplication

The exporter uses a grid-based spatial index (~0.5 m threshold) to merge
nearby nodes, producing cleaner output. All node IDs are negative per OSM
convention for unsaved data.

---

## Future Enhancements

### Phase 4a - OSM Enhancements
- [ ] **Road Surface Types**: Import OSM `surface` tag (asphalt, concrete, gravel, etc.)
- [ ] **Lane Type Classification**: Parse cycleway, parking, sidewalk lanes separately
- [ ] **Turn Restrictions**: Import OSM restriction relations, export to OpenDrive links

### Phase 4b - Advanced Features
- [ ] **Geometry Simplification**: Douglas-Peucker algorithm to reduce point count
- [ ] **Lane Boundary Generation**: Create boundary polylines from centerline + widths
- [ ] **Elevation Profiles**: Query elevation APIs for road z-coordinates
- [ ] **Road-Image Snapping**: Use computer vision to snap OSM roads to visible features

---

## Examples

### Example 1: Basic Road Import
```
1. Load image: File → Load Image → aerial_photo.jpg
2. Georeference: Tools → Georeferencing
   - Add control point 1: pixel (100, 100) = lat/lon (59.33, 18.06)
   - Add control point 2: pixel (2000, 100) = lat/lon (59.34, 18.08)
   - Add control point 3: pixel (1000, 1500) = lat/lon (59.32, 18.07)
3. Import: File → Import OpenStreetMap Data
   - Mode: Add to existing
   - Detail: Moderate
   - Lane width: 3.5m
   - Click Import
4. Result: Roads, lanes, and traffic signals imported
```

### Example 2: Full Import with Objects
```
1. (Assuming image and georeferencing already set up)
2. Import: File → Import OpenStreetMap Data
   - Mode: Replace all (clear existing annotations)
   - Detail: Full
   - Lane width: 3.0m (urban area)
   - Junctions: Enabled
   - Click Import
3. Result: Roads, signals, lampposts, guardrails, trees, and buildings imported
```

### Example 3: Re-Import After Area Update
```
1. (Assuming previous import)
2. OpenStreetMap has been updated (new roads added)
3. Import: File → Import OpenStreetMap Data
   - Mode: Add to existing
   - Detail: Moderate
   - Click Import
4. Result: Only new roads imported, existing roads skipped (duplicate detection)
```

---

## API Reference

### OSMImporter Class
```python
import importlib

osm_importer_module = importlib.import_module("orbit.import.osm_importer")
OSMImporter = osm_importer_module.OSMImporter
ImportOptions = osm_importer_module.ImportOptions
ImportMode = osm_importer_module.ImportMode
DetailLevel = osm_importer_module.DetailLevel

# Create importer
importer = OSMImporter(project, transformer, image_width, image_height)

# Configure options
options = ImportOptions(
    import_mode=ImportMode.ADD,        # or ImportMode.REPLACE
    detail_level=DetailLevel.MODERATE,  # or DetailLevel.FULL
    default_lane_width=3.5,            # meters
    import_junctions=True,
    timeout=60                          # seconds
)

# Perform import
result = importer.import_osm_data(options)

# Check results
if result.success:
    print(f"Imported {result.roads_imported} roads")
    print(f"Imported {result.signals_imported} signals")
    print(f"Imported {result.objects_imported} objects")
else:
    print(f"Import failed: {result.error_message}")
```

### calculate_bbox_from_image
```python
import importlib

osm_to_orbit = importlib.import_module("orbit.import.osm_to_orbit")
calculate_bbox_from_image = osm_to_orbit.calculate_bbox_from_image

bbox = calculate_bbox_from_image(
    image_width=2048,
    image_height=1536,
    transformer=transformer,
    buffer_percent=5.0  # Add 5% buffer
)
# Returns: (min_lat, min_lon, max_lat, max_lon)
```

---

## Testing Status

### Completed ✅
- [x] Module structure and imports
- [x] Syntax validation (all files compile)
- [x] Import dialog UI
- [x] Menu integration
- [x] Validation checks (georeferencing, image)

### Pending Real-World Testing
- [ ] Import with moderate detail
- [ ] Import with full detail
- [ ] Junction detection in actual road network
- [ ] Oneway vs two-way lane configuration
- [ ] Speed limit extraction and conversion
- [ ] Duplicate detection on re-import
- [ ] API timeout handling
- [ ] Large area performance
- [ ] Various OSM data quality scenarios

---

## Version History

### 2026-02 - OSM Export and Hybrid Transformer
- OSM export to `.osm` XML (roads, signals, objects, parking, lane widths)
- Custom radius import with hybrid homography/affine transformer
- No-image coordinate mode for importing without a loaded image
- Expanded object types (forest, farmland, meadow, wetland, etc.)

### 2025-11 - Initial Implementation
- Complete OSM import functionality
- Overpass API client with error handling
- Road network import with lane configuration
- Junction detection and section splitting
- Signal and object import
- Import dialog GUI
- Menu integration

---

## References

- **Overpass API**: https://wiki.openstreetmap.org/wiki/Overpass_API
- **Overpass Turbo** (query testing): https://overpass-turbo.eu/
- **OpenStreetMap Wiki**: https://wiki.openstreetmap.org/
- **OSM Highway Tags**: https://wiki.openstreetmap.org/wiki/Key:highway
- **OSM Lane Tags**: https://wiki.openstreetmap.org/wiki/Key:lanes
- **OpenDrive Specification**: https://www.asam.net/standards/detail/opendrive/

---

## Support

For issues or questions:
1. Check this guide and DEVELOPMENT.md
2. Check CLAUDE.md for development guidance
3. Report bugs via project issue tracker (if configured)
4. Review OSM import code in `import/` directory

---

**Last Updated**: 2026-02
**Version**: 0.6.0
**Status**: Production Ready

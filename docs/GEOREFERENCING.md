# Georeferencing Guide for ORBIT

## Overview

Georeferencing converts pixel coordinates in images to real-world geographic coordinates (latitude/longitude). This is essential for:
- **Accurate distance measurements** (lane widths in meters)
- **OpenStreetMap import** (requires image-to-world mapping)
- **OpenDrive export** (requires metric coordinates)
- **GIS integration** (export georeferenced road data)

**Status**: ✅ Fully implemented with uncertainty analysis (2025-11-12)

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [How Georeferencing Works](#how-georeferencing-works)
3. [Control Points: What You Need](#control-points-what-you-need)
4. [Adding Control Points](#adding-control-points)
5. [Uncertainty Analysis](#uncertainty-analysis)
6. [Validation and Quality Control](#validation-and-quality-control)
7. [Best Practices](#best-practices)
8. [Troubleshooting](#troubleshooting)

---

## Quick Start

### Prerequisites
- An image loaded in ORBIT
- At least 3-4 control points with known coordinates

### Basic Workflow
1. **Open Georeferencing**: Tools → Georeferencing
2. **Add Control Points**: Either manually or via CSV import
3. **Validate**: Check reprojection errors (should be <3 pixels)
4. **Analyze Uncertainty** (optional): Run Monte Carlo analysis
5. **Use**: Export to OpenDrive or import OSM data

---

## How Georeferencing Works

### The Mathematical Approach

ORBIT uses **homography transformation** (planar perspective transformation) to convert between pixel coordinates and geographic coordinates. This is the same technique used in professional photogrammetry and computer vision applications.

#### Coordinate Systems

Three coordinate systems are involved:

```
┌──────────────────────┐       ┌──────────────────────┐       ┌──────────────────────┐
│   Image (Pixels)     │  →    │  Local (Meters)      │  →    │  Geographic (WGS84)  │
│                      │       │                      │       │                      │
│  Origin: Top-left    │       │  Origin: Center of   │       │  Latitude/Longitude  │
│  Units: pixels       │       │  control points      │       │  Decimal degrees     │
│  (u, v)              │       │  (East, North)       │       │  (lat, lon)          │
└──────────────────────┘       └──────────────────────┘       └──────────────────────┘
```

#### The Homography Matrix

A homography is a 3×3 matrix **H** that relates pixel coordinates to ground coordinates:

```
[X]       [h₁₁  h₁₂  h₁₃]   [u]
[Y]  =  H [h₂₁  h₂₂  h₂₃] × [v]
[1]       [h₃₁  h₃₂  h₃₃]   [1]
```

After matrix multiplication, coordinates are normalized:
```
X = (h₁₁·u + h₁₂·v + h₁₃) / (h₃₁·u + h₃₂·v + h₃₃)
Y = (h₂₁·u + h₂₂·v + h₂₃) / (h₃₁·u + h₃₂·v + h₃₃)
```

This accounts for:
- **Translation** (image shift)
- **Rotation** (camera orientation)
- **Scale** (altitude/zoom)
- **Perspective distortion** (camera tilt)

### Computing the Transformation

The homography matrix is computed using **Direct Linear Transformation (DLT)**:

1. **Input**: At least 4 control points with both (pixel_x, pixel_y) and (latitude, longitude)
2. **Process**: Set up system of equations and solve using Singular Value Decomposition (SVD)
3. **Output**: 3×3 homography matrix that best fits all control points

**Why this works:**
- Learns actual transformation from your data
- Compensates for camera parameters (FOV, tilt, distortion)
- More robust than using camera metadata alone
- Handles perspective distortion from tilted cameras

### Transformation Methods

ORBIT supports two transformation methods (configurable in Edit → Preferences):

**Affine Transformation** (6 parameters):
- Minimum 3 control points required
- Best for: Orthoimages, satellite imagery, nadir (straight-down) views
- Assumes: No perspective distortion

**Homography Transformation** (8 parameters):
- Minimum 4 control points required
- Best for: Drone images, oblique angles, perspective views
- Handles: Perspective distortion from camera tilt

**Recommendation**: Use Homography for drone images (default), Affine for satellite/orthoimage.

---

## Control Points: What You Need

### What is a Control Point?

A **Ground Control Point (GCP)** is a location where you know both:
- **Pixel coordinates** (x, y in the image)
- **Geographic coordinates** (latitude, longitude)

### Two Types of Control Points

**1. Training Points (GCP - Georeferencing Control Points)**
- Used to compute the transformation
- Minimum 3 (affine) or 4 (homography) required
- More points = more robust transformation

**2. Validation Points (GVP - Georeferencing Validation Points)**
- Used to test transformation accuracy
- Not used in computation
- Provides honest accuracy estimate
- Optional but recommended (2-3 validation points)

### How Many Control Points?

| Count | Training RMSE | Validation RMSE | Quality | Use Case |
|-------|--------------|-----------------|---------|----------|
| 3-4 | 0.0 pixels | 2-5 pixels | Minimum ★★★☆☆ | Quick test |
| 6 | <0.1 pixels | 1-3 pixels | Good ★★★★☆ | Typical work |
| 8 | <0.1 pixels | 0.5-2 pixels | Excellent ★★★★★ | Production |
| 10+ | <0.1 pixels | 0.5-2 pixels | Excellent ★★★★★ | Research |

**Key insight**: More points improve robustness, but diminishing returns after 8-10 points.

### Where to Place Control Points

**Priority 1: Corners (4 points)** ⭐⭐⭐⭐⭐

```
┌─────────────────────────────────┐
│ ●                             ● │
│                                 │
│                                 │
│ ●                             ● │
└─────────────────────────────────┘
Coverage: ~80%
```

**Priority 2: Edge Midpoints (2-4 points)** ⭐⭐⭐⭐☆

```
┌─────────────────────────────────┐
│ ●             ●               ● │
│                                 │
│ ●                             ● │
│                                 │
│ ●             ●               ● │
└─────────────────────────────────┘
Coverage: ~90%
```

**Priority 3: Interior Points (2-4 points)** ⭐⭐⭐☆☆

```
┌─────────────────────────────────┐
│ ●             ●               ● │
│         ●           ●           │
│ ●                             ● │
│             ●                   │
│ ●             ●               ● │
└─────────────────────────────────┘
Coverage: ~95%
```

**Distribution matters MORE than count!** 6 well-placed points > 10 clustered points.

### Good Control Point Features

**✅ Excellent Choices:**
- Building corners (sharp, distinctive angles)
- Road intersections (precise center point)
- Painted road markings (lane lines, crosswalks)
- Manholes / drainage covers
- Fence posts (at base, not top)
- Curb corners
- Parking lot markings
- Survey markers (ideal!)

**❌ Poor Choices:**
- Cars, people, animals (moving objects)
- Shadows (change with sun position)
- Tree canopies (move with wind, use base instead)
- Middle of uniform fields
- Water surfaces (reflections, waves)
- Motion-blurred areas
- Glass/reflective surfaces

---

## Adding Control Points

ORBIT provides three methods to add control points:

### Method 1: Manual Placement (Interactive)

**Best for**: Small number of points, first-time setup

**Steps**:
1. Open **Tools → Georeferencing**
2. Click **"Pick Point on Image"**
   - Dialog minimizes, allowing you to see the image
3. **Click on the image** at a distinctive feature
   - Zoom in with mouse wheel for precision
   - Use crosshair cursor for accuracy
4. Enter geographic coordinates:
   - **Longitude**: Decimal degrees (-180 to 180)
   - **Latitude**: Decimal degrees (-90 to 90)
   - **Name** (optional): Descriptive label
5. Choose **Point Type**:
   - **Training (GCP)**: Used to compute transformation
   - **Validation (GVP)**: Used to test accuracy
6. Click **"Add Control Point"**

**Tips**:
- Paste coordinates from Google Maps, GPS device, or survey data
- Right-click → Copy in Google Maps gives comma-separated lat,lon
- Use validation points to honestly assess accuracy

### Method 2: CSV Import (Batch)

**Best for**: Many points, pre-surveyed data, RTK GPS data

**CSV Format**:
```csv
name,latitude,longitude
CP1,57.742249607,12.895378640
CP2,57.742248634,12.895413625
CP3,57.742858304,12.894386332
```

**Recognized column names** (case-insensitive):
- **Latitude**: `latitude`, `lat`, `y`, `northing`, `north`
- **Longitude**: `longitude`, `lon`, `long`, `lng`, `x`, `easting`, `east`
- **Name**: `point_name`, `name`, `id`, `point_id`, `marker`, `label`
- **Altitude** (optional): `altitude`, `alt`, `elevation`, `z`, `height`

**Steps**:
1. Open **Tools → Georeferencing**
2. Click **"Import from CSV..."**
3. Select your CSV file
4. Review detected points in table
5. Check/uncheck points to import
6. Click **"Start Placement"**
7. For each point:
   - CSV data is shown (lat/lon/altitude)
   - Click **"Pick Point on Image"**
   - Click on the image at that location
   - Click **"Add Control Point"** or **"Skip This Point"**
8. Import completes when all selected points are placed

**Features**:
- Flexible column detection (works with various CSV formats)
- Preview all points before importing
- Sequential placement with progress tracking
- Out-of-bounds warnings if placement seems wrong
- Duplicate name detection
- Skip individual points if not visible

**Example Use Case**: Import ArUco marker positions surveyed with RTK GPS

### Method 3: Modify Existing Points

**Edit Point**:
1. Select point in table
2. Click **"Edit Point"**
3. Modify coordinates, name, or type
4. Click **"OK"**

**Delete Point**:
1. Select point in table
2. Click **"Delete Point"**
3. Confirm deletion

**Convert to Validation**:
1. Hold out 2-3 well-distributed points
2. Edit each point and change type to "Validation (GVP)"
3. These points test accuracy without influencing transformation

---

## Uncertainty Analysis

ORBIT includes comprehensive uncertainty analysis to help you assess georeferencing quality and identify areas where additional control points are needed.

### What is Uncertainty?

**Position uncertainty** is the expected error (in meters) when converting a pixel location to geographic coordinates. It varies across the image based on:
- Distance from control points
- Distribution of control points
- Measurement errors in pixel placement
- Transformation quality

### Uncertainty Sources

1. **Measurement error**: Placing control points by clicking (±1-2 pixels)
2. **GPS accuracy**:
   - Standard GPS: ±3-5 meters
   - RTK GPS: ±0.01 meters
3. **Transformation residuals**: How well the model fits the control points
4. **Extrapolation**: Areas far from control points have higher uncertainty

### How Uncertainty is Computed

ORBIT uses **Monte Carlo simulation** with measurement error:

1. **Simulate noise**: Add random Gaussian noise (±σ pixels) to control point positions
2. **Recompute transformation**: Calculate new homography matrix with noised points
3. **Sample positions**: Convert grid of pixel positions to geographic coordinates
4. **Repeat**: Perform 200 iterations
5. **Calculate uncertainty**: Standard deviation of position across iterations
6. **Result**: Uncertainty grid (meters) across the entire image

**Why this works**:
- Accounts for realistic measurement errors in control point placement
- Propagates pixel-space uncertainty to geographic space
- Provides spatially-varying uncertainty estimates
- More accurate than simple distance-based heuristics

### Configurable Parameters

**Measurement Error (σ pixels)**:
- Default: **1.5 pixels**
- Typical range: 1.0-2.0 pixels for manual digitization
- Lower (0.5-1.0): Very careful placement, high-resolution image
- Higher (2.0-3.0): Quick rough placement, low-resolution image

**Baseline Uncertainty (meters)**:
- Default: **0.05 meters** (5 cm)
- Minimum expected position error from all sources
- Adjust based on:
  - Image resolution (GSD: ground sample distance)
  - GPS accuracy
  - Transformation quality

**To configure**: Adjust spinboxes in Georeferencing dialog before running analysis

### Running Uncertainty Analysis

**Steps**:
1. Open **Tools → Georeferencing**
2. Add at least 4 training control points
3. Configure parameters (optional):
   - **Measurement error**: σ in pixels
   - **Baseline uncertainty**: Minimum error in meters
4. Click **"Compute Uncertainty (Monte Carlo)"**
5. Wait for progress bar (~10-30 seconds for 200 iterations)
6. Review statistics:
   - Mean uncertainty across image
   - Maximum uncertainty
   - Coverage (% of area within thresholds)
   - Last computed timestamp

**Result**: Uncertainty grid cached in project for fast queries

### Viewing Uncertainty

**Uncertainty Overlay**:
1. View → Uncertainty Overlay → Position
2. Heatmap shows position uncertainty across image:
   - **Green**: <0.1m (excellent)
   - **Yellow**: 0.1-0.2m (good)
   - **Orange**: 0.2-0.4m (warning)
   - **Red**: >0.4m (poor - add control points here!)

**Scale Tool with Uncertainty**:
1. Enable Tools → Measure Scale Factor (Ctrl+M)
2. Draw a line segment on the image
3. See scale with uncertainty ranges:
   ```
   X: 4.85 ± 0.12 cm/px
   Y: 4.92 ± 0.15 cm/px
   Confidence: Good (0.15m)
   ```

### Interpreting Results

**Mean Uncertainty**:
- <0.10m: Excellent ★★★★★ (sub-lane accuracy)
- 0.10-0.20m: Good ★★★★☆ (lane-level accuracy)
- 0.20-0.50m: Acceptable ★★★☆☆ (road-level accuracy)
- >0.50m: Poor ★★☆☆☆ (add more control points)

**Using Uncertainty to Improve**:
1. Run Monte Carlo analysis
2. Enable uncertainty overlay (View → Uncertainty Overlay → Position)
3. Identify red/orange areas (high uncertainty)
4. Add control points in those areas
5. Recompute uncertainty
6. Verify improvement

### When to Recompute

Uncertainty cache is **automatically invalidated** when:
- Control points are added or removed
- Control point coordinates are edited
- Transform method is changed (affine ↔ homography)
- Uncertainty parameters are changed

Recompute Monte Carlo analysis after any changes for updated estimates.

---

## Validation and Quality Control

### Reprojection Error

**What it measures**: How well the transformation fits the training control points

**How it's computed**:
1. Transform pixel → geographic using computed homography
2. Transform geographic → pixel using inverse
3. Calculate distance between original and reprojected pixel
4. Compute RMS (root mean square) error

**Quality thresholds**:
- **RMSE < 2 pixels**: Excellent ★★★★★
- **RMSE 2-3 pixels**: Good ★★★★☆
- **RMSE 3-5 pixels**: Acceptable ★★★☆☆
- **RMSE > 5 pixels**: Review control points ★★☆☆☆

**View in dialog**: Georeferencing → Validation section shows:
- Overall RMSE (pixels)
- RMSE in meters (if scale can be computed)
- Per-point errors (identify outliers)

### Validation Points (GVP)

**Purpose**: Provide honest accuracy estimate

**How to use**:
1. Add 6-8 total control points
2. Convert 2-3 to validation points:
   - Edit point → Change type to "Validation (GVP)"
   - Choose well-distributed points
3. Transformation uses only training points
4. Validation points show true accuracy

**Result**: Validation RMSE displayed separately in dialog

**Benefits**:
- Detects overfitting (training RMSE good, validation RMSE poor)
- Honest accuracy assessment
- Identifies areas needing more control points

### Visual Inspection

**Check transformation quality**:
1. Enable uncertainty overlay
2. Verify low uncertainty (green) in areas of interest
3. Check that roads align with OSM import (if available)
4. Measure known distances with scale tool

**Red flags**:
- Very high uncertainty in center of image
- Validation RMSE much worse than training RMSE
- Per-point errors show specific outliers >5 pixels
- OSM data doesn't align with image features

---

## Best Practices

### Planning Phase

- [ ] Identify 6-10 potential control point locations before starting
- [ ] Choose distinctive, permanent features visible in image
- [ ] Spread points across entire image area
- [ ] Plan to cover all corners and edges
- [ ] If possible, survey GPS coordinates in advance (RTK GPS ideal)

### During Georeferencing

- [ ] Start with 4 corner control points
- [ ] Check initial RMSE after first 4 points
- [ ] Add edge points if RMSE > 3 pixels
- [ ] Add interior points if still needed
- [ ] Hold out 2-3 points for validation
- [ ] Zoom in when picking pixel locations (mouse wheel)
- [ ] Use distinctive features (corners, markings, intersections)

### Quality Control Checklist

- [ ] **Minimum points met**:
  - Affine: ≥3 training points
  - Homography: ≥4 training points
- [ ] **Distribution**: Points spread across entire image (not clustered)
- [ ] **RMSE**: Training RMSE < 3 pixels
- [ ] **Validation**: If using GVPs, validation RMSE < 5 pixels
- [ ] **Uncertainty**: Mean uncertainty appropriate for use case
- [ ] **Coverage**: High uncertainty areas either:
  - Not areas of interest, OR
  - Additional control points added

### For Different Image Types

**Drone Images (Oblique)**:
- Use Homography transformation
- 6-8 control points recommended
- Focus on far edge (more perspective distortion)
- Run uncertainty analysis to verify coverage

**Satellite/Orthoimage (Nadir)**:
- Can use Affine transformation
- 4-6 control points sufficient
- Distribute evenly across image
- Edges less critical than drone images

**High-Resolution Images (>8 MP)**:
- Sub-pixel accuracy possible
- Worth effort for 8-10 control points
- Careful pixel placement critical
- Lower measurement error parameter (σ = 1.0)

**Low-Resolution Images (<2 MP)**:
- Pixel placement less precise
- 4-6 points usually sufficient
- Higher measurement error parameter (σ = 2.0)
- Accept higher uncertainty

---

## Troubleshooting

### High Reprojection Error (RMSE > 5 pixels)

**Causes**:
1. Bad control point coordinates (typo in lat/lon)
2. Wrong control point placement (clicked wrong location)
3. Insufficient control points for image distortion
4. Control points too clustered

**Solutions**:
1. Review per-point errors in validation section
2. Find point with highest error
3. Edit that point and verify coordinates
4. Or delete and re-add the point
5. Add more well-distributed points

### High Uncertainty in Center of Image

**Cause**: Control points only on edges, none in center

**Solution**: Add 2-3 interior control points in high-uncertainty areas

### Validation RMSE Much Worse Than Training RMSE

**Cause**: Overfitting - transformation fits training points but doesn't generalize

**Solution**:
1. Check if validation points are far from training points
2. Add more training points near validation points
3. Verify validation points don't have coordinate errors

### CSV Import: Column Detection Fails

**Error**: "Could not detect latitude and longitude columns"

**Solution**:
1. Check that CSV has header row with column names
2. Verify column names match recognized aliases:
   - Latitude: `latitude`, `lat`, `y`, `northing`, `north`
   - Longitude: `longitude`, `lon`, `long`, `lng`, `x`, `easting`, `east`
3. Edit CSV to use recognized names

### Out-of-Bounds Warning During CSV Import

**Warning**: "Picked location seems far from expected position"

**Cause**: Estimation based on first 2 control points predicts different location

**When to ignore**:
- Only 2-3 points placed so far (estimation unreliable)
- Control points very sparse (extrapolation error)
- You're confident you clicked correct location

**When to heed**:
- 4+ points already placed
- Control points well-distributed
- Warning distance >200 pixels
- Action: Click "Pick Point on Image" again, re-check location

### Monte Carlo Analysis Produces High Uncertainty

**Causes**:
1. Measurement error parameter (σ) too high for your data
2. Baseline uncertainty too high
3. Control points too sparse
4. Poor control point distribution

**Solutions**:
1. **Reduce σ pixels**: If you placed points very carefully (e.g., σ = 1.0)
2. **Reduce baseline uncertainty**: If image scale is high-resolution (e.g., 0.03m)
3. **Add more control points**: Especially in high-uncertainty areas
4. **Improve distribution**: Add points to corners and edges

### Uncertainty Overlay Takes Long Time

**Cause**: No cached uncertainty grid - using fallback heuristic

**Solution**:
1. Open Georeferencing dialog
2. Click "Compute Uncertainty (Monte Carlo)"
3. Wait for analysis to complete (~10-30 seconds)
4. Now overlay will load instantly

### OSM Import Doesn't Align with Image

**Causes**:
1. Georeferencing has high error
2. Wrong coordinate system in control points
3. Image is from different time than OSM data

**Solutions**:
1. Check reprojection RMSE (should be <3 pixels)
2. Verify control point coordinates are correct (lat/lon not swapped)
3. Run uncertainty analysis to identify problem areas
4. Add validation points to test accuracy
5. If OSM data is old/new, manual adjustment may be needed

---

## Advanced Topics

### Coordinate System Notes

**WGS84 (World Geodetic System 1984)**:
- Standard for GPS coordinates
- Latitude/longitude in decimal degrees
- What ORBIT expects for control points

**UTM, State Plane, Other Systems**:
- Currently not directly supported
- Convert to WGS84 lat/lon before import
- Use online converter or GIS software

### Accuracy Factors

**Best Case (Sub-meter accuracy)**:
- RTK GPS for control points (±0.01m)
- High-resolution image (GSD <0.05 m/px)
- 8+ well-distributed control points
- Flat terrain
- Careful pixel placement
- Result: ~0.05-0.15m uncertainty

**Typical Case (Meter-level accuracy)**:
- Standard GPS for control points (±3-5m)
- Moderate resolution (GSD ~0.10 m/px)
- 6 control points
- Result: ~0.50-2.0m uncertainty

**Minimum Case (Road-level accuracy)**:
- Coordinates from Google Maps
- Low resolution image
- 4 control points
- Result: ~2-10m uncertainty

### When Homography Fails

**Assumptions**:
- Flat ground (planar)
- Single rigid transformation across image

**Limitations**:
- Significant terrain elevation changes
- Very large coverage areas (>10 km)
- Very low altitude (<10m) with high distortion

**Alternatives**:
- Use photogrammetry software (Pix4D, Agisoft Metashape)
- Create orthomosaic first
- Use multiple overlapping images
- Apply terrain correction with DEM

---

## Summary: Quick Reference

### Minimum Requirements
- **Affine**: 3 training control points
- **Homography**: 4 training control points

### Recommended Setup
- **Control points**: 6-8 well-distributed
- **Validation points**: 2-3 held out for testing
- **Distribution**: Corners + edges + some interior
- **Target RMSE**: <3 pixels
- **Target uncertainty**: <0.2m for lane-level work

### Workflow Checklist
1. Add 4 corner control points
2. Check RMSE (should be <5 pixels)
3. Add 2-4 edge/interior points
4. Recheck RMSE (target <3 pixels)
5. Convert 2 points to validation
6. Run Monte Carlo uncertainty analysis
7. Review uncertainty overlay
8. Add control points in high-uncertainty areas (if needed)
9. Proceed with OSM import or OpenDrive export

### When Something Goes Wrong
- RMSE >5 pixels → Check per-point errors, review coordinates
- High uncertainty → Add control points, improve distribution
- Import fails → Verify coordinate format, check lat/lon not swapped
- Validation poor → Add training points near validation points

---

## Files and References

### Implementation Files
- **`utils/coordinate_transform.py`**: Homography computation (DLT algorithm)
- **`utils/uncertainty_estimator.py`**: Monte Carlo uncertainty analysis
- **`gui/georeference_dialog.py`**: Main georeferencing dialog
- **`gui/csv_import_dialog.py`**: CSV import functionality
- **`gui/uncertainty_overlay.py`**: Uncertainty visualization
- **`models/project.py`**: Control point data model

### Theoretical Background
- See `datasets/drone_georef/ALGORITHM_THEORY.md` for mathematical details
- See `datasets/drone_georef/GCP_BEST_PRACTICES.md` for comprehensive GCP guide
- Hartley & Zisserman: "Multiple View Geometry in Computer Vision"
- Kraus: "Photogrammetry: Geometry from Images and Laser Scans"

---

**Last Updated**: 2026-02
**Version**: 0.5.0
**Status**: Production Ready

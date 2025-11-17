# Validation and Uncertainty Analysis: Technical Guide

**Status**: Production Ready | **Version**: 0.1.0 | **Date**: 2025-11-12

## Overview

This document provides a comprehensive technical explanation of ORBIT's validation and uncertainty analysis features, including the mathematical theory, implementation details, and practical usage guidelines.

---

## Table of Contents

1. [Validation Metrics](#validation-metrics)
2. [Uncertainty Estimation](#uncertainty-estimation)
3. [GCP Suggestion Algorithm](#gcp-suggestion-algorithm)
4. [Statistical Foundations](#statistical-foundations)
5. [Configuration Parameters](#configuration-parameters)
6. [Practical Guidelines](#practical-guidelines)
7. [Implementation Details](#implementation-details)

---

## Validation Metrics

### 1.1 Reprojection Error

#### What It Measures

Reprojection error quantifies how well the computed transformation fits the training control points (GCPs). It measures the **round-trip error** when transforming coordinates from pixel space to geographic space and back.

#### Mathematical Definition

For each GCP *i* with pixel coordinates (u<sub>i</sub>, v<sub>i</sub>) and geographic coordinates (lat<sub>i</sub>, lon<sub>i</sub>):

1. **Forward transformation**: (u<sub>i</sub>, v<sub>i</sub>) → (lat'<sub>i</sub>, lon'<sub>i</sub>)
2. **Inverse transformation**: (lat'<sub>i</sub>, lon'<sub>i</sub>) → (u'<sub>i</sub>, v'<sub>i</sub>)
3. **Reprojection error** (pixels):

```
e_i = √[(u_i - u'_i)² + (v_i - v'_i)²]
```

4. **Root Mean Square Error (RMSE)**:

```
RMSE = √[(Σ e_i²) / n]
```

where *n* is the number of training GCPs.

#### Why Reprojection Error Matters

**Training RMSE** indicates:
- **Transformation quality**: How well the mathematical model (affine/homography) fits the data
- **Data consistency**: Whether control point coordinates are accurate
- **Outlier detection**: Individual points with high errors may have coordinate mistakes

**Important**: Training RMSE can be **misleadingly low** due to overfitting. A transformation can fit training points perfectly while performing poorly elsewhere. This is why validation points are crucial.

#### Interpretation Guidelines

| Training RMSE | Quality | Interpretation |
|--------------|---------|----------------|
| <1 pixel | Excellent ★★★★★ | Perfect fit, may indicate overfitting |
| 1-2 pixels | Very Good ★★★★☆ | High-quality transformation |
| 2-3 pixels | Good ★★★☆☆ | Acceptable for most applications |
| 3-5 pixels | Fair ★★☆☆☆ | Review control points, may need more GCPs |
| >5 pixels | Poor ★☆☆☆☆ | Check for coordinate errors or outliers |

**Ground Sample Distance (GSD) context**: For a typical drone image with GSD ≈ 0.05 m/px:
- 2 pixels RMSE ≈ 0.10m ground error
- 5 pixels RMSE ≈ 0.25m ground error

### 1.2 Per-Point Errors

#### Functionality

ORBIT computes reprojection error **individually for each GCP**, allowing identification of problematic control points.

**Displayed in**: Georeferencing dialog → Validation section

**Example**:
```
GCP Reprojection Errors:
  Point 1 (Corner NW): 1.2 px
  Point 2 (Corner NE): 0.8 px
  Point 3 (Corner SE): 1.5 px
  Point 4 (Corner SW): 0.9 px
  Point 5 (Center): 8.3 px  ← OUTLIER!
```

#### Outlier Detection Strategy

1. **Identify high-error points**: e<sub>i</sub> > 2 × RMSE or e<sub>i</sub> > 5 pixels
2. **Review coordinates**: Check lat/lon values for typos
3. **Verify pixel placement**: Ensure correct feature was clicked
4. **Options**:
   - **Fix**: Edit control point with correct coordinates
   - **Remove**: Delete outlier if uncertain
   - **Convert to validation**: Change type to GVP to exclude from training

### 1.3 Training vs. Validation Points

#### Training Points (GCP - Georeferencing Control Points)

**Purpose**: Used to **compute** the transformation matrix

**How they're used**:
- Affine: 3+ GCPs solve for 6 parameters
- Homography: 4+ GCPs solve for 8 parameters
- Overdetermined system (>min required) uses least squares optimization

**Error characteristics**:
- Training RMSE is typically **very low** (near-zero for exactly determined systems)
- Can be **misleadingly good** due to overfitting
- Does not represent true accuracy

#### Validation Points (GVP - Georeferencing Validation Points)

**Purpose**: Used to **test** transformation accuracy on unseen data

**How they're used**:
- Excluded from transformation computation
- Transformed using the computed matrix
- Error represents **true generalization accuracy**

**Error characteristics**:
- Validation RMSE is **honest** measure of accuracy
- Typically **higher** than training RMSE
- Represents expected error at arbitrary locations

#### Mathematical Insight

For exactly determined systems (4 GCPs, homography):
- **Training RMSE** = 0 (perfect fit by construction)
- **Validation RMSE** = actual accuracy (may be much higher)

For overdetermined systems (6+ GCPs):
- **Training RMSE** = fitting residual (least squares error)
- **Validation RMSE** = generalization error

**Ideal scenario**:
```
Training RMSE ≈ Validation RMSE
```

**Overfitting**:
```
Training RMSE << Validation RMSE  (BAD!)
```

#### Best Practice: Hold-Out Validation

**Recommended workflow**:
1. Add 8-10 total control points
2. Convert 2-3 to validation points (GVP)
3. Ensure validation points are well-distributed (corners + center)
4. Compare training vs. validation RMSE
5. If validation RMSE >> training RMSE: add more training GCPs near validation points

**Example**:
```
Training GCPs: 6 points (corners + edges)
Validation GVPs: 2 points (center-left, center-right)

Training RMSE: 1.8 px
Validation RMSE: 2.3 px
Ratio: 1.28 → Good generalization ✓
```

### 1.4 Validation Error in Metric Space

#### Converting Pixel Errors to Meters

ORBIT automatically converts pixel-space errors to metric-space errors when sufficient data is available.

**Formula**:
```
error_meters = error_pixels × GSD
```

where GSD (Ground Sample Distance) is computed from the transformation matrix:

```
GSD_x = ||∂(meters)/∂(pixel_x)||
GSD_y = ||∂(meters)/∂(pixel_y)||
```

**Why this matters**: Pixel errors are resolution-dependent. A 3-pixel error on:
- High-res image (GSD=0.02 m/px): 0.06m error (excellent)
- Low-res image (GSD=0.20 m/px): 0.60m error (poor)

Metric-space errors provide **absolute** quality assessment independent of image resolution.

---

## Uncertainty Estimation

### 2.1 Why Uncertainty Analysis?

#### The Problem

After computing a georeferencing transformation, you know:
- ✓ Reprojection error at **training GCPs**
- ✓ Reprojection error at **validation GVPs** (if any)
- ✗ Expected error at **arbitrary locations** across the image

**Questions uncertainty analysis answers**:
1. What's the expected position error at pixel (1500, 2000)?
2. Where in my image is georeferencing most/least accurate?
3. Where should I add more control points to improve accuracy?
4. Can I trust georeferencing for this specific road segment?

#### The Solution: Uncertainty Estimation

Uncertainty estimation provides **spatially-varying error estimates** across the entire image by:
1. **Modeling measurement errors** in control point placement
2. **Propagating these errors** through the transformation
3. **Computing position uncertainty** at every location
4. **Visualizing results** as a heatmap overlay

### 2.2 Monte Carlo Uncertainty Estimation

#### Theory: Measurement Error Propagation

**Core idea**: Control point pixel coordinates are measured with uncertainty. This measurement error propagates through the transformation computation, causing position uncertainty in the final result.

**Measurement sources**:
1. **Digitization error**: Manual clicking precision (±1-2 pixels typical)
2. **Feature ambiguity**: Exact location of corner/edge unclear
3. **Sub-pixel accuracy**: Pixel coordinates are discrete
4. **Orthorectification error**: Image distortion not fully corrected

**Statistical model**:
- True pixel coordinate: (u, v)
- Measured coordinate: (u + ε<sub>x</sub>, v + ε<sub>y</sub>)
- Noise model: ε ~ N(0, σ²) (Gaussian with standard deviation σ)

#### The Monte Carlo Algorithm

**Input**:
- N training GCPs with pixel coordinates {(u<sub>i</sub>, v<sub>i</sub>)} and geographic coordinates {(lat<sub>i</sub>, lon<sub>i</sub>)}
- Measurement error standard deviation: σ (pixels)
- Number of iterations: K (typically 200)
- Grid resolution: R × C (typically 50 × 50)

**Process**:

```python
For iteration k = 1 to K:
    # Step 1: Add noise to GCP pixel coordinates
    For each GCP i:
        ũ_i = u_i + N(0, σ²)
        ṽ_i = v_i + N(0, σ²)

    # Step 2: Compute transformation from noised GCPs
    H̃_k = compute_homography({(ũ_i, ṽ_i)}, {(lat_i, lon_i)})

    # Step 3: Transform grid points with this realization
    For each grid cell (r, c):
        (x_grid, y_grid) = grid_coordinates(r, c)
        (X_k[r,c], Y_k[r,c]) = H̃_k.transform(x_grid, y_grid)

# Step 4: Compute uncertainty as standard deviation across iterations
For each grid cell (r, c):
    uncertainty[r,c] = √(std(X[:, r, c])² + std(Y[:, r, c])²)
```

**Output**:
- Uncertainty grid U[r, c] with position uncertainty (meters) at each grid cell

#### Mathematical Justification

**Law of Total Variance**:
```
Var(Position) = E[Var(Position | Measurement)] + Var(E[Position | Measurement])
```

Monte Carlo estimates the second term (epistemic uncertainty from measurement error).

**Central Limit Theorem**:
With K=200 iterations, the sample standard deviation converges to the true standard deviation:
```
std_sample → std_population  as K → ∞
```

**First-Order Error Propagation**:
```
σ²_position ≈ (∂Position/∂u)² σ²_measurement + (∂Position/∂v)² σ²_measurement
```

Monte Carlo computes this exactly without linearization.

#### Why 200 Iterations?

**Convergence analysis**:
- K=50: Noisy estimates, high variance
- K=100: Reasonable estimates, some variance
- K=200: Stable estimates, low variance ✓
- K=500: Diminishing returns, 2.5× slower

**Standard error of std estimate**:
```
SE(std) ≈ std / √(2K)
```

For K=200: SE ≈ 0.05 × std (5% relative error)

### 2.3 Bootstrap Uncertainty Estimation

#### Theory: Resampling with Replacement

**Alternative approach**: Instead of adding noise to coordinates, **resample the GCPs themselves**.

**Core idea**: If GCP distribution is representative of true distribution, resampling estimates transformation variability.

**Algorithm**:
```python
For iteration k = 1 to K:
    # Step 1: Resample GCPs with replacement
    indices = random.choice([0, 1, ..., N-1], size=N, replace=True)
    GCPs_resampled = [GCPs[i] for i in indices]

    # Step 2: Compute transformation from resampled set
    H̃_k = compute_homography(GCPs_resampled)

    # Step 3: Transform grid points
    For each grid cell (r, c):
        (x_grid, y_grid) = grid_coordinates(r, c)
        scale_k[r,c] = compute_scale(H̃_k, x_grid, y_grid)

# Step 4: Compute scale uncertainty
For each grid cell (r, c):
    uncertainty[r,c] = std(scale[:, r, c])
```

**Note**: Bootstrap in ORBIT computes **scale uncertainty** (m/px variance), not position uncertainty directly.

#### Bootstrap vs. Monte Carlo

| Aspect | Monte Carlo | Bootstrap |
|--------|-------------|-----------|
| **Error model** | Measurement noise | GCP sampling |
| **Output** | Position uncertainty (m) | Scale uncertainty (m/px) |
| **Speed** | Fast (200 iter ≈ 20s) | Moderate (200 iter ≈ 30s) |
| **Assumptions** | Gaussian measurement error | Representative GCP distribution |
| **Recommended** | Yes (primary method) | Alternative for comparison |

**When to use Bootstrap**:
- GCPs from different sources with varying quality
- Investigating impact of specific GCP removal
- Validating Monte Carlo results

### 2.4 Baseline Uncertainty

#### Concept

Even with perfect measurements and perfect transformation, there's **minimum uncertainty** from:
1. **Coordinate quantization**: GPS precision (±3-5m standard, ±0.01m RTK)
2. **Transformation model error**: Affine/homography assumptions (flat ground, no distortion)
3. **Numerical precision**: Floating-point arithmetic

**Implementation**:
```python
uncertainty_total = max(uncertainty_monte_carlo, baseline_uncertainty)
```

**Default**: 0.05m (5 cm)

**Configuration**: Adjust based on:
- GPS quality (RTK: 0.01m, Standard: 0.10m)
- Image resolution (High-res: 0.03m, Low-res: 0.10m)
- Transformation quality (Good fit: 0.05m, Poor fit: 0.15m)

### 2.5 Spatial Variation of Uncertainty

#### Geometric Factors

Uncertainty is **not uniform** across the image. It depends on:

**1. Distance from GCPs**:
```
uncertainty(p) ∝ min_distance(p, {GCPs})
```
Points far from any GCP have higher uncertainty (extrapolation vs. interpolation).

**2. GCP density**:
```
uncertainty(p) ∝ 1 / local_density(GCPs near p)
```
Areas with clustered GCPs have lower uncertainty.

**3. Geometric dilution of precision (GDOP)**:
```
uncertainty(p) ∝ 1 / det(design_matrix(p))
```
Points inside a well-conditioned GCP polygon have lower uncertainty.

**4. Perspective effects** (homography only):
```
uncertainty(p) ∝ |h₃₁u + h₃₂v + h₃₃|²
```
Areas with strong perspective distortion have higher uncertainty.

#### Expected Patterns

**Typical drone image** (4 corner GCPs):
```
┌─────────────────────────────┐
│ Low    Low    Low    Low    │  ← Edges: low uncertainty
│                             │
│ Low    High   High   Low    │  ← Center: high uncertainty
│                             │
│ Low    High   High   Low    │
│                             │
│ Low    Low    Low    Low    │  ← Corners: lowest uncertainty
└─────────────────────────────┘
```

**Well-distributed GCPs** (8 points: corners + edges + center):
```
┌─────────────────────────────┐
│ Low    Low    Low    Low    │
│                             │
│ Low    Low    Low    Low    │  ← Uniform: low uncertainty
│                             │
│ Low    Low    Low    Low    │
│                             │
│ Low    Low    Low    Low    │
└─────────────────────────────┘
```

---

## GCP Suggestion Algorithm

### 3.1 Problem Statement

**Goal**: Automatically identify **optimal locations** for adding new control points to maximize improvement in georeferencing accuracy.

**Challenges**:
1. Infinite possible locations (every pixel)
2. Uncertainty reduction is non-local (adding GCP affects entire image)
3. Practical constraints (features must be identifiable, measurable)

**Approach**: Divide image into **spatial regions** and find:
- Highest uncertainty point in each region
- Only regions above threshold (worth improving)
- Natural spatial separation (diverse coverage)
- Ranked by impact (prioritized suggestions)

### 3.2 Algorithm Details

#### Input Parameters

- **Uncertainty grid**: U[R, C] with R × C = 50 × 50 cells
- **Threshold**: τ (meters, configurable, default 0.2m)
- **Region grid**: (cols, rows) = (4, 3) = 12 regions
- **Maximum suggestions**: N<sub>max</sub> = 12 (one per region)

#### Step 1: Divide Image into Regions

```python
region_cols = 4  # Horizontal divisions
region_rows = 3  # Vertical divisions
total_regions = 12

# Calculate region size in grid cells
region_width = grid_cols / region_cols   # 50 / 4 ≈ 12 cells
region_height = grid_rows / region_rows  # 50 / 3 ≈ 16 cells

┌──────┬──────┬──────┬──────┐
│  R1  │  R2  │  R3  │  R4  │
├──────┼──────┼──────┼──────┤
│  R5  │  R6  │  R7  │  R8  │
├──────┼──────┼──────┼──────┤
│  R9  │ R10  │ R11  │ R12  │
└──────┴──────┴──────┴──────┘
```

#### Step 2: Find Maximum in Each Region

```python
suggestions = []

For each region (row, col):
    # Extract region from uncertainty grid
    region = U[row_start:row_end, col_start:col_end]

    # Find maximum uncertainty in this region
    max_uncertainty = max(region)

    # Only suggest if above threshold
    if max_uncertainty >= τ:
        # Find location of maximum
        (i, j) = argmax(region)

        # Convert to pixel coordinates
        x = (j / grid_cols) × image_width
        y = (i / grid_rows) × image_height

        suggestions.append((x, y, max_uncertainty))

# Sort by uncertainty (descending)
suggestions.sort(by=max_uncertainty, reverse=True)
```

**Why region-based approach?**
- **Natural spatial distribution**: One suggestion per region ensures good coverage
- **No clustering**: Suggestions automatically separated by region boundaries
- **Simple and predictable**: Users understand 12-region grid
- **No local maxima detection**: Avoids issues with smooth uncertainty gradients
- **Scalable**: Can adjust region grid (e.g., 3×3=9 or 5×4=20)

**Ranking**: Since suggestions come from different regions (naturally separated), sort by uncertainty descending to prioritize worst areas.

```python
# Sort by uncertainty (highest first)
suggestions.sort(key=lambda s: s[2], reverse=True)
```

#### Output

List of up to 12 pixel coordinates `[(x₁, y₁), (x₂, y₂), ...]` sorted by priority (highest uncertainty first).

**Spatial distribution**: Automatically ensured by region grid - suggestions are spread across image in a 4×3 pattern.

**Display format**:
```
Found 8 high-uncertainty area(s):
(Using threshold: 0.15m)

1. Pixel (2456, 345) - Uncertainty: 0.45m
2. Pixel (789, 1890) - Uncertainty: 0.38m
3. Pixel (3210, 567) - Uncertainty: 0.32m
4. Pixel (1234, 2100) - Uncertainty: 0.28m
5. Pixel (3400, 1450) - Uncertainty: 0.25m
6. Pixel (456, 678) - Uncertainty: 0.22m
7. Pixel (2890, 2567) - Uncertainty: 0.19m
8. Pixel (1678, 456) - Uncertainty: 0.17m

Current mean uncertainty: 0.15m
Current max uncertainty: 0.45m

(Suggestions distributed across 4×3 region grid)
```

### 3.3 Threshold Configuration

#### Why Configurable?

Different applications have different accuracy requirements:

| Application | Target Accuracy | Suggested Threshold |
|-------------|-----------------|---------------------|
| Lane-level mapping | <10 cm | 0.10m |
| Precision agriculture | <20 cm | 0.15m |
| Road network mapping | <30 cm | 0.20m (default) |
| Rough mapping | <50 cm | 0.30m |

**User control**: `GCP suggestion threshold` spin box in Georeferencing dialog.

#### Impact of Threshold

**Low threshold (0.10m)**:
- More suggestions (up to 5)
- Suggests even moderately-uncertain areas
- Use when: High accuracy needed

**Medium threshold (0.20m)** - Default:
- Balanced suggestions (2-4 typically)
- Suggests clearly-uncertain areas
- Use when: Standard mapping

**High threshold (0.30m)**:
- Fewer suggestions (0-2)
- Only worst areas
- Use when: Quick improvement, limited GCPs available

**No suggestions**:
```
"No high-uncertainty areas found above threshold (0.15m)!
Your current control point distribution provides good coverage.
To find more suggestions, lower the threshold."
```

### 3.4 Uncertainty Overlay Visualization

#### Color Mapping

Uncertainty overlay provides **immediate visual feedback** on georeferencing quality.

**Color scale** (smooth gradients):
```
Green:  <0.1m    - Excellent
Yellow: 0.1-0.2m - Good
Orange: 0.2-0.4m - Warning
Red:    >0.4m    - Poor
```

**Implementation**: NumPy vectorized operations
```python
# Green: < 0.1m
mask = uncertainty_grid < 0.1
rgba_array[mask] = [0, 255, 0, alpha]

# Green to Yellow: 0.1-0.2m
mask = (uncertainty_grid >= 0.1) & (uncertainty_grid < 0.2)
t = (uncertainty_grid[mask] - 0.1) / 0.1  # Interpolation factor
rgba_array[mask, 0] = (255 * t).astype(np.uint8)  # Red channel
rgba_array[mask, 1] = 255                          # Green channel
```

**Transparency**: 30% opacity (alpha=76) to see image underneath

**Performance**: 50×50 grid upscaled with smooth interpolation
- Fast generation (<1 second)
- No UI freezing
- Good visual quality

#### GCP Suggestion Markers

**Visual style**:
- **Orange circles**: 20px diameter, 3px stroke
- **Labels**: Uncertainty value (e.g., "0.32m")
- **Positioning**: Circle at suggestion location, label to the right

**When shown**:
- Overlay enabled: View → Uncertainty Overlay → Position
- Markers visible if threshold met
- Updated when GCPs added/removed

**Purpose**:
- Visual guidance for GCP placement
- Connect numerical suggestions to spatial locations
- Verify suggested areas are identifiable features

---

## Statistical Foundations

### 4.1 Uncertainty Quantification Framework

#### Aleatory vs. Epistemic Uncertainty

**Aleatory (irreducible)**:
- GPS signal noise
- Atmospheric effects
- Multipath errors
- **Cannot be reduced** by adding GCPs

**Epistemic (reducible)**:
- GCP placement uncertainty (measurement error)
- Transformation model uncertainty (limited GCPs)
- Interpolation/extrapolation error
- **CAN be reduced** by adding GCPs

**ORBIT focuses on**: Epistemic uncertainty from measurement error propagation

#### Confidence Intervals

Monte Carlo provides **distribution** of possible positions, allowing confidence intervals:

**68% Confidence** (1σ):
```
Position ∈ [X - σ_x, X + σ_x] × [Y - σ_y, Y + σ_y]
```

**95% Confidence** (2σ):
```
Position ∈ [X - 2σ_x, X + 2σ_x] × [Y - 2σ_y, Y + 2σ_y]
```

**Circular Error Probable (CEP)**:
```
CEP_50 = 0.59 × (σ_x + σ_y)
CEP_95 = 2.45 × σ_position
```

**ORBIT reports**: σ<sub>position</sub> = √(σ<sub>x</sub>² + σ<sub>y</sub>²)

### 4.2 Error Propagation Mathematics

#### First-Order Taylor Approximation

For small measurement errors, **linearization** gives analytical estimate:

```
σ²_position ≈ (∂Position/∂u)² σ²_u + (∂Position/∂v)² σ²_v
```

**Jacobian matrix**:
```
J = [∂X/∂u   ∂X/∂v]
    [∂Y/∂u   ∂Y/∂v]
```

**Covariance propagation**:
```
Σ_position = J Σ_measurement J^T
```

**Limitations of linearization**:
- Assumes small errors (σ < 5% of magnitude)
- Ignores higher-order terms
- Less accurate for homography (nonlinear)

**Monte Carlo advantage**: Exact computation without approximation

#### Homography Nonlinearity

Homography transformation is **nonlinear**:
```
X = (h₁₁u + h₁₂v + h₁₃) / (h₃₁u + h₃₂v + h₃₃)
Y = (h₂₁u + h₂₂v + h₂₃) / (h₃₁u + h₃₂v + h₃₃)
```

**Denominator term** causes:
- Non-constant scale across image
- Asymmetric error distribution
- Perspective-dependent uncertainty

**Monte Carlo correctly handles** all nonlinear effects.

### 4.3 Degrees of Freedom

#### Transformation Parameters

**Affine** (6 DOF):
```
[X]   [a₁₁  a₁₂  t_x] [u]
[Y] = [a₂₁  a₂₂  t_y] [v]
[1]   [0    0    1  ] [1]
```
- Minimum: 3 GCPs (6 equations, 6 unknowns)
- Overdetermined: 4+ GCPs (least squares)

**Homography** (8 DOF):
```
[X]   [h₁₁  h₁₂  h₁₃] [u]
[Y] = [h₂₁  h₂₂  h₂₃] [v]
[1]   [h₃₁  h₃₂  h₃₃] [1]
```
- Minimum: 4 GCPs (8 equations, 8 unknowns)
- Overdetermined: 5+ GCPs (least squares)

#### Redundancy and Uncertainty

**Redundancy**: r = n<sub>observations</sub> - n<sub>parameters</sub>

**Affine**:
- 3 GCPs: r = 6 - 6 = 0 (no redundancy, RMSE = 0)
- 6 GCPs: r = 12 - 6 = 6 (good redundancy)

**Homography**:
- 4 GCPs: r = 8 - 8 = 0 (no redundancy, RMSE = 0)
- 8 GCPs: r = 16 - 8 = 8 (good redundancy)

**General rule**: Redundancy ≥ 4-6 for reliable uncertainty estimates

---

## Configuration Parameters

### 5.1 Parameter Overview

| Parameter | Symbol | Default | Range | Units | Affects |
|-----------|--------|---------|-------|-------|---------|
| Measurement error | σ | 1.5 | 0.1-5.0 | pixels | Monte Carlo noise level |
| Baseline uncertainty | β | 0.05 | 0.01-0.5 | meters | Minimum uncertainty floor |
| GCP suggestion threshold | τ | 0.20 | 0.05-1.0 | meters | Suggestion sensitivity |

### 5.2 Measurement Error (σ pixels)

#### Physical Meaning

Standard deviation of pixel coordinate measurement error when manually clicking control points.

**Sources**:
1. **Cursor precision**: ±1 pixel (discrete positioning)
2. **Feature localization**: ±0.5-2 pixels (where exactly is corner?)
3. **Sub-pixel interpolation**: ±0.5 pixels (if used)

**Typical values**:

| Scenario | σ (pixels) | Explanation |
|----------|------------|-------------|
| Very careful placement, zoom in | 1.0 | Minimum realistic |
| Careful placement | 1.5 | **Default** |
| Normal placement | 2.0 | Typical quick work |
| Rough placement | 3.0 | Approximate clicking |

#### How to Choose

**Empirical test**:
1. Pick same GCP location 10 times (without undo)
2. Record pixel coordinates each time
3. Compute standard deviation: σ<sub>empirical</sub>
4. Use as parameter value

**Conservative approach**: Use σ = 2.0 (overestimate → higher uncertainty → more cautious)

**Optimistic approach**: Use σ = 1.0 (underestimate → lower uncertainty → may be overconfident)

### 5.3 Baseline Uncertainty (β meters)

#### Physical Meaning

Minimum expected position uncertainty even with perfect measurements and infinite GCPs.

**Sources**:
1. **GPS accuracy**:
   - Standard GPS: ±3-5m
   - DGPS: ±0.5-1m
   - RTK GPS: ±0.01-0.05m
2. **Transformation model error**:
   - Flat ground assumption
   - No lens distortion correction
   - Numerical precision
3. **Ground truth uncertainty**:
   - Survey marker position accuracy
   - Feature identification ambiguity

#### How to Choose

**Based on GPS quality**:
```
β = 0.5 × GPS_accuracy
```

Examples:
- RTK GPS (±2cm): β = 0.01m
- DGPS (±1m): β = 0.50m
- Standard GPS (±5m): β = 2.5m
- Google Maps (~±10m): β = 5.0m

**Based on GSD**:
```
β = 2 × GSD
```

Examples:
- High-res drone (GSD=0.02 m/px): β = 0.04m
- Medium-res drone (GSD=0.05 m/px): β = 0.10m
- Satellite (GSD=0.30 m/px): β = 0.60m

**Default (0.05m = 5cm)**: Assumes good-quality GPS and typical drone imagery.

### 5.4 GCP Suggestion Threshold (τ meters)

#### Physical Meaning

Minimum uncertainty level to trigger GCP suggestion. Areas with uncertainty < τ are considered "good enough."

#### How to Choose

**Based on application requirements**:

| Application | τ (meters) | Rationale |
|-------------|-----------|-----------|
| Precision surveys | 0.10 | Need sub-decimeter accuracy |
| Lane-level mapping | 0.15 | Lane width ≈ 3.5m, need <5% error |
| Road-level mapping | 0.20 | **Default** - road width ≈ 10m, need ~2% error |
| Rough mapping | 0.30 | General location sufficient |

**Dynamic adjustment**:
1. Run Monte Carlo
2. Check mean uncertainty
3. Set τ ≈ 0.75 × mean_uncertainty
4. Get suggestions in worst 25% of image

---

## Practical Guidelines

### 6.1 Validation Workflow

#### Step-by-Step Process

**1. Initial GCP Placement** (4-6 points):
```
- Add 4 corner GCPs
- Or 6 GCPs (corners + 2 edges)
- Check training RMSE
- Target: <3 pixels
```

**2. Hold-Out Validation** (if 6+ total points):
```
- Convert 2 well-distributed GCPs → GVPs
- Recompute transformation (now 4 training points)
- Check validation RMSE
- Target: validation RMSE < 1.5 × training RMSE
```

**3. Uncertainty Analysis**:
```
- Configure σ and β parameters
- Run Monte Carlo (200 iterations, ~20 seconds)
- Review mean/max uncertainty
- Target: mean < target_accuracy
```

**4. GCP Suggestions**:
```
- Set threshold τ = target_accuracy
- Click "Suggest GCP Locations"
- Review suggested pixel coordinates
- Add GCPs at 2-3 suggested locations
```

**5. Iteration**:
```
- Recompute Monte Carlo with new GCPs
- Verify uncertainty reduction
- Repeat until satisfied
```

#### Quality Targets

**Minimum acceptable**:
- Training RMSE: <5 pixels
- Validation RMSE: <10 pixels
- Mean uncertainty: <0.5m

**Good quality**:
- Training RMSE: <3 pixels
- Validation RMSE: <5 pixels
- Mean uncertainty: <0.3m

**Excellent quality**:
- Training RMSE: <2 pixels
- Validation RMSE: <3 pixels
- Mean uncertainty: <0.2m

### 6.2 Troubleshooting High Uncertainty

#### Diagnosis

**Symptom**: Mean uncertainty >0.5m despite multiple GCPs

**Possible causes**:

**1. Poor GCP distribution**:
```
Check: Are GCPs clustered in one area?
Fix: Add GCPs to opposite corners/edges
```

**2. High measurement error (σ)**:
```
Check: Is σ too high for your placement quality?
Fix: Reduce σ if you placed points carefully
Example: σ=3.0 → σ=1.5
```

**3. High baseline uncertainty (β)**:
```
Check: Is β too high for your GPS quality?
Fix: Reduce β if using high-quality GPS
Example: β=0.10m → β=0.03m (for RTK)
```

**4. Poor-quality GCPs**:
```
Check: Per-point reprojection errors
Fix: Remove/correct outliers (error >5 pixels)
```

**5. Wrong transformation method**:
```
Check: Using affine for tilted drone image?
Fix: Switch to homography (Edit → Preferences)
```

### 6.3 Interpreting Uncertainty Maps

#### Patterns to Recognize

**Pattern 1: High center, low edges**
```
Cause: GCPs only on edges/corners
Solution: Add 1-2 center GCPs
```

**Pattern 2: Gradient from one corner**
```
Cause: Missing GCP in opposite corner
Solution: Add GCP in high-uncertainty corner
```

**Pattern 3: Uniform low uncertainty**
```
Cause: Well-distributed GCPs
Action: No action needed ✓
```

**Pattern 4: Streaks/bands of high uncertainty**
```
Cause: Collinear GCPs (all on one line)
Solution: Add GCP perpendicular to the line
```

**Pattern 5: Very high everywhere (>1m)**
```
Cause: Poor georeferencing quality
Solution: Review all GCP coordinates, check RMSE
```

#### Using Overlay for GCP Placement

**Workflow**:
1. Enable overlay: View → Uncertainty Overlay → Position
2. Visual scan: Identify red/orange areas
3. Zoom in: Find identifiable feature in high-uncertainty area
4. Add GCP: Place control point at that feature
5. Recompute: Run Monte Carlo again
6. Verify: Check that area is now yellow/green

**Before/After example**:
```
Before (4 corner GCPs):
┌─────────────────┐
│ G     Y     G   │  Mean: 0.28m
│ Y     O     Y   │  Max:  0.45m
│ O     R     O   │  Bad:  35% area >0.3m
│ Y     O     Y   │
│ G     Y     G   │
└─────────────────┘

After (6 GCPs: corners + center + right edge):
┌─────────────────┐
│ G     G     G   │  Mean: 0.12m
│ G     G     G   │  Max:  0.18m
│ G     G     G   │  Bad:  0% area >0.3m
│ G     G     G   │
│ G     G     G   │
└─────────────────┘
```

### 6.4 Optimal GCP Placement Strategy

#### Information-Theoretic Approach

**Goal**: Minimize expected uncertainty with N total GCPs

**Greedy algorithm**:
```
1. Add 4 corner GCPs (required)
2. Run Monte Carlo → get uncertainty map
3. While N < budget:
    a. Find location with max uncertainty
    b. Add GCP at that location
    c. Recompute Monte Carlo
4. Done
```

**ORBIT implements**: Steps 2-3a automatically via "Suggest GCP Locations"

**User completes**: Steps 3b-3c (add suggested GCPs, recompute)

#### Diminishing Returns

**Uncertainty reduction** is logarithmic in number of GCPs:

```
uncertainty ∝ 1 / √N
```

**Example**:
- 4 GCPs: mean uncertainty = 0.40m
- 6 GCPs: mean uncertainty = 0.28m (30% reduction)
- 8 GCPs: mean uncertainty = 0.22m (22% reduction)
- 10 GCPs: mean uncertainty = 0.18m (18% reduction)
- 12 GCPs: mean uncertainty = 0.16m (11% reduction)

**Practical limit**: ~8-10 GCPs for typical applications
- Further additions yield <10% improvement
- Effort not justified unless very high precision needed

---

## Implementation Details

### 7.1 Code Architecture

#### Key Classes

**`UncertaintyEstimator`** (utils/uncertainty_estimator.py):
- `compute_uncertainty_monte_carlo()`: Main MC algorithm
- `run_bootstrap_analysis()`: Bootstrap alternative
- `estimate_position_uncertainty_at_point()`: Query uncertainty at pixel
- `find_high_uncertainty_regions()`: GCP suggestion
- `get_uncertainty_statistics()`: Aggregate statistics

**`UncertaintyOverlay`** (gui/uncertainty_overlay.py):
- `_create_heat_map()`: Generate color-coded overlay
- `_find_suggestion_points()`: Compute markers
- `paint()`: Render overlay on image

**`GeoreferenceDialog`** (gui/georeference_dialog.py):
- `run_monte_carlo_analysis()`: UI for MC computation
- `suggest_gcp_locations()`: UI for suggestions
- `update_uncertainty_statistics()`: Display stats

#### Data Flow

```
User clicks "Compute Uncertainty (Monte Carlo)"
    ↓
GeoreferenceDialog.run_monte_carlo_analysis()
    ↓
UncertaintyEstimator.compute_uncertainty_monte_carlo(
    n_iterations=200,
    sigma_pixels=project.mc_sigma_pixels,
    resolution=(50, 50)
)
    ↓
[200 iterations of noise + transformation]
    ↓
uncertainty_grid = np.std(position_samples)
    ↓
project.uncertainty_grid_cache = uncertainty_grid.tolist()
    ↓
GeoreferenceDialog.update_uncertainty_statistics()
    ↓
Display: mean, max, coverage statistics
```

### 7.2 Performance Optimizations

#### NumPy Vectorization

**Before** (slow):
```python
for i in range(rows):
    for j in range(cols):
        uncertainty[i, j] = compute_uncertainty(i, j)  # 2500 calls
```

**After** (fast):
```python
std_x = np.std(position_samples_x, axis=0)  # Vectorized
std_y = np.std(position_samples_y, axis=0)
uncertainty = np.sqrt(std_x**2 + std_y**2)  # Single operation
```

**Speedup**: 100-1000× faster

#### Grid Resolution Trade-off

**Options**:
- Low-res (25×25): Fast (<5s), coarse estimates
- Medium-res (50×50): **Default** - Good balance (~20s)
- High-res (100×100): Slow (~60s), fine-grained

**Storage**:
- 50×50 grid: 2,500 values × 8 bytes = 20 KB
- Cached in .orbit file (negligible)

#### Caching Strategy

**First run**: Compute and cache
```
200 iterations × 50×50 grid = ~20 seconds
```

**Subsequent queries**: Instant
```
Bilinear interpolation from cache = <1ms
```

**Cache invalidation**: Automatic when GCPs change

### 7.3 Validation and Testing

#### Unit Tests

**Test cases** (manual testing):
1. **MC convergence**: Verify σ estimates stable after 200 iterations
2. **Known transformation**: Synthetic data with known error → check estimates
3. **Outlier handling**: Singular matrix iterations skipped correctly
4. **Grid interpolation**: Bilinear interpolation matches expected values

#### Integration Tests

**Workflow tests**:
1. Add 4 GCPs → Run MC → Verify mean ~0.2-0.4m
2. Add 2 more GCPs → Run MC → Verify mean decreases
3. Change σ parameter → Verify uncertainty scales proportionally
4. Enable overlay → Verify no crashes, reasonable display

#### Validation Against Literature

**Expected behavior**:
- Uncertainty increases with distance from GCPs ✓
- Uncertainty decreases with more GCPs ✓
- σ<sub>position</sub> ∝ σ<sub>measurement</sub> ✓
- Bootstrap ≈ Monte Carlo (for similar assumptions) ✓

---

## References

### Academic Literature

1. **Hartley, R., & Zisserman, A. (2003)**. *Multiple View Geometry in Computer Vision*. Cambridge University Press.
   - Chapter 4: Estimation (2D projective transformations)
   - Section 4.1.6: Uncertainty estimation

2. **Mikhail, E. M., Bethel, J. S., & McGlone, J. C. (2001)**. *Introduction to Modern Photogrammetry*. Wiley.
   - Chapter 5: Error propagation in coordinate transformations

3. **Förstner, W., & Wrobel, B. P. (2016)**. *Photogrammetric Computer Vision*. Springer.
   - Section 6.3: Quality assessment of georeferencing

4. **Kraus, K. (2007)**. *Photogrammetry: Geometry from Images and Laser Scans*. De Gruyter.
   - Chapter 6: Accuracy and reliability

### Statistical Methods

5. **Efron, B., & Tibshirani, R. J. (1993)**. *An Introduction to the Bootstrap*. Chapman and Hall.
   - Bootstrap methods for uncertainty estimation

6. **JCGM (2008)**. *Evaluation of measurement data - Guide to the expression of uncertainty in measurement*. BIPM.
   - GUM framework for uncertainty quantification

### Implementation Resources

7. **OpenCV Documentation**: Camera Calibration and 3D Reconstruction
   - Practical implementation of homography estimation

8. **NumPy Documentation**: Random sampling and statistics
   - Monte Carlo implementation techniques

---

**Document Version**: 1.0
**Last Updated**: 2025-11-12
**Authors**: ORBIT Development Team
**Status**: Complete ✅

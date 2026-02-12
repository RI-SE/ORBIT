"""
Georeferencing uncertainty estimation module.

Provides tools to estimate and analyze uncertainty in georeferencing transformations,
helping users identify where to add control points and assess data quality.
"""

import copy
import math
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
from scipy.spatial import ConvexHull, distance

from .coordinate_transform import CoordinateTransformer
from .logging_config import get_logger

logger = get_logger(__name__)


class UncertaintyEstimator:
    """
    Estimates georeferencing uncertainty using distance-weighted residual propagation.

    Uncertainty thresholds (meters):
    - <0.1: Excellent (green)
    - 0.1-0.2: Good (yellow)
    - 0.2-0.4: Warning (orange)
    - >0.4: Bad (red)
    """

    def __init__(self, transformer: CoordinateTransformer,
                 image_width: int, image_height: int,
                 baseline_uncertainty: float = 0.05):
        """
        Initialize uncertainty estimator.

        Args:
            transformer: CoordinateTransformer instance (affine or homography)
            image_width: Image width in pixels
            image_height: Image height in pixels
            baseline_uncertainty: Baseline position uncertainty in meters (default: 0.05m = 5cm)
        """
        self.transformer = transformer
        self.image_width = image_width
        self.image_height = image_height
        self._cached_grid = None
        self._grid_resolution = (50, 50)
        self._calibration_factor = 1.0  # Tuned using validation points

        # Baseline uncertainty in meters (minimum expected error from measurement/digitization)
        # Typical: 1-2 pixels * scale, or ~0.05-0.15m for careful digitization
        self._baseline_uncertainty = baseline_uncertainty

        # Compute reprojection errors for training points
        self._compute_gcp_residuals()

        # Build convex hull for extrapolation detection
        self._build_convex_hull()

        # Auto-calibrate from validation points if available
        if self.transformer.validation_points and len(self.transformer.validation_points) >= 2:
            self.calibrate_from_validation_points()

    def _compute_gcp_residuals(self):
        """Compute reprojection errors for all training GCPs."""
        self.gcp_residuals = {}

        if not self.transformer.training_points:
            return

        residuals_list = []
        for cp in self.transformer.training_points:
            # Transform pixel to geo and back
            lon, lat = self.transformer.pixel_to_geo(cp.pixel_x, cp.pixel_y)
            pred_x, pred_y = self.transformer.geo_to_pixel(lon, lat)

            # Calculate residual in pixels
            residual_px = math.sqrt((pred_x - cp.pixel_x)**2 + (pred_y - cp.pixel_y)**2)

            # Convert to meters using local scale
            mx1, my1 = self.transformer.pixel_to_meters(cp.pixel_x, cp.pixel_y)
            mx2, my2 = self.transformer.pixel_to_meters(cp.pixel_x + residual_px, cp.pixel_y)
            residual_m = math.sqrt((mx2 - mx1)**2 + (my2 - my1)**2)

            self.gcp_residuals[(cp.pixel_x, cp.pixel_y)] = residual_m
            residuals_list.append(residual_m)

        # Compute RMS of reprojection errors
        if residuals_list:
            self.rms_reprojection_error = math.sqrt(sum(r**2 for r in residuals_list) / len(residuals_list))
            # Use baseline if reprojection RMS is too small (well-fitted transformation)
            # This accounts for inherent measurement/digitization uncertainty
            if self.rms_reprojection_error < self._baseline_uncertainty:
                self.rms_reprojection_error = self._baseline_uncertainty
        else:
            self.rms_reprojection_error = self._baseline_uncertainty

    def _build_convex_hull(self):
        """Build convex hull of training GCPs for extrapolation detection."""
        if len(self.transformer.training_points) < 3:
            self.convex_hull = None
            self.hull_points = None
            return

        points = np.array([[cp.pixel_x, cp.pixel_y]
                          for cp in self.transformer.training_points])

        try:
            self.convex_hull = ConvexHull(points)
            self.hull_points = points

            # Calculate characteristic hull size for penalty scaling
            hull_vertices = points[self.convex_hull.vertices]
            self.hull_size = np.max(distance.pdist(hull_vertices))
        except Exception:
            # Collinear points or other issues
            self.convex_hull = None
            self.hull_points = None
            self.hull_size = 0

    def _is_inside_convex_hull(self, x: float, y: float) -> bool:
        """Check if point is inside convex hull of GCPs."""
        if self.convex_hull is None:
            return True  # Can't determine, assume inside

        try:
            # Create test point
            test_point = np.array([x, y])

            # Check if point is inside hull using hyperplane test
            for simplex in self.convex_hull.simplices:
                # Get vertices of simplex (triangle in 2D)
                vertices = self.hull_points[simplex]

                # Check if point is on the same side as hull center
                hull_center = np.mean(self.hull_points[self.convex_hull.vertices], axis=0)

                # Use cross product to determine side
                v1 = vertices[1] - vertices[0]
                v2 = test_point - vertices[0]
                cross = v1[0] * v2[1] - v1[1] * v2[0]

                v2_center = hull_center - vertices[0]
                cross_center = v1[0] * v2_center[1] - v1[1] * v2_center[0]

                if cross * cross_center < 0:
                    # Point is outside this edge
                    return False

            return True
        except Exception:
            return True

    def _distance_from_hull(self, x: float, y: float) -> float:
        """Calculate minimum distance from point to convex hull boundary."""
        if self.convex_hull is None:
            return 0.0

        min_dist = float('inf')
        point = np.array([x, y])

        # Check distance to each edge
        for simplex in self.convex_hull.simplices:
            p1 = self.hull_points[simplex[0]]
            p2 = self.hull_points[simplex[1]]

            # Distance from point to line segment
            d = self._point_to_segment_distance(point, p1, p2)
            min_dist = min(min_dist, d)

        return min_dist

    def _point_to_segment_distance(self, point: np.ndarray,
                                   seg_start: np.ndarray,
                                   seg_end: np.ndarray) -> float:
        """Calculate distance from point to line segment."""
        # Vector from seg_start to seg_end
        seg_vec = seg_end - seg_start
        seg_len_sq = np.dot(seg_vec, seg_vec)

        if seg_len_sq < 1e-10:
            # Degenerate segment
            return np.linalg.norm(point - seg_start)

        # Project point onto line
        t = max(0, min(1, np.dot(point - seg_start, seg_vec) / seg_len_sq))
        projection = seg_start + t * seg_vec

        return np.linalg.norm(point - projection)

    def estimate_position_uncertainty_at_point(self, x: float, y: float) -> float:
        """
        Estimate position uncertainty (meters) at pixel location.

        Uses cached Monte Carlo grid if available, otherwise returns baseline.

        Args:
            x: Pixel x coordinate
            y: Pixel y coordinate

        Returns:
            Uncertainty in meters
        """
        # Use cached grid if available
        if self._cached_grid is not None:
            return self._interpolate_uncertainty_from_grid(x, y)

        # Fallback: return baseline with distance heuristic
        if not self.transformer.training_points:
            return 1.0

        # Simple heuristic: check if near any GCP
        gcp_points = [(cp.pixel_x, cp.pixel_y) for cp in self.transformer.training_points]
        min_dist = min(math.sqrt((x - gcp_x)**2 + (y - gcp_y)**2) for gcp_x, gcp_y in gcp_points)

        # Scale linearly with distance (very rough estimate)
        # Typical: 0.1m near GCP, increases to 0.5m at distance = image_width/4
        scale_dist = self.image_width / 4.0
        uncertainty = self._baseline_uncertainty * (1.0 + min_dist / scale_dist)

        return min(uncertainty, 1.0)  # Cap at 1m

    def _interpolate_uncertainty_from_grid(self, x: float, y: float) -> float:
        """
        Interpolate uncertainty from cached grid using bilinear interpolation.

        Args:
            x: Pixel x coordinate
            y: Pixel y coordinate

        Returns:
            Interpolated uncertainty in meters
        """
        if self._cached_grid is None:
            return self._baseline_uncertainty

        rows, cols = self._cached_grid.shape

        # Map pixel to grid coordinates
        gx = (x / self.image_width) * (cols - 1)
        gy = (y / self.image_height) * (rows - 1)

        # Clamp to grid bounds
        gx = max(0, min(cols - 1 - 1e-6, gx))
        gy = max(0, min(rows - 1 - 1e-6, gy))

        # Bilinear interpolation
        x0 = int(gx)
        y0 = int(gy)
        x1 = min(x0 + 1, cols - 1)
        y1 = min(y0 + 1, rows - 1)

        fx = gx - x0
        fy = gy - y0

        v00 = self._cached_grid[y0, x0]
        v10 = self._cached_grid[y0, x1]
        v01 = self._cached_grid[y1, x0]
        v11 = self._cached_grid[y1, x1]

        v0 = v00 * (1 - fx) + v10 * fx
        v1 = v01 * (1 - fx) + v11 * fx
        value = v0 * (1 - fy) + v1 * fy

        return value

    def estimate_scale_uncertainty_at_point(self, x: float, y: float) -> Tuple[float, float]:
        """
        Estimate scale factor uncertainty (cm/px) at pixel location.

        Samples nearby points (±5px) to calculate local scale variation.

        Args:
            x: Pixel x coordinate
            y: Pixel y coordinate

        Returns:
            (x_uncertainty_cm_per_px, y_uncertainty_cm_per_px)
        """
        offset = 5.0  # pixels

        try:
            # Calculate scales in X and Y directions
            mx1, my1 = self.transformer.pixel_to_meters(x, y)
            mx2, my2 = self.transformer.pixel_to_meters(x + offset, y)
            mx3, my3 = self.transformer.pixel_to_meters(x, y + offset)

            # Scale factors (meters per pixel)
            _scale_x = math.sqrt((mx2 - mx1)**2 + (my2 - my1)**2) / offset
            _scale_y = math.sqrt((mx3 - mx1)**2 + (my3 - my1)**2) / offset

            # Position uncertainty at this point
            pos_unc = self.estimate_position_uncertainty_at_point(x, y)

            # Scale uncertainty is proportional to position uncertainty
            # Convert to cm/px
            scale_unc_x = (pos_unc / offset) * 100  # meters to cm
            scale_unc_y = (pos_unc / offset) * 100

            return (scale_unc_x, scale_unc_y)

        except Exception:
            # Fallback to default uncertainty
            return (1.0, 1.0)

    def generate_uncertainty_grid(self, resolution: Optional[Tuple[int, int]] = None) -> np.ndarray:
        """
        Generate 2D grid of position uncertainties across entire image.

        Args:
            resolution: (rows, cols) for grid. If None, uses default (50, 50)

        Returns:
            Array[rows, cols] with uncertainty in meters at each grid point
            Cached for performance - invalidated when GCPs change
        """
        if resolution is None:
            resolution = self._grid_resolution

        rows, cols = resolution

        # Create grid of sample points
        x_coords = np.linspace(0, self.image_width, cols)
        y_coords = np.linspace(0, self.image_height, rows)

        # Initialize grid
        grid = np.zeros((rows, cols))

        # Calculate uncertainty at each grid point
        for i, y in enumerate(y_coords):
            for j, x in enumerate(x_coords):
                grid[i, j] = self.estimate_position_uncertainty_at_point(x, y)

        # Cache the result
        self._cached_grid = grid

        return grid

    def compute_uncertainty_monte_carlo(self, n_iterations: int = 200,
                                       sigma_pixels: float = 1.5,
                                       resolution: Optional[Tuple[int, int]] = None,
                                       progress_callback: Optional[Callable[[int], None]] = None) -> np.ndarray:
        """
        Monte Carlo uncertainty estimation with measurement error.

        Adds Gaussian noise to GCP positions and recomputes transformation many times
        to estimate uncertainty from propagation of measurement error.

        Args:
            n_iterations: Number of Monte Carlo samples (default 200)
            sigma_pixels: Standard deviation of measurement error in pixels (default 1.5)
            resolution: (rows, cols) for grid. If None, uses default (50, 50)
            progress_callback: Optional callback function(percent) for progress updates

        Returns:
            Uncertainty grid (rows×cols) with uncertainty in meters at each point
        """
        if resolution is None:
            resolution = self._grid_resolution

        rows, cols = resolution

        # Grid coordinates
        x_coords = np.linspace(0, self.image_width, cols)
        y_coords = np.linspace(0, self.image_height, rows)

        # Store position samples for each grid point (in meters)
        position_samples_x = np.zeros((n_iterations, rows, cols))
        position_samples_y = np.zeros((n_iterations, rows, cols))

        # Get transformer class
        if hasattr(self.transformer, 'H'):
            from .coordinate_transform import HomographyTransformer
            TransformerClass = HomographyTransformer
        else:
            from .coordinate_transform import AffineTransformer
            TransformerClass = AffineTransformer

        # Get training points
        training_points = self.transformer.training_points
        validation_points = self.transformer.validation_points

        for iteration in range(n_iterations):
            try:
                # Add Gaussian noise to GCP pixel positions
                noisy_gcps = []
                for gcp in training_points:
                    noise_x = np.random.normal(0, sigma_pixels)
                    noise_y = np.random.normal(0, sigma_pixels)

                    # Create noisy GCP (deep copy to avoid modifying original)
                    noisy_gcp = copy.copy(gcp)
                    noisy_gcp.pixel_x = gcp.pixel_x + noise_x
                    noisy_gcp.pixel_y = gcp.pixel_y + noise_y
                    noisy_gcps.append(noisy_gcp)

                # Combine with validation points (don't add noise to those)
                all_points = noisy_gcps + validation_points

                # Recompute transformation with noisy points
                noisy_transformer = TransformerClass(all_points, use_validation=True)

                # Sample position at each grid point
                for i, y in enumerate(y_coords):
                    for j, x in enumerate(x_coords):
                        # Transform to meters using noisy transformation
                        mx, my = noisy_transformer.pixel_to_meters(x, y)
                        position_samples_x[iteration, i, j] = mx
                        position_samples_y[iteration, i, j] = my

            except Exception:
                # If transformation fails (singular matrix), skip this iteration
                # Use previous iteration's values
                if iteration > 0:
                    position_samples_x[iteration, :, :] = position_samples_x[iteration - 1, :, :]
                    position_samples_y[iteration, :, :] = position_samples_y[iteration - 1, :, :]

            # Report progress (every iteration to keep UI responsive)
            if progress_callback:
                percent = int((iteration + 1) / n_iterations * 100)
                progress_callback(percent)

        # Calculate position uncertainty as RMS of X and Y standard deviations
        # This is the uncertainty in transformed position (meters)
        std_x = np.std(position_samples_x, axis=0)
        std_y = np.std(position_samples_y, axis=0)

        # Combined positional uncertainty (RSS)
        uncertainty_grid = np.sqrt(std_x**2 + std_y**2)

        # Cache the result
        self._cached_grid = uncertainty_grid

        if progress_callback:
            progress_callback(100)

        return uncertainty_grid

    def find_high_uncertainty_regions(self, threshold: float = 0.2,
                                     region_grid: Tuple[int, int] = (4, 3),
                                     verbose: bool = False) -> List[Tuple[float, float]]:
        """
        Identify locations where adding a GCP would help most.

        Strategy:
        - Divide image into regions (e.g., 4×3 = 12 squares)
        - Find highest uncertainty point in each region
        - Only suggest regions where max uncertainty > threshold
        - Return pixel coordinates of suggestions (one per qualifying region)

        This approach ensures good spatial distribution of suggestions.

        Args:
            threshold: Minimum uncertainty (meters) to consider
            region_grid: (cols, rows) for dividing image (default: 4×3 = 12 regions)
            verbose: Enable debug output (default: False)

        Returns:
            List of (x, y) pixel coordinates, up to len(region_grid) points
        """
        # Generate grid if not cached
        if self._cached_grid is None:
            grid = self.generate_uncertainty_grid()
        else:
            grid = self._cached_grid

        grid_rows, grid_cols = grid.shape
        region_cols, region_rows = region_grid

        # Debug info
        if verbose:
            logger.debug("Grid shape: %s", grid.shape)
            logger.debug("Grid min/max: %.3f / %.3fm", np.min(grid), np.max(grid))
            logger.debug("Threshold: %.3fm", threshold)
            total_regions = region_cols * region_rows
            logger.debug("Dividing into %dx%d = %d regions",
                         region_cols, region_rows, total_regions)
            cells_above_threshold = np.sum(grid >= threshold)
            logger.debug("Cells above threshold: %d / %d",
                         cells_above_threshold, grid_rows * grid_cols)

        # Calculate region boundaries
        region_height_cells = grid_rows // region_rows
        region_width_cells = grid_cols // region_cols

        suggestions = []

        # Process each region
        for region_row in range(region_rows):
            for region_col in range(region_cols):
                # Define region boundaries in grid coordinates
                row_start = region_row * region_height_cells
                row_end = (region_row + 1) * region_height_cells if region_row < region_rows - 1 else grid_rows
                col_start = region_col * region_width_cells
                col_end = (region_col + 1) * region_width_cells if region_col < region_cols - 1 else grid_cols

                # Extract region from grid
                region = grid[row_start:row_end, col_start:col_end]

                # Find max uncertainty in this region
                max_unc = np.max(region)

                # Only suggest if above threshold
                if max_unc >= threshold:
                    # Find location of maximum within region
                    region_max_idx = np.unravel_index(np.argmax(region), region.shape)
                    grid_i = row_start + region_max_idx[0]
                    grid_j = col_start + region_max_idx[1]

                    # Convert grid indices to pixel coordinates
                    x = (grid_j / (grid_cols - 1)) * self.image_width
                    y = (grid_i / (grid_rows - 1)) * self.image_height

                    suggestions.append((x, y, max_unc))
                    if verbose:
                        logger.debug("Region (%d,%d): max=%.3fm at pixel (%.0f,%.0f)",
                                     region_row, region_col, max_unc, x, y)

        # Sort by uncertainty (descending) to prioritize worst areas
        suggestions.sort(key=lambda s: s[2], reverse=True)

        if verbose:
            logger.debug("Found %d suggestions from %d regions",
                         len(suggestions), region_cols * region_rows)

        # Return just (x, y) coordinates
        return [(x, y) for x, y, _ in suggestions]

    def get_uncertainty_statistics(self) -> Dict:
        """
        Compute overall uncertainty statistics from grid.

        Returns:
            {
                'mean': 0.15,
                'median': 0.12,
                'max': 0.45,
                'p90': 0.28,  # 90th percentile
                'coverage': {
                    0.1: 0.42,  # 42% of image within 0.1m
                    0.2: 0.78,  # 78% within 0.2m
                    0.4: 0.95,  # 95% within 0.4m
                }
            }
        """
        # Generate grid if not cached
        if self._cached_grid is None:
            grid = self.generate_uncertainty_grid()
        else:
            grid = self._cached_grid

        # Flatten grid for statistics
        values = grid.flatten()

        # Calculate statistics
        stats = {
            'mean': float(np.mean(values)),
            'median': float(np.median(values)),
            'min': float(np.min(values)),
            'max': float(np.max(values)),
            'p90': float(np.percentile(values, 90)),
            'coverage': {}
        }

        # Calculate coverage percentages
        thresholds = [0.1, 0.2, 0.4]
        for threshold in thresholds:
            coverage = np.sum(values <= threshold) / len(values)
            stats['coverage'][threshold] = float(coverage)

        return stats

    def calibrate_from_validation_points(self) -> float:
        """
        Tune uncertainty model using actual GVP errors.

        Compares predicted uncertainty to actual validation errors.
        Adjusts internal scaling factor for better accuracy.

        Returns:
            Calibration quality (0-1, higher is better)
        """
        if not self.transformer.validation_points or len(self.transformer.validation_points) < 2:
            return 0.0

        # Calculate actual validation errors
        actual_errors = []
        predicted_uncertainties = []

        for vp in self.transformer.validation_points:
            # Transform pixel to geo using training-only transformer
            pred_lon, pred_lat = self.transformer.pixel_to_geo(vp.pixel_x, vp.pixel_y)

            # Calculate error in meters
            # Convert both predicted and actual to meters
            pred_mx, pred_my = self.transformer.pixel_to_meters(vp.pixel_x, vp.pixel_y)

            # Get actual position in meters by transforming actual geo coords
            actual_mx, actual_my = self._geo_to_meters(vp.longitude, vp.latitude)

            actual_error = math.sqrt((pred_mx - actual_mx)**2 + (pred_my - actual_my)**2)
            actual_errors.append(actual_error)

            # Get predicted uncertainty at this point
            pred_unc = self.estimate_position_uncertainty_at_point(vp.pixel_x, vp.pixel_y)
            predicted_uncertainties.append(pred_unc)

        # Calculate calibration factor
        # We want predicted uncertainties to match actual errors
        actual_errors = np.array(actual_errors)
        predicted_uncertainties = np.array(predicted_uncertainties)

        # Avoid division by zero
        if np.mean(predicted_uncertainties) > 1e-6:
            calibration_factor = np.mean(actual_errors) / np.mean(predicted_uncertainties)
            self._calibration_factor = calibration_factor

        # Calculate calibration quality (correlation)
        if len(actual_errors) >= 2:
            correlation = np.corrcoef(actual_errors, predicted_uncertainties)[0, 1]
            quality = abs(correlation)
        else:
            quality = 0.0

        return quality

    def _geo_to_meters(self, lon: float, lat: float) -> Tuple[float, float]:
        """Convert geographic coordinates to local metric coordinates."""
        # Use the transformer's reference point and projection
        # This is a simplified version - the actual implementation depends on
        # how the transformer handles geo to meters conversion

        if not self.transformer.training_points:
            return (0.0, 0.0)

        # Get a reference point (center of training points)
        ref_lats = [cp.latitude for cp in self.transformer.training_points]
        ref_lons = [cp.longitude for cp in self.transformer.training_points]
        ref_lat = np.mean(ref_lats)
        ref_lon = np.mean(ref_lons)

        # Simple equirectangular approximation
        lat_m_per_deg = 111000.0
        lon_m_per_deg = 111000.0 * math.cos(math.radians(ref_lat))

        mx = (lon - ref_lon) * lon_m_per_deg
        my = (lat - ref_lat) * lat_m_per_deg

        return (mx, my)

    def run_bootstrap_analysis(self, n_iterations: int = 200,
                              progress_callback: Optional[Callable[[int], None]] = None) -> np.ndarray:
        """
        Detailed bootstrap uncertainty analysis (runs in background).

        For each iteration:
        1. Resample GCPs with replacement
        2. Compute new transformation
        3. Calculate uncertainty at grid points

        Args:
            n_iterations: Number of bootstrap iterations (default 200)
            progress_callback: Optional callback function(percent) for progress updates

        Returns:
            High-resolution uncertainty grid (200x200)
        """
        if not self.transformer.training_points or len(self.transformer.training_points) < 3:
            # Not enough points for bootstrap
            return self.generate_uncertainty_grid((200, 200))

        # High resolution grid
        rows, cols = 200, 200
        x_coords = np.linspace(0, self.image_width, cols)
        y_coords = np.linspace(0, self.image_height, rows)

        # Store scale values for each iteration at each grid point
        scale_samples = np.zeros((n_iterations, rows, cols))

        training_points = self.transformer.training_points
        n_points = len(training_points)

        # Get transformer method
        if hasattr(self.transformer, 'H'):
            from .coordinate_transform import HomographyTransformer
            TransformerClass = HomographyTransformer
        else:
            from .coordinate_transform import AffineTransformer
            TransformerClass = AffineTransformer

        for iteration in range(n_iterations):
            # Resample with replacement
            indices = np.random.choice(n_points, size=n_points, replace=True)
            resampled_points = [training_points[i] for i in indices]

            try:
                # Create new transformer with resampled points
                # Combine with validation points (don't resample those)
                all_points = resampled_points + self.transformer.validation_points
                resampled_transformer = TransformerClass(all_points, use_validation=True)

                # Calculate scale at each grid point
                for i, y in enumerate(y_coords):
                    for j, x in enumerate(x_coords):
                        # Calculate scale
                        offset = 5.0
                        mx1, my1 = resampled_transformer.pixel_to_meters(x, y)
                        mx2, my2 = resampled_transformer.pixel_to_meters(x + offset, y)
                        scale = math.sqrt((mx2 - mx1)**2 + (my2 - my1)**2) / offset
                        scale_samples[iteration, i, j] = scale

            except Exception:
                # Resampling may create singular matrices occasionally
                # Skip this iteration
                continue

            # Report progress (every iteration to keep UI responsive)
            if progress_callback:
                percent = int((iteration + 1) / n_iterations * 100)
                progress_callback(percent)

        # Calculate standard deviation across iterations at each point
        uncertainty_grid = np.std(scale_samples, axis=0)

        if progress_callback:
            progress_callback(100)

        return uncertainty_grid

"""
Uncertainty overlay visualization for georeferencing quality assessment.

Displays a color-coded heat map showing position uncertainty across the image,
with optional markers suggesting optimal GCP placement locations.
"""

import numpy as np
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QGraphicsItem

from orbit.utils.uncertainty_estimator import UncertaintyEstimator


class UncertaintyOverlay(QGraphicsItem):
    """
    Heat map overlay showing uncertainty across image.

    Features:
    - Color-coded uncertainty levels (green/yellow/orange/red)
    - Semi-transparent (30% opacity)
    - Suggested GCP markers (orange circles)
    - Toggle visibility via View menu
    """

    def __init__(self, estimator: UncertaintyEstimator, show_suggestions: bool = True,
                 suggestion_threshold: float = 0.2):
        """
        Initialize overlay with uncertainty estimator.

        Args:
            estimator: UncertaintyEstimator instance
            show_suggestions: Whether to show suggested GCP locations
            suggestion_threshold: Minimum uncertainty (meters) for GCP suggestions
        """
        super().__init__()

        self.estimator = estimator
        self.show_suggestions = show_suggestions
        self.suggestion_threshold = suggestion_threshold
        self.uncertainty_grid = None
        self.suggestion_points = []
        self.heat_map_pixmap = None

        # Generate the heat map
        self._create_heat_map()

        # Find suggested GCP locations
        if self.show_suggestions:
            self._find_suggestion_points()

        # Set item properties
        self.setZValue(50)  # Above image, below polylines

    def _create_heat_map(self):
        """
        Generate heat map from uncertainty grid.

        Process:
        1. Get uncertainty grid from estimator
        2. Map uncertainties to colors:
           - <0.1m: rgba(0, 255, 0, 128)    # Green, 50% opacity
           - 0.1-0.2m: rgba(255, 255, 0, 128) # Yellow
           - 0.2-0.4m: rgba(255, 165, 0, 128) # Orange
           - >0.4m: rgba(255, 0, 0, 128)      # Red
        3. Create QPixmap with colored grid
        4. Smooth transitions using bilinear interpolation
        """
        # Generate uncertainty grid
        self.uncertainty_grid = self.estimator.generate_uncertainty_grid()
        rows, cols = self.uncertainty_grid.shape

        # Create moderate-resolution image (scale down for performance)
        # We'll create at grid resolution and let Qt scale it up smoothly
        target_width = cols
        target_height = rows

        # Create RGBA array using NumPy (much faster than pixel-by-pixel)
        rgba_array = np.zeros((target_height, target_width, 4), dtype=np.uint8)

        # Vectorized color mapping
        alpha = 128  # 50% opacity

        # Green: < 0.1m
        mask = self.uncertainty_grid < 0.1
        rgba_array[mask] = [0, 255, 0, alpha]

        # Green to Yellow: 0.1-0.2m
        mask = (self.uncertainty_grid >= 0.1) & (self.uncertainty_grid < 0.2)
        t = (self.uncertainty_grid[mask] - 0.1) / 0.1
        rgba_array[mask, 0] = (255 * t).astype(np.uint8)
        rgba_array[mask, 1] = 255
        rgba_array[mask, 2] = 0
        rgba_array[mask, 3] = alpha

        # Yellow to Orange: 0.2-0.4m
        mask = (self.uncertainty_grid >= 0.2) & (self.uncertainty_grid < 0.4)
        t = (self.uncertainty_grid[mask] - 0.2) / 0.2
        rgba_array[mask, 0] = 255
        rgba_array[mask, 1] = (255 - 90 * t).astype(np.uint8)
        rgba_array[mask, 2] = 0
        rgba_array[mask, 3] = alpha

        # Orange to Red: >= 0.4m
        mask = self.uncertainty_grid >= 0.4
        t = np.minimum(1.0, (self.uncertainty_grid[mask] - 0.4) / 0.2)
        rgba_array[mask, 0] = 255
        rgba_array[mask, 1] = (165 * (1 - t)).astype(np.uint8)
        rgba_array[mask, 2] = 0
        rgba_array[mask, 3] = alpha

        # Convert NumPy array to QImage
        height, width = rgba_array.shape[:2]
        bytes_per_line = 4 * width
        image = QImage(rgba_array.data, width, height, bytes_per_line, QImage.Format.Format_RGBA8888)

        # Convert to pixmap and scale to full image size (Qt does smooth scaling)
        self.heat_map_pixmap = QPixmap.fromImage(image).scaled(
            self.estimator.image_width,
            self.estimator.image_height,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

    def _interpolate_grid_value(self, gx: float, gy: float) -> float:
        """
        Interpolate uncertainty value from grid using bilinear interpolation.

        Args:
            gx: Grid x coordinate (float)
            gy: Grid y coordinate (float)

        Returns:
            Interpolated uncertainty value
        """
        rows, cols = self.uncertainty_grid.shape

        # Clamp to grid bounds
        gx = max(0, min(cols - 1 - 1e-6, gx))
        gy = max(0, min(rows - 1 - 1e-6, gy))

        # Get integer and fractional parts
        x0 = int(gx)
        y0 = int(gy)
        x1 = min(x0 + 1, cols - 1)
        y1 = min(y0 + 1, rows - 1)

        fx = gx - x0
        fy = gy - y0

        # Bilinear interpolation
        v00 = self.uncertainty_grid[y0, x0]
        v10 = self.uncertainty_grid[y0, x1]
        v01 = self.uncertainty_grid[y1, x0]
        v11 = self.uncertainty_grid[y1, x1]

        v0 = v00 * (1 - fx) + v10 * fx
        v1 = v01 * (1 - fx) + v11 * fx
        value = v0 * (1 - fy) + v1 * fy

        return value

    def _uncertainty_to_color(self, uncertainty: float) -> QColor:
        """
        Map uncertainty value to color with smooth transitions.

        Thresholds:
        - <0.1m: Green
        - 0.1-0.2m: Yellow
        - 0.2-0.4m: Orange
        - >0.4m: Red

        Args:
            uncertainty: Uncertainty in meters

        Returns:
            QColor with 30% opacity (alpha=76)
        """
        alpha = 76  # 30% opacity

        if uncertainty < 0.1:
            # Green
            return QColor(0, 255, 0, alpha)
        elif uncertainty < 0.2:
            # Interpolate between green and yellow
            t = (uncertainty - 0.1) / 0.1  # 0 to 1
            r = int(255 * t)
            g = 255
            b = 0
            return QColor(r, g, b, alpha)
        elif uncertainty < 0.4:
            # Interpolate between yellow and orange
            t = (uncertainty - 0.2) / 0.2  # 0 to 1
            r = 255
            g = int(255 - 90 * t)  # 255 to 165
            b = 0
            return QColor(r, g, b, alpha)
        else:
            # Interpolate between orange and red
            t = min(1.0, (uncertainty - 0.4) / 0.2)  # 0 to 1
            r = 255
            g = int(165 * (1 - t))  # 165 to 0
            b = 0
            return QColor(r, g, b, alpha)

    def _find_suggestion_points(self):
        """
        Find suggested GCP locations using estimator.

        Updates self.suggestion_points with [(x, y), ...] coordinates.
        """
        self.suggestion_points = self.estimator.find_high_uncertainty_regions(
            threshold=self.suggestion_threshold
        )

    def update_overlay(self):
        """Regenerate overlay when GCPs change."""
        self._create_heat_map()

        if self.show_suggestions:
            self._find_suggestion_points()

        self.update()

    def set_show_suggestions(self, show: bool):
        """Toggle GCP suggestion markers."""
        self.show_suggestions = show
        if show and not self.suggestion_points:
            self._find_suggestion_points()
        self.update()

    def paint(self, painter: QPainter, option, widget):
        """
        Render the overlay.

        Args:
            painter: QPainter instance
            option: Style options (unused)
            widget: Widget being painted on (unused)
        """
        if not self.heat_map_pixmap:
            return

        # Draw heat map
        painter.drawPixmap(0, 0, self.heat_map_pixmap)

        # Draw suggestion markers if enabled
        if self.show_suggestions and self.suggestion_points:
            self._draw_suggestion_markers(painter)

    def _draw_suggestion_markers(self, painter: QPainter):
        """
        Draw markers at suggested GCP locations.

        Visual style:
        - Orange circle outline (3px thick)
        - Diameter: 20px
        - No fill (transparent center)
        - Label showing uncertainty value
        """
        # Set up pen for circles
        pen = QPen(QColor(255, 140, 0))  # Dark orange
        pen.setWidth(3)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)  # No fill

        # Set up font for labels
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)

        marker_radius = 10  # pixels

        for x, y in self.suggestion_points:
            # Draw circle
            painter.drawEllipse(int(x - marker_radius), int(y - marker_radius),
                              marker_radius * 2, marker_radius * 2)

            # Get uncertainty value at this point
            uncertainty = self.estimator.estimate_position_uncertainty_at_point(x, y)

            # Draw label to the right of circle
            label = f"{uncertainty:.2f}m"
            label_x = int(x + marker_radius + 5)
            label_y = int(y - marker_radius)

            # Get text dimensions
            text_rect = painter.fontMetrics().boundingRect(label)
            text_width = text_rect.width()
            text_height = text_rect.height()

            # Create background rectangle at the label position
            bg_rect = QRectF(label_x - 3, label_y - 1, text_width + 6, text_height + 2)
            painter.fillRect(bg_rect, QColor(128, 128, 128, 200))  # Grey background

            # Draw text inside the background rectangle
            # drawText with baseline, so add ascent to position properly
            painter.setPen(QColor(255, 255, 255))  # White text for contrast
            painter.drawText(int(label_x), int(label_y + painter.fontMetrics().ascent()), label)

    def boundingRect(self) -> QRectF:
        """
        Return bounding rectangle (entire image).

        Returns:
            QRectF covering the full image dimensions
        """
        return QRectF(0, 0, self.estimator.image_width, self.estimator.image_height)

"""UI constants for ORBIT application.

Centralizes colors, opacity values, and default settings used across
the GUI to ensure consistency and easy maintenance.
"""

from PyQt6.QtGui import QColor

# =============================================================================
# OPACITY VALUES
# =============================================================================

# Interactive element opacity
OPACITY_DEFAULT = 77      # ~30% opacity for lane polygons
OPACITY_HOVER = 204       # ~80% opacity on hover
OPACITY_SEMI = 100        # Semi-transparent elements
OPACITY_OVERLAY = 180     # Dark overlay backgrounds


# =============================================================================
# SCALE DEFAULTS
# =============================================================================

# Default scale when no georeferencing available (m/px)
DEFAULT_SCALE_M_PER_PX = 0.058  # 5.8 cm/px

# Default lane width in meters
DEFAULT_LANE_WIDTH_M = 3.5


# =============================================================================
# POLYLINE COLORS
# =============================================================================

# Centerline colors
COLOR_CENTERLINE = QColor(255, 165, 0)       # Orange
COLOR_CENTERLINE_SELECTED = QColor(255, 255, 0)  # Yellow when selected

# Lane boundary colors
COLOR_LANE_BOUNDARY = QColor(0, 255, 255)    # Cyan
COLOR_LANE_BOUNDARY_SELECTED = QColor(255, 255, 0)  # Yellow when selected

# Point colors
COLOR_POINT_DEFAULT = QColor(255, 255, 0)    # Yellow
COLOR_POINT_SELECTED = QColor(255, 128, 0)   # Orange for selected point


# =============================================================================
# LANE VISUALIZATION COLORS
# =============================================================================

# Lane polygon base colors (used with alpha for transparency)
COLOR_LANE_RIGHT = QColor(100, 255, 100)     # Green for right lanes
COLOR_LANE_LEFT = QColor(100, 180, 255)      # Blue for left lanes
COLOR_LANE_CENTER = QColor(200, 200, 200)    # Gray for center lane

# Lane polygon borders
COLOR_LANE_BORDER = QColor(200, 200, 200, 150)  # Light gray
COLOR_LANE_BORDER_SELECTED = QColor(0, 0, 0, 255)  # Black when selected


# =============================================================================
# JUNCTION COLORS
# =============================================================================

COLOR_JUNCTION = QColor(255, 0, 255)         # Magenta
COLOR_JUNCTION_SELECTED = QColor(255, 255, 0)  # Yellow when selected
COLOR_JUNCTION_FILL = QColor(255, 0, 255, 100)  # Semi-transparent magenta


# =============================================================================
# MEASUREMENT AND DISPLAY COLORS
# =============================================================================

COLOR_MEASUREMENT_LINE = QColor(0, 255, 255)  # Cyan for measurement
COLOR_TEXT_DEFAULT = QColor(255, 255, 255)    # White text
COLOR_BACKGROUND_OVERLAY = QColor(0, 0, 0, 180)  # Semi-transparent dark


# =============================================================================
# CONTROL POINT COLORS
# =============================================================================

COLOR_CONTROL_POINT_OUTER = QColor(0, 50, 150)    # Dark blue border
COLOR_CONTROL_POINT_FILL = QColor(100, 150, 255, 180)  # Semi-transparent blue
COLOR_CONTROL_POINT_INNER = QColor(0, 100, 255)   # Bright blue center


# =============================================================================
# UNCERTAINTY VISUALIZATION COLORS
# =============================================================================

def get_uncertainty_color(uncertainty_m: float, alpha: int = 200) -> QColor:
    """Get color based on uncertainty level.

    Args:
        uncertainty_m: Uncertainty in meters.
        alpha: Alpha channel value (0-255).

    Returns:
        QColor ranging from green (low) to red (high uncertainty).
    """
    if uncertainty_m < 1.0:
        return QColor(0, 255, 0, alpha)       # Green - good
    elif uncertainty_m < 2.0:
        return QColor(255, 255, 0, alpha)     # Yellow - acceptable
    elif uncertainty_m < 5.0:
        return QColor(255, 165, 0, alpha)     # Orange - marginal
    else:
        return QColor(255, 0, 0, alpha)       # Red - poor


# =============================================================================
# CONNECTING ROAD COLORS
# =============================================================================

COLOR_CONNECTING_ROAD = QColor(255, 200, 0)  # Orange/yellow

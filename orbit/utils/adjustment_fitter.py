"""Auto-fit adjustment from user-picked correspondence point pairs."""

import math
from typing import List, Optional, Tuple

import numpy as np

from orbit.utils.coordinate_transform import TransformAdjustment


def fit_affine(
    sources: List[Tuple[float, float]],
    targets: List[Tuple[float, float]],
) -> np.ndarray:
    """Least-squares fit of a 2D affine matrix mapping sources → targets.

    Solves for M (3×3) such that M × [sx, sy, 1]^T ≈ [tx, ty, 1]^T.
    Requires ≥3 non-collinear point pairs.
    """
    n = len(sources)
    if n < 3:
        raise ValueError(f"Need ≥3 point pairs, got {n}")

    # Build linear system: for each pair, two equations
    # tx = a*sx + b*sy + c
    # ty = d*sx + e*sy + f
    A = np.zeros((2 * n, 6))
    b = np.zeros(2 * n)
    for i, ((sx, sy), (tx, ty)) in enumerate(zip(sources, targets)):
        A[2 * i] = [sx, sy, 1, 0, 0, 0]
        A[2 * i + 1] = [0, 0, 0, sx, sy, 1]
        b[2 * i] = tx
        b[2 * i + 1] = ty

    params, _, _, _ = np.linalg.lstsq(A, b, rcond=None)
    a, b_val, c, d, e, f = params

    return np.array([
        [a, b_val, c],
        [d, e, f],
        [0, 0, 1],
    ], dtype=np.float64)


def decompose_to_adjustment(
    matrix: np.ndarray,
    pivot_x: float,
    pivot_y: float,
) -> TransformAdjustment:
    """Decompose a 3×3 affine matrix into TransformAdjustment parameters.

    Factors M = T_offset × T_from_pivot × R × S × H × T_to_pivot.
    """
    # Extract the 2×2 linear part
    A = matrix[:2, :2].copy()

    # Rotation angle from first column
    theta = math.atan2(A[1, 0], A[0, 0])

    # De-rotate to get S × H
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    R_inv = np.array([[cos_t, sin_t], [-sin_t, cos_t]])
    B = R_inv @ A  # ≈ [[sx, sx*hx], [sy*hy, sy]]

    sx = B[0, 0] if abs(B[0, 0]) > 1e-12 else 1.0
    sy = B[1, 1] if abs(B[1, 1]) > 1e-12 else 1.0
    shear_x = B[0, 1] / sx if abs(sx) > 1e-12 else 0.0
    shear_y = B[1, 0] / sy if abs(sy) > 1e-12 else 0.0

    # Translation: M = T_offset × T_from_pivot × A_linear × T_to_pivot
    # So: M × [px, py, 1]^T = [px + tx, py + ty, 1]^T
    # i.e., tx = M[0,2] + (M[0,0]-1)*(-px) + M[0,1]*(-py) ... actually:
    # M[0,2] = tx + px - A[0,0]*px - A[0,1]*py
    # M[1,2] = ty + py - A[1,0]*px - A[1,1]*py
    tx = matrix[0, 2] - pivot_x + A[0, 0] * pivot_x + A[0, 1] * pivot_y
    ty = matrix[1, 2] - pivot_y + A[1, 0] * pivot_x + A[1, 1] * pivot_y

    return TransformAdjustment(
        translation_x=tx,
        translation_y=ty,
        rotation=math.degrees(theta),
        scale_x=sx,
        scale_y=sy,
        shear_x=shear_x,
        shear_y=shear_y,
        pivot_x=pivot_x,
        pivot_y=pivot_y,
    )


def fit_adjustment(
    sources: List[Tuple[float, float]],
    targets: List[Tuple[float, float]],
    pivot_x: float,
    pivot_y: float,
    current_adjustment: Optional[TransformAdjustment] = None,
) -> TransformAdjustment:
    """Fit adjustment parameters from correspondence point pairs.

    If current_adjustment is set, the fit is composed on top of it:
    M_new = F × M_current, where F maps current displayed positions to targets.
    """
    F = fit_affine(sources, targets)

    if current_adjustment is not None and not current_adjustment.is_identity():
        M_current = current_adjustment.get_adjustment_matrix()
        M_new = F @ M_current
    else:
        M_new = F

    return decompose_to_adjustment(M_new, pivot_x, pivot_y)

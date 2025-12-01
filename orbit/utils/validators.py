"""
Validation utilities for ORBIT.

Provides common validation functions and result types for consistent validation
patterns across the codebase.
"""

from typing import List, Tuple, Optional, Any
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    """
    Result of a validation operation.

    Provides a consistent structure for validation results that includes
    success/failure status and a list of error messages.
    """
    is_valid: bool
    errors: List[str] = field(default_factory=list)

    @staticmethod
    def success() -> 'ValidationResult':
        """Create a successful validation result."""
        return ValidationResult(is_valid=True, errors=[])

    @staticmethod
    def failure(errors: List[str]) -> 'ValidationResult':
        """Create a failed validation result with error messages."""
        return ValidationResult(is_valid=False, errors=errors)

    def add_error(self, message: str) -> None:
        """Add an error message and mark as invalid."""
        self.errors.append(message)
        self.is_valid = False

    def merge(self, other: 'ValidationResult') -> None:
        """Merge another validation result into this one."""
        if not other.is_valid:
            self.is_valid = False
            self.errors.extend(other.errors)


def has_minimum_points(
    points: List[Tuple[float, float]],
    minimum: int = 2
) -> bool:
    """
    Check if a list of points meets the minimum count requirement.

    Args:
        points: List of (x, y) coordinate tuples
        minimum: Minimum number of points required (default: 2)

    Returns:
        True if points list has at least minimum entries
    """
    return points is not None and len(points) >= minimum


def validate_point_list(
    points: Optional[List[Tuple[float, float]]],
    name: str = "points",
    minimum: int = 2
) -> ValidationResult:
    """
    Validate a list of coordinate points.

    Args:
        points: List of (x, y) coordinate tuples to validate
        name: Name of the points list for error messages
        minimum: Minimum number of points required

    Returns:
        ValidationResult with success or error details
    """
    result = ValidationResult.success()

    if points is None:
        result.add_error(f"{name} cannot be None")
        return result

    if len(points) < minimum:
        result.add_error(
            f"{name} must have at least {minimum} points, "
            f"got {len(points)}"
        )

    return result


def is_valid_id(value: Optional[str]) -> bool:
    """
    Check if a value is a valid non-empty ID string.

    Args:
        value: Value to check

    Returns:
        True if value is a non-empty string
    """
    return value is not None and isinstance(value, str) and len(value) > 0

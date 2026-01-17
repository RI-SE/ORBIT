"""
Unit tests for validation utilities.

Tests the ValidationResult class and validation helper functions.
"""

import pytest
from typing import List, Tuple

from orbit.utils.validators import (
    ValidationResult,
    has_minimum_points,
    validate_point_list,
    is_valid_id,
)


# ============================================================================
# Test ValidationResult Class
# ============================================================================

class TestValidationResult:
    """Test ValidationResult dataclass and its methods."""

    def test_success_creates_valid_result(self):
        """Test success() creates a valid result with no errors."""
        result = ValidationResult.success()
        assert result.is_valid is True
        assert result.errors == []

    def test_failure_creates_invalid_result(self):
        """Test failure() creates an invalid result with errors."""
        errors = ["Error 1", "Error 2"]
        result = ValidationResult.failure(errors)
        assert result.is_valid is False
        assert result.errors == errors

    def test_failure_with_single_error(self):
        """Test failure() with single error."""
        result = ValidationResult.failure(["Something went wrong"])
        assert result.is_valid is False
        assert len(result.errors) == 1
        assert result.errors[0] == "Something went wrong"

    def test_failure_with_empty_errors(self):
        """Test failure() with empty error list."""
        result = ValidationResult.failure([])
        assert result.is_valid is False
        assert result.errors == []

    def test_add_error_marks_invalid(self):
        """Test add_error() marks result as invalid."""
        result = ValidationResult.success()
        assert result.is_valid is True

        result.add_error("New error")

        assert result.is_valid is False
        assert "New error" in result.errors

    def test_add_error_appends_to_existing(self):
        """Test add_error() appends to existing errors."""
        result = ValidationResult.failure(["Error 1"])
        result.add_error("Error 2")

        assert len(result.errors) == 2
        assert "Error 1" in result.errors
        assert "Error 2" in result.errors

    def test_add_multiple_errors(self):
        """Test adding multiple errors sequentially."""
        result = ValidationResult.success()
        result.add_error("First error")
        result.add_error("Second error")
        result.add_error("Third error")

        assert result.is_valid is False
        assert len(result.errors) == 3

    def test_merge_with_valid_result(self):
        """Test merge() with another valid result."""
        result1 = ValidationResult.success()
        result2 = ValidationResult.success()

        result1.merge(result2)

        assert result1.is_valid is True
        assert result1.errors == []

    def test_merge_with_invalid_result(self):
        """Test merge() with an invalid result."""
        result1 = ValidationResult.success()
        result2 = ValidationResult.failure(["Error from result2"])

        result1.merge(result2)

        assert result1.is_valid is False
        assert "Error from result2" in result1.errors

    def test_merge_combines_errors(self):
        """Test merge() combines errors from both results."""
        result1 = ValidationResult.failure(["Error 1"])
        result2 = ValidationResult.failure(["Error 2", "Error 3"])

        result1.merge(result2)

        assert result1.is_valid is False
        assert len(result1.errors) == 3
        assert "Error 1" in result1.errors
        assert "Error 2" in result1.errors
        assert "Error 3" in result1.errors

    def test_merge_invalid_into_invalid(self):
        """Test merge() of two invalid results."""
        result1 = ValidationResult.failure(["A"])
        result2 = ValidationResult.failure(["B"])

        result1.merge(result2)

        assert result1.is_valid is False
        assert result1.errors == ["A", "B"]

    def test_merge_valid_into_invalid(self):
        """Test merge() valid into invalid keeps invalid."""
        result1 = ValidationResult.failure(["Original error"])
        result2 = ValidationResult.success()

        result1.merge(result2)

        assert result1.is_valid is False
        assert result1.errors == ["Original error"]

    def test_direct_construction_valid(self):
        """Test direct construction of valid result."""
        result = ValidationResult(is_valid=True, errors=[])
        assert result.is_valid is True
        assert result.errors == []

    def test_direct_construction_invalid(self):
        """Test direct construction of invalid result."""
        result = ValidationResult(is_valid=False, errors=["Custom error"])
        assert result.is_valid is False
        assert result.errors == ["Custom error"]


# ============================================================================
# Test has_minimum_points Function
# ============================================================================

class TestHasMinimumPoints:
    """Test has_minimum_points validation function."""

    def test_sufficient_points_default_minimum(self):
        """Test with sufficient points for default minimum (2)."""
        points = [(0, 0), (1, 1)]
        assert has_minimum_points(points) is True

    def test_more_than_minimum(self):
        """Test with more points than minimum."""
        points = [(0, 0), (1, 1), (2, 2), (3, 3)]
        assert has_minimum_points(points, minimum=2) is True

    def test_exactly_minimum(self):
        """Test with exactly minimum points."""
        points = [(0, 0), (1, 1), (2, 2)]
        assert has_minimum_points(points, minimum=3) is True

    def test_below_minimum(self):
        """Test with fewer points than minimum."""
        points = [(0, 0)]
        assert has_minimum_points(points, minimum=2) is False

    def test_empty_list(self):
        """Test with empty points list."""
        assert has_minimum_points([], minimum=1) is False
        assert has_minimum_points([], minimum=2) is False

    def test_none_points(self):
        """Test with None points."""
        assert has_minimum_points(None) is False
        assert has_minimum_points(None, minimum=1) is False

    def test_custom_minimum(self):
        """Test with custom minimum requirement."""
        points = [(0, 0), (1, 1), (2, 2), (3, 3), (4, 4)]
        assert has_minimum_points(points, minimum=5) is True
        assert has_minimum_points(points, minimum=6) is False

    def test_minimum_zero(self):
        """Test with minimum of 0."""
        assert has_minimum_points([], minimum=0) is True
        assert has_minimum_points([(0, 0)], minimum=0) is True

    def test_minimum_one(self):
        """Test with minimum of 1."""
        assert has_minimum_points([(0, 0)], minimum=1) is True
        assert has_minimum_points([], minimum=1) is False


# ============================================================================
# Test validate_point_list Function
# ============================================================================

class TestValidatePointList:
    """Test validate_point_list validation function."""

    def test_valid_point_list(self):
        """Test validation of valid point list."""
        points = [(0, 0), (1, 1), (2, 2)]
        result = validate_point_list(points)
        assert result.is_valid is True
        assert result.errors == []

    def test_none_points(self):
        """Test validation of None points."""
        result = validate_point_list(None)
        assert result.is_valid is False
        assert len(result.errors) == 1
        assert "cannot be None" in result.errors[0]

    def test_none_points_custom_name(self):
        """Test validation of None with custom name."""
        result = validate_point_list(None, name="centerline")
        assert result.is_valid is False
        assert "centerline cannot be None" in result.errors[0]

    def test_insufficient_points(self):
        """Test validation with insufficient points."""
        points = [(0, 0)]  # Only 1 point, need 2
        result = validate_point_list(points)
        assert result.is_valid is False
        assert "at least 2 points" in result.errors[0]

    def test_insufficient_points_custom_minimum(self):
        """Test validation with custom minimum."""
        points = [(0, 0), (1, 1)]  # 2 points, need 3
        result = validate_point_list(points, minimum=3)
        assert result.is_valid is False
        assert "at least 3 points" in result.errors[0]
        assert "got 2" in result.errors[0]

    def test_empty_list(self):
        """Test validation of empty list."""
        result = validate_point_list([])
        assert result.is_valid is False
        assert "at least 2 points" in result.errors[0]
        assert "got 0" in result.errors[0]

    def test_exactly_minimum_points(self):
        """Test validation with exactly minimum points."""
        points = [(0, 0), (1, 1)]
        result = validate_point_list(points, minimum=2)
        assert result.is_valid is True

    def test_custom_name_in_error(self):
        """Test that custom name appears in error message."""
        result = validate_point_list([(0, 0)], name="boundary_points", minimum=3)
        assert result.is_valid is False
        assert "boundary_points" in result.errors[0]

    def test_default_name(self):
        """Test default name 'points' in error message."""
        result = validate_point_list([])
        assert "points" in result.errors[0]


# ============================================================================
# Test is_valid_id Function
# ============================================================================

class TestIsValidId:
    """Test is_valid_id validation function."""

    def test_valid_id(self):
        """Test with valid ID string."""
        assert is_valid_id("abc123") is True

    def test_valid_uuid_style_id(self):
        """Test with UUID-style ID."""
        assert is_valid_id("550e8400-e29b-41d4-a716-446655440000") is True

    def test_valid_single_char_id(self):
        """Test with single character ID."""
        assert is_valid_id("a") is True

    def test_none_id(self):
        """Test with None ID."""
        assert is_valid_id(None) is False

    def test_empty_string_id(self):
        """Test with empty string ID."""
        assert is_valid_id("") is False

    def test_integer_id(self):
        """Test with integer (wrong type)."""
        assert is_valid_id(123) is False

    def test_float_id(self):
        """Test with float (wrong type)."""
        assert is_valid_id(1.5) is False

    def test_list_id(self):
        """Test with list (wrong type)."""
        assert is_valid_id(["id"]) is False

    def test_whitespace_only_id(self):
        """Test with whitespace-only string (considered valid by current implementation)."""
        # Note: Current implementation only checks for non-empty string
        # Whitespace-only strings are technically valid by this check
        assert is_valid_id("   ") is True

    def test_id_with_spaces(self):
        """Test ID containing spaces."""
        assert is_valid_id("road 1") is True

    def test_id_with_special_chars(self):
        """Test ID with special characters."""
        assert is_valid_id("road_1-test.v2") is True


# ============================================================================
# Test Integration Scenarios
# ============================================================================

class TestValidationIntegration:
    """Test validation utilities in realistic scenarios."""

    def test_validate_road_geometry(self):
        """Test validating road geometry with multiple checks."""
        centerline = [(0, 0), (10, 0), (20, 0)]
        left_boundary = [(0, 2), (10, 2), (20, 2)]
        right_boundary = [(0, -2)]  # Invalid - too few points

        result = ValidationResult.success()
        result.merge(validate_point_list(centerline, name="centerline"))
        result.merge(validate_point_list(left_boundary, name="left_boundary"))
        result.merge(validate_point_list(right_boundary, name="right_boundary"))

        assert result.is_valid is False
        assert len(result.errors) == 1
        assert "right_boundary" in result.errors[0]

    def test_validate_multiple_issues(self):
        """Test collecting multiple validation errors."""
        result = ValidationResult.success()
        result.merge(validate_point_list(None, name="centerline"))
        result.merge(validate_point_list([], name="boundary"))
        result.merge(validate_point_list([(0, 0)], name="reference", minimum=2))

        assert result.is_valid is False
        assert len(result.errors) == 3

    def test_all_valid_scenario(self):
        """Test scenario where all validations pass."""
        points1 = [(0, 0), (1, 1)]
        points2 = [(2, 2), (3, 3), (4, 4)]

        result = ValidationResult.success()
        result.merge(validate_point_list(points1, name="line1"))
        result.merge(validate_point_list(points2, name="line2", minimum=3))

        assert result.is_valid is True
        assert result.errors == []

    def test_conditional_validation(self):
        """Test conditional validation based on has_minimum_points."""
        points = [(0, 0), (1, 1)]
        result = ValidationResult.success()

        if not has_minimum_points(points, minimum=3):
            result.add_error("Need at least 3 points for this operation")

        assert result.is_valid is False
        assert "Need at least 3 points" in result.errors[0]

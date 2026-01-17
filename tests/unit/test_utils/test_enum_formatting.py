"""
Unit tests for enum formatting utilities.

Tests the format_snake_case and format_enum_name functions.
"""

import pytest
from enum import Enum, auto

from orbit.utils.enum_formatting import (
    format_snake_case,
    format_enum_name,
)


# ============================================================================
# Test Enums for Testing
# ============================================================================

class SnakeCaseEnum(Enum):
    """Test enum with snake_case values."""
    LANE_BOUNDARY = "lane_boundary"
    ROAD_CENTERLINE = "road_centerline"
    TRAFFIC_SIGNAL = "traffic_signal"
    SINGLE_WORD = "single"
    MULTI_WORD_VALUE = "multi_word_value"


class CamelCaseEnum(Enum):
    """Test enum with camelCase values."""
    LOW_SPEED = "lowSpeed"
    HIGH_SPEED = "highSpeed"
    MEDIUM_FLOW = "mediumFlow"
    SINGLE = "single"
    MY_VARIABLE_NAME = "myVariableName"


class LowerCaseEnum(Enum):
    """Test enum with lowercase values."""
    SOLID = "solid"
    BROKEN = "broken"
    NONE = "none"


class MixedCaseEnum(Enum):
    """Test enum with various naming conventions."""
    SNAKE = "snake_case_value"
    CAMEL = "camelCaseValue"
    LOWER = "lowercase"
    UPPER = "UPPERCASE"


# ============================================================================
# Test format_snake_case Function
# ============================================================================

class TestFormatSnakeCase:
    """Test format_snake_case function."""

    def test_single_underscore(self):
        """Test converting single underscore."""
        assert format_snake_case("lane_boundary") == "Lane Boundary"

    def test_multiple_underscores(self):
        """Test converting multiple underscores."""
        assert format_snake_case("multi_word_value_here") == "Multi Word Value Here"

    def test_single_word(self):
        """Test single word (no underscores)."""
        assert format_snake_case("solid") == "Solid"

    def test_empty_string(self):
        """Test empty string."""
        assert format_snake_case("") == ""

    def test_already_title_case(self):
        """Test string that's already capitalized."""
        assert format_snake_case("Already_Title") == "Already Title"

    def test_uppercase_words(self):
        """Test all uppercase words."""
        assert format_snake_case("ALL_CAPS") == "All Caps"

    def test_leading_underscore(self):
        """Test leading underscore."""
        assert format_snake_case("_private_var") == " Private Var"

    def test_trailing_underscore(self):
        """Test trailing underscore."""
        assert format_snake_case("value_") == "Value "

    def test_double_underscore(self):
        """Test double underscore."""
        assert format_snake_case("double__underscore") == "Double  Underscore"

    def test_numbers_in_string(self):
        """Test string with numbers."""
        assert format_snake_case("value_1_test") == "Value 1 Test"


# ============================================================================
# Test format_enum_name Function - Snake Case Values
# ============================================================================

class TestFormatEnumNameSnakeCase:
    """Test format_enum_name with snake_case enum values."""

    def test_lane_boundary(self):
        """Test formatting lane_boundary."""
        result = format_enum_name(SnakeCaseEnum.LANE_BOUNDARY)
        assert result == "Lane Boundary"

    def test_road_centerline(self):
        """Test formatting road_centerline."""
        result = format_enum_name(SnakeCaseEnum.ROAD_CENTERLINE)
        assert result == "Road Centerline"

    def test_traffic_signal(self):
        """Test formatting traffic_signal."""
        result = format_enum_name(SnakeCaseEnum.TRAFFIC_SIGNAL)
        assert result == "Traffic Signal"

    def test_single_word_snake(self):
        """Test single word snake_case value."""
        result = format_enum_name(SnakeCaseEnum.SINGLE_WORD)
        assert result == "Single"

    def test_multi_word(self):
        """Test multi-word snake_case value."""
        result = format_enum_name(SnakeCaseEnum.MULTI_WORD_VALUE)
        assert result == "Multi Word Value"


# ============================================================================
# Test format_enum_name Function - Camel Case Values
# ============================================================================

class TestFormatEnumNameCamelCase:
    """Test format_enum_name with camelCase enum values."""

    def test_low_speed(self):
        """Test formatting lowSpeed."""
        result = format_enum_name(CamelCaseEnum.LOW_SPEED)
        assert result == "Low Speed"

    def test_high_speed(self):
        """Test formatting highSpeed."""
        result = format_enum_name(CamelCaseEnum.HIGH_SPEED)
        assert result == "High Speed"

    def test_medium_flow(self):
        """Test formatting mediumFlow."""
        result = format_enum_name(CamelCaseEnum.MEDIUM_FLOW)
        assert result == "Medium Flow"

    def test_single_word_camel(self):
        """Test single word value (no case change needed)."""
        result = format_enum_name(CamelCaseEnum.SINGLE)
        assert result == "Single"

    def test_long_camel_case(self):
        """Test longer camelCase value."""
        result = format_enum_name(CamelCaseEnum.MY_VARIABLE_NAME)
        assert result == "My Variable Name"


# ============================================================================
# Test format_enum_name Function - Lowercase Values
# ============================================================================

class TestFormatEnumNameLowerCase:
    """Test format_enum_name with lowercase enum values."""

    def test_solid(self):
        """Test formatting solid."""
        result = format_enum_name(LowerCaseEnum.SOLID)
        assert result == "Solid"

    def test_broken(self):
        """Test formatting broken."""
        result = format_enum_name(LowerCaseEnum.BROKEN)
        assert result == "Broken"

    def test_none_value(self):
        """Test formatting none."""
        result = format_enum_name(LowerCaseEnum.NONE)
        assert result == "None"


# ============================================================================
# Test format_enum_name Function - Custom Map
# ============================================================================

class TestFormatEnumNameCustomMap:
    """Test format_enum_name with custom mapping."""

    def test_custom_map_override(self):
        """Test custom map overrides default formatting."""
        custom_map = {
            SnakeCaseEnum.LANE_BOUNDARY: "Custom Lane Name"
        }
        result = format_enum_name(SnakeCaseEnum.LANE_BOUNDARY, custom_map)
        assert result == "Custom Lane Name"

    def test_custom_map_partial(self):
        """Test custom map only overrides specified values."""
        custom_map = {
            SnakeCaseEnum.LANE_BOUNDARY: "Overridden"
        }
        # This one should still use default formatting
        result = format_enum_name(SnakeCaseEnum.ROAD_CENTERLINE, custom_map)
        assert result == "Road Centerline"

    def test_custom_map_empty(self):
        """Test empty custom map falls back to default."""
        result = format_enum_name(SnakeCaseEnum.LANE_BOUNDARY, {})
        assert result == "Lane Boundary"

    def test_custom_map_none(self):
        """Test None custom map uses default formatting."""
        result = format_enum_name(SnakeCaseEnum.LANE_BOUNDARY, None)
        assert result == "Lane Boundary"

    def test_custom_map_with_special_chars(self):
        """Test custom map with special characters in value."""
        custom_map = {
            LowerCaseEnum.SOLID: "Solid (continuous)"
        }
        result = format_enum_name(LowerCaseEnum.SOLID, custom_map)
        assert result == "Solid (continuous)"

    def test_custom_map_multiple_entries(self):
        """Test custom map with multiple entries."""
        custom_map = {
            CamelCaseEnum.LOW_SPEED: "Slow",
            CamelCaseEnum.HIGH_SPEED: "Fast",
        }
        assert format_enum_name(CamelCaseEnum.LOW_SPEED, custom_map) == "Slow"
        assert format_enum_name(CamelCaseEnum.HIGH_SPEED, custom_map) == "Fast"
        # Unmapped value uses default
        assert format_enum_name(CamelCaseEnum.MEDIUM_FLOW, custom_map) == "Medium Flow"


# ============================================================================
# Test format_enum_name Function - Edge Cases
# ============================================================================

class TestFormatEnumNameEdgeCases:
    """Test format_enum_name edge cases."""

    def test_uppercase_value(self):
        """Test all uppercase value."""
        result = format_enum_name(MixedCaseEnum.UPPER)
        # "UPPERCASE" -> title case -> "Uppercase"
        assert result == "Uppercase"

    def test_mixed_formats(self):
        """Test that different formats in same enum work correctly."""
        assert format_enum_name(MixedCaseEnum.SNAKE) == "Snake Case Value"
        assert format_enum_name(MixedCaseEnum.CAMEL) == "Camel Case Value"
        assert format_enum_name(MixedCaseEnum.LOWER) == "Lowercase"


# ============================================================================
# Test with Real ORBIT Enums (if available)
# ============================================================================

class TestWithOrbitEnums:
    """Test with actual ORBIT enum types."""

    def test_line_type_enum(self):
        """Test formatting LineType enum values."""
        from orbit.models.polyline import LineType

        # Test that we can format LineType values
        for line_type in LineType:
            result = format_enum_name(line_type)
            # Should produce non-empty string
            assert len(result) > 0
            # Should not contain underscores (converted to spaces)
            if '_' in line_type.value:
                assert '_' not in result

    def test_road_mark_type_enum(self):
        """Test formatting RoadMarkType enum values."""
        from orbit.models.polyline import RoadMarkType

        for mark_type in RoadMarkType:
            result = format_enum_name(mark_type)
            assert len(result) > 0
            # First character should be uppercase
            assert result[0].isupper()

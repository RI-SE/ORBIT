"""
Enum formatting utilities for ORBIT.

Provides generic formatting functions for displaying enum values in the GUI.
"""

import re
from enum import Enum
from typing import Dict, Optional


def format_snake_case(value: str) -> str:
    """
    Format a snake_case string for human-readable display.

    Args:
        value: Snake_case string to format

    Returns:
        Title Case string with spaces

    Example:
        >>> format_snake_case('lane_boundary')
        'Lane Boundary'
    """
    return value.replace('_', ' ').title()


def format_enum_name(enum_value: Enum, custom_map: Optional[Dict[Enum, str]] = None) -> str:
    """
    Format enum value for human-readable display.

    Converts enum values to display strings, either using a custom mapping
    or automatic conversion using smart formatting rules.

    Args:
        enum_value: The enum value to format
        custom_map: Optional dictionary mapping enum values to display names

    Returns:
        Human-readable string with proper capitalization

    Examples:
        >>> format_enum_name(LineType.LANE_BOUNDARY)
        'Lane Boundary'

        >>> format_enum_name(RoadType.LOW_SPEED)  # from "lowSpeed"
        'Low Speed'

        >>> format_enum_name(RoadMarkType.SOLID)  # from "solid"
        'Solid'
    """
    if custom_map and enum_value in custom_map:
        return custom_map[enum_value]

    # Get the string value
    value = enum_value.value

    # Handle different naming conventions:
    # 1. snake_case: "lane_boundary" -> "Lane Boundary"
    if '_' in value:
        return format_snake_case(value)

    # 2. All uppercase: "UPPERCASE" -> "Uppercase"
    # Check before camelCase handling to avoid "U P P E R C A S E"
    if value.isupper():
        return value.title()

    # 3. camelCase: "lowSpeed" -> "Low Speed"
    # Insert space before each capital letter (except first)
    spaced = re.sub(r'(?<!^)(?=[A-Z])', ' ', value)
    return spaced.title()

    # 4. lowercase with spaces: "solid solid" -> "Solid Solid"
    # (handled by .title() in camelCase case above)

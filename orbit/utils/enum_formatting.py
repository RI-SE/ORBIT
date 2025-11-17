"""
Enum formatting utilities for ORBIT.

Provides generic formatting functions for displaying enum values in the GUI.
"""

from enum import Enum
from typing import Dict, Optional


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
        return value.replace('_', ' ').title()

    # 2. camelCase: "lowSpeed" -> "Low Speed"
    # Insert space before capital letters and capitalize
    import re
    # Insert space before each capital letter (except first)
    spaced = re.sub(r'(?<!^)(?=[A-Z])', ' ', value)
    return spaced.title()

    # 3. lowercase with spaces: "solid solid" -> "Solid Solid"
    # (handled by .title() in camelCase case above)

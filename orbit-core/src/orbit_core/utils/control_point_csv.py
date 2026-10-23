"""Control points from survey CSV files (e.g. RTK exports): column detection and parsing.

Shared by ORBIT's CSV import dialog and tools/attach_altitudes.py.
"""

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class CSVControlPoint:
    """Intermediate representation of CSV control point."""
    row_number: int
    point_name: str
    latitude: float
    longitude: float
    altitude: Optional[float] = None
    sigma_h_m: Optional[float] = None  # surveyed horizontal standard deviation (m)
    sigma_v_m: Optional[float] = None  # surveyed vertical standard deviation (m)
    point_type: Optional[str] = None
    status: str = "pending"  # pending, placed, skipped, error
    pixel_x: Optional[float] = None
    pixel_y: Optional[float] = None
    error: Optional[str] = None
    selected: bool = True


# Column name aliases for flexible detection
LATITUDE_ALIASES = ['latitude', 'lat', 'y', 'northing', 'north']
LONGITUDE_ALIASES = ['longitude', 'lon', 'long', 'lng', 'x', 'easting', 'east']
NAME_ALIASES = ['point_name', 'name', 'id', 'point_id', 'marker', 'label']
ALTITUDE_ALIASES = ['altitude', 'alt', 'elevation', 'z', 'height']
# RTK survey exports use "horizontal SD"/"vertical SD"; SAVANT's marker CSVs also allow the short forms
SIGMA_H_ALIASES = ['horizontal sd', 'horiz sd', 'sigma_h', 'sigma_h_m', 'hsd']
SIGMA_V_ALIASES = ['vertical sd', 'vert sd', 'sigma_v', 'sigma_v_m', 'vsd']
POINT_TYPE_ALIASES = ['point_type', 'point type']


def find_column_index(headers: List[str], aliases: List[str]) -> Optional[int]:
    """
    Find column index by matching aliases (case-insensitive).

    Args:
        headers: List of column headers from CSV
        aliases: List of possible column name aliases

    Returns:
        Column index or None if not found
    """
    headers_lower = [h.lower().strip() for h in headers]
    for alias in aliases:
        if alias in headers_lower:
            return headers_lower.index(alias)
    return None


def detect_columns(headers: List[str]) -> dict:
    """
    Auto-detect column indices by name matching.

    Args:
        headers: List of column headers from CSV

    Returns:
        Dictionary with 'name', 'latitude', 'longitude', 'altitude' keys
    """
    return {
        'name': find_column_index(headers, NAME_ALIASES),
        'latitude': find_column_index(headers, LATITUDE_ALIASES),
        'longitude': find_column_index(headers, LONGITUDE_ALIASES),
        'altitude': find_column_index(headers, ALTITUDE_ALIASES),
        'sigma_h_m': find_column_index(headers, SIGMA_H_ALIASES),
        'sigma_v_m': find_column_index(headers, SIGMA_V_ALIASES),
        'point_type': find_column_index(headers, POINT_TYPE_ALIASES),
    }


def _optional_float(row: List[str], index: Optional[int]) -> Optional[float]:
    """Numeric cell or None when the column is absent, empty or not a number (e.g. "/" in survey exports)."""
    if index is None or index >= len(row):
        return None
    try:
        return float(row[index])
    except ValueError:
        return None


def parse_csv_file(filepath: Path) -> Tuple[List[CSVControlPoint], str]:
    """
    Parse CSV file and extract control points.

    Args:
        filepath: Path to CSV file

    Returns:
        Tuple of (list of CSVControlPoint, error message or empty string)
    """
    points = []

    try:
        # Try different encodings
        encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']
        content = None

        for encoding in encodings:
            try:
                with open(filepath, 'r', encoding=encoding) as f:
                    content = f.read()
                break
            except UnicodeDecodeError:
                continue

        if content is None:
            return [], "Failed to decode CSV file with any supported encoding"

        # Parse CSV
        lines = content.strip().split('\n')
        if len(lines) < 2:
            return [], "CSV file is empty or has no data rows"

        reader = csv.reader(lines)
        headers = next(reader)

        # Detect columns
        columns = detect_columns(headers)

        if columns['latitude'] is None or columns['longitude'] is None:
            return [], (
                "Could not detect latitude and longitude columns.\n\n"
                f"Available columns: {', '.join(headers)}\n\n"
                "Expected column names like: latitude, longitude, lat, lon"
            )

        # Parse data rows
        for i, row in enumerate(reader, start=1):
            if not row or len(row) < max(columns['latitude'], columns['longitude']) + 1:
                continue  # Skip empty or incomplete rows

            try:
                # Extract data
                point_name = row[columns['name']] if columns['name'] is not None else f"Point_{i}"
                latitude = float(row[columns['latitude']])
                longitude = float(row[columns['longitude']])
                altitude = _optional_float(row, columns['altitude'])  # "/" or empty: unknown

                # Validate ranges
                if not (-90 <= latitude <= 90):
                    points.append(CSVControlPoint(
                        row_number=i,
                        point_name=point_name,
                        latitude=0,
                        longitude=0,
                        status="error",
                        error=f"Invalid latitude: {latitude} (must be -90 to 90)",
                        selected=False
                    ))
                    continue

                if not (-180 <= longitude <= 180):
                    points.append(CSVControlPoint(
                        row_number=i,
                        point_name=point_name,
                        latitude=0,
                        longitude=0,
                        status="error",
                        error=f"Invalid longitude: {longitude} (must be -180 to 180)",
                        selected=False
                    ))
                    continue

                # Create control point
                points.append(CSVControlPoint(
                    row_number=i,
                    point_name=point_name,
                    latitude=latitude,
                    longitude=longitude,
                    altitude=altitude,
                    sigma_h_m=_optional_float(row, columns['sigma_h_m']),
                    sigma_v_m=_optional_float(row, columns['sigma_v_m']),
                    point_type=(row[columns['point_type']].strip() or None
                                if columns['point_type'] is not None and columns['point_type'] < len(row) else None),
                    selected=True
                ))

            except (ValueError, IndexError) as e:
                # Invalid numeric value or missing column
                point_name = (
                    row[columns['name']]
                    if columns['name'] is not None
                    and len(row) > columns['name']
                    else f"Point_{i}"
                )
                points.append(CSVControlPoint(
                    row_number=i,
                    point_name=point_name,
                    latitude=0,
                    longitude=0,
                    status="error",
                    error=f"Parse error: {str(e)}",
                    selected=False
                ))

        if not points:
            return [], "No valid data rows found in CSV"

        return points, ""

    except Exception as e:
        return [], f"Error reading CSV file: {type(e).__name__}: {str(e)}"


# Survey fields copied onto existing control points (names as in the .orbit file)
SURVEY_FIELDS = ("altitude", "sigma_h_m", "sigma_v_m", "point_type")
# A name match farther apart than this is treated as a different point (wrong CSV, or a reused name)
MAX_MATCH_DISTANCE_M = 1.0
_EARTH_RADIUS_M = 6371000.0


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    return _EARTH_RADIUS_M * math.hypot(dlat, dlon)


def attach_survey_data(control_points: List[Dict[str, Any]], survey: List[CSVControlPoint],
                       overwrite: bool = False,
                       max_distance_m: float = MAX_MATCH_DISTANCE_M) -> Dict[str, List[str]]:
    """Copy altitude, SDs and point type from survey points onto control points (dicts as in a .orbit file).

    Points are matched by name (case-insensitive, surrounding spaces ignored); a match farther apart than
    max_distance_m is rejected. Fields already set are kept unless overwrite. Modifies control_points in place.
    Returns {"updated", "unchanged", "unmatched", "too_far", "duplicate"} lists of point names.
    """
    by_name: Dict[str, CSVControlPoint] = {}
    duplicate = set()
    for point in survey:
        if point.status == "error":
            continue
        key = point.point_name.strip().lower()
        if key in by_name:
            duplicate.add(key)
        by_name[key] = point
    report: Dict[str, List[str]] = {"updated": [], "unchanged": [], "unmatched": [], "too_far": [], "duplicate": []}
    for cp in control_points:
        name = str(cp.get("name") or "").strip()
        point = by_name.get(name.lower())
        if point is None:
            report["unmatched"].append(name)
            continue
        if name.lower() in duplicate:
            report["duplicate"].append(name)
            continue
        if _distance_m(cp["latitude"], cp["longitude"], point.latitude, point.longitude) > max_distance_m:
            report["too_far"].append(name)
            continue
        changed = False
        for field in SURVEY_FIELDS:
            value = getattr(point, field)
            if value is not None and (overwrite or cp.get(field) is None) and cp.get(field) != value:
                cp[field] = value
                changed = True
        report["updated" if changed else "unchanged"].append(name)
    return report

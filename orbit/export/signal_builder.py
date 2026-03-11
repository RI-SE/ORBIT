"""
Signal XML builder for OpenDRIVE export.

Handles creation of signal-related XML elements.
"""

import math
from typing import TYPE_CHECKING, List, Optional

from lxml import etree

from orbit.models import Road, Signal
from orbit.models.sign_library_manager import SignLibraryManager
from orbit.models.signal import SignalType, SpeedUnit

if TYPE_CHECKING:
    from orbit.utils.coordinate_transform import CoordinateTransformer


def _project_point_onto_polyline(px: float, py: float, pts: List[tuple]):
    """
    Project (px, py) onto a polyline, returning (s, t) in the same coordinate
    system as the polyline points.

    s is the arc-length distance along the polyline to the closest foot point.
    t is the signed lateral offset (positive = left of travel direction).
    """
    min_dist = float('inf')
    best_s = 0.0
    best_t = 0.0
    cumulative_s = 0.0

    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        dx, dy = x2 - x1, y2 - y1
        seg_len = math.sqrt(dx * dx + dy * dy)
        if seg_len < 1e-9:
            continue
        t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (seg_len * seg_len)))
        cx = x1 + t * dx
        cy = y1 + t * dy
        dist = math.sqrt((px - cx) ** 2 + (py - cy) ** 2)
        if dist < min_dist:
            min_dist = dist
            best_s = cumulative_s + t * seg_len
            cross = (px - x1) * dy - (py - y1) * dx
            best_t = (1.0 if cross >= 0 else -1.0) * dist
        cumulative_s += seg_len

    return best_s, best_t


class SignalBuilder:
    """Builds signal XML elements for OpenDRIVE export."""

    def __init__(self, scale_x: float = 1.0, country_code: str = "se",
                 use_german_codes: bool = False,
                 transformer: Optional['CoordinateTransformer'] = None):
        """
        Initialize signal builder.

        Args:
            scale_x: Fallback scale factor in meters per pixel (x-direction)
            country_code: Two-letter ISO 3166-1 country code
            use_german_codes: If True, use German VzKat codes (opendrive_de) when available
            transformer: Coordinate transformer used for accurate pixel→metric conversion.
                When provided together with centerline_points_meters in create_signals,
                signal s/t positions are computed in metric space instead of using the
                uniform scale_x approximation.
        """
        self.scale_x = scale_x
        self.country_code = country_code.upper()  # Schema requires uppercase [A-Z]{2}
        self.use_german_codes = use_german_codes
        self.transformer = transformer

    def create_signals_for_connecting_road(
        self,
        connecting_road,
        signals: List[Signal],
        path_pixel: List[tuple],
        path_meters: Optional[List[tuple]] = None,
    ) -> Optional[etree.Element]:
        """
        Create signals element for a connecting road.

        Args:
            connecting_road: ConnectingRoad object
            signals: All signals in the project
            path_pixel: Connecting road path in pixel coordinates
            path_meters: Connecting road path in metric coordinates

        Returns:
            signals XML element or None if no signals assigned to this connecting road
        """
        road_signals = [s for s in signals if s.road_id == connecting_road.id]
        if not road_signals:
            return None

        signals_elem = etree.Element('signals')
        for signal in road_signals:
            signal_elem = self._create_signal(signal, path_pixel, path_meters)
            if signal_elem is not None:
                signals_elem.append(signal_elem)

        return signals_elem if len(signals_elem) > 0 else None

    def create_signals(
        self,
        road: Road,
        signals: List[Signal],
        centerline_points_pixel: List[tuple],
        centerline_points_meters: Optional[List[tuple]] = None,
    ) -> Optional[etree.Element]:
        """
        Create signals element for a road.

        Args:
            road: Road object
            signals: All signals in the project
            centerline_points_pixel: List of centerline points in pixel coordinates
            centerline_points_meters: Centerline points in metric coordinates (metres).
                When provided together with a transformer, signal positions are projected
                in metric space for accurate s/t values independent of road orientation.

        Returns:
            signals XML element or None if no signals for this road
        """
        # Find all signals assigned to this road
        road_signals = [s for s in signals if s.road_id == road.id]

        if not road_signals:
            return None

        signals_elem = etree.Element('signals')

        for signal in road_signals:
            signal_elem = self._create_signal(signal, centerline_points_pixel, centerline_points_meters)
            if signal_elem is not None:
                signals_elem.append(signal_elem)

        return signals_elem if len(signals_elem) > 0 else None

    def _create_signal(
        self,
        signal: Signal,
        centerline_points_pixel: List[tuple],
        centerline_points_meters: Optional[List[tuple]] = None,
    ) -> Optional[etree.Element]:
        """Create a single signal element."""
        # Prefer metric-space projection when the transformer and metric centerline are
        # available.  The pixel-space fallback (s_px × scale_x) is inaccurate when
        # the road runs at an angle or the homography scale varies across the image.
        if self.transformer is not None and centerline_points_meters is not None:
            try:
                sig_mx, sig_my = self.transformer.pixel_to_meters(
                    signal.position[0], signal.position[1]
                )
                s_meters, t_meters = _project_point_onto_polyline(
                    sig_mx, sig_my, centerline_points_meters
                )
            except Exception:
                # Fall back to pixel method if transformer fails
                s_position = signal.calculate_s_position(centerline_points_pixel)
                if s_position is None:
                    return None
                s_meters = s_position * self.scale_x
                t_meters = self._calculate_t_offset(signal.position, centerline_points_pixel, s_position)
        else:
            s_position = signal.calculate_s_position(centerline_points_pixel)
            if s_position is None:
                return None
            s_meters = s_position * self.scale_x
            t_meters = self._calculate_t_offset(signal.position, centerline_points_pixel, s_position)

        # Create signal element
        signal_elem = etree.Element('signal')
        signal_elem.set('id', signal.id)
        signal_elem.set('s', f'{s_meters:.6f}')
        signal_elem.set('t', f'{t_meters:.6f}')
        signal_elem.set('name', signal.name if signal.name else signal.get_display_name())
        signal_elem.set('dynamic', signal.dynamic if signal.dynamic else 'no')

        # OpenDRIVE orientation: '+' (forward), '-' (backward), or 'none' (both)
        signal_elem.set('orientation', signal.orientation)

        # hOffset: heading offset in radians relative to perpendicular direction
        signal_elem.set('hOffset', f'{signal.h_offset:.6f}')

        # Z offset (height above ground)
        signal_elem.set('zOffset', f'{signal.z_offset:.2f}')

        # Physical dimensions of the sign
        signal_elem.set('height', f'{signal.sign_height:.2f}')
        signal_elem.set('width', f'{signal.sign_width:.2f}')

        # Country code: prefer signal's stored country, fallback to builder's default
        country = signal.country if signal.country else self.country_code
        signal_elem.set('country', country)

        # Map signal type to OpenDRIVE type/subtype
        self._set_signal_type_attributes(signal_elem, signal)

        # Lane validity (which lanes this signal applies to)
        if signal.validity_lanes is not None and len(signal.validity_lanes) > 0:
            # Export each lane range as a validity element
            # OpenDRIVE validity uses fromLane/toLane (inclusive range)
            # Sort lanes and group into contiguous ranges
            sorted_lanes = sorted(signal.validity_lanes)
            ranges = []
            range_start = sorted_lanes[0]
            range_end = sorted_lanes[0]

            for lane_id in sorted_lanes[1:]:
                if lane_id == range_end + 1:
                    range_end = lane_id
                else:
                    ranges.append((range_start, range_end))
                    range_start = lane_id
                    range_end = lane_id
            ranges.append((range_start, range_end))

            for from_lane, to_lane in ranges:
                validity = etree.SubElement(signal_elem, 'validity')
                validity.set('fromLane', str(from_lane))
                validity.set('toLane', str(to_lane))

        return signal_elem

    def _set_signal_type_attributes(self, signal_elem: etree.Element, signal: Signal) -> None:
        """Set type and subtype attributes based on signal type.

        For LIBRARY_SIGN, looks up type/subtype from the sign library.
        If use_german_codes is True and opendrive_de codes exist, uses those instead.
        For CUSTOM, uses the custom type/subtype codes.
        For legacy types, derives type/subtype from ORBIT signal type.
        If signal has stored subtype from import, use that for round-trip.
        """
        # If signal has stored subtype from OpenDRIVE import, prefer that for round-trip
        stored_subtype = signal.subtype if signal.subtype else None

        # Handle library-based signs
        if signal.type == SignalType.LIBRARY_SIGN:
            if signal.library_id and signal.sign_id:
                manager = SignLibraryManager.instance()
                sign_def = manager.get_sign_definition(signal.library_id, signal.sign_id)
                if sign_def:
                    # Check if we should use German codes
                    if self.use_german_codes and sign_def.opendrive_de_type:
                        signal_elem.set('type', sign_def.opendrive_de_type)
                        signal_elem.set('subtype', stored_subtype or sign_def.opendrive_de_subtype or '-1')
                        signal_elem.set('country', 'DE')
                    else:
                        signal_elem.set('type', sign_def.opendrive_type)
                        signal_elem.set('subtype', stored_subtype or sign_def.opendrive_subtype)
                    return
            # Fallback if library/sign not found
            signal_elem.set('type', '-1')
            signal_elem.set('subtype', stored_subtype or '-1')
            return

        # Handle custom OpenDRIVE codes
        if signal.type == SignalType.CUSTOM:
            signal_elem.set('type', signal.custom_type or '-1')
            signal_elem.set('subtype', stored_subtype or signal.custom_subtype or '-1')
            return

        # Legacy types - using German sign codes (DE:) as OpenDRIVE standard
        if signal.type == SignalType.STOP:
            signal_elem.set('type', '205')
            signal_elem.set('subtype', stored_subtype or '-1')
        elif signal.type == SignalType.GIVE_WAY:
            signal_elem.set('type', '206')
            signal_elem.set('subtype', stored_subtype or '-1')
        elif signal.type == SignalType.NO_ENTRY:
            signal_elem.set('type', '267')
            signal_elem.set('subtype', stored_subtype or '-1')
        elif signal.type == SignalType.PRIORITY_ROAD:
            signal_elem.set('type', '301')
            signal_elem.set('subtype', stored_subtype or '-1')
        elif signal.type == SignalType.SPEED_LIMIT:
            signal_elem.set('type', '274')
            if stored_subtype:
                signal_elem.set('subtype', stored_subtype)
            else:
                speed_value = signal.value
                if signal.speed_unit == SpeedUnit.MPH:
                    # Convert mph to km/h for OpenDRIVE
                    speed_value = int(signal.value * 1.60934)
                signal_elem.set('subtype', str(speed_value) if speed_value else '-1')
        elif signal.type == SignalType.END_OF_SPEED_LIMIT:
            signal_elem.set('type', '278')
            signal_elem.set('subtype', stored_subtype or '-1')
        elif signal.type == SignalType.TRAFFIC_SIGNALS:
            signal_elem.set('type', '1000001')
            signal_elem.set('subtype', stored_subtype or '-1')
        else:
            # Generic/unknown sign
            signal_elem.set('type', '-1')
            signal_elem.set('subtype', stored_subtype or '-1')

    def _calculate_t_offset(
        self,
        signal_position: tuple,
        centerline_points: List[tuple],
        s_position: float
    ) -> float:
        """
        Calculate lateral offset (t-coordinate) of signal from road centerline.

        Args:
            signal_position: (x, y) position of signal in pixels
            centerline_points: List of centerline points in pixels
            s_position: s-coordinate along centerline in pixels

        Returns:
            t-offset in meters (positive = left, negative = right)
        """
        cumulative_s = 0.0
        px, py = signal_position

        for i in range(len(centerline_points) - 1):
            x1, y1 = centerline_points[i]
            x2, y2 = centerline_points[i + 1]

            segment_length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
            next_s = cumulative_s + segment_length

            if next_s >= s_position:
                # This is the segment containing s_position
                if segment_length == 0:
                    ref_x, ref_y = x1, y1
                else:
                    t = (s_position - cumulative_s) / segment_length
                    ref_x = x1 + t * (x2 - x1)
                    ref_y = y1 + t * (y2 - y1)

                # Calculate distance from signal to reference point
                distance_px = ((px - ref_x) ** 2 + (py - ref_y) ** 2) ** 0.5

                # Determine sign using cross product
                dx, dy = x2 - x1, y2 - y1
                cross = (px - x1) * dy - (py - y1) * dx
                sign = 1.0 if cross >= 0 else -1.0

                # Convert to meters
                distance_m = distance_px * self.scale_x
                return sign * distance_m

            cumulative_s = next_s

        # Fallback: use distance to last point
        x, y = centerline_points[-1]
        distance_px = ((px - x) ** 2 + (py - y) ** 2) ** 0.5
        distance_m = distance_px * self.scale_x
        return distance_m

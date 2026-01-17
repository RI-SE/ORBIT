"""Tests for orbit.export.signal_builder module."""

import math
import pytest
from unittest.mock import Mock, patch
from lxml import etree

from orbit.export.signal_builder import SignalBuilder
from orbit.models.signal import Signal, SignalType, SpeedUnit


class TestSignalBuilderInit:
    """Tests for SignalBuilder initialization."""

    def test_default_init(self):
        """Default initialization."""
        builder = SignalBuilder()
        assert builder.scale_x == 1.0
        assert builder.country_code == "SE"
        assert builder.use_german_codes is False

    def test_custom_scale(self):
        """Custom scale factor."""
        builder = SignalBuilder(scale_x=0.5)
        assert builder.scale_x == 0.5

    def test_custom_country_code(self):
        """Custom country code is uppercased."""
        builder = SignalBuilder(country_code="de")
        assert builder.country_code == "DE"

    def test_use_german_codes(self):
        """German codes flag."""
        builder = SignalBuilder(use_german_codes=True)
        assert builder.use_german_codes is True


class TestCreateSignals:
    """Tests for create_signals method."""

    @pytest.fixture
    def builder(self):
        """Create signal builder."""
        return SignalBuilder(scale_x=0.1)

    @pytest.fixture
    def mock_road(self):
        """Create mock road."""
        road = Mock()
        road.id = "road1"
        return road

    @pytest.fixture
    def centerline_points(self):
        """Simple horizontal centerline."""
        return [(0, 100), (100, 100), (200, 100)]

    def test_no_signals_for_road(self, builder, mock_road, centerline_points):
        """Returns None when no signals assigned to road."""
        signals = []
        result = builder.create_signals(mock_road, signals, centerline_points)
        assert result is None

    def test_signals_not_assigned_to_road(self, builder, mock_road, centerline_points):
        """Returns None when signals assigned to different road."""
        signal = Signal(signal_type=SignalType.STOP, position=(50, 100))
        signal.road_id = "other_road"
        signals = [signal]

        result = builder.create_signals(mock_road, signals, centerline_points)
        assert result is None

    def test_creates_signals_element(self, builder, mock_road, centerline_points):
        """Creates signals element with signal children."""
        signal = Signal(signal_type=SignalType.STOP, position=(50, 100))
        signal.road_id = "road1"
        signals = [signal]

        result = builder.create_signals(mock_road, signals, centerline_points)

        assert result is not None
        assert result.tag == 'signals'
        assert len(result) >= 1
        assert result[0].tag == 'signal'

    def test_multiple_signals(self, builder, mock_road, centerline_points):
        """Creates multiple signal elements."""
        signal1 = Signal(signal_type=SignalType.STOP, position=(50, 100))
        signal1.road_id = "road1"
        signal2 = Signal(signal_type=SignalType.GIVE_WAY, position=(150, 100))
        signal2.road_id = "road1"
        signals = [signal1, signal2]

        result = builder.create_signals(mock_road, signals, centerline_points)

        assert len(result) == 2


class TestCreateSignal:
    """Tests for _create_signal method."""

    @pytest.fixture
    def builder(self):
        """Create signal builder with scale factor."""
        return SignalBuilder(scale_x=0.1, country_code="SE")

    @pytest.fixture
    def centerline_points(self):
        """Horizontal centerline 200 pixels long."""
        return [(0, 100), (200, 100)]

    def test_signal_at_start(self, builder, centerline_points):
        """Signal at start of road."""
        signal = Signal(signal_type=SignalType.STOP, position=(0, 100))

        result = builder._create_signal(signal, centerline_points)

        assert result is not None
        assert result.get('s') == '0.000000'

    def test_signal_at_middle(self, builder, centerline_points):
        """Signal in middle of road."""
        signal = Signal(signal_type=SignalType.STOP, position=(100, 100))

        result = builder._create_signal(signal, centerline_points)

        assert result is not None
        # 100 pixels * 0.1 scale = 10 meters
        assert result.get('s') == '10.000000'

    def test_signal_attributes_set(self, builder, centerline_points):
        """All required attributes are set."""
        signal = Signal(signal_type=SignalType.STOP, position=(50, 100))
        signal.name = "Stop Sign"
        signal.orientation = "+"
        signal.h_offset = 0.0
        signal.z_offset = 2.0
        signal.sign_height = 0.6
        signal.sign_width = 0.6

        result = builder._create_signal(signal, centerline_points)

        assert result.get('id') is not None
        assert result.get('name') == 'Stop Sign'
        assert result.get('orientation') == '+'
        assert result.get('zOffset') == '2.00'
        assert result.get('height') == '0.60'
        assert result.get('width') == '0.60'
        assert result.get('country') == 'SE'

    def test_signal_uses_custom_country(self, builder, centerline_points):
        """Signal uses its own country code if set."""
        signal = Signal(signal_type=SignalType.STOP, position=(50, 100))
        signal.country = "NO"

        result = builder._create_signal(signal, centerline_points)

        assert result.get('country') == 'NO'


class TestSetSignalTypeAttributes:
    """Tests for _set_signal_type_attributes method."""

    @pytest.fixture
    def builder(self):
        """Create signal builder."""
        return SignalBuilder()

    def test_stop_sign(self, builder):
        """Stop sign type mapping."""
        elem = etree.Element('signal')
        signal = Signal(signal_type=SignalType.STOP, position=(0, 0))

        builder._set_signal_type_attributes(elem, signal)

        assert elem.get('type') == '205'
        assert elem.get('subtype') == '-1'

    def test_give_way_sign(self, builder):
        """Give way sign type mapping."""
        elem = etree.Element('signal')
        signal = Signal(signal_type=SignalType.GIVE_WAY, position=(0, 0))

        builder._set_signal_type_attributes(elem, signal)

        assert elem.get('type') == '206'

    def test_no_entry_sign(self, builder):
        """No entry sign type mapping."""
        elem = etree.Element('signal')
        signal = Signal(signal_type=SignalType.NO_ENTRY, position=(0, 0))

        builder._set_signal_type_attributes(elem, signal)

        assert elem.get('type') == '267'

    def test_priority_road_sign(self, builder):
        """Priority road sign type mapping."""
        elem = etree.Element('signal')
        signal = Signal(signal_type=SignalType.PRIORITY_ROAD, position=(0, 0))

        builder._set_signal_type_attributes(elem, signal)

        assert elem.get('type') == '301'

    def test_speed_limit_sign(self, builder):
        """Speed limit sign type mapping."""
        elem = etree.Element('signal')
        signal = Signal(signal_type=SignalType.SPEED_LIMIT, position=(0, 0))
        signal.value = 50
        signal.speed_unit = SpeedUnit.KMH

        builder._set_signal_type_attributes(elem, signal)

        assert elem.get('type') == '274'
        assert elem.get('subtype') == '50'

    def test_speed_limit_mph_converted(self, builder):
        """Speed limit in mph is converted to km/h."""
        elem = etree.Element('signal')
        signal = Signal(signal_type=SignalType.SPEED_LIMIT, position=(0, 0))
        signal.value = 30  # 30 mph
        signal.speed_unit = SpeedUnit.MPH

        builder._set_signal_type_attributes(elem, signal)

        assert elem.get('type') == '274'
        # 30 mph * 1.60934 = ~48 km/h
        assert elem.get('subtype') == '48'

    def test_end_speed_limit_sign(self, builder):
        """End of speed limit sign type mapping."""
        elem = etree.Element('signal')
        signal = Signal(signal_type=SignalType.END_OF_SPEED_LIMIT, position=(0, 0))

        builder._set_signal_type_attributes(elem, signal)

        assert elem.get('type') == '278'

    def test_traffic_signals(self, builder):
        """Traffic signals type mapping."""
        elem = etree.Element('signal')
        signal = Signal(signal_type=SignalType.TRAFFIC_SIGNALS, position=(0, 0))

        builder._set_signal_type_attributes(elem, signal)

        assert elem.get('type') == '1000001'

    def test_custom_signal(self, builder):
        """Custom signal uses custom type/subtype."""
        elem = etree.Element('signal')
        signal = Signal(signal_type=SignalType.CUSTOM, position=(0, 0))
        signal.custom_type = "999"
        signal.custom_subtype = "123"

        builder._set_signal_type_attributes(elem, signal)

        assert elem.get('type') == '999'
        assert elem.get('subtype') == '123'

    def test_stored_subtype_preserved(self, builder):
        """Stored subtype from import is preserved."""
        elem = etree.Element('signal')
        signal = Signal(signal_type=SignalType.STOP, position=(0, 0))
        signal.subtype = "10"  # Stored from import

        builder._set_signal_type_attributes(elem, signal)

        assert elem.get('type') == '205'
        assert elem.get('subtype') == '10'


class TestCalculateTOffset:
    """Tests for _calculate_t_offset method."""

    @pytest.fixture
    def builder(self):
        """Create signal builder with scale factor."""
        return SignalBuilder(scale_x=0.1)  # 0.1 m/pixel

    def test_signal_on_centerline(self, builder):
        """Signal on centerline has t=0."""
        centerline = [(0, 100), (200, 100)]
        signal_pos = (100, 100)  # On centerline
        s_position = 100  # At middle

        t = builder._calculate_t_offset(signal_pos, centerline, s_position)

        assert t == pytest.approx(0.0, abs=0.01)

    def test_signal_left_of_centerline(self, builder):
        """Signal left of centerline has positive t."""
        # Centerline going east (left is up = negative y in image)
        centerline = [(0, 100), (200, 100)]
        signal_pos = (100, 90)  # 10 pixels above centerline
        s_position = 100

        t = builder._calculate_t_offset(signal_pos, centerline, s_position)

        # 10 pixels * 0.1 scale = 1 meter, positive for left
        assert t == pytest.approx(1.0, abs=0.01)

    def test_signal_right_of_centerline(self, builder):
        """Signal right of centerline has negative t."""
        # Centerline going east (right is down = positive y in image)
        centerline = [(0, 100), (200, 100)]
        signal_pos = (100, 110)  # 10 pixels below centerline
        s_position = 100

        t = builder._calculate_t_offset(signal_pos, centerline, s_position)

        # 10 pixels * 0.1 scale = 1 meter, negative for right
        assert t == pytest.approx(-1.0, abs=0.01)

    def test_signal_on_diagonal_road(self, builder):
        """Signal offset from diagonal road."""
        # 45-degree centerline
        centerline = [(0, 0), (100, 100)]
        signal_pos = (50, 50)  # On centerline
        s_position = 70.71  # sqrt(50^2 + 50^2)

        t = builder._calculate_t_offset(signal_pos, centerline, s_position)

        assert t == pytest.approx(0.0, abs=0.1)


class TestSignalValidity:
    """Tests for lane validity export."""

    @pytest.fixture
    def builder(self):
        """Create signal builder."""
        return SignalBuilder(scale_x=0.1)

    @pytest.fixture
    def centerline_points(self):
        """Simple centerline."""
        return [(0, 100), (100, 100)]

    def test_single_lane_validity(self, builder, centerline_points):
        """Single lane validity is exported."""
        signal = Signal(signal_type=SignalType.STOP, position=(50, 100))
        signal.validity_lanes = [-1]

        result = builder._create_signal(signal, centerline_points)
        validity = result.find('validity')

        assert validity is not None
        assert validity.get('fromLane') == '-1'
        assert validity.get('toLane') == '-1'

    def test_contiguous_lanes_validity(self, builder, centerline_points):
        """Contiguous lanes create single validity element."""
        signal = Signal(signal_type=SignalType.STOP, position=(50, 100))
        signal.validity_lanes = [-1, -2, -3]

        result = builder._create_signal(signal, centerline_points)
        validities = result.findall('validity')

        assert len(validities) == 1
        assert validities[0].get('fromLane') == '-3'
        assert validities[0].get('toLane') == '-1'

    def test_noncontiguous_lanes_validity(self, builder, centerline_points):
        """Non-contiguous lanes create multiple validity elements."""
        signal = Signal(signal_type=SignalType.STOP, position=(50, 100))
        signal.validity_lanes = [-1, -3]  # Gap at -2

        result = builder._create_signal(signal, centerline_points)
        validities = result.findall('validity')

        assert len(validities) == 2

    def test_no_validity_when_empty(self, builder, centerline_points):
        """No validity element when no lanes specified."""
        signal = Signal(signal_type=SignalType.STOP, position=(50, 100))
        signal.validity_lanes = []

        result = builder._create_signal(signal, centerline_points)
        validity = result.find('validity')

        assert validity is None

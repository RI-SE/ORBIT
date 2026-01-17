"""Tests for orbit.import.osm_query module."""

import importlib
import json
import urllib.error
import pytest
from unittest.mock import Mock, patch, MagicMock

# Import from orbit.import using importlib (import is a reserved keyword)
osm_query = importlib.import_module('orbit.import.osm_query')

OverpassAPIError = osm_query.OverpassAPIError
OverpassAPIClient = osm_query.OverpassAPIClient
query_osm_data = osm_query.query_osm_data


class TestOverpassAPIError:
    """Tests for OverpassAPIError exception."""

    def test_is_exception(self):
        """OverpassAPIError is an Exception."""
        assert issubclass(OverpassAPIError, Exception)

    def test_can_be_raised(self):
        """OverpassAPIError can be raised with a message."""
        with pytest.raises(OverpassAPIError) as exc_info:
            raise OverpassAPIError("Test error")
        assert str(exc_info.value) == "Test error"


class TestOverpassAPIClientInit:
    """Tests for OverpassAPIClient initialization."""

    def test_default_endpoint(self):
        """Default endpoint is the public Overpass API."""
        client = OverpassAPIClient()
        assert client.endpoint == 'https://overpass-api.de/api/interpreter'

    def test_custom_endpoint(self):
        """Custom endpoint can be specified."""
        client = OverpassAPIClient(endpoint='https://custom.api/interpreter')
        assert client.endpoint == 'https://custom.api/interpreter'

    def test_default_timeout(self):
        """Default timeout is 60 seconds."""
        client = OverpassAPIClient()
        assert client.timeout == 60

    def test_custom_timeout(self):
        """Custom timeout can be specified."""
        client = OverpassAPIClient(timeout=120)
        assert client.timeout == 120

    def test_class_constants(self):
        """Class constants are defined."""
        assert hasattr(OverpassAPIClient, 'DEFAULT_ENDPOINT')
        assert hasattr(OverpassAPIClient, 'BACKUP_ENDPOINT')
        assert 'overpass-api.de' in OverpassAPIClient.DEFAULT_ENDPOINT
        assert 'kumi.systems' in OverpassAPIClient.BACKUP_ENDPOINT


class TestBuildQuery:
    """Tests for OverpassAPIClient._build_query method."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return OverpassAPIClient(timeout=30)

    @pytest.fixture
    def bbox(self):
        """Sample bounding box (Stockholm area)."""
        return (59.3, 18.0, 59.4, 18.1)

    def test_moderate_query_contains_highways(self, client, bbox):
        """Moderate query includes highway ways."""
        query = client._build_query(bbox, 'moderate')
        assert 'way["highway"]' in query

    def test_moderate_query_contains_traffic_signals(self, client, bbox):
        """Moderate query includes traffic signals."""
        query = client._build_query(bbox, 'moderate')
        assert 'node["highway"="traffic_signals"]' in query

    def test_moderate_query_contains_stop_signs(self, client, bbox):
        """Moderate query includes stop signs."""
        query = client._build_query(bbox, 'moderate')
        assert 'node["highway"="stop"]' in query

    def test_moderate_query_contains_give_way(self, client, bbox):
        """Moderate query includes give way signs."""
        query = client._build_query(bbox, 'moderate')
        assert 'node["highway"="give_way"]' in query

    def test_moderate_query_contains_cycleways(self, client, bbox):
        """Moderate query includes cycleways."""
        query = client._build_query(bbox, 'moderate')
        assert 'way["highway"="cycleway"]' in query

    def test_moderate_query_contains_footways(self, client, bbox):
        """Moderate query includes footways."""
        query = client._build_query(bbox, 'moderate')
        assert 'way["highway"="footway"]' in query

    def test_moderate_query_excludes_steps(self, client, bbox):
        """Moderate query excludes steps."""
        query = client._build_query(bbox, 'moderate')
        assert 'highway"!~"steps' in query

    def test_moderate_query_contains_bbox(self, client, bbox):
        """Moderate query contains bounding box."""
        query = client._build_query(bbox, 'moderate')
        assert '59.3,18.0,59.4,18.1' in query

    def test_moderate_query_sets_timeout(self, client, bbox):
        """Moderate query sets the timeout."""
        query = client._build_query(bbox, 'moderate')
        assert 'timeout:30' in query

    def test_moderate_query_requests_json(self, client, bbox):
        """Moderate query requests JSON output."""
        query = client._build_query(bbox, 'moderate')
        assert '[out:json]' in query

    def test_moderate_query_contains_restrictions(self, client, bbox):
        """Moderate query includes turn restrictions."""
        query = client._build_query(bbox, 'moderate')
        assert 'relation["type"="restriction"]' in query

    def test_full_query_contains_trees(self, client, bbox):
        """Full query includes trees."""
        query = client._build_query(bbox, 'full')
        assert 'node["natural"="tree"]' in query

    def test_full_query_contains_buildings(self, client, bbox):
        """Full query includes buildings."""
        query = client._build_query(bbox, 'full')
        assert 'way["building"]' in query

    def test_full_query_contains_street_lamps(self, client, bbox):
        """Full query includes street lamps."""
        query = client._build_query(bbox, 'full')
        assert 'node["highway"="street_lamp"]' in query

    def test_full_query_contains_guard_rails(self, client, bbox):
        """Full query includes guard rails."""
        query = client._build_query(bbox, 'full')
        assert 'way["barrier"="guard_rail"]' in query

    def test_full_query_contains_crossings(self, client, bbox):
        """Full query includes crossings (not in moderate)."""
        query = client._build_query(bbox, 'full')
        assert 'node["highway"="crossing"]' in query

    def test_invalid_detail_level_raises(self, client, bbox):
        """Invalid detail level raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            client._build_query(bbox, 'invalid')
        assert 'Invalid detail_level' in str(exc_info.value)


class TestExecuteQuery:
    """Tests for OverpassAPIClient._execute_query method."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return OverpassAPIClient(timeout=30)

    def test_successful_query(self, client):
        """Successful query returns parsed JSON."""
        mock_response = Mock()
        mock_response.read.return_value = b'{"elements": []}'
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)

        with patch('urllib.request.urlopen', return_value=mock_response):
            result = client._execute_query('test query')

        assert result == {"elements": []}

    def test_http_error_raises_api_error(self, client):
        """HTTP errors are wrapped in OverpassAPIError."""
        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.HTTPError(
                url='http://test', code=429, msg='Too Many Requests',
                hdrs={}, fp=None
            )
            with pytest.raises(OverpassAPIError) as exc_info:
                client._execute_query('test query')

        assert '429' in str(exc_info.value)
        assert 'Too Many Requests' in str(exc_info.value)

    def test_url_error_raises_api_error(self, client):
        """URL errors are wrapped in OverpassAPIError."""
        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.URLError('Connection refused')
            with pytest.raises(OverpassAPIError) as exc_info:
                client._execute_query('test query')

        assert 'Connection error' in str(exc_info.value)

    def test_json_decode_error_raises_api_error(self, client):
        """Invalid JSON responses raise OverpassAPIError."""
        mock_response = Mock()
        mock_response.read.return_value = b'not valid json'
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)

        with patch('urllib.request.urlopen', return_value=mock_response):
            with pytest.raises(OverpassAPIError) as exc_info:
                client._execute_query('test query')

        assert 'Invalid JSON' in str(exc_info.value)

    def test_timeout_error_raises_api_error(self, client):
        """Timeout errors are wrapped in OverpassAPIError."""
        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_urlopen.side_effect = TimeoutError()
            with pytest.raises(OverpassAPIError) as exc_info:
                client._execute_query('test query')

        assert 'timed out' in str(exc_info.value)

    def test_overpass_remark_error_raises_api_error(self, client):
        """Overpass API error remarks raise OverpassAPIError."""
        mock_response = Mock()
        mock_response.read.return_value = b'{"remark": "runtime error: Query timeout"}'
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)

        with patch('urllib.request.urlopen', return_value=mock_response):
            with pytest.raises(OverpassAPIError) as exc_info:
                client._execute_query('test query')

        assert 'timeout' in str(exc_info.value).lower()

    def test_overpass_remark_warning_not_error(self, client):
        """Overpass API warnings (without error/timeout) don't raise."""
        mock_response = Mock()
        mock_response.read.return_value = b'{"remark": "This is a warning", "elements": []}'
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)

        with patch('urllib.request.urlopen', return_value=mock_response):
            result = client._execute_query('test query')

        assert result['elements'] == []

    def test_request_uses_post(self, client):
        """Request uses POST method with query data."""
        mock_response = Mock()
        mock_response.read.return_value = b'{"elements": []}'
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)

        with patch('urllib.request.urlopen', return_value=mock_response) as mock_urlopen:
            with patch('urllib.request.Request') as mock_request:
                mock_request.return_value = Mock()
                client._execute_query('test query')

        mock_request.assert_called_once()
        call_args = mock_request.call_args
        # Check that data was passed (POST)
        assert call_args.kwargs.get('data') == b'test query' or call_args[1].get('data') == b'test query'

    def test_request_sets_user_agent(self, client):
        """Request sets User-Agent header."""
        mock_response = Mock()
        mock_response.read.return_value = b'{"elements": []}'
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)

        with patch('urllib.request.urlopen', return_value=mock_response):
            with patch('urllib.request.Request') as mock_request:
                mock_request.return_value = Mock()
                client._execute_query('test query')

        call_args = mock_request.call_args
        headers = call_args.kwargs.get('headers') or call_args[1].get('headers', {})
        assert 'User-Agent' in headers
        assert 'ORBIT' in headers['User-Agent']


class TestQueryBbox:
    """Tests for OverpassAPIClient.query_bbox method."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return OverpassAPIClient(timeout=30)

    @pytest.fixture
    def bbox(self):
        """Sample bounding box."""
        return (59.3, 18.0, 59.4, 18.1)

    def test_successful_query(self, client, bbox):
        """Successful query returns data."""
        mock_result = {'elements': [{'type': 'way', 'id': 123}]}

        with patch.object(client, '_execute_query', return_value=mock_result):
            result = client.query_bbox(bbox, 'moderate')

        assert result == mock_result

    def test_calls_build_and_execute(self, client, bbox):
        """query_bbox calls _build_query and _execute_query."""
        with patch.object(client, '_build_query', return_value='query') as mock_build:
            with patch.object(client, '_execute_query', return_value={}) as mock_exec:
                client.query_bbox(bbox, 'moderate')

        mock_build.assert_called_once_with(bbox, 'moderate')
        mock_exec.assert_called_once_with('query')

    def test_tries_backup_on_failure(self, client, bbox):
        """Falls back to backup endpoint on primary failure."""
        # First call fails, second succeeds
        call_count = 0

        def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise OverpassAPIError("Primary failed")
            return {'elements': []}

        with patch.object(client, '_execute_query', side_effect=mock_execute):
            result = client.query_bbox(bbox, 'moderate')

        assert result == {'elements': []}
        assert call_count == 2

    def test_backup_restores_primary_on_success(self, client, bbox):
        """Primary endpoint is restored after successful backup query."""
        original_endpoint = client.endpoint
        call_count = 0

        def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise OverpassAPIError("Primary failed")
            return {'elements': []}

        with patch.object(client, '_execute_query', side_effect=mock_execute):
            client.query_bbox(bbox, 'moderate')

        assert client.endpoint == original_endpoint

    def test_backup_restores_primary_on_failure(self, client, bbox):
        """Primary endpoint is restored even if backup also fails."""
        original_endpoint = client.endpoint

        with patch.object(client, '_execute_query',
                         side_effect=OverpassAPIError("Both failed")):
            with pytest.raises(OverpassAPIError):
                client.query_bbox(bbox, 'moderate')

        assert client.endpoint == original_endpoint

    def test_no_backup_for_custom_endpoint(self, bbox):
        """Backup is not tried for custom endpoints."""
        client = OverpassAPIClient(endpoint='https://custom.api/interpreter')

        with patch.object(client, '_execute_query',
                         side_effect=OverpassAPIError("Custom failed")):
            with pytest.raises(OverpassAPIError):
                client.query_bbox(bbox, 'moderate')

        # Should only have been called once (no backup attempt)
        # Can verify by checking endpoint wasn't changed


class TestQueryOsmData:
    """Tests for query_osm_data convenience function."""

    @pytest.fixture
    def bbox(self):
        """Sample bounding box."""
        return (59.3, 18.0, 59.4, 18.1)

    def test_returns_data_on_success(self, bbox):
        """Returns data on successful query."""
        mock_result = {'elements': [{'type': 'way', 'id': 123}]}

        with patch.object(OverpassAPIClient, 'query_bbox', return_value=mock_result):
            result = query_osm_data(bbox)

        assert result == mock_result

    def test_returns_none_on_failure(self, bbox):
        """Returns None on query failure."""
        with patch.object(OverpassAPIClient, 'query_bbox',
                         side_effect=OverpassAPIError("Query failed")):
            result = query_osm_data(bbox)

        assert result is None

    def test_passes_detail_level(self, bbox):
        """Passes detail_level to client."""
        with patch.object(OverpassAPIClient, 'query_bbox', return_value={}) as mock_query:
            query_osm_data(bbox, detail_level='full')

        mock_query.assert_called_once_with(bbox, 'full')

    def test_passes_timeout(self, bbox):
        """Passes timeout to client constructor."""
        with patch.object(OverpassAPIClient, '__init__', return_value=None) as mock_init:
            with patch.object(OverpassAPIClient, 'query_bbox', return_value={}):
                query_osm_data(bbox, timeout=120)

        mock_init.assert_called_once_with(timeout=120)

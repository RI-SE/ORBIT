"""
Overpass API client for querying OpenStreetMap data.
"""

import json
import urllib.request
import urllib.error
from typing import Optional


class OverpassAPIError(Exception):
    """Raised when Overpass API request fails."""
    pass


class OverpassAPIClient:
    """Client for querying Overpass API."""

    # Public Overpass API endpoints
    DEFAULT_ENDPOINT = 'https://overpass-api.de/api/interpreter'
    BACKUP_ENDPOINT = 'https://overpass.kumi.systems/api/interpreter'

    def __init__(self, endpoint: str = None, timeout: int = 60):
        """
        Initialize Overpass API client.

        Args:
            endpoint: Overpass API endpoint URL (default: public API)
            timeout: Request timeout in seconds (default: 60)
        """
        self.endpoint = endpoint or self.DEFAULT_ENDPOINT
        self.timeout = timeout

    def query_bbox(self, bbox: tuple[float, float, float, float],
                   detail_level: str = 'moderate') -> dict:
        """
        Query OSM data for a bounding box.

        Args:
            bbox: Tuple of (min_lat, min_lon, max_lat, max_lon)
            detail_level: 'moderate' or 'full'

        Returns:
            Parsed JSON response from Overpass API

        Raises:
            OverpassAPIError: If query fails
        """
        query = self._build_query(bbox, detail_level)

        try:
            return self._execute_query(query)
        except OverpassAPIError as e:
            # Try backup endpoint if primary fails
            if self.endpoint == self.DEFAULT_ENDPOINT:
                print(f"Primary endpoint failed: {e}")
                print(f"Retrying with backup endpoint: {self.BACKUP_ENDPOINT}")
                old_endpoint = self.endpoint
                self.endpoint = self.BACKUP_ENDPOINT
                try:
                    result = self._execute_query(query)
                    # Restore primary endpoint for next time
                    self.endpoint = old_endpoint
                    return result
                except OverpassAPIError:
                    # Restore primary endpoint
                    self.endpoint = old_endpoint
                    raise
            else:
                raise

    def _build_query(self, bbox: tuple[float, float, float, float],
                     detail_level: str) -> str:
        """
        Build Overpass QL query string.

        Args:
            bbox: Bounding box (min_lat, min_lon, max_lat, max_lon)
            detail_level: 'moderate' or 'full'

        Returns:
            Overpass QL query string
        """
        min_lat, min_lon, max_lat, max_lon = bbox
        bbox_str = f"{min_lat},{min_lon},{max_lat},{max_lon}"

        if detail_level == 'moderate':
            # Roads, paths, traffic signals, common regulatory signs, and turn restrictions
            query = f"""
[out:json][timeout:{self.timeout}];
(
  way["highway"]["highway"!~"steps|bridleway|corridor|pedestrian"]({bbox_str});
  way["highway"="cycleway"]({bbox_str});
  way["highway"="footway"]({bbox_str});
  way["highway"="path"]["bicycle"="designated"]({bbox_str});
  way["highway"="path"]["foot"="designated"]({bbox_str});
  node["highway"="traffic_signals"]({bbox_str});
  node["highway"="give_way"]({bbox_str});
  node["highway"="stop"]({bbox_str});
  node["traffic_sign"~"maxspeed|274|C3[123]"]({bbox_str});
  node["maxspeed"]({bbox_str});
  relation["type"="restriction"]({bbox_str});
);
out body;
>;
out skel qt;
"""
        elif detail_level == 'full':
            # Everything: roads, paths, signals, signs, furniture, buildings, vegetation, restrictions
            query = f"""
[out:json][timeout:{self.timeout}];
(
  way["highway"]["highway"!~"steps|bridleway|corridor|pedestrian"]({bbox_str});
  way["highway"="cycleway"]({bbox_str});
  way["highway"="footway"]({bbox_str});
  way["highway"="path"]["bicycle"="designated"]({bbox_str});
  way["highway"="path"]["foot"="designated"]({bbox_str});
  node["highway"="traffic_signals"]({bbox_str});
  node["highway"="give_way"]({bbox_str});
  node["highway"="stop"]({bbox_str});
  node["highway"="crossing"]({bbox_str});
  node["traffic_sign"~"SE:|DE:"]({bbox_str});
  node["traffic_sign"]({bbox_str});
  node["maxspeed"]({bbox_str});
  node["highway"="street_lamp"]({bbox_str});
  way["barrier"="guard_rail"]({bbox_str});
  way["building"]({bbox_str});
  node["natural"="tree"]({bbox_str});
  node["natural"="scrub"]({bbox_str});
  node["natural"="bush"]({bbox_str});
  relation["type"="restriction"]({bbox_str});
);
out body;
>;
out skel qt;
"""
        else:
            raise ValueError(f"Invalid detail_level: {detail_level}")

        return query.strip()

    def _execute_query(self, query: str) -> dict:
        """
        Execute Overpass query and return parsed JSON.

        Args:
            query: Overpass QL query string

        Returns:
            Parsed JSON response

        Raises:
            OverpassAPIError: If request fails
        """
        # Encode query as POST data
        data = query.encode('utf-8')

        # Create request
        req = urllib.request.Request(
            self.endpoint,
            data=data,
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'ORBIT-OSM-Importer/1.0'
            }
        )

        try:
            # Execute request
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                response_data = response.read()

            # Parse JSON
            result = json.loads(response_data.decode('utf-8'))

            # Check for Overpass API errors
            if 'remark' in result:
                # Overpass API returns remarks for errors/warnings
                remark = result['remark']
                if 'error' in remark.lower() or 'timeout' in remark.lower():
                    raise OverpassAPIError(f"Overpass API error: {remark}")

            return result

        except urllib.error.HTTPError as e:
            raise OverpassAPIError(
                f"HTTP error {e.code}: {e.reason}"
            )
        except urllib.error.URLError as e:
            raise OverpassAPIError(
                f"Connection error: {e.reason}"
            )
        except json.JSONDecodeError as e:
            raise OverpassAPIError(
                f"Invalid JSON response: {e}"
            )
        except TimeoutError:
            raise OverpassAPIError(
                f"Request timed out after {self.timeout} seconds. "
                "Try a smaller area or increase timeout."
            )
        except Exception as e:
            raise OverpassAPIError(
                f"Unexpected error: {type(e).__name__}: {e}"
            )


def query_osm_data(bbox: tuple[float, float, float, float],
                   detail_level: str = 'moderate',
                   timeout: int = 60) -> Optional[dict]:
    """
    Convenience function to query OSM data.

    Args:
        bbox: Bounding box (min_lat, min_lon, max_lat, max_lon)
        detail_level: 'moderate' or 'full'
        timeout: Request timeout in seconds

    Returns:
        Parsed OSM data dict, or None if query fails
    """
    client = OverpassAPIClient(timeout=timeout)
    try:
        return client.query_bbox(bbox, detail_level)
    except OverpassAPIError as e:
        print(f"Failed to query OSM data: {e}")
        return None

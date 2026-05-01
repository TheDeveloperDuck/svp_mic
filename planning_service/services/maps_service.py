"""Google Maps geocoding integration for the Planning Service.

Exposes a single async function:
- get_coordinates -- resolve a street address to latitude/longitude.
"""

import os

import httpx
from dotenv import load_dotenv

from shared.exceptions import (
    ExternalMappingUnavailableError,
    InvalidCoordinatesError,
)
from shared.logger import logger


load_dotenv()

_GEOCODING_URL: str = "https://maps.googleapis.com/maps/api/geocode/json"
_MOCK_KEY: str = "mock_key"
_MOCK_COORDINATES: dict = {"lat": 53.3498, "lng": -6.2603}


async def get_coordinates(address: str, tracing_headers: dict | None = None) -> dict:
    """Resolve a street address to geographic coordinates.

    When the configured API key is ``mock_key``, the real API is bypassed
    and a fixed set of Dublin coordinates is returned for development use.

    Arguments:
    address -- the street address string to geocode.

    Return value:
    dict -- a mapping with ``lat`` and ``lng`` float keys.

    Raises:
    ExternalMappingUnavailableError -- when the API returns a non-200
        response or an empty results list.
    InvalidCoordinatesError -- when the result is missing ``lat`` or ``lng``.
    """
    api_key: str = os.getenv("GOOGLE_MAPS_API_KEY", "")

    if api_key == _MOCK_KEY:
        logger.debug(
            "Mock key detected; returning hardcoded coordinates for '%s'.",
            address,
        )
        return _MOCK_COORDINATES

    async with httpx.AsyncClient() as client:
        response = await client.get(
            _GEOCODING_URL,
            params={"address": address, "key": api_key},
            headers=tracing_headers or {},
        )

    if response.status_code != 200:
        logger.error(
            "Geocoding API returned HTTP %d for address '%s'.",
            response.status_code,
            address,
        )
        raise ExternalMappingUnavailableError(
            f"Geocoding API returned HTTP {response.status_code}"
            f" for address '{address}'."
        )

    results = response.json().get("results", [])
    if not results:
        logger.error(
            "Geocoding API returned empty results for address '%s'.", address
        )
        raise ExternalMappingUnavailableError(
            f"Geocoding API returned no results for address '{address}'."
        )

    location = results[0].get("geometry", {}).get("location", {})
    lat = location.get("lat")
    lng = location.get("lng")

    if lat is None or lng is None:
        logger.error(
            "Geocoding result missing lat/lng for address '%s': %s.",
            address,
            location,
        )
        raise InvalidCoordinatesError(
            f"Geocoding result for '{address}' is missing lat or lng."
        )

    logger.info("Geocoded '%s' → lat=%s, lng=%s.", address, lat, lng)
    return {"lat": lat, "lng": lng}

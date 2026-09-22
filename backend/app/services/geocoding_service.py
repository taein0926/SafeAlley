import threading
import time
from typing import Any

import httpx

from app.core.config import get_settings


class GeocodingServiceError(RuntimeError):
    """Raised when the configured fallback geocoder is unavailable or invalid."""


_request_lock = threading.Lock()
_last_request_at = 0.0
_MIN_REQUEST_INTERVAL_SECONDS = 1.0


def _bounded_viewbox(bounds: tuple[float, float, float, float]) -> str:
    min_lon, min_lat, max_lon, max_lat = bounds
    return f"{min_lon},{max_lat},{max_lon},{min_lat}"


def _request_payload(path: str, params: dict[str, object]) -> object:
    global _last_request_at

    settings = get_settings()
    url = f"{settings.nominatim_base_url.rstrip('/')}/{path.lstrip('/')}"
    with _request_lock:
        wait_seconds = _MIN_REQUEST_INTERVAL_SECONDS - (
            time.monotonic() - _last_request_at
        )
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        try:
            response = httpx.get(
                url,
                params=params,
                headers={"User-Agent": settings.nominatim_user_agent},
                timeout=settings.nominatim_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise GeocodingServiceError(
                "Fallback place search service is unavailable"
            ) from exc
        finally:
            _last_request_at = time.monotonic()

    return payload


def _request_results(
    name: str,
    bounds: tuple[float, float, float, float],
) -> list[dict[str, Any]]:
    payload = _request_payload(
        "search",
        {
            "q": f"{name.strip()}, 미추홀구, 인천광역시",
            "format": "jsonv2",
            "addressdetails": 1,
            "namedetails": 1,
            "limit": 3,
            "countrycodes": "kr",
            "viewbox": _bounded_viewbox(bounds),
            "bounded": 1,
        },
    )

    if not isinstance(payload, list) or any(
        not isinstance(item, dict) for item in payload
    ):
        raise GeocodingServiceError(
            "Fallback place search returned an invalid response"
        )
    return payload


def _place_from_result(
    result: dict[str, Any],
    fallback_name: str,
) -> dict[str, object]:
    try:
        latitude = float(result["lat"])
        longitude = float(result["lon"])
    except (KeyError, TypeError, ValueError) as exc:
        raise GeocodingServiceError(
            "Fallback place search returned invalid coordinates"
        ) from exc

    namedetails = result.get("namedetails")
    display_name = str(result.get("display_name") or fallback_name).strip()
    resolved_name = str(result.get("name") or fallback_name).strip()
    if isinstance(namedetails, dict):
        resolved_name = str(
            namedetails.get("name:ko")
            or namedetails.get("name")
            or resolved_name
        ).strip()
    if not resolved_name:
        resolved_name = display_name.split(",", maxsplit=1)[0].strip() or fallback_name
    osm_type = str(result.get("osm_type") or "place")
    osm_id = str(result.get("osm_id") or result.get("place_id") or "unknown")
    return {
        "name": resolved_name,
        "category": str(result.get("type"))[:64]
        if result.get("type")
        else None,
        "address": display_name,
        "source": "nominatim-osm",
        "source_id": f"{osm_type}-{osm_id}"[:128],
        "latitude": latitude,
        "longitude": longitude,
    }


def geocode_place(
    name: str,
    bounds: tuple[float, float, float, float],
) -> dict[str, object] | None:
    """Resolve one user-triggered query inside the loaded Michuhol road extent."""

    results = _request_results(name, bounds)
    if not results:
        return None

    place = _place_from_result(results[0], name.strip())
    latitude = float(place["latitude"])
    longitude = float(place["longitude"])

    min_lon, min_lat, max_lon, max_lat = bounds
    if not (min_lon <= longitude <= max_lon and min_lat <= latitude <= max_lat):
        return None

    return place


def reverse_geocode_place(latitude: float, longitude: float) -> dict[str, object]:
    """Resolve a clicked WGS84 coordinate with the same Nominatim policy."""

    payload = _request_payload(
        "reverse",
        {
            "lat": latitude,
            "lon": longitude,
            "format": "jsonv2",
            "addressdetails": 1,
            "namedetails": 1,
            "zoom": 18,
        },
    )
    if not isinstance(payload, dict):
        raise GeocodingServiceError(
            "Fallback reverse place search returned an invalid response"
        )
    return _place_from_result(payload, "선택한 건물")

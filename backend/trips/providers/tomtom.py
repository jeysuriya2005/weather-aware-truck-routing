"""
TomTom Geocoding and Routing client.

Response shapes were checked against the live API (2026-10-23):
* Geocode: results[].{id, type, entityType, position{lat, lon}, address.freeformAddress}
* Routing: routes[].{summary{lengthInMeters, travelTimeInSeconds, trafficDelayInSeconds,
  departureTime, arrivalTime}, legs[].points[]{latitude, longitude},
  progress[]{pointIndex, travelTimeInSeconds, distanceInMeters}}
* Errors: {"detailedError": {"code", "message"}}; an invalid key returns 401.

The API key travels as a query parameter, so request URLs are never logged
and transport exceptions are re-raised without their original message.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime
from typing import Any
from urllib.parse import quote

import requests

from ..domain.geometry import Coordinate
from ..domain.routes import Place, ProgressPoint, RouteOption
from .errors import (
    NoRouteFound,
    ProviderAuthFailed,
    ProviderBadResponse,
    ProviderError,
    ProviderNotConfigured,
    ProviderRateLimited,
    ProviderRejectedRequest,
    ProviderTimeout,
    ProviderUnavailable,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://api.tomtom.com"
CONNECT_TIMEOUT_SECONDS = 3.05
GEOCODE_READ_TIMEOUT_SECONDS = 8.0
ROUTE_READ_TIMEOUT_SECONDS = 30.0

# The assessment is US-focused (miles, pounds, US weather models).
GEOCODE_COUNTRY_SET = "US"

# Primary route + up to two alternatives = up to three options.
MAX_ALTERNATIVES = 2

# TomTom engine codes that mean "no drivable route between these points".
NO_ROUTE_ERROR_CODES = {"NO_ROUTE_FOUND", "MAP_MATCHING_FAILURE", "CANNOT_RESTORE_BASEROUTE"}


class TomTomClient:
    def __init__(self, api_key: str, session: requests.Session | None = None):
        if not api_key:
            raise ProviderNotConfigured()
        self._api_key = api_key
        self._session = session or requests.Session()

    # --- public API --------------------------------------------------------

    def geocode(self, query: str, limit: int = 5) -> list[Place]:
        payload = self._get(
            f"/search/2/geocode/{quote(query, safe='')}.json",
            params={"limit": limit, "countrySet": GEOCODE_COUNTRY_SET, "typeahead": "true"},
            read_timeout=GEOCODE_READ_TIMEOUT_SECONDS,
            operation="geocode",
        )
        return parse_geocode_response(payload)

    def calculate_routes(
        self, origin: Coordinate, destination: Coordinate, depart_at: datetime
    ) -> list[RouteOption]:
        if depart_at.tzinfo is None:
            raise ValueError("depart_at must be timezone-aware")
        locations = f"{origin.lat:.6f},{origin.lon:.6f}:{destination.lat:.6f},{destination.lon:.6f}"
        payload = self._get(
            f"/routing/1/calculateRoute/{locations}/json",
            params=[
                ("maxAlternatives", MAX_ALTERNATIVES),
                # Truck routing with default dimensions. The driver's load weight is
                # deliberately NOT sent as vehicleWeight: it is cargo, not gross weight.
                ("travelMode", "truck"),
                ("departAt", depart_at.isoformat(timespec="seconds")),
                ("traffic", "true"),
                ("routeRepresentation", "polyline"),
                ("extendedRouteRepresentation", "travelTime"),
                ("extendedRouteRepresentation", "distance"),
            ],
            read_timeout=ROUTE_READ_TIMEOUT_SECONDS,
            operation="route",
        )
        routes = parse_route_response(payload)
        if not routes:
            raise NoRouteFound()
        return routes

    # --- transport ---------------------------------------------------------

    def _get(self, path: str, params: Any, read_timeout: float, operation: str) -> Any:
        query = list(params.items()) if isinstance(params, dict) else list(params)
        query.append(("key", self._api_key))
        try:
            response = self._session.get(
                BASE_URL + path,
                params=query,
                timeout=(CONNECT_TIMEOUT_SECONDS, read_timeout),
            )
        except requests.Timeout:
            logger.warning("TomTom %s request timed out", operation)
            raise ProviderTimeout() from None
        except requests.RequestException as exc:
            # The exception text can contain the URL (and therefore the key): log the type only.
            logger.warning("TomTom %s request failed: %s", operation, type(exc).__name__)
            raise ProviderUnavailable() from None

        if response.status_code != 200:
            raise _error_for_status(response, operation)

        try:
            return response.json()
        except ValueError:
            logger.warning("TomTom %s returned non-JSON content", operation)
            raise ProviderBadResponse() from None


def _error_for_status(response: requests.Response, operation: str) -> ProviderError:
    status = response.status_code
    provider_code = _detailed_error_code(response)
    logger.warning("TomTom %s failed: HTTP %s %s", operation, status, provider_code or "")

    if status in (401, 403):
        return ProviderAuthFailed()
    if status == 429:
        return ProviderRateLimited()
    if status == 400:
        if provider_code in NO_ROUTE_ERROR_CODES:
            return NoRouteFound()
        return ProviderRejectedRequest()
    if status in (408, 504):
        return ProviderTimeout()
    return ProviderUnavailable()


def _detailed_error_code(response: requests.Response) -> str | None:
    try:
        code = response.json().get("detailedError", {}).get("code")
    except (ValueError, AttributeError):
        return None
    return code if isinstance(code, str) else None


# --- parsing (pure functions, unit-tested with recorded shapes) ---------------

def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProviderBadResponse(f"Routing provider response has an invalid '{field}'.")
    return float(value)


def _datetime(value: Any, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ProviderBadResponse(f"Routing provider response has an invalid '{field}'.") from None
    if parsed.tzinfo is None:
        raise ProviderBadResponse(f"Routing provider response has an invalid '{field}'.")
    return parsed


def _coordinate(lat: Any, lon: Any) -> Coordinate:
    try:
        return Coordinate(_number(lat, "latitude"), _number(lon, "longitude"))
    except ValueError:
        raise ProviderBadResponse("Routing provider returned an out-of-range coordinate.") from None


def parse_geocode_response(payload: Any) -> list[Place]:
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ProviderBadResponse()

    places: list[Place] = []
    seen_labels: set[str] = set()
    for result in payload["results"]:
        # Skip individual incomplete suggestions rather than failing the whole list.
        try:
            label = result["address"]["freeformAddress"].strip()
            coordinate = _coordinate(result["position"]["lat"], result["position"]["lon"])
            place_id = str(result["id"])
        except (KeyError, TypeError, AttributeError, ProviderBadResponse):
            continue
        # TomTom can return several entities with the same label (e.g. a city and
        # its county seat); results are ranked, so keep the first.
        if not label or label in seen_labels:
            continue
        seen_labels.add(label)
        kind = result.get("entityType") or result.get("type") or "Place"
        places.append(Place(id=place_id, label=label, coordinate=coordinate, kind=str(kind)))
    return places


def _parse_points(legs: Any) -> tuple[Coordinate, ...]:
    if not isinstance(legs, list) or not legs:
        raise ProviderBadResponse("Routing provider response has no route legs.")
    # Points are kept exactly as returned (no de-duplication) so that
    # progress[].pointIndex keeps indexing into this sequence.
    points: list[Coordinate] = []
    for leg in legs:
        leg_points = leg.get("points") if isinstance(leg, dict) else None
        if not isinstance(leg_points, list) or not leg_points:
            raise ProviderBadResponse("Routing provider response has no route geometry.")
        for raw in leg_points:
            if not isinstance(raw, dict):
                raise ProviderBadResponse("Routing provider response has invalid route geometry.")
            points.append(_coordinate(raw.get("latitude"), raw.get("longitude")))
    if len(points) < 2:
        raise ProviderBadResponse("Routing provider response has too little route geometry.")
    return tuple(points)


def _parse_progress(raw_progress: Any, point_count: int) -> tuple[ProgressPoint, ...]:
    if raw_progress is None:
        return ()
    if not isinstance(raw_progress, list):
        raise ProviderBadResponse("Routing provider response has invalid progress data.")
    progress: list[ProgressPoint] = []
    for raw in raw_progress:
        if not isinstance(raw, dict):
            raise ProviderBadResponse("Routing provider response has invalid progress data.")
        index = raw.get("pointIndex")
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < point_count:
            raise ProviderBadResponse("Routing provider response has invalid progress data.")
        entry = ProgressPoint(
            point_index=index,
            travel_time_seconds=_number(raw.get("travelTimeInSeconds"), "travelTimeInSeconds"),
            distance_meters=_number(raw.get("distanceInMeters"), "distanceInMeters"),
        )
        if progress and (
            entry.point_index <= progress[-1].point_index
            or entry.travel_time_seconds < progress[-1].travel_time_seconds
            or entry.distance_meters < progress[-1].distance_meters
        ):
            raise ProviderBadResponse("Routing provider progress data is not monotonic.")
        progress.append(entry)
    return tuple(progress)


def parse_route(raw: Any) -> RouteOption:
    if not isinstance(raw, dict) or not isinstance(raw.get("summary"), dict):
        raise ProviderBadResponse("Routing provider response has no route summary.")
    summary = raw["summary"]
    points = _parse_points(raw.get("legs"))

    distance = _number(summary.get("lengthInMeters"), "lengthInMeters")
    travel_time = _number(summary.get("travelTimeInSeconds"), "travelTimeInSeconds")
    if distance <= 0 or travel_time <= 0:
        raise ProviderBadResponse("Routing provider returned a route with no length or duration.")

    return RouteOption(
        points=points,
        distance_meters=distance,
        travel_time_seconds=travel_time,
        traffic_delay_seconds=_number(summary.get("trafficDelayInSeconds", 0), "trafficDelayInSeconds"),
        departure_time=_datetime(summary.get("departureTime"), "departureTime"),
        arrival_time=_datetime(summary.get("arrivalTime"), "arrivalTime"),
        progress=_parse_progress(raw.get("progress"), len(points)),
    )


def parse_route_response(payload: Any) -> list[RouteOption]:
    if not isinstance(payload, dict) or not isinstance(payload.get("routes"), list):
        raise ProviderBadResponse()
    return _unique_routes([parse_route(raw) for raw in payload["routes"]])


def _unique_routes(routes: Sequence[RouteOption]) -> list[RouteOption]:
    """Drop exact geometric duplicates, keeping provider order. Never adds routes."""
    unique: dict[str, RouteOption] = {}
    for route in routes:
        unique.setdefault(route.route_id, route)
    return list(unique.values())

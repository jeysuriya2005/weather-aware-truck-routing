"""
Open-Meteo hourly forecast client (no API key; free tier is non-commercial).

Behaviour checked against the live API (2026-10-23):
* Several locations per request via comma-separated latitude/longitude; the
  response is a list in input order (a single location returns an object).
* start_hour/end_hour (GMT, "YYYY-MM-DDTHH:MM") are inclusive. An end_hour
  after 23:00 UTC on today + 15 days fails the *whole* request with HTTP 400,
  so callers must clamp to `forecast_horizon_end()`.
* Errors: HTTP 400 with {"error": true, "reason": "..."}.
* With wind_speed_unit=mph and precipitation_unit=inch, wind is reported as
  "mp/h" and rain/showers/snowfall as "inch" (snowfall included). Units are
  verified on every response.
* rain/showers/snowfall are sums over the preceding hour (= in/hr).
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from ..domain.forecast import ForecastSample
from ..domain.geometry import Coordinate
from .errors import (
    ProviderBadResponse,
    ProviderRateLimited,
    ProviderRejectedRequest,
    ProviderTimeout,
    ProviderUnavailable,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://api.open-meteo.com/v1/forecast"
HOURLY_VARIABLES = ("wind_speed_10m", "wind_gusts_10m", "rain", "showers", "snowfall")
EXPECTED_UNITS = {
    "wind_speed_10m": "mp/h",
    "wind_gusts_10m": "mp/h",
    "rain": "inch",
    "showers": "inch",
    "snowfall": "inch",
}
MAX_LOCATIONS_PER_REQUEST = 100  # keeps URLs ~1.6 KB; 100 x 49 h measured at ~1.2 s
MAX_PARALLEL_REQUESTS = 4
CONNECT_TIMEOUT_SECONDS = 3.05
READ_TIMEOUT_SECONDS = 20.0
FORECAST_HORIZON_DAYS = 15
TIME_FORMAT = "%Y-%m-%dT%H:%M"

Series = dict[datetime, ForecastSample]


def forecast_horizon_end(now: datetime) -> datetime:
    """Latest hour Open-Meteo accepts as end_hour: 23:00 UTC on today + 15 days."""
    today = now.astimezone(timezone.utc).date()
    last_day = today + timedelta(days=FORECAST_HORIZON_DAYS)
    return datetime(last_day.year, last_day.month, last_day.day, 23, tzinfo=timezone.utc)


class OpenMeteoClient:
    def __init__(self, base_url: str = BASE_URL):
        self._base_url = base_url

    def fetch_hourly(self, locations: Sequence[Coordinate], start: datetime, end: datetime) -> list[Series]:
        """Hourly samples for each location (input order), start..end inclusive (UTC hours)."""
        if not locations:
            return []
        if start.tzinfo is None or end.tzinfo is None or end < start:
            raise ValueError("start and end must be timezone-aware with start <= end")
        chunks = [
            list(locations[i : i + MAX_LOCATIONS_PER_REQUEST])
            for i in range(0, len(locations), MAX_LOCATIONS_PER_REQUEST)
        ]
        if len(chunks) == 1:
            return self._fetch_chunk(chunks[0], start, end)
        with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL_REQUESTS, len(chunks))) as pool:
            results = list(pool.map(lambda chunk: self._fetch_chunk(chunk, start, end), chunks))
        return [series for chunk_result in results for series in chunk_result]

    def _fetch_chunk(self, locations: list[Coordinate], start: datetime, end: datetime) -> list[Series]:
        params = {
            "latitude": ",".join(f"{c.lat:.4f}" for c in locations),
            "longitude": ",".join(f"{c.lon:.4f}" for c in locations),
            "hourly": ",".join(HOURLY_VARIABLES),
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timezone": "GMT",
            "timeformat": "unixtime",
            "start_hour": start.astimezone(timezone.utc).strftime(TIME_FORMAT),
            "end_hour": end.astimezone(timezone.utc).strftime(TIME_FORMAT),
        }
        try:
            response = requests.get(
                self._base_url, params=params, timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS)
            )
        except requests.Timeout:
            logger.warning("Open-Meteo request timed out")
            raise ProviderTimeout("The weather provider did not respond in time.") from None
        except requests.RequestException as exc:
            logger.warning("Open-Meteo request failed: %s", type(exc).__name__)
            raise ProviderUnavailable("The weather provider is currently unavailable.") from None

        if response.status_code != 200:
            reason = _error_reason(response)
            logger.warning("Open-Meteo failed: HTTP %s %s", response.status_code, reason or "")
            if response.status_code == 429:
                raise ProviderRateLimited("The weather provider's rate limit was reached. Try again shortly.")
            if response.status_code == 400:
                raise ProviderRejectedRequest("The weather provider rejected the forecast request.")
            raise ProviderUnavailable("The weather provider is currently unavailable.")

        try:
            payload = response.json()
        except ValueError:
            raise ProviderBadResponse("The weather provider returned an unexpected response.") from None
        return parse_forecast_payload(payload, expected_locations=len(locations))


def _error_reason(response: requests.Response) -> str | None:
    try:
        reason = response.json().get("reason")
    except (ValueError, AttributeError):
        return None
    return reason if isinstance(reason, str) else None


def _bad(detail: str) -> ProviderBadResponse:
    return ProviderBadResponse(f"The weather provider returned an unexpected response ({detail}).")


def _optional_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise _bad("non-numeric value")
    return float(value)


def parse_location(payload: Any) -> Series:
    if not isinstance(payload, dict) or not isinstance(payload.get("hourly"), dict):
        raise _bad("missing hourly data")
    units = payload.get("hourly_units")
    if not isinstance(units, dict):
        raise _bad("missing units")
    for variable, unit in EXPECTED_UNITS.items():
        if units.get(variable) != unit:
            raise _bad(f"unexpected unit for {variable}")

    hourly = payload["hourly"]
    times = hourly.get("time")
    if not isinstance(times, list):
        raise _bad("missing times")
    columns = {}
    for variable in HOURLY_VARIABLES:
        column = hourly.get(variable)
        if not isinstance(column, list) or len(column) != len(times):
            raise _bad(f"missing or misaligned {variable}")
        columns[variable] = column

    series: Series = {}
    for row, stamp in enumerate(times):
        if isinstance(stamp, bool) or not isinstance(stamp, int):
            raise _bad("invalid time")
        moment = datetime.fromtimestamp(stamp, tz=timezone.utc)
        series[moment] = ForecastSample(
            time=moment,
            wind_mph=_optional_number(columns["wind_speed_10m"][row]),
            wind_gust_mph=_optional_number(columns["wind_gusts_10m"][row]),
            rain_in_per_hr=_optional_number(columns["rain"][row]),
            showers_in_per_hr=_optional_number(columns["showers"][row]),
            snow_in_per_hr=_optional_number(columns["snowfall"][row]),
        )
    return series


def parse_forecast_payload(payload: Any, expected_locations: int) -> list[Series]:
    items = [payload] if isinstance(payload, dict) else payload
    if not isinstance(items, list) or len(items) != expected_locations:
        raise _bad("location count mismatch")
    return [parse_location(item) for item in items]

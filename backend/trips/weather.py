"""
Forecast retrieval with caching. Turns a set of locations and a time window
into hourly samples, reusing recent responses to limit Open-Meteo calls.

Window: from the forecast hour containing the departure, extended in whole
days to cover the 48 h heatmap and the latest checkpoint ETA, then clamped
to the provider's horizon. Day-aligned windows keep cache keys stable when
the same trip is planned again. Hours past the horizon stay missing and
are reported as unavailable, never as Low risk.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from django.core.cache import cache

from .domain.forecast import ForecastSample, forecast_hour_for
from .domain.geometry import Coordinate
from .providers.errors import ProviderError
from .providers.open_meteo import OpenMeteoClient, Series, forecast_horizon_end

HEATMAP_HOURS = 48
CACHE_TTL_SECONDS = 30 * 60  # models update hourly; keep reuse short
CACHE_PREFIX = "openmeteo:v1"
CHECKPOINT_SNAP_DEGREES = 0.05  # ~5.5 km; nearby checkpoints share one forecast lookup


@dataclass(frozen=True)
class ForecastWindow:
    start: datetime  # inclusive, UTC hour
    end: datetime  # inclusive, UTC hour

    def contains(self, moment: datetime) -> bool:
        return self.start <= moment <= self.end


def forecast_window(departure: datetime, latest_eta: datetime, now: datetime) -> ForecastWindow | None:
    start = forecast_hour_for(departure)
    needed_end = max(start + timedelta(hours=HEATMAP_HOURS), forecast_hour_for(latest_eta))
    days = math.ceil((needed_end - start) / timedelta(days=1))
    end = min(start + timedelta(days=days), forecast_horizon_end(now))
    if end < start:
        return None
    return ForecastWindow(start=start, end=end)


def snap(coordinate: Coordinate, step: float = CHECKPOINT_SNAP_DEGREES) -> Coordinate:
    return Coordinate(round(round(coordinate.lat / step) * step, 4), round(round(coordinate.lon / step) * step, 4))


@dataclass
class ForecastResult:
    series: dict[Coordinate, Series] = field(default_factory=dict)
    error: ProviderError | None = None
    cached_locations: int = 0
    fetched_locations: int = 0

    def sample(self, location: Coordinate, hour: datetime) -> ForecastSample | None:
        return self.series.get(location, {}).get(hour)


def _cache_key(location: Coordinate, window: ForecastWindow) -> str:
    return (
        f"{CACHE_PREFIX}:{location.lat:.4f}:{location.lon:.4f}:"
        f"{window.start:%Y%m%d%H}:{window.end:%Y%m%d%H}"
    )


def fetch_forecasts(
    locations: Iterable[Coordinate],
    window: ForecastWindow | None,
    client: OpenMeteoClient | None = None,
) -> ForecastResult:
    unique = list(dict.fromkeys(locations))
    result = ForecastResult()
    if window is None or not unique:
        return result

    keys = {location: _cache_key(location, window) for location in unique}
    cached = cache.get_many(list(keys.values()))
    for location, key in keys.items():
        if key in cached:
            result.series[location] = cached[key]
    result.cached_locations = len(result.series)

    missing = [location for location in unique if location not in result.series]
    if not missing:
        return result
    try:
        fetched = (client or OpenMeteoClient()).fetch_hourly(missing, window.start, window.end)
    except ProviderError as exc:
        result.error = exc
        return result

    result.series.update(zip(missing, fetched))
    result.fetched_locations = len(missing)
    cache.set_many({keys[location]: series for location, series in zip(missing, fetched)}, CACHE_TTL_SECONDS)
    return result

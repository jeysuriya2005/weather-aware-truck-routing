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

import logging
import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from django.core.cache import cache

from .domain.forecast import ForecastSample, forecast_hour_for
from .domain.geometry import Coordinate
from .providers.errors import ProviderError
from .providers.open_meteo import OpenMeteoClient, Series, forecast_horizon_end

logger = logging.getLogger(__name__)

HEATMAP_HOURS = 48
CACHE_TTL_SECONDS = 30 * 60  # models update hourly; keep reuse short
CACHE_PREFIX = "openmeteo:v1"
CHECKPOINT_SNAP_DEGREES = 0.05  # ~5.5 km; nearby checkpoints share one forecast lookup

# Open-Meteo counts EVERY location in a request against its free-tier limit of
# 600 calls/minute (observed: 100-location bursts -> HTTP 429, 2026-10-24). A
# coast-to-coast plan at 10 mi needs ~1,090 locations, so each plan is capped
# well below the limit. Checkpoints get priority; the heatmap gets the rest.
LOCATION_BUDGET = 500
MIN_HEATMAP_POINTS = 60
MAX_HEATMAP_POINTS = 200
# Coarser forecast-lookup grids, used only when a trip's checkpoints need more
# distinct forecast points than the budget allows. Checkpoint placement and
# ETAs are unaffected; only the weather grid point each one reads from changes.
SNAP_OPTIONS_DEGREES = (0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.75, 1.0)


def choose_snap_step(coordinates: Iterable[Coordinate], max_points: int) -> float:
    """Finest lookup grid whose distinct points fit in `max_points`."""
    coordinates = list(coordinates)
    for step in SNAP_OPTIONS_DEGREES:
        if len({snap(c, step) for c in coordinates}) <= max_points:
            return step
    return SNAP_OPTIONS_DEGREES[-1]


def heatmap_point_budget(checkpoint_points: int) -> int:
    """Heatmap points left after checkpoints, within [MIN, MAX]."""
    return max(MIN_HEATMAP_POINTS, min(MAX_HEATMAP_POINTS, LOCATION_BUDGET - checkpoint_points))


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
    requested_locations: int = 0
    failed_locations: int = 0

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
    result = ForecastResult(requested_locations=len(unique))
    if window is None:
        logger.warning("Forecast fetch skipped: departure window is beyond the provider's forecast horizon")
        return result
    if not unique:
        return result

    keys = {location: _cache_key(location, window) for location in unique}
    cached = cache.get_many(list(keys.values()))
    for location, key in keys.items():
        if key in cached:
            result.series[location] = cached[key]
    result.cached_locations = len(result.series)

    missing = [location for location in unique if location not in result.series]
    if missing:
        try:
            fetched, result.error = (client or OpenMeteoClient()).fetch_hourly_partial(missing, window.start, window.end)
        except ProviderError as exc:
            result.error = exc
            fetched = [None] * len(missing)

        # Keep whatever succeeded: a failed request (e.g. rate limit) only leaves its
        # own locations missing, and missing is reported as unknown, never as Low.
        succeeded = {location: series for location, series in zip(missing, fetched) if series is not None}
        result.series.update(succeeded)
        result.fetched_locations = len(succeeded)
        result.failed_locations = len(missing) - len(succeeded)
        cache.set_many({keys[location]: series for location, series in succeeded.items()}, CACHE_TTL_SECONDS)

    _log_summary(result, window)
    return result


def _log_summary(result: ForecastResult, window: ForecastWindow) -> None:
    """One line per plan for production diagnosis. Contains no secrets (Open-Meteo uses no key)."""
    level = logging.WARNING if result.error else logging.INFO
    logger.log(
        level,
        "Forecast fetch: %d locations requested, %d cached, %d fetched, %d failed; window %s..%s UTC%s",
        result.requested_locations,
        result.cached_locations,
        result.fetched_locations,
        result.failed_locations,
        f"{window.start:%Y-%m-%dT%H:%M}",
        f"{window.end:%Y-%m-%dT%H:%M}",
        f"; error {type(result.error).__name__}: {result.error.message}" if result.error else "",
    )

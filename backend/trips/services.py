"""
Use-case orchestration between views, providers and domain logic.

Trip planning pipeline:
  TomTom routes -> checkpoints with ETAs -> Open-Meteo forecasts (cached)
  -> per-checkpoint risk -> route summaries -> recommendation -> heatmap.

If the weather provider fails, routes are still returned with risk marked
unavailable and no recommendation: missing weather is never shown as safe.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone

from . import presenters
from .domain.checkpoints import Checkpoint, build_timeline, place_checkpoints
from .domain.corridor import corridor_grid
from .domain.forecast import AssessedSample, assess_sample, forecast_hour_for
from .domain.geometry import Coordinate
from .domain.recommendation import RiskSegment, RouteRiskInput, recommend_route
from .domain.routes import RouteOption
from .providers.tomtom import MAX_ALTERNATIVES, TomTomClient
from .weather import (
    CHECKPOINT_SNAP_DEGREES,
    HEATMAP_HOURS,
    LOCATION_BUDGET,
    MIN_HEATMAP_POINTS,
    ForecastResult,
    choose_snap_step,
    fetch_forecasts,
    forecast_window,
    heatmap_point_budget,
    snap,
)

REQUESTED_ROUTE_OPTIONS = MAX_ALTERNATIVES + 1
WEATHER_PROVIDER = "Open-Meteo"


def get_routing_client() -> TomTomClient:
    """Raises ProviderNotConfigured when TOMTOM_API_KEY is empty."""
    return TomTomClient(settings.TOMTOM_API_KEY)


def search_places(query: str) -> list[dict]:
    return [presenters.present_place(place) for place in get_routing_client().geocode(query)]


@dataclass
class _RouteAnalysis:
    route: RouteOption
    eta_source: str
    checkpoints: list[Checkpoint]
    assessed: list[AssessedSample]
    forecast_times: list[datetime]

    def risk_input(self) -> RouteRiskInput:
        return RouteRiskInput(
            route_id=self.route.route_id,
            travel_time_seconds=self.route.travel_time_seconds,
            segments=[
                RiskSegment(cp.segment_miles, a.risk.overall if a.risk else None)
                for cp, a in zip(self.checkpoints, self.assessed)
            ],
        )

    @property
    def known_checkpoints(self) -> int:
        return sum(a.available for a in self.assessed)


def plan_trip(
    origin: Coordinate,
    destination: Coordinate,
    departure_time: datetime,
    load_weight_lb: float,
    interval_miles: int,
    inputs: dict,
    now: datetime | None = None,
) -> dict:
    now = now or timezone.now()
    routes = get_routing_client().calculate_routes(origin, destination, departure_time)

    # 1. Checkpoints along each route's full geometry.
    placed = []
    for route in routes:
        timeline = build_timeline(route)
        placed.append((route, timeline.eta_source, place_checkpoints(route, interval_miles, timeline)))

    # 2. One batched, cached forecast lookup for checkpoints + heatmap corridor,
    #    kept within the provider's per-minute location budget (checkpoints first).
    latest_eta = max(cp.eta for _, _, cps in placed for cp in cps)
    window = forecast_window(departure_time, latest_eta, now)
    all_checkpoints = [cp for _, _, cps in placed for cp in cps]
    snap_step = choose_snap_step((cp.coordinate for cp in all_checkpoints), LOCATION_BUDGET - MIN_HEATMAP_POINTS)
    checkpoint_points = list(dict.fromkeys(snap(cp.coordinate, snap_step) for cp in all_checkpoints))
    grid = corridor_grid([route.points for route in routes], max_points=heatmap_point_budget(len(checkpoint_points)))
    locations = list(dict.fromkeys(checkpoint_points + grid.points))
    forecasts = fetch_forecasts(locations, window)

    # 3. Risk per checkpoint at its arrival hour.
    analyses = []
    for route, eta_source, checkpoints in placed:
        times = [forecast_hour_for(cp.eta) for cp in checkpoints]
        assessed = [
            assess_sample(forecasts.sample(snap(cp.coordinate, snap_step), hour), load_weight_lb)
            for cp, hour in zip(checkpoints, times)
        ]
        analyses.append(_RouteAnalysis(route, eta_source, checkpoints, assessed, times))

    # 4. Recommendation only when there is some real weather to rank on.
    any_known = any(a.known_checkpoints for a in analyses)
    recommendation = recommend_route([a.risk_input() for a in analyses]) if any_known else None
    ranks = {route_id: i + 1 for i, route_id in enumerate(recommendation.ranked_route_ids)} if recommendation else {}
    labels = {a.route.route_id: presenters.route_label(i) for i, a in enumerate(analyses)}

    weather_status = _weather_status(analyses, forecasts, window, snap_step, len(locations))
    presented_routes = []
    for index, analysis in enumerate(analyses):
        route_id = analysis.route.route_id
        checkpoints = [
            presenters.present_checkpoint(cp, hour, assessed, load_weight_lb, snap(cp.coordinate, snap_step))
            for cp, hour, assessed in zip(analysis.checkpoints, analysis.forecast_times, analysis.assessed)
        ]
        presented_routes.append(
            presenters.present_route(
                analysis.route,
                index,
                checkpoints,
                analysis.eta_source,
                recommendation.summaries[route_id] if recommendation else None,
                ranks.get(route_id),
                recommendation is not None and recommendation.recommended_route_id == route_id,
            )
        )

    count = len(routes)
    return {
        "routes": presented_routes,
        "route_count": count,
        "requested_route_count": REQUESTED_ROUTE_OPTIONS,
        "notice": None
        if count >= REQUESTED_ROUTE_OPTIONS
        else (
            f"The routing provider returned {count} of the {REQUESTED_ROUTE_OPTIONS} requested "
            f"route options for this trip. Only real provider routes are shown."
        ),
        "recommendation": presenters.present_recommendation(recommendation, labels, weather_status["message"]),
        "weather_risk": weather_status,
        "heatmap": _heatmap(grid.spacing_degrees, grid.points, departure_time, forecasts, load_weight_lb),
        "inputs": inputs,
        "provider": {"routing": "TomTom", "travel_mode": "truck", "weather": WEATHER_PROVIDER},
    }


def _weather_status(
    analyses: list[_RouteAnalysis], forecasts: ForecastResult, window, snap_step: float, location_count: int
) -> dict:
    total = sum(len(a.assessed) for a in analyses)
    known = sum(a.known_checkpoints for a in analyses)
    reason = None
    if known == total:
        status, message = "complete", "Forecasts are available for every checkpoint."
        if snap_step > CHECKPOINT_SNAP_DEGREES:
            message += (
                f" This long trip reads forecasts from a {snap_step:g}° grid (about "
                f"{snap_step * 111:.0f} km) to stay within the weather provider's request limits."
            )
    elif known == 0:
        status = "unavailable"
        if forecasts.error is not None:
            reason = forecasts.error.code
            message = f"{forecasts.error.message} Route risk cannot be assessed; no route is recommended."
        elif window is None:
            reason = "beyond_forecast_horizon"
            message = "The departure is beyond the weather provider's forecast range. Route risk cannot be assessed."
        else:
            reason = "no_forecast_data"
            message = "Forecasts are unavailable for these arrival times. Route risk cannot be assessed."
    else:
        status = "partial"
        reason = forecasts.error.code if forecasts.error is not None else "forecast_gaps"
        message = (
            f"Forecasts are missing for {total - known} of {total} checkpoints; "
            "those segments are unknown risk, not low risk."
        )
    return {
        "status": status,
        # Machine-readable cause when not complete: a provider error code (e.g.
        # provider_rate_limited, provider_timeout), beyond_forecast_horizon,
        # no_forecast_data or forecast_gaps. None when complete.
        "reason": reason,
        "message": message,
        "provider": WEATHER_PROVIDER,
        "checkpoints_total": total,
        # Grid (degrees) checkpoint forecasts are read from: 0.05 normally, coarser for very long trips.
        "forecast_grid_degrees": snap_step,
        "forecast_locations": location_count,
        "checkpoints_with_forecast": known,
        "window_start": window.start.isoformat() if window else None,
        "window_end": window.end.isoformat() if window else None,
    }


def _heatmap(
    spacing: float,
    points: list[Coordinate],
    departure_time: datetime,
    forecasts: ForecastResult,
    load_weight_lb: float,
) -> dict:
    """Risk and conditions at each corridor point for departure + 0..48 h."""
    frame_times = [forecast_hour_for(departure_time + timedelta(hours=h)) for h in range(HEATMAP_HOURS + 1)]
    risk, wind, rain, snow = [], [], [], []
    known = 0
    for hour in frame_times:
        frame_risk, frame_wind, frame_rain, frame_snow = [], [], [], []
        for point in points:
            assessed = assess_sample(forecasts.sample(point, hour), load_weight_lb)
            if assessed.available:
                known += 1
                frame_risk.append(int(assessed.risk.overall))
                frame_wind.append(round(assessed.weather.wind_mph, 1))
                frame_rain.append(round(assessed.weather.rain_in_per_hr, 3))
                frame_snow.append(round(assessed.weather.snow_in_per_hr, 3))
            else:
                for frame in (frame_risk, frame_wind, frame_rain, frame_snow):
                    frame.append(None)
        risk.append(frame_risk)
        wind.append(frame_wind)
        rain.append(frame_rain)
        snow.append(frame_snow)

    cells = len(points) * len(frame_times)
    status = "complete" if known == cells else "unavailable" if known == 0 else "partial"
    return {
        "status": status,
        "spacing_degrees": spacing,
        "frame_offsets_hours": list(range(HEATMAP_HOURS + 1)),
        "frame_times": [t.isoformat() for t in frame_times],
        "lats": [p.lat for p in points],
        "lons": [p.lon for p in points],
        # risk[frame][point]: 0 Low .. 4 No Travel, null = forecast unavailable.
        "risk": risk,
        "wind_mph": wind,
        "rain_in_per_hr": rain,
        "snow_in_per_hr": snow,
    }

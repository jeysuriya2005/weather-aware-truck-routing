"""
JSON shaping for API responses, including human-readable explanations.
Contains no business rules: it only presents domain results.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from .domain.checkpoints import Checkpoint
from .domain.forecast import AssessedSample
from .domain.geometry import simplify_polyline
from .domain.recommendation import Recommendation, RouteRiskSummary
from .domain.risk import RiskLevel
from .domain.routes import Place, RouteOption
from .domain.units import meters_to_miles

# ~0.0002 deg is ~20 m: visually lossless at route zoom levels, and it cuts
# ~10k-point cross-country routes to about a thousand points for the browser.
DISPLAY_SIMPLIFY_TOLERANCE_DEGREES = 0.0002
ROUTE_LABELS = "ABCDEF"
SIGNIFICANT_RISK = RiskLevel.HIGH

LEVEL_CODES = {
    RiskLevel.LOW: "low",
    RiskLevel.MODERATE: "moderate",
    RiskLevel.HIGH: "high",
    RiskLevel.SEVERE: "severe",
    RiskLevel.NO_TRAVEL: "no_travel",
}

UNAVAILABLE_WARNING = "Forecast unavailable for this arrival time: risk is unknown, not low."


def level_code(level: RiskLevel | None) -> str | None:
    return None if level is None else LEVEL_CODES[level]


def route_label(index: int) -> str:
    return f"Route {ROUTE_LABELS[index]}"


def _iso(moment: datetime | None) -> str | None:
    return None if moment is None else moment.isoformat(timespec="seconds")


def _round(value: float | None, digits: int) -> float | None:
    return None if value is None else round(value, digits)


# --- places ------------------------------------------------------------------

def present_place(place: Place) -> dict:
    return {
        "id": place.id,
        "label": place.label,
        "lat": place.coordinate.lat,
        "lon": place.coordinate.lon,
        "kind": place.kind,
    }


# --- checkpoints -------------------------------------------------------------

def hazards_at_overall(assessed: AssessedSample) -> list[str]:
    """Hazards that set the overall level (only when it is above Low)."""
    risk = assessed.risk
    if risk is None or risk.overall == RiskLevel.LOW:
        return []
    return [name for name, level in (("wind", risk.wind), ("rain", risk.rain), ("snow", risk.snow))
            if level == risk.overall]


def describe_hazard(name: str, assessed: AssessedSample) -> str:
    weather = assessed.weather
    if name == "wind":
        return f"wind {weather.wind_mph:.0f} mph"
    if name == "rain":
        return f"rain {weather.rain_in_per_hr:.2f} in/hr"
    return f"snow {weather.snow_in_per_hr:.2f} in/hr"


def checkpoint_warnings(assessed: AssessedSample, load_weight_lb: float) -> list[str]:
    if not assessed.available:
        return [UNAVAILABLE_WARNING]
    risk = assessed.risk
    warnings = []
    if risk.load_rule_applied:
        warnings.append(
            f"Load rule: {load_weight_lb:,.0f} lb with {assessed.weather.wind_mph:.0f} mph wind raises "
            f"wind risk from {risk.wind_base.label} to {risk.wind.label}."
        )
    if risk.overall >= SIGNIFICANT_RISK:
        causes = ", ".join(describe_hazard(name, assessed) for name in hazards_at_overall(assessed))
        prefix = "No Travel" if risk.overall == RiskLevel.NO_TRAVEL else f"{risk.overall.label} risk"
        warnings.append(f"{prefix}: {causes}.")
    return warnings


def present_checkpoint(
    checkpoint: Checkpoint, forecast_time: datetime, assessed: AssessedSample, load_weight_lb: float
) -> dict:
    sample, risk = assessed.sample, assessed.risk
    return {
        "index": checkpoint.index,
        "mile": round(checkpoint.mile, 2),
        "segment_start_mile": round(checkpoint.segment_start_mile, 3),
        "segment_end_mile": round(checkpoint.segment_end_mile, 3),
        "segment_miles": round(checkpoint.segment_miles, 3),
        "lat": round(checkpoint.coordinate.lat, 5),
        "lon": round(checkpoint.coordinate.lon, 5),
        "eta": _iso(checkpoint.eta),
        "forecast_time": _iso(forecast_time),
        "status": "ok" if assessed.available else "unavailable",
        "weather": None
        if not assessed.available
        else {
            "wind_mph": round(assessed.weather.wind_mph, 1),
            "wind_gust_mph": _round(sample.wind_gust_mph, 1),
            "rain_in_per_hr": round(assessed.weather.rain_in_per_hr, 3),
            "snow_in_per_hr": round(assessed.weather.snow_in_per_hr, 3),
        },
        "risk": None
        if risk is None
        else {
            "overall": level_code(risk.overall),
            "wind": level_code(risk.wind),
            "wind_before_load_rule": level_code(risk.wind_base),
            "rain": level_code(risk.rain),
            "snow": level_code(risk.snow),
            "load_rule_applied": risk.load_rule_applied,
        },
        "hazards": hazards_at_overall(assessed),
        "warnings": checkpoint_warnings(assessed, load_weight_lb),
    }


# --- route hazard stretches -------------------------------------------------

def hazard_stretches(checkpoints: Sequence[dict]) -> list[dict]:
    """Consecutive checkpoints at High or worse with the same level, merged into stretches."""
    stretches: list[dict] = []
    significant = {"high", "severe", "no_travel"}
    for cp in checkpoints:
        level = cp["risk"]["overall"] if cp["risk"] else None
        if level not in significant:
            continue
        last = stretches[-1] if stretches else None
        if last and last["level"] == level and last["last_index"] == cp["index"] - 1:
            last["end_mile"] = cp["segment_end_mile"]
            last["last_eta"] = cp["eta"]
            last["last_index"] = cp["index"]
            last["hazards"] = sorted(set(last["hazards"]) | set(cp["hazards"]))
        else:
            stretches.append({
                "level": level,
                "hazards": list(cp["hazards"]),
                "start_mile": cp["segment_start_mile"],
                "end_mile": cp["segment_end_mile"],
                "first_eta": cp["eta"],
                "last_eta": cp["eta"],
                "first_index": cp["index"],
                "last_index": cp["index"],
            })
    order = {"no_travel": 0, "severe": 1, "high": 2}
    return sorted(stretches, key=lambda s: (order[s["level"]], s["start_mile"]))


# --- routes --------------------------------------------------------------------

def present_summary(summary: RouteRiskSummary | None) -> dict | None:
    if summary is None:
        return None
    return {
        "total_miles": round(summary.total_miles, 2),
        "miles_by_level": {LEVEL_CODES[level]: round(miles, 2) for level, miles in summary.miles_by_level.items()},
        "unknown_miles": round(summary.unknown_miles, 2),
        "severe_or_worse_miles": round(summary.severe_or_worse_miles, 2),
        "average_risk": _round(summary.average_risk, 3),
        "max_risk": level_code(summary.max_risk),
        "has_no_travel": summary.has_no_travel,
        "coverage_complete": not summary.has_unknown,
    }


def present_route(
    route: RouteOption,
    index: int,
    checkpoints: list[dict],
    eta_source: str,
    summary: RouteRiskSummary | None,
    rank: int | None,
    recommended: bool,
) -> dict:
    display_points = simplify_polyline(route.points, DISPLAY_SIMPLIFY_TOLERANCE_DEGREES)
    return {
        "id": route.route_id,
        "index": index,
        "label": route_label(index),
        "distance_meters": route.distance_meters,
        "distance_miles": round(meters_to_miles(route.distance_meters), 1),
        "duration_seconds": route.travel_time_seconds,
        "traffic_delay_seconds": route.traffic_delay_seconds,
        "departure_time": route.departure_time.isoformat(),
        "arrival_time": route.arrival_time.isoformat(),
        "geometry": {
            "type": "LineString",
            # GeoJSON order is [longitude, latitude].
            "coordinates": [[point.lon, point.lat] for point in display_points],
        },
        "geometry_point_count": {"provider": len(route.points), "display": len(display_points)},
        "eta_source": eta_source,
        "checkpoints": checkpoints,
        "risk_summary": present_summary(summary),
        "hazard_stretches": hazard_stretches(checkpoints),
        "rank": rank,
        "recommended": recommended,
    }


# --- recommendation ------------------------------------------------------------

def _hours(seconds: float) -> str:
    minutes = round(seconds / 60)
    return f"{minutes // 60} h {minutes % 60:02d} min"


def explain_recommendation(recommendation: Recommendation, labels: dict[str, str]) -> str:
    ranked = recommendation.ranked_route_ids
    best = recommendation.summaries[ranked[0]]
    name = labels[best.route_id]

    if len(ranked) == 1:
        reason = f"{name} is the only route option returned."
    else:
        other = recommendation.summaries[ranked[1]]
        other_name = labels[other.route_id]
        reasons = {
            "no_travel": (
                f"{name} avoids No Travel conditions; {other_name} has "
                f"{other.no_travel_miles:.1f} mi of No Travel."
            ),
            "severe_miles": (
                f"{name} has the fewest Severe-or-worse miles ({best.severe_or_worse_miles:.1f} mi vs "
                f"{other.severe_or_worse_miles:.1f} mi on {other_name})."
            ),
            "high_miles": (
                f"{name} ties on Severe miles ({best.severe_or_worse_miles:.1f} mi) and has the fewest "
                f"High miles ({best.high_miles:.1f} mi vs {other.high_miles:.1f} mi on {other_name})."
            ),
            "average_risk": (
                f"{name} ties on Severe and High miles and has the lowest average risk "
                f"({best.average_risk:.2f} vs {other.average_risk:.2f} on {other_name}, scale 0-4)."
                if best.average_risk is not None and other.average_risk is not None
                else f"{name} ties on Severe and High miles and has the lowest known average risk."
            ),
            "travel_time": (
                f"{name} ties on all weather-risk criteria and is the fastest "
                f"({_hours(best.travel_time_seconds)} vs {_hours(other.travel_time_seconds)} on {other_name})."
            ),
            "input_order": f"{name} ties with {other_name} on every criterion; the routing provider listed it first.",
        }
        reason = reasons[recommendation.decided_by]

    if recommendation.no_safe_route_available:
        return (
            "No route is fully safe: every option has No Travel conditions. "
            f"{name} has the least exposure by the ranking criteria. {reason}"
        )
    return reason


def present_recommendation(
    recommendation: Recommendation | None, labels: dict[str, str], unavailable_message: str
) -> dict:
    if recommendation is None:
        return {
            "status": "unavailable",
            "route_id": None,
            "route_label": None,
            "ranked_route_ids": [],
            "decided_by": None,
            "explanation": unavailable_message,
            "warnings": [],
            "coverage_complete": False,
        }

    warnings = []
    if recommendation.no_safe_route_available:
        warnings.append("Every route option includes No Travel conditions. Consider delaying departure.")
    if not recommendation.coverage_complete:
        affected = ", ".join(labels[r] for r in recommendation.routes_with_unknown_miles)
        warnings.append(
            f"Forecast data is missing for part of {affected}; those miles are unknown, "
            "not low risk, and are excluded from the ranking."
        )
    route_id = recommendation.recommended_route_id
    return {
        "status": "no_safe_route" if recommendation.no_safe_route_available else "recommended",
        "route_id": route_id,
        "route_label": labels[route_id],
        "ranked_route_ids": recommendation.ranked_route_ids,
        "decided_by": recommendation.decided_by,
        "explanation": explain_recommendation(recommendation, labels),
        "warnings": warnings,
        "coverage_complete": recommendation.coverage_complete,
    }

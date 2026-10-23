"""
Route summaries and the route recommendation.

Assessment PDF, "Route Recommendation" -- prefer, in order:
  1. Fewest Severe miles
  2. Fewest High miles
  3. Lowest average risk
  4. Shortest travel time

Design decisions (the PDF does not specify how No Travel is ranked):

* Safety category first. Any route with No Travel miles is unsafe. Routes
  without No Travel always rank above routes with it. The four criteria are
  then applied in order *within* each category.
* "Severe miles" for criterion 1 counts miles at Severe *or worse*. No Travel
  is strictly worse than Severe, so it should never make a route look
  better. This only matters when comparing two unsafe routes; safe routes
  have no No Travel miles. Severe-only and No Travel miles are still
  reported separately in the summary.
* "Average risk" is the distance-weighted mean of segment scores
  (Low=0, Moderate=1, High=2, Severe=3, No Travel=4). Each segment covers the
  exact road distance its checkpoint represents, so it is not a count of
  checkpoints.
* Comparisons are deterministic. Miles are compared at 0.01 mi and average
  risk at 1e-6 so floating-point noise cannot decide a ranking. A full tie
  keeps the input (routing provider) order.
* Missing forecast data is never counted as Low. Segments without a risk
  level (risk=None) are reported as unknown miles. They are excluded from
  the level buckets and from the average, and the recommendation lists the
  affected routes so callers can warn that the ranking is based on partial
  data. A route with no known miles at all ranks last on average risk. The
  PDF's criteria and their order are unchanged.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from .risk import RiskLevel

MILES_COMPARISON_DECIMALS = 2
AVERAGE_RISK_COMPARISON_DECIMALS = 6


@dataclass(frozen=True)
class RiskSegment:
    """A stretch of route, in miles, represented by one checkpoint's risk (None = unknown)."""

    distance_miles: float
    risk: RiskLevel | None

    def __post_init__(self) -> None:
        if math.isnan(self.distance_miles) or math.isinf(self.distance_miles) or self.distance_miles < 0:
            raise ValueError(f"distance_miles must be finite and non-negative, got {self.distance_miles!r}")


@dataclass(frozen=True)
class RouteRiskInput:
    route_id: str
    travel_time_seconds: float
    segments: Sequence[RiskSegment]


@dataclass(frozen=True)
class RouteRiskSummary:
    route_id: str
    travel_time_seconds: float
    total_miles: float
    miles_by_level: dict[RiskLevel, float]
    # Distance-weighted over known miles only; None when no mile is known.
    average_risk: float | None
    unknown_miles: float = 0.0

    @property
    def has_unknown(self) -> bool:
        return self.unknown_miles > 0

    @property
    def max_risk(self) -> RiskLevel | None:
        known = [level for level, miles in self.miles_by_level.items() if miles > 0]
        return max(known) if known else None

    @property
    def no_travel_miles(self) -> float:
        return self.miles_by_level[RiskLevel.NO_TRAVEL]

    @property
    def severe_miles(self) -> float:
        """Severe only, excluding No Travel."""
        return self.miles_by_level[RiskLevel.SEVERE]

    @property
    def severe_or_worse_miles(self) -> float:
        return self.severe_miles + self.no_travel_miles

    @property
    def high_miles(self) -> float:
        return self.miles_by_level[RiskLevel.HIGH]

    @property
    def has_no_travel(self) -> bool:
        return self.no_travel_miles > 0


def summarize_route(route: RouteRiskInput) -> RouteRiskSummary:
    if not route.segments:
        raise ValueError(f"Route {route.route_id!r} has no risk segments")
    if math.isnan(route.travel_time_seconds) or route.travel_time_seconds < 0:
        raise ValueError(f"Route {route.route_id!r} has an invalid travel time")

    miles_by_level = {level: 0.0 for level in RiskLevel}
    unknown_miles = 0.0
    weighted_score = 0.0
    for segment in route.segments:
        if segment.risk is None:
            unknown_miles += segment.distance_miles
            continue
        miles_by_level[segment.risk] += segment.distance_miles
        weighted_score += segment.distance_miles * int(segment.risk)

    known_miles = sum(miles_by_level.values())
    total_miles = known_miles + unknown_miles
    if total_miles <= 0:
        raise ValueError(f"Route {route.route_id!r} has zero total distance")

    return RouteRiskSummary(
        route_id=route.route_id,
        travel_time_seconds=route.travel_time_seconds,
        total_miles=total_miles,
        miles_by_level=miles_by_level,
        average_risk=weighted_score / known_miles if known_miles > 0 else None,
        unknown_miles=unknown_miles,
    )


# Criteria in ranking order; names are returned to explain the decision.
CRITERIA = (
    "no_travel",
    "severe_miles",
    "high_miles",
    "average_risk",
    "travel_time",
)


def _ranking_key(summary: RouteRiskSummary) -> tuple:
    return (
        summary.has_no_travel,
        round(summary.severe_or_worse_miles, MILES_COMPARISON_DECIMALS),
        round(summary.high_miles, MILES_COMPARISON_DECIMALS),
        math.inf
        if summary.average_risk is None
        else round(summary.average_risk, AVERAGE_RISK_COMPARISON_DECIMALS),
        summary.travel_time_seconds,
    )


@dataclass(frozen=True)
class Recommendation:
    recommended_route_id: str
    ranked_route_ids: list[str]
    summaries: dict[str, RouteRiskSummary]
    # True when every route has No Travel miles: nothing can be recommended as safe.
    no_safe_route_available: bool
    # Which criterion separated the winner from the runner-up. "input_order"
    # means a full tie; None means there was only one route.
    decided_by: str | None = field(default=None)

    @property
    def recommended_has_no_travel(self) -> bool:
        return self.summaries[self.recommended_route_id].has_no_travel

    @property
    def routes_with_unknown_miles(self) -> list[str]:
        return [route_id for route_id in self.ranked_route_ids if self.summaries[route_id].has_unknown]

    @property
    def coverage_complete(self) -> bool:
        return not self.routes_with_unknown_miles


def recommend_route(routes: Sequence[RouteRiskInput]) -> Recommendation:
    if not routes:
        raise ValueError("At least one route is required")
    route_ids = [route.route_id for route in routes]
    if len(set(route_ids)) != len(route_ids):
        raise ValueError("Route ids must be unique")

    summaries = [summarize_route(route) for route in routes]
    # sorted() is stable, so full ties keep the provider's order.
    ranked = sorted(summaries, key=_ranking_key)

    decided_by: str | None = None
    if len(ranked) > 1:
        best_key, runner_up_key = _ranking_key(ranked[0]), _ranking_key(ranked[1])
        decided_by = next(
            (name for name, a, b in zip(CRITERIA, best_key, runner_up_key) if a != b),
            "input_order",
        )

    return Recommendation(
        recommended_route_id=ranked[0].route_id,
        ranked_route_ids=[summary.route_id for summary in ranked],
        summaries={summary.route_id: summary for summary in summaries},
        no_safe_route_available=all(summary.has_no_travel for summary in summaries),
        decided_by=decided_by,
    )

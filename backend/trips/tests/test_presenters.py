from datetime import datetime, timezone

import pytest

from trips import presenters
from trips.domain.forecast import ForecastSample, assess_sample
from trips.domain.recommendation import RiskSegment, RouteRiskInput, recommend_route
from trips.domain.risk import RiskLevel

L, M, H, S, NT = (
    RiskLevel.LOW,
    RiskLevel.MODERATE,
    RiskLevel.HIGH,
    RiskLevel.SEVERE,
    RiskLevel.NO_TRAVEL,
)
T = datetime(2026, 10, 25, 11, tzinfo=timezone.utc)
LABELS = {"a": "Route A", "b": "Route B", "c": "Route C"}


def route(route_id, hours, *segments):
    return RouteRiskInput(route_id, hours * 3600, [RiskSegment(m, level) for m, level in segments])


def assessed(wind=5.0, rain=0.0, snow=0.0, load=20_000, gust=10.0):
    return assess_sample(ForecastSample(T, wind, gust, rain, 0.0, snow), load)


# --- explanations ------------------------------------------------------------------

@pytest.mark.parametrize(
    ("routes", "fragment"),
    [
        ([route("a", 2, (5, NT), (95, L)), route("b", 3, (100, L))],
         "Route B avoids No Travel conditions; Route A has 5.0 mi of No Travel."),
        ([route("a", 2, (10, S), (90, L)), route("b", 3, (100, L))],
         "Route B has the fewest Severe-or-worse miles (0.0 mi vs 10.0 mi on Route A)."),
        ([route("a", 2, (20, H), (80, L)), route("b", 3, (10, H), (90, L))],
         "Route B ties on Severe miles (0.0 mi) and has the fewest High miles (10.0 mi vs 20.0 mi on Route A)."),
        ([route("a", 2, (100, M)), route("b", 3, (100, L))],
         "Route B ties on Severe and High miles and has the lowest average risk (0.00 vs 1.00 on Route A"),
        ([route("a", 3, (100, L)), route("b", 2.5, (100, L))],
         "Route B ties on all weather-risk criteria and is the fastest (2 h 30 min vs 3 h 00 min on Route A)."),
        ([route("a", 2, (100, L)), route("b", 2, (100, L))],
         "Route A ties with Route B on every criterion; the routing provider listed it first."),
        ([route("a", 2, (100, L))], "Route A is the only route option returned."),
    ],
)
def test_explanations_name_the_deciding_criterion(routes, fragment):
    text = presenters.explain_recommendation(recommend_route(routes), LABELS)
    assert fragment in text


def test_no_safe_route_is_stated_explicitly():
    rec = recommend_route([route("a", 2, (30, NT), (70, L)), route("b", 3, (10, NT), (90, L))])
    presented = presenters.present_recommendation(rec, LABELS, "")
    assert presented["status"] == "no_safe_route"
    assert presented["explanation"].startswith("No route is fully safe")
    assert "least exposure" in presented["explanation"]
    assert any("Every route option includes No Travel" in w for w in presented["warnings"])


def test_partial_coverage_warning():
    rec = recommend_route([route("a", 2, (90, L), (10, None)), route("b", 3, (100, L))])
    presented = presenters.present_recommendation(rec, LABELS, "")
    assert presented["status"] == "recommended"
    assert presented["coverage_complete"] is False
    assert any("Route A" in w and "unknown, not low" in w for w in presented["warnings"])


def test_unavailable_recommendation():
    presented = presenters.present_recommendation(None, LABELS, "Weather down.")
    assert presented["status"] == "unavailable"
    assert presented["route_id"] is None
    assert presented["explanation"] == "Weather down."


# --- checkpoint warnings and hazards -------------------------------------------------

def test_load_rule_warning_and_no_travel_cause():
    warnings = presenters.checkpoint_warnings(assessed(wind=46, load=38_000), 38_000)
    assert warnings[0] == "Load rule: 38,000 lb with 46 mph wind raises wind risk from Severe to No Travel."
    assert warnings[1] == "No Travel: wind 46 mph."


def test_multiple_hazards_at_overall_level():
    a = assessed(rain=0.6, snow=2.5)
    assert presenters.hazards_at_overall(a) == ["rain", "snow"]
    assert presenters.checkpoint_warnings(a, 0) == ["Severe risk: rain 0.60 in/hr, snow 2.50 in/hr."]


def test_low_risk_has_no_hazards_or_warnings():
    a = assessed()
    assert presenters.hazards_at_overall(a) == []
    assert presenters.checkpoint_warnings(a, 0) == []


def test_unavailable_checkpoint_warning():
    a = assess_sample(None, 0)
    assert presenters.checkpoint_warnings(a, 0) == [presenters.UNAVAILABLE_WARNING]
    assert presenters.hazards_at_overall(a) == []


def cp(index, level, hazards=("wind",), start=None):
    start = index * 25 if start is None else start
    return {
        "index": index,
        "risk": None if level is None else {"overall": level},
        "hazards": list(hazards) if level else [],
        "segment_start_mile": start,
        "segment_end_mile": start + 25,
        "eta": f"t{index}",
    }


def test_hazard_stretches_merge_consecutive_same_level():
    stretches = presenters.hazard_stretches([
        cp(0, "low"), cp(1, "high"), cp(2, "high", ("rain",)), cp(3, "severe"), cp(4, None), cp(5, "high"),
    ])
    assert [(s["level"], s["start_mile"], s["end_mile"]) for s in stretches] == [
        ("severe", 75, 100),
        ("high", 25, 75),
        ("high", 125, 150),
    ]
    assert stretches[1]["hazards"] == ["rain", "wind"]
    assert stretches[1]["first_eta"] == "t1" and stretches[1]["last_eta"] == "t2"


def test_unknown_checkpoints_never_form_hazard_stretches_or_count_as_low():
    assert presenters.hazard_stretches([cp(0, None), cp(1, None)]) == []

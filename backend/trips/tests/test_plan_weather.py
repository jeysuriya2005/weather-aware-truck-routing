"""End-to-end /api/trips/plan/ tests with mocked TomTom and Open-Meteo."""

import re
from datetime import datetime, timedelta, timezone

import pytest
import requests
import responses
from rest_framework.test import APIClient

from . import tomtom_fixtures as fx
from .open_meteo_fixtures import URL_PATTERN, calm, mock_open_meteo, open_meteo_calls

ROUTE_URL = re.compile(re.escape("https://api.tomtom.com/routing/1/calculateRoute/") + ".*")


def add_routes(count=3):
    responses.add_callback(responses.GET, ROUTE_URL, callback=fx.routes_callback(count))


def plan(load_weight_lb=38_000, interval=25, departure=None):
    departure = departure or (datetime.now(timezone.utc).replace(minute=7, second=0, microsecond=0) + timedelta(days=1))
    body = {
        "origin": {"lat": 32.7767, "lon": -96.797, "label": "Dallas, TX"},
        "destination": {"lat": 39.7392, "lon": -104.9903, "label": "Denver, CO"},
        "departure_time": departure.isoformat(),
        "load_weight_lb": load_weight_lb,
        "checkpoint_interval_miles": interval,
    }
    response = APIClient().post("/api/trips/plan/", body, format="json")
    assert response.status_code == 200, response.content
    return response.json()


def storm_on_route_a(lat, lon, t):
    """46 mph wind around Route A's unique vertex (36.0, -101.0); calm elsewhere."""
    if abs(lat - 36.0) < 0.4 and abs(lon + 101.0) < 0.4:
        return {"wind_speed_10m": 46.0, "wind_gusts_10m": 61.0, "rain": 0.0, "showers": 0.0, "snowfall": 0.0}
    return calm(lat, lon, t)


def storm_everywhere(lat, lon, t):
    return {"wind_speed_10m": 47.0, "wind_gusts_10m": 60.0, "rain": 0.0, "showers": 0.0, "snowfall": 0.0}


def route_by_label(data, label):
    return next(r for r in data["routes"] if r["label"] == label)


# --- checkpoints ------------------------------------------------------------------

@pytest.mark.parametrize("interval", [10, 25, 50])
@responses.activate
def test_checkpoints_cover_each_route_exactly(interval):
    add_routes()
    mock_open_meteo()
    data = plan(interval=interval)
    for route in data["routes"]:
        checkpoints = route["checkpoints"]
        assert checkpoints[0]["mile"] == 0
        assert checkpoints[-1]["mile"] == pytest.approx(route["distance_miles"], abs=0.06)
        assert sum(cp["segment_miles"] for cp in checkpoints) == pytest.approx(route["distance_miles"], abs=0.06)
        gaps = [b["mile"] - a["mile"] for a, b in zip(checkpoints, checkpoints[1:])]
        assert all(gap <= interval + 1e-6 for gap in gaps)
        assert route["eta_source"] == "provider_timing"


@responses.activate
def test_checkpoint_eta_and_forecast_hour_alignment():
    add_routes()
    mock_open_meteo()
    data = plan()
    route = data["routes"][0]
    departure = datetime.fromisoformat(route["departure_time"])
    first, last = route["checkpoints"][0], route["checkpoints"][-1]
    assert datetime.fromisoformat(first["eta"]) == departure
    assert datetime.fromisoformat(last["eta"]) == datetime.fromisoformat(route["arrival_time"])
    for cp in route["checkpoints"]:
        eta, hour = datetime.fromisoformat(cp["eta"]), datetime.fromisoformat(cp["forecast_time"])
        assert timedelta(0) <= hour - eta < timedelta(hours=1)
        assert hour.minute == 0 and hour.utcoffset() == timedelta(0)
        assert cp["status"] == "ok"
        # Provenance: the forecast point is the 0.05-deg grid point nearest the checkpoint.
        point = cp["forecast_point"]
        assert abs(point["lat"] - cp["lat"]) <= 0.025 + 1e-6 and abs(point["lon"] - cp["lon"]) <= 0.025 + 1e-6
        assert abs(point["lat"] / 0.05 - round(point["lat"] / 0.05)) < 1e-6


# --- risk, summaries, recommendation --------------------------------------------------

@responses.activate
def test_load_rule_storm_makes_route_a_unsafe_and_b_recommended():
    add_routes()
    mock_open_meteo(storm_on_route_a)
    data = plan(load_weight_lb=38_000)
    a, b = route_by_label(data, "Route A"), route_by_label(data, "Route B")

    stormy = [cp for cp in a["checkpoints"] if cp["risk"]["overall"] == "no_travel"]
    assert stormy, "Route A should cross the storm"
    for cp in stormy:
        assert cp["risk"]["wind_before_load_rule"] == "severe"
        assert cp["risk"]["load_rule_applied"] is True
        assert cp["weather"]["wind_mph"] == 46.0
        assert cp["hazards"] == ["wind"]
        assert any(w.startswith("Load rule: 38,000 lb") for w in cp["warnings"])

    assert a["risk_summary"]["has_no_travel"] is True
    assert a["risk_summary"]["miles_by_level"]["no_travel"] == pytest.approx(
        sum(cp["segment_miles"] for cp in stormy), abs=0.01
    )
    assert a["hazard_stretches"][0]["level"] == "no_travel"

    rec = data["recommendation"]
    assert rec["status"] == "recommended"
    # B and C are both calm; B is faster (45,114 s vs 47,000 s).
    assert rec["route_id"] == b["id"] and b["recommended"] is True and b["rank"] == 1
    assert rec["ranked_route_ids"][-1] == a["id"]
    assert rec["decided_by"] == "travel_time"
    assert data["weather_risk"]["status"] == "complete"


@responses.activate
def test_same_storm_with_light_load_is_only_severe():
    add_routes()
    mock_open_meteo(storm_on_route_a)
    a = route_by_label(plan(load_weight_lb=30_000), "Route A")  # not > 30,000 lb
    levels = {cp["risk"]["overall"] for cp in a["checkpoints"]}
    assert "no_travel" not in levels and "severe" in levels
    assert all(not cp["risk"]["load_rule_applied"] for cp in a["checkpoints"])


@responses.activate
def test_every_route_no_travel_flags_no_safe_route():
    add_routes()
    mock_open_meteo(storm_everywhere)
    data = plan(load_weight_lb=38_000)
    rec = data["recommendation"]
    assert rec["status"] == "no_safe_route"
    assert rec["explanation"].startswith("No route is fully safe")
    assert all(r["risk_summary"]["has_no_travel"] for r in data["routes"])


@responses.activate
def test_average_risk_is_distance_weighted():
    add_routes()
    mock_open_meteo(storm_everywhere)  # 47 mph -> Severe at 20,000 lb everywhere
    data = plan(load_weight_lb=20_000)
    for route in data["routes"]:
        summary = route["risk_summary"]
        assert summary["average_risk"] == pytest.approx(3.0)
        assert summary["miles_by_level"]["severe"] == pytest.approx(route["distance_miles"], abs=0.06)


# --- missing / failing weather ------------------------------------------------------

@responses.activate
def test_weather_outage_still_returns_routes_without_recommendation():
    add_routes()
    responses.add(responses.GET, URL_PATTERN, body=requests.ReadTimeout("slow"))
    data = plan()
    assert data["route_count"] == 3
    assert data["weather_risk"]["status"] == "unavailable"
    assert "did not respond in time" in data["weather_risk"]["message"]
    assert data["recommendation"]["status"] == "unavailable"
    assert data["recommendation"]["route_id"] is None
    for route in data["routes"]:
        assert route["risk_summary"] is None and route["rank"] is None and not route["recommended"]
        for cp in route["checkpoints"]:
            assert cp["status"] == "unavailable" and cp["risk"] is None and cp["weather"] is None
            assert "unknown, not low" in cp["warnings"][0]
    assert data["heatmap"]["status"] == "unavailable"
    assert all(v is None for frame in data["heatmap"]["risk"] for v in frame)


@responses.activate
def test_partial_nulls_are_unknown_not_low():
    def gap_near_denver(lat, lon, t):
        row = calm(lat, lon, t)
        if lat > 39.0:
            row["wind_speed_10m"] = None
        return row

    add_routes()
    mock_open_meteo(gap_near_denver)
    data = plan()
    assert data["weather_risk"]["status"] == "partial"
    route = data["routes"][0]
    unknown = [cp for cp in route["checkpoints"] if cp["status"] == "unavailable"]
    assert unknown
    assert route["risk_summary"]["unknown_miles"] == pytest.approx(
        sum(cp["segment_miles"] for cp in unknown), abs=0.01
    )
    assert route["risk_summary"]["miles_by_level"]["low"] < route["distance_miles"] - 1
    assert route["risk_summary"]["coverage_complete"] is False
    assert data["recommendation"]["coverage_complete"] is False


# --- heatmap -----------------------------------------------------------------------------

@responses.activate
def test_heatmap_has_49_frames_relative_to_departure():
    add_routes()
    mock_open_meteo(storm_on_route_a)
    departure = datetime.now(timezone.utc).replace(minute=7, second=0, microsecond=0) + timedelta(days=1)
    data = plan(departure=departure)
    heatmap = data["heatmap"]
    points = len(heatmap["lats"])
    assert 0 < points <= 200 and len(heatmap["lons"]) == points
    assert heatmap["frame_offsets_hours"] == list(range(49))
    assert len(heatmap["frame_times"]) == 49
    first = datetime.fromisoformat(heatmap["frame_times"][0])
    assert first - departure == timedelta(minutes=53)  # the hourly period containing departure
    assert datetime.fromisoformat(heatmap["frame_times"][48]) - first == timedelta(hours=48)
    for key in ("risk", "wind_mph", "rain_in_per_hr", "snow_in_per_hr"):
        assert len(heatmap[key]) == 49 and all(len(frame) == points for frame in heatmap[key])
    assert heatmap["status"] == "complete"
    assert 4 in heatmap["risk"][0]  # the storm shows as No Travel at 38,000 lb
    assert 0 in heatmap["risk"][0]


@responses.activate
def test_open_meteo_requests_are_bounded_and_reused():
    add_routes()
    mock_open_meteo()
    plan(interval=10)
    first_calls = len(open_meteo_calls())
    assert 1 <= first_calls <= 6
    plan(interval=10)  # identical trip: served from cache
    assert len(open_meteo_calls()) == first_calls


# --- Location budget (regression: long 10-mi trips exceeded Open-Meteo's 600/min) ---

def _requested_locations():
    from urllib.parse import parse_qs, urlparse

    return sum(len(parse_qs(urlparse(c.request.url).query)["latitude"][0].split(",")) for c in open_meteo_calls())


@responses.activate
def test_normal_plan_uses_fine_grid_within_budget():
    add_routes()
    mock_open_meteo()
    data = plan(interval=25)
    assert data["weather_risk"]["forecast_grid_degrees"] == 0.05
    assert _requested_locations() == data["weather_risk"]["forecast_locations"] <= 500


@responses.activate
def test_plan_needing_too_many_points_coarsens_lookup_grid_but_keeps_every_checkpoint(monkeypatch):
    # Shrink the budget so the 3 fixture routes at 10 mi (~270 checkpoints) exceed it.
    monkeypatch.setattr("trips.services.LOCATION_BUDGET", 160)
    monkeypatch.setattr("trips.weather.LOCATION_BUDGET", 160)
    add_routes()
    mock_open_meteo()
    data = plan(interval=10)
    weather = data["weather_risk"]
    step = weather["forecast_grid_degrees"]
    assert step > 0.05
    assert weather["status"] == "complete"
    assert "grid" in weather["message"] and "request limits" in weather["message"]
    assert _requested_locations() <= 160  # hard cap: checkpoints + heatmap never exceed the budget
    for route in data["routes"]:
        gaps = [b["mile"] - a["mile"] for a, b in zip(route["checkpoints"], route["checkpoints"][1:])]
        assert all(g <= 10 + 1e-6 for g in gaps)  # still a checkpoint every 10 mi
        for cp in route["checkpoints"]:
            assert cp["status"] == "ok"
            point = cp["forecast_point"]
            assert abs(point["lat"] / step - round(point["lat"] / step)) < 1e-6
            assert abs(point["lat"] - cp["lat"]) <= step / 2 + 1e-6


@responses.activate
def test_rate_limited_batch_gives_partial_forecasts_not_zero():
    from urllib.parse import parse_qs, urlparse

    from .open_meteo_fixtures import make_callback

    calls = {"n": 0}

    def second_request_rate_limited(request):
        calls["n"] += 1
        lats = parse_qs(urlparse(request.url).query)["latitude"][0].split(",")
        if len(lats) == 100 and float(lats[0]) > 36:  # one of the full batches
            return 429, {"Content-Type": "application/json"}, '{"error": true, "reason": "Minutely API request limit exceeded."}'
        return make_callback()(request)

    add_routes()
    responses.add_callback(responses.GET, URL_PATTERN, callback=second_request_rate_limited)
    data = plan(interval=10)
    status = data["weather_risk"]
    # Before the fix one 429 discarded every forecast (0/N, "unavailable").
    assert status["status"] == "partial"
    assert 0 < status["checkpoints_with_forecast"] < status["checkpoints_total"]
    assert data["recommendation"]["status"] != "unavailable"
    assert data["recommendation"]["coverage_complete"] is False
    unknown = [cp for r in data["routes"] for cp in r["checkpoints"] if cp["status"] == "unavailable"]
    assert unknown and all(cp["risk"] is None for cp in unknown)

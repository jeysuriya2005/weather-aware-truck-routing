import re
from datetime import datetime, timedelta, timezone

import pytest
import requests
import responses
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from trips.serializers import RoutePlanRequestSerializer

from . import tomtom_fixtures as fx
from .open_meteo_fixtures import mock_open_meteo

TEST_KEY = "test-tomtom-key-not-real"  # matches config.test_settings
ROUTE_URL = re.compile(re.escape("https://api.tomtom.com/routing/1/calculateRoute/") + ".*")
GEOCODE_URL = re.compile(re.escape("https://api.tomtom.com/search/2/geocode/") + ".*")
NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def api():
    return APIClient()


def plan_body(**overrides):
    body = {
        "origin": {"lat": 32.7767, "lon": -96.797, "label": "Dallas, TX"},
        "destination": {"lat": 39.7392, "lon": -104.9903, "label": "Denver, CO"},
        "departure_time": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "load_weight_lb": 38000,
        "checkpoint_interval_miles": 25,
    }
    body.update(overrides)
    return body


def assert_no_secret(response):
    assert TEST_KEY not in response.content.decode()


# --- /api/geocode/ -------------------------------------------------------------

@responses.activate
def test_geocode_returns_suggestions(api):
    responses.add(responses.GET, GEOCODE_URL, json=fx.geocode_payload())
    response = api.get("/api/geocode/", {"q": "Dallas"})
    assert response.status_code == 200
    assert response.json() == {
        "results": [
            {"id": "ATFFDvKyxtf1HepzrswVcQ", "label": "Dallas, TX", "lat": 32.7779765, "lon": -96.7962148,
             "kind": "Municipality"},
            {"id": "dallas-ga", "label": "Dallas, GA", "lat": 33.9237, "lon": -84.8408, "kind": "Municipality"},
        ]
    }
    assert_no_secret(response)


@responses.activate
def test_geocode_no_matches_is_empty_list(api):
    responses.add(responses.GET, GEOCODE_URL, json={"results": []})
    response = api.get("/api/geocode/", {"q": "zzqqxx"})
    assert response.status_code == 200
    assert response.json() == {"results": []}


@pytest.mark.parametrize("params", [{}, {"q": ""}, {"q": " a "}, {"q": "x" * 201}])
def test_geocode_validates_query(api, params):
    response = api.get("/api/geocode/", params)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
    assert "q" in response.json()["error"]["fields"]


# --- /api/trips/plan/ success -------------------------------------------------

@responses.activate
def test_plan_returns_routes(api):
    responses.add(responses.GET, ROUTE_URL, json=fx.routes_payload(3))
    mock_open_meteo()
    response = api.post("/api/trips/plan/", plan_body(), format="json")
    assert response.status_code == 200
    data = response.json()

    assert data["route_count"] == 3
    assert data["requested_route_count"] == 3
    assert data["notice"] is None
    assert data["weather_risk"]["status"] == "complete"
    assert data["inputs"]["load_weight_lb"] == 38000
    assert data["inputs"]["checkpoint_interval_miles"] == 25

    first = data["routes"][0]
    assert first["label"] == "Route A"
    assert first["id"].startswith("rt_")
    assert first["distance_meters"] == 1_419_953
    assert first["distance_miles"] == 882.3
    assert first["duration_seconds"] == 42_540
    assert first["arrival_time"] == "2026-10-25T18:49:00-06:00"
    assert first["geometry"]["type"] == "LineString"
    # GeoJSON order is [lon, lat].
    assert first["geometry"]["coordinates"][0] == [-96.797, 32.7767]
    assert len({route["id"] for route in data["routes"]}) == 3
    assert_no_secret(response)


@pytest.mark.parametrize("count", [1, 2])
@responses.activate
def test_plan_reports_fewer_routes_without_padding(api, count):
    responses.add(responses.GET, ROUTE_URL, json=fx.routes_payload(count))
    data = api.post("/api/trips/plan/", plan_body(), format="json").json()
    assert data["route_count"] == count
    assert len(data["routes"]) == count
    assert f"returned {count} of the 3" in data["notice"]


@responses.activate
def test_plan_defaults_checkpoint_interval_to_25(api):
    responses.add(responses.GET, ROUTE_URL, json=fx.routes_payload(1))
    body = plan_body()
    del body["checkpoint_interval_miles"]
    assert api.post("/api/trips/plan/", body, format="json").json()["inputs"]["checkpoint_interval_miles"] == 25


@pytest.mark.parametrize("interval", [10, 25, 50])
@responses.activate
def test_plan_accepts_supported_intervals(api, interval):
    responses.add(responses.GET, ROUTE_URL, json=fx.routes_payload(1))
    response = api.post("/api/trips/plan/", plan_body(checkpoint_interval_miles=interval), format="json")
    assert response.status_code == 200


# --- /api/trips/plan/ validation ----------------------------------------------

@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"checkpoint_interval_miles": 30}, "checkpoint_interval_miles"),
        ({"load_weight_lb": -1}, "load_weight_lb"),
        ({"load_weight_lb": 200_001}, "load_weight_lb"),
        ({"load_weight_lb": "heavy"}, "load_weight_lb"),
        ({"origin": {"lat": 91, "lon": 0}}, "origin"),
        ({"destination": {"lat": 0, "lon": -181}}, "destination"),
        ({"origin": None}, "origin"),
        ({"departure_time": "next tuesday"}, "departure_time"),
        ({"departure_time": "2026-10-25T08:00:00"}, "departure_time"),  # no offset
        ({"departure_time": "2020-01-01T08:00:00Z"}, "departure_time"),  # past
        ({"destination": {"lat": 32.77671, "lon": -96.79701}}, "destination"),  # same as origin
    ],
)
def test_plan_validation_errors(api, overrides, field):
    response = api.post("/api/trips/plan/", plan_body(**overrides), format="json")
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    assert field in error["fields"]


def test_plan_missing_fields(api):
    response = api.post("/api/trips/plan/", {}, format="json")
    assert response.status_code == 400
    fields = response.json()["error"]["fields"]
    assert {"origin", "destination", "departure_time", "load_weight_lb"} <= set(fields)


@pytest.mark.parametrize(
    ("departure", "valid"),
    [
        (NOW - timedelta(minutes=15), True),  # tolerance edge
        (NOW - timedelta(minutes=16), False),
        (NOW + timedelta(days=13), True),  # departure + 48 h must fit the 15-day forecast horizon
        (NOW + timedelta(days=13, seconds=1), False),
    ],
)
def test_departure_window_boundaries(departure, valid):
    serializer = RoutePlanRequestSerializer(
        data=plan_body(departure_time=departure.isoformat()), context={"now": NOW}
    )
    assert serializer.is_valid() is valid


def test_departure_accepts_z_suffix_and_keeps_offset():
    serializer = RoutePlanRequestSerializer(
        data=plan_body(departure_time="2026-10-24T14:30:00Z"), context={"now": NOW}
    )
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["departure_time"] == datetime(2026, 10, 24, 14, 30, tzinfo=timezone.utc)


def test_plan_rejects_get(api):
    assert api.get("/api/trips/plan/").status_code == 405


# --- /api/trips/plan/ provider failures ----------------------------------------

@pytest.mark.parametrize(
    ("mock", "status", "code"),
    [
        ({"status": 400, "json": fx.error_payload("NO_ROUTE_FOUND")}, 422, "no_route_found"),
        ({"status": 400, "json": fx.error_payload("BAD_INPUT")}, 422, "provider_rejected_request"),
        ({"status": 401, "json": {"detailedError": {"code": "Unauthorized"}}}, 502, "provider_auth_failed"),
        ({"status": 403, "body": "<xml/>"}, 502, "provider_auth_failed"),
        ({"status": 429, "body": "<xml/>"}, 503, "provider_rate_limited"),
        ({"status": 500, "body": ""}, 502, "provider_unavailable"),
        ({"status": 504, "body": ""}, 504, "provider_timeout"),
        ({"status": 200, "body": "<html/>"}, 502, "provider_bad_response"),
        ({"status": 200, "json": {"routes": [{"summary": {}}]}}, 502, "provider_bad_response"),
        ({"status": 200, "json": {"routes": []}}, 422, "no_route_found"),
        ({"body": requests.ReadTimeout(f"key={TEST_KEY}")}, 504, "provider_timeout"),
        ({"body": requests.ConnectionError(f"key={TEST_KEY}")}, 502, "provider_unavailable"),
    ],
)
@responses.activate
def test_plan_provider_failures_are_safe(api, mock, status, code):
    responses.add(responses.GET, ROUTE_URL, **mock)
    response = api.post("/api/trips/plan/", plan_body(), format="json")
    assert response.status_code == status
    error = response.json()["error"]
    assert error["code"] == code
    assert error["message"]
    assert_no_secret(response)


@responses.activate
def test_rate_limit_sets_retry_after(api):
    responses.add(responses.GET, ROUTE_URL, status=429, body="")
    response = api.post("/api/trips/plan/", plan_body(), format="json")
    assert response["Retry-After"] == "60"


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [("get", "/api/geocode/", {"q": "Dallas"}), ("post", "/api/trips/plan/", None)],
)
def test_missing_key_returns_503(api, settings, method, path, payload):
    settings.TOMTOM_API_KEY = ""
    if method == "get":
        response = api.get(path, payload)
    else:
        response = api.post(path, plan_body(), format="json")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "provider_not_configured"


# --- throttling ----------------------------------------------------------------

@responses.activate
def test_geocode_is_throttled(api, monkeypatch):
    from django.core.cache import cache

    cache.clear()
    monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", {"geocode": "2/min", "trip_plan": "2/min"})
    responses.add(responses.GET, GEOCODE_URL, json={"results": []})
    statuses = [api.get("/api/geocode/", {"q": "Dallas"}).status_code for _ in range(3)]
    assert statuses == [200, 200, 429]
    cache.clear()

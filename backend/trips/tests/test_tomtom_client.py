import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pytest
import requests
import responses

from trips.domain.geometry import Coordinate
from trips.providers import errors
from trips.providers.tomtom import (
    TomTomClient,
    parse_geocode_response,
    parse_route_response,
)

from . import tomtom_fixtures as fx

KEY = "unit-test-key-123"
ROUTE_URL_PREFIX = "https://api.tomtom.com/routing/1/calculateRoute/"
GEOCODE_URL_PREFIX = "https://api.tomtom.com/search/2/geocode/"
DALLAS = Coordinate(32.7767, -96.7970)
DENVER = Coordinate(39.7392, -104.9903)
DEPART = datetime(2026, 10, 25, 13, 0, tzinfo=timezone.utc)


@pytest.fixture
def client():
    return TomTomClient(KEY)


def add_route_response(**kwargs):
    responses.add(responses.GET, re.compile(re.escape(ROUTE_URL_PREFIX) + ".*"), **kwargs)


def add_geocode_response(**kwargs):
    responses.add(responses.GET, re.compile(re.escape(GEOCODE_URL_PREFIX) + ".*"), **kwargs)


# --- configuration ------------------------------------------------------------

@pytest.mark.parametrize("key", ["", None])
def test_missing_key_is_reported_as_not_configured(key):
    with pytest.raises(errors.ProviderNotConfigured):
        TomTomClient(key)


# --- geocoding ----------------------------------------------------------------

@responses.activate
def test_geocode_request_and_parsing(client):
    add_geocode_response(json=fx.geocode_payload())
    places = client.geocode("Dallas, TX")

    url = urlparse(responses.calls[0].request.url)
    assert url.path == "/search/2/geocode/Dallas%2C%20TX.json"
    query = parse_qs(url.query)
    assert query["countrySet"] == ["US"]
    assert query["typeahead"] == ["true"]
    assert query["key"] == [KEY]

    assert [p.label for p in places] == ["Dallas, TX", "Dallas, GA"]  # duplicate label dropped
    assert places[0].coordinate == Coordinate(32.7779765, -96.7962148)
    assert places[0].kind == "Municipality"


@responses.activate
def test_geocode_escapes_path_characters(client):
    add_geocode_response(json={"results": []})
    client.geocode("a/b?c#d")
    assert urlparse(responses.calls[0].request.url).path == "/search/2/geocode/a%2Fb%3Fc%23d.json"


def test_geocode_skips_incomplete_suggestions():
    payload = fx.geocode_payload()
    del payload["results"][0]["position"]
    payload["results"][2]["position"]["lat"] = 999
    assert [p.label for p in parse_geocode_response(payload)] == ["Dallas, TX"]


@pytest.mark.parametrize("payload", [None, [], {"results": None}, {"nope": []}])
def test_geocode_rejects_malformed_payload(payload):
    with pytest.raises(errors.ProviderBadResponse):
        parse_geocode_response(payload)


def test_geocode_empty_results_is_not_an_error():
    assert parse_geocode_response({"results": []}) == []


# --- routing request ----------------------------------------------------------

@responses.activate
def test_route_request_parameters(client):
    add_route_response(json=fx.routes_payload())
    client.calculate_routes(DALLAS, DENVER, DEPART)

    url = urlparse(responses.calls[0].request.url)
    assert url.path == "/routing/1/calculateRoute/32.776700,-96.797000:39.739200,-104.990300/json"
    query = parse_qs(url.query)
    assert query["maxAlternatives"] == ["2"]
    assert query["travelMode"] == ["truck"]
    assert query["departAt"] == ["2026-10-25T13:00:00+00:00"]
    assert query["routeRepresentation"] == ["polyline"]
    assert sorted(query["extendedRouteRepresentation"]) == ["distance", "travelTime"]
    # Load weight is cargo, not gross vehicle weight: never sent to the router.
    assert "vehicleWeight" not in query


def test_route_rejects_naive_departure(client):
    with pytest.raises(ValueError):
        client.calculate_routes(DALLAS, DENVER, datetime(2026, 10, 25, 8, 0))


# --- routing response parsing -------------------------------------------------

def test_parse_routes():
    routes = parse_route_response(fx.routes_payload())
    assert len(routes) == 3
    first = routes[0]
    assert first.distance_meters == 1_419_953
    assert first.travel_time_seconds == 42_540
    assert first.traffic_delay_seconds == 71
    assert first.departure_time.isoformat() == "2026-10-25T08:00:00-05:00"
    assert first.arrival_time.isoformat() == "2026-10-25T18:49:00-06:00"
    assert first.points[0] == Coordinate(32.7767, -96.7970)
    assert first.points[-1] == Coordinate(39.7392, -104.9903)
    assert [p.point_index for p in first.progress] == [0, 3]
    assert len({route.route_id for route in routes}) == 3


def test_route_ids_are_stable_across_requests():
    first = [r.route_id for r in parse_route_response(fx.routes_payload())]
    second = [r.route_id for r in parse_route_response(fx.routes_payload())]
    assert first == second
    assert all(route_id.startswith("rt_") for route_id in first)


@pytest.mark.parametrize("count", [1, 2])
def test_fewer_routes_are_returned_as_is(count):
    assert len(parse_route_response(fx.routes_payload(count))) == count


def test_duplicate_geometries_are_collapsed_not_padded():
    payload = fx.routes_payload(1)
    payload["routes"].append(fx.route_json(fx.ROUTE_A_POINTS))
    assert len(parse_route_response(payload)) == 1


def test_progress_is_optional():
    payload = {"routes": [fx.route_json(fx.ROUTE_A_POINTS, progress=False)]}
    assert parse_route_response(payload)[0].progress == ()


def test_points_are_not_deduplicated_so_progress_indices_stay_valid():
    points = [(30.0, -100.0), (30.0, -100.0), (30.1, -100.1)]
    route = parse_route_response({"routes": [fx.route_json(points)]})[0]
    assert len(route.points) == 3
    assert route.progress[-1].point_index == 2


def _mutations():
    def drop(path):
        def apply(route):
            target = route
            for key in path[:-1]:
                target = target[key]
            del target[path[-1]]
        return apply

    def set_value(path, value):
        def apply(route):
            target = route
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
        return apply

    return [
        pytest.param(drop(["summary"]), id="no-summary"),
        pytest.param(drop(["legs"]), id="no-legs"),
        pytest.param(set_value(["legs"], []), id="empty-legs"),
        pytest.param(drop(["summary", "lengthInMeters"]), id="no-length"),
        pytest.param(set_value(["summary", "lengthInMeters"], "far"), id="string-length"),
        pytest.param(set_value(["summary", "travelTimeInSeconds"], 0), id="zero-time"),
        pytest.param(set_value(["summary", "departureTime"], "tomorrow"), id="bad-departure"),
        pytest.param(set_value(["summary", "arrivalTime"], "2026-10-25T18:49:00"), id="naive-arrival"),
        pytest.param(set_value(["legs", 0, "points"], [{"latitude": 1, "longitude": 1}]), id="one-point"),
        pytest.param(set_value(["legs", 0, "points", 1, "latitude"], 123.0), id="lat-out-of-range"),
        pytest.param(set_value(["legs", 0, "points", 1], "x"), id="point-not-object"),
        pytest.param(set_value(["progress", 1, "pointIndex"], 99), id="progress-index-out-of-range"),
        pytest.param(set_value(["progress", 1, "travelTimeInSeconds"], -1), id="progress-not-monotonic"),
        pytest.param(set_value(["progress"], {"a": 1}), id="progress-not-list"),
    ]


@pytest.mark.parametrize("mutate", _mutations())
def test_malformed_routes_are_rejected(mutate):
    payload = fx.routes_payload(1)
    mutate(payload["routes"][0])
    with pytest.raises(errors.ProviderBadResponse):
        parse_route_response(payload)


@pytest.mark.parametrize("payload", [None, [], {"routes": "x"}, {"formatVersion": "0.0.12"}])
def test_malformed_route_payload_rejected(payload):
    with pytest.raises(errors.ProviderBadResponse):
        parse_route_response(payload)


@responses.activate
def test_empty_route_list_is_no_route_found(client):
    add_route_response(json={"routes": []})
    with pytest.raises(errors.NoRouteFound):
        client.calculate_routes(DALLAS, DENVER, DEPART)


# --- HTTP failure mapping -----------------------------------------------------

@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (400, fx.error_payload("NO_ROUTE_FOUND"), errors.NoRouteFound),
        (400, fx.error_payload("MAP_MATCHING_FAILURE"), errors.NoRouteFound),
        (400, fx.error_payload("BAD_INPUT"), errors.ProviderRejectedRequest),
        (400, "not json", errors.ProviderRejectedRequest),
        (401, {"detailedError": {"code": "Unauthorized"}}, errors.ProviderAuthFailed),
        (403, "<xml>Forbidden</xml>", errors.ProviderAuthFailed),
        (429, "<xml>Over quota</xml>", errors.ProviderRateLimited),
        (408, "", errors.ProviderTimeout),
        (504, "", errors.ProviderTimeout),
        (500, fx.error_payload("INTERNAL"), errors.ProviderUnavailable),
        (503, "", errors.ProviderUnavailable),
        (596, "", errors.ProviderUnavailable),
    ],
)
@responses.activate
def test_http_errors_are_mapped(client, status, body, expected):
    if isinstance(body, dict):
        add_route_response(status=status, json=body)
    else:
        add_route_response(status=status, body=body)
    with pytest.raises(expected):
        client.calculate_routes(DALLAS, DENVER, DEPART)


@pytest.mark.parametrize(
    ("exception", "expected"),
    [
        (requests.ConnectTimeout(f"timed out: ...?key={KEY}"), errors.ProviderTimeout),
        (requests.ReadTimeout(f"read timed out ...?key={KEY}"), errors.ProviderTimeout),
        (requests.ConnectionError(f"Max retries exceeded with url: /x?key={KEY}"), errors.ProviderUnavailable),
    ],
)
@responses.activate
def test_transport_errors_are_mapped_without_leaking_key(client, caplog, exception, expected):
    add_route_response(body=exception)
    with pytest.raises(expected) as raised:
        client.calculate_routes(DALLAS, DENVER, DEPART)
    assert KEY not in str(raised.value)
    assert raised.value.__cause__ is None and raised.value.__suppress_context__
    assert KEY not in caplog.text


@responses.activate
def test_non_json_success_is_bad_response(client):
    add_route_response(status=200, body="<html>proxy page</html>")
    with pytest.raises(errors.ProviderBadResponse):
        client.calculate_routes(DALLAS, DENVER, DEPART)


@responses.activate
def test_timeouts_are_explicit(client, monkeypatch):
    seen = {}
    original = requests.Session.get

    def spy(self, url, **kwargs):
        seen["timeout"] = kwargs.get("timeout")
        return original(self, url, **kwargs)

    monkeypatch.setattr(requests.Session, "get", spy)
    add_route_response(json=fx.routes_payload())
    client.calculate_routes(DALLAS, DENVER, DEPART)
    connect, read = seen["timeout"]
    assert 0 < connect <= 5 and 0 < read <= 60

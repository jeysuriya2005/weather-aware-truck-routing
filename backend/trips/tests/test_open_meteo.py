from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pytest
import requests
import responses

from trips.domain.geometry import Coordinate
from trips.providers import errors
from trips.providers.open_meteo import (
    MAX_LOCATIONS_PER_REQUEST,
    OpenMeteoClient,
    forecast_horizon_end,
    parse_forecast_payload,
)

from .open_meteo_fixtures import URL_PATTERN, UNITS, location_payload, mock_open_meteo, open_meteo_calls

START = datetime(2026, 10, 25, 13, tzinfo=timezone.utc)
END = datetime(2026, 10, 25, 16, tzinfo=timezone.utc)
TIMES = [datetime(2026, 10, 25, h, tzinfo=timezone.utc) for h in range(13, 17)]
DENVER = Coordinate(39.74, -104.99)


def windy(lat, lon, t):
    return {"wind_speed_10m": 40.0 + t.hour, "wind_gusts_10m": 60.0, "rain": 0.1, "showers": 0.02, "snowfall": 0.5}


@responses.activate
def test_request_parameters_and_parsing():
    mock_open_meteo(windy)
    series = OpenMeteoClient().fetch_hourly([DENVER, Coordinate(32.78, -96.8)], START, END)

    query = parse_qs(urlparse(open_meteo_calls()[0].request.url).query)
    assert query["latitude"] == ["39.7400,32.7800"]
    assert query["longitude"] == ["-104.9900,-96.8000"]
    assert query["wind_speed_unit"] == ["mph"]
    assert query["precipitation_unit"] == ["inch"]
    assert query["timezone"] == ["GMT"]
    assert query["start_hour"] == ["2026-10-25T13:00"]
    assert query["end_hour"] == ["2026-10-25T16:00"]
    assert set(query["hourly"][0].split(",")) == {"wind_speed_10m", "wind_gusts_10m", "rain", "showers", "snowfall"}
    assert "key" not in query  # Open-Meteo needs no API key

    assert len(series) == 2
    first = series[0][TIMES[1]]
    assert first.wind_mph == 54.0
    assert first.rain_in_per_hr == 0.1 and first.showers_in_per_hr == 0.02
    assert first.snow_in_per_hr == 0.5
    assert list(series[0]) == TIMES


@responses.activate
def test_single_location_object_response():
    mock_open_meteo()
    assert len(OpenMeteoClient().fetch_hourly([DENVER], START, END)) == 1


@responses.activate
def test_locations_are_chunked_and_order_preserved():
    mock_open_meteo(lambda lat, lon, t: {**windy(lat, lon, t), "wind_speed_10m": lat})
    locations = [Coordinate(30 + i * 0.01, -100) for i in range(MAX_LOCATIONS_PER_REQUEST * 2 + 5)]
    series = OpenMeteoClient().fetch_hourly(locations, START, END)
    assert len(open_meteo_calls()) == 3
    assert [s[TIMES[0]].wind_mph for s in series] == pytest.approx([c.lat for c in locations])


def test_empty_locations_make_no_request():
    assert OpenMeteoClient().fetch_hourly([], START, END) == []


def test_null_values_are_preserved_as_missing():
    payload = location_payload(39.74, -104.99, TIMES, windy)
    payload["hourly"]["wind_speed_10m"][2] = None
    payload["hourly"]["snowfall"][3] = None
    series = parse_forecast_payload(payload, 1)[0]
    assert series[TIMES[2]].wind_mph is None
    assert series[TIMES[3]].snow_in_per_hr is None
    assert series[TIMES[1]].wind_mph == 54.0


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda p: p["hourly_units"].update(wind_speed_10m="km/h"), id="wind-in-kmh"),
        pytest.param(lambda p: p["hourly_units"].update(snowfall="cm"), id="snow-in-cm"),
        pytest.param(lambda p: p["hourly_units"].update(rain="mm"), id="rain-in-mm"),
        pytest.param(lambda p: p.pop("hourly_units"), id="no-units"),
        pytest.param(lambda p: p.pop("hourly"), id="no-hourly"),
        pytest.param(lambda p: p["hourly"]["rain"].pop(), id="misaligned-column"),
        pytest.param(lambda p: p["hourly"].pop("showers"), id="missing-column"),
        pytest.param(lambda p: p["hourly"]["time"].__setitem__(0, "noon"), id="bad-time"),
        pytest.param(lambda p: p["hourly"]["rain"].__setitem__(0, "wet"), id="non-numeric"),
    ],
)
def test_malformed_payloads_are_rejected(mutate):
    payload = location_payload(39.74, -104.99, TIMES, windy, units=dict(UNITS))
    mutate(payload)
    with pytest.raises(errors.ProviderBadResponse):
        parse_forecast_payload(payload, 1)


def test_location_count_mismatch_is_rejected():
    payload = [location_payload(39.74, -104.99, TIMES, windy)]
    with pytest.raises(errors.ProviderBadResponse):
        parse_forecast_payload(payload, 2)


@pytest.mark.parametrize(
    ("mock", "expected"),
    [
        ({"status": 400, "json": {"error": True, "reason": "end_hour out of range"}}, errors.ProviderRejectedRequest),
        ({"status": 429, "json": {"error": True, "reason": "limit"}}, errors.ProviderRateLimited),
        ({"status": 500, "body": ""}, errors.ProviderUnavailable),
        ({"status": 200, "body": "<html/>"}, errors.ProviderBadResponse),
        ({"body": requests.ReadTimeout("slow")}, errors.ProviderTimeout),
        ({"body": requests.ConnectionError("down")}, errors.ProviderUnavailable),
    ],
)
@responses.activate
def test_errors_are_mapped(mock, expected):
    responses.add(responses.GET, URL_PATTERN, **mock)
    with pytest.raises(expected) as raised:
        OpenMeteoClient().fetch_hourly([DENVER], START, END)
    assert "weather provider" in raised.value.message


def test_rejects_naive_or_inverted_window():
    with pytest.raises(ValueError):
        OpenMeteoClient().fetch_hourly([DENVER], datetime(2026, 10, 25), END)
    with pytest.raises(ValueError):
        OpenMeteoClient().fetch_hourly([DENVER], END, START)


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        # Verified live on 2026-10-23: end_hour accepted up to 2026-11-07T23:00.
        (datetime(2026, 10, 23, 11, 27, tzinfo=timezone.utc), datetime(2026, 11, 7, 23, tzinfo=timezone.utc)),
        (datetime(2026, 10, 23, 23, 59, tzinfo=timezone.utc), datetime(2026, 11, 7, 23, tzinfo=timezone.utc)),
    ],
)
def test_forecast_horizon_end(now, expected):
    assert forecast_horizon_end(now) == expected

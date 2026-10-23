from datetime import datetime, timedelta, timezone

import pytest
import requests
import responses

from trips.domain.geometry import Coordinate
from trips.providers import errors
from trips.weather import fetch_forecasts, forecast_window, snap

from .open_meteo_fixtures import URL_PATTERN, mock_open_meteo, open_meteo_calls

NOW = datetime(2026, 10, 23, 11, 27, tzinfo=timezone.utc)
CDT = timezone(timedelta(hours=-5))
HORIZON = datetime(2026, 11, 7, 23, tzinfo=timezone.utc)


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def test_window_starts_at_departure_forecast_hour_and_covers_48h():
    departure = datetime(2026, 10, 25, 8, 20, tzinfo=CDT)  # 13:20 UTC
    window = forecast_window(departure, departure + timedelta(hours=12), NOW)
    assert window.start == utc(2026, 10, 25, 14)
    assert window.end == utc(2026, 10, 27, 14)  # whole days, >= 48 h


def test_window_extends_for_long_trips():
    departure = utc(2026, 10, 25, 14)
    window = forecast_window(departure, departure + timedelta(hours=60, minutes=5), NOW)
    assert window.end == utc(2026, 10, 28, 14)
    assert window.contains(utc(2026, 10, 28, 3))


def test_window_is_clamped_to_provider_horizon():
    departure = utc(2026, 11, 6, 10)
    window = forecast_window(departure, departure + timedelta(hours=20), NOW)
    assert window.end == HORIZON
    assert not window.contains(utc(2026, 11, 8, 10))  # later frames stay unavailable


def test_window_none_when_departure_beyond_horizon():
    assert forecast_window(utc(2026, 11, 9, 0), utc(2026, 11, 9, 5), NOW) is None


@pytest.mark.parametrize(
    ("coordinate", "expected"),
    [
        (Coordinate(32.7767, -96.797), Coordinate(32.8, -96.8)),
        (Coordinate(32.724, -96.776), Coordinate(32.7, -96.8)),
        (Coordinate(39.7392, -104.9903), Coordinate(39.75, -105.0)),
    ],
)
def test_snap_to_005_degrees(coordinate, expected):
    assert snap(coordinate) == expected


WINDOW = forecast_window(utc(2026, 10, 25, 14), utc(2026, 10, 25, 20), NOW)
LOCATIONS = [Coordinate(32.8, -96.8), Coordinate(39.75, -105.0)]


@responses.activate
def test_forecasts_are_cached_per_location_and_window():
    mock_open_meteo()
    first = fetch_forecasts(LOCATIONS, WINDOW)
    assert first.fetched_locations == 2 and first.error is None
    second = fetch_forecasts(LOCATIONS + [Coordinate(35.0, -100.0)], WINDOW)
    assert second.cached_locations == 2 and second.fetched_locations == 1
    third_query = open_meteo_calls()[1].request.url
    assert "latitude=35.0000" in third_query and "32.8000" not in third_query
    assert second.sample(LOCATIONS[0], utc(2026, 10, 25, 15)).wind_mph == 8.0


@responses.activate
def test_duplicate_locations_requested_once():
    mock_open_meteo()
    fetch_forecasts(LOCATIONS + LOCATIONS, WINDOW)
    assert open_meteo_calls()[0].request.url.count("32.8000") == 1


@responses.activate
def test_provider_error_is_returned_not_raised():
    responses.add(responses.GET, URL_PATTERN, body=requests.ReadTimeout("slow"))
    result = fetch_forecasts(LOCATIONS, WINDOW)
    assert isinstance(result.error, errors.ProviderTimeout)
    assert result.sample(LOCATIONS[0], utc(2026, 10, 25, 15)) is None


def test_no_window_means_no_request_and_no_data():
    result = fetch_forecasts(LOCATIONS, None)
    assert result.series == {} and result.error is None


@responses.activate
def test_hours_outside_window_are_missing():
    mock_open_meteo()
    result = fetch_forecasts(LOCATIONS, WINDOW)
    assert result.sample(LOCATIONS[0], WINDOW.end + timedelta(hours=1)) is None

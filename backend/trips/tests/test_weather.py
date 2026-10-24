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


# --- Per-plan location budget (Open-Meteo counts every location) --------------

from trips import weather as weather_module  # noqa: E402
from trips.weather import (  # noqa: E402
    LOCATION_BUDGET,
    MAX_HEATMAP_POINTS,
    MIN_HEATMAP_POINTS,
    choose_snap_step,
    heatmap_point_budget,
)


def _line(n, step_deg):
    return [Coordinate(30.0 + i * step_deg, -100.0) for i in range(n)]


def test_snap_step_stays_fine_when_within_budget():
    assert choose_snap_step(_line(100, 0.1), 400) == 0.05


def test_snap_step_coarsens_only_as_much_as_needed():
    # 900 checkpoints ~10 mi apart along an east-west line (like a long 10-mi trip).
    points = [Coordinate(40.0, -170.0 + i * 0.12) for i in range(900)]
    step = choose_snap_step(points, 440)
    assert step > 0.05
    assert len({snap(p, step) for p in points}) <= 440
    finer = weather_module.SNAP_OPTIONS_DEGREES[weather_module.SNAP_OPTIONS_DEGREES.index(step) - 1]
    assert len({snap(p, finer) for p in points}) > 440


@pytest.mark.parametrize(
    ("checkpoint_points", "expected"),
    [(0, MAX_HEATMAP_POINTS), (200, MAX_HEATMAP_POINTS), (350, LOCATION_BUDGET - 350), (480, MIN_HEATMAP_POINTS)],
)
def test_heatmap_gets_remaining_budget(checkpoint_points, expected):
    assert heatmap_point_budget(checkpoint_points) == expected


def _rate_limit_second_chunk(request):
    """First 100-location request succeeds; any request starting at latitude >= 40 gets 429."""
    from urllib.parse import parse_qs, urlparse

    from .open_meteo_fixtures import make_callback

    first_lat = float(parse_qs(urlparse(request.url).query)["latitude"][0].split(",")[0])
    if first_lat >= 40:
        return 429, {"Content-Type": "application/json"}, '{"error": true, "reason": "Minutely API request limit exceeded."}'
    return make_callback()(request)


@responses.activate
def test_rate_limited_chunk_only_blanks_its_own_locations():
    responses.add_callback(responses.GET, URL_PATTERN, callback=_rate_limit_second_chunk)
    locations = [Coordinate(30 + i * 0.1, -100) for i in range(200)]  # chunk 2 starts at lat 40
    result = fetch_forecasts(locations, WINDOW)
    assert isinstance(result.error, errors.ProviderRateLimited)
    assert result.fetched_locations == 100
    assert result.sample(locations[0], utc(2026, 10, 25, 15)) is not None
    assert result.sample(locations[150], utc(2026, 10, 25, 15)) is None  # unknown, not Low

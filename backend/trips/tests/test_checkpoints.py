from datetime import datetime, timedelta, timezone

import pytest

from trips.domain.checkpoints import (
    ETA_SOURCE_PROPORTIONAL,
    ETA_SOURCE_PROVIDER,
    build_timeline,
    checkpoint_miles,
    place_checkpoints,
    segment_bounds,
)
from trips.domain.geometry import Coordinate, cumulative_distances_meters, haversine_meters
from trips.domain.routes import ProgressPoint, RouteOption
from trips.domain.units import meters_to_miles, miles_to_meters

DEPART = datetime(2026, 10, 25, 8, 0, tzinfo=timezone(timedelta(hours=-5)))


def meridian_points(count=151, step=0.01, start_lat=30.0, lon=-100.0):
    return tuple(Coordinate(start_lat + i * step, lon) for i in range(count))


def make_route(points, distance_m=None, travel_s=None, progress=()):
    geometric = cumulative_distances_meters(points)[-1]
    return RouteOption(
        points=tuple(points),
        distance_meters=distance_m or geometric,
        travel_time_seconds=travel_s or 3600.0,
        traffic_delay_seconds=0,
        departure_time=DEPART,
        arrival_time=DEPART + timedelta(seconds=travel_s or 3600.0),
        progress=tuple(progress),
    )


# --- mile markers and segments -----------------------------------------------

@pytest.mark.parametrize(
    ("total", "interval", "expected"),
    [
        (100, 25, [0, 25, 50, 75, 100]),
        (103.6, 25, [0, 25, 50, 75, 100, 103.6]),
        (100.3, 25, [0, 25, 50, 75, 100.3]),  # <0.5 mi tail merges into the last mark
        (7, 10, [0, 7]),
        (0.3, 10, [0, 0.3]),
        (120, 50, [0, 50, 100, 120]),
        (30, 10, [0, 10, 20, 30]),
    ],
)
def test_checkpoint_miles(total, interval, expected):
    assert checkpoint_miles(total, interval) == pytest.approx(expected)


@pytest.mark.parametrize("marks", [[0, 25, 50, 75, 100, 103.6], [0, 7], [0, 10, 20, 30]])
def test_segments_tile_the_route_exactly(marks):
    bounds = segment_bounds(marks)
    assert bounds[0][0] == 0
    assert bounds[-1][1] == marks[-1]
    for (_, end), (start, _) in zip(bounds, bounds[1:]):
        assert end == start  # contiguous, no gaps or overlaps
    assert sum(end - start for start, end in bounds) == pytest.approx(marks[-1])


def test_segment_midpoints():
    assert segment_bounds([0, 25, 50, 53]) == [(0, 12.5), (12.5, 37.5), (37.5, 51.5), (51.5, 53)]


@pytest.mark.parametrize("bad", [0, 15, 30, -10])
def test_rejects_unsupported_intervals(bad):
    with pytest.raises(ValueError):
        place_checkpoints(make_route(meridian_points()), bad)


# --- placement on the road geometry -------------------------------------------

@pytest.mark.parametrize("interval", [10, 25, 50])
def test_represented_miles_sum_to_route_length(interval):
    route = make_route(meridian_points())
    checkpoints = place_checkpoints(route, interval)
    total = meters_to_miles(route.distance_meters)
    assert sum(cp.segment_miles for cp in checkpoints) == pytest.approx(total)
    assert checkpoints[0].mile == 0
    assert checkpoints[-1].mile == pytest.approx(total)


def test_checkpoints_are_at_road_distance_along_geometry():
    points = meridian_points()
    route = make_route(points)
    for cp in place_checkpoints(route, 25):
        along = haversine_meters(points[0], cp.coordinate)  # straight meridian: along == chord
        assert meters_to_miles(along) == pytest.approx(cp.mile, abs=0.01)
        assert cp.coordinate.lon == pytest.approx(-100.0)


def test_checkpoints_follow_bends_not_straight_line():
    # L-shaped road: north 1 degree, then east 1 degree.
    north = [Coordinate(30 + i * 0.01, -100) for i in range(101)]
    east = [Coordinate(31, -100 + i * 0.01) for i in range(1, 101)]
    route = make_route(north + east)
    for cp in place_checkpoints(route, 10):
        on_north_leg = abs(cp.coordinate.lon + 100) < 1e-9
        on_east_leg = abs(cp.coordinate.lat - 31) < 1e-9
        assert on_north_leg or on_east_leg, cp


def test_mile_markers_use_provider_distance_scale():
    points = meridian_points()
    geometric = cumulative_distances_meters(points)[-1]
    route = make_route(points, distance_m=geometric * 1.05)  # provider reports 5% longer road
    checkpoints = place_checkpoints(route, 25)
    assert checkpoints[-1].mile == pytest.approx(meters_to_miles(geometric * 1.05))
    # Placement still lands on the geometry, proportionally.
    mid = next(cp for cp in checkpoints if cp.mile == 50)
    assert meters_to_miles(haversine_meters(points[0], mid.coordinate)) == pytest.approx(50 / 1.05, abs=0.01)


# --- arrival times --------------------------------------------------------------

def test_eta_follows_provider_timing_anchors():
    points = meridian_points()  # ~103.6 mi
    route_m = cumulative_distances_meters(points)
    half_m = route_m[75]
    total_m = route_m[-1]
    slow_s = meters_to_miles(half_m) / 30 * 3600  # first half at 30 mph
    fast_s = meters_to_miles(total_m - half_m) / 60 * 3600  # second half at 60 mph
    route = make_route(
        points,
        travel_s=slow_s + fast_s,
        progress=[
            ProgressPoint(0, 0, 0),
            ProgressPoint(75, slow_s, half_m),
            ProgressPoint(150, slow_s + fast_s, total_m),
        ],
    )
    timeline = build_timeline(route)
    assert timeline.eta_source == ETA_SOURCE_PROVIDER
    by_mile = {round(cp.mile): cp for cp in place_checkpoints(route, 25, timeline)}

    assert by_mile[25].elapsed_seconds == pytest.approx(25 / 30 * 3600, rel=1e-6)
    half_mi = meters_to_miles(half_m)
    assert by_mile[75].elapsed_seconds == pytest.approx(slow_s + (75 - half_mi) / 60 * 3600, rel=1e-6)
    assert by_mile[75].eta == DEPART + timedelta(seconds=by_mile[75].elapsed_seconds)
    assert by_mile[0].eta == DEPART


def test_eta_falls_back_to_proportional_without_progress():
    route = make_route(meridian_points(), travel_s=7200)
    timeline = build_timeline(route)
    assert timeline.eta_source == ETA_SOURCE_PROPORTIONAL
    checkpoints = place_checkpoints(route, 25, timeline)
    total = meters_to_miles(route.distance_meters)
    for cp in checkpoints:
        assert cp.elapsed_seconds == pytest.approx(7200 * cp.mile / total, rel=1e-6)
    assert checkpoints[-1].eta == DEPART + timedelta(seconds=7200)


def test_etas_are_monotonic_and_timezone_aware():
    route = make_route(meridian_points(), travel_s=5000)
    etas = [cp.eta for cp in place_checkpoints(route, 10)]
    assert etas == sorted(etas)
    assert all(eta.tzinfo is not None for eta in etas)


def test_duplicate_points_do_not_break_interpolation():
    points = list(meridian_points(count=11))
    points.insert(5, points[5])  # zero-length span, as TomTom geometry can contain
    route = make_route(points, progress=[ProgressPoint(0, 0, 0)])
    checkpoints = place_checkpoints(route, 10)
    assert checkpoints[-1].mile == pytest.approx(meters_to_miles(route.distance_meters))


def test_miles_helpers_round_trip():
    assert meters_to_miles(miles_to_meters(25)) == pytest.approx(25)

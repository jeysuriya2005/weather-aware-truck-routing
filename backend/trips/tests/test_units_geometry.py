import math
import time

import pytest

from trips.domain.geometry import Coordinate, simplify_polyline
from trips.domain.units import kmh_to_mph, meters_to_miles, miles_to_meters


@pytest.mark.parametrize(
    ("meters", "miles"),
    [
        (0, 0),
        (1609.344, 1),
        (16_093.44, 10),
        (40_233.6, 25),
        (80_467.2, 50),
        (1_419_953, 882.3179),  # real Dallas -> Denver TomTom route length
    ],
)
def test_meters_to_miles(meters, miles):
    assert meters_to_miles(meters) == pytest.approx(miles, abs=1e-4)


@pytest.mark.parametrize("miles", [0, 0.5, 10, 25, 50, 1234.5])
def test_miles_meters_round_trip(miles):
    assert meters_to_miles(miles_to_meters(miles)) == pytest.approx(miles)


@pytest.mark.parametrize(("kmh", "mph"), [(0, 0), (1.609344, 1), (40.2336, 25), (88.51392, 55)])
def test_kmh_to_mph(kmh, mph):
    assert kmh_to_mph(kmh) == pytest.approx(mph)


@pytest.mark.parametrize(("lat", "lon"), [(91, 0), (-91, 0), (0, 181), (0, -181), (math.nan, 0)])
def test_coordinate_rejects_out_of_range(lat, lon):
    with pytest.raises(ValueError):
        Coordinate(lat, lon)


def test_simplify_removes_collinear_points_and_keeps_endpoints():
    points = [Coordinate(0, x / 10) for x in range(11)]
    assert simplify_polyline(points, 0.0001) == [points[0], points[-1]]


def test_simplify_keeps_significant_corners():
    points = [Coordinate(0, 0), Coordinate(0, 1), Coordinate(1, 1), Coordinate(1, 2)]
    assert simplify_polyline(points, 0.01) == points


def test_simplify_respects_tolerance():
    points = [Coordinate(0, 0), Coordinate(0.00005, 0.5), Coordinate(0, 1)]
    assert simplify_polyline(points, 0.0001) == [points[0], points[2]]
    assert simplify_polyline(points, 0.00001) == points


@pytest.mark.parametrize("count", [0, 1, 2])
def test_simplify_short_lines_unchanged(count):
    points = [Coordinate(0, i) for i in range(count)]
    assert simplify_polyline(points, 1) == points


def test_simplify_long_curved_route_quickly():
    # ~20k points along a gently winding road, larger than real TomTom
    # cross-country routes (~10k points, ~50 ms measured).
    points = [Coordinate(30 + math.sin(i / 500) * 2, -100 + i * 0.001) for i in range(20_000)]
    started = time.perf_counter()
    simplified = simplify_polyline(points, 0.0002)
    assert time.perf_counter() - started < 5
    assert simplified[0] == points[0] and simplified[-1] == points[-1]
    assert len(simplified) < len(points) // 10


def test_simplify_rejects_negative_tolerance():
    with pytest.raises(ValueError):
        simplify_polyline([Coordinate(0, 0)] * 3, -1)

import time

import pytest

from trips.domain.corridor import SPACING_OPTIONS_DEGREES, corridor_grid, resample
from trips.domain.geometry import Coordinate, haversine_meters


def line(start, end, steps=400):
    return [
        Coordinate(start[0] + (end[0] - start[0]) * i / steps, start[1] + (end[1] - start[1]) * i / steps)
        for i in range(steps + 1)
    ]


DALLAS_DENVER = line((32.78, -96.80), (39.74, -104.99))
DALLAS_DENVER_ALT = line((32.78, -96.80), (35.2, -101.8)) + line((35.2, -101.8), (39.74, -104.99))[1:]


def test_resample_spacing():
    samples = resample(line((30, -100), (31, -100)), 10_000)
    gaps = [haversine_meters(a, b) for a, b in zip(samples, samples[1:])]
    assert all(gap <= 10_000.1 for gap in gaps)
    assert samples[0] == Coordinate(30, -100) and samples[-1] == Coordinate(31, -100)


@pytest.mark.parametrize("budget", [50, 120, 200])
def test_grid_respects_budget(budget):
    grid = corridor_grid([DALLAS_DENVER, DALLAS_DENVER_ALT], max_points=budget)
    assert 0 < len(grid.points) <= budget
    assert grid.spacing_degrees in SPACING_OPTIONS_DEGREES


def test_grid_is_lattice_aligned_and_deterministic():
    first = corridor_grid([DALLAS_DENVER])
    second = corridor_grid([DALLAS_DENVER])
    assert first == second
    s = first.spacing_degrees
    for p in first.points:
        assert abs(p.lat / s - round(p.lat / s)) < 1e-6
        assert abs(p.lon / s - round(p.lon / s)) < 1e-6


def test_every_route_point_is_covered_by_a_nearby_cell():
    grid = corridor_grid([DALLAS_DENVER, DALLAS_DENVER_ALT])
    cell_km = grid.spacing_degrees * 111.32
    for point in DALLAS_DENVER[::20] + DALLAS_DENVER_ALT[::20]:
        nearest = min(haversine_meters(point, cell) for cell in grid.points)
        assert nearest / 1000 <= cell_km  # a cell centre within one cell width


def test_cells_stay_within_the_corridor():
    grid = corridor_grid([DALLAS_DENVER])
    reach_km = max(30, grid.spacing_degrees * 111.32 * 0.75)
    samples = resample(DALLAS_DENVER, 2_000)
    for cell in grid.points[::5]:
        assert min(haversine_meters(cell, p) for p in samples) / 1000 <= reach_km + 2


def test_short_trip_gets_finest_grid():
    grid = corridor_grid([line((32.78, -96.80), (33.0, -97.0), steps=20)])
    assert grid.spacing_degrees == SPACING_OPTIONS_DEGREES[0]


def test_long_trip_gets_coarser_grid_quickly():
    coast_to_coast = line((34.05, -118.24), (40.71, -74.0), steps=10_000)
    started = time.perf_counter()
    grid = corridor_grid([coast_to_coast])
    assert time.perf_counter() - started < 5
    assert grid.spacing_degrees > SPACING_OPTIONS_DEGREES[0]
    assert len(grid.points) <= 200


def test_rejects_bad_input():
    with pytest.raises(ValueError):
        corridor_grid([])
    with pytest.raises(ValueError):
        corridor_grid([DALLAS_DENVER], max_points=0)

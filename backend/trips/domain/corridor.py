"""
Bounded sampling grid for the weather heatmap along the trip corridor.

Grid cells are aligned to a fixed lattice (multiples of the spacing in
degrees), so the same area always produces the same sample coordinates,
which keeps forecasts cacheable. The finest spacing that keeps the number
of cells within `max_points` is chosen, which bounds the forecast cost.
`max_points` is a hard cap: the weather provider counts every location
against a per-minute limit, so exceeding it fails the request.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from .geometry import Coordinate, cumulative_distances_meters, haversine_meters, interpolate

SPACING_OPTIONS_DEGREES = (0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.75, 1.0, 1.5, 2.0)
DEFAULT_MAX_POINTS = 200
DEFAULT_HALF_WIDTH_KM = 30.0
KM_PER_DEGREE_LAT = 111.32


@dataclass(frozen=True)
class CorridorGrid:
    spacing_degrees: float
    points: list[Coordinate]


def resample(points: Sequence[Coordinate], step_m: float) -> list[Coordinate]:
    """Points every `step_m` metres along a polyline (plus both ends)."""
    if len(points) < 2:
        return list(points)
    cumulative = cumulative_distances_meters(points)
    samples = [points[0]]
    target, i = step_m, 1
    while target < cumulative[-1]:
        while cumulative[i] < target:
            i += 1
        span = cumulative[i] - cumulative[i - 1]
        fraction = (target - cumulative[i - 1]) / span if span else 0.0
        samples.append(interpolate(points[i - 1], points[i], fraction))
        target += step_m
    samples.append(points[-1])
    return samples


def _cells(samples: list[Coordinate], spacing: float, half_width_km: float) -> set[tuple[int, int]]:
    cell_km = spacing * KM_PER_DEGREE_LAT
    reach_km = max(half_width_km, cell_km * 0.75)
    cells: set[tuple[int, int]] = set()
    for point in samples:
        row, col = round(point.lat / spacing), round(point.lon / spacing)
        lat_steps = math.ceil(reach_km / cell_km)
        lon_steps = math.ceil(reach_km / (cell_km * max(math.cos(math.radians(point.lat)), 0.1)))
        for dr in range(-lat_steps, lat_steps + 1):
            for dc in range(-lon_steps, lon_steps + 1):
                cell = (row + dr, col + dc)
                if cell in cells:
                    continue
                center = Coordinate(cell[0] * spacing, cell[1] * spacing)
                if haversine_meters(center, point) <= reach_km * 1000:
                    cells.add(cell)
    return cells


def corridor_grid(
    routes: Sequence[Sequence[Coordinate]],
    max_points: int = DEFAULT_MAX_POINTS,
    half_width_km: float = DEFAULT_HALF_WIDTH_KM,
) -> CorridorGrid:
    if not routes:
        raise ValueError("At least one route is required")
    if max_points < 1:
        raise ValueError("max_points must be positive")

    # Sample routes densely enough for the finest spacing; reused for every option.
    step_m = min(SPACING_OPTIONS_DEGREES[0] * KM_PER_DEGREE_LAT * 1000 / 2, half_width_km * 1000)
    samples = [point for route in routes for point in resample(route, step_m)]

    cells: set[tuple[int, int]] = set()
    spacing = SPACING_OPTIONS_DEGREES[-1]
    for option in SPACING_OPTIONS_DEGREES:
        cells = _cells(samples, option, half_width_km)
        spacing = option
        if len(cells) <= max_points:
            break

    ordered = sorted(cells)
    if len(ordered) > max_points:
        # Even the coarsest spacing is too many cells (very wide, multi-route,
        # continent-scale corridors). Thin evenly so coverage stays spread over
        # the whole corridor while the provider's location limit is respected.
        stride = len(ordered) / max_points
        ordered = [ordered[int(i * stride)] for i in range(max_points)]
    points = [Coordinate(round(r * spacing, 6), round(c * spacing, 6)) for r, c in ordered]
    return CorridorGrid(spacing_degrees=spacing, points=points)

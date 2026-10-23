"""Geometry helpers that do not depend on any provider."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

EARTH_RADIUS_METERS = 6_371_008.8  # IUGG mean radius


@dataclass(frozen=True)
class Coordinate:
    lat: float
    lon: float

    def __post_init__(self) -> None:
        if not (-90.0 <= self.lat <= 90.0) or not (-180.0 <= self.lon <= 180.0):
            raise ValueError(f"Coordinate out of range: {self.lat}, {self.lon}")


def haversine_meters(a: Coordinate, b: Coordinate) -> float:
    """Great-circle distance between two coordinates."""
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    dlat = lat2 - lat1
    dlon = math.radians(b.lon - a.lon)
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_METERS * math.asin(min(1.0, math.sqrt(h)))


def cumulative_distances_meters(points: Sequence[Coordinate]) -> list[float]:
    """Running great-circle distance along a polyline, starting at 0."""
    distances = [0.0]
    for previous, current in zip(points, points[1:]):
        distances.append(distances[-1] + haversine_meters(previous, current))
    return distances


def interpolate(a: Coordinate, b: Coordinate, fraction: float) -> Coordinate:
    """Linear interpolation; adequate for the short spans between route vertices."""
    return Coordinate(a.lat + (b.lat - a.lat) * fraction, a.lon + (b.lon - a.lon) * fraction)


def _perpendicular_distance(point: Coordinate, start: Coordinate, end: Coordinate) -> float:
    """Distance in degrees from point to the segment start-end (planar approximation)."""
    dx, dy = end.lon - start.lon, end.lat - start.lat
    if dx == 0 and dy == 0:
        return ((point.lon - start.lon) ** 2 + (point.lat - start.lat) ** 2) ** 0.5
    t = ((point.lon - start.lon) * dx + (point.lat - start.lat) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    px, py = start.lon + t * dx, start.lat + t * dy
    return ((point.lon - px) ** 2 + (point.lat - py) ** 2) ** 0.5


def simplify_polyline(points: Sequence[Coordinate], tolerance_degrees: float) -> list[Coordinate]:
    """
    Ramer-Douglas-Peucker simplification, used only to shrink the geometry
    sent to the browser for drawing. Distance and checkpoint calculations
    always use the full provider geometry.

    Iterative (no recursion limit on long routes). Always keeps both endpoints.
    """
    if tolerance_degrees < 0:
        raise ValueError("tolerance_degrees must be non-negative")
    if len(points) < 3:
        return list(points)

    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        max_distance, index = -1.0, first
        for i in range(first + 1, last):
            distance = _perpendicular_distance(points[i], points[first], points[last])
            if distance > max_distance:
                max_distance, index = distance, i
        if max_distance > tolerance_degrees:
            keep[index] = True
            stack.append((first, index))
            stack.append((index, last))

    return [point for point, kept in zip(points, keep) if kept]

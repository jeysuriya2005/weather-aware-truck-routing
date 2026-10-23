"""Provider-neutral route data, as returned by any routing provider client."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime

from .geometry import Coordinate


@dataclass(frozen=True)
class ProgressPoint:
    """Cumulative travel time and distance at a geometry point index."""

    point_index: int
    travel_time_seconds: float
    distance_meters: float


@dataclass(frozen=True)
class RouteOption:
    points: tuple[Coordinate, ...]
    distance_meters: float
    travel_time_seconds: float
    traffic_delay_seconds: float
    departure_time: datetime
    arrival_time: datetime
    # Provider timing along the geometry; used for checkpoint ETAs (Phase 3).
    progress: tuple[ProgressPoint, ...] = ()

    @property
    def route_id(self) -> str:
        """
        Stable identifier derived from the route's geometry: the same road path
        gets the same id across repeated requests, independent of list order.
        """
        digest = hashlib.sha256()
        for point in self.points:
            digest.update(f"{point.lat:.5f},{point.lon:.5f};".encode())
        return f"rt_{digest.hexdigest()[:12]}"


@dataclass(frozen=True)
class Place:
    """A geocoding suggestion."""

    id: str
    label: str
    coordinate: Coordinate
    kind: str

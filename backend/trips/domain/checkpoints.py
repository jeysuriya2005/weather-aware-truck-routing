"""
Weather checkpoints along a route's real road geometry, with arrival times.

Placement: a checkpoint at every `interval` miles of road distance from the
origin (mile 0), plus one at the destination.

Represented distance: each checkpoint stands for the road from the midpoint
with its previous checkpoint to the midpoint with its next one. The origin
checkpoint starts at mile 0 and the destination checkpoint ends at the route
length. The segments therefore tile the route exactly, and risk miles add up
to the route distance rather than to a checkpoint count.

Distances use the routing provider's own scale (TomTom lengthInMeters and
progress distances), so checkpoint mile markers agree with the route
summary. Arrival times come from the provider's cumulative travel-time
anchors (TomTom `progress`), interpolated by road distance between anchors.
Without anchors, time is spread in proportion to distance and the result
is flagged.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import datetime, timedelta

from .geometry import Coordinate, cumulative_distances_meters, interpolate
from .routes import ProgressPoint, RouteOption
from .units import meters_to_miles, miles_to_meters

SUPPORTED_INTERVALS_MILES = (10, 25, 50)
# A destination closer than this to the last regular checkpoint replaces it,
# so no checkpoint stands for a sliver of road.
MIN_FINAL_GAP_MILES = 0.5

ETA_SOURCE_PROVIDER = "provider_timing"
ETA_SOURCE_PROPORTIONAL = "proportional_estimate"


@dataclass(frozen=True)
class Checkpoint:
    index: int
    coordinate: Coordinate
    mile: float
    segment_start_mile: float
    segment_end_mile: float
    eta: datetime
    elapsed_seconds: float

    @property
    def segment_miles(self) -> float:
        return self.segment_end_mile - self.segment_start_mile


@dataclass(frozen=True)
class RouteTimeline:
    """Provider distance (m) and elapsed time (s) at every geometry point."""

    distances_m: list[float]
    elapsed_s: list[float]
    eta_source: str


def build_timeline(route: RouteOption) -> RouteTimeline:
    points = route.points
    geometric = cumulative_distances_meters(points)
    last = len(points) - 1

    anchors: list[ProgressPoint] = list(route.progress)
    eta_source = ETA_SOURCE_PROVIDER if len(anchors) >= 2 else ETA_SOURCE_PROPORTIONAL
    # Always pin both ends to the route summary.
    if not anchors or anchors[0].point_index != 0:
        anchors.insert(0, ProgressPoint(0, 0.0, 0.0))
    if anchors[-1].point_index != last:
        anchors.append(ProgressPoint(last, route.travel_time_seconds, route.distance_meters))

    distances = [0.0] * len(points)
    elapsed = [0.0] * len(points)
    for start, end in zip(anchors, anchors[1:]):
        span_geo = geometric[end.point_index] - geometric[start.point_index]
        span_points = end.point_index - start.point_index
        for i in range(start.point_index, end.point_index + 1):
            if span_geo > 0:
                fraction = (geometric[i] - geometric[start.point_index]) / span_geo
            else:
                fraction = (i - start.point_index) / span_points if span_points else 0.0
            distances[i] = start.distance_meters + fraction * (end.distance_meters - start.distance_meters)
            elapsed[i] = start.travel_time_seconds + fraction * (
                end.travel_time_seconds - start.travel_time_seconds
            )
    return RouteTimeline(distances_m=distances, elapsed_s=elapsed, eta_source=eta_source)


def checkpoint_miles(total_miles: float, interval_miles: float) -> list[float]:
    """Mile markers: 0, interval, 2*interval, ..., and the destination."""
    if interval_miles <= 0:
        raise ValueError("interval_miles must be positive")
    if total_miles <= 0:
        raise ValueError("total_miles must be positive")
    marks = [0.0]
    mile = interval_miles
    while mile < total_miles:
        marks.append(mile)
        mile += interval_miles
    if total_miles - marks[-1] < MIN_FINAL_GAP_MILES and len(marks) > 1:
        marks[-1] = total_miles
    else:
        marks.append(total_miles)
    return marks


def segment_bounds(marks: list[float]) -> list[tuple[float, float]]:
    """Midpoint boundaries so that the segments tile [0, last mark] exactly."""
    bounds = []
    for i, mark in enumerate(marks):
        start = 0.0 if i == 0 else (marks[i - 1] + mark) / 2
        end = marks[-1] if i == len(marks) - 1 else (mark + marks[i + 1]) / 2
        bounds.append((start, end))
    return bounds


def _locate(route: RouteOption, timeline: RouteTimeline, target_m: float) -> tuple[Coordinate, float]:
    distances = timeline.distances_m
    target_m = min(max(target_m, 0.0), distances[-1])
    i = bisect.bisect_left(distances, target_m)
    if i <= 0:
        return route.points[0], timeline.elapsed_s[0]
    if i >= len(distances):
        return route.points[-1], timeline.elapsed_s[-1]
    span = distances[i] - distances[i - 1]
    fraction = (target_m - distances[i - 1]) / span if span > 0 else 1.0
    coordinate = interpolate(route.points[i - 1], route.points[i], fraction)
    elapsed = timeline.elapsed_s[i - 1] + fraction * (timeline.elapsed_s[i] - timeline.elapsed_s[i - 1])
    return coordinate, elapsed


def place_checkpoints(
    route: RouteOption, interval_miles: float, timeline: RouteTimeline | None = None
) -> list[Checkpoint]:
    if interval_miles not in SUPPORTED_INTERVALS_MILES:
        raise ValueError(f"interval_miles must be one of {SUPPORTED_INTERVALS_MILES}")
    timeline = timeline or build_timeline(route)
    total_miles = meters_to_miles(timeline.distances_m[-1])
    marks = checkpoint_miles(total_miles, interval_miles)

    checkpoints = []
    for index, (mark, (start, end)) in enumerate(zip(marks, segment_bounds(marks))):
        coordinate, elapsed = _locate(route, timeline, miles_to_meters(mark))
        checkpoints.append(
            Checkpoint(
                index=index,
                coordinate=coordinate,
                mile=mark,
                segment_start_mile=start,
                segment_end_mile=end,
                eta=route.departure_time + timedelta(seconds=elapsed),
                elapsed_seconds=elapsed,
            )
        )
    return checkpoints

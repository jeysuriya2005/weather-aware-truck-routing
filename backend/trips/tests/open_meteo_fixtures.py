"""
Open-Meteo mock: builds responses with the live API's structure (checked
2026-10-23) from the request's own latitude/longitude/start_hour/end_hour,
so tests can describe weather as a function of place and time.
"""

import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import responses

URL_PATTERN = re.compile(re.escape("https://api.open-meteo.com/v1/forecast") + ".*")
UNITS = {
    "time": "unixtime",
    "wind_speed_10m": "mp/h",
    "wind_gusts_10m": "mp/h",
    "rain": "inch",
    "showers": "inch",
    "snowfall": "inch",
}


def calm(lat, lon, time):
    return {"wind_speed_10m": 8.0, "wind_gusts_10m": 14.0, "rain": 0.0, "showers": 0.0, "snowfall": 0.0}


def location_payload(lat, lon, times, weather, units=None):
    rows = [weather(lat, lon, t) for t in times]
    hourly = {"time": [int(t.timestamp()) for t in times]}
    for variable in ("wind_speed_10m", "wind_gusts_10m", "rain", "showers", "snowfall"):
        hourly[variable] = [row[variable] for row in rows]
    return {
        "latitude": lat,
        "longitude": lon,
        "utc_offset_seconds": 0,
        "timezone": "GMT",
        "hourly_units": units or UNITS,
        "hourly": hourly,
    }


def _hours(start: str, end: str):
    first = datetime.strptime(start, "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
    last = datetime.strptime(end, "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
    times, t = [], first
    while t <= last:
        times.append(t)
        t += timedelta(hours=1)
    return times


def make_callback(weather=calm, units=None):
    def callback(request):
        query = parse_qs(urlparse(request.url).query)
        lats = [float(v) for v in query["latitude"][0].split(",")]
        lons = [float(v) for v in query["longitude"][0].split(",")]
        times = _hours(query["start_hour"][0], query["end_hour"][0])
        items = [location_payload(lat, lon, times, weather, units) for lat, lon in zip(lats, lons)]
        body = items[0] if len(items) == 1 else items
        return 200, {"Content-Type": "application/json"}, json.dumps(body)

    return callback


def mock_open_meteo(weather=calm, units=None):
    responses.add_callback(responses.GET, URL_PATTERN, callback=make_callback(weather, units))


def open_meteo_calls():
    return [call for call in responses.calls if "open-meteo" in call.request.url]

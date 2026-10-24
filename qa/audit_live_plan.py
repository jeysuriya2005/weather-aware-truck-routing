"""
Independent live data audit for POST /api/trips/plan/.

Plans one real trip through a running backend, then re-derives every value it
can WITHOUT importing application code:

* unit conversions, checkpoint spacing, segment tiling, ETA consistency;
* each checkpoint's forecast, re-fetched directly from Open-Meteo at the same
  snapped location and the same hour (the app snaps checkpoint lookups to 0.05 deg);
* risk levels, re-implemented here from the assessment PDF table;
* route summaries, ranking order, decided-by criterion and explanation numbers;
* heatmap frame times, a sample of heatmap cells against Open-Meteo, and every
  heatmap cell's risk code against its own reported wind/rain/snow values.

Usage (backend must be running with a TomTom key; Open-Meteo needs no key):
    backend\\.venv\\Scripts\\python.exe qa\\audit_live_plan.py [--api http://127.0.0.1:8000]
        [--origin LAT,LON] [--destination LAT,LON] [--load 42000] [--interval 25] [--out plan.json]

Uses only the Python standard library. Makes 1 backend request (1 TomTom routing call,
a few Open-Meteo calls) plus 2-3 direct Open-Meteo requests.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

METERS_PER_MILE = 1609.344
LEVELS = ["low", "moderate", "high", "severe", "no_travel"]
SCORE = {code: i for i, code in enumerate(LEVELS)}
OPEN_METEO = "https://api.open-meteo.com/v1/forecast"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, bool(ok), detail))
    return bool(ok)


# --- independent re-implementation of the assessment rules -------------------

def wind_level(mph: float, load_lb: float) -> tuple[str, str]:
    base = ("no_travel" if mph >= 55 else "severe" if mph >= 45 else "high" if mph >= 35
            else "moderate" if mph >= 25 else "low")
    adjusted = base
    if base == "severe" and load_lb > 30_000:
        adjusted = "no_travel"
    elif base == "high" and load_lb > 40_000:
        adjusted = "severe"
    return base, adjusted


def rain_level(inches: float) -> str:
    return ("no_travel" if inches > 1.0 else "severe" if inches >= 0.5 else "high" if inches >= 0.25
            else "moderate" if inches >= 0.10 else "low")


def snow_level(inches: float) -> str:
    return ("no_travel" if inches > 3.0 else "severe" if inches >= 2.0 else "high" if inches >= 1.0
            else "moderate" if inches >= 0.5 else "low")


def overall(levels: list[str]) -> str:
    return max(levels, key=lambda code: SCORE[code])


def hour_containing(moment: datetime) -> datetime:
    utc = moment.astimezone(timezone.utc)
    floored = utc.replace(minute=0, second=0, microsecond=0)
    return floored if floored == utc else floored + timedelta(hours=1)


def snap(value: float, step: float = 0.05) -> float:
    return round(round(value / step) * step, 4)


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2
    return 2 * 6_371_008.8 * math.asin(min(1.0, math.sqrt(h)))


def point_to_polyline_m(point: tuple[float, float], line: list[list[float]]) -> float:
    """Approximate min distance (m) from a lat/lon point to a [lon, lat] polyline."""
    best = math.inf
    for (lon1, lat1), (lon2, lat2) in zip(line, line[1:]):
        for t in (0.0, 0.25, 0.5, 0.75, 1.0):
            best = min(best, haversine_m(point, (lat1 + (lat2 - lat1) * t, lon1 + (lon2 - lon1) * t)))
        # exact projection in a local planar frame
        kx = math.cos(math.radians(point[0]))
        dx, dy = (lon2 - lon1) * kx, lat2 - lat1
        if dx or dy:
            t = max(0.0, min(1.0, (((point[1] - lon1) * kx) * dx + (point[0] - lat1) * dy) / (dx * dx + dy * dy)))
            best = min(best, haversine_m(point, (lat1 + dy * t, lon1 + (lon2 - lon1) * t)))
    return best


# --- HTTP helpers ------------------------------------------------------------------

def post_json(url: str, body: dict) -> dict:
    request = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.load(response)


def open_meteo(points: list[tuple[float, float]], start: datetime, end: datetime) -> list[dict]:
    """Direct Open-Meteo fetch (same variables/units the app requests). Returns list per point."""
    out = []
    for i in range(0, len(points), 100):
        chunk = points[i:i + 100]
        query = urllib.parse.urlencode({
            "latitude": ",".join(f"{lat:.4f}" for lat, _ in chunk),
            "longitude": ",".join(f"{lon:.4f}" for _, lon in chunk),
            "hourly": "wind_speed_10m,wind_gusts_10m,rain,showers,snowfall",
            "wind_speed_unit": "mph", "precipitation_unit": "inch",
            "timezone": "GMT", "timeformat": "unixtime",
            "start_hour": start.strftime("%Y-%m-%dT%H:%M"), "end_hour": end.strftime("%Y-%m-%dT%H:%M"),
        })
        # Open-Meteo counts every location in a request against its 600/min limit
        # (observed 2026-10-24), so back off and retry on HTTP 429.
        for attempt in range(4):
            try:
                with urllib.request.urlopen(f"{OPEN_METEO}?{query}", timeout=60) as response:
                    payload = json.load(response)
                break
            except urllib.error.HTTPError as error:
                if error.code != 429 or attempt == 3:
                    raise
                print("  (Open-Meteo minute limit reached; waiting 61 s)", file=sys.stderr)
                time.sleep(61)
        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            units = item["hourly_units"]
            assert units["wind_speed_10m"] == "mp/h" and units["snowfall"] == "inch", units
            hourly = item["hourly"]
            out.append({t: {k: hourly[k][j] for k in hourly if k != "time"} for j, t in enumerate(hourly["time"])})
    return out


# --- audit sections -------------------------------------------------------------------

def audit_routes(plan: dict, interval: int) -> None:
    for route in plan["routes"]:
        name = route["label"]
        cps = route["checkpoints"]
        dep, arr = datetime.fromisoformat(route["departure_time"]), datetime.fromisoformat(route["arrival_time"])
        check(f"{name}: distance_miles = meters / 1609.344 (1 dp)",
              abs(route["distance_miles"] - round(route["distance_meters"] / METERS_PER_MILE, 1)) < 1e-9,
              f'{route["distance_meters"]} m -> {route["distance_miles"]} mi')
        check(f"{name}: duration = arrival - departure",
              abs((arr - dep).total_seconds() - route["duration_seconds"]) <= 1,
              f'{route["duration_seconds"]} s vs {(arr - dep).total_seconds()} s')
        coords = route["geometry"]["coordinates"]
        check(f"{name}: geometry starts at origin / ends at destination (< 2 km)",
              haversine_m((coords[0][1], coords[0][0]), (plan["inputs"]["origin"]["lat"], plan["inputs"]["origin"]["lon"])) < 2000
              and haversine_m((coords[-1][1], coords[-1][0]),
                              (plan["inputs"]["destination"]["lat"], plan["inputs"]["destination"]["lon"])) < 2000)
        geo_len_mi = sum(haversine_m((a[1], a[0]), (b[1], b[0])) for a, b in zip(coords, coords[1:])) / METERS_PER_MILE
        check(f"{name}: provider distance vs geometry length within 2%",
              abs(geo_len_mi - route["distance_miles"]) / route["distance_miles"] < 0.02,
              f"geometry {geo_len_mi:.1f} mi vs provider {route['distance_miles']} mi")

        expected_count = math.ceil(route["distance_meters"] / METERS_PER_MILE / interval) + 1
        tail = route["distance_meters"] / METERS_PER_MILE - (expected_count - 2) * interval
        if 0 < tail < 0.5:
            expected_count -= 1
        check(f"{name}: checkpoint count for {interval} mi interval", len(cps) == expected_count,
              f"{len(cps)} vs expected {expected_count}")
        marks_ok = all(abs(cp["mile"] - i * interval) < 1e-6 for i, cp in enumerate(cps[:-1]))
        check(f"{name}: checkpoints every {interval} mi from mile 0, last at route end",
              marks_ok and abs(cps[-1]["mile"] - route["distance_meters"] / METERS_PER_MILE) < 0.01)
        tiles = all(abs(a["segment_end_mile"] - b["segment_start_mile"]) < 1e-6 for a, b in zip(cps, cps[1:]))
        check(f"{name}: segments contiguous, start 0, end at route length",
              tiles and cps[0]["segment_start_mile"] == 0
              and abs(cps[-1]["segment_end_mile"] - route["distance_meters"] / METERS_PER_MILE) < 0.01)
        total = sum(cp["segment_miles"] for cp in cps)
        check(f"{name}: sum of segment miles = route miles",
              abs(total - route["distance_meters"] / METERS_PER_MILE) < 0.01, f"{total:.3f} vs {route['distance_miles']}")
        # `mile` is rounded to 2 dp and segment bounds to 3 dp in the API, hence the 0.006 tolerance.
        midpoint_ok = all(abs(cp["segment_end_mile"] - (cp["mile"] + nxt["mile"]) / 2) < 0.006 for cp, nxt in zip(cps, cps[1:]))
        check(f"{name}: segment boundaries are midpoints between checkpoints", midpoint_ok)

        etas = [datetime.fromisoformat(cp["eta"]) for cp in cps]
        check(f"{name}: first checkpoint ETA = departure", abs((etas[0] - dep).total_seconds()) <= 1)
        check(f"{name}: last checkpoint ETA = arrival", abs((etas[-1] - arr).total_seconds()) <= 1)
        check(f"{name}: ETAs non-decreasing", all(a <= b for a, b in zip(etas, etas[1:])))
        speeds = [
            (b["mile"] - a["mile"]) / ((tb - ta).total_seconds() / 3600)
            for a, b, ta, tb in zip(cps, cps[1:], etas, etas[1:]) if tb > ta
        ]
        check(f"{name}: implied speed between checkpoints 5-85 mph", all(5 <= s <= 85 for s in speeds),
              f"min {min(speeds):.0f} / max {max(speeds):.0f} mph")
        off_route = max(point_to_polyline_m((cp["lat"], cp["lon"]), coords) for cp in cps)
        check(f"{name}: every checkpoint lies on the drawn route (< 100 m)", off_route < 100, f"max {off_route:.0f} m")
        check(f"{name}: forecast_time = UTC hour containing ETA",
              all(datetime.fromisoformat(cp["forecast_time"]) == hour_containing(datetime.fromisoformat(cp["eta"]))
                  for cp in cps))


def audit_weather_and_risk(plan: dict, load_lb: float) -> None:  # noqa: C901
    cps = [(route, cp) for route in plan["routes"] for cp in route["checkpoints"] if cp["status"] == "ok"]
    unknown = [cp for route in plan["routes"] for cp in route["checkpoints"] if cp["status"] != "ok"]
    check("unavailable checkpoints carry no weather/risk and an 'unknown, not low' warning",
          all(cp["weather"] is None and cp["risk"] is None and "not low" in cp["warnings"][0] for cp in unknown),
          f"{len(unknown)} unavailable")
    if not cps:
        check("weather: some checkpoints have forecasts", False)
        return
    def point_of(cp):
        # The API states which grid point it used. Re-snapping the 5-dp rounded coordinate
        # here can pick the neighbouring point when a checkpoint sits on a half-cell boundary.
        fp = cp.get("forecast_point")
        return (fp["lat"], fp["lon"]) if fp else (snap(cp["lat"]), snap(cp["lon"]))

    boundary = sum(1 for _, cp in cps if point_of(cp) != (snap(cp["lat"]), snap(cp["lon"])))
    check("forecast point = nearest 0.05-deg grid point (half-cell boundary ties informational)",
          all(abs(point_of(cp)[0] - cp["lat"]) <= 0.0251 and abs(point_of(cp)[1] - cp["lon"]) <= 0.0251 for _, cp in cps),
          f"{boundary} checkpoint(s) on a rounding boundary")
    points = sorted({point_of(cp) for _, cp in cps})
    max_snap = max(haversine_m((cp["lat"], cp["lon"]), point_of(cp)) for _, cp in cps)
    check("weather lookup snapping offset <= 4 km (0.05 deg grid)", max_snap <= 4000, f"max {max_snap / 1000:.2f} km")
    hours = [datetime.fromisoformat(cp["forecast_time"]) for _, cp in cps]
    # Request the SAME window the app requested (weather_risk.window_*). Verified 2026-10-24:
    # Open-Meteo's value at the HRRR->GFS hand-over hour differs when a request ENDS on
    # that hour versus continues past it, so a different window is not a like-for-like check.
    window_start = datetime.fromisoformat(plan["weather_risk"]["window_start"])
    window_end = datetime.fromisoformat(plan["weather_risk"]["window_end"])
    series = dict(zip(points, open_meteo(points, window_start, window_end)))
    short = dict(zip(points, open_meteo(points, min(hours), max(hours))))
    handover = sum(
        1 for _, cp in cps
        if (stamp := int(datetime.fromisoformat(cp["forecast_time"]).timestamp()))
        and series[point_of(cp)].get(stamp) != short[point_of(cp)].get(stamp)
    )
    check("provider note: checkpoint-hours whose Open-Meteo value depends on request window (informational)", True,
          f"{handover} of {len(cps)} (model hand-over hour); app uses one continuous window")

    mismatches, risk_errors, load_errors = [], [], []
    for route, cp in cps:
        stamp = int(datetime.fromisoformat(cp["forecast_time"]).timestamp())
        raw = series[point_of(cp)][stamp]
        w = cp["weather"]
        expected = {
            "wind_mph": round(raw["wind_speed_10m"], 1),
            "wind_gust_mph": None if raw["wind_gusts_10m"] is None else round(raw["wind_gusts_10m"], 1),
            "rain_in_per_hr": round(raw["rain"] + raw["showers"], 3),
            "snow_in_per_hr": round(raw["snowfall"], 3),
        }
        for key, value in expected.items():
            if value != w[key] and not (value is not None and w[key] is not None and abs(value - w[key]) <= 0.051):
                mismatches.append(f'{route["label"]} mi {cp["mile"]} {key}: app {w[key]} vs Open-Meteo {value}')
        base, wind = wind_level(w["wind_mph"], load_lb)
        levels = {"wind": wind, "rain": rain_level(w["rain_in_per_hr"]), "snow": snow_level(w["snow_in_per_hr"])}
        r = cp["risk"]
        if (r["wind"], r["rain"], r["snow"], r["overall"], r["wind_before_load_rule"]) != (
                levels["wind"], levels["rain"], levels["snow"], overall(list(levels.values())), base):
            risk_errors.append(f'{route["label"]} mi {cp["mile"]}: app {r} vs independent {levels}')
        if r["load_rule_applied"] != (base != wind):
            load_errors.append(f'{route["label"]} mi {cp["mile"]}')
    check(f"weather values match a direct Open-Meteo fetch (same snapped point + hour) [{len(cps)} checkpoints]",
          not mismatches, "; ".join(mismatches[:5]))
    check("rain shown = rain + showers (liquid), snow = snowfall, wind = sustained 10 m (gust separate)", not mismatches)
    check(f"per-hazard and overall risk match independent PDF classifier [{len(cps)} checkpoints]",
          not risk_errors, "; ".join(risk_errors[:3]))
    check("load_rule_applied flag consistent with wind before/after load rule", not load_errors)

    wind_values = [cp["weather"]["wind_mph"] for _, cp in cps]
    rain_values = [cp["weather"]["rain_in_per_hr"] for _, cp in cps]
    snow_values = [cp["weather"]["snow_in_per_hr"] for _, cp in cps]
    check("observed weather ranges (informational)", True,
          f"wind {min(wind_values)}-{max(wind_values)} mph, rain max {max(rain_values)} in/hr, snow max {max(snow_values)} in/hr")


def recompute_summary(route: dict) -> dict:
    miles = {code: 0.0 for code in LEVELS}
    unknown = weighted = 0.0
    for cp in route["checkpoints"]:
        if cp["risk"] is None:
            unknown += cp["segment_miles"]
        else:
            miles[cp["risk"]["overall"]] += cp["segment_miles"]
            weighted += cp["segment_miles"] * SCORE[cp["risk"]["overall"]]
    known = sum(miles.values())
    return {
        "miles_by_level": miles, "unknown_miles": unknown,
        "severe_or_worse_miles": miles["severe"] + miles["no_travel"],
        "average_risk": weighted / known if known else None,
        "max_risk": max((c for c in LEVELS if miles[c] > 0), key=SCORE.get, default=None),
        "has_no_travel": miles["no_travel"] > 0, "coverage_complete": unknown == 0,
    }


def audit_summaries_and_ranking(plan: dict) -> None:
    summaries = {}
    for route in plan["routes"]:
        s, mine = route["risk_summary"], recompute_summary(route)
        summaries[route["id"]] = (route, mine)
        if s is None:
            check(f'{route["label"]}: summary null only when no forecast at all',
                  plan["recommendation"]["status"] == "unavailable")
            continue
        ok = all(abs(s["miles_by_level"][c] - mine["miles_by_level"][c]) < 0.02 for c in LEVELS)
        ok &= abs(s["unknown_miles"] - mine["unknown_miles"]) < 0.02
        ok &= abs(s["severe_or_worse_miles"] - mine["severe_or_worse_miles"]) < 0.02
        ok &= (s["average_risk"] is None) == (mine["average_risk"] is None)
        ok &= s["average_risk"] is None or abs(s["average_risk"] - mine["average_risk"]) < 0.001
        ok &= s["max_risk"] == mine["max_risk"] and s["has_no_travel"] == mine["has_no_travel"]
        ok &= s["coverage_complete"] == mine["coverage_complete"]
        check(f'{route["label"]}: risk summary recomputed from checkpoint segments matches', ok,
              f'avg {s["average_risk"]} vs {mine["average_risk"]}, miles {s["miles_by_level"]}')

        stretches = [(st["level"], st["start_mile"], st["end_mile"]) for st in route["hazard_stretches"]]
        mine_st, current = [], None
        for cp in route["checkpoints"]:
            level = cp["risk"]["overall"] if cp["risk"] else None
            if level in ("high", "severe", "no_travel"):
                if current and current[0] == level and current[3] == cp["index"] - 1:
                    current[2], current[3] = cp["segment_end_mile"], cp["index"]
                else:
                    current = [level, cp["segment_start_mile"], cp["segment_end_mile"], cp["index"]]
                    mine_st.append(current)
        order = {"no_travel": 0, "severe": 1, "high": 2}
        mine_st = sorted(((s_[0], s_[1], s_[2]) for s_ in mine_st), key=lambda s_: (order[s_[0]], s_[1]))
        check(f'{route["label"]}: hazard stretches recomputed match', stretches == mine_st, f"{len(stretches)} stretch(es)")

    rec = plan["recommendation"]
    if rec["status"] == "unavailable":
        check("no recommendation when weather unavailable", rec["route_id"] is None)
        return

    def key(route_id):
        route, s = summaries[route_id]
        return (s["has_no_travel"], round(s["severe_or_worse_miles"], 2), round(s["miles_by_level"]["high"], 2),
                math.inf if s["average_risk"] is None else round(s["average_risk"], 6), route["duration_seconds"])

    provider_order = [r["id"] for r in plan["routes"]]
    mine = sorted(provider_order, key=key)  # stable: ties keep provider order
    check("ranking recomputed with assessment priority order matches", mine == rec["ranked_route_ids"],
          f"app {rec['ranked_route_ids']} vs independent {mine}")
    check("recommended route = rank 1, and route cards' rank/recommended flags agree",
          rec["route_id"] == mine[0]
          and all(r["rank"] == mine.index(r["id"]) + 1 and r["recommended"] == (r["id"] == mine[0]) for r in plan["routes"]))
    if len(mine) > 1:
        names = ["no_travel", "severe_miles", "high_miles", "average_risk", "travel_time"]
        decided = next((n for n, a, b in zip(names, key(mine[0]), key(mine[1])) if a != b), "input_order")
        check("decided_by = first criterion separating #1 and #2", decided == rec["decided_by"],
              f"{rec['decided_by']} vs {decided}")
        if rec["decided_by"] == "travel_time":
            def fmt(seconds):
                hours, minutes = divmod(math.floor(seconds / 60 + 0.5), 60)
                return f"{minutes} min" if not hours else f"{hours} h" if not minutes else f"{hours} h {minutes} min"
            best, other = summaries[mine[0]][0], summaries[mine[1]][0]
            expected = f"({fmt(best['duration_seconds'])} vs {fmt(other['duration_seconds'])} on {other['label']})"
            check("explanation travel times match the two top routes", expected in rec["explanation"], expected)
        if rec["decided_by"] == "average_risk":
            numbers = [float(x) for x in re.findall(r"\((\d+\.\d+) vs (\d+\.\d+)", rec["explanation"])[0]]
            best_avg, other_avg = summaries[mine[0]][1]["average_risk"], summaries[mine[1]][1]["average_risk"]
            check("explanation average-risk numbers match the two top routes",
                  numbers == [round(best_avg, 2), round(other_avg, 2)], f"{numbers} vs {best_avg:.3f}/{other_avg:.3f}")
    no_safe = all(summaries[r][1]["has_no_travel"] for r in provider_order)
    check("no_safe_route status iff every route has No Travel", (rec["status"] == "no_safe_route") == no_safe)


def audit_heatmap(plan: dict, load_lb: float, departure: datetime) -> None:
    h = plan["heatmap"]
    n = len(h["lats"])
    check("heatmap: 49 frames, offsets 0..48", h["frame_offsets_hours"] == list(range(49)) and len(h["frame_times"]) == 49)
    check("heatmap: frame h time = UTC hour containing (departure + h hours)",
          all(datetime.fromisoformat(t) == hour_containing(departure + timedelta(hours=i))
              for i, t in enumerate(h["frame_times"])))
    check("heatmap: arrays are [49][points]",
          all(len(h[k]) == 49 and all(len(f) == n for f in h[k])
              for k in ("risk", "wind_mph", "rain_in_per_hr", "snow_in_per_hr")), f"{n} points")
    spacing = h["spacing_degrees"]
    check("heatmap: points on the declared lattice",
          all(abs(v / spacing - round(v / spacing)) < 1e-6 for v in h["lats"] + h["lons"]), f"spacing {spacing} deg")
    route_lines = [r["geometry"]["coordinates"] for r in plan["routes"]]
    farthest = max(min(point_to_polyline_m((lat, lon), line[::5]) for line in route_lines)
                   for lat, lon in zip(h["lats"], h["lons"]))
    check("heatmap: every cell within the trip corridor (<= 30 km + 0.75 cell)",
          farthest <= max(30_000, spacing * 111_320 * 0.75) + 5_000, f"farthest {farthest / 1000:.1f} km")

    bad, null_mismatch = 0, 0
    for f in range(49):
        for i in range(n):
            code = h["risk"][f][i]
            values = (h["wind_mph"][f][i], h["rain_in_per_hr"][f][i], h["snow_in_per_hr"][f][i])
            if code is None:
                null_mismatch += any(v is not None for v in values)
                continue
            _, wind = wind_level(values[0], load_lb)
            if SCORE[overall([wind, rain_level(values[1]), snow_level(values[2])])] != code:
                bad += 1
    check(f"heatmap: every cell's risk code matches its own wind/rain/snow ({49 * n} cells)", bad == 0, f"{bad} mismatches")
    check("heatmap: null risk <=> null weather values", null_mismatch == 0)

    sample = list(range(0, n, max(1, n // 12)))[:12]
    frames = [0, 12, 24, 48]
    raw = open_meteo([(h["lats"][i], h["lons"][i]) for i in sample],
                     datetime.fromisoformat(plan["weather_risk"]["window_start"]),
                     datetime.fromisoformat(plan["weather_risk"]["window_end"]))
    mismatches = []
    for j, i in enumerate(sample):
        for f in frames:
            stamp = int(datetime.fromisoformat(h["frame_times"][f]).timestamp())
            r = raw[j].get(stamp)
            if r is None or h["wind_mph"][f][i] is None:
                continue
            if abs(r["wind_speed_10m"] - h["wind_mph"][f][i]) > 0.051 or \
                    abs(r["rain"] + r["showers"] - h["rain_in_per_hr"][f][i]) > 0.0011:
                mismatches.append(f"pt {i} frame {f}: app {h['wind_mph'][f][i]} mph vs Open-Meteo {r['wind_speed_10m']}")
    check(f"heatmap: sampled cells match direct Open-Meteo, same window ({len(sample)} pts x {len(frames)} frames)",
          not mismatches, "; ".join(mismatches[:3]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--origin", default="32.7767,-96.7970")
    parser.add_argument("--destination", default="39.7392,-104.9903")
    parser.add_argument("--load", type=float, default=42_000)
    parser.add_argument("--interval", type=int, default=25)
    parser.add_argument("--out")
    args = parser.parse_args()

    # Deliberately not on the hour, to exercise "hour containing the ETA".
    departure = (datetime.now(timezone.utc) + timedelta(hours=26)).replace(minute=20, second=0, microsecond=0)
    o, d = (tuple(float(x) for x in v.split(",")) for v in (args.origin, args.destination))
    body = {
        "origin": {"lat": o[0], "lon": o[1], "label": "origin"},
        "destination": {"lat": d[0], "lon": d[1], "label": "destination"},
        "departure_time": departure.isoformat(), "load_weight_lb": args.load,
        "checkpoint_interval_miles": args.interval,
    }
    plan = post_json(f"{args.api}/api/trips/plan/", body)
    if args.out:
        with open(args.out, "w") as handle:
            json.dump(plan, handle)

    check("echoed inputs match request", plan["inputs"]["load_weight_lb"] == args.load
          and plan["inputs"]["checkpoint_interval_miles"] == args.interval)
    check("route_count matches routes, notice iff fewer than 3",
          plan["route_count"] == len(plan["routes"]) and (plan["notice"] is None) == (len(plan["routes"]) >= 3),
          f"{len(plan['routes'])} routes")
    check("route ids unique", len({r["id"] for r in plan["routes"]}) == len(plan["routes"]))
    audit_routes(plan, args.interval)
    audit_weather_and_risk(plan, args.load)
    audit_summaries_and_ranking(plan)
    audit_heatmap(plan, args.load, departure)

    width = max(len(name) for name, _, _ in results)
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name.ljust(width)}  {detail}")
    failed = sum(not ok for _, ok, _ in results)
    print(f"\n{len(results) - failed}/{len(results)} checks passed; weather status {plan['weather_risk']['status']}, "
          f"recommendation {plan['recommendation']['status']} ({plan['recommendation']['route_label']}), "
          f"decided_by {plan['recommendation']['decided_by']}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

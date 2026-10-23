"""
Synthetic TomTom payloads with the same structure as live responses
recorded on 2026-10-23 (values are made up; no real data or keys).
"""

import copy


def geocode_payload():
    return copy.deepcopy(
        {
            "summary": {"query": "dallas tx", "numResults": 3},
            "results": [
                {
                    "type": "Geography",
                    "id": "ATFFDvKyxtf1HepzrswVcQ",
                    "entityType": "Municipality",
                    "address": {"freeformAddress": "Dallas, TX", "countryCode": "US"},
                    "position": {"lat": 32.7779765, "lon": -96.7962148},
                },
                {
                    # Same label, different entity: should be de-duplicated.
                    "type": "Geography",
                    "id": "sXCQIVHbX669yXPcLJ-Iug",
                    "entityType": "Municipality",
                    "address": {"freeformAddress": "Dallas, TX", "countryCode": "US"},
                    "position": {"lat": 32.841482, "lon": -97.042091},
                },
                {
                    "type": "Geography",
                    "id": "dallas-ga",
                    "entityType": "Municipality",
                    "address": {"freeformAddress": "Dallas, GA", "countryCode": "US"},
                    "position": {"lat": 33.9237, "lon": -84.8408},
                },
            ],
        }
    )


def route_json(points, length_m=1_419_953, time_s=42_540, delay_s=71, progress=True):
    raw = {
        "summary": {
            "lengthInMeters": length_m,
            "travelTimeInSeconds": time_s,
            "trafficDelayInSeconds": delay_s,
            "trafficLengthInMeters": 9527,
            "departureTime": "2026-10-25T08:00:00-05:00",
            "arrivalTime": "2026-10-25T18:49:00-06:00",
        },
        "legs": [
            {
                "summary": {"lengthInMeters": length_m},
                "points": [{"latitude": lat, "longitude": lon} for lat, lon in points],
            }
        ],
        "sections": [{"startPointIndex": 0, "endPointIndex": len(points) - 1, "sectionType": "TRAVEL_MODE",
                      "travelMode": "truck"}],
    }
    if progress:
        raw["progress"] = [
            {"pointIndex": 0, "travelTimeInSeconds": 0, "distanceInMeters": 0},
            {"pointIndex": len(points) - 1, "travelTimeInSeconds": time_s, "distanceInMeters": length_m},
        ]
    return raw


ROUTE_A_POINTS = [(32.7767, -96.7970), (34.0, -98.5), (36.0, -101.0), (39.7392, -104.9903)]
ROUTE_B_POINTS = [(32.7767, -96.7970), (33.5, -99.9), (37.0, -102.5), (39.7392, -104.9903)]
ROUTE_C_POINTS = [(32.7767, -96.7970), (35.2, -97.5), (38.0, -100.0), (39.7392, -104.9903)]


def routes_payload(count=3):
    routes = [
        route_json(ROUTE_A_POINTS),
        route_json(ROUTE_B_POINTS, length_m=1_284_983, time_s=45_114, delay_s=0),
        route_json(ROUTE_C_POINTS, length_m=1_500_000, time_s=47_000, delay_s=120),
    ][:count]
    return {"formatVersion": "0.0.12", "routes": routes}


def routes_callback(count=3):
    """Like the live API, echo the requested departAt in each route's departure/arrival times."""
    import json
    from datetime import datetime, timedelta
    from urllib.parse import parse_qs, urlparse

    def callback(request):
        depart = datetime.fromisoformat(parse_qs(urlparse(request.url).query)["departAt"][0])
        payload = routes_payload(count)
        for route in payload["routes"]:
            summary = route["summary"]
            summary["departureTime"] = depart.isoformat()
            summary["arrivalTime"] = (depart + timedelta(seconds=summary["travelTimeInSeconds"])).isoformat()
        return 200, {"Content-Type": "application/json"}, json.dumps(payload)

    return callback


def error_payload(code, message="error"):
    return {"formatVersion": "0.0.12", "detailedError": {"code": code, "message": message}}

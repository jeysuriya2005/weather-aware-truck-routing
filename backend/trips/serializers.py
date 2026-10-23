from __future__ import annotations

from datetime import datetime, timedelta

from django.utils import timezone
from rest_framework import serializers

CHECKPOINT_INTERVAL_CHOICES_MILES = (10, 25, 50)
DEFAULT_CHECKPOINT_INTERVAL_MILES = 25

# Sanity bound only; the assessment's load rules start at >30,000 lb.
MAX_LOAD_WEIGHT_LB = 200_000

# Departures slightly in the past are allowed (form filled in a few minutes ago).
DEPARTURE_PAST_TOLERANCE = timedelta(minutes=15)
# Open-Meteo accepts hours up to 23:00 UTC on today + 15 days (verified live).
# Departure + the 48 h heatmap window must fit inside that horizon.
DEPARTURE_MAX_AHEAD = timedelta(days=13)


class GeocodeQuerySerializer(serializers.Serializer):
    q = serializers.CharField(min_length=2, max_length=200, trim_whitespace=True)


class LocationSerializer(serializers.Serializer):
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)
    label = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class RoutePlanRequestSerializer(serializers.Serializer):
    origin = LocationSerializer()
    destination = LocationSerializer()
    departure_time = serializers.CharField(
        help_text="ISO 8601 date-time with a UTC offset, e.g. 2026-10-25T08:00:00-05:00"
    )
    load_weight_lb = serializers.FloatField(min_value=0, max_value=MAX_LOAD_WEIGHT_LB)
    checkpoint_interval_miles = serializers.ChoiceField(
        choices=CHECKPOINT_INTERVAL_CHOICES_MILES,
        required=False,
        default=DEFAULT_CHECKPOINT_INTERVAL_MILES,
    )

    def validate_departure_time(self, value: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            raise serializers.ValidationError("Must be an ISO 8601 date-time.") from None
        if parsed.tzinfo is None:
            raise serializers.ValidationError("Must include a UTC offset (e.g. 'Z' or '-05:00').")

        now = self.context.get("now") or timezone.now()
        if parsed < now - DEPARTURE_PAST_TOLERANCE:
            raise serializers.ValidationError("Departure time cannot be in the past.")
        if parsed > now + DEPARTURE_MAX_AHEAD:
            raise serializers.ValidationError(
                f"Departure time must be within {DEPARTURE_MAX_AHEAD.days} days "
                "so forecasts cover the trip."
            )
        return parsed

    def validate(self, attrs: dict) -> dict:
        origin, destination = attrs["origin"], attrs["destination"]
        if round(origin["lat"], 4) == round(destination["lat"], 4) and round(origin["lon"], 4) == round(
            destination["lon"], 4
        ):
            raise serializers.ValidationError({"destination": "Destination must differ from origin."})
        return attrs

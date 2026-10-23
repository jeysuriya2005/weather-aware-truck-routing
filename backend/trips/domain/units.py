"""Unit conversions. Providers report metric; the app works in miles, mph and pounds."""

METERS_PER_MILE = 1609.344  # exact, international mile
KMH_PER_MPH = 1.609344


def meters_to_miles(meters: float) -> float:
    return meters / METERS_PER_MILE


def miles_to_meters(miles: float) -> float:
    return miles * METERS_PER_MILE


def kmh_to_mph(kmh: float) -> float:
    return kmh / KMH_PER_MPH

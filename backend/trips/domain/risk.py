"""
Weather risk classification for a single checkpoint.

Source of truth: the assessment PDF "Risk Rules" and "Load rules".

    Condition | Low        | Moderate  | High      | Severe    | No Travel
    Wind      | <25 mph    | 25-34     | 35-44     | 45-54     | >=55 mph
    Rain      | <0.10 in/hr| 0.10-0.25 | 0.25-0.50 | 0.50-1.00 | >1.00
    Snow      | <0.5 in/hr | 0.5-1.0   | 1.0-2.0   | 2.0-3.0   | >3.0

    Load rules (wind only):
      >=55 mph                 -> No Travel for any load
      45-54 mph + >30,000 lb   -> No Travel
      35-44 mph + >40,000 lb   -> Severe

Boundary convention (agreed design decision): where two published ranges
share an endpoint (e.g. rain 0.25 appears in Moderate and High), a band
includes its lower bound and excludes its upper bound. Wind bands are
published as whole numbers; continuous values between them (e.g. 34.6 mph)
belong to the lower band, i.e. Moderate is 25 <= wind < 35. The No Travel
edges are kept exactly as published: wind >= 55, rain > 1.00, snow > 3.0,
so exactly 1.00 in/hr rain and exactly 3.0 in/hr snow are Severe.

Units are explicit in every name: mph, inches per hour, pounds.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import IntEnum


class RiskLevel(IntEnum):
    """Ordered risk levels. The integer value is the score used for averages."""

    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self) -> str:
        return _LABELS[self]


_LABELS = {
    RiskLevel.LOW: "Low",
    RiskLevel.MODERATE: "Moderate",
    RiskLevel.HIGH: "High",
    RiskLevel.SEVERE: "Severe",
    RiskLevel.NO_TRAVEL: "No Travel",
}

# Wind (mph): lower bounds, inclusive.
WIND_MODERATE_MPH = 25.0
WIND_HIGH_MPH = 35.0
WIND_SEVERE_MPH = 45.0
WIND_NO_TRAVEL_MPH = 55.0

# Rain (in/hr): lower bounds inclusive, except No Travel which is strictly greater.
RAIN_MODERATE_IN_HR = 0.10
RAIN_HIGH_IN_HR = 0.25
RAIN_SEVERE_IN_HR = 0.50
RAIN_NO_TRAVEL_ABOVE_IN_HR = 1.00

# Snow (in/hr): lower bounds inclusive, except No Travel which is strictly greater.
SNOW_MODERATE_IN_HR = 0.5
SNOW_HIGH_IN_HR = 1.0
SNOW_SEVERE_IN_HR = 2.0
SNOW_NO_TRAVEL_ABOVE_IN_HR = 3.0

# Load rules (lb): strictly greater than.
LOAD_SEVERE_WIND_NO_TRAVEL_ABOVE_LB = 30_000.0
LOAD_HIGH_WIND_SEVERE_ABOVE_LB = 40_000.0


def _require_non_negative(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number, got {type(value).__name__}")
    if math.isnan(value) or math.isinf(value) or value < 0:
        raise ValueError(f"{name} must be a finite, non-negative number, got {value!r}")


def classify_wind_base(wind_mph: float) -> RiskLevel:
    """Wind level from the threshold table alone, before load rules."""
    _require_non_negative("wind_mph", wind_mph)
    if wind_mph >= WIND_NO_TRAVEL_MPH:
        return RiskLevel.NO_TRAVEL
    if wind_mph >= WIND_SEVERE_MPH:
        return RiskLevel.SEVERE
    if wind_mph >= WIND_HIGH_MPH:
        return RiskLevel.HIGH
    if wind_mph >= WIND_MODERATE_MPH:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def apply_load_rules(base_wind_level: RiskLevel, load_weight_lb: float) -> RiskLevel:
    """
    Upgrade a wind level according to the load rules. Never downgrades.

    The load-rule wind ranges (45-54, 35-44 mph) are exactly the Severe and
    High wind bands, so the rules are applied by band membership. That keeps
    their boundaries identical to the threshold table's.
    """
    _require_non_negative("load_weight_lb", load_weight_lb)
    adjusted = base_wind_level
    if base_wind_level == RiskLevel.SEVERE and load_weight_lb > LOAD_SEVERE_WIND_NO_TRAVEL_ABOVE_LB:
        adjusted = RiskLevel.NO_TRAVEL
    elif base_wind_level == RiskLevel.HIGH and load_weight_lb > LOAD_HIGH_WIND_SEVERE_ABOVE_LB:
        adjusted = RiskLevel.SEVERE
    return max(base_wind_level, adjusted)


def classify_wind(wind_mph: float, load_weight_lb: float) -> RiskLevel:
    """Wind level after load rules."""
    return apply_load_rules(classify_wind_base(wind_mph), load_weight_lb)


def classify_rain(rain_in_per_hr: float) -> RiskLevel:
    _require_non_negative("rain_in_per_hr", rain_in_per_hr)
    if rain_in_per_hr > RAIN_NO_TRAVEL_ABOVE_IN_HR:
        return RiskLevel.NO_TRAVEL
    if rain_in_per_hr >= RAIN_SEVERE_IN_HR:
        return RiskLevel.SEVERE
    if rain_in_per_hr >= RAIN_HIGH_IN_HR:
        return RiskLevel.HIGH
    if rain_in_per_hr >= RAIN_MODERATE_IN_HR:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def classify_snow(snow_in_per_hr: float) -> RiskLevel:
    _require_non_negative("snow_in_per_hr", snow_in_per_hr)
    if snow_in_per_hr > SNOW_NO_TRAVEL_ABOVE_IN_HR:
        return RiskLevel.NO_TRAVEL
    if snow_in_per_hr >= SNOW_SEVERE_IN_HR:
        return RiskLevel.SEVERE
    if snow_in_per_hr >= SNOW_HIGH_IN_HR:
        return RiskLevel.HIGH
    if snow_in_per_hr >= SNOW_MODERATE_IN_HR:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


@dataclass(frozen=True)
class CheckpointWeather:
    """Forecast values at one checkpoint for its estimated arrival hour."""

    wind_mph: float
    rain_in_per_hr: float
    snow_in_per_hr: float


@dataclass(frozen=True)
class RiskAssessment:
    wind_base: RiskLevel
    wind: RiskLevel
    rain: RiskLevel
    snow: RiskLevel
    overall: RiskLevel

    @property
    def load_rule_applied(self) -> bool:
        return self.wind != self.wind_base


def assess_checkpoint(weather: CheckpointWeather, load_weight_lb: float) -> RiskAssessment:
    """Overall risk is the highest of wind (after load rules), rain and snow."""
    wind_base = classify_wind_base(weather.wind_mph)
    wind = apply_load_rules(wind_base, load_weight_lb)
    rain = classify_rain(weather.rain_in_per_hr)
    snow = classify_snow(weather.snow_in_per_hr)
    return RiskAssessment(
        wind_base=wind_base,
        wind=wind,
        rain=rain,
        snow=snow,
        overall=max(wind, rain, snow),
    )

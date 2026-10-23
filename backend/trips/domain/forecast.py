"""
Forecast time alignment and conversion of forecast samples into risk inputs.

Open-Meteo hourly precipitation and snowfall are totals over the *preceding*
hour: the value stamped 11:00 covers 10:00-11:00. A truck arriving at 10:20
is therefore matched to the 11:00 record, the hourly period that contains
its arrival. Wind at that stamp is instantaneous and at most 59 minutes
later than the arrival.

Missing data is never treated as Low risk. A sample with any missing input
(wind, rain, showers, snowfall) cannot be classified and is reported as
unavailable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .risk import CheckpointWeather, RiskAssessment, assess_checkpoint

HOUR = timedelta(hours=1)


def forecast_hour_for(moment: datetime) -> datetime:
    """The UTC hour stamp whose preceding-hour period contains `moment`."""
    if moment.tzinfo is None:
        raise ValueError("moment must be timezone-aware")
    utc = moment.astimezone(timezone.utc)
    floored = utc.replace(minute=0, second=0, microsecond=0)
    return floored if floored == utc else floored + HOUR


@dataclass(frozen=True)
class ForecastSample:
    """Raw provider values for one location and hour. None means missing."""

    time: datetime
    wind_mph: float | None
    wind_gust_mph: float | None
    rain_in_per_hr: float | None
    showers_in_per_hr: float | None
    snow_in_per_hr: float | None

    def to_risk_input(self) -> CheckpointWeather | None:
        """Risk inputs, or None if any required value is missing or invalid."""
        values = (self.wind_mph, self.rain_in_per_hr, self.showers_in_per_hr, self.snow_in_per_hr)
        if any(v is None or not math.isfinite(v) or v < 0 for v in values):
            return None
        return CheckpointWeather(
            wind_mph=self.wind_mph,
            # The assessment's "rain" is liquid precipitation: large-scale + convective.
            rain_in_per_hr=self.rain_in_per_hr + self.showers_in_per_hr,
            snow_in_per_hr=self.snow_in_per_hr,
        )


@dataclass(frozen=True)
class AssessedSample:
    sample: ForecastSample | None
    weather: CheckpointWeather | None
    risk: RiskAssessment | None

    @property
    def available(self) -> bool:
        return self.risk is not None


def assess_sample(sample: ForecastSample | None, load_weight_lb: float) -> AssessedSample:
    weather = sample.to_risk_input() if sample else None
    risk = assess_checkpoint(weather, load_weight_lb) if weather else None
    return AssessedSample(sample=sample, weather=weather, risk=risk)

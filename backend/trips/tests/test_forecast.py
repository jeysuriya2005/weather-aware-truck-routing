import math
from datetime import datetime, timedelta, timezone

import pytest

from trips.domain.forecast import ForecastSample, assess_sample, forecast_hour_for
from trips.domain.risk import RiskLevel

UTC = timezone.utc
CDT = timezone(timedelta(hours=-5))
T = datetime(2026, 10, 25, 11, tzinfo=UTC)


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (datetime(2026, 10, 25, 11, 0, tzinfo=UTC), datetime(2026, 10, 25, 11, tzinfo=UTC)),  # exact hour
        (datetime(2026, 10, 25, 10, 20, tzinfo=UTC), datetime(2026, 10, 25, 11, tzinfo=UTC)),  # 10:00-11:00 period
        (datetime(2026, 10, 25, 10, 0, 1, tzinfo=UTC), datetime(2026, 10, 25, 11, tzinfo=UTC)),
        (datetime(2026, 10, 25, 10, 59, 59, tzinfo=UTC), datetime(2026, 10, 25, 11, tzinfo=UTC)),
        (datetime(2026, 10, 25, 5, 20, tzinfo=CDT), datetime(2026, 10, 25, 11, tzinfo=UTC)),  # offset handled
        (datetime(2026, 10, 25, 23, 30, tzinfo=UTC), datetime(2026, 10, 26, 0, tzinfo=UTC)),  # day rollover
    ],
)
def test_forecast_hour_contains_arrival(moment, expected):
    assert forecast_hour_for(moment) == expected


def test_forecast_hour_requires_timezone():
    with pytest.raises(ValueError):
        forecast_hour_for(datetime(2026, 10, 25, 10, 20))


def sample(wind=10.0, gust=15.0, rain=0.0, showers=0.0, snow=0.0):
    return ForecastSample(T, wind, gust, rain, showers, snow)


def test_rain_is_liquid_rain_plus_showers():
    weather = sample(rain=0.06, showers=0.05).to_risk_input()
    assert weather.rain_in_per_hr == pytest.approx(0.11)
    assert assess_sample(sample(rain=0.06, showers=0.05), 0).risk.rain == RiskLevel.MODERATE


@pytest.mark.parametrize(
    "missing",
    [
        {"wind": None},
        {"rain": None},
        {"showers": None},
        {"snow": None},
        {"wind": math.nan},
        {"rain": -0.01},
    ],
)
def test_missing_or_invalid_values_are_unavailable_not_low(missing):
    assessed = assess_sample(sample(**missing), load_weight_lb=20_000)
    assert assessed.available is False
    assert assessed.risk is None


def test_missing_gust_does_not_block_assessment():
    assert assess_sample(sample(gust=None), 0).available


def test_no_sample_is_unavailable():
    assessed = assess_sample(None, 0)
    assert not assessed.available and assessed.sample is None


@pytest.mark.parametrize(
    ("values", "load", "overall"),
    [
        ({"wind": 24.9}, 80_000, RiskLevel.LOW),
        ({"wind": 46}, 30_000, RiskLevel.SEVERE),
        ({"wind": 46}, 30_001, RiskLevel.NO_TRAVEL),  # load rule via forecast pipeline
        ({"wind": 36}, 40_001, RiskLevel.SEVERE),
        ({"rain": 0.5, "showers": 0.51}, 0, RiskLevel.NO_TRAVEL),  # 1.01 in/hr combined
        ({"snow": 3.0}, 0, RiskLevel.SEVERE),
        ({"snow": 3.01}, 0, RiskLevel.NO_TRAVEL),
    ],
)
def test_assessment_uses_assessment_rules(values, load, overall):
    assert assess_sample(sample(**values), load).risk.overall == overall

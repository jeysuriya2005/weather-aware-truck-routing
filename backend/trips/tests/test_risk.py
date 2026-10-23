import math

import pytest

from trips.domain.risk import (
    CheckpointWeather,
    RiskLevel,
    apply_load_rules,
    assess_checkpoint,
    classify_rain,
    classify_snow,
    classify_wind,
    classify_wind_base,
)

L, M, H, S, NT = (
    RiskLevel.LOW,
    RiskLevel.MODERATE,
    RiskLevel.HIGH,
    RiskLevel.SEVERE,
    RiskLevel.NO_TRAVEL,
)


# --- Threshold table (PDF "Risk Rules"), every published edge -------------

@pytest.mark.parametrize(
    ("wind_mph", "expected"),
    [
        (0, L),
        (24.99, L),
        (25, M),  # Moderate 25-34
        (34, M),
        (34.99, M),  # between published integer bands -> lower band
        (35, H),  # High 35-44
        (44, H),
        (44.99, H),
        (45, S),  # Severe 45-54
        (54, S),
        (54.99, S),
        (55, NT),  # No Travel >= 55
        (80, NT),
    ],
)
def test_wind_thresholds(wind_mph, expected):
    assert classify_wind_base(wind_mph) == expected


@pytest.mark.parametrize(
    ("rain_in_per_hr", "expected"),
    [
        (0, L),
        (0.0999, L),
        (0.10, M),  # Moderate 0.10-0.25
        (0.2499, M),
        (0.25, H),  # shared edge -> upper band (inclusive lower bound)
        (0.4999, H),
        (0.50, S),  # shared edge -> Severe
        (0.9999, S),
        (1.00, S),  # No Travel is strictly > 1.00
        (1.0001, NT),
        (3.5, NT),
    ],
)
def test_rain_thresholds(rain_in_per_hr, expected):
    assert classify_rain(rain_in_per_hr) == expected


@pytest.mark.parametrize(
    ("snow_in_per_hr", "expected"),
    [
        (0, L),
        (0.499, L),
        (0.5, M),  # Moderate 0.5-1.0
        (0.999, M),
        (1.0, H),  # shared edge -> High
        (1.999, H),
        (2.0, S),  # shared edge -> Severe
        (2.999, S),
        (3.0, S),  # No Travel is strictly > 3.0
        (3.001, NT),
        (6, NT),
    ],
)
def test_snow_thresholds(snow_in_per_hr, expected):
    assert classify_snow(snow_in_per_hr) == expected


# --- Load rules (PDF "Load rules"), wind x load boundary matrix -----------

@pytest.mark.parametrize(
    ("wind_mph", "load_weight_lb", "expected"),
    [
        # Below 35 mph: load never matters.
        (34.99, 0, M),
        (34.99, 80_000, M),
        # 35-44 mph + >40,000 lb -> Severe.
        (35, 40_000, H),
        (35, 40_000.01, S),
        (35, 40_001, S),
        (44.99, 40_000, H),
        (44.99, 40_001, S),
        (35, 30_001, H),  # 30k rule applies only to 45-54 mph
        # 45-54 mph + >30,000 lb -> No Travel.
        (45, 30_000, S),
        (45, 30_000.01, NT),
        (45, 30_001, NT),
        (54.99, 30_000, S),
        (54.99, 30_001, NT),
        (45, 0, S),
        # >= 55 mph -> No Travel for any load.
        (55, 0, NT),
        (55, 30_000, NT),
        (55, 80_000, NT),
    ],
)
def test_wind_with_load_rules(wind_mph, load_weight_lb, expected):
    assert classify_wind(wind_mph, load_weight_lb) == expected


@pytest.mark.parametrize("base", list(RiskLevel))
@pytest.mark.parametrize("load_weight_lb", [0, 30_000, 30_001, 40_000, 40_001, 120_000])
def test_load_rules_never_downgrade(base, load_weight_lb):
    assert apply_load_rules(base, load_weight_lb) >= base


@pytest.mark.parametrize("load_weight_lb", [0, 30_001, 40_001, 120_000])
def test_load_rules_do_not_affect_rain_or_snow(load_weight_lb):
    weather = CheckpointWeather(wind_mph=0, rain_in_per_hr=0.3, snow_in_per_hr=1.5)
    result = assess_checkpoint(weather, load_weight_lb)
    assert (result.rain, result.snow, result.wind) == (H, H, L)


# --- Overall checkpoint risk ----------------------------------------------

@pytest.mark.parametrize(
    ("wind_mph", "rain", "snow", "load_weight_lb", "expected_overall"),
    [
        (10, 0, 0, 20_000, L),
        (30, 0.3, 0, 20_000, H),  # rain dominates
        (30, 0.05, 2.5, 20_000, S),  # snow dominates
        (40, 0.05, 0, 20_000, H),  # wind High, light load
        (40, 0.05, 0, 45_000, S),  # wind upgraded by load dominates
        (50, 0.6, 0, 35_000, NT),  # load upgrade to No Travel beats Severe rain
        (10, 1.5, 0, 0, NT),  # rain No Travel
    ],
)
def test_overall_is_max_after_load_adjustment(wind_mph, rain, snow, load_weight_lb, expected_overall):
    weather = CheckpointWeather(wind_mph=wind_mph, rain_in_per_hr=rain, snow_in_per_hr=snow)
    assert assess_checkpoint(weather, load_weight_lb).overall == expected_overall


def test_assessment_reports_load_rule_application():
    weather = CheckpointWeather(wind_mph=46, rain_in_per_hr=0, snow_in_per_hr=0)
    result = assess_checkpoint(weather, 35_000)
    assert result.wind_base == S
    assert result.wind == NT
    assert result.load_rule_applied

    light = assess_checkpoint(weather, 10_000)
    assert not light.load_rule_applied


# --- Input validation ------------------------------------------------------

@pytest.mark.parametrize("bad", [-0.01, math.nan, math.inf])
@pytest.mark.parametrize("classifier", [classify_wind_base, classify_rain, classify_snow])
def test_rejects_invalid_measurements(classifier, bad):
    with pytest.raises(ValueError):
        classifier(bad)


@pytest.mark.parametrize("bad", [-1, math.nan])
def test_rejects_invalid_load_weight(bad):
    with pytest.raises(ValueError):
        classify_wind(30, bad)


@pytest.mark.parametrize("bad", [None, "30", True])
def test_rejects_non_numeric(bad):
    with pytest.raises(TypeError):
        classify_wind_base(bad)


def test_levels_are_ordered_and_labelled():
    assert [int(level) for level in RiskLevel] == [0, 1, 2, 3, 4]
    assert [level.label for level in RiskLevel] == ["Low", "Moderate", "High", "Severe", "No Travel"]

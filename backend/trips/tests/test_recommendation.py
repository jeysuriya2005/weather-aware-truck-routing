import pytest

from trips.domain.recommendation import (
    RiskSegment,
    RouteRiskInput,
    recommend_route,
    summarize_route,
)
from trips.domain.risk import RiskLevel

L, M, H, S, NT = (
    RiskLevel.LOW,
    RiskLevel.MODERATE,
    RiskLevel.HIGH,
    RiskLevel.SEVERE,
    RiskLevel.NO_TRAVEL,
)
HOUR = 3600


def route(route_id, hours, *segments):
    """segments: (miles, level) pairs."""
    return RouteRiskInput(
        route_id=route_id,
        travel_time_seconds=hours * HOUR,
        segments=[RiskSegment(miles, level) for miles, level in segments],
    )


# --- Summaries -------------------------------------------------------------

def test_summary_uses_segment_distance_not_checkpoint_count():
    # Three short Severe segments vs one long Low segment: 3 of 4 checkpoints
    # are Severe, but only 6 of 106 miles are.
    summary = summarize_route(route("a", 2, (2, S), (2, S), (2, S), (100, L)))
    assert summary.total_miles == pytest.approx(106)
    assert summary.severe_miles == pytest.approx(6)
    assert summary.average_risk == pytest.approx(6 * 3 / 106)


def test_summary_tracks_no_travel_separately():
    summary = summarize_route(route("a", 1, (10, S), (5, NT), (20, H), (15, L)))
    assert summary.severe_miles == pytest.approx(10)
    assert summary.no_travel_miles == pytest.approx(5)
    assert summary.severe_or_worse_miles == pytest.approx(15)
    assert summary.high_miles == pytest.approx(20)
    assert summary.has_no_travel


def test_summary_rejects_empty_or_zero_length_routes():
    with pytest.raises(ValueError):
        summarize_route(route("a", 1))
    with pytest.raises(ValueError):
        summarize_route(route("a", 1, (0, L)))


def test_segment_rejects_negative_distance():
    with pytest.raises(ValueError):
        RiskSegment(-1, L)


# --- PDF priority order, each criterion deciding in turn -------------------

@pytest.mark.parametrize(
    ("routes", "expected_winner", "expected_criterion"),
    [
        pytest.param(
            [
                route("fast", 5, (10, S), (90, L)),
                route("slow", 9, (5, S), (95, H)),
            ],
            "slow",
            "severe_miles",
            id="1-fewest-severe-beats-everything-after",
        ),
        pytest.param(
            [
                route("a", 5, (10, S), (40, H), (50, L)),
                route("b", 9, (10, S), (20, H), (70, M)),
            ],
            "b",
            "high_miles",
            id="2-fewest-high-when-severe-ties",
        ),
        pytest.param(
            [
                route("a", 5, (10, H), (90, M)),
                route("b", 9, (10, H), (90, L)),
            ],
            "b",
            "average_risk",
            id="3-lowest-average-when-severe-and-high-tie",
        ),
        pytest.param(
            [
                route("a", 9, (100, M)),
                route("b", 5, (100, M)),
            ],
            "b",
            "travel_time",
            id="4-shortest-time-as-last-criterion",
        ),
        pytest.param(
            [
                route("first", 5, (100, L)),
                route("second", 5, (100, L)),
            ],
            "first",
            "input_order",
            id="full-tie-keeps-provider-order",
        ),
    ],
)
def test_priority_order(routes, expected_winner, expected_criterion):
    result = recommend_route(routes)
    assert result.recommended_route_id == expected_winner
    assert result.decided_by == expected_criterion
    assert result.no_safe_route_available is False


def test_full_ranking_is_deterministic():
    routes = [
        route("c", 6, (20, H), (80, L)),
        route("a", 4, (5, S), (95, L)),
        route("b", 7, (20, H), (80, L)),
        route("d", 3, (100, L)),
    ]
    assert recommend_route(routes).ranked_route_ids == ["d", "c", "b", "a"]
    assert recommend_route(routes).ranked_route_ids == recommend_route(routes).ranked_route_ids


# --- No Travel handling (documented design decision) ------------------------

def test_route_without_no_travel_beats_faster_route_with_no_travel():
    result = recommend_route(
        [
            route("unsafe", 3, (1, NT), (99, L)),
            route("safe", 10, (40, S), (60, H)),
        ]
    )
    assert result.recommended_route_id == "safe"
    assert result.decided_by == "no_travel"
    assert result.recommended_has_no_travel is False
    assert result.no_safe_route_available is False


def test_all_routes_with_no_travel_are_flagged_and_still_ranked():
    result = recommend_route(
        [
            route("a", 3, (30, NT), (70, L)),
            route("b", 5, (10, NT), (90, L)),
        ]
    )
    assert result.no_safe_route_available is True
    assert result.recommended_has_no_travel is True
    # Within the unsafe category, criterion 1 counts Severe-or-worse miles.
    assert result.recommended_route_id == "b"
    assert result.decided_by == "severe_miles"


def test_no_travel_counts_toward_severe_criterion_between_unsafe_routes():
    # "a" has fewer Severe-only miles, but more Severe-or-worse miles.
    result = recommend_route(
        [
            route("a", 1, (0.5, S), (50, NT), (49.5, L)),
            route("b", 9, (10, S), (1, NT), (89, L)),
        ]
    )
    assert result.recommended_route_id == "b"


# --- Missing forecast data (risk=None) -----------------------------------------

U = None  # unknown risk


def test_unknown_miles_are_not_counted_as_low():
    summary = summarize_route(route("a", 1, (40, U), (60, L)))
    assert summary.unknown_miles == pytest.approx(40)
    assert summary.miles_by_level[L] == pytest.approx(60)
    assert summary.total_miles == pytest.approx(100)
    assert summary.average_risk == pytest.approx(0)  # over the 60 known miles only
    assert summary.has_unknown


def test_average_excludes_unknown_miles():
    summary = summarize_route(route("a", 1, (50, S), (50, U)))
    assert summary.average_risk == pytest.approx(3.0)  # not diluted to 1.5 by unknown miles


def test_all_unknown_route_has_no_average_and_ranks_last_on_it():
    result = recommend_route([route("blind", 1, (100, U)), route("known", 9, (100, M))])
    assert result.summaries["blind"].average_risk is None
    assert result.summaries["blind"].max_risk is None
    assert result.recommended_route_id == "known"
    assert result.decided_by == "average_risk"


def test_coverage_flags():
    complete = recommend_route([route("a", 1, (100, L)), route("b", 2, (100, L))])
    assert complete.coverage_complete and complete.routes_with_unknown_miles == []
    partial = recommend_route([route("a", 1, (90, L), (10, U)), route("b", 2, (100, L))])
    assert not partial.coverage_complete
    assert partial.routes_with_unknown_miles == ["a"]


def test_unknown_does_not_hide_no_travel():
    result = recommend_route([route("a", 1, (5, NT), (95, U)), route("b", 5, (100, H))])
    assert result.recommended_route_id == "b"
    assert result.decided_by == "no_travel"


def test_max_risk():
    assert summarize_route(route("a", 1, (10, H), (90, L))).max_risk == H
    assert summarize_route(route("a", 1, (10, NT), (90, S))).max_risk == NT


# --- Robustness ------------------------------------------------------------

def test_float_noise_does_not_decide_ranking():
    # 0.1 + 0.2 != 0.3 in binary floating point; this must fall through to travel time.
    result = recommend_route(
        [
            route("a", 9, (0.1, S), (0.2, S), (99.7, L)),
            route("b", 5, (0.3, S), (99.7, L)),
        ]
    )
    assert result.recommended_route_id == "b"
    assert result.decided_by == "travel_time"


def test_single_route():
    result = recommend_route([route("only", 4, (100, M))])
    assert result.recommended_route_id == "only"
    assert result.decided_by is None


def test_rejects_empty_and_duplicate_routes():
    with pytest.raises(ValueError):
        recommend_route([])
    with pytest.raises(ValueError):
        recommend_route([route("x", 1, (1, L)), route("x", 2, (1, L))])

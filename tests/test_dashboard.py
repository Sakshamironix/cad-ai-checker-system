"""Tests for the Milestone 7 operator dashboard data."""

from __future__ import annotations

import pytest

from app.comparison_rules import FAIL, PASS, evaluate_matching_result
from app.dashboard import build_dashboard_rows
from app.feature_matcher import (
    MATCHED,
    OUT_OF_TOLERANCE,
    FeatureMatch,
    FeatureMatchingResult,
)


def _match(status: str, model_value: float) -> FeatureMatch:
    return FeatureMatch(
        source_kind="dimension",
        source_entity=4,
        requirement="Hole diameter",
        drawing_value_mm=6.0,
        model_feature="Likely STEP hole face 7",
        model_value_mm=model_value,
        difference_mm=model_value - 6.0,
        lower_deviation_mm=-0.1,
        upper_deviation_mm=0.1,
        tolerance_source="drawing",
        status=status,
        confidence="medium",
        reason="Synthetic dashboard evidence.",
    )


def _result(match: FeatureMatch, drawing: str = "part.dxf") -> FeatureMatchingResult:
    return FeatureMatchingResult(
        drawing_source=drawing,
        model_source="part.step",
        unit_conversion_factor_to_mm=1.0,
        default_tolerance_mm=0.1,
        matches=(match,),
        warnings=(),
    )


def test_dashboard_row_calculates_limits_for_pass() -> None:
    result = _result(_match(MATCHED, 6.05))
    judgement = evaluate_matching_result(result)

    row = build_dashboard_rows(result, judgement)[0]

    assert row.outcome == PASS
    assert row.allowed_minimum_mm == pytest.approx(5.9)
    assert row.allowed_maximum_mm == pytest.approx(6.1)
    assert row.difference_mm == pytest.approx(0.05)
    assert row.outside_limit_by_mm == pytest.approx(0.0)


def test_dashboard_row_calculates_amount_above_limit() -> None:
    result = _result(_match(OUT_OF_TOLERANCE, 6.25))
    judgement = evaluate_matching_result(result)

    row = build_dashboard_rows(result, judgement)[0]

    assert row.outcome == FAIL
    assert row.difference_mm == pytest.approx(0.25)
    assert row.outside_limit_by_mm == pytest.approx(0.15)


def test_dashboard_rejects_mismatched_sources() -> None:
    result = _result(_match(MATCHED, 6.0))
    other_result = _result(_match(MATCHED, 6.0), drawing="other.dxf")
    judgement = evaluate_matching_result(other_result)

    with pytest.raises(ValueError, match="Drawing sources"):
        build_dashboard_rows(result, judgement)

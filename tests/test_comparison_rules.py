"""Tests for comparison rules and final prototype judgement."""

from __future__ import annotations

import pytest

from app.comparison_rules import NG, OK, RulePolicy, evaluate_matching_result
from app.feature_matcher import (
    MATCHED,
    NO_MODEL_CANDIDATE,
    OUT_OF_TOLERANCE,
    UNMATCHED_3D,
    UNSUPPORTED,
    FeatureMatch,
    FeatureMatchingResult,
)


def _match(
    status: str,
    *,
    confidence: str = "medium",
    difference: float | None = 0.0,
    model_value: float | None = 10.0,
) -> FeatureMatch:
    return FeatureMatch(
        source_kind="dimension",
        source_entity=1,
        requirement="Linear dimension",
        drawing_value_mm=10.0,
        model_feature="Bounding box X" if model_value is not None else None,
        model_value_mm=model_value,
        difference_mm=difference,
        lower_deviation_mm=-0.1,
        upper_deviation_mm=0.1,
        tolerance_source="dimension",
        status=status,
        confidence=confidence,
        reason="Synthetic rule-engine evidence.",
    )


def _result(*matches: FeatureMatch) -> FeatureMatchingResult:
    return FeatureMatchingResult(
        drawing_source="drawing.dxf",
        model_source="model.step",
        unit_conversion_factor_to_mm=1.0,
        default_tolerance_mm=0.1,
        matches=matches,
        warnings=("Synthetic warning",),
    )


def test_all_supported_matches_produce_ok() -> None:
    judgement = evaluate_matching_result(
        _result(
            _match(MATCHED),
            _match(MATCHED, difference=0.05, model_value=10.05),
        )
    )

    assert judgement.decision == OK
    assert judgement.release_allowed is True
    assert judgement.pass_count == 2
    assert judgement.fail_count == 0
    assert judgement.review_count == 0
    assert judgement.pass_rate_percent == pytest.approx(100.0)


def test_tolerance_violation_produces_ng() -> None:
    judgement = evaluate_matching_result(
        _result(_match(OUT_OF_TOLERANCE, difference=0.5, model_value=10.5))
    )

    assert judgement.decision == NG
    assert judgement.release_allowed is False
    assert judgement.fail_count == 1
    assert judgement.findings[0].rule_id == "R-002"


def test_missing_and_unmatched_features_produce_ng() -> None:
    judgement = evaluate_matching_result(
        _result(
            _match(NO_MODEL_CANDIDATE, difference=None, model_value=None),
            _match(UNMATCHED_3D, difference=None, model_value=6.0),
        )
    )

    assert judgement.decision == NG
    assert judgement.fail_count == 2
    assert {finding.rule_id for finding in judgement.findings} == {"R-003", "R-004"}


def test_low_confidence_match_is_ok_but_unsupported_item_is_ng() -> None:
    judgement = evaluate_matching_result(
        _result(
            _match(MATCHED, confidence="low"),
            _match(UNSUPPORTED, difference=None, model_value=None),
        )
    )

    assert judgement.decision == NG
    assert judgement.pass_count == 1
    assert judgement.fail_count == 1
    assert judgement.review_count == 0
    assert judgement.release_allowed is False


def test_ng_has_precedence_over_ok() -> None:
    judgement = evaluate_matching_result(
        _result(
            _match(UNSUPPORTED, difference=None, model_value=None),
            _match(OUT_OF_TOLERANCE, difference=-0.5, model_value=9.5),
        )
    )

    assert judgement.decision == NG
    assert judgement.fail_count == 2
    assert judgement.review_count == 0


def test_no_comparisons_produces_ng() -> None:
    judgement = evaluate_matching_result(_result())

    assert judgement.decision == NG
    assert judgement.findings[0].rule_id == "R-000"
    assert judgement.pass_rate_percent == pytest.approx(0.0)


def test_missing_feature_remains_ng_without_review_state() -> None:
    policy = RulePolicy(
        fail_on_missing_model_candidate=False,
        fail_on_unmatched_3d_feature=False,
    )
    judgement = evaluate_matching_result(
        _result(_match(NO_MODEL_CANDIDATE, difference=None, model_value=None)),
        policy=policy,
    )

    assert judgement.decision == NG
    assert judgement.fail_count == 1
    assert judgement.review_count == 0


def test_policy_rejects_invalid_minimum_comparisons() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        RulePolicy(minimum_comparisons=0)

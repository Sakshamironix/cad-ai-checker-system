"""Tests for provisional project general-tolerance routing."""

from __future__ import annotations

import pytest

from app.general_tolerances import GeneralToleranceSet


def test_routes_each_supported_dimension_class() -> None:
    tolerances = GeneralToleranceSet(
        linear_mm=0.2,
        circular_mm=0.05,
        profile_mm=0.3,
        position_mm=0.1,
    )

    assert tolerances.for_dimension_classification("linear") == pytest.approx(0.2)
    assert tolerances.for_dimension_classification("diameter") == pytest.approx(0.05)
    assert tolerances.for_dimension_classification("radius") == pytest.approx(0.05)
    assert tolerances.to_dict()["profile_mm"] == pytest.approx(0.3)


def test_rejects_non_positive_limit() -> None:
    with pytest.raises(ValueError, match="profile_mm must be greater than zero"):
        GeneralToleranceSet(
            linear_mm=0.1,
            circular_mm=0.1,
            profile_mm=0.0,
            position_mm=0.1,
        )


def test_unsupported_dimension_class_has_no_silent_fallback() -> None:
    tolerances = GeneralToleranceSet.uniform(0.1)

    with pytest.raises(ValueError, match="No general tolerance is routed"):
        tolerances.for_dimension_classification("angle")


def test_application_state_changes_without_exposing_new_values() -> None:
    background_rules = GeneralToleranceSet(
        linear_mm=0.2,
        circular_mm=0.05,
        profile_mm=0.3,
        position_mm=0.1,
    )

    disabled = background_rules.with_application(False)

    assert disabled.applied is False
    assert disabled.linear_mm == pytest.approx(background_rules.linear_mm)
    assert disabled.circular_mm == pytest.approx(background_rules.circular_mm)
    assert disabled.profile_mm == pytest.approx(background_rules.profile_mm)

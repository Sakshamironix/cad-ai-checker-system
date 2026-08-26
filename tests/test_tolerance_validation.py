from __future__ import annotations

import pytest

from app.tolerance_validation import ToleranceConfigurationError, validate_tolerance_configuration


def _payload() -> dict[str, object]:
    return {"rule_set":{"id":"PROJECT","version":"1.0","unit":"mm","status":"provisional"}, "linear":[], "angular":[], "radii_and_chamfers":[], "feature_specific":[]}


def test_empty_provisional_categories_are_valid_and_explicit() -> None:
    assert validate_tolerance_configuration(_payload()).version == "1.0"


def test_rejects_non_mm_configuration() -> None:
    payload = _payload(); payload["rule_set"] = {"id":"PROJECT","version":"1.0","unit":"inch","status":"provisional"}
    with pytest.raises(ToleranceConfigurationError, match="millimetres"):
        validate_tolerance_configuration(payload)


def test_rejects_overlapping_rules() -> None:
    payload = _payload(); payload["linear"] = [
        {"minimum_mm":0,"maximum_mm":10,"lower_deviation_mm":-0.1,"upper_deviation_mm":0.1},
        {"minimum_mm":9,"maximum_mm":20,"lower_deviation_mm":-0.1,"upper_deviation_mm":0.1},
    ]
    with pytest.raises(ToleranceConfigurationError, match="overlap"):
        validate_tolerance_configuration(payload)

from __future__ import annotations

from app.drawing_interpreter import DimensionRequirement, Tolerance
from app.tolerance_resolver import resolve_tolerance
from app.tolerance_validation import validate_tolerance_configuration


def _requirement(tolerance: Tolerance | None = None) -> DimensionRequirement:
    return DimensionRequirement(1,"Linear","linear",20.0,tolerance,"dimension" if tolerance else None,None,None,"Millimetres","DIM",None)


def _rules():
    return validate_tolerance_configuration({"rule_set":{"id":"PROJECT","version":"1.0","unit":"mm","status":"approved"},"linear":[{"id":"LIN-01","minimum_mm":0,"maximum_mm":30,"lower_deviation_mm":-0.2,"upper_deviation_mm":0.2}],"angular":[],"radii_and_chamfers":[],"feature_specific":[]})


def test_explicit_tolerance_has_priority() -> None:
    result = resolve_tolerance(_requirement(Tolerance(-0.05,0.05)), True, _rules())
    assert result.source == "Explicit drawing tolerance" and result.tolerance == Tolerance(-0.05,0.05)


def test_background_rule_is_selected_by_nominal_range() -> None:
    result = resolve_tolerance(_requirement(), True, _rules())
    assert result.source == "Background rule" and result.rule_identifier == "LIN-01"


def test_missing_limit_is_deterministic_ng_input() -> None:
    result = resolve_tolerance(_requirement(), False, _rules())
    assert result.tolerance is None and "not applied" in result.reason

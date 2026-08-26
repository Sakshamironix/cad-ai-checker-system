"""Deterministic tolerance-priority resolution for normalized dimensions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.drawing_interpreter import DimensionRequirement, Tolerance
from app.tolerance_validation import ValidatedToleranceRules


@dataclass(frozen=True)
class ResolvedTolerance:
    tolerance: Tolerance | None
    source: str
    rule_identifier: str | None
    reason: str | None = None


def resolve_tolerance(requirement: DimensionRequirement, general_tolerance_applied: bool, rules: ValidatedToleranceRules) -> ResolvedTolerance:
    """Use explicit limits first; only then consider an enabled approved rule."""
    if requirement.tolerance is not None:
        return ResolvedTolerance(requirement.tolerance, "Explicit drawing tolerance", None)
    if not general_tolerance_applied:
        return ResolvedTolerance(None, "Unavailable", None, "No explicit tolerance exists and general tolerance was not applied.")
    category = "linear"
    if requirement.classification == "angle": category = "angular"
    elif requirement.classification in {"radius", "diameter", "chamfer"}: category = "radii_and_chamfers"
    if requirement.nominal_value is None:
        return ResolvedTolerance(None, "Unavailable", None, "Dimension has no nominal value.")
    candidates = [entry for entry in rules.categories[category] if float(entry["minimum_mm"]) <= requirement.nominal_value <= float(entry["maximum_mm"])]
    if len(candidates) != 1:
        return ResolvedTolerance(None, "Unavailable", None, "No applicable approved background tolerance rule exists.")
    rule: dict[str, Any] = candidates[0]
    return ResolvedTolerance(Tolerance(float(rule["lower_deviation_mm"]), float(rule["upper_deviation_mm"])), "Background rule", str(rule.get("id", f"{rules.rule_set_id}:{category}")))

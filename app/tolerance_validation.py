"""Validation for the versioned Milestone 15 tolerance-rule configuration."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REQUIRED_CATEGORIES = ("linear", "angular", "radii_and_chamfers", "feature_specific")


class ToleranceConfigurationError(ValueError):
    """Raised when a background tolerance configuration is not safe to use."""


@dataclass(frozen=True)
class ValidatedToleranceRules:
    rule_set_id: str
    version: str
    unit: str
    status: str
    categories: dict[str, tuple[dict[str, Any], ...]]


def validate_tolerance_configuration(payload: dict[str, Any]) -> ValidatedToleranceRules:
    """Validate schema and non-overlapping numeric ranges without inventing values."""
    rule_set = payload.get("rule_set")
    if not isinstance(rule_set, dict):
        raise ToleranceConfigurationError("Configuration requires a rule_set object.")
    for key in ("id", "version", "unit", "status"):
        if not isinstance(rule_set.get(key), str) or not rule_set[key].strip():
            raise ToleranceConfigurationError(f"rule_set.{key} must be a non-empty string.")
    if rule_set["unit"] != "mm":
        raise ToleranceConfigurationError("General-tolerance rules must use millimetres (mm).")

    categories: dict[str, tuple[dict[str, Any], ...]] = {}
    for category in REQUIRED_CATEGORIES:
        entries = payload.get(category)
        if not isinstance(entries, list):
            raise ToleranceConfigurationError(f"Configuration requires a {category} list.")
        normalized: list[dict[str, Any]] = []
        ranges: list[tuple[float, float]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise ToleranceConfigurationError(f"{category} entries must be objects.")
            minimum, maximum = entry.get("minimum_mm"), entry.get("maximum_mm")
            lower, upper = entry.get("lower_deviation_mm"), entry.get("upper_deviation_mm")
            if not all(isinstance(value, (int, float)) for value in (minimum, maximum, lower, upper)):
                raise ToleranceConfigurationError(f"{category} rules require numeric ranges and deviations.")
            if minimum < 0 or maximum <= minimum:
                raise ToleranceConfigurationError(f"{category} rule has an invalid nominal-size range.")
            if lower > 0 or upper < 0:
                raise ToleranceConfigurationError(f"{category} rule deviations must span zero.")
            ranges.append((float(minimum), float(maximum)))
            normalized.append(dict(entry))
        for previous, following in zip(sorted(ranges), sorted(ranges)[1:]):
            if following[0] < previous[1]:
                raise ToleranceConfigurationError(f"{category} nominal-size ranges overlap.")
        categories[category] = tuple(normalized)
    return ValidatedToleranceRules(rule_set["id"], rule_set["version"], rule_set["unit"], rule_set["status"], categories)


def load_validated_tolerance_rules(path: str | Path) -> ValidatedToleranceRules:
    """Load then validate a versioned JSON rule set."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ToleranceConfigurationError(f"Unable to load tolerance configuration: {exc}") from exc
    if not isinstance(payload, dict):
        raise ToleranceConfigurationError("Tolerance configuration root must be an object.")
    return validate_tolerance_configuration(payload)

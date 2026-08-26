"""View-aware deterministic dimension-to-drawing and STEP-feature mapping."""
from __future__ import annotations

from dataclasses import dataclass

from app.drawing_interpreter import DimensionRequirement, DrawingRequirements
from app.step_measurements import StepMeasurement, measurable_features
from app.step_reader import StepAnalysis


@dataclass(frozen=True)
class DimensionMapping:
    requirement_id: str
    view_id: str | None
    drawing_feature: str | None
    step_feature_id: str | None
    mapping_evidence: tuple[str, ...]
    confidence: str
    status: str
    reason: str | None = None


def _features_for_requirement(requirement: DimensionRequirement, step: StepAnalysis) -> tuple[StepMeasurement, ...]:
    features = measurable_features(step)
    if requirement.classification in {"diameter", "radius"}:
        return tuple(item for item in features if item.feature_type == "through hole")
    if requirement.classification in {"linear", "ordinate"}:
        return tuple(item for item in features if item.feature_id.startswith("EXTENT-"))
    return ()


def map_dimensions(requirements: DrawingRequirements, step: StepAnalysis, candidate_margin_mm: float = 0.000001) -> tuple[DimensionMapping, ...]:
    """Map only unique, type-compatible STEP features; ambiguity is an NG finding."""
    mappings: list[DimensionMapping] = []
    used_features_by_view: dict[str, set[str]] = {}
    for ordinal, requirement in enumerate(requirements.dimensions, start=1):
        requirement_id = requirement.requirement_id or f"DIM-{ordinal:03d}"
        if requirement.nominal_value is None:
            mappings.append(DimensionMapping(requirement_id, requirement.view_id, None, None, (), "None", "NG", "Dimension has no usable nominal value.")); continue
        candidates = _features_for_requirement(requirement, step)
        if not candidates:
            mappings.append(DimensionMapping(requirement_id, requirement.view_id, None, None, (), "None", "NG", "No STEP feature has a compatible deterministic type.")); continue
        ranked = sorted(candidates, key=lambda item: abs(item.value_mm - requirement.nominal_value))
        best = ranked[0]
        tied = len(ranked) > 1 and abs(abs(ranked[1].value_mm-requirement.nominal_value)-abs(best.value_mm-requirement.nominal_value)) <= candidate_margin_mm
        if tied:
            # The assigned DXF view is deterministic evidence. It lets repeated
            # same-size features be assigned one-to-one without borrowing a
            # feature from another drawing view.
            used = used_features_by_view.setdefault(requirement.view_id, set()) if requirement.view_id else set()
            available = [item for item in ranked if item.feature_id not in used]
            if requirement.view_id and available:
                best = available[0]
            else:
                mappings.append(DimensionMapping(requirement_id, requirement.view_id, None, None, (), "Low", "NG", "Multiple STEP features satisfy the same deterministic mapping conditions.")); continue
        drawing_feature = "Circular boundary" if requirement.classification in {"diameter", "radius"} else "Overall extent"
        if requirement.view_id:
            used_features_by_view.setdefault(requirement.view_id, set()).add(best.feature_id)
        mappings.append(DimensionMapping(requirement_id, requirement.view_id, drawing_feature, best.feature_id, (best.evidence, f"Type-compatible {best.feature_type}"), "High", "OK"))
    return tuple(mappings)

"""Match interpreted 2D drawing requirements with available 3D STEP features."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Final

from app.drawing_interpreter import (
    DimensionRequirement,
    DrawingRequirements,
    Tolerance,
)
from app.step_reader import StepAnalysis

DEFAULT_MATCH_TOLERANCE_MM: Final = 0.1

UNIT_TO_MILLIMETRES: Final[dict[str, float]] = {
    "Millimetres": 1.0,
    "Centimetres": 10.0,
    "Metres": 1000.0,
    "Inches": 25.4,
    "Feet": 304.8,
}

MATCHED = "matched"
OUT_OF_TOLERANCE = "out_of_tolerance"
NO_MODEL_CANDIDATE = "no_model_candidate"
UNSUPPORTED = "unsupported"
UNMATCHED_3D = "unmatched_3d"


@dataclass(frozen=True)
class FeatureMatch:
    """One traceable comparison between a 2D requirement and a 3D feature."""

    source_kind: str
    source_entity: int | None
    requirement: str
    drawing_value_mm: float | None
    model_feature: str | None
    model_value_mm: float | None
    difference_mm: float | None
    lower_deviation_mm: float | None
    upper_deviation_mm: float | None
    tolerance_source: str | None
    status: str
    confidence: str
    reason: str


@dataclass(frozen=True)
class FeatureMatchingResult:
    """Complete basic 2D-to-3D feature-matching result."""

    drawing_source: str
    model_source: str
    unit_conversion_factor_to_mm: float | None
    default_tolerance_mm: float
    matches: tuple[FeatureMatch, ...]
    warnings: tuple[str, ...]

    @property
    def matched_count(self) -> int:
        """Return the number of comparisons inside their allowed limits."""
        return sum(match.status == MATCHED for match in self.matches)

    @property
    def issue_count(self) -> int:
        """Return the number of mismatches and missing-feature findings."""
        issue_statuses = {OUT_OF_TOLERANCE, NO_MODEL_CANDIDATE, UNMATCHED_3D}
        return sum(match.status in issue_statuses for match in self.matches)

    @property
    def unresolved_count(self) -> int:
        """Return the number of unsupported comparisons requiring review."""
        return sum(match.status == UNSUPPORTED for match in self.matches)

    def to_dict(self) -> dict[str, object]:
        """Convert the result into Streamlit/JSON-friendly values."""
        result = asdict(self)
        result["matched_count"] = self.matched_count
        result["issue_count"] = self.issue_count
        result["unresolved_count"] = self.unresolved_count
        return result


def _converted_tolerance(
    tolerance: Tolerance | None,
    factor: float,
    default_tolerance_mm: float,
) -> tuple[float, float, str]:
    """Return lower/upper deviations in millimetres and their source label."""
    if tolerance is None:
        return -default_tolerance_mm, default_tolerance_mm, "prototype default"
    return (
        tolerance.lower_deviation * factor,
        tolerance.upper_deviation * factor,
        "drawing",
    )


def _comparison(
    *,
    source_kind: str,
    source_entity: int | None,
    requirement: str,
    drawing_value_mm: float,
    model_feature: str,
    model_value_mm: float,
    lower_deviation_mm: float,
    upper_deviation_mm: float,
    tolerance_source: str,
    confidence: str,
    reason_prefix: str,
) -> FeatureMatch:
    """Create a comparison and judge it against asymmetric deviation limits."""
    difference = model_value_mm - drawing_value_mm
    matched = lower_deviation_mm <= difference <= upper_deviation_mm
    status = MATCHED if matched else OUT_OF_TOLERANCE
    result_text = "within limits" if matched else "outside limits"
    return FeatureMatch(
        source_kind=source_kind,
        source_entity=source_entity,
        requirement=requirement,
        drawing_value_mm=drawing_value_mm,
        model_feature=model_feature,
        model_value_mm=model_value_mm,
        difference_mm=difference,
        lower_deviation_mm=lower_deviation_mm,
        upper_deviation_mm=upper_deviation_mm,
        tolerance_source=tolerance_source,
        status=status,
        confidence=confidence,
        reason=f"{reason_prefix}; difference {difference:+.6g} mm is {result_text}.",
    )


def _no_candidate(
    *,
    source_kind: str,
    source_entity: int | None,
    requirement: str,
    drawing_value_mm: float | None,
    reason: str,
) -> FeatureMatch:
    """Create a result when the 3D analysis has no compatible candidate."""
    return FeatureMatch(
        source_kind=source_kind,
        source_entity=source_entity,
        requirement=requirement,
        drawing_value_mm=drawing_value_mm,
        model_feature=None,
        model_value_mm=None,
        difference_mm=None,
        lower_deviation_mm=None,
        upper_deviation_mm=None,
        tolerance_source=None,
        status=NO_MODEL_CANDIDATE,
        confidence="none",
        reason=reason,
    )


def _closest_available(
    target: float,
    candidates: list[tuple[int, str, float]],
    used_indexes: set[int],
) -> tuple[int, str, float] | None:
    """Return the closest unused numeric candidate."""
    available = [candidate for candidate in candidates if candidate[0] not in used_indexes]
    if not available:
        return None
    return min(available, key=lambda candidate: abs(candidate[2] - target))


def _match_overall_size(
    requirements: DrawingRequirements,
    step: StepAnalysis,
    factor: float,
    default_tolerance_mm: float,
) -> list[FeatureMatch]:
    """Match geometry-derived 2D width/height to unique 3D bounding-box axes."""
    if requirements.drawing_size is None:
        return []

    axes = [
        (0, "Bounding box X", step.bounding_box.x),
        (1, "Bounding box Y", step.bounding_box.y),
        (2, "Bounding box Z", step.bounding_box.z),
    ]
    drawing_sizes = [
        ("Overall drawing width", requirements.drawing_size.width * factor),
        ("Overall drawing height", requirements.drawing_size.height * factor),
    ]
    used_axes: set[int] = set()
    matches: list[FeatureMatch] = []
    for label, value_mm in drawing_sizes:
        candidate = _closest_available(value_mm, axes, used_axes)
        if candidate is None:
            matches.append(
                _no_candidate(
                    source_kind="drawing extent",
                    source_entity=None,
                    requirement=label,
                    drawing_value_mm=value_mm,
                    reason="No unused 3D bounding-box axis is available.",
                )
            )
            continue
        axis_index, axis_label, axis_value = candidate
        used_axes.add(axis_index)
        matches.append(
            _comparison(
                source_kind="drawing extent",
                source_entity=None,
                requirement=label,
                drawing_value_mm=value_mm,
                model_feature=axis_label,
                model_value_mm=axis_value,
                lower_deviation_mm=-default_tolerance_mm,
                upper_deviation_mm=default_tolerance_mm,
                tolerance_source="prototype default",
                confidence="low",
                reason_prefix="Closest unique 3D bounding-box axis",
            )
        )
    return matches


def _match_linear_dimensions(
    dimensions: tuple[DimensionRequirement, ...],
    step: StepAnalysis,
    factor: float,
    default_tolerance_mm: float,
) -> list[FeatureMatch]:
    """Match linear dimensions to unique 3D bounding-box axes."""
    axes = [
        (0, "Bounding box X", step.bounding_box.x),
        (1, "Bounding box Y", step.bounding_box.y),
        (2, "Bounding box Z", step.bounding_box.z),
    ]
    used_axes: set[int] = set()
    matches: list[FeatureMatch] = []

    for dimension in dimensions:
        if dimension.classification != "linear":
            continue
        if dimension.nominal_value is None:
            matches.append(
                _no_candidate(
                    source_kind="dimension",
                    source_entity=dimension.entity_index,
                    requirement="Linear dimension",
                    drawing_value_mm=None,
                    reason="The DXF dimension has no usable nominal value.",
                )
            )
            continue
        nominal_mm = dimension.nominal_value * factor
        candidate = _closest_available(nominal_mm, axes, used_axes)
        if candidate is None:
            matches.append(
                _no_candidate(
                    source_kind="dimension",
                    source_entity=dimension.entity_index,
                    requirement="Linear dimension",
                    drawing_value_mm=nominal_mm,
                    reason="No unused 3D bounding-box axis is available.",
                )
            )
            continue
        axis_index, axis_label, axis_value = candidate
        used_axes.add(axis_index)
        lower, upper, fallback_source = _converted_tolerance(
            dimension.tolerance,
            factor,
            default_tolerance_mm,
        )
        matches.append(
            _comparison(
                source_kind="dimension",
                source_entity=dimension.entity_index,
                requirement="Linear dimension",
                drawing_value_mm=nominal_mm,
                model_feature=axis_label,
                model_value_mm=axis_value,
                lower_deviation_mm=lower,
                upper_deviation_mm=upper,
                tolerance_source=dimension.tolerance_source or fallback_source,
                confidence="medium",
                reason_prefix="Closest unique 3D bounding-box axis",
            )
        )
    return matches


def _match_cylindrical_dimensions(
    dimensions: tuple[DimensionRequirement, ...],
    step: StepAnalysis,
    factor: float,
    default_tolerance_mm: float,
    referenced_holes: set[int],
) -> list[FeatureMatch]:
    """Match diameter/radius dimensions with likely cylindrical STEP holes."""
    matches: list[FeatureMatch] = []
    used_for_dimensions: set[int] = set()

    for dimension in dimensions:
        if dimension.classification not in {"diameter", "radius"}:
            continue
        label = "Hole diameter" if dimension.classification == "diameter" else "Hole radius"
        if dimension.nominal_value is None:
            matches.append(
                _no_candidate(
                    source_kind="dimension",
                    source_entity=dimension.entity_index,
                    requirement=label,
                    drawing_value_mm=None,
                    reason="The DXF dimension has no usable nominal value.",
                )
            )
            continue

        nominal_mm = dimension.nominal_value * factor
        candidates = [
            (
                index,
                f"Likely STEP hole face {hole.face_index}",
                hole.diameter if dimension.classification == "diameter" else hole.radius,
            )
            for index, hole in enumerate(step.holes)
        ]
        candidate = _closest_available(nominal_mm, candidates, used_for_dimensions)
        if candidate is None:
            matches.append(
                _no_candidate(
                    source_kind="dimension",
                    source_entity=dimension.entity_index,
                    requirement=label,
                    drawing_value_mm=nominal_mm,
                    reason="No likely cylindrical STEP hole is available.",
                )
            )
            continue
        hole_index, hole_label, model_value = candidate
        used_for_dimensions.add(hole_index)
        referenced_holes.add(hole_index)
        lower, upper, fallback_source = _converted_tolerance(
            dimension.tolerance,
            factor,
            default_tolerance_mm,
        )
        matches.append(
            _comparison(
                source_kind="dimension",
                source_entity=dimension.entity_index,
                requirement=label,
                drawing_value_mm=nominal_mm,
                model_feature=hole_label,
                model_value_mm=model_value,
                lower_deviation_mm=lower,
                upper_deviation_mm=upper,
                tolerance_source=dimension.tolerance_source or fallback_source,
                confidence="medium",
                reason_prefix="Closest likely STEP hole by size",
            )
        )
    return matches


def _match_circle_candidates(
    requirements: DrawingRequirements,
    step: StepAnalysis,
    factor: float,
    default_tolerance_mm: float,
    referenced_holes: set[int],
) -> list[FeatureMatch]:
    """Match DXF circles with likely STEP holes using diameter only."""
    candidates = [
        (index, f"Likely STEP hole face {hole.face_index}", hole.diameter)
        for index, hole in enumerate(step.holes)
    ]
    used_for_circles: set[int] = set()
    matches: list[FeatureMatch] = []

    for circle in requirements.hole_candidates:
        diameter_mm = circle.diameter * factor
        candidate = _closest_available(diameter_mm, candidates, used_for_circles)
        if candidate is None:
            matches.append(
                _no_candidate(
                    source_kind="circle candidate",
                    source_entity=circle.entity_index,
                    requirement="Circle diameter",
                    drawing_value_mm=diameter_mm,
                    reason="No unused likely cylindrical STEP hole is available.",
                )
            )
            continue
        hole_index, hole_label, hole_diameter = candidate
        used_for_circles.add(hole_index)
        referenced_holes.add(hole_index)
        matches.append(
            _comparison(
                source_kind="circle candidate",
                source_entity=circle.entity_index,
                requirement="Circle diameter",
                drawing_value_mm=diameter_mm,
                model_feature=hole_label,
                model_value_mm=hole_diameter,
                lower_deviation_mm=-default_tolerance_mm,
                upper_deviation_mm=default_tolerance_mm,
                tolerance_source="prototype default",
                confidence="medium",
                reason_prefix="Closest likely STEP hole by diameter",
            )
        )
    return matches


def _unsupported_dimensions(
    dimensions: tuple[DimensionRequirement, ...],
    factor: float,
) -> list[FeatureMatch]:
    """Return explicit review rows for dimension classes not yet matchable."""
    matches: list[FeatureMatch] = []
    for dimension in dimensions:
        if dimension.classification in {"linear", "diameter", "radius"}:
            continue
        value_mm = (
            dimension.nominal_value * factor
            if dimension.nominal_value is not None and dimension.classification != "angle"
            else dimension.nominal_value
        )
        matches.append(
            FeatureMatch(
                source_kind="dimension",
                source_entity=dimension.entity_index,
                requirement=f"{dimension.classification.title()} dimension",
                drawing_value_mm=value_mm,
                model_feature=None,
                model_value_mm=None,
                difference_mm=None,
                lower_deviation_mm=None,
                upper_deviation_mm=None,
                tolerance_source=dimension.tolerance_source,
                status=UNSUPPORTED,
                confidence="none",
                reason="This dimension class cannot be matched with the current STEP feature data.",
            )
        )
    return matches


def match_features(
    requirements: DrawingRequirements,
    step: StepAnalysis,
    default_tolerance_mm: float = DEFAULT_MATCH_TOLERANCE_MM,
) -> FeatureMatchingResult:
    """Match basic 2D requirements with available 3D STEP measurements."""
    if default_tolerance_mm <= 0:
        raise ValueError("default_tolerance_mm must be greater than zero")

    factor = UNIT_TO_MILLIMETRES.get(requirements.units_name)
    warnings = [
        "Hole matching currently uses diameter or radius only; center position and axis are not yet compared.",
        "Drawing extents are matched with low confidence because annotations can enlarge DXF extents.",
    ]
    if factor is None:
        warnings.append(
            f"DXF units '{requirements.units_name}' cannot be converted to millimetres."
        )
        return FeatureMatchingResult(
            drawing_source=requirements.source_name,
            model_source=step.source_name,
            unit_conversion_factor_to_mm=None,
            default_tolerance_mm=default_tolerance_mm,
            matches=(),
            warnings=tuple(warnings),
        )

    matches: list[FeatureMatch] = []
    referenced_holes: set[int] = set()
    matches.extend(_match_overall_size(requirements, step, factor, default_tolerance_mm))
    matches.extend(
        _match_linear_dimensions(
            requirements.dimensions,
            step,
            factor,
            default_tolerance_mm,
        )
    )
    matches.extend(
        _match_cylindrical_dimensions(
            requirements.dimensions,
            step,
            factor,
            default_tolerance_mm,
            referenced_holes,
        )
    )
    matches.extend(
        _match_circle_candidates(
            requirements,
            step,
            factor,
            default_tolerance_mm,
            referenced_holes,
        )
    )
    matches.extend(_unsupported_dimensions(requirements.dimensions, factor))

    for hole_index, hole in enumerate(step.holes):
        if hole_index in referenced_holes:
            continue
        matches.append(
            FeatureMatch(
                source_kind="3D feature",
                source_entity=None,
                requirement="Likely STEP hole without a matched 2D requirement",
                drawing_value_mm=None,
                model_feature=f"Likely STEP hole face {hole.face_index}",
                model_value_mm=hole.diameter,
                difference_mm=None,
                lower_deviation_mm=None,
                upper_deviation_mm=None,
                tolerance_source=None,
                status=UNMATCHED_3D,
                confidence="medium",
                reason="No DXF circle or diameter/radius requirement referenced this likely STEP hole.",
            )
        )

    return FeatureMatchingResult(
        drawing_source=requirements.source_name,
        model_source=step.source_name,
        unit_conversion_factor_to_mm=factor,
        default_tolerance_mm=default_tolerance_mm,
        matches=tuple(matches),
        warnings=tuple(warnings),
    )

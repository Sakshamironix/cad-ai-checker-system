"""Build operator-friendly dashboard rows from deterministic comparison evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from app.comparison_rules import EngineeringJudgement
from app.feature_matcher import FeatureMatch, FeatureMatchingResult
from app.profile_comparison import ProfileComparisonResult


@dataclass(frozen=True)
class DashboardRow:
    """One result row shown in the Milestone 7 comparison dashboard."""

    check_number: int
    outcome: str
    rule_id: str
    requirement: str
    drawing_value_mm: float | None
    allowed_minimum_mm: float | None
    allowed_maximum_mm: float | None
    model_feature: str | None
    model_value_mm: float | None
    difference_mm: float | None
    outside_limit_by_mm: float | None
    confidence: str
    source_entity: int | None
    reason: str

    def to_dict(self) -> dict[str, object]:
        """Return a stable dictionary for Streamlit tables."""
        return asdict(self)


@dataclass(frozen=True)
class SummaryRow:
    """Compact judgement-first row shown before technical evidence."""

    judgement: str
    category: str
    check: str
    drawing_value: float | int | str | None
    model_value: float | int | str | None
    difference: float | None
    tolerance: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _allowed_limit(
    nominal: float | None,
    deviation: float | None,
) -> float | None:
    if nominal is None or deviation is None:
        return None
    return nominal + deviation


def _outside_limit_by(match: FeatureMatch) -> float | None:
    """Return signed distance beyond the violated limit, or zero inside limits."""
    difference = match.difference_mm
    lower = match.lower_deviation_mm
    upper = match.upper_deviation_mm
    if difference is None or lower is None or upper is None:
        return None
    if difference < lower:
        return difference - lower
    if difference > upper:
        return difference - upper
    return 0.0


def build_dashboard_rows(
    matching_result: FeatureMatchingResult,
    judgement: EngineeringJudgement,
) -> tuple[DashboardRow, ...]:
    """Join every rule finding to the feature evidence used to produce it."""
    if matching_result.drawing_source != judgement.drawing_source:
        raise ValueError("Drawing sources do not match")
    if matching_result.model_source != judgement.model_source:
        raise ValueError("Model sources do not match")

    rows: list[DashboardRow] = []
    for check_number, finding in enumerate(judgement.findings, start=1):
        match: FeatureMatch | None = None
        if finding.match_index is not None:
            match_offset = finding.match_index - 1
            if match_offset < 0 or match_offset >= len(matching_result.matches):
                raise ValueError("Rule finding references an invalid feature match")
            match = matching_result.matches[match_offset]

        rows.append(
            DashboardRow(
                check_number=check_number,
                outcome=finding.outcome,
                rule_id=finding.rule_id,
                requirement=finding.requirement or finding.title,
                drawing_value_mm=(match.drawing_value_mm if match else None),
                allowed_minimum_mm=(
                    _allowed_limit(match.drawing_value_mm, match.lower_deviation_mm)
                    if match
                    else None
                ),
                allowed_maximum_mm=(
                    _allowed_limit(match.drawing_value_mm, match.upper_deviation_mm)
                    if match
                    else None
                ),
                model_feature=(match.model_feature if match else None),
                model_value_mm=(match.model_value_mm if match else None),
                difference_mm=(match.difference_mm if match else None),
                outside_limit_by_mm=(_outside_limit_by(match) if match else None),
                confidence=(match.confidence if match else "none"),
                source_entity=finding.source_entity,
                reason=finding.message,
            )
        )
    return tuple(rows)


def build_summary_rows(
    matching_result: FeatureMatchingResult,
    judgement: EngineeringJudgement,
    profile_result: ProfileComparisonResult,
) -> tuple[SummaryRow, ...]:
    """Return dimensions first, followed by profile checks."""
    detailed_rows = build_dashboard_rows(matching_result, judgement)
    rows: list[SummaryRow] = []
    for row in detailed_rows:
        if row.drawing_value_mm is None and row.model_value_mm is None:
            continue
        tolerance = "Fallback comparison limit"
        if row.allowed_minimum_mm is not None and row.allowed_maximum_mm is not None:
            tolerance = f"{row.allowed_minimum_mm:.6g} to {row.allowed_maximum_mm:.6g} mm"
        rows.append(
            SummaryRow(
                judgement=row.outcome,
                category="Dimension",
                check=row.requirement,
                drawing_value=row.drawing_value_mm,
                model_value=row.model_value_mm,
                difference=row.difference_mm,
                tolerance=tolerance,
            )
        )

    for check in profile_result.checks:
        rows.append(
            SummaryRow(
                judgement=check.judgement,
                category=check.category,
                check=check.feature,
                drawing_value=check.drawing_value,
                model_value=check.model_value,
                difference=check.difference,
                tolerance=(
                    f"±{check.tolerance:.6g} mm" if check.tolerance is not None else "Not applicable"
                ),
            )
        )
    return tuple(rows)

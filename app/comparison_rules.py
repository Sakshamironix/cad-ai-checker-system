"""Rule engine for traceable prototype engineering judgements."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from app.feature_matcher import (
    MATCHED,
    NO_MODEL_CANDIDATE,
    OUT_OF_TOLERANCE,
    UNMATCHED_3D,
    UNSUPPORTED,
    FeatureMatch,
    FeatureMatchingResult,
)

PASS = "PASS"
FAIL = "FAIL"
REVIEW = "REVIEW"


@dataclass(frozen=True)
class RulePolicy:
    """Explicit policy controlling how feature-match statuses affect judgement."""

    fail_on_missing_model_candidate: bool = True
    fail_on_unmatched_3d_feature: bool = True
    low_confidence_requires_review: bool = True
    unsupported_requires_review: bool = True
    minimum_comparisons: int = 1

    def __post_init__(self) -> None:
        if self.minimum_comparisons < 1:
            raise ValueError("minimum_comparisons must be at least 1")


@dataclass(frozen=True)
class RuleFinding:
    """One rule outcome linked to a feature match."""

    rule_id: str
    outcome: str
    title: str
    message: str
    match_index: int | None
    source_entity: int | None
    requirement: str | None


@dataclass(frozen=True)
class EngineeringJudgement:
    """Final prototype judgement and its complete rule trace."""

    drawing_source: str
    model_source: str
    decision: str
    release_allowed: bool
    decision_reason: str
    policy: RulePolicy
    findings: tuple[RuleFinding, ...]
    warnings: tuple[str, ...]

    @property
    def pass_count(self) -> int:
        return sum(finding.outcome == PASS for finding in self.findings)

    @property
    def fail_count(self) -> int:
        return sum(finding.outcome == FAIL for finding in self.findings)

    @property
    def review_count(self) -> int:
        return sum(finding.outcome == REVIEW for finding in self.findings)

    @property
    def decisive_count(self) -> int:
        return self.pass_count + self.fail_count

    @property
    def pass_rate_percent(self) -> float | None:
        if self.decisive_count == 0:
            return None
        return (self.pass_count / self.decisive_count) * 100.0

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["pass_count"] = self.pass_count
        result["fail_count"] = self.fail_count
        result["review_count"] = self.review_count
        result["decisive_count"] = self.decisive_count
        result["pass_rate_percent"] = self.pass_rate_percent
        return result


def _finding_for_match(
    match: FeatureMatch,
    match_index: int,
    policy: RulePolicy,
) -> RuleFinding:
    """Evaluate one feature match against the active policy."""
    common = {
        "match_index": match_index,
        "source_entity": match.source_entity,
        "requirement": match.requirement,
    }

    if match.status == OUT_OF_TOLERANCE:
        return RuleFinding(
            rule_id="R-002",
            outcome=FAIL,
            title="Tolerance violation",
            message=match.reason,
            **common,
        )

    if match.status == NO_MODEL_CANDIDATE:
        outcome = FAIL if policy.fail_on_missing_model_candidate else REVIEW
        return RuleFinding(
            rule_id="R-003",
            outcome=outcome,
            title="Missing compatible 3D feature",
            message=match.reason,
            **common,
        )

    if match.status == UNMATCHED_3D:
        outcome = FAIL if policy.fail_on_unmatched_3d_feature else REVIEW
        return RuleFinding(
            rule_id="R-004",
            outcome=outcome,
            title="Unmatched 3D feature",
            message=match.reason,
            **common,
        )

    if match.status == UNSUPPORTED:
        outcome = REVIEW if policy.unsupported_requires_review else PASS
        return RuleFinding(
            rule_id="R-005",
            outcome=outcome,
            title="Unsupported requirement",
            message=match.reason,
            **common,
        )

    if match.status == MATCHED:
        if match.difference_mm is None or match.model_value_mm is None:
            return RuleFinding(
                rule_id="R-006",
                outcome=REVIEW,
                title="Incomplete comparison evidence",
                message="The match is marked successful but required numeric evidence is missing.",
                **common,
            )
        if match.confidence == "low" and policy.low_confidence_requires_review:
            return RuleFinding(
                rule_id="R-007",
                outcome=REVIEW,
                title="Low-confidence match",
                message=(
                    f"The numeric comparison is within limits, but the match confidence is low. "
                    f"{match.reason}"
                ),
                **common,
            )
        return RuleFinding(
            rule_id="R-001",
            outcome=PASS,
            title="Requirement within limits",
            message=match.reason,
            **common,
        )

    return RuleFinding(
        rule_id="R-999",
        outcome=REVIEW,
        title="Unknown matching status",
        message=f"Unsupported feature-match status: {match.status}",
        **common,
    )


def _decision(findings: tuple[RuleFinding, ...], policy: RulePolicy) -> tuple[str, str]:
    """Resolve the overall decision using failure-first precedence."""
    fail_count = sum(finding.outcome == FAIL for finding in findings)
    review_count = sum(finding.outcome == REVIEW for finding in findings)
    pass_count = sum(finding.outcome == PASS for finding in findings)

    if fail_count:
        return FAIL, f"{fail_count} mandatory comparison rule(s) failed."
    if review_count:
        return REVIEW, f"{review_count} item(s) require engineering review."
    if pass_count < policy.minimum_comparisons:
        return REVIEW, (
            f"Only {pass_count} decisive comparison(s) were available; "
            f"at least {policy.minimum_comparisons} are required."
        )
    return PASS, f"All {pass_count} decisive comparison rule(s) passed."


def evaluate_matching_result(
    result: FeatureMatchingResult,
    policy: RulePolicy | None = None,
) -> EngineeringJudgement:
    """Evaluate feature matches and produce a final prototype judgement."""
    active_policy = policy or RulePolicy()
    findings = tuple(
        _finding_for_match(match, match_index, active_policy)
        for match_index, match in enumerate(result.matches, start=1)
    )

    if not findings:
        findings = (
            RuleFinding(
                rule_id="R-000",
                outcome=REVIEW,
                title="No comparable evidence",
                message="No 2D-to-3D feature comparisons were available for judgement.",
                match_index=None,
                source_entity=None,
                requirement=None,
            ),
        )

    decision, reason = _decision(findings, active_policy)
    warnings = list(result.warnings)
    warnings.append(
        "This is a prototype engineering judgement and must not be treated as production release approval."
    )

    return EngineeringJudgement(
        drawing_source=result.drawing_source,
        model_source=result.model_source,
        decision=decision,
        release_allowed=decision == PASS,
        decision_reason=reason,
        policy=active_policy,
        findings=findings,
        warnings=tuple(warnings),
    )

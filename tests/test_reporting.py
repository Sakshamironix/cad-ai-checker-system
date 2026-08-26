"""Tests for ordered final JSON and PDF report generation."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from app.comparison_rules import NG, evaluate_matching_result
from app.feature_matcher import OUT_OF_TOLERANCE, FeatureMatch, FeatureMatchingResult
from app.general_tolerances import GeneralToleranceSet
from app.profile_comparison import OK, ProfileCheck, ProfileComparisonResult
from app.projection import Point2D, ProjectedPrimitive, StepProjection
from app.reporting import NOT_GOOD_LABEL, build_final_report


def _matching_result() -> FeatureMatchingResult:
    return FeatureMatchingResult(
        drawing_source="ring.dxf",
        model_source="ring.step",
        unit_conversion_factor_to_mm=1.0,
        default_tolerance_mm=0.1,
        matches=(
            FeatureMatch(
                source_kind="dimension",
                source_entity=4,
                requirement="Outer diameter",
                drawing_value_mm=50.0,
                model_feature="Projected outer diameter",
                model_value_mm=50.3,
                difference_mm=0.3,
                lower_deviation_mm=-0.1,
                upper_deviation_mm=0.1,
                tolerance_source="drawing",
                status=OUT_OF_TOLERANCE,
                confidence="high",
                reason="Difference +0.3 mm is outside limits.",
            ),
        ),
        warnings=("Synthetic warning",),
        general_tolerances=GeneralToleranceSet.uniform(0.1).with_application(False),
    )


def _profile_result() -> ProfileComparisonResult:
    points = (Point2D(0.0, 0.0), Point2D(50.0, 0.0))
    projection = StepProjection(
        view="top",
        width=50.0,
        height=0.0,
        primitives=(ProjectedPrimitive("line", points),),
    )
    return ProfileComparisonResult(
        drawing_source="ring.dxf",
        model_source="ring.step",
        selected_view="top",
        judgement=OK,
        reason="Profile is OK.",
        checks=(
            ProfileCheck(
                category="Profile",
                feature="Overall profile width",
                drawing_value=50.0,
                model_value=50.0,
                difference=0.0,
                tolerance=0.1,
                judgement=OK,
                details="Difference is within limits.",
            ),
        ),
        dxf_primitives=(),
        step_projection=projection,
    )


def _report():
    matching = _matching_result()
    judgement = evaluate_matching_result(matching)
    return build_final_report(
        matching,
        judgement,
        _profile_result(),
        generated_at_utc="2026-08-21T00:00:00+00:00",
    )


def test_report_sections_follow_required_order() -> None:
    report = _report()

    assert list(report.to_dict()) == [
        "judgement",
        "report_information",
        "files",
        "millimetre_units",
        "detected_drawing_views",
        "view_to_step_mapping",
        "general_tolerance",
        "dimension_summary",
        "dimension_to_feature_mapping",
        "profile_summary",
        "ng_findings",
        "ai_assistance",
        "detailed_evidence",
        "warnings",
        "limitations",
    ]
    assert report.overall_judgement == NG
    assert report.judgement_label == NOT_GOOD_LABEL
    assert report.ng_findings[0]["category"] == "Dimension"


def test_json_report_is_complete_and_hides_background_values() -> None:
    report = _report()
    payload = json.loads(report.to_json_bytes())

    assert payload["judgement"]["label"] == "NG (Not Good)"
    assert payload["general_tolerance"]["applied"] is False
    assert payload["general_tolerance"]["rule_source"] == "Background rule set"
    assert "linear_mm" not in payload["general_tolerance"]
    assert payload["dimension_summary"][0]["judgement"] == NG
    assert payload["dimension_to_feature_mapping"] == []


def test_pdf_report_is_a_nonempty_pdf() -> None:
    pdf = _report().to_pdf_bytes()

    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 3000
    assert b"%%EOF" in pdf[-32:]


def test_pdf_report_renders_view_and_mapping_findings_without_rule_ids() -> None:
    report = replace(
        _report(),
        ng_findings=(
            {
                "category": "View",
                "view": "VIEW-01",
                "check": "Unknown view",
                "details": "No deterministic STEP match.",
            },
            {
                "category": "Feature mapping",
                "requirement": "DIM-01",
                "view": "VIEW-01",
                "check": "Unmapped feature",
                "details": "Dimension mapping is NG.",
            },
        ),
    )

    pdf = report.to_pdf_bytes()

    assert pdf.startswith(b"%PDF-")
    assert b"%%EOF" in pdf[-32:]


def test_report_rejects_mismatched_profile_source() -> None:
    matching = _matching_result()
    judgement = evaluate_matching_result(matching)
    profile = _profile_result()
    wrong_profile = ProfileComparisonResult(
        drawing_source="other.dxf",
        model_source=profile.model_source,
        selected_view=profile.selected_view,
        judgement=profile.judgement,
        reason=profile.reason,
        checks=profile.checks,
        dxf_primitives=profile.dxf_primitives,
        step_projection=profile.step_projection,
    )

    with pytest.raises(ValueError, match="Profile drawing source"):
        build_final_report(matching, judgement, wrong_profile)


def test_report_includes_assistance_without_changing_judgement() -> None:
    matching = _matching_result()
    judgement = evaluate_matching_result(matching)
    assistance = {
        "source": "test",
        "overall_judgement": NG,
        "summary_en": "Evidence explanation.",
        "summary_ja": "証拠の説明。",
        "findings": [],
        "safety_notice_en": "Assistance only.",
    }

    report = build_final_report(
        matching,
        judgement,
        _profile_result(),
        ai_assistance=assistance,
        generated_at_utc="2026-08-21T00:00:00+00:00",
    )

    assert report.overall_judgement == NG
    assert report.to_dict()["ai_assistance"] == assistance
    assert report.to_pdf_bytes().startswith(b"%PDF-")


def test_report_rejects_assistance_with_different_judgement() -> None:
    matching = _matching_result()
    judgement = evaluate_matching_result(matching)

    with pytest.raises(ValueError, match="does not match deterministic judgement"):
        build_final_report(
            matching,
            judgement,
            _profile_result(),
            ai_assistance={"overall_judgement": OK},
        )

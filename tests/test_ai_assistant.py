"""Tests for guarded local and OpenAI-assisted discrepancy explanations."""

from __future__ import annotations

from dataclasses import dataclass
import json

import pytest

from app.ai_assistant import (
    AIConfigurationError,
    AIResponseError,
    build_deterministic_explanation,
    generate_openai_explanation,
)
from app.comparison_rules import NG, evaluate_matching_result
from app.feature_matcher import OUT_OF_TOLERANCE, FeatureMatch, FeatureMatchingResult
from app.general_tolerances import GeneralToleranceSet
from app.profile_comparison import OK, ProfileCheck, ProfileComparisonResult
from app.projection import Point2D, ProjectedPrimitive, StepProjection
from app.reporting import build_final_report


def _report():
    matching = FeatureMatchingResult(
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
        warnings=(),
        general_tolerances=GeneralToleranceSet.uniform(0.1),
    )
    points = (Point2D(0.0, 0.0), Point2D(50.0, 0.0))
    profile = ProfileComparisonResult(
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
        step_projection=StepProjection(
            view="top",
            width=50.0,
            height=0.0,
            primitives=(ProjectedPrimitive("line", points),),
        ),
    )
    judgement = evaluate_matching_result(matching)
    return build_final_report(
        matching,
        judgement,
        profile,
        generated_at_utc="2026-08-21T00:00:00+00:00",
    )


def _response_payload() -> dict[str, object]:
    return {
        "summary_en": "NG is caused by one dimension discrepancy.",
        "summary_ja": "1件の寸法差異によりNGです。",
        "findings": [
            {
                "category": "Dimension",
                "check": "Outer diameter",
                "explanation_en": "The measured diameter is outside its limit.",
                "explanation_ja": "測定直径が限界外です。",
                "likely_causes_en": ["Model revision difference."],
                "likely_causes_ja": ["モデル改訂差。"],
                "recommended_checks_en": ["Confirm the matched feature."],
                "recommended_checks_ja": ["対応フィーチャーを確認してください。"],
            }
        ],
        "drawing_notes": [
            {
                "note": "REMOVE BURRS",
                "interpretation_en": "Deburr the part.",
                "interpretation_ja": "バリを除去してください。",
            }
        ],
    }


@dataclass
class _FakeResponse:
    output_text: str


class _FakeResponses:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.kwargs: dict[str, object] = {}

    def create(self, **kwargs: object) -> _FakeResponse:
        self.kwargs = kwargs
        return _FakeResponse(json.dumps(self.payload, ensure_ascii=False))


class _FakeClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.responses = _FakeResponses(payload)


def test_local_explanation_preserves_ng_and_evidence() -> None:
    report = _report()

    explanation = build_deterministic_explanation(report, ("REMOVE BURRS",))

    assert explanation.overall_judgement == NG
    assert explanation.findings[0].check == "Outer diameter"
    assert explanation.findings[0].evidence == report.ng_findings[0]["details"]
    assert explanation.drawing_notes[0].note == "REMOVE BURRS"
    assert "NG" in explanation.summary_en


def test_openai_request_uses_normalized_evidence_and_strict_schema() -> None:
    client = _FakeClient(_response_payload())

    explanation = generate_openai_explanation(
        _report(),
        ("REMOVE BURRS",),
        client=client,
        model="test-model",
    )

    assert explanation.overall_judgement == NG
    assert explanation.model == "test-model"
    request = client.responses.kwargs
    assert request["model"] == "test-model"
    assert request["text"]["format"]["strict"] is True
    transmitted = json.loads(request["input"])
    assert transmitted["immutable_judgement"] == NG
    assert transmitted["drawing_notes"] == ["REMOVE BURRS"]
    assert "raw_cad" not in transmitted


def test_openai_response_cannot_change_finding_identity() -> None:
    payload = _response_payload()
    payload["findings"][0]["check"] = "Invented feature"

    with pytest.raises(AIResponseError, match="changed deterministic finding identity"):
        generate_openai_explanation(
            _report(),
            ("REMOVE BURRS",),
            client=_FakeClient(payload),
            model="test-model",
        )


def test_missing_api_key_has_clear_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(AIConfigurationError, match="OPENAI_API_KEY"):
        generate_openai_explanation(_report())

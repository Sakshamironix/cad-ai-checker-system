"""Tests for guarded local and dual-provider discrepancy explanations."""

from __future__ import annotations

import json

import pytest

from app.ai_assistant import (
    AIConfigurationError,
    AIResponseError,
    ai_provider_status,
    build_deterministic_explanation,
    generate_ai_explanation,
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


class _FakeCaller:
    def __init__(self, payload: dict[str, object] | None = None, error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error
        self.calls: list[dict[str, object]] = []

    def __call__(
        self,
        api_key: str,
        model: str,
        normalized_evidence: str,
        schema: dict[str, object],
    ) -> str:
        self.calls.append(
            {
                "api_key": api_key,
                "model": model,
                "evidence": normalized_evidence,
                "schema": schema,
            }
        )
        if self.error is not None:
            raise self.error
        assert self.payload is not None
        return json.dumps(self.payload, ensure_ascii=False)


def test_local_explanation_preserves_ng_and_evidence() -> None:
    report = _report()

    explanation = build_deterministic_explanation(report, ("REMOVE BURRS",))

    assert explanation.overall_judgement == NG
    assert explanation.findings[0].check == "Outer diameter"
    assert explanation.findings[0].evidence == report.ng_findings[0]["details"]
    assert explanation.drawing_notes[0].note == "REMOVE BURRS"
    assert "NG" in explanation.summary_en


def test_gemini_primary_uses_normalized_evidence_and_schema() -> None:
    gemini = _FakeCaller(_response_payload())
    groq = _FakeCaller(_response_payload())

    explanation = generate_ai_explanation(
        _report(),
        ("REMOVE BURRS",),
        gemini_caller=gemini,
        groq_caller=groq,
        gemini_api_key="gemini-test-key",
        groq_api_key="groq-test-key",
        gemini_model="gemini-test-model",
    )

    assert explanation.overall_judgement == NG
    assert explanation.source == "Gemini primary assistance"
    assert explanation.model == "gemini-test-model"
    assert len(gemini.calls) == 1
    assert groq.calls == []
    request = gemini.calls[0]
    assert request["model"] == "gemini-test-model"
    assert request["schema"]["additionalProperties"] is False
    transmitted = json.loads(request["evidence"])
    assert transmitted["immutable_judgement"] == NG
    assert transmitted["drawing_notes"] == ["REMOVE BURRS"]
    assert "raw_cad" not in transmitted


def test_groq_is_used_when_gemini_fails() -> None:
    gemini = _FakeCaller(error=AIResponseError("temporary Gemini failure"))
    groq = _FakeCaller(_response_payload())

    explanation = generate_ai_explanation(
        _report(),
        ("REMOVE BURRS",),
        gemini_caller=gemini,
        groq_caller=groq,
        gemini_api_key="gemini-test-key",
        groq_api_key="groq-test-key",
        groq_model="groq-test-model",
    )

    assert len(gemini.calls) == 1
    assert len(groq.calls) == 1
    assert explanation.source == "Groq fallback assistance"
    assert explanation.model == "groq-test-model"
    assert explanation.overall_judgement == NG


def test_provider_response_cannot_change_finding_identity() -> None:
    payload = _response_payload()
    payload["findings"][0]["check"] = "Invented feature"

    with pytest.raises(AIResponseError, match="All configured AI providers failed"):
        generate_ai_explanation(
            _report(),
            ("REMOVE BURRS",),
            gemini_caller=_FakeCaller(payload),
            gemini_api_key="gemini-test-key",
        )


def test_missing_api_keys_have_clear_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    with pytest.raises(AIConfigurationError, match="GEMINI_API_KEY.*GROQ_API_KEY"):
        generate_ai_explanation(_report())


def test_provider_status_never_returns_secret_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "private-gemini-value")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    assert ai_provider_status() == {"gemini": True, "groq": False}

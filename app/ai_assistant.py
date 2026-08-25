"""Guarded AI assistance for explaining deterministic CAD comparison results.

The geometry and rule engines decide OK/NG before this module is called.  This
module can explain that evidence, but it cannot replace or change the decision.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from typing import Callable, Final
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.reporting import FinalReport


DEFAULT_GEMINI_MODEL: Final = "gemini-3.5-flash"
DEFAULT_GROQ_MODEL: Final = "llama-3.3-70b-versatile"
HTTP_TIMEOUT_SECONDS: Final = 45


class AIConfigurationError(RuntimeError):
    """Raised when optional external AI assistance is unavailable."""


class AIResponseError(RuntimeError):
    """Raised when an AI response is incomplete or changes evidence identity."""


ProviderCaller = Callable[[str, str, str, dict[str, object]], str]


@dataclass(frozen=True)
class AssistanceFinding:
    """Explanation attached to one immutable deterministic NG finding."""

    category: str
    check: str
    evidence: str
    explanation_en: str
    explanation_ja: str
    likely_causes_en: tuple[str, ...]
    likely_causes_ja: tuple[str, ...]
    recommended_checks_en: tuple[str, ...]
    recommended_checks_ja: tuple[str, ...]


@dataclass(frozen=True)
class NoteInterpretation:
    """Plain-language interpretation of one drawing note."""

    note: str
    interpretation_en: str
    interpretation_ja: str


@dataclass(frozen=True)
class AIExplanation:
    """Bilingual assistance that carries the pre-existing OK/NG judgement."""

    source: str
    model: str | None
    overall_judgement: str
    summary_en: str
    summary_ja: str
    findings: tuple[AssistanceFinding, ...]
    drawing_notes: tuple[NoteInterpretation, ...]
    safety_notice_en: str = (
        "Assistance only. The deterministic geometry and tolerance engines remain "
        "the authority for OK/NG. Verify suggested causes before corrective action."
    )
    safety_notice_ja: str = (
        "説明支援のみです。OK/NGの判定は決定論的な形状・公差エンジンが行います。"
        "是正処置の前に推定原因を確認してください。"
    )

    def to_dict(self) -> dict[str, object]:
        """Return a report-ready representation."""
        return asdict(self)


def _possible_causes(category: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if category == "Profile":
        return (
            (
                "The manufactured or modeled profile differs from the drawing profile.",
                "The selected projection or 90-degree registration is not the intended drawing view.",
                "The DXF and STEP files may represent different revisions.",
            ),
            (
                "製作品またはモデルの輪郭が図面輪郭と異なる可能性があります。",
                "選択した投影方向または90度単位の位置合わせが意図した図面ビューと異なる可能性があります。",
                "DXFとSTEPが異なる改訂版である可能性があります。",
            ),
        )
    return (
        (
            "The model dimension differs from the drawing requirement.",
            "The drawing and model may represent different revisions or units.",
            "The automatic feature match may have selected a different geometric feature.",
        ),
        (
            "モデル寸法が図面要求と異なる可能性があります。",
            "図面とモデルの改訂または単位が異なる可能性があります。",
            "自動フィーチャーマッチングが別の形状を選択した可能性があります。",
        ),
    )


def _recommended_checks(category: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if category == "Profile":
        return (
            (
                "Confirm the intended STEP projection against the drawing view.",
                "Inspect the red overlay regions and compare file revision identifiers.",
            ),
            (
                "意図したSTEP投影方向が図面ビューと一致するか確認してください。",
                "赤色の重ね合わせ領域を確認し、ファイルの改訂識別を比較してください。",
            ),
        )
    return (
        (
            "Verify the matched 2D requirement and 3D feature refer to the same feature.",
            "Confirm units, revisions, and the applicable explicit or general tolerance rule.",
        ),
        (
            "対応する2D要求と3Dフィーチャーが同一箇所を示すか確認してください。",
            "単位、改訂、および適用される明示公差または普通公差ルールを確認してください。",
        ),
    )


def build_deterministic_explanation(
    report: FinalReport,
    drawing_notes: tuple[str, ...] = (),
) -> AIExplanation:
    """Build a useful local explanation without an external AI service."""
    if report.overall_judgement == "OK":
        summary_en = (
            "The deterministic checker returned OK because all available dimension "
            "and projected-profile comparisons are within their applicable limits."
        )
        summary_ja = (
            "利用可能な寸法および投影輪郭の比較がすべて適用限界内のため、"
            "決定論的チェッカーはOKと判定しました。"
        )
    else:
        count = len(report.ng_findings)
        summary_en = (
            f"The deterministic checker returned NG because {count} comparison "
            "finding(s) require correction or verification."
        )
        summary_ja = (
            f"{count}件の比較結果で修正または確認が必要なため、"
            "決定論的チェッカーはNG（不合格）と判定しました。"
        )

    findings: list[AssistanceFinding] = []
    for finding in report.ng_findings:
        category = str(finding["category"])
        check = str(finding["check"])
        evidence = str(finding["details"])
        causes_en, causes_ja = _possible_causes(category)
        checks_en, checks_ja = _recommended_checks(category)
        findings.append(
            AssistanceFinding(
                category=category,
                check=check,
                evidence=evidence,
                explanation_en=f"{check} is NG based on this evidence: {evidence}",
                explanation_ja=f"{check}は次の証拠に基づきNGです：{evidence}",
                likely_causes_en=causes_en,
                likely_causes_ja=causes_ja,
                recommended_checks_en=checks_en,
                recommended_checks_ja=checks_ja,
            )
        )

    notes = tuple(
        NoteInterpretation(
            note=note,
            interpretation_en=(
                "Drawing note retained for engineering review. Confirm its applicability "
                "to the inspected feature and tolerance rules."
            ),
            interpretation_ja=(
                "技術確認用に図面注記を保持しています。検査対象フィーチャーおよび"
                "公差ルールへの適用性を確認してください。"
            ),
        )
        for note in drawing_notes
        if note.strip()
    )
    return AIExplanation(
        source="local deterministic assistance",
        model=None,
        overall_judgement=report.overall_judgement,
        summary_en=summary_en,
        summary_ja=summary_ja,
        findings=tuple(findings),
        drawing_notes=notes,
    )


def ai_provider_status() -> dict[str, bool]:
    """Return provider availability without exposing credential values."""
    return {
        "gemini": bool(os.environ.get("GEMINI_API_KEY", "").strip()),
        "groq": bool(os.environ.get("GROQ_API_KEY", "").strip()),
    }


def ai_is_configured() -> bool:
    """Return whether at least one external explanation provider is configured."""
    return any(ai_provider_status().values())


def _response_schema() -> dict[str, object]:
    string_array = {"type": "array", "items": {"type": "string"}}
    finding_properties = {
        "category": {"type": "string"},
        "check": {"type": "string"},
        "explanation_en": {"type": "string"},
        "explanation_ja": {"type": "string"},
        "likely_causes_en": string_array,
        "likely_causes_ja": string_array,
        "recommended_checks_en": string_array,
        "recommended_checks_ja": string_array,
    }
    note_properties = {
        "note": {"type": "string"},
        "interpretation_en": {"type": "string"},
        "interpretation_ja": {"type": "string"},
    }
    return {
        "type": "object",
        "properties": {
            "summary_en": {"type": "string"},
            "summary_ja": {"type": "string"},
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": finding_properties,
                    "required": list(finding_properties),
                    "additionalProperties": False,
                },
            },
            "drawing_notes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": note_properties,
                    "required": list(note_properties),
                    "additionalProperties": False,
                },
            },
        },
        "required": ["summary_en", "summary_ja", "findings", "drawing_notes"],
        "additionalProperties": False,
    }


def _ai_input(report: FinalReport, drawing_notes: tuple[str, ...]) -> str:
    payload = {
        "immutable_judgement": report.overall_judgement,
        "decision_reason": report.decision_reason,
        "general_tolerance_applied": report.general_tolerance_applied,
        "dimension_summary": list(report.dimension_summary),
        "profile_summary": list(report.profile_summary),
        "ng_findings": list(report.ng_findings),
        "drawing_notes": list(drawing_notes),
        "limitations": list(report.limitations),
    }
    return json.dumps(payload, ensure_ascii=False, allow_nan=False)


def _post_json(url: str, headers: dict[str, str], payload: dict[str, object]) -> dict[str, object]:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            response_body = response.read().decode("utf-8")
    except HTTPError as exc:
        raise AIResponseError(f"provider HTTP request failed with status {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise AIResponseError(f"provider connection failed: {type(exc).__name__}") from exc
    try:
        decoded = json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise AIResponseError("provider returned invalid response JSON") from exc
    if not isinstance(decoded, dict):
        raise AIResponseError("provider response must be a JSON object")
    return decoded


def _gemini_request(
    api_key: str,
    model: str,
    normalized_evidence: str,
    schema: dict[str, object],
) -> str:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    response = _post_json(
        url,
        {"x-goog-api-key": api_key},
        {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": _provider_prompt(normalized_evidence)}],
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": schema,
            },
        },
    )
    try:
        text = response["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AIResponseError("Gemini returned no explanation text") from exc
    if not isinstance(text, str) or not text.strip():
        raise AIResponseError("Gemini returned no explanation text")
    return text


def _groq_request(
    api_key: str,
    model: str,
    normalized_evidence: str,
    schema: dict[str, object],
) -> str:
    del schema  # Groq JSON Object Mode is validated locally against our schema rules.
    response = _post_json(
        "https://api.groq.com/openai/v1/chat/completions",
        {"Authorization": f"Bearer {api_key}"},
        {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": _system_instruction(),
                },
                {
                    "role": "user",
                    "content": normalized_evidence,
                },
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        },
    )
    try:
        text = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AIResponseError("Groq returned no explanation text") from exc
    if not isinstance(text, str) or not text.strip():
        raise AIResponseError("Groq returned no explanation text")
    return text


def _system_instruction() -> str:
    return (
        "You are an engineering inspection explanation assistant. The supplied OK/NG "
        "judgement and evidence are immutable. Never create or change a judgement, "
        "measurement, tolerance, finding identity, or drawing-note text. Explain every "
        "finding in concise English and Japanese. Possible causes are hypotheses only; "
        "state practical verification checks. Return only one JSON object matching the "
        "requested fields."
    )


def _provider_prompt(normalized_evidence: str) -> str:
    return f"{_system_instruction()}\n\nNormalized evidence:\n{normalized_evidence}"


def _required_text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AIResponseError(f"AI response field '{key}' must be non-empty text")
    return value.strip()


def _text_tuple(payload: dict[str, object], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise AIResponseError(f"AI response field '{key}' must be a text list")
    return tuple(item.strip() for item in value)


def _validated_explanation(
    report: FinalReport,
    drawing_notes: tuple[str, ...],
    payload: dict[str, object],
    model: str,
    source: str,
) -> AIExplanation:
    raw_findings = payload.get("findings")
    if not isinstance(raw_findings, list) or len(raw_findings) != len(report.ng_findings):
        raise AIResponseError("AI response must explain every deterministic NG finding exactly once")

    findings: list[AssistanceFinding] = []
    for raw, evidence in zip(raw_findings, report.ng_findings, strict=True):
        if not isinstance(raw, dict):
            raise AIResponseError("Each AI finding must be an object")
        category = _required_text(raw, "category")
        check = _required_text(raw, "check")
        if category != evidence["category"] or check != evidence["check"]:
            raise AIResponseError("AI response changed deterministic finding identity")
        causes_en = _text_tuple(raw, "likely_causes_en")
        causes_ja = _text_tuple(raw, "likely_causes_ja")
        checks_en = _text_tuple(raw, "recommended_checks_en")
        checks_ja = _text_tuple(raw, "recommended_checks_ja")
        if len(causes_en) != len(causes_ja):
            raise AIResponseError("English and Japanese cause lists must have equal length")
        if len(checks_en) != len(checks_ja):
            raise AIResponseError("English and Japanese check lists must have equal length")
        findings.append(
            AssistanceFinding(
                category=category,
                check=check,
                evidence=str(evidence["details"]),
                explanation_en=_required_text(raw, "explanation_en"),
                explanation_ja=_required_text(raw, "explanation_ja"),
                likely_causes_en=causes_en,
                likely_causes_ja=causes_ja,
                recommended_checks_en=checks_en,
                recommended_checks_ja=checks_ja,
            )
        )

    raw_notes = payload.get("drawing_notes")
    if not isinstance(raw_notes, list) or len(raw_notes) != len(drawing_notes):
        raise AIResponseError("AI response must interpret each supplied drawing note exactly once")
    notes: list[NoteInterpretation] = []
    for raw, original in zip(raw_notes, drawing_notes, strict=True):
        if not isinstance(raw, dict) or raw.get("note") != original:
            raise AIResponseError("AI response changed drawing-note text or order")
        notes.append(
            NoteInterpretation(
                note=original,
                interpretation_en=_required_text(raw, "interpretation_en"),
                interpretation_ja=_required_text(raw, "interpretation_ja"),
            )
        )

    return AIExplanation(
        source=source,
        model=model,
        overall_judgement=report.overall_judgement,
        summary_en=_required_text(payload, "summary_en"),
        summary_ja=_required_text(payload, "summary_ja"),
        findings=tuple(findings),
        drawing_notes=tuple(notes),
    )


def generate_ai_explanation(
    report: FinalReport,
    drawing_notes: tuple[str, ...] = (),
    *,
    gemini_caller: ProviderCaller | None = None,
    groq_caller: ProviderCaller | None = None,
    gemini_api_key: str | None = None,
    groq_api_key: str | None = None,
    gemini_model: str | None = None,
    groq_model: str | None = None,
) -> AIExplanation:
    """Explain normalized evidence with Gemini first and Groq as fallback."""
    active_gemini_key = (
        gemini_api_key if gemini_api_key is not None else os.environ.get("GEMINI_API_KEY", "")
    ).strip()
    active_groq_key = (
        groq_api_key if groq_api_key is not None else os.environ.get("GROQ_API_KEY", "")
    ).strip()
    active_gemini_model = (
        gemini_model or os.environ.get("GEMINI_MODEL", "")
    ).strip() or DEFAULT_GEMINI_MODEL
    active_groq_model = (
        groq_model or os.environ.get("GROQ_MODEL", "")
    ).strip() or DEFAULT_GROQ_MODEL
    normalized_evidence = _ai_input(report, drawing_notes)
    schema = _response_schema()
    providers: list[tuple[str, str, str, ProviderCaller]] = []
    if active_gemini_key:
        providers.append(
            ("Gemini primary assistance", active_gemini_key, active_gemini_model, gemini_caller or _gemini_request)
        )
    if active_groq_key:
        providers.append(
            ("Groq fallback assistance", active_groq_key, active_groq_model, groq_caller or _groq_request)
        )
    if not providers:
        raise AIConfigurationError(
            "Neither GEMINI_API_KEY nor GROQ_API_KEY is configured. "
            "Local deterministic assistance remains available."
        )

    failures: list[str] = []
    for source, api_key, model, caller in providers:
        provider_name = source.split()[0]
        try:
            output_text = caller(api_key, model, normalized_evidence, schema)
            payload = json.loads(output_text)
            if not isinstance(payload, dict):
                raise AIResponseError("response must be a JSON object")
            return _validated_explanation(
                report,
                drawing_notes,
                payload,
                model,
                source,
            )
        except json.JSONDecodeError:
            failures.append(f"{provider_name}: invalid structured JSON")
        except Exception as exc:
            failures.append(f"{provider_name}: {exc}")

    raise AIResponseError("All configured AI providers failed. " + " | ".join(failures))

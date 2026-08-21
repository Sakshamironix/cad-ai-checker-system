"""Create ordered JSON and PDF reports from deterministic CAD comparison evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from io import BytesIO
import json
from typing import Final, Sequence

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    LongTable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.comparison_rules import NG, OK, EngineeringJudgement
from app.dashboard import build_dashboard_rows
from app.feature_matcher import FeatureMatchingResult
from app.overlay import OverlayVisualization
from app.profile_comparison import ProfileComparisonResult


REPORT_SCHEMA_VERSION: Final = "1.0"
NOT_GOOD_LABEL: Final = "NG (Not Good)"


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _display(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


@dataclass(frozen=True)
class FinalReport:
    """Judgement-first final report ready for JSON and PDF download."""

    generated_at_utc: str
    overall_judgement: str
    judgement_label: str
    decision_reason: str
    drawing_source: str
    model_source: str
    general_tolerance_applied: bool
    dimension_summary: tuple[dict[str, object], ...]
    profile_summary: tuple[dict[str, object], ...]
    ng_findings: tuple[dict[str, object], ...]
    ai_assistance: dict[str, object] | None
    detailed_dimension_evidence: tuple[dict[str, object], ...]
    detailed_profile_evidence: tuple[dict[str, object], ...]
    visual_evidence: dict[str, object] | None
    warnings: tuple[str, ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return sections in the required report-reading order."""
        return {
            "report_information": {
                "schema_version": REPORT_SCHEMA_VERSION,
                "generated_at_utc": self.generated_at_utc,
                "report_type": "CAD drawing-to-model comparison",
            },
            "judgement": {
                "result": self.overall_judgement,
                "label": self.judgement_label,
                "reason": self.decision_reason,
            },
            "files": {
                "drawing_2d": self.drawing_source,
                "model_3d": self.model_source,
            },
            "general_tolerance": {
                "applied": self.general_tolerance_applied,
                "operator_display": "Applied" if self.general_tolerance_applied else "Not applied",
                "rule_source": "Background rule set",
            },
            "dimension_summary": list(self.dimension_summary),
            "profile_summary": list(self.profile_summary),
            "ng_findings": list(self.ng_findings),
            "ai_assistance": self.ai_assistance,
            "detailed_evidence": {
                "dimensions": list(self.detailed_dimension_evidence),
                "profiles": list(self.detailed_profile_evidence),
                "visual_overlay": self.visual_evidence,
            },
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
        }

    def to_json_bytes(self) -> bytes:
        """Serialize the complete report as readable UTF-8 JSON."""
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        ).encode("utf-8")

    def to_pdf_bytes(self) -> bytes:
        """Render the complete report as an ordered, multi-page PDF."""
        return _render_pdf(self)


def build_final_report(
    matching_result: FeatureMatchingResult,
    judgement: EngineeringJudgement,
    profile_result: ProfileComparisonResult,
    overlay: OverlayVisualization | None = None,
    *,
    ai_assistance: dict[str, object] | None = None,
    generated_at_utc: str | None = None,
) -> FinalReport:
    """Build one final report from results produced by the same CAD file pair."""
    if matching_result.drawing_source != judgement.drawing_source:
        raise ValueError("Drawing sources do not match")
    if matching_result.model_source != judgement.model_source:
        raise ValueError("Model sources do not match")
    if profile_result.drawing_source != judgement.drawing_source:
        raise ValueError("Profile drawing source does not match")
    if profile_result.model_source != judgement.model_source:
        raise ValueError("Profile model source does not match")

    overall = NG if NG in {judgement.decision, profile_result.judgement} else OK
    dimension_rows = build_dashboard_rows(matching_result, judgement)
    dimension_summary = tuple(
        {
            "judgement": row.outcome,
            "check": row.requirement,
            "drawing_mm": row.drawing_value_mm,
            "model_mm": row.model_value_mm,
            "difference_mm": row.difference_mm,
            "allowed_minimum_mm": row.allowed_minimum_mm,
            "allowed_maximum_mm": row.allowed_maximum_mm,
        }
        for row in dimension_rows
        if row.drawing_value_mm is not None or row.model_value_mm is not None
    )
    profile_summary = tuple(
        {
            "judgement": check.judgement,
            "check": check.feature,
            "drawing_value": check.drawing_value,
            "model_value": check.model_value,
            "difference_mm": check.difference,
            "applicable_limit_mm": check.tolerance,
        }
        for check in profile_result.checks
    )

    dimension_ng = tuple(
        {
            "category": "Dimension",
            "rule": finding.rule_id,
            "check": finding.requirement or finding.title,
            "details": finding.message,
        }
        for finding in judgement.findings
        if finding.outcome == NG
    )
    profile_ng = tuple(
        {
            "category": "Profile",
            "rule": "PROFILE",
            "check": check.feature,
            "details": check.details,
        }
        for check in profile_result.checks
        if check.judgement == NG
    )

    detailed_dimensions = tuple(row.to_dict() for row in dimension_rows)
    detailed_profiles = tuple(
        {
            "judgement": check.judgement,
            "category": check.category,
            "feature": check.feature,
            "drawing_value": check.drawing_value,
            "model_value": check.model_value,
            "difference_mm": check.difference,
            "tolerance_mm": check.tolerance,
            "details": check.details,
        }
        for check in profile_result.checks
    )
    visual_evidence = None
    if overlay is not None:
        visual_evidence = {
            "alignment_rotation_degrees": overlay.alignment_quarter_turns * 90,
            "dxf_mismatched_geometry_count": overlay.dxf_mismatch_count,
            "step_mismatched_geometry_count": overlay.step_mismatch_count,
            "mismatch_classification_enabled": matching_result.general_tolerances.applied,
        }

    limitations = [
        "This report is a prototype engineering aid and is not production release approval.",
        "Profile alignment currently centers geometry and tests rotations in 90-degree steps.",
        "Feature-position tolerance is reserved until position comparison is implemented.",
    ]
    if not matching_result.general_tolerances.applied:
        limitations.append(
            "General tolerance was not applied; requirements without explicit limits are NG."
        )

    if ai_assistance is not None:
        assisted_judgement = ai_assistance.get("overall_judgement")
        if assisted_judgement != overall:
            raise ValueError("Assisted explanation judgement does not match deterministic judgement")

    return FinalReport(
        generated_at_utc=generated_at_utc or _now_utc(),
        overall_judgement=overall,
        judgement_label=OK if overall == OK else NOT_GOOD_LABEL,
        decision_reason=(
            "Dimension and profile comparisons are OK."
            if overall == OK
            else "One or more dimension or profile comparisons are NG."
        ),
        drawing_source=judgement.drawing_source,
        model_source=judgement.model_source,
        general_tolerance_applied=matching_result.general_tolerances.applied,
        dimension_summary=dimension_summary,
        profile_summary=profile_summary,
        ng_findings=dimension_ng + profile_ng,
        ai_assistance=ai_assistance,
        detailed_dimension_evidence=detailed_dimensions,
        detailed_profile_evidence=detailed_profiles,
        visual_evidence=visual_evidence,
        warnings=tuple(dict.fromkeys((*judgement.warnings, *matching_result.warnings))),
        limitations=tuple(limitations),
    )


def _pdf_table(
    headers: Sequence[str],
    rows: Sequence[Sequence[object]],
    widths: Sequence[float],
    body_style: ParagraphStyle,
) -> LongTable:
    data = [
        [Paragraph(f"<b>{escape(header)}</b>", body_style) for header in headers]
    ]
    data.extend(
        [Paragraph(escape(_display(value)), body_style) for value in row]
        for row in rows
    )
    table = LongTable(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4e78")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#aab7c4")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f6f8")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _render_pdf(report: FinalReport) -> bytes:
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=15 * mm,
        bottomMargin=16 * mm,
        title="CAD AI Checker Final Report",
        author="CAD AI Checker",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#17365d"),
        spaceAfter=8,
    )
    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#1f4e78"),
        spaceBefore=8,
        spaceAfter=5,
    )
    body_style = ParagraphStyle(
        "ReportBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=9.5,
    )
    judgement_style = ParagraphStyle(
        "Judgement",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=26,
        alignment=TA_CENTER,
        textColor=colors.white,
    )

    story: list[object] = [
        Paragraph("CAD AI Checker — Final Comparison Report", title_style),
        Paragraph(
            f"Generated: {escape(report.generated_at_utc)} · Schema: {REPORT_SCHEMA_VERSION}",
            body_style,
        ),
        Spacer(1, 5 * mm),
    ]
    judgement_color = colors.HexColor("#198754" if report.overall_judgement == OK else "#c62828")
    judgement_box = Table(
        [[Paragraph(escape(report.judgement_label), judgement_style)]],
        colWidths=[182 * mm],
    )
    judgement_box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), judgement_color),
                ("BOX", (0, 0), (-1, -1), 0.8, judgement_color),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    story.extend(
        [
            judgement_box,
            Spacer(1, 3 * mm),
            Paragraph(escape(report.decision_reason), body_style),
            Paragraph("1. Identification and tolerance state", section_style),
            _pdf_table(
                ("Item", "Value"),
                (
                    ("2D drawing", report.drawing_source),
                    ("3D model", report.model_source),
                    (
                        "General tolerance",
                        "Applied" if report.general_tolerance_applied else "Not applied",
                    ),
                    ("Rule source", "Background rule set"),
                ),
                (52 * mm, 130 * mm),
                body_style,
            ),
            Paragraph("2. Dimension summary", section_style),
            _pdf_table(
                ("Result", "Check", "Drawing", "Model", "Difference", "Allowed range"),
                tuple(
                    (
                        row["judgement"],
                        row["check"],
                        row["drawing_mm"],
                        row["model_mm"],
                        row["difference_mm"],
                        (
                            f'{_display(row["allowed_minimum_mm"])} to '
                            f'{_display(row["allowed_maximum_mm"])}'
                            if row["allowed_minimum_mm"] is not None
                            else "No authorized limit"
                        ),
                    )
                    for row in report.dimension_summary
                ),
                (16 * mm, 52 * mm, 24 * mm, 24 * mm, 24 * mm, 42 * mm),
                body_style,
            ),
            Paragraph("3. Profile summary", section_style),
            _pdf_table(
                ("Result", "Check", "Drawing", "Model", "Difference", "Limit"),
                tuple(
                    (
                        row["judgement"],
                        row["check"],
                        row["drawing_value"],
                        row["model_value"],
                        row["difference_mm"],
                        row["applicable_limit_mm"],
                    )
                    for row in report.profile_summary
                ),
                (16 * mm, 52 * mm, 24 * mm, 24 * mm, 24 * mm, 42 * mm),
                body_style,
            ),
            Paragraph("4. NG findings", section_style),
        ]
    )
    if report.ng_findings:
        story.append(
            _pdf_table(
                ("Category", "Rule", "Check", "Details"),
                tuple(
                    (row["category"], row["rule"], row["check"], row["details"])
                    for row in report.ng_findings
                ),
                (24 * mm, 20 * mm, 50 * mm, 88 * mm),
                body_style,
            )
        )
    else:
        story.append(Paragraph("No NG findings.", body_style))

    story.append(Paragraph("5. Assisted explanation", section_style))
    if report.ai_assistance is None:
        story.append(Paragraph("No assisted explanation was included.", body_style))
    else:
        story.append(
            Paragraph(
                escape(str(report.ai_assistance.get("summary_en", "—"))),
                body_style,
            )
        )
        for finding in report.ai_assistance.get("findings", []):
            if isinstance(finding, dict):
                story.append(
                    Paragraph(
                        "<b>" + escape(str(finding.get("check", "Finding"))) + "</b>: "
                        + escape(str(finding.get("explanation_en", "—"))),
                        body_style,
                    )
                )
        story.append(
            Paragraph(
                escape(str(report.ai_assistance.get("safety_notice_en", ""))),
                body_style,
            )
        )

    story.extend(
        [
            PageBreak(),
            Paragraph("6. Detailed dimension evidence", section_style),
            _pdf_table(
                ("#", "Result", "Rule", "Requirement", "3D feature", "Difference", "Details"),
                tuple(
                    (
                        row["check_number"],
                        row["outcome"],
                        row["rule_id"],
                        row["requirement"],
                        row["model_feature"],
                        row["difference_mm"],
                        row["reason"],
                    )
                    for row in report.detailed_dimension_evidence
                ),
                (9 * mm, 15 * mm, 16 * mm, 38 * mm, 35 * mm, 22 * mm, 47 * mm),
                body_style,
            ),
            Paragraph("7. Detailed profile evidence", section_style),
            _pdf_table(
                ("Result", "Feature", "Drawing", "Model", "Difference", "Limit", "Details"),
                tuple(
                    (
                        row["judgement"],
                        row["feature"],
                        row["drawing_value"],
                        row["model_value"],
                        row["difference_mm"],
                        row["tolerance_mm"],
                        row["details"],
                    )
                    for row in report.detailed_profile_evidence
                ),
                (15 * mm, 38 * mm, 20 * mm, 20 * mm, 20 * mm, 18 * mm, 51 * mm),
                body_style,
            ),
            Paragraph("8. Warnings and limitations", section_style),
        ]
    )
    for warning in report.warnings:
        story.append(Paragraph(f"• {escape(warning)}", body_style))
    for limitation in report.limitations:
        story.append(Paragraph(f"• {escape(limitation)}", body_style))

    def add_page_number(canvas: object, doc: object) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#5b6573"))
        canvas.drawRightString(196 * mm, 8 * mm, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    return buffer.getvalue()

"""Milestone 11 Streamlit entry point for the CAD AI Checker."""

from __future__ import annotations

from pathlib import Path
from typing import Final

import streamlit as st

from app.ai_assistant import (
    AIConfigurationError,
    AIExplanation,
    AIResponseError,
    build_deterministic_explanation,
    generate_openai_explanation,
    openai_is_configured,
)
from app.comparison_rules import (
    NG,
    OK,
    EngineeringJudgement,
    evaluate_matching_result,
)
from app.dashboard import build_dashboard_rows, build_summary_rows
from app.drawing_interpreter import DrawingRequirements, interpret_dxf_analysis
from app.dxf_reader import DxfAnalysis, DxfReaderError, analyze_dxf_bytes
from app.feature_matcher import FeatureMatchingResult, match_features
from app.general_tolerances import PROVISIONAL_GENERAL_TOLERANCES
from app.overlay import OverlayError, build_overlay_visualization
from app.profile_comparison import (
    ProfileComparisonError,
    ProfileComparisonResult,
    compare_uploaded_profiles,
)
from app.reporting import build_final_report
from app.step_reader import StepAnalysis, StepReaderError, analyze_step_bytes

APP_NAME: Final = "CAD AI Checker"
APP_STAGE: Final = "Milestone 11 — AI-assisted explanations / マイルストーン11 — AI説明支援"


def _bilingual(english: str, japanese: str) -> str:
    """Return one consistent English/Japanese predefined dashboard label."""
    return f"{english} / {japanese}"


def get_app_status() -> dict[str, str]:
    """Return the visible application state used by the UI and setup test."""
    return {
        "application": APP_NAME,
        "stage": APP_STAGE,
        "capability": (
            "Guarded bilingual discrepancy explanations after deterministic OK/NG / "
            "決定論的OK/NG判定後の保護された日英不一致説明"
        ),
    }


def _render_step_results(analysis: StepAnalysis) -> None:
    """Render a complete STEP analysis in a compact engineering layout."""
    st.success(f"Successfully analyzed {analysis.source_name}")

    st.subheader("Topology")
    topology_columns = st.columns(5)
    topology_values = (
        ("Solids", analysis.topology.solids),
        ("Shells", analysis.topology.shells),
        ("Faces", analysis.topology.faces),
        ("Edges", analysis.topology.edges),
        ("Vertices", analysis.topology.vertices),
    )
    for column, (label, value) in zip(topology_columns, topology_values, strict=True):
        column.metric(label, value)

    st.subheader("Model dimensions")
    st.dataframe(
        {
            "Axis": ["X", "Y", "Z"],
            "Bounding-box size": [
                analysis.bounding_box.x,
                analysis.bounding_box.y,
                analysis.bounding_box.z,
            ],
        },
        hide_index=True,
        use_container_width=True,
    )

    property_columns = st.columns(3)
    property_columns[0].metric("Volume", f"{analysis.volume:.6g}")
    property_columns[1].metric("Surface area", f"{analysis.surface_area:.6g}")
    property_columns[2].metric(
        "Center of mass",
        f"({analysis.center_of_mass.x:.4g}, {analysis.center_of_mass.y:.4g}, "
        f"{analysis.center_of_mass.z:.4g})",
    )

    st.subheader("Detected geometry")
    geometry_columns = st.columns(5)
    geometry_values = (
        ("Planar faces", analysis.planar_faces),
        ("Cylindrical faces", analysis.cylindrical_faces),
        ("Circular edges", analysis.circular_edges),
        ("Likely holes", analysis.hole_count),
        ("Outer boundaries", analysis.outer_boundaries),
    )
    for column, (label, value) in zip(geometry_columns, geometry_values, strict=True):
        column.metric(label, value)

    if analysis.holes:
        st.subheader("Likely cylindrical holes")
        st.dataframe(
            [
                {
                    "Face": hole.face_index,
                    "Radius": hole.radius,
                    "Diameter": hole.diameter,
                }
                for hole in analysis.holes
            ],
            hide_index=True,
            use_container_width=True,
        )

    st.caption(
        "Units are inherited from the STEP model. STEP geometry commonly uses millimetres, "
        "but the file itself controls the actual unit conversion."
    )
    with st.expander("Complete analysis data"):
        st.json(analysis.to_dict())


def _render_interpreted_requirements(requirements: DrawingRequirements) -> None:
    """Render structured engineering requirements derived from DXF entities."""
    st.subheader("Interpreted engineering requirements")
    requirement_columns = st.columns(4)
    requirement_columns[0].metric("Dimensions", len(requirements.dimensions))
    requirement_columns[1].metric(
        "Resolved dimensions", requirements.resolved_dimension_count
    )
    requirement_columns[2].metric("With tolerance", requirements.tolerance_count)
    requirement_columns[3].metric("Hole candidates", len(requirements.hole_candidates))

    if requirements.general_tolerance is not None:
        st.info(
            "General tolerance detected: "
            f"{requirements.general_tolerance.lower_deviation:+g} / "
            f"{requirements.general_tolerance.upper_deviation:+g}"
        )

    if requirements.drawing_size is not None:
        st.caption(
            "Geometry-derived drawing size: "
            f"{requirements.drawing_size.width:.6g} × "
            f"{requirements.drawing_size.height:.6g} "
            f"{requirements.drawing_size.unit}. This is not treated as a dimensioned tolerance."
        )

    if requirements.dimensions:
        st.markdown("#### Normalized dimensions")
        st.dataframe(
            [
                {
                    "Entity": dimension.entity_index,
                    "Class": dimension.classification,
                    "Type": dimension.dimension_type,
                    "Nominal": dimension.nominal_value,
                    "Lower deviation": (
                        dimension.tolerance.lower_deviation
                        if dimension.tolerance is not None
                        else None
                    ),
                    "Upper deviation": (
                        dimension.tolerance.upper_deviation
                        if dimension.tolerance is not None
                        else None
                    ),
                    "Minimum": dimension.minimum_value,
                    "Maximum": dimension.maximum_value,
                    "Tolerance source": dimension.tolerance_source,
                    "Unit": dimension.unit,
                    "Layer": dimension.layer,
                }
                for dimension in requirements.dimensions
            ],
            hide_index=True,
            use_container_width=True,
        )

    if requirements.hole_candidates:
        st.markdown("#### Circle-based hole candidates")
        st.dataframe(
            [
                {
                    "Entity": hole.entity_index,
                    "Layer": hole.layer,
                    "Center X": hole.center.x,
                    "Center Y": hole.center.y,
                    "Diameter": hole.diameter,
                    "Unit": hole.unit,
                }
                for hole in requirements.hole_candidates
            ],
            hide_index=True,
            use_container_width=True,
        )
        st.caption(
            "Circles are candidates only. Use the 2D ↔ 3D Match tab to compare them with "
            "likely cylindrical features in the STEP model."
        )

    for warning in requirements.warnings:
        st.warning(warning)

    with st.expander("Complete interpreted requirement data"):
        st.json(requirements.to_dict())


def _render_dxf_results(
    analysis: DxfAnalysis,
    requirements: DrawingRequirements,
) -> None:
    """Render DXF analysis results in a compact engineering layout."""
    st.success(f"Successfully analyzed {analysis.source_name}")

    summary_columns = st.columns(4)
    summary_columns[0].metric("DXF version", analysis.dxf_version)
    summary_columns[1].metric("Units", analysis.units_name)
    summary_columns[2].metric("Layers", len(analysis.layers))
    summary_columns[3].metric("Entities", analysis.entity_counts.total)

    st.subheader("Drawing extents")
    if analysis.extents is None:
        st.warning("No measurable model-space extents were found.")
    else:
        extent_columns = st.columns(4)
        extent_columns[0].metric("Width", f"{analysis.extents.width:.6g}")
        extent_columns[1].metric("Height", f"{analysis.extents.height:.6g}")
        extent_columns[2].metric(
            "Minimum",
            f"({analysis.extents.minimum.x:.4g}, {analysis.extents.minimum.y:.4g})",
        )
        extent_columns[3].metric(
            "Maximum",
            f"({analysis.extents.maximum.x:.4g}, {analysis.extents.maximum.y:.4g})",
        )

    st.subheader("Model-space entities")
    st.dataframe(
        [
            {"Entity type": entity_type, "Count": count}
            for entity_type, count in analysis.entity_types.items()
        ],
        hide_index=True,
        use_container_width=True,
    )

    if analysis.circles:
        st.subheader("Circles")
        st.dataframe(
            [
                {
                    "Entity": circle.entity_index,
                    "Layer": circle.layer,
                    "Center X": circle.center.x,
                    "Center Y": circle.center.y,
                    "Radius": circle.radius,
                    "Diameter": circle.diameter,
                }
                for circle in analysis.circles
            ],
            hide_index=True,
            use_container_width=True,
        )

    if analysis.arcs:
        st.subheader("Arcs")
        st.dataframe(
            [
                {
                    "Entity": arc.entity_index,
                    "Layer": arc.layer,
                    "Center X": arc.center.x,
                    "Center Y": arc.center.y,
                    "Radius": arc.radius,
                    "Start angle": arc.start_angle,
                    "End angle": arc.end_angle,
                }
                for arc in analysis.arcs
            ],
            hide_index=True,
            use_container_width=True,
        )

    if analysis.dimensions:
        st.subheader("Dimensions")
        st.dataframe(
            [
                {
                    "Entity": dimension.entity_index,
                    "Layer": dimension.layer,
                    "Type": dimension.dimension_type,
                    "Measurement": dimension.measurement,
                    "Text override": dimension.text_override,
                    "Style": dimension.style,
                }
                for dimension in analysis.dimensions
            ],
            hide_index=True,
            use_container_width=True,
        )

    if analysis.texts:
        st.subheader("Drawing text")
        st.dataframe(
            [
                {
                    "Entity": annotation.entity_index,
                    "Type": annotation.entity_type,
                    "Layer": annotation.layer,
                    "Content": annotation.content,
                }
                for annotation in analysis.texts
            ],
            hide_index=True,
            use_container_width=True,
        )

    st.caption(f"Drawing layers: {', '.join(analysis.layers)}")
    with st.expander("Complete DXF analysis data"):
        st.json(analysis.to_dict())

    _render_interpreted_requirements(requirements)


def _render_feature_matches(result: FeatureMatchingResult) -> None:
    """Render basic 2D-to-3D feature-matching results."""
    st.success(f"Compared {result.drawing_source} with {result.model_source}")
    summary_columns = st.columns(4)
    summary_columns[0].metric("Comparisons", len(result.matches))
    summary_columns[1].metric("Matched", result.matched_count)
    summary_columns[2].metric("Issues", result.issue_count)
    summary_columns[3].metric("Unresolved", result.unresolved_count)

    if result.matches:
        st.dataframe(
            [
                {
                    "Status": match.status,
                    "2D source": match.source_kind,
                    "Entity": match.source_entity,
                    "Requirement": match.requirement,
                    "Drawing value (mm)": match.drawing_value_mm,
                    "3D feature": match.model_feature,
                    "Model value (mm)": match.model_value_mm,
                    "Difference (mm)": match.difference_mm,
                    "Lower deviation (mm)": match.lower_deviation_mm,
                    "Upper deviation (mm)": match.upper_deviation_mm,
                    "Tolerance source": match.tolerance_source,
                    "Confidence": match.confidence,
                    "Reason": match.reason,
                }
                for match in result.matches
            ],
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.warning("No comparable features were produced.")

    for warning in result.warnings:
        st.warning(warning)

    with st.expander("Complete feature-matching data"):
        st.json(result.to_dict())


def _render_engineering_judgement(judgement: EngineeringJudgement) -> None:
    """Render the dimension-rule judgement without a third review state."""
    if judgement.decision == OK:
        st.success(f"Dimension judgement: {judgement.decision}")
    else:
        st.error(f"Dimension judgement: {judgement.decision}")
    st.write(judgement.decision_reason)

    summary_columns = st.columns(3)
    summary_columns[0].metric("OK checks", judgement.pass_count)
    summary_columns[1].metric("NG checks", judgement.fail_count)
    summary_columns[2].metric(
        "OK rate",
        (
            f"{judgement.pass_rate_percent:.1f}%"
            if judgement.pass_rate_percent is not None
            else "0.0%"
        ),
    )

    st.dataframe(
        [
            {
                "Rule": finding.rule_id,
                "Outcome": finding.outcome,
                "Title": finding.title,
                "Match": finding.match_index,
                "DXF entity": finding.source_entity,
                "Requirement": finding.requirement,
                "Message": finding.message,
            }
            for finding in judgement.findings
        ],
        hide_index=True,
        use_container_width=True,
    )

    for warning in judgement.warnings:
        st.warning(warning)

    with st.expander("Complete engineering judgement data"):
        st.json(judgement.to_dict())


def _render_assisted_explanation(explanation: AIExplanation) -> None:
    """Render bilingual assistance while keeping the source and safety boundary visible."""
    source_label = explanation.source
    if explanation.model is not None:
        source_label = f"{source_label} ({explanation.model})"
    st.caption(_bilingual(f"Explanation source: {source_label}", f"説明ソース：{source_label}"))
    st.info(f"{explanation.summary_en}\n\n{explanation.summary_ja}")

    for index, finding in enumerate(explanation.findings, start=1):
        with st.expander(f"{index}. {finding.category} — {finding.check}", expanded=index == 1):
            st.write(finding.explanation_en)
            st.write(finding.explanation_ja)
            cause_columns = st.columns(2)
            with cause_columns[0]:
                st.markdown("**Possible causes / 推定原因**")
                for english, japanese in zip(
                    finding.likely_causes_en,
                    finding.likely_causes_ja,
                    strict=True,
                ):
                    st.markdown(f"- {english}\n  \n  {japanese}")
            with cause_columns[1]:
                st.markdown("**Recommended checks / 推奨確認**")
                for english, japanese in zip(
                    finding.recommended_checks_en,
                    finding.recommended_checks_ja,
                    strict=True,
                ):
                    st.markdown(f"- {english}\n  \n  {japanese}")

    if explanation.drawing_notes:
        with st.expander(_bilingual("Drawing-note interpretation", "図面注記の解釈")):
            for note in explanation.drawing_notes:
                st.markdown(f"**{note.note}**")
                st.write(note.interpretation_en)
                st.write(note.interpretation_ja)

    st.warning(f"{explanation.safety_notice_en}\n\n{explanation.safety_notice_ja}")


def _render_step_uploader() -> None:
    """Render the independent STEP/STP upload workflow."""
    st.write(
        "Upload a small STEP or STP model to inspect its topology, dimensions, physical "
        "properties, and basic geometry."
    )
    uploaded_file = st.file_uploader(
        "STEP/STP model",
        type=["step", "stp"],
        accept_multiple_files=False,
        help="Prototype limit: 25 MB. Start with a small single part.",
        key="step_upload",
    )

    if uploaded_file is None:
        st.info("Select a STEP or STP file to begin 3D analysis.")
        return

    try:
        with st.spinner("Reading STEP geometry with OpenCASCADE..."):
            analysis = analyze_step_bytes(uploaded_file.getvalue(), uploaded_file.name)
    except StepReaderError as exc:
        st.error(str(exc))
        return

    _render_step_results(analysis)


def _render_dxf_uploader() -> None:
    """Render the independent DXF upload workflow."""
    st.write(
        "Upload a small DXF drawing to inspect layers, model-space geometry, drawing "
        "extents, dimensions, and text annotations."
    )
    uploaded_file = st.file_uploader(
        "DXF drawing",
        type=["dxf"],
        accept_multiple_files=False,
        help="Prototype limit: 25 MB. Use a model-space engineering drawing.",
        key="dxf_upload",
    )

    if uploaded_file is None:
        st.info("Select a DXF file to begin 2D analysis.")
        return

    try:
        with st.spinner("Reading DXF entities with ezdxf..."):
            analysis = analyze_dxf_bytes(uploaded_file.getvalue(), uploaded_file.name)
            requirements = interpret_dxf_analysis(analysis)
    except DxfReaderError as exc:
        st.error(str(exc))
        return

    _render_dxf_results(analysis, requirements)


def _render_matching_uploader() -> None:
    """Render the paired DXF/STEP profile and dimension workflow."""
    st.write(
        _bilingual(
            "Upload one DXF drawing and one STEP/STP model. The checker compares "
            "dimensions, outer profiles, internal circular profiles, feature counts, "
            "and projected shape.",
            "DXF図面1ファイルとSTEP/STPモデル1ファイルをアップロードしてください。"
            "寸法、外形、内部円形状、フィーチャー数、および投影形状を比較します。",
        )
    )
    st.markdown("#### " + _bilingual("1. Select the two CAD files", "1. 2つのCADファイルを選択"))
    upload_columns = st.columns(2)
    with upload_columns[0]:
        dxf_file = st.file_uploader(
            _bilingual("2D DXF drawing", "2D DXF図面"),
            type=["dxf"],
            accept_multiple_files=False,
            key="matching_dxf_upload",
            help=_bilingual("Prototype limit: 25 MB.", "試作版の上限：25 MB。"),
        )
    with upload_columns[1]:
        step_file = st.file_uploader(
            _bilingual("3D STEP/STP model", "3D STEP/STPモデル"),
            type=["step", "stp"],
            accept_multiple_files=False,
            key="matching_step_upload",
            help=_bilingual("Prototype limit: 25 MB.", "試作版の上限：25 MB。"),
        )

    st.markdown("#### " + _bilingual("2. Set comparison options", "2. 比較条件を設定"))
    option_columns = st.columns(2)
    view_options = {
        _bilingual("Auto", "自動"): "auto",
        _bilingual("Top", "上面"): "top",
        _bilingual("Front", "正面"): "front",
        _bilingual("Right", "右側面"): "right",
    }
    with option_columns[0]:
        selected_view_label = st.selectbox(
            _bilingual("STEP projection", "STEP投影方向"),
            options=list(view_options),
            index=0,
            help=_bilingual(
                "Auto selects the projection that best matches the DXF profile.",
                "自動ではDXF外形に最も一致する投影を選択します。",
            ),
        )
    with option_columns[1]:
        tolerance_application_label = st.radio(
            _bilingual("General tolerance", "普通公差"),
            options=[
                _bilingual("Applied", "適用あり"),
                _bilingual("Not applied", "適用なし"),
            ],
            horizontal=True,
            help=_bilingual(
                "The numerical rule set is controlled in the background. Explicit drawing "
                "tolerances always take priority.",
                "数値ルールセットはバックグラウンドで管理されます。図面の明示公差を常に優先します。",
            ),
        )
    general_tolerance_applied = tolerance_application_label == _bilingual(
        "Applied", "適用あり"
    )
    general_tolerances = PROVISIONAL_GENERAL_TOLERANCES.with_application(
        general_tolerance_applied
    )
    profile_tolerance_mm = (
        general_tolerances.profile_mm if general_tolerances.applied else None
    )
    st.caption(
        _bilingual(
            "General-tolerance values are maintained in the background rule set and are not operator inputs.",
            "普通公差値はバックグラウンドのルールセットで管理され、作業者入力ではありません。",
        )
    )

    ready = dxf_file is not None and step_file is not None
    run_check = st.button(
        _bilingual("Run CAD Check", "CAD照合を実行"),
        type="primary",
        disabled=not ready,
        use_container_width=True,
    )

    if not ready:
        st.info(_bilingual("Select both files, then press Run CAD Check.", "両方のファイルを選択し、CAD照合を実行してください。"))
        return

    current_signature = (
        dxf_file.name,
        len(dxf_file.getvalue()),
        step_file.name,
        len(step_file.getvalue()),
        general_tolerances.applied,
        view_options[selected_view_label],
    )

    if not run_check:
        stored = st.session_state.get("cad_check_result")
        if stored is None or stored["signature"] != current_signature:
            st.info(_bilingual("Files are ready. Press Run CAD Check to calculate the result.", "ファイルの準備ができました。CAD照合を実行してください。"))
            return
        dxf_analysis = stored["dxf_analysis"]
        requirements = stored["requirements"]
        step_analysis = stored["step_analysis"]
        matching_result = stored["matching_result"]
        judgement = stored["judgement"]
        profile_result = stored["profile_result"]
    else:
        try:
            with st.spinner(_bilingual("Reading both CAD files and calculating the comparison...", "両方のCADファイルを読み込み、比較を計算しています…")):
                dxf_analysis = analyze_dxf_bytes(dxf_file.getvalue(), dxf_file.name)
                requirements = interpret_dxf_analysis(dxf_analysis)
                step_analysis = analyze_step_bytes(step_file.getvalue(), step_file.name)
                matching_result = match_features(
                    requirements,
                    step_analysis,
                    general_tolerances=general_tolerances,
                )
                judgement = evaluate_matching_result(matching_result)
                profile_result = compare_uploaded_profiles(
                    dxf_file.getvalue(),
                    dxf_file.name,
                    step_file.getvalue(),
                    step_file.name,
                    tolerance_mm=profile_tolerance_mm,
                    requested_view=view_options[selected_view_label],
                )
        except (DxfReaderError, StepReaderError, ProfileComparisonError, ValueError) as exc:
            st.error(str(exc))
            return

        st.session_state["cad_check_result"] = {
            "signature": current_signature,
            "dxf_analysis": dxf_analysis,
            "requirements": requirements,
            "step_analysis": step_analysis,
            "matching_result": matching_result,
            "judgement": judgement,
            "profile_result": profile_result,
        }
        st.session_state.pop("cad_ai_explanation", None)

    st.divider()
    st.markdown("#### " + _bilingual("3. Judgement", "3. 判定"))
    overall_judgement = NG if NG in {judgement.decision, profile_result.judgement} else OK
    if overall_judgement == OK:
        st.success(_bilingual("Overall judgement: OK", "総合判定：OK"))
        st.write(_bilingual("The available dimension and projected-profile comparisons agree.", "確認可能な寸法および投影輪郭の比較は一致しています。"))
    else:
        st.error(_bilingual("Overall judgement: NG", "総合判定：NG（不合格）"))
        st.write(_bilingual("One or more dimension or projected-profile comparisons do not agree.", "寸法または投影輪郭の比較に1件以上の不一致があります。"))

    file_columns = st.columns(4)
    file_columns[0].metric(_bilingual("2D drawing", "2D図面"), judgement.drawing_source)
    file_columns[1].metric(_bilingual("3D model", "3Dモデル"), judgement.model_source)
    file_columns[2].metric(_bilingual("STEP view", "STEP投影"), profile_result.selected_view.title())
    file_columns[3].metric(
        _bilingual("General tolerance", "普通公差"),
        _bilingual("Applied", "適用あり")
        if general_tolerances.applied
        else _bilingual("Not applied", "適用なし"),
    )

    st.markdown("#### " + _bilingual("4. Dimension and profile summary", "4. 寸法・輪郭サマリー"))
    summary_rows = build_summary_rows(matching_result, judgement, profile_result)
    summary_rows = tuple(
        sorted(
            summary_rows,
            key=lambda row: (row.category != "Dimension", row.judgement != NG, row.check),
        )
    )
    st.dataframe(
        [
            {
                _bilingual("Judgement", "判定"): row.judgement,
                _bilingual("Category", "区分"): row.category,
                _bilingual("Check", "確認項目"): row.check,
                _bilingual("2D drawing", "2D図面"): row.drawing_value,
                _bilingual("3D model", "3Dモデル"): row.model_value,
                _bilingual("Difference", "差異"): row.difference,
                _bilingual("Applicable limit", "適用限界"): row.tolerance,
            }
            for row in summary_rows
        ],
        hide_index=True,
        use_container_width=True,
    )

    st.markdown("#### " + _bilingual("5. Visual comparison", "5. 形状の可視比較"))
    overlay = None
    try:
        overlay = build_overlay_visualization(
            profile_result,
            tolerance_mm=profile_tolerance_mm,
        )
    except OverlayError as exc:
        st.warning(_bilingual(f"Vector overlay is unavailable: {exc}", f"ベクター重ね合わせを表示できません：{exc}"))
    else:
        if general_tolerances.applied:
            overlay_columns = st.columns(3)
            overlay_columns[0].metric(_bilingual("DXF mismatched geometry", "DXF不一致形状"), overlay.dxf_mismatch_count)
            overlay_columns[1].metric(_bilingual("STEP mismatched geometry", "STEP不一致形状"), overlay.step_mismatch_count)
            overlay_columns[2].metric(
                _bilingual("Alignment rotation", "位置合わせ回転"),
                f"{overlay.alignment_quarter_turns * 90}°",
            )
            st.caption(_bilingual(
                "Blue: DXF geometry · Green: STEP projection · Red dashed: geometry outside "
                "the applicable background profile rule. Profiles may be rotated in 90° steps.",
                "青：DXF形状・緑：STEP投影・赤破線：バックグラウンド輪郭ルール外。"
                "輪郭は90°単位で回転して比較します。",
            ))
        else:
            st.metric(
                _bilingual("Alignment rotation", "位置合わせ回転"),
                f"{overlay.alignment_quarter_turns * 90}°",
            )
            st.warning(
                _bilingual(
                    "General tolerance is not applied. The overlay is shown without red mismatch classification.",
                    "普通公差は適用されていません。重ね合わせは赤色の不一致判定なしで表示されます。",
                )
            )
        overlay_tab, dxf_geometry_tab, step_geometry_tab = st.tabs(
            [
                _bilingual("Combined overlay", "重ね合わせ"),
                _bilingual("DXF geometry", "DXF形状"),
                _bilingual("STEP projection", "STEP投影"),
            ]
        )
        with overlay_tab:
            st.html(overlay.combined_svg)
        with dxf_geometry_tab:
            st.html(overlay.dxf_svg)
        with step_geometry_tab:
            st.html(overlay.step_svg)

    base_report = build_final_report(
        matching_result,
        judgement,
        profile_result,
        overlay,
    )
    local_explanation = build_deterministic_explanation(base_report, requirements.notes)
    stored_explanation = st.session_state.get("cad_ai_explanation")
    if (
        isinstance(stored_explanation, dict)
        and stored_explanation.get("signature") == current_signature
        and isinstance(stored_explanation.get("explanation"), AIExplanation)
    ):
        active_explanation = stored_explanation["explanation"]
    else:
        active_explanation = local_explanation

    st.markdown("#### " + _bilingual("6. Assisted explanation", "6. 説明支援"))
    st.caption(
        _bilingual(
            "The OK/NG result above is already final for this check. Assistance can only explain it.",
            "上記のOK/NG結果はこの照合の確定判定です。説明支援は判定を変更できません。",
        )
    )
    if openai_is_configured():
        st.caption(
            _bilingual(
                "Optional OpenAI assistance sends normalized comparison evidence and drawing text only; raw CAD files are not sent.",
                "任意のOpenAI説明支援では正規化された比較証拠と図面テキストのみを送信し、生のCADファイルは送信しません。",
            )
        )
        if st.button(
            _bilingual("Generate enhanced explanation", "詳細説明を生成"),
            use_container_width=True,
        ):
            try:
                with st.spinner(_bilingual("Generating guarded explanation...", "保護された説明を生成しています…")):
                    active_explanation = generate_openai_explanation(
                        base_report,
                        requirements.notes,
                    )
            except (AIConfigurationError, AIResponseError, RuntimeError) as exc:
                st.error(_bilingual(f"Enhanced explanation failed: {exc}", f"詳細説明の生成に失敗しました：{exc}"))
                active_explanation = local_explanation
            else:
                st.session_state["cad_ai_explanation"] = {
                    "signature": current_signature,
                    "explanation": active_explanation,
                }
    else:
        st.info(
            _bilingual(
                "OpenAI is not configured on the server. The safe local explanation is shown below.",
                "サーバーにOpenAIが設定されていないため、安全なローカル説明を表示します。",
            )
        )
    _render_assisted_explanation(active_explanation)

    st.markdown("#### " + _bilingual("7. Final report", "7. 最終レポート"))
    final_report = build_final_report(
        matching_result,
        judgement,
        profile_result,
        overlay,
        ai_assistance=active_explanation.to_dict(),
    )
    report_columns = st.columns(3)
    report_columns[0].metric(
        _bilingual("Final judgement", "最終判定"),
        final_report.judgement_label,
    )
    report_columns[1].metric(
        _bilingual("Dimension checks", "寸法確認数"),
        len(final_report.dimension_summary),
    )
    report_columns[2].metric(
        _bilingual("Profile checks", "輪郭確認数"),
        len(final_report.profile_summary),
    )
    st.caption(
        _bilingual(
            "Report order: judgement, files, tolerance application, summaries, NG findings, assisted explanation, detailed evidence, warnings, and limitations.",
            "レポート順序：判定、ファイル、普通公差適用、サマリー、NG項目、説明支援、詳細証拠、警告、制限事項。",
        )
    )
    report_basename = f"{Path(dxf_file.name).stem}_cad_comparison_report"
    download_columns = st.columns(2)
    download_columns[0].download_button(
        _bilingual("Download JSON report", "JSONレポートをダウンロード"),
        data=final_report.to_json_bytes(),
        file_name=f"{report_basename}.json",
        mime="application/json",
        use_container_width=True,
    )
    download_columns[1].download_button(
        _bilingual("Download PDF report", "PDFレポートをダウンロード"),
        data=final_report.to_pdf_bytes(),
        file_name=f"{report_basename}.pdf",
        mime="application/pdf",
        use_container_width=True,
    )

    dashboard_rows = build_dashboard_rows(matching_result, judgement)
    with st.expander("Detailed comparison evidence"):
        st.markdown("##### Dimension evidence")
        st.dataframe(
            [
                {
                    "#": row.check_number,
                    "Judgement": row.outcome,
                    "Check": row.requirement,
                    "Drawing (mm)": row.drawing_value_mm,
                    "Allowed min (mm)": row.allowed_minimum_mm,
                    "Allowed max (mm)": row.allowed_maximum_mm,
                    "3D feature": row.model_feature,
                    "3D value (mm)": row.model_value_mm,
                    "Difference (mm)": row.difference_mm,
                    "Outside limit (mm)": row.outside_limit_by_mm,
                    "Confidence": row.confidence,
                    "DXF entity": row.source_entity,
                    "Details": row.reason,
                }
                for row in dashboard_rows
            ],
            hide_index=True,
            use_container_width=True,
        )
        st.markdown("##### Profile evidence")
        st.dataframe(
            [
                {
                    "Judgement": check.judgement,
                    "Feature": check.feature,
                    "2D drawing": check.drawing_value,
                    "3D model": check.model_value,
                    "Difference": check.difference,
                    "Tolerance": check.tolerance,
                    "Details": check.details,
                }
                for check in profile_result.checks
            ],
            hide_index=True,
            use_container_width=True,
        )

    with st.expander("Supporting CAD analysis"):
        st.markdown("##### STEP model summary")
        _render_step_results(step_analysis)
        st.markdown("##### DXF drawing summary")
        _render_dxf_results(dxf_analysis, requirements)
        st.markdown("##### Raw feature-matching evidence")
        _render_feature_matches(matching_result)
        st.markdown("##### Raw profile-comparison evidence")
        st.json(profile_result.to_dict())


def render_app() -> None:
    """Render independent STEP/STP and DXF analysis interfaces."""
    status = get_app_status()
    st.set_page_config(page_title=status["application"], page_icon="📐", layout="wide")

    st.title(status["application"])
    st.caption(status["stage"])
    st.write(_bilingual(
        "Uploaded CAD files are processed temporarily and are not committed to GitHub. "
        "Milestone 11 compares dimensions and projected profile geometry with deterministic "
        "OK/NG rules, shows vector evidence, creates ordered JSON/PDF reports, and explains "
        "the completed judgement without changing it. Explicit "
        "drawing tolerances take priority. The operator selects whether background "
        "general-tolerance rules apply.",
        "アップロードしたCADファイルは一時処理され、GitHubには保存されません。"
        "マイルストーン11では寸法と投影輪郭を決定論的なOK/NG規則で比較し、"
        "ベクター証拠と順序化されたJSON/PDFレポートを作成し、確定判定を変更せずに説明します。"
        "図面の明示公差を優先し、"
        "バックグラウンド普通公差ルールを適用するか作業者が選択します。",
    ))

    step_tab, dxf_tab, matching_tab = st.tabs(
        [
            _bilingual("Run CAD Check", "CAD照合"),
            _bilingual("Inspect 3D STEP/STP", "3D STEP/STP確認"),
            _bilingual("Inspect 2D DXF", "2D DXF確認"),
        ]
    )
    with step_tab:
        _render_matching_uploader()
    with dxf_tab:
        _render_step_uploader()
    with matching_tab:
        _render_dxf_uploader()


if __name__ == "__main__":
    render_app()

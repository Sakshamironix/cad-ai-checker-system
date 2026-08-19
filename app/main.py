"""Milestone 7 Streamlit entry point for the CAD AI Checker."""

from __future__ import annotations

from typing import Final

import streamlit as st

from app.comparison_rules import (
    FAIL,
    PASS,
    EngineeringJudgement,
    evaluate_matching_result,
)
from app.dashboard import build_dashboard_rows
from app.drawing_interpreter import DrawingRequirements, interpret_dxf_analysis
from app.dxf_reader import DxfAnalysis, DxfReaderError, analyze_dxf_bytes
from app.feature_matcher import FeatureMatchingResult, match_features
from app.step_reader import StepAnalysis, StepReaderError, analyze_step_bytes

APP_NAME: Final = "CAD AI Checker"
APP_STAGE: Final = "Milestone 7 — Trial-ready PASS/FAIL dashboard"


def get_app_status() -> dict[str, str]:
    """Return the visible application state used by the UI and setup test."""
    return {
        "application": APP_NAME,
        "stage": APP_STAGE,
        "capability": "Operator-ready tolerance comparison dashboard",
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
    """Render the final rule-based prototype engineering judgement."""
    if judgement.decision == PASS:
        st.success(f"Prototype judgement: {judgement.decision}")
    elif judgement.decision == FAIL:
        st.error(f"Prototype judgement: {judgement.decision}")
    else:
        st.warning(f"Prototype judgement: {judgement.decision}")
    st.write(judgement.decision_reason)

    summary_columns = st.columns(4)
    summary_columns[0].metric("Passed rules", judgement.pass_count)
    summary_columns[1].metric("Failed rules", judgement.fail_count)
    summary_columns[2].metric("Review items", judgement.review_count)
    summary_columns[3].metric(
        "Decisive pass rate",
        (
            f"{judgement.pass_rate_percent:.1f}%"
            if judgement.pass_rate_percent is not None
            else "N/A"
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
    """Render the paired DXF/STEP upload and trial dashboard workflow."""
    st.write(
        "Upload one interpreted DXF drawing and one STEP/STP model. The prototype matches "
        "overall size, linear dimensions, diameter/radius requirements, and circle-based "
        "hole candidates."
    )
    st.markdown("#### 1. Select the two CAD files")
    upload_columns = st.columns(2)
    with upload_columns[0]:
        dxf_file = st.file_uploader(
            "2D DXF drawing",
            type=["dxf"],
            accept_multiple_files=False,
            key="matching_dxf_upload",
            help="Prototype limit: 25 MB.",
        )
    with upload_columns[1]:
        step_file = st.file_uploader(
            "3D STEP/STP model",
            type=["step", "stp"],
            accept_multiple_files=False,
            key="matching_step_upload",
            help="Prototype limit: 25 MB.",
        )

    st.markdown("#### 2. Set the fallback tolerance")
    default_tolerance_mm = st.number_input(
        "Default tolerance for requirements without a drawing tolerance (mm)",
        min_value=0.001,
        max_value=10.0,
        value=0.1,
        step=0.01,
        format="%.3f",
        help=(
            "An explicit DXF tolerance takes priority. This value is used only when the "
            "drawing provides no usable tolerance."
        ),
    )

    ready = dxf_file is not None and step_file is not None
    run_check = st.button(
        "Run CAD Check",
        type="primary",
        disabled=not ready,
        use_container_width=True,
    )

    if not ready:
        st.info("Select both files, then press Run CAD Check.")
        return

    current_signature = (
        dxf_file.name,
        len(dxf_file.getvalue()),
        step_file.name,
        len(step_file.getvalue()),
        float(default_tolerance_mm),
    )

    if not run_check:
        stored = st.session_state.get("cad_check_result")
        if stored is None or stored["signature"] != current_signature:
            st.info("Files are ready. Press Run CAD Check to calculate the result.")
            return
        dxf_analysis = stored["dxf_analysis"]
        requirements = stored["requirements"]
        step_analysis = stored["step_analysis"]
        matching_result = stored["matching_result"]
        judgement = stored["judgement"]
    else:
        try:
            with st.spinner("Reading both CAD files and calculating the comparison..."):
                dxf_analysis = analyze_dxf_bytes(dxf_file.getvalue(), dxf_file.name)
                requirements = interpret_dxf_analysis(dxf_analysis)
                step_analysis = analyze_step_bytes(step_file.getvalue(), step_file.name)
                matching_result = match_features(
                    requirements,
                    step_analysis,
                    default_tolerance_mm=float(default_tolerance_mm),
                )
                judgement = evaluate_matching_result(matching_result)
        except (DxfReaderError, StepReaderError, ValueError) as exc:
            st.error(str(exc))
            return

        st.session_state["cad_check_result"] = {
            "signature": current_signature,
            "dxf_analysis": dxf_analysis,
            "requirements": requirements,
            "step_analysis": step_analysis,
            "matching_result": matching_result,
            "judgement": judgement,
        }

    st.divider()
    st.markdown("#### 3. Review the result")
    file_columns = st.columns(3)
    file_columns[0].metric("2D drawing", judgement.drawing_source)
    file_columns[1].metric("3D model", judgement.model_source)
    file_columns[2].metric("Fallback tolerance", f"±{default_tolerance_mm:.3f} mm")
    _render_engineering_judgement(judgement)

    dashboard_rows = build_dashboard_rows(matching_result, judgement)
    selected_outcomes = st.multiselect(
        "Show outcomes",
        options=[FAIL, "REVIEW", PASS],
        default=[FAIL, "REVIEW", PASS],
    )
    visible_rows = [row for row in dashboard_rows if row.outcome in selected_outcomes]
    st.dataframe(
        [
            {
                "#": row.check_number,
                "Result": row.outcome,
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
                "Reason": row.reason,
            }
            for row in visible_rows
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


def render_app() -> None:
    """Render independent STEP/STP and DXF analysis interfaces."""
    status = get_app_status()
    st.set_page_config(page_title=status["application"], page_icon="📐", layout="wide")

    st.title(status["application"])
    st.caption(status["stage"])
    st.write(
        "Uploaded CAD files are processed temporarily and are not committed to GitHub. "
        "Milestone 7 provides a trial-ready dashboard using deterministic geometry and "
        "tolerance rules."
    )

    step_tab, dxf_tab, matching_tab = st.tabs(
        ["Run CAD Check", "Inspect 3D STEP/STP", "Inspect 2D DXF"]
    )
    with step_tab:
        _render_matching_uploader()
    with dxf_tab:
        _render_step_uploader()
    with matching_tab:
        _render_dxf_uploader()


if __name__ == "__main__":
    render_app()

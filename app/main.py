"""Milestone 2 Streamlit entry point for the CAD AI Checker."""

from __future__ import annotations

from typing import Final

import streamlit as st

from app.step_reader import StepAnalysis, StepReaderError, analyze_step_bytes

APP_NAME: Final = "CAD AI Checker"
APP_STAGE: Final = "Milestone 2 — STEP/STP reader"


def get_app_status() -> dict[str, str]:
    """Return the visible application state used by the UI and setup test."""
    return {
        "application": APP_NAME,
        "stage": APP_STAGE,
        "capability": "STEP/STP topology and geometry analysis",
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


def render_app() -> None:
    """Render the STEP/STP upload and analysis interface."""
    status = get_app_status()
    st.set_page_config(page_title=status["application"], page_icon="📐", layout="wide")

    st.title(status["application"])
    st.caption(status["stage"])
    st.write(
        "Upload a small STEP or STP model to inspect its topology, dimensions, physical "
        "properties, and basic geometry. Uploaded files are processed temporarily and are "
        "not committed to GitHub."
    )

    uploaded_file = st.file_uploader(
        "STEP/STP model",
        type=["step", "stp"],
        accept_multiple_files=False,
        help="Prototype limit: 25 MB. Start with a small single part.",
    )

    if uploaded_file is None:
        st.info("Select a STEP or STP file to begin analysis.")
        return

    try:
        with st.spinner("Reading STEP geometry with OpenCASCADE..."):
            analysis = analyze_step_bytes(uploaded_file.getvalue(), uploaded_file.name)
    except StepReaderError as exc:
        st.error(str(exc))
        return

    _render_step_results(analysis)


if __name__ == "__main__":
    render_app()

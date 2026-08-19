"""Milestone 1 Streamlit entry point for the CAD AI Checker."""

from __future__ import annotations

from typing import Final

import streamlit as st

APP_NAME: Final = "CAD AI Checker"
APP_STAGE: Final = "Milestone 1 — Project foundation"


def get_app_status() -> dict[str, str]:
    """Return the visible application state used by the UI and setup test."""
    return {
        "application": APP_NAME,
        "stage": APP_STAGE,
        "next_capability": "STEP/STP model reading",
    }


def render_app() -> None:
    """Render the intentionally minimal, working Milestone 1 interface."""
    status = get_app_status()
    st.set_page_config(page_title=status["application"], page_icon="📐", layout="wide")

    st.title(status["application"])
    st.caption(status["stage"])
    st.success("The Codespaces development environment and Streamlit application are ready.")

    st.subheader("Current scope")
    st.write(
        "This milestone establishes the secure repository, reproducible CAD environment, "
        "test runner, and continuous-integration workflow. File upload and CAD parsing begin "
        "in the next milestone."
    )

    st.subheader("Next milestone")
    st.info(f"Next capability: {status['next_capability']}.")


if __name__ == "__main__":
    render_app()

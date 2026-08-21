"""Tests for deterministic DXF/STEP vector overlays."""

from __future__ import annotations

import math

import pytest

from app.overlay import OverlayError, build_overlay_visualization
from app.profile_comparison import OK, ProfileComparisonResult, ProfilePrimitive
from app.projection import Point2D, ProjectedPrimitive, StepProjection


def _circle(radius: float, kind: str = "profile") -> tuple[Point2D, ...]:
    del kind
    return tuple(
        Point2D(
            radius * math.cos(index * 2.0 * math.pi / 96),
            radius * math.sin(index * 2.0 * math.pi / 96),
        )
        for index in range(96)
    )


def _result(dxf_radius: float, step_radius: float) -> ProfileComparisonResult:
    dxf = ProfilePrimitive("circle", _circle(dxf_radius), Point2D(0.0, 0.0), dxf_radius)
    step = ProjectedPrimitive(
        "circle", _circle(step_radius), Point2D(0.0, 0.0), step_radius
    )
    projection = StepProjection(
        view="top",
        width=step_radius * 2.0,
        height=step_radius * 2.0,
        primitives=(step,),
    )
    return ProfileComparisonResult(
        drawing_source="ring.dxf",
        model_source="ring.step",
        selected_view="top",
        judgement=OK,
        reason="Synthetic overlay test.",
        checks=(),
        dxf_primitives=(dxf,),
        step_projection=projection,
    )


def test_matching_profiles_create_clean_overlay() -> None:
    overlay = build_overlay_visualization(_result(25.0, 25.0), tolerance_mm=0.1)

    assert overlay.dxf_mismatch_count == 0
    assert overlay.step_mismatch_count == 0
    assert 'data-layer="dxf"' in overlay.combined_svg
    assert 'data-layer="step"' in overlay.combined_svg
    assert 'data-mismatch="true"' not in overlay.combined_svg
    assert "viewBox=" in overlay.combined_svg


def test_different_profiles_are_highlighted_as_mismatches() -> None:
    overlay = build_overlay_visualization(_result(25.0, 27.0), tolerance_mm=0.1)

    assert overlay.dxf_mismatch_count == 1
    assert overlay.step_mismatch_count == 1
    assert overlay.combined_svg.count('data-mismatch="true"') == 2
    assert "#dc2626" in overlay.combined_svg


def test_overlay_rejects_non_positive_tolerance() -> None:
    with pytest.raises(OverlayError, match="greater than zero"):
        build_overlay_visualization(_result(25.0, 25.0), tolerance_mm=0.0)


def test_overlay_without_applied_tolerance_has_no_mismatch_classification() -> None:
    overlay = build_overlay_visualization(_result(25.0, 27.0), tolerance_mm=None)

    assert overlay.dxf_mismatch_count == 0
    assert overlay.step_mismatch_count == 0
    assert 'data-mismatch="true"' not in overlay.combined_svg

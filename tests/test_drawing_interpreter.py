"""Tests for DXF engineering requirement interpretation."""

from __future__ import annotations

import pytest

from app.drawing_interpreter import _normalize_text, interpret_dxf_analysis, parse_dimension_text
from app.dxf_reader import (
    CircleFeature,
    DimensionFeature,
    DrawingExtents,
    DxfAnalysis,
    EntityCounts,
    Point2D,
    TextFeature,
)


def _empty_counts(total: int) -> EntityCounts:
    return EntityCounts(
        total=total,
        lines=0,
        circles=0,
        arcs=0,
        lightweight_polylines=0,
        polylines=0,
        text=0,
        multiline_text=0,
        dimensions=0,
        other=0,
    )


def test_parse_symmetric_dimension_tolerance() -> None:
    result = parse_dimension_text("4X %%c10 +/-0.05", measured_value=10.0)

    assert result.nominal_value == pytest.approx(10.0)
    assert result.tolerance is not None
    assert result.tolerance.lower_deviation == pytest.approx(-0.05)
    assert result.tolerance.upper_deviation == pytest.approx(0.05)


def test_parse_asymmetric_dimension_tolerance() -> None:
    result = parse_dimension_text("25 +0.20/-0.10", measured_value=25.0)

    assert result.nominal_value == pytest.approx(25.0)
    assert result.tolerance is not None
    assert result.tolerance.lower_deviation == pytest.approx(-0.10)
    assert result.tolerance.upper_deviation == pytest.approx(0.20)


def test_parse_placeholder_uses_measured_value() -> None:
    result = parse_dimension_text("<> ±0.10", measured_value=42.5)

    assert result.nominal_value == pytest.approx(42.5)
    assert result.tolerance is not None
    assert result.tolerance.lower_deviation == pytest.approx(-0.10)
    assert result.tolerance.upper_deviation == pytest.approx(0.10)


def test_normalize_autocad_unicode_diameter_symbol() -> None:
    assert "⌀" in _normalize_text(r"\\A1;\\U+2205<>")


def test_parse_limit_dimension() -> None:
    result = parse_dimension_text("19.95 / 20.05", measured_value=20.0)

    assert result.nominal_value == pytest.approx(20.0)
    assert result.tolerance is not None
    assert result.tolerance.lower_deviation == pytest.approx(-0.05)
    assert result.tolerance.upper_deviation == pytest.approx(0.05)


def test_interpret_dimensions_general_tolerance_and_holes() -> None:
    analysis = DxfAnalysis(
        source_name="plate.dxf",
        dxf_version="AC1024",
        units_code=4,
        units_name="Millimetres",
        layers=("0", "DIMENSIONS", "HOLES", "NOTES"),
        entity_counts=_empty_counts(total=5),
        extents=DrawingExtents(
            minimum=Point2D(0.0, 0.0),
            maximum=Point2D(100.0, 50.0),
            width=100.0,
            height=50.0,
        ),
        circles=(
            CircleFeature(
                entity_index=1,
                layer="HOLES",
                center=Point2D(20.0, 25.0),
                radius=3.0,
                diameter=6.0,
            ),
        ),
        arcs=(),
        dimensions=(
            DimensionFeature(
                entity_index=2,
                layer="DIMENSIONS",
                dimension_type="Linear",
                measurement=100.0,
                text_override=None,
                style="ISO-25",
            ),
            DimensionFeature(
                entity_index=3,
                layer="DIMENSIONS",
                dimension_type="Diameter",
                measurement=6.0,
                text_override="Ø6 +0.10/-0.05",
                style="ISO-25",
            ),
        ),
        texts=(
            TextFeature(
                entity_index=4,
                entity_type="MTEXT",
                layer="NOTES",
                content="GENERAL TOLERANCE ±0.20",
            ),
            TextFeature(
                entity_index=5,
                entity_type="TEXT",
                layer="NOTES",
                content="DEBURR ALL EDGES",
            ),
        ),
        entity_types={"CIRCLE": 1, "DIMENSION": 2, "MTEXT": 1, "TEXT": 1},
    )

    result = interpret_dxf_analysis(analysis)

    assert result.drawing_size is not None
    assert result.drawing_size.width == pytest.approx(100.0)
    assert result.general_tolerance is not None
    assert result.general_tolerance.upper_deviation == pytest.approx(0.20)
    assert result.resolved_dimension_count == 2
    assert result.tolerance_count == 2
    assert result.dimensions[0].tolerance_source == "general note"
    assert result.dimensions[0].minimum_value == pytest.approx(99.8)
    assert result.dimensions[0].maximum_value == pytest.approx(100.2)
    assert result.dimensions[1].classification == "diameter"
    assert result.dimensions[1].tolerance_source == "dimension"
    assert result.dimensions[1].minimum_value == pytest.approx(5.95)
    assert result.dimensions[1].maximum_value == pytest.approx(6.10)
    assert len(result.hole_candidates) == 1
    assert result.hole_candidates[0].diameter == pytest.approx(6.0)
    assert "DEBURR ALL EDGES" in result.notes
    assert result.warnings == ()


def test_unitless_empty_analysis_returns_clear_warnings() -> None:
    analysis = DxfAnalysis(
        source_name="empty.dxf",
        dxf_version="AC1024",
        units_code=0,
        units_name="Unitless",
        layers=("0",),
        entity_counts=_empty_counts(total=0),
        extents=None,
        circles=(),
        arcs=(),
        dimensions=(),
        texts=(),
        entity_types={},
    )

    result = interpret_dxf_analysis(analysis)

    assert any("unitless" in warning for warning in result.warnings)
    assert any("No DXF DIMENSION" in warning for warning in result.warnings)
    assert any("No circle" in warning for warning in result.warnings)

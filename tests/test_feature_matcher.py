"""Tests for basic 2D-to-3D feature matching."""

from __future__ import annotations

import pytest

from app.drawing_interpreter import (
    DimensionRequirement,
    DrawingRequirements,
    DrawingSizeRequirement,
    HoleCandidateRequirement,
    Tolerance,
)
from app.dxf_reader import Point2D
from app.feature_matcher import (
    MATCHED,
    OUT_OF_TOLERANCE,
    UNMATCHED_3D,
    match_features,
)
from app.step_reader import HoleFeature, StepAnalysis, TopologyCounts, Vector3D


def _step_analysis() -> StepAnalysis:
    return StepAnalysis(
        source_name="plate.step",
        topology=TopologyCounts(solids=1, shells=1, faces=10, edges=24, vertices=16),
        bounding_box=Vector3D(x=100.0, y=50.0, z=10.0),
        volume=48000.0,
        surface_area=13000.0,
        center_of_mass=Vector3D(x=0.0, y=0.0, z=0.0),
        planar_faces=6,
        cylindrical_faces=2,
        circular_edges=4,
        outer_boundaries=8,
        outer_boundary_length=500.0,
        holes=(
            HoleFeature(face_index=7, radius=3.025, diameter=6.05),
            HoleFeature(face_index=8, radius=2.0, diameter=4.0),
        ),
    )


def _dimension(
    entity_index: int,
    classification: str,
    nominal: float,
    tolerance: Tolerance,
) -> DimensionRequirement:
    return DimensionRequirement(
        entity_index=entity_index,
        dimension_type=classification.title(),
        classification=classification,
        nominal_value=nominal,
        tolerance=tolerance,
        tolerance_source="dimension",
        minimum_value=nominal + tolerance.lower_deviation,
        maximum_value=nominal + tolerance.upper_deviation,
        unit="Millimetres",
        layer="DIMENSIONS",
        source_text=None,
    )


def test_match_basic_sizes_dimensions_and_hole_candidates() -> None:
    requirements = DrawingRequirements(
        source_name="plate.dxf",
        units_name="Millimetres",
        drawing_size=DrawingSizeRequirement(width=100.0, height=50.0, unit="Millimetres"),
        general_tolerance=None,
        dimensions=(
            _dimension(1, "linear", 10.0, Tolerance(-0.1, 0.1)),
            _dimension(2, "diameter", 6.0, Tolerance(-0.1, 0.1)),
        ),
        hole_candidates=(
            HoleCandidateRequirement(
                entity_index=3,
                layer="HOLES",
                center=Point2D(25.0, 25.0),
                diameter=6.0,
                radius=3.0,
                unit="Millimetres",
            ),
        ),
        notes=(),
        warnings=(),
    )

    result = match_features(requirements, _step_analysis())

    assert result.unit_conversion_factor_to_mm == pytest.approx(1.0)
    assert result.matched_count == 5
    assert any(
        match.requirement == "Linear dimension"
        and match.model_feature == "Bounding box Z"
        and match.status == MATCHED
        for match in result.matches
    )
    assert any(
        match.requirement == "Hole diameter"
        and match.model_value_mm == pytest.approx(6.05)
        and match.status == MATCHED
        for match in result.matches
    )
    assert any(match.status == UNMATCHED_3D for match in result.matches)
    assert result.issue_count == 1


def test_out_of_tolerance_dimension_is_reported() -> None:
    requirements = DrawingRequirements(
        source_name="wrong_hole.dxf",
        units_name="Millimetres",
        drawing_size=None,
        general_tolerance=None,
        dimensions=(
            _dimension(1, "diameter", 8.0, Tolerance(-0.05, 0.05)),
        ),
        hole_candidates=(),
        notes=(),
        warnings=(),
    )

    result = match_features(requirements, _step_analysis())
    dimension_match = next(
        match for match in result.matches if match.requirement == "Hole diameter"
    )

    assert dimension_match.status == OUT_OF_TOLERANCE
    assert dimension_match.drawing_value_mm == pytest.approx(8.0)
    assert dimension_match.model_value_mm == pytest.approx(6.05)
    assert dimension_match.difference_mm == pytest.approx(-1.95)


def test_inch_values_are_converted_to_millimetres() -> None:
    requirements = DrawingRequirements(
        source_name="inch_part.dxf",
        units_name="Inches",
        drawing_size=None,
        general_tolerance=None,
        dimensions=(
            _dimension(1, "linear", 100.0 / 25.4, Tolerance(-0.001, 0.001)),
        ),
        hole_candidates=(),
        notes=(),
        warnings=(),
    )

    result = match_features(requirements, _step_analysis())
    dimension_match = next(
        match for match in result.matches if match.requirement == "Linear dimension"
    )

    assert result.unit_conversion_factor_to_mm == pytest.approx(25.4)
    assert dimension_match.drawing_value_mm == pytest.approx(100.0)
    assert dimension_match.status == MATCHED


def test_unitless_drawing_is_not_compared() -> None:
    requirements = DrawingRequirements(
        source_name="unitless.dxf",
        units_name="Unitless",
        drawing_size=None,
        general_tolerance=None,
        dimensions=(),
        hole_candidates=(),
        notes=(),
        warnings=(),
    )

    result = match_features(requirements, _step_analysis())

    assert result.matches == ()
    assert result.unit_conversion_factor_to_mm is None
    assert any("cannot be converted" in warning for warning in result.warnings)


def test_reject_non_positive_default_tolerance() -> None:
    requirements = DrawingRequirements(
        source_name="plate.dxf",
        units_name="Millimetres",
        drawing_size=None,
        general_tolerance=None,
        dimensions=(),
        hole_candidates=(),
        notes=(),
        warnings=(),
    )

    with pytest.raises(ValueError, match="greater than zero"):
        match_features(requirements, _step_analysis(), default_tolerance_mm=0.0)

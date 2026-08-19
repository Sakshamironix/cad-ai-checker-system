"""Tests for STEP/STP topology and geometry analysis."""

from __future__ import annotations

from pathlib import Path

import cadquery as cq
import pytest

from app.step_reader import StepReaderError, analyze_step_bytes, analyze_step_file


def _export_step(shape: cq.Workplane, path: Path) -> None:
    cq.exporters.export(shape, str(path), exportType="STEP")


def test_analyze_rectangular_box(tmp_path: Path) -> None:
    step_path = tmp_path / "box.step"
    _export_step(cq.Workplane("XY").box(10.0, 20.0, 30.0), step_path)

    result = analyze_step_file(step_path)

    assert result.topology.solids == 1
    assert result.topology.faces == 6
    assert result.topology.edges == 12
    assert result.topology.vertices == 8
    assert result.bounding_box.x == pytest.approx(10.0)
    assert result.bounding_box.y == pytest.approx(20.0)
    assert result.bounding_box.z == pytest.approx(30.0)
    assert result.volume == pytest.approx(6000.0)
    assert result.surface_area == pytest.approx(2200.0)
    assert result.center_of_mass.x == pytest.approx(0.0, abs=1e-9)
    assert result.center_of_mass.y == pytest.approx(0.0, abs=1e-9)
    assert result.center_of_mass.z == pytest.approx(0.0, abs=1e-9)
    assert result.planar_faces == 6
    assert result.cylindrical_faces == 0
    assert result.circular_edges == 0
    assert result.hole_count == 0
    assert result.outer_boundaries == 6


def test_detect_through_hole(tmp_path: Path) -> None:
    step_path = tmp_path / "plate_with_hole.stp"
    plate = cq.Workplane("XY").box(20.0, 20.0, 10.0).faces(">Z").workplane().hole(6.0)
    _export_step(plate, step_path)

    result = analyze_step_file(step_path)

    assert result.topology.solids == 1
    assert result.cylindrical_faces >= 1
    assert result.circular_edges >= 2
    assert result.hole_count == 1
    assert result.holes[0].diameter == pytest.approx(6.0)


def test_analyze_uploaded_bytes(tmp_path: Path) -> None:
    step_path = tmp_path / "uploaded.step"
    _export_step(cq.Workplane("XY").box(2.0, 3.0, 4.0), step_path)

    result = analyze_step_bytes(step_path.read_bytes(), "uploaded.step")

    assert result.source_name == "uploaded.step"
    assert result.volume == pytest.approx(24.0)


def test_reject_unsupported_extension() -> None:
    with pytest.raises(StepReaderError, match="Only .step and .stp"):
        analyze_step_bytes(b"not a step file", "model.txt")


def test_reject_empty_upload() -> None:
    with pytest.raises(StepReaderError, match="empty"):
        analyze_step_bytes(b"", "model.step")

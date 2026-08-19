"""Tests for DXF drawing entity and dimension analysis."""

from __future__ import annotations

from pathlib import Path

import ezdxf
import pytest
from ezdxf import units

from app.dxf_reader import DxfReaderError, analyze_dxf_bytes, analyze_dxf_file


def _create_test_dxf(path: Path) -> None:
    document = ezdxf.new("R2010", setup=True)
    document.units = units.MM
    document.layers.add("GEOMETRY", color=7)
    document.layers.add("ANNOTATION", color=3)
    modelspace = document.modelspace()

    modelspace.add_line((0.0, 0.0), (100.0, 0.0), dxfattribs={"layer": "GEOMETRY"})
    modelspace.add_circle((25.0, 30.0), 5.0, dxfattribs={"layer": "GEOMETRY"})
    modelspace.add_arc(
        (50.0, 50.0),
        10.0,
        start_angle=0.0,
        end_angle=90.0,
        dxfattribs={"layer": "GEOMETRY"},
    )
    modelspace.add_lwpolyline(
        [(0.0, 0.0), (0.0, 20.0), (20.0, 20.0), (20.0, 0.0)],
        close=True,
        dxfattribs={"layer": "GEOMETRY"},
    )
    modelspace.add_text("PLATE", dxfattribs={"layer": "ANNOTATION"})
    modelspace.add_mtext("CHECK HOLES", dxfattribs={"layer": "ANNOTATION"})
    dimension = modelspace.add_linear_dim(
        base=(0.0, -10.0),
        p1=(0.0, 0.0),
        p2=(100.0, 0.0),
        angle=0.0,
        dxfattribs={"layer": "ANNOTATION"},
    )
    dimension.render()
    document.saveas(path)


def test_analyze_dxf_geometry_and_annotations(tmp_path: Path) -> None:
    dxf_path = tmp_path / "drawing.dxf"
    _create_test_dxf(dxf_path)

    result = analyze_dxf_file(dxf_path)

    assert result.source_name == "drawing.dxf"
    assert result.dxf_version == "AC1024"
    assert result.units_code == units.MM
    assert result.units_name == "Millimetres"
    assert "GEOMETRY" in result.layers
    assert "ANNOTATION" in result.layers
    assert result.entity_counts.lines == 1
    assert result.entity_counts.circles == 1
    assert result.entity_counts.arcs == 1
    assert result.entity_counts.lightweight_polylines == 1
    assert result.entity_counts.text == 1
    assert result.entity_counts.multiline_text == 1
    assert result.entity_counts.dimensions == 1
    assert result.circles[0].diameter == pytest.approx(10.0)
    assert result.arcs[0].radius == pytest.approx(10.0)
    assert result.dimensions[0].dimension_type == "Linear"
    assert result.dimensions[0].measurement == pytest.approx(100.0)
    assert {annotation.content for annotation in result.texts} == {"PLATE", "CHECK HOLES"}
    assert result.extents is not None
    assert result.extents.width >= 100.0


def test_analyze_uploaded_dxf_bytes(tmp_path: Path) -> None:
    dxf_path = tmp_path / "uploaded.dxf"
    _create_test_dxf(dxf_path)

    result = analyze_dxf_bytes(dxf_path.read_bytes(), "uploaded.dxf")

    assert result.source_name == "uploaded.dxf"
    assert result.entity_counts.total >= 7


def test_analyze_empty_valid_dxf(tmp_path: Path) -> None:
    dxf_path = tmp_path / "empty.dxf"
    ezdxf.new("R2010").saveas(dxf_path)

    result = analyze_dxf_file(dxf_path)

    assert result.entity_counts.total == 0
    assert result.extents is None
    assert result.circles == ()
    assert result.dimensions == ()


def test_reject_unsupported_extension() -> None:
    with pytest.raises(DxfReaderError, match="Only .dxf"):
        analyze_dxf_bytes(b"not a dxf file", "drawing.pdf")


def test_reject_empty_upload() -> None:
    with pytest.raises(DxfReaderError, match="empty"):
        analyze_dxf_bytes(b"", "drawing.dxf")


def test_reject_malformed_dxf() -> None:
    with pytest.raises(DxfReaderError, match="could not read"):
        analyze_dxf_bytes(b"this is not a DXF", "broken.dxf")

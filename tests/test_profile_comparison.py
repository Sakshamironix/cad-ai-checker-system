"""Tests for ring and closed-profile comparison."""

from __future__ import annotations

from pathlib import Path

import cadquery as cq
import ezdxf
import pytest
from ezdxf import units

from app.profile_comparison import NG, OK, compare_uploaded_profiles


def _write_ring_dxf(path: Path, outer_diameter: float, inner_diameter: float) -> None:
    document = ezdxf.new("R2010")
    document.units = units.MM
    modelspace = document.modelspace()
    modelspace.add_circle((0.0, 0.0), outer_diameter / 2.0)
    modelspace.add_circle((0.0, 0.0), inner_diameter / 2.0)
    document.saveas(path)


def _write_ring_step(path: Path) -> None:
    ring = cq.Workplane("XY").circle(25.0).circle(15.0).extrude(5.0)
    cq.exporters.export(ring, str(path), exportType="STEP")


def test_equal_ring_profiles_are_ok(tmp_path: Path) -> None:
    dxf_path = tmp_path / "ring.dxf"
    step_path = tmp_path / "ring.step"
    _write_ring_dxf(dxf_path, outer_diameter=50.0, inner_diameter=30.0)
    _write_ring_step(step_path)

    result = compare_uploaded_profiles(
        dxf_path.read_bytes(),
        dxf_path.name,
        step_path.read_bytes(),
        step_path.name,
        tolerance_mm=0.1,
        requested_view="auto",
    )

    assert result.judgement == OK
    assert result.selected_view == "top"
    assert result.ng_count == 0
    assert any(check.feature == "Outer circular profile diameter" for check in result.checks)
    assert any(check.feature == "Internal circular profile 1 diameter" for check in result.checks)


def test_wrong_outer_ring_diameter_is_ng(tmp_path: Path) -> None:
    dxf_path = tmp_path / "wrong_ring.dxf"
    step_path = tmp_path / "ring.step"
    _write_ring_dxf(dxf_path, outer_diameter=52.0, inner_diameter=30.0)
    _write_ring_step(step_path)

    result = compare_uploaded_profiles(
        dxf_path.read_bytes(),
        dxf_path.name,
        step_path.read_bytes(),
        step_path.name,
        tolerance_mm=0.1,
        requested_view="top",
    )

    assert result.judgement == NG
    outer = next(check for check in result.checks if check.feature == "Outer circular profile diameter")
    assert outer.judgement == NG
    assert outer.difference == pytest.approx(-2.0)


def test_missing_inner_ring_profile_is_ng(tmp_path: Path) -> None:
    dxf_path = tmp_path / "disc.dxf"
    step_path = tmp_path / "ring.step"
    document = ezdxf.new("R2010")
    document.units = units.MM
    document.modelspace().add_circle((0.0, 0.0), 25.0)
    document.saveas(dxf_path)
    _write_ring_step(step_path)

    result = compare_uploaded_profiles(
        dxf_path.read_bytes(),
        dxf_path.name,
        step_path.read_bytes(),
        step_path.name,
        tolerance_mm=0.1,
        requested_view="top",
    )

    count_check = next(check for check in result.checks if check.feature == "Circular profile count")
    assert result.judgement == NG
    assert count_check.judgement == NG


def test_equal_profile_is_ng_without_an_authorized_tolerance(tmp_path: Path) -> None:
    dxf_path = tmp_path / "ring.dxf"
    step_path = tmp_path / "ring.step"
    _write_ring_dxf(dxf_path, outer_diameter=50.0, inner_diameter=30.0)
    _write_ring_step(step_path)

    result = compare_uploaded_profiles(
        dxf_path.read_bytes(),
        dxf_path.name,
        step_path.read_bytes(),
        step_path.name,
        tolerance_mm=None,
        requested_view="top",
    )

    assert result.judgement == NG
    assert any(check.tolerance is None for check in result.checks)
    assert any("no profile limit is authorized" in check.details for check in result.checks)

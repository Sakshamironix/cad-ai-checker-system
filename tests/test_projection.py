"""Tests for deterministic STEP vector projections."""

from __future__ import annotations

import cadquery as cq
import pytest

from app.projection import ProjectionError, project_step_shape


def test_top_projection_detects_ring_profiles() -> None:
    ring = cq.Workplane("XY").circle(25.0).circle(15.0).extrude(5.0)

    projection = project_step_shape(ring.val(), "top")

    radii = sorted(
        primitive.radius
        for primitive in projection.primitives
        if primitive.kind == "circle" and primitive.radius is not None
    )
    assert projection.width == pytest.approx(50.0)
    assert projection.height == pytest.approx(50.0)
    assert radii == pytest.approx([15.0, 25.0])


def test_projection_rejects_unknown_view() -> None:
    box = cq.Workplane("XY").box(10.0, 20.0, 5.0)

    with pytest.raises(ProjectionError, match="View must be one of"):
        project_step_shape(box.val(), "isometric")

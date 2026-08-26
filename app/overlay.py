"""Create deterministic SVG overlays for DXF and STEP profile geometry."""

from __future__ import annotations

from dataclasses import dataclass
import html
import math
from typing import Iterable, Sequence

from app.profile_comparison import ProfileComparisonResult, ProfilePrimitive
from app.projection import Point2D, ProjectedPrimitive


DXF_COLOR = "#2563eb"
STEP_COLOR = "#16a34a"
MISMATCH_COLOR = "#dc2626"
GRID_COLOR = "#e2e8f0"


class OverlayError(ValueError):
    """Raised when a vector overlay cannot be generated."""


@dataclass(frozen=True)
class OverlayPrimitive:
    """One centered and orientation-aligned primitive."""

    kind: str
    points: tuple[Point2D, ...]
    mismatch: bool


@dataclass(frozen=True)
class OverlayVisualization:
    """SVG views and mismatch counts for one profile comparison."""

    dxf_svg: str
    step_svg: str
    combined_svg: str
    dxf_mismatch_count: int
    step_mismatch_count: int
    alignment_quarter_turns: int


Primitive = ProfilePrimitive | ProjectedPrimitive


def _all_points(primitives: Iterable[Primitive]) -> tuple[Point2D, ...]:
    return tuple(point for primitive in primitives for point in primitive.points)


def _bounds(points: Sequence[Point2D]) -> tuple[float, float, float, float]:
    if not points:
        raise OverlayError("Overlay geometry is empty.")
    return (
        min(point.x for point in points),
        min(point.y for point in points),
        max(point.x for point in points),
        max(point.y for point in points),
    )


def _center(primitives: Sequence[Primitive]) -> tuple[tuple[str, tuple[Point2D, ...]], ...]:
    points = _all_points(primitives)
    minimum_x, minimum_y, maximum_x, maximum_y = _bounds(points)
    center_x = (minimum_x + maximum_x) / 2.0
    center_y = (minimum_y + maximum_y) / 2.0
    return tuple(
        (
            primitive.kind,
            tuple(Point2D(point.x - center_x, point.y - center_y) for point in primitive.points),
        )
        for primitive in primitives
    )


def _rotate_point(point: Point2D, quarter_turns: int) -> Point2D:
    turns = quarter_turns % 4
    if turns == 0:
        return point
    if turns == 1:
        return Point2D(-point.y, point.x)
    if turns == 2:
        return Point2D(-point.x, -point.y)
    return Point2D(point.y, -point.x)


def _rotate(
    primitives: Sequence[tuple[str, tuple[Point2D, ...]]],
    quarter_turns: int,
) -> tuple[tuple[str, tuple[Point2D, ...]], ...]:
    return tuple(
        (kind, tuple(_rotate_point(point, quarter_turns) for point in points))
        for kind, points in primitives
    )


def _point_to_segment_distance(point: Point2D, start: Point2D, end: Point2D) -> float:
    delta_x = end.x - start.x
    delta_y = end.y - start.y
    length_squared = delta_x * delta_x + delta_y * delta_y
    if math.isclose(length_squared, 0.0):
        return math.hypot(point.x - start.x, point.y - start.y)
    fraction = (
        (point.x - start.x) * delta_x + (point.y - start.y) * delta_y
    ) / length_squared
    fraction = min(1.0, max(0.0, fraction))
    nearest_x = start.x + fraction * delta_x
    nearest_y = start.y + fraction * delta_y
    return math.hypot(point.x - nearest_x, point.y - nearest_y)


def _segments(
    primitives: Sequence[tuple[str, tuple[Point2D, ...]]],
) -> tuple[tuple[Point2D, Point2D], ...]:
    result: list[tuple[Point2D, Point2D]] = []
    for kind, points in primitives:
        result.extend(zip(points, points[1:]))
        if kind == "circle" and len(points) > 2:
            result.append((points[-1], points[0]))
    return tuple(result)


def _maximum_distance(
    points: Sequence[Point2D],
    target_segments: Sequence[tuple[Point2D, Point2D]],
) -> float:
    if not points or not target_segments:
        return math.inf
    return max(
        min(_point_to_segment_distance(point, start, end) for start, end in target_segments)
        for point in points
    )


def _alignment_deviation(
    first: Sequence[tuple[str, tuple[Point2D, ...]]],
    second: Sequence[tuple[str, tuple[Point2D, ...]]],
) -> float:
    first_segments = _segments(first)
    second_segments = _segments(second)
    first_points = tuple(point for _, points in first for point in points)
    second_points = tuple(point for _, points in second for point in points)
    return max(
        _maximum_distance(first_points, second_segments),
        _maximum_distance(second_points, first_segments),
    )


def _best_alignment(
    dxf: Sequence[tuple[str, tuple[Point2D, ...]]],
    step: Sequence[tuple[str, tuple[Point2D, ...]]],
) -> tuple[int, tuple[tuple[str, tuple[Point2D, ...]], ...]]:
    candidates = tuple((turns, _rotate(step, turns)) for turns in range(4))
    return min(candidates, key=lambda candidate: _alignment_deviation(dxf, candidate[1]))


def _mark_mismatches(
    source: Sequence[tuple[str, tuple[Point2D, ...]]],
    target: Sequence[tuple[str, tuple[Point2D, ...]]],
    tolerance_mm: float,
) -> tuple[OverlayPrimitive, ...]:
    target_segments = _segments(target)
    return tuple(
        OverlayPrimitive(
            kind=kind,
            points=points,
            mismatch=_maximum_distance(points, target_segments) > tolerance_mm,
        )
        for kind, points in source
    )


def _svg(
    title: str,
    layers: Sequence[tuple[str, Sequence[OverlayPrimitive], str]],
    width: int = 900,
    height: int = 520,
) -> str:
    all_points = tuple(
        point
        for _, primitives, _ in layers
        for primitive in primitives
        for point in primitive.points
    )
    minimum_x, minimum_y, maximum_x, maximum_y = _bounds(all_points)
    span_x = max(maximum_x - minimum_x, 1.0)
    span_y = max(maximum_y - minimum_y, 1.0)
    padding = 42.0
    scale = min((width - 2.0 * padding) / span_x, (height - 2.0 * padding) / span_y)

    def screen(point: Point2D) -> tuple[float, float]:
        x = padding + (point.x - minimum_x) * scale
        y = height - padding - (point.y - minimum_y) * scale
        return x, y

    paths: list[str] = []
    for layer_name, primitives, base_color in layers:
        for index, primitive in enumerate(primitives):
            coordinates = [screen(point) for point in primitive.points]
            path_data = " ".join(
                ("M" if point_index == 0 else "L") + f" {x:.2f} {y:.2f}"
                for point_index, (x, y) in enumerate(coordinates)
            )
            if primitive.kind == "circle":
                path_data += " Z"
            color = MISMATCH_COLOR if primitive.mismatch else base_color
            dash = ' stroke-dasharray="8 5"' if primitive.mismatch else ""
            paths.append(
                f'<path data-layer="{html.escape(layer_name)}" data-index="{index}" '
                f'data-mismatch="{str(primitive.mismatch).lower()}" d="{path_data}" '
                f'fill="none" stroke="{color}" stroke-width="{3.2 if primitive.mismatch else 1.8}"'
                f' stroke-linecap="round" stroke-linejoin="round"{dash}/>'
            )

    safe_title = html.escape(title)
    return (
        f'<svg role="img" aria-label="{safe_title}" viewBox="0 0 {width} {height}" '
        'style="width:100%;height:auto;background:#ffffff;border:1px solid #cbd5e1;'
        'border-radius:10px">'
        f'<title>{safe_title}</title>'
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>'
        f'<path d="M {width / 2:.1f} 20 V {height - 20}" stroke="{GRID_COLOR}" stroke-width="1"/>'
        f'<path d="M 20 {height / 2:.1f} H {width - 20}" stroke="{GRID_COLOR}" stroke-width="1"/>'
        + "".join(paths)
        + "</svg>"
    )


def build_overlay_visualization(
    result: ProfileComparisonResult,
    tolerance_mm: float | None,
) -> OverlayVisualization:
    """Build centered DXF, STEP, and combined SVG views with mismatch highlighting."""
    if tolerance_mm is not None and tolerance_mm <= 0:
        raise OverlayError("Overlay tolerance must be greater than zero.")
    if not result.dxf_primitives or not result.step_projection.primitives:
        raise OverlayError("Both DXF and STEP profile geometry are required for an overlay.")

    dxf_centered = _center(result.dxf_primitives)
    step_centered = _center(result.step_projection.primitives)
    turns, step_aligned = _best_alignment(dxf_centered, step_centered)
    if tolerance_mm is None:
        dxf_marked = tuple(
            OverlayPrimitive(kind, points, False) for kind, points in dxf_centered
        )
        step_marked = tuple(
            OverlayPrimitive(kind, points, False) for kind, points in step_aligned
        )
    else:
        dxf_marked = _mark_mismatches(dxf_centered, step_aligned, tolerance_mm)
        step_marked = _mark_mismatches(step_aligned, dxf_centered, tolerance_mm)

    dxf_only = tuple(
        OverlayPrimitive(item.kind, item.points, False) for item in dxf_marked
    )
    step_only = tuple(
        OverlayPrimitive(item.kind, item.points, False) for item in step_marked
    )
    return OverlayVisualization(
        dxf_svg=_svg("DXF profile", (("dxf", dxf_only, DXF_COLOR),)),
        step_svg=_svg("STEP projected profile", (("step", step_only, STEP_COLOR),)),
        combined_svg=_svg(
            "DXF and STEP profile overlay",
            (
                ("dxf", dxf_marked, DXF_COLOR),
                ("step", step_marked, STEP_COLOR),
            ),
        ),
        dxf_mismatch_count=sum(item.mismatch for item in dxf_marked),
        step_mismatch_count=sum(item.mismatch for item in step_marked),
        alignment_quarter_turns=turns,
    )

"""Compare DXF profile geometry with deterministic STEP vector projections."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterable, Sequence

import ezdxf
import numpy as np

from app.projection import Point2D, ProjectionError, StepProjection, project_step_bytes

OK = "OK"
NG = "NG"


class ProfileComparisonError(ValueError):
    """Raised when profile geometry cannot be compared."""


@dataclass(frozen=True)
class ProfilePrimitive:
    kind: str
    points: tuple[Point2D, ...]
    center: Point2D | None = None
    radius: float | None = None


@dataclass(frozen=True)
class ProfileCheck:
    category: str
    feature: str
    drawing_value: float | int | str | None
    model_value: float | int | str | None
    difference: float | None
    tolerance: float | None
    judgement: str
    details: str


@dataclass(frozen=True)
class ProfileComparisonResult:
    drawing_source: str
    model_source: str
    selected_view: str
    judgement: str
    reason: str
    checks: tuple[ProfileCheck, ...]
    dxf_primitives: tuple[ProfilePrimitive, ...]
    step_projection: StepProjection

    @property
    def ok_count(self) -> int:
        return sum(check.judgement == OK for check in self.checks)

    @property
    def ng_count(self) -> int:
        return sum(check.judgement == NG for check in self.checks)

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["ok_count"] = self.ok_count
        result["ng_count"] = self.ng_count
        return result


def _circle_points(center: Point2D, radius: float, count: int = 96) -> tuple[Point2D, ...]:
    return tuple(
        Point2D(
            x=center.x + radius * math.cos(index * 2.0 * math.pi / count),
            y=center.y + radius * math.sin(index * 2.0 * math.pi / count),
        )
        for index in range(count)
    )


def _line_points(start: Point2D, end: Point2D, count: int = 32) -> tuple[Point2D, ...]:
    return tuple(
        Point2D(
            x=start.x + (end.x - start.x) * index / (count - 1),
            y=start.y + (end.y - start.y) * index / (count - 1),
        )
        for index in range(count)
    )


def _arc_points(
    center: Point2D,
    radius: float,
    start_angle: float,
    end_angle: float,
    count: int = 48,
) -> tuple[Point2D, ...]:
    sweep = (end_angle - start_angle) % 360.0
    if math.isclose(sweep, 0.0):
        sweep = 360.0
    return tuple(
        Point2D(
            x=center.x + radius * math.cos(math.radians(start_angle + sweep * index / (count - 1))),
            y=center.y + radius * math.sin(math.radians(start_angle + sweep * index / (count - 1))),
        )
        for index in range(count)
    )


def _entity_primitives(entity: object) -> list[ProfilePrimitive]:
    entity_type = entity.dxftype()
    if entity_type == "CIRCLE":
        center = Point2D(float(entity.dxf.center.x), float(entity.dxf.center.y))
        radius = float(entity.dxf.radius)
        return [ProfilePrimitive("circle", _circle_points(center, radius), center, radius)]
    if entity_type == "LINE":
        start = Point2D(float(entity.dxf.start.x), float(entity.dxf.start.y))
        end = Point2D(float(entity.dxf.end.x), float(entity.dxf.end.y))
        return [ProfilePrimitive("line", _line_points(start, end))]
    if entity_type == "ARC":
        center = Point2D(float(entity.dxf.center.x), float(entity.dxf.center.y))
        radius = float(entity.dxf.radius)
        return [
            ProfilePrimitive(
                "arc",
                _arc_points(
                    center,
                    radius,
                    float(entity.dxf.start_angle),
                    float(entity.dxf.end_angle),
                ),
                center,
                radius,
            )
        ]
    if entity_type in {"LWPOLYLINE", "POLYLINE"}:
        primitives: list[ProfilePrimitive] = []
        try:
            for virtual in entity.virtual_entities():
                primitives.extend(_entity_primitives(virtual))
        except Exception:
            return []
        return primitives
    if entity_type == "SPLINE":
        try:
            points = tuple(Point2D(float(point.x), float(point.y)) for point in entity.flattening(0.05))
        except Exception:
            return []
        return [ProfilePrimitive("curve", points)] if len(points) >= 2 else []
    return []


def extract_dxf_profile(data: bytes, filename: str) -> tuple[ProfilePrimitive, ...]:
    """Extract only model-space profile geometry, excluding annotations."""
    if not filename.lower().endswith(".dxf"):
        raise ProfileComparisonError("Only .dxf drawings are supported.")
    if not data:
        raise ProfileComparisonError("The uploaded DXF file is empty.")
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(suffix=".dxf", delete=False) as temporary_file:
            temporary_file.write(data)
            temporary_path = Path(temporary_file.name)
        document = ezdxf.readfile(temporary_path)
    except Exception as exc:
        raise ProfileComparisonError(f"Could not read DXF profile geometry: {exc}") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    primitives: list[ProfilePrimitive] = []
    for entity in document.modelspace():
        primitives.extend(_entity_primitives(entity))
    if not primitives:
        raise ProfileComparisonError(
            "The DXF contains no supported LINE, ARC, CIRCLE, POLYLINE, or SPLINE profile geometry."
        )
    return tuple(primitives)


def _all_points(primitives: Iterable[ProfilePrimitive | object]) -> np.ndarray:
    rows = [(point.x, point.y) for primitive in primitives for point in primitive.points]
    if not rows:
        return np.empty((0, 2), dtype=float)
    return np.asarray(rows, dtype=float)


def _bounds(points: np.ndarray) -> tuple[float, float, float, float]:
    minimum = points.min(axis=0)
    maximum = points.max(axis=0)
    return float(minimum[0]), float(minimum[1]), float(maximum[0]), float(maximum[1])


def _center_on_bounds(points: np.ndarray) -> np.ndarray:
    minimum = points.min(axis=0)
    maximum = points.max(axis=0)
    return points - ((minimum + maximum) / 2.0)


def _rotate(points: np.ndarray, quarter_turns: int) -> np.ndarray:
    angle = quarter_turns * math.pi / 2.0
    matrix = np.asarray(
        [[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]],
        dtype=float,
    )
    return points @ matrix.T


def _directed_hausdorff(first: np.ndarray, second: np.ndarray) -> float:
    if first.size == 0 or second.size == 0:
        return math.inf
    maximum = 0.0
    for start in range(0, len(first), 256):
        chunk = first[start : start + 256]
        distances = np.sqrt(((chunk[:, None, :] - second[None, :, :]) ** 2).sum(axis=2))
        maximum = max(maximum, float(distances.min(axis=1).max()))
    return maximum


def _best_profile_deviation(dxf_points: np.ndarray, step_points: np.ndarray) -> float:
    dxf_centered = _center_on_bounds(dxf_points)
    step_centered = _center_on_bounds(step_points)
    candidates: list[float] = []
    for turns in range(4):
        rotated = _rotate(step_centered, turns)
        candidates.append(
            max(
                _directed_hausdorff(dxf_centered, rotated),
                _directed_hausdorff(rotated, dxf_centered),
            )
        )
    return min(candidates)


def _check(
    category: str,
    feature: str,
    drawing: float,
    model: float,
    tolerance: float,
) -> ProfileCheck:
    difference = model - drawing
    judgement = OK if abs(difference) <= tolerance else NG
    details = (
        f"Difference {difference:+.6g} mm is within the comparison tolerance."
        if judgement == OK
        else f"Difference {difference:+.6g} mm exceeds the comparison tolerance by {abs(difference) - tolerance:.6g} mm."
    )
    return ProfileCheck(category, feature, drawing, model, difference, tolerance, judgement, details)


def _feature_count_check(feature: str, drawing: int, model: int) -> ProfileCheck:
    judgement = OK if drawing == model else NG
    return ProfileCheck(
        category="Profile",
        feature=feature,
        drawing_value=drawing,
        model_value=model,
        difference=float(model - drawing),
        tolerance=0.0,
        judgement=judgement,
        details="Feature counts agree." if judgement == OK else "Feature counts do not agree.",
    )


def compare_profile_geometry(
    dxf_primitives: Sequence[ProfilePrimitive],
    projection: StepProjection,
    tolerance_mm: float,
    drawing_source: str = "drawing.dxf",
    model_source: str = "model.step",
) -> ProfileComparisonResult:
    """Compare one DXF profile with one STEP projection."""
    if tolerance_mm <= 0:
        raise ProfileComparisonError("Comparison tolerance must be greater than zero.")

    dxf_points = _all_points(dxf_primitives)
    step_points = _all_points(projection.primitives)
    if dxf_points.size == 0 or step_points.size == 0:
        raise ProfileComparisonError("Both files must provide comparable profile geometry.")

    dxf_bounds = _bounds(dxf_points)
    step_bounds = _bounds(step_points)
    dxf_width = dxf_bounds[2] - dxf_bounds[0]
    dxf_height = dxf_bounds[3] - dxf_bounds[1]
    step_width = step_bounds[2] - step_bounds[0]
    step_height = step_bounds[3] - step_bounds[1]

    same_orientation_error = abs(step_width - dxf_width) + abs(step_height - dxf_height)
    rotated_error = abs(step_height - dxf_width) + abs(step_width - dxf_height)
    if rotated_error < same_orientation_error:
        step_width, step_height = step_height, step_width

    checks: list[ProfileCheck] = [
        _check("Profile", "Overall profile width", dxf_width, step_width, tolerance_mm),
        _check("Profile", "Overall profile height", dxf_height, step_height, tolerance_mm),
    ]

    dxf_circles = sorted(
        (primitive for primitive in dxf_primitives if primitive.kind == "circle" and primitive.radius is not None),
        key=lambda item: item.radius or 0.0,
        reverse=True,
    )
    step_circles = sorted(
        (primitive for primitive in projection.primitives if primitive.kind == "circle" and primitive.radius is not None),
        key=lambda item: item.radius or 0.0,
        reverse=True,
    )
    checks.append(_feature_count_check("Circular profile count", len(dxf_circles), len(step_circles)))

    for index, (drawing_circle, model_circle) in enumerate(zip(dxf_circles, step_circles)):
        label = "Outer circular profile diameter" if index == 0 else f"Internal circular profile {index} diameter"
        checks.append(
            _check(
                "Profile",
                label,
                float(drawing_circle.radius) * 2.0,
                float(model_circle.radius) * 2.0,
                tolerance_mm,
            )
        )

    deviation = _best_profile_deviation(dxf_points, step_points)
    deviation_judgement = OK if deviation <= tolerance_mm else NG
    checks.append(
        ProfileCheck(
            category="Profile",
            feature="Maximum profile deviation",
            drawing_value=0.0,
            model_value=deviation,
            difference=deviation,
            tolerance=tolerance_mm,
            judgement=deviation_judgement,
            details=(
                "Projected profile agrees within the comparison tolerance."
                if deviation_judgement == OK
                else f"Projected profile exceeds the comparison tolerance by {deviation - tolerance_mm:.6g} mm."
            ),
        )
    )

    overall = NG if any(check.judgement == NG for check in checks) else OK
    reason = (
        "All profile comparisons are within the applicable limits."
        if overall == OK
        else f"{sum(check.judgement == NG for check in checks)} profile comparison(s) are NG."
    )
    return ProfileComparisonResult(
        drawing_source=drawing_source,
        model_source=model_source,
        selected_view=projection.view,
        judgement=overall,
        reason=reason,
        checks=tuple(checks),
        dxf_primitives=tuple(dxf_primitives),
        step_projection=projection,
    )


def compare_uploaded_profiles(
    dxf_data: bytes,
    dxf_filename: str,
    step_data: bytes,
    step_filename: str,
    tolerance_mm: float,
    requested_view: str = "auto",
) -> ProfileComparisonResult:
    """Extract, select a projection, and compare uploaded CAD profiles."""
    dxf_primitives = extract_dxf_profile(dxf_data, dxf_filename)
    try:
        projections = project_step_bytes(step_data, step_filename)
    except ProjectionError as exc:
        raise ProfileComparisonError(str(exc)) from exc

    requested = requested_view.lower()
    if requested != "auto":
        candidates = [projection for projection in projections if projection.view == requested]
        if not candidates:
            raise ProfileComparisonError("Requested STEP projection is not available.")
        selected = candidates[0]
    else:
        dxf_points = _all_points(dxf_primitives)
        selected = min(
            projections,
            key=lambda projection: _best_profile_deviation(
                dxf_points,
                _all_points(projection.primitives),
            ),
        )

    return compare_profile_geometry(
        dxf_primitives,
        selected,
        tolerance_mm,
        drawing_source=dxf_filename,
        model_source=step_filename,
    )

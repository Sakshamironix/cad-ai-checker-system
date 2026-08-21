"""Deterministic vector projections of simple STEP geometry."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Final, Iterable

import cadquery as cq
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Line


SUPPORTED_VIEWS: Final = ("top", "front", "right")
MAX_STEP_FILE_SIZE_BYTES: Final = 25 * 1024 * 1024


class ProjectionError(ValueError):
    """Raised when a STEP projection cannot be generated."""


@dataclass(frozen=True)
class Point2D:
    x: float
    y: float


@dataclass(frozen=True)
class ProjectedPrimitive:
    """One projected STEP edge represented as deterministic 2D geometry."""

    kind: str
    points: tuple[Point2D, ...]
    center: Point2D | None = None
    radius: float | None = None


@dataclass(frozen=True)
class StepProjection:
    """A vector projection suitable for geometric comparison."""

    view: str
    width: float
    height: float
    primitives: tuple[ProjectedPrimitive, ...]

    @property
    def circle_count(self) -> int:
        return sum(item.kind == "circle" for item in self.primitives)

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["circle_count"] = self.circle_count
        return result


def _project_xyz(x: float, y: float, z: float, view: str) -> Point2D:
    if view == "top":
        return Point2D(x=x, y=y)
    if view == "front":
        return Point2D(x=x, y=z)
    if view == "right":
        return Point2D(x=y, y=z)
    raise ProjectionError(f"Unsupported projection view: {view}")


def _view_direction(view: str) -> tuple[float, float, float]:
    if view == "top":
        return (0.0, 0.0, 1.0)
    if view == "front":
        return (0.0, 1.0, 0.0)
    if view == "right":
        return (1.0, 0.0, 0.0)
    raise ProjectionError(f"Unsupported projection view: {view}")


def _project_vector(vector: cq.Vector, view: str) -> Point2D:
    return _project_xyz(float(vector.x), float(vector.y), float(vector.z), view)


def _rounded_point(point: Point2D, digits: int = 7) -> tuple[float, float]:
    return (round(point.x, digits), round(point.y, digits))


def _sample_edge(edge: cq.Edge, view: str, count: int = 96) -> tuple[Point2D, ...]:
    try:
        vectors = edge.discretize(n=count)
    except Exception:
        vectors = [edge.startPoint(), edge.endPoint()]
    return tuple(_project_vector(vector, view) for vector in vectors)


def _deduplicate(primitives: Iterable[ProjectedPrimitive]) -> tuple[ProjectedPrimitive, ...]:
    unique: list[ProjectedPrimitive] = []
    keys: set[tuple[object, ...]] = set()
    for primitive in primitives:
        if primitive.kind == "circle" and primitive.center and primitive.radius is not None:
            key = (
                "circle",
                *_rounded_point(primitive.center),
                round(primitive.radius, 7),
            )
        else:
            rounded = tuple(_rounded_point(point) for point in primitive.points)
            reverse = tuple(reversed(rounded))
            key = (primitive.kind, min(rounded, reverse))
        if key in keys:
            continue
        keys.add(key)
        unique.append(primitive)
    return tuple(unique)


def project_step_shape(shape: cq.Shape, view: str) -> StepProjection:
    """Project STEP edges into top, front, or right-side vector geometry."""
    view = view.lower()
    if view not in SUPPORTED_VIEWS:
        raise ProjectionError(f"View must be one of: {', '.join(SUPPORTED_VIEWS)}")
    if shape is None or shape.isNull():
        raise ProjectionError("The STEP shape is empty.")

    direction = _view_direction(view)
    primitives: list[ProjectedPrimitive] = []
    for edge in shape.Edges():
        adaptor = BRepAdaptor_Curve(edge.wrapped)
        curve_type = adaptor.GetType()
        if curve_type == GeomAbs_Circle:
            circle = adaptor.Circle()
            axis = circle.Axis().Direction()
            alignment = abs(
                float(axis.X()) * direction[0]
                + float(axis.Y()) * direction[1]
                + float(axis.Z()) * direction[2]
            )
            if alignment >= 0.999:
                location = circle.Location()
                center = _project_xyz(
                    float(location.X()),
                    float(location.Y()),
                    float(location.Z()),
                    view,
                )
                radius = float(circle.Radius())
                points = tuple(
                    Point2D(
                        x=center.x + radius * math.cos(index * 2.0 * math.pi / 96),
                        y=center.y + radius * math.sin(index * 2.0 * math.pi / 96),
                    )
                    for index in range(96)
                )
                primitives.append(
                    ProjectedPrimitive(
                        kind="circle",
                        points=points,
                        center=center,
                        radius=radius,
                    )
                )
                continue

        points = _sample_edge(edge, view)
        if len(points) < 2:
            continue
        kind = "line" if curve_type == GeomAbs_Line else "curve"
        primitives.append(ProjectedPrimitive(kind=kind, points=points))

    box = shape.BoundingBox()
    if view == "top":
        width, height = float(box.xlen), float(box.ylen)
    elif view == "front":
        width, height = float(box.xlen), float(box.zlen)
    else:
        width, height = float(box.ylen), float(box.zlen)

    return StepProjection(
        view=view,
        width=width,
        height=height,
        primitives=_deduplicate(primitives),
    )


def project_step_bytes(data: bytes, filename: str) -> tuple[StepProjection, ...]:
    """Import uploaded STEP bytes and return all supported projections."""
    suffix = Path(filename).suffix.lower()
    if suffix not in {".step", ".stp"}:
        raise ProjectionError("Only .step and .stp files are supported.")
    if not data:
        raise ProjectionError("The uploaded STEP file is empty.")
    if len(data) > MAX_STEP_FILE_SIZE_BYTES:
        raise ProjectionError("The STEP file exceeds the 25 MB prototype limit.")

    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(suffix=suffix, delete=False) as temporary_file:
            temporary_file.write(data)
            temporary_path = Path(temporary_file.name)
        imported = cq.importers.importStep(str(temporary_path))
        shape = imported.val()
        return tuple(project_step_shape(shape, view) for view in SUPPORTED_VIEWS)
    except ProjectionError:
        raise
    except Exception as exc:
        raise ProjectionError(f"Could not generate STEP projections: {exc}") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

"""STEP/STP loading and geometry analysis utilities."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Final

import cadquery as cq
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Cylinder, GeomAbs_Plane, GeomAbs_Torus
from OCP.TopAbs import TopAbs_REVERSED
from app.runtime_limits import load_runtime_limits

SUPPORTED_STEP_EXTENSIONS: Final = {".step", ".stp"}
MAX_STEP_FILE_SIZE_BYTES: Final = 25 * 1024 * 1024


class StepReaderError(ValueError):
    """Raised when a STEP file cannot be validated or analyzed."""


@dataclass(frozen=True)
class Vector3D:
    """A serializable three-dimensional vector."""

    x: float
    y: float
    z: float


@dataclass(frozen=True)
class TopologyCounts:
    """Counts of the primary boundary-representation entities."""

    solids: int
    shells: int
    faces: int
    edges: int
    vertices: int


@dataclass(frozen=True)
class HoleFeature:
    """A likely cylindrical hole detected from reversed face orientation."""

    face_index: int
    radius: float
    diameter: float


@dataclass(frozen=True)
class StepAnalysis:
    """Serializable STEP model analysis returned to the UI and tests."""

    source_name: str
    topology: TopologyCounts
    bounding_box: Vector3D
    volume: float
    surface_area: float
    center_of_mass: Vector3D
    planar_faces: int
    cylindrical_faces: int
    circular_edges: int
    outer_boundaries: int
    outer_boundary_length: float
    holes: tuple[HoleFeature, ...]
    toroidal_faces: int = 0

    @property
    def hole_count(self) -> int:
        """Return the number of likely holes."""
        return len(self.holes)

    def to_dict(self) -> dict[str, object]:
        """Convert the complete result into Streamlit/JSON-friendly values."""
        result = asdict(self)
        result["hole_count"] = self.hole_count
        return result


def _validate_filename(filename: str) -> str:
    """Validate an uploaded name and return its normalized suffix."""
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_STEP_EXTENSIONS:
        raise StepReaderError("Only .step and .stp files are supported.")
    return suffix


def _cylindrical_face_radius(face: cq.Face) -> float:
    """Read a cylindrical face radius using OpenCASCADE's surface adaptor."""
    adaptor = BRepAdaptor_Surface(face.wrapped)
    return float(adaptor.Cylinder().Radius())


def analyze_step_file(file_path: str | Path, source_name: str | None = None) -> StepAnalysis:
    """Load and analyze a STEP/STP file from disk."""
    path = Path(file_path)
    display_name = source_name or path.name
    _validate_filename(display_name)

    if not path.is_file():
        raise StepReaderError(f"STEP file was not found: {path}")
    if path.stat().st_size == 0:
        raise StepReaderError("The uploaded STEP file is empty.")
    limits = load_runtime_limits()
    if path.stat().st_size > limits.max_step_bytes:
        raise StepReaderError("The STEP file exceeds the configured pilot upload limit.")

    try:
        imported = cq.importers.importStep(str(path))
        shape = imported.val()
    except Exception as exc:  # CadQuery exposes multiple parser exception types.
        raise StepReaderError(f"OpenCASCADE could not read this STEP file: {exc}") from exc

    if shape is None or shape.isNull():
        raise StepReaderError("The STEP file did not contain readable geometry.")

    solids = shape.Solids()
    shells = shape.Shells()
    faces = shape.Faces()
    edges = shape.Edges()
    vertices = shape.Vertices()
    if len(faces) > limits.max_step_faces or len(edges) > limits.max_step_edges:
        raise StepReaderError("The STEP topology exceeds the configured pilot processing limit.")
    bounding_box = shape.BoundingBox()
    center = shape.Center()

    planar_faces = 0
    cylindrical_faces = 0
    toroidal_faces = 0
    holes: list[HoleFeature] = []
    outer_boundaries = 0
    outer_boundary_length = 0.0

    for face_index, face in enumerate(faces, start=1):
        surface = BRepAdaptor_Surface(face.wrapped)
        surface_type = surface.GetType()
        if surface_type == GeomAbs_Plane:
            planar_faces += 1
        elif surface_type == GeomAbs_Cylinder:
            cylindrical_faces += 1
            if face.wrapped.Orientation() == TopAbs_REVERSED:
                radius = _cylindrical_face_radius(face)
                holes.append(
                    HoleFeature(
                        face_index=face_index,
                        radius=radius,
                        diameter=radius * 2.0,
                    )
                )
        elif surface_type == GeomAbs_Torus:
            toroidal_faces += 1

        try:
            outer_wire = face.outerWire()
            outer_boundaries += 1
            outer_boundary_length += float(outer_wire.Length())
        except Exception:
            # Degenerate imported faces can lack a usable outer wire; analysis continues.
            continue

    circular_edges = 0
    for edge in edges:
        curve = BRepAdaptor_Curve(edge.wrapped)
        if curve.GetType() == GeomAbs_Circle:
            circular_edges += 1

    return StepAnalysis(
        source_name=display_name,
        topology=TopologyCounts(
            solids=len(solids),
            shells=len(shells),
            faces=len(faces),
            edges=len(edges),
            vertices=len(vertices),
        ),
        bounding_box=Vector3D(
            x=float(bounding_box.xlen),
            y=float(bounding_box.ylen),
            z=float(bounding_box.zlen),
        ),
        volume=float(shape.Volume()),
        surface_area=float(shape.Area()),
        center_of_mass=Vector3D(
            x=float(center.x),
            y=float(center.y),
            z=float(center.z),
        ),
        planar_faces=planar_faces,
        cylindrical_faces=cylindrical_faces,
        circular_edges=circular_edges,
        outer_boundaries=outer_boundaries,
        outer_boundary_length=outer_boundary_length,
        holes=tuple(holes),
        toroidal_faces=toroidal_faces,
    )


def analyze_step_bytes(data: bytes, filename: str) -> StepAnalysis:
    """Safely analyze uploaded STEP bytes using a temporary file."""
    suffix = _validate_filename(filename)
    if not data:
        raise StepReaderError("The uploaded STEP file is empty.")
    if len(data) > load_runtime_limits().max_step_bytes:
        raise StepReaderError("The STEP file exceeds the configured pilot upload limit.")

    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(suffix=suffix, delete=False) as temporary_file:
            temporary_file.write(data)
            temporary_path = Path(temporary_file.name)
        return analyze_step_file(temporary_path, source_name=filename)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

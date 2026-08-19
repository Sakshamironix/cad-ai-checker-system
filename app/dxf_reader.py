"""DXF loading and two-dimensional drawing analysis utilities."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Final

import ezdxf
from ezdxf import bbox
from ezdxf.lldxf.const import DXFError

SUPPORTED_DXF_EXTENSIONS: Final = {".dxf"}
MAX_DXF_FILE_SIZE_BYTES: Final = 25 * 1024 * 1024

DXF_UNIT_NAMES: Final[dict[int, str]] = {
    0: "Unitless",
    1: "Inches",
    2: "Feet",
    3: "Miles",
    4: "Millimetres",
    5: "Centimetres",
    6: "Metres",
    7: "Kilometres",
    8: "Microinches",
    9: "Mils",
    10: "Yards",
    11: "Angstroms",
    12: "Nanometres",
    13: "Micrometres",
    14: "Decimetres",
    15: "Decametres",
    16: "Hectometres",
    17: "Gigametres",
    18: "Astronomical units",
    19: "Light years",
    20: "Parsecs",
}

DIMENSION_TYPE_NAMES: Final[dict[int, str]] = {
    0: "Linear",
    1: "Aligned",
    2: "Angular",
    3: "Diameter",
    4: "Radius",
    5: "Angular 3-point",
    6: "Ordinate",
}


class DxfReaderError(ValueError):
    """Raised when a DXF file cannot be validated or analyzed."""


@dataclass(frozen=True)
class Point2D:
    """A serializable two-dimensional coordinate."""

    x: float
    y: float


@dataclass(frozen=True)
class DrawingExtents:
    """Axis-aligned model-space extents."""

    minimum: Point2D
    maximum: Point2D
    width: float
    height: float


@dataclass(frozen=True)
class EntityCounts:
    """Counts of supported and unsupported model-space DXF entities."""

    total: int
    lines: int
    circles: int
    arcs: int
    lightweight_polylines: int
    polylines: int
    text: int
    multiline_text: int
    dimensions: int
    other: int


@dataclass(frozen=True)
class CircleFeature:
    """A circle entity that may later be matched with a 3D hole."""

    entity_index: int
    layer: str
    center: Point2D
    radius: float
    diameter: float


@dataclass(frozen=True)
class ArcFeature:
    """An arc entity from the 2D drawing."""

    entity_index: int
    layer: str
    center: Point2D
    radius: float
    start_angle: float
    end_angle: float


@dataclass(frozen=True)
class DimensionFeature:
    """A DXF dimension with its measured value and optional text override."""

    entity_index: int
    layer: str
    dimension_type: str
    measurement: float | None
    text_override: str | None
    style: str


@dataclass(frozen=True)
class TextFeature:
    """A TEXT or MTEXT annotation from model space."""

    entity_index: int
    entity_type: str
    layer: str
    content: str


@dataclass(frozen=True)
class DxfAnalysis:
    """Serializable DXF drawing analysis returned to the UI and tests."""

    source_name: str
    dxf_version: str
    units_code: int
    units_name: str
    layers: tuple[str, ...]
    entity_counts: EntityCounts
    extents: DrawingExtents | None
    circles: tuple[CircleFeature, ...]
    arcs: tuple[ArcFeature, ...]
    dimensions: tuple[DimensionFeature, ...]
    texts: tuple[TextFeature, ...]
    entity_types: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        """Convert the complete result into Streamlit/JSON-friendly values."""
        return asdict(self)


def _validate_filename(filename: str) -> str:
    """Validate an uploaded filename and return its normalized suffix."""
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_DXF_EXTENSIONS:
        raise DxfReaderError("Only .dxf files are supported by the 2D reader.")
    return suffix


def _read_text(entity: object, entity_type: str) -> str:
    """Return visible content from a TEXT or MTEXT entity."""
    if entity_type == "TEXT":
        return str(entity.dxf.text)
    return str(entity.plain_text())


def _read_measurement(entity: object) -> float | None:
    """Read a dimension measurement without rejecting partially defined DXFs."""
    try:
        return float(entity.get_measurement())
    except (AttributeError, TypeError, ValueError, DXFError):
        return None


def _drawing_extents(modelspace: object) -> DrawingExtents | None:
    """Calculate model-space extents for entities supported by ezdxf."""
    try:
        box = bbox.extents(modelspace, fast=True)
    except (DXFError, TypeError, ValueError):
        return None

    if not box.has_data:
        return None

    return DrawingExtents(
        minimum=Point2D(x=float(box.extmin.x), y=float(box.extmin.y)),
        maximum=Point2D(x=float(box.extmax.x), y=float(box.extmax.y)),
        width=float(box.size.x),
        height=float(box.size.y),
    )


def analyze_dxf_file(file_path: str | Path, source_name: str | None = None) -> DxfAnalysis:
    """Load and analyze a DXF drawing from disk."""
    path = Path(file_path)
    display_name = source_name or path.name
    _validate_filename(display_name)

    if not path.is_file():
        raise DxfReaderError(f"DXF file was not found: {path}")
    if path.stat().st_size == 0:
        raise DxfReaderError("The uploaded DXF file is empty.")
    if path.stat().st_size > MAX_DXF_FILE_SIZE_BYTES:
        raise DxfReaderError("The DXF file exceeds the 25 MB prototype limit.")

    try:
        document = ezdxf.readfile(path)
        modelspace = document.modelspace()
    except (OSError, UnicodeError, DXFError) as exc:
        raise DxfReaderError(f"ezdxf could not read this DXF file: {exc}") from exc

    entities = list(modelspace)
    type_counts = Counter(entity.dxftype() for entity in entities)
    supported_types = {
        "LINE",
        "CIRCLE",
        "ARC",
        "LWPOLYLINE",
        "POLYLINE",
        "TEXT",
        "MTEXT",
        "DIMENSION",
    }

    circles: list[CircleFeature] = []
    arcs: list[ArcFeature] = []
    dimensions: list[DimensionFeature] = []
    texts: list[TextFeature] = []

    for entity_index, entity in enumerate(entities, start=1):
        entity_type = entity.dxftype()
        layer = str(entity.dxf.layer)

        if entity_type == "CIRCLE":
            center = entity.dxf.center
            radius = float(entity.dxf.radius)
            circles.append(
                CircleFeature(
                    entity_index=entity_index,
                    layer=layer,
                    center=Point2D(x=float(center.x), y=float(center.y)),
                    radius=radius,
                    diameter=radius * 2.0,
                )
            )
        elif entity_type == "ARC":
            center = entity.dxf.center
            arcs.append(
                ArcFeature(
                    entity_index=entity_index,
                    layer=layer,
                    center=Point2D(x=float(center.x), y=float(center.y)),
                    radius=float(entity.dxf.radius),
                    start_angle=float(entity.dxf.start_angle),
                    end_angle=float(entity.dxf.end_angle),
                )
            )
        elif entity_type == "DIMENSION":
            raw_text = str(entity.dxf.text)
            text_override = None if raw_text in {"", "<>"} else raw_text
            dimension_code = int(entity.dxf.dimtype) & 0x0F
            dimensions.append(
                DimensionFeature(
                    entity_index=entity_index,
                    layer=layer,
                    dimension_type=DIMENSION_TYPE_NAMES.get(
                        dimension_code, f"Unknown ({dimension_code})"
                    ),
                    measurement=_read_measurement(entity),
                    text_override=text_override,
                    style=str(entity.dxf.dimstyle),
                )
            )
        elif entity_type in {"TEXT", "MTEXT"}:
            texts.append(
                TextFeature(
                    entity_index=entity_index,
                    entity_type=entity_type,
                    layer=layer,
                    content=_read_text(entity, entity_type),
                )
            )

    units_code = int(document.header.get("$INSUNITS", 0))
    layers = tuple(sorted(str(layer.dxf.name) for layer in document.layers))
    other_count = sum(
        count for entity_type, count in type_counts.items() if entity_type not in supported_types
    )

    return DxfAnalysis(
        source_name=display_name,
        dxf_version=str(document.dxfversion),
        units_code=units_code,
        units_name=DXF_UNIT_NAMES.get(units_code, f"Unknown ({units_code})"),
        layers=layers,
        entity_counts=EntityCounts(
            total=len(entities),
            lines=type_counts["LINE"],
            circles=type_counts["CIRCLE"],
            arcs=type_counts["ARC"],
            lightweight_polylines=type_counts["LWPOLYLINE"],
            polylines=type_counts["POLYLINE"],
            text=type_counts["TEXT"],
            multiline_text=type_counts["MTEXT"],
            dimensions=type_counts["DIMENSION"],
            other=other_count,
        ),
        extents=_drawing_extents(modelspace),
        circles=tuple(circles),
        arcs=tuple(arcs),
        dimensions=tuple(dimensions),
        texts=tuple(texts),
        entity_types=dict(sorted(type_counts.items())),
    )


def analyze_dxf_bytes(data: bytes, filename: str) -> DxfAnalysis:
    """Safely analyze uploaded DXF bytes using a temporary file."""
    suffix = _validate_filename(filename)
    if not data:
        raise DxfReaderError("The uploaded DXF file is empty.")
    if len(data) > MAX_DXF_FILE_SIZE_BYTES:
        raise DxfReaderError("The DXF file exceeds the 25 MB prototype limit.")

    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(suffix=suffix, delete=False) as temporary_file:
            temporary_file.write(data)
            temporary_path = Path(temporary_file.name)
        return analyze_dxf_file(temporary_path, source_name=filename)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

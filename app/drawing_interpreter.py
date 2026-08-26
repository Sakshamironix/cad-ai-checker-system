
"""Convert raw DXF analysis into structured engineering requirements."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re

from app.dxf_reader import DxfAnalysis, Point2D

NUMBER_PATTERN = r"\d+(?:\.\d+)?"
SIGNED_NUMBER_PATTERN = r"[+-]?\d+(?:\.\d+)?"

GENERAL_TOLERANCE_PATTERN = re.compile(
    rf"(?:GENERAL\s+)?TOL(?:ERANCE)?\s*[:=]?\s*(?:±|\+/-|\+-)\s*({NUMBER_PATTERN})",
    re.IGNORECASE,
)
ASYMMETRIC_TOLERANCE_PATTERN = re.compile(
    rf"\+\s*({NUMBER_PATTERN})\s*/?\s*-\s*({NUMBER_PATTERN})",
    re.IGNORECASE,
)
SYMMETRIC_TOLERANCE_PATTERN = re.compile(
    rf"(?:±|\+/-|\+-)\s*({NUMBER_PATTERN})",
    re.IGNORECASE,
)
NOMINAL_PREFIX_PATTERN = re.compile(
    rf"^\s*(?:\d+\s*[xX]\s*)?(?:⌀|Ø|R)?\s*(<>|{SIGNED_NUMBER_PATTERN})",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Tolerance:
    """Lower and upper deviations from a nominal value."""

    lower_deviation: float
    upper_deviation: float


@dataclass(frozen=True)
class ParsedDimensionText:
    """Nominal value and explicit tolerance parsed from DXF dimension text."""

    nominal_value: float | None
    tolerance: Tolerance | None


@dataclass(frozen=True)
class DimensionRequirement:
    """A normalized engineering dimension requirement."""

    entity_index: int
    dimension_type: str
    classification: str
    nominal_value: float | None
    tolerance: Tolerance | None
    tolerance_source: str | None
    minimum_value: float | None
    maximum_value: float | None
    unit: str
    layer: str
    source_text: str | None


@dataclass(frozen=True)
class HoleCandidateRequirement:
    """A circle that may represent a hole in the engineering drawing."""

    entity_index: int
    layer: str
    center: Point2D
    diameter: float
    radius: float
    unit: str


@dataclass(frozen=True)
class DrawingSizeRequirement:
    """Overall model-space size derived from geometric extents."""

    width: float
    height: float
    unit: str


@dataclass(frozen=True)
class DrawingRequirements:
    """Structured requirements ready for later 2D-to-3D feature matching."""

    source_name: str
    units_name: str
    drawing_size: DrawingSizeRequirement | None
    general_tolerance: Tolerance | None
    dimensions: tuple[DimensionRequirement, ...]
    hole_candidates: tuple[HoleCandidateRequirement, ...]
    notes: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def resolved_dimension_count(self) -> int:
        """Return the number of dimensions with a usable nominal value."""
        return sum(dimension.nominal_value is not None for dimension in self.dimensions)

    @property
    def tolerance_count(self) -> int:
        """Return the number of dimensions with an explicit or general tolerance."""
        return sum(dimension.tolerance is not None for dimension in self.dimensions)

    def to_dict(self) -> dict[str, object]:
        """Convert the interpretation into Streamlit/JSON-friendly values."""
        result = asdict(self)
        result["resolved_dimension_count"] = self.resolved_dimension_count
        result["tolerance_count"] = self.tolerance_count
        return result


def _normalize_text(text: str) -> str:
    """Normalize common AutoCAD control text and whitespace."""
    normalized = text.replace("%%c", "⌀").replace("%%C", "⌀")
    return " ".join(normalized.replace("\\P", " ").split())


def _nominal_from_text(text: str, measured_value: float | None) -> float | None:
    """Read the nominal prefix while avoiding quantity prefixes such as 4X."""
    match = NOMINAL_PREFIX_PATTERN.search(text)
    if match is None or match.group(1) == "<>":
        return measured_value
    try:
        return float(match.group(1))
    except ValueError:
        return measured_value


def parse_dimension_text(
    text: str | None,
    measured_value: float | None,
) -> ParsedDimensionText:
    """Parse common symmetric and asymmetric tolerance formats.

    Supported examples include ``50 ±0.1``, ``50 +/-0.1``,
    ``25 +0.2/-0.1``, ``4X Ø10 ±0.05``, and ``<> ±0.1``.
    """
    if text is None or not text.strip():
        return ParsedDimensionText(nominal_value=measured_value, tolerance=None)

    normalized = _normalize_text(text)
    nominal = _nominal_from_text(normalized, measured_value)

    asymmetric = ASYMMETRIC_TOLERANCE_PATTERN.search(normalized)
    if asymmetric is not None:
        return ParsedDimensionText(
            nominal_value=nominal,
            tolerance=Tolerance(
                lower_deviation=-float(asymmetric.group(2)),
                upper_deviation=float(asymmetric.group(1)),
            ),
        )

    symmetric = SYMMETRIC_TOLERANCE_PATTERN.search(normalized)
    if symmetric is not None:
        deviation = float(symmetric.group(1))
        return ParsedDimensionText(
            nominal_value=nominal,
            tolerance=Tolerance(
                lower_deviation=-deviation,
                upper_deviation=deviation,
            ),
        )

    return ParsedDimensionText(nominal_value=nominal, tolerance=None)


def _find_general_tolerance(notes: tuple[str, ...]) -> Tolerance | None:
    """Find the first supported general tolerance statement in drawing text."""
    for note in notes:
        match = GENERAL_TOLERANCE_PATTERN.search(_normalize_text(note))
        if match is not None:
            deviation = float(match.group(1))
            return Tolerance(lower_deviation=-deviation, upper_deviation=deviation)
    return None


def _classify_dimension(dimension_type: str, source_text: str | None) -> str:
    """Classify a dimension without claiming an unproven 3D feature match."""
    normalized = _normalize_text(source_text or "").upper()
    if dimension_type == "Diameter" or "⌀" in normalized or "Ø" in normalized:
        return "diameter"
    if dimension_type == "Radius" or normalized.startswith("R"):
        return "radius"
    if "Angular" in dimension_type:
        return "angle"
    if dimension_type == "Ordinate":
        return "ordinate"
    return "linear"


def _limits(
    nominal_value: float | None,
    tolerance: Tolerance | None,
) -> tuple[float | None, float | None]:
    """Calculate lower and upper limits when both inputs are available."""
    if nominal_value is None or tolerance is None:
        return None, None
    return (
        nominal_value + tolerance.lower_deviation,
        nominal_value + tolerance.upper_deviation,
    )


def interpret_dxf_analysis(analysis: DxfAnalysis) -> DrawingRequirements:
    """Convert raw DXF entities into basic engineering requirements."""
    notes = tuple(
        annotation.content.strip()
        for annotation in analysis.texts
        if annotation.content.strip()
    )
    general_tolerance = _find_general_tolerance(notes)
    dimensions: list[DimensionRequirement] = []

    for dimension in analysis.dimensions:
        parsed = parse_dimension_text(dimension.text_override, dimension.measurement)
        tolerance = parsed.tolerance or general_tolerance
        tolerance_source: str | None = None
        if parsed.tolerance is not None:
            tolerance_source = "dimension"
        elif general_tolerance is not None:
            tolerance_source = "general note"
        minimum_value, maximum_value = _limits(parsed.nominal_value, tolerance)

        dimensions.append(
            DimensionRequirement(
                entity_index=dimension.entity_index,
                dimension_type=dimension.dimension_type,
                classification=_classify_dimension(
                    dimension.dimension_type,
                    dimension.text_override,
                ),
                nominal_value=parsed.nominal_value,
                tolerance=tolerance,
                tolerance_source=tolerance_source,
                minimum_value=minimum_value,
                maximum_value=maximum_value,
                unit=analysis.units_name,
                layer=dimension.layer,
                source_text=dimension.text_override,
            )
        )

    hole_candidates = tuple(
        HoleCandidateRequirement(
            entity_index=circle.entity_index,
            layer=circle.layer,
            center=circle.center,
            diameter=circle.diameter,
            radius=circle.radius,
            unit=analysis.units_name,
        )
        for circle in analysis.circles
    )

    drawing_size = None
    if analysis.extents is not None:
        drawing_size = DrawingSizeRequirement(
            width=analysis.extents.width,
            height=analysis.extents.height,
            unit=analysis.units_name,
        )

    warnings: list[str] = []
    if analysis.units_code == 0:
        warnings.append("The DXF is unitless; numeric requirements cannot be safely scaled.")
    if drawing_size is None:
        warnings.append("No measurable model-space drawing extents were found.")
    if not dimensions:
        warnings.append("No DXF DIMENSION entities were found.")
    if any(dimension.nominal_value is None for dimension in dimensions):
        warnings.append("One or more dimensions do not contain a usable nominal value.")
    if any(dimension.tolerance is None for dimension in dimensions):
        warnings.append("One or more dimensions have no explicit or general tolerance.")
    if not hole_candidates:
        warnings.append("No circle entities were found as possible hole candidates.")

    return DrawingRequirements(
        source_name=analysis.source_name,
        units_name=analysis.units_name,
        drawing_size=drawing_size,
        general_tolerance=general_tolerance,
        dimensions=tuple(dimensions),
        hole_candidates=hole_candidates,
        notes=notes,
        warnings=tuple(warnings),
    )

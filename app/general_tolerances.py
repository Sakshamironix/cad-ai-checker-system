"""Structured provisional tolerances used when a drawing gives no explicit limit."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Final


@dataclass(frozen=True)
class GeneralToleranceSet:
    """Project-level fallback limits grouped by engineering comparison type.

    These values are deliberately not presented as an ISO/JIS tolerance class. They are
    temporary project settings until the approved general-tolerance table is supplied.
    """

    linear_mm: float
    circular_mm: float
    profile_mm: float
    position_mm: float
    name: str = "Provisional project set / 暫定プロジェクト公差セット"
    provisional: bool = True
    applied: bool = True

    def __post_init__(self) -> None:
        values = {
            "linear_mm": self.linear_mm,
            "circular_mm": self.circular_mm,
            "profile_mm": self.profile_mm,
            "position_mm": self.position_mm,
        }
        for field_name, value in values.items():
            if value <= 0:
                raise ValueError(f"{field_name} must be greater than zero")

    @classmethod
    def uniform(cls, tolerance_mm: float) -> GeneralToleranceSet:
        """Build a compatibility set from the former single prototype tolerance."""
        return cls(
            linear_mm=tolerance_mm,
            circular_mm=tolerance_mm,
            profile_mm=tolerance_mm,
            position_mm=tolerance_mm,
        )

    def for_dimension_classification(self, classification: str) -> float:
        """Return the applicable fallback limit for a supported dimension class."""
        if classification == "linear":
            return self.linear_mm
        if classification in {"diameter", "radius"}:
            return self.circular_mm
        raise ValueError(f"No general tolerance is routed for '{classification}'.")

    def with_application(self, applied: bool) -> GeneralToleranceSet:
        """Return the background rule set with its application state changed."""
        return replace(self, applied=applied)

    def to_dict(self) -> dict[str, object]:
        """Return JSON-friendly settings for reports and audit evidence."""
        return asdict(self)


PROVISIONAL_GENERAL_TOLERANCES: Final = GeneralToleranceSet(
    linear_mm=0.1,
    circular_mm=0.1,
    profile_mm=0.1,
    position_mm=0.1,
)

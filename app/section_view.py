"""Deterministic section-view evidence and validation helpers."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from app.view_classification import ViewClassification

@dataclass(frozen=True)
class SectionInterpretation:
    view_id: str; section_kind: str; evidence: tuple[str, ...]; is_section: bool
    def to_dict(self) -> dict[str, object]: return asdict(self)

def interpret_section(classification: ViewClassification) -> SectionInterpretation:
    is_section = classification.detected_type in {"Full section", "Half section"}
    return SectionInterpretation(classification.view_id, classification.detected_type if is_section else "Not section", classification.evidence, is_section)
